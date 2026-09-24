#!/usr/bin/env python3
"""Compare matched live architectures using independent training-seed means."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

from report_learning import load, summarize


def seed_statistics(values):
    center = statistics.mean(values)
    margin = 4.302652729911275 * statistics.stdev(values) / math.sqrt(3)
    return {"mean": center, "training_seed_means": values,
            "conditional_t_interval_95": [center - margin, center + margin]}


def run(args):
    groups = {}
    identities = {}
    matched = None
    seed_set = None
    matrix = None
    engine = None
    budget_fields = ("device", "requested_updates", "episode_action_horizon", "training_reward",
                     "rollout_length", "environments", "minibatch_size", "epochs", "training_templates",
                     "trainer_sha256", "openttd_sha256", "deterministic_cudnn")
    for paths in args.group:
        if len(paths) != 3:
            raise ValueError("Register exactly three independent training seeds per architecture")
        group = {}
        architecture = None
        for path in paths:
            evaluation = load(path)
            package = Path(evaluation["package"])
            training_path = package.parent.parent / "run.json"
            training = json.loads(training_path.read_text())
            manifest = json.loads((package / "manifest.json").read_text())
            if training["status"] != "completed" or training["model"]["path"] != str(package) or training.get("resume_from"):
                raise ValueError("Comparison needs complete, unresumed training linked to the evaluated package")
            if training["seed"] != manifest["run_seed"]:
                raise ValueError("Training seed differs from evaluated model")
            settings = {key: training[key] for key in budget_fields}
            settings["entropy_coefficient"] = training.get("entropy_coefficient", 0.01)
            settings["gae_lambda"] = training.get("gae_lambda", 0.95)
            settings["spatial_validation"] = training.get("spatial_validation", "reference")
            if matched is not None and settings != matched:
                raise ValueError("Architecture training budgets/settings/binaries differ")
            matched = settings
            rows = evaluation["episodes"]
            current_matrix = sorted((row["policy"], row["template_id"], row["sampling_seed"],
                                     row["scenario"]["identity"]["scenario_sha256"]) for row in rows)
            if matrix is not None and current_matrix != matrix:
                raise ValueError("Architecture evaluation scenario/sampling matrices differ")
            if engine is not None and evaluation["engine_sha256"] != engine:
                raise ValueError("Evaluation engines differ")
            matrix, engine = current_matrix, evaluation["engine_sha256"]
            if architecture is not None and training["architecture"] != architecture:
                raise ValueError("One group contains different architectures")
            architecture = training["architecture"]
            if training["seed"] in group:
                raise ValueError("Duplicate training seed")
            group[training["seed"]] = rows
            for identity_path in (path / "run.json", training_path, package / "manifest.json"):
                identities[str(identity_path.resolve())] = hashlib.sha256(identity_path.read_bytes()).hexdigest()
        if architecture in groups or (seed_set is not None and set(group) != seed_set):
            raise ValueError("Duplicate architecture or unmatched training seeds")
        seed_set = set(group)
        groups[architecture] = group
    report = {"claim": "Three training seeds on fixed development maps; conditional uncertainty, no held-out generalization claim",
              "matched_training": matched, "evaluation_matrix": matrix, "input_sha256": identities,
              "training_seeds": sorted(seed_set), "architectures": {}, "paired_differences": {}}
    for name, group in groups.items():
        report["architectures"][name] = {}
        for policy in ("greedy", "sampled"):
            by_seed = [[row for row in group[seed] if row["policy"] == policy] for seed in sorted(group)]
            report["architectures"][name][policy] = {
                **summarize([row for rows in by_seed for row in rows]),
                "statistics": {metric: seed_statistics([statistics.mean(row[metric] for row in rows) for rows in by_seed])
                               for metric in ("passengers", "operating_profit", "operating_profit_less_capital", "balance_change")}}
    reference = next(iter(groups))
    for name in list(groups)[1:]:
        report["paired_differences"][f"{name} minus {reference}"] = {
            policy: {metric: seed_statistics([a - b for a, b in zip(
                report["architectures"][name][policy]["statistics"][metric]["training_seed_means"],
                report["architectures"][reference][policy]["statistics"][metric]["training_seed_means"], strict=True)])
                for metric in ("passengers", "operating_profit", "operating_profit_less_capital", "balance_change")}
            for policy in ("greedy", "sampled")}
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "comparison.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    lines = ["# Matched live architecture comparison", "", report["claim"], "",
             "| Architecture | Selection | Episodes | Passengers | Operating profit | Profit less capital | Cash change | Sustained |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, policies in report["architectures"].items():
        for policy, summary in policies.items():
            lines.append(f"| {name} | {policy} | {summary['episodes']} | {summary['mean_passengers']:.1f} | "
                         f"{summary['mean_operating_profit']:.1f} | {summary['mean_operating_profit_less_capital']:.1f} | "
                         f"{summary['mean_balance_change']:.1f} | {summary['sustained_service_episodes']}/{summary['episodes']} |")
    lines += ["", "95% Student-t intervals and paired seed differences are in comparison.json.",
              "Sampling repeats and maps within a training seed are averaged before estimating uncertainty.",
              "Only three independent training seeds are available; all intervals are conditional on these development maps.",
              "Cash change includes capital and monthly other expenses omitted from native operating profit."]
    (args.output / "comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", type=Path, nargs="+", action="append", required=True,
                        help="Three completed evaluation directories for one architecture; repeat for another")
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
