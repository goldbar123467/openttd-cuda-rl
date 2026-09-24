"""Logging must see transformed rewards and preserve native rollout ownership."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
import train_live  # frozen transition type and reward adapters
from credit_trace import CreditTrace
from m08_trainer_client import Transition
from training_reward import UniversalDecisionCost
from audit_credit import reconstruct
from m07_ppo_reference import reference_vectors


class CreditTraceTests(unittest.TestCase):
    def test_offline_credit_matches_frozen_reference_with_terminal_and_truncation(self):
        rewards = [1., .5, 2., -1., 3., 4.]
        values = [.2, .1, .4, -.2, .3, .5]
        next_values = [.4, -.2, .3, .5, .7, .8]
        bootstrap = [True, True, True, False, False, True]
        continuation = [True, True, True, False, False, False]
        rows = [dict(zip(("reward", "old_value", "next_value", "bootstrap", "continuation"), fields))
                for fields in zip(rewards, values, next_values, bootstrap, continuation)]
        actual = reconstruct(rows, 2, .9, .8)
        expected = reference_vectors()
        for values, name in zip(actual, ("advantages", "normalized_advantages", "returns")):
            for value, reference in zip(values, expected[name]):
                self.assertAlmostEqual(value, reference, places=12)

    def test_logs_actual_native_reward_inputs_and_preserves_masks_and_bootstrap(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "trace.jsonl"
            native = Mock()
            native.update.return_value = SimpleNamespace(update=1, samples=2)
            trace = CreditTrace(native, path, 2, 1)
            reward = UniversalDecisionCost(trace)
            rows = [Transition([.2], [.4], [1, 1], 1, -.7, .4, .8, .5, True, False),
                    Transition([.3], [.6], [1, 0], 0, 0., .5, -.2, 0., False, False)]
            reward.update(rows)
            sent = native.update.call_args.args[0]
            self.assertEqual(sent[0].reward, .8 - 1/64)
            for actual, original in zip(sent, rows):
                self.assertIs(actual.legal_mask, original.legal_mask)
                for key in ("action", "old_log_probability", "old_value", "bootstrap", "continuation"):
                    self.assertEqual(getattr(actual, key), getattr(original, key))
            logged = json.loads(path.read_text())
            self.assertEqual(logged["transitions"][0]["reward"], sent[0].reward)
            self.assertTrue(logged["transitions"][0]["bootstrap"])
            self.assertFalse(logged["transitions"][0]["continuation"])


if __name__ == "__main__":
    unittest.main()
