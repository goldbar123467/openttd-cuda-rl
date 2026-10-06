"""Evaluation data cannot become trainer input or bypass native integrity checks."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from audit_human_evaluation_v2 import EVALUATION_SCHEMA, validate
from human_campaign_v2 import artifact
from imitate_v2 import DATASET_SCHEMA, ORDERS_OBSERVATION_SCHEMA, prepare_dataset


class HumanEvaluationTests(unittest.TestCase):
    def test_training_partition_is_not_an_evaluation_export(self):
        with self.assertRaisesRegex(ValueError, "development or test"):
            validate(Path("unused.json"), "train")

    def test_evaluation_export_is_rejected_by_trainer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset = root / "evaluation.json"
            dataset.write_text(json.dumps({"schema_version": EVALUATION_SCHEMA, "source_kind": "human",
                                          "split": "development", "observation_schema_id": ORDERS_OBSERVATION_SCHEMA}))
            with self.assertRaises(ValueError):
                prepare_dataset(dataset, root / "trainer-input", financial_features="signed-log-orders-v2")
            self.assertFalse((root / "trainer-input").exists())

    def test_failed_native_finance_check_blocks_evaluation_even_with_passed_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            recording = root / "recording"
            recording.mkdir()
            metadata = recording / "recording.json"
            metadata.write_text(json.dumps({"status": "raw_capture_completed", "exit_code": 0,
                                           "version": "15.3", "seed": 8}))
            preservation = recording / "preservation.json"
            preservation.write_text(json.dumps({"split": "development"}))
            (recording / "transfer.json").write_text(json.dumps({"hashes_verified": True, "files": [
                {"file": "recording.json", "sha256": artifact(metadata)["sha256"]},
                {"file": "preservation.json", "sha256": artifact(preservation)["sha256"]}]}))
            source = {"path": str(recording), "sha256": "unused"}
            checks = {key: True for key in ("roads", "orders", "cash", "debt", "date", "tick", "finance",
                                           "vehicles", "stations", "depots", "command_cost_accounting")}
            checks["finance"] = False
            report = root / "report.json"
            report.write_text(json.dumps({"schema_version": "openttd-rl-development-human-replay-validation-1",
                "status": "passed", "checks": checks, "source_recording": source,
                "observation_mode": "orders-v1", "observation_schema_id": ORDERS_OBSERVATION_SCHEMA}))
            dataset = root / "dataset.json"
            dataset.write_text(json.dumps({"schema_version": DATASET_SCHEMA, "source_kind": "human",
                "observation_schema_id": ORDERS_OBSERVATION_SCHEMA, "observation_mode": "orders-v1",
                "action_semantics": "orders-v1", "financial_features": "signed-log-orders-v1",
                "source_recording": source, "replay_validation": {"status": "passed", **artifact(report)}}))
            with self.assertRaisesRegex(ValueError, "every native checkpoint check"):
                validate(dataset, "development")


if __name__ == "__main__":
    unittest.main()
