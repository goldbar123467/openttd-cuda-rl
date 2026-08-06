#!/usr/bin/env python3
"""Validate all-six-run M22 training, baseline, and development-selection evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import pathlib
import re
import sys
from typing import Any

import jsonschema

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    LiveInputManifest,
    RoleRequirement,
    add_artifact_root_argument,
    resolve_artifact_root,
)
import encode_m22_native_corpus as encoder
import run_m22_recovery as recovery
import run_m22_training as training
from source_context import SourceContextError, run_git


REPORT = pathlib.Path("config/v2/m22-training-evidence.json")
LIVE_CONSUMER = "m22-training-evidence"


class M22TrainingValidationError(ValueError):
    """The retained M22 training evidence is malformed or insufficient."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22TrainingValidationError(message)


def self_hash(value: dict[str, Any]) -> None:
    payload = copy.deepcopy(value)
    expected = payload.pop("report_sha256")
    require(expected == recovery.sha256_bytes(recovery.canonical_bytes(payload)), "M22 training report self-hash mismatch")


def _requirements(report: dict[str, Any]) -> tuple[RoleRequirement, ...]:
    requirements: list[RoleRequirement] = []
    for run in report["runs"]:
        process = run["process"]
        requirements.append(RoleRequirement(
            "training-artifacts",
            process["log_path"],
            "file",
            LIVE_CONSUMER,
            process["stdout_sha256"],
        ))
        for checkpoint in process["checkpoints"]:
            for item in checkpoint["files"]:
                requirements.append(RoleRequirement(
                    "training-artifacts",
                    f"{checkpoint['path']}/{item['name']}",
                    "file",
                    LIVE_CONSUMER,
                    item["sha256"],
                ))
    identity = report["identity"]
    requirements.extend((
        RoleRequirement(
            "v2-campaign-executable", ".", "file", LIVE_CONSUMER,
            identity["campaign_executable_sha256"],
        ),
        RoleRequirement(
            "v2-corpus-binary", ".", "file", LIVE_CONSUMER,
            identity["corpus_binary_sha256"],
        ),
    ))
    require(len(requirements) == len(set(requirements)),
            "M22 training live-input closure contains duplicates")
    return tuple(requirements)


def required_live_inputs(root: pathlib.Path) -> tuple[RoleRequirement, ...]:
    root = root.resolve()
    return _requirements(recovery.load(root / REPORT))


def committed_bytes(root: pathlib.Path, commit: str, relative: str) -> bytes:
    try:
        completed = run_git("show", f"{commit}:{relative}", repository=root)
    except SourceContextError as exc:
        raise M22TrainingValidationError(
            f"M22 historical source is unavailable: {relative}: {exc}"
        ) from exc
    require(completed.returncode == 0,
            f"M22 historical source is unavailable: {relative}")
    return completed.stdout


def committed_files(root: pathlib.Path, commit: str) -> list[dict[str, str]]:
    return [
        {"path": relative, "sha256": hashlib.sha256(committed_bytes(root, commit, relative)).hexdigest()}
        for relative in training.SOURCE_PATHS
    ]


def validate_process(process: dict[str, Any], architecture: str, seed: int) -> None:
    require(process["exit_code"] == 0 and process["name"] == "training" and process["pid"] > 1 and
            process["wall_seconds"] > 0, "M22 training process did not complete freshly")
    require([item["update"] for item in process["updates"]] == list(range(1, 49)), "M22 training update sequence drifted")
    require(process["updates_sha256"] == recovery.sha256_bytes(recovery.canonical_bytes(process["updates"])),
            "M22 training update digest mismatch")
    require(process["terminal"] == {"architecture": architecture, "seed": seed, "transitions": 6144, "updates": 48},
            "M22 training terminal projection drifted")
    require([item["update"] for item in process["checkpoints"]] == list(training.CANDIDATE_UPDATES),
            "M22 training checkpoint cadence drifted")
    for checkpoint in process["checkpoints"]:
        checkpoint_path = checkpoint["path"]
        require(isinstance(checkpoint_path, str) and checkpoint_path and
                not checkpoint_path.startswith("/") and "\\" not in checkpoint_path and
                "\x00" not in checkpoint_path and
                all(part not in {"", ".", ".."} for part in checkpoint_path.split("/")) and
                checkpoint_path.endswith("/" + checkpoint["id"]) and
                [item["name"] for item in checkpoint["files"]] == list(recovery.INVENTORY),
                "M22 training checkpoint inventory/path drifted")
    for index, update in enumerate(process["updates"], 1):
        training.validate_update_counts(update)
        require(update["update"] == index and update["transitions"] == index * 128 and
                all(math.isfinite(value) for value in update.values() if isinstance(value, float)),
                "M22 training update metric/counter drifted")
        retention_expected = index % 4 == 0
        require(update["retention_ran"] is retention_expected and ("retention" in update) is retention_expected,
                "M22 training retention cadence drifted")
        if retention_expected:
            require(not update["retention"]["catastrophic_regression"] and update["retention"]["checkpoint_allowed"],
                    "M22 training suffered catastrophic retention loss")


