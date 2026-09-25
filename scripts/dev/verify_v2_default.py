#!/usr/bin/env python3
"""Exact default equivalence to a pre-recovery native binary, plus A0 device agreement."""
import argparse
import contextlib
from pathlib import Path
from types import SimpleNamespace

import compare_v2_training
from local import source_identity, write_json, capture_source
from studies.execution_v2 import artifact
import train_v2
from verify_v2_options import compare_exact


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    capture_source(root / "source")
    report = {"kind": "v2-default-recovery-equivalence", "status": "running", "source": source_identity(),
              "reference_trainer": artifact(args.reference_trainer), "trainer": artifact(args.trainer),
              "engine": artifact(args.openttd), "checks": {}}
    try:
        for device in ("cpu", "cuda:0"):
            label = device.replace(":", "-")
            for variant, trainer in (("reference", args.reference_trainer), ("default", args.trainer), ("a0", args.trainer)):
                a0 = variant == "a0"
                settings = SimpleNamespace(openttd=args.openttd, trainer=trainer, device=device,
                    output=root / f"{label}-{variant}", seed=20260923, updates=2,
                    rollout_length=64 if a0 else 32, episode_horizon=128 if a0 else 20,
                    training_map_count=8 if a0 else 4, financial_features="signed-log-v1" if a0 else "raw",
                    entropy_coefficient=.01, gae_lambda=.95, guidance="one-bus-public-plan-v2" if a0 else "none",
                    reuse_bootstrap_tensors=a0, checkpoint_interval=0, resume=None)
                with (root / f"{label}-{variant}.log").open("x") as stream, contextlib.redirect_stdout(stream):
                    train_v2.run(settings)
            report["checks"][label] = compare_exact(root / f"{label}-reference", root / f"{label}-default")
        for variant in ("default", "a0"):
            compare_v2_training.run(SimpleNamespace(cpu=root / f"cpu-{variant}", cuda=root / f"cuda-0-{variant}",
                                                   output=root / f"agreement-{variant}"))
            report["checks"]["agreement-" + variant] = artifact(root / f"agreement-{variant}/comparison.json")
        if source_identity() != report["source"]:
            raise ValueError("Source changed during default qualification")
        report["status"] = "passed"
    except BaseException as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(root / "verification.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("trainer", "reference-trainer", "openttd", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
