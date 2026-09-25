from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from studies.protocol_v2 import development_matrix, load_protocol
from studies.recovery_decision import decide_arm, select_arm


def fixture():
    p = load_protocol()
    training = [{"training_seed": s, "status": "completed", "decisions": 8192} for s in p["training_seeds"]]
    def case(r):
        return {**r, "execution_status": "passed", "guidance": "one-bus-public-plan-v2", "summary": {
            "operating_profit": 100, "cash_result_excluding_financing": -1000, "invalid_actions": 0,
            "bankruptcy": False, "service_in_all_final_three_windows": True}}
    controls = [case({**r, "controller": name}) for name in ("uniform", "scripted") for r in development_matrix(p)]
    candidates = [case({**r, "training_seed": s}) for s in p["training_seeds"] for r in development_matrix(p)]
    for c in candidates:
        c["summary"]["operating_profit"] += 1
        c["summary"]["cash_result_excluding_financing"] += 1
    return p, training, candidates, controls


class RecoveryDecisionTests(unittest.TestCase):
    def decide(self, data):
        p, training, candidates, controls = data
        return decide_arm("A1", training, candidates, controls, p, bootstrap_iterations=100)

    def test_positive_paired_profit_and_cash_pass_even_if_cash_level_negative(self):
        result = self.decide(fixture())
        self.assertTrue(result["eligible"])
        self.assertEqual(result["sampled_paired_vs_uniform"]["cash_result_excluding_financing"]["mean"], 1)
        self.assertEqual(set(result["greedy_sustained_maps_by_training_seed"].values()), {8})

    def test_both_economic_metrics_must_be_positive_for_the_same_two_seeds(self):
        data = fixture()
        p, _, candidates, _ = data
        for c in candidates:
            if c["training_seed"] == p["training_seeds"][0]:
                c["summary"]["operating_profit"] = 99
            if c["training_seed"] == p["training_seeds"][2]:
                c["summary"]["cash_result_excluding_financing"] = -1001
        result = self.decide(data)
        self.assertTrue(result["checks"]["positive_pooled_profit_and_cash"])
        self.assertFalse(result["checks"]["positive_profit_and_cash_at_least_two_training_seeds"])
        self.assertFalse(result["eligible"])

    def test_greedy_threshold_and_single_failure_are_not_pooled_away(self):
        data = fixture()
        greedy = [c for c in data[2] if c["training_seed"] == data[0]["training_seeds"][0] and c["mode"] == "greedy"]
        greedy[0]["summary"]["service_in_all_final_three_windows"] = False
        self.assertTrue(self.decide(data)["eligible"])
        greedy[1]["summary"]["service_in_all_final_three_windows"] = False
        self.assertFalse(self.decide(data)["eligible"])
        for field, value in (("invalid_actions", 1), ("bankruptcy", True)):
            data = fixture()
            data[2][0]["summary"][field] = value
            self.assertFalse(self.decide(data)["eligible"])

    def test_stopped_seeds_remain_failures_without_selected_intermediate_models(self):
        p, training, candidates, controls = fixture()
        training[0].update(status="early-stopped", decisions=2560)
        with self.assertRaises(ValueError):
            self.decide((p, training, candidates, controls))
        candidates = [c for c in candidates if c["training_seed"] != training[0]["training_seed"]]
        result = self.decide((p, training, candidates, controls))
        self.assertFalse(result["eligible"])
        self.assertEqual(result["failed_training_seeds"], [training[0]["training_seed"]])
        self.assertEqual(result["sampled_paired_vs_uniform"], {})

    def test_failed_cases_guide_mismatch_and_missing_matrices_fail(self):
        data = fixture()
        data[2][0].update(execution_status="failed", summary=None)
        result = self.decide(data)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["failed_evaluation_cases"], 1)
        data = fixture()
        data[3][0]["guidance"] = "one-bus-public-plan-v1"
        with self.assertRaises(ValueError):
            self.decide(data)
        data = fixture()
        data[2].pop()
        with self.assertRaises(ValueError):
            self.decide(data)

    def test_selection_requires_all_arms_and_uses_fixed_order(self):
        p = load_protocol()
        results = [{"arm": a["id"], "eligible": a["id"] != "A0"} for a in p["arms"]]
        self.assertEqual(select_arm(results[::-1], p), "A1")
        with self.assertRaises(ValueError):
            select_arm(results[:-1], p)
        self.assertIsNone(select_arm([{**r, "eligible": False} for r in results], p))


if __name__ == "__main__":
    unittest.main()
