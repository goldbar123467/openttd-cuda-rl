#!/usr/bin/env python3
"""Replay every retained V1 development observation through native deterministic ACT.

INSPECT returns the distribution from the same ACT implementation, including fused
CUDA when selected. No optimizer update or game/held-out access occurs. Historical
MLP traces need no spatial input; CNN traces must retain spatial_before explicitly.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

from local import ROOT, capture_source, host, source_identity, write_json
sys.path.insert(0, str(ROOT / "scripts/v1"))
from m08_trainer_client import TrainerClient
from trainer_diagnostics import backend_info

PROBABILITY_ATOL = 1e-6
PROBABILITY_RTOL = 1e-5
LOG_PROBABILITY_ATOL = 1e-5
LOG_PROBABILITY_RTOL = 1e-5


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def finite_vector(value, size, name):
    if not isinstance(value, list) or len(value) != size or any(
            isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value):
        raise ValueError(f"{name} must contain {size} finite numbers")
    return value


def inputs(row, architecture):
    structured = finite_vector(row["structured_before"], 256, "structured_before")
    mask = row["legal"]
    if not isinstance(mask, list) or len(mask) != 41 or any(type(x) not in (bool, int) or x not in (0, 1) for x in mask) or not any(mask):
        raise ValueError("legal mask must contain 41 booleans and at least one choice")
    if "spatial_before" in row:
        spatial = finite_vector(row["spatial_before"], 32768, "spatial_before")
    elif architecture == "structured-mlp-v1":
        spatial = [0.] * 32768  # Explicit unused placeholder: the MLP ignores it.
    else:
        raise ValueError("CNN agreement requires retained spatial_before; rerun development evaluation with --retain-spatial-inputs")
    return structured, spatial, mask


def inspect(client, structured, spatial, masks):
    client._validate_batches(structured, spatial, masks, maximum=64)
    data = bytearray(struct.pack("<IB", len(structured), 1))
    for rows, size in ((structured, 256), (spatial, 32768)):
        for row in rows:
            data.extend(struct.pack(f"<{size}f", *row))
    for row in masks:
        data.extend(bytes(row))
    response = client._request(9, bytes(data))
    size = struct.calcsize("<q84d")
    if len(response) != 4 + len(structured) * size or struct.unpack_from("<I", response)[0] != len(structured):
        raise ValueError("Invalid development INSPECT response")
    rows = [struct.unpack_from("<q84d", response, 4 + i * size) for i in range(len(structured))]
    return [dict(action=row[0], log_probability=row[1], value=row[2], logits=list(row[3:44]),
                 probabilities=list(row[44:85])) for row in rows]


def import_package(client, package):
    data = client._request(10, client._pack_string(str(package)))
    if len(data) < 4 or struct.unpack_from("<I", data)[0] != 1:
        raise ValueError("Invalid evaluation import response")
    offset, values = 4, []
    for _ in range(3):
        value, offset = client._unpack_string(data, offset)
        values.append(value)
    if offset != len(data):
        raise ValueError("Trailing evaluation import response")
    return dict(zip(("package_id", "model_sha256", "model_state_sha256"), values))


def distribution(prediction, mask, name):
    probabilities = finite_vector(prediction["probabilities"], 41, f"{name} probabilities")
    finite_vector(prediction["logits"], 41, f"{name} logits")
    if any(p < 0 or p > 1 or (not legal and p != 0) for p, legal in zip(probabilities, mask)) or abs(sum(probabilities) - 1) > 1e-5:
        raise ValueError(f"{name} distribution violates legality/normalization")
    action = prediction["action"]
    if type(action) is not int or not 0 <= action < 41 or not mask[action]:
        raise ValueError(f"{name} action is illegal")
    if not all(math.isfinite(prediction[k]) for k in ("log_probability", "value")):
        raise ValueError(f"{name} selected outputs are nonfinite")
    return probabilities


def compare_row(row, actual, policy):
    """Sampled trace actions are not argmax; compare the recorded distribution."""
    mask, reference = row["legal"], row["prediction"]
    expected = distribution(reference, mask, "CPU")
    observed = distribution(actual, mask, "device")
    if row["action"] != reference["action"]:
        raise ValueError("Trace action differs from recorded CPU prediction")
    # Match PyTorch's first maximum, ignoring illegal zero-probability entries.
    greedy = max((i for i, legal in enumerate(mask) if legal), key=lambda i: expected[i])
    device_greedy = max((i for i, legal in enumerate(mask) if legal), key=lambda i: observed[i])
    if actual["action"] != device_greedy or (policy == "greedy" and reference["action"] != greedy):
        raise ValueError("Deterministic ACT is not the first legal argmax")
    errors = [abs(a - b) for a, b in zip(observed, expected)]
    bad = sum(e > PROBABILITY_ATOL + PROBABILITY_RTOL * abs(p) for e, p in zip(errors, expected))
    # The recorded selected logp is comparable only when it selects this argmax.
    selected_error = abs(actual["log_probability"] - reference["log_probability"]) if reference["action"] == actual["action"] else None
    logp_ok = selected_error is None or selected_error <= LOG_PROBABILITY_ATOL + LOG_PROBABILITY_RTOL * abs(reference["log_probability"])
    return {"passed": actual["action"] == greedy and bad == 0 and logp_ok,
            "argmax_equal": actual["action"] == greedy, "probability_failures": bad,
            "max_probability_error": max(errors), "selected_logp_error": selected_error,
            "reference_argmax": greedy, "device_argmax": actual["action"]}


def package_hashes(package):
    if package.is_symlink() or not package.is_dir() or sorted(p.name for p in package.iterdir()) != ["manifest.json", "model.pt"]:
        raise ValueError("Expected an immutable native evaluation package")
    if any(p.is_symlink() or not p.is_file() for p in package.iterdir()):
        raise ValueError("Package members must be regular files")
    hashes = {p.name: sha256(p) for p in package.iterdir()}
    manifest = json.loads((package / "manifest.json").read_text())
    if hashes["manifest.json"] != package.name or manifest["model_sha256"] != hashes["model.pt"]:
        raise ValueError("Package content identity differs")
    return hashes, manifest


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {"kind": "v1-training-device-agreement-v1", "status": "running", "command": sys.argv, "source": source_identity(),
              "source_archive": capture_source(output / "source"), "device": args.device, "host": host(),
              "batch_size": args.batch_size, "run_seed": 20260925, "final_evaluation_accessed": False,
              "probability_atol": PROBABILITY_ATOL, "probability_rtol": PROBABILITY_RTOL,
              "logp_atol": LOG_PROBABILITY_ATOL, "logp_rtol": LOG_PROBABILITY_RTOL,
              "argmax_requirement": "exact first legal maximum on every replayed row",
              "episodes": [], "input_sha256": {}}
    client = None
    def bind(path):
        record["input_sha256"][str(path)] = sha256(path)
    def read(path):
        bind(path)
        return json.loads(path.read_text())
    try:
        evaluation = args.evaluation.resolve()
        metadata = read(evaluation / "run.json")
        if metadata.get("kind") != "complete-episode-development-evaluation" or metadata.get("status") != "completed" or metadata.get("split") != "development" or metadata.get("final_evaluation_accessed") is not False or metadata.get("inference_backend") != "native":
            raise ValueError("Agreement only accepts completed native development evaluations")
        package = Path(metadata["package"])
        hashes, manifest = package_hashes(package)
        if metadata["package_hashes"] != hashes:
            raise ValueError("Evaluation package hashes differ")
        candidate = args.candidate_package.resolve() if args.candidate_package else package
        candidate_hashes, candidate_manifest = package_hashes(candidate)
        if candidate_manifest["architecture"] != manifest["architecture"]:
            raise ValueError("Candidate architecture differs")
        for p in {package, candidate}:
            for name in ("manifest.json", "model.pt"):
                bind(p / name)
        record.update(reference_package=str(package), candidate_package=str(candidate),
                      package_identity_equal=candidate_hashes == hashes, architecture=manifest["architecture"],
                      spatial_input_policy="Retained full inputs; explicit unused zero placeholder only for structured MLP")
        trainer = args.trainer.resolve()
        bind(trainer)
        build = read(trainer.parent / "development-build.json")
        record["build"] = build
        client = TrainerClient.start(trainer, architecture=manifest["architecture"], device=args.device,
            run_seed=20260925, rollout_length=4, environment_count=1, minibatch_size=4,
            optimization_epochs=1, diagnostic_root=output / "diagnostics")
        record["backend"] = backend_info(client, build, args.device)
        if record["backend"]["act_distribution"] != args.expected_backend:
            raise ValueError("Actual native backend differs from --expected-backend")
        imported = import_package(client, candidate)
        if imported["package_id"] != candidate.name or imported["model_sha256"] != candidate_hashes["model.pt"]:
            raise ValueError("Native imported identity differs")
        record["native_import"] = imported
        names = set()
        for ep in metadata["episodes"]:
            if ep["policy"] not in ("greedy", "sampled"):
                continue
            if ep["template_id"] not in ("m02-template-05", "m02-template-06") or ep["scenario"]["split"] != "development":
                raise ValueError("Episode is not a development map")
            name = f'{ep["policy"]}-{ep["template_id"]}-s{ep["sampling_seed"]}'
            if name in names:
                raise ValueError("Duplicate evaluation episode")
            names.add(name)
            stored = read(evaluation / name / "episode.json")
            if stored != ep or ep["status"] != "completed" or ep["package_id"] != package.name or ep["inference_device"] != "cpu" or ep["inference_backend"] != "native":
                raise ValueError("Episode metadata differs from completed evaluation")
            path = evaluation / name / "actions.jsonl"
            bind(path)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            if len(rows) != ep["actions"] or not 1 <= len(rows) <= 512 or [r["step"] for r in rows] != list(range(1, len(rows)+1)):
                raise ValueError("Trace is incomplete, duplicated or out of order")
            summary = {"episode": name, "rows": len(rows), "failed_rows": 0, "argmax_mismatches": 0,
                       "probability_failures": 0, "max_probability_error": 0., "max_selected_logp_error": 0.,
                       "model_state_equal": ep["model_state_sha256"] == imported["model_state_sha256"],
                       "first_failures": []}
            for start in range(0, len(rows), args.batch_size):
                batch = rows[start:start+args.batch_size]
                packed = [inputs(row, manifest["architecture"]) for row in batch]
                structured, spatial, masks = map(list, zip(*packed))
                predictions = inspect(client, structured, spatial, masks)
                regular = client.act(structured, spatial, masks, deterministic=True)
                for row, actual, act in zip(batch, predictions, regular):
                    if dataclasses.asdict(act) != {k: actual[k] for k in ("action", "log_probability", "value")}:
                        raise ValueError("INSPECT differs from unchanged ACT request")
                    check = compare_row(row, actual, ep["policy"])
                    summary["failed_rows"] += not check["passed"]
                    summary["argmax_mismatches"] += not check["argmax_equal"]
                    summary["probability_failures"] += check["probability_failures"]
                    summary["max_probability_error"] = max(summary["max_probability_error"], check["max_probability_error"])
                    summary["max_selected_logp_error"] = max(summary["max_selected_logp_error"], check["selected_logp_error"] or 0.)
                    if not check["passed"] and len(summary["first_failures"]) < 16:
                        summary["first_failures"].append(dict(step=row["step"], **check))
            record["episodes"].append(summary)
            write_json(output / "verification.json", record)
            print(f'DEVICE_AGREEMENT episode={name} rows={len(rows)} failed={summary["failed_rows"]}', flush=True)
        if not names:
            raise ValueError("No neural development episodes to replay")
        client.close()
        client = None
        record["inputs_unchanged"] = all(sha256(Path(path)) == expected for path, expected in record["input_sha256"].items())
        passed = record["package_identity_equal"] and record["inputs_unchanged"] and all(
            e["failed_rows"] == 0 and e["model_state_equal"] for e in record["episodes"])
        record["status"] = "passed" if passed else "failed"
        return 0 if passed else 1
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        if client is not None:
            client.abort()
        write_json(output / "verification.json", record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--trainer", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    parser.add_argument("--expected-backend", choices=("reference", "fused-cuda"), required=True)
    parser.add_argument("--batch-size", type=int, choices=range(1, 65), default=1,
                        help="Default reproduces the CPU evaluator's one-observation calls")
    parser.add_argument("--candidate-package", type=Path,
                        help="Negative-control/diagnostic import. A differing package can never pass, even if its outputs match.")
    parser.add_argument("--output", type=Path, required=True)
    try:
        return run(parser.parse_args())
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(f"Device agreement failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
