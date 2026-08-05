#!/usr/bin/env python3
"""Freeze and validate representative M15 candidate/action evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema

from artifact_context import ArtifactContext, ArtifactRequirement
import qualify_m15_action
import qualify_m15_native_reset
import qualify_m15_observation
import run_m15_action_evidence


SCHEMA = pathlib.Path("docs/project/schema/v2-m15-action-evidence.schema.json")
CONFIG = pathlib.Path("config/v2/m15-action-evidence.json")
CONTRACT = pathlib.Path("config/v2/m15-scalable-contract.json")
ACTION_CONTRACT = pathlib.Path("config/v2/m15-action-contract.json")
ACTION_SOURCE = pathlib.Path("config/v2/m15-action-source.json")
METADATA_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-candidate-metadata.schema.json")
REQUEST_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-action-request.schema.json")
RESULT_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-action-result.schema.json")
MAP_DIRS = ["reset-0064x0064", "reset-0064x0256", "reset-0512x0128", "reset-1024x1024"]
REPEAT_DIR = "repeat-0064x0064"
ACTION_DIRS = [item[0] for item in run_m15_action_evidence.POSITIVE_CASES + run_m15_action_evidence.NEGATIVE_CASES]
LOGICAL_ARTIFACT_SET = "v2-m15-action-evidence-a"
LIVE_CONSUMER = "m15-action-evidence"


class M15ActionEvidenceError(ValueError):
    """The frozen M15 action evidence is missing or inconsistent."""


@dataclass(frozen=True)
class M15ActionEvidenceSummary:
    map_cases: int
    action_cases: int
    passed: int
    maximum_rss_kib: int
    live: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15ActionEvidenceError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15ActionEvidenceError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15ActionEvidenceError(f"cannot hash {path}: {exc}") from exc


def map_case_from_artifact(root: pathlib.Path, artifact_root: pathlib.Path, directory: str) -> dict[str, Any]:
    artifact = artifact_root / directory
    evidence_path = artifact / qualify_m15_action.EVIDENCE_NAME
    evidence = load_json(evidence_path)
    manifest = load_json(artifact / qualify_m15_action.MANIFEST_NAME)
    projection = qualify_m15_native_reset.validate_projection(root, manifest, artifact / qualify_m15_action.PROJECTION_NAME)
    observation = load_json(artifact / qualify_m15_action.OBSERVATION_METADATA_NAME)
    qualify_m15_observation.validate_observation(root, artifact, manifest, projection)
    summary = qualify_m15_action.validate_candidates(root, artifact, manifest, observation, projection)
    require(evidence["outcome"] == "PASS" and (evidence["width"], evidence["height"]) == (summary.width, summary.height), f"action map evidence outcome/dimensions drifted: {directory}")
    require(evidence["candidate_binary_sha256"] == summary.binary_sha256 and evidence["selected_candidates"] == summary.selected and evidence["total_legal"] == summary.total_legal, f"action map evidence summary drifted: {directory}")
    for key, filename in (("manifest_sha256", qualify_m15_action.MANIFEST_NAME), ("projection_sha256", qualify_m15_action.PROJECTION_NAME), ("candidate_metadata_sha256", qualify_m15_action.CANDIDATE_METADATA_NAME)):
        require(evidence[key] == sha256_file(artifact / filename), f"action map evidence {key} drifted: {directory}")
    return {
        "artifact_dir": directory, "width": summary.width, "height": summary.height, "seed": evidence["seed"], "outcome": evidence["outcome"],
        "candidate_bytes": qualify_m15_action.CANDIDATE_BYTES, "selected_candidates": summary.selected, "total_legal": summary.total_legal,
        "omitted_legal": summary.total_legal - summary.selected, "maximum_rss_kib": evidence["maximum_rss_kib"], "wall_seconds": evidence["wall_seconds"],
        "manifest_sha256": evidence["manifest_sha256"], "projection_sha256": evidence["projection_sha256"], "observation_sha256": evidence["observation_sha256"],
        "candidate_metadata_sha256": evidence["candidate_metadata_sha256"], "candidate_binary_sha256": evidence["candidate_binary_sha256"],
        "snapshot_token": evidence["snapshot_token"], "evidence_sha256": sha256_file(evidence_path),
        "transcript_sha256": sha256_file(artifact / qualify_m15_action.TRANSCRIPT_NAME), "oracle_checks": evidence["oracle_checks"],
    }


def action_case_from_artifact(root: pathlib.Path, artifact_root: pathlib.Path, directory: str) -> dict[str, Any]:
    artifact = artifact_root / directory
    request = load_json(artifact / qualify_m15_action.REQUEST_NAME)
    result = qualify_m15_action.validate_result(root, artifact, request)
    evidence = load_json(artifact / qualify_m15_action.EVIDENCE_NAME)
    category = directory.split("-", 1)[0]
    require(category in ("positive", "negative") and evidence["status"] == result["status"], f"action case category/status drifted: {directory}")
    return {
        "artifact_dir": directory, "category": category, "family_index": request["family_index"], "candidate_row": request["candidate_row"],
        "status": result["status"], "mutated": result["state_sha256_before"] != result["state_sha256_after"],
        "command_count": len(result["native_commands"]), "tick_delta": result["tick_after"] - result["tick_before"],
        "request_sha256": sha256_file(artifact / qualify_m15_action.REQUEST_NAME), "result_sha256": sha256_file(artifact / qualify_m15_action.RESULT_NAME),
        "evidence_sha256": sha256_file(artifact / qualify_m15_action.EVIDENCE_NAME),
    }


def summarize(map_cases: list[dict[str, Any]], action_cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "map_cases": len(map_cases), "action_cases": len(action_cases), "passed": len(map_cases) + len(action_cases),
        "candidate_bytes": qualify_m15_action.CANDIDATE_BYTES, "maximum_rss_kib": max(item["maximum_rss_kib"] for item in map_cases),
        "maximum_wall_seconds": max(item["wall_seconds"] for item in map_cases), "maximum_total_legal": max(item["total_legal"] for item in map_cases),
        "maximum_omitted_legal": max(item["omitted_legal"] for item in map_cases),
        "positive_actions": sum(item["category"] == "positive" for item in action_cases), "negative_actions": sum(item["category"] == "negative" for item in action_cases),
    }


def _recorded_artifact_set(config: dict[str, Any]) -> str:
    recorded_base = config["artifact_base_hint"]
    parts = recorded_base.split("/")
    require(
        recorded_base.startswith("/")
        and not recorded_base.startswith("//")
        and all(part not in {"", ".", ".."} for part in parts[1:]),
        "M15 action recorded artifact base is not an absolute normalized POSIX path",
    )
    require(
        config["artifact_root"] == LOGICAL_ARTIFACT_SET,
        "M15 action logical artifact set drifted",
    )
    return config["artifact_root"]


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    config = load_json(root / CONFIG)
    logical_set = _recorded_artifact_set(config)
    requirements: list[ArtifactRequirement] = []

    map_records = {item["artifact_dir"]: item for item in config["map_cases"]}
    for directory in (*MAP_DIRS, REPEAT_DIR):
        record = map_records.get(directory)
        if record is None:
            record = config["determinism"]
        digests = {
            "action-evidence.json": record.get("evidence_sha256"),
            "reset-manifest.json": record.get("manifest_sha256"),
            "reset-projection.json": record.get("projection_sha256"),
            "observation-metadata.json": None,
            "observation-metadata.bin": record["observation_sha256"],
            "candidate-metadata.json": record["candidate_metadata_sha256"],
            "candidate-metadata.bin": record["candidate_binary_sha256"],
            "openttd-action.log": record.get("transcript_sha256"),
        }
        for filename, digest in digests.items():
            requirements.append(ArtifactRequirement(
                logical_set,
                f"{directory}/{filename}",
                "file",
                LIVE_CONSUMER,
                digest,
            ))

    for record in config["action_cases"]:
        directory = record["artifact_dir"]
        for filename, field in (
            ("action-request.json", "request_sha256"),
            ("action-result.json", "result_sha256"),
            ("action-evidence.json", "evidence_sha256"),
        ):
            requirements.append(ArtifactRequirement(
                logical_set,
                f"{directory}/{filename}",
                "file",
                LIVE_CONSUMER,
                record[field],
            ))
    return tuple(requirements)


def freeze(root: pathlib.Path, artifact_root: pathlib.Path, output: pathlib.Path) -> pathlib.Path:
    root, artifact_root, output = root.resolve(), artifact_root.resolve(), output.resolve()
    require(artifact_root.is_dir() and not artifact_root.is_symlink(), "action artifact root is missing or a symlink")
    require(not output.exists() and not output.is_symlink(), "refusing to overwrite frozen action evidence")
    map_cases = [map_case_from_artifact(root, artifact_root, directory) for directory in MAP_DIRS]
    repeat = map_case_from_artifact(root, artifact_root, REPEAT_DIR)
    primary = map_cases[0]
    for key in ("observation_sha256", "candidate_metadata_sha256", "candidate_binary_sha256", "snapshot_token"):
        require(repeat[key] == primary[key], f"action deterministic repeat {key} differs")
    action_cases = [action_case_from_artifact(root, artifact_root, directory) for directory in ACTION_DIRS]
    source = load_json(root / ACTION_SOURCE)
    value = {
        "$schema": "../../docs/project/schema/v2-m15-action-evidence.schema.json", "schema_version": "openttd-rl-v2-m15-action-evidence-1",
        "schema_sha256": sha256_file(root / SCHEMA), "snapshot_date": "2026-08-02", "contract_sha256": sha256_file(root / CONTRACT),
        "action_contract_sha256": sha256_file(root / ACTION_CONTRACT), "action_source_sha256": sha256_file(root / ACTION_SOURCE),
        "metadata_schema_sha256": sha256_file(root / METADATA_SCHEMA), "request_schema_sha256": sha256_file(root / REQUEST_SCHEMA),
        "result_schema_sha256": sha256_file(root / RESULT_SCHEMA), "executable": {key: source["build"]["executable"][key] for key in ("sha256", "size")},
        "artifact_base_hint": str(artifact_root.parent), "artifact_root": artifact_root.name, "map_cases": map_cases, "action_cases": action_cases,
        "determinism": {"primary_artifact_dir": MAP_DIRS[0], "repeat_artifact_dir": REPEAT_DIR, **{key: primary[key] for key in ("observation_sha256", "candidate_metadata_sha256", "candidate_binary_sha256", "snapshot_token")}, "byte_identical": True},
        "policy": {"exact_candidate_bytes": qualify_m15_action.CANDIDATE_BYTES, "bounded_streaming_top_k": True, "full_native_domain_counts": True,
            "rectangular_maps": True, "maximum_budget_map": True, "all_initial_families_executed": True, "all_twelve_families_executed": False,
            "typed_invalid_no_mutation": True, "g15_pass_claim": False},
        "summary": summarize(map_cases, action_cases),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    validate(
        root,
        output,
        artifact_context=ArtifactContext.live(artifact_root.parent),
    )
    return output


def validate(
    root: pathlib.Path,
    config_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_context: ArtifactContext | None = None,
) -> M15ActionEvidenceSummary:
    context = artifact_context or ArtifactContext.offline()
    root = root.resolve()
    config_path, schema_path = config_path or root / CONFIG, schema_path or root / SCHEMA
    config, schema = load_json(config_path), load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(config)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15ActionEvidenceError(f"M15 action evidence schema failed at {location}: {exc.message}") from exc
    require(config["schema_sha256"] == sha256_file(schema_path), "M15 action evidence schema SHA-256 mismatch")
    for field, path in (("contract_sha256", CONTRACT), ("action_contract_sha256", ACTION_CONTRACT), ("action_source_sha256", ACTION_SOURCE),
                        ("metadata_schema_sha256", METADATA_SCHEMA), ("request_schema_sha256", REQUEST_SCHEMA), ("result_schema_sha256", RESULT_SCHEMA)):
        require(config[field] == sha256_file(root / path), f"M15 action evidence {field} drifted")
    source = load_json(root / ACTION_SOURCE)
    require(config["executable"] == {key: source["build"]["executable"][key] for key in ("sha256", "size")}, "M15 action executable identity drifted")
    require([item["artifact_dir"] for item in config["map_cases"]] == MAP_DIRS, "M15 action map artifact directories drifted")
    require([item["artifact_dir"] for item in config["action_cases"]] == ACTION_DIRS, "M15 action case directories drifted")
    require(config["summary"] == summarize(config["map_cases"], config["action_cases"]), "M15 action evidence summary drifted")
    require([item["status"] for item in config["action_cases"][-4:]] == [item[3] for item in run_m15_action_evidence.NEGATIVE_CASES], "M15 typed negative outcomes drifted")
    require(all(not item["mutated"] and item["command_count"] == 0 and item["tick_delta"] == 0 for item in config["action_cases"][-4:]), "M15 negative action invariant drifted")
    primary = config["map_cases"][0]
    require(all(config["determinism"][key] == primary[key] for key in ("observation_sha256", "candidate_metadata_sha256", "candidate_binary_sha256", "snapshot_token")), "M15 action deterministic lock drifted")
    logical_set = _recorded_artifact_set(config)
    if context.is_live:
        artifact_root = context.artifact_set(logical_set)
        require(artifact_root.is_dir() and not artifact_root.is_symlink(), "M15 action live artifact root is missing or a symlink")
        require([map_case_from_artifact(root, artifact_root, directory) for directory in MAP_DIRS] == config["map_cases"], "M15 action live map cases drifted")
        require([action_case_from_artifact(root, artifact_root, directory) for directory in ACTION_DIRS] == config["action_cases"], "M15 action live action cases drifted")
        repeat = map_case_from_artifact(root, artifact_root, REPEAT_DIR)
        for key in ("observation_sha256", "candidate_metadata_sha256", "candidate_binary_sha256", "snapshot_token"):
            require(repeat[key] == primary[key], f"M15 action live deterministic repeat {key} drifted")
    return M15ActionEvidenceSummary(len(config["map_cases"]), len(config["action_cases"]), config["summary"]["passed"], config["summary"]["maximum_rss_kib"], context.is_live)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.artifact_root is not None:
            require(args.output is not None, "creation requires --output")
            path = freeze(args.root, args.artifact_root, args.output)
            print(f"V2_M15_ACTION_EVIDENCE=FROZEN path={path} sha256={sha256_file(path)}")
            return 0
        require(args.output is None, "creation requires --artifact-root and --output")
        summary = validate(args.root, artifact_context=ArtifactContext.offline())
        print(f"V2_M15_ACTION_EVIDENCE=PASS map_cases={summary.map_cases} action_cases={summary.action_cases} passed={summary.passed} max_rss_kib={summary.maximum_rss_kib} live={str(summary.live).lower()}")
        return 0
    except (M15ActionEvidenceError, qualify_m15_action.M15ActionError, qualify_m15_observation.M15ObservationError, qualify_m15_native_reset.M15NativeResetError, OSError) as exc:
        print(f"V2_M15_ACTION_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
