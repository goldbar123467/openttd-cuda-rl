"""Development diagnostics must count real economics and reject incomplete runs."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
import evaluate_live as evaluate


class EpisodeTests(unittest.TestCase):
    def test_one_bus_script_does_not_purchase_unused_fleet(self):
        observation = {"structured": {"data": [0.] * 256}}
        legal = [0] * 41
        legal[0] = legal[16] = legal[17] = 1
        self.assertEqual(evaluate.one_bus_action(observation, legal), 16)
        observation["structured"]["data"][6] = 1 / 8
        self.assertEqual(evaluate.one_bus_action(observation, legal), 17)
        legal[17] = 0
        legal[25] = 1
        self.assertEqual(evaluate.one_bus_action(observation, legal), 25)
        legal[25] = 0
        self.assertEqual(evaluate.one_bus_action(observation, legal), 0)

    def fixture(self, root, *, terminate=True):
        template = root / "template.json"
        template.write_text(json.dumps({"split": "development"}))
        observation = {"structured": {"shape": [256], "data": [0.] * 256}}
        controller = Mock(action_horizon=2)
        controller.snapshot.return_value = {"company": {"balance": 100000}}
        controller.observe.return_value = observation
        controller.mask.return_value = {"legal": [1] + [0] * 40}
        results = []
        for step in range(1, 3):
            results.append({"reward": {"scalar": 1., "raw": {
                "delivered_passengers_delta": 10, "operating_profit_delta": 90,
                "capital_spend": 20 if step == 1 else 0, "native_rejected": 0,
                "idle_bus_ticks": 0, "vehicle_loss_count": 0},
                "source": {"post": {"primary_bus_count": 1, "stopped_primary_bus_count": 0,
                    "operating_income_total": 100 * step, "operating_expenses_total": -10 * step}}},
                "termination": {"reason": "ACTION_AND_TICK_HORIZON" if step == 2 and terminate else "NONE",
                                "trainable": True}, "action_outcome": {},
                # Simulate a quarter rollover: snapshot counters are not lifetime totals.
                "snapshot": {"company": {"balance": 100000 + 90 * step - 20,
                                         "income": 0, "expenses": 0, "delivered_passengers": 0}}})
        controller.step.side_effect = results
        environment = evaluate.m07.Environment(0, 0, template, controller, observation, controller.mask.return_value)
        return template, environment

    def test_economics_survive_quarter_rollover_and_preserve_trace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template, environment = self.fixture(root)
            with patch.object(evaluate.m07, "start_environment", return_value=environment), redirect_stdout(io.StringIO()):
                result = evaluate.episode(engine=root / "engine", template=template, output=root / "run",
                                          reward={}, policy="wait", seed=1, evaluator=None, package=None)
            self.assertEqual(result["operating_profit"], 180)
            self.assertEqual(result["operating_income"], 200)
            self.assertEqual(result["passengers"], 20)
            self.assertEqual(result["operating_profit_less_capital"], 160)
            self.assertEqual(result["first_delivery_action"], 1)
            self.assertFalse(result["service_in_all_final_three_windows"])
            self.assertEqual(len((root / "run/actions.jsonl").read_text().splitlines()), 2)
            environment.controller.close.assert_called_once()
            environment.controller.abort.assert_not_called()

    def test_nonterminal_cutoff_is_failure_and_retains_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template, environment = self.fixture(root, terminate=False)
            with patch.object(evaluate.m07, "start_environment", return_value=environment):
                with self.assertRaisesRegex(RuntimeError, "without an engine termination"):
                    evaluate.episode(engine=root / "engine", template=template, output=root / "run",
                                     reward={}, policy="wait", seed=1, evaluator=None, package=None)
            record = json.loads((root / "run/episode.json").read_text())
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["completed_actions"], 2)
            environment.controller.abort.assert_called_once()

    def test_window_sums_unclipped_raw_economics(self):
        rows = [{"step": 1, "raw": {"delivered_passengers_delta": 150,
                  "operating_profit_delta": 20000, "capital_spend": 70000}},
                {"step": 2, "raw": {"delivered_passengers_delta": 0,
                  "operating_profit_delta": -100, "capital_spend": 0}}]
        self.assertEqual(evaluate.economic_window(rows), {"first_action": 1, "last_action": 2,
                         "passengers": 150, "operating_profit": 19900, "capital_spend": 70000})


if __name__ == "__main__":
    unittest.main()
