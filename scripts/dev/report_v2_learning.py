#!/usr/bin/env python3
"""Rederive V2 development economics from native traces without altering old reports."""
import argparse
import json
from pathlib import Path
import statistics

from local import write_json
from eval_stats import nested_bootstrap, pair_episodes
from studies.evidence_v2 import Inputs, load_episode, public_case


METRICS = ("passengers", "operating_profit", "net_capital_spend", "cash_result_excluding_financing", "cash_result_before_capital")


def aggregate(rows):
    values = [entry["summary"] for entry in rows]
    return {"episodes": len(values),
            **{f"mean_{key}": statistics.mean(row[key] for row in values) for key in METRICS},
            "sustained_native_operating_service": sum(row["service_in_all_final_three_windows"] for row in values),
            "sustained_positive_cash_service": sum(row["positive_cash_service_in_all_final_three_windows"] for row in values),
            "bankruptcies": sum(row["bankruptcy"] for row in values), "invalid_actions": sum(row["invalid_actions"] for row in values)}


def build_report(entries, *, bootstrap_iterations=10000):
    if not entries or len({e["record"]["engine_sha256"] for e in entries}) != 1:
        raise ValueError("Comparison requires episodes from one native engine")
    groups = {}
    for entry in entries:
        # Retain historical sampled-control labels; the new greedy diagnostic
        # receives its own label rather than changing old summary keys.
        label = "/".join(entry[k] for k in ("controller", "guidance"))
        if entry["controller"] == "neural" or entry["mode"] == "greedy":
            label += "/" + entry["mode"]
        groups.setdefault(label, []).append({**entry, "group": label})
    episodes = []
    for rows in groups.values():
        for entry in rows:
            record = entry["record"]
            controller = {"sampling_seed": entry["sampling_seed"]}
            if entry["controller"] == "neural":
                controller.update(training_run=record["training_run"], model=record["model"])
            episodes.append({**public_case(entry), "controller_name": entry["controller"], "controller": controller})
    report = {"claim": "Descriptive development comparison; training seeds are independent models, action seeds are repeated games. No held-out result or automatic advancement claim.",
              "engine_sha256": entries[0]["record"]["engine_sha256"],
              "episodes": episodes,
              "summaries": {}, "per_map": {}, "per_training_seed": {}, "paired_comparisons": {}, "unpaired_groups": []}
    for name, rows in groups.items():
        seeds = sorted({r.get("training_seed", 0) for r in rows})
        matrices = []
        for seed in seeds:
            selected = [r for r in rows if r.get("training_seed", 0) == seed]
            matrix = [(r["map_seed"], r["sampling_seed"]) for r in selected]
            if len(matrix) != len(set(matrix)):
                raise ValueError("Duplicate training/map/action case in " + name)
            matrices.append(set(matrix))
            if rows[0]["controller"] == "neural" and len({r["record"]["model"]["sha256"] for r in selected}) != 1:
                raise ValueError("Multiple models for one training seed")
        if any(m != matrices[0] for m in matrices):
            raise ValueError("Training-seed evaluation matrices differ")
        action_sets = [{a for m, a in matrices[0] if m == map_seed} for map_seed in sorted({m for m, a in matrices[0]})]
        if any(s != action_sets[0] for s in action_sets) or (rows[0]["mode"] == "greedy" and len(action_sets[0]) != 1):
            raise ValueError("Map/action matrix is incomplete or repeats deterministic greedy cases")
        for map_seed in {r["map_seed"] for r in rows}:
            if len({json.dumps(r["reset"], sort_keys=True) for r in rows if r["map_seed"] == map_seed}) != 1:
                raise ValueError("Same map has different native reset identities")
        report["summaries"][name] = aggregate(rows)
        report["per_map"][name] = {m: aggregate([r for r in rows if r["map_seed"] == m]) for m in sorted({r["map_seed"] for r in rows})}
        if rows[0]["controller"] != "neural":
            continue
        report["per_training_seed"][name] = {s: aggregate([r for r in rows if r["training_seed"] == s]) for s in seeds}
        # Separate training recipes and evaluation overrides cannot be pooled as
        # seed replications. These fields cover the current and recovery routes.
        recipe_fields = ("guidance", "financial_features", "entropy_coefficient", "gamma", "gae_lambda", "requested_updates",
                         "rollout_steps", "sequence_length", "optimization_epochs", "episode_horizon", "training_map_seeds",
                         "reuse_bootstrap_tensors", "reward_schema", "observation_schema_id", "trainer_sha256", "device",
                         "choice_weighted", "asset_potential", "sequences_per_minibatch", "choice_kl_limit")
        recipes = {json.dumps({k: r["training"].get(k) for k in recipe_fields}, sort_keys=True) for r in rows}
        if len(recipes) != 1:
            raise ValueError("Different training recipes cannot be pooled as independent seed replications")
        matches = [(label, control) for label, control in groups.items() if control[0]["controller"] != "neural" and
                   control[0]["guidance"] == rows[0]["guidance"] and control[0]["mode"] == rows[0]["mode"]]
        if not matches:
            report["unpaired_groups"].append({"group": name, "reason": "No identical-guide/action-mode control in supplied episodes"})
        for label, control in matches:
            # Pair only reset-identical games with the same evaluator source.
            resets = {r["map_seed"]: r["reset"] for r in rows}
            sources = {json.dumps(r["record"]["source"], sort_keys=True) for r in [*rows, *control]}
            if len(sources) != 1 or any(resets.get(c["map_seed"]) != c["reset"] for c in control):
                report["unpaired_groups"].append({"group": name, "control": label, "reason": "Evaluator source or native reset identities differ"})
                continue
            if any(r["record"].get("guidance_override") is not None for r in rows):
                report["unpaired_groups"].append({"group": name, "control": label, "reason": "Guide override is a diagnostic, not matched trained-guide evidence"})
                continue
            policy = [{"training_seed": r["training_seed"], "map_seed": r["map_seed"], "action_seed": r["sampling_seed"], **r["summary"]} for r in rows]
            baseline = [{"map_seed": r["map_seed"], "action_seed": r["sampling_seed"], **r["summary"]} for r in control]
            report["paired_comparisons"][name + " minus " + label] = {}
            for metric in METRICS:
                pairs = pair_episodes(policy, baseline, metric)
                report["paired_comparisons"][name + " minus " + label][metric] = {
                    **nested_bootstrap(pairs, iterations=bootstrap_iterations), "episode_differences": pairs}
    return report


