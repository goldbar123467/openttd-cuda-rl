"""Live V2 rewards must distinguish economic flows and charge execution once."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from train_v2 import reward_components


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


if __name__ == "__main__":
    unittest.main()
