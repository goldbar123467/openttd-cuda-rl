#!/usr/bin/env python3
"""Compare completed development episodes; uncertainty units are training seeds."""
import argparse
import json
import math
from pathlib import Path
import statistics


def load(path):
    run = json.loads((path / "run.json").read_text())
    if run["status"] != "completed" or run["split"] != "development" or run["final_evaluation_accessed"]:
        raise ValueError(f"Not a complete development evaluation: {path}")
    rows = run["episodes"]
    if run["action_horizon"] != 512 or any(
            r["status"] != "completed" or not 0 < r["actions"] <= 512 or
            (r["actions"] < 512 and not r["termination"]["terminal"]) for r in rows):
        raise ValueError(f"Comparison requires completed episodes with a 512-action budget: {path}")
    return run


def summarize(rows):
    return {"episodes": len(rows),
            **{f"mean_{key}": statistics.mean(r[key] for r in rows) for key in
               ("passengers", "operating_profit", "operating_profit_less_capital", "balance_change")},
            "operating_profit_range": [min(r["operating_profit"] for r in rows), max(r["operating_profit"] for r in rows)],
            "sustained_service_episodes": sum(r["service_in_all_final_three_windows"] for r in rows),
            "invalid_actions": sum(r["invalid_actions"] for r in rows),
            "bankruptcies": sum(r["bankruptcy"] for r in rows)}


