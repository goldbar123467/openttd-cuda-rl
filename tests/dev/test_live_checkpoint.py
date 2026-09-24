"""Reject incomplete or incompatible recovery rather than silently restarting."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
import train_live  # establishes frozen collector imports
import live_checkpoint as checkpoint


class CheckpointTests(unittest.TestCase):
    def test_gae_option_and_invalid_range(self):
        with patch.object(checkpoint.subprocess, "Popen") as process, patch.object(checkpoint, "TrainerClient"):
            checkpoint.start_trainer(Path("native"), deterministic_cudnn=True, device="cpu")
            self.assertNotIn("--gae-lambda", process.call_args.args[0])
            checkpoint.start_trainer(Path("native"), gae_lambda=1.0, device="cpu")
            self.assertIn("--gae-lambda", process.call_args.args[0])
            self.assertIn("1.0", process.call_args.args[0])
            process.reset_mock()
            for coefficient in (float("nan"), float("inf"), -0.1, 1.1):
                with self.assertRaisesRegex(ValueError, "finite"):
                    checkpoint.start_trainer(Path("native"), gae_lambda=coefficient)
            process.assert_not_called()

    def test_entropy_option_is_explicit_and_invalid_values_fail_before_launch(self):
        with patch.object(checkpoint.subprocess, "Popen") as process, patch.object(checkpoint, "TrainerClient") as client:
            checkpoint.start_trainer(Path("native"), deterministic_cudnn=True, device="cpu")
            self.assertNotIn("--entropy-coefficient", process.call_args.args[0])
            checkpoint.start_trainer(Path("native"), entropy_coefficient=0.05, device="cpu")
            self.assertIn("--entropy-coefficient", process.call_args.args[0])
            self.assertIn("0.05", process.call_args.args[0])
            process.reset_mock()
            for coefficient in (float("nan"), float("inf"), -0.1):
                with self.assertRaisesRegex(ValueError, "finite"):
                    checkpoint.start_trainer(Path("native"), entropy_coefficient=coefficient)
            process.assert_not_called()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.expected = {"configuration": {"environments": 1, "episode_action_horizon": 512, "rollout_length": 32}}
        self.environment = SimpleNamespace(environment_id=0, episode_index=3, episode_length=0,
                                           template=Path("training-template.json"), observation={"state": [1, 2]},
                                           mask={"legal": [1, 0]}, controller=Mock())
        self.metrics = SimpleNamespace(update=48, samples=6144)

    def save(self):
        adapter = checkpoint.CheckpointClient(Mock(), {0: self.environment}, self.root,
                                               self.expected, 16, {"commit": "fixture"})
        with patch.object(checkpoint, "native_request", side_effect=lambda client, kind, path: path.write_bytes(b"native-state")):
            adapter.save(self.metrics)
        return Path(adapter.saved[0]["path"])

    def test_checksum_and_configuration_fail_before_native_restore(self):
        path = self.save()
        manifest = checkpoint.read_checkpoint(path, self.expected)
        self.assertEqual(manifest["environments"][0]["episode_index"], 3)
        with self.assertRaisesRegex(ValueError, "configuration"):
            checkpoint.read_checkpoint(path, {"wrong": "config"})
        (path / "trainer.pt").write_bytes(b"damaged")
        with patch.object(checkpoint, "native_request") as native:
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                with checkpoint.checkpoint_collection(Mock(), self.root, self.expected, 16, {}, path):
                    pass
            native.assert_not_called()

    def test_mid_game_is_not_published_as_reset_checkpoint(self):
        self.environment.episode_length = 1
        adapter = checkpoint.CheckpointClient(Mock(), {0: self.environment}, self.root,
                                               self.expected, 16, {})
        with patch.object(checkpoint, "native_request") as native:
            adapter.save(self.metrics)
            native.assert_not_called()
        self.assertEqual(adapter.saved[0]["status"], "skipped")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_resume_uses_saved_episode_and_verifies_recreated_state(self):
        path = self.save()
        original_factory = Mock(return_value=self.environment)
        with patch.object(checkpoint.m07, "start_environment", original_factory), patch.object(checkpoint, "native_request"):
            with checkpoint.checkpoint_collection(Mock(), self.root, self.expected, 16, {}, path):
                environment = checkpoint.m07.start_environment(None, [], self.root, {}, 0, 0, 60, "train")
                self.assertIs(environment, self.environment)
            self.assertIs(checkpoint.m07.start_environment, original_factory)
        self.assertEqual(original_factory.call_args.args[5], 3)
        self.environment.observation = {"state": "wrong"}
        with patch.object(checkpoint.m07, "start_environment", original_factory), patch.object(checkpoint, "native_request"):
            with self.assertRaisesRegex(ValueError, "differs from saved reset"):
                with checkpoint.checkpoint_collection(Mock(), self.root, self.expected, 16, {}, path):
                    checkpoint.m07.start_environment(None, [], self.root, {}, 0, 0, 60, "train")
            self.assertIs(checkpoint.m07.start_environment, original_factory)
        self.environment.controller.abort.assert_called_once()

    def test_unsafe_interval_is_rejected_before_restore(self):
        with patch.object(checkpoint, "native_request") as native:
            with self.assertRaisesRegex(ValueError, "multiple"):
                with checkpoint.checkpoint_collection(Mock(), self.root, self.expected, 3, {}, "unused"):
                    pass
            native.assert_not_called()

    def test_failed_initial_worker_creation_releases_earlier_workers(self):
        self.environment.controller.worker.process.poll.return_value = None
        original = Mock(side_effect=[self.environment, RuntimeError("next reset failed")])
        with patch.object(checkpoint.m07, "start_environment", original):
            with self.assertRaisesRegex(RuntimeError, "next reset failed"):
                with checkpoint.checkpoint_collection(Mock(), self.root, self.expected, 16, {}):
                    checkpoint.m07.start_environment(None, [], self.root, {}, 0, 0, 60, "train")
                    checkpoint.m07.start_environment(None, [], self.root, {}, 1, 0, 60, "train")
            self.assertIs(checkpoint.m07.start_environment, original)
        self.environment.controller.abort.assert_called_once()


if __name__ == "__main__":
    unittest.main()
