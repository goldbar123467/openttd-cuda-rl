#!/usr/bin/env python3
"""Read-only reward, forced-choice, and scalar credit audit of retained V2 runs."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct

from local import source_identity, write_json


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def credit(rows, gamma, trace_weight):
    """Independent scalar recurrence; match the native float32 input boundary."""
    advantages = [0.] * len(rows)
    accumulator = 0.
    for index in reversed(range(len(rows))):
        row = rows[index]
        delta = (f32(row["training_reward"]["reward"]) + gamma * row["bootstrap"] *
                 f32(row["feedback"]["next_value"]) - f32(row["prediction"]["value"]))
        accumulator = delta + gamma * trace_weight * row["continuation"] * accumulator
        advantages[index] = accumulator
    targets = [f32(a + f32(row["prediction"]["value"])) for a, row in zip(advantages, rows, strict=True)]
    residuals = [target - f32(row["prediction"]["value"]) for target, row in zip(targets, rows, strict=True)]
    variance = statistics.pvariance(targets)
    explained = 0. if variance == 0 else 1 - statistics.pvariance(residuals) / variance
    return advantages, explained


def describe(values):
    return {"count": len(values), "mean": statistics.mean(values),
            "population_std": statistics.pstdev(values), "min": min(values), "max": max(values)} if values else None


def audit_rows(record, rows):
    if record["kind"] != "native-v2-live-recurrent-ppo" or record["reward_schema"] != "development-v2-live-reward-1":
        raise ValueError("Audit requires the explicitly supported historical V2 reward schema")
    rollout = record["rollout_steps"]
    if not rows or len(rows) != len(record["updates"]) * rollout:
        raise ValueError("Trajectory does not cover exactly the recorded completed updates")
    offset = record.get("restored_transitions", 0)
    clips = {name: Counter() for name in ("delivery", "operating_profit", "capital")}
    terminals, updates = [], []
    grouped = defaultdict(list)
    choice_count = forced_count = missing_choice_count = 0
    maximum_error = 0.
    for index, row in enumerate(rows):
        if row["step"] != offset + index + 1:
            raise ValueError("Nonconsecutive training steps")
        t = row["transition"]
        if row["bootstrap"] != (not t["terminal"]) or row["continuation"] != (not (t["terminal"] or t["truncated"])):
            raise ValueError("Recorded return boundaries disagree with native transition")
        before, after = t["before"], t["after"]
        delivery = after.get("delivered_passengers", before["delivered_passengers"]) - before["delivered_passengers"]
        profit = after.get("operating_profit", before["operating_profit"]) - before["operating_profit"]
        capital = 0
        if t["action"]["family"] in ("BUILD_ROAD_PATH", "BUILD_BUS_STOP", "BUILD_ROAD_DEPOT", "BUY_BUS"):
            capital = sum(max(0, c["cost"]) for c in t["action"]["native_commands"]
                          if c["phase"] == "EXECUTE" and c["status"] == "SUCCESS")
        expected = {"delivery": min(max(delivery, 0), 64) / 64,
                    "operating_profit": min(max(profit, -256), 256) / 256,
                    "capital": -min(capital, 4096) / 4096,
                    "decision": -1 / 64, "bankruptcy": -5. if t["terminal"] else 0.}
        logged = row["training_reward"]
        if (logged["schema_version"] != record["reward_schema"] or logged["components"] != expected or
                logged["reward"] != sum(expected.values()) or
                (logged["raw_passengers"], logged["raw_operating_profit"], logged["raw_capital"]) != (delivery, profit, capital)):
            raise ValueError(f"Reward accounting disagrees with native trace at step {row['step']}")
        for name, value, low, high in (("delivery", delivery, 0, 64),
                                      ("operating_profit", profit, -256, 256), ("capital", capital, 0, 4096)):
            clips[name]["rows"] += 1
            clips[name]["upper_bound_reached"] += value >= high
            clips[name]["upper_clipped"] += value > high
            clips[name]["lower_clipped"] += value < low
            clips[name]["magnitude_removed"] += max(value - high, low - value, 0)
        if t["terminal"]:
            terminals.append({"step": row["step"], "episode": row["episode"],
                              "reported_reason": t.get("terminal_reason", t.get("reason", "not-recorded")),
                              "alive_after": after.get("alive"), "charged_terminal_penalty": expected["bankruptcy"]})
        count = (row.get("guidance") or {}).get("sampling_legal_count")
        if count is None:
            missing_choice_count += 1
        elif type(count) is not int or count < 1:
            raise ValueError("Invalid recorded sampling legal count")
        else:
            choice_count += count >= 2
            forced_count += count == 1
    for index, native in enumerate(record["updates"]):
        segment = rows[index * rollout:(index + 1) * rollout]
        if native["transitions"] != segment[-1]["step"]:
            raise ValueError("Update counters do not match trajectory")
        advantages, explained = credit(segment, record.get("gamma", .99), record.get("gae_lambda", .95))
        error = abs(explained - native["explained_variance"])
        if not math.isfinite(error) or error > 1e-5:
            raise ValueError(f"Scalar GAE explained variance differs at update {native['update']}: {error}")
        maximum_error = max(maximum_error, error)
        choices = []
        for row, advantage in zip(segment, advantages, strict=True):
            count = (row.get("guidance") or {}).get("sampling_legal_count")
            if count is not None and count >= 2:
                choices.append(advantage)
                grouped[row["transition"]["action"]["family"]].append(advantage)
        updates.append({"update": native["update"], "all_advantages": describe(advantages),
                        "choice_advantages": describe(choices), "choice_steps": len(choices),
                        "approximate_kl_all_steps": native["approximate_kl"],
                        "explained_variance_reconstructed": explained})
    return {"source_status": record["status"], "transitions": len(rows), "first_step": rows[0]["step"],
            "clips": clips, "terminals": terminals, "choice_steps": choice_count, "forced_steps": forced_count,
            "choice_count_unavailable_steps": missing_choice_count,
            "choice_fraction": choice_count / len(rows) if not missing_choice_count else None,
            "choice_advantages_by_family": {family: describe(values) for family, values in sorted(grouped.items())},
            "approximate_kl_all_steps": describe([u["approximate_kl"] for u in record["updates"]]),
            "choice_kl_available": False, "updates": updates,
            "maximum_explained_variance_error": maximum_error,
            "terminal_reason_limit": "Absent terminal reasons remain unknown; a penalty name does not establish bankruptcy",
            "claim": "Offline accounting/credit reconstruction; no causal claim, new training, or held-out access"}


def audit_run(root):
    run_path = root / "run.json"
    path = root / "trajectory.jsonl"
    if not path.exists():
        path = path.with_suffix(".jsonl.gz")
    inputs = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (run_path, path)}
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        rows = [json.loads(line) for line in stream]
    report = audit_rows(json.loads(run_path.read_text()), rows)
    for name, expected in inputs.items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise ValueError("Audit input changed during reading")
    return {"training_run": str(root), "inputs_sha256": inputs, **report}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-runs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    record = {"status": "running", "source": source_identity(), "runs": []}
    try:
        for root in args.training_runs:
            result = audit_run(root.resolve())
            record["runs"].append(result)
            print(json.dumps({key: result[key] for key in ("training_run", "transitions", "choice_fraction", "maximum_explained_variance_error")}), flush=True)
        record["status"] = "passed"
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(args.output / "audit.json", record)
