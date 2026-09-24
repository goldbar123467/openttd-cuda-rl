#!/usr/bin/env python3
"""Compare uninterrupted and resumed native PPO on real training games."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from local import ROOT, capture_source, source_identity, write_json


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    capture_source(root / "source")
    prefix_updates = 128 // args.rollout_length
    checkpoint = root / f"prefix/checkpoints/update-{prefix_updates:06d}"
    record = {"kind": "live-reset-resume-differential", "status": "running", "source": source_identity(),
              "device": args.device, "seed": args.seed, "episode_horizon": 128,
              "rollout_length": args.rollout_length, "training_reward": args.training_reward,
              "gae_lambda": args.gae_lambda, "entropy_coefficient": args.entropy_coefficient,
              "workers": args.workers, "credit_trace": args.credit_trace,
              "spatial_validation": args.spatial_validation,
              "claim": "exact same-host recovery at synchronized native training resets; not gameplay strength"}
    for name in ("trainer", "openttd"):
        record[name + "_sha256"] = hashlib.sha256(getattr(args, name).read_bytes()).hexdigest()
    write_json(root / "verification.json", record)

    def train(name, updates, resume=None):
        command = [sys.executable, str(ROOT / "scripts/dev/train_live.py"), "--trainer", str(args.trainer.resolve()),
                   "--openttd", str(args.openttd.resolve()), "--instance-dir", str(args.instance_dir.resolve()),
                   "--output", str(root / name), "--device", args.device, "--seed", str(args.seed),
                   "--updates", str(updates), "--episode-horizon", "128", "--evaluation-steps", "1",
                   "--bridge-validation", "fast", "--checkpoint-interval", str(prefix_updates),
                   "--rollout-length", str(args.rollout_length), "--training-reward", args.training_reward,
                   "--spatial-validation", args.spatial_validation,
                   "--gae-lambda", str(args.gae_lambda), "--entropy-coefficient", str(args.entropy_coefficient)]
        if args.credit_trace:
            command += ["--credit-trace"]
        if resume:
            command += ["--resume", str(resume)]
        with (root / f"{name}.log").open("x") as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        return json.loads((root / name / "run.json").read_text())

    try:
        if args.workers == 1:
            full = train("uninterrupted", prefix_updates * 2)
            prefix = train("prefix", prefix_updates)
            resumed = train("resumed", prefix_updates, checkpoint)
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                full_future = executor.submit(train, "uninterrupted", prefix_updates * 2)
                prefix_future = executor.submit(train, "prefix", prefix_updates)
                prefix = prefix_future.result()
                resumed = train("resumed", prefix_updates, checkpoint)
                full = full_future.result()
        if full["training"]["updates"][:prefix_updates] != prefix["training"]["updates"]:
            raise ValueError("Independent uninterrupted/prefix training metrics differ")
        if full["training"]["updates"][prefix_updates:] != resumed["training"]["updates"]:
            raise ValueError("Resumed PPO metrics differ from uninterrupted continuation")
        if full["model"]["id"] != resumed["model"]["id"]:
            raise ValueError("Exported final model identities differ")
        if args.credit_trace:
            def credit(name):
                return [json.loads(line) for line in (root / name / "credit-trace.jsonl").read_text().splitlines()]
            if credit("uninterrupted") != credit("prefix") + credit("resumed"):
                raise ValueError("Accepted scalar PPO inputs differ across recovery")
        traces = []
        for environment_id in range(4):
            name = f"m07-train-e{environment_id}-p1.jsonl"
            expected = (root / "uninterrupted/episode-metrics" / name).read_bytes()
            actual = (root / "resumed/episode-metrics" / name).read_bytes()
            if not expected or expected != actual:
                raise ValueError(f"Resumed live action/economic trace differs: {name}")
            traces.append({"name": name, "sha256": hashlib.sha256(actual).hexdigest(), "transitions": len(actual.splitlines())})
        record.update(status="passed", exact_metrics=True, exact_native_traces=traces,
                      identical_model_id=full["model"]["id"], additional_updates=prefix_updates,
                      exact_scalar_ppo_inputs=True if args.credit_trace else None,
                      checkpoint=str(checkpoint))
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(root / "verification.json", record)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trainer", type=Path, required=True)
    parser.add_argument("--openttd", type=Path, required=True)
    parser.add_argument("--instance-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    parser.add_argument("--seed", type=int, default=20260926)
    parser.add_argument("--rollout-length", type=int, choices=(32, 64), default=32)
    parser.add_argument("--training-reward", choices=("native", "universal-decision-cost", "service-potential", "economic", "balanced-economic"), default="native")
    parser.add_argument("--gae-lambda", type=float, default=.95)
    parser.add_argument("--entropy-coefficient", type=float, default=.01)
    parser.add_argument("--credit-trace", action="store_true")
    parser.add_argument("--spatial-validation", choices=("reference", "vectorized"), default="reference")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=1,
                        help="Concurrent training jobs; one leaves a slot available for another experiment")
    run(parser.parse_args())
