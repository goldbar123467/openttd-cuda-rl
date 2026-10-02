"""Financing decisions use native legality at every stage of the one-bus guide."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from guide_v2 import FINANCE_GUIDANCE, PublicPlanGuide


class ConstructionPlan:
    def __init__(self, *args, **kwargs):
        self.stage = 0
        self.plan = {"actions": [["BUILD_ROAD_DEPOT", [22, 1, 0]]]}

    def choose(self, observation):
        if self.stage >= len(self.plan["actions"]):
            return next(c for c in observation["candidates"] if c["family"] == "WAIT")
        family, params = self.plan["actions"][self.stage]
        candidate = next((c for c in observation["candidates"] if
                          c["family"] == family and c["parameters"][1:4] == params), None)
        if candidate is None:
            raise RuntimeError(f"Planned primitive is no longer exposed/legal at stage {self.stage}")
        self.stage += 1
        return candidate


class FinanceGuideTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.observation = {"economy": {"balance": 100000, "loan": 100000}, "vehicles": []}
        with patch("guide_v2.ServicePolicy", ConstructionPlan):
            self.guide = PublicPlanGuide(self.observation, self.root, guidance=FINANCE_GUIDANCE)

    def frame(self, name, *, borrow=True, repay=True, investment=True):
        records = {}
        def add(row, family, key, params):
            index = self.guide.families.index(family)
            records[row] = {"family_index": index, "stable_key": key,
                            "parameters": [index, *params], "cost": 0}
        add(0, "WAIT", "wait", [0, 0, 0])
        if investment:
            add(7, "BUILD_ROAD_DEPOT", "invest", [22, 1, 0])
        add(9, "BUILD_ROAD_PATH", "unrelated", [23, 5, 1])
        if borrow:
            add(16, "MANAGE_LOAN", "borrow", [1, 10000, 0])
        if repay:
            add(31, "MANAGE_LOAN", "repay", [2, 10000, 0])
        native_mask = bytes(int(row in records) for row in range(4096))
        path = self.root / (name + ".bin")
        original = bytes(790528 - 4096) + native_mask
        path.write_bytes(original)
        result = self.guide.prepare(self.observation, path, records, native_mask)
        guided, mask, info = result
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(guided.read_bytes(), original[:-4096] + mask)
        self.assertEqual(info["sampling_binary_sha256"], hashlib.sha256(guided.read_bytes()).hexdigest())
        self.assertTrue(all(not value or native_mask[row] for row, value in enumerate(mask)))
        self.assertEqual(info["sampling_legal_count"], sum(mask))
        self.assertNotIn("unrelated", info["allowed_keys"])
        return result, (path, records, native_mask)

    def test_upfront_borrow_and_repay_compete_with_investment_and_wait(self):
        (path, mask, info), _ = self.frame("upfront")
        self.assertEqual(info["allowed_keys"], ["borrow", "invest", "repay", "wait"])
        self.assertEqual(info["loan_allowed_keys"], ["borrow", "repay"])
        self.assertEqual({row for row, value in enumerate(mask) if value}, {0, 7, 16, 31})
        self.assertFalse(info["service_started"])
        self.assertEqual(self.guide.policy.stage, 0)
        manifest = json.loads((self.root / "planner-guide.json").read_text())
        self.assertIn("Planner supplies one-bus route construction choices", manifest["claim"])
        self.assertIn("No human imitation", manifest["claim"])

    def test_low_cash_and_max_debt_follow_native_candidates(self):
        # Native testing has already rejected repayment with insufficient cash.
        self.observation["economy"] = {"balance": 2500, "loan": 100000}
        (_, _, info), _ = self.frame("low-cash", repay=False, investment=False)
        self.assertEqual(info["allowed_keys"], ["borrow", "wait"])
        self.assertTrue(info["construction_blocked"])
        # The environment can expose repayment below the old 20,000 threshold.
        self.observation["economy"] = {"balance": 10000, "loan": 300000}
        (_, _, info), _ = self.frame("max-loan", borrow=False)
        self.assertEqual(info["allowed_keys"], ["invest", "repay", "wait"])
        # Neither option is invented when both native commands are unavailable.
        self.observation["economy"]["balance"] = 0
        (_, _, info), _ = self.frame("no-liquidity", borrow=False, repay=False, investment=False)
        self.assertEqual(info["allowed_keys"], ["wait"])

    def test_finance_and_wait_commits_do_not_advance_or_change_preview(self):
        first, (path, records, native_mask) = self.frame("preview")
        for key in ("borrow", "repay", "wait"):
            self.guide.commit(key)
            self.assertEqual(self.guide.policy.stage, 0)
            self.assertEqual(first, self.guide.prepare(self.observation, path, records, native_mask))
        self.guide.commit("invest")
        self.assertEqual(self.guide.policy.stage, 1)

    def test_finance_does_not_commit_a_reordered_construction_plan(self):
        actions = [["BUILD_BUS_STOP", [99, 1, 0]], ["BUILD_ROAD_DEPOT", [22, 1, 0]]]
        self.guide.policy.plan["actions"] = actions
        (_, _, info), _ = self.frame("reorder")
        self.assertTrue(info["construction_reordered"])
        self.guide.commit("repay")
        self.assertEqual(self.guide.policy.plan["actions"], actions)
        self.assertEqual(self.guide.policy.stage, 0)
        self.guide.commit("invest")
        self.assertEqual(self.guide.policy.plan["actions"], list(reversed(actions)))
        self.assertEqual(self.guide.policy.stage, 1)

    def test_both_finance_choices_remain_after_service_started(self):
        self.guide.policy.stage = 1
        self.guide.service_started = True
        self.observation["vehicles"] = [{"id": 0}]
        (_, _, info), _ = self.frame("service")
        self.assertEqual(info["allowed_keys"], ["borrow", "repay", "wait"])
        self.assertTrue(info["service_started"])
        self.guide.commit("borrow")
        self.assertEqual(self.guide.policy.stage, 1)

    def test_unaffordable_service_can_choose_finance_without_advancing(self):
        self.guide.policy.stage = 1
        with patch.object(self.guide.policy, "choose", side_effect=RuntimeError(
                "Planned service continuation has no exposed legal candidate")):
            (_, _, info), _ = self.frame("blocked-service", repay=False)
        self.assertEqual(info["allowed_keys"], ["borrow", "wait"])
        self.assertTrue(info["construction_blocked"])
        self.guide.commit("borrow")
        self.assertEqual(self.guide.policy.stage, 1)

    def test_native_mask_disagreement_cannot_admit_a_loan(self):
        _, (path, records, native_mask) = self.frame("mask-mismatch")
        changed = bytearray(native_mask)
        changed[16] = 0
        with self.assertRaisesRegex(ValueError, "subset of native legality"):
            self.guide.prepare(self.observation, path, records, bytes(changed))


if __name__ == "__main__":
    unittest.main()
