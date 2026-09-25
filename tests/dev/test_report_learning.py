import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from report_learning import matrix, paired_statistics


def fixture():
    reference = [{"template_id": m, "sampling_seed": a, "scenario": {"identity": {"scenario_sha256": m}},
                  "passengers": 10, "operating_profit": -100, "operating_profit_less_capital": -1000, "balance_change": -1200}
                 for m in ("map-a", "map-b") for a in (10, 20, 30)]
    groups = [[{**copy.deepcopy(r), "operating_profit": r["operating_profit"] + s} for r in reference] for s in (-1, 0, 2)]
    return groups, [copy.deepcopy(reference) for _ in groups], [-1, 0, 2]


class V1ReportTests(unittest.TestCase):
    def test_nested_report_preserves_seed_pairing_and_map_labels(self):
        report = paired_statistics(*fixture(), iterations=100)
        self.assertAlmostEqual(report["operating_profit"]["mean"], 1 / 3)
        self.assertEqual(report["operating_profit"]["per_training_seed"], {-1: -1, 0: 0, 2: 2})
        self.assertEqual(report["operating_profit"]["per_map"], {"map-a": 1/3, "map-b": 1/3})
        self.assertEqual(report["passengers"]["nested_percentile_95_interval"], [0, 0])
        self.assertEqual(len(report["operating_profit"]["episode_differences"]), 18)

    def test_missing_duplicate_wrong_scenario_and_seed_pairing_fail(self):
        for kind in ("missing", "duplicate", "scenario", "seed"):
            groups, refs, seeds = fixture()
            if kind == "missing": refs[0].pop()
            if kind == "duplicate": groups[0].append(copy.deepcopy(groups[0][0]))
            if kind == "scenario": refs[0][0]["scenario"]["identity"]["scenario_sha256"] = "wrong"
            if kind == "seed": seeds[0] = seeds[1]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                paired_statistics(groups, refs, seeds, iterations=100)


if __name__ == "__main__":
    unittest.main()
