#!/usr/bin/env python3
"""Validate frozen M21 evidence, exact twins, saves, and pre-world rejections."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

import jsonschema

import run_m21_broad_matrix as matrix


CONFIG = pathlib.Path("config/v2/m21-broad-evidence.json")
EVIDENCE_SCHEMA = pathlib.Path("docs/project/schema/v2-m21-broad-evidence.schema.json")
CONTRACT_SCHEMA = pathlib.Path("docs/project/schema/v2-m21-broad-contract.schema.json")
COVERAGE_SCHEMA = pathlib.Path("docs/project/schema/v2-m21-broad-coverage.schema.json")


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


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, *, artifact_root: pathlib.Path | None = None) -> dict[str, Any]:
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
    artifact_root = (artifact_root or pathlib.Path(evidence["artifact_root"])).resolve()
    maximum_wall = 0.0
    for record, case in zip(evidence["cases"], contract["cases"], strict=True):
        require({key: record[key] for key in ("case_id", "landscape", "probe", "seed")} == case and record["twin_exact"],
                f"case metadata drifted: {case['case_id']}")
        normalized = []
        saves = []
        for replicate, name in zip(record["replicates"], matrix.REPLICATES, strict=True):
            require(replicate["name"] == name, f"replicate order drifted: {case['case_id']}")
            report_path = artifact_root / replicate["report_path"]
            require(report_path.is_file() and not report_path.is_symlink() and report_path.resolve().is_relative_to(artifact_root),
                    f"report missing or unsafe: {report_path}")
            require(sha256(report_path) == replicate["report_sha256"], f"report hash drifted: {report_path}")
            report = load(report_path)
            matrix.validate_report(report, case, name, contract, source, evidence["contract_sha256"], evidence["identities"]["content_lock_sha256"])
            digest = hashlib.sha256(matrix.normalized(report)).hexdigest()
            require(digest == replicate["normalized_sha256"], f"normalized report drifted: {report_path}")
            normalized.append(digest)
            save_path = pathlib.Path(str(report_path) + ".sav")
            if case["probe"] == "content":
                require(replicate["save"] is None and not save_path.exists(), f"content case unexpectedly retained a save: {case['case_id']}")
            else:
                require(save_path.is_file() and replicate["save"] == {"bytes": save_path.stat().st_size, "sha256": sha256(save_path)},
                        f"save identity drifted: {save_path}")
                saves.append(replicate["save"])
            maximum_wall = max(maximum_wall, replicate["wall_seconds"])
        require(len(set(normalized)) == 1 and (not saves or saves[0] == saves[1]), f"exact twin drifted: {case['case_id']}")
    require(evidence["aggregate"]["maximum_wall_seconds"] == round(maximum_wall, 6), "maximum wall time drifted")
    require(evidence["aggregate"] | {"maximum_wall_seconds": 0} == {"cases": 16, "command_dispositions": coverage_summary["commands"],
            "exact_twins": 16, "feature_domains": coverage_summary["features"], "maximum_wall_seconds": 0,
            "native_runs": 32, "negative_cases": 3}, "aggregate drifted")
    require([item["case_id"] for item in evidence["negative_cases"]] == [item["case_id"] for item in contract["negative_cases"]],
            "negative inventory drifted")
    for record, expected in zip(evidence["negative_cases"], contract["negative_cases"], strict=True):
        log = artifact_root / record["log_path"]
        require(record["diagnostic"] == expected["diagnostic"] and log.is_file() and
                expected["diagnostic"] in log.read_text(encoding="utf-8") and record["exit_code"] != 0 and
                record["report_absent"] and not (log.parent / "report.json").exists(), f"negative rejection drifted: {record['case_id']}")
    return {"cases": 16, "commands": coverage_summary["commands"], "features": coverage_summary["features"], "runs": 32, "twins": 16}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path)
    args = parser.parse_args()
    try:
        result = validate(args.root, artifact_root=args.artifact_root)
        print(f"V2_M21_BROAD_EVIDENCE=PASS cases={result['cases']} runs={result['runs']} twins={result['twins']} "
              f"features={result['features']} commands={result['commands']}")
        return 0
    except (M21EvidenceError, matrix.M21MatrixError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M21_BROAD_EVIDENCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
