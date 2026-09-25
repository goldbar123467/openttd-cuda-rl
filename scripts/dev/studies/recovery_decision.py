"""Frozen A0-A3 advancement from complete, identity-verified development cases."""
import math

from eval_stats import nested_bootstrap, pair_episodes
from studies.protocol_v2 import require_development_matrix


def decide_arm(arm_id, training, candidates, controls, protocol, *, bootstrap_iterations=10000):
    arm = next((a for a in protocol["arms"] if a["id"] == arm_id), None)
    if arm is None:
        raise ValueError("Arm has no prospective execution protocol")
    seeds = protocol["training_seeds"]
    if len(training) != len(seeds) or sorted(r["training_seed"] for r in training) != sorted(seeds):
        raise ValueError("Every registered training seed, including failures, must be retained exactly once")
    completed = []
    for row in training:
        if row["status"] not in ("completed", "early-stopped", "failed"):
            raise ValueError("Training is unfinished or has an unknown disposition")
        if row["status"] == "completed":
            if row["decisions"] != protocol["fixed_training"]["decisions"]:
                raise ValueError("Completed training differs from its registered budget")
            completed.append(row["training_seed"])
    if any(c["training_seed"] not in completed for c in candidates):
        raise ValueError("Failed or unregistered seeds cannot contribute selected intermediate models")
    for seed in completed:
        require_development_matrix([c for c in candidates if c["training_seed"] == seed], protocol)
    names = protocol["controls"]["controllers"]
    if any(c["controller"] not in names for c in controls):
        raise ValueError("Unregistered control")
    for name in names:
        require_development_matrix([c for c in controls if c["controller"] == name], protocol)
    for case in [*candidates, *controls]:
        if case["guidance"] != arm["guide"]:
            raise ValueError("Study controls and policies must use the exact same guide")
        if case["execution_status"] not in ("passed", "failed"):
            raise ValueError("Evaluation is unfinished or has an unknown disposition")
        if case["execution_status"] == "passed":
            s = case["summary"]
            for metric in ("operating_profit", "cash_result_excluding_financing"):
                if not math.isfinite(s[metric]):
                    raise ValueError("Nonfinite completed economic outcome")
    successful = [c for c in candidates if c["execution_status"] == "passed"]
    greedy_service = {seed: sum(c["summary"]["service_in_all_final_three_windows"] for c in successful
                               if c["training_seed"] == seed and c["mode"] == "greedy") for seed in seeds}
    checks = {
        "all_three_training_seeds_complete": len(completed) == len(seeds),
        "all_scheduled_evaluations_complete": all(c["execution_status"] == "passed" for c in [*candidates, *controls]),
        "zero_invalid_actions": all(c["summary"]["invalid_actions"] == 0 for c in successful),
        "zero_bankruptcies": all(not c["summary"]["bankruptcy"] for c in successful),
        "greedy_service_at_least_seven_maps_every_seed": all(v >= protocol["advancement"]["greedy_sustained_maps_per_training_seed"] for v in greedy_service.values()),
        "positive_profit_and_cash_at_least_two_training_seeds": False,
        "positive_pooled_profit_and_cash": False,
    }
    paired = {}
    if checks["all_three_training_seeds_complete"] and checks["all_scheduled_evaluations_complete"]:
        policy = [{"training_seed": c["training_seed"], "map_seed": c["map_seed"], "action_seed": c["sampling_seed"], **c["summary"]}
                  for c in candidates if c["mode"] == "sampled"]
        baseline = [{"map_seed": c["map_seed"], "action_seed": c["sampling_seed"], **c["summary"]}
                    for c in controls if c["controller"] == "uniform" and c["mode"] == "sampled"]
        for metric in ("operating_profit", "cash_result_excluding_financing"):
            paired[metric] = nested_bootstrap(pair_episodes(policy, baseline, metric), iterations=bootstrap_iterations)
        profit, cash = (paired[key] for key in ("operating_profit", "cash_result_excluding_financing"))
        checks["positive_profit_and_cash_at_least_two_training_seeds"] = sum(
            profit["per_training_seed"][s] > 0 and cash["per_training_seed"][s] > 0 for s in seeds
        ) >= protocol["advancement"]["sampled_positive_paired_profit_and_cash_training_seeds"]
        checks["positive_pooled_profit_and_cash"] = profit["mean"] > 0 and cash["mean"] > 0
    return {"arm": arm_id, "eligible": all(checks.values()), "checks": checks,
            "greedy_sustained_maps_by_training_seed": greedy_service, "sampled_paired_vs_uniform": paired,
            "failed_training_seeds": [r["training_seed"] for r in training if r["status"] != "completed"],
            "failed_evaluation_cases": sum(c["execution_status"] == "failed" for c in [*candidates, *controls])}


def select_arm(results, protocol):
    ids = [r["arm"] for r in results]
    mandatory = [a["id"] for a in protocol["arms"]]
    if len(set(ids)) != len(ids) or set(ids) != set(mandatory):
        raise ValueError("All mandatory arms must finish before held-out selection")
    by_id = {r["arm"]: r for r in results}
    return next((arm for arm in protocol["selection"]["order"] if arm in by_id and by_id[arm]["eligible"]), None)
