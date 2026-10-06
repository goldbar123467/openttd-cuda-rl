#!/usr/bin/env python3
"""Audit every training insertion for aliases, targeting errors and row alignment."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess

from audit_action_inputs_v2 import artifact, checked, native_aliases, parameter_row
from audit_imitation_choices_v2 import input_distance
from compare_human_imitation_v2 import corpus
from local import capture_source, source_identity, write_json


def classify(target, selected):
    if selected[0] != 6 or selected[2] & 255 != 1:
        return {"category": "wrong-action-or-order-primitive"}
    same_vehicle, same_station = target[1] == selected[1], target[3] == selected[3]
    same_position = (target[2] >> 8) & 255 == (selected[2] >> 8) & 255
    same_variant = target[2] >> 16 == selected[2] >> 16
    if not same_vehicle:
        category = "wrong-target-vehicle"
    elif not same_station and not same_position:
        category = "wrong-station-and-position"
    elif not same_station:
        category = "wrong-station-correct-position"
    elif not same_position:
        category = "correct-station-wrong-position"
    elif not same_variant:
        category = "correct-vehicle-station-position-wrong-order-variant"
    else:
        category = "exact-insertion"
    return {"category": category, "same_vehicle": same_vehicle, "same_station": same_station,
            "same_position": same_position, "same_order_variant": same_variant}


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    labels, tensors, refs = corpus(args.training_run / "run.json")
    offline_ref, diagnostics_ref = artifact(args.offline_model), artifact(args.choice_diagnostics)
    offline, diagnostics = [json.loads(Path(ref["path"]).read_text()) for ref in (offline_ref, diagnostics_ref)]
    if diagnostics["status"] != "completed" or offline["model"] != "seven-game-256":
        raise ValueError("Insertion audit requires complete diagnostics for the frozen model")
    frozen_rows = {(row["game_id"], row["sample_id"]): row for row in offline["corpora"]["seven-games"]["rows"]}
    cache = {(row["game_id"], row["sample_id"]): row["native_input_audit"] for row in diagnostics["wrong_order_input_pairs"]}
    report = {"status": "running", "source": source_identity(), "training_run": artifact(args.training_run / "run.json"),
              "offline": offline_ref, "choice_diagnostics": diagnostics_ref, "audit_executable": artifact(args.audit_executable),
              "training_run_performed": False, "rows": []}
    try:
        report["source_capture"] = capture_source(output / "source-provenance")
        for label, pair in zip(labels, tensors):
            if label["operation"] != "insert-order":
                continue
            key = (label["game_id"], label["sample_id"])
            predicted = frozen_rows[key]
            audit_ref = cache.get(key)
            if audit_ref is None:
                path = output / f"native-{len(report['rows']):02d}.json"
                with path.open("x") as stdout, path.with_suffix(".log").open("x") as stderr:
                    subprocess.run([str(args.audit_executable.resolve()), "--observation", checked(pair["observation"])["path"],
                                    "--candidates", checked(pair["candidate"])["path"], "--financial-features", "signed-log-orders-v2"],
                                   stdout=stdout, stderr=stderr, check=True, timeout=60)
                audit_ref = artifact(path)
            document = json.loads(Path(checked(audit_ref)["path"]).read_text())
            data = Path(checked(pair["candidate"])["path"]).read_bytes()
            aliases = native_aliases(document, data, label)
            native = {row["row"]: row for row in document["rows"]}
            target, selected = label["action_row"], predicted["prediction"]["greedy_row"]
            target_parameters = parameter_row(data, target)
            raw_observation = json.loads(Path(label["observation_path"]).read_text())
            exposed = [row for row in raw_observation["candidates"] if row["key"] == label["candidate_key"]]
            if len(exposed) != 1 or exposed[0]["parameters"] != target_parameters:
                raise ValueError("Human target is absent/misaligned in its exact pre-command public inventory")
            row = {"game_id": key[0], "sample_id": key[1], "target_row": target, "selected_row": selected,
                   "input_alias_audit": aliases, "error": classify(target_parameters, native[selected]["parameters"]),
                   "input_comparison": input_distance(native[target], native[selected]), "native_input_audit": audit_ref,
                   "original_unique_exact": predicted["prediction"]["unique_exact"],
                   "permuted_unique_exact": predicted["permuted_prediction"]["unique_greedy_target"],
                   "permuted_semantic_choice_unchanged": predicted["prediction"]["greedy_row"] == predicted["permuted_prediction"]["original_greedy_row"],
                   "permutation_max_probability_error": predicted["permutation_probability_max_error"],
                   "label_alignment": "passed"}
            report["rows"].append(row)
        if len(report["rows"]) != 43:
            raise ValueError("Did not audit all 43 training insertions")
        report["summary"] = {"examples": 43, "aliased_targets": sum(bool(row["input_alias_audit"]["target_alias_rows"]) for row in report["rows"]),
                             "alias_groups": sum(len(row["input_alias_audit"]["alias_groups"]) for row in report["rows"]),
                             "errors": dict(Counter(row["error"]["category"] for row in report["rows"])),
                             "aligned_targets": 43, "permutation_changed_choices": sum(not row["permuted_semantic_choice_unchanged"] for row in report["rows"]),
                             "maximum_permutation_probability_error": max(row["permutation_max_probability_error"] for row in report["rows"])}
        for reference in (*refs, offline_ref, diagnostics_ref, report["training_run"], report["audit_executable"]):
            checked(reference)
        if report["summary"]["aliased_targets"] or report["summary"]["permutation_changed_choices"]:
            raise ValueError("Insertion inputs alias or fail row permutation")
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        write_json(output / "report.json", report)
    print(json.dumps(report["summary"]), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-run", type=Path, required=True)
    parser.add_argument("--offline-model", type=Path, required=True)
    parser.add_argument("--choice-diagnostics", type=Path, required=True)
    parser.add_argument("--audit-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
