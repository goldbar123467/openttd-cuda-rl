#!/usr/bin/env python3
"""Validate frozen exact replay evidence across all M15 curriculum/generalization sizes."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    add_artifact_root_argument,
)
import run_m15_cross_scale_replay


CONFIG = pathlib.Path("config/v2/m15-cross-scale-replay-evidence.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m15-cross-scale-replay-evidence.schema.json")
LOGICAL_ARTIFACT_SET = "v2-m15-cross-scale-replay-a"
LIVE_CONSUMER = "m15-cross-scale-replay"


class M15CrossScaleReplayEvidenceError(ValueError):
    """Cross-scale replay evidence is inconsistent."""


@dataclass(frozen=True)
class M15CrossScaleReplayEvidenceSummary:
    cases: int
    runs: int
    maximum_rss_kib: int
    maximum_wall_seconds: float
    live: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15CrossScaleReplayEvidenceError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15CrossScaleReplayEvidenceError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15CrossScaleReplayEvidenceError(f"cannot hash {path}: {exc}") from exc


def _recorded_artifact_set(config: dict[str, Any]) -> str:
    recorded = config["artifact_root"]
    path = pathlib.PurePosixPath(recorded)
    require(
        isinstance(recorded, str)
        and recorded.startswith("/")
        and not recorded.startswith("//")
        and str(path) == recorded
        and all(part not in {"", ".", ".."} for part in path.parts[1:]),
        "cross-scale replay recorded artifact root is not an absolute normalized POSIX path",
    )
    require(path.name == LOGICAL_ARTIFACT_SET, "cross-scale replay logical artifact set drifted")
    return path.name


def _requirements(config: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    logical_set = _recorded_artifact_set(config)
    requirements: list[ArtifactRequirement] = [
        ArtifactRequirement(
            logical_set,
            "matrix-run.json",
            "file",
            LIVE_CONSUMER,
            config["matrix_run_sha256"],
        ),
    ]
    for case in config["cases"]:
        for run in run_m15_cross_scale_replay.RUNS:
            prefix = f"{case['case_id']}/{run}"
            requirements.extend([
                ArtifactRequirement(logical_set, f"{prefix}/episode-trace.json", "file", LIVE_CONSUMER, case["trace_sha256"]),
                ArtifactRequirement(logical_set, f"{prefix}/reset-projection.json", "file", LIVE_CONSUMER, case["projection_sha256"]),
                ArtifactRequirement(logical_set, f"{prefix}/resource.txt", "file", LIVE_CONSUMER),
                ArtifactRequirement(logical_set, f"{prefix}/artifacts/reset-ready.sav", "file", LIVE_CONSUMER, case["checkpoint_sha256"]),
            ])
            for label in ("capture-branch-a", "capture-branch-b"):
                requirements.extend([
                    ArtifactRequirement(logical_set, f"{prefix}/artifacts/{label}.sav", "file", LIVE_CONSUMER, case["save_sha256"]),
                    ArtifactRequirement(logical_set, f"{prefix}/artifacts/{label}-observation.json", "file", LIVE_CONSUMER),
                    ArtifactRequirement(logical_set, f"{prefix}/artifacts/{label}-observation.bin", "file", LIVE_CONSUMER, case["observation_sha256"]),
                    ArtifactRequirement(logical_set, f"{prefix}/artifacts/{label}-candidates.json", "file", LIVE_CONSUMER),
                    ArtifactRequirement(logical_set, f"{prefix}/artifacts/{label}-candidates.bin", "file", LIVE_CONSUMER, case["candidate_sha256"]),
                ])
    return tuple(requirements)


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    return _requirements(load_json(root / CONFIG))


def expected_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cases": len(cases),
        "runs": len(cases) * len(run_m15_cross_scale_replay.RUNS),
        "curriculum_cases": sum(item["tier"] == "curriculum" for item in cases),
        "generalization_cases": sum(item["tier"] == "generalization" for item in cases),
        "twin_process_exact": sum(item["twin_process_exact"] is True for item in cases),
        "save_load_exact": sum(item["save_load_exact"] is True for item in cases),
        "maximum_rss_kib": max(item["maximum_rss_kib"] for item in cases),
        "maximum_wall_seconds": max(item["maximum_wall_seconds"] for item in cases),
        "status": "PASS",
    }


def validate(
    root: pathlib.Path,
    config_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_context: ArtifactContext | None = None,
) -> M15CrossScaleReplayEvidenceSummary:
    context = artifact_context or ArtifactContext.offline()
    repository_config = config_path is None
    root = root.resolve()
    config_path, schema_path = config_path or root / CONFIG, schema_path or root / SCHEMA
    config, schema = load_json(config_path), load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(config)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15CrossScaleReplayEvidenceError(f"M15 cross-scale replay evidence schema failed at {location}: {exc.message}") from exc
    require(config["schema_sha256"] == sha256_file(schema_path), "cross-scale replay evidence schema SHA-256 mismatch")
    identities = {
        "contract_sha256": "config/v2/m15-scalable-contract.json",
        "episode_source_sha256": "config/v2/m15-episode-source.json",
        "program_schema_sha256": "docs/project/schema/v2-m15-episode-program.schema.json",
        "trace_schema_sha256": "docs/project/schema/v2-m15-episode-trace.schema.json",
        "program_sha256": "config/v2/m15-cross-scale-replay-program.json",
    }
    for field, path in identities.items():
        require(config[field] == sha256_file(root / path), f"cross-scale replay identity drifted: {field}")
    episode_source = load_json(root / "config/v2/m15-episode-source.json")
    require(all(config["executable"][field] == episode_source["build"]["executable"][field] for field in ("sha256", "size")), "cross-scale replay executable identity drifted")
    expected = [(case_id, width, height, seed, split, tier) for case_id, width, height, seed, split, tier in run_m15_cross_scale_replay.CASES]
    actual = [(case["case_id"], case["width"], case["height"], case["seed"], case["split"], case["tier"]) for case in config["cases"]]
    require(actual == expected, "cross-scale replay case inventory/order drifted")
    scalable = load_json(root / "config/v2/m15-scalable-contract.json")
    require([[case["width"], case["height"]] for case in config["cases"][:4]] == scalable["map"]["curriculum"], "curriculum replay map coverage drifted")
    require([[case["width"], case["height"]] for case in config["cases"][4:]] == scalable["map"]["generalization"], "generalization replay map coverage drifted")
    require([case["seed"] for case in config["cases"][:4]] == scalable["seeds"]["sets"]["training"]["seeds"][:4], "curriculum replay seed coverage drifted")
    require([case["seed"] for case in config["cases"][4:]] == scalable["seeds"]["sets"]["generalization"]["seeds"][:5], "generalization replay seed coverage drifted")
    digest_fields = ["projection_sha256", "trace_sha256", "checkpoint_sha256", "state_sha256", "save_sha256", "observation_sha256", "candidate_sha256", "candidate_semantic_sha256"]
    for case in config["cases"]:
        require(all(case[field] != "0" * 64 for field in digest_fields), f"cross-scale replay contains a zero digest: {case['case_id']}")
    require(config["summary"] == expected_summary(config["cases"]), "cross-scale replay summary drifted")
    logical_set = _recorded_artifact_set(config)

    if context.is_live:
        requirements = (
            required_live_inputs(root)
            if repository_config
            else _requirements(config)
        )
        context.preflight(requirements)
        artifact_root = context.artifact_set(logical_set)
        matrix_path = context.resolve(requirements[0])
        require(sha256_file(matrix_path) == config["matrix_run_sha256"], "cross-scale matrix-run digest drifted")
        matrix = load_json(matrix_path)
        require(matrix["outcome"] == "PASS" and matrix["program_sha256"] == config["program_sha256"] and len(matrix["cases"]) == 9, "cross-scale matrix-run summary drifted")
        for frozen, live_case in zip(config["cases"], matrix["cases"], strict=True):
            for field in ("case_id", "width", "height", "seed", "split", "tier"):
                require(live_case[field] == frozen[field], f"cross-scale matrix case field drifted: {frozen['case_id']} {field}")
            require(live_case["twin_process_exact"] is True and live_case["save_load_exact"] is True and len(live_case["runs"]) == 2, f"cross-scale exact disposition drifted: {frozen['case_id']}")
            projected = [run_m15_cross_scale_replay.project_run(root, artifact_root / frozen["case_id"] / name) for name in run_m15_cross_scale_replay.RUNS]
            require(all(projected[0][field] == projected[1][field] for field in digest_fields), f"cross-scale live twin run differs: {frozen['case_id']}")
            for field in digest_fields + ["checkpoint_bytes"]:
                require(projected[0][field] == frozen[field], f"cross-scale live digest drifted: {frozen['case_id']} {field}")
            require(max(item["maximum_rss_kib"] for item in projected) == frozen["maximum_rss_kib"], f"cross-scale live RSS drifted: {frozen['case_id']}")
            require(max(item["wall_seconds"] for item in projected) == frozen["maximum_wall_seconds"], f"cross-scale live wall time drifted: {frozen['case_id']}")
    return M15CrossScaleReplayEvidenceSummary(
        config["summary"]["cases"], config["summary"]["runs"], config["summary"]["maximum_rss_kib"],
        config["summary"]["maximum_wall_seconds"], context.is_live,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    add_artifact_root_argument(parser)
    args = parser.parse_args()
    try:
        context = (
            ArtifactContext.offline()
            if args.artifact_root is None
            else ArtifactContext.live(args.artifact_root)
        )
        summary = validate(
            args.root,
            args.config,
            args.schema,
            artifact_context=context,
        )
        print(f"V2_M15_CROSS_SCALE_REPLAY_EVIDENCE=PASS cases={summary.cases} runs={summary.runs} max_rss_kib={summary.maximum_rss_kib} max_wall_seconds={summary.maximum_wall_seconds} live={str(summary.live).lower()}")
        return 0
    except (
        M15CrossScaleReplayEvidenceError,
        run_m15_cross_scale_replay.M15CrossScaleReplayError,
        ArtifactContextError,
        OSError,
        ValueError,
    ) as exc:
        print(f"V2_M15_CROSS_SCALE_REPLAY_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
