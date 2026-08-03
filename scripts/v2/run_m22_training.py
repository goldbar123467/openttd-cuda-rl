#!/usr/bin/env python3
"""Run all six frozen M22 learned campaigns and matched non-neural baselines."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
from typing import Any

import encode_m22_native_corpus as encoder
import run_m22_recovery as recovery


CONTRACT = pathlib.Path("config/v2/m22-learning-contract.json")
CORPUS = pathlib.Path("config/v2/m22-native-corpus.json")
RECOVERY = pathlib.Path("config/v2/m22-recovery-evidence-v2.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m22-training-evidence.schema.json")
SEEDS = (1910917137, 1360150311, 1636894266)
ARCHITECTURES = recovery.ARCHITECTURES
CANDIDATE_UPDATES = (8, 16, 24, 32, 40, 48)
BASELINES = ("public-heuristic-v1", "seeded-random-legal-v1", "wait-only-v1")
RANDOM_DOMAIN = "openttd-rl-v2-m22-random-legal-v1"
SOURCE_PATHS = tuple(sorted(set(recovery.SOURCE_PATHS + (
    "config/v2/m22-recovery-evidence-v2.json",
    "scripts/v2/run_m22_training.py",
    "scripts/v2/validate_m22_training_evidence.py",
    "training/v2/tests/m22_campaign_gate.cpp",
))))


class M22TrainingError(RuntimeError):
    """The complete matched M22 training campaign did not satisfy its frozen contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22TrainingError(message)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def random_correct(seed: int, program: int, occurrence: int) -> bool:
    payload = f"{RANDOM_DOMAIN}\0{seed}\0{program}\0{occurrence}".encode("ascii")
    return hashlib.sha256(payload).digest()[0] < 128


def source_identity(root: pathlib.Path) -> dict[str, Any]:
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=root,
        check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    require(status == "", "accepted M22 training requires a clean source worktree")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "M22 training source commit is malformed")
    files = []
    for relative in SOURCE_PATHS:
        path = root / relative
        require(path.is_file() and not path.is_symlink(), f"M22 training source is absent or symlinked: {relative}")
        files.append({"path": relative, "sha256": sha256(path)})
    return {"clean": True, "files": files, "repository_commit": commit,
            "tree_sha256": recovery.sha256_bytes(recovery.canonical_bytes(files))}


