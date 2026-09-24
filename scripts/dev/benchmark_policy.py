#!/usr/bin/env python3
"""Record repeated native masked-policy microbenchmarks, explicitly not gameplay."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

from local import capture_source, host, positive, source_identity, write_json


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    executable = args.executable.resolve()
    record = {"kind": "masked-policy-native-microbenchmark", "status": "running",
              "claim": "Wall time including validation and synchronization, excluding host-device input transfer; not end-to-end training speed",
              "source": source_identity(), "host": host(),
              "executable": str(executable), "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
              "repetitions": args.repetitions, "runs": []}
    capture_source(output / "source")
    write_json(output / "benchmark.json", record)
    try:
        if not record["host"]["cuda_available"]:
            raise RuntimeError("CUDA unavailable; this comparison has no CPU fallback")
        for index in range(args.repetitions):
            # Alternate process order to reduce systematic warm-up/order bias.
            for device in (("cpu", "cuda:0") if index % 2 == 0 else ("cuda:0", "cpu")):
                result = subprocess.run([str(executable), device], capture_output=True, text=True, check=True, timeout=120)
                (output / f"repeat-{index}-{device.replace(':', '-')}.json").write_text(result.stdout)
                record["runs"].append(json.loads(result.stdout))
        summaries = []
        for device in ("cpu", "cuda:0"):
            for batch in (4, 64, 512):
                rows = [row for run in record["runs"] if run["device"] == device
                        for row in run["results"] if row["batch"] == batch]
                summary = {"device": device, "batch": batch}
                for name in ("reference_wall_us_per_call", "fused_wall_us_per_call"):
                    values = [row[name] for row in rows if name in row]
                    if values:
                        summary[name] = {"median": statistics.median(values), "minimum": min(values), "maximum": max(values), "values": values}
                summaries.append(summary)
        record.update(status="passed", summaries=summaries)
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(output / "benchmark.json", record)
    print(json.dumps(record["summaries"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=positive, default=5)
    run(parser.parse_args())
