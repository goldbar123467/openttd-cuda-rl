#!/usr/bin/env python3
"""Plot training-seed uncertainty from a verified architecture comparison."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def run(args):
    data = json.loads(args.comparison.read_text())
    names = {"structured-mlp-v1": "MLP", "spatial-cnn-v1": "CNN", "combined-cnn-mlp-v1": "Combined"}
    colors = {"structured-mlp-v1": "#2563a6", "spatial-cnn-v1": "#c26435", "combined-cnn-mlp-v1": "#418156"}
    metrics = [("passengers", "Passengers delivered"), ("operating_profit", "Operating profit"),
               ("operating_profit_less_capital", "Profit less net capital")]
    groups = [(name, policy, summary) for name, policies in data["architectures"].items()
              for policy, summary in policies.items()]
    cash_available = all("balance_change" in summary["statistics"] for _, _, summary in groups)
    if cash_available:
        metrics[-1] = ("balance_change", "Cash change, including capital")
    fig, axes = plt.subplots(1, 3, figsize=(15, 6))
    for ax, (metric, title) in zip(axes, metrics, strict=True):
        ax.axhline(0, color="#bac2cc", linewidth=1)
        for x, (name, policy, summary) in enumerate(groups):
            stats = summary["statistics"][metric]
            mean = stats["mean"]
            low, high = stats["conditional_t_interval_95"]
            ax.errorbar(x, mean, yerr=[[mean - low], [high - mean]], fmt="D", color=colors[name],
                        markersize=6, capsize=6, linewidth=2, zorder=3)
            ax.scatter([x - .12, x, x + .12], stats["training_seed_means"], s=34,
                       facecolors="white", edgecolors=colors[name], linewidth=1.4, zorder=4)
        ax.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=16)
        ax.set_xticks(range(len(groups)), [policy.title() for _, policy, _ in groups])
        for name in data["architectures"]:
            positions = [index for index, (group_name, _, _) in enumerate(groups) if group_name == name]
            ax.text(sum(positions) / len(positions), -.18, names[name], ha="center", va="top",
                    transform=ax.get_xaxis_transform(), fontsize=10, fontweight="bold", color=colors[name])
        ax.set_xlim(-.5, len(groups) - .5)
        ax.grid(axis="y", color="#e5e9ee", linewidth=.7)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["bottom", "left"]].set_color("#bac2cc")
        ax.tick_params(axis="both", labelsize=9, color="#bac2cc")
        ax.ticklabel_format(axis="y", style="plain", useOffset=False)
        ax.set_ylabel("Passengers" if metric == "passengers" else "Native OpenTTD currency units", fontsize=10)
    transitions = data["matched_training"]["requested_updates"] * data["matched_training"]["rollout_length"] * data["matched_training"]["environments"]
    fig.suptitle(f"Live OpenTTD architecture comparison\n{transitions:,} training transitions per model · 3 training seeds · 2 development maps", x=.06,
                 ha="left", fontsize=16, fontweight="bold")
    fig.text(.06, .095, "Hollow circles: training-seed means. Diamonds: overall means. Bars: conditional 95% Student-t intervals (n=3).", fontsize=10)
    fig.text(.06, .055, "Sampling repeats are averaged within each model. Greedy and sampled evaluations both use full 512-action episodes.", fontsize=10)
    footer = "Cash change includes capital and monthly other expenses." if cash_available else "Profit less capital omits monthly other cash expenses."
    fig.text(.06, .018, "Fixed development maps, not held-out results. " + footer, fontsize=10, color="#5c6672")
    fig.subplots_adjust(left=.06, right=.98, top=.73, bottom=.24, wspace=.38)
    args.output.mkdir(parents=True, exist_ok=False)
    for suffix in ("png", "svg"):
        fig.savefig(args.output / f"architectures.{suffix}", dpi=170, facecolor="white")
    plt.close(fig)
    (args.output / "provenance.json").write_text(json.dumps({
        "comparison": str(args.comparison.resolve()), "comparison_sha256": hashlib.sha256(args.comparison.read_bytes()).hexdigest(),
        "plotter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "matplotlib_version": matplotlib.__version__, "claim": data["claim"]}, indent=2) + "\n")
    print(args.output.resolve())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
