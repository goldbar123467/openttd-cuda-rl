"""Explicit development reward transform; native game rewards remain intact."""
import dataclasses
import statistics


def service_potential(snapshot, source, *, terminal=False):
    """Bounded public-state potential for the single-company V1 scenario only."""
    pools = snapshot["pools"]
    if pools["companies"] > 1:
        raise ValueError("Service potential is restricted to a single company")
    if terminal or not source["company_present"]:
        return 0.0
    return float(min(pools["stations"], 2) + min(pools["depots"], 1)
                 + min(source["primary_bus_count"], 1)
                 + int(source["primary_bus_count"] > source["stopped_primary_bus_count"]))


class UniversalDecisionCost:
    """Extend the native WAIT cost to every decision, removing free toggling.

    M06 charges WAIT 1/64. Subtracting 1/64 from each non-WAIT transition
    makes the decision cost independent of which action was chosen. PPO,
    behavior probabilities, exact masks, values and bootstrap flags are reused.
    """

    def __init__(self, client):
        self.client = client
        self.updates = []

    def act(self, *args, **kwargs):
        return self.client.act(*args, **kwargs)

    def update(self, transitions):
        adapted = [dataclasses.replace(t, reward=t.reward - (1 / 64 if t.action != 0 else 0))
                   for t in transitions]
        result = self.client.update(adapted)
        self.updates.append({"mean_native_reward": statistics.mean(t.reward for t in transitions),
                             "mean_training_reward": statistics.mean(t.reward for t in adapted),
                             "extra_decision_cost": sum(t.action != 0 for t in transitions) / 64})
        return result


class ServicePotentialReward(UniversalDecisionCost):
    """Add gamma*Phi(next)-Phi(current) to the universal decision-cost reward.

    Gamma matches the unchanged native PPO config (0.99). Terminal potential is
    zero; time-limit truncations keep the potential of the bootstrapped state.
    The observer queue is checked against the collector's ordered transitions.
    """
    gamma = 0.99

    def __init__(self, client):
        super().__init__(client)
        self.pending = []

    def observe_transition(self, action, native_reward, before, after, *, reward_details=None):
        entry = {"action": action, "native_reward": native_reward,
                 "potential_before": before, "potential_after": after,
                 "shaping": self.gamma * after - before,
                 "extra_decision_cost": 1 / 64 if action != 0 else 0}
        entry["training_reward"] = native_reward + entry["shaping"] - entry["extra_decision_cost"]
        self.pending.append(entry)
        return entry

    def update(self, transitions):
        if len(transitions) != len(self.pending) or any(
                t.action != r["action"] or t.reward != r["native_reward"]
                for t, r in zip(transitions, self.pending)):
            raise ValueError("Potential reward stream differs from the on-policy rollout")
        adapted = [dataclasses.replace(t, reward=r["training_reward"])
                   for t, r in zip(transitions, self.pending)]
        result = self.client.update(adapted)
        self.updates.append({"mean_native_reward": statistics.mean(t.reward for t in transitions),
                             "mean_training_reward": statistics.mean(t.reward for t in adapted),
                             "extra_decision_cost": sum(r["extra_decision_cost"] for r in self.pending),
                             "potential_shaping_sum": sum(r["shaping"] for r in self.pending),
                             "economic_adjustment_sum": sum(r.get("economic_adjustment", 0.) for r in self.pending)})
        self.pending.clear()
        return result


def economic_reward(components):
    """Opt-in economics objective using the bridge's validated bounded terms.

    Passenger /128, operating profit /256, and capital -/1024; one uniform
    1/64 decision cost. Rejection, idle, loss and bankruptcy penalties retain
    their native coefficients. This changes the objective, not the game ledger.
    """
    return rescaled_economic_reward(components, (1 / 8, 16, 16, 0, 1, 1, 1, 1))


def balanced_economic_reward(components):
    """Intermediate opt-in objective: passengers /64, profit /1024, capital -/4096.

    Compared with the native objective this values profit/capital four times
    more and passengers four times less. Native clipping and failure terms are
    retained; these are reward weights, not accounting or new engine semantics.
    """
    return rescaled_economic_reward(components, (1 / 4, 4, 4, 0, 1, 1, 1, 1))


def rescaled_economic_reward(components, factors):
    if [component["component_id"] for component in components] != [f"RC-{i:03d}" for i in range(1, 9)]:
        raise ValueError("Economic reward component order differs from native M06")
    scaled = [component["weighted"] * factor for component, factor in
              zip(components, factors, strict=True)]
    scaled[3] = -1 / 64
    return sum(scaled), scaled


class EconomicReward(ServicePotentialReward):
    """Reuse the ordered on-policy reward adapter with no progress potential."""

    transform = staticmethod(economic_reward)

    def observe_transition(self, action, native_reward, before, after, *, reward_details=None):
        if reward_details is None or reward_details["scalar"] != native_reward:
            raise ValueError("Economic reward requires matching native components")
        transformed, components = self.transform(reward_details["components"])
        decision_cost = 1 / 64 + reward_details["components"][3]["weighted"]
        entry = {"action": action, "native_reward": native_reward, "training_reward": transformed,
                 "rescaled_components": components, "shaping": 0., "extra_decision_cost": decision_cost,
                 "economic_adjustment": transformed - native_reward + decision_cost}
        self.pending.append(entry)
        return entry


class BalancedEconomicReward(EconomicReward):
    """Use the same validated on-policy adapter with the intermediate objective."""

    transform = staticmethod(balanced_economic_reward)
