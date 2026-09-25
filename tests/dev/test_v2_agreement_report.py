import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from compare_v2_training import run


class AgreementReportTests(unittest.TestCase):
    def test_failed_numeric_check_publishes_measured_error_without_relaxing_bound(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            for device, name in (("cpu", "cpu"), ("cuda:0", "cuda")):
                folder = root / name
                folder.mkdir()
                update = {k: 0.0 for k in ("policy_loss", "value_loss", "entropy", "approximate_kl", "explained_variance", "behavior_replay_max_error")}
                update["gradient_norm"] = 1.0 if device == "cpu" else 1.0002
                record = {"device": device, "status": "completed", "kind": "native-v2-live-recurrent-ppo", "run_seed": 1,
                          "requested_updates": 1, "episode_horizon": 32, "training_map_seeds": [1], "reward_schema": "fixture",
                          "trainer_sha256": "a" * 64, "engine_sha256": "b" * 64, "rollout_steps": 32,
                          "sequence_length": 8, "optimization_epochs": 4, "updates": [update]}
                (folder / "run.json").write_text(json.dumps(record))
                rows = []
                for i in range(32):
                    rows.append({"step": i + 1, "episode": 0, "reset": i == 0, "candidate": {}, "training_reward": {},
                                 "prediction": {"row": 0, "log_probability": 0.0, "value": 0.0}, "feedback": {"next_value": 0.0},
                                 "transition": {"tick_before": i * 128, "tick_after": (i + 1) * 128,
                                                "action": {"status": "NO_OP"}, "terminal": False, "truncated": i == 31},
                                 "bootstrap": True, "continuation": i != 31})
                (folder / "trajectory.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            with self.assertRaisesRegex(ValueError, "1e-4 exceeded"):
                run(SimpleNamespace(cpu=root / "cpu", cuda=root / "cuda", output=root / "report"))
            report = json.loads((root / "report/comparison.json").read_text())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["numeric_atol"], 1e-4)
            self.assertAlmostEqual(report["update_metric_errors"]["gradient_norm"], .0002)
            self.assertEqual(report["native_transitions_identical"], 32)
            self.assertEqual(len(report["input_record_sha256"]), 2)


if __name__ == "__main__":
    unittest.main()
