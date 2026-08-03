#!/usr/bin/env python3
"""Execute the preregistered M22 final suite exactly once after source freeze.

All fallible preflight checks happen before the manifest is read.  After that
single read, every declared case receives one fresh optimizer-free evaluator
attempt and one native dispatch attempt.  Case failures are recorded and do not
shorten, retry, replace, or reorder the campaign.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import pathlib
import resource
import shutil
import signal
import statistics
import subprocess
import sys
import time
from typing import Any

import jsonschema

import m22_final_native as native
import run_m22_recovery as recovery
import validate_m22_final_runtime_source as runtime_validator
import validate_m22_learning_contract as learning


CONTRACT = pathlib.Path("config/v2/m22-learning-contract.json")
QUALIFICATION = pathlib.Path("config/v2/m22-qualification-evidence.json")
RUNTIME_SOURCE = pathlib.Path("config/v2/m22-final-runtime-source.json")
PRIOR_ATTEMPT = pathlib.Path("config/v2/m22-final-attempt-a.json")
PRIOR_ATTEMPT_SCHEMA = pathlib.Path("docs/project/schema/v2-m22-final-attempt.schema.json")
MANIFEST_SCHEMA = pathlib.Path("docs/project/schema/v2-m22-evaluation-manifest.schema.json")
EVALUATOR_SCHEMA = pathlib.Path("docs/project/schema/v2-m22-evaluator-report.schema.json")
EVIDENCE_SCHEMA = pathlib.Path("docs/project/schema/v2-m22-final-evaluation-evidence.schema.json")
RANDOM_DOMAIN = "openttd-rl-v2-m22-final-random-legal-v1"
EVALUATOR_TIMEOUT_SECONDS = 300
PROGRAMS = tuple(learning.PROGRAMS)
PROGRAM_INDEX = {name: index for index, name in enumerate(PROGRAMS)}
EVALUATOR_PUBLIC_FIELDS = tuple(field for field in native.PUBLIC_FIELDS if field != "case_id")
SERVICE_MODES = {"road", "rail", "water", "air", "multimodal"}
EXPECTED_SIZES = {(64, 64), (128, 128), (512, 128), (1024, 1024)}
SOURCE_PATHS = (
    "config/v2/m22-final-attempt-a.json",
    "docs/project/schema/v2-m22-evaluator-report.schema.json",
    "docs/project/schema/v2-m22-final-attempt.schema.json",
    "docs/project/schema/v2-m22-final-evaluation-evidence.schema.json",
    "scripts/v2/m22_final_native.py",
    "scripts/v2/run_m22_final_evaluation.py",
    "scripts/v2/validate_m22_final_evaluation.py",
    "tests/project/v2/test_v2_m22_evaluator.py",
    "tests/project/v2/test_v2_m22_final_evaluation_source.py",
    "training/v2/include/openttd_rl/v2/m22_evaluation.h",
    "training/v2/m22/CMakeLists.txt",
    "training/v2/src/m22_evaluation.cpp",
    "training/v2/src/m22_evaluator_main.cpp",
    "training/v2/tests/m22_evaluation_gate.cpp",
)
FAILURES = (
    "evaluator-process", "evaluator-report", "evaluator-identity", "evaluator-public-boundary",
    "learned-program-mismatch", "native-execution", "native-service", "opponent-retention", "broad-retention",
)
PREFLIGHT_CASE = {
    "case_id": "source-preflight-g15-road", "task": "service", "transport_mode": "road",
    "climate": "temperate", "map_width": 64, "map_height": 64, "cargo": "PASS",
    "opponent": "not-applicable", "seed": 220001, "required_program": "road-passenger",
    "native_probe": "passenger-service", "source_gate": "G15",
}

# Two-sided 95% Student-t critical values for df=1..41.  The final campaign
# always has n=42; retaining the complete table also makes subset diagnostics
# exact and removes a SciPy/runtime-network dependency.
T95 = (
    0.0, 12.706204736, 4.302652730, 3.182446305, 2.776445105, 2.570581836,
    2.446911851, 2.364624252, 2.306004135, 2.262157163, 2.228138852,
    2.200985160, 2.178812830, 2.160368656, 2.144786688, 2.131449546,
    2.119905299, 2.109815578, 2.100922040, 2.093024054, 2.085963447,
    2.079613845, 2.073873068, 2.068657610, 2.063898562, 2.059538553,
    2.055529439, 2.051830516, 2.048407142, 2.045229642, 2.042272456,
    2.039513446, 2.036933343, 2.034515297, 2.032244509, 2.030107928,
    2.028094001, 2.026192463, 2.024394164, 2.022690920, 2.021075390,
    2.019540970,
)


class M22FinalEvaluationError(RuntimeError):
    """The final runner or one of its frozen boundaries is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22FinalEvaluationError(message)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"nonfinite JSON constant: {token}")))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise M22FinalEvaluationError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def write_bytes_new(path: pathlib.Path, value: bytes) -> None:
    require(not path.exists() and not path.is_symlink(), f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(value)
        output.flush()
        os.fsync(output.fileno())


def write_new(path: pathlib.Path, value: Any) -> None:
    write_bytes_new(path, canonical_bytes(value))


def schema_validate(value: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M22FinalEvaluationError(f"{label} schema failed at {where}: {exc.message}") from exc


def git(root: pathlib.Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    require(result.returncode == 0, f"git {' '.join(arguments)} failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def source_identity(root: pathlib.Path) -> dict[str, Any]:
    require(git(root, "status", "--porcelain=v1", "--untracked-files=all") == "",
            "M22 final execution requires a clean source worktree")
    files = []
    for relative in SOURCE_PATHS:
        path = root / relative
        require(path.is_file() and not path.is_symlink(), f"M22 final source is absent or symlinked: {relative}")
        files.append({"path": relative, "sha256": sha256(path)})
    commit = git(root, "rev-parse", "HEAD")
    return {
        "clean": True, "files": files, "repository_commit": commit,
        "repository_tree": git(root, "rev-parse", "HEAD^{tree}"),
        "tree_sha256": sha256_bytes(canonical_bytes(files)),
    }


def public_case(case: dict[str, Any]) -> dict[str, Any]:
    return {field: case[field] for field in native.PUBLIC_FIELDS}


def evaluator_public_case(case: dict[str, Any]) -> dict[str, Any]:
    return {field: case[field] for field in EVALUATOR_PUBLIC_FIELDS}


def public_program(case: dict[str, Any]) -> str:
    """Derive the one active program strictly from evaluator-visible fields."""
    probe = native.canonical_probe(case)
    mapping = {
        ("G15", "passenger-service"): "road-passenger",
        ("G16", "single-leg"): "road-cargo",
        ("G17", "passenger"): "rail-passenger", ("G17", "freight"): "rail-freight",
        ("G18", "natural"): "ship-natural", ("G18", "constructed"): "ship-constructed",
        ("G19", "service"): "air-service", ("G19", "helicopter"): "air-helicopter",
        ("G19", "multimodal"): "multimodal-transfer", ("G19", "router"): "mode-router",
        ("G20", "head_to_head"): "competition-head-to-head",
        ("G21", "calendar"): "calendar-inspect", ("G21", "authority_economy"): "authority-economy",
        ("G21", "events"): "event-recovery", ("G21", "gamescript"): "gamescript-response",
        ("G21", "content"): "content-discovery",
    }
    key = (case["source_gate"], probe)
    require(key in mapping, f"public capability has no program mapping: {key}")
    return mapping[key]


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


def rounded(value: float) -> float:
    require(math.isfinite(value), "nonfinite statistic")
    return float(f"{value:.12g}")


def summary_stats(values: list[float]) -> dict[str, Any]:
    require(2 <= len(values) <= 42, "Student-t summary requires 2..42 complete paired values")
    require(all(math.isfinite(value) for value in values), "statistics contain a nonfinite value")
    count = len(values)
    mean = statistics.fmean(values)
    deviation = statistics.stdev(values)
    error = deviation / math.sqrt(count)
    critical = T95[count - 1]
    return {
        "ci95_lower": rounded(mean - critical * error), "ci95_upper": rounded(mean + critical * error),
        "maximum": rounded(max(values)), "mean": rounded(mean), "median": rounded(statistics.median(values)),
        "minimum": rounded(min(values)), "n": count, "sample_sd": rounded(deviation),
        "standard_error": rounded(error), "t_critical_95": rounded(critical),
    }


def native_reward(native_result: dict[str, Any]) -> float:
    if native_result["status"] != "PASS":
        return 0.0
    metrics = native_result["record"]["metrics"]
    delivered = max(0.0, float(metrics.get("delivered", 0)))
    economic = float(metrics.get("company_value", metrics.get("income", 0)))
    reward = 1.0 + min(math.log1p(delivered) / 10.0, 1.0) + min(math.log1p(max(0.0, economic)) / 20.0, 1.0)
    return rounded(reward)


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


def apply_evaluator_limits() -> None:
    recovery.apply_limits()
    resource.setrlimit(resource.RLIMIT_CPU, (EVALUATOR_TIMEOUT_SECONDS, EVALUATOR_TIMEOUT_SECONDS))


def evaluator_command(
    bwrap: pathlib.Path, root: pathlib.Path, evaluator: pathlib.Path, checkpoint: pathlib.Path,
    case_root: pathlib.Path, case: dict[str, Any], device: str,
) -> list[str]:
    report = case_root / "evaluator-report.json"
    public = evaluator_public_case(case)
    return [
        str(bwrap), "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-ipc",
        "--unshare-uts", "--unshare-net", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
        "--proc", "/proc", "--tmpfs", "/tmp", "--bind", str(case_root), str(case_root),
        "--chdir", str(root), "--clearenv", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp",
        "--setenv", "TMPDIR", "/tmp", "--setenv", "LANG", "C.UTF-8", "--setenv", "TZ", "UTC",
        "--setenv", "CUDA_VISIBLE_DEVICES", "0", "--setenv", "CUDA_CACHE_DISABLE", "1",
        "--setenv", "CUBLAS_WORKSPACE_CONFIG", ":4096:8", "--setenv", "OMP_NUM_THREADS", "1", "--",
        str(evaluator), "--checkpoint", str(checkpoint), "--report", str(report), "--device", device,
        "--task", public["task"], "--transport-mode", public["transport_mode"], "--climate", public["climate"],
        "--map-width", str(public["map_width"]), "--map-height", str(public["map_height"]),
        "--cargo", public["cargo"], "--opponent", public["opponent"], "--native-probe", public["native_probe"],
        "--source-gate", public["source_gate"], "--policy-split", "final",
    ]


def process_record(
    *, exit_code: int | None, launched: bool, stderr_path: pathlib.Path, stdout_path: pathlib.Path,
    case_root: pathlib.Path, timed_out: bool, wall_seconds: float,
) -> dict[str, Any]:
    return {
        "attempt": 1, "exit_code": exit_code, "fresh_process": True, "launched": launched,
        "network_unshared": True, "stderr_path": stderr_path.relative_to(case_root).as_posix(),
        "stderr_sha256": sha256(stderr_path), "stdout_path": stdout_path.relative_to(case_root).as_posix(),
        "stdout_sha256": sha256(stdout_path), "timed_out": timed_out, "wall_seconds": rounded(wall_seconds),
    }


def evaluator_failure(category: str, detail: str, process: dict[str, Any]) -> dict[str, Any]:
    require(category in FAILURES[:4], "unknown evaluator failure category")
    return {
        "action": None, "action_index": None, "failure_category": category, "failure_detail": detail[:2000],
        "legal_active_program": None, "process": process, "report_path": None, "report_sha256": None, "status": "FAIL",
    }


def run_evaluator(
    root: pathlib.Path, bwrap: pathlib.Path, evaluator: pathlib.Path, checkpoint: pathlib.Path,
    checkpoint_id: str, case_root: pathlib.Path, case: dict[str, Any], device: str,
    evaluator_schema: dict[str, Any],
) -> dict[str, Any]:
    case_root.mkdir(parents=True, mode=0o700)
    stdout_path, stderr_path = case_root / "evaluator.stdout", case_root / "evaluator.stderr"
    started = time.monotonic()
    launched, timed_out, exit_code = False, False, None
    stdout = stderr = b""
    try:
        process = subprocess.Popen(
            evaluator_command(bwrap, root, evaluator, checkpoint, case_root, case, device),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, preexec_fn=apply_evaluator_limits,
        )
        launched = True
        try:
            stdout, stderr = process.communicate(timeout=EVALUATOR_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        exit_code = process.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        stderr = str(exc).encode("utf-8", errors="replace")
    wall = time.monotonic() - started
    write_bytes_new(stdout_path, stdout)
    write_bytes_new(stderr_path, stderr)
    process_info = process_record(
        exit_code=exit_code, launched=launched, stderr_path=stderr_path, stdout_path=stdout_path,
        case_root=case_root, timed_out=timed_out, wall_seconds=wall,
    )
    if not launched or timed_out or exit_code != 0:
        return evaluator_failure("evaluator-process", stderr.decode("utf-8", errors="replace")[-2000:], process_info)
    report_path = case_root / "evaluator-report.json"
    if not report_path.is_file() or report_path.is_symlink():
        return evaluator_failure("evaluator-report", "evaluator report is absent or symlinked", process_info)
    try:
        report = load(report_path)
        schema_validate(report, evaluator_schema, "M22 evaluator report")
    except M22FinalEvaluationError as exc:
        return evaluator_failure("evaluator-report", str(exc), process_info)
    if report["checkpoint"]["id"] != checkpoint_id or report["execution"]["device"] != device or not all(
        report["execution"][field] is False
        for field in ("optimizer_constructed", "optimizer_deserialized", "optimizer_path_opened")
    ):
        return evaluator_failure("evaluator-identity", "checkpoint, device, or optimizer boundary drifted", process_info)
    active = public_program(case)
    mask = report["tensor_input"]["program_mask"]
    expected_mask = [index in (0, PROGRAM_INDEX[active]) for index in range(len(PROGRAMS))]
    if report["public_state"] != evaluator_public_case(case) or report["policy"]["legal_active_program"] != active or \
            report["policy"]["legal_active_index"] != PROGRAM_INDEX[active] or mask != expected_mask:
        return evaluator_failure("evaluator-public-boundary", "public projection or legal mask drifted", process_info)
    return {
        "action": report["policy"]["action"], "action_index": report["policy"]["action_index"],
        "failure_category": None, "failure_detail": None, "legal_active_program": active,
        "process": process_info, "report_path": report_path.relative_to(case_root).as_posix(),
        "report_sha256": sha256(report_path), "status": "PASS",
    }


def artifact_inventory(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    result = []
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise M22FinalEvaluationError(f"final artifact contains a symlink: {item}")
        if item.is_file():
            result.append({"bytes": item.stat().st_size, "path": item.relative_to(path).as_posix(), "sha256": sha256(item)})
    return result


def run_native(
    root: pathlib.Path, runtime: native.RuntimePaths, case_root: pathlib.Path, case: dict[str, Any],
) -> dict[str, Any]:
    try:
        record = native.run_native_case(root, runtime, case_root, case)
        return {
            "artifact_inventory": artifact_inventory(case_root), "attempt": 1, "failure_category": None,
            "failure_detail": None, "record": record, "status": "PASS",
        }
    except (native.M22FinalNativeError, OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError) as exc:
        return {
            "artifact_inventory": artifact_inventory(case_root), "attempt": 1, "failure_category": "native-execution",
            "failure_detail": str(exc)[:2000], "record": None, "status": "FAIL",
        }


def failure_categories(case: dict[str, Any], evaluator: dict[str, Any], native_result: dict[str, Any],
                       scores: dict[str, Any]) -> list[str]:
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
    if case["task"] == "service" and case["transport_mode"] in SERVICE_MODES and not (
        metrics.get("delivered", 0) > 0 and metrics.get("income", 0) > 0
    ):
        failures.append("native-service")
    if case["opponent"] != "not-applicable" and metrics.get("opponent") != case["opponent"]:
        failures.append("opponent-retention")
    return failures


def validate_manifest_value(
    root: pathlib.Path, manifest: dict[str, Any], manifest_sha: str, contract: dict[str, Any],
    manifest_schema: dict[str, Any],
) -> None:
    schema_validate(manifest, manifest_schema, "M22 final manifest")
    require(manifest["schema_sha256"] == sha256(root / MANIFEST_SCHEMA), "final manifest schema identity drifted")
    expected = contract["independent_evaluation"]
    require(manifest_sha == expected["manifest_sha256"] == contract["identities"]["final_evaluation_manifest_sha256"],
            "final manifest identity drifted")
    cases = manifest["cases"]
    require(len(cases) == expected["case_count"] == 42 and len({case["case_id"] for case in cases}) == 42,
            "final case count or identity closure drifted")
    seeds = [learning.derived_seed(manifest["seed_derivation"]["domain"],
                                   manifest["seed_derivation"]["ordinal_start"] + index) for index in range(42)]
    require([case["seed"] for case in cases] == seeds and len(set(seeds)) == 42, "final seed derivation drifted")
    require({case["transport_mode"] for case in cases} == learning.MODES and
            {case["climate"] for case in cases} == learning.CLIMATES and
            {(case["map_width"], case["map_height"]) for case in cases} == EXPECTED_SIZES,
            "final mode, climate, or size coverage drifted")
    require({case["opponent"] for case in cases if case["opponent"] != "not-applicable"} == learning.OPPONENTS,
            "final opponent coverage drifted")
    program_gate = {item["id"]: item["source_gate"] for item in contract["policy_interface"]["programs"]}
    for case in cases:
        require(case["required_program"] in PROGRAM_INDEX and program_gate[case["required_program"]] == case["source_gate"],
                f"final required program/gate drifted: {case['case_id']}")
        require(public_program(case) == case["required_program"],
                f"final public capability/required program drifted: {case['case_id']}")


def checkpoint_preflight(qualification: dict[str, Any], training_root: pathlib.Path) -> tuple[pathlib.Path, dict[str, Any]]:
    selected, expected = qualification["finalized_selection"], qualification["identity"]["checkpoint"]
    require(selected["finalized"] and not selected["final_manifest_accessed"] and
            selected["checkpoint_id"] == expected["id"] and selected["checkpoint_path"] == expected["path"],
            "M22 selected checkpoint boundary drifted")
    checkpoint = (training_root / selected["checkpoint_path"]).resolve()
    require(checkpoint.is_relative_to(training_root) and checkpoint.is_dir() and not checkpoint.is_symlink(),
            "M22 selected checkpoint is unavailable")
    names = [item["name"] for item in expected["files"]]
    require(names == list(recovery.INVENTORY), "M22 selected checkpoint inventory drifted")
    for record in expected["files"]:
        path = checkpoint / record["name"]
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == record["bytes"] and
                sha256(path) == record["sha256"], f"M22 selected checkpoint file drifted: {record['name']}")
    return checkpoint, selected


def validate_prior_attempt(root: pathlib.Path, contract: dict[str, Any]) -> dict[str, Any]:
    record = load(root / PRIOR_ATTEMPT)
    schema_validate(record, load(root / PRIOR_ATTEMPT_SCHEMA), "M22 rejected final attempt")
    require(record["schema_sha256"] == sha256(root / PRIOR_ATTEMPT_SCHEMA),
            "M22 rejected-attempt schema identity drifted")
    require(record["manifest"]["sha256"] == contract["independent_evaluation"]["manifest_sha256"] and
            record["manifest"]["cases_observed"] == contract["independent_evaluation"]["case_count"],
            "M22 rejected-attempt manifest binding drifted")
    require(record["identity"]["qualification_evidence_sha256"] == sha256(root / QUALIFICATION) and
            record["identity"]["runtime_source_sha256"] == sha256(root / RUNTIME_SOURCE),
            "M22 rejected-attempt prerequisite identity drifted")
    commit = record["source"]["repository_commit"]
    require(git(root, "cat-file", "-t", commit) == "commit" and
            git(root, "show", "-s", "--format=%T", commit) == record["source"]["repository_tree"],
            "M22 rejected-attempt repository identity drifted")
    prior_source = subprocess.run(
        ["git", "show", f"{commit}:scripts/v2/run_m22_final_evaluation.py"], cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    require(prior_source.returncode == 0 and sha256_bytes(prior_source.stdout) == record["source"]["runner_sha256"],
            "M22 rejected-attempt runner identity drifted")
    artifact_root = pathlib.Path(record["artifacts"]["root"])
    require(artifact_root.is_absolute() and artifact_root.is_dir() and not artifact_root.is_symlink(),
            "M22 rejected-attempt artifact root is unavailable")
    for name in ("evaluator_report", "preflight_record", "stderr", "stdout"):
        item = record["artifacts"][name]
        path = artifact_root / item["path"]
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == item["bytes"] and
                sha256(path) == item["sha256"], f"M22 rejected-attempt artifact identity drifted: {name}")
    preflight = load(artifact_root / record["artifacts"]["preflight_record"]["path"])
    require(preflight["public_case"] == public_case(PREFLIGHT_CASE) and
            preflight["evaluator"]["status"] == "PASS" and
            preflight["evaluator"]["action"] == PREFLIGHT_CASE["required_program"],
            "M22 rejected-attempt preflight semantic drifted")
    return record


def runtime_paths(source: dict[str, Any]) -> native.RuntimePaths:
    return native.RuntimePaths(
        executable=pathlib.Path(source["executable"]["path"]),
        opengfx=pathlib.Path(source["runtime"]["open_gfx"]["path"]),
        base_config=pathlib.Path(source["runtime"]["configs"]["base"]["path"]),
        content_config=pathlib.Path(source["runtime"]["configs"]["content"]["path"]),
        gamescript_config=pathlib.Path(source["runtime"]["configs"]["gamescript"]["path"]),
        source_tree=source["source"]["tree"],
    )


def aggregate_statistics(runs: list[dict[str, Any]]) -> dict[str, Any]:
    policy_order = ("learned", "seeded-random-legal", "wait-only", "public-heuristic-v1")
    returns: dict[str, list[float]] = {policy: [] for policy in policy_order}
    for run in runs:
        returns["learned"].append(run["scores"]["learned_return"])
        for baseline in run["scores"]["baselines"]:
            returns[baseline["policy"]].append(baseline["return"])
    policies = [{"policy": policy, "statistics": summary_stats(returns[policy])} for policy in policy_order]
    effects = []
    for baseline in policy_order[1:]:
        differences = [learned - other for learned, other in zip(returns["learned"], returns[baseline], strict=True)]
        effects.append({"baseline": baseline, "learned": "learned", "statistics": summary_stats(differences)})
    return {"paired_effects": effects, "policies": policies}


def acceptance(runs: list[dict[str, Any]], statistics_value: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    effects = {item["baseline"]: item["statistics"] for item in statistics_value["paired_effects"]}
    all_native = all(run["native"]["status"] == "PASS" for run in runs)
    all_programs = all(run["scores"]["learned_correct"] for run in runs)
    service = [run for run in runs if run["public_case"]["task"] == "service" and
               run["public_case"]["transport_mode"] in SERVICE_MODES]
    service_modes = {run["public_case"]["transport_mode"] for run in service}
    service_pass = service_modes == SERVICE_MODES and all(
        run["native"]["status"] == "PASS" and run["scores"]["learned_correct"] and
        run["native"]["record"]["metrics"].get("delivered", 0) > 0 and
        run["native"]["record"]["metrics"].get("income", 0) > 0 for run in service
    )
    opponents = [run for run in runs if run["public_case"]["opponent"] != "not-applicable"]
    opponent_pass = {run["public_case"]["opponent"] for run in opponents} == learning.OPPONENTS and all(
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
        "native_processes": 42, "post_result_selection": False, "prior_nonexecuting_attempts": 1,
        "replacements": 0, "retries": 0, "total_manifest_reads": 2,
    }
    execution = len(runs) == 42 and all(protocol[key] == value for key, value in expected_protocol.items())
    result = {
        "all_42_once": execution, "all_climates": {run["public_case"]["climate"] for run in runs} == learning.CLIMATES,
        "all_map_sizes": {(run["public_case"]["map_width"], run["public_case"]["map_height"]) for run in runs} == EXPECTED_SIZES,
        "all_programs": all_programs, "broad_retained": broad_pass,
        "learned_lower_ci_above_random": effects["seeded-random-legal"]["ci95_lower"] > 0,
        "learned_lower_ci_above_wait": effects["wait-only"]["ci95_lower"] > 0,
        "native_g15_g21_retained": all_native, "no_failures": all(not run["failures"] for run in runs),
        "opponents_retained": opponent_pass, "service_every_mode": service_pass,
    }
    result["overall"] = all(result.values())
    return result


def protocol_record(runs: list[dict[str, Any]], case_ids: list[str]) -> dict[str, Any]:
    return {
        "case_order": case_ids, "cases_attempted": len(runs), "cases_declared": len(case_ids),
        "evaluator_attempts": len(runs),
        "evaluator_processes": sum(run["evaluator"]["process"]["launched"] for run in runs),
        "manifest_reads": 1, "native_dispatches": len(runs),
        "native_processes": sum(run["native"]["status"] == "PASS" and
                                run["native"]["record"]["fresh_processes"] == 1 for run in runs),
        "post_result_selection": False, "prior_nonexecuting_attempts": 1,
        "replacements": 0, "retries": 0, "total_manifest_reads": 2,
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
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "M22 final artifact root must be new")
    require(not evidence_path.exists() and not evidence_path.is_symlink(), "M22 final evidence path must be new")
    require(evaluator_executable.is_file() and not evaluator_executable.is_symlink() and
            os.access(evaluator_executable, os.X_OK), "M22 evaluator executable is unavailable")
    bwrap_raw = shutil.which("bwrap")
    require(bwrap_raw is not None, "bubblewrap is required for M22 final evaluation")
    bwrap = pathlib.Path(bwrap_raw).resolve()

    # Complete every check that can be completed without final-manifest access.
    contract = load(root / CONTRACT)
    qualification = load(root / QUALIFICATION)
    runtime_source = load(root / RUNTIME_SOURCE)
    prior_attempt = validate_prior_attempt(root, contract)
    manifest_schema, evaluator_schema = load(root / MANIFEST_SCHEMA), load(root / EVALUATOR_SCHEMA)
    source = source_identity(root)
    expected_manifest = (root / contract["independent_evaluation"]["manifest"]).resolve()
    require(manifest_path == expected_manifest and manifest_path.is_file() and not manifest_path.is_symlink(),
            "M22 final manifest path is not the frozen contract path")
    checkpoint, selected = checkpoint_preflight(qualification, training_artifact_root)
    runtime_validator.validate(root, artifact_root=runtime_artifact_root)
    runtime = runtime_paths(runtime_source)
    evaluator_sha = sha256(evaluator_executable)
    native.validate_runtime(runtime)
    require(contract["device"]["production"] == "cuda:0", "M22 production evaluator device drifted")
    require(runtime_artifact_root == pathlib.Path(runtime_source["retained_artifact"]),
            "M22 runtime artifact root drifted")

    # Exercise the exact binary/checkpoint/CUDA/sandbox path on a fixed public
    # source case before consuming final access.  A failed preflight remains as
    # a create-only diagnostic and cannot consume or partially execute the suite.
    artifact_root.mkdir(parents=True, mode=0o700)
    preflight_root = artifact_root / "preflight" / "evaluator"
    preflight_evaluator = run_evaluator(
        root, bwrap, evaluator_executable, checkpoint, selected["checkpoint_id"], preflight_root,
        PREFLIGHT_CASE, "cuda:0", evaluator_schema,
    )
    require(preflight_evaluator["status"] == "PASS" and
            preflight_evaluator["action"] == PREFLIGHT_CASE["required_program"],
            f"M22 evaluator preflight failed before final access: {preflight_evaluator['failure_detail'] or preflight_evaluator['action']}")
    preflight = {"evaluator": preflight_evaluator, "public_case": public_case(PREFLIGHT_CASE)}
    write_new(artifact_root / "preflight" / "preflight-record.json", preflight)

    # This is the single manifest read owned by the final runner.
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha = sha256_bytes(manifest_bytes)
    try:
        manifest = json.loads(manifest_bytes, parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"nonfinite JSON constant: {token}")))
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise M22FinalEvaluationError(f"cannot decode M22 final manifest: {exc}") from exc
    require(isinstance(manifest, dict), "M22 final manifest root is not an object")
    validate_manifest_value(root, manifest, manifest_sha, contract, manifest_schema)

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
            "learning_contract_sha256": sha256(root / CONTRACT),
            "native_executable_sha256": runtime_source["executable"]["sha256"],
            "native_source_tree": runtime_source["source"]["tree"],
            "prior_attempt_sha256": sha256(root / PRIOR_ATTEMPT),
            "qualification_evidence_sha256": sha256(root / QUALIFICATION),
            "runtime_source_sha256": sha256(root / RUNTIME_SOURCE),
        },
        "manifest": {
            "case_count": 42, "id": manifest["manifest_id"], "path": manifest_path.relative_to(root).as_posix(),
            "sha256": manifest_sha,
        },
        "history": {
            "cases_attempted": prior_attempt["execution"]["cases_attempted"],
            "failure_category": prior_attempt["failure"]["category"],
            "manifest_reads": prior_attempt["manifest"]["reads"],
            "prior_attempt": PRIOR_ATTEMPT.as_posix(), "status": prior_attempt["status"],
        },
        "preflight": preflight, "protocol": protocol, "runs": runs,
        "schema_version": "openttd-rl-v2-m22-final-evaluation-evidence-1",
        "source": source, "statistics": statistics_value,
        "status": "PASS" if acceptance_value["overall"] else "FAIL",
    }
    report["report_sha256"] = sha256_bytes(canonical_bytes(report))
    schema_validate(report, load(root / EVIDENCE_SCHEMA), "M22 final evaluation evidence")
    import validate_m22_final_evaluation as validator
    validator.validate_value(report, root, artifact_root=artifact_root, manifest_value=manifest)
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
    except (M22FinalEvaluationError, native.M22FinalNativeError, runtime_validator.M22RuntimeSourceError,
            OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_FINAL_EVALUATION=FAIL {exc}", file=sys.stderr)
        return 1
    print(f"V2_M22_FINAL_EVALUATION={report['status']} cases={len(report['runs'])} "
          f"failures={sum(report['failure_counts'].values())} checkpoint={report['identity']['checkpoint_id']}")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
