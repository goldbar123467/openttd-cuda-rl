#!/usr/bin/env python3
"""Validate paired CPU/CUDA end-to-end learning evidence for all M08 architectures."""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any

import jsonschema

import validate_m07_ppo_contract


class M08ArchitectureSmokeError(ValueError):
    """The paired architecture smoke reports do not close the M08 claim."""


ARCHITECTURES = ["structured-mlp-v1", "spatial-cnn-v1", "combined-cnn-mlp-v1"]


def load_and_validate(path: pathlib.Path, schema: dict[str, Any]) -> dict[str, Any]:
    report = validate_m07_ppo_contract.load_strict_json(path)
    jsonschema.Draft202012Validator(schema).validate(report)
    if [item["architecture"] for item in report["architectures"]] != ARCHITECTURES:
        raise M08ArchitectureSmokeError("architecture order or coverage drifted")
    for item in report["architectures"]:
        if item["final_target_log_probability"] < item["initial_target_log_probability"] + report["objective_delta"]:
            raise M08ArchitectureSmokeError(f"{item['architecture']} did not reach the learning objective")
    return report


def validate(cpu_path: pathlib.Path, cuda_path: pathlib.Path, schema_path: pathlib.Path) -> tuple[dict[str, Any], dict[str, Any]]:
    schema = validate_m07_ppo_contract.load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    cpu = load_and_validate(cpu_path, schema)
    cuda = load_and_validate(cuda_path, schema)
    if cpu["device"] != "cpu" or cuda["device"] != "cuda:0":
        raise M08ArchitectureSmokeError("paired reports do not cover cpu and cuda:0")
    for cpu_item, cuda_item in zip(cpu["architectures"], cuda["architectures"], strict=True):
        if cpu_item["parameter_count"] != cuda_item["parameter_count"]:
            raise M08ArchitectureSmokeError("device move changed parameter count")
        if cpu_item["samples_to_objective"] != cuda_item["samples_to_objective"]:
            raise M08ArchitectureSmokeError("CPU/CUDA sample efficiency changed on the fixed task")
        for field in ("initial_target_log_probability", "final_target_log_probability"):
            if abs(cpu_item[field] - cuda_item[field]) > 1e-4:
                raise M08ArchitectureSmokeError(f"CPU/CUDA {field} drifted beyond tolerance")
    cpu_by_name = {item["architecture"]: item for item in cpu["architectures"]}
    cuda_by_name = {item["architecture"]: item for item in cuda["architectures"]}
    for architecture in ("spatial-cnn-v1", "combined-cnn-mlp-v1"):
        if cuda_by_name[architecture]["elapsed_ns"] >= cpu_by_name[architecture]["elapsed_ns"]:
            raise M08ArchitectureSmokeError(f"{architecture} CUDA trainer smoke was not faster than CPU")
    return cpu, cuda


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpu", type=pathlib.Path, required=True)
    parser.add_argument("--cuda", type=pathlib.Path, required=True)
    parser.add_argument("--schema", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        cpu, cuda = validate(args.cpu, args.cuda, args.schema)
    except (M08ArchitectureSmokeError, OSError, ValueError, jsonschema.ValidationError) as exc:
        print(f"M08_ARCHITECTURE_SMOKE_REPORT=FAIL {exc}", file=sys.stderr)
        return 1
    speedups = {
        cpu_item["architecture"]: cpu_item["elapsed_ns"] / cuda_item["elapsed_ns"]
        for cpu_item, cuda_item in zip(cpu["architectures"], cuda["architectures"], strict=True)
    }
    print(
        "M08_ARCHITECTURE_SMOKE_REPORT=PASS architectures=3 samples_each=256 "
        f"spatial_speedup={speedups['spatial-cnn-v1']:.6f} "
        f"combined_speedup={speedups['combined-cnn-mlp-v1']:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
