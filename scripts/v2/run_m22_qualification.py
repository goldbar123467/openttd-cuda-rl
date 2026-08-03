#!/usr/bin/env python3
"""Qualify and finalize the development-selected M22 checkpoint without final access."""

from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import re
import resource
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Any

import run_m22_recovery as recovery
import run_m22_training as training
import validate_m22_native_corpus as native_validator
import validate_m22_training_evidence as training_validator


CONTRACT = pathlib.Path("config/v2/m22-learning-contract.json")
CORPUS = pathlib.Path("config/v2/m22-native-corpus.json")
TRAINING = pathlib.Path("config/v2/m22-training-evidence.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m22-qualification-evidence.schema.json")
FINAL_MANIFEST = recovery.FINAL_MANIFEST
ARTIFACT_NAMES = (
    "device-result.json", "gpu-monitor-summary.json", "gpu-telemetry.jsonl", "stderr.txt", "stdout.txt",
)
SOURCE_PATHS = tuple(sorted(set(training.SOURCE_PATHS + (
    "docs/project/schema/v2-m22-qualification-evidence.schema.json",
    "scripts/v2/build_m22_native_corpus.py",
    "scripts/v2/run_m22_qualification.py",
    "scripts/v2/validate_m22_native_corpus.py",
    "scripts/v2/validate_m22_qualification_evidence.py",
    "tests/project/v2/test_v2_m22_qualification.py",
    "training/v2/tests/m22_qualification_gate.cpp",
))))
TELEMETRY_QUERY = "name,uuid,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"


