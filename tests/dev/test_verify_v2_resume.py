"""Path normalization must not hide a changed planner mask or policy output."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from verify_v2_resume import comparison_row


class ComparisonTests(unittest.TestCase):
    def test_run_locations_normalize_but_causal_guide_and_actor_fields_remain(self):
        first = {"step": 129, "episode": 1, "reset": True, "prediction": {"value": .1},
                 "candidate": {"row": 3}, "transition": {"tick": 128}, "training_reward": .2,
                 "guidance": {"sampling_binary": "/full/episode-1/mask.bin", "sampling_binary_sha256": "a" * 64,
                              "allowed_keys": [1, 2], "stage": 0},
                 "bootstrap": True, "continuation": True, "feedback": {"next_value": .2}}
        second = copy.deepcopy(first)
        second["guidance"]["sampling_binary"] = "/resumed/episode-1/mask.bin"
        expected = comparison_row(first, Path("/full"))
        self.assertEqual(expected, comparison_row(second, Path("/resumed")))
        for key, value in (("sampling_binary_sha256", "b" * 64), ("allowed_keys", [1]), ("stage", 1)):
            changed = copy.deepcopy(second)
            changed["guidance"][key] = value
            self.assertNotEqual(expected, comparison_row(changed, Path("/resumed")))
        second["prediction"]["value"] += 1e-9
        self.assertNotEqual(expected, comparison_row(second, Path("/resumed")))
        with self.assertRaises(ValueError):
            comparison_row(first, Path("/unrelated"))


if __name__ == "__main__":
    unittest.main()
