#!/usr/bin/env python3
"""Validate the frozen M14 competition protocol against qualified package evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema

import validate_opponent_runtime_evidence


class CompetitionManifestError(ValueError):
    """The competition preregistration violates a fairness or identity invariant."""


@dataclass(frozen=True)
class CompetitionManifestSummary:
    tournament_opponents: int
    controls: int
    audit_pool: int
    seeds: int
    paired_legs: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CompetitionManifestError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompetitionManifestError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CompetitionManifestError(f"cannot hash {path}: {exc}") from exc


def derive_seed(domain: str, set_name: str, ordinal: int) -> int:
    digest = hashlib.sha256(f"{domain}:{set_name}:{ordinal}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def validate(
    root: pathlib.Path,
    manifest_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
) -> CompetitionManifestSummary:
    root = root.resolve()
    manifest_path = manifest_path or root / "config/v2/m14-competition-manifest.json"
    schema_path = schema_path or root / "docs/project/schema/v2-competition-manifest.schema.json"
    manifest = load_json(manifest_path)
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(manifest)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise CompetitionManifestError(f"competition manifest schema failed at {location}: {exc.message}") from exc
    require(manifest["schema_sha256"] == sha256_file(schema_path), "competition schema SHA-256 mismatch")

    research_path = root / "config/v2/research-baseline.json"
    setting_path = root / "config/v2/setting-inventory.json"
    runtime_path = root / "config/v2/opponent-runtime-evidence.json"
    package_path = root / "config/v2/opponent-package-evidence.json"
    require(manifest["identity"]["research_baseline_sha256"] == sha256_file(research_path), "competition/research baseline SHA-256 mismatch")
    require(manifest["identity"]["setting_inventory_sha256"] == sha256_file(setting_path), "competition/setting inventory SHA-256 mismatch")
    require(manifest["identity"]["runtime_evidence_sha256"] == sha256_file(runtime_path), "competition/runtime evidence SHA-256 mismatch")
    try:
        validate_opponent_runtime_evidence.validate(root)
    except validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError as exc:
        raise CompetitionManifestError(f"competition runtime authority failed: {exc}") from exc

    source = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    runtime = load_json(runtime_path)
    package = load_json(package_path)
    require(manifest["identity"]["engine_source"] == {key: source[key] for key in ("release", "commit", "tree")}, "competition engine source drifted")
    require(manifest["identity"]["executable"] == runtime["executable"], "competition executable drifted from runtime qualification")

    runtime_by_name = {item["name"]: item for item in runtime["results"]}
    package_by_name = {item["name"]: item for item in package["results"]}
    dispositions = manifest["audit_pool_disposition"]
    disposition_names = [item["name"] for item in dispositions]
    require(disposition_names == sorted(disposition_names), "competition audit dispositions are not bytewise sorted")
    require(len(disposition_names) == len(set(disposition_names)), "competition audit dispositions contain duplicates")
    require(set(disposition_names) == set(runtime_by_name), "competition audit dispositions do not cover the runtime audit pool exactly")
    for item in dispositions:
        qualified = runtime_by_name[item["name"]]
        expected = {
            "name": qualified["name"],
            "content_unique_id": qualified["content_unique_id"],
            "admission": qualified["admission"],
            "reason_code": qualified["reason_code"],
        }
        require(item == expected, f"{item['name']} competition admission drifted from runtime evidence")

    admitted_by_type = {
        "tournament": sorted(name for name, item in runtime_by_name.items() if item["admission"] == "TOURNAMENT"),
        "controls": sorted(name for name, item in runtime_by_name.items() if item["admission"] == "CONTROL"),
    }
    for roster_name, admission in (("tournament", "TOURNAMENT"), ("controls", "CONTROL")):
        participants = manifest["roster"][roster_name]
        names = [item["name"] for item in participants]
        require(names == sorted(names), f"competition {roster_name} roster is not bytewise sorted")
        require(names == admitted_by_type[roster_name], f"competition {roster_name} roster is not the exact admitted set")
        for item in participants:
            runtime_item = runtime_by_name[item["name"]]
            package_item = package_by_name[item["name"]]
            require(item["admission"] == admission, f"{item['name']} is in the wrong competition roster")
            require(item["content_unique_id"] == runtime_item["content_unique_id"], f"{item['name']} content ID drifted")
            require(item["runtime_evidence_sha256"] == runtime_item["evidence_sha256"], f"{item['name']} runtime evidence digest drifted")
            require(package_item["outcome"] == "LOCKED", f"{item['name']} lacks a locked package")
            require(item["package_evidence_sha256"] == package_item["evidence_sha256"], f"{item['name']} package evidence digest drifted")

    domain = manifest["seed_protocol"]["domain"]
    all_seeds: list[int] = []
    for set_name, seed_set in manifest["seed_protocol"]["sets"].items():
        expected = [derive_seed(domain, set_name, seed_set["ordinal_start"] + index) for index in range(len(seed_set["seeds"]))]
        require(seed_set["seeds"] == expected, f"competition {set_name} seeds do not match deterministic derivation")
        all_seeds.extend(seed_set["seeds"])
    require(len(all_seeds) == len(set(all_seeds)), "competition seed sets overlap")
    require(len(manifest["seed_protocol"]["sets"]["final"]["seeds"]) >= 20, "competition final seed set is underpowered by contract")

    legs = manifest["fairness"]["paired_legs"]
    observed_legs = {
        (item["leg"], item["rl_slot"], item["opponent_slot"], item["rl_start_delay_days"], item["opponent_start_delay_days"])
        for item in legs
    }
    expected_legs = {
        ("A", 0, 1, 0, 365),
        ("B", 1, 0, 0, 365),
        ("C", 0, 1, 365, 0),
        ("D", 1, 0, 365, 0),
    }
    require(observed_legs == expected_legs, "competition legs do not symmetrically cross slots and start delays")
    require(all(item["rl_slot"] != item["opponent_slot"] for item in legs), "competition assigns both participants to one company slot")

    research = load_json(research_path)
    require(manifest["scenario_contract"]["allowed_native_side_lengths"] == research["maps"]["native_side_lengths"], "competition map sizes drifted from research inventory")
    require(manifest["scenario_contract"]["allowed_climates"] == ["temperate", "sub-arctic", "sub-tropical", "toyland"], "competition climate set is incomplete or reordered")
    required_run_fields = {
        "competition_manifest_sha256", "engine_source_tree", "executable_sha256", "policy_package_sha256",
        "opponent_package_evidence_sha256", "opponent_runtime_evidence_sha256", "map_manifest_sha256",
        "settings_manifest_sha256", "content_manifest_sha256", "map_seed", "simulation_seed", "rl_company_slot",
        "opponent_company_slot", "rl_start_delay_days", "opponent_start_delay_days", "calendar_days",
    }
    require(set(manifest["scenario_contract"]["required_run_identity_fields"]) == required_run_fields, "competition per-run identity fields are incomplete")
    required_denials = {"opponent_ai_memory", "opponent_pathfinder_state", "future_random_events", "final_suite_label_or_seed_as_policy_input"}
    require(required_denials <= set(manifest["policy_visibility"]["deny"]), "competition policy visibility permits privileged state")
    require(not (set(manifest["policy_visibility"]["allow"]) & set(manifest["policy_visibility"]["deny"])), "competition visibility allow/deny lists overlap")
    expected_secondary = {"survival_rate", "operating_profit", "delivered_cargo_units", "delivered_passengers", "delivered_mail", "vehicle_count", "infrastructure_count"}
    require(set(manifest["scoring"]["secondary"]) == expected_secondary, "competition secondary scoring inventory is incomplete")

    return CompetitionManifestSummary(
        tournament_opponents=len(manifest["roster"]["tournament"]),
        controls=len(manifest["roster"]["controls"]),
        audit_pool=len(dispositions),
        seeds=len(all_seeds),
        paired_legs=len(legs),
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--manifest", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        summary = validate(args.root, args.manifest, args.schema)
        print(
            f"V2_COMPETITION_MANIFEST=PASS tournament={summary.tournament_opponents} controls={summary.controls} "
            f"audit_pool={summary.audit_pool} seeds={summary.seeds} legs={summary.paired_legs}"
        )
        return 0
    except (CompetitionManifestError, OSError) as exc:
        print(f"V2_COMPETITION_MANIFEST=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
