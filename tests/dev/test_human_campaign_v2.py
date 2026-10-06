"""Whole-game assembly cannot bypass the exact individual replay consumer."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
import human_campaign_v2 as campaign


class HumanCampaignTests(unittest.TestCase):
    def fixture(self, root, number, *, seed=None, count=1):
        recording = root / f"recording-{number}"
        recording.mkdir()
        metadata = recording / "recording.json"
        metadata.write_text(json.dumps({"status": "raw_capture_completed", "exit_code": 0,
                                       "version": "15.3", "seed": seed or number}))
        transfer = recording / "transfer.json"
        transfer.write_text(json.dumps({"hashes_verified": True,
            "files": [{"file": "recording.json", "sha256": campaign.artifact(metadata)["sha256"]}]}))
        native = f"native-{number}"
        records = [{"sample_id": f"command-{index}", "game_id": native, "split": "train",
                    "operation": "buy-bus", "action_row": 2560, "action_family": 5, "legal_rows": [2560]}
                   for index in range(count)]
        dataset = root / f"dataset-{number}.json"
        dataset.write_text(json.dumps({"schema_version": campaign.SINGLE_SCHEMA,
            "observation_schema_id": campaign.OBSERVATION_SCHEMA, "records": records,
            "source_recording": {"path": str(recording), "sha256": hashlib.sha256(str(number).encode()).hexdigest()}}))
        return {"game_id": f"game-{number}", "native_game_id": native, "split": "train", "seed": seed or number,
                "dataset": campaign.artifact(dataset), "recording_metadata": campaign.artifact(metadata),
                "capture_transfer": campaign.artifact(transfer)}

    def manifest(self, root, games):
        path = root / "campaign.json"
        path.write_text(json.dumps({"schema_version": campaign.CAMPAIGN_SCHEMA, "source_kind": "human",
            "split": "training_only", "observation_schema_id": campaign.OBSERVATION_SCHEMA,
            "action_semantics": "orders-v1", "financial_features": "signed-log-orders-v2", "games": games}))
        output = root / "output"
        output.mkdir()
        return path, output

    def validated_child(self, path, output, **kwargs):
        records = json.loads(path.read_text())["records"]
        native = output / "native-imitation.tsv"
        lines = [campaign.NATIVE_SCHEMA] + ["\t".join([row["sample_id"], row["game_id"], "obs.bin", "cand.bin",
                  "2560", "5", "2560"]) for row in records]
        native.write_text("\n".join(lines) + "\n")
        labels = output / "labels.json"
        labels.write_text(json.dumps({"records": records}))
        return {"games": sorted({row["game_id"] for row in records}), "example_count": len(records),
                "native_manifest": campaign.artifact(native), "labels": campaign.artifact(labels)}

    def prepare(self, path, output, child=None, mode="signed-log-orders-v2"):
        return campaign.prepare_campaign_dataset(path, output, financial_features=mode,
                                                   prepare_single=child or self.validated_child)

    def test_multiple_games_keep_original_identity_and_delegate_every_child(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, output = self.manifest(root, [self.fixture(root, 1), self.fixture(root, 2)])
            calls = []
            def child(path, output, **kwargs):
                calls.append((path, kwargs))
                return self.validated_child(path, output, **kwargs)
            prepared = self.prepare(path, output, child)
            labels = json.loads(Path(prepared["labels"]["path"]).read_text())["records"]
            self.assertEqual(len(calls), 2)
            self.assertEqual(prepared["example_count"], 2)
            self.assertEqual([row["game_id"] for row in labels], ["native-1", "native-2"])
            self.assertEqual([row["sample_id"] for row in labels], ["command-0", "command-0"])
            self.assertEqual([row["campaign_game_id"] for row in labels], ["game-1", "game-2"])
            self.assertEqual(prepared["supported_operations"], {"buy-bus": 2})
            self.assertEqual(len(Path(prepared["native_manifest"]["path"]).read_text().splitlines()), 3)

    def test_development_or_test_games_are_never_training_labels(self):
        for split in ("development", "test"):
            with self.subTest(split=split), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                game = self.fixture(root, 1)
                game["split"] = split
                path, output = self.manifest(root, [game])
                with self.assertRaisesRegex(ValueError, "training-only"):
                    self.prepare(path, output)
                self.assertFalse((output / "native-imitation.tsv").exists())

    def bind_capture_split(self, game, split):
        dataset = json.loads(Path(game["dataset"]["path"]).read_text())
        recording = Path(dataset["source_recording"]["path"])
        preservation = recording / "preservation.json"
        preservation.write_text(json.dumps({"split": split}))
        transfer_path = recording / "transfer.json"
        transfer = json.loads(transfer_path.read_text())
        transfer["files"].append({"file": "preservation.json", "sha256": campaign.artifact(preservation)["sha256"]})
        transfer_path.write_text(json.dumps(transfer))
        game["capture_transfer"] = campaign.artifact(transfer_path)
        return dataset, preservation

    def test_preserved_partition_cannot_be_relabelled_by_training_cli(self):
        for split in ("development", "test"):
            with self.subTest(split=split), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                game = self.fixture(root, 8)
                dataset, _ = self.bind_capture_split(game, split)
                self.assertEqual(campaign.recording_split(dataset), split)
                campaign.capture_identity(dataset, expected_split=split)
                with self.assertRaisesRegex(ValueError, "whole-game partition"):
                    campaign.capture_identity(dataset)
                with self.assertRaisesRegex(ValueError, "whole-game training"):
                    campaign.require_training_split(dataset)
                with self.assertRaisesRegex(ValueError, "whole-game partition"):
                    with patch.object(campaign, "capture_source", return_value={}), patch.object(campaign, "source_identity", return_value={}):
                        campaign.assemble([(game["game_id"], Path(game["dataset"]["path"]))],
                                          root / "assembly", "signed-log-orders-v2")
                self.assertFalse((root / "assembly/dataset.json").exists())

    def test_direct_imitation_refuses_development_capture_before_export(self):
        from imitate_v2 import prepare_dataset
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = self.fixture(root, 8)
            dataset, _ = self.bind_capture_split(game, "development")
            report = root / "report.json"
            report.write_text(json.dumps({"schema_version": "openttd-rl-development-human-replay-validation-1",
                "status": "passed", "checks": {key: True for key in ("roads", "orders", "cash", "debt", "date",
                    "tick", "finance", "vehicles", "stations", "depots", "command_cost_accounting")}}))
            dataset.update(source_kind="human", action_semantics="orders-v1", observation_mode="orders-v1",
                           financial_features="signed-log-orders-v1",
                           replay_validation={"status": "passed", **campaign.artifact(report)})
            path = Path(game["dataset"]["path"])
            path.write_text(json.dumps(dataset))
            with self.assertRaisesRegex(ValueError, "whole-game training"):
                prepare_dataset(path, root / "training-output", financial_features="signed-log-orders-v2")
            self.assertFalse((root / "training-output").exists())

    def test_partition_hash_changes_and_conflicting_declared_split_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = self.fixture(root, 8)
            dataset, preservation = self.bind_capture_split(game, "development")
            conflicting = {**dataset, "split": "train"}
            with self.assertRaisesRegex(ValueError, "partition differ"):
                campaign.recording_split(conflicting)
            preservation.write_text(json.dumps({"split": "train"}))
            with self.assertRaisesRegex(ValueError, "hash differs"):
                campaign.recording_split(dataset)

    def test_duplicate_seeds_and_relabelled_recordings_are_rejected(self):
        for kind in ("seed", "log"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                first = self.fixture(root, 1)
                second = self.fixture(root, 2, seed=1 if kind == "seed" else None)
                if kind == "log":
                    ref = Path(second["dataset"]["path"])
                    data = json.loads(ref.read_text())
                    data["source_recording"]["sha256"] = json.loads(Path(first["dataset"]["path"]).read_text())["source_recording"]["sha256"]
                    ref.write_text(json.dumps(data))
                    second["dataset"] = campaign.artifact(ref)
                path, output = self.manifest(root, [first, second])
                with self.assertRaisesRegex(ValueError, "repeats|seed/capture"):
                    self.prepare(path, output)

    def test_changed_child_dataset_or_metadata_is_rejected(self):
        for name in ("dataset", "recording_metadata"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                game = self.fixture(root, 1)
                ref = Path(game[name]["path"])
                ref.write_text(ref.read_text() + " ")
                path, output = self.manifest(root, [game])
                with self.assertRaisesRegex(ValueError, "hash differs|preserved transfer"):
                    self.prepare(path, output)

    def test_individual_validation_failure_cannot_produce_combined_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, output = self.manifest(root, [self.fixture(root, 1)])
            def invalid_child(*args, **kwargs):
                raise ValueError("native cash comparison failed")
            with self.assertRaisesRegex(ValueError, "cash comparison"):
                self.prepare(path, output, invalid_child)
            self.assertFalse((output / "native-imitation.tsv").exists())

    def test_aggregate_limit_and_reader_version_are_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, output = self.manifest(root, [self.fixture(root, 1, count=300), self.fixture(root, 2, count=300)])
            with self.assertRaisesRegex(ValueError, "1..512"):
                self.prepare(path, output)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, output = self.manifest(root, [self.fixture(root, 1)])
            with self.assertRaisesRegex(ValueError, "preprocessing"):
                self.prepare(path, output, mode="signed-log-orders-v1")

    def test_manifest_changed_during_consumption_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, output = self.manifest(root, [self.fixture(root, 1)])
            def changed_parent(child_path, child_output, **kwargs):
                path.write_text(path.read_text() + " ")
                return self.validated_child(child_path, child_output, **kwargs)
            with self.assertRaisesRegex(ValueError, "hash differs"):
                self.prepare(path, output, changed_parent)


if __name__ == "__main__":
    unittest.main()
