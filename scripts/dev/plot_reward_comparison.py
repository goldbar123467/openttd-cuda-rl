#!/usr/bin/env python3
"""Show paired training seeds and the service/cash tradeoff of a reward trial."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter

from local import write_json


def run(args):
    data = json.loads(args.comparison.read_text())
    pairs = data["paired_training_seed_differences"]["sampled"]
    stats = data["training_seed_statistics"]["sampled"]
    colors = ["#167b9a", "#d16a22", "#7565aa"]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 3, figsize=(12.8, 5.8))
    for axis, metric, title in zip(axes, ("passengers", "operating_profit", "balance_change"),
                                 ("Passenger deliveries", "Native operating profit", "Cash after capital")):
        values = stats[metric]["training_seed_means"]
        if len(values) != 3 or set(values) != set(pairs[metric]["new_minus_old_by_seed"]):
            raise ValueError("Figure requires the matched three-seed comparison")
        for (seed, new), color in zip(sorted(values.items()), colors, strict=True):
            old = new - pairs[metric]["new_minus_old_by_seed"][seed]
            axis.plot([0, 1], [old, new], "o-", color=color, markersize=7, linewidth=1.5, label="Seed " + seed)
        axis.axhline(data["summaries"]["one-bus"]["mean_" + metric], color="#60666b", linestyle="--", linewidth=1.2,
                     label="One-bus control")
        axis.set_title(title, weight="bold", pad=15)
        axis.set_xticks([0, 1], ["Native reward", "Balanced reward"])
        axis.set_xlim(-.2, 1.2)
        axis.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        axis.grid(axis="y", alpha=.17)
        axis.margins(y=.15)
    fig.suptitle("Lower spending does not guarantee reliable service", fontsize=19, weight="bold", y=.98)
    fig.text(.5, .90, "Each point: one trained MLP, averaged over six sampled development episodes", ha="center")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, ncol=4, loc="lower center", bbox_to_anchor=(.5, .095), frameon=False, fontsize=10)
    fig.text(.065, .028, "Matched 16,384-transition budgets · three independent training seeds · two fixed development maps\n"
             "Balanced greedy play failed in all six episodes. Lines are paired seeds; this is development evidence, not held-out generalization.", fontsize=9)
    fig.subplots_adjust(left=.075, right=.975, bottom=.25, top=.78, wspace=.37)
    args.output.mkdir(parents=True, exist_ok=False)
    for extension in ("png", "svg"):
        fig.savefig(args.output / ("reward-tradeoff." + extension), dpi=180)
    write_json(args.output / "figure.json", {"matplotlib": matplotlib.__version__,
        "input": str(args.comparison.resolve()), "input_sha256": hashlib.sha256(args.comparison.read_bytes()).hexdigest()})
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("comparison", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
