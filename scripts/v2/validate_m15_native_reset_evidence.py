#!/usr/bin/env python3
"""Validate the compact and optionally live M15 native reset matrix."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
from dataclasses import dataclass
from typing import Any

import jsonschema

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    add_artifact_root_argument,
)
import qualify_m15_native_reset


EVIDENCE = pathlib.Path("config/v2/m15-native-reset-evidence.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m15-native-reset-evidence.schema.json")
EXPECTED = [
    ("64-a", "qualified-64-a", 64, 64),
    ("64-b", "qualified-64-b", 64, 64),
    ("128-a", "qualified-128-a", 128, 128),
    ("64x256-a", "qualified-64x256-a", 64, 256),
    ("512x128-a", "qualified-512x128-a", 512, 128),
    ("1024-a", "qualified-1024-a", 1024, 1024),
]
LOGICAL_ARTIFACT_SET = "v2-m15-native-a"
LIVE_CONSUMER = "m15-native-reset-evidence"


class M15NativeResetEvidenceError(ValueError):
    """The retained native reset matrix is missing or inconsistent."""


@dataclass(frozen=True)
class M15NativeResetEvidenceSummary:
    runs: int
    rectangles: int
    maximum_rss_kib: int
    live: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15NativeResetEvidenceError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15NativeResetEvidenceError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15NativeResetEvidenceError(f"cannot hash {path}: {exc}") from exc


def result_from_live(artifact: pathlib.Path, run: str, artifact_dir: str) -> dict[str, Any]:
    evidence_path = artifact / qualify_m15_native_reset.EVIDENCE_NAME
    evidence = load_json(evidence_path)
    return {
        "run": run,
        "artifact_dir": artifact_dir,
        "width": evidence["width"],
        "height": evidence["height"],
        "outcome": evidence["outcome"],
        "manifest_sha256": evidence["manifest_sha256"],
        "projection_sha256": evidence["projection_sha256"],
        "evidence_sha256": sha256_file(evidence_path),
        "transcript_sha256": evidence["transcript_sha256"],
        "towns": evidence["towns"],
        "industries": evidence["industries"],
        "maximum_rss_kib": evidence["maximum_rss_kib"],
        "wall_seconds": evidence["wall_seconds"],
    }


def expected_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    projections = collections.Counter(item["projection_sha256"] for item in results)
    return {
        "runs": len(results),
        "distinct_rectangles": len({(item["width"], item["height"]) for item in results}),
        "byte_identical_repeats": sum(count - 1 for count in projections.values() if count > 1),
        "maximum_rss_kib": max(item["maximum_rss_kib"] for item in results),
        "summed_wall_seconds": round(sum(item["wall_seconds"] for item in results), 6),
        "maximum_towns": max(item["towns"] for item in results),
        "maximum_industries": max(item["industries"] for item in results),
    }


def _recorded_artifact_set(evidence: dict[str, Any]) -> str:
    recorded = evidence["artifact_base_hint"]
    path = pathlib.PurePosixPath(recorded)
    require(
        isinstance(recorded, str)
        and recorded.startswith("/")
        and not recorded.startswith("//")
        and str(path) == recorded
        and all(part not in {"", ".", ".."} for part in path.parts[1:]),
        "M15 native reset recorded artifact base is not an absolute normalized POSIX path",
    )
    require(path.name == LOGICAL_ARTIFACT_SET, "M15 native reset logical artifact set drifted")
    return path.name


def _requirements(evidence: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    logical_set = _recorded_artifact_set(evidence)
    requirements: list[ArtifactRequirement] = []
    for result in evidence["results"]:
        directory = result["artifact_dir"]
        for filename, digest in (
            (qualify_m15_native_reset.EVIDENCE_NAME, result["evidence_sha256"]),
            (qualify_m15_native_reset.MANIFEST_NAME, result["manifest_sha256"]),
            (qualify_m15_native_reset.PROJECTION_NAME, result["projection_sha256"]),
            (qualify_m15_native_reset.TRANSCRIPT_NAME, result["transcript_sha256"]),
        ):
            requirements.append(ArtifactRequirement(
                logical_set,
                f"{directory}/{filename}",
                "file",
                LIVE_CONSUMER,
                digest,
            ))
    return tuple(requirements)


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    return _requirements(load_json(root / EVIDENCE))


def validate(
    root: pathlib.Path,
    evidence_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_context: ArtifactContext | None = None,
) -> M15NativeResetEvidenceSummary:
    context = artifact_context or ArtifactContext.offline()
    repository_evidence = evidence_path is None
    root = root.resolve()
    evidence_path = evidence_path or root / EVIDENCE
    schema_path = schema_path or root / SCHEMA
    evidence = load_json(evidence_path)
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(evidence)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15NativeResetEvidenceError(f"M15 native reset evidence schema failed at {location}: {exc.message}") from exc
    require(evidence["schema_sha256"] == sha256_file(schema_path), "M15 native reset evidence schema SHA-256 mismatch")
    require(evidence["contract_sha256"] == sha256_file(root / qualify_m15_native_reset.CONTRACT), "M15 native reset contract SHA-256 mismatch")
    require(evidence["native_source_sha256"] == sha256_file(root / qualify_m15_native_reset.SOURCE), "M15 native source evidence SHA-256 mismatch")
    source = load_json(root / qualify_m15_native_reset.SOURCE)
    require(evidence["executable"] == {key: source["build"]["executable"][key] for key in ("sha256", "size")}, "M15 native reset executable identity drifted")
    results = evidence["results"]
    require([(item["run"], item["artifact_dir"], item["width"], item["height"]) for item in results] == EXPECTED, "M15 native reset run order/coverage drifted")
    require(all(item["towns"] == max(2, min(128, item["width"] * item["height"] // 4096)) for item in results), "M15 native reset town target drifted")
    require(results[0]["projection_sha256"] == results[1]["projection_sha256"], "same-manifest native reset projections differ")
    require(evidence["summary"] == expected_summary(results), "M15 native reset summary drifted")
    logical_set = _recorded_artifact_set(evidence)

    if context.is_live:
        requirements = (
            required_live_inputs(root)
            if repository_evidence
            else _requirements(evidence)
        )
        context.preflight(requirements)
        artifact_base = context.artifact_set(logical_set)
        for expected, result in zip(EXPECTED, results, strict=True):
            run, artifact_dir, width, height = expected
            artifact = artifact_base / artifact_dir
            require(artifact.is_dir() and not artifact.is_symlink(), f"M15 live reset artifact is missing or a symlink: {artifact_dir}")
            live = result_from_live(artifact, run, artifact_dir)
            require(live == result, f"M15 live reset result drifted: {artifact_dir}")
            manifest_path = artifact / qualify_m15_native_reset.MANIFEST_NAME
            projection_path = artifact / qualify_m15_native_reset.PROJECTION_NAME
            transcript_path = artifact / qualify_m15_native_reset.TRANSCRIPT_NAME
            require(sha256_file(manifest_path) == result["manifest_sha256"], f"M15 reset manifest drifted: {artifact_dir}")
            require(sha256_file(projection_path) == result["projection_sha256"], f"M15 reset projection drifted: {artifact_dir}")
            require(sha256_file(transcript_path) == result["transcript_sha256"], f"M15 reset transcript drifted: {artifact_dir}")
            manifest = load_json(manifest_path)
            qualify_m15_native_reset.validate_schema(manifest, root / qualify_m15_native_reset.MANIFEST_SCHEMA, "M15 reset manifest")
            projection = qualify_m15_native_reset.validate_projection(root, manifest, projection_path)
            require(projection["state"]["counts"]["towns"] == result["towns"], f"M15 reset town count drifted: {artifact_dir}")

    return M15NativeResetEvidenceSummary(len(results), evidence["summary"]["distinct_rectangles"], evidence["summary"]["maximum_rss_kib"], context.is_live)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--evidence", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    add_artifact_root_argument(parser)
    args = parser.parse_args(argv)
    try:
        context = (
            ArtifactContext.offline()
            if args.artifact_root is None
            else ArtifactContext.live(args.artifact_root)
        )
        summary = validate(
            args.root,
            args.evidence,
            args.schema,
            artifact_context=context,
        )
        print(f"V2_M15_NATIVE_RESET_EVIDENCE=PASS runs={summary.runs} rectangles={summary.rectangles} max_rss_kib={summary.maximum_rss_kib} live={str(summary.live).lower()}")
        return 0
    except (
        M15NativeResetEvidenceError,
        qualify_m15_native_reset.M15NativeResetError,
        ArtifactContextError,
        OSError,
    ) as exc:
        print(f"V2_M15_NATIVE_RESET_EVIDENCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
