#!/usr/bin/env python3
"""Execute the frozen M22 independent follow-up-v2 suite exactly once.

Every fallible source, checkpoint, runtime, CUDA, sandbox, and evaluator check
precedes the single follow-up-v2-manifest read.  The immutable failed final-v1
and follow-up-v1 suites are evidence and seed-exclusion boundaries, never retry
sources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
from collections import Counter
from typing import Any

import build_m22_followup_v2_manifest as manifest_builder
import m22_final_native as native
import run_m22_final_evaluation as foundation
import validate_m22_final_evaluation as final_evidence_validator
import validate_m22_followup_evaluation as followup_v1_evidence_validator
import validate_m22_followup_v2_manifest as manifest_validator
import validate_m22_followup_runtime_source as runtime_validator


CONTRACT = foundation.CONTRACT
QUALIFICATION = foundation.QUALIFICATION
RUNTIME_SOURCE = pathlib.Path("config/v2/m22-followup-runtime-source.json")
IMMUTABLE_FINAL = pathlib.Path("config/v2/m22-final-evaluation-evidence.json")
IMMUTABLE_FOLLOWUP_V1 = pathlib.Path("config/v2/m22-followup-evaluation-evidence.json")
MANIFEST = manifest_builder.MANIFEST
MANIFEST_SCHEMA = manifest_builder.SCHEMA
EVALUATOR_SCHEMA = foundation.EVALUATOR_SCHEMA
EVIDENCE_SCHEMA = pathlib.Path("docs/project/schema/v2-m22-followup-v2-evaluation-evidence.schema.json")
RANDOM_DOMAIN = "openttd-rl-v2-m22-followup-v2-random-legal-v1"
PROGRAMS = foundation.PROGRAMS
PROGRAM_INDEX = foundation.PROGRAM_INDEX
SERVICE_MODES = foundation.SERVICE_MODES
EXPECTED_SIZES = foundation.EXPECTED_SIZES
FAILURES = foundation.FAILURES
SERVICE_PROGRAM_COUNTS = manifest_builder.SERVICE_PROGRAM_COUNTS
SERVICE_PROGRAM_MODES = manifest_builder.SERVICE_PROGRAM_MODES
SOURCE_PATHS = (
    "config/v2/m22-final-evaluation-evidence.json",
    "config/v2/m22-followup-evaluation-evidence.json",
    "docs/project/schema/v2-m22-evaluator-report.schema.json",
    "docs/project/schema/v2-m22-followup-evaluation-evidence.schema.json",
    "docs/project/schema/v2-m22-followup-manifest.schema.json",
    "docs/project/schema/v2-m22-followup-v2-evaluation-evidence.schema.json",
    "docs/project/schema/v2-m22-followup-v2-manifest.schema.json",
    "scripts/v2/build_m22_followup_manifest.py",
    "scripts/v2/build_m22_followup_v2_manifest.py",
    "scripts/v2/m22_final_native.py",
    "scripts/v2/run_m22_final_evaluation.py",
    "scripts/v2/run_m22_followup_evaluation.py",
    "scripts/v2/run_m22_followup_v2_evaluation.py",
    "scripts/v2/validate_m22_final_evaluation.py",
    "scripts/v2/validate_m22_followup_evaluation.py",
    "scripts/v2/validate_m22_followup_manifest.py",
    "scripts/v2/validate_m22_followup_v2_evaluation.py",
    "scripts/v2/validate_m22_followup_v2_manifest.py",
    "scripts/v2/validate_m22_followup_runtime_source.py",
    "tests/project/v2/test_v2_m22_evaluator.py",
    "tests/project/v2/test_v2_m22_followup_evaluation_source.py",
    "tests/project/v2/test_v2_m22_followup_manifest.py",
    "tests/project/v2/test_v2_m22_followup_v2_evaluation_source.py",
    "tests/project/v2/test_v2_m22_followup_v2_manifest.py",
    "training/v2/include/openttd_rl/v2/m22_evaluation.h",
    "training/v2/m22/CMakeLists.txt",
    "training/v2/src/m22_evaluation.cpp",
    "training/v2/src/m22_evaluator_main.cpp",
    "training/v2/tests/m22_evaluation_gate.cpp",
)
PREFLIGHT_CASE = {
    "case_id": "followup-v2-source-preflight-g15-road", "task": "service", "transport_mode": "road",
    "climate": "temperate", "map_width": 64, "map_height": 64, "cargo": "PASS",
    "opponent": "not-applicable", "seed": 225503, "required_program": "road-passenger",
    "native_probe": "passenger-service", "source_gate": "G15",
}


class M22FollowupV2EvaluationError(RuntimeError):
    """The follow-up-v2 runner or one of its frozen boundaries is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22FollowupV2EvaluationError(message)


