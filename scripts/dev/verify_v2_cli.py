"""Qualify native entropy/financial options without collecting experience."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from local import capture_source, host, source_identity, write_json


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    capture_source(root / "source")
    binary = args.trainer.resolve()
    record = {"status": "running", "source": source_identity(), "host": host(), "binary": str(binary),
              "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "cases": []}
    write_json(root / "verification.json", record)
    base = [str(binary), "--device", "cpu", "--seed", "20260923"]
    try:
        cases = [("entropy-" + str(i), ["--entropy-coefficient", v], "entropy-coefficient must be finite and in [0,1]")
                 for i, v in enumerate(("nan", "inf", "-inf", "-0.1", "1.1", "bad", ".01trailing"))]
        cases += [
            ("duplicate-entropy", ["--entropy-coefficient", ".01", "--entropy-coefficient", ".001"], "duplicate trainer option"),
            ("duplicate-finance", ["--financial-features", "raw", "--financial-features", "signed-log-v1"], "duplicate trainer option"),
            ("unknown-option", ["--not-a-native-option", "1"], "unknown or duplicate trainer option"),
            ("unknown-finance", ["--financial-features", "unknown"], "financial"),
        ]
        for name, flags, reason in cases:
            process = subprocess.run(base + flags, input="", capture_output=True, text=True, timeout=30)
            (root / (name + ".stderr")).write_text(process.stderr)
            if process.returncode != 1 or process.stdout or reason not in process.stderr:
                raise ValueError("Invalid option accepted or wrong failure: " + name)
            record["cases"].append({"name": name, "command": base + flags, "rejected_before_output": True})
            write_json(root / "verification.json", record)
        for value in (0., .001, .01, 1.):
            command = base + ["--entropy-coefficient", str(value), "--financial-features", "signed-log-v1"]
            process = subprocess.run(command, input="TRAINING_INFO\nFINANCIAL_FEATURES_INFO\nCLOSE\n",
                                     capture_output=True, text=True, timeout=30)
            (root / ("valid-" + str(value) + ".stdout")).write_text(process.stdout)
            if process.returncode != 0:
                raise ValueError(process.stderr)
            info, features, closed = map(json.loads, process.stdout.splitlines())
            if (info != {"rollout_steps": 32, "sequence_length": 8, "optimization_epochs": 4,
                         "gamma": .99, "gae_lambda": .95, "entropy_coefficient": value} or
                    features != {"financial_features": "signed-log-v1"} or closed != {"status": "CLOSED"}):
                raise ValueError("Native configuration disagrees")
            record["cases"].append({"command": command, "training_info": info, "financial_features_info": features})
        record["status"] = "passed"
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(root / "verification.json", record)
    print(json.dumps({"status": record["status"], "cases": len(record["cases"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("trainer", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
