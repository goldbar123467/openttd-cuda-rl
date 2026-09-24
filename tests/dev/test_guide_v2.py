"""Planner preview must preserve recurrent replay inputs and native legality."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from guide_v2 import PublicPlanGuide


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


if __name__ == "__main__":
    unittest.main()