def validate_candidates(run: dict[str, Any], development_rewards: dict[int, float], company_values: dict[int, int]) -> None:
    require([item["update"] for item in run["candidates"]] == list(training.CANDIDATE_UPDATES),
            "M22 training candidate cadence drifted")
    updates = {item["update"]: item for item in run["process"]["updates"]}
    for candidate in run["candidates"]:
        retention = updates[candidate["update"]]["retention"]
        development = training.development_baselines(run["seed"], retention["introduced_programs"], development_rewards)
        company = sum(company_values[program] if retention["pass_mask"] & (1 << program) else 0
                      for program in range(1, retention["introduced_programs"] + 1)) / retention["introduced_programs"]
        require(candidate["development_baselines"] == development and candidate["service_count"] == retention["passed_programs"] and
                candidate["mean_development_return"] == retention["mean_reward"] and candidate["mean_company_value"] == company and
                candidate["transitions"] == candidate["update"] * 128,
                "M22 training candidate metrics are not source-derived")
        random_record = training.baseline(development, "seeded-random-legal-v1")
        expected_eligibility = {
            "all_introduced_stages_pass": retention["passed_programs"] == retention["introduced_programs"],
            "beats_seeded_random": retention["mean_reward"] > random_record["mean_return"],
            "beats_wait_only": retention["mean_reward"] > 0,
            "checkpoint_allowed": retention["checkpoint_allowed"], "final_access": False,
            "finite_metrics": all(math.isfinite(value) for value in (retention["accuracy"], retention["mean_reward"], company)),
            "native_failures": 0,
        }
        eligible = all(value is True for key, value in expected_eligibility.items() if key not in {"final_access", "native_failures"})
        require(candidate["eligibility"] == expected_eligibility and candidate["eligible"] is eligible,
                "M22 training candidate eligibility is not source-derived")
        checkpoint = recovery.checkpoint(run["process"], candidate["update"])
        require(candidate["checkpoint_id"] == checkpoint["id"] and candidate["checkpoint_path"] == checkpoint["path"],
                "M22 training candidate checkpoint identity drifted")
    require(run["provisional_selection"] == training.select(run["candidates"]),
            "M22 per-run development selection ordering drifted")


def validate_artifacts(report: dict[str, Any], artifact_root: pathlib.Path) -> None:
    artifact_root = artifact_root.resolve()
    require(artifact_root.is_dir() and not artifact_root.is_symlink(), "M22 training artifact root is unavailable")
    for run in report["runs"]:
        process = run["process"]
        log = artifact_root / process["log_path"]
        require(log.is_file() and training.sha256(log) == process["stdout_sha256"], "M22 training log identity drifted")
        for checkpoint in process["checkpoints"]:
            path = artifact_root / checkpoint["path"]
            observed = [{"bytes": (path / name).stat().st_size, "name": name, "sha256": training.sha256(path / name)}
                        for name in recovery.INVENTORY]
            require(observed == checkpoint["files"], "M22 training checkpoint artifact identity drifted")


