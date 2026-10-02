import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from report_imitation_eval_v2 import build_report, finance_metrics, validate_finance_chain


def economy(cash=100000, loan=100000, interest=0):
    return {"balance": cash, "loan": loan, "operating_profit": 0,
            "finance": {"maximum_loan": 300000, "borrowing_headroom": 300000 - loan,
                        "interest_rate_percent": 2, "quarter_income": 0, "quarter_expenses": 0,
                        "quarter_operating_profit": 0, "year_interest_paid": interest}}


def transitions():
    actions = [("MANAGE_LOAN", 1, 10000), ("MANAGE_LOAN", 2, 10000),
               ("START_VEHICLE", 0, 0), ("MANAGE_LOAN", 2, 10000), ("WAIT", 0, 0),
               ("MANAGE_LOAN", 1, 10000)]
    rows = []
    before = economy()
    for index, (family, operation, amount) in enumerate(actions, 1):
        delta = amount if operation == 1 else -amount
        after = economy(before["balance"] + delta, before["loan"] + delta)
        rows.append({"decision": index, "before": before, "after": after,
                     "action": {"family": family, "parameters": [0, operation, amount],
                                "status": "SUCCESS", "rolled_back": False}})
        before = after
    return rows


def case(label="policy", map_seed=11):
    return {"label": label, "map_seed": map_seed, "mode": "greedy", "action_seed": 1,
            "requested_decisions": 6,
            "model": {"sha256": "a"}, "guidance": "v5", "guidance_override": None,
            "reset": {"map_seed": map_seed}, "source": {"commit": "a"},
            "observation_schema_id": "finance-v1",
            "summary": {"decisions": 6, "passengers": 0, "bankruptcy": False, "invalid_actions": 0,
                        "operating_profit": 0, "cash_result_excluding_financing": 0, "capital_spend": 0},
            "finance": finance_metrics(transitions())}


class FinanceReportTests(unittest.TestCase):
    def test_loan_roundtrip_does_not_earn_cash_and_wait_breaks_immediate_churn(self):
        rows = transitions()
        validate_finance_chain(rows)
        result = finance_metrics(rows)
        self.assertEqual(result["initial_cash"], result["final_cash"])
        self.assertEqual(result["initial_debt"], result["final_debt"])
        self.assertEqual(result["principal_borrowed"], 20000)
        self.assertEqual(result["principal_repaid"], 20000)
        self.assertEqual(result["immediate_opposite_loan_actions"], 1)
        self.assertEqual(result["repay_before_service_actions"], 1)
        self.assertEqual(result["first_start_service_action"], 3)
        self.assertEqual(result["minimum_cash_at_decision_boundary"], 90000)

    def test_failed_start_is_not_service_and_low_cash_is_explicit(self):
        rows = transitions()
        rows[2]["action"]["status"] = "FAILED"
        rows[3]["after"]["balance"] = 5000
        result = finance_metrics(rows)
        self.assertIsNone(result["first_start_service_action"])
        self.assertEqual(result["repay_before_service_actions"], 2)
        self.assertEqual(result["repay_leaving_less_than_10000"], 1)

    def test_interest_reset_is_counted_without_negative_credit(self):
        rows = transitions()[:2]
        rows[0]["before"]["finance"]["year_interest_paid"] = 100
        rows[0]["after"]["finance"]["year_interest_paid"] = 120
        rows[1]["after"]["finance"]["year_interest_paid"] = 5
        result = finance_metrics(rows)
        self.assertEqual(result["observed_interest_lower_bound"], 25)
        self.assertEqual(result["interest_counter_resets"], 1)

    def test_corrupt_finance_and_principal_fail(self):
        for kind in ("chain", "capacity", "quarter", "type", "principal"):
            rows = copy.deepcopy(transitions())
            if kind == "chain":
                rows[1]["before"] = copy.deepcopy(rows[1]["before"])
                rows[1]["before"]["finance"]["year_interest_paid"] += 1
            if kind == "capacity": rows[0]["before"]["finance"]["borrowing_headroom"] += 1
            if kind == "quarter": rows[0]["before"]["finance"]["quarter_income"] += 1
            if kind == "type": rows[0]["before"]["finance"]["maximum_loan"] = "300000"
            if kind == "principal": rows[0]["action"]["parameters"][2] += 1
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validate_finance_chain(rows)
                finance_metrics(rows)

    def test_matching_separates_source_and_imitation_mask_transfer(self):
        baseline, neural = case("script"), case("imitation")
        neural["source"] = {"commit": "b"}
        neural["guidance_override"] = "v5"
        result = build_report([baseline, neural])
        self.assertTrue(result["matched_environment_settings"])
        self.assertFalse(result["source_identity_same"])
        neural["reset"]["map_seed"] = 22
        self.assertFalse(build_report([baseline, neural])["matched_environment_settings"])

    def test_duplicate_or_mixed_model_and_budget_rejected(self):
        for kind in ("duplicate", "model", "budget"):
            first, second = case(), case(map_seed=22)
            if kind == "duplicate": second = copy.deepcopy(first)
            if kind == "model": second["model"]["sha256"] = "other"
            if kind == "budget": second["requested_decisions"] += 1
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                build_report([first, second])

    def test_early_bankruptcy_is_retained_under_same_requested_horizon(self):
        first, second = case(), case(map_seed=22)
        second["summary"]["decisions"] = 3
        second["summary"]["bankruptcy"] = True
        result = build_report([first, second])
        self.assertEqual(result["groups"]["policy"]["games"], 2)
        self.assertEqual(result["groups"]["policy"]["bankruptcies"], 1)


if __name__ == "__main__":
    unittest.main()
