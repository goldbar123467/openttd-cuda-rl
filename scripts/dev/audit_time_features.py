#!/usr/bin/env python3
"""Audit V1 time-feature coverage without replaying or modifying retained games."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from local import ROOT, source_identity, write_json

ENCODER = ROOT / "integration/openttd/patches/15.3/m04/0005-versioned-policy-observation.patch"


def clock_features(decisions, ticks):
    if decisions < 0 or ticks < 0:
        raise ValueError("Negative episode clock")
    return [min(decisions, 512) / 512, max(512 - decisions, 0) / 512,
            min(ticks, 65536) / 65536, max(65536 - ticks, 0) / 65536]


def training_features(rows):
    """Reconstruct pre-action features from post-step snapshots and pinned ticks."""
    if not rows:
        raise ValueError("Empty training episode")
    values = []
    initial_tick = rows[0]["snapshot"]["tick"] - 128
    for i, row in enumerate(rows):
        snapshot = row["snapshot"]
        if (row["step"] != i + 1 or snapshot["transition_ordinal"] != i + 1 or
                snapshot["tick"] != initial_tick + (i + 1) * 128 or snapshot["scenario"]["split"] != "training"):
            raise ValueError("Training snapshot clock or split differs from the reconstruction contract")
        values.append(clock_features(i, i * 128))
    return values


def summary(values):
    if not values:
        raise ValueError("No feature evidence")
    result = {}
    for offset in range(4):
        column = [row[offset] for row in values]
        counts = [0] * 8
        for value in column:
            if not 0 <= value <= 1:
                raise ValueError("Invalid normalized time feature")
            counts[min(int(value * 8), 7)] += 1
        result[str(offset + 16)] = {"min": min(column), "max": max(column), "count": len(column),
                                  "histogram": counts, "bin_edges": [i / 8 for i in range(9)]}
    return result


def read_rows(path, inputs):
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        rows = [json.loads(line) for line in stream]
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise ValueError("Input changed during audit")
    inputs[str(path)] = before
    return rows


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "source": source_identity(), "inputs_sha256": {}, "training": [], "evaluation": [],
              "claim": "Training inputs are reconstructed from native clocks, not directly logged observations; evaluation inputs are observed",
              "reconstruction": "M04 features 16-19, 512-action/65536-tick divisors; verify 128 ticks and consecutive ordinals per training step"}
    inputs = report["inputs_sha256"]
    inputs[str(ENCODER)] = hashlib.sha256(ENCODER.read_bytes()).hexdigest()
    training_values = []
    try:
        for root in args.training_runs:
            root = root.resolve()
            manifest = root / "run.json"
            record = json.loads(manifest.read_text())
            inputs[str(manifest)] = hashlib.sha256(manifest.read_bytes()).hexdigest()
            if record["status"] != "completed":
                raise ValueError("Use a completed training run")
            paths = sorted((root / "episode-metrics").glob("*.jsonl*"))
            values, unused_resets = [], []
            for path in paths:
                rows = read_rows(path, inputs)
                if not rows:
                    # The historical collector opens the next reset immediately
                    # after its last transition. It records that unused episode.
                    summary_path = path.with_name(path.name.split(".jsonl")[0] + ".json")
                    episode = json.loads(summary_path.read_text())
                    inputs[str(summary_path)] = hashlib.sha256(summary_path.read_bytes()).hexdigest()
                    if episode["status"] != "partial" or episode["actions"] != 0:
                        raise ValueError("Empty training trace is not a declared unused reset")
                    unused_resets.append(str(path))
                    continue
                values.extend(training_features(rows))
            report["training"].append({"root": str(root), "episodes": len(paths),
                                       "unused_reset_episodes": unused_resets,
                                       "horizon": record["episode_action_horizon"], "features": summary(values)})
            training_values.extend(values)
        ranges = summary(training_values)
        for root in args.evaluations:
            root = root.resolve()
            manifest = root / "run.json"
            record = json.loads(manifest.read_text())
            inputs[str(manifest)] = hashlib.sha256(manifest.read_bytes()).hexdigest()
            if record["status"] != "completed" or record["split"] != "development":
                raise ValueError("Only completed development evaluations may enter this audit")
            paths = sorted(root.rglob("actions.jsonl*"))
            values = []
            for path in paths:
                rows = read_rows(path, inputs)
                for i, row in enumerate(rows):
                    features = row["structured_before"][16:20]
                    if row["step"] != i + 1 or features != clock_features(i, i * 128):
                        raise ValueError("Observed evaluation time features disagree with the pinned reconstruction")
                    values.append(features)
            counts = {str(k + 16): sum(not ranges[str(k + 16)]["min"] <= row[k] <= ranges[str(k + 16)]["max"]
                                      for row in values) for k in range(4)}
            report["evaluation"].append({"root": str(root), "episodes": len(paths), "features": summary(values),
                                         "outside_observed_training_clock_range": counts})
        report["status"] = "passed"
    except BaseException as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(args.output / "audit.json", report)
    print(json.dumps({"status": report["status"], "training_runs": len(report["training"]),
                      "development_evaluations": len(report["evaluation"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-runs", nargs="+", type=Path, required=True)
    parser.add_argument("--evaluations", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
