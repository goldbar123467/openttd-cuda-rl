#!/usr/bin/env python3
"""Audit public v3 inputs and one frozen fit on training/development only."""
import argparse
from collections import Counter, defaultdict
import gzip
import json
import math
from pathlib import Path
import subprocess

from audit_action_inputs_v2 import artifact, checked, native_aliases, parameter_row, reverse_legal_rows
from audit_bus_orders_v2 import public_order_tensor
from compare_human_imitation_v2 import corpus
from imitation_prediction_metrics_v2 import prediction_metrics, prediction_summary
from imitation_warm_start_v2 import checked_imitation_run
from infer_v2 import PolicyClient
from local import capture_source, source_identity, write_json
from order_projection_v3 import project_pair


def public_context(state, parameters):
    vehicles = {bus["id"]: bus for bus in state["vehicles"]}
    bus = vehicles[parameters[1]]
    orders = [order["destination"] for order in bus["orders"]]
    operation, index = parameters[2] & 255, parameters[2] >> 8 & 255
    if operation == 3:
        return [0, 0, len(orders) / 4, int(bus["stopped"]), 0, 0]
    station = parameters[3] if operation == 1 else orders[index]
    adjacent = operation == 1 and ((index > 0 and orders[index - 1] == station) or
                                  (index < len(orders) and orders[index] == station))
    # Count independently from JSON, once per bus even when its list repeats a stop.
    serving = sum(any(order["destination"] == station for order in other["orders"])
                  for other in state["vehicles"])
    stop = next(stop for stop in state["stations"] if stop["id"] == station)
    waiting = min(stop["waiting_passengers"], 65535)
    return [int(station in orders), int(adjacent), len(orders) / 4, int(bus["stopped"]),
            math.log1p(serving) / math.log1p(1024), math.log1p(waiting) / math.log1p(65535)]


