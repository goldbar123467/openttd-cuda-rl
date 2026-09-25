#!/usr/bin/env python3
"""Exercise native rejection boundaries using an existing real-game checkpoint."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

from local import capture_source, source_identity, write_json


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_arguments(config, case, seed):
    command = ["--device", config["device"], "--seed", str(seed)]
    if config["rollout_steps"] != 32 and case != "wrong-rollout":
        command.extend(["--rollout-length", str(config["rollout_steps"])])
    gae_lambda = config.get("gae_lambda", .95)
    if case == "wrong-lambda":
        gae_lambda = 1.0 if gae_lambda != 1.0 else .95
    if gae_lambda != .95:
        command.extend(["--gae-lambda", str(gae_lambda)])
    entropy = config.get("entropy_coefficient", .01)
    if case == "wrong-entropy":
        entropy = .01 if entropy != .01 else .001
    if entropy != .01:
        command.extend(["--entropy-coefficient", str(entropy)])
    features = config.get("financial_features", "raw")
    if case == "wrong-financial-features":
        features = "signed-log-v1" if features == "raw" else "raw"
    if features != "raw":
        command.extend(["--financial-features", features])
    return command


def run(args):
    checkpoint = args.checkpoint.resolve()
    manifest = json.loads((checkpoint / "checkpoint.json").read_text())
    config = manifest["compatibility"]["configuration"]
    rollout = config["rollout_steps"]
    if rollout not in (32, 64, 128):
        raise ValueError("Unsupported native rollout length")
    if digest(args.trainer) != config["trainer_sha256"] or digest(checkpoint / "trainer.pt") != manifest["trainer_sha256"]:
        raise ValueError("Checkpoint or trainer identity differs from recorded native evidence")
    gae_lambda = config.get("gae_lambda", .95)
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    capture_source(root / "source")
    report = {"kind": "v2-native-checkpoint-boundary-tests", "status": "running", "source": source_identity(),
        "checkpoint": str(checkpoint), "checkpoint_manifest_sha256": digest(checkpoint / "checkpoint.json"),
        "trainer_sha256": config["trainer_sha256"], "device": config["device"], "rollout_steps": rollout, "gae_lambda": gae_lambda, "cases": [],
        "financial_features": config.get("financial_features", "raw"), "entropy_coefficient": config.get("entropy_coefficient", .01),
        "claim": "Native state/publication rejection checks. Repeated snapshot inputs are a synthetic fixture, not new gameplay."}
    write_json(root / "verification.json", report)
    try:
        paths = {}
        for name, signature in (("observation", "observation_binary_sha256"), ("candidates", "native_candidates_binary_sha256")):
            source = checkpoint / "next-reset-probe/artifacts" / f"tensors-000000-{name}.bin.gz"
            with gzip.open(source, "rb") as stream:
                data = stream.read()
            if hashlib.sha256(data).hexdigest() != manifest["next_reset"][signature]:
                raise ValueError("Archived reset fixture differs from its verified checkpoint signature")
            paths[name] = root / (name + ".bin")
            paths[name].write_bytes(data)
        restore = f"RESTORE\t{checkpoint / 'trainer.pt'}"
        act = f"ACT\t{paths['observation']}\t{paths['candidates']}\t"
        reward = f"REWARD\t0\t1\t1\t{paths['observation']}\t{paths['candidates']}"
        target = root / "must-not-exist.pt"
        sentinel = root / "existing.pt"
        sentinel.write_bytes(b"existing checkpoint must never be overwritten")
        corrupt = root / "corrupt.pt"
        corrupt.write_bytes(b"deliberately invalid archive")
        middle = [restore]
        for step in range(rollout):
            middle.extend([act + str(int(step == 0)), reward])
        middle.extend(["UPDATE", f"CHECKPOINT\t{target}"])
        cases = [
            ("fresh-save", [f"CHECKPOINT\t{target}"], "CHECKPOINT requires", config["run_seed"]),
            ("wrong-seed", [restore], "checkpoint configuration", config["run_seed"] + 1),
            ("restore-twice", [restore, restore], "RESTORE requires", config["run_seed"]),
            ("no-overwrite", [restore, f"CHECKPOINT\t{sentinel}"], "never overwriting", config["run_seed"]),
            ("relative-save", [restore, "CHECKPOINT\trelative.pt"], "absolute path", config["run_seed"]),
            ("pending-action", [restore, act + "1", f"CHECKPOINT\t{target}"], "CHECKPOINT requires", config["run_seed"]),
            ("partial-rollout", [restore, act + "1", "REWARD\t0\t0\t0\t-\t-", f"CHECKPOINT\t{target}"],
             "CHECKPOINT requires", config["run_seed"]),
            ("updated-midgame", middle, "CHECKPOINT requires", config["run_seed"]),
            ("corrupt-archive", [f"RESTORE\t{corrupt}"], "live V2 PPO failed", config["run_seed"]),
        ]
        if rollout != 32:
            halfway = [restore]
            for step in range(rollout // 2):
                halfway.extend([act + str(int(step == 0)), reward])
            cases.extend([
                ("wrong-rollout", [restore], "checkpoint configuration", config["run_seed"]),
                ("premature-update", [*halfway, "UPDATE"], "UPDATE requires", config["run_seed"]),
                ("overfilled-rollout", [*middle[:-2], act + "0"], "ACT at invalid rollout boundary", config["run_seed"]),
            ])
        if "gae_lambda" in config:
            cases.append(("wrong-lambda", [restore], "checkpoint configuration", config["run_seed"]))
        for option in ("entropy", "financial-features"):
            cases.append(("wrong-" + option, [restore], "checkpoint configuration", config["run_seed"]))
        for name, requests, reason, seed in cases:
            command = [str(args.trainer.resolve()), *native_arguments(config, name, seed)]
            process = subprocess.run(command,
                input="\n".join(requests) + "\n", capture_output=True, text=True, timeout=120)
            (root / (name + ".stdout")).write_text(process.stdout)
            (root / (name + ".stderr")).write_text(process.stderr)
            if process.returncode != 1 or reason not in process.stderr:
                raise ValueError("Unexpected native result for rejection case: " + name)
            # Every preparatory request must have succeeded; the last request is
            # the only expected failure, and the service must terminate afterward.
            responses = [json.loads(line) for line in process.stdout.splitlines()]
            if len(responses) != len(requests) - 1:
                raise ValueError("Rejection happened at an earlier preparatory request: " + name)
            if target.exists() or sentinel.read_bytes() != b"existing checkpoint must never be overwritten":
                raise ValueError("Invalid checkpoint publication changed a destination")
            report["cases"].append({"name": name, "rejected": True, "successful_preparatory_requests": len(responses)})
            write_json(root / "verification.json", report)
            print(name + ": rejected correctly", flush=True)
        if digest(checkpoint / "trainer.pt") != manifest["trainer_sha256"]:
            raise ValueError("Source checkpoint changed during rejection tests")
        report["status"] = "passed"
    except BaseException as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(root / "verification.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("trainer", "checkpoint", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
