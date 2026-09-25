#!/usr/bin/env python3
"""Compare registered rollout/GAE development experiments at equal experience."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

from local import capture_source, source_identity, write_json
from report_learning import load, matrix, paired_statistics, summarize

METRICS = ("passengers", "operating_profit", "operating_profit_less_capital", "balance_change")


def settings(training):
    result = {key: training[key] for key in ("architecture", "device", "episode_action_horizon",
        "environments", "minibatch_size", "epochs", "training_templates", "development_templates",
        "openttd_sha256", "deterministic_cudnn", "training_reward", "bridge_validation")}
    result.update(entropy_coefficient=training.get("entropy_coefficient", .01),
                  spatial_validation=training.get("spatial_validation", "reference"),
                  gae_lambda=training.get("gae_lambda", .95), rollout_length=training["rollout_length"],
                  transitions=training["requested_updates"] * training["rollout_length"] * training["environments"])
    return result


def validate_pair(old, new, axis):
    left, right = settings(old), settings(new)
    key = {"rollout": "rollout_length", "lambda": "gae_lambda"}[axis]
    changed = [field for field in left if left[field] != right[field]]
    if changed != [key]:
        raise ValueError("Training configurations must differ only in " + key + ": " + str(changed))
    if old["seed"] != new["seed"]:
        raise ValueError("Training seed pairing differs")
    return {"reference": left, "candidate": right}


def verified_binary_chain(reference, candidate, evidence, architecture, device):
    # A passed finite fixture is supporting evidence, not proof for every input.
    reachable = {reference}
    edges = []
    for path in evidence:
        record = json.loads(path.read_text())
        cases = [case for case in record["cases"] if case["architecture"] == architecture and case["device"] == device]
        if (record["status"] != "passed" or record["kind"] not in
                ("native-entropy-option-verification", "native-gae-option-verification") or
                len(cases) != 1 or cases[0]["default_exact"] is not True):
            raise ValueError("Missing passed default-equivalence evidence for this architecture/device")
        edges.append((record["binaries"]["reference"], record["binaries"]["candidate"]))
    for _ in range(len(edges)):
        for start, end in edges:
            if start in reachable:
                reachable.add(end)
    if candidate not in reachable:
        raise ValueError("Trainer binaries differ without a verified default-equivalence chain")


def training_for(evaluation):
    package = Path(evaluation["package"])
    path = package.parent.parent / "run.json"
    training = json.loads(path.read_text())
    manifest = json.loads((package / "manifest.json").read_text())
    if (training["status"] != "completed" or training.get("resume_from") or
            training["model"]["path"] != str(package) or training["model"]["id"] != package.name or
            manifest["run_seed"] != training["seed"] or
            len(training["training"]["updates"]) != training["requested_updates"] or
            training["training"]["updates"][-1]["samples"] != settings(training)["transitions"]):
        raise ValueError("Requires completed, unresumed training and its final model")
    return path, training


def interval(values):
    center = statistics.mean(values)
    margin = 4.302652729911275 * statistics.stdev(values) / math.sqrt(3) if len(values) == 3 else None
    return {"mean": center, "conditional_t_interval_95": [center - margin, center + margin] if margin is not None else None}


def run(args):
    groups, inputs = {}, list(args.default_equivalence)
    for label, paths in (("reference", args.reference), ("candidate", args.candidate)):
        groups[label] = {}
        for path in paths:
            evaluation = load(path)
            training_path, training = training_for(evaluation)
            seed = training["seed"]
            if seed in groups[label]:
                raise ValueError("Duplicate independent training seed")
            groups[label][seed] = (evaluation, training)
            inputs += [path / "run.json", training_path]
    seeds = sorted(groups["reference"])
    if set(seeds) != set(groups["candidate"]) or len(seeds) not in (1, 3):
        raise ValueError("Requires one diagnostic pair or three matched training seeds")
    report = {"axis": args.axis, "training_seeds": seeds, "source": source_identity(), "summaries": {},
        "claim": "Development maps only. Sampling repetitions are not independent training seeds. Three-seed intervals are imprecise and conditional on these maps.",
        "matched_settings": [], "paired_differences": {}, "per_map": {}, "episodes": {}, "hierarchical_paired_differences": {}}
    all_evaluations = [evaluation for group in groups.values() for evaluation, _ in group.values()]
    controls = [("baselines", load(args.baseline)), ("one-bus", load(args.one_bus))]
    all_evaluations += [evaluation for _, evaluation in controls]
    if len({evaluation["engine_sha256"] for evaluation in all_evaluations}) != 1:
        raise ValueError("Evaluation engines differ")
    if any(evaluation["ticks_per_action"] != 128 for evaluation in all_evaluations):
        raise ValueError("Evaluation simulation-time budgets differ")
    if len({(evaluation["evaluator_sha256"], evaluation["inference_backend"]) for evaluation in all_evaluations[:-2]}) != 1:
        raise ValueError("Neural inference backends differ")
    common = None
    for seed in seeds:
        old, new = groups["reference"][seed][1], groups["candidate"][seed][1]
        pair = validate_pair(old, new, args.axis)
        if common is not None and pair != common:
            raise ValueError("Training configurations differ across seeds")
        common = pair
        verified_binary_chain(old["trainer_sha256"], new["trainer_sha256"], args.default_equivalence, old["architecture"], old["device"])
        if old["trainer_sha256"] != new["trainer_sha256"] and (args.axis != "rollout" or old.get("gae_lambda", .95) != .95 or old.get("entropy_coefficient", .01) != .01):
            raise ValueError("Cross-binary comparison requires the tested default GAE/entropy settings")
        report["matched_settings"].append({"seed": seed, **pair,
            "trainer_sha256": {"reference": old["trainer_sha256"], "candidate": new["trainer_sha256"]}})
    for policy in ("greedy", "sampled"):
        paired = {metric: {} for metric in METRICS}
        reference_matrix = None
        for seed in seeds:
            rows = {label: [row for row in groups[label][seed][0]["episodes"] if row["policy"] == policy]
                    for label in groups}
            expected = 2 if policy == "greedy" else 6
            if (len(rows["reference"]) != expected or len(set(matrix(rows["reference"]))) != expected or
                    matrix(rows["reference"]) != matrix(rows["candidate"]) or
                    (reference_matrix is not None and matrix(rows["reference"]) != reference_matrix)):
                raise ValueError("Scenario/sampling matrices differ")
            reference_matrix = matrix(rows["reference"])
            for metric in METRICS:
                paired[metric][seed] = statistics.mean(r[metric] for r in rows["candidate"]) - statistics.mean(r[metric] for r in rows["reference"])
        report["paired_differences"][policy] = {metric: {"candidate_minus_reference_by_seed": values, **interval(list(values.values()))}
                                                 for metric, values in paired.items()}
        report["hierarchical_paired_differences"][policy] = paired_statistics(
            [[r for r in groups["candidate"][seed][0]["episodes"] if r["policy"] == policy] for seed in seeds],
            [[r for r in groups["reference"][seed][0]["episodes"] if r["policy"] == policy] for seed in seeds],
            seeds, iterations=getattr(args, "bootstrap_iterations", 10000))
        for label in groups:
            rows = [{**r, "training_seed": seed} for seed in seeds for r in groups[label][seed][0]["episodes"] if r["policy"] == policy]
            name = label + "-" + policy
            report["summaries"][name] = summarize(rows)
            report["episodes"][name] = rows
            report["per_map"][name] = {template: summarize([r for r in rows if r["template_id"] == template]) for template in sorted({r["template_id"] for r in rows})}
    for label, evaluation in controls:
        for policy in (("wait", "random", "scripted") if label == "baselines" else ("one-bus",)):
            report["summaries"][policy] = summarize([row for row in evaluation["episodes"] if row["policy"] == policy])
    inputs += [args.baseline / "run.json", args.one_bus / "run.json"]
    report["input_sha256"] = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    report["limitations"] = ["Rollout changes also alter update frequency and within-update normalization; temporal credit alone is not isolated.",
        "Different trainer binaries are admitted only with recorded exact default checks; those finite fixtures are not universal equivalence proofs.",
        "A single seed receives no training-seed t interval; nested map/action intervals are conditional on that one model. Full-episode cash can remain negative despite sustained operating service."]
    args.output.mkdir(parents=True, exist_ok=False)
    report["source_archive"] = capture_source(args.output / "source")
    write_json(args.output / "comparison.json", report)
    lines = ["# Development credit experiment", "", report["claim"], "",
        "| Policy | Episodes | Passengers | Operating profit | Cash change | Sustained service |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, result in report["summaries"].items():
        lines.append(f"| {name} | {result['episodes']} | {result['mean_passengers']:.1f} | {result['mean_operating_profit']:.1f} | {result['mean_balance_change']:.1f} | {result['sustained_service_episodes']}/{result['episodes']} |")
    lines += ["", *report["limitations"], "", "All paired seed differences, conditional intervals, settings and input identities are in comparison.json."]
    (args.output / "comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "candidate"):
        parser.add_argument("--" + name, type=Path, nargs="+", required=True)
    for name in ("baseline", "one-bus", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--axis", choices=("rollout", "lambda"), required=True)
    parser.add_argument("--default-equivalence", type=Path, nargs="*", default=[])
    parser.add_argument("--bootstrap-iterations", type=int, default=10000)
    run(parser.parse_args())
