#!/usr/bin/env python3
"""Read-only native inference on original training examples before/after PPO."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct
import time

from imitation_warm_start_v2 import checked_imitation_run
from imitation_prediction_metrics_v2 import PROBABILITY_TOLERANCE, prediction_metrics, prediction_summary
from infer_v2 import PolicyClient
from local import capture_source, host, source_identity, write_json


def artifact(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def checked(record):
    actual = artifact(record["path"])
    if actual["sha256"] != record["sha256"]:
        raise ValueError("Retention audit source artifact hash differs")
    return actual


def summary(rows):
    groups = defaultdict(list)
    for row in rows:
        groups["all"].append(row)
        groups[str(row["target_family"])].append(row)
    result = {}
    for name, group in groups.items():
        result[name] = {}
        for phase in ("imitation", "ppo"):
            items = [row[phase] for row in group]
            result[name][phase] = prediction_summary(items)
        result[name]["forgotten_exact_rows"] = sum(row["imitation"]["exact_row"] and not row["ppo"]["exact_row"] for row in group)
        result[name]["gained_exact_rows"] = sum(not row["imitation"]["exact_row"] and row["ppo"]["exact_row"] for row in group)
        result[name]["forgotten_unique_choices"] = sum(row["imitation"]["unique_exact"] and not row["ppo"]["unique_exact"] for row in group)
        result[name]["gained_unique_choices"] = sum(not row["imitation"]["unique_exact"] and row["ppo"]["unique_exact"] for row in group)
    return result


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"kind": "native-v2-training-example-retention", "status": "running", "device": "cpu", "seed": 20261002,
        "source": source_identity(), "runtime": host(), "policy_executable": artifact(args.policy),
        "context": "independent recurrent reset for each original training observation",
        "mask": "immutable full native legal mask used for imitation, without the live PPO planner restriction",
        "metric_definition": {"accuracy": "legacy exact greedy row, including ties",
            "unique_exact_accuracy": "target strictly beats every legal alternative by the probability tolerance",
            "probability_tolerance": PROBABILITY_TOLERANCE, "input_alias_audit_performed": False},
        "claim": "Training-example retention only; no held-out accuracy, policy selection, training, or new gameplay"}
    write_json(output / "report.json", report)
    started = time.monotonic()
    try:
        report["source_capture"] = capture_source(output / "source")
        ppo_root = args.ppo_run.resolve()
        ppo = json.loads((ppo_root / "run.json").read_text())
        if ppo.get("kind") != "native-v2-live-recurrent-ppo" or ppo.get("status") != "completed":
            raise ValueError("Retention audit requires completed native live PPO")
        imitation, ancestry = checked_imitation_run(args.imitation_run,
            observation_schema=ppo["observation_schema_id"], financial_features=ppo["financial_features"])
        if ppo.get("initial_policy") != ancestry:
            raise ValueError("PPO was initialized from a different imitation policy")
        if Path(ppo["model"]["path"]).resolve() != ppo_root / "inference-weights.pt" or ppo["model"]["financial_features"] != ppo["financial_features"]:
            raise ValueError("PPO model path/preprocessing differs")
        models = {"imitation": checked(imitation["model"]), "ppo": checked(ppo["model"])}
        report["models"] = models
        report["run_manifests"] = {"imitation": artifact(args.imitation_run / "run.json"), "ppo": artifact(ppo_root / "run.json")}
        report["financial_features"] = ppo["financial_features"]
        report["labels"] = checked(imitation["dataset"]["labels"])
        labels = json.loads(Path(report["labels"]["path"]).read_text())["records"]
        if not labels or len(labels) != imitation["dataset"]["example_count"]:
            raise ValueError("Original training label count differs")
        rows = []
        for label in labels:
            if label["split"] != "train":
                raise ValueError("Retention audit must not consume held-out labels")
            tensors = {name: checked(value) for name, value in label["archived_tensors"].items()}
            data = Path(tensors["candidate"]["path"]).read_bytes()
            if len(data) != 790528 or [i for i, value in enumerate(data[-4096:]) if value] != label["legal_rows"]:
                raise ValueError("Original training legal mask differs")
            target = struct.unpack_from("<16I", data, 4096 * 128 + label["action_row"] * 64)
            if target[0] != label["action_family"]:
                raise ValueError("Training target family differs")
            rows.append({"sample_id": label["sample_id"], "game_id": label["game_id"], "source_command_index": label["source_command_index"],
                         "target_row": label["action_row"], "target_family": target[0], "target_parameters": list(target), "tensors": tensors})
        for phase, model in models.items():
            client = PolicyClient(args.policy.resolve(), output / f"{phase}-inference.log", "cpu", 20261002,
                                  mode="greedy", weights=Path(model["path"]), financial_features=ppo["financial_features"])
            try:
                client.check_financial_features()
                for row, label in zip(rows, labels):
                    observation, candidates = (row["tensors"][name]["path"] for name in ("observation", "candidate"))
                    client.request("RESET")
                    prediction = client.request(f"{observation}\t{candidates}")
                    probabilities = prediction["probabilities"]
                    metrics = prediction_metrics(prediction, label)
                    data = Path(candidates).read_bytes()
                    selected = struct.unpack_from("<16I", data, 4096 * 128 + prediction["row"] * 64)
                    row[phase] = {**metrics,
                        "greedy_row": prediction["row"], "greedy_family": selected[0], "greedy_parameters": list(selected),
                        "loan_direction": ("borrow" if selected[1] == 1 else "repay") if selected[0] == 11 else None,
                        "greedy_probability": probabilities[prediction["row"]], "value": prediction["value"]}
                client.close(); client = None
            finally:
                if client:
                    client.abort()
        report["rows"] = rows
        report["summary"] = summary(rows)
        # Recheck every input/model after both reads to establish immutability.
        for record in [*models.values(), *report["run_manifests"].values(), report["labels"], report["policy_executable"]]:
            checked(record)
        for row in rows:
            for record in row["tensors"].values():
                checked(record)
        report["inputs_unchanged"] = True
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"; report["error"] = repr(error)
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "report.json", report)
    print(json.dumps(report["summary"], sort_keys=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--imitation-run", type=Path, required=True)
    parser.add_argument("--ppo-run", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
