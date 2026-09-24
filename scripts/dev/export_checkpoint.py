#!/usr/bin/env python3
"""Export inference weights from a verified native reset checkpoint without training."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from local import ROOT, capture_source, source_identity, write_json
sys.path.insert(0, str(ROOT / "scripts/v1"))
from live_checkpoint import native_request, read_checkpoint, start_trainer


def run(args):
    training_root = args.training_run.resolve()
    checkpoint = args.checkpoint.resolve()
    training = json.loads((training_root / "run.json").read_text())
    if training["kind"] != "live-openttd-development-training" or training["status"] != "completed":
        raise ValueError("Checkpoint export requires a completed development training run")
    if not any(entry["status"] == "saved" and Path(entry["path"]).resolve() == checkpoint
               for entry in training.get("checkpoints", [])):
        raise ValueError("The checkpoint is not registered by this completed training run")
    manifest = json.loads((checkpoint / "checkpoint.json").read_text())
    configuration = manifest["compatibility"]["configuration"]
    if any(training[key] != value for key, value in configuration.items()):
        raise ValueError("Checkpoint configuration differs from its training run")
    if hashlib.sha256(args.trainer.read_bytes()).hexdigest() != configuration["trainer_sha256"]:
        raise ValueError("Checkpoint export requires its recorded native trainer binary")
    # This restores into the exact native runtime for export only. It never
    # resumes collection under changed Python code or claims environment recovery.
    manifest = read_checkpoint(checkpoint, manifest["compatibility"])
    metrics = next((row for row in training["training"]["updates"] if row["update"] == manifest["update"]), None)
    if metrics is None or metrics["samples"] != manifest["samples"]:
        raise ValueError("Checkpoint counters are absent from training metrics")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    record = {"kind": "native-checkpoint-inference-export", "status": "running", "source": source_identity(),
        "training_run": str(training_root), "checkpoint": str(checkpoint), "configuration": configuration,
        "checkpoint_manifest_sha256": hashlib.sha256((checkpoint / "checkpoint.json").read_bytes()).hexdigest(),
        "trainer_payload_sha256": manifest["trainer_sha256"], "update": manifest["update"], "samples": manifest["samples"],
        "claim": "Inference export at a saved update; no new training or environment continuation was performed"}
    capture_source(root / "source")
    write_json(root / "run.json", record)
    client = None
    try:
        client = start_trainer(args.trainer.resolve(), architecture=configuration["architecture"], device=configuration["device"],
            run_seed=configuration["seed"], rollout_length=configuration["rollout_length"],
            environment_count=configuration["environments"], minibatch_size=configuration["minibatch_size"],
            optimization_epochs=configuration["epochs"], deterministic_cudnn=configuration["deterministic_cudnn"],
            entropy_coefficient=configuration.get("entropy_coefficient", 0.01),
            gae_lambda=configuration.get("gae_lambda", 0.95),
            diagnostic_root=root / "diagnostics")
        native_request(client, 6, checkpoint / "trainer.pt")
        model_id, package = client.export_evaluation_model(root / "models", repository_commit=training["source"]["commit"],
            training_mean_reward=metrics.get("mean_training_reward", metrics["mean_rollout_reward"]))
        client.close(); client = None
        record.update(status="completed", model={"id": model_id, "path": str(package)},
            matches_final_training_model=model_id == training["model"]["id"])
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        if client is not None:
            client.abort()
        write_json(root / "run.json", record)
    print(json.dumps({key: record[key] for key in ("status", "update", "samples", "model", "matches_final_training_model")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("training-run", "checkpoint", "trainer", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    run(parser.parse_args())