canonical_bytes = foundation.canonical_bytes
sha256_bytes = foundation.sha256_bytes
sha256 = foundation.sha256
load = foundation.load
write_bytes_new = foundation.write_bytes_new
write_new = foundation.write_new
schema_validate = foundation.schema_validate
git = foundation.git
public_case = foundation.public_case
evaluator_public_case = foundation.evaluator_public_case
public_program = foundation.public_program
evaluator_command = foundation.evaluator_command
rounded = foundation.rounded
summary_stats = foundation.summary_stats
native_reward = foundation.native_reward
run_evaluator = foundation.run_evaluator
run_native = foundation.run_native
checkpoint_preflight = foundation.checkpoint_preflight
runtime_paths = foundation.runtime_paths
aggregate_statistics = foundation.aggregate_statistics
artifact_inventory = foundation.artifact_inventory


def source_identity(root: pathlib.Path) -> dict[str, Any]:
    require(git(root, "status", "--porcelain=v1", "--untracked-files=all") == "",
            "M22 follow-up-v2 execution requires a clean source worktree")
    files = []
    for relative in SOURCE_PATHS:
        path = root / relative
        require(path.is_file() and not path.is_symlink(),
                f"M22 follow-up-v2 source is absent or symlinked: {relative}")
        files.append({"path": relative, "sha256": sha256(path)})
    commit = git(root, "rev-parse", "HEAD")
    require(git(root, "branch", "--show-current") == "main" and
            git(root, "rev-parse", "origin/main") == commit,
            "M22 follow-up-v2 execution requires source-frozen main synchronized with origin/main")
    return {
        "clean": True, "files": files, "main_synchronized": True, "repository_commit": commit,
        "repository_tree": git(root, "rev-parse", "HEAD^{tree}"),
        "tree_sha256": sha256_bytes(canonical_bytes(files)),
    }


def random_legal_seed(case: dict[str, Any]) -> int:
    digest = hashlib.sha256(f"{RANDOM_DOMAIN}:{case['case_id']}".encode("ascii")).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFF_FFFF


def baseline_decisions(case: dict[str, Any]) -> list[dict[str, Any]]:
    active = public_program(case)
    seed = random_legal_seed(case)
    random_action = ("wait", active)[seed % 2]
    return [
        {"action": random_action, "decision_seed": seed, "policy": "seeded-random-legal"},
        {"action": "wait", "decision_seed": None, "policy": "wait-only"},
        {"action": active, "decision_seed": None, "policy": "public-heuristic-v1"},
    ]


def case_scores(case: dict[str, Any], evaluator: dict[str, Any], native_result: dict[str, Any]) -> dict[str, Any]:
    reward = native_reward(native_result)
    learned_action = evaluator["action"] if evaluator["status"] == "PASS" else None
    learned_correct = learned_action == case["required_program"]
    baselines = []
    for decision in baseline_decisions(case):
        correct = decision["action"] == case["required_program"]
        baselines.append({**decision, "correct": correct, "return": reward if correct else 0.0})
    return {
        "baselines": baselines, "learned_correct": learned_correct,
        "learned_return": reward if learned_correct else 0.0, "native_reward": reward,
    }


