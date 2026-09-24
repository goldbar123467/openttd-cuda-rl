#!/usr/bin/env python3
"""Verify native/ONNX behavior across matched, complete real-game replays."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from export_live import canonical, compare, require
from local import ROOT, source_identity, write_json


def run(reference, candidate, output):
    output.mkdir(parents=True, exist_ok=False)
    record = {"kind": "complete-native-onnx-replay-comparison", "status": "running", "source": source_identity(),
              "reference": str(reference), "candidate": str(candidate)}
    try:
        left = json.loads((reference / "run.json").read_text())
        right = json.loads((candidate / "run.json").read_text())
        require(left["status"] == right["status"] == "completed", "Both replay runs must be complete")
        require(left["engine_sha256"] == right["engine_sha256"], "Replay engines differ")
        require(left.get("inference_backend", "native") == "native" and right["inference_backend"] == "onnx", "Expected native and ONNX replays")
        manifest = json.loads((Path(right["package"]) / "manifest.json").read_text())
        require(manifest["provenance"]["source_package_id"] == Path(left["package"]).name, "ONNX was exported from another model")
        expected_paths = sorted(path.relative_to(reference) for path in reference.rglob("actions.jsonl"))
        actual_paths = sorted(path.relative_to(candidate) for path in candidate.rglob("actions.jsonl"))
        require(expected_paths == actual_paths and expected_paths, "Replay case matrix differs")
        tolerance = json.loads((ROOT / "config/v1/m10-model-package-contract.json").read_text())["tolerances"]
        maximum = {key: 0. for key in ("logits", "probabilities", "value")}
        cases = []
        for path in expected_paths:
            expected = [json.loads(line) for line in (reference / path).read_text().splitlines()]
            actual = [json.loads(line) for line in (candidate / path).read_text().splitlines()]
            require(len(expected) == len(actual) and expected, f"Replay length differs: {path}")
            semantic_hash = hashlib.sha256()
            for old, new in zip(expected, actual, strict=True):
                old_prediction, new_prediction = old.pop("prediction"), new.pop("prediction")
                for key, error in compare(SimpleNamespace(**old_prediction), SimpleNamespace(**new_prediction), tolerance).items():
                    maximum[key] = max(maximum[key], error)
                require(old == new, f"Action, mask, native state or economics differ: {path}, step {old['step']}")
                semantic_hash.update(canonical(new) + b"\n")
            cases.append({"case": str(path.parent), "transitions": len(actual), "semantic_trace_sha256": semantic_hash.hexdigest()})
        record.update(status="passed", cases=cases, maximum_absolute_errors=maximum,
                      transitions=sum(case["transitions"] for case in cases),
                      exact_actions_masks_native_states_rewards_economics=True)
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(output / "comparison.json", record)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.reference.resolve(), args.candidate.resolve(), args.output.resolve())
