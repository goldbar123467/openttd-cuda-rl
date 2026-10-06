#!/usr/bin/env python3
"""Assemble whole-game human data through the existing exact replay consumer."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from local import capture_source, source_identity, write_json

CAMPAIGN_SCHEMA = "openttd-rl-development-human-imitation-campaign-1"
SINGLE_SCHEMA = "openttd-rl-development-human-imitation-dataset-1"
OBSERVATION_SCHEMA = "v2-m15-public-development-orders-v1"
NATIVE_SCHEMA = "openttd-rl-development-v2-imitation-1"
MODES = ("signed-log-orders-v1", "signed-log-orders-v2", "signed-log-orders-v3")


def artifact(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def checked(reference):
    actual = artifact(reference["path"])
    if actual["sha256"] != reference["sha256"]:
        raise ValueError("Campaign evidence artifact hash differs")
    return actual


def recording_split(dataset):
    """Respect the whole-game partition bound into the preserved capture."""
    source = dataset["source_recording"]
    root = Path(source.get("runtime_copy", source["path"])).resolve(strict=True)
    split = dataset.get("split", "train")
    transfer_path = root / "transfer.json"
    if transfer_path.is_file():
        transfer = json.loads(transfer_path.read_text(encoding="utf-8-sig"))
        bindings = [row for row in transfer["files"] if row["file"] == "preservation.json"]
        if len(bindings) > 1:
            raise ValueError("Whole-game preservation binding repeats")
        if bindings:
            reference = checked({"path": str(root / "preservation.json"), "sha256": bindings[0]["sha256"]})
            preserved = json.loads(Path(reference["path"]).read_text(encoding="utf-8-sig"))
            split = preserved.get("split", "train")
            if dataset.get("split", split) != split:
                raise ValueError("Dataset and preserved whole-game partition differ")
    if split not in ("train", "development", "test"):
        raise ValueError("Unknown whole-game partition")
    return split


def require_training_split(dataset):
    if recording_split(dataset) != "train":
        raise ValueError("Human training requires the preserved whole-game training partition")


def capture_identity(dataset, *, expected_split="train"):
    if recording_split(dataset) != expected_split:
        raise ValueError("Capture differs from the expected whole-game partition")
    source = dataset["source_recording"]
    root = Path(source.get("runtime_copy", source["path"])).resolve(strict=True)
    metadata_ref, transfer_ref = artifact(root / "recording.json"), artifact(root / "transfer.json")
    transfer = json.loads(Path(transfer_ref["path"]).read_text(encoding="utf-8-sig"))
    metadata_rows = [row for row in transfer["files"] if row["file"] == "recording.json"]
    if (transfer.get("hashes_verified") is not True or len(metadata_rows) != 1 or
            metadata_rows[0]["sha256"] != metadata_ref["sha256"]):
        raise ValueError("Campaign recording metadata differs from preserved transfer")
    metadata = json.loads(Path(metadata_ref["path"]).read_text(encoding="utf-8-sig"))
    if (metadata.get("status") != "raw_capture_completed" or metadata.get("exit_code") != 0 or
            metadata.get("version") != "15.3" or type(metadata.get("seed")) is not int):
        raise ValueError("Campaign requires completed pinned captures with recorded seeds")
    return metadata["seed"], metadata_ref, transfer_ref


def prepare_campaign_dataset(dataset_path, output, *, financial_features, prepare_single):
    parent_ref = artifact(dataset_path)
    manifest = json.loads(Path(parent_ref["path"]).read_text())
    if (manifest.get("schema_version") != CAMPAIGN_SCHEMA or manifest.get("source_kind") != "human" or
            manifest.get("split") != "training_only" or manifest.get("observation_schema_id") != OBSERVATION_SCHEMA or
            manifest.get("action_semantics") != "orders-v1" or financial_features not in MODES or
            manifest.get("financial_features") != financial_features):
        raise ValueError("Campaign requires explicit training-only order semantics/preprocessing")
    games = manifest.get("games")
    if not isinstance(games, list) or not 1 <= len(games) <= 10:
        raise ValueError("Campaign requires 1..10 complete games")
    ids, seeds, logs, identities = set(), set(), set(), set()
    archived, lines, sources = [], [NATIVE_SCHEMA], []
    for game in games:
        identity = game.get("game_id", "")
        if (not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", identity) or
                identity in ids or game.get("split") != "train"):
            raise ValueError("Campaign game IDs must be unique and whole-game training-only")
        ids.add(identity)
        dataset_ref = checked(game["dataset"])
        child = json.loads(Path(dataset_ref["path"]).read_text())
        if child.get("schema_version") != SINGLE_SCHEMA or child.get("observation_schema_id") != OBSERVATION_SCHEMA:
            raise ValueError("Campaign children must be individual native order datasets")
        seed, metadata_ref, transfer_ref = capture_identity(child)
        if (seed != game.get("seed") or seed in seeds or
                metadata_ref != checked(game["recording_metadata"]) or transfer_ref != checked(game["capture_transfer"])):
            raise ValueError("Campaign seed/capture identity differs or repeats")
        seeds.add(seed)
        log_hash = child["source_recording"]["sha256"]
        if log_hash in logs:
            raise ValueError("Campaign repeats one recording under different game IDs")
        logs.add(log_hash)
        child_output = output / "games" / identity
        child_output.mkdir(parents=True, exist_ok=False)
        # This is the original validator, including manual-checkpoint equality,
        # original packet matching, exact candidate masks and tensor hashes.
        prepared = prepare_single(Path(dataset_ref["path"]), child_output, financial_features=financial_features)
        if len(prepared["games"]) != 1 or prepared["games"][0] != game.get("native_game_id"):
            raise ValueError("One campaign entry must bind exactly one original native game")
        labels = json.loads(Path(prepared["labels"]["path"]).read_text())["records"]
        native = Path(prepared["native_manifest"]["path"]).read_text().splitlines()
        if not native or native[0] != NATIVE_SCHEMA or len(native) != len(labels) + 1:
            raise ValueError("Campaign child native manifest/count differs")
        for label in labels:
            key = label["game_id"], label["sample_id"]
            if key in identities:
                raise ValueError("Campaign repeats a native game/sample identity")
            identities.add(key)
            archived.append({**label, "campaign_game_id": identity})
        lines.extend(native[1:])
        sources.append({"game_id": identity, "seed": seed, "split": "train", "dataset": dataset_ref,
                        "recording_metadata": metadata_ref, "capture_transfer": transfer_ref, "prepared": prepared})
    if not 1 <= len(archived) <= 512:
        raise ValueError("Campaign requires 1..512 verified supported examples")
    # Recheck the immutable parent and every source after assembly.
    checked(parent_ref)
    for source in sources:
        for name in ("dataset", "recording_metadata", "capture_transfer"):
            checked(source[name])
    native_path = output / "native-imitation.tsv"
    native_path.write_text("\n".join(lines) + "\n")
    write_json(output / "labels.json", {"records": archived})
    return {"schema_version": CAMPAIGN_SCHEMA, "source_kind": "human", "split": "training_only",
            "observation_schema_id": OBSERVATION_SCHEMA, "action_semantics": "orders-v1",
            "model_financial_features": financial_features, "games": sorted(ids), "example_count": len(archived),
            "manifest": parent_ref, "native_manifest": artifact(native_path),
            "labels": artifact(output / "labels.json"), "sources": sources,
            "supported_operations": dict(Counter(label["operation"] for label in archived))}


def assemble(games, output, financial_features):
    from imitate_v2 import prepare_dataset
    output.mkdir(parents=True, exist_ok=False)
    report = {"kind": "native-human-campaign-assembly", "status": "running", "source": source_identity(),
              "claim": "Validated whole training games; no training or inferred labels"}
    try:
        report["source_capture"] = capture_source(output / "source")
        entries = []
        for identity, path in games:
            reference = artifact(path)
            dataset = json.loads(Path(reference["path"]).read_text())
            seed, metadata, transfer = capture_identity(dataset)
            native_ids = sorted({row["game_id"] for row in dataset["records"]})
            if len(native_ids) != 1:
                raise ValueError("Each entry must be one native game")
            entries.append({"game_id": identity, "native_game_id": native_ids[0], "split": "train", "seed": seed,
                            "dataset": reference, "recording_metadata": metadata, "capture_transfer": transfer})
        manifest = {"schema_version": CAMPAIGN_SCHEMA, "source_kind": "human", "split": "training_only",
                    "observation_schema_id": OBSERVATION_SCHEMA, "action_semantics": "orders-v1",
                    "financial_features": financial_features, "games": entries}
        path = output / "dataset.json"
        write_json(path, manifest)
        validation = output / "validation"
        validation.mkdir()
        report["prepared"] = prepare_dataset(path, validation, financial_features=financial_features)
        report["status"] = "passed"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", nargs=2, action="append", required=True, metavar=("GAME_ID", "DATASET"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--financial-features", choices=MODES, default="signed-log-orders-v2")
    args = parser.parse_args()
    report = assemble(args.game, args.output.resolve(), args.financial_features)
    print(json.dumps({"status": report["status"], "examples": report["prepared"]["example_count"],
                      "games": report["prepared"]["games"]}))