def failure_categories(
    case: dict[str, Any], evaluator: dict[str, Any], native_result: dict[str, Any], scores: dict[str, Any],
) -> list[str]:
    failures = []
    if evaluator["failure_category"] is not None:
        failures.append(evaluator["failure_category"])
    elif not scores["learned_correct"]:
        failures.append("learned-program-mismatch")
    if native_result["status"] != "PASS":
        failures.append("native-execution")
        if case["source_gate"] == "G21":
            failures.append("broad-retention")
        return failures
    metrics = native_result["record"]["metrics"]
    if case["required_program"] in SERVICE_PROGRAM_COUNTS and not (
        metrics.get("delivered", 0) > 0 and metrics.get("income", 0) > 0
    ):
        failures.append("native-service")
    if case["opponent"] != "not-applicable" and metrics.get("opponent") != case["opponent"]:
        failures.append("opponent-retention")
    return failures


def protocol_record(runs: list[dict[str, Any]], case_ids: list[str]) -> dict[str, Any]:
    return {
        "case_order": case_ids, "cases_attempted": len(runs), "cases_declared": len(case_ids),
        "evaluator_attempts": len(runs),
        "evaluator_processes": sum(run["evaluator"]["process"]["launched"] for run in runs),
        "manifest_reads": 1, "native_dispatches": len(runs),
        "native_processes": sum(run["native"]["status"] == "PASS" and
                                run["native"]["record"]["fresh_processes"] == 1 for run in runs),
        "post_result_selection": False, "prior_nonexecuting_attempts": 0,
        "replacements": 0, "retries": 0, "total_manifest_reads": 1,
    }