def input_audit(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    labels, tensors, references = corpus(args.training)
    if len(labels) != 186 or any(row.get("split") != "train" for row in labels):
        raise ValueError("V3 audit requires exactly the 186 training labels")
    report = {"kind": "orders-v3-public-input-audit", "status": "running", "source": source_identity(),
              "audit_executable": artifact(args.audit_executable), "corpus": artifact(args.training), "states": []}
    try:
        report["source_capture"] = capture_source(output / "source")
        for index, (label, pair) in enumerate(zip(labels, tensors)):
            state = json.loads(Path(label["observation_path"]).read_text())
            original = Path(pair["observation"]["path"]).read_bytes()
            public_order_tensor(state, original)
            paths, projection = project_pair(pair["observation"]["path"], pair["candidate"]["path"], output / "projected", public_state=state)
            native = subprocess.run([str(args.audit_executable.resolve()), "--observation", str(paths[0]),
                                     "--candidates", str(paths[1]), "--financial-features", "signed-log-orders-v3"],
                                    capture_output=True, text=True, check=True, timeout=60)
            document = json.loads(native.stdout)
            data = paths[1].read_bytes()
            aliases = native_aliases(document, data, label)
            if aliases["alias_groups"]:
                raise ValueError("V3 introduced exact candidate aliases")
            errors = []
            for row in document["rows"]:
                if row["family"] == 6:
                    expected = public_context(state, row["parameters"])
                    error = max(abs(a - b) for a, b in zip(expected, row["features"][14:20]))
                    if error > 1e-6:
                        raise ValueError("Native v3 context differs from independent public JSON projection")
                    errors.append(error)
            native_path = output / f"state-{index:03d}.json.gz"
            with gzip.open(native_path, "wt") as stream:
                stream.write(native.stdout)
            report["states"].append({"game_id": label["game_id"], "sample_id": label["sample_id"],
                                     "aliases": aliases, "native_audit": artifact(native_path), "projection": projection,
                                     "public_context_max_error": max(errors, default=0)})
            if (index + 1) % 32 == 0:
                print(json.dumps({"input_states_audited": index + 1}), flush=True)
        for ref in references:
            checked(ref)
        checked(report["audit_executable"])
        report.update(status="passed", states_audited=len(labels), alias_groups=0,
                      public_context_max_error=max(row["public_context_max_error"] for row in report["states"]))
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        write_json(output / "report.json", report)
    return report


def fit_audit(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    run, _ = checked_imitation_run(args.imitation_run, observation_schema="v2-m15-public-development-orders-v1")
    mode = run["financial_features"]
    if mode not in ("signed-log-orders-v2", "signed-log-orders-v3"):
        raise ValueError("Only frozen v2/v3 actors are accepted")
    report = {"kind": "orders-v3-frozen-fit-audit", "status": "running", "source": source_identity(),
              "model": checked(run["model"]), "financial_features": mode, "corpora": {}}
    client = None
    try:
        report["source_capture"] = capture_source(output / "source")
        client = PolicyClient(args.policy.resolve(), output / "policy.log", "cpu", 20261002,
                              mode="greedy", weights=Path(run["model"]["path"]), financial_features=mode)
        client.check_financial_features()
        for name, path in (("training", args.training), ("development-game-08", args.development)):
            labels, tensors, references = corpus(path)
            expected = "train" if name == "training" else "development"
            if len(labels) != (186 if expected == "train" else 34) or any(label.get("split") != expected for label in labels):
                raise ValueError("V3 fit audit refuses other partitions/counts")
            rows, groups = [], defaultdict(list)
            directory = output / name
            directory.mkdir()
            with (directory / "predictions.jsonl").open("x") as stream:
                for index, (label, pair) in enumerate(zip(labels, tensors)):
                    obs, candidate = (Path(pair[key]["path"]) for key in ("observation", "candidate"))
                    state = json.loads(Path(label["observation_path"]).read_text())
                    client.request("RESET")
                    prediction = client.request(f"{obs}\t{candidate}", public_state=state)
                    data = candidate.read_bytes()
                    parameters = parameter_row(data, prediction["row"])
                    context = public_context(state, parameters) if parameters[0] == 6 else None
                    permuted, permutation = reverse_legal_rows(data, label)
                    permuted_path = directory / "permuted.bin"
                    permuted_path.write_bytes(permuted)
                    client.request("RESET")
                    reordered = client.request(f"{obs}\t{permuted_path}", public_state=state)
                    error = max(abs(prediction["probabilities"][old] - reordered["probabilities"][new])
                                for new, old in permutation.items())
                    if error > 1e-6:
                        raise ValueError("Policy probabilities changed under candidate permutation")
                    operation = label["operation"]
                    if operation == "manage-loan":
                        operation += ":" + label["source_command"]["name"]
                    row = {"game_id": label["game_id"], "sample_id": label["sample_id"], "operation": operation,
                           "prediction": prediction_metrics(prediction, label), "selected_parameters": parameters,
                           "insert_stop_already_present": bool(context and parameters[2] & 255 == 1 and context[0]),
                           "adjacent_duplicate_insertion": bool(context and parameters[2] & 255 == 1 and context[1]),
                           "permutation_max_error": error,
                           "permutation_semantic_choice_changed": permutation[reordered["row"]] != prediction["row"]}
                    rows.append(row); groups[operation].append(row["prediction"])
                    stream.write(json.dumps({**row, "original": prediction, "permuted": reordered}) + "\n")
            for ref in references:
                checked(ref)
            insertions = [row for row in rows if row["operation"] == "insert-order"]
            report["corpora"][name] = {"corpus": artifact(path), "overall": prediction_summary([r["prediction"] for r in rows]),
                                       "by_operation": {key: prediction_summary(items) for key, items in groups.items()},
                                       "insertion_states": len(insertions),
                                       "adjacent_duplicate_predictions": sum(row["adjacent_duplicate_insertion"] for row in insertions),
                                       "already_present_stop_predictions": sum(row["insert_stop_already_present"] for row in insertions),
                                       "permutation_max_error": max(row["permutation_max_error"] for row in rows),
                                       "permutation_semantic_choices_changed": sum(row["permutation_semantic_choice_changed"] for row in rows),
                                       "predictions": artifact(directory / "predictions.jsonl"), "rows": rows}
            print(json.dumps({"corpus": name, "unique_exact": report["corpora"][name]["overall"]["unique_exact_rows"],
                              "adjacent_duplicates": report["corpora"][name]["adjacent_duplicate_predictions"]}), flush=True)
        client.close(); client = None
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        if client:
            client.abort()
        write_json(output / "report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("inputs", "fit"), required=True)
    parser.add_argument("--training", type=Path, required=True)
    parser.add_argument("--development", type=Path)
    parser.add_argument("--imitation-run", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--audit-executable", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({"status": (input_audit(args) if args.stage == "inputs" else fit_audit(args))["status"]}))
