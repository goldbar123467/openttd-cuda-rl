from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from verify_v2_checkpoint_boundaries import native_arguments


class NativeArgumentsTests(unittest.TestCase):
    def test_each_mismatch_changes_only_its_own_setting(self):
        config = {"device": "cpu", "rollout_steps": 64, "gae_lambda": 1.,
                  "entropy_coefficient": .001, "financial_features": "signed-log-v1"}
        def settings(case):
            result = {"--rollout-length": "32", "--gae-lambda": ".95", "--entropy-coefficient": ".01", "--financial-features": "raw"}
            args = native_arguments(config, case, 725)
            result.update(zip(args[::2], args[1::2]))
            return result
        baseline = settings("no-overwrite")
        for case, flag in (("wrong-rollout", "--rollout-length"), ("wrong-lambda", "--gae-lambda"),
                           ("wrong-entropy", "--entropy-coefficient"), ("wrong-financial-features", "--financial-features")):
            changed = settings(case)
            self.assertEqual([k for k in baseline if baseline[k] != changed[k]], [flag])

    def test_default_settings_remain_compatible(self):
        self.assertEqual(native_arguments({"device": "cpu", "rollout_steps": 32}, "no-overwrite", 1),
                         ["--device", "cpu", "--seed", "1"])


if __name__ == "__main__":
    unittest.main()
