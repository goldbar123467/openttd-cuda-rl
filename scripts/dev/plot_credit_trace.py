#!/usr/bin/env python3
"""Explain GAE on one recorded rollout; counterfactual values are offline only."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from audit_credit import reconstruct
from local import write_json


def run(args):
    config_path = args.training_run / "run.json"
    trace_path = args.training_run / "credit-trace.jsonl"
    config = json.loads(config_path.read_text())
    if config["status"] != "completed" or config.get("resume_from") or config.get("gae_lambda", .95) != .95:
        raise ValueError("Figure requires a completed unresumed lambda 0.95 training run")
    with trace_path.open() as stream:
        update = json.loads(next(stream))
    rows = update["transitions"]
    environments = config["environments"]
    if update["update"] != 1 or len(rows) != environments * config["rollout_length"]:
        raise ValueError("First rollout layout differs")
    # First update, environment 0: chosen by position, never by economic result.
    actual, _, _ = reconstruct(rows, environments, .99, .95)
    alternative, _, _ = reconstruct(rows, environments, .99, 1.)
    selected = rows[::environments]
    steps = list(range(1, len(selected) + 1))
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(3, 1, figsize=(11.8, 8.6))
    axes[0].bar(steps, [row["reward"] for row in selected], color="#527b91", width=.9)
    construction = [(i + 1, row["reward"]) for i, row in enumerate(selected) if 3 <= row["action"] <= 16]
    if construction:
        axes[0].scatter(*zip(*construction), marker="v", color="#bc532c", zorder=3, label="Construction / bus purchase")
    axes[0].set_title("Actual rewards entering C++ PPO · first rollout, environment 0", loc="left", weight="bold")
    axes[0].set_ylabel("Balanced reward")
    axes[0].legend(frameon=False, loc="lower right")
    axes[1].plot(steps, actual[::environments], color="#167b9a", linewidth=2, label="Actual GAE: lambda 0.95")
    axes[1].plot(steps, alternative[::environments], color="#d16a22", linewidth=2, label="Offline recomputation: lambda 1.0")
    axes[1].set_title("Advantages recomputed from the same actions, rewards and critic values", loc="left", weight="bold")
    axes[1].set_ylabel("Raw advantage")
    axes[1].legend(frameon=False, loc="lower right")
    axes[1].set_xlabel("Decision in the recorded rollout")
    lags = list(range(64))
    for coefficient, color in ((.95, "#167b9a"), (1., "#d16a22")):
        axes[2].plot(lags, [(.99 * coefficient) ** lag for lag in lags], color=color, linewidth=2,
                     label=f"lambda {coefficient}: (0.99 × lambda)^lag")
    axes[2].set_title("How much a later TD error contributes to an earlier advantage", loc="left", weight="bold")
    axes[2].set_ylabel("Trace weight")
    axes[2].set_xlabel("Decisions after the action")
    axes[2].legend(frameon=False, loc="upper right")
    axes[2].set_ylim(-.025, 1.05)
    for axis in axes:
        axis.axhline(0, linewidth=.7, color="#777777")
        axis.grid(axis="y", alpha=.15)
        axis.set_xlim(0, 64)
    fig.suptitle("PPO construction credit: a longer trace changes attribution", weight="bold", fontsize=17, y=.985)
    fig.text(.08, .026, "Gamma = 0.99. The lambda 1.0 curve is an offline counterfactual, not a new policy or a learning result.\n"
        "PPO later normalizes advantages across the rollout. Native terminal/truncation flags and boundary bootstraps are retained.", fontsize=9)
    fig.subplots_adjust(left=.085, right=.975, top=.925, bottom=.115, hspace=.61)
    args.output.mkdir(parents=True, exist_ok=False)
    for extension in ("png", "svg"):
        fig.savefig(args.output / ("construction-credit." + extension), dpi=180)
    write_json(args.output / "figure.json", {"matplotlib": matplotlib.__version__,
        "selection": {"update": 1, "environment": 0}, "gamma": .99, "actual_lambda": .95,
        "counterfactual_lambda": 1., "weight_at_lag_32": {"lambda_095": (.99 * .95) ** 32, "lambda_1": .99 ** 32},
        "inputs": {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in (config_path, trace_path)}})
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("training-run", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
