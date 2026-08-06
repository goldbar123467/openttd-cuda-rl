#!/usr/bin/env python3
"""Independently validate M22's complete one-shot final-evaluation evidence."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from typing import Any

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
import m22_evaluation_validation as evaluation_common
import run_m22_final_evaluation as runner
import qualify_m15_native_map as map_validator
import validate_m22_final_runtime_source as runtime_validator
from source_context import SourceContextError


CONFIG = pathlib.Path("config/v2/m22-final-evaluation-evidence.json")
PRIOR_LOGICAL_SET = "v2-m22-final-evaluation-a"
RESULT_LOGICAL_SET = "v2-m22-final-evaluation-b"
LIVE_CONSUMER = "m22-final-evaluation"
EXPECTED_RESULT_INPUTS = 351
EXPECTED_PRIOR_INPUTS = 4
BWRAP_SHA256 = "52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712"
EVALUATOR_SHA256 = "bc87f4608643b4664068381fa5136d464c44bd05dad09a66fa088bfa995b92e6"


class M22FinalEvidenceError(ValueError):
    """The retained M22 final evidence is incomplete, inconsistent, or drifted."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22FinalEvidenceError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    return evaluation_common.load_json_object(path, error_type=M22FinalEvidenceError)


def schema_validate(value: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    evaluation_common.validate_schema(value, schema, label, error_type=M22FinalEvidenceError)


def _safe_relative(value: str, *, label: str) -> str:
    require(isinstance(value, str) and value and not value.startswith("/") and
            "\\" not in value and "\x00" not in value and
            all(part not in {"", ".", ".."} for part in value.split("/")),
            f"{label} is not a safe relative POSIX path")
    return value


def validate_source(value: dict[str, Any], root: pathlib.Path) -> None:
    try:
        evaluation_common.validate_source_identity(
            value, root, mechanics=runner, suite_label="M22 final", require=require,
        )
    except evaluation_common._CommitTreeError as exc:
        message = (
            "M22 final source commit has no tree"
            if exc.reason == "no-tree"
            else "M22 final source repository identity drifted"
        )
        require(False, message)
        raise AssertionError("require() returned after rejecting source commit tree")


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
        "learning_contract_sha256": runner.sha256(root / runner.CONTRACT),
        "native_executable_sha256": runtime["executable"]["sha256"],
        "native_source_tree": runtime["source"]["tree"],
        "prior_attempt_sha256": runner.sha256(root / runner.PRIOR_ATTEMPT),
        "qualification_evidence_sha256": runner.sha256(root / runner.QUALIFICATION),
        "runtime_source_sha256": runner.sha256(root / runner.RUNTIME_SOURCE),
    }


def _file_requirement(logical_set: str, relative: str, digest: str) -> ArtifactRequirement:
    return ArtifactRequirement(
        logical_set, _safe_relative(relative, label="M22 final live-input path"),
        "file", LIVE_CONSUMER, digest,
    )


