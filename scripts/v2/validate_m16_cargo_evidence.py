#!/usr/bin/env python3
"""Validate frozen M16 cargo evidence and every retained native twin report."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

import jsonschema

import run_m16_cargo_matrix as matrix


CONFIG = pathlib.Path("config/v2/m16-cargo-evidence.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m16-cargo-evidence.schema.json")


class M16EvidenceError(ValueError):
    """M16 cargo evidence is inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M16EvidenceError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, schema_path: pathlib.Path | None = None, *, artifact_root: pathlib.Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    evidence, schema = load(config_path or root / CONFIG), load(schema_path or root / SCHEMA)
    try:
        jsonschema.Draft202012Validator(schema).validate(evidence)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M16EvidenceError(f"evidence schema failed at {where}: {exc.message}") from exc
    contract, source = load(root / matrix.CONTRACT), load(root / matrix.SOURCE)
    require(evidence["contract_sha256"] == sha256(root / matrix.CONTRACT), "contract identity drifted")
    require(evidence["source_sha256"] == sha256(root / matrix.SOURCE), "source identity drifted")
    require(evidence["executable_sha256"] == source["executable"]["sha256"], "executable identity drifted")
    expected_cases = matrix.cases(contract)
    require([item["case_id"] for item in evidence["cases"]] == [item.case_id for item in expected_cases], "case order or inventory drifted")
    live = artifact_root is not None
    if artifact_root is None:
        artifact_root = pathlib.Path(evidence["artifact_root"])
    artifact_root = artifact_root.resolve()
    require(str(artifact_root) == evidence["artifact_root"], "artifact root drifted")
    cargos: set[str] = set()
    occurrences: set[tuple[str, str]] = set()
    classes: set[str] = set()
    edges: set[tuple[str, int, str, str]] = set()
    for record, case in zip(evidence["cases"], expected_cases, strict=True):
        require(record["climate"] == case.climate and record["cargo"] == case.cargo and record["probe"] == case.probe and record["seed"] == case.seed, f"case metadata drifted: {case.case_id}")
        normalized: list[str] = []
        for twin in record["twins"]:
            path = artifact_root / twin["report_path"]
            require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(artifact_root), f"report missing or unsafe: {path}")
            require(sha256(path) == twin["report_sha256"], f"report SHA-256 drifted: {path}")
            report = load(path)
            matrix.validate_common(report, case, contract, evidence["executable_sha256"])
            normalized_sha = hashlib.sha256(matrix.normalized(report)).hexdigest()
            require(normalized_sha == twin["normalized_sha256"], f"normalized report drifted: {path}")
            normalized.append(normalized_sha)
        require(len(set(normalized)) == 1, f"twin reports differ: {case.case_id}")
        report = load(artifact_root / record["twins"][0]["report_path"])
        metrics = matrix.validate_probe(report, case)
        require(metrics == record["metrics"], f"projected metrics drifted: {case.case_id}")
        for cargo in report["cargo_catalog"]:
            cargos.add(cargo["label"]); occurrences.add((case.climate, cargo["label"])); classes.update(cargo["classes"])
        for edge in report["industry_graph"]["production_transitions"]:
            edges.add((case.climate, edge["industry_id"], edge["accepted"], edge["produced"]))
    aggregate = evidence["aggregate"]
    require(len(cargos) == aggregate["unique_cargo_labels"] == 31 and len(occurrences) == aggregate["climate_occurrences"] == 46, "cargo completeness drifted")
    require(sorted(classes) == aggregate["actual_cargo_classes"] and len(classes) == aggregate["actual_cargo_class_count"] == 10, "cargo class completeness drifted")
    require(len(edges) == aggregate["production_edges"] >= 20, "production edge completeness drifted")
    return {"cases": len(expected_cases), "runs": aggregate["native_runs"], "edges": len(edges), "live": live}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path)
    args = parser.parse_args()
    try:
        summary = validate(args.root, artifact_root=args.artifact_root)
        print(f"V2_M16_CARGO_EVIDENCE=PASS cases={summary['cases']} runs={summary['runs']} edges={summary['edges']} live={str(summary['live']).lower()}")
        return 0
    except (M16EvidenceError, matrix.M16MatrixError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M16_CARGO_EVIDENCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