def run(args):
    old_paths = [args.old_policy] if isinstance(args.old_policy, Path) else args.old_policy
    baselines, one_bus = [load(path) for path in (args.baseline, args.one_bus)]
    old_runs = [load(path) for path in old_paths]
    old = {"episodes": [row for source in old_runs for row in source["episodes"]]}
    learned = [load(path) for path in args.new_policy]
    runs = [baselines, one_bus, *old_runs, *learned]
    if len({r["engine_sha256"] for r in runs}) != 1:
        raise ValueError("Engine identities differ")
    seed_ids = [json.loads((Path(r["package"]) / "manifest.json").read_text())["run_seed"] for r in learned]
    if len(set(seed_ids)) != len(seed_ids):
        raise ValueError("Training seeds must be distinct")
    report = {"claim": "Fixed development maps; no held-out result. Sampling repetitions are not independent training seeds.",
              "inputs": [str(p.resolve()) for p in (args.baseline, args.one_bus, *old_paths, *args.new_policy)],
              "source_identities": [r["source"] for r in runs], "engine_sha256": runs[0]["engine_sha256"],
              "summaries": {}, "training_seed_statistics": {}}
    for name, source, policy in (("wait", baselines, "wait"), ("random", baselines, "random"),
                                 ("existing-script", baselines, "scripted"), ("one-bus", one_bus, "one-bus"),
                                 ("old-greedy", old, "greedy"), ("old-sampled", old, "sampled")):
        report["summaries"][name] = summarize([r for r in source["episodes"] if r["policy"] == policy])
    for policy in ("greedy", "sampled"):
        groups = [[r for r in source["episodes"] if r["policy"] == policy] for source in learned]
        # Require the same scenario/sampling matrix for each independent model.
        matrices = [{(r["template_id"], r["sampling_seed"]) for r in rows} for rows in groups]
        if not all(m == matrices[0] for m in matrices) or any(not r for r in groups):
            raise ValueError("Learned-policy evaluation matrices differ")
        report["summaries"][f"new-{policy}"] = summarize([row for rows in groups for row in rows])
        stats = {}
        for metric in ("passengers", "operating_profit", "operating_profit_less_capital", "balance_change"):
            values = [statistics.mean(r[metric] for r in rows) for rows in groups]
            center = statistics.mean(values)
            # The 95% two-sided Student-t critical value for n=3 independent
            # training seeds. Do not silently substitute a large-sample interval.
            margin = 4.302652729911275 * statistics.stdev(values) / math.sqrt(3) if len(values) == 3 else None
            stats[metric] = {"training_seed_means": dict(zip(seed_ids, values)), "mean": center,
                             "range": [min(values), max(values)],
                             "t_interval_95": [center - margin, center + margin] if margin is not None else None,
                             "interval_scope": ("Across three training seeds conditional on these fixed development scenarios and sampling seeds; n=3 is imprecise."
                                if len(values) == 3 else f"No training-seed confidence interval is reported for this {len(values)}-seed comparison.")}
        report["training_seed_statistics"][policy] = stats
    if len(old_runs) > 1:
        old_seeds = [json.loads((Path(r["package"]) / "manifest.json").read_text())["run_seed"] for r in old_runs]
        if len(old_seeds) != 3 or len(set(old_seeds)) != 3 or set(old_seeds) != set(seed_ids):
            raise ValueError("Paired references require the same three independent training seeds")
        settings = None
        for source in [*old_runs, *learned]:
            package = Path(source["package"])
            training = json.loads((package.parent.parent / "run.json").read_text())
            if training["status"] != "completed" or training["model"]["path"] != str(package) or training.get("resume_from"):
                raise ValueError("Paired reward comparison requires complete unresumed training")
            current = {key: training[key] for key in ("architecture", "device", "requested_updates", "episode_action_horizon",
                "rollout_length", "environments", "minibatch_size", "epochs", "training_templates", "trainer_sha256",
                "openttd_sha256", "deterministic_cudnn")}
            current["entropy_coefficient"] = training.get("entropy_coefficient", 0.01)
            current["gae_lambda"] = training.get("gae_lambda", 0.95)
            current["spatial_validation"] = training.get("spatial_validation", "reference")
            if settings is not None and current != settings:
                raise ValueError("Paired training configurations differ beyond the reward objective")
            settings = current
        report["paired_training_seed_differences"] = {}
        for policy in ("greedy", "sampled"):
            paired = []
            for seed in sorted(seed_ids):
                new_rows = [row for row in learned[seed_ids.index(seed)]["episodes"] if row["policy"] == policy]
                old_rows = [row for row in old_runs[old_seeds.index(seed)]["episodes"] if row["policy"] == policy]
                def matrix(rows):
                    return sorted((r["template_id"], r["sampling_seed"], r["scenario"]["identity"]["scenario_sha256"]) for r in rows)
                if matrix(new_rows) != matrix(old_rows):
                    raise ValueError("Paired evaluation scenario/sampling matrices differ")
                paired.append({metric: statistics.mean(r[metric] for r in new_rows) - statistics.mean(r[metric] for r in old_rows)
                    for metric in ("passengers", "operating_profit", "operating_profit_less_capital", "balance_change")})
            differences = {}
            for metric in paired[0]:
                values = [row[metric] for row in paired]
                center = statistics.mean(values)
                margin = 4.302652729911275 * statistics.stdev(values) / math.sqrt(3)
                differences[metric] = {"new_minus_old_by_seed": dict(zip(sorted(seed_ids), values)), "mean": center,
                    "conditional_t_interval_95": [center - margin, center + margin]}
            report["paired_training_seed_differences"][policy] = differences
        report["matched_training_except_reward"] = settings
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "comparison.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    lines = ["# Development learning comparison", "", report["claim"], "",
             "| Policy | Episodes | Mean passengers | Mean operating profit | Mean profit less capital | Cash change | Sustained service |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, r in report["summaries"].items():
        lines.append(f"| {name} | {r['episodes']} | {r['mean_passengers']:.1f} | {r['mean_operating_profit']:.1f} | "
                     f"{r['mean_operating_profit_less_capital']:.1f} | {r['mean_balance_change']:.1f} | {r['sustained_service_episodes']}/{r['episodes']} |")
    lines += ["", "Sustained service requires deliveries and positive operating profit in each of the final three 128-action windows.",
              "All episodes use the same engine and 512-action budget. Financial units are native OpenTTD units.",
              "Cash change includes net capital and monthly other expenses omitted from the native operating subtotal.", "",
              "Training-seed means and their ranges are in `comparison.json`.",
              ("Conditional 95% t intervals describe three training seeds on two fixed development maps; they do not establish generalization."
               if len(learned) == 3 else f"This comparison contains {len(learned)} new training seed(s); no training-seed confidence interval is reported.")]
    (args.output / "comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("baseline", "one-bus", "output"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    parser.add_argument("--old-policy", type=Path, nargs="+", required=True,
                        help="One reference model, or the same three seeds for a paired reward comparison")
    parser.add_argument("--new-policy", type=Path, nargs="+", required=True)
    run(parser.parse_args())