def device_identity() -> dict[str, Any]:
    query = "index,name,uuid,compute_cap,driver_version,memory.total"
    completed = subprocess.run(
        ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
        check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    rows = [item.strip() for item in completed.stdout.splitlines() if item.strip()]
    require(len(rows) == 1, "M22 production training requires exactly one visible GPU")
    fields = [item.strip() for item in rows[0].split(",")]
    require(len(fields) == 6 and fields[0] == "0" and fields[3] == "12.0", "M22 production GPU identity drifted")
    executable = pathlib.Path(shutil.which("nvidia-smi") or "").resolve()
    return {
        "compute_capability": fields[3], "driver_version": fields[4], "index": 0,
        "memory_mib": int(fields[5]), "name": fields[1], "nvidia_smi_sha256": sha256(executable), "uuid": fields[2],
    }


def corpus_maps(root: pathlib.Path, decoded: encoder.DecodedCorpus) -> tuple[dict[int, float], dict[int, float], dict[int, int]]:
    correct_training = {item.program: item.rewards[item.program] for item in decoded.entries if item.split == "training"}
    correct_development = {item.program: item.rewards[item.program] for item in decoded.entries if item.split == "development"}
    corpus = recovery.load(root / CORPUS)
    company_values: dict[int, int] = {}
    for item in corpus["entries"]:
        if item["split"] == "development":
            company_values[encoder.PROGRAM_INDEX[item["program"]]] = int(item["native"]["income_or_company_value"])
    require(set(correct_training) == set(range(1, 17)) and set(correct_development) == set(range(1, 17)) and
            set(company_values) == set(range(1, 17)), "M22 corpus baseline projection is incomplete")
    return correct_training, correct_development, company_values


def matched_baselines(seed: int, counts: list[int], rewards: dict[int, float]) -> list[dict[str, Any]]:
    require(len(counts) == 17 and counts[0] == 0 and sum(counts) == 6144, "M22 matched baseline case budget drifted")
    result = []
    for baseline in BASELINES:
        correct = 0
        total_return = 0.0
        for program in range(1, 17):
            if baseline == "public-heuristic-v1":
                successes = counts[program]
            elif baseline == "wait-only-v1":
                successes = 0
            else:
                successes = sum(random_correct(seed, program, occurrence) for occurrence in range(counts[program]))
            correct += successes
            total_return += successes * rewards[program]
        result.append({
            "baseline": baseline,
            "correct_program_fraction": correct / 6144,
            "matched_transitions": 6144,
            "mean_return": total_return / 6144,
            "total_return": total_return,
        })
    return result


def development_baselines(seed: int, introduced: int, rewards: dict[int, float]) -> list[dict[str, Any]]:
    trials = 384
    result = []
    for baseline in BASELINES:
        correct = 0
        total_return = 0.0
        for program in range(1, introduced + 1):
            if baseline == "public-heuristic-v1":
                successes = trials
            elif baseline == "wait-only-v1":
                successes = 0
            else:
                successes = sum(random_correct(seed, program, occurrence) for occurrence in range(trials))
            correct += successes
            total_return += successes * rewards[program]
        decisions = introduced * trials
        result.append({"baseline": baseline, "decisions": decisions,
                       "mean_return": total_return / decisions, "success_fraction": correct / decisions})
    return result


def baseline(records: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [item for item in records if item["baseline"] == name]
    require(len(matches) == 1, f"M22 baseline record is absent or duplicated: {name}")
    return matches[0]


def checkpoint(process: dict[str, Any], update: int) -> dict[str, Any]:
    return recovery.checkpoint(process, update)


def checkpoint_selection(artifact_root: pathlib.Path, record: dict[str, Any]) -> dict[str, Any]:
    path = artifact_root / record["path"] / "selection.json"
    value = recovery.load(path)
    require(value["update"] == record["update"], "M22 checkpoint selection/update projection drifted")
    return value


def candidates(
    process: dict[str, Any], seed: int, development_rewards: dict[int, float],
    company_values: dict[int, int], artifact_root: pathlib.Path,
) -> list[dict[str, Any]]:
    updates = {item["update"]: item for item in process["updates"]}
    result = []
    for update in CANDIDATE_UPDATES:
        metric = updates[update]
        require(metric["retention_ran"], "M22 candidate update lacks a retention evaluation")
        retention = metric["retention"]
        checkpoint_record = checkpoint(process, update)
        selection = checkpoint_selection(artifact_root, checkpoint_record)
        require(selection == {
            "accuracy": retention["accuracy"], "eligible": retention["selection_eligible"],
            "mean_reward": retention["mean_reward"], "passed_programs": retention["passed_programs"],
            "stage": retention["stage"], "update": retention["update"],
        }, "M22 checkpoint development selection is not source-derived")
        introduced = retention["introduced_programs"]
        development = development_baselines(seed, introduced, development_rewards)
        mean_company_value = sum(
            company_values[program] if retention["pass_mask"] & (1 << program) else 0
            for program in range(1, introduced + 1)
        ) / introduced
        random_record = baseline(development, "seeded-random-legal-v1")
        wait_record = baseline(development, "wait-only-v1")
        eligibility = {
            "all_introduced_stages_pass": retention["passed_programs"] == introduced,
            "beats_seeded_random": retention["mean_reward"] > random_record["mean_return"],
            "beats_wait_only": retention["mean_reward"] > wait_record["mean_return"],
            "checkpoint_allowed": retention["checkpoint_allowed"],
            "final_access": False,
            "finite_metrics": all(math.isfinite(value) for value in (
                retention["accuracy"], retention["mean_reward"], mean_company_value,
            )),
            "native_failures": 0,
        }
        eligible = all(value is True for key, value in eligibility.items() if key not in {"final_access", "native_failures"}) and \
            eligibility["final_access"] is False and eligibility["native_failures"] == 0
        require(eligible == selection["eligible"], "M22 derived candidate eligibility disagrees with checkpoint selection")
        result.append({
            "checkpoint_id": checkpoint_record["id"], "checkpoint_path": checkpoint_record["path"],
            "development_baselines": development, "eligibility": eligibility, "eligible": eligible,
            "mean_company_value": mean_company_value, "mean_development_return": retention["mean_reward"],
            "service_count": retention["passed_programs"], "transitions": update * 128, "update": update,
        })
    return result


def selection_key(candidate: dict[str, Any]) -> tuple[float | int | str, ...]:
    return (
        -candidate["service_count"], -candidate["mean_development_return"],
        -candidate["mean_company_value"], candidate["transitions"], candidate["checkpoint_id"],
    )


def select(candidates_value: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [item for item in candidates_value if item["eligible"]]
    require(eligible, "M22 campaign produced no development-eligible checkpoint")
    return min(eligible, key=selection_key)


def validate_update_counts(update: dict[str, Any]) -> None:
    cases = update.get("case_program_counts")
    actions = update.get("action_counts")
    require(isinstance(cases, list) and isinstance(actions, list) and len(cases) == 17 and len(actions) == 17,
            "M22 update case/action count inventory drifted")
    require(cases[0] == 0 and sum(cases) == 128 and sum(actions) == 128 and
            all(isinstance(value, int) and value >= 0 for value in cases + actions),
            "M22 update case/action counts are invalid")


def run_one(
    root: pathlib.Path, executable: pathlib.Path, corpus: pathlib.Path, artifact_root: pathlib.Path,
    bwrap: pathlib.Path, architecture: str, seed: int, training_rewards: dict[int, float],
    development_rewards: dict[int, float], company_values: dict[int, int],
) -> dict[str, Any]:
    run_root = artifact_root / architecture / f"seed-{seed}" / "training"
    checkpoint_root = run_root / "checkpoints"
    command = recovery.sandbox_command(
        bwrap, root, artifact_root, executable, corpus, checkpoint_root, architecture, seed, 48, None,
    )
    process = recovery.run_process(
        "training", command, architecture, seed, 0, 48, checkpoint_root, artifact_root,
    )
    for update in process["updates"]:
        validate_update_counts(update)
        require(update["gradient_norm"] >= 0 and update["clip_fraction"] >= 0 and
                not (update["retention_ran"] and update["retention"]["catastrophic_regression"]),
                "M22 campaign contains an invalid or catastrophic update")
    counts = [sum(update["case_program_counts"][program] for update in process["updates"]) for program in range(17)]
    actions = [sum(update["action_counts"][program] for update in process["updates"]) for program in range(17)]
    matched = matched_baselines(seed, counts, training_rewards)
    learned_mean = sum(update["mean_rollout_reward"] * 128 for update in process["updates"]) / 6144
    learned_correct = sum(update["correct_program_fraction"] * 128 for update in process["updates"]) / 6144
    random_mean = baseline(matched, "seeded-random-legal-v1")["mean_return"]
    wait_mean = baseline(matched, "wait-only-v1")["mean_return"]
    require(learned_mean > random_mean and learned_mean > wait_mean,
            "M22 learned campaign did not improve over its matched random/wait baselines")
    candidate_records = candidates(process, seed, development_rewards, company_values, artifact_root)
    selected = select(candidate_records)
    return {
        "action_counts": actions,
        "architecture": architecture,
        "candidates": candidate_records,
        "case_program_counts": counts,
        "learned": {"beats_seeded_random": True, "beats_wait_only": True,
                    "correct_program_fraction": learned_correct, "mean_training_return": learned_mean, "transitions": 6144},
        "matched_baselines": matched,
        "process": process,
        "provisional_selection": copy.deepcopy(selected),
        "seed": seed,
        "throughput_transitions_per_second": 6144 / process["wall_seconds"],
    }


def run(root: pathlib.Path, executable: pathlib.Path, corpus: pathlib.Path,
        artifact_root: pathlib.Path, evidence_path: pathlib.Path) -> dict[str, Any]:
    root, executable, corpus = root.resolve(), executable.resolve(), corpus.resolve()
    artifact_root, evidence_path = artifact_root.resolve(), evidence_path.resolve()
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "M22 training artifact root must be new")
    require(not evidence_path.exists() and not evidence_path.is_symlink(), "M22 training evidence path must be new")
    require(executable.is_file() and os.access(executable, os.X_OK), "M22 campaign executable is absent")
    bwrap_raw = shutil.which("bwrap")
    require(bwrap_raw is not None, "bubblewrap is required for M22 production training isolation")
    bwrap = pathlib.Path(bwrap_raw).resolve()
    contract = recovery.load(root / CONTRACT)
    require(tuple(contract["seeds"]["trainer_seeds"]) == SEEDS and contract["ppo"]["updates"] == 48 and
            contract["ppo"]["transitions_per_seed"] == 6144 and
            tuple(contract["selection"]["candidate_updates"]) == CANDIDATE_UPDATES,
            "M22 training configuration drifted from the frozen contract")
    decoded = encoder.decode(corpus.read_bytes())
    require(decoded.learning_contract_sha256 == sha256(root / CONTRACT) and decoded.corpus_sha256 == sha256(root / CORPUS),
            "M22 training corpus binary identity drifted")
    training_rewards, development_rewards, company_values = corpus_maps(root, decoded)
    source = source_identity(root)
    artifact_root.mkdir(parents=True, mode=0o700)
    runs = []
    for architecture in ARCHITECTURES:
        for seed in SEEDS:
            runs.append(run_one(root, executable, corpus, artifact_root, bwrap, architecture, seed,
                                training_rewards, development_rewards, company_values))
    all_candidates = []
    for item in runs:
        for candidate in item["candidates"]:
            all_candidates.append({"architecture": item["architecture"], "seed": item["seed"], **candidate})
    provisional = select(all_candidates)
    walls = [item["process"]["wall_seconds"] for item in runs]
    report: dict[str, Any] = {
        "configuration": {
            "architectures": list(ARCHITECTURES), "candidate_updates": list(CANDIDATE_UPDATES),
            "device": "cuda:0", "seeds": list(SEEDS), "transitions_per_seed": 6144, "updates_per_seed": 48,
        },
        "device": device_identity(),
        "identity": {
            "bubblewrap_sha256": sha256(bwrap), "campaign_executable_sha256": sha256(executable),
            "corpus_binary_sha256": sha256(corpus), "learning_contract_sha256": sha256(root / CONTRACT),
            "native_corpus_sha256": sha256(root / CORPUS), "recovery_evidence_sha256": sha256(root / RECOVERY),
            "training_schema_sha256": sha256(root / SCHEMA),
        },
        "isolation": {
            "artifact_root_only_writable": True, "bubblewrap": True, "final_manifest_accessed": False,
            "final_manifest_binding": "read-only-empty-file", "network_namespace": "unshared", "root_filesystem": "read-only",
        },
        "provisional_development_selection": {
            "architecture": provisional["architecture"], "checkpoint_id": provisional["checkpoint_id"],
            "checkpoint_path": provisional["checkpoint_path"], "finalized": False,
            "ordering": list(contract["selection"]["ordering"]), "pending": "native-retention-and-device-gates",
            "seed": provisional["seed"], "update": provisional["update"],
        },
        "runs": runs,
        "schema_version": "openttd-rl-v2-m22-training-evidence-1",
        "source": source,
        "status": "PASS",
        "summary": {
            "architecture_superiority_claimed": False, "campaigns": 6, "candidate_checkpoints": 36,
            "development_eligible_checkpoints": sum(candidate["eligible"] for candidate in all_candidates),
            "finite_updates": 288, "matched_baseline_campaigns": 18,
            "maximum_wall_seconds": max(walls), "total_transitions": 36864,
        },
    }
    report["report_sha256"] = recovery.sha256_bytes(recovery.canonical_bytes(report))
    import validate_m22_training_evidence
    validate_m22_training_evidence.validate_value(report, root, artifact_root, executable, corpus)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with evidence_path.open("xb") as output:
        output.write(recovery.canonical_bytes(report) + b"\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--executable", type=pathlib.Path, required=True)
    parser.add_argument("--corpus", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--evidence", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.root, args.executable, args.corpus, args.artifact_root, args.evidence)
    except (M22TrainingError, recovery.M22RecoveryError, OSError, subprocess.SubprocessError,
            KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_TRAINING=FAIL {exc}", file=sys.stderr)
        return 1
    selected = result["provisional_development_selection"]
    print(f"V2_M22_TRAINING=PASS campaigns={result['summary']['campaigns']} transitions={result['summary']['total_transitions']} "
          f"selected={selected['architecture']}:{selected['seed']}:{selected['update']}:{selected['checkpoint_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
