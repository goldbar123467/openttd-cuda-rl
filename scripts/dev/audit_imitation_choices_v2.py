#!/usr/bin/env python3
"""Read-only random-choice baselines and exact native candidate-input comparisons."""
import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import statistics
import subprocess

from audit_action_inputs_v2 import artifact, checked, checked_candidate_data, parameter_row
from compare_human_imitation_v2 import corpus
from local import capture_source, source_identity, write_json


def choice_group(parameters):
    """Give order-primitive hints only to the diagnostic conditional baseline."""
    family = parameters[0]
    return (family, parameters[2] & 255) if family == 6 else (family,)


def input_distance(target, selected):
    difference = [abs(a - b) for a, b in zip(target["features"], selected["features"], strict=True)]
    same_family = target["family"] == selected["family"]
    return {"same_family": same_family, "identical_features": same_family and not any(difference),
            "maximum_feature_difference": max(difference), "l2_feature_distance": math.sqrt(sum(x*x for x in difference)),
            "changed_feature_slots": [i for i, value in enumerate(difference) if value],
            "small_difference_thresholds": {str(tolerance): same_family and max(difference) <= tolerance
                                            for tolerance in (1e-6, 1e-3, 1e-2)},
            "target_parameters": target["parameters"], "selected_parameters": selected["parameters"],
            "target_features": target["features"], "selected_features": selected["features"]}


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["model"], row["corpus"], row["operation"])].append(row)
    return [{"model": key[0], "corpus": key[1], "operation": key[2], "examples": len(items),
             "unique_exact": sum(row["unique_exact"] for row in items),
             "unique_exact_accuracy": statistics.mean(row["unique_exact"] for row in items),
             "random_all_legal_accuracy": statistics.mean(row["random_all_legal_probability"] for row in items),
             "random_given_primitive_accuracy": statistics.mean(row["random_given_primitive_probability"] for row in items),
             "mean_all_legal_candidates": statistics.mean(row["legal_candidates"] for row in items),
             "mean_same_primitive_candidates": statistics.mean(row["same_primitive_candidates"] for row in items),
             "min_same_primitive_candidates": min(row["same_primitive_candidates"] for row in items),
             "max_same_primitive_candidates": max(row["same_primitive_candidates"] for row in items),
             "selected_correct_primitive": sum(row["selected_correct_primitive"] for row in items),
             "exact_given_primitive_hint": sum(row["conditional_exact"] for row in items)} for key, items in sorted(groups.items())]


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    offline_ref = artifact(args.offline)
    offline = json.loads(Path(offline_ref["path"]).read_text())
    if offline["status"] != "completed" or not offline["inputs_unchanged"]:
        raise ValueError("Diagnostics require a complete frozen offline comparison")
    audit = args.audit_executable.resolve(strict=True)
    report = {"status": "running", "source": source_identity(), "offline": offline_ref,
              "audit_executable": artifact(audit), "training_run": False,
              "conditional_baseline": "Uniform among same action family, or same order primitive for family 6. Loan direction is not hinted.",
              "near_input_interpretation": "Thresholds are descriptive feature scales, not proof of learned distinguishability; family embeddings are categorical.",
              "rows": [], "wrong_order_input_pairs": []}
    references = [offline_ref, report["audit_executable"]]
    try:
        report["source_capture"] = capture_source(output / "source-provenance")
        corpora = {name: corpus(Path(path)) for name, path in args.corpus}
        cache = {}
        for model_result in offline["results"]:
            model = model_result["model"]
            for corpus_name, corpus_result in model_result["corpora"].items():
                labels, tensors, refs = corpora[corpus_name]
                references += refs
                prediction_ref = corpus_result["raw_predictions"]
                checked(prediction_ref)
                references.append(prediction_ref)
                predictions = [json.loads(line) for line in Path(prediction_ref["path"]).read_text().splitlines()]
                if len(predictions) != len(labels):
                    raise ValueError("Prediction/label counts differ")
                for index, (label, pair, prediction) in enumerate(zip(labels, tensors, predictions)):
                    if prediction["sample_id"] != label["sample_id"] or prediction["game_id"] != label["game_id"]:
                        raise ValueError("Frozen prediction has another native sample identity")
                    candidate_data = Path(checked(pair["candidate"])["path"]).read_bytes()
                    legal = checked_candidate_data(candidate_data, label)
                    parameters = {row: parameter_row(candidate_data, row) for row in legal}
                    target = label["action_row"]
                    selected = prediction["original"]["row"]
                    group = choice_group(parameters[target])
                    matching = [row for row in legal if choice_group(parameters[row]) == group]
                    probabilities = prediction["original"]["probabilities"]
                    conditional = max(matching, key=lambda row: probabilities[row])
                    maximum = probabilities[conditional]
                    conditional_unique = conditional == target and all(maximum - probabilities[row] > 1e-6 for row in matching if row != target)
                    row = {"model": model, "corpus": corpus_name, "sample_id": label["sample_id"], "game_id": label["game_id"],
                           "operation": prediction["operation"], "unique_exact": prediction["prediction"]["unique_exact"],
                           "target_row": target, "selected_row": selected, "legal_candidates": len(legal),
                           "same_primitive_candidates": len(matching), "random_all_legal_probability": 1 / len(legal),
                           "random_given_primitive_probability": 1 / len(matching),
                           "selected_correct_primitive": choice_group(parameters[selected]) == group,
                           "conditional_exact": conditional_unique}
                    report["rows"].append(row)
                    if prediction["operation"] in ("insert-order", "copy-orders") and selected != target:
                        key = (pair["observation"]["sha256"], pair["candidate"]["sha256"])
                        if key not in cache:
                            filename = output / f"native-{len(cache):04d}.json"
                            with filename.open("x") as stdout, filename.with_suffix(".log").open("x") as stderr:
                                subprocess.run([str(audit), "--observation", checked(pair["observation"])["path"],
                                                "--candidates", pair["candidate"]["path"], "--financial-features", "signed-log-orders-v2"],
                                               stdout=stdout, stderr=stderr, check=True, timeout=60)
                            document = json.loads(filename.read_text())
                            encoded = {value["row"]: value for value in document["rows"]}
                            if encoded.keys() != set(legal):
                                raise ValueError("Native audit legal rows differ")
                            cache[key] = (encoded, artifact(filename))
                        encoded, ref = cache[key]
                        report["wrong_order_input_pairs"].append({**row, "native_input_audit": ref,
                                                                 "distance": input_distance(encoded[target], encoded[selected])})
            print(json.dumps({"diagnostic_model_completed": model}), flush=True)
        report["summary"] = summarize(report["rows"])
        with (output / "random-baselines.csv").open("x", newline="") as stream:
            writer = csv.DictWriter(stream, list(report["summary"][0]))
            writer.writeheader()
            writer.writerows(report["summary"])
        for reference in references:
            checked(reference)
        report["native_states_audited"] = len(cache)
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", type=Path, required=True)
    parser.add_argument("--audit-executable", type=Path, required=True)
    parser.add_argument("--corpus", nargs=2, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
