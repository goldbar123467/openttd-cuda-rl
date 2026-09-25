from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from asset_potential_v2 import AssetPotential, SCHEMA
from train_v2 import reward_components


def transition(cost=0, family="BUILD_ROAD_PATH", terminal=False, truncated=False):
    return {"before": {"delivered_passengers": 0, "operating_profit": 0},
            "after": {"delivered_passengers": 0, "operating_profit": 0},
            "action": {"family": family, "native_commands": [{"phase": "EXECUTE", "status": "SUCCESS", "cost": cost}]},
            "terminal": terminal, "truncated": truncated}


class AssetPotentialTests(unittest.TestCase):
    def test_capital_uses_charged_clipped_magnitude(self):
        ledger = AssetPotential(.99, 128)
        for cost in (16, 4096, 99999, 0):
            t = transition(cost)
            raw = reward_components(t)
            before = ledger.potential
            result = ledger.apply(raw, t)
            self.assertEqual(result["native_reward"], raw["reward"])
            self.assertEqual(result["components"], raw["components"])
            self.assertEqual(result["capital_added"], min(cost, 4096) / 4096)
            self.assertAlmostEqual(result["reward"], -.01 * (before + min(cost, 4096) / 4096) - 1 / 64, places=12)
            self.assertEqual(result["schema_version"], SCHEMA)

    def test_terminal_zeroes_potential_and_truncation_keeps_bootstrap(self):
        for terminal in (True, False):
            ledger = AssetPotential(.99, 128)
            first = transition(4096)
            ledger.apply(reward_components(first), first)
            last = transition(0, "WAIT", terminal=terminal, truncated=not terminal)
            result = ledger.apply(reward_components(last), last)
            self.assertEqual(result["potential_after"], 0 if terminal else 1)
            self.assertAlmostEqual(result["shaping"], -1 if terminal else -.01)
            with self.assertRaisesRegex(ValueError, "reset"):
                ledger.apply(reward_components(first), first)
        self.assertEqual(AssetPotential(.99, 128).potential, 0)

    def test_discounted_telescoping_including_terminal_and_time_limit(self):
        rng = random.Random(20260925)
        for gamma in (0., .99, .995, 1.):
            for terminal in (False, True):
                ledger = AssetPotential(gamma, 128)
                discounted = 0
                for i in range(128):
                    t = transition(rng.randrange(20000), terminal=terminal and i == 127,
                                   truncated=not terminal and i == 127)
                    row = ledger.apply(reward_components(t), t)
                    discounted += gamma ** i * row["shaping"]
                self.assertLessEqual(abs(discounted - gamma ** 128 * ledger.potential), 1e-9)

    def test_history_is_explicit_and_bound_is_enforced(self):
        one, two = AssetPotential(.99, 2), AssetPotential(.99, 2)
        t = transition(8192)
        one.apply(reward_components(t), t)
        for _ in range(2):
            t = transition(4096)
            two.apply(reward_components(t), t)
        self.assertEqual((one.potential, two.potential), (1, 2))
        with self.assertRaisesRegex(ValueError, "reset"):
            two.apply(reward_components(t), t)
        for family in ("SELL_VEHICLE", "REMOVE_ROAD", "DEMOLISH", "INVENTED"):
            t = transition(10, family)
            with self.assertRaisesRegex(ValueError, "forbids"):
                one.apply(reward_components(t), t)
        for invalid in (-.1, float("nan"), float("inf"), 1.1):
            with self.assertRaises(ValueError):
                AssetPotential(invalid, 128)


if __name__ == "__main__":
    unittest.main()
