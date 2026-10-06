#!/usr/bin/env python3
"""Qualify development/test human records without creating trainer input."""
import argparse
from collections import Counter
import json
from pathlib import Path

from human_campaign_v2 import artifact, checked, capture_identity
from imitate_v2 import DATASET_SCHEMA, ORDERS_OBSERVATION_SCHEMA, REPLAY_CHECKS
from infer_v2 import checked_tensors, TENSOR_SCHEMA
from local import capture_source, source_identity, write_json
from replay_human import build_events, validate_samples

EVALUATION_SCHEMA = "openttd-rl-development-human-evaluation-dataset-1"


def validate(dataset_path, split):
    if split not in ("development", "test"):
        raise ValueError("Evaluation audit requires a development or test partition")
    dataset_ref = artifact(dataset_path)
    dataset = json.loads(Path(dataset_ref["path"]).read_text())
    if (dataset.get("schema_version") != DATASET_SCHEMA or dataset.get("source_kind") != "human" or
            dataset.get("observation_schema_id") != ORDERS_OBSERVATION_SCHEMA or
            dataset.get("observation_mode") != "orders-v1" or dataset.get("action_semantics") != "orders-v1" or
            dataset.get("financial_features") != "signed-log-orders-v1"):
        raise ValueError("Evaluation audit requires the exact native order replay schema")
    seed, metadata_ref, transfer_ref = capture_identity(dataset, expected_split=split)
    replay_ref = checked(dataset["replay_validation"])
    replay = json.loads(Path(replay_ref["path"]).read_text())
    checks = REPLAY_CHECKS | {"tick", "finance"}
    if (dataset["replay_validation"].get("status") != "passed" or replay.get("status") != "passed" or
            replay.get("schema_version") != "openttd-rl-development-human-replay-validation-1" or
            not checks <= replay.get("checks", {}).keys() or any(value is not True for value in replay["checks"].values()) or
            replay.get("source_recording") != dataset["source_recording"] or
            replay.get("observation_mode") != "orders-v1" or replay.get("observation_schema_id") != ORDERS_OBSERVATION_SCHEMA):
        raise ValueError("Evaluation requires every native checkpoint check")
    for path, digest in replay["inputs"].items():
        checked({"path": path, "sha256": digest})
    source = dataset["source_recording"]
    recording = Path(source.get("runtime_copy", source["path"])).resolve(strict=True)
    transfer = json.loads(Path(transfer_ref["path"]).read_text(encoding="utf-8-sig"))
    for row in transfer["files"]:
        checked({"path": str(recording / row["file"]), "sha256": row["sha256"]})
    log_ref = artifact(recording / "save/autosave/commands-out.log")
    if log_ref["sha256"] != source["sha256"]:
        raise ValueError("Original recording command log differs")
    root = Path(replay_ref["path"]).parent
    records = dataset["records"]
    if records != json.loads((root / "samples.json").read_text()):
        raise ValueError("Evaluation records differ from the immutable native replay")
    commands = [json.loads(line) for line in (root / "commands.jsonl").read_text().splitlines()]
    if len(commands) != replay["command_count"] or any(row["succeeded"] is not True or
            row["after_cash"] - row["before_cash"] != row["after_loan"] - row["before_loan"] - row["command_cost"] for row in commands):
        raise ValueError("Evaluation command count or accounting differs")
    events, _ = build_events(Path(log_ref["path"]), replay["checkpoint"], replay["checkpoint_occurrence"], "orders-v1")
    if json.loads((root / "config.json").read_text())["events"] != events or replay["checkpoint_log_line"] != events[-1]["line"]:
        raise ValueError("Evaluation event packets differ from the original recording")
    operations = validate_samples(records, commands, events, "orders-v1")
    seen, native_games, exported = set(), set(), []
    for row in records:
        identity = row["game_id"], row["sample_id"]
        if identity in seen or row.get("split") != "train":
            raise ValueError("Native record identity or legacy export metadata differs")
        seen.add(identity)
        native_games.add(row["game_id"])
        observation = json.loads(Path(row["observation_path"]).read_text())
        response = {"status": "OK", "tensors": {"schema_version": TENSOR_SCHEMA,
                    "token": observation["token"], "company_id": observation["company_id"],
                    "observation": row["observation_metadata_path"], "candidates": row["candidate_metadata_path"]}}
        obs, candidates, inventory, mask = checked_tensors(response, observation, observation_mode="orders-v1")
        if (obs.resolve() != Path(row["observation_tensor_path"]).resolve() or
                candidates.resolve() != Path(row["candidate_tensor_path"]).resolve() or
                row["legal_rows"] != [index for index, value in enumerate(mask) if value] or
                row["action_row"] not in inventory or
                inventory[row["action_row"]]["stable_key"] != row["candidate_key"] or
                inventory[row["action_row"]]["family_index"] != row["action_family"]):
            raise ValueError("Evaluation target, tensor paths or exact legal mask differs")
        exported.append({**row, "split": split, "native_replay_record_split": row["split"],
                         "verified_tensors": {"observation": artifact(obs), "candidates": artifact(candidates)}})
    if len(native_games) != 1 or not records or dict(Counter(row["operation"] for row in exported)) != operations:
        raise ValueError("Evaluation must bind one complete native game and its exact operation inventory")
    for reference in (dataset_ref, replay_ref, metadata_ref, transfer_ref):
        checked(reference)
    return {"schema_version": EVALUATION_SCHEMA, "source_kind": "human", "split": split,
            "observation_schema_id": ORDERS_OBSERVATION_SCHEMA, "action_semantics": "orders-v1",
            "financial_features": "signed-log-orders-v2", "seed": seed, "native_game_id": next(iter(native_games)),
            "source_dataset": dataset_ref, "replay_validation": replay_ref,
            "recording_metadata": metadata_ref, "capture_transfer": transfer_ref,
            "example_count": len(exported), "supported_operations": operations, "records": exported}


def audit(dataset_path, output, split):
    output.mkdir(parents=True, exist_ok=False)
    report = {"kind": "native-human-evaluation-audit", "status": "running", "split": split,
              "source": source_identity(), "training_run": False,
              "claim": "Read-only whole-game integrity audit; no model scores, fitting or trainer manifest"}
    try:
        report["source_capture"] = capture_source(output / "source-provenance")
        dataset = validate(dataset_path, split)
        write_json(output / "dataset.json", dataset)
        report.update(status="passed", example_count=dataset["example_count"],
                      supported_operations=dataset["supported_operations"], dataset=artifact(output / "dataset.json"))
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=("development", "test"), required=True)
    args = parser.parse_args()
    report = audit(args.dataset.resolve(), args.output.resolve(), args.split)
    print(json.dumps({key: report[key] for key in ("status", "split", "example_count")}))
