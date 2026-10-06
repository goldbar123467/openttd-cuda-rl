#!/usr/bin/env python3
"""Compare compatible human imitation models on disclosed corpora or bus contexts.

This reports imperfect fits as outcomes. It never selects or trains a model.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import time

from audit_action_inputs_v2 import artifact, checked, check_labels, prediction_result, reverse_legal_rows
from audit_bus_orders_v2 import SCHEMA, check_replay
from imitation_prediction_metrics_v2 import prediction_metrics, prediction_summary
from imitation_warm_start_v2 import checked_imitation_run
from infer_v2 import PolicyClient
from live_bus_orders_v2 import CONTEXTS, run_context
from local import capture_source, host, source_identity, write_json

MODE = "signed-log-orders-v2"


def valid_name(name):
    return isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name) is not None


def label_identity(label):
    return (label["game_id"], label["sample_id"], label["action_row"], label["action_family"],
            tuple(label["legal_rows"]),
            tuple(label["archived_tensors"][name]["sha256"] for name in ("observation", "candidate")))


def corpus(path):
    reference = artifact(path)
    document = json.loads(Path(reference["path"]).read_text())
    if document.get("kind") == "native-human-evaluation-audit" and document.get("status") == "passed":
        from audit_human_evaluation_v2 import validate
        export_ref = checked(document["dataset"])
        export = json.loads(Path(export_ref["path"]).read_text())
        expected = validate(Path(export["source_dataset"]["path"]), document["split"])
        if export != expected or export["example_count"] != document["example_count"]:
            raise ValueError("Evaluation corpus differs from its exact integrity audit")
        labels, tensors = [], []
        refs = [reference, export_ref, checked(export["source_dataset"]), checked(export["replay_validation"]),
                checked(export["recording_metadata"]), checked(export["capture_transfer"])]
        for row in export["records"]:
            pair = {"observation": checked(row["verified_tensors"]["observation"]),
                    "candidate": checked(row["verified_tensors"]["candidates"])}
            labels.append({**row, "archived_tensors": pair})
            tensors.append(pair)
            refs.extend(pair.values())
        return labels, tensors, refs
    if document.get("kind") == "native-human-campaign-assembly" and document.get("status") == "passed":
        dataset = document["prepared"]
    elif document.get("kind") == "native-v2-human-imitation" and document.get("status") == "completed":
        dataset = document["dataset"]
    else:
        raise ValueError("Corpus must come from a passed assembly or completed human imitation run")
    if dataset["observation_schema_id"] != SCHEMA or dataset["model_financial_features"] != MODE:
        raise ValueError("Corpus observation or preprocessing differs")
    labels, tensors, refs = check_labels({"dataset": dataset})
    children = [item["prepared"] for item in dataset.get("sources", [])] or [dataset]
    for child in children:
        refs += [checked(child["manifest"]), checked(child["replay_validation"]),
                 checked(child["source_recording"]["command_log"])]
    for source in dataset.get("sources", []):
        refs += [checked(source[name]) for name in ("dataset", "recording_metadata", "capture_transfer")]
    refs += [reference, checked(dataset["manifest"])]
    refs += [value for pair in tensors for value in pair.values()]
    checked(reference)
    return labels, tensors, refs


def grouped(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row["prediction"])
    return {name: prediction_summary(items) for name, items in sorted(groups.items())}


def offline(args, name, imitation, output, corpora):
    output.mkdir(parents=True, exist_ok=False)
    training, _, _ = check_labels(imitation)
    identities = {label_identity(label) for label in training}
    client = PolicyClient(args.policy.resolve(), output / "policy.log", args.device, args.seed,
                          mode="greedy", weights=Path(imitation["model"]["path"]), financial_features=MODE)
    result = {"model": name, "corpora": {}}
    try:
        client.check_financial_features()
        for corpus_name, (labels, tensors, _) in corpora.items():
            directory = output / corpus_name
            directory.mkdir(exist_ok=False)
            rows = []
            with (directory / "predictions.jsonl").open("x") as stream:
                for index, (label, pair) in enumerate(zip(labels, tensors)):
                    observation, candidate = [pair[key]["path"] for key in ("observation", "candidate")]
                    client.request("RESET")
                    prediction = client.request(f"{observation}\t{candidate}")
                    permuted, permutation = reverse_legal_rows(Path(candidate).read_bytes(), label)
                    permuted_path = directory / f"{index:04d}-permuted.bin"
                    permuted_path.write_bytes(permuted)
                    client.request("RESET")
                    reordered = client.request(f"{observation}\t{permuted_path}")
                    reordered_metrics = prediction_result(reordered, label, permutation=permutation)
                    error = max(abs(prediction["probabilities"][old] - reordered["probabilities"][new])
                                for new, old in permutation.items())
                    if error > 1e-6:
                        raise ValueError("Candidate permutation changes semantic probabilities above tolerance")
                    operation = label["operation"]
                    if operation == "manage-loan":
                        operation += ":" + label["source_command"]["name"]
                    row = {"game_id": label["game_id"], "sample_id": label["sample_id"],
                           "game": label.get("campaign_game_id", label["game_id"]), "operation": operation,
                           "partition": label.get("split", "train"),
                           "scope": "training-fit" if label_identity(label) in identities else "unseen-recording-transfer",
                           "prediction": prediction_metrics(prediction, label), "permuted_prediction": reordered_metrics,
                           "permutation_probability_max_error": error, "permuted_tensor": artifact(permuted_path)}
                    rows.append(row)
                    stream.write(json.dumps({**row, "original": prediction, "permuted": reordered,
                                             "new_to_original": permutation}) + "\n")
                    stream.flush()
            summary = {"overall": prediction_summary([row["prediction"] for row in rows]),
                       "by_operation": grouped(rows, "operation"), "by_game": grouped(rows, "game"),
                       "by_scope": grouped(rows, "scope"),
                       "by_partition": grouped(rows, "partition"),
                       "permutation_max_probability_error": max(row["permutation_probability_max_error"] for row in rows),
                       "permuted_unique_exact": sum(row["permuted_prediction"]["unique_greedy_target"] for row in rows)}
            result["corpora"][corpus_name] = {"summary": summary, "rows": rows,
                                            "raw_predictions": artifact(directory / "predictions.jsonl")}
            write_json(output / "report.json", result)
            print(json.dumps({"model": name, "corpus": corpus_name, **summary["overall"]}), flush=True)
        client.close()
        client = None
    finally:
        if client:
            client.abort()
    return result


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {"kind": "human-imitation-comparison", "status": "running", "stage": args.stage,
              "source": source_identity(), "runtime": host(), "device": args.device, "seed": args.seed,
              "financial_features": MODE, "policy": artifact(args.policy), "models": {}, "results": [],
              "claim": "Disclosed fit/transfer diagnostics and bounded supplied-context continuations; no held-out strength estimate"}
    started = time.monotonic()
    refs = [record["policy"]]
    record["inputs"] = refs
    record["configuration"] = {key: str(value) if isinstance(value, Path) else value
                               for key, value in vars(args).items()}
    try:
        record["source_capture"] = capture_source(output / "source")
        corpora = {}
        if args.stage == "offline":
            if not args.corpus:
                raise ValueError("Offline comparison requires explicit corpora")
            for name, path in args.corpus:
                if not valid_name(name) or name in corpora:
                    raise ValueError("Corpus names must be unique simple identifiers")
                corpora[name] = corpus(Path(path))
                refs += corpora[name][2]
            record["corpora"] = {name: {"examples": len(value[0]), "inputs": value[2]} for name, value in corpora.items()}
        else:
            if args.replay is None or args.openttd is None:
                raise ValueError("Live comparison requires explicit verified contexts and engine")
            check_replay(args.replay)
            refs += [artifact(args.replay / "report.json"), artifact(args.openttd)]
            record["openttd"] = refs[-1]
            record["live_budget"] = {"decisions": args.decisions, "ticks": args.ticks, "contexts": list(CONTEXTS),
                                      "modes": ["greedy", "sampled"], "guidance": "none"}
        for name, path in args.model:
            if not valid_name(name) or name in record["models"]:
                raise ValueError("Model names must be unique simple identifiers")
            imitation, _ = checked_imitation_run(Path(path), observation_schema=SCHEMA, financial_features=MODE)
            model_ref = checked(imitation["model"])
            run_ref = artifact(Path(path) / "run.json")
            refs += [run_ref, model_ref]
            record["models"][name] = {"run": run_ref, "model": model_ref, "epochs": imitation["epochs"],
                                       "training_examples": imitation["dataset"]["example_count"],
                                       "native_training_result": imitation["result"]}
            if args.stage == "offline":
                record["results"].append(offline(args, name, imitation, output / name, corpora))
            else:
                results = []
                for line in CONTEXTS:
                    for mode in ("greedy", "sampled"):
                        directory = output / name / f"line-{line}-{mode}"
                        result = run_context(args, args.replay, model_ref, directory, line, mode, MODE,
                                             context_claim="Continuation from disclosed October 2 recording contexts; familiarity depends on model training data; no construction learning or held-out strength claim")
                        item = {"report": artifact(directory / "run.json"), "line": line, "mode": mode,
                                "summary": result["summary"], "operation_counts": result["operation_counts"],
                                "target_started_with_exact_full_load_route": result["target_started_with_exact_full_load_route"],
                                "target_started_with_same_station_pair_and_full_load": any(
                                    start["is_target_bus"] and start["both_endpoints_full_load_any"] and
                                    sorted(start["route"]) == sorted(CONTEXTS[line]["expected_route"])
                                    for start in result["starts"]),
                                "target_final_exact_full_load_route": result["target_final_exact_full_load_route"],
                                "target_final": result["target_final"]}
                        results.append(item)
                        write_json(output / name / "report.json", {"model": name, "runs": results})
                        print(json.dumps({"model": name, **item}), flush=True)
                record["results"].append({"model": name, "runs": results})
            write_json(output / "report.json", record)
        for reference in refs:
            checked(reference)
        record["inputs_unchanged"] = True
        record["status"] = "completed"
    except BaseException as error:
        record.update(status="failed", error=repr(error))
        raise
    finally:
        record["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "report.json", record)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("offline", "live"), required=True)
    parser.add_argument("--model", nargs=2, action="append", required=True, metavar=("NAME", "RUN"))
    parser.add_argument("--corpus", nargs=2, action="append", metavar=("NAME", "REPORT"))
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--openttd", type=Path)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), default="cpu")
    parser.add_argument("--seed", type=int, default=20261002)
    parser.add_argument("--decisions", type=int, choices=range(1, 65), default=24)
    parser.add_argument("--ticks", type=int, choices=range(1, 129), default=128)
    run(parser.parse_args())
