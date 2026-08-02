#!/usr/bin/env python3
"""Validate frozen M18 ship evidence and every retained native twin report."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

import jsonschema

import run_m18_ship_matrix as matrix


CONFIG = pathlib.Path("config/v2/m18-ship-evidence.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m18-ship-evidence.schema.json")
CONTRACT_SCHEMA = pathlib.Path("docs/project/schema/v2-m18-ship-contract.schema.json")


class M18EvidenceError(ValueError):
    """M18 ship evidence is inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M18EvidenceError(message)


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
        raise M18EvidenceError(f"{label} schema failed at {where}: {exc.message}") from exc


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, schema_path: pathlib.Path | None = None,
             *, artifact_root: pathlib.Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    evidence = load(config_path or root / CONFIG)
    schema_validate(evidence, load(schema_path or root / SCHEMA), "evidence")
    contract, source = load(root / matrix.CONTRACT), load(root / matrix.SOURCE)
    schema_validate(contract, load(root / CONTRACT_SCHEMA), "contract")
    require(evidence["contract_sha256"] == sha256(root / matrix.CONTRACT), "contract identity drifted")
    require(evidence["source_sha256"] == sha256(root / matrix.SOURCE), "source identity drifted")
    require(evidence["executable_sha256"] == source["executable"]["sha256"], "executable identity drifted")
    expected = matrix.cases(contract)
    require([item["case_id"] for item in evidence["cases"]] == [item.case_id for item in expected], "case inventory/order drifted")
    artifact_root = (artifact_root or pathlib.Path(evidence["artifact_root"])).resolve()
    maximum_wall = 0.0
    for record, case in zip(evidence["cases"], expected, strict=True):
        require((record["cargo"], record["probe"], record["seed"]) == (case.cargo, case.probe, case.seed), f"case metadata drifted: {case.case_id}")
        normalized: list[str] = []
        for twin in record["twins"]:
            path = artifact_root / twin["report_path"]
            require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(artifact_root), f"report missing or unsafe: {path}")
            require(sha256(path) == twin["report_sha256"], f"report SHA-256 drifted: {path}")
            report = load(path)
            matrix.validate_common(report, case, evidence["executable_sha256"])
            digest = hashlib.sha256(matrix.normalized(report)).hexdigest()
            require(digest == twin["normalized_sha256"], f"normalized report drifted: {path}")
            normalized.append(digest)
            maximum_wall = max(maximum_wall, twin["wall_seconds"])
        require(len(set(normalized)) == 1, f"twin reports differ: {case.case_id}")
        report = load(artifact_root / record["twins"][0]["report_path"])
        require(matrix.validate_probe(report, case) == record["metrics"], f"projected metrics drifted: {case.case_id}")
    require(evidence["aggregate"]["maximum_wall_seconds"] == round(maximum_wall, 6), "maximum wall time drifted")
    require(evidence["baselines"] == matrix.baseline_evidence(root), "ShipAI baseline evidence drifted")
    require(all(record["metrics"]["income"] > 0 and record["metrics"]["delivered"] > 0 for record in evidence["cases"]
                if record["probe"] in ("natural", "constructed")), "zero-service comparator was not beaten")
    return {"cases": len(expected), "runs": evidence["aggregate"]["native_runs"], "twin_exact": evidence["aggregate"]["twin_exact_cases"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path)
    args = parser.parse_args()
    try:
        summary = validate(args.root, artifact_root=args.artifact_root)
        print(f"V2_M18_SHIP_EVIDENCE=PASS cases={summary['cases']} runs={summary['runs']} twin_exact={summary['twin_exact']}")
        return 0
    except (M18EvidenceError, matrix.M18MatrixError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M18_SHIP_EVIDENCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
