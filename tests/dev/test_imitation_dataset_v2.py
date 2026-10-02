"""Fail closed before supervised training when native human evidence is invalid."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from imitate_v2 import DATASET_SCHEMA, OBSERVATION_SCHEMA, ORDERS_OBSERVATION_SCHEMA, prepare_dataset


class ImitationDatasetTests(unittest.TestCase):
    def test_consistent_sample_and_config_packet_edits_cannot_override_recording_log(self):
        from replay_human import build_events
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            recording = root / "recording"
            log = recording / "save/autosave/commands-out.log"
            log.parent.mkdir(parents=True)
            log.write_text("\n".join([
                "[time] save: 00000001; 00; initial.sav",
                "[time] cmd: 00000002; 00; 00; 0000002e; 00001080; 010000000061000100FE00000000FFFF (CmdInsertOrder)",
                "[time] save: 00000003; 00; done.sav"]))
            log_sha = hashlib.sha256(log.read_bytes()).hexdigest()
            source = {"path": str(recording), "sha256": log_sha}
            events, _ = build_events(log, "done.sav", "unique", "orders-v1")
            report = root / "report.json"
            report.write_text(json.dumps({
                "schema_version": "openttd-rl-development-human-replay-validation-1", "status": "passed",
                "checks": {key: True for key in ("roads", "orders", "cash", "debt", "date", "tick", "finance",
                    "vehicles", "stations", "depots", "command_cost_accounting")},
                "inputs": {str(log): log_sha}, "source_recording": source, "command_count": 1,
                "checkpoint": "done.sav", "checkpoint_occurrence": "unique", "checkpoint_log_line": 3,
                "observation_mode": "orders-v1", "observation_schema_id": ORDERS_OBSERVATION_SCHEMA}))
            (root / "commands.jsonl").write_text(json.dumps({"source_command_index": 2}) + "\n")
            dataset = root / "dataset.json"
            for corrupt in (False, True):
                # Alter both metadata copies consistently while the authentic
                # original command log and its verified hash remain unchanged.
                if corrupt:
                    events[0]["payload"] = "00"
                samples = [{"source_command_index": 2, "source_command": events[0]}]
                (root / "samples.json").write_text(json.dumps(samples))
                (root / "config.json").write_text(json.dumps({"events": events}))
                dataset.write_text(json.dumps({"schema_version": DATASET_SCHEMA, "source_kind": "human",
                    "observation_schema_id": ORDERS_OBSERVATION_SCHEMA, "observation_mode": "orders-v1",
                    "action_semantics": "orders-v1", "financial_features": "signed-log-orders-v1",
                    "source_recording": source, "records": samples,
                    "replay_validation": {"status": "passed", "path": str(report),
                        "sha256": hashlib.sha256(report.read_bytes()).hexdigest()}}))
                for mode in ("signed-log-orders-v1", "signed-log-orders-v2"):
                    with self.subTest(corrupt=corrupt, mode=mode), patch("replay_human.validate_samples", side_effect=ValueError("reached exact sample validator")) as validator:
                        message = "hash-verified recording log" if corrupt else "reached exact sample validator"
                        with self.assertRaisesRegex(ValueError, message):
                            prepare_dataset(dataset, root, financial_features=mode)
                        self.assertEqual(validator.call_count, 0 if corrupt else 1)
                self.assertEqual(hashlib.sha256(log.read_bytes()).hexdigest(), log_sha)

    def test_v2_reader_accepts_immutable_v1_order_dataset_but_still_requires_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = root / "dataset.json"
            dataset.write_text(json.dumps({"schema_version": DATASET_SCHEMA, "source_kind": "human",
                "observation_schema_id": ORDERS_OBSERVATION_SCHEMA, "observation_mode": "orders-v1",
                "action_semantics": "orders-v1", "financial_features": "signed-log-orders-v1",
                "replay_validation": {"status": "failed"}}))
            original = dataset.read_bytes()
            for mode in ("signed-log-orders-v1", "signed-log-orders-v2"):
                with self.assertRaisesRegex(ValueError, "Replay verification|replay verification"):
                    prepare_dataset(dataset, root, financial_features=mode)
                self.assertEqual(original, dataset.read_bytes())

    def test_order_schema_cannot_use_legacy_model_preprocessing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = root / "dataset.json"
            dataset.write_text(json.dumps({"schema_version": DATASET_SCHEMA, "source_kind": "human",
                "observation_schema_id": ORDERS_OBSERVATION_SCHEMA, "observation_mode": "orders-v1",
                "action_semantics": "orders-v1", "financial_features": "signed-log-orders-v1"}))
            with self.assertRaisesRegex(ValueError, "model preprocessing differ"):
                prepare_dataset(dataset, root, financial_features="signed-log-actions-v1")
            value = json.loads(dataset.read_text())
            del value["action_semantics"]
            dataset.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "versioned observation/action"):
                prepare_dataset(dataset, root, financial_features="signed-log-orders-v1")

    def test_order_replay_requires_tick_and_finance_checks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / "report.json"
            report.write_text(json.dumps({"schema_version": "openttd-rl-development-human-replay-validation-1",
                "status": "passed", "checks": {key: True for key in
                ("roads", "orders", "cash", "debt", "date", "vehicles", "stations", "depots", "command_cost_accounting")}}))
            dataset = root / "dataset.json"
            dataset.write_text(json.dumps({"schema_version": DATASET_SCHEMA, "source_kind": "human",
                "observation_schema_id": ORDERS_OBSERVATION_SCHEMA, "observation_mode": "orders-v1",
                "action_semantics": "orders-v1", "financial_features": "signed-log-orders-v1",
                "replay_validation": {"status": "passed", "path": str(report), "sha256": hashlib.sha256(report.read_bytes()).hexdigest()}}))
            with self.assertRaisesRegex(ValueError, "every equivalence check"):
                prepare_dataset(dataset, root)

    def test_passed_claim_cannot_override_failed_replay_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / "report.json"
            report.write_text(json.dumps({"schema_version": "openttd-rl-development-human-replay-validation-1",
                                          "status": "failed", "checks": {"cash": False}}))
            dataset = root / "dataset.json"
            dataset.write_text(json.dumps({"schema_version": DATASET_SCHEMA, "source_kind": "human",
                "observation_schema_id": OBSERVATION_SCHEMA,
                "replay_validation": {"status": "passed", "path": str(report), "sha256": hashlib.sha256(report.read_bytes()).hexdigest()}}))
            with self.assertRaisesRegex(ValueError, "Referenced native replay report"):
                prepare_dataset(dataset, root)

    def test_scripted_or_synthetic_labels_are_not_human(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for kind in ("scripted", "synthetic", "llm"):
                dataset = root / "dataset.json"
                dataset.write_text(json.dumps({"schema_version": DATASET_SCHEMA, "source_kind": kind,
                                              "observation_schema_id": OBSERVATION_SCHEMA}))
                with self.assertRaisesRegex(ValueError, "human replay"):
                    prepare_dataset(dataset, root)

    def test_mutated_replay_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = root / "report.json"
            report.write_text("{}")
            dataset = root / "dataset.json"
            dataset.write_text(json.dumps({"schema_version": DATASET_SCHEMA, "source_kind": "human",
                "observation_schema_id": OBSERVATION_SCHEMA,
                "replay_validation": {"status": "passed", "path": str(report), "sha256": "0" * 64}}))
            with self.assertRaisesRegex(ValueError, "hash differs"):
                prepare_dataset(dataset, root)


if __name__ == "__main__":
    unittest.main()
