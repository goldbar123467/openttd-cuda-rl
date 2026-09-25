#!/usr/bin/env python3
"""Compare completed development episodes; uncertainty units are training seeds."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

from eval_stats import nested_bootstrap, pair_episodes


def read_json(path, identities):
    data = path.read_bytes()
    key, sha = str(path.resolve()), hashlib.sha256(data).hexdigest()
    if key in identities and identities[key] != sha:
        raise ValueError("Report input changed between reads: " + key)
    identities[key] = sha
    return json.loads(data)


def load(path, identities=None):
    run = read_json(path / "run.json", identities if identities is not None else {})
    if run["status"] != "completed" or run["split"] != "development" or run["final_evaluation_accessed"]:
        raise ValueError(f"Not a complete development evaluation: {path}")
    rows = run["episodes"]
    if run["action_horizon"] != 512 or any(
            r["status"] != "completed" or not 0 < r["actions"] <= 512 or
            (r["actions"] < 512 and not r["termination"]["terminal"]) for r in rows):
        raise ValueError(f"Comparison requires completed episodes with a 512-action budget: {path}")
    return run


def matrix(rows):
    keys = [(r["template_id"], r["sampling_seed"], r["scenario"]["identity"]["scenario_sha256"]) for r in rows]
    if not keys or len(keys) != len(set((t, s) for t, s, _ in keys)):
        raise ValueError("Empty or duplicate scenario/action case")
    return sorted(keys)


def paired_statistics(policy_groups, reference_groups, seed_ids, *, iterations=10000):
    """Pair by scenario identity before resampling the three-level hierarchy."""
    differences = {metric: [] for metric in ("passengers", "operating_profit", "operating_profit_less_capital", "balance_change")}
    if len(policy_groups) != len(reference_groups) or len(seed_ids) != len(policy_groups) or len(set(seed_ids)) != len(seed_ids):
        raise ValueError("Training-seed pairing differs")
    for seed, policy, reference in zip(seed_ids, policy_groups, reference_groups, strict=True):
        if matrix(policy) != matrix(reference):
            raise ValueError("Paired evaluation scenario/sampling matrices differ")
        p = [{**row, "training_seed": seed, "map_seed": row["template_id"], "action_seed": row["sampling_seed"]} for row in policy]
        c = [{**row, "map_seed": row["template_id"], "action_seed": row["sampling_seed"]} for row in reference]
        for metric in differences:
            differences[metric].extend(pair_episodes(p, c, metric))
    return {metric: {**nested_bootstrap(rows, iterations=iterations), "episode_differences": rows} for metric, rows in differences.items()}


def summarize(rows):
    return {"episodes": len(rows),
            **{f"mean_{key}": statistics.mean(r[key] for r in rows) for key in
               ("passengers", "operating_profit", "operating_profit_less_capital", "balance_change")},
            "operating_profit_range": [min(r["operating_profit"] for r in rows), max(r["operating_profit"] for r in rows)],
            "sustained_service_episodes": sum(r["service_in_all_final_three_windows"] for r in rows),
            "invalid_actions": sum(r["invalid_actions"] for r in rows),
            "bankruptcies": sum(r["bankruptcy"] for r in rows)}


def run(args):
    identities = {}
    old_paths = [args.old_policy] if isinstance(args.old_policy, Path) else args.old_policy
    baselines, one_bus = [load(path, identities) for path in (args.baseline, args.one_bus)]
    old_runs = [load(path, identities) for path in old_paths]
    old = {"episodes": [row for source in old_runs for row in source["episodes"]]}
    learned = [load(path, identities) for path in args.new_policy]
    runs = [baselines, one_bus, *old_runs, *learned]
    if len({r["engine_sha256"] for r in runs}) != 1:
        raise ValueError("Engine identities differ")
    seed_ids = [read_json(Path(r["package"]) / "manifest.json", identities)["run_seed"] for r in learned]
    if len(set(seed_ids)) != len(seed_ids):
        raise ValueError("Training seeds must be distinct")
    report = {"claim": "Fixed development maps; no held-out result. Sampling repetitions are not independent training seeds.",
              "inputs": [str(p.resolve()) for p in (args.baseline, args.one_bus, *old_paths, *args.new_policy)],
              "source_identities": [r["source"] for r in runs], "engine_sha256": runs[0]["engine_sha256"],
              "summaries": {}, "training_seed_statistics": {}, "per_map": {}, "episodes": {},
              "hierarchical_paired_differences": {},
              "control_scope": {"existing-script": "Historical M09 script with privileged environment access; not a public-information control",
                                "one-bus": "Public-observation and legal-mask script", "random": "Uniform native legal actions"}}
    for source in runs:
        for policy in {r["policy"] for r in source["episodes"]}:
            matrix([r for r in source["episodes"] if r["policy"] == policy])
    for name, source, policy in (("wait", baselines, "wait"), ("random", baselines, "random"),
                                 ("existing-script", baselines, "scripted"), ("one-bus", one_bus, "one-bus"),
                                 ("old-greedy", old, "greedy"), ("old-sampled", old, "sampled")):
        report["summaries"][name] = summarize([r for r in source["episodes"] if r["policy"] == policy])
    for policy in ("greedy", "sampled"):
        groups = [[r for r in source["episodes"] if r["policy"] == policy] for source in learned]
        # Require the same scenario/sampling matrix for each independent model.
        matrices = [matrix(rows) for rows in groups]
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
        report["episodes"][policy] = [{**row, "training_seed": seed} for seed, rows in zip(seed_ids, groups, strict=True) for row in rows]
        report["per_map"][policy] = {template: summarize([r for rows in groups for r in rows if r["template_id"] == template])
                                     for template in sorted({r["template_id"] for r in groups[0]})}
    if len(old_runs) > 1:
        old_seeds = [read_json(Path(r["package"]) / "manifest.json", identities)["run_seed"] for r in old_runs]
        if len(old_seeds) != 3 or len(set(old_seeds)) != 3 or set(old_seeds) != set(seed_ids):
            raise ValueError("Paired references require the same three independent training seeds")
        settings = None
        for source in [*old_runs, *learned]:
            package = Path(source["package"])
            training = read_json(package.parent.parent / "run.json", identities)
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
    else:
        old_seeds = [read_json(Path(old_runs[0]["package"]) / "manifest.json", identities)["run_seed"]]
    for policy in ("greedy", "sampled"):
        new_groups = [[r for r in source["episodes"] if r["policy"] == policy] for source in learned]
        references = [old_runs[old_seeds.index(seed)] if len(old_runs) > 1 else old_runs[0] for seed in seed_ids]
        old_groups = [[r for r in source["episodes"] if r["policy"] == policy] for source in references]
        report["hierarchical_paired_differences"][policy] = {
            "reference_scope": "Matched training seeds" if len(old_runs) > 1 else "One fixed reference model reused across candidate training seeds",
            "metrics": paired_statistics(new_groups, old_groups, seed_ids, iterations=getattr(args, "bootstrap_iterations", 10000))}
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha for p, sha in identities.items()):
        raise ValueError("Report inputs changed during reading")
    report["inputs_sha256"] = identities
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
              "Per-map results, continuous windows, training-seed means, paired signs and nested intervals are in `comparison.json`.",
              "The historical M09 scripted baseline has privileged environment access; it is labeled separately from public controls.",
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
    parser.add_argument("--bootstrap-iterations", type=int, default=10000)
    run(parser.parse_args())
