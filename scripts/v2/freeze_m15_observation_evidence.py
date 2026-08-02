#!/usr/bin/env python3
"""Freeze and validate representative M15 bounded-observation oracle evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema

import qualify_m15_native_reset
import qualify_m15_observation


SCHEMA = pathlib.Path("docs/project/schema/v2-m15-observation-evidence.schema.json")
CONFIG = pathlib.Path("config/v2/m15-observation-evidence.json")
CONTRACT = pathlib.Path("config/v2/m15-scalable-contract.json")
SOURCE = pathlib.Path("config/v2/m15-observation-source.json")
METADATA_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-observation-metadata.schema.json")
CASE_DIRS = ["reset-0064x0064", "reset-0064x0256", "reset-0512x0128", "reset-1024x1024"]
REPEAT_DIR = "repeat-0064x0064"


class M15ObservationEvidenceError(ValueError):
    """The frozen bounded-observation evidence is missing or inconsistent."""


@dataclass(frozen=True)
class M15ObservationEvidenceSummary:
    cases: int
    passed: int
    maximum_rss_kib: int
    live: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15ObservationEvidenceError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15ObservationEvidenceError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15ObservationEvidenceError(f"cannot hash {path}: {exc}") from exc


def case_from_artifact(root: pathlib.Path, artifact_root: pathlib.Path, directory: str) -> dict[str, Any]:
    artifact = artifact_root / directory
    evidence_path = artifact / qualify_m15_observation.EVIDENCE_NAME
    evidence = load_json(evidence_path)
    manifest = load_json(artifact / qualify_m15_observation.MANIFEST_NAME)
    projection_path = artifact / qualify_m15_observation.PROJECTION_NAME
    projection = qualify_m15_native_reset.validate_projection(root, manifest, projection_path)
    summary = qualify_m15_observation.validate_observation(root, artifact, manifest, projection)
    metadata = load_json(artifact / qualify_m15_observation.METADATA_NAME)
    require(evidence["outcome"] == "PASS" and evidence["width"] == summary.width and evidence["height"] == summary.height, f"observation evidence outcome/dimensions drifted: {directory}")
    require(evidence["binary_sha256"] == summary.binary_sha256 and evidence["observation_bytes"] == qualify_m15_observation.OBSERVATION_BYTES, f"observation evidence binary drifted: {directory}")
    for key, filename in (
        ("manifest_sha256", qualify_m15_observation.MANIFEST_NAME), ("projection_sha256", qualify_m15_observation.PROJECTION_NAME),
        ("metadata_sha256", qualify_m15_observation.METADATA_NAME), ("transcript_sha256", qualify_m15_observation.TRANSCRIPT_NAME),
    ):
        require(evidence[key] == sha256_file(artifact / filename), f"observation evidence {key} drifted: {directory}")
    return {
        "artifact_dir": directory,
        "width": evidence["width"], "height": evidence["height"], "seed": evidence["seed"], "outcome": evidence["outcome"],
        "observation_bytes": evidence["observation_bytes"], "towns": evidence["towns"], "industries": evidence["industries"],
        "omitted_industries": metadata["entities"]["industries"]["omitted"], "maximum_rss_kib": evidence["maximum_rss_kib"],
        "wall_seconds": evidence["wall_seconds"], "manifest_sha256": evidence["manifest_sha256"], "projection_sha256": evidence["projection_sha256"],
        "metadata_sha256": evidence["metadata_sha256"], "binary_sha256": evidence["binary_sha256"], "evidence_sha256": sha256_file(evidence_path),
        "transcript_sha256": evidence["transcript_sha256"], "oracle_checks": evidence["oracle_checks"],
    }


def summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cases": len(cases), "passed": sum(item["outcome"] == "PASS" for item in cases),
        "observation_bytes": qualify_m15_observation.OBSERVATION_BYTES,
        "maximum_rss_kib": max(item["maximum_rss_kib"] for item in cases),
        "maximum_wall_seconds": max(item["wall_seconds"] for item in cases),
        "maximum_industries": max(item["industries"] for item in cases),
        "maximum_omitted_industries": max(item["omitted_industries"] for item in cases),
    }


def freeze(root: pathlib.Path, artifact_root: pathlib.Path, output: pathlib.Path) -> pathlib.Path:
    root, artifact_root, output = root.resolve(), artifact_root.resolve(), output.resolve()
    require(artifact_root.is_dir() and not artifact_root.is_symlink(), "observation artifact root is missing or a symlink")
    require(not output.exists() and not output.is_symlink(), "refusing to overwrite frozen observation evidence")
    cases = [case_from_artifact(root, artifact_root, directory) for directory in CASE_DIRS]
    primary = cases[0]
    repeat = case_from_artifact(root, artifact_root, REPEAT_DIR)
    for key in ("manifest_sha256", "projection_sha256", "metadata_sha256", "binary_sha256"):
        require(repeat[key] == primary[key], f"observation deterministic repeat {key} differs")
    source = load_json(root / SOURCE)
    value = {
        "$schema": "../../docs/project/schema/v2-m15-observation-evidence.schema.json",
        "schema_version": "openttd-rl-v2-m15-observation-evidence-1",
        "schema_sha256": sha256_file(root / SCHEMA), "snapshot_date": "2026-08-02",
        "contract_sha256": sha256_file(root / CONTRACT), "observation_source_sha256": sha256_file(root / SOURCE),
        "metadata_schema_sha256": sha256_file(root / METADATA_SCHEMA),
        "executable": {key: source["build"]["executable"][key] for key in ("sha256", "size")},
        "artifact_base_hint": str(artifact_root.parent), "artifact_root": artifact_root.name,
        "cases": cases,
        "determinism": {
            "primary_artifact_dir": CASE_DIRS[0], "repeat_artifact_dir": REPEAT_DIR,
            **{key: primary[key] for key in ("manifest_sha256", "projection_sha256", "metadata_sha256", "binary_sha256")},
            "byte_identical": True,
        },
        "policy": {"exact_bytes": qualify_m15_observation.OBSERVATION_BYTES, "independent_decoder": True, "cross_view_64": True, "rectangular_maps": True, "maximum_budget_map": True, "overflow_observed": True, "g15_pass_claim": False},
        "summary": summarize(cases),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    validate(root, output, artifact_base=artifact_root.parent)
    return output


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, schema_path: pathlib.Path | None = None, *, artifact_base: pathlib.Path | None = None) -> M15ObservationEvidenceSummary:
    root = root.resolve()
    config_path, schema_path = config_path or root / CONFIG, schema_path or root / SCHEMA
    config, schema = load_json(config_path), load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(config)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15ObservationEvidenceError(f"M15 observation evidence schema failed at {location}: {exc.message}") from exc
    require(config["schema_sha256"] == sha256_file(schema_path), "M15 observation evidence schema SHA-256 mismatch")
    require(config["contract_sha256"] == sha256_file(root / CONTRACT), "M15 observation contract identity drifted")
    require(config["observation_source_sha256"] == sha256_file(root / SOURCE), "M15 observation source identity drifted")
    require(config["metadata_schema_sha256"] == sha256_file(root / METADATA_SCHEMA), "M15 observation metadata schema identity drifted")
    source = load_json(root / SOURCE)
    require(config["executable"] == {key: source["build"]["executable"][key] for key in ("sha256", "size")}, "M15 observation executable identity drifted")
    expected_dimensions = [(64, 64), (64, 256), (512, 128), (1024, 1024)]
    require([(item["width"], item["height"]) for item in config["cases"]] == expected_dimensions, "M15 observation evidence dimensions/order drifted")
    require([item["artifact_dir"] for item in config["cases"]] == CASE_DIRS, "M15 observation artifact directories drifted")
    require(config["summary"] == summarize(config["cases"]), "M15 observation evidence summary drifted")
    require(config["cases"][-1]["omitted_industries"] > 0, "M15 observation overflow evidence disappeared")
    primary = config["cases"][0]
    require(all(config["determinism"][key] == primary[key] for key in ("manifest_sha256", "projection_sha256", "metadata_sha256", "binary_sha256")), "M15 observation deterministic lock drifted")

    if artifact_base is not None:
        artifact_base = artifact_base.resolve()
        require(str(artifact_base) == config["artifact_base_hint"], "M15 observation artifact base drifted")
        artifact_root = artifact_base / config["artifact_root"]
        require(artifact_root.is_dir() and not artifact_root.is_symlink(), "M15 observation live artifact root is missing or a symlink")
        live_cases = [case_from_artifact(root, artifact_root, directory) for directory in CASE_DIRS]
        require(live_cases == config["cases"], "M15 observation live cases drifted")
        repeat = case_from_artifact(root, artifact_root, REPEAT_DIR)
        for key in ("manifest_sha256", "projection_sha256", "metadata_sha256", "binary_sha256"):
            require(repeat[key] == primary[key], f"M15 observation live deterministic repeat {key} drifted")
    return M15ObservationEvidenceSummary(len(config["cases"]), config["summary"]["passed"], config["summary"]["maximum_rss_kib"], artifact_base is not None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    parser.add_argument("--artifact-base", type=pathlib.Path)
    args = parser.parse_args(argv or sys.argv[1:])
    try:
        if args.artifact_root is not None:
            require(args.output is not None and args.config is None and args.artifact_base is None, "freeze requires --output and forbids validation-only options")
            path = freeze(args.root, args.artifact_root, args.output)
            print(f"V2_M15_OBSERVATION_EVIDENCE=FROZEN path={path} sha256={sha256_file(path)}")
            return 0
        summary = validate(args.root, args.config, args.schema, artifact_base=args.artifact_base)
        print(f"V2_M15_OBSERVATION_EVIDENCE=PASS cases={summary.cases} passed={summary.passed} max_rss_kib={summary.maximum_rss_kib} live={str(summary.live).lower()}")
        return 0
    except (M15ObservationEvidenceError, qualify_m15_observation.M15ObservationError, qualify_m15_native_reset.M15NativeResetError, OSError) as exc:
        print(f"V2_M15_OBSERVATION_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