def validate_value(report: dict[str, Any], root: pathlib.Path, artifact_root: pathlib.Path | None = None,
                   executable: pathlib.Path | None = None, corpus: pathlib.Path | None = None, *,
                   artifact_context: ArtifactContext | None = None,
                   live_inputs: LiveInputManifest | None = None) -> None:
    context = artifact_context or ArtifactContext.offline()
    if artifact_context is not None and not context.is_live:
        artifact_root = executable = corpus = None
    root = root.resolve()
    source = report.get("source")
    require(isinstance(source, dict), "M22 training source identity is absent")
    commit = source.get("repository_commit")
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
            "M22 training source commit is malformed")
    try:
        retained = run_git("cat-file", "-e", commit + "^{commit}", repository=root)
    except SourceContextError as exc:
        raise M22TrainingValidationError(f"M22 training source commit is unavailable: {exc}") from exc
    require(retained.returncode == 0, "M22 training source commit is not retained")
    try:
        schema = json.loads(committed_bytes(root, commit, training.SCHEMA.as_posix()))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise M22TrainingValidationError(f"M22 committed training schema is malformed: {exc}") from exc
    jsonschema.Draft202012Validator.check_schema(schema)
    try:
        jsonschema.Draft202012Validator(schema).validate(report)
    except jsonschema.ValidationError as exc:
        location = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M22TrainingValidationError(f"M22 training schema failed at {location}: {exc.message}") from exc
    self_hash(report)
    files = committed_files(root, commit)
    require(source["clean"] and source["files"] == files and
            source["tree_sha256"] == recovery.sha256_bytes(recovery.canonical_bytes(files)),
            "M22 training source identity drifted")
    source_hashes = {item["path"]: item["sha256"] for item in files}
    identity = report["identity"]
    require(identity["learning_contract_sha256"] == source_hashes[training.CONTRACT.as_posix()] and
            identity["native_corpus_sha256"] == source_hashes[training.CORPUS.as_posix()] and
            identity["recovery_evidence_sha256"] == source_hashes[training.RECOVERY.as_posix()] and
            identity["training_schema_sha256"] == hashlib.sha256(
                committed_bytes(root, commit, training.SCHEMA.as_posix())).hexdigest(),
            "M22 training contract/corpus/schema identity drifted")
    if context.is_live:
        require(live_inputs is not None and live_inputs.is_live,
                "live-input manifest is required for live M22 training validation")
        assert live_inputs is not None
        require(live_inputs.artifact_root == context.artifact_root,
                "live-input manifest and artifact context must share one exact artifact root")
        requirements = _requirements(report)
        live_inputs.preflight(requirements)
        artifact_root = live_inputs.resolve(RoleRequirement(
            "training-artifacts", ".", "directory", LIVE_CONSUMER,
        ))
        executable = live_inputs.resolve(requirements[-2])
        corpus = live_inputs.resolve(requirements[-1])
    if executable is not None:
        require(identity["campaign_executable_sha256"] == training.sha256(executable.resolve()) and
                identity["corpus_binary_sha256"] == training.sha256(corpus.resolve()),
                "M22 training live executable/corpus identity drifted")
    require(report["configuration"] == {
        "architectures": list(training.ARCHITECTURES), "candidate_updates": list(training.CANDIDATE_UPDATES),
        "device": "cuda:0", "seeds": list(training.SEEDS), "transitions_per_seed": 6144, "updates_per_seed": 48,
    }, "M22 training configuration drifted")
    require(report["isolation"] == {
        "artifact_root_only_writable": True, "bubblewrap": True, "final_manifest_accessed": False,
        "final_manifest_binding": "read-only-empty-file", "network_namespace": "unshared", "root_filesystem": "read-only",
    }, "M22 training isolation drifted")
    expected_runs = [(architecture, seed) for architecture in training.ARCHITECTURES for seed in training.SEEDS]
    require([(item["architecture"], item["seed"]) for item in report["runs"]] == expected_runs,
            "M22 training run inventory/order drifted")
    decoded = encoder.decode((corpus.resolve() if corpus is not None else pathlib.Path("/dev/null")).read_bytes()) if corpus is not None else None
    if decoded is None:
        binary = encoder.encode(root)
        decoded = encoder.decode(binary)
    training_rewards, development_rewards, company_values = training.corpus_maps(root, decoded)
    pids = []
    all_candidates = []
    for run in report["runs"]:
        validate_process(run["process"], run["architecture"], run["seed"])
        pids.append(run["process"]["pid"])
        counts = [sum(update["case_program_counts"][program] for update in run["process"]["updates"]) for program in range(17)]
        actions = [sum(update["action_counts"][program] for update in run["process"]["updates"]) for program in range(17)]
        require(run["case_program_counts"] == counts and run["action_counts"] == actions,
                "M22 training aggregate program/action counts drifted")
        require(run["matched_baselines"] == training.matched_baselines(run["seed"], counts, training_rewards),
                "M22 matched baseline result drifted")
        learned_return = sum(update["mean_rollout_reward"] * 128 for update in run["process"]["updates"]) / 6144
        learned_correct = sum(update["correct_program_fraction"] * 128 for update in run["process"]["updates"]) / 6144
        random_mean = training.baseline(run["matched_baselines"], "seeded-random-legal-v1")["mean_return"]
        wait_mean = training.baseline(run["matched_baselines"], "wait-only-v1")["mean_return"]
        require(run["learned"] == {"beats_seeded_random": learned_return > random_mean,
                                   "beats_wait_only": learned_return > wait_mean,
                                   "correct_program_fraction": learned_correct, "mean_training_return": learned_return,
                                   "transitions": 6144} and run["learned"]["beats_seeded_random"] and
                run["learned"]["beats_wait_only"], "M22 learned aggregate/baseline improvement drifted")
        require(run["throughput_transitions_per_second"] == 6144 / run["process"]["wall_seconds"],
                "M22 training throughput is not source-derived")
        validate_candidates(run, development_rewards, company_values)
        for candidate in run["candidates"]:
            all_candidates.append({"architecture": run["architecture"], "seed": run["seed"], **candidate})
    require(len(set(pids)) == 6, "M22 training did not use six fresh processes")
    selected = training.select(all_candidates)
    expected_selection = {
        "architecture": selected["architecture"], "checkpoint_id": selected["checkpoint_id"],
        "checkpoint_path": selected["checkpoint_path"], "finalized": False,
        "ordering": ["all-stage-service-count-descending", "mean-development-return-descending",
                     "mean-company-value-descending", "transition-count-ascending", "checkpoint-id-ascending"],
        "pending": "native-retention-and-device-gates", "seed": selected["seed"], "update": selected["update"],
    }
    require(report["provisional_development_selection"] == expected_selection,
            "M22 overall development selection ordering drifted")
    walls = [run["process"]["wall_seconds"] for run in report["runs"]]
    require(report["summary"] == {
        "architecture_superiority_claimed": False, "campaigns": 6, "candidate_checkpoints": 36,
        "development_eligible_checkpoints": sum(candidate["eligible"] for candidate in all_candidates),
        "finite_updates": 288, "matched_baseline_campaigns": 18, "maximum_wall_seconds": max(walls),
        "total_transitions": 36864,
    }, "M22 training summary drifted")
    if context.is_live and artifact_root is not None:
        validate_artifacts(report, artifact_root)
    elif artifact_context is None and artifact_root is not None:
        validate_artifacts(report, artifact_root)


