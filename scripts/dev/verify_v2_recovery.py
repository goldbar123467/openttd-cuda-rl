#!/usr/bin/env python3
"""Bounded recovery correctness; no development selection or held-out gameplay."""
import argparse
import contextlib
import json
from pathlib import Path
from types import SimpleNamespace

import compare_v2_training
from infer_v2 import PolicyClient
from local import capture_source, host, source_identity, write_json
import train_v2
import training_probes_v2
from studies.execution_v2 import artifact
from studies.protocol_v2 import load_protocol
from verify_v2_options import compare_exact
from v2_checkpoint_state import compare as compare_checkpoint_state


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    capture_source(root / "source")
    gradient_norm = getattr(args, "gradient_norm", "historical")
    report = {"kind": "v2-recovery-correctness", "status": "running", "source": source_identity(),
              "host": host(), "trainer": artifact(args.trainer), "engine": artifact(args.openttd), "checks": {},
              "gradient_norm": gradient_norm,
              "claim": "Bounded correctness and exact read-only probe equality; not learning improvement"}
    write_json(root / "verification.json", report)
    try:
        entries = training_probes_v2.prepare(args.openttd, root / "training-reset-inputs",
                    load_protocol()["training_maps"], 128, "one-bus-public-plan-v4")
        for device in args.devices:
            label = device.replace(":", "-")
            probes = []
            class ProbedClient(PolicyClient):
                def request(self, request):
                    reply = super().request(request)
                    if request == "UPDATE":
                        probes.append(training_probes_v2.probe(self, entries, reply["update"]))
                    return reply
            for name, factory in (("plain", PolicyClient), ("probed", ProbedClient)):
                settings = SimpleNamespace(openttd=args.openttd, trainer=args.trainer, device=device,
                    output=root / f"{label}-{name}", seed=20260923, updates=2, rollout_length=64,
                    episode_horizon=128, training_map_count=8, financial_features="signed-log-v1",
                    gae_lambda=.95, entropy_coefficient=.003, guidance="one-bus-public-plan-v4",
                    reuse_bootstrap_tensors=True, checkpoint_interval=2, resume=None,
                    policy_loss="choice-weighted", asset_potential=True, gradient_norm=gradient_norm)
                with (root / f"{label}-{name}.log").open("x") as stream, contextlib.redirect_stdout(stream):
                    train_v2.run(settings, trainer_factory=factory)
                print(json.dumps({"case": f"{label}-{name}", "status": "completed"}), flush=True)
            exact = compare_exact(root / f"{label}-plain", root / f"{label}-probed")
            checkpoints = [artifact(root / f"{label}-{name}/checkpoints/update-000002/trainer.pt") for name in ("plain", "probed")]
            checkpoint_equality = compare_checkpoint_state(checkpoints[0]["path"], checkpoints[1]["path"])
            report["checks"][f"probe-equality-{label}"] = {**exact, "native_checkpoints": checkpoints,
                "exact_checkpoint_state": checkpoint_equality, "probes": probes}
            mismatch = PolicyClient(args.trainer, root / f"{label}-wrong-loss.log", device, 20260923,
                                   rollout_length=64, financial_features="signed-log-v1", entropy_coefficient=.003,
                                   gradient_norm=gradient_norm)
            rejected = False
            try:
                mismatch.request(f"RESTORE\t{checkpoints[0]['path']}")
            except RuntimeError:
                rejected = True
            finally:
                mismatch.abort()
            if not rejected or "checkpoint configuration" not in (root / f"{label}-wrong-loss.log").read_text():
                raise ValueError("Native checkpoint accepted another policy-loss configuration")
            report["checks"][f"wrong-loss-rejected-{label}"] = True
            # Keep loss and every other setting equal: only norm accumulation
            # changes, proving the native checkpoint binds this numerical mode.
            mismatch = PolicyClient(args.trainer, root / f"{label}-wrong-norm.log", device, 20260923,
                                   rollout_length=64, financial_features="signed-log-v1", entropy_coefficient=.003,
                                   choice_weighted=True, gradient_norm="fp64-v1" if gradient_norm == "historical" else "historical")
            rejected = False
            try:
                mismatch.request(f"RESTORE\t{checkpoints[0]['path']}")
            except RuntimeError:
                rejected = True
            finally:
                mismatch.abort()
            if not rejected or "checkpoint configuration" not in (root / f"{label}-wrong-norm.log").read_text():
                raise ValueError("Native checkpoint accepted another gradient norm accumulation mode")
            report["checks"][f"wrong-norm-rejected-{label}"] = True
            write_json(root / "verification.json", report)
        if set(args.devices) == {"cpu", "cuda:0"}:
            compare_v2_training.run(SimpleNamespace(cpu=root / "cpu-plain", cuda=root / "cuda-0-plain", output=root / "device-agreement"))
            report["checks"]["cpu-cuda"] = artifact(root / "device-agreement/comparison.json")
        if report["source"] != source_identity():
            raise ValueError("Qualification source changed while native checks ran")
        report["status"] = "passed"
    except BaseException as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(root / "verification.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("trainer", "openttd", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--devices", choices=("cpu", "cuda:0"), nargs="+", default=["cpu", "cuda:0"])
    parser.add_argument("--gradient-norm", choices=("historical", "fp64-v1"), default="historical")
    run(parser.parse_args())