def acceptance(runs: list[dict[str, Any]], statistics_value: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    effects = {item["baseline"]: item["statistics"] for item in statistics_value["paired_effects"]}
    all_native = all(run["native"]["status"] == "PASS" for run in runs)
    all_programs = all(run["scores"]["learned_correct"] for run in runs)
    service = [run for run in runs if run["required_program"] in SERVICE_PROGRAM_COUNTS]
    service_modes = {run["public_case"]["transport_mode"] for run in service}
    service_contract = (Counter(run["required_program"] for run in service) ==
                        Counter(SERVICE_PROGRAM_COUNTS) and
                        all(run["public_case"]["transport_mode"] == SERVICE_PROGRAM_MODES[run["required_program"]]
                            for run in service) and
                        all(run["public_case"]["task"] == "routing" for run in service
                            if run["required_program"] == "multimodal-transfer"))
    service_pass = service_contract and service_modes == SERVICE_MODES and all(
        run["native"]["status"] == "PASS" and run["scores"]["learned_correct"] and
        run["native"]["record"]["metrics"].get("delivered", 0) > 0 and
        run["native"]["record"]["metrics"].get("income", 0) > 0 for run in service
    )
    opponents = [run for run in runs if run["public_case"]["opponent"] != "not-applicable"]
    opponent_pass = {run["public_case"]["opponent"] for run in opponents} == foundation.learning.OPPONENTS and all(
        run["native"]["status"] == "PASS" and run["scores"]["learned_correct"] and
        run["native"]["record"]["metrics"].get("opponent") == run["public_case"]["opponent"] for run in opponents
    )
    broad = [run for run in runs if run["public_case"]["source_gate"] == "G21"]
    broad_pass = {public_program(run["public_case"]) for run in broad} == {
        "calendar-inspect", "authority-economy", "event-recovery", "gamescript-response", "content-discovery",
    } and all(run["native"]["status"] == "PASS" and run["scores"]["learned_correct"] for run in broad)
    expected_protocol = {
        "cases_declared": 42, "cases_attempted": 42, "evaluator_attempts": 42,
        "evaluator_processes": 42, "manifest_reads": 1, "native_dispatches": 42,
        "native_processes": 42, "post_result_selection": False, "prior_nonexecuting_attempts": 0,
        "replacements": 0, "retries": 0, "total_manifest_reads": 1,
    }
    execution = len(runs) == 42 and all(protocol[key] == value for key, value in expected_protocol.items())
    result = {
        "all_42_once": execution,
        "all_climates": {run["public_case"]["climate"] for run in runs} == foundation.learning.CLIMATES,
        "all_map_sizes": {(run["public_case"]["map_width"], run["public_case"]["map_height"])
                          for run in runs} == EXPECTED_SIZES,
        "all_programs": all_programs, "broad_retained": broad_pass,
        "learned_lower_ci_above_random": effects["seeded-random-legal"]["ci95_lower"] > 0,
        "learned_lower_ci_above_wait": effects["wait-only"]["ci95_lower"] > 0,
        "native_g15_g21_retained": all_native, "no_failures": all(not run["failures"] for run in runs),
        "opponents_retained": opponent_pass, "service_case_contract_exact": service_contract,
        "service_every_mode": service_pass,
    }
    result["overall"] = all(result.values())
    return result


def immutable_final_record(root: pathlib.Path, value: dict[str, Any]) -> dict[str, Any]:
    result = final_evidence_validator.validate(root)
    require(result == {"cases": 42, "failures": 10, "live": False, "status": "FAIL"},
            "immutable final-v1 evidence no longer validates as the retained failed suite")
    require(value["status"] == "FAIL" and value["protocol"]["cases_attempted"] == 42,
            "immutable final-v1 report boundary drifted")
    return {
        "cases_attempted": 42, "evidence_path": IMMUTABLE_FINAL.as_posix(),
        "evidence_sha256": sha256(root / IMMUTABLE_FINAL), "followup_replaces_final_v1": False,
        "original_cases_reexecuted": 0, "status": "FAIL",
    }


def immutable_followup_v1_record(root: pathlib.Path, value: dict[str, Any]) -> dict[str, Any]:
    result = followup_v1_evidence_validator.validate(root)
    require(result == {"cases": 42, "failures": 0, "live": False, "status": "FAIL"},
            "immutable follow-up-v1 evidence no longer validates as the retained zero-failure aggregate FAIL")
    require(value["status"] == "FAIL" and value["protocol"]["cases_attempted"] == 42 and
            value["acceptance"]["overall"] is False and
            value["acceptance"]["service_every_mode"] is False,
            "immutable follow-up-v1 report boundary drifted")
    return {
        "cases_attempted": 42, "classified_failures": 0,
        "evidence_path": IMMUTABLE_FOLLOWUP_V1.as_posix(),
        "evidence_sha256": sha256(root / IMMUTABLE_FOLLOWUP_V1),
        "followup_v2_replaces_followup_v1": False,
        "original_cases_reexecuted": 0, "status": "FAIL",
    }


def run(
    root: pathlib.Path, manifest_path: pathlib.Path, evaluator_executable: pathlib.Path,
    training_artifact_root: pathlib.Path, runtime_artifact_root: pathlib.Path,
    artifact_root: pathlib.Path, evidence_path: pathlib.Path,
) -> dict[str, Any]:
    root, manifest_path, evaluator_executable = root.resolve(), manifest_path.resolve(), evaluator_executable.resolve()
    training_artifact_root, runtime_artifact_root, artifact_root, evidence_path = (
        training_artifact_root.resolve(), runtime_artifact_root.resolve(), artifact_root.resolve(), evidence_path.resolve(),
    )
    require(not artifact_root.exists() and not artifact_root.is_symlink(),
            "M22 follow-up-v2 artifact root must be new")
    require(not evidence_path.exists() and not evidence_path.is_symlink(),
            "M22 follow-up-v2 evidence path must be new")
    require(evaluator_executable.is_file() and not evaluator_executable.is_symlink() and
            os.access(evaluator_executable, os.X_OK), "M22 evaluator executable is unavailable")
    bwrap_raw = shutil.which("bwrap")
    require(bwrap_raw is not None, "bubblewrap is required for M22 follow-up-v2 evaluation")
    bwrap = pathlib.Path(bwrap_raw).resolve()

    # This complete preflight intentionally does not read the follow-up-v2 manifest.
    contract = load(root / CONTRACT)
    qualification = load(root / QUALIFICATION)
    runtime_source = load(root / RUNTIME_SOURCE)
    immutable_final = load(root / IMMUTABLE_FINAL)
    immutable_followup_v1 = load(root / IMMUTABLE_FOLLOWUP_V1)
    manifest_schema, evaluator_schema = load(root / MANIFEST_SCHEMA), load(root / EVALUATOR_SCHEMA)
    source = source_identity(root)
    expected_manifest = (root / MANIFEST).resolve()
    require(manifest_path == expected_manifest and manifest_path.is_file() and not manifest_path.is_symlink(),
            "M22 follow-up-v2 manifest path is not the frozen protocol path")
    checkpoint, selected = checkpoint_preflight(qualification, training_artifact_root)
    base_source_record = load(root / runtime_validator.preparation.foundation.M21_SOURCE)
    runtime_validator.validate(
        root, artifact_root=runtime_artifact_root, base_source=pathlib.Path(base_source_record["source"]["path"]),
    )
    runtime = runtime_paths(runtime_source)
    evaluator_sha = sha256(evaluator_executable)
    native.validate_runtime(runtime)
    final_boundary = immutable_final_record(root, immutable_final)
    followup_v1_boundary = immutable_followup_v1_record(root, immutable_followup_v1)
    require(contract["device"]["production"] == "cuda:0", "M22 production evaluator device drifted")
    require(runtime_artifact_root == pathlib.Path(runtime_source["retained_artifact"]),
            "M22 corrected runtime artifact root drifted")
    require(manifest_schema["$id"].endswith("v2-m22-followup-v2-manifest.schema.json"),
            "M22 follow-up-v2 manifest schema identity drifted")

    artifact_root.mkdir(parents=True, mode=0o700)
    preflight_root = artifact_root / "preflight" / "evaluator"
    preflight_evaluator = run_evaluator(
        root, bwrap, evaluator_executable, checkpoint, selected["checkpoint_id"], preflight_root,
        PREFLIGHT_CASE, "cuda:0", evaluator_schema,
    )
    require(preflight_evaluator["status"] == "PASS" and
            preflight_evaluator["action"] == PREFLIGHT_CASE["required_program"],
            f"M22 evaluator preflight failed before follow-up-v2 access: "
            f"{preflight_evaluator['failure_detail'] or preflight_evaluator['action']}")
    preflight = {"evaluator": preflight_evaluator, "public_case": public_case(PREFLIGHT_CASE)}
    write_new(artifact_root / "preflight" / "preflight-record.json", preflight)

    # The follow-up-v2 runner owns exactly this one manifest read.
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha = sha256_bytes(manifest_bytes)
    try:
        manifest = json.loads(manifest_bytes, parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"nonfinite JSON constant: {token}")))
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise M22FollowupV2EvaluationError(f"cannot decode M22 follow-up-v2 manifest: {exc}") from exc
    require(isinstance(manifest, dict), "M22 follow-up-v2 manifest root is not an object")
    manifest_validator.validate_value(root, manifest, manifest_bytes)

    cases_root = artifact_root / "cases"
    cases_root.mkdir(mode=0o700)
    runs = []
    for ordinal, case in enumerate(manifest["cases"]):
        case_root = cases_root / f"{ordinal:02d}-{case['case_id']}"
        case_root.mkdir(mode=0o700)
        evaluator_result = run_evaluator(
            root, bwrap, evaluator_executable, checkpoint, selected["checkpoint_id"], case_root / "evaluator",
            case, "cuda:0", evaluator_schema,
        )
        native_result = run_native(root, runtime, case_root / "native", case)
        scores = case_scores(case, evaluator_result, native_result)
        failures = failure_categories(case, evaluator_result, native_result, scores)
        run_record = {
            "artifact_path": case_root.relative_to(artifact_root).as_posix(), "evaluator": evaluator_result,
            "failures": failures, "ordinal": ordinal, "private_seed": case["seed"],
            "public_case": public_case(case), "required_program": case["required_program"],
            "native": native_result, "scores": scores,
        }
        write_new(case_root / "case-record.json", run_record)
        runs.append(run_record)

    protocol = protocol_record(runs, [case["case_id"] for case in manifest["cases"]])
    statistics_value = aggregate_statistics(runs)
    acceptance_value = acceptance(runs, statistics_value, protocol)
    failure_counts = {category: sum(category in run["failures"] for run in runs) for category in FAILURES}
    report: dict[str, Any] = {
        "acceptance": acceptance_value, "artifact_root": str(artifact_root), "failure_counts": failure_counts,
        "identity": {
            "aggregate_schema_sha256": sha256(root / EVIDENCE_SCHEMA),
            "bubblewrap_sha256": sha256(bwrap), "checkpoint_id": selected["checkpoint_id"],
            "evaluation_manifest_schema_sha256": sha256(root / MANIFEST_SCHEMA),
            "evaluator_executable_sha256": evaluator_sha,
            "evaluator_report_schema_sha256": sha256(root / EVALUATOR_SCHEMA),
            "immutable_final_v1_evidence_sha256": sha256(root / IMMUTABLE_FINAL),
            "immutable_followup_v1_evidence_sha256": sha256(root / IMMUTABLE_FOLLOWUP_V1),
            "learning_contract_sha256": sha256(root / CONTRACT),
            "native_executable_sha256": runtime_source["executable"]["sha256"],
            "native_source_tree": runtime_source["source"]["tree"],
            "qualification_evidence_sha256": sha256(root / QUALIFICATION),
            "runtime_source_sha256": sha256(root / RUNTIME_SOURCE),
        },
        "immutable_final_v1": final_boundary, "immutable_followup_v1": followup_v1_boundary,
        "manifest": {
            "case_count": 42, "id": manifest["manifest_id"], "path": MANIFEST.as_posix(), "sha256": manifest_sha,
        },
        "preflight": preflight, "protocol": protocol, "runs": runs,
        "schema_version": "openttd-rl-v2-m22-followup-v2-evaluation-evidence-1",
        "source": source, "statistics": statistics_value,
        "status": "PASS" if acceptance_value["overall"] else "FAIL",
    }
    report["report_sha256"] = sha256_bytes(canonical_bytes(report))
    schema_validate(report, load(root / EVIDENCE_SCHEMA), "M22 follow-up-v2 evaluation evidence")
    import validate_m22_followup_v2_evaluation as validator
    validator.validate_value(report, root, artifact_root=artifact_root, manifest_value=manifest,
                             manifest_bytes=manifest_bytes)
    write_new(evidence_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--evaluator-executable", type=pathlib.Path, required=True)
    parser.add_argument("--training-artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--runtime-artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--evidence", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        report = run(
            args.root, args.manifest, args.evaluator_executable, args.training_artifact_root,
            args.runtime_artifact_root, args.artifact_root, args.evidence,
        )
    except (M22FollowupV2EvaluationError, foundation.M22FinalEvaluationError, native.M22FinalNativeError,
            runtime_validator.M22FollowupRuntimeSourceError, OSError, subprocess.SubprocessError,
            KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_FOLLOWUP_V2_EVALUATION=FAIL {exc}", file=sys.stderr)
        return 1
    print(f"V2_M22_FOLLOWUP_V2_EVALUATION={report['status']} cases={len(report['runs'])} "
          f"failures={sum(report['failure_counts'].values())} checkpoint={report['identity']['checkpoint_id']}")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
