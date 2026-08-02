#!/usr/bin/env python3
"""Run the full M08 CUDA gate while recording honest NVIDIA telemetry."""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import threading
import time
from typing import Any


QUERY = "name,uuid,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw"


def canonical_line(value: dict[str, Any]) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parse_sample(text: str, timestamp_ns: int) -> dict[str, Any]:
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    if len(rows) != 1:
        raise ValueError("nvidia-smi returned zero or multiple devices")
    fields = [field.strip() for field in rows[0].split(",")]
    if len(fields) != 7:
        raise ValueError("nvidia-smi telemetry field count drifted")
    name, uuid, utilization, memory_used, memory_total, temperature, power = fields
    return {
        "gpu_available": True,
        "memory_total_mib": int(memory_total),
        "memory_used_mib": int(memory_used),
        "name": name,
        "power_w": float(power),
        "temperature_c": int(temperature),
        "timestamp_ns": timestamp_ns,
        "utilization_percent": int(utilization),
        "uuid": uuid,
    }


def sample_once(nvidia_smi: str) -> dict[str, Any]:
    timestamp_ns = time.time_ns()
    try:
        result = subprocess.run(
            [nvidia_smi, f"--query-gpu={QUERY}", "--format=csv,noheader,nounits"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"nvidia-smi exited {result.returncode}")
        return parse_sample(result.stdout, timestamp_ns)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
        return {
            "detail": str(exc),
            "gpu_available": False,
            "memory_total_mib": None,
            "memory_used_mib": None,
            "name": None,
            "power_w": None,
            "temperature_c": None,
            "timestamp_ns": timestamp_ns,
            "utilization_percent": None,
            "uuid": None,
        }


def monitor(nvidia_smi: str, destination: pathlib.Path, stop: threading.Event) -> None:
    with destination.open("x", encoding="utf-8") as output:
        while True:
            output.write(canonical_line(sample_once(nvidia_smi)) + "\n")
            output.flush()
            if stop.wait(0.2):
                break


def summarize(path: pathlib.Path) -> dict[str, Any]:
    samples = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    available = [sample for sample in samples if sample["gpu_available"]]
    unavailable = len(samples) - len(available)
    if not available:
        return {
            "available_samples": 0,
            "gpu_available": False,
            "sample_count": len(samples),
            "unavailable_samples": unavailable,
        }
    names = {sample["name"] for sample in available}
    uuids = {sample["uuid"] for sample in available}
    if len(names) != 1 or len(uuids) != 1:
        raise ValueError("GPU identity changed during the gate")
    return {
        "available_samples": len(available),
        "gpu_available": True,
        "memory_peak_mib": max(sample["memory_used_mib"] for sample in available),
        "name": available[0]["name"],
        "power_peak_w": max(sample["power_w"] for sample in available),
        "sample_count": len(samples),
        "schema_version": "openttd-rl-v1-m08-gpu-monitor-summary-1",
        "temperature_peak_c": max(sample["temperature_c"] for sample in available),
        "unavailable_samples": unavailable,
        "utilization_mean_percent": sum(sample["utilization_percent"] for sample in available) / len(available),
        "utilization_peak_percent": max(sample["utilization_percent"] for sample in available),
        "uuid": available[0]["uuid"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    if not args.executable.is_absolute() or not args.executable.is_file():
        parser.error("--executable must be an existing absolute file")
    if not args.artifact_root.is_absolute() or args.artifact_root.exists():
        parser.error("--artifact-root must be a new absolute path")
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi is None:
        print("M08_CUDA_RUN=FAIL class=cuda-unavailable detail=nvidia-smi-not-found", file=sys.stderr)
        return 3
    args.artifact_root.mkdir(parents=True)
    telemetry_path = args.artifact_root / "gpu-telemetry.jsonl"
    stop = threading.Event()
    monitor_thread = threading.Thread(target=monitor, args=(nvidia_smi, telemetry_path, stop), daemon=False)
    monitor_thread.start()
    command = [str(args.executable), "--report", str(args.artifact_root / "cuda-report.json")]
    if args.quick:
        command.append("--quick")
    try:
        result = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    finally:
        stop.set()
        monitor_thread.join(timeout=10)
    (args.artifact_root / "stdout.txt").write_bytes(result.stdout)
    (args.artifact_root / "stderr.txt").write_bytes(result.stderr)
    summary = summarize(telemetry_path)
    (args.artifact_root / "gpu-monitor-summary.json").write_text(canonical_line(summary) + "\n", encoding="utf-8")
    if result.returncode != 0:
        sys.stderr.buffer.write(result.stderr)
        print(f"M08_CUDA_RUN=FAIL rc={result.returncode} artifact_root={args.artifact_root}", file=sys.stderr)
        return result.returncode
    if not summary["gpu_available"] or summary["unavailable_samples"] != 0:
        print("M08_CUDA_RUN=FAIL class=telemetry-unavailable", file=sys.stderr)
        return 7
    sys.stdout.buffer.write(result.stdout)
    print(
        "M08_CUDA_RUN=PASS "
        f"samples={summary['sample_count']} peak_utilization={summary['utilization_peak_percent']} "
        f"peak_memory_mib={summary['memory_peak_mib']} artifact_root={args.artifact_root}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
