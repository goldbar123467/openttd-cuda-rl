#!/usr/bin/env python3
"""Paired real-game timing/correctness for two native CUDA trainer builds."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

from local import ROOT, capture_source, positive, source_identity, write_json


def exact_comparison(args):
    explicit = getattr(args, "require_exact", False)
    same_binary = hashlib.sha256(args.reference.read_bytes()).digest() == hashlib.sha256(args.candidate.read_bytes()).digest()
    if args.candidate_spatial_validation == "vectorized" and not (explicit or same_binary):
        raise ValueError("Spatial validation comparison requires the same native trainer")
    return explicit or args.candidate_spatial_validation == "vectorized"


def run(args):
    exact_inputs = exact_comparison(args)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {"kind": "paired-live-trainer-backend-comparison", "status": "running",
              "source": source_identity(), "pairs": [],
              "claim": "Bounded live correctness/performance experiment; not evidence of playing strength",
              "criteria": {"native_traces": "byte-identical", "update_metrics_rtol": 0 if exact_inputs else 1e-4,
                           "update_metrics_atol": 0 if exact_inputs else 1e-5, "exact_final_model": exact_inputs},
              "candidate_spatial_validation": args.candidate_spatial_validation,
              "explicit_cross_binary_exact": getattr(args, "require_exact", False),
              "requested_pairs": args.pairs, "updates_per_run": args.updates,
              "reference_sha256": hashlib.sha256(args.reference.read_bytes()).hexdigest(),
              "candidate_sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest()}
    capture_source(output / "source")
    write_json(output / "comparison.json", record)
    try:
        for pair in range(args.pairs):
            runs = {}
            for name in (("reference", "candidate") if pair % 2 == 0 else ("candidate", "reference")):
                target = output / f"pair-{pair}-{name}"
                command = [sys.executable, str(ROOT / "scripts/dev/train_live.py"),
                           "--trainer", str(getattr(args, name).resolve()), "--openttd", str(args.openttd.resolve()),
                           "--instance-dir", str(args.instance_dir.resolve()), "--device", "cuda:0",
                           "--architecture", "structured-mlp-v1", "--seed", str(20260927 + pair),
                           "--updates", str(args.updates), "--evaluation-steps", "1", "--bridge-validation", "fast",
                           "--spatial-validation", args.candidate_spatial_validation if name == "candidate" else "reference",
                           "--output", str(target)]
                with (output / f"pair-{pair}-{name}.log").open("x") as log:
                    subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
                runs[name] = json.loads((target / "run.json").read_text())
                if runs[name]["status"] != "completed":
                    raise RuntimeError("Paired training did not complete")
            old, new = (runs[name]["training"] for name in ("reference", "candidate"))
            differences = {}
            for left, right in zip(old["updates"], new["updates"], strict=True):
                if left.keys() != right.keys():
                    raise RuntimeError("Update metric fields differ")
                for name in left:
                    if not math.isclose(left[name], right[name],
                                        rel_tol=record["criteria"]["update_metrics_rtol"], abs_tol=record["criteria"]["update_metrics_atol"]):
                        raise RuntimeError(f"Update metric outside declared tolerance: {name} {left[name]} vs {right[name]}")
                    differences[name] = max(differences.get(name, 0.), abs(left[name] - right[name]))
            if exact_inputs and runs["reference"]["model"]["id"] != runs["candidate"]["model"]["id"]:
                raise RuntimeError("Exact comparison changed final native model identity")
            reference_root = output / f"pair-{pair}-reference/episode-metrics"
            candidate_root = output / f"pair-{pair}-candidate/episode-metrics"
            files = sorted(p.name for p in reference_root.glob("*.jsonl"))
            if not files or files != sorted(p.name for p in candidate_root.glob("*.jsonl")):
                raise RuntimeError("Native trace file sets differ")
            traces = []
            for name in files:
                left, right = (reference_root / name).read_bytes(), (candidate_root / name).read_bytes()
                if left != right:
                    raise RuntimeError(f"Native action/state/economic trace differs: {name}")
                traces.append({"file": name, "transitions": len(left.splitlines()), "sha256": hashlib.sha256(left).hexdigest()})
            timings = {name: {key: value / 1e9 for key, value in run["training"].items() if key.endswith("_ns")}
                       for name, run in runs.items()}
            ratio = old["collection_and_optimization_elapsed_ns"] / new["collection_and_optimization_elapsed_ns"]
            record["pairs"].append({"pair": pair, "seed": 20260927 + pair, "traces": traces,
                                    "model_ids": {name: run["model"]["id"] for name, run in runs.items()},
                                    "maximum_absolute_metric_differences": differences,
                                    "seconds": timings, "end_to_end_speedup": ratio})
            write_json(output / "comparison.json", record)
        ratios = [pair["end_to_end_speedup"] for pair in record["pairs"]]
        record.update(status="passed", median_speedup=statistics.median(ratios), speedup_range=[min(ratios), max(ratios)])
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(output / "comparison.json", record)
    print(json.dumps({key: record[key] for key in ("status", "median_speedup", "speedup_range")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "candidate", "openttd", "instance-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--pairs", type=positive, default=2)
    parser.add_argument("--updates", type=positive, default=4)
    parser.add_argument("--require-exact", action="store_true", help="Require exact metrics and final model even across different binaries")
    parser.add_argument("--candidate-spatial-validation", choices=("reference", "vectorized"), default="reference",
                        help="Use identical trainer paths to isolate opt-in CPU spatial validation")
    run(parser.parse_args())
