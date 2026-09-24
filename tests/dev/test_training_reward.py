"""Reward experiments must not corrupt on-policy masks or behavior statistics."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/v1"))
from m08_trainer_client import Transition
from training_reward import BalancedEconomicReward, EconomicReward, ServicePotentialReward, UniversalDecisionCost, economic_reward, service_potential


class RewardTests(unittest.TestCase):
    def test_economic_reward_does_not_double_charge_wait_or_reward_free_toggling(self):
        for adapter in (EconomicReward, BalancedEconomicReward):
            with self.subTest(adapter=adapter.__name__):
                self.check_economic_adapter(adapter)

    def check_economic_adapter(self, adapter):
        client = Mock()
        policy = adapter(client)
        transitions = []
        for action, noop in ((0, -1 / 64), (1, 0.), (2, 0.)):
            components = [{"component_id": f"RC-{i+1:03d}", "weighted": v}
                          for i, v in enumerate((1., .25, -.1, noop, 0., 0., 0., 0.))]
            native = sum(c["weighted"] for c in components)
            policy.observe_transition(action, native, 4., 5.,
                                      reward_details={"scalar": native, "components": components})
            transitions.append(Transition([0.] * 256, [0.] * 32768, [1] * 41,
                                          action, -1.25, .4, native, .5, True, False))
        policy.update(transitions)
        sent = client.update.call_args.args[0]
        self.assertEqual(len({t.reward for t in sent}), 1)
        self.assertEqual(policy.updates[0]["potential_shaping_sum"], 0.)
        for original, transformed in zip(transitions, sent):
            self.assertIs(original.legal_mask, transformed.legal_mask)
            self.assertEqual((original.old_log_probability, original.old_value, original.next_value, original.bootstrap, original.continuation),
                             (transformed.old_log_probability, transformed.old_value, transformed.next_value, transformed.bootstrap, transformed.continuation))

    def test_economic_reward_fails_on_component_identity_drift(self):
        components = [{"component_id": f"RC-{i+1:03d}", "weighted": 0.} for i in range(8)]
        components[0], components[1] = components[1], components[0]
        with self.assertRaisesRegex(ValueError, "component order"):
            economic_reward(components)

    def test_potential_does_not_reward_extra_buses_and_clears_at_terminal(self):
        snapshot = {"pools": {"companies": 1, "stations": 2, "depots": 1}}
        source = {"company_present": True, "primary_bus_count": 1, "stopped_primary_bus_count": 0}
        self.assertEqual(service_potential(snapshot, source), 5.)
        source.update(primary_bus_count=8, stopped_primary_bus_count=7)
        self.assertEqual(service_potential(snapshot, source), 5.)
        self.assertEqual(service_potential(snapshot, source, terminal=True), 0.)
        # Time limits are not terminals: keep the potential of the bootstrap state.
        self.assertEqual(service_potential(snapshot, source, terminal=False), 5.)

    def test_discounted_shaping_telescopes_and_stop_start_cycle_is_not_profitable(self):
        policy = ServicePotentialReward(Mock())
        potentials = [0., 1., 3., 5., 4., 5.]
        changes = [policy.observe_transition(1, 0., a, b)["shaping"] for a, b in zip(potentials, potentials[1:])]
        actual = sum(policy.gamma ** i * r for i, r in enumerate(changes))
        self.assertAlmostEqual(actual, policy.gamma ** len(changes) * potentials[-1] - potentials[0])
        stop = policy.observe_transition(33, 0., 5., 4.)["shaping"]
        start = policy.observe_transition(25, 0., 4., 5.)["shaping"]
        self.assertLess(stop + policy.gamma * start, 0.)

    def test_misaligned_potential_rewards_never_reach_ppo(self):
        client = Mock()
        policy = ServicePotentialReward(client)
        policy.observe_transition(1, 0., 0., 1.)
        with self.assertRaisesRegex(ValueError, "differs from the on-policy rollout"):
            policy.update([])
        client.update.assert_not_called()

    def test_equivalent_wait_and_free_toggle_have_same_decision_cost(self):
        client = Mock()
        policy = UniversalDecisionCost(client)
        def transition(action, reward):
            return Transition([0.] * 256, [0.] * 32768, [1] * 41, action, -1.25, 0.4,
                              reward, 0.5, True, False)
        native = [transition(0, -1 / 64), transition(1, 0.), transition(2, 0.)]
        policy.update(native)
        sent = client.update.call_args.args[0]
        self.assertEqual([t.reward for t in sent], [-1 / 64] * 3)
        self.assertEqual([t.reward for t in native], [-1 / 64, 0., 0.])
        for old, new in zip(native, sent):
            self.assertIs(old.legal_mask, new.legal_mask)
            self.assertIs(old.structured, new.structured)
            self.assertIs(old.spatial, new.spatial)
            self.assertEqual((old.old_log_probability, old.old_value, old.next_value, old.bootstrap, old.continuation),
                             (new.old_log_probability, new.old_value, new.next_value, new.bootstrap, new.continuation))
        self.assertEqual(policy.updates[0]["extra_decision_cost"], 2 / 64)


if __name__ == "__main__":
    unittest.main()
