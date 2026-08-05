#!/usr/bin/env python3
"""Validate frozen M17 rail evidence and every retained native twin report."""

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
import run_m17_rail_matrix as matrix


CONFIG = pathlib.Path("config/v2/m17-rail-evidence.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m17-rail-evidence.schema.json")
CONTRACT_SCHEMA = pathlib.Path("docs/project/schema/v2-m17-rail-contract.schema.json")
LOGICAL_ARTIFACT_SET = "v2-m17-rail-matrix-a"
LIVE_CONSUMER = "m17-rail-evidence"


class M17EvidenceError(ValueError):
    """M17 rail evidence is inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M17EvidenceError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _recorded_artifact_set(evidence: dict[str, Any]) -> str:
    recorded = evidence["artifact_root"]
    path = pathlib.PurePosixPath(recorded)
    require(
        isinstance(recorded, str)
        and recorded.startswith("/")
        and not recorded.startswith("//")
        and str(path) == recorded
        and all(part not in {"", ".", ".."} for part in path.parts[1:]),
        "artifact root is not an absolute normalized POSIX path",
    )
    require(path.name == LOGICAL_ARTIFACT_SET, "artifact root drifted")
    return path.name


def _requirements(evidence: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    logical_set = _recorded_artifact_set(evidence)
    requirements: list[ArtifactRequirement] = []
    for record in evidence["cases"]:
        require([twin["name"] for twin in record["twins"]] == ["a", "b"], f"twin inventory drifted: {record['case_id']}")
        for twin in record["twins"]:
            expected = f"{record['case_id']}/twin-{twin['name']}/report.json"
            require(twin["report_path"] == expected, f"report path drifted: {record['case_id']}")
            requirements.append(ArtifactRequirement(
                logical_set,
                twin["report_path"],
                "file",
                LIVE_CONSUMER,
                twin["report_sha256"],
            ))
    require(len(requirements) == len(set(requirements)), "report inventory contains duplicates")
    return tuple(requirements)


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    return _requirements(load(root / CONFIG))


def schema_validate(value: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M17EvidenceError(f"{label} schema failed at {where}: {exc.message}") from exc


def validate(
    root: pathlib.Path,
    config_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_context: ArtifactContext | None = None,
) -> dict[str, Any]:
    context = artifact_context or ArtifactContext.offline()
    repository_evidence = config_path is None
    root = root.resolve()
    evidence = load(config_path or root / CONFIG)
    schema_validate(evidence, load(schema_path or root / SCHEMA), "evidence")
    contract, source = load(root / matrix.CONTRACT), load(root / matrix.SOURCE)
    schema_validate(contract, load(root / CONTRACT_SCHEMA), "contract")
    require(evidence["contract_sha256"] == sha256(root / matrix.CONTRACT), "contract identity drifted")
    require(evidence["source_sha256"] == sha256(root / matrix.SOURCE), "source identity drifted")
    require(evidence["executable_sha256"] == source["executable"]["sha256"], "executable identity drifted")
    expected_cases = matrix.cases(contract)
    require([item["case_id"] for item in evidence["cases"]] == [item.case_id for item in expected_cases], "case order or inventory drifted")
    requirements = _requirements(evidence)
    live_reports: dict[str, pathlib.Path] = {}
    if context.is_live:
        requirements = required_live_inputs(root) if repository_evidence else requirements
        context.preflight(requirements)
        live_reports = {item.relative_path: context.resolve(item) for item in requirements}
    maximum_wall = 0.0
    for record, case in zip(evidence["cases"], expected_cases, strict=True):
        require(record["cargo"] == case.cargo and record["probe"] == case.probe and record["seed"] == case.seed, f"case metadata drifted: {case.case_id}")
        normalized: list[str] = []
        for twin in record["twins"]:
            normalized.append(twin["normalized_sha256"])
            maximum_wall = max(maximum_wall, twin["wall_seconds"])
            if not context.is_live:
                continue
            path = live_reports[twin["report_path"]]
            require(sha256(path) == twin["report_sha256"], f"report SHA-256 drifted: {path}")
            report = load(path)
            matrix.validate_common(report, case, contract, evidence["executable_sha256"])
            normalized_sha = hashlib.sha256(matrix.normalized(report)).hexdigest()
            require(normalized_sha == twin["normalized_sha256"], f"normalized report drifted: {path}")
        require(len(set(normalized)) == 1, f"twin reports differ: {case.case_id}")
        if context.is_live:
            report = load(live_reports[record["twins"][0]["report_path"]])
            require(matrix.validate_probe(report, case) == record["metrics"], f"projected metrics drifted: {case.case_id}")
        elif case.probe in ("passenger", "freight", "stress"):
            require(record["metrics"]["income"] > 0 and record["metrics"]["delivered"] > 0 and record["metrics"]["ticks"] > 0, f"projected metrics drifted: {case.case_id}")
        else:
            require(record["metrics"] == {"delivered": 0, "income": 0, "ticks": 0}, f"projected metrics drifted: {case.case_id}")
    require(evidence["aggregate"]["maximum_wall_seconds"] == round(maximum_wall, 6), "maximum wall-time projection drifted")
    require(evidence["baselines"] == matrix.baseline_evidence(root, contract), "baseline evidence drifted")
    require(all(record["metrics"]["income"] > 0 and record["metrics"]["delivered"] > 0 for record in evidence["cases"] if record["probe"] in ("passenger", "freight")), "zero-service comparator was not beaten")
    return {"cases": len(expected_cases), "runs": evidence["aggregate"]["native_runs"], "twin_exact": evidence["aggregate"]["twin_exact_cases"], "live": context.is_live}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    add_artifact_root_argument(parser)
    args = parser.parse_args(argv)
    try:
        artifact_root = resolve_artifact_root(args.artifact_root)
        context = ArtifactContext.offline() if artifact_root is None else ArtifactContext.live(artifact_root)
        summary = validate(args.root, artifact_context=context)
        print(f"V2_M17_RAIL_EVIDENCE=PASS cases={summary['cases']} runs={summary['runs']} twin_exact={summary['twin_exact']} live={str(summary['live']).lower()}")
        return 0
    except (M17EvidenceError, matrix.M17MatrixError, ArtifactContextError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M17_RAIL_EVIDENCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
