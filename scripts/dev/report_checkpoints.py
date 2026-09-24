#!/usr/bin/env python3
"""Compare a registered training-only checkpoint selection with final weights."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics

from local import write_json
from report_architectures import seed_statistics
from report_learning import load, summarize


def run(args):
    selection = json.loads(args.selection.read_text())
    choices = {row["seed"]: row for row in selection["selections"]}
    if len(choices) != 3 or len(args.selected_evaluations) != 3 or len(args.final_evaluations) != 3:
        raise ValueError("This diagnostic requires exactly three independent training seeds")
    inputs = {str(args.selection.resolve()): hashlib.sha256(args.selection.read_bytes()).hexdigest()}
    for name, digest in selection["input_sha256"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError("Training evidence used for selection has changed")
    groups = {}
    matrix = engine = None
    for label, paths in (("selected", args.selected_evaluations), ("final", args.final_evaluations)):
        group = {}
        for path in paths:
            evaluation = load(path)
            package = Path(evaluation["package"])
            manifest = json.loads((package / "manifest.json").read_text())
            seed = manifest["run_seed"]
            if seed not in choices or seed in group:
                raise ValueError("Unregistered or duplicate training seed")
            choice = choices[seed]
            training_root = Path(choice["training_run"])
            training = json.loads((training_root / "run.json").read_text())
            if training["status"] != "completed" or training["training"]["updates"][-1]["samples"] != selection["total_training_transitions_per_seed"]:
                raise ValueError("Selection training budget differs from completed training")
            paths_to_hash = [path / "run.json", package / "manifest.json", training_root / "run.json"]
            if label == "selected":
                exported_path = package.parent.parent / "run.json"
                exported = json.loads(exported_path.read_text())
                if (exported["status"] != "completed" or exported["kind"] != "native-checkpoint-inference-export" or
                        exported["training_run"] != str(training_root) or exported["checkpoint"] != choice["selected"]["checkpoint"] or
                        exported["update"] != choice["selected"]["update"] or exported["model"]["path"] != str(package)):
                    raise ValueError("Evaluated export differs from registered checkpoint selection")
                paths_to_hash.append(exported_path)
            elif training["model"]["path"] != str(package):
                raise ValueError("Final evaluation differs from completed training model")
            rows = evaluation["episodes"]
            current = sorted((row["policy"], row["template_id"], row["sampling_seed"],
                              row["scenario"]["identity"]["scenario_sha256"]) for row in rows)
            if (matrix is not None and matrix != current) or (engine is not None and engine != evaluation["engine_sha256"]):
                raise ValueError("Evaluation scenario matrix or engine differs")
            matrix, engine = current, evaluation["engine_sha256"]
            group[seed] = rows
            for source in paths_to_hash:
                inputs[str(source.resolve())] = hashlib.sha256(source.read_bytes()).hexdigest()
        groups[label] = group
    report = {"claim": "Training-only checkpoint recovery diagnostic on fixed development maps; no held-out result or cure for later collapse",
              "selection_criterion": selection["criterion"], "total_training_transitions_per_seed": selection["total_training_transitions_per_seed"],
              "selected_updates": {seed: choices[seed]["selected"]["update"] for seed in choices},
              "input_sha256": inputs, "engine_sha256": engine, "evaluation_matrix": matrix,
              "results": {}, "selected_minus_final": {}}
    metrics = ("passengers", "operating_profit", "operating_profit_less_capital", "balance_change")
    for label, group in groups.items():
        report["results"][label] = {}
        for policy in ("greedy", "sampled"):
            rows_by_seed = [[row for row in group[seed] if row["policy"] == policy] for seed in sorted(choices)]
            report["results"][label][policy] = {
                **summarize([row for rows in rows_by_seed for row in rows]),
                "statistics": {metric: seed_statistics([statistics.mean(row[metric] for row in rows) for rows in rows_by_seed]) for metric in metrics}}
    for policy in ("greedy", "sampled"):
        report["selected_minus_final"][policy] = {metric: seed_statistics([a - b for a, b in zip(
            report["results"]["selected"][policy]["statistics"][metric]["training_seed_means"],
            report["results"]["final"][policy]["statistics"][metric]["training_seed_means"], strict=True)]) for metric in metrics}
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "comparison.json", report)
    lines = ["# Training-selected checkpoint comparison", "", report["claim"], "",
        f"All {selection['total_training_transitions_per_seed']:,} training transitions per seed count toward selection. Original final-model architecture results remain unchanged.", "",
        "| Checkpoint | Policy | Episodes | Passengers | Operating profit | Cash change | Sustained |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for label, policies in report["results"].items():
        for policy, summary in policies.items():
            lines.append(f"| {label} | {policy} | {summary['episodes']} | {summary['mean_passengers']:.1f} | {summary['mean_operating_profit']:.1f} | "
                         f"{summary['mean_balance_change']:.1f} | {summary['sustained_service_episodes']}/{summary['episodes']} |")
    lines += ["", "Conditional paired 95% t intervals average scenarios and sampling repeats within each of three training seeds.",
              "Checkpoint selection uses training episodes only. This diagnostic followed observation of final-model failure; it is not a preregistered architecture winner claim."]
    (args.output / "comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--selected-evaluations", type=Path, nargs="+", required=True)
    parser.add_argument("--final-evaluations", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
