#!/usr/bin/env python3
"""Independently validate M22's complete one-shot follow-up evidence."""

from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Any

import jsonschema

import run_m22_followup_evaluation as runner


CONFIG = pathlib.Path("config/v2/m22-followup-evaluation-evidence.json")


class M22FollowupEvidenceError(ValueError):
    """The M22 follow-up evidence is incomplete, inconsistent, or drifted."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22FollowupEvidenceError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"nonfinite JSON constant: {token}")))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise M22FollowupEvidenceError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def schema_validate(value: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M22FollowupEvidenceError(f"{label} schema failed at {where}: {exc.message}") from exc


def git(root: pathlib.Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    require(result.returncode == 0, f"git {' '.join(arguments)} failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def validate_source(value: dict[str, Any], root: pathlib.Path) -> None:
    require([item["path"] for item in value["files"]] == list(runner.SOURCE_PATHS),
            "M22 follow-up source inventory/order drifted")
    for record in value["files"]:
        path = root / record["path"]
        require(path.is_file() and not path.is_symlink() and runner.sha256(path) == record["sha256"],
                f"M22 follow-up source identity drifted: {record['path']}")
    require(value["tree_sha256"] == runner.sha256_bytes(runner.canonical_bytes(value["files"])),
            "M22 follow-up source inventory digest drifted")
    require(git(root, "cat-file", "-t", value["repository_commit"]) == "commit" and
            git(root, "show", "-s", "--format=%T", value["repository_commit"]) == value["repository_tree"],
            "M22 follow-up source repository identity drifted")


def expected_identity(root: pathlib.Path, report: dict[str, Any]) -> dict[str, Any]:
    qualification = load(root / runner.QUALIFICATION)
    runtime = load(root / runner.RUNTIME_SOURCE)
    bwrap_raw = shutil.which("bwrap")
    require(bwrap_raw is not None, "bubblewrap is unavailable for M22 follow-up evidence validation")
    return {
        "aggregate_schema_sha256": runner.sha256(root / runner.EVIDENCE_SCHEMA),
        "bubblewrap_sha256": runner.sha256(pathlib.Path(bwrap_raw).resolve()),
        "checkpoint_id": qualification["finalized_selection"]["checkpoint_id"],
        "evaluation_manifest_schema_sha256": runner.sha256(root / runner.MANIFEST_SCHEMA),
        "evaluator_executable_sha256": report["identity"]["evaluator_executable_sha256"],
        "evaluator_report_schema_sha256": runner.sha256(root / runner.EVALUATOR_SCHEMA),
        "immutable_final_v1_evidence_sha256": runner.sha256(root / runner.IMMUTABLE_FINAL),
        "learning_contract_sha256": runner.sha256(root / runner.CONTRACT),
        "native_executable_sha256": runtime["executable"]["sha256"],
        "native_source_tree": runtime["source"]["tree"],
        "qualification_evidence_sha256": runner.sha256(root / runner.QUALIFICATION),
        "runtime_source_sha256": runner.sha256(root / runner.RUNTIME_SOURCE),
    }


def validate_live_evaluator(
    run: dict[str, Any], case_root: pathlib.Path, evaluator_schema: dict[str, Any], checkpoint_id: str,
) -> None:
    root = case_root / "evaluator"
    process = run["evaluator"]["process"]
    for path_key, digest_key in (("stdout_path", "stdout_sha256"), ("stderr_path", "stderr_sha256")):
        path = root / process[path_key]
        require(path.is_file() and not path.is_symlink() and runner.sha256(path) == process[digest_key],
                f"M22 follow-up evaluator stream identity drifted: {run['public_case']['case_id']}/{path_key}")
    if run["evaluator"]["status"] == "PASS":
        path = root / run["evaluator"]["report_path"]
        require(path.is_file() and not path.is_symlink() and runner.sha256(path) == run["evaluator"]["report_sha256"],
                f"M22 follow-up evaluator report identity drifted: {run['public_case']['case_id']}")
        value = load(path)
        schema_validate(value, evaluator_schema, "retained M22 follow-up evaluator report")
        require(value["checkpoint"]["id"] == checkpoint_id and
                value["public_state"] == runner.evaluator_public_case(run["public_case"]) and
                value["policy"]["action"] == run["evaluator"]["action"] and
                value["policy"]["legal_active_program"] == runner.public_program(run["public_case"]),
                f"M22 retained follow-up evaluator semantic drifted: {run['public_case']['case_id']}")


def validate_live_native(run: dict[str, Any], case_root: pathlib.Path, identity: dict[str, Any]) -> None:
    root = case_root / "native"
    require(runner.artifact_inventory(root) == run["native"]["artifact_inventory"],
            f"M22 follow-up native artifact inventory drifted: {run['public_case']['case_id']}")
    if run["native"]["status"] != "PASS":
        return
    record = run["native"]["record"]
    require(record["case"] == run["public_case"] and
            record["executable_sha256"] == identity["native_executable_sha256"] and
            record["source_tree"] == identity["native_source_tree"],
            f"M22 follow-up native public/source identity drifted: {run['public_case']['case_id']}")
    for path_key, digest_key in (("manifest_path", "manifest_sha256"), ("report_path", "report_sha256"),
                                 ("openttd_log_path", "openttd_log_sha256")):
        path = root / record[path_key]
        require(path.is_file() and not path.is_symlink() and runner.sha256(path) == record[digest_key],
                f"M22 follow-up native artifact identity drifted: {run['public_case']['case_id']}/{path_key}")


def validate_run(
    run: dict[str, Any], case: dict[str, Any], ordinal: int, identity: dict[str, Any],
    artifact_root: pathlib.Path | None, evaluator_schema: dict[str, Any],
) -> None:
    require(run["ordinal"] == ordinal and run["private_seed"] == case["seed"] and
            run["required_program"] == case["required_program"] and run["public_case"] == runner.public_case(case),
            f"M22 follow-up case projection/order drifted at ordinal {ordinal}")
    expected_artifact = f"cases/{ordinal:02d}-{case['case_id']}"
    require(run["artifact_path"] == expected_artifact, f"M22 follow-up case artifact path drifted: {case['case_id']}")
    evaluator = run["evaluator"]
    if evaluator["status"] == "PASS":
        require(evaluator["failure_category"] is None and evaluator["failure_detail"] is None and
                evaluator["action"] in runner.PROGRAMS and
                evaluator["action_index"] == runner.PROGRAM_INDEX[evaluator["action"]] and
                evaluator["legal_active_program"] == runner.public_program(case),
                f"M22 follow-up evaluator semantic record drifted: {case['case_id']}")
    else:
        require(evaluator["failure_category"] in runner.FAILURES[:4] and evaluator["action"] is None and
                evaluator["action_index"] is None and evaluator["legal_active_program"] is None,
                f"M22 follow-up evaluator failure record drifted: {case['case_id']}")
    native_result = run["native"]
    if native_result["status"] == "PASS":
        require(native_result["failure_category"] is None and native_result["failure_detail"] is None and
                native_result["record"] is not None, f"M22 follow-up native success record drifted: {case['case_id']}")
    else:
        require(native_result["failure_category"] == "native-execution" and native_result["record"] is None,
                f"M22 follow-up native failure record drifted: {case['case_id']}")
    expected_scores = runner.case_scores(case, evaluator, native_result)
    require(run["scores"] == expected_scores, f"M22 follow-up case score drifted: {case['case_id']}")
    require(run["failures"] == runner.failure_categories(case, evaluator, native_result, expected_scores),
            f"M22 follow-up case failure classification drifted: {case['case_id']}")
    if artifact_root is not None:
        case_root = artifact_root / expected_artifact
        require(case_root.is_dir() and not case_root.is_symlink(),
                f"M22 follow-up case artifact root is absent: {case['case_id']}")
        record_path = case_root / "case-record.json"
        require(record_path.is_file() and not record_path.is_symlink() and load(record_path) == run,
                f"M22 retained follow-up case record drifted: {case['case_id']}")
        validate_live_evaluator(run, case_root, evaluator_schema, identity["checkpoint_id"])
        validate_live_native(run, case_root, identity)


def validate_value(
    report: dict[str, Any], root: pathlib.Path, *, artifact_root: pathlib.Path | None = None,
    manifest_value: dict[str, Any] | None = None, manifest_bytes: bytes | None = None,
    evaluator_executable: pathlib.Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    schema_validate(report, load(root / runner.EVIDENCE_SCHEMA), "M22 follow-up evaluation evidence")
    unsigned = copy.deepcopy(report)
    claimed = unsigned.pop("report_sha256")
    require(claimed == runner.sha256_bytes(runner.canonical_bytes(unsigned)),
            "M22 follow-up report digest drifted")
    validate_source(report["source"], root)
    identity = expected_identity(root, report)
    require(report["identity"] == identity, "M22 follow-up identity binding drifted")
    if evaluator_executable is not None:
        evaluator_executable = evaluator_executable.resolve()
        require(evaluator_executable.is_file() and not evaluator_executable.is_symlink() and
                os.access(evaluator_executable, os.X_OK) and
                runner.sha256(evaluator_executable) == identity["evaluator_executable_sha256"],
                "M22 follow-up evaluator executable identity drifted")

    manifest_path = root / report["manifest"]["path"]
    if manifest_bytes is None:
        manifest_bytes = manifest_path.read_bytes()
    if manifest_value is None:
        try:
            manifest_value = json.loads(manifest_bytes, parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"nonfinite JSON constant: {token}")))
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise M22FollowupEvidenceError(f"cannot decode follow-up manifest: {exc}") from exc
    require(isinstance(manifest_value, dict), "M22 follow-up manifest root is not an object")
    runner.manifest_validator.validate_value(root, manifest_value, manifest_bytes)
    require(report["manifest"] == {
        "case_count": 42, "id": manifest_value["manifest_id"], "path": runner.MANIFEST.as_posix(),
        "sha256": runner.sha256_bytes(manifest_bytes),
    }, "M22 follow-up manifest record drifted")
    immutable = load(root / runner.IMMUTABLE_FINAL)
    require(report["immutable_final_v1"] == runner.immutable_final_record(root, immutable),
            "M22 immutable final-v1 boundary drifted in follow-up evidence")
    if artifact_root is not None:
        artifact_root = artifact_root.resolve()
        require(str(artifact_root) == report["artifact_root"] and artifact_root.is_dir() and
                not artifact_root.is_symlink(), "M22 follow-up artifact root drifted")
    evaluator_schema = load(root / runner.EVALUATOR_SCHEMA)
    preflight = report["preflight"]
    require(preflight["public_case"] == runner.public_case(runner.PREFLIGHT_CASE) and
            preflight["evaluator"]["status"] == "PASS" and
            preflight["evaluator"]["action"] == runner.PREFLIGHT_CASE["required_program"],
            "M22 follow-up evaluator preflight record drifted")
    if artifact_root is not None:
        preflight_root = artifact_root / "preflight"
        record_path = preflight_root / "preflight-record.json"
        require(record_path.is_file() and not record_path.is_symlink() and load(record_path) == preflight,
                "M22 retained follow-up evaluator preflight record drifted")
        validate_live_evaluator(preflight, preflight_root, evaluator_schema, identity["checkpoint_id"])
    cases = manifest_value["cases"]
    require(len(report["runs"]) == len(cases) == 42, "M22 follow-up run inventory drifted")
    for ordinal, (run, case) in enumerate(zip(report["runs"], cases, strict=True)):
        validate_run(run, case, ordinal, identity, artifact_root, evaluator_schema)
    expected_protocol = runner.protocol_record(report["runs"], [case["case_id"] for case in cases])
    require(report["protocol"] == expected_protocol, "M22 follow-up protocol accounting drifted")
    expected_statistics = runner.aggregate_statistics(report["runs"])
    require(report["statistics"] == expected_statistics, "M22 follow-up statistics drifted")
    expected_acceptance = runner.acceptance(report["runs"], expected_statistics, expected_protocol)
    require(report["acceptance"] == expected_acceptance, "M22 follow-up acceptance recomputation drifted")
    failure_counts = {category: sum(category in run["failures"] for run in report["runs"])
                      for category in runner.FAILURES}
    require(report["failure_counts"] == failure_counts, "M22 follow-up failure counts drifted")
    require(report["status"] == ("PASS" if expected_acceptance["overall"] else "FAIL"),
            "M22 follow-up status drifted")
    return {
        "cases": len(cases), "failures": sum(failure_counts.values()),
        "live": artifact_root is not None, "status": report["status"],
    }


def validate(
    root: pathlib.Path, config_path: pathlib.Path | None = None, *, artifact_root: pathlib.Path | None = None,
    evaluator_executable: pathlib.Path | None = None,
) -> dict[str, Any]:
    return validate_value(load(config_path or root / CONFIG), root, artifact_root=artifact_root,
                          evaluator_executable=evaluator_executable)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--artifact-root", type=pathlib.Path)
    parser.add_argument("--evaluator-executable", type=pathlib.Path)
    args = parser.parse_args()
    try:
        result = validate(args.root, args.config, artifact_root=args.artifact_root,
                          evaluator_executable=args.evaluator_executable)
    except (M22FollowupEvidenceError, runner.M22FollowupEvaluationError,
            runner.foundation.M22FinalEvaluationError, OSError, subprocess.SubprocessError,
            KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_FOLLOWUP_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1
    print(f"V2_M22_FOLLOWUP_EVIDENCE={result['status']} cases={result['cases']} failures={result['failures']} "
          f"live={str(result['live']).lower()}")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
