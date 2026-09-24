#!/usr/bin/env python3
"""Check the development GAE option without replacing native PPO/GAE math."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from local import capture_source, source_identity, write_json
from verify_entropy_option import exercise


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    capture_source(root / "source")
    result = {"kind": "native-gae-option-verification", "status": "running", "source": source_identity(),
              "claim": "Synthetic configuration and recovery checks, not gameplay evidence", "cases": [],
              "binaries": {name: hashlib.sha256(getattr(args, name).read_bytes()).hexdigest() for name in ("reference", "candidate")}}
    try:
        for bad in ("nan", "inf", "-0.1", "1.1", "garbage", "1.0trailing"):
            process = subprocess.run([str(args.candidate), "--gae-lambda", bad], input=b"", capture_output=True, timeout=30)
            if process.returncode != 1 or b"gae-lambda must be finite and in [0,1]" not in process.stderr:
                raise ValueError("Native GAE parser did not reject invalid coefficient")
        result["invalid_coefficients_rejected"] = 6
        for device in ("cpu", "cuda:0"):
            for architecture in ("structured-mlp-v1", "spatial-cnn-v1", "combined-cnn-mlp-v1"):
                label = device.replace(":", "-") + "-" + architecture
                old = exercise(args.reference, root / (label + "-reference"), architecture, device)
                new = exercise(args.candidate, root / (label + "-default"), architecture, device)
                if old != new:
                    raise ValueError(f"Default native behavior differs: {label}")
                custom = exercise(args.candidate, root / (label + "-lambda1"), architecture, device,
                                  checkpoint=True, gae_lambda=1.0)
                if custom["model_id"] == new["model_id"] or custom["actions"][:2] != new["actions"][:2]:
                    raise ValueError("GAE option changed initialization or did not affect optimization")
                result["cases"].append({"architecture": architecture, "device": device,
                    "default_exact": True, "default": new, "gae_lambda_1": custom})
                write_json(root / "verification.json", result)
                print(json.dumps({"architecture": architecture, "device": device,
                                  "default_exact": True, "custom_recovery_exact": True}), flush=True)
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
