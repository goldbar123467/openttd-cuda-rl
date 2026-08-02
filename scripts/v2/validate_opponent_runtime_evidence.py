#!/usr/bin/env python3
"""Validate the M14 package-to-runtime opponent qualification matrix."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Any

import jsonschema

import qualify_ai_runtime
import validate_opponent_package_evidence


class OpponentRuntimeEvidenceError(ValueError):
    """The M14 opponent runtime evidence matrix violates an invariant."""


@dataclass(frozen=True)
class RuntimeEvidenceSummary:
    opponents: int
    package_rejected: int
    runtime_rejected: int
    tournament: int
    control: int
    scenario_required: int
    live_artifacts: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OpponentRuntimeEvidenceError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OpponentRuntimeEvidenceError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise OpponentRuntimeEvidenceError(f"cannot hash {path}: {exc}") from exc


def vehicle_projection(company: dict[str, Any] | None) -> dict[str, int] | None:
    if company is None:
        return None
    return {
        "train": company["trains"],
        "road": company["road_vehicles"],
        "air": company["aircraft"],
        "ship": company["ships"],
    }


def elapsed_days(manifest: dict[str, Any]) -> int | None:
    start = manifest["observations"]["start_date"]
    end = manifest["observations"]["post_load_date"]
    if start is None or end is None:
        return None
    return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days


def validate(
    root: pathlib.Path,
    evidence_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_base: pathlib.Path | None = None,
    openttd: pathlib.Path | None = None,
) -> RuntimeEvidenceSummary:
    root = root.resolve()
    evidence_path = evidence_path or root / "config/v2/opponent-runtime-evidence.json"
    schema_path = schema_path or root / "docs/project/schema/v2-opponent-runtime-evidence.schema.json"
    evidence = load_json(evidence_path)
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(evidence)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise OpponentRuntimeEvidenceError(f"runtime evidence schema failed at {location}: {exc.message}") from exc
    require(evidence["schema_sha256"] == sha256_file(schema_path), "runtime evidence schema SHA-256 mismatch")
    source = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    require(evidence["engine_source"] == {key: source[key] for key in ("release", "commit", "tree")}, "runtime evidence engine source drifted")
    package_path = root / "config/v2/opponent-package-evidence.json"
    require(evidence["package_evidence_sha256"] == sha256_file(package_path), "runtime/package evidence SHA-256 mismatch")
    package_evidence = load_json(package_path)
    package_results = {item["name"]: item for item in package_evidence["results"]}
    baseline = load_json(root / "config/v2/research-baseline.json")
    baseline_by_name = {item["name"]: item for item in baseline["opponents"]}

    results = evidence["results"]
    names = [item["name"] for item in results]
    require(names == sorted(names), "runtime evidence results are not bytewise sorted")
    require(len(names) == len(set(names)), "runtime evidence has duplicate opponents")
    require(set(names) == set(baseline_by_name), "runtime evidence does not cover the ten-AI audit pool exactly")
    require(len({item["artifact_dir"] for item in results}) == len(results), "runtime evidence has duplicate artifact directories")

    for result in results:
        name = result["name"]
        require(result["content_unique_id"] == baseline_by_name[name]["content_id"], f"{name} runtime content ID drifted")
        package = package_results[name]
        if result["phase"] == "PACKAGE":
            require(package["outcome"] == "REJECTED", f"{name} runtime matrix rejects a locked package before runtime")
            require(result["evidence_sha256"] == package["evidence_sha256"], f"{name} package rejection digest drifted")
            require(result["artifact_dir"] == package["artifact_dir"], f"{name} package rejection artifact drifted")
        else:
            require(package["outcome"] == "LOCKED", f"{name} runtime result has no package lock")
            vehicles = result["vehicles"]
            vehicle_count = 0 if vehicles is None else sum(vehicles.values())
            if result["outcome"] == "QUALIFIED_ACTIVE":
                require(result["admission"] == "TOURNAMENT" and vehicle_count > 0 and result["elapsed_days"] >= 30, f"{name} active admission lacks 30-day vehicle activity")
                require(result["reason_code"] is None, f"{name} active admission has a rejection reason")
            elif result["outcome"] == "QUALIFIED_HEALTHY_INACTIVE":
                require(result["admission"] == "SCENARIO_REQUIRED" and vehicle_count == 0 and result["elapsed_days"] >= 30, f"{name} inactive admission policy mismatch")
                require(result["reason_code"] is None, f"{name} inactive result has a rejection reason")
            elif result["outcome"] == "QUALIFIED_CONTROL":
                require(name == "NoOpAI" and result["admission"] == "CONTROL" and vehicle_count == 0 and result["elapsed_days"] >= 2, "control admission is not an inactive NoOpAI run")
                require(result["reason_code"] is None, "control result has a rejection reason")
            else:
                require(result["admission"] == "EXCLUDED" and result["reason_code"] is not None, f"{name} runtime rejection is not excluded/reasoned")

    counts = Counter(result["outcome"] for result in results)
    admissions = Counter(result["admission"] for result in results)
    require(counts == {"PACKAGE_REJECTED": 2, "QUALIFIED_ACTIVE": 2, "QUALIFIED_HEALTHY_INACTIVE": 3, "REJECTED": 2, "QUALIFIED_CONTROL": 1}, f"runtime outcome inventory drifted: {dict(counts)}")
    require(admissions == {"EXCLUDED": 4, "TOURNAMENT": 2, "SCENARIO_REQUIRED": 3, "CONTROL": 1}, f"runtime admission inventory drifted: {dict(admissions)}")

    if artifact_base is not None:
        artifact_base = artifact_base.resolve()
        try:
            validate_opponent_package_evidence.validate(root, artifact_base=artifact_base, openttd=openttd)
        except validate_opponent_package_evidence.OpponentEvidenceError as exc:
            raise OpponentRuntimeEvidenceError(f"live package evidence failed: {exc}") from exc
        if openttd is not None:
            openttd = openttd.resolve()
            require(sha256_file(openttd) == evidence["executable"]["sha256"], "runtime evidence executable SHA-256 mismatch")
            require(openttd.stat().st_size == evidence["executable"]["size"], "runtime evidence executable size mismatch")
        for result in results:
            evidence_file = artifact_base / result["artifact_dir"] / result["evidence_file"]
            require(evidence_file.is_file() and not evidence_file.is_symlink(), f"runtime evidence file is missing or a symlink: {evidence_file}")
            require(sha256_file(evidence_file) == result["evidence_sha256"], f"{result['name']} runtime evidence SHA-256 mismatch")
            if result["phase"] == "PACKAGE":
                continue
            try:
                manifest = qualify_ai_runtime.validate_manifest(root, evidence_file, openttd=openttd)
            except qualify_ai_runtime.AIRuntimeError as exc:
                raise OpponentRuntimeEvidenceError(f"{result['name']} runtime manifest failed: {exc}") from exc
            require(manifest["package_lock"]["catalog_name"] == result["name"], f"{result['name']} manifest name mismatch")
            require(manifest["package_lock"]["catalog_unique_id"] == result["content_unique_id"], f"{result['name']} manifest content ID mismatch")
            require(manifest["outcome"] == result["outcome"], f"{result['name']} manifest outcome mismatch")
            require(elapsed_days(manifest) == result["elapsed_days"], f"{result['name']} elapsed-day mismatch")
            require(vehicle_projection(manifest["observations"]["company_after_load"]) == result["vehicles"], f"{result['name']} vehicle projection mismatch")
            require(manifest["resources"]["max_rss_kib"] == result["max_rss_kib"], f"{result['name']} RSS evidence mismatch")
            save = manifest["observations"]["save"]
            require((None if save is None else save["sha256"]) == result["save_sha256"], f"{result['name']} save digest mismatch")
            transcript = (evidence_file.parent / qualify_ai_runtime.TRANSCRIPT_NAME).read_text(encoding="utf-8")
            if result["reason_code"] == "declared-identity-not-listed":
                require(not manifest["checks"]["declared_identity_listed"] and "Compile error" in transcript, f"{result['name']} identity rejection lacks compile-error evidence")
            elif result["reason_code"] == "script-crash-missing-library":
                require(not manifest["checks"]["no_script_crash"] and "couldn't find library" in transcript, f"{result['name']} missing-library rejection lacks crash evidence")

    return RuntimeEvidenceSummary(
        opponents=len(results),
        package_rejected=counts["PACKAGE_REJECTED"],
        runtime_rejected=counts["REJECTED"],
        tournament=admissions["TOURNAMENT"],
        control=admissions["CONTROL"],
        scenario_required=admissions["SCENARIO_REQUIRED"],
        live_artifacts=artifact_base is not None,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--evidence", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    parser.add_argument("--artifact-base", type=pathlib.Path)
    parser.add_argument("--openttd", type=pathlib.Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        summary = validate(args.root, args.evidence, args.schema, artifact_base=args.artifact_base, openttd=args.openttd)
        print(
            f"V2_OPPONENT_RUNTIME=PASS opponents={summary.opponents} package_rejected={summary.package_rejected} "
            f"runtime_rejected={summary.runtime_rejected} tournament={summary.tournament} control={summary.control} "
            f"scenario_required={summary.scenario_required} live={str(summary.live_artifacts).lower()}"
        )
        return 0
    except (OpponentRuntimeEvidenceError, OSError) as exc:
        print(f"V2_OPPONENT_RUNTIME=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