def _prior_requirements(prior: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    recorded_root = pathlib.PurePosixPath(prior["artifacts"]["root"])
    require(recorded_root.is_absolute() and recorded_root.name == PRIOR_LOGICAL_SET,
            "M22 rejected-attempt artifact root drifted")
    expected_paths = {
        "evaluator_report": "preflight/evaluator/evaluator-report.json",
        "preflight_record": "preflight/preflight-record.json",
        "stderr": "preflight/evaluator/evaluator.stderr",
        "stdout": "preflight/evaluator/evaluator.stdout",
    }
    requirements_list: list[ArtifactRequirement] = []
    for name in ("evaluator_report", "preflight_record", "stderr", "stdout"):
        record = prior["artifacts"][name]
        require(isinstance(record, dict) and set(record) == {"bytes", "path", "sha256"} and
                record["path"] == expected_paths[name] and isinstance(record["bytes"], int) and
                not isinstance(record["bytes"], bool) and record["bytes"] >= 0,
                "M22 rejected-attempt artifact descriptor drifted")
        requirements_list.append(_file_requirement(
            PRIOR_LOGICAL_SET, record["path"], record["sha256"],
        ))
    requirements = tuple(requirements_list)
    require(len(requirements) == EXPECTED_PRIOR_INPUTS and len(set(requirements)) == EXPECTED_PRIOR_INPUTS,
            "M22 rejected-attempt live-input closure drifted")
    return requirements


def _evaluator_requirements(
    logical_set: str, base: str, evaluator: dict[str, Any],
) -> list[ArtifactRequirement]:
    process = evaluator["process"]
    require(process["stdout_path"] == "evaluator.stdout" and process["stderr_path"] == "evaluator.stderr",
            "M22 final evaluator artifact paths drifted")
    result = [
        _file_requirement(logical_set, f"{base}/evaluator/{process[path_key]}", process[digest_key])
        for path_key, digest_key in (("stdout_path", "stdout_sha256"), ("stderr_path", "stderr_sha256"))
    ]
    if evaluator["status"] == "PASS":
        require(evaluator["report_path"] == "evaluator-report.json",
                "M22 final evaluator report path drifted")
        result.append(_file_requirement(
            logical_set, f"{base}/evaluator/{evaluator['report_path']}", evaluator["report_sha256"],
        ))
    return result


def _result_requirements(report: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    recorded_root = pathlib.PurePosixPath(report["artifact_root"])
    require(recorded_root.is_absolute() and recorded_root.name == RESULT_LOGICAL_SET,
            "M22 final artifact root drifted")
    requirements: list[ArtifactRequirement] = [
        _file_requirement(
            RESULT_LOGICAL_SET, "preflight/preflight-record.json",
            runner.sha256_bytes(runner.canonical_bytes(report["preflight"])),
        ),
        *_evaluator_requirements(RESULT_LOGICAL_SET, "preflight", report["preflight"]["evaluator"]),
    ]
    seen_case_ids: set[str] = set()
    for ordinal, run in enumerate(report["runs"]):
        case_id = _safe_relative(run["public_case"]["case_id"], label="M22 final case id")
        require("/" not in case_id and case_id not in seen_case_ids, "M22 final case identity/order drifted")
        seen_case_ids.add(case_id)
        expected_base = f"cases/{ordinal:02d}-{case_id}"
        require(run["ordinal"] == ordinal and run["artifact_path"] == expected_base,
                "M22 final case artifact root drifted")
        base = _safe_relative(run["artifact_path"], label="M22 final case artifact path")
        requirements.append(_file_requirement(
            RESULT_LOGICAL_SET, f"{base}/case-record.json",
            runner.sha256_bytes(runner.canonical_bytes(run)),
        ))
        requirements.extend(_evaluator_requirements(RESULT_LOGICAL_SET, base, run["evaluator"]))
        inventory = run["native"]["artifact_inventory"]
        require(isinstance(inventory, list), "M22 final native artifact inventory is malformed")
        by_path: dict[str, dict[str, Any]] = {}
        for item in inventory:
            require(isinstance(item, dict) and set(item) == {"bytes", "path", "sha256"} and
                    isinstance(item["bytes"], int) and not isinstance(item["bytes"], bool) and item["bytes"] >= 0,
                    "M22 final native artifact inventory bytes/shape drifted")
            path = _safe_relative(item["path"], label="M22 final native artifact path")
            require(path not in by_path and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is not None,
                    "M22 final native artifact inventory path/digest drifted")
            by_path[path] = item
            requirements.append(_file_requirement(
                RESULT_LOGICAL_SET, f"{base}/native/{path}", item["sha256"],
            ))
        require(tuple(by_path) == runner.native.expected_artifact_paths(run["public_case"], run["native"]["status"]),
                "M22 final native artifact inventory drifted")
        if run["native"]["status"] == "PASS":
            record = run["native"]["record"]
            for path_key, digest_key, expected_path in (
                ("manifest_path", "manifest_sha256", "manifest.json"),
                ("openttd_log_path", "openttd_log_sha256", "openttd.log"),
                ("report_path", "report_sha256", "report.json"),
            ):
                require(record[path_key] == expected_path and
                        record[digest_key] == by_path[expected_path]["sha256"],
                        "M22 final native record/inventory binding drifted")
    require(len(requirements) == EXPECTED_RESULT_INPUTS and len(set(requirements)) == EXPECTED_RESULT_INPUTS,
            f"M22 final live-input closure must contain exactly {EXPECTED_RESULT_INPUTS} files")
    return tuple(requirements)


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    report = load(root / CONFIG)
    prior = load(root / runner.PRIOR_ATTEMPT)
    return (*_prior_requirements(prior), *_result_requirements(report),
            *runtime_validator.required_live_inputs(root))


def _close_tree(path: pathlib.Path, expected: set[str], *, label: str) -> None:
    actual: set[str] = set()
    for item in path.rglob("*"):
        require(not item.is_symlink(), f"{label} contains a symlink: {item}")
        if item.is_file():
            actual.add(item.relative_to(path).as_posix())
    require(actual == expected, f"{label} file inventory drifted")


def _preflight_live(
    context: ArtifactContext,
    root: pathlib.Path,
    report: dict[str, Any],
    prior: dict[str, Any],
    result_requirements: tuple[ArtifactRequirement, ...],
    live_inputs: LiveInputManifest | None,
    bwrap_path: pathlib.Path | None,
) -> tuple[pathlib.Path, dict[str, pathlib.Path], LiveInputManifest, pathlib.Path]:
    require(live_inputs is not None and live_inputs.is_live,
            "M22 final live-input manifest is required")
    require(live_inputs.artifact_root == context.artifact_root,
            "M22 final live-input manifest root differs from artifact context")
    require(bwrap_path is not None, "M22 final bwrap tool path is required")
    prior_requirements = _prior_requirements(prior)
    runtime_requirements = runtime_validator.required_live_inputs(root)
    aggregate = (*prior_requirements, *result_requirements, *runtime_requirements)
    context.preflight(aggregate)
    evaluator_requirement = RoleRequirement(
        "final-v1-evaluator", ".", "file", LIVE_CONSUMER, EVALUATOR_SHA256,
    )
    live_inputs.preflight((evaluator_requirement,))
    bwrap = pathlib.Path(bwrap_path)
    artifact_context.preflight_tools((ToolRequirement("bwrap", bwrap, report["identity"]["bubblewrap_sha256"]),))
    resolved_files = [context.resolve(item) for item in (*prior_requirements, *result_requirements)
                      if item.kind == "file"]
    resolved_files.append(live_inputs.resolve(evaluator_requirement))
    identities: dict[tuple[int, int], pathlib.Path] = {}
    for path in resolved_files:
        stat = path.stat()
        require(stat.st_nlink == 1, f"M22 final live input is a hard link: {path}")
        key = (stat.st_dev, stat.st_ino)
        require(key not in identities, f"M22 final live inputs alias one file: {identities.get(key)} and {path}")
        identities[key] = path
    prior_root = context.artifact_set(PRIOR_LOGICAL_SET)
    result_root = context.artifact_set(RESULT_LOGICAL_SET)
    _close_tree(prior_root, {item.relative_path for item in prior_requirements}, label="M22 rejected-attempt artifacts")
    _close_tree(result_root, {item.relative_path for item in result_requirements}, label="M22 final artifacts")
    result_files = {item.relative_path: context.resolve(item) for item in result_requirements}
    return prior_root, result_files, live_inputs, bwrap


def validate_live_evaluator(
    run: dict[str, Any], base: str, files: dict[str, pathlib.Path],
    evaluator_schema: dict[str, Any], checkpoint_id: str,
) -> None:
    process = run["evaluator"]["process"]
    for path_key, digest_key in (("stdout_path", "stdout_sha256"), ("stderr_path", "stderr_sha256")):
        path = files[f"{base}/evaluator/{process[path_key]}"]
        require(path.is_file() and not path.is_symlink() and runner.sha256(path) == process[digest_key],
                f"M22 evaluator stream identity drifted: {run['public_case']['case_id']}/{path_key}")
    if run["evaluator"]["status"] == "PASS":
        path = files[f"{base}/evaluator/{run['evaluator']['report_path']}"]
        require(path.is_file() and not path.is_symlink() and runner.sha256(path) == run["evaluator"]["report_sha256"],
                f"M22 evaluator report identity drifted: {run['public_case']['case_id']}")
        value = load(path)
        schema_validate(value, evaluator_schema, "retained M22 evaluator report")
        require(value["checkpoint"]["id"] == checkpoint_id and
                value["public_state"] == runner.evaluator_public_case(run["public_case"]) and
                value["policy"]["action"] == run["evaluator"]["action"] and
                value["policy"]["legal_active_program"] == runner.public_program(run["public_case"]),
                f"M22 retained evaluator semantic drifted: {run['public_case']['case_id']}")


def validate_preflighted_native(
    root: pathlib.Path, run: dict[str, Any], base: str, files: dict[str, pathlib.Path],
    identity: dict[str, Any], runtime_source: dict[str, Any], runtime: runner.native.RuntimePaths,
) -> None:
    """Validate one native result using only the aggregate-preflight path map."""

    case_id = run["public_case"]["case_id"]
    inventory = run["native"]["artifact_inventory"]
    for item in inventory:
        path = files[f"{base}/native/{item['path']}"]
        require(path.stat().st_size == item["bytes"] and runner.sha256(path) == item["sha256"],
                f"M22 native artifact bytes/digest drifted: {case_id}/{item['path']}")
    case = {**run["public_case"], "seed": run["private_seed"], "required_program": run["required_program"]}
    manifest_path = files[f"{base}/native/manifest.json"]
    try:
        manifest = runtime_validator._live_json(manifest_path, label=f"evaluation {case_id} manifest")
        require(manifest == runtime_validator._expected_smoke_manifest(root, runtime_source, runtime, case),
                f"M22 native manifest semantics drifted: {case_id}")
        log = files[f"{base}/native/openttd.log"].read_text(encoding="utf-8")
        require("\x00" not in log and "Traceback (most recent call last)" not in log,
                f"M22 native log semantics drifted: {case_id}")
        for item in inventory:
            if item["path"].endswith(".sav"):
                summary = map_validator.parse_save(files[f"{base}/native/{item['path']}"])
                require((summary["width"], summary["height"]) ==
                        (case["map_width"], case["map_height"]),
                        f"M22 native savegame map semantics drifted: {case_id}/{item['path']}")
        if run["native"]["status"] != "PASS":
            require(runner.native.expected_failure_marker(case) in run["native"]["failure_detail"] and
                    runner.native.expected_failure_marker(case) in log,
                    f"M22 native failure log semantics drifted: {case_id}")
            if "report.json" in {item["path"] for item in inventory}:
                runtime_validator._live_json(
                    files[f"{base}/native/report.json"], label=f"failed evaluation {case_id} report",
                )
            return
        record = run["native"]["record"]
        require(record["case"] == run["public_case"] and
                record["executable_sha256"] == identity["native_executable_sha256"] and
                record["source_tree"] == identity["native_source_tree"] and
                record["native_probe"] == runner.native.canonical_probe(case) and
                record["fresh_processes"] == 1 and record["network_unshared"] and record["status"] == "PASS",
                f"M22 native public/source/process identity drifted: {case_id}")
        report = runtime_validator._live_json(
            files[f"{base}/native/report.json"], label=f"evaluation {case_id} report",
        )
        metrics = runtime_validator._report_metrics(root, runtime_source, case, report)
        require(metrics == record["metrics"], f"M22 native report/metrics semantics drifted: {case_id}")
    except M22FinalEvidenceError:
        raise
    except (runtime_validator.M22RuntimeSourceError, map_validator.M15MapQualificationError,
            OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise M22FinalEvidenceError(f"M22 native semantic validation failed for {case_id}: {exc}") from exc


def validate_run(
    run: dict[str, Any], case: dict[str, Any], ordinal: int, identity: dict[str, Any],
    live_files: dict[str, pathlib.Path] | None, evaluator_schema: dict[str, Any], *,
    root: pathlib.Path | None = None, runtime_source: dict[str, Any] | None = None,
    runtime: runner.native.RuntimePaths | None = None,
) -> None:
    require(run["ordinal"] == ordinal and run["private_seed"] == case["seed"] and
            run["required_program"] == case["required_program"] and run["public_case"] == runner.public_case(case),
            f"M22 case projection/order drifted at ordinal {ordinal}")
    expected_artifact = f"cases/{ordinal:02d}-{case['case_id']}"
    require(run["artifact_path"] == expected_artifact, f"M22 case artifact path drifted: {case['case_id']}")
    evaluator = run["evaluator"]
    if evaluator["status"] == "PASS":
        require(evaluator["failure_category"] is None and evaluator["failure_detail"] is None and
                evaluator["action"] in runner.PROGRAMS and evaluator["action_index"] == runner.PROGRAM_INDEX[evaluator["action"]] and
                evaluator["legal_active_program"] == runner.public_program(case),
                f"M22 evaluator semantic record drifted: {case['case_id']}")
    else:
        require(evaluator["failure_category"] in runner.FAILURES[:4] and evaluator["action"] is None and
                evaluator["action_index"] is None and evaluator["legal_active_program"] is None,
                f"M22 evaluator failure record drifted: {case['case_id']}")
    native_result = run["native"]
    if native_result["status"] == "PASS":
        require(native_result["failure_category"] is None and native_result["failure_detail"] is None and
                native_result["record"] is not None, f"M22 native success record drifted: {case['case_id']}")
    else:
        require(native_result["failure_category"] == "native-execution" and native_result["record"] is None and
                runner.native.expected_failure_marker(case) in native_result["failure_detail"],
                f"M22 native failure semantics drifted: {case['case_id']}")
    expected_scores = runner.case_scores(case, evaluator, native_result)
    require(run["scores"] == expected_scores, f"M22 case score drifted: {case['case_id']}")
    require(run["failures"] == runner.failure_categories(case, evaluator, native_result, expected_scores),
            f"M22 case failure classification drifted: {case['case_id']}")
    if live_files is not None:
        record_path = live_files[f"{expected_artifact}/case-record.json"]
        require(record_path.is_file() and not record_path.is_symlink() and load(record_path) == run,
                f"M22 retained case record drifted: {case['case_id']}")
        validate_live_evaluator(run, expected_artifact, live_files, evaluator_schema, identity["checkpoint_id"])
        require(root is not None and runtime_source is not None and runtime is not None,
                "M22 native semantic context is absent after preflight")
        validate_preflighted_native(root, run, expected_artifact, live_files, identity, runtime_source, runtime)


def validate_value(
    report: dict[str, Any], root: pathlib.Path, *, artifact_context: ArtifactContext | None = None,
    live_inputs: LiveInputManifest | None = None, bwrap_path: pathlib.Path | None = None,
    manifest_value: dict[str, Any] | None = None, manifest_bytes: bytes | None = None,
) -> dict[str, Any]:
    context = artifact_context or ArtifactContext.offline()
    root = root.resolve()
    schema_validate(report, load(root / runner.EVIDENCE_SCHEMA), "M22 final evaluation evidence")
    evaluation_common.validate_report_digest(
        report, mechanics=runner, suite_label="M22 final", require=require,
    )
    validate_source(report["source"], root)
    identity = expected_identity(root, report)
    require(report["identity"] == identity, "M22 final identity binding drifted")
    require(identity["bubblewrap_sha256"] == BWRAP_SHA256,
            "M22 final bubblewrap frozen identity drifted")
    result_requirements = _result_requirements(report)
    manifest_path = root / report["manifest"]["path"]
    if manifest_bytes is None:
        try:
            manifest_bytes = manifest_path.read_bytes()
        except OSError as exc:
            raise M22FinalEvidenceError(f"cannot load final manifest {manifest_path}: {exc}") from exc
    try:
        decoded_manifest = json.loads(
            manifest_bytes, parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"nonfinite JSON constant: {token}")),
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise M22FinalEvidenceError(f"cannot decode final manifest {manifest_path}: {exc}") from exc
    require(isinstance(decoded_manifest, dict), f"final manifest root is not an object: {manifest_path}")
    if manifest_value is None:
        manifest_value = decoded_manifest
    require(manifest_value == decoded_manifest, "M22 final manifest bytes/value binding drifted")
    manifest_sha = runner.sha256_bytes(manifest_bytes)
    require(manifest_sha == report["manifest"]["sha256"], "M22 final manifest byte digest drifted")
    contract = load(root / runner.CONTRACT)
    prior_attempt = runner.validate_prior_attempt_record(root, contract)
    require(report["history"] == {
        "cases_attempted": prior_attempt["execution"]["cases_attempted"],
        "failure_category": prior_attempt["failure"]["category"],
        "manifest_reads": prior_attempt["manifest"]["reads"],
        "prior_attempt": runner.PRIOR_ATTEMPT.as_posix(), "status": prior_attempt["status"],
    }, "M22 rejected-attempt history projection drifted")
    runner.validate_manifest_value(
        root, manifest_value, manifest_sha, contract, load(root / runner.MANIFEST_SCHEMA),
    )
    require(report["manifest"] == {
        "case_count": 42, "id": manifest_value["manifest_id"], "path": runner.learning.EVALUATION.as_posix(),
        "sha256": manifest_sha,
    }, "M22 final manifest record drifted")
    live_files: dict[str, pathlib.Path] | None = None
    runtime_source: dict[str, Any] | None = None
    runtime: runner.native.RuntimePaths | None = None
    if context.is_live:
        prior_root, live_files, live_inputs, _ = _preflight_live(
            context, root, report, prior_attempt, result_requirements, live_inputs, bwrap_path,
        )
        runtime_validator.validate(root, artifact_context=context)
        runner.validate_prior_attempt_live(prior_attempt, prior_root)
        runtime_source = load(root / runner.RUNTIME_SOURCE)
        runtime = runner.runtime_paths(runtime_source, context)
    evaluator_schema = load(root / runner.EVALUATOR_SCHEMA)
    preflight = report["preflight"]
    require(preflight["public_case"] == runner.public_case(runner.PREFLIGHT_CASE) and
            preflight["evaluator"]["status"] == "PASS" and
            preflight["evaluator"]["action"] == runner.PREFLIGHT_CASE["required_program"],
            "M22 evaluator preflight record drifted")
    if live_files is not None:
        record_path = live_files["preflight/preflight-record.json"]
        require(record_path.is_file() and not record_path.is_symlink() and load(record_path) == preflight,
                "M22 retained evaluator preflight record drifted")
        validate_live_evaluator(preflight, "preflight", live_files, evaluator_schema, identity["checkpoint_id"])
    cases = manifest_value["cases"]
    require(len(report["runs"]) == len(cases) == 42, "M22 final run inventory drifted")
    for ordinal, (run, case) in enumerate(zip(report["runs"], cases, strict=True)):
        validate_run(
            run, case, ordinal, identity, live_files, evaluator_schema,
            root=root, runtime_source=runtime_source, runtime=runtime,
        )
    result = evaluation_common.validate_aggregate_records(
        report, cases, mechanics=runner, suite_label="M22 final",
        live=context.is_live, require=require,
    )
    require(len(cases) == 42 and report["status"] == "FAIL" and result["failures"] == 10,
            "M22 final-v1 frozen result drifted")
    return result


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
    except (M22FinalEvidenceError, runner.M22FinalEvaluationError, runtime_validator.M22RuntimeSourceError,
            ArtifactContextError, SourceContextError, OSError, subprocess.SubprocessError,
            KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_FINAL_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1
    print(f"V2_M22_FINAL_EVIDENCE={result['status']} cases={result['cases']} failures={result['failures']} "
          f"live={str(result['live']).lower()}")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
