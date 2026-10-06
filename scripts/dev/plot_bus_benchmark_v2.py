#!/usr/bin/env python3
"""Export static Matplotlib figures from a verified frozen benchmark summary."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def render(results, output):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    import numpy as np
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False, "savefig.dpi": 170})
    models = ("one-game-1000", "one-game-256", "four-game-256", "seven-game-256")
    labels = ("1 game\n1,000 updates", "1 game\n256 updates", "4 games\n256 updates", "7 games\n256 updates")
    x = np.arange(4)
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    series = (("Development: game 8", "#427bb7", -.18), ("Test: games 9–10", "#319575", .18))
    for title, color, offset in series:
        values, counts = [], []
        for model in models:
            data = results["offline"][model]
            metric = (data["corpora"]["development"]["overall"] if offset < 0 else data["combined_test"])
            exact = metric.get("unique_exact_rows", metric.get("exact"))
            total = metric.get("examples", metric.get("total"))
            values.append(100 * exact / total)
            counts.append(f"{exact}/{total}")
        bars = ax.bar(x + offset, values, .34, label=title, color=color)
        ax.bar_label(bars, labels=counts, padding=4)
    ax.set(ylim=(0, 100), ylabel="Exact human choices uniquely matched (%)",
           xticks=x, xticklabels=labels, title="Human decision matching on recordings excluded from training")
    ax.legend(frameon=False, loc="upper left")
    ax.yaxis.grid(True, alpha=.18)
    ax.set_axisbelow(True)
    fig.text(.5, -.045, "7 training games: 186 choices. Development: 34 choices. Test: 64 choices in 2 games.\n"
             "All scores use frozen final weights; choices within a recording are correlated.", ha="center", fontsize=9)
    fig.savefig(output / "human-decision-comparison.png", bbox_inches="tight")
    fig.savefig(output / "human-decision-comparison.pdf", bbox_inches="tight")
    plt.close(fig)
    if "diagnostics" in results:
        names = ("buy-bus", "insert-order", "full-load-any", "copy-orders", "delete-order", "set-load",
                 "start-vehicle", "manage-loan:CmdDecreaseLoan")
        captions = ("Buy\nbus", "Insert\nstation", "Full load\nany", "Copy\norders", "Delete\norder", "Other\nload", "Start\nbus", "Repay\nloan")
        metrics = {row["operation"]: row for row in results["diagnostics"]["choice_summary"]
                   if row["model"] == "seven-game-256" and row["corpus"] == "seven-games"}
        x = np.arange(len(names))
        fig, ax = plt.subplots(figsize=(11, 5), layout="constrained")
        actual = [100 * metrics[name]["unique_exact_accuracy"] for name in names]
        random = [100 * metrics[name]["random_given_primitive_accuracy"] for name in names]
        bars = ax.bar(x - .18, actual, .34, color="#319575", label="Frozen seven-game model")
        ax.bar_label(bars, labels=[f"{metrics[name]['unique_exact']}/{metrics[name]['examples']}" for name in names], padding=4)
        ax.bar(x + .18, random, .34, color="#aeb7c2", label="Uniform random with family/primitive hint")
        ax.set(xticks=x, xticklabels=captions, ylabel="Exact choices matched (%)", ylim=(0, 118),
               title="Exact fit by action type in the 186 training choices")
        ax.legend(frameon=False, loc="upper left")
        ax.yaxis.grid(True, alpha=.18)
        ax.set_axisbelow(True)
        fig.text(.5, -.04, "The conditional random baseline is given the correct family/order primitive; loan direction remains unknown.\n"
                 "The model receives no such hint. Uniform guessing over the complete legal mask averages about 0.04%.", ha="center", fontsize=9)
        fig.savefig(output / "action-type-diagnostics.png", bbox_inches="tight")
        fig.savefig(output / "action-type-diagnostics.pdf", bbox_inches="tight")
        plt.close(fig)
    actors = (*models, "scripted-one-bus-repay")
    short = (*labels, "Scripted\n1 bus + repay")
    x = np.arange(5)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    metrics = (("mean_passengers", "Mean passengers delivered", False),
               ("mean_operating_profit", "Mean operating profit", False),
               ("mean_cash_result_excluding_financing", "Mean cash change after capital, excluding loan principal", False),
               ("sustained_service", "Sustained profitable passenger service (episodes / 25)", True))
    for ax, (key, title, rate) in zip(axes.flat, metrics):
        for mode, color, offset in (("greedy", "#427bb7", -.18), ("sampled", "#dd8b43", .18)):
            values = [results["gameplay"][actor][mode][key] for actor in actors]
            bars = ax.bar(x + offset, values, .34, color=color, label=mode.capitalize())
            ax.bar_label(bars, labels=[f"{value:.0f}" for value in values],
                         padding=3 if mode == "greedy" else 12, fontsize=8)
        ax.set(xticks=x, xticklabels=short, title=title)
        if rate:
            ax.set_ylim(0, 28)
        else:
            ax.margins(y=.12)
        ax.axhline(0, color="#555555", linewidth=.8)
        ax.yaxis.grid(True, alpha=.18)
        ax.set_axisbelow(True)
        ax.tick_params(axis="x", labelsize=8)
    axes[0, 0].legend(frameon=False)
    fig.suptitle("Saved native OpenTTD bus-control benchmark: 50 attempts per actor", fontsize=14)
    fig.text(.5, -.055, "25 supplied worlds × greedy/sampled; 8 distinct map seeds repeated across dimensions.\n"
             "Up to 512 decisions × 128 ticks; interface failures stop early. See matched-horizon financial comparisons.\n"
             "Two stops, roads and one depot supplied; no buses supplied.", ha="center", fontsize=9)
    fig.savefig(output / "live-game-comparison.png", bbox_inches="tight")
    fig.savefig(output / "live-game-comparison.pdf", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dependency-dir", type=Path)
    args = parser.parse_args()
    if args.dependency_dir:
        sys.path.insert(0, str(args.dependency_dir.resolve(strict=True)))
    results = json.loads(args.results.read_text())
    if results["status"] != "completed":
        raise ValueError("Plots require a complete, verified comparison")
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "figures.json").exists() or any(args.output.glob("*-comparison.png")) or (args.output / "action-type-diagnostics.png").exists():
        raise ValueError("Preserve existing figures and select a fresh output directory")
    render(results, args.output)
    import matplotlib
    def reference(path):
        return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    names = ["human-decision-comparison", "live-game-comparison"]
    if "diagnostics" in results:
        names.append("action-type-diagnostics")
    figures = [reference(args.output / (name + suffix)) for name in names for suffix in (".png", ".pdf")]
    record = {"status": "completed", "results": reference(args.results), "renderer": reference(Path(__file__)),
              "matplotlib": matplotlib.__version__, "files": figures}
    with (args.output / "figures.json").open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
