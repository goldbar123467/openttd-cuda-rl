import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from report_v2_learning import build_report


def fixture():
    entries = []
    for controller, seeds in (("neural", (1, 2, 3)), ("uniform", (None,)), ("scripted", (None,))):
        for seed in seeds:
            for m in (10, 20):
                for action in (4, 5, 6):
                    s = {"passengers": 10, "operating_profit": 100 + (seed or 0), "net_capital_spend": 1000,
                         "cash_result_excluding_financing": -900 + (seed or 0), "cash_result_before_capital": 100 + (seed or 0),
                         "service_in_all_final_three_windows": True, "positive_cash_service_in_all_final_three_windows": True,
                         "bankruptcy": False, "invalid_actions": 0, "windows": [{"first_decision": 1, "decisions": 128}]}
                    r = {"controller": controller, "map_seed": m, "sampling_seed": action, "mode": "sampled",
                         "guidance": "one-bus-public-plan-v2", "summary": s, "source": f"/fixture/{controller}-{seed}-{m}-{action}",
                         "reset": {"map_seed": m, "content_manifest_sha256": "a"},
                         "record": {"engine_sha256": "a" * 64, "source": {"fixture": 1}, "model": {"sha256": str(seed)},
                                    "training_run": f"/fixture/train-{seed}", "guidance_override": None}}
                    if seed:
                        r.update(training_seed=seed, training={"guidance": "one-bus-public-plan-v2", "entropy_coefficient": .003})
                    entries.append(r)
    return entries


class ReportTests(unittest.TestCase):
    def test_full_pairing_retains_windows_seeds_maps_and_signs(self):
        result = build_report(fixture(), bootstrap_iterations=100)
        metric = next(iter(result["paired_comparisons"].values()))["operating_profit"]
        self.assertEqual(metric["mean"], 2)
        self.assertEqual(metric["per_training_seed"], {1: 1, 2: 2, 3: 3})
        self.assertEqual(metric["per_map"], {10: 2, 20: 2})
        self.assertEqual(metric["training_seed_sign_counts"], {"positive": 3, "negative": 0, "zero": 0})
        self.assertEqual(len(metric["episode_differences"]), 18)
        self.assertTrue(all(e["summary"]["windows"] for e in result["episodes"]))
        self.assertEqual(len(result["paired_comparisons"]), 2)
        self.assertFalse(result["unpaired_groups"])
        self.assertIn("uniform/one-bus-public-plan-v2", result["summaries"])
        self.assertEqual(result["episodes"][0]["controller"], {"sampling_seed": 4, "training_run": "/fixture/train-1", "model": {"sha256": "1"}})

    def test_missing_duplicate_changed_model_and_recipe_rejected(self):
        for kind in ("missing-policy", "missing-control", "duplicate", "model", "recipe", "reset"):
            rows = fixture()
            if kind == "missing-policy": rows.pop(0)
            if kind == "missing-control": rows.pop(18)
            if kind == "duplicate": rows.append(copy.deepcopy(rows[0]))
            if kind == "model": rows[0]["record"]["model"]["sha256"] = "different"
            if kind == "recipe": rows[0]["training"]["entropy_coefficient"] = .01
            if kind == "reset": rows[0]["reset"]["content_manifest_sha256"] = "different"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                build_report(rows, bootstrap_iterations=100)

    def test_mixed_guides_sources_and_overrides_are_explicitly_unpaired(self):
        for kind in ("guide", "source", "override", "reset"):
            rows = fixture()
            for row in rows:
                if row["controller"] != "neural":
                    if kind == "guide": row["guidance"] = "one-bus-public-plan-v1"
                    if kind == "source": row["record"]["source"] = {"fixture": 2}
                    if kind == "reset": row["reset"]["content_manifest_sha256"] = "different"
                elif kind == "override": row["record"]["guidance_override"] = row["guidance"]
            report = build_report(rows, bootstrap_iterations=100)
            self.assertFalse(report["paired_comparisons"])
            self.assertTrue(report["unpaired_groups"])


if __name__ == "__main__":
    unittest.main()
