"""An exact-options proof must reject causal changes while allowing new binaries."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from verify_v2_options import compare_exact


class ExactOptionsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.reference = Path(self.temporary.name) / "old"
        self.candidate = Path(self.temporary.name) / "new"
        for root in (self.reference, self.candidate):
            root.mkdir()
            (root / "inference-weights.pt").write_bytes(b"fixed parameter archive")
            record = {"status": "completed", "kind": "native-v2-live-recurrent-ppo", "device": "cpu",
                      "run_seed": 7, "requested_updates": 1, "episode_horizon": 32, "training_map_seeds": [42],
                      "reward_schema": "reward-1", "engine_sha256": "engine", "rollout_steps": 32,
                      "sequence_length": 8, "optimization_epochs": 4, "observation_schema_id": "public",
                      "guidance": "none", "trainer_sha256": root.name, "source": {"commit": root.name},
                      "updates": [{"update": 1, "value_loss": .5, "elapsed_ns": len(root.name)}],
                      "model": {"sha256": hashlib.sha256((root / "inference-weights.pt").read_bytes()).hexdigest()}}
            (root / "run.json").write_text(json.dumps(record))
            metadata = root / "tensor.json"
            metadata.write_text(json.dumps({"binary": {"sha256": "same input"}}))
            rows = [{"step": i + 1, "episode": 0, "reset": i == 0,
                     "prediction": {"row": 0, "log_probability": -.3, "value": .2},
                     "candidate": {"row": 0}, "transition": {"tick_before": i * 128, "tick_after": (i + 1) * 128,
                     "action": {"status": "SUCCESS"}, "terminal": False, "truncated": i == 31},
                     "training_reward": -.015625, "guidance": None,
                     "bootstrap": True, "continuation": i != 31, "feedback": {"next_value": .4},
                     "observation_metadata": str(metadata), "candidates_metadata": str(metadata)} for i in range(32)]
            (root / "trajectory.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))

    def mutate_run(self, function):
        path = self.candidate / "run.json"
        data = json.loads(path.read_text())
        function(data)
        path.write_text(json.dumps(data))

    def test_different_builds_and_legacy_default_metadata_can_match(self):
        self.mutate_run(lambda run: run.update(entropy_coefficient=.01, financial_features="raw", gamma=.99))
        self.assertEqual(compare_exact(self.reference, self.candidate)["exact_transitions"], 32)

    def test_changed_entropy_is_not_hidden_by_identical_actions(self):
        self.mutate_run(lambda run: run.update(entropy_coefficient=.001))
        with self.assertRaisesRegex(ValueError, "entropy_coefficient"):
            compare_exact(self.reference, self.candidate)

    def test_changed_bootstrap_value_is_rejected(self):
        path = self.candidate / "trajectory.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[-1]["feedback"]["next_value"] += 1e-9
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        with self.assertRaisesRegex(ValueError, "step 32"):
            compare_exact(self.reference, self.candidate)

    def test_changed_tensor_is_rejected_even_with_same_predictions(self):
        (self.candidate / "tensor.json").write_text(json.dumps({"binary": {"sha256": "different"}}))
        with self.assertRaisesRegex(ValueError, "tensor mismatch"):
            compare_exact(self.reference, self.candidate)

    def test_changed_update_is_rejected(self):
        self.mutate_run(lambda run: run["updates"][0].update(value_loss=.50000001))
        with self.assertRaisesRegex(ValueError, "update metrics"):
            compare_exact(self.reference, self.candidate)

    def test_corrupt_model_cannot_pass_using_recorded_hash(self):
        (self.candidate / "inference-weights.pt").write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "weights no longer match"):
            compare_exact(self.reference, self.candidate)


if __name__ == "__main__":
    unittest.main()
