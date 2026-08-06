#!/usr/bin/env python3
"""Fail-closed validation of M22 selected-checkpoint qualification evidence."""

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
import run_m22_qualification as qualification
import run_m22_recovery as recovery
import run_m22_training as training
import validate_m22_native_corpus as native_validator
import validate_m22_recovery_evidence as recovery_validator
import validate_m22_training_evidence as training_validator
from source_context import SourceContextError, run_git


REPORT = pathlib.Path("config/v2/m22-qualification-evidence.json")
LIVE_CONSUMER = "m22-qualification-evidence"


class M22QualificationValidationError(ValueError):
    """Retained M22 qualification evidence is malformed, stale, or insufficient."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22QualificationValidationError(message)


def committed_bytes(root: pathlib.Path, commit: str, relative: str) -> bytes:
    try:
        completed = run_git("show", f"{commit}:{relative}", repository=root)
    except SourceContextError as exc:
        raise M22QualificationValidationError(
            f"M22 historical source is unavailable: {relative}: {exc}"
        ) from exc
    require(completed.returncode == 0,
            f"M22 historical source is unavailable: {relative}")
    return completed.stdout


def committed_files(root: pathlib.Path, commit: str) -> list[dict[str, str]]:
    return [
        {"path": relative, "sha256": hashlib.sha256(committed_bytes(root, commit, relative)).hexdigest()}
        for relative in qualification.SOURCE_PATHS
    ]


def self_hash(report: dict[str, Any]) -> None:
    payload = copy.deepcopy(report)
    expected = payload.pop("report_sha256")
    require(expected == recovery.sha256_bytes(recovery.canonical_bytes(payload)),
            "M22 qualification report self-hash mismatch")


def _requirements(report: dict[str, Any]) -> tuple[RoleRequirement, ...]:
    selected = report["finalized_selection"]
    checkpoint = report["identity"]["checkpoint"]
    require(checkpoint["path"] == selected["checkpoint_path"],
            "M22 qualification selected checkpoint path drifted")
    requirements = [
        RoleRequirement(
            "qualification-artifacts",
            item["path"],
            "file",
            LIVE_CONSUMER,
            item["sha256"],
        )
        for item in report["artifacts"]
    ]
    requirements.extend(
        RoleRequirement(
            "training-artifacts",
            f"{selected['checkpoint_path']}/{item['name']}",
            "file",
            LIVE_CONSUMER,
            item["sha256"],
        )
        for item in checkpoint["files"]
    )
    identity = report["identity"]
    requirements.extend((
        RoleRequirement(
            "qualification-executable", ".", "file", LIVE_CONSUMER,
            identity["qualification_executable_sha256"],
        ),
        RoleRequirement(
            "v2-corpus-binary", ".", "file", LIVE_CONSUMER,
            identity["corpus_binary_sha256"],
        ),
    ))
    require(len(requirements) == len(set(requirements)),
            "M22 qualification live-input closure contains duplicates")
    return tuple(requirements)


def required_live_inputs(root: pathlib.Path) -> tuple[RoleRequirement, ...]:
    root = root.resolve()
    return _requirements(recovery.load(root / REPORT))


def _validate_record_paths(report: dict[str, Any]) -> None:
    require(
        [item["path"] for item in report["artifacts"]] == list(qualification.ARTIFACT_NAMES),
        "M22 qualification artifact path inventory drifted",
    )
    selected = report["finalized_selection"]
    checkpoint = report["identity"]["checkpoint"]
    checkpoint_id = checkpoint["id"]
    require(
        isinstance(checkpoint_id, str) and re.fullmatch(r"[0-9a-f]{64}", checkpoint_id) is not None and
        checkpoint["path"] == selected["checkpoint_path"] and
        selected["checkpoint_id"] == checkpoint_id and
        recovery_validator._safe_relative_posix(checkpoint["path"]) and
        checkpoint["path"].endswith("/" + checkpoint_id) and
        [item["name"] for item in checkpoint["files"]] == list(recovery.INVENTORY),
        "M22 qualification selected checkpoint inventory/path drifted",
    )


def close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1.0e-9, abs_tol=1.0e-12)


def selected_records(report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    selected = report["provisional_development_selection"]
    runs = [item for item in report["runs"] if item["architecture"] == selected["architecture"] and
            item["seed"] == selected["seed"]]
    require(len(runs) == 1, "M22 qualification selected run is absent or duplicated")
    candidates = [item for item in runs[0]["candidates"] if item["checkpoint_id"] == selected["checkpoint_id"] and
                  item["update"] == selected["update"]]
    require(len(candidates) == 1, "M22 qualification selected candidate is absent or duplicated")
    checkpoint = recovery.checkpoint(runs[0]["process"], selected["update"])
    return runs[0], candidates[0], checkpoint


def validate_device_result(result: dict[str, Any], contract: dict[str, Any], selected: dict[str, Any],
                           decoded: training.encoder.DecodedCorpus) -> None:
    expected_checkpoint = {
        "architecture": selected["architecture"], "id": selected["checkpoint_id"],
        "seed": selected["seed"], "update": selected["update"],
    }
    require(result["checkpoint"] == expected_checkpoint, "M22 qualification device checkpoint identity drifted")
    require(tuple(int(item) for item in result["device"]["compute_capability"].split(".")) >= (12, 0),
            "M22 qualification CUDA compute capability is unsupported")
    tolerances = contract["device"]["tolerances"]
    batches = contract["device"]["parity_batches"]
    require([item["batch"] for item in result["parity"]] == batches,
            "M22 qualification parity batch order or coverage drifted")
    for item in result["parity"]:
        require(item["forward_max_abs"] <= tolerances["forward_max_abs"] and
                item["loss_max_abs"] <= tolerances["loss_max_abs"] and
                item["gradient_max_abs"] <= tolerances["gradient_max_abs"] and
                item["update_max_abs"] <= tolerances["update_max_abs"] and
                item["checkpoint_max_abs"] <= tolerances["checkpoint_max_abs"],
                f"M22 qualification parity tolerance failed at batch {item['batch']}")
        require(item["identical_greedy_programs"] == item["batch"] and
                item["minimum_greedy_margin"] > 2 * tolerances["forward_max_abs"],
                f"M22 qualification stable greedy parity failed at batch {item['batch']}")
        require(all(math.isfinite(value) for value in item.values() if isinstance(value, float)),
                "M22 qualification parity contains a nonfinite metric")
    workloads = ["forward-backward-adam-update", "batched-inference"]
    require([item["workload"] for item in result["benchmarks"]] == workloads,
            "M22 qualification benchmark workload order or coverage drifted")
    for workload in result["benchmarks"]:
        require(workload["warmups"] == contract["device"]["benchmark_warmups"] and
                workload["samples"] == contract["device"]["benchmark_samples"] and
                [item["batch"] for item in workload["batches"]] == contract["device"]["benchmark_batches"],
                "M22 qualification benchmark budget or batch coverage drifted")
        for item in workload["batches"]:
            require(close(item["speedup"], item["cpu"]["median_ns"] / item["cuda"]["median_ns"]),
                    "M22 qualification speedup is not timing-derived")
            for device in ("cpu", "cuda"):
                timing = item[device]
                require(timing["p95_ns"] >= timing["median_ns"] and
                        close(timing["samples_per_second"], item["batch"] * 1.0e9 / timing["median_ns"]),
                        "M22 qualification latency or throughput derivation drifted")
            require(item["peak_allocated_bytes"] > 0 and item["peak_reserved_bytes"] > 0,
                    "M22 qualification CUDA allocation telemetry is empty")
    retention = result["retention"]
    expected_actions = list(range(1, 17))
    require(retention["cpu_actions"] == expected_actions and retention["cuda_actions"] == expected_actions and
            retention["all_programs_pass"] and retention["devices_identical"],
            "M22 qualification lost a native-qualified development program")
    development = sorted((item for item in decoded.entries if item.split == "development"), key=lambda item: item.program)
    require([item.program for item in development] == expected_actions,
            "M22 qualification development corpus coverage drifted")
    expected_reward = sum(item.rewards[item.program] for item in development) / len(development)
    require(close(retention["mean_reward"], expected_reward),
            "M22 qualification retention reward is not corpus-derived")
    require(result["semantics"] == {
        "deterministic_algorithms": True, "dtype": "float32", "mixed_precision": False,
        "observation_encoding": "cpu-public-state-to-device-copy",
        "policy": "cuda:0-production-cpu-oracle", "simulation": "cpu-only", "tf32": False,
    }, "M22 qualification device semantics drifted")


def validate_artifacts(report: dict[str, Any], artifact_root: pathlib.Path) -> None:
    artifact_root = artifact_root.resolve()
    require(artifact_root.is_dir() and not artifact_root.is_symlink(),
            "M22 qualification artifact root is unavailable")
    expected_artifacts = []
    for name in qualification.ARTIFACT_NAMES:
        path = artifact_root / name
        require(path.is_file() and not path.is_symlink(),
                f"M22 qualification artifact is absent: {name}")
        expected_artifacts.append({
            "bytes": path.stat().st_size,
            "path": name,
            "sha256": training.sha256(path),
        })
    require(report["artifacts"] == expected_artifacts,
            "M22 qualification artifact inventory drifted")
    require(recovery.load(artifact_root / "device-result.json") == report["device_result"] and
            recovery.load(artifact_root / "gpu-monitor-summary.json") == report["telemetry"],
            "M22 qualification embedded device/telemetry result drifted from artifacts")
    require(report["process"]["stdout_sha256"] == training.sha256(artifact_root / "stdout.txt") and
            report["process"]["stderr_sha256"] == training.sha256(artifact_root / "stderr.txt"),
            "M22 qualification process log identity drifted")


def validate_value(
    report: dict[str, Any], root: pathlib.Path, training_artifact_root: pathlib.Path | None = None,
    artifact_root: pathlib.Path | None = None, executable: pathlib.Path | None = None,
    corpus: pathlib.Path | None = None, *, artifact_context: ArtifactContext | None = None,
    live_inputs: LiveInputManifest | None = None,
) -> None:
    context = artifact_context or ArtifactContext.offline()
    if artifact_context is not None and not context.is_live:
        training_artifact_root = artifact_root = executable = corpus = None
    root = root.resolve()
    source = report.get("source")
    require(isinstance(source, dict), "M22 qualification source identity is absent")
    commit = source.get("repository_commit")
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
            "M22 qualification source commit is malformed")
    try:
        retained = run_git("cat-file", "-e", commit + "^{commit}", repository=root)
    except SourceContextError as exc:
        raise M22QualificationValidationError(
            f"M22 qualification source commit is unavailable: {exc}"
        ) from exc
    require(retained.returncode == 0, "M22 qualification source commit is not retained")
    schema_bytes = committed_bytes(root, commit, qualification.SCHEMA.as_posix())
    schema = json.loads(schema_bytes)
    jsonschema.Draft202012Validator.check_schema(schema)
    try:
        jsonschema.Draft202012Validator(schema).validate(report)
    except jsonschema.ValidationError as exc:
        location = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M22QualificationValidationError(
            f"M22 qualification schema failed at {location}: {exc.message}") from exc
    self_hash(report)
    files = committed_files(root, commit)
    require(source["clean"] and source["files"] == files and
            source["tree_sha256"] == recovery.sha256_bytes(recovery.canonical_bytes(files)),
            "M22 qualification source identity drifted")

    identity = report["identity"]
    training_bytes = committed_bytes(root, commit, qualification.TRAINING.as_posix())
    expected_committed = {
        "learning_contract_sha256": hashlib.sha256(committed_bytes(root, commit, qualification.CONTRACT.as_posix())).hexdigest(),
        "native_corpus_sha256": hashlib.sha256(committed_bytes(root, commit, qualification.CORPUS.as_posix())).hexdigest(),
        "qualification_schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
        "training_evidence_sha256": hashlib.sha256(training_bytes).hexdigest(),
    }
    require(all(identity[key] == value for key, value in expected_committed.items()),
            "M22 qualification committed contract/corpus/schema/training identity drifted")
    _validate_record_paths(report)
    if context.is_live:
        require(live_inputs is not None and live_inputs.is_live,
                "live-input manifest is required for live M22 qualification validation")
        assert live_inputs is not None
        require(live_inputs.artifact_root == context.artifact_root,
                "live-input manifest and artifact context must share one exact artifact root")
        requirements = _requirements(report)
        live_inputs.preflight(requirements)
        artifact_root = live_inputs.resolve(RoleRequirement(
            "qualification-artifacts", ".", "directory", LIVE_CONSUMER,
        ))
        training_artifact_root = live_inputs.resolve(RoleRequirement(
            "training-artifacts", ".", "directory", LIVE_CONSUMER,
        ))
        executable = live_inputs.resolve(requirements[-2])
        corpus = live_inputs.resolve(requirements[-1])
        selected_checkpoint_path = training_artifact_root / report["finalized_selection"]["checkpoint_path"]
        exact_directories = [
            (artifact_root, tuple(qualification.ARTIFACT_NAMES), "M22 qualification artifact directory"),
            (selected_checkpoint_path, recovery.INVENTORY, "M22 qualification selected checkpoint"),
        ]
        recovery_validator._validate_live_structure(
            live_inputs, requirements, exact_directories, require,
        )
        recovery_validator._validate_checkpoint_artifact(
            selected_checkpoint_path, identity["checkpoint"],
            report["finalized_selection"]["architecture"], report["finalized_selection"]["seed"],
            identity["learning_contract_sha256"], identity["native_corpus_sha256"], require,
        )
    if executable is not None or corpus is not None:
        require(executable is not None and corpus is not None and
                identity["qualification_executable_sha256"] == training.sha256(executable.resolve()) and
                identity["corpus_binary_sha256"] == training.sha256(corpus.resolve()),
                "M22 qualification live executable/corpus identity drifted")

    try:
        training_report = json.loads(training_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise M22QualificationValidationError(
            f"M22 committed training evidence is malformed: {exc}"
        ) from exc
    require(isinstance(training_report, dict), "M22 committed training evidence is not an object")
    training_validator.validate_value(
        training_report,
        root,
        artifact_context=ArtifactContext.offline(),
        live_inputs=LiveInputManifest.offline(),
    )
    selected = training_report["provisional_development_selection"]
    selected_run, selected_candidate, selected_checkpoint = selected_records(training_report)
    require(identity["checkpoint"] == selected_checkpoint,
            "M22 qualification checkpoint inventory is not the development-selected training artifact")
    expected_selection = {
        "architecture": selected["architecture"], "checkpoint_id": selected["checkpoint_id"],
        "checkpoint_path": selected["checkpoint_path"], "final_manifest_accessed": False, "finalized": True,
        "ordering": selected["ordering"], "pending": "final-only-independent-evaluation",
        "qualification": "native-retention-and-device-gates-passed", "seed": selected["seed"], "update": selected["update"],
    }
    require(report["finalized_selection"] == expected_selection,
            "M22 qualification finalized a checkpoint other than the development selection")
    if training_artifact_root is not None:
        checkpoint = training_artifact_root.resolve() / selected["checkpoint_path"]
        observed = recovery.inspect_checkpoint(
            checkpoint, training_artifact_root.resolve(), selected["update"], selected["checkpoint_id"],
        )
        require(observed == identity["checkpoint"], "M22 qualification checkpoint artifact identity drifted")

    contract = recovery.load(root / qualification.CONTRACT)
    expected_configuration = {
        "benchmark_batches": contract["device"]["benchmark_batches"],
        "benchmark_samples": contract["device"]["benchmark_samples"],
        "benchmark_warmups": contract["device"]["benchmark_warmups"], "oracle": contract["device"]["oracle"],
        "parity_batches": contract["device"]["parity_batches"], "production": contract["device"]["production"],
        "retention_programs": 16, "retention_split": "development",
        "tolerances": contract["device"]["tolerances"],
    }
    require(report["configuration"] == expected_configuration,
            "M22 qualification configuration drifted from the learning contract")
    decoded = training.encoder.decode(corpus.resolve().read_bytes()) if corpus is not None else training.encoder.decode(training.encoder.encode(root))
    validate_device_result(report["device_result"], contract, selected, decoded)

    native_summary = native_validator.validate(
        root,
        artifact_context=ArtifactContext.offline(),
    )
    corpus_json = recovery.load(root / qualification.CORPUS)
    expected_native = {
        "accepted_checkpoint_count": 1,
        "development": {"all_programs_pass": True, "devices_identical": True, "programs": 16, "split": "development"},
        "native_corpus_revalidated": native_summary.entries == 32 and native_summary.native_gates == 7,
        "source_validation": "exact-rebuild-from-accepted-G15-G21-evidence",
        "sources": [{**item, "status": "PASS"} for item in corpus_json["sources"]],
    }
    require(report["native_retention"] == expected_native,
            "M22 qualification native G15-G21 retention binding drifted")
    expected_baselines = {
        "architecture_superiority_claimed": training_report["summary"]["architecture_superiority_claimed"],
        "development": selected_candidate["development_baselines"], "learned": selected_run["learned"],
        "matched_baseline_campaigns": training_report["summary"]["matched_baseline_campaigns"],
        "matched_training": selected_run["matched_baselines"], "training_campaigns": training_report["summary"]["campaigns"],
    }
    require(report["baseline_binding"] == expected_baselines,
            "M22 qualification matched baseline binding drifted")
    require(report["isolation"] == {
        "artifact_root_only_writable": True, "bubblewrap": True, "final_manifest_accessed": False,
        "final_manifest_binding": "read-only-empty-file", "network_namespace": "unshared", "root_filesystem": "read-only",
    }, "M22 qualification isolation drifted")
    telemetry = report["telemetry"]
    require(telemetry["sample_count"] == telemetry["available_samples"] and telemetry["unavailable_samples"] == 0 and
            telemetry["name"] == report["device_result"]["device"]["name"],
            "M22 qualification telemetry coverage or device identity drifted")
    require(report["summary"] == {
        "accepted_checkpoints": 1, "benchmark_measurements": 6, "final_manifest_accessed": False,
        "native_gates": 7, "parity_batches": 3, "retained_programs": 16, "selection_finalized": True,
    }, "M22 qualification summary drifted")
    require([item["path"] for item in report["artifacts"]] == list(qualification.ARTIFACT_NAMES),
            "M22 qualification artifact path inventory drifted")

    if artifact_root is not None and (context.is_live or artifact_context is None):
        validate_artifacts(report, artifact_root)


def validate(
    report_path: pathlib.Path,
    root: pathlib.Path,
    *,
    artifact_context: ArtifactContext | None = None,
) -> dict[str, bool]:
    context = artifact_context or ArtifactContext.offline()
    report = recovery.load(report_path.resolve())
    require(report_path.resolve().read_bytes() == recovery.canonical_bytes(report) + b"\n",
            "M22 qualification evidence is not canonical JSON")
    live_inputs = (
        LiveInputManifest.load(context.artifact_root)
        if context.is_live and context.artifact_root is not None
        else LiveInputManifest.offline()
    )
    validate_value(
        report, root,
        artifact_context=context,
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
        context = ArtifactContext.offline() if artifact_root is None else ArtifactContext.live(artifact_root)
        summary = validate(
            args.report, args.root,
            artifact_context=context,
        )
        report = recovery.load(args.report)
    except (M22QualificationValidationError, qualification.M22QualificationError, training.M22TrainingError,
            recovery.M22RecoveryError, ArtifactContextError, SourceContextError, OSError, json.JSONDecodeError,
            jsonschema.ValidationError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_QUALIFICATION_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1
    selected = report["finalized_selection"]
    print(f"V2_M22_QUALIFICATION_EVIDENCE=PASS checkpoint={selected['checkpoint_id']} "
          f"parity={report['summary']['parity_batches']} native_programs={report['summary']['retained_programs']} "
          f"live={str(summary['live']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
