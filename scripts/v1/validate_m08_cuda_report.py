#!/usr/bin/env python3
"""Fail-closed validation of the M08 full CPU/CUDA parity and benchmark report."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from typing import Any

import jsonschema

import validate_m07_ppo_contract


class M08CudaReportError(ValueError):
    """The M08 CUDA report does not close its frozen acceptance contract."""


ARCHITECTURES = ["structured-mlp-v1", "spatial-cnn-v1", "combined-cnn-mlp-v1"]
BATCHES = [1, 4, 16, 64, 256, 1024]
WORKLOADS = ["forward-backward-adam-update", "batched-inference"]


def close(actual: float, expected: float, *, relative: float = 1e-9) -> bool:
    return math.isclose(actual, expected, rel_tol=relative, abs_tol=1e-12)


def validate(report_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    report = validate_m07_ppo_contract.load_strict_json(report_path)
    schema = validate_m07_ppo_contract.load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(report)
    if report["mode"] != "contract-full":
        raise M08CudaReportError("diagnostic quick output cannot pass G08")
    if [item["architecture"] for item in report["parity"]] != ARCHITECTURES:
        raise M08CudaReportError("CPU/CUDA parity architecture order or coverage drifted")
    for item in report["parity"]:
        if item["forward_absolute"] > 1e-4 or not item["forward_allclose"]:
            raise M08CudaReportError(f"{item['architecture']} forward parity failed")
        if item["loss_absolute"] > 1e-5:
            raise M08CudaReportError(f"{item['architecture']} PPO loss parity failed")
        if item["gradient_absolute"] > 5e-4:
            raise M08CudaReportError(f"{item['architecture']} gradient parity failed")
        if item["updated_parameter_absolute"] > 5e-4:
            raise M08CudaReportError(f"{item['architecture']} optimizer-update parity failed")
        if item["checkpoint_absolute"] > 1e-4:
            raise M08CudaReportError(f"{item['architecture']} device/checkpoint parity failed")
    if [item["workload"] for item in report["benchmarks"]] != WORKLOADS:
        raise M08CudaReportError("benchmark workload order or coverage drifted")
    for workload in report["benchmarks"]:
        if workload["warmup_iterations"] != 20 or workload["measurement_iterations"] != 100:
            raise M08CudaReportError("full benchmark iteration budget drifted")
        if [item["batch_size"] for item in workload["batches"]] != BATCHES:
            raise M08CudaReportError("full benchmark batch coverage drifted")
        for item in workload["batches"]:
            expected_speedup = item["cpu"]["median_ns"] / item["cuda"]["median_ns"]
            if not close(item["speedup"], expected_speedup):
                raise M08CudaReportError("reported speedup does not derive from median timings")
            for device in ("cpu", "cuda"):
                expected_throughput = item["batch_size"] * 1e9 / item[device]["median_ns"]
                if not close(item[device]["samples_per_second"], expected_throughput):
                    raise M08CudaReportError("reported throughput does not derive from batch and median")
                if item[device]["p95_ns"] < item[device]["median_ns"]:
                    raise M08CudaReportError("p95 latency is below median latency")
        batch_64 = next(item for item in workload["batches"] if item["batch_size"] == 64)
        if batch_64["speedup"] < workload["minimum_accepted_speedup"]:
            raise M08CudaReportError(f"{workload['workload']} lacks robust CUDA benefit at batch 64")
    capability = tuple(int(part) for part in report["device"]["compute_capability"].split("."))
    if capability < (12, 0):
        raise M08CudaReportError("measured CUDA device is below the frozen capability floor")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=pathlib.Path)
    parser.add_argument("schema", type=pathlib.Path)
    args = parser.parse_args()
    try:
        report = validate(args.report, args.schema)
    except (M08CudaReportError, OSError, ValueError, jsonschema.ValidationError) as exc:
        print(f"M08_CUDA_REPORT=FAIL {exc}", file=sys.stderr)
        return 1
    speedups = {
        workload["workload"]: next(item["speedup"] for item in workload["batches"] if item["batch_size"] == 64)
        for workload in report["benchmarks"]
    }
    print(
        "M08_CUDA_REPORT=PASS "
        f"device={json.dumps(report['device']['name'])} "
        f"update_speedup_batch64={speedups['forward-backward-adam-update']:.6f} "
        f"inference_speedup_batch64={speedups['batched-inference']:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
