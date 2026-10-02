"""Regression checks for semantic alias and greedy-tie audit behavior."""
import copy
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from audit_action_inputs_v2 import (CAPACITY, CANDIDATE_BYTES, PARAMETER_OFFSET,
    checked_candidate_data, mode_summary, native_aliases, prediction_result, reverse_legal_rows)


def fixture():
    data = bytearray(CANDIDATE_BYTES)
    rows = []
    for row, family, identity in ((1, 7, 1), (2, 7, 2), (3, 11, 2)):
        parameters = [family, identity] + [0] * 14
        struct.pack_into("<16I", data, PARAMETER_OFFSET + row * 64, *parameters)
        struct.pack_into("<32f", data, row * 128, *([float(row)] * 32))
        data[-CAPACITY + row] = 1
        rows.append({"row": row, "family": family, "parameters": parameters, "features": [0.0] * 32})
    label = {"legal_rows": [1, 2, 3], "action_row": 1, "action_family": 7}
    return data, label, {"rows": rows}


class ActionInputAuditTests(unittest.TestCase):
    def test_same_family_distinct_vehicle_inputs_are_reported(self):
        data, label, native = fixture()
        result = native_aliases(native, data, label)
        self.assertEqual(result["alias_groups"], [{"family": 7, "rows": [1, 2],
                         "parameters": [native["rows"][0]["parameters"], native["rows"][1]["parameters"]]}])
        self.assertEqual(result["target_alias_rows"], [2])
        native["rows"][1]["features"][30] = 1.0
        self.assertEqual(native_aliases(native, data, label)["alias_groups"], [])

    def test_summary_preserves_families_with_zero_aliases(self):
        data, label, native = fixture()
        native["rows"][1]["features"][30] = 1.0
        result = mode_summary([{"new": native_aliases(native, data, label), "target_family": 7}], "new")
        self.assertEqual(result["by_family"], {
            "7": {"legal_candidates": 2, "alias_groups": 0, "aliased_rows": 0, "aliased_targets": 0},
            "11": {"legal_candidates": 1, "alias_groups": 0, "aliased_rows": 0, "aliased_targets": 0}})

    def test_numeric_zero_and_float32_rounding_cannot_hide_aliases(self):
        data, label, native = fixture()
        native["rows"][0]["features"][0] = -0.0
        native["rows"][0]["features"][1] = 1.0
        native["rows"][1]["features"][1] = 1.0 + 1e-9
        self.assertEqual(native_aliases(native, data, label)["target_alias_rows"], [2])

    def test_same_parameters_are_not_a_semantic_alias(self):
        data, label, native = fixture()
        native["rows"][1]["parameters"] = list(native["rows"][0]["parameters"])
        struct.pack_into("<16I", data, PARAMETER_OFFSET + 2 * 64, *native["rows"][1]["parameters"])
        self.assertEqual(native_aliases(native, data, label)["alias_groups"], [])

    def test_native_inventory_and_parameter_changes_fail_closed(self):
        data, label, native = fixture()
        changes = [lambda rows: rows.pop(), lambda rows: rows.append(copy.deepcopy(rows[0])),
                   lambda rows: rows[0].update(row=2), lambda rows: rows[0].update(family=1),
                   lambda rows: rows[0]["parameters"].__setitem__(1, 99),
                   lambda rows: rows[0]["parameters"].__setitem__(1, True)]
        for change in changes:
            altered = copy.deepcopy(native)
            change(altered["rows"])
            with self.subTest(change=change), self.assertRaises(ValueError):
                native_aliases(altered, data, label)

    def test_nonfinite_and_wrong_width_features_fail_closed(self):
        data, label, native = fixture()
        for value in (float("nan"), float("inf"), 1e300, True):
            altered = copy.deepcopy(native)
            altered["rows"][0]["features"][0] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                native_aliases(altered, data, label)
        native["rows"][0]["features"].pop()
        with self.assertRaisesRegex(ValueError, "32-float"):
            native_aliases(native, data, label)

    def test_binary_masks_and_legal_targets_are_required(self):
        data, label, _ = fixture()
        data[-CAPACITY + 1] = 2
        with self.assertRaisesRegex(ValueError, "nonbinary"):
            checked_candidate_data(data, label)
        data[-CAPACITY + 1] = 1
        label["action_row"] = 0
        with self.assertRaisesRegex(ValueError, "legal native action"):
            checked_candidate_data(data, label)

    def test_permutation_moves_complete_records_and_maps_target(self):
        data, label, _ = fixture()
        permuted, mapping = reverse_legal_rows(data, label)
        self.assertEqual(mapping, {1: 2, 2: 1, 3: 3})
        self.assertEqual(permuted[128:256], data[256:384])
        self.assertEqual(permuted[PARAMETER_OFFSET + 64:PARAMETER_OFFSET + 128],
                         data[PARAMETER_OFFSET + 128:PARAMETER_OFFSET + 192])
        self.assertEqual(permuted[-CAPACITY:], data[-CAPACITY:])
        probabilities = [0.0] * CAPACITY
        probabilities[1], probabilities[2], probabilities[3] = 0.1, 0.8, 0.1
        result = prediction_result({"row": 2, "probabilities": probabilities}, label, permutation=mapping)
        self.assertTrue(result["unique_greedy_target"])
        self.assertEqual(result["original_greedy_row"], 1)

    def test_correct_row_is_insufficient_when_greedy_ties(self):
        _, label, _ = fixture()
        probabilities = [0.0] * CAPACITY
        probabilities[1], probabilities[2] = 0.5, 0.5
        result = prediction_result({"row": 1, "probabilities": probabilities}, label)
        self.assertTrue(result["exact_row"])
        self.assertFalse(result["unique_greedy_target"])
        self.assertEqual(result["target_margin"], 0)
        self.assertEqual(result["greedy_tie_rows"], [1, 2])

    def test_near_tie_does_not_qualify_as_unique_correct_prediction(self):
        _, label, _ = fixture()
        probabilities = [0.0] * CAPACITY
        probabilities[1], probabilities[2] = 0.50000025, 0.49999975
        result = prediction_result({"row": 1, "probabilities": probabilities}, label)
        self.assertTrue(result["exact_row"])
        self.assertEqual(result["greedy_tie_rows"], [1])
        self.assertEqual(result["target_near_tie_rows"], [2])
        self.assertFalse(result["unique_greedy_target"])

    def test_invalid_distributions_fail_closed(self):
        _, label, _ = fixture()
        for entries, selected in (({1: .4}, 1), ({0: .5, 1: .5}, 1), ({1: .2, 2: .8}, 1), ({1: 1}, True)):
            probabilities = [0.0] * CAPACITY
            for row, value in entries.items():
                probabilities[row] = value
            with self.subTest(entries=entries, selected=selected), self.assertRaises(ValueError):
                prediction_result({"row": selected, "probabilities": probabilities}, label)


if __name__ == "__main__":
    unittest.main()
