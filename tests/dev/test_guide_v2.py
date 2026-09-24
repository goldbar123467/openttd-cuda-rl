"""Planner preview must preserve recurrent replay inputs and native legality."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from guide_v2 import GUIDANCE, WAIT_GUIDANCE, PublicPlanGuide


class FakePlan:
    def __init__(self, *args, **kwargs):
        self.stage = 0
        self.plan = {"actions": [["BUILD_ROAD_DEPOT", [22, 1, 0]]]}

    def choose(self, observation):
        self.stage += 1
        return next(c for c in observation["candidates"] if c["family"] == "BUILD_ROAD_DEPOT")


class GuideTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.mask = bytes(int(row in (0, 7, 9)) for row in range(4096))
        self.native = self.root / "tensors-000000-candidates.bin"
        self.original = bytes(790528 - 4096) + self.mask
        self.native.write_bytes(self.original)
        self.records = {row: {"family_index": family, "stable_key": key, "parameters": [family, 22, 1, 0], "cost": 10}
                        for row, family, key in ((0, 0, "wait"), (7, 4, "proposal"), (9, 2, "unrelated-road"))}
        self.obs = {"economy": {"balance": 100000, "loan": 100000}, "candidates": []}
        with patch("guide_v2.ServicePolicy", FakePlan):
            self.guide = PublicPlanGuide(self.obs, self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_preview_and_wait_do_not_advance_construction(self):
        path, mask, info = self.guide.prepare(self.obs, self.native, self.records, self.mask)
        self.assertEqual(self.guide.policy.stage, 0)
        self.guide.commit("wait")
        again = self.guide.prepare(self.obs, self.native, self.records, self.mask)
        self.assertEqual((path, mask, info), again)
        self.assertEqual(self.guide.policy.stage, 0)
        self.guide.commit("proposal")
        self.assertEqual(self.guide.policy.stage, 1)

    def test_sampling_mask_is_a_subset_and_native_bytes_are_untouched(self):
        path, mask, _ = self.guide.prepare(self.obs, self.native, self.records, self.mask)
        self.assertEqual({row for row, value in enumerate(mask) if value}, {0, 7})
        self.assertEqual(self.native.read_bytes(), self.original)
        self.assertEqual(path.read_bytes()[:-4096], self.original[:-4096])

    def test_unexposed_proposal_fails_without_modifying_native_input(self):
        with patch.object(self.guide.policy, "choose", return_value={"key": "invented"}):
            with self.assertRaisesRegex(ValueError, "unexposed"):
                self.guide.prepare(self.obs, self.native, self.records, self.mask)
        self.assertEqual(self.native.read_bytes(), self.original)

    def test_changing_native_candidate_set_reorders_only_on_commit(self):
        actions = [["BUILD_BUS_STOP", [99, 1, 0]], ["BUILD_ROAD_DEPOT", [22, 1, 0]]]
        self.guide.policy.plan["actions"] = actions
        with patch.object(self.guide.policy, "choose", side_effect=RuntimeError(
                "Planned primitive is no longer exposed/legal at stage 0")):
            _, _, info = self.guide.prepare(self.obs, self.native, self.records, self.mask)
        self.assertTrue(info["construction_reordered"])
        self.guide.commit("wait")
        self.assertEqual(self.guide.policy.plan["actions"], actions)
        self.guide.commit("proposal")
        self.assertEqual(self.guide.policy.plan["actions"], list(reversed(actions)))
        self.assertEqual(self.guide.policy.stage, 1)

    def test_unavailable_construction_proposes_wait_without_progress(self):
        self.guide.policy.plan["actions"] = [["BUILD_BUS_STOP", [99, 1, 0]]]
        with patch.object(self.guide.policy, "choose", side_effect=RuntimeError(
                "Planned primitive is no longer exposed/legal at stage 0")):
            _, mask, info = self.guide.prepare(self.obs, self.native, self.records, self.mask)
        self.assertEqual(sum(mask), 1)
        self.assertTrue(info["construction_blocked"])
        self.guide.commit("wait")
        self.assertEqual(self.guide.policy.stage, 0)

    def test_legacy_unavailable_service_remains_an_explicit_failure(self):
        self.assertEqual(self.guide.guidance, GUIDANCE)
        self.guide.policy.stage = len(self.guide.policy.plan["actions"])
        with patch.object(self.guide.policy, "choose", side_effect=RuntimeError(
                "Planned service continuation has no exposed legal candidate")):
            with self.assertRaisesRegex(RuntimeError, "service continuation"):
                self.guide.prepare(self.obs, self.native, self.records, self.mask)
        self.assertEqual(self.native.read_bytes(), self.original)

    def test_v2_unavailable_service_waits_without_inventing_actions_or_advancing(self):
        with patch("guide_v2.ServicePolicy", FakePlan):
            guide = PublicPlanGuide(self.obs, self.root, guidance=WAIT_GUIDANCE)
        guide.policy.stage = len(guide.policy.plan["actions"])
        with patch.object(guide.policy, "choose", side_effect=RuntimeError(
                "Planned service continuation has no exposed legal candidate")):
            first = guide.prepare(self.obs, self.native, self.records, self.mask)
            guide.commit("wait")
            second = guide.prepare(self.obs, self.native, self.records, self.mask)
        self.assertEqual(first, second)
        self.assertEqual(sum(first[1]), 1)
        self.assertEqual(first[2]["guidance"], WAIT_GUIDANCE)
        self.assertTrue(first[2]["construction_blocked"])
        self.assertEqual(guide.policy.stage, 1)
        self.assertEqual(self.native.read_bytes(), self.original)

    def test_v2_does_not_swallow_unrelated_planner_errors(self):
        self.guide.guidance = WAIT_GUIDANCE
        self.guide.policy.stage = len(self.guide.policy.plan["actions"])
        with patch.object(self.guide.policy, "choose", side_effect=RuntimeError("unrelated defect")):
            with self.assertRaisesRegex(RuntimeError, "unrelated defect"):
                self.guide.prepare(self.obs, self.native, self.records, self.mask)

    def test_unknown_guide_version_rejected_before_planning(self):
        with patch("guide_v2.ServicePolicy") as policy:
            with self.assertRaisesRegex(ValueError, "guidance version"):
                PublicPlanGuide(self.obs, self.root, guidance="unknown")
            policy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