def run(args):
    inputs = Inputs()
    entries = [load_episode(p, inputs, legacy_sampled_control=getattr(args, "legacy_sampled_controls", False)) for p in args.runs]
    report = build_report(entries, bootstrap_iterations=getattr(args, "bootstrap_iterations", 10000))
    inputs.unchanged()
    report["source_sha256"] = inputs.sha256
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "comparison.json", report)
    lines = ["# Live V2 development comparison", "", report["claim"], "",
             "| Controller | Episodes | Passengers | Native operating profit | Cash result before capital | Cash after capital | Sustained cash service |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, row in report["summaries"].items():
        lines.append(f"| {name} | {row['episodes']} | {row['mean_passengers']:.1f} | {row['mean_operating_profit']:.1f} | "
                     f"{row['mean_cash_result_before_capital']:.1f} | {row['mean_cash_result_excluding_financing']:.1f} | "
                     f"{row['sustained_positive_cash_service']}/{row['episodes']} |")
    lines += ["", "Cash results exclude loan principal. Cash before capital adds back net construction/vehicle cost, including sale proceeds.",
              "Native operating profit omits EXPENSES_OTHER; cash measures retain those charges.",
              "The planner supplies route geometry. Only matching guide, source, reset and action-mode controls contribute paired differences.",
              "Per-map, per-training-seed, continuous-window results, paired signs and nested intervals are in comparison.json; unmatched groups are explicit.",
              "Prior summaries are preserved; this report rederives economics from their original native traces."]
    (args.output / "comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--legacy-sampled-controls", action="store_true", help="Explicitly identify historical controls whose evaluator only supported sampling")
    parser.add_argument("--bootstrap-iterations", type=int, default=10000)
    run(parser.parse_args())
