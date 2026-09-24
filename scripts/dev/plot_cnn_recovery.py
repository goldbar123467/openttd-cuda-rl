#!/usr/bin/env python3
"""Plot executed CNN training and the separate checkpoint recovery diagnostic."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from local import write_json


def run(args):
    selection = json.loads(args.selection.read_text())
    report = json.loads(args.comparison.read_text())
    seeds = sorted(row["seed"] for row in selection["selections"])
    colors = ["#167b9a", "#d16a22", "#7565aa"]
    inputs = {}
    def read(path):
        inputs[str(path.resolve())] = hashlib.sha256(path.read_bytes()).hexdigest()
        return json.loads(path.read_text())
    read(args.selection); read(args.comparison)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titleweight": "bold"})
    fig, axes = plt.subplots(2, 2, figsize=(12.4, 9))
    for seed, color in zip(seeds, colors, strict=True):
        choice = next(row for row in selection["selections"] if row["seed"] == seed)
        root = Path(choice["training_run"])
        training = read(root / "run.json")
        if training["episode_action_horizon"] != 128 or training["rollout_length"] != 32 or training["environments"] != 4:
            raise ValueError("Unexpected training episode/update alignment")
        by_episode = {}
        for path in root.glob("episode-metrics/m07-train-e*-p*.json"):
            match = re.fullmatch(r"m07-train-e(\d+)-p(\d+)\.json", path.name)
            row = read(path)
            if row["actions"] == 0:
                continue
            if row["actions"] != 128 or row["status"] != "completed":
                raise ValueError("This figure requires complete aligned training episodes")
            by_episode.setdefault(int(match[2]), []).append(row["passengers"])
        if sorted(by_episode) != list(range(32)) or any(len(rows) != 4 for rows in by_episode.values()):
            raise ValueError("Missing training episode or environment")
        axes[0, 0].plot([4 * (e + 1) for e in sorted(by_episode)],
                       [statistics.mean(by_episode[e]) for e in sorted(by_episode)], color=color, label=str(seed))
        updates = training["training"]["updates"]
        axes[0, 1].plot([u["update"] for u in updates], [u["entropy"] for u in updates], color=color)
    axes[0, 0].set(title="Training passenger service declines", ylabel="Passengers per 128-action episode", xlabel="PPO update")
    axes[0, 0].legend(title="Training seed", frameon=False, fontsize=9)
    axes[0, 1].set(title="The action distribution also narrows", ylabel="Mean policy entropy (nats)", xlabel="PPO update")
    for axis in axes[0]:
        axis.set_xlim(0, 130)
        axis.set_ylim(bottom=0)
        axis.grid(axis="y", alpha=.17)
    for axis, metric, title, ylabel in (
        (axes[1, 0], "passengers", "Earlier checkpoints recover sampled service", "Full-episode passenger deliveries"),
        (axes[1, 1], "operating_profit", "Operating results remain inconsistent", "Native operating profit")):
        for offset, label, shade in ((-.18, "selected", "#167b9a"), (.18, "final", "#b6bdc2")):
            values = report["results"][label]["sampled"]["statistics"][metric]["training_seed_means"]
            axis.bar([i + offset for i in range(3)], values, .33, color=shade, label="Training-selected" if label == "selected" else "Final update")
        axis.set_xticks(range(3), [f"Seed {seed}\nSelected update {report['selected_updates'][str(seed)]}" for seed in seeds])
        axis.set(title=title, ylabel=ylabel)
        axis.axhline(0, color="#555555", linewidth=.7)
        axis.grid(axis="y", alpha=.17)
        axis.set_axisbelow(True)
    axes[1, 0].legend(frameon=False, fontsize=9)
    fig.suptitle("Earlier CNN service disappears during training", fontsize=18, weight="bold", y=.98)
    fig.text(.5, .938, "Three independent training seeds · 16,384 transitions per seed · fixed development scenarios", ha="center", fontsize=11)
    fig.text(.075, .038, "Bars: six sampled episodes per seed. Training-only selection counts the full training budget. Greedy play fails at both checkpoints.\n"
             "Recovery was tested after observing final-model failure. This is a development diagnostic, not held-out validation or a causal explanation.", fontsize=9)
    fig.subplots_adjust(left=.085, right=.975, top=.87, bottom=.12, hspace=.45, wspace=.27)
    args.output.mkdir(parents=True, exist_ok=False)
    for extension in ("png", "svg"):
        fig.savefig(args.output / ("cnn-recovery." + extension), dpi=180)
    write_json(args.output / "figure.json", {"matplotlib": matplotlib.__version__, "inputs": inputs,
               "scope": "Executed training curves and full development checkpoint evaluations; three training seeds"})
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("selection", "comparison", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
