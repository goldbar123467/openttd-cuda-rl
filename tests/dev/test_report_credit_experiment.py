"""Comparisons must not silently conflate budgets, objectives or trainer builds."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from report_credit_experiment import interval, validate_pair, verified_binary_chain


class CreditComparisonTests(unittest.TestCase):
    def test_rollout_pair_rejects_confounding_settings(self):
        old = dict(architecture="structured-mlp-v1", device="cuda:0", episode_action_horizon=128,
            environments=4, minibatch_size=32, epochs=4, training_templates=["a", "b"],
            development_templates=["c", "d"], openttd_sha256="engine", deterministic_cudnn=True,
            training_reward="balanced-economic", bridge_validation="fast", seed=23,
            requested_updates=128, rollout_length=32)
        new = dict(old, requested_updates=64, rollout_length=64)
        self.assertEqual(validate_pair(old, new, "rollout")["candidate"]["transitions"], 16384)
        for key, value in (("requested_updates", 128), ("epochs", 8), ("gae_lambda", 1.),
                           ("training_reward", "native"), ("seed", 24), ("episode_action_horizon", 512)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_pair(old, dict(new, **{key: value}), "rollout")
        validate_pair(old, dict(old, gae_lambda=1.), "lambda")
        with self.assertRaises(ValueError):
            validate_pair(old, new, "lambda")

    def test_cross_binary_requires_passed_directional_chain_for_device(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = [Path(temporary) / str(i) for i in range(2)]
            fixture = dict(kind="native-gae-option-verification", status="passed",
                cases=[dict(architecture="structured-mlp-v1", device="cuda:0", default_exact=True)])
            for path, pair in zip(paths, (("a", "b"), ("b", "c"))):
                path.write_text(json.dumps(dict(fixture, binaries=dict(zip(("reference", "candidate"), pair)))))
            verified_binary_chain("a", "c", paths[::-1], "structured-mlp-v1", "cuda:0")
            for left, right, evidence, device in (("a", "c", paths[:1], "cuda:0"),
                    ("c", "a", paths, "cuda:0"), ("a", "c", paths, "cpu")):
                with self.assertRaises(ValueError):
                    verified_binary_chain(left, right, evidence, "structured-mlp-v1", device)
            failed = copy.deepcopy(fixture)
            failed["cases"][0]["default_exact"] = False
            paths[1].write_text(json.dumps(dict(failed, binaries=dict(reference="b", candidate="c"))))
            with self.assertRaises(ValueError):
                verified_binary_chain("a", "c", paths, "structured-mlp-v1", "cuda:0")

    def test_only_independent_three_seed_interval(self):
        self.assertIsNone(interval([3.])["conditional_t_interval_95"])
        result = interval([1., 2., 3.])
        self.assertEqual(result["mean"], 2.)
        self.assertLess(result["conditional_t_interval_95"][0], 0.)
        self.assertGreater(result["conditional_t_interval_95"][1], 4.)


if __name__ == "__main__":
    unittest.main()
