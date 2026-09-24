#!/usr/bin/env python3
"""Compare bounded CPU/CUDA V2 PPO runs, including their actual native traces."""
import argparse
import hashlib
import json
from pathlib import Path

from local import write_json


def read_run(path):
    record = json.loads((path / "run.json").read_text())
    if record["status"] != "completed" or record["kind"] != "native-v2-live-recurrent-ppo":
        raise ValueError("Comparison requires completed live V2 PPO runs")
    rows = [json.loads(line) for line in (path / "trajectory.jsonl").read_text().splitlines()]
    if record["rollout_steps"] not in (32, 64) or len(rows) != record["requested_updates"] * record["rollout_steps"]:
        raise ValueError("Incomplete rollout history")
    for index, row in enumerate(rows):
        t = row["transition"]
        if row["step"] != index + 1 or t["tick_after"] - t["tick_before"] != 128:
            raise ValueError("Transition sequence or simulation-time budget differs")
        if t["action"]["status"] not in ("SUCCESS", "NO_OP"):
            raise ValueError("Live training action failed")
        if row["bootstrap"] != (not t["terminal"]) or row["continuation"] != (not (t["terminal"] or t["truncated"])):
            raise ValueError("Terminal/time-limit GAE masks differ from native semantics")
        if row["reset"] != (index == 0 or not rows[index - 1]["continuation"]):
            raise ValueError("Recurrent state reset does not follow native episode boundary")
    return record, rows


def run(args):
    cpu, a = read_run(args.cpu)
    gpu, b = read_run(args.cuda)
    if cpu["device"] != "cpu" or gpu["device"] != "cuda:0":
        raise ValueError("Expected explicit CPU and CUDA runs")
    for key in ("run_seed", "requested_updates", "episode_horizon", "training_map_seeds", "reward_schema",
                "trainer_sha256", "engine_sha256", "rollout_steps", "sequence_length", "optimization_epochs"):
        if cpu[key] != gpu[key]:
            raise ValueError(f"Training comparison configuration differs: {key}")
    if cpu.get("observation_schema_id") != gpu.get("observation_schema_id"):
        raise ValueError("Public observation schemas differ")
    if cpu.get("guidance", "none") != gpu.get("guidance", "none"):
        raise ValueError("Planner curriculum configurations differ")
    errors = {"log_probability": 0.0, "value": 0.0, "next_value": 0.0, "update_metric": 0.0}
    for left, right in zip(a, b, strict=True):
        for key in ("step", "episode", "reset", "candidate", "transition", "training_reward", "bootstrap", "continuation"):
            if left[key] != right[key]:
                raise ValueError(f"CPU/CUDA game history differs at step {left['step']}: {key}")
        if left["prediction"]["row"] != right["prediction"]["row"]:
            raise ValueError("Sampled candidate row differs")
        for key in ("sampling_binary_sha256", "native_binary_sha256", "stage", "proposed_key", "allowed_keys"):
            if (left.get("guidance") or {}).get(key) != (right.get("guidance") or {}).get(key):
                raise ValueError("CPU/CUDA planner masks or progression differ")
        for key in ("log_probability", "value"):
            errors[key] = max(errors[key], abs(left["prediction"][key] - right["prediction"][key]))
        errors["next_value"] = max(errors["next_value"], abs(left["feedback"]["next_value"] - right["feedback"]["next_value"]))
    for left, right in zip(cpu["updates"], gpu["updates"], strict=True):
        for key in ("policy_loss", "value_loss", "entropy", "approximate_kl", "gradient_norm", "explained_variance"):
            errors["update_metric"] = max(errors["update_metric"], abs(left[key] - right[key]))
        if max(left["behavior_replay_max_error"], right["behavior_replay_max_error"]) > 1e-4:
            raise ValueError("Behavior replay exceeded its pre-optimization tolerance")
    if max(errors.values()) > 1e-4:
        raise ValueError(f"CPU/CUDA absolute numeric tolerance 1e-4 exceeded: {errors}")
    normalized = json.dumps([row["transition"] for row in a], sort_keys=True, separators=(",", ":")).encode()
    report = {"status": "passed", "inputs": [str(args.cpu.resolve()), str(args.cuda.resolve())],
              "native_transitions_identical": len(a), "native_trace_sha256": hashlib.sha256(normalized).hexdigest(),
              "max_abs_errors": errors, "numeric_atol": 1e-4,
              "time_limit_bootstraps": sum(row["transition"]["truncated"] for row in a),
              "recurrent_resets": sum(row["reset"] for row in a),
              "claim": "Bounded live PPO correctness; not playing competence, generalization or a performance benchmark"}
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "comparison.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cpu", "cuda", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    run(parser.parse_args())
