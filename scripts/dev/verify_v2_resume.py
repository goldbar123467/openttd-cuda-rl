#!/usr/bin/env python3
"""Sequential full/prefix/resume comparison through real V2 native games."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from guide_v2 import GUIDANCES
from local import ROOT, capture_source, source_identity, write_json


def comparison_row(row, storage_root):
    selected = {key: row[key] for key in ("step", "episode", "reset", "prediction", "candidate", "transition",
        "training_reward", "guidance", "bootstrap", "continuation", "feedback")}
    if selected["guidance"] is not None:
        # Storage roots necessarily differ. Preserve the complete relative
        # snapshot path, mask hash, allowed keys and guide state.
        guide = dict(selected["guidance"])
        guide["sampling_binary"] = str(Path(guide["sampling_binary"]).relative_to(storage_root))
        selected["guidance"] = guide
    return selected


def compare_completed(root):
    runs = {name: json.loads((root / name / "run.json").read_text()) for name in ("uninterrupted", "prefix", "resumed")}
    full, prefix, resumed = [runs[name] for name in ("uninterrupted", "prefix", "resumed")]
    rollout = full["rollout_steps"]
    if rollout not in (32, 64, 128) or full["episode_horizon"] != 128:
        raise ValueError("V2 comparison requires 32/64/128-step rollouts and 128-decision episodes")
    prefix_updates = 128 // rollout
    settings = ("device", "run_seed", "rollout_steps", "environments", "sequence_length", "optimization_epochs",
                "episode_horizon", "training_map_seeds", "reward_schema", "observation_schema_id", "guidance",
                "trainer_sha256", "engine_sha256", "native_checkpoint_runtime")
    for name, record in runs.items():
        if record["status"] != "completed" or any(record[key] != full[key] for key in settings):
            raise ValueError("V2 comparison requires complete runs with identical configuration")
        if record.get("reuse_bootstrap_tensors", False) != full.get("reuse_bootstrap_tensors", False):
            raise ValueError("V2 comparison requires identical tensor reuse configuration")
        for key, default in (("gamma", .99), ("gae_lambda", .95)):
            if record.get(key, default) != full.get(key, default):
                raise ValueError("V2 comparison requires identical return configuration")
        if record["requested_updates"] != prefix_updates * (2 if name == "uninterrupted" else 1):
            raise ValueError("V2 comparison requires 256 uninterrupted versus 128 plus 128 decisions")
    if Path(resumed["resume_from"]).resolve() != (root / f"prefix/checkpoints/update-{prefix_updates:06d}").resolve():
        raise ValueError("V2 resumed run restored another checkpoint")
    def metrics(run):
        return [{k: v for k, v in update.items() if k != "elapsed_ns"} for update in run["updates"]]
    if metrics(full)[:prefix_updates] != metrics(prefix) or metrics(full)[prefix_updates:] != metrics(resumed):
        raise ValueError("V2 continued PPO metrics differ")
    if full["model"]["sha256"] != resumed["model"]["sha256"]:
        raise ValueError("Final native inference archives differ; inspect parameter equivalence before any exactness claim")
    expected = root / "uninterrupted/episode-000001/transitions.jsonl"
    actual = root / "resumed/episode-000001/transitions.jsonl"
    if expected.read_bytes() != actual.read_bytes() or len(actual.read_bytes().splitlines()) != 128:
        raise ValueError("V2 continued native game/economic trace differs")
    def choices(path):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        return [comparison_row(row, path.parent) for row in rows]
    full_choices = choices(root / "uninterrupted/trajectory.jsonl")
    if full_choices[:128] != choices(root / "prefix/trajectory.jsonl"):
        raise ValueError("V2 prefix actor or on-policy metadata differs")
    if full_choices[128:] != choices(root / "resumed/trajectory.jsonl"):
        raise ValueError("V2 continued actor, guide, value or on-policy metadata differs")
    return {"exact_update_metrics": True, "exact_actor_and_feedback": True,
        "exact_native_trace_sha256": hashlib.sha256(actual.read_bytes()).hexdigest(),
        "continuation_transitions": 128, "identical_inference_weights_sha256": full["model"]["sha256"],
        "restored_update": resumed["restored_update"], "restored_transitions": resumed["restored_transitions"],
        "comparison_path_rule": "Only each run's absolute storage root is normalized; relative paths and every guide/mask field remain compared"}


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    capture_source(root / "source")
    report = {"kind": "v2-native-reset-resume-verification", "status": "running", "source": source_identity(),
              "device": args.device, "guidance": args.guidance, "seed": args.seed, "rollout_steps": args.rollout_length,
              "training_map_count": args.training_map_count, "gae_lambda": args.gae_lambda,
              "reuse_bootstrap_tensors": args.reuse_bootstrap_tensors,
              "claim": "Exact same-host continuation at a native episode reset, not arbitrary mid-game recovery or gameplay strength",
              "trainer_sha256": hashlib.sha256(args.trainer.read_bytes()).hexdigest(),
              "engine_sha256": hashlib.sha256(args.openttd.read_bytes()).hexdigest()}
    write_json(root / "verification.json", report)
    prefix_updates = 128 // args.rollout_length
    def train(name, updates, resume=None):
        command = [sys.executable, str(ROOT / "scripts/dev/train_v2.py"), "--openttd", str(args.openttd.resolve()),
                   "--trainer", str(args.trainer.resolve()), "--device", args.device, "--seed", str(args.seed),
                   "--updates", str(updates), "--episode-horizon", "128", "--guidance", args.guidance,
                   "--training-map-count", str(args.training_map_count),
                   "--checkpoint-interval", str(prefix_updates), "--output", str(root / name)]
        if args.rollout_length != 32:
            command.extend(["--rollout-length", str(args.rollout_length)])
        if args.gae_lambda != .95:
            command.extend(["--gae-lambda", str(args.gae_lambda)])
        if args.reuse_bootstrap_tensors:
            command.append("--reuse-bootstrap-tensors")
        if resume is not None:
            command.extend(["--resume", str(resume)])
        with (root / (name + ".log")).open("x") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(json.dumps({"stage": name, "device": args.device, "status": "completed"}), flush=True)
        return json.loads((root / name / "run.json").read_text())
    try:
        if args.existing is None:
            train("uninterrupted", 2 * prefix_updates)
            train("prefix", prefix_updates)
            train("resumed", prefix_updates, root / f"prefix/checkpoints/update-{prefix_updates:06d}")
            compared = root
        else:
            compared = args.existing.resolve()
            original = json.loads((compared / "verification.json").read_text())
            if original.get("rollout_steps", 32) != args.rollout_length:
                raise ValueError("Existing verification uses another rollout length")
            if original.get("gae_lambda", .95) != args.gae_lambda:
                raise ValueError("Existing verification uses another GAE trace weight")
            if original.get("training_map_count", 4) != args.training_map_count:
                raise ValueError("Existing verification uses another training map count")
            if original.get("reuse_bootstrap_tensors", False) != args.reuse_bootstrap_tensors:
                raise ValueError("Existing verification uses another tensor reuse mode")
            for key in ("device", "guidance", "seed", "trainer_sha256", "engine_sha256"):
                if original[key] != report[key]:
                    raise ValueError("Existing verification differs from requested native configuration")
            report["existing_run_root"] = str(compared)
            report["original_verification_sha256"] = hashlib.sha256((compared / "verification.json").read_bytes()).hexdigest()
        report.update(status="passed", **compare_completed(compared))
    except BaseException as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(root / "verification.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("trainer", "openttd", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    parser.add_argument("--guidance", choices=("none", *GUIDANCES), default="none")
    parser.add_argument("--seed", type=int, default=20260923)
    parser.add_argument("--rollout-length", type=int, choices=(32, 64, 128), default=32)
    parser.add_argument("--gae-lambda", type=float, default=.95)
    parser.add_argument("--training-map-count", type=int, default=4)
    parser.add_argument("--reuse-bootstrap-tensors", action="store_true")
    parser.add_argument("--existing", type=Path, help="Audit already completed full/prefix/resumed runs into a fresh output directory")
    run(parser.parse_args())