class M22QualificationError(RuntimeError):
    """The selected checkpoint did not close the pre-final M22 qualification boundary."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22QualificationError(message)


def source_identity(root: pathlib.Path) -> dict[str, Any]:
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=root, check=True,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    require(status == "", "accepted M22 qualification requires a clean source worktree")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "M22 qualification source commit is malformed")
    files = []
    for relative in SOURCE_PATHS:
        path = root / relative
        require(path.is_file() and not path.is_symlink(), f"M22 qualification source is absent or symlinked: {relative}")
        files.append({"path": relative, "sha256": training.sha256(path)})
    return {
        "clean": True, "files": files, "repository_commit": commit,
        "tree_sha256": recovery.sha256_bytes(recovery.canonical_bytes(files)),
    }


def parse_telemetry_sample(text: str, timestamp_ns: int) -> dict[str, Any]:
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    require(len(rows) == 1, "nvidia-smi returned zero or multiple devices")
    fields = [field.strip() for field in rows[0].split(",")]
    require(len(fields) == 7, "nvidia-smi telemetry field count drifted")
    name, uuid, utilization, memory_used, memory_total, temperature, power = fields
    return {
        "gpu_available": True, "memory_total_mib": int(memory_total), "memory_used_mib": int(memory_used),
        "name": name, "power_w": float(power), "temperature_c": int(temperature),
        "timestamp_ns": timestamp_ns, "utilization_percent": int(utilization), "uuid": uuid,
    }


def sample_telemetry(nvidia_smi: pathlib.Path) -> dict[str, Any]:
    timestamp_ns = time.time_ns()
    try:
        result = subprocess.run(
            [str(nvidia_smi), f"--query-gpu={TELEMETRY_QUERY}", "--format=csv,noheader,nounits"],
            check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
        )
        if result.returncode != 0:
            raise M22QualificationError(result.stderr.strip() or f"nvidia-smi exited {result.returncode}")
        return parse_telemetry_sample(result.stdout, timestamp_ns)
    except (OSError, subprocess.TimeoutExpired, ValueError, M22QualificationError) as exc:
        return {
            "detail": str(exc), "gpu_available": False, "memory_total_mib": None, "memory_used_mib": None,
            "name": None, "power_w": None, "temperature_c": None, "timestamp_ns": timestamp_ns,
            "utilization_percent": None, "uuid": None,
        }


def monitor(nvidia_smi: pathlib.Path, destination: pathlib.Path, stop: threading.Event) -> None:
    with destination.open("x", encoding="utf-8") as output:
        while True:
            output.write(json.dumps(sample_telemetry(nvidia_smi), allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n")
            output.flush()
            if stop.wait(0.2):
                break


def summarize_telemetry(path: pathlib.Path) -> dict[str, Any]:
    samples = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    available = [sample for sample in samples if sample["gpu_available"]]
    require(available and len(available) == len(samples), "M22 qualification GPU telemetry is unavailable")
    require(len({sample["name"] for sample in available}) == 1 and
            len({sample["uuid"] for sample in available}) == 1, "M22 qualification GPU identity changed")
    return {
        "available_samples": len(available), "gpu_available": True,
        "memory_peak_mib": max(sample["memory_used_mib"] for sample in available),
        "name": available[0]["name"], "power_peak_w": max(sample["power_w"] for sample in available),
        "sample_count": len(samples), "temperature_peak_c": max(sample["temperature_c"] for sample in available),
        "unavailable_samples": 0,
        "utilization_mean_percent": sum(sample["utilization_percent"] for sample in available) / len(available),
        "utilization_peak_percent": max(sample["utilization_percent"] for sample in available),
        "uuid": available[0]["uuid"],
    }


def sandbox_command(
    bwrap: pathlib.Path, root: pathlib.Path, artifact_root: pathlib.Path, executable: pathlib.Path,
    corpus: pathlib.Path, checkpoint: pathlib.Path,
) -> list[str]:
    report = artifact_root / "device-result.json"
    return [
        str(bwrap), "--die-with-parent", "--new-session", "--unshare-net",
        "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev", "--proc", "/proc",
        "--tmpfs", "/tmp", "--bind", str(artifact_root), str(artifact_root),
        "--ro-bind", str(executable), str(executable), "--ro-bind", str(corpus), str(corpus),
        "--ro-bind", str(checkpoint), str(checkpoint), "--ro-bind", "/dev/null", str(root / FINAL_MANIFEST),
        "--chdir", str(root), "--clearenv", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp",
        "--setenv", "TMPDIR", "/tmp", "--setenv", "LANG", "C.UTF-8", "--setenv", "TZ", "UTC",
        "--setenv", "CUDA_VISIBLE_DEVICES", "0", "--setenv", "CUDA_CACHE_DISABLE", "1",
        "--setenv", "CUBLAS_WORKSPACE_CONFIG", ":4096:8", "--setenv", "OMP_NUM_THREADS", "6",
        "--", str(executable), "--checkpoint", str(checkpoint), "--corpus", str(corpus), "--report", str(report),
    ]


def run_process(command: list[str], artifact_root: pathlib.Path, nvidia_smi: pathlib.Path) -> dict[str, Any]:
    telemetry_path = artifact_root / "gpu-telemetry.jsonl"
    stop = threading.Event()
    monitor_thread = threading.Thread(target=monitor, args=(nvidia_smi, telemetry_path, stop), daemon=False)
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.monotonic()
    monitor_thread.start()
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, preexec_fn=recovery.apply_limits,
    )
    try:
        stdout, stderr = process.communicate(timeout=1800)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        raise M22QualificationError("M22 qualification exceeded its 1,800-second timeout")
    finally:
        stop.set()
        monitor_thread.join(timeout=10)
    wall_seconds = round(time.monotonic() - started, 6)
    usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    (artifact_root / "stdout.txt").write_bytes(stdout)
    (artifact_root / "stderr.txt").write_bytes(stderr)
    require(process.returncode == 0, f"M22 qualification process failed ({process.returncode}): {stderr[-1000:]!r}")
    require((artifact_root / "device-result.json").is_file(), "M22 qualification device result is absent")
    telemetry = summarize_telemetry(telemetry_path)
    (artifact_root / "gpu-monitor-summary.json").write_bytes(recovery.canonical_bytes(telemetry) + b"\n")
    return {
        "process": {
            "exit_code": 0, "max_rss_kib": usage_after.ru_maxrss, "pid": process.pid,
            "stderr_sha256": training.sha256(artifact_root / "stderr.txt"),
            "stdout_sha256": training.sha256(artifact_root / "stdout.txt"),
            "system_cpu_seconds": round(usage_after.ru_stime - usage_before.ru_stime, 6),
            "user_cpu_seconds": round(usage_after.ru_utime - usage_before.ru_utime, 6),
            "wall_seconds": wall_seconds,
        },
        "telemetry": telemetry,
    }


def artifact_inventory(artifact_root: pathlib.Path) -> list[dict[str, Any]]:
    result = []
    for name in ARTIFACT_NAMES:
        path = artifact_root / name
        require(path.is_file() and not path.is_symlink(), f"M22 qualification artifact is absent or symlinked: {name}")
        result.append({"bytes": path.stat().st_size, "path": name, "sha256": training.sha256(path)})
    return result


def selected_records(report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    selected = report["provisional_development_selection"]
    runs = [item for item in report["runs"] if item["architecture"] == selected["architecture"] and
            item["seed"] == selected["seed"]]
    require(len(runs) == 1, "M22 selected training run is absent or duplicated")
    candidates = [item for item in runs[0]["candidates"] if item["checkpoint_id"] == selected["checkpoint_id"] and
                  item["update"] == selected["update"]]
    require(len(candidates) == 1, "M22 selected training candidate is absent or duplicated")
    return runs[0], candidates[0]


def run(
    root: pathlib.Path, executable: pathlib.Path, corpus: pathlib.Path, training_artifact_root: pathlib.Path,
    artifact_root: pathlib.Path, evidence_path: pathlib.Path,
) -> dict[str, Any]:
    root, executable, corpus = root.resolve(), executable.resolve(), corpus.resolve()
    training_artifact_root, artifact_root, evidence_path = (
        training_artifact_root.resolve(), artifact_root.resolve(), evidence_path.resolve(),
    )
    require(executable.is_file() and os.access(executable, os.X_OK), "M22 qualification executable is absent")
    require(corpus.is_file() and not corpus.is_symlink(), "M22 qualification corpus binary is absent or symlinked")
    require(training_artifact_root.is_dir() and not training_artifact_root.is_symlink(),
            "M22 training artifact root is absent or symlinked")
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "M22 qualification artifact root must be new")
    require(not evidence_path.exists() and not evidence_path.is_symlink(), "M22 qualification evidence path must be new")
    bwrap_raw, nvidia_raw = shutil.which("bwrap"), shutil.which("nvidia-smi")
    require(bwrap_raw is not None, "bubblewrap is required for M22 qualification isolation")
    require(nvidia_raw is not None, "nvidia-smi is required for M22 qualification telemetry")
    bwrap, nvidia_smi = pathlib.Path(bwrap_raw).resolve(), pathlib.Path(nvidia_raw).resolve()

    training_report = recovery.load(root / TRAINING)
    training_validator.validate_value(training_report, root, training_artifact_root)
    native_summary = native_validator.validate(root)
    contract = recovery.load(root / CONTRACT)
    decoded = training.encoder.decode(corpus.read_bytes())
    require(decoded.learning_contract_sha256 == training.sha256(root / CONTRACT) and
            decoded.corpus_sha256 == training.sha256(root / CORPUS), "M22 qualification corpus identities drifted")
    selected = training_report["provisional_development_selection"]
    checkpoint = training_artifact_root / selected["checkpoint_path"]
    checkpoint_record = recovery.inspect_checkpoint(
        checkpoint, training_artifact_root, selected["update"], selected["checkpoint_id"],
    )
    source = source_identity(root)
    artifact_root.mkdir(parents=True, mode=0o700)
    executed = run_process(
        sandbox_command(bwrap, root, artifact_root, executable, corpus, checkpoint), artifact_root, nvidia_smi,
    )
    device_result = recovery.load(artifact_root / "device-result.json")
    selected_run, selected_candidate = selected_records(training_report)
    corpus_json = recovery.load(root / CORPUS)
    finalized = {
        "architecture": selected["architecture"], "checkpoint_id": selected["checkpoint_id"],
        "checkpoint_path": selected["checkpoint_path"], "final_manifest_accessed": False, "finalized": True,
        "ordering": copy.deepcopy(selected["ordering"]), "pending": "final-only-independent-evaluation",
        "qualification": "native-retention-and-device-gates-passed", "seed": selected["seed"], "update": selected["update"],
    }
    report: dict[str, Any] = {
        "artifacts": artifact_inventory(artifact_root),
        "baseline_binding": {
            "architecture_superiority_claimed": training_report["summary"]["architecture_superiority_claimed"],
            "development": copy.deepcopy(selected_candidate["development_baselines"]),
            "learned": copy.deepcopy(selected_run["learned"]),
            "matched_baseline_campaigns": training_report["summary"]["matched_baseline_campaigns"],
            "matched_training": copy.deepcopy(selected_run["matched_baselines"]),
            "training_campaigns": training_report["summary"]["campaigns"],
        },
        "configuration": {
            "benchmark_batches": copy.deepcopy(contract["device"]["benchmark_batches"]),
            "benchmark_samples": contract["device"]["benchmark_samples"],
            "benchmark_warmups": contract["device"]["benchmark_warmups"], "oracle": contract["device"]["oracle"],
            "parity_batches": copy.deepcopy(contract["device"]["parity_batches"]),
            "production": contract["device"]["production"], "retention_programs": 16,
            "retention_split": "development", "tolerances": copy.deepcopy(contract["device"]["tolerances"]),
        },
        "device_result": device_result,
        "finalized_selection": finalized,
        "identity": {
            "bubblewrap_sha256": training.sha256(bwrap), "checkpoint": checkpoint_record,
            "corpus_binary_sha256": training.sha256(corpus),
            "learning_contract_sha256": training.sha256(root / CONTRACT),
            "native_corpus_sha256": training.sha256(root / CORPUS),
            "qualification_executable_sha256": training.sha256(executable),
            "qualification_schema_sha256": training.sha256(root / SCHEMA),
            "training_evidence_sha256": training.sha256(root / TRAINING),
        },
        "isolation": {
            "artifact_root_only_writable": True, "bubblewrap": True, "final_manifest_accessed": False,
            "final_manifest_binding": "read-only-empty-file", "network_namespace": "unshared",
            "root_filesystem": "read-only",
        },
        "native_retention": {
            "accepted_checkpoint_count": 1,
            "development": {key: device_result["retention"][key] for key in
                            ("all_programs_pass", "devices_identical", "programs", "split")},
            "native_corpus_revalidated": native_summary.native_gates == 7 and native_summary.entries == 32,
            "source_validation": "exact-rebuild-from-accepted-G15-G21-evidence",
            "sources": [{**item, "status": "PASS"} for item in corpus_json["sources"]],
        },
        "process": executed["process"], "schema_version": "openttd-rl-v2-m22-qualification-evidence-1",
        "source": source, "status": "PASS",
        "summary": {
            "accepted_checkpoints": 1, "benchmark_measurements": 6, "final_manifest_accessed": False,
            "native_gates": 7, "parity_batches": 3, "retained_programs": 16, "selection_finalized": True,
        },
        "telemetry": executed["telemetry"],
    }
    report["report_sha256"] = recovery.sha256_bytes(recovery.canonical_bytes(report))
    import validate_m22_qualification_evidence as validator
    validator.validate_value(report, root, training_artifact_root, artifact_root, executable, corpus)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with evidence_path.open("xb") as output:
        output.write(recovery.canonical_bytes(report) + b"\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--executable", type=pathlib.Path, required=True)
    parser.add_argument("--corpus", type=pathlib.Path, required=True)
    parser.add_argument("--training-artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--evidence", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.root, args.executable, args.corpus, args.training_artifact_root,
                     args.artifact_root, args.evidence)
    except (M22QualificationError, training.M22TrainingError, recovery.M22RecoveryError,
            OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_QUALIFICATION=FAIL {exc}", file=sys.stderr)
        return 1
    selected = report["finalized_selection"]
    print(f"V2_M22_QUALIFICATION=PASS checkpoint={selected['checkpoint_id']} "
          f"parity={report['summary']['parity_batches']} benchmarks={report['summary']['benchmark_measurements']} "
          f"native_programs={report['summary']['retained_programs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
