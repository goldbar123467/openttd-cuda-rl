#!/usr/bin/env python3
"""Validate frozen M21 evidence, exact twins, saves, and pre-world rejections."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

import jsonschema

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    add_artifact_root_argument,
    resolve_artifact_root,
)
import run_m21_broad_matrix as matrix


CONFIG = pathlib.Path("config/v2/m21-broad-evidence.json")
EVIDENCE_SCHEMA = pathlib.Path("docs/project/schema/v2-m21-broad-evidence.schema.json")
CONTRACT_SCHEMA = pathlib.Path("docs/project/schema/v2-m21-broad-contract.schema.json")
COVERAGE_SCHEMA = pathlib.Path("docs/project/schema/v2-m21-broad-coverage.schema.json")
LOGICAL_ARTIFACT_SET = "v2-m21-broad-f"
LIVE_CONSUMER = "m21-broad-evidence"


class M21EvidenceError(ValueError):
    """M21 retained evidence is inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M21EvidenceError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schema_validate(value: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M21EvidenceError(f"{label} schema failed at {where}: {exc.message}") from exc


def _recorded_artifact_set(evidence: dict[str, Any]) -> str:
    recorded = evidence["artifact_root"]
    path = pathlib.PurePosixPath(recorded)
    require(isinstance(recorded, str) and recorded.startswith("/") and not recorded.startswith("//") and
            str(path) == recorded and all(part not in {"", ".", ".."} for part in path.parts[1:]),
            "artifact root is not an absolute normalized POSIX path")
    require(path.name == LOGICAL_ARTIFACT_SET, "artifact root drifted")
    return path.name


def _requirements(evidence: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    logical_set = _recorded_artifact_set(evidence)
    requirements: list[ArtifactRequirement] = []
    for record in evidence["cases"]:
        require([item["name"] for item in record["replicates"]] == ["a", "b"], f"replicate order drifted: {record['case_id']}")
        for replicate in record["replicates"]:
            expected_report = f"{record['case_id']}/replicate-{replicate['name']}/report.json"
            require(replicate["report_path"] == expected_report, f"report path drifted: {record['case_id']}")
            requirements.append(ArtifactRequirement(logical_set, expected_report, "file", LIVE_CONSUMER, replicate["report_sha256"]))
            if replicate["save"] is not None:
                requirements.append(ArtifactRequirement(logical_set, f"{expected_report}.sav", "file", LIVE_CONSUMER, replicate["save"]["sha256"]))
    for record in evidence["negative_cases"]:
        expected_log = f"{record['case_id']}/openttd.log"
        require(record["log_path"] == expected_log, f"negative log path drifted: {record['case_id']}")
        requirements.append(ArtifactRequirement(logical_set, expected_log, "file", LIVE_CONSUMER))
    require(len(requirements) == len(set(requirements)), "live evidence inventory contains duplicates")
    return tuple(requirements)


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    return _requirements(load(root / CONFIG))


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, *,
             artifact_context: ArtifactContext | None = None) -> dict[str, Any]:
    context = artifact_context or ArtifactContext.offline()
    repository_evidence = config_path is None
    root = root.resolve()
    evidence = load(config_path or root / CONFIG)
    contract, coverage, source = load(root / matrix.CONTRACT), load(root / matrix.COVERAGE), load(root / matrix.SOURCE)
    schema_validate(evidence, load(root / EVIDENCE_SCHEMA), "evidence")
    schema_validate(contract, load(root / CONTRACT_SCHEMA), "contract")
    schema_validate(coverage, load(root / COVERAGE_SCHEMA), "coverage")
    require(evidence["contract_sha256"] == sha256(root / matrix.CONTRACT), "contract identity drifted")
    require(evidence["coverage_sha256"] == sha256(root / matrix.COVERAGE), "coverage identity drifted")
    require(evidence["source_sha256"] == sha256(root / matrix.SOURCE), "source identity drifted")
    require(evidence["executable_sha256"] == source["executable"]["sha256"], "executable identity drifted")
    require(evidence["identities"] == matrix.identities(root, contract), "prerequisite identities drifted")
    coverage_summary = matrix.validate_coverage(root, contract, coverage)
    require([item["case_id"] for item in evidence["cases"]] == [item["case_id"] for item in contract["cases"]], "case inventory/order drifted")
    requirements = _requirements(evidence)
    live_paths: dict[str, pathlib.Path] = {}
    if context.is_live:
        requirements = required_live_inputs(root) if repository_evidence else requirements
        context.preflight(requirements)
        live_paths = {item.relative_path: context.resolve(item) for item in requirements}
    maximum_wall = 0.0
    for record, case in zip(evidence["cases"], contract["cases"], strict=True):
        require({key: record[key] for key in ("case_id", "landscape", "probe", "seed")} == case and record["twin_exact"],
                f"case metadata drifted: {case['case_id']}")
        normalized = []
        saves = []
        for replicate, name in zip(record["replicates"], matrix.REPLICATES, strict=True):
            require(replicate["name"] == name, f"replicate order drifted: {case['case_id']}")
            normalized.append(replicate["normalized_sha256"])
            if case["probe"] == "content":
                require(replicate["save"] is None, f"content case unexpectedly retained a save: {case['case_id']}")
                if context.is_live:
                    report_path = live_paths[replicate["report_path"]]
                    require(not pathlib.Path(str(report_path) + ".sav").exists(), f"content case unexpectedly retained a save: {case['case_id']}")
            else:
                saves.append(replicate["save"])
            if context.is_live:
                report_path = live_paths[replicate["report_path"]]
                require(sha256(report_path) == replicate["report_sha256"], f"report hash drifted: {report_path}")
                report = load(report_path)
                matrix.validate_report(report, case, name, contract, source, evidence["contract_sha256"], evidence["identities"]["content_lock_sha256"])
                digest = hashlib.sha256(matrix.normalized(report)).hexdigest()
                require(digest == replicate["normalized_sha256"], f"normalized report drifted: {report_path}")
                if replicate["save"] is not None:
                    save_path = live_paths[f"{replicate['report_path']}.sav"]
                    require(replicate["save"] == {"bytes": save_path.stat().st_size, "sha256": sha256(save_path)}, f"save identity drifted: {save_path}")
            maximum_wall = max(maximum_wall, replicate["wall_seconds"])
        require(len(set(normalized)) == 1 and (not saves or saves[0] == saves[1]), f"exact twin drifted: {case['case_id']}")
    require(evidence["aggregate"]["maximum_wall_seconds"] == round(maximum_wall, 6), "maximum wall time drifted")
    require(evidence["aggregate"] | {"maximum_wall_seconds": 0} == {"cases": 16, "command_dispositions": coverage_summary["commands"],
            "exact_twins": 16, "feature_domains": coverage_summary["features"], "maximum_wall_seconds": 0,
            "native_runs": 32, "negative_cases": 3}, "aggregate drifted")
    require([item["case_id"] for item in evidence["negative_cases"]] == [item["case_id"] for item in contract["negative_cases"]],
            "negative inventory drifted")
    for record, expected in zip(evidence["negative_cases"], contract["negative_cases"], strict=True):
        require(record["diagnostic"] == expected["diagnostic"] and record["exit_code"] != 0 and record["report_absent"],
                f"negative rejection drifted: {record['case_id']}")
        if context.is_live:
            log = live_paths[record["log_path"]]
            require(expected["diagnostic"] in log.read_text(encoding="utf-8") and not (log.parent / "report.json").exists(),
                    f"negative rejection drifted: {record['case_id']}")
    return {"cases": 16, "commands": coverage_summary["commands"], "features": coverage_summary["features"], "runs": 32, "twins": 16, "live": context.is_live}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    add_artifact_root_argument(parser)
    args = parser.parse_args(argv)
    try:
        artifact_root = resolve_artifact_root(args.artifact_root)
        context = ArtifactContext.offline() if artifact_root is None else ArtifactContext.live(artifact_root)
        result = validate(args.root, artifact_context=context)
        print(f"V2_M21_BROAD_EVIDENCE=PASS cases={result['cases']} runs={result['runs']} twins={result['twins']} "
              f"features={result['features']} commands={result['commands']} live={str(result['live']).lower()}")
        return 0
    except (M21EvidenceError, matrix.M21MatrixError, ArtifactContextError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M21_BROAD_EVIDENCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
