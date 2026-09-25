"""Live V2 rewards must distinguish economic flows and charge execution once."""
from pathlib import Path
import sys
import unittest
import tempfile
import subprocess
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from train_v2 import reward_components, run


class LiveV2RewardTests(unittest.TestCase):
    def transition(self, family, cost=0, *, profit=0, passengers=0, terminal=False):
        return {"before": {"delivered_passengers": 10, "operating_profit": 100},
                "after": {"delivered_passengers": 10 + passengers, "operating_profit": 100 + profit,
                          "balance": 999999, "loan": 999999},
                "action": {"family": family, "native_commands": [
                    {"phase": phase, "status": "SUCCESS", "cost": cost} for phase in ("TEST", "EXECUTE")]},
                "terminal": terminal}

    def test_loan_principal_is_not_operating_reward_or_capital(self):
        shaped = reward_components(self.transition("MANAGE_LOAN", cost=10000))
        self.assertEqual(shaped["raw_capital"], 0)
        self.assertEqual(shaped["reward"], -1 / 64)

    def test_construction_cost_counts_execution_only(self):
        shaped = reward_components(self.transition("BUILD_BUS_STOP", cost=1024, profit=-64, passengers=16))
        self.assertEqual(shaped["raw_capital"], 1024)
        self.assertEqual(shaped["components"], {"delivery": .25, "operating_profit": -.25,
                         "capital": -.25, "decision": -1 / 64, "bankruptcy": 0.0})

    def test_bounds_preserve_raw_economics_and_terminal_penalty(self):
        shaped = reward_components(self.transition("BUY_BUS", cost=6000, profit=-1000, passengers=100, terminal=True))
        self.assertEqual((shaped["raw_capital"], shaped["raw_operating_profit"], shaped["raw_passengers"]), (6000, -1000, 100))
        self.assertEqual(shaped["components"]["delivery"], 1)
        self.assertEqual(shaped["components"]["operating_profit"], -1)
        self.assertEqual(shaped["components"]["capital"], -1)
        self.assertEqual(shaped["components"]["bankruptcy"], -5)


class LiveV2ReturnConfigurationTests(unittest.TestCase):
    def test_invalid_entropy_fails_before_output_or_native_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist"
            for value in (-.1, 1.1, float("nan"), float("inf")):
                args = SimpleNamespace(episode_horizon=128, entropy_coefficient=value, output=output)
                with self.assertRaisesRegex(ValueError, "entropy-coefficient"):
                    run(args)
                self.assertFalse(output.exists())

    def test_entropy_cli_rejects_invalid_or_duplicate_before_output(self):
        script = Path(__file__).resolve().parents[2] / "scripts/dev/train_v2.py"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist"
            base = [sys.executable, str(script), "--openttd", "missing", "--trainer", "missing",
                    "--device", "cpu", "--output", str(output)]
            for flags in (["--entropy-coefficient", "nan"], ["--entropy-coefficient", "1.1"],
                          ["--entropy-coefficient=.01", "--entropy-coefficient", ".001"]):
                result = subprocess.run(base + flags, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("entropy-coefficient", result.stderr)
                self.assertFalse(output.exists())

    def test_unknown_financial_preprocessing_fails_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist"
            for value in ("signed-log-v2", " raw", None):
                with self.assertRaisesRegex(ValueError, "Financial features"):
                    run(SimpleNamespace(financial_features=value, output=output))
                self.assertFalse(output.exists())

    def test_invalid_gae_weight_fails_before_output_or_native_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist"
            for value in (-.1, 1.1, float("nan"), float("inf")):
                args = SimpleNamespace(episode_horizon=128, gae_lambda=value, output=output)
                with self.assertRaisesRegex(ValueError, "gae-lambda"):
                    run(args)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
