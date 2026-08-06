#!/usr/bin/env python3
"""Independently validate M22's complete one-shot follow-up evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from typing import Any

import jsonschema

import artifact_context
from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    LiveInputManifest,
    RoleRequirement,
    ToolRequirement,
    add_artifact_root_argument,
)
import run_m22_followup_evaluation as runner
from source_context import SourceContextError, run_git


CONFIG = pathlib.Path("config/v2/m22-followup-evaluation-evidence.json")
RESULT_LOGICAL_SET = "v2-m22-followup-evaluation-a"
LIVE_CONSUMER = "m22-followup-evaluation"
EXPECTED_RESULT_INPUTS = 359
BWRAP_SHA256 = runner.foundation.BWRAP_SHA256
EVALUATOR_SHA256 = runner.foundation.EVALUATOR_SHA256


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


def _safe_relative(value: str, *, label: str) -> str:
    require(isinstance(value, str) and value and not value.startswith("/") and
            "\\" not in value and "\x00" not in value and
            all(part not in {"", ".", ".."} for part in value.split("/")),
            f"{label} is not a safe relative POSIX path")
    return value


def _historical_blob(root: pathlib.Path, commit: str, relative: str) -> bytes:
    _safe_relative(relative, label="M22 follow-up historical source path")
    try:
        completed = run_git("show", f"{commit}:{relative}", repository=root)
    except SourceContextError as exc:
        raise M22FollowupEvidenceError(f"M22 follow-up historical source is unavailable: {relative}: {exc}") from exc
    require(completed.returncode == 0, f"M22 follow-up historical source is unavailable: {relative}")
    return completed.stdout


def _commit_tree(root: pathlib.Path, commit: str) -> str:
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "M22 follow-up source commit is malformed")
    try:
        exists = run_git("cat-file", "-e", f"{commit}^{{commit}}", repository=root)
        body = run_git("cat-file", "-p", commit, repository=root)
    except SourceContextError as exc:
        raise M22FollowupEvidenceError(f"M22 follow-up source repository identity is unavailable: {exc}") from exc
    first = body.stdout.splitlines()[0] if body.stdout else b""
    require(exists.returncode == 0 and body.returncode == 0 and first.startswith(b"tree "),
            "M22 follow-up source repository identity drifted")
    return first.removeprefix(b"tree ").decode("ascii")


def validate_source(value: dict[str, Any], root: pathlib.Path) -> None:
    require(isinstance(value, dict) and isinstance(value.get("files"), list),
            "M22 follow-up source identity is malformed")
    require([item.get("path") for item in value["files"] if isinstance(item, dict)] == list(runner.SOURCE_PATHS),
            "M22 follow-up source inventory/order drifted")
    commit = value.get("repository_commit")
    require(isinstance(commit, str), "M22 follow-up source commit is malformed")
    for record in value["files"]:
        require(set(record) == {"path", "sha256"} and isinstance(record["sha256"], str),
                "M22 follow-up source file record is malformed")
        require(hashlib.sha256(_historical_blob(root, commit, record["path"])).hexdigest() == record["sha256"],
                f"M22 follow-up source identity drifted: {record['path']}")
    require(value["tree_sha256"] == runner.sha256_bytes(runner.canonical_bytes(value["files"])),
            "M22 follow-up source inventory digest drifted")
    require(_commit_tree(root, commit) == value.get("repository_tree"),
            "M22 follow-up source repository identity drifted")


def expected_identity(root: pathlib.Path, report: dict[str, Any]) -> dict[str, Any]:
    qualification = load(root / runner.QUALIFICATION)
    runtime = load(root / runner.RUNTIME_SOURCE)
    return {
        "aggregate_schema_sha256": runner.sha256(root / runner.EVIDENCE_SCHEMA),
        "bubblewrap_sha256": BWRAP_SHA256,
        "checkpoint_id": qualification["finalized_selection"]["checkpoint_id"],
        "evaluation_manifest_schema_sha256": runner.sha256(root / runner.MANIFEST_SCHEMA),
        "evaluator_executable_sha256": EVALUATOR_SHA256,
        "evaluator_report_schema_sha256": runner.sha256(root / runner.EVALUATOR_SCHEMA),
        "immutable_final_v1_evidence_sha256": runner.sha256(root / runner.IMMUTABLE_FINAL),
        "learning_contract_sha256": runner.sha256(root / runner.CONTRACT),
        "native_executable_sha256": runtime["executable"]["sha256"],
        "native_source_tree": runtime["source"]["tree"],
        "qualification_evidence_sha256": runner.sha256(root / runner.QUALIFICATION),
        "runtime_source_sha256": runner.sha256(root / runner.RUNTIME_SOURCE),
    }


def _file_requirement(relative: str, digest: str) -> ArtifactRequirement:
    return ArtifactRequirement(
        RESULT_LOGICAL_SET, _safe_relative(relative, label="M22 follow-up live-input path"),
        "file", LIVE_CONSUMER, digest,
    )


def _evaluator_requirements(base: str, evaluator: dict[str, Any]) -> list[ArtifactRequirement]:
    process = evaluator["process"]
    require(process["stdout_path"] == "evaluator.stdout" and process["stderr_path"] == "evaluator.stderr",
            "M22 follow-up evaluator artifact paths drifted")
    result = [
        _file_requirement(f"{base}/evaluator/{process[path_key]}", process[digest_key])
        for path_key, digest_key in (("stdout_path", "stdout_sha256"), ("stderr_path", "stderr_sha256"))
    ]
    if evaluator["status"] == "PASS":
        require(evaluator["report_path"] == "evaluator-report.json",
                "M22 follow-up evaluator report path drifted")
        result.append(_file_requirement(f"{base}/evaluator/{evaluator['report_path']}", evaluator["report_sha256"]))
    return result


def _result_requirements(report: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    recorded = pathlib.PurePosixPath(report["artifact_root"])
    require(recorded.is_absolute() and recorded.name == RESULT_LOGICAL_SET,
            "M22 follow-up artifact root drifted")
    requirements: list[ArtifactRequirement] = [
        _file_requirement("preflight/preflight-record.json",
                          runner.sha256_bytes(runner.canonical_bytes(report["preflight"]))),
        *_evaluator_requirements("preflight", report["preflight"]["evaluator"]),
    ]
    seen_case_ids: set[str] = set()
    for ordinal, run in enumerate(report["runs"]):
        case_id = _safe_relative(run["public_case"]["case_id"], label="M22 follow-up case id")
        require("/" not in case_id and case_id not in seen_case_ids, "M22 follow-up case identity/order drifted")
        seen_case_ids.add(case_id)
        expected_base = f"cases/{ordinal:02d}-{case_id}"
        require(run["ordinal"] == ordinal and run["artifact_path"] == expected_base,
                "M22 follow-up case artifact root drifted")
        base = _safe_relative(run["artifact_path"], label="M22 follow-up case artifact path")
        requirements.append(_file_requirement(
            f"{base}/case-record.json", runner.sha256_bytes(runner.canonical_bytes(run)),
        ))
        requirements.extend(_evaluator_requirements(base, run["evaluator"]))
        inventory = run["native"]["artifact_inventory"]
        require(isinstance(inventory, list), "M22 follow-up native artifact inventory is malformed")
        by_path: dict[str, dict[str, Any]] = {}
        for item in inventory:
            require(isinstance(item, dict) and set(item) == {"bytes", "path", "sha256"} and
                    isinstance(item["bytes"], int) and not isinstance(item["bytes"], bool) and item["bytes"] >= 0,
                    "M22 follow-up native artifact inventory bytes/shape drifted")
            path = _safe_relative(item["path"], label="M22 follow-up native artifact path")
            require(path not in by_path and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is not None,
                    "M22 follow-up native artifact inventory path/digest drifted")
            by_path[path] = item
            requirements.append(_file_requirement(f"{base}/native/{path}", item["sha256"]))
        require(tuple(by_path) == runner.native.expected_artifact_paths(run["public_case"], run["native"]["status"]),
                "M22 follow-up native artifact inventory drifted")
        if run["native"]["status"] == "PASS":
            record = run["native"]["record"]
            for path_key, digest_key, expected_path in (
                ("manifest_path", "manifest_sha256", "manifest.json"),
                ("openttd_log_path", "openttd_log_sha256", "openttd.log"),
                ("report_path", "report_sha256", "report.json"),
            ):
                require(record[path_key] == expected_path and
                        record[digest_key] == by_path[expected_path]["sha256"],
                        "M22 follow-up native record/inventory binding drifted")
    require(len(requirements) == EXPECTED_RESULT_INPUTS and len(set(requirements)) == EXPECTED_RESULT_INPUTS,
            f"M22 follow-up live-input closure must contain exactly {EXPECTED_RESULT_INPUTS} files")
    return tuple(requirements)


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    return (*_result_requirements(load(root / CONFIG)), *runner.runtime_validator.required_live_inputs(root))


def _close_tree(path: pathlib.Path, expected: set[str]) -> None:
    actual: set[str] = set()
    for item in path.rglob("*"):
        require(not item.is_symlink(), f"M22 follow-up artifacts contain a symlink: {item}")
        if item.is_file():
            actual.add(item.relative_to(path).as_posix())
    require(actual == expected, "M22 follow-up artifact file inventory drifted")


def _preflight_live(
    context: ArtifactContext, root: pathlib.Path, report: dict[str, Any],
    result_requirements: tuple[ArtifactRequirement, ...],
    live_inputs: LiveInputManifest | None, bwrap_path: pathlib.Path | None,
) -> dict[str, pathlib.Path]:
    require(live_inputs is not None and live_inputs.is_live,
            "M22 follow-up live-input manifest is required")
    require(live_inputs.artifact_root == context.artifact_root,
            "M22 follow-up live-input manifest root differs from artifact context")
    require(bwrap_path is not None, "M22 follow-up bwrap tool path is required")
    runtime_requirements = runner.runtime_validator.required_live_inputs(root)
    context.preflight((*result_requirements, *runtime_requirements))
    evaluator_requirement = RoleRequirement(
        "final-v1-evaluator", ".", "file", LIVE_CONSUMER, EVALUATOR_SHA256,
    )
    live_inputs.preflight((evaluator_requirement,))
    artifact_context.preflight_tools((ToolRequirement(
        "bwrap", pathlib.Path(bwrap_path), report["identity"]["bubblewrap_sha256"],
    ),))
    resolved = [context.resolve(item) for item in result_requirements]
    resolved.append(live_inputs.resolve(evaluator_requirement))
    identities: dict[tuple[int, int], pathlib.Path] = {}
    for path in resolved:
        stat = path.stat()
        require(stat.st_nlink == 1, f"M22 follow-up live input is a hard link: {path}")
        key = (stat.st_dev, stat.st_ino)
        require(key not in identities,
                f"M22 follow-up live inputs alias one file: {identities.get(key)} and {path}")
        identities[key] = path
    result_root = context.artifact_set(RESULT_LOGICAL_SET)
    _close_tree(result_root, {item.relative_path for item in result_requirements})
    return {item.relative_path: context.resolve(item) for item in result_requirements}


def validate_live_evaluator(
    run: dict[str, Any], base: str, files: dict[str, pathlib.Path],
    evaluator_schema: dict[str, Any], checkpoint_id: str,
) -> None:
    process = run["evaluator"]["process"]
    for path_key, digest_key in (("stdout_path", "stdout_sha256"), ("stderr_path", "stderr_sha256")):
        path = files[f"{base}/evaluator/{process[path_key]}"]
        require(path.is_file() and not path.is_symlink() and runner.sha256(path) == process[digest_key],
                f"M22 follow-up evaluator stream identity drifted: {run['public_case']['case_id']}/{path_key}")
    if run["evaluator"]["status"] == "PASS":
        path = files[f"{base}/evaluator/{run['evaluator']['report_path']}"]
        require(path.is_file() and not path.is_symlink() and runner.sha256(path) == run["evaluator"]["report_sha256"],
                f"M22 follow-up evaluator report identity drifted: {run['public_case']['case_id']}")
        value = load(path)
        schema_validate(value, evaluator_schema, "retained M22 follow-up evaluator report")
        require(value["checkpoint"]["id"] == checkpoint_id and
                value["public_state"] == runner.evaluator_public_case(run["public_case"]) and
                value["policy"]["action"] == run["evaluator"]["action"] and
                value["policy"]["legal_active_program"] == runner.public_program(run["public_case"]),
                f"M22 retained follow-up evaluator semantic drifted: {run['public_case']['case_id']}")


def validate_run(
    run: dict[str, Any], case: dict[str, Any], ordinal: int, identity: dict[str, Any],
    live_files: dict[str, pathlib.Path] | None, evaluator_schema: dict[str, Any], *,
    root: pathlib.Path | None = None, runtime_source: dict[str, Any] | None = None,
    runtime: runner.native.RuntimePaths | None = None,
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
        require(native_result["failure_category"] == "native-execution" and native_result["record"] is None and
                runner.native.expected_failure_marker(case) in native_result["failure_detail"],
                f"M22 follow-up native failure record drifted: {case['case_id']}")
    expected_scores = runner.case_scores(case, evaluator, native_result)
    require(run["scores"] == expected_scores, f"M22 follow-up case score drifted: {case['case_id']}")
    require(run["failures"] == runner.failure_categories(case, evaluator, native_result, expected_scores),
            f"M22 follow-up case failure classification drifted: {case['case_id']}")
    if live_files is not None:
        record_path = live_files[f"{expected_artifact}/case-record.json"]
        require(record_path.is_file() and not record_path.is_symlink() and load(record_path) == run,
                f"M22 retained follow-up case record drifted: {case['case_id']}")
        validate_live_evaluator(run, expected_artifact, live_files, evaluator_schema, identity["checkpoint_id"])
        require(root is not None and runtime_source is not None and runtime is not None,
                "M22 follow-up native semantic context is absent after preflight")
        try:
            runner.final_evidence_validator.validate_preflighted_native(
                root, run, expected_artifact, live_files, identity, runtime_source, runtime,
            )
        except runner.final_evidence_validator.M22FinalEvidenceError as exc:
            raise M22FollowupEvidenceError(f"M22 follow-up native semantic validation failed: {exc}") from exc


def validate_value(
    report: dict[str, Any], root: pathlib.Path, *, artifact_context: ArtifactContext | None = None,
    live_inputs: LiveInputManifest | None = None, bwrap_path: pathlib.Path | None = None,
    manifest_value: dict[str, Any] | None = None, manifest_bytes: bytes | None = None,
) -> dict[str, Any]:
    context = artifact_context or ArtifactContext.offline()
    root = root.resolve()
    schema_validate(report, load(root / runner.EVIDENCE_SCHEMA), "M22 follow-up evaluation evidence")
    unsigned = copy.deepcopy(report)
    claimed = unsigned.pop("report_sha256")
    require(claimed == runner.sha256_bytes(runner.canonical_bytes(unsigned)),
            "M22 follow-up report digest drifted")
    validate_source(report["source"], root)
    identity = expected_identity(root, report)
    require(report["identity"] == identity, "M22 follow-up identity binding drifted")
    require(identity["bubblewrap_sha256"] == BWRAP_SHA256,
            "M22 follow-up bubblewrap frozen identity drifted")
    result_requirements = _result_requirements(report)

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
    live_files: dict[str, pathlib.Path] | None = None
    runtime_source: dict[str, Any] | None = None
    runtime: runner.native.RuntimePaths | None = None
    if context.is_live:
        live_files = _preflight_live(
            context, root, report, result_requirements, live_inputs, bwrap_path,
        )
        runner.runtime_validator.validate(root, artifact_context=context)
        runtime_source = load(root / runner.RUNTIME_SOURCE)
        runtime = runner.runtime_paths(runtime_source, context)
    evaluator_schema = load(root / runner.EVALUATOR_SCHEMA)
    preflight = report["preflight"]
    require(preflight["public_case"] == runner.public_case(runner.PREFLIGHT_CASE) and
            preflight["evaluator"]["status"] == "PASS" and
            preflight["evaluator"]["action"] == runner.PREFLIGHT_CASE["required_program"],
            "M22 follow-up evaluator preflight record drifted")
    if live_files is not None:
        record_path = live_files["preflight/preflight-record.json"]
        require(record_path.is_file() and not record_path.is_symlink() and load(record_path) == preflight,
                "M22 retained follow-up evaluator preflight record drifted")
        validate_live_evaluator(preflight, "preflight", live_files, evaluator_schema, identity["checkpoint_id"])
    cases = manifest_value["cases"]
    require(len(report["runs"]) == len(cases) == 42, "M22 follow-up run inventory drifted")
    for ordinal, (run, case) in enumerate(zip(report["runs"], cases, strict=True)):
        validate_run(
            run, case, ordinal, identity, live_files, evaluator_schema,
            root=root, runtime_source=runtime_source, runtime=runtime,
        )
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
    require(len(cases) == 42 and report["status"] == "FAIL" and sum(failure_counts.values()) == 0,
            "M22 follow-up-v1 frozen result drifted")
    return {
        "cases": len(cases), "failures": sum(failure_counts.values()),
        "live": context.is_live, "status": report["status"],
    }


def validate(
    root: pathlib.Path, config_path: pathlib.Path | None = None, *,
    artifact_context: ArtifactContext | None = None,
    live_inputs: LiveInputManifest | None = None,
    bwrap_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    context = artifact_context or ArtifactContext.offline()
    if live_inputs is None:
        live_inputs = LiveInputManifest.load(context.artifact_root) if context.is_live else None
    return validate_value(
        load(config_path or root / CONFIG), root, artifact_context=context,
        live_inputs=live_inputs, bwrap_path=bwrap_path,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    add_artifact_root_argument(parser)
    parser.add_argument("--evaluator", type=pathlib.Path)
    parser.add_argument("--bwrap", type=pathlib.Path)
    args = parser.parse_args()
    try:
        common_root = args.artifact_root
        context = ArtifactContext.offline() if common_root is None else ArtifactContext.live(common_root)
        live_inputs = None if common_root is None else LiveInputManifest.bind(
            context, {"final-v1-evaluator": args.evaluator}
        )
        result = validate(
            args.root, args.config, artifact_context=context,
            live_inputs=live_inputs, bwrap_path=args.bwrap,
        )
    except (M22FollowupEvidenceError, runner.M22FollowupEvaluationError,
            runner.foundation.M22FinalEvaluationError, runner.runtime_validator.M22FollowupRuntimeSourceError,
            ArtifactContextError, SourceContextError, OSError, subprocess.SubprocessError,
            KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_FOLLOWUP_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1
    print(f"V2_M22_FOLLOWUP_EVIDENCE={result['status']} cases={result['cases']} failures={result['failures']} "
          f"live={str(result['live']).lower()}")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
