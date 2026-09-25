import copy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from studies.legacy_advancement import decide


def fixture():
    cases = []
    def add(name, split, mode, seed, map_seed, value):
        cases.append({"controller": name, "split": split, "mode": mode, "sampling_seed": seed,
                      "map_seed": map_seed, "execution_status": "passed", "summary": {
                          "decisions": 512, "passengers": value, "operating_profit": value,
                          "cash_result_excluding_financing": value, "service_in_all_final_three_windows": True,
                          "invalid_actions": 0, "bankruptcy": False}})
    for name in ("candidate", "reference", "uniform"):
        for seed in (1, 2, 3):
            for map_seed in (10, 11):
                add(name, "development", "sampled", seed, map_seed, 100 + map_seed + (seed + 1 if name == "candidate" else 0))
    for map_seed in (10, 11):
        add("candidate", "development", "greedy", 1, map_seed, 100)
    add("candidate", "training", "greedy", 1, 20, 100)
    return cases


def decision(cases):
    return decide(cases, "candidate", ["reference", "uniform"], [10, 11], [1, 2, 3], 20)


class LegacyAdvancementTests(unittest.TestCase):
    def test_independent_known_pairing_and_original_interval(self):
        report = decision(fixture())
        self.assertTrue(report["advance_to_replication"])
        paired = report["paired_differences"]["uniform"]["operating_profit"]
        self.assertEqual(paired["seed_differences"], [2, 3, 4])
        self.assertEqual(paired["mean"], 3)
        margin = 4.302652729749462 / math.sqrt(3)
        for actual, expected in zip(paired["approximate_95_percent_t_interval"], [3 - margin, 3 + margin]):
            self.assertAlmostEqual(actual, expected, places=12)
        self.assertEqual(decision(list(reversed(fixture()))), report)

    def test_failure_is_retained_and_never_averaged_as_complete(self):
        cases = fixture()
        cases[0].update(execution_status="failed", summary=None)
        report = decision(cases)
        self.assertFalse(report["advance_to_replication"])
        self.assertEqual(report["checks"], {"all_nine_complete": False})
        self.assertNotIn("candidate", report["summaries"])

    def test_missing_duplicate_wrong_split_and_partial_are_rejected(self):
        cases = fixture()
        for altered in (cases[:-1], cases + [copy.deepcopy(cases[0])]):
            with self.assertRaises(ValueError):
                decision(altered)
        for key, value in (("split", "final"), ("map_seed", 99)):
            altered = copy.deepcopy(cases)
            altered[0][key] = value
            with self.assertRaises(ValueError):
                decision(altered)
        for key, value in (("decisions", 128), ("operating_profit", float("nan"))):
            altered = copy.deepcopy(cases)
            altered[0]["summary"][key] = value
            with self.assertRaises(ValueError):
                decision(altered)

    def test_zero_uniform_difference_and_one_service_failure_fail(self):
        cases = fixture()
        for case in cases:
            if case["controller"] == "candidate" and case["mode"] == "sampled":
                case["summary"]["operating_profit"] = 100 + case["map_seed"]
        report = decision(cases)
        self.assertTrue(report["checks"]["operating_profit_at_least_reference"])
        self.assertFalse(report["checks"]["operating_profit_exceeds_uniform"])
        cases = fixture()
        cases[-1]["summary"]["service_in_all_final_three_windows"] = False
        self.assertFalse(decision(cases)["advance_to_replication"])


if __name__ == "__main__":
    unittest.main()
