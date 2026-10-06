"""Diagnose exact target mistakes without silently granting oracle hints."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from audit_imitation_choices_v2 import choice_group, input_distance, summarize
from audit_insertion_structure_v2 import classify


class ChoiceDiagnosticTests(unittest.TestCase):
    def test_random_loan_comparison_does_not_reveal_direction(self):
        self.assertEqual(choice_group([11, 1, 10000, 0]), choice_group([11, 2, 10000, 0]))
        self.assertNotEqual(choice_group([6, 1, 1, 0]), choice_group([6, 1, 3, 0]))

    def test_station_position_vehicle_and_variant_mistakes_are_distinct(self):
        target = [6, 7, 1 | 1 << 8 | 0x61 << 16, 2]
        self.assertEqual(classify(target, [6, 7, target[2], 0])["category"], "wrong-station-correct-position")
        self.assertEqual(classify(target, [6, 7, 1 | 0x61 << 16, 2])["category"], "correct-station-wrong-position")
        self.assertEqual(classify(target, [6, 8, target[2], 2])["category"], "wrong-target-vehicle")
        self.assertEqual(classify(target, [6, 7, 1 | 1 << 8 | 0x21 << 16, 2])["category"],
                         "correct-vehicle-station-position-wrong-order-variant")

    def test_equal_features_in_different_families_are_not_input_aliases(self):
        left = {"features": [0.] * 32, "family": 6, "parameters": [6]}
        right = {**left, "family": 11, "parameters": [11]}
        self.assertFalse(input_distance(left, right)["identical_features"])
        self.assertTrue(input_distance(left, left)["identical_features"])


if __name__ == "__main__":
    unittest.main()
