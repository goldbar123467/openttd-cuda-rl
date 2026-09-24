"""Regression tests for local experiment safety and failure provenance."""
from argparse import ArgumentTypeError, Namespace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
import local
import train_live


class LocalWorkflowTests(unittest.TestCase):
    def test_cached_torch_from_another_environment_is_rejected_before_building(self):
        with tempfile.TemporaryDirectory() as temporary:
            build_dir = Path(temporary)
            (build_dir / "CMakeCache.txt").write_text("Torch_DIR:PATH=/old/Torch\n")
            with patch.object(local.sys, "platform", "linux"), \
                    patch.object(local, "host", return_value={"cmake_prefix": "/new"}), \
                    patch.object(local.shutil, "which", return_value="/usr/bin/tool"), \
                    patch.object(local.subprocess, "run") as command:
                with self.assertRaisesRegex(ValueError, "another Torch environment"):
                    local.build(Namespace(build_dir=build_dir))
                command.assert_not_called()

    def test_unavailable_cuda_does_not_start_or_create_a_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            with patch.object(local, "host", return_value={"cuda_available": False}):
                with self.assertRaisesRegex(ValueError, "no CPU fallback"):
                    local.smoke(Namespace(device="cuda:0", output=output))
            self.assertFalse(output.exists())

    def test_nonpositive_budgets_are_rejected(self):
        for value in ("0", "-1"):
            with self.assertRaises(ArgumentTypeError):
                local.positive(value)


class LiveWorkflowTests(unittest.TestCase):
    def test_rollout_length_is_restored_after_failure(self):
        original = train_live.m08.ROLLOUT_LENGTH
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            with train_live.collector_rollout_length(64):
                self.assertEqual(train_live.m08.ROLLOUT_LENGTH, 64)
                raise RuntimeError("interrupted")
        self.assertEqual(train_live.m08.ROLLOUT_LENGTH, original)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ("trainer", "openttd", "train"):
            (self.root / name).write_bytes(name.encode())
        self.args = Namespace(trainer=self.root / "trainer", openttd=self.root / "openttd",
                              instance_dir=self.root / "instances", output=self.root / "run",
                              architecture="structured-mlp-v1", device="cpu", seed=17,
                              updates=2, evaluation_steps=8, timeout=30)
        self.client = Mock()
        self.client.export_evaluation_model.return_value = ("b" * 64, self.root / "model")
        self.training = {"updates": [{"mean_rollout_reward": 0.25}], "accepted_samples": 256}
        for target, value in (
            ("train_live.source_identity", {"commit": "a" * 40, "status": "dirty"}),
            ("train_live.capture_source", {"fixture": True}),
            ("train_live.m07.partition_templates", ([self.root / "train"], [self.root / "dev-a", self.root / "dev-b"])),
            ("train_live.validate_m06_reward_contract.validate", {}),
            ("train_live.m08_trainer_client.TrainerClient.start", self.client),
            ("train_live.m08.train_architecture", self.training),
            ("train_live.m08.evaluate_architecture", {"return": 1.0}),
        ):
            patcher = patch(target, return_value=value)
            mock = patcher.start()
            self.addCleanup(patcher.stop)
            if target.endswith("train_architecture"):
                self.collect = mock
            elif target.endswith("evaluate_architecture"):
                self.evaluate = mock

    def record(self):
        return json.loads((self.args.output / "run.json").read_text())

    def test_training_exports_weights_and_evaluates_both_development_cases(self):
        train_live.run(self.args)
        record = self.record()
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["training"]["accepted_samples"], 256)
        self.assertEqual(len(record["development"]), 2)
        self.assertEqual(self.evaluate.call_count, 2)
        self.assertIn("not an optimizer-resume", record["model"]["purpose"])
        self.client.close.assert_called_once()
        self.client.abort.assert_not_called()

    def test_failed_collection_preserves_primary_and_cleanup_errors(self):
        self.collect.side_effect = RuntimeError("worker disconnected")
        self.client.abort.side_effect = RuntimeError("cleanup failed")
        with self.assertRaisesRegex(RuntimeError, "worker disconnected"):
            train_live.run(self.args)
        record = self.record()
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["error"], "worker disconnected")
        self.assertEqual(record["cleanup_error"], "cleanup failed")
        self.client.export_evaluation_model.assert_not_called()

    def test_failed_evaluation_retains_successfully_trained_model(self):
        self.evaluate.side_effect = RuntimeError("evaluation disconnected")
        with self.assertRaisesRegex(RuntimeError, "evaluation disconnected"):
            train_live.run(self.args)
        self.assertEqual(self.record()["model"]["id"], "b" * 64)
        self.assertEqual(self.record()["status"], "failed")

    def test_invalid_build_provenance_is_recorded_as_failure(self):
        (self.root / "development-build.json").write_text("not-json")
        with self.assertRaises(ValueError):
            train_live.run(self.args)
        self.assertEqual(self.record()["status"], "failed")
        self.collect.assert_not_called()

    def test_existing_run_is_preserved_and_no_training_starts(self):
        self.args.output.mkdir()
        marker = self.args.output / "important-result.txt"
        marker.write_text("preserve")
        with self.assertRaises(FileExistsError):
            train_live.run(self.args)
        self.assertEqual(marker.read_text(), "preserve")
        self.collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
