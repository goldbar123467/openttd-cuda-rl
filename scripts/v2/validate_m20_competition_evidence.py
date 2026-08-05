#!/usr/bin/env python3
"""Validate frozen M20 competition evidence and every retained native report."""

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
import run_m20_competition_matrix as matrix


CONFIG = pathlib.Path("config/v2/m20-competition-evidence.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m20-competition-evidence.schema.json")
CONTRACT_SCHEMA = pathlib.Path("docs/project/schema/v2-m20-competition-contract.schema.json")
LOGICAL_ARTIFACT_SET = "v2-m20-competition-matrix-f"
LIVE_CONSUMER = "m20-competition-evidence"


class M20EvidenceError(ValueError):
    """M20 competition evidence is inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M20EvidenceError(message)


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
        raise M20EvidenceError(f"{label} schema failed at {where}: {exc.message}") from exc


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
            expected = f"{record['case_id']}/replicate-{replicate['name']}/report.json"
            require(replicate["report_path"] == expected, f"report path drifted: {record['case_id']}")
            requirements.append(ArtifactRequirement(logical_set, replicate["report_path"], "file", LIVE_CONSUMER, replicate["report_sha256"]))
    require(len(requirements) == len(set(requirements)), "report inventory contains duplicates")
    return tuple(requirements)


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    return _requirements(load(root / CONFIG))


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, schema_path: pathlib.Path | None = None,
             *, artifact_context: ArtifactContext | None = None) -> dict[str, Any]:
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
    identities = matrix.expected_identities(root, contract)
    require(evidence["identities"] == identities, "run identity closure drifted")
    expected = matrix.cases(contract)
    require([item["case_id"] for item in evidence["cases"]] == [item.case_id for item in expected], "case inventory/order drifted")
    requirements = _requirements(evidence)
    live_reports: dict[str, pathlib.Path] = {}
    if context.is_live:
        requirements = required_live_inputs(root) if repository_evidence else requirements
        context.preflight(requirements)
        live_reports = {item.relative_path: context.resolve(item) for item in requirements}
    maximum_wall = 0.0
    for record, case in zip(evidence["cases"], expected, strict=True):
        require((record["leg"], record["map_seed"], record["probe"], record["seed_ordinal"], record["simulation_seed"]) ==
                (case.leg, case.map_seed, case.probe, case.seed_ordinal, case.simulation_seed), f"case metadata drifted: {case.case_id}")
        normalized: list[str] = []
        for index, (replicate, expected_name) in enumerate(zip(record["replicates"], matrix.REPLICATES, strict=True)):
            require(replicate["name"] == expected_name, f"replicate order drifted: {case.case_id}")
            normalized.append(replicate["normalized_sha256"])
            maximum_wall = max(maximum_wall, replicate["wall_seconds"])
            if context.is_live:
                path = live_reports[replicate["report_path"]]
                require(sha256(path) == replicate["report_sha256"], f"report SHA-256 drifted: {path}")
                report = load(path)
                matrix.validate_common(report, case, expected_name, identities, source, contract)
                digest = hashlib.sha256(matrix.normalized(report)).hexdigest()
                require(digest == replicate["normalized_sha256"], f"normalized report drifted: {path}")
                require(matrix.validate_probe(report, case) == record["replicate_metrics"][index], f"metric projection drifted: {path}")
        require(len(normalized) == 2, f"replicate accounting differs: {case.case_id}")
        require(record["projection_replay_exact"] is True, f"projection replay flag drifted: {case.case_id}")
    require(evidence["aggregate"]["maximum_wall_seconds"] == round(maximum_wall, 6), "maximum wall time drifted")
    require(evidence["scoring"] == matrix.scoring(expected, evidence["cases"], contract), "scoring/interval projection drifted")
    require(all(metric["rl"]["alive"] and metric["rl"]["delivered_cargo_units"] >= 25 and metric["save_load_public_exact"]
                for record in evidence["cases"] for metric in record["replicate_metrics"]), "solo competence or save/load was not retained")
    if context.is_live:
        require(all(not load(live_reports[replicate["report_path"]])["result"]["privileged_inputs"]
                    for record in evidence["cases"] for replicate in record["replicates"]), "privileged policy input was retained")
    return {"cases": len(expected), "runs": evidence["aggregate"]["native_runs"],
            "replay_exact": evidence["aggregate"]["projection_replay_exact_cases"], "live": context.is_live}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    add_artifact_root_argument(parser)
    args = parser.parse_args(argv)
    try:
        artifact_root = resolve_artifact_root(args.artifact_root)
        context = ArtifactContext.offline() if artifact_root is None else ArtifactContext.live(artifact_root)
        summary = validate(args.root, artifact_context=context)
        print(f"V2_M20_COMPETITION_EVIDENCE=PASS cases={summary['cases']} runs={summary['runs']} "
              f"replay_exact={summary['replay_exact']} live={str(summary['live']).lower()}")
        return 0
    except (M20EvidenceError, matrix.M20MatrixError, ArtifactContextError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M20_COMPETITION_EVIDENCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
