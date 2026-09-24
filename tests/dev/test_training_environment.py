"""The curriculum must request real engine limits and remain training-only."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/v1"))
import training_environment as runtime


class TrainingEnvironmentTests(unittest.TestCase):
    def test_horizon_adapter_restores_controller_on_exception(self):
        original = runtime.bridge.Controller
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, "test interruption"):
                with runtime.training_episodes(Path(temp) / "metrics", 128):
                    self.assertIsNot(runtime.bridge.Controller, original)
                    raise RuntimeError("test interruption")
        self.assertIs(runtime.bridge.Controller, original)

    def test_short_horizon_calls_native_reset_not_synthetic_termination(self):
        original = runtime.bridge.Controller
        with tempfile.TemporaryDirectory() as temp, patch.object(original, "reset_evaluation") as reset:
            with runtime.training_episodes(Path(temp) / "metrics", 128):
                controller = runtime.bridge.Controller.__new__(runtime.bridge.Controller)
                controller.instance_value = {"split": "training"}
                controller.reset()
            reset.assert_called_once_with(evaluation_contract_sha256=runtime.M09_COMPATIBILITY_SHA256,
                                          starting_balance=100_000, action_horizon=128, observe=False)

    def test_development_scenario_cannot_enter_curriculum(self):
        with tempfile.TemporaryDirectory() as temp:
            with runtime.training_episodes(Path(temp) / "metrics", 128):
                controller = runtime.bridge.Controller.__new__(runtime.bridge.Controller)
                controller.instance_value = {"split": "development"}
                with self.assertRaisesRegex(ValueError, "only reset a training scenario"):
                    controller.reset()


if __name__ == "__main__":
    unittest.main()
