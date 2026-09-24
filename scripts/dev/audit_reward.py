#!/usr/bin/env python3
"""Attribute native reward and rescore completed traces before economic training."""
import argparse
import json
from pathlib import Path
import statistics
import sys

from local import ROOT, source_identity, write_json
from training_reward import balanced_economic_reward, economic_reward
sys.path.insert(0, str(ROOT / "scripts/v1"))
from m06_reward_reference import compute_reward


def audit(roots, output, training_reward="economic", gamma=0.99):
    if not 0 < gamma <= 1:
        raise ValueError("Discount factor must be in (0,1]")
    transform = {"economic": economic_reward, "balanced-economic": balanced_economic_reward}[training_reward]
    return_name = training_reward.replace("-", "_") + "_return_on_same_actions"
    output.mkdir(parents=True, exist_ok=False)
    contract = json.loads((ROOT / "config/v1/m06-reward-trajectory-contract.json").read_text())
    rows = []
    for root in roots:
        run = json.loads((root / "run.json").read_text())
        if run["status"] != "completed":
            raise ValueError("Reward audit requires completed source evaluations")
        for path in sorted(root.rglob("episode.json")):
            summary = json.loads(path.read_text())
            if summary["status"] != "completed":
                raise ValueError("Reward audit requires complete native episodes")
            totals = [0.] * 8
            proposed = 0.
            discounted_native = discounted_proposed = 0.
            for step, line in enumerate((path.parent / "actions.jsonl").read_text().splitlines()):
                transition = json.loads(line)
                if transition["step"] != step + 1:
                    raise ValueError("Reward audit requires consecutive action indices")
                reward = compute_reward(transition["raw"], contract)
                if reward.scalar != transition["reward"]:
                    raise ValueError("Reward trace disagrees with frozen CPU reference")
                for index, value in enumerate(reward.weighted):
                    totals[index] += value
                components = [{"component_id": f"RC-{i+1:03d}", "weighted": value} for i, value in enumerate(reward.weighted)]
                transformed = transform(components)[0]
                proposed += transformed
                discounted_native += gamma ** step * reward.scalar
                discounted_proposed += gamma ** step * transformed
            rows.append({"source": str(path), "evaluation_root": str(root.resolve()), "package": run.get("package"),
                         "policy": summary["policy"], "template_id": summary["template_id"],
                         "passengers": summary["passengers"], "operating_profit": summary["operating_profit"],
                         "native_return": sum(totals), "native_component_totals": totals,
                         return_name: proposed, "discounted_native_return": discounted_native,
                         "discounted_training_return_on_same_actions": discounted_proposed})
    # Different trained models can both be called "sampled" or "greedy". Do
    # not pool their outcomes simply because the action-selection label matches.
    means = [{"evaluation_root": evaluation, "policy": policy,
              **{name: statistics.mean(row[name] for row in rows if (row["evaluation_root"], row["policy"]) == (evaluation, policy))
              for name in ("passengers", "operating_profit", "native_return", return_name,
                           "discounted_native_return", "discounted_training_return_on_same_actions")}}
             for evaluation, policy in sorted({(row["evaluation_root"], row["policy"]) for row in rows})]
    write_json(output / "audit.json", {"source": source_identity(), "training_reward": training_reward, "gamma": gamma,
               "discount_scope": "Finite executed episode, discount starts at its first action; no critic bootstrap is added",
               "episodes": rows, "policy_means": means,
               "claim": "offline reward-objective audit of executed traces, not evidence of learning under the new objective"})
    print(json.dumps(means, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluations", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--training-reward", choices=("economic", "balanced-economic"), default="economic")
    parser.add_argument("--gamma", type=float, default=0.99)
    args = parser.parse_args()
    audit(args.evaluations, args.output, args.training_reward, args.gamma)
