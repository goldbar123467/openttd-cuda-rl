"""Reject ambiguous preprocessing before creating an evaluation or native client."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
import infer_v2


class FinancialCompatibilityTests(unittest.TestCase):
    def test_model_and_run_metadata_must_agree_before_evaluation_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            training = root / "training"
            training.mkdir()
            output = root / "must-not-exist"
            base = {"kind": "native-v2-live-recurrent-ppo", "status": "completed",
                "observation_schema_id": "v2-m15-public-development-v2", "guidance": "none"}
            for run_mode, model_mode in [("raw", "signed-log-v1"), ("signed-log-v1", "raw")]:
                (training / "run.json").write_text(json.dumps({**base, "financial_features": run_mode,
                    "model": {"financial_features": model_mode}}))
                with patch.object(infer_v2.subprocess, "Popen") as process:
                    with self.assertRaisesRegex(ValueError, "Model and training financial preprocessing differ"):
                        infer_v2.run(SimpleNamespace(training_run=training, output=output))
                    process.assert_not_called()
                self.assertFalse(output.exists())

    def test_unknown_client_mode_fails_before_log_or_process(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "must-not-exist.log"
            with patch.object(infer_v2.subprocess, "Popen") as process:
                with self.assertRaisesRegex(ValueError, "Financial features"):
                    infer_v2.PolicyClient(Path("unused"), log, "cpu", 1, financial_features="unknown")
                process.assert_not_called()
            self.assertFalse(log.exists())


if __name__ == "__main__":
    unittest.main()
