#!/usr/bin/env python3
"""Qualify integrated V2 options against original and retained live trainers."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import compare_v2_training
from local import ROOT, capture_source, host, source_identity, write_json
from verify_v2_resume import comparison_row


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare_exact(reference, candidate):
    """Allow different binaries/source roots, but no changed learning semantics."""
    left, a = compare_v2_training.read_run(reference)
    right, b = compare_v2_training.read_run(candidate)
    keys = ("device", "run_seed", "requested_updates", "episode_horizon", "training_map_seeds",
            "reward_schema", "engine_sha256", "rollout_steps", "sequence_length",
            "optimization_epochs", "observation_schema_id", "guidance")
    for key in keys:
        if left[key] != right[key]:
            raise ValueError(f"Exact comparison configuration differs: {key}")
    for key, default in (("gamma", .99), ("gae_lambda", .95), ("financial_features", "raw"),
                         ("entropy_coefficient", .01), ("reuse_bootstrap_tensors", False),
                         ("choice_weighted", False), ("asset_potential", False), ("gradient_norm", "historical")):
        if left.get(key, default) != right.get(key, default):
            raise ValueError(f"Exact comparison configuration differs: {key}")
    for first, second in zip(a, b, strict=True):
        if comparison_row(first, reference) != comparison_row(second, candidate):
            raise ValueError(f"Exact actor/guide/reward/feedback mismatch at step {first['step']}")
        for name in ("observation_metadata", "candidates_metadata"):
            first_path, second_path = Path(first[name]), Path(second[name])
            first_path.relative_to(reference)
            second_path.relative_to(candidate)
            first_meta = json.loads(first_path.read_text())
            second_meta = json.loads(second_path.read_text())
            if first_meta["binary"]["sha256"] != second_meta["binary"]["sha256"]:
                raise ValueError(f"Exact native tensor mismatch at step {first['step']}: {name}")
    updates = lambda run: [{k: v for k, v in row.items() if k != "elapsed_ns"} for row in run["updates"]]
    if updates(left) != updates(right):
        raise ValueError("Exact PPO update metrics differ")
    weights = []
    inputs = []
    for path, record in ((reference, left), (candidate, right)):
        actual = digest(path / "inference-weights.pt")
        if actual != record["model"]["sha256"]:
            raise ValueError("Inference weights no longer match their run record")
        weights.append(actual)
        inputs.append({"root": str(path), "run_sha256": digest(path / "run.json"),
                       "trajectory_sha256": digest(path / "trajectory.jsonl"),
                       "trainer_sha256": record["trainer_sha256"], "source": record["source"]})
    if weights[0] != weights[1]:
        raise ValueError("Exact final inference weights differ")
    return {"status": "passed", "inputs": inputs, "exact_transitions": len(a),
            "exact_update_metrics": True, "exact_input_tensor_hashes": True,
            "identical_inference_weights_sha256": weights[0],
            "normalization": "Only elapsed_ns and absolute storage roots are excluded; all causal fields remain exact"}


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    capture_source(root / "source")
    report = {"kind": "v2-integrated-options-qualification", "status": "running",
              "source": source_identity(), "host": host(), "seed": args.seed,
              "engine_sha256": digest(args.openttd), "cases": [],
              "claim": "Bounded exact implementation equivalence, not learning improvement or a timing study"}
    write_json(root / "verification.json", report)

    def train(name, source_root, trainer, device, retained):
        output = root / name
        command = [sys.executable, str(source_root / "scripts/dev/train_v2.py"),
                   "--openttd", str(args.openttd.resolve()), "--trainer", str(trainer.resolve()),
                   "--device", device, "--seed", str(args.seed), "--updates", "2",
                   "--episode-horizon", "128" if retained else "20", "--output", str(output)]
        if retained:
            command += ["--rollout-length", "64", "--training-map-count", "8",
                        "--financial-features", "signed-log-v1", "--entropy-coefficient", ".001",
                        "--guidance", "one-bus-public-plan-v3", "--reuse-bootstrap-tensors"]
        with (root / (name + ".log")).open("x") as log:
            subprocess.run(command, cwd=source_root, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(json.dumps({"completed": name}), flush=True)
        return output

    try:
        for retained, label in ((False, "default"), (True, "retained")):
            candidates = {}
            for device in args.devices:
                suffix = device.replace(":", "-")
                reference_root = args.retained_root if retained else args.reference_root
                reference_trainer = args.retained_trainer if retained else args.reference_trainer
                reference = train(f"{label}-{suffix}-reference", reference_root.resolve(), reference_trainer, device, retained)
                candidate = train(f"{label}-{suffix}-candidate", ROOT, args.trainer, device, retained)
                result = compare_exact(reference, candidate)
                report["cases"].append({"case": label, "device": device, **result})
                candidates[device] = candidate
                write_json(root / "verification.json", report)
            if set(candidates) == {"cpu", "cuda:0"}:
                compare_v2_training.run(SimpleNamespace(cpu=candidates["cpu"], cuda=candidates["cuda:0"],
                                                       output=root / f"{label}-cpu-cuda"))
        report["status"] = "passed"
    except BaseException as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(root / "verification.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("trainer", "reference-root", "reference-trainer", "retained-root", "retained-trainer", "openttd", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--devices", nargs="+", choices=("cpu", "cuda:0"), default=["cpu", "cuda:0"])
    parser.add_argument("--seed", type=int, default=20260923)
    run(parser.parse_args())
