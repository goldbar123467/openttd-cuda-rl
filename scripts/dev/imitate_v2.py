#!/usr/bin/env python3
"""Orchestrate C++ supervised fitting of replay-verified human decisions."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time

from local import capture_source, host, positive, source_identity, write_json
from infer_v2 import checked_tensors, TENSOR_SCHEMA
from v2_onnx_package import FINANCIAL_FEATURES

DATASET_SCHEMA = "openttd-rl-development-human-imitation-dataset-1"
NATIVE_SCHEMA = "openttd-rl-development-v2-imitation-1"
OBSERVATION_SCHEMA = "v2-m15-public-development-finance-v1"
ORDERS_OBSERVATION_SCHEMA = "v2-m15-public-development-orders-v1"
ORDER_FEATURES = ("signed-log-orders-v1", "signed-log-orders-v2")
REPLAY_CHECKS = {"roads", "orders", "cash", "debt", "date", "vehicles", "stations", "depots", "command_cost_accounting"}


def artifact(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def checked_artifact(record):
    actual = artifact(record["path"])
    if actual["sha256"] != record["sha256"]:
        raise ValueError("Imitation evidence artifact hash differs")
    return actual


def prepare_dataset(dataset_path, output, *, financial_features=None):
    dataset = json.loads(dataset_path.read_text())
    from human_campaign_v2 import CAMPAIGN_SCHEMA, prepare_campaign_dataset, require_training_split
    if dataset.get("schema_version") == CAMPAIGN_SCHEMA:
        return prepare_campaign_dataset(dataset_path, output, financial_features=financial_features,
                                        prepare_single=prepare_dataset)
    if (dataset.get("schema_version") != DATASET_SCHEMA or dataset.get("source_kind") != "human" or
            dataset.get("observation_schema_id") not in (OBSERVATION_SCHEMA, ORDERS_OBSERVATION_SCHEMA)):
        raise ValueError("Only native finance observations from human replay are accepted")
    orders = dataset["observation_schema_id"] == ORDERS_OBSERVATION_SCHEMA
    if orders and (dataset.get("action_semantics") != "orders-v1" or dataset.get("observation_mode") != "orders-v1" or
                   dataset.get("financial_features") != "signed-log-orders-v1"):
        raise ValueError("Orders dataset requires versioned observation/action/preprocessing metadata")
    # The immutable replay names its original compatible reader. Both explicit
    # model versions consume the same public tensors and exact native actions.
    if financial_features is not None and orders != (financial_features in ORDER_FEATURES):
        raise ValueError("Dataset observation/action semantics and model preprocessing differ")
    replay = dataset["replay_validation"]
    if replay.get("status") != "passed":
        raise ValueError("Human replay verification must pass before imitation")
    replay_artifact = checked_artifact(replay)
    replay_report = json.loads(Path(replay_artifact["path"]).read_text())
    required_checks = REPLAY_CHECKS | ({"tick", "finance"} if orders else set())
    if (replay_report.get("schema_version") != "openttd-rl-development-human-replay-validation-1" or
            replay_report.get("status") != "passed" or not required_checks <= replay_report.get("checks", {}).keys() or
            any(value is not True for value in replay_report["checks"].values())):
        raise ValueError("Referenced native replay report did not pass every equivalence check")
    require_training_split(dataset)
    if replay_report["source_recording"] != dataset["source_recording"]:
        raise ValueError("Replay and imitation refer to different recordings")
    for path, digest in replay_report["inputs"].items():
        checked_artifact({"path": path, "sha256": digest})
    recording_ref = dataset["source_recording"]
    recording = Path(recording_ref.get("runtime_copy", recording_ref["path"])).resolve(strict=True)
    recording_log = artifact(recording / "save/autosave/commands-out.log")
    if recording_log["sha256"] != dataset["source_recording"]["sha256"]:
        raise ValueError("Original recording command log hash differs")
    recording_artifact = {**dataset["source_recording"], "command_log": recording_log}
    records = dataset["records"]
    replay_root = Path(replay_artifact["path"]).parent
    if records != json.loads((replay_root / "samples.json").read_text()):
        raise ValueError("Imitation labels differ from native replay exported samples")
    command_rows = list(map(json.loads, (replay_root / "commands.jsonl").read_text().splitlines()))
    commands = {entry["source_command_index"]: entry for entry in command_rows}
    if len(commands) != len(command_rows) or len(command_rows) != replay_report["command_count"]:
        raise ValueError("Native replay command identities/count differ")
    if orders:
        if (replay_report.get("observation_mode") != "orders-v1" or
                replay_report.get("observation_schema_id") != ORDERS_OBSERVATION_SCHEMA):
            raise ValueError("Replay report and order dataset semantics differ")
        # Recheck at consumption as well as export: no caller can replace an
        # operation/source mapping while retaining only its greedy row label.
        from replay_human import build_events, validate_samples
        replay_config = json.loads((replay_root / "config.json").read_text())
        authoritative_events, _ = build_events(Path(recording_log["path"]), replay_report["checkpoint"],
                                              replay_report["checkpoint_occurrence"], "orders-v1")
        if (replay_config["events"] != authoritative_events or
                replay_report.get("checkpoint_log_line") != authoritative_events[-1]["line"]):
            raise ValueError("Replay events or checkpoint differ from the hash-verified recording log")
        validate_samples(records, command_rows, replay_config["events"], "orders-v1")
    if not 1 <= len(records) <= 512:
        raise ValueError("Small imitation test requires 1..512 supported examples")
    seen, games, lines, archived = set(), set(), [NATIVE_SCHEMA], []
    tensors = output / "tensors"
    tensors.mkdir()
    for index, record in enumerate(records):
        game, sample = str(record["game_id"]), str(record["sample_id"])
        if (record.get("split") != "train" or not game or not sample or
                any(c in game + sample for c in "\t\r\n") or (game, sample) in seen):
            raise ValueError("Imitation must contain unique training-only game/sample identities")
        seen.add((game, sample)); games.add(game)
        if type(record.get("source_command_index")) is not int or record["source_command_index"] < 0:
            raise ValueError("Human label lacks its source command index")
        if type(record.get("command_cost")) is not int:
            raise ValueError("Human label lacks confirmed integer command cost")
        command = commands.get(record["source_command_index"], {})
        if command.get("succeeded") is not True or command.get("command_cost") != record["command_cost"]:
            raise ValueError("Human label lacks a matching successful native command result")
        if command["after_cash"] - command["before_cash"] != command["after_loan"] - command["before_loan"] - command["command_cost"]:
            raise ValueError("Human label command cash/principal accounting differs")
        observation = json.loads(Path(record["observation_path"]).read_text())
        response = {"status": "OK", "tensors": {"schema_version": TENSOR_SCHEMA,
                    "token": observation["token"], "company_id": observation["company_id"],
                    "observation": record["observation_metadata_path"], "candidates": record["candidate_metadata_path"]}}
        obs_path, candidate_path, native_records, _ = checked_tensors(response, observation, observation_mode="orders-v1" if orders else "finance-v1")
        if (obs_path.resolve() != Path(record["observation_tensor_path"]).resolve() or
                candidate_path.resolve() != Path(record["candidate_tensor_path"]).resolve()):
            raise ValueError("Human replay metadata points at different binary tensors")
        action, family, legal = record["action_row"], record["action_family"], record["legal_rows"]
        if type(action) is not int or type(family) is not int or not 0 <= action < 4096 or not 0 <= family < 12:
            raise ValueError("Human label is outside native candidate inventory")
        if action not in native_records or native_records[action]["stable_key"] != record["candidate_key"]:
            raise ValueError("Human label does not match the native stable candidate key")
        if (not isinstance(legal, list) or not legal or any(type(row) is not int or not 0 <= row < 4096 for row in legal) or
                legal != sorted(set(legal)) or action not in legal):
            raise ValueError("Exact legal rows are invalid or exclude human label")
        copied = {}
        for name, size in (("observation", 2182927), ("candidate", 790528)):
            source = Path(record[name + "_tensor_path"]).resolve(strict=True)
            data = source.read_bytes()
            if len(data) != size:
                raise ValueError("Human replay tensor size differs")
            if name == "candidate":
                mask = data[-4096:]
                if any(value not in (0, 1) for value in mask) or legal != [row for row, value in enumerate(mask) if value]:
                    raise ValueError("Exact native legal mask differs from human replay manifest")
                if struct.unpack_from("<I", data, 4096 * 32 * 4 + action * 16 * 4)[0] != family:
                    raise ValueError("Human replay family differs from candidate parameters")
            target = tensors / f"{index:04d}-{name}.bin"
            target.write_bytes(data)
            copied[name] = artifact(target)
        # Save the full label/evidence row separately; the native service reads
        # only bounded paths, indices and the exact observed mask.
        archived.append({**record, "archived_tensors": copied})
        lines.append("\t".join([sample, game, copied["observation"]["path"], copied["candidate"]["path"],
                                 str(action), str(family), ",".join(map(str, legal))]))
    manifest = output / "native-imitation.tsv"
    manifest.write_text("\n".join(lines) + "\n")
    write_json(output / "labels.json", {"records": archived})
    return {"schema_version": DATASET_SCHEMA, "source_kind": "human", "split": "training_only",
            "observation_schema_id": dataset["observation_schema_id"],
            "action_semantics": "orders-v1" if orders else "legacy",
            "dataset_declared_financial_features": dataset.get("financial_features"),
            "model_financial_features": financial_features,
            "games": sorted(games), "example_count": len(records), "manifest": artifact(dataset_path),
            "native_manifest": artifact(manifest), "replay_validation": replay_artifact,
            "source_recording": recording_artifact, "labels": artifact(output / "labels.json")}


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {"kind": "native-v2-human-imitation", "status": "running", "source": source_identity(),
              "runtime": host(), "device": args.device, "seed": args.seed, "epochs": args.epochs,
              "learning_rate": args.learning_rate, "financial_features": args.financial_features,
              "observation_schema_id": ORDERS_OBSERVATION_SCHEMA if args.financial_features in ORDER_FEATURES else OBSERVATION_SCHEMA,
              "action_semantics": "orders-v1" if args.financial_features in ORDER_FEATURES else "legacy", "guidance": "none",
              "context": "independent-reset", "trainer": artifact(args.trainer),
              "objective": "mean negative log likelihood of exact native human candidate; no critic labels",
              "limitations": ["Sparse supported decisions reset recurrent state independently.",
                              "Training accuracy is a fit check, not evaluation on held-out games.",
                              "No unobserved borrowing choice or inter-command gap becomes a human label."]}
    write_json(output / "run.json", record)
    started = time.monotonic()
    try:
        record["source_capture"] = capture_source(output / "source")
        record["dataset"] = prepare_dataset(args.dataset.resolve(), output, financial_features=args.financial_features)
        model = output / "inference-weights.pt"
        command = [str(args.trainer.resolve()), "--device", args.device, "--seed", str(args.seed),
                   "--epochs", str(args.epochs), "--learning-rate", str(args.learning_rate),
                   "--financial-features", args.financial_features, "--manifest", record["dataset"]["native_manifest"]["path"],
                   "--output", str(model)]
        record["command"] = command
        write_json(output / "run.json", record)
        with (output / "native-metrics.jsonl").open("x") as metrics, (output / "trainer.log").open("x") as log:
            subprocess.run(command, stdout=metrics, stderr=log, check=True)
        events = [json.loads(line) for line in (output / "native-metrics.jsonl").read_text().splitlines()]
        result = events[-1]
        if (result["event"] != "completed" or result["device"] != args.device or
                result["examples"] != record["dataset"]["example_count"] or not result["finite_gradients"] or
                not result["exact_legal_masks"] or result["final"]["loss"] >= result["initial"]["loss"] or
                (args.device == "cuda:0" and not result["cpu_cuda_compared"])):
            raise ValueError("Native imitation verification result differs")
        record["result"] = result
        record["model"] = {**artifact(model), "financial_features": args.financial_features,
                           "observation_schema_id": record["observation_schema_id"], "action_semantics": record["action_semantics"]}
        record["status"] = "completed"
    except BaseException as error:
        record["status"] = "failed"
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        record["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "run.json", record)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trainer", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--epochs", type=positive, default=20)
    parser.add_argument("--learning-rate", type=float, default=0.0003)
    parser.add_argument("--financial-features", choices=FINANCIAL_FEATURES, default="signed-log-actions-v1")
    run(parser.parse_args())
