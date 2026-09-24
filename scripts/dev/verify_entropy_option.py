#!/usr/bin/env python3
"""Check a tunable native trainer against its previous default, CPU and CUDA."""
import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from local import ROOT, capture_source, source_identity, write_json
sys.path.insert(0, str(ROOT / "scripts/v1"))
from m08_trainer_client import Transition
from live_checkpoint import native_request, start_trainer


def exercise(binary, root, architecture, device, coefficient=0.01, checkpoint=False, gae_lambda=0.95):
    root.mkdir()
    settings = dict(architecture=architecture, device=device, run_seed=20260923,
                    rollout_length=2, environment_count=4, minibatch_size=4,
                    optimization_epochs=2, deterministic_cudnn=True,
                    entropy_coefficient=coefficient, gae_lambda=gae_lambda, diagnostic_root=root / "diagnostics")
    client = start_trainer(binary, **settings)
    result = {"actions": [], "updates": []}
    structured = [[((i + e * 3) % 17) / 16 for i in range(256)] for e in range(4)]
    spatial = [[((i + e * 7) % 31) / 30 for i in range(32768)] for e in range(4)]
    masks = [[int(i in (0, 1 + e, 6 + e)) for i in range(41)] for e in range(4)]
    try:
        for update in range(2):
            transitions = []
            for step in range(2):
                predictions = client.act(structured, spatial, masks, deterministic=False)
                result["actions"].append([dataclasses.asdict(p) for p in predictions])
                for e, prediction in enumerate(predictions):
                    transitions.append(Transition(structured[e], spatial[e], masks[e], prediction.action,
                        prediction.log_probability, prediction.value, float(prediction.action == 1 + e),
                        prediction.value, True, step == 0))
            result["updates"].append(dataclasses.asdict(client.update(transitions)))
            if checkpoint and update == 0:
                native_request(client, 5, root / "trainer.pt")
        model_id, _ = client.export_evaluation_model(root / "models", repository_commit="0" * 40, training_mean_reward=0.)
        result["model_id"] = model_id
        client.close(); client = None
        if checkpoint:
            # Resume the second fixture update with native optimizer/RNG state.
            client = start_trainer(binary, **settings)
            native_request(client, 6, root / "trainer.pt")
            transitions = []
            repeated = []
            for step in range(2):
                predictions = client.act(structured, spatial, masks, deterministic=False)
                repeated.append([dataclasses.asdict(p) for p in predictions])
                for e, prediction in enumerate(predictions):
                    transitions.append(Transition(structured[e], spatial[e], masks[e], prediction.action,
                        prediction.log_probability, prediction.value, float(prediction.action == 1 + e),
                        prediction.value, True, step == 0))
            metrics = dataclasses.asdict(client.update(transitions))
            resumed_id, _ = client.export_evaluation_model(root / "resumed-models", repository_commit="0" * 40, training_mean_reward=0.)
            if repeated != result["actions"][2:] or metrics != result["updates"][1] or resumed_id != model_id:
                raise ValueError("Nondefault native recovery differs")
            result["custom_configuration_exact_recovery"] = True
            client.close(); client = None
    finally:
        if client is not None:
            client.abort()
    return result


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    capture_source(root / "source")
    result = {"kind": "native-entropy-option-verification", "status": "running", "source": source_identity(),
              "claim": "Synthetic numerical/configuration checks; no gameplay or learning-strength claim", "cases": [],
              "binaries": {name: hashlib.sha256(getattr(args, name).read_bytes()).hexdigest() for name in ("reference", "candidate")}}
    try:
        for bad in ("nan", "inf", "-0.1", "garbage", "0.05trailing"):
            process = subprocess.run([str(args.candidate), "--entropy-coefficient", bad], input=b"", capture_output=True, timeout=30)
            if process.returncode != 1 or b"entropy-coefficient must be finite and nonnegative" not in process.stderr:
                raise ValueError("Native entropy parser did not reject invalid coefficient")
        result["invalid_native_coefficients_rejected"] = 5
        for device in ("cpu", "cuda:0"):
            for architecture in ("structured-mlp-v1", "spatial-cnn-v1", "combined-cnn-mlp-v1"):
                label = device.replace(":", "-") + "-" + architecture
                old = exercise(args.reference, root / (label + "-reference"), architecture, device)
                new = exercise(args.candidate, root / (label + "-default"), architecture, device)
                if old != new:
                    raise ValueError(f"Default native behavior differs: {label}")
                custom = exercise(args.candidate, root / (label + "-custom"), architecture, device, .05, checkpoint=True)
                if custom["model_id"] == new["model_id"] or custom["actions"][:2] != new["actions"][:2]:
                    raise ValueError("Entropy option changed initialization or did not affect optimization")
                result["cases"].append({"architecture": architecture, "device": device,
                    "default_exact": True, "default": new, "entropy_0_05": custom})
                write_json(root / "verification.json", result)
                print(json.dumps({"architecture": architecture, "device": device, "default_exact": True, "custom_recovery_exact": True}), flush=True)
        result["status"] = "passed"
    except BaseException as exc:
        result.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(root / "verification.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "candidate", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
