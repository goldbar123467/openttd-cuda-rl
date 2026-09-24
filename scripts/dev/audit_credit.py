#!/usr/bin/env python3
"""Offline scalar GAE audit; never supplies advantages or updates to training."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct

from local import ROOT, write_json


def reconstruct(rows, environments, gamma, trace_weight):
    if len(rows) % environments:
        raise ValueError("Credit trace layout is incomplete")
    accumulators = [0.0] * environments
    advantages = [0.0] * len(rows)
    for index in reversed(range(len(rows))):
        row = rows[index]
        environment = index % environments
        delta = row["reward"] + gamma * row["bootstrap"] * row["next_value"] - row["old_value"]
        accumulators[environment] = delta + gamma * trace_weight * row["continuation"] * accumulators[environment]
        advantages[index] = accumulators[environment]
    mean = statistics.mean(advantages)
    scale = math.sqrt(statistics.pvariance(advantages) + 1e-8)
    normalized = [(value - mean) / scale for value in advantages]
    returns = [value + row["old_value"] for value, row in zip(advantages, rows, strict=True)]
    return advantages, normalized, returns


def run(args):
    root = args.training_run.resolve()
    config = json.loads((root / "run.json").read_text())
    if config["status"] != "completed" or not config.get("credit_trace") or config.get("resume_from"):
        raise ValueError("Credit audit requires complete, unresumed training with scalar traces")
    source = root / "credit-trace.jsonl"
    updates = [json.loads(line) for line in source.read_text().splitlines()]
    if len(updates) != config["requested_updates"]:
        raise ValueError("Credit trace does not cover all accepted updates")
    families = json.loads((ROOT / "config/v1/m05-action-contract.json").read_text())["families"]
    action_names = {index: family["name"] for family in families for index in range(family["index_start"], family["index_end"] + 1)}
    grouped = {}
    maximum_error = 0.0
    for update, native in zip(updates, config["training"]["updates"], strict=True):
        if (update["update"] != native["update"] or update["samples"] != native["samples"] or
                update["rollout_length"] != config["rollout_length"] or update["environments"] != config["environments"] or
                len(update["transitions"]) != config["rollout_length"] * config["environments"] or
                update["layout"] != "time-major-environment-minor"):
            raise ValueError("Credit trace identity or layout differs from accepted native metrics")
        rows = update["transitions"]
        raw, normalized, targets = reconstruct(rows, config["environments"], .99, config.get("gae_lambda", .95))
        # The native service converts GAE returns to float32 before PPO and its
        # explained-variance audit. Match that conversion before comparing.
        targets = [struct.unpack("<f", struct.pack("<f", value))[0] for value in targets]
        variance = statistics.pvariance(targets)
        residual = [target - row["old_value"] for target, row in zip(targets, rows, strict=True)]
        explained = 1 - statistics.pvariance(residual) / variance if variance > 1e-16 else 0.0
        error = abs(explained - native["explained_variance"])
        maximum_error = max(maximum_error, error)
        if error > 1e-6:
            raise ValueError("Offline GAE does not reproduce native value-target diagnostics")
        for index, row in enumerate(rows):
            # Equal update ranges, not selected after seeing outcomes.
            quarter = min(4, 1 + (update["update"] - 1) * 4 // len(updates))
            key = (quarter, action_names[row["action"]])
            grouped.setdefault(key, []).append((row["reward"], raw[index], normalized[index]))
    summary = [{"training_quarter": quarter, "action_family": family, "count": len(values),
                "mean_reward": statistics.mean(v[0] for v in values),
                "mean_raw_advantage": statistics.mean(v[1] for v in values),
                "mean_normalized_advantage": statistics.mean(v[2] for v in values),
                "positive_normalized_fraction": statistics.mean(v[2] > 0 for v in values)}
               for (quarter, family), values in sorted(grouped.items())]
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "audit.json", {"training_run": str(root), "gae_lambda": config.get("gae_lambda", .95),
        "claim": "Descriptive credit on the collected behavior trajectories, not a causal effect or held-out evaluation",
        "inputs": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / "run.json", source)},
        "accepted_updates": len(updates), "maximum_native_explained_variance_error": maximum_error, "by_quarter_and_action": summary})
    print(json.dumps({"updates": len(updates), "maximum_native_explained_variance_error": maximum_error}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