def validate(report_path: pathlib.Path, root: pathlib.Path, artifact_root: pathlib.Path | None = None,
             executable: pathlib.Path | None = None, corpus: pathlib.Path | None = None, *,
             artifact_context: ArtifactContext | None = None,
             live_inputs: LiveInputManifest | None = None) -> dict[str, bool]:
    context = artifact_context or ArtifactContext.offline()
    report = recovery.load(report_path.resolve())
    require(report_path.resolve().read_bytes() == recovery.canonical_bytes(report) + b"\n",
            "M22 training evidence is not canonical JSON")
    validate_value(
        report, root, artifact_root, executable, corpus,
        artifact_context=context if artifact_context is not None else None,
        live_inputs=live_inputs,
    )
    return {"live": context.is_live}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--report", type=pathlib.Path, required=True)
    add_artifact_root_argument(parser)
    args = parser.parse_args(argv)
    try:
        artifact_root = resolve_artifact_root(args.artifact_root)
        if artifact_root is None:
            context = ArtifactContext.offline()
            live_inputs = LiveInputManifest.offline()
        else:
            context = ArtifactContext.live(artifact_root)
            live_inputs = LiveInputManifest.load(artifact_root)
        summary = validate(
            args.report, args.root,
            artifact_context=context,
            live_inputs=live_inputs,
        )
        report = recovery.load(args.report)
    except (M22TrainingValidationError, training.M22TrainingError, recovery.M22RecoveryError,
            ArtifactContextError, SourceContextError, OSError, jsonschema.ValidationError,
            KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_TRAINING_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1
    selected = report["provisional_development_selection"]
    print(f"V2_M22_TRAINING_EVIDENCE=PASS campaigns={report['summary']['campaigns']} "
          f"updates={report['summary']['finite_updates']} selected={selected['checkpoint_id']} "
          f"live={str(summary['live']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
