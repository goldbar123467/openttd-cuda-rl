#!/usr/bin/env python3
"""Validate M07 metric schema, source registry, and native emitted fixture."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import subprocess
import sys
from typing import Any

import jsonschema

import validate_m07_ppo_contract


class M07MetricError(ValueError):
    """The M07 metric surface is incomplete or not source-accurate."""


EXPECTED_FIELDS = {
    "best_development_score", "checkpoint_id", "counters.accepted_samples",
    "counters.completed_episodes", "counters.completed_updates", "counters.environment_steps",
    "counters.simulation_ticks", "elapsed_ns", "environment.company_profit",
    "environment.invalid_actions", "environment.mask_violations", "environment.mean_episode_length",
    "environment.mean_episode_return", "environment.passenger_deliveries", "environment.resets",
    "environment.routes", "environment.vehicles", "run.device", "run.environment_count",
    "run.environment_version", "run.openttd_version", "run.repository_commit", "run.run_name",
    "run.run_seed", "steps_per_second", "system.cpu_utilization_percent", "system.gpu_available",
    "system.gpu_memory_bytes", "system.gpu_utilization_percent", "system.process_memory_bytes",
    "training.approximate_kl", "training.clip_fraction", "training.entropy",
    "training.explained_variance", "training.gradient_norm", "training.learning_rate",
    "training.policy_loss", "training.samples", "training.update", "training.value_loss",
    "warning_state",
}


def load(path: pathlib.Path) -> dict[str, Any]:
    return validate_m07_ppo_contract.load_strict_json(path)


def validate(
    schema_path: pathlib.Path,
    sources_path: pathlib.Path,
    trainer: pathlib.Path | None,
) -> dict[str, Any] | None:
    schema = load(schema_path)
    sources = load(sources_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    if sources.get("schema_version") != "openttd-rl-v1-m07-metric-sources-1":
        raise M07MetricError("metric source registry version drifted")
    if set(sources.get("fields", {})) != EXPECTED_FIELDS:
        missing = EXPECTED_FIELDS - set(sources.get("fields", {}))
        extra = set(sources.get("fields", {})) - EXPECTED_FIELDS
        raise M07MetricError(f"metric source inventory differs missing={sorted(missing)} extra={sorted(extra)}")
    for name, definition in sources["fields"].items():
        if set(definition) != {"source", "unit", "aggregation", "unavailable"}:
            raise M07MetricError(f"metric source definition is incomplete: {name}")
        if definition["unavailable"] not in ("null", "forbidden"):
            raise M07MetricError(f"metric unavailable policy is invalid: {name}")
    if trainer is None:
        return None
    trainer = trainer.resolve()
    if not trainer.is_file():
        raise M07MetricError("trainer executable is missing")
    result = subprocess.run(
        [str(trainer), "--metric-fixture"], check=False, capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0 or result.stderr:
        raise M07MetricError(f"native metric fixture failed rc={result.returncode} stderr={result.stderr!r}")
    try:
        event = json.loads(
            result.stdout,
            object_pairs_hook=lambda pairs: _unique_object(pairs),
            parse_constant=lambda token: (_ for _ in ()).throw(M07MetricError(f"invalid constant {token}")),
        )
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise M07MetricError(f"native metric event is not strict JSON: {exc}") from exc
    jsonschema.Draft202012Validator(schema).validate(event)
    expected_sps = event["counters"]["environment_steps"] * 1_000_000_000 / event["elapsed_ns"]
    if not math.isclose(event["steps_per_second"], expected_sps, rel_tol=0.0, abs_tol=1e-12):
        raise M07MetricError("steps_per_second does not match logged counter/time sources")
    if event["system"]["gpu_available"] or event["system"]["gpu_utilization_percent"] is not None or event["system"]["gpu_memory_bytes"] is not None:
        raise M07MetricError("unavailable GPU telemetry was fabricated")
    if event["training"]["update"] != event["counters"]["completed_updates"] or event["training"]["samples"] != event["counters"]["accepted_samples"]:
        raise M07MetricError("duplicate trainer counters disagree")
    return event


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise M07MetricError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", type=pathlib.Path, required=True)
    parser.add_argument("--sources", type=pathlib.Path, required=True)
    parser.add_argument("--trainer", type=pathlib.Path)
    args = parser.parse_args()
    try:
        event = validate(args.schema, args.sources, args.trainer)
    except (M07MetricError, OSError, jsonschema.ValidationError, subprocess.SubprocessError) as exc:
        print(f"M07_METRICS=FAIL {exc}", file=sys.stderr)
        return 1
    print(f"M07_METRICS=PASS fields={len(EXPECTED_FIELDS)} native_fixture={event is not None}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
