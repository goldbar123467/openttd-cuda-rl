import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from eval_stats import nested_bootstrap, pair_episodes


class EvaluationStatsTests(unittest.TestCase):
    def test_pairing_is_exact_and_order_independent(self):
        controls = [{"map_seed": m, "action_seed": a, "profit": m + a} for m in (10, 20) for a in (1, 2)]
        policies = [{**r, "training_seed": s, "profit": r["profit"] + s} for s in (-1, 0, 2) for r in controls]
        paired = pair_episodes(policies, controls, "profit")
        self.assertEqual(pair_episodes(policies[::-1], controls[::-1], "profit"), paired)
        result = nested_bootstrap(paired, iterations=500)
        self.assertAlmostEqual(result["mean"], 1 / 3)
        self.assertEqual(result["per_training_seed"], {-1: -1, 0: 0, 2: 2})
        self.assertEqual(result["per_map"], {10: 1 / 3, 20: 1 / 3})
        self.assertEqual(result["training_seed_sign_counts"], {"positive": 1, "zero": 1, "negative": 1})
        self.assertEqual(nested_bootstrap(paired[::-1], iterations=500), result)

    def test_constant_difference_has_degenerate_interval(self):
        rows = [{"training_seed": s, "map_seed": m, "action_seed": a, "difference": 7.5}
                for s in (1, 2, 3) for m in (10, 20) for a in (4, 5, 6)]
        report = nested_bootstrap(rows, iterations=100)
        self.assertEqual(report["nested_percentile_95_interval"], [7.5, 7.5])
        self.assertEqual(report["training_seeds"], 3)
        self.assertEqual(report["action_seeds_per_map"], 3)

    def test_seed_variation_is_not_diluted_by_repeated_action_seeds(self):
        # With two seed-level outcomes {-1,+1}, the exact bootstrap means are
        # {-1,0,+1}, so its central 95% interval covers both extremes even when
        # each seed has many identical action samples.
        rows = [{"training_seed": s, "map_seed": 10, "action_seed": a, "difference": s}
                for s in (-1, 1) for a in range(10)]
        self.assertEqual(nested_bootstrap(rows, iterations=1000)["nested_percentile_95_interval"], [-1, 1])

    def test_missing_duplicate_extra_nonfinite_and_incomplete_rows_fail(self):
        c = [{"map_seed": 1, "action_seed": 2, "profit": 3}]
        p = [{**c[0], "training_seed": 4}]
        for policies, controls in ((p * 2, c), (p, c * 2), (p, []), ([], c), (p, c + [{"map_seed": 9, "action_seed": 2, "profit": 0}])):
            with self.assertRaises(ValueError):
                pair_episodes(policies, controls, "profit")
        bad = copy.deepcopy(p)
        bad[0]["profit"] = float("inf")
        with self.assertRaises(ValueError):
            pair_episodes(bad, c, "profit")
        rows = [{"training_seed": s, "map_seed": m, "action_seed": 0, "difference": 1.}
                for s in (1, 2) for m in (10, 20)]
        for bad_rows in ([], rows[:-1], rows + [rows[0]], [{**rows[0], "difference": float("nan")} ]):
            with self.assertRaises(ValueError):
                nested_bootstrap(bad_rows, iterations=100)


if __name__ == "__main__":
    unittest.main()
