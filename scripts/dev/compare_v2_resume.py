#!/usr/bin/env python3
"""Compare an actual live-PPO continuation exactly, including native Adam/RNG."""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path

from local import source_identity, write_json
from v2_checkpoint_state import checkpoint_state, compare, fingerprint


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def saved_checkpoint(entry):
    path = Path(entry["path"]).resolve()
    if digest(path / "checkpoint.json") != entry["manifest_sha256"]:
        raise ValueError("Saved checkpoint manifest digest differs")
    manifest = read(path / "checkpoint.json")
    if manifest["update"] != entry["update"] or digest(path / "trainer.pt") != manifest["trainer_sha256"]:
        raise ValueError("Saved native checkpoint counters/digest differ")
    return path, manifest


def check_coverage(updates, rows, boundary, final_update, rollout):
    expected_updates = list(range(boundary["update"] + 1, final_update + 1))
    if not expected_updates or [u["update"] for u in updates] != expected_updates:
        raise ValueError("Continuation updates are missing, duplicated or out of order")
    if any(u["transitions"] != u["update"] * rollout for u in updates):
        raise ValueError("Continuation update transition counters differ")
    expected_steps = list(range(boundary["transitions"] + 1, final_update * rollout + 1))
    if [r["step"] for r in rows] != expected_steps:
        raise ValueError("Continuation trajectory is incomplete, duplicated or out of order")


def binary_digest(path, expected):
    path = Path(path)
    if path.is_file():
        payload = path.read_bytes()
    else:
        with gzip.open(str(path) + ".gz", "rb") as stream:
            payload = stream.read()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError("Archived native tensor digest differs: " + str(path))
    return actual


def owned_path(path, root):
    path = Path(path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Continuation tensor evidence is outside its own run")
    return path


def canonical_transition(row, storage_root):
    result = copy.deepcopy(row)
    result.pop("inference_elapsed_ns")
    for field in ("observation_metadata", "candidates_metadata"):
        metadata_path = owned_path(result.pop(field), storage_root)
        binary = read(metadata_path)["binary"]
        if not binary["file"] or Path(binary["file"]).name != binary["file"]:
            raise ValueError("Native tensor metadata must name a binary basename")
        result[field] = str(metadata_path.relative_to(storage_root.resolve()))
        result[field + "_sha256"] = binary_digest(metadata_path.parent / binary["file"], binary["sha256"])
    if result["guidance"] is not None:
        guide = result["guidance"]
        path = owned_path(guide.pop("sampling_binary"), storage_root)
        binary_digest(path, guide["sampling_binary_sha256"])
        guide["sampling_binary"] = str(path.relative_to(storage_root.resolve()))
    return result


def run(original, resumed, output):
    original, resumed = original.resolve(), resumed.resolve()
    if output.exists():
        raise ValueError("Resume report must be a fresh path")
    left, right = read(original / "run.json"), read(resumed / "run.json")
    if any(r.get("kind") != "native-v2-live-recurrent-ppo" or r.get("status") != "completed" for r in (left, right)):
        raise ValueError("Both live-PPO runs must have completed")
    checkpoint = Path(right["resume_from"]).resolve()
    entries = [c for c in left["checkpoints"] if c["status"] == "saved" and Path(c["path"]).resolve() == checkpoint]
    if len(entries) != 1:
        raise ValueError("Continuation did not resume an original saved checkpoint")
    _, boundary = saved_checkpoint(entries[0])
    if (right["restored_transitions"] != boundary["transitions"] or
            right["restored_update"] != boundary["update"] or "imitation_import" in right or
            left.get("initial_policy") != right.get("initial_policy")):
        raise ValueError("Resume boundary or supervised ancestry differs")
    for key in ("trainer_sha256", "engine_sha256", "financial_features", "observation_schema_id", "guidance", "rollout_steps"):
        if left[key] != right[key]:
            raise ValueError("Resume runtime differs: " + key)
    updates_left = [{k: v for k, v in u.items() if k != "elapsed_ns"}
                    for u in left["updates"] if u["update"] > boundary["update"]]
    updates_right = [{k: v for k, v in u.items() if k != "elapsed_ns"} for u in right["updates"]]
    if not updates_left or updates_left != updates_right:
        raise ValueError("Native PPO continuation update metrics differ")
    rows_left = [json.loads(line) for line in (original / "trajectory.jsonl").read_text().splitlines()]
    rows_left = [row for row in rows_left if row["step"] > boundary["transitions"]]
    rows_right = [json.loads(line) for line in (resumed / "trajectory.jsonl").read_text().splitlines()]
    if not rows_left or len(rows_left) != len(rows_right):
        raise ValueError("Resumed trajectory length differs")
    final_update = left["updates"][-1]["update"]
    for updates, rows in ((updates_left, rows_left), (updates_right, rows_right)):
        check_coverage(updates, rows, boundary, final_update, left["rollout_steps"])
    trace_hash = hashlib.sha256()
    for a, b in zip(rows_left, rows_right):
        a, b = canonical_transition(a, original), canonical_transition(b, resumed)
        if a != b:
            raise ValueError("Live continuation differs at step " + str(a["step"]))
        trace_hash.update(json.dumps(a, sort_keys=True, allow_nan=False).encode() + b"\n")
    final_paths = []
    for record in (left, right):
        entries = [c for c in record["checkpoints"] if c["status"] == "saved" and c["update"] == final_update]
        if len(entries) != 1:
            raise ValueError("Both continuations need a final reset checkpoint")
        path, manifest = saved_checkpoint(entries[0])
        if manifest["compatibility"] != boundary["compatibility"]:
            raise ValueError("Final checkpoint compatibility differs")
        if manifest["transitions"] != final_update * left["rollout_steps"]:
            raise ValueError("Final checkpoint transition counter differs")
        final_paths.append(path / "trainer.pt")
    native = compare(*final_paths)
    if fingerprint(checkpoint_state(final_paths[1])) != native["exact_state_sha256"]:
        raise ValueError("Native checkpoint state bytes differ")
    if checkpoint_state(final_paths[0])["counters"][0].item() != final_update:
        raise ValueError("Native archive update counter differs from recorded continuation")
    report = {"status": "passed", "kind": "exact-live-v2-warm-start-resume-comparison",
              "source": source_identity(), "audit_sha256": digest(__file__),
              "state_reader_sha256": digest(Path(__file__).with_name("v2_checkpoint_state.py")),
              "run_sha256": {"original": digest(original / "run.json"), "resumed": digest(resumed / "run.json")},
              "original": str(original), "resumed": str(resumed), "boundary_update": boundary["update"],
              "compared_updates": len(updates_left), "compared_transitions": len(rows_left),
              "canonical_trace_sha256": trace_hash.hexdigest(), "native_checkpoint": native,
              "initial_policy": left.get("initial_policy"),
              "ignored": ["wall-clock inference/update durations", "artifact directory names"],
              "checks": ["exact public input bytes and guided sampling masks", "behavior probabilities and actions",
                         "native economic transitions and rewards", "PPO update metrics",
                         "model tensors, Adam moments/options, recurrent state, counters and CPU/CUDA RNG"]}
    write_json(output, report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--resumed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.original, args.resumed, args.output)
