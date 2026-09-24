"""Keep final access explicit and judge the predeclared independent-seed matrix."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from evaluate_live import episode
from evaluate_registered import summaries_and_criteria, validate_registration


def fixture():
    settings = dict(action_horizon=512, ticks_per_action=128, starting_balance=100000,
        sampling_seeds=[20260923, 20260924, 20260925], primary_mode="sampled", diagnostic_mode="greedy",
        template_ids=["m02-template-07", "m02-template-08"], baselines=["wait", "random", "scripted", "one-bus"],
        minimum_sustained_per_model=5, bankruptcies_allowed=0, invalid_actions_allowed=0)
    return dict(format="openttd-rl-registered-holdout-1", status="registered-before-final-access",
        allow_tuning_from_results=False, protocol=settings,
        models=[dict(training_seed=seed, package=str(seed)) for seed in settings["sampling_seeds"]])


class RegisteredEvaluationTests(unittest.TestCase):
    def test_default_episode_refuses_final_before_reading_it(self):
        with patch.object(Path, "read_text", side_effect=AssertionError("final must not be read")):
            with self.assertRaisesRegex(ValueError, "dedicated registered"):
                episode(engine=Path("engine"), template=Path("m02-template-07.json"), output=Path("unused"),
                    reward={}, policy="wait", seed=23, evaluator=None, package=None)

    def test_protocol_and_model_identity_cannot_be_weakened(self):
        registration = fixture()
        validate_registration(registration)
        weakened = copy.deepcopy(registration)
        weakened["protocol"]["minimum_sustained_per_model"] = 4
        with self.assertRaises(ValueError):
            validate_registration(weakened)
        weakened = copy.deepcopy(registration)
        weakened["models"][1]["package"] = weakened["models"][0]["package"]
        with self.assertRaises(ValueError):
            validate_registration(weakened)

    def test_service_is_required_per_independent_model_and_cases_cannot_duplicate(self):
        registration = fixture()
        rows = []
        cases = [(None, policy) for policy in registration["protocol"]["baselines"]]
        cases += [(model["training_seed"], policy) for model in registration["models"] for policy in ("sampled", "greedy")]
        for training_seed, policy in cases:
            for template in registration["protocol"]["template_ids"]:
                for seed in ([20260923, 20260924, 20260925] if policy in ("random", "sampled") else [20260923]):
                    rows.append(dict(training_seed=training_seed, policy=policy, template_id=template, sampling_seed=seed,
                        passengers=100, operating_profit=200 if training_seed else 100,
                        operating_profit_less_capital=-100 if training_seed else -200,
                        balance_change=-100 if training_seed else -200, service_in_all_final_three_windows=True,
                        invalid_actions=0, bankruptcy=False))
        self.assertEqual(len(rows), 36)
        self.assertTrue(summaries_and_criteria(rows, registration)["acceptance_passed"])
        damaged = copy.deepcopy(rows)
        index = [i for i, row in enumerate(damaged) if row["training_seed"] == 20260925 and row["policy"] == "sampled"]
        for i in index[:2]:
            damaged[i]["service_in_all_final_three_windows"] = False
        # 16/18 total is insufficient when one model only serves 4/6 cases.
        self.assertFalse(summaries_and_criteria(damaged, registration)["acceptance_passed"])
        damaged = copy.deepcopy(rows)
        damaged[-1] = copy.deepcopy(damaged[-2])
        with self.assertRaisesRegex(ValueError, "matrix differs"):
            summaries_and_criteria(damaged, registration)


if __name__ == "__main__":
    unittest.main()
