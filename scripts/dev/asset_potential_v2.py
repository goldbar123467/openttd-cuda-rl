"""Finite-episode capital ledger potential; raw native economics stay unchanged.

The ledger is explicit history-dependent reward state, not a resale valuation
deduced from physical assets. Per-decision clipping can make identical assets
reached by different histories have different ledger values. This version is
restricted to the one-bus guide's monotone construction actions. Reset-only
recovery starts a fresh ledger; no mid-game ledger reconstruction is supported.
"""
import math

SCHEMA = "development-v2-live-reward-2-asset-potential"
LEDGER = "clipped-capital-history-v1"
SUPPORTED_ACTIONS = frozenset(("WAIT", "MANAGE_LOAN", "BUILD_ROAD_PATH", "BUILD_BUS_STOP",
                               "BUILD_ROAD_DEPOT", "BUY_BUS", "SET_ROUTE", "START_VEHICLE"))


class AssetPotential:
    def __init__(self, gamma, horizon):
        if not math.isfinite(gamma) or not 0 <= gamma <= 1 or type(horizon) is not int or not 1 <= horizon <= 512:
            raise ValueError("Invalid potential discount or finite episode bound")
        self.gamma, self.horizon = gamma, horizon
        self.potential = 0.0
        self.decisions = 0
        self.closed = False

    def apply(self, raw, transition):
        if self.closed or self.decisions >= self.horizon:
            raise ValueError("Potential ledger must reset at each episode boundary")
        if transition["action"]["family"] not in SUPPORTED_ACTIONS:
            raise ValueError("Asset-potential ledger forbids sales, demolition and unsupported actions")
        spent = -raw["components"]["capital"]
        if not math.isfinite(spent) or not 0 <= spent <= 1:
            raise ValueError("Potential requires the exact bounded capital reward component")
        before = self.potential
        after = 0.0 if transition["terminal"] else before + spent
        self.decisions += 1
        if not 0 <= after <= self.decisions <= self.horizon:
            raise ValueError("Potential exceeds its explicit finite-episode bound")
        shaping = self.gamma * after - before
        reward = raw["reward"] + shaping
        if not math.isfinite(reward):
            raise ValueError("Nonfinite shaped reward")
        self.potential = after
        self.closed = bool(transition["terminal"] or transition["truncated"])
        return {**raw, "schema_version": SCHEMA, "native_reward": raw["reward"], "reward": reward,
                "potential_ledger": LEDGER, "potential_before": before, "potential_after": after,
                "capital_added": spent, "shaping": shaping, "shaping_gamma": self.gamma,
                "ledger_decisions": self.decisions, "ledger_bound": self.horizon}
