import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
import checkpoint_v2


class CheckpointV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.expected = {"configuration": {"episode_horizon": 128, "rollout_steps": 32}}
        payload = b"native archive fixture"
        (self.root / "trainer.pt").write_bytes(payload)
        self.manifest = {"format": "openttd-rl-development-v2-reset-checkpoint-1", "compatibility": self.expected,
                         "update": 4, "transitions": 128, "next_episode": 1,
                         "trainer_sha256": hashlib.sha256(payload).hexdigest(), "next_reset": {"snapshot": "expected"}}
        (self.root / "checkpoint.json").write_text(json.dumps(self.manifest))

    def test_corrupt_payload_and_changed_config_rejected_before_native_restore(self):
        client = Mock()
        with patch.object(checkpoint_v2, "reset_signature") as probe:
            with self.assertRaisesRegex(ValueError, "configuration"):
                checkpoint_v2.restore(client, None, self.root, self.root, {"changed": True})
            (self.root / "trainer.pt").write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "digest"):
                checkpoint_v2.restore(client, None, self.root, self.root, self.expected)
            probe.assert_not_called()
            client.request.assert_not_called()

    def test_changed_reset_fails_before_native_restore(self):
        client = Mock()
        with patch.object(checkpoint_v2, "reset_signature", return_value={"snapshot": "changed"}):
            with self.assertRaisesRegex(ValueError, "Recreated"):
                checkpoint_v2.restore(client, None, self.root, self.root, self.expected)
        client.request.assert_not_called()

    def test_changed_training_seed_order_or_coverage_fails_before_restore(self):
        seeds = [1110312784, 786545128, 1922409719, 583478638]
        self.expected["configuration"]["training_map_seeds"] = seeds
        (self.root / "checkpoint.json").write_text(json.dumps(self.manifest))
        for changed in (list(reversed(seeds)), seeds[:2], seeds + [903537006]):
            expected = {"configuration": {**self.expected["configuration"], "training_map_seeds": changed}}
            client = Mock()
            with patch.object(checkpoint_v2, "reset_signature") as probe:
                with self.assertRaisesRegex(ValueError, "configuration"):
                    checkpoint_v2.restore(client, None, self.root, self.root, expected)
                probe.assert_not_called()
            client.request.assert_not_called()

    def test_changed_return_or_reuse_config_fails_before_restore(self):
        self.expected["configuration"].update(gamma=.99, gae_lambda=.95, reuse_bootstrap_tensors=False)
        (self.root / "checkpoint.json").write_text(json.dumps(self.manifest))
        for key, value in (("gamma", .9), ("gae_lambda", 1.0), ("reuse_bootstrap_tensors", True)):
            expected = {"configuration": {**self.expected["configuration"], key: value}}
            client = Mock()
            with patch.object(checkpoint_v2, "reset_signature") as probe:
                with self.assertRaisesRegex(ValueError, "configuration"):
                    checkpoint_v2.restore(client, None, self.root, self.root, expected)
                probe.assert_not_called()
            client.request.assert_not_called()

    def test_changed_guide_is_rejected_before_native_restore(self):
        self.expected["configuration"]["guidance"] = "one-bus-public-plan-v1"
        (self.root / "checkpoint.json").write_text(json.dumps(self.manifest))
        changed = {"configuration": {**self.expected["configuration"], "guidance": "one-bus-public-plan-v2"}}
        client = Mock()
        with patch.object(checkpoint_v2, "reset_signature") as probe:
            with self.assertRaisesRegex(ValueError, "configuration"):
                checkpoint_v2.restore(client, None, self.root, self.root, changed)
            probe.assert_not_called()
        client.request.assert_not_called()

    def test_native_counter_mismatch_is_rejected(self):
        client = Mock()
        client.request.return_value = {"status": "RESTORED_RESET_CHECKPOINT", "updates": 3, "transitions": 96}
        with patch.object(checkpoint_v2, "reset_signature", return_value=self.manifest["next_reset"]):
            with self.assertRaisesRegex(ValueError, "counters"):
                checkpoint_v2.restore(client, None, self.root, self.root, self.expected)

    def test_interval_aligns_with_a_real_reset(self):
        checkpoint_v2.validate_interval(0, 20)
        checkpoint_v2.validate_interval(4, 128)
        checkpoint_v2.validate_interval(2, 128, 64)
        checkpoint_v2.validate_interval(1, 128, 128)
        for interval in (-1, 1, 3):
            with self.assertRaisesRegex(ValueError, "align"):
                checkpoint_v2.validate_interval(interval, 128)
        with self.assertRaisesRegex(ValueError, "align"):
            checkpoint_v2.validate_interval(1, 128, 64)
        with self.assertRaisesRegex(ValueError, "rollout length"):
            checkpoint_v2.validate_interval(4, 128, 16)

    def test_rollout_length_binds_checkpoint_transition_counters(self):
        for rollout in (64, 128):
            self.expected["configuration"]["rollout_steps"] = rollout
            self.manifest.update(update=128 // rollout, transitions=128)
            (self.root / "checkpoint.json").write_text(json.dumps(self.manifest))
            self.assertEqual(checkpoint_v2.read(self.root, self.expected)["transitions"], 128)
            self.manifest["transitions"] = 64
            (self.root / "checkpoint.json").write_text(json.dumps(self.manifest))
            with self.assertRaisesRegex(ValueError, "counters"):
                checkpoint_v2.read(self.root, self.expected)


if __name__ == "__main__":
    unittest.main()
