"""Offline audits must distinguish clipping, terminal labels, and return cuts."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from audit_v2_reward import audit_rows, credit


class RewardAuditTests(unittest.TestCase):
    def sample(self):
        record = {"kind": "native-v2-live-recurrent-ppo", "status": "completed",
                  "reward_schema": "development-v2-live-reward-1", "rollout_steps": 2,
                  "gamma": .99, "gae_lambda": .95,
                  "updates": [{"update": 1, "transitions": 2, "explained_variance": 0., "approximate_kl": .01}]}
        rows = []
        for i in range(2):
            components = {"delivery": 1., "operating_profit": 1., "capital": -1.,
                          "decision": -1 / 64, "bankruptcy": -5. if i == 1 else 0.}
            rows.append({"step": i + 1, "episode": 0, "prediction": {"value": 0.},
                         "feedback": {"next_value": 0.}, "bootstrap": i == 0, "continuation": i == 0,
                         "guidance": {"sampling_legal_count": 3 if i == 0 else 1},
                         "transition": {"before": {"delivered_passengers": 0, "operating_profit": 0},
                                        "after": {"delivered_passengers": 64 if i == 0 else 70,
                                                  "operating_profit": 256 if i == 0 else 300, "alive": True},
                                        "terminal": i == 1, "truncated": False,
                                        "action": {"family": "BUY_BUS", "native_commands": [
                                            {"phase": "TEST", "status": "SUCCESS", "cost": 4921},
                                            {"phase": "EXECUTE", "status": "SUCCESS", "cost": 4921}]}},
                         "training_reward": {"schema_version": record["reward_schema"], "components": components,
                                             "reward": sum(components.values()), "raw_capital": 4921,
                                             "raw_passengers": 64 if i == 0 else 70,
                                             "raw_operating_profit": 256 if i == 0 else 300}})
        return record, rows

    def test_bound_equality_is_not_clipping_and_terminal_is_not_assumed_bankruptcy(self):
        result = audit_rows(*self.sample())
        self.assertEqual(result["clips"]["delivery"]["upper_bound_reached"], 2)
        self.assertEqual(result["clips"]["delivery"]["upper_clipped"], 1)
        self.assertEqual(result["clips"]["capital"]["magnitude_removed"], 1650)
        self.assertEqual(result["choice_fraction"], .5)
        self.assertEqual(result["terminals"][0]["reported_reason"], "not-recorded")
        self.assertTrue(result["terminals"][0]["alive_after"])

    def test_wrong_reward_and_boundary_fail(self):
        record, rows = self.sample()
        for kind in ("reward", "boundary"):
            changed = copy.deepcopy(rows)
            if kind == "reward":
                changed[0]["training_reward"]["raw_capital"] += 1
            else:
                changed[-1]["bootstrap"] = True
            with self.assertRaises(ValueError):
                audit_rows(record, changed)

    def test_truncation_keeps_bootstrap_but_cuts_future_episode_credit(self):
        rows = [{"training_reward": {"reward": 1.}, "prediction": {"value": 2.},
                 "feedback": {"next_value": 4.}, "bootstrap": True, "continuation": False},
                {"training_reward": {"reward": 100.}, "prediction": {"value": 0.},
                 "feedback": {"next_value": 0.}, "bootstrap": False, "continuation": False}]
        advantages, _ = credit(rows, .5, 1.)
        self.assertEqual(advantages, [1., 100.])

    def test_resumed_offsets_and_missing_masks_are_explicit(self):
        record, rows = self.sample()
        record["restored_transitions"] = 64
        record["updates"][0]["transitions"] += 64
        for row in rows:
            row["step"] += 64
            row["guidance"] = None
        result = audit_rows(record, rows)
        self.assertEqual(result["first_step"], 65)
        self.assertEqual(result["choice_count_unavailable_steps"], 2)
        self.assertIsNone(result["choice_fraction"])


if __name__ == "__main__":
    unittest.main()
