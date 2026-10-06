#!/usr/bin/env python3
"""Train an isolated diagnostic subset of already validated training insertions."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from audit_action_inputs_v2 import artifact, checked, prediction_result, reverse_legal_rows
from compare_human_imitation_v2 import corpus
from imitation_warm_start_v2 import checked_imitation_run
from infer_v2 import PolicyClient
from local import capture_source, host, source_identity, write_json


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    base, _ = checked_imitation_run(args.training_run, observation_schema="v2-m15-public-development-orders-v1",
                                    financial_features="signed-log-orders-v2")
    labels, tensors, refs = corpus(args.training_run / "run.json")
    selected = [(label, pair) for label, pair in zip(labels, tensors) if label["operation"] == "insert-order"]
    if len(selected) != 43 or any(label["split"] != "train" for label, _ in selected):
        raise ValueError("Diagnostic requires the 43 actual training insertions")
    manifest = output / "native-imitation.tsv"
    lines = ["openttd-rl-development-v2-imitation-1"]
    for label, pair in selected:
        lines.append("\t".join([label["sample_id"], label["game_id"], pair["observation"]["path"], pair["candidate"]["path"],
                                str(label["action_row"]), str(label["action_family"]), ",".join(map(str, label["legal_rows"]))]))
    manifest.write_text("\n".join(lines) + "\n")
    write_json(output / "labels.json", {"diagnostic_subset": "train-only-insertions", "records": [label for label, _ in selected]})
    report = {"kind": "native-human-insertion-memorization-diagnostic", "status": "running", "source": source_identity(),
              "runtime": host(), "source_training_run": artifact(args.training_run / "run.json"),
              "device": "cuda:0", "seed": 20261002, "epochs": args.epochs, "learning_rate": .0003,
              "examples": 43, "financial_features": "signed-log-orders-v2", "context": "independent-reset",
              "trainer": artifact(args.trainer), "policy": artifact(args.policy), "native_manifest": artifact(manifest),
              "objective": "Unchanged C++ exact-candidate mean NLL, only the verified 43 training insertions; complete legal masks",
              "initialization": "fresh fixed-seed policy, no source-model weights loaded",
              "evaluation_model_unchanged": checked(base["model"]), "not_a_benchmark_actor": True}
    client = None
    try:
        report["source_capture"] = capture_source(output / "source-provenance")
        model = output / "inference-weights.pt"
        command = [str(args.trainer.resolve()), "--device", "cuda:0", "--seed", "20261002", "--epochs", str(args.epochs),
                   "--learning-rate", "0.0003", "--financial-features", "signed-log-orders-v2", "--manifest", str(manifest),
                   "--output", str(model)]
        report["command"] = command
        write_json(output / "run.json", report)
        with (output / "native-metrics.jsonl").open("x") as metrics, (output / "trainer.log").open("x") as log:
            subprocess.run(command, stdout=metrics, stderr=log, check=True)
        events = [json.loads(line) for line in (output / "native-metrics.jsonl").read_text().splitlines()]
        result = events[-1]
        if (result["event"] != "completed" or result["device"] != "cuda:0" or result["examples"] != 43
                or not result["finite_gradients"] or not result["exact_legal_masks"] or not result["cpu_cuda_compared"]
                or result["final"]["loss"] >= result["initial"]["loss"]):
            raise ValueError("Native diagnostic training did not pass numerical checks")
        report.update(result=result, model=artifact(model))
        client = PolicyClient(args.policy.resolve(), output / "inference.log", "cpu", 20261002, mode="greedy",
                              weights=model, financial_features="signed-log-orders-v2")
        client.check_financial_features()
        rows = []
        for index, (label, pair) in enumerate(selected):
            client.request("RESET")
            original = client.request(f"{pair['observation']['path']}\t{pair['candidate']['path']}")
            data, permutation = reverse_legal_rows(Path(pair["candidate"]["path"]).read_bytes(), label)
            path = output / f"permuted-{index:02d}.bin"
            path.write_bytes(data)
            client.request("RESET")
            permuted = client.request(f"{pair['observation']['path']}\t{path}")
            error = max(abs(original["probabilities"][old] - permuted["probabilities"][new]) for new, old in permutation.items())
            if error > 1e-6:
                raise ValueError("Diagnostic candidate permutation differs")
            rows.append({"sample_id": label["sample_id"], "game_id": label["game_id"], "original": prediction_result(original, label),
                         "permuted": prediction_result(permuted, label, permutation=permutation), "probability_max_error": error})
        client.close()
        client = None
        report["permutation_audit"] = {"rows": rows, "unique_exact": sum(row["original"]["unique_greedy_target"] for row in rows),
                                       "permuted_unique_exact": sum(row["permuted"]["unique_greedy_target"] for row in rows),
                                       "maximum_probability_error": max(row["probability_max_error"] for row in rows)}
        for reference in (*refs, report["source_training_run"], report["trainer"], report["policy"], report["evaluation_model_unchanged"]):
            checked(reference)
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        if client:
            client.abort()
        report["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "run.json", report)
    print(json.dumps({"status": report["status"], "epochs": args.epochs, "examples": 43,
                      "unique_exact": report["permutation_audit"]["unique_exact"], "loss": report["result"]["final"]["loss"]}), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-run", type=Path, required=True)
    parser.add_argument("--trainer", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--epochs", type=int, choices=(256, 1000), default=256)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
