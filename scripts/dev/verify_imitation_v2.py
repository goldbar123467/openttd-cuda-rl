#!/usr/bin/env python3
"""Verify native imitation numerics or import of an immutable human policy."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from infer_v2 import PolicyClient
from local import capture_source, host, source_identity, write_json
from imitation_warm_start_v2 import checked_imitation_run, import_imitation
from imitation_prediction_metrics_v2 import PROBABILITY_TOLERANCE, prediction_metrics, prediction_summary
from v2_onnx_package import FINANCIAL_FEATURES


def verify_import(build, weights, observation, candidates, action, output, device, financial_features):
    infer = PolicyClient(build / "rl_dev_v2_infer", output / "infer.log", device, 20261002,
                         mode="greedy", weights=weights, financial_features=financial_features)
    trainer = PolicyClient(build / "rl_dev_v2_train", output / "ppo.log", device, 20261002,
                           financial_features=financial_features, gradient_norm="fp64-v1")
    try:
        imported = trainer.request(f"IMPORT_WEIGHTS\t{weights}")
        if imported != {"status": "IMPORTED_WEIGHTS", "updates": 0, "optimizer_reset": True, "recurrent_reset": True}:
            raise ValueError("Unexpected warm start result")
        expected = infer.request(f"{observation}\t{candidates}")
        actual = trainer.request(f"PROBE\t{observation}\t{candidates}\t{action}")
        errors = {"probability": abs(actual["proposal_probability"] - expected["probabilities"][action]),
                  "value": abs(actual["value"] - expected["value"]), "entropy": abs(actual["entropy"] - expected["entropy"])}
        if max(errors.values()) > 1e-5:
            raise ValueError("Imported PPO differs from saved imitation inference")
        infer.close(); infer = None
        return trainer, {"import": imported, "errors": errors, "probe_before": actual}
    except BaseException:
        trainer.abort()
        raise
    finally:
        if infer:
            infer.abort()


def run(args):
    root, build = args.output.resolve(), args.build_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    record = {"kind": "synthetic-native-imitation-regression", "status": "running", "source": source_identity(),
              "source_capture": capture_source(root / "source"), "runtime": host(), "device": args.device,
              "seed": 20261002, "financial_features": args.financial_features,
              "fixture": "artificial zero observation with WAIT and one target loan candidate; not human data"}
    write_json(root / "report.json", record)
    try:
        obs = root / "synthetic-observation.bin"
        observation = bytearray(2182927)
        if args.financial_features in ("signed-log-orders-v1", "signed-log-orders-v2"):
            struct.pack_into("<f", observation, 511 * 4, 1.0)
        obs.write_bytes(observation)
        candidate = root / "synthetic-candidates.bin"
        data = bytearray(790528)
        struct.pack_into("<f", data, 3 * 128, 1.0)
        struct.pack_into("<I", data, 4096 * 128 + 3 * 64, 11)
        struct.pack_into("<2I", data, 4096 * 128 + 3 * 64 + 4, 2, 10000)
        data[-4096] = 1; data[-4096 + 3] = 1
        candidate.write_bytes(data)
        manifest = root / "synthetic.tsv"
        manifest.write_text(f"openttd-rl-development-v2-imitation-1\nfixture\tsynthetic-test\t{obs}\t{candidate}\t3\t11\t0,3\n")
        weights = root / "inference-weights.pt"
        command = [str(build / "rl_dev_v2_imitation"), "--device", args.device, "--seed", "20261002", "--epochs", "8",
                   "--learning-rate", "0.0003", "--financial-features", args.financial_features, "--manifest", str(manifest), "--output", str(weights)]
        record["command"] = command
        with (root / "metrics.jsonl").open("x") as metrics, (root / "imitation.log").open("x") as log:
            subprocess.run(command, stdout=metrics, stderr=log, check=True)
        record["native"] = json.loads((root / "metrics.jsonl").read_text().splitlines()[-1])
        failures = []
        for name, row, family, legal in (("masked-label", 2, 11, "0,3"), ("stale-mask", 3, 11, "3"), ("wrong-family", 3, 2, "0,3"), ("duplicate-mask", 3, 11, "0,3,3")):
            invalid = root / f"{name}.tsv"
            invalid.write_text(f"openttd-rl-development-v2-imitation-1\nfixture\tsynthetic-test\t{obs}\t{candidate}\t{row}\t{family}\t{legal}\n")
            modified = list(command)
            modified[modified.index("--manifest") + 1] = str(invalid)
            modified[modified.index("--output") + 1] = str(root / f"{name}.pt")
            result = subprocess.run(modified, capture_output=True, text=True)
            (root / f"{name}.log").write_text(result.stdout + result.stderr)
            if result.returncode == 0 or (root / f"{name}.pt").exists():
                raise ValueError("Invalid dataset unexpectedly accepted")
            failures.append(name)
        if args.financial_features in ("signed-log-actions-v1", "signed-log-orders-v1", "signed-log-orders-v2"):
            # A duplicate target input must fail before an optimizer update,
            # even if row order would make argmax appear correct.
            aliased = bytearray(data)
            aliased[4 * 128:5 * 128] = aliased[3 * 128:4 * 128]
            offset = 4096 * 128
            aliased[offset + 4 * 64:offset + 5 * 64] = aliased[offset + 3 * 64:offset + 4 * 64]
            aliased[-4096 + 4] = 1
            alias_candidates = root / "aliased-candidates.bin"
            alias_candidates.write_bytes(aliased)
            alias_manifest = root / "aliased-target.tsv"
            alias_manifest.write_text(f"openttd-rl-development-v2-imitation-1\nfixture\tsynthetic-test\t{obs}\t{alias_candidates}\t3\t11\t0,3,4\n")
            modified = list(command)
            modified[modified.index("--manifest") + 1] = str(alias_manifest)
            modified[modified.index("--output") + 1] = str(root / "aliased-target.pt")
            result = subprocess.run(modified, capture_output=True, text=True)
            (root / "aliased-target.log").write_text(result.stdout + result.stderr)
            events = [json.loads(line) for line in result.stdout.splitlines()]
            if (result.returncode == 0 or (root / "aliased-target.pt").exists() or
                    [event["event"] for event in events] != ["initial"] or
                    events[0]["metrics"]["target_input_alias_count"] != 1 or
                    "action-aware imitation target input alias" not in result.stderr):
                raise ValueError("Aliased target was not rejected before optimization")
            failures.append("aliased-target-before-update")
        record["invalid_dataset_rejections"] = failures
        trainer, parity = verify_import(build, weights, obs, candidate, 3, root, args.device, args.financial_features)
        record["import_parity"] = parity
        try:
            for _ in range(32):
                choice = trainer.request(f"ACT\t{obs}\t{candidate}\t1")
                trainer.request(f"REWARD\t{int(choice['row'] == 3)}\t0\t0\t-\t-")
            record["synthetic_ppo_update"] = trainer.request("UPDATE")
            after = trainer.request(f"PROBE\t{obs}\t{candidate}\t3")
            record["post_ppo_probe"] = after
            before = parity["probe_before"]
            if max(abs(after[key] - before[key]) for key in ("proposal_probability", "value")) <= 1e-8:
                raise ValueError("PPO update did not change observable policy/value behavior")
            refined = root / "synthetic-ppo.pt"
            record["ppo_save"] = trainer.request(f"SAVE\t{refined}")
            if weights.read_bytes() == refined.read_bytes():
                raise ValueError("PPO update did not change imported weights")
            record["weights_changed_after_ppo"] = True
            trainer.close(); trainer = None
        finally:
            if trainer:
                trainer.abort()
        repeated = subprocess.run([str(build / "rl_dev_v2_train"), "--device", args.device, "--seed", "20261002", "--financial-features", args.financial_features],
                                  input=f"IMPORT_WEIGHTS\t{weights}\nIMPORT_WEIGHTS\t{weights}\n", capture_output=True, text=True)
        (root / "repeat-import.log").write_text(repeated.stdout + repeated.stderr)
        if repeated.returncode == 0 or len(repeated.stdout.splitlines()) != 1:
            raise ValueError("Repeated import was not rejected after the first successful import")
        record["repeated_import_rejected"] = True
        record["binary_sha256"] = {name: hashlib.sha256((build / name).read_bytes()).hexdigest()
                                    for name in ("rl_dev_v2_imitation", "rl_dev_v2_train", "rl_dev_v2_infer")}
        record["status"] = "passed"
    except BaseException as error:
        record["status"] = "failed"; record["error"] = repr(error)
        raise
    finally:
        write_json(root / "report.json", record)


def human_import(args):
    root, build = args.output.resolve(), args.build_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    run, ancestry = checked_imitation_run(args.imitation_run, financial_features=args.financial_features)
    report = {"kind": "native-human-imitation-ppo-import-verification", "status": "running",
              "source": source_identity(), "runtime": host(), "device": args.device, "seed": 20261002,
              "ancestry": ancestry, "checks": [],
              "claim": "Passed status verifies import parity; training-example reproduction is reported separately, not held-out accuracy",
              "metric_definition": {"accuracy": "legacy exact greedy row, including ties",
                  "unique_exact_accuracy": "target strictly beats every legal alternative by the probability tolerance",
                  "probability_tolerance": PROBABILITY_TOLERANCE, "input_alias_audit_performed": False}}
    infer = trainer = None
    try:
        infer = PolicyClient(build / "rl_dev_v2_infer", root / "infer.log", args.device, 20261002,
                             mode="greedy", weights=Path(ancestry["weights"]), financial_features=args.financial_features)
        trainer = PolicyClient(build / "rl_dev_v2_train", root / "ppo.log", args.device, 20261002,
                               financial_features=args.financial_features, gradient_norm="fp64-v1")
        report["import"] = import_imitation(trainer, ancestry)
        for example in json.loads(Path(run["dataset"]["labels"]["path"]).read_text())["records"]:
            observation = example["archived_tensors"]["observation"]["path"]
            candidates = example["archived_tensors"]["candidate"]["path"]
            action = example["action_row"]
            infer.request("RESET")
            expected = infer.request(f"{observation}\t{candidates}")
            metrics = prediction_metrics(expected, example)
            actual = trainer.request(f"PROBE\t{observation}\t{candidates}\t{action}")
            errors = {"probability": abs(actual["proposal_probability"] - expected["probabilities"][action]),
                      "value": abs(actual["value"] - expected["value"]), "entropy": abs(actual["entropy"] - expected["entropy"])}
            if max(errors.values()) > 1e-5:
                raise ValueError("Human imitation policy changed on PPO import")
            parameters = struct.unpack_from("<16I", Path(candidates).read_bytes(), 4096 * 128 + expected["row"] * 64)
            target_parameters = struct.unpack_from("<16I", Path(candidates).read_bytes(), 4096 * 128 + action * 64)
            report["checks"].append({**metrics, "sample_id": example["sample_id"], "errors": errors,
                "target_row": action, "target_family": example["action_family"], "target_parameters": list(target_parameters),
                "greedy_row": expected["row"], "greedy_family": parameters[0], "greedy_parameters": list(parameters),
                "target_probability": expected["probabilities"][action],
                "greedy_probability": expected["probabilities"][expected["row"]]})
        report["summary"] = prediction_summary(report["checks"])
        report["by_family"] = {str(family): prediction_summary([item for item in report["checks"] if item["target_family"] == family])
                               for family in sorted({item["target_family"] for item in report["checks"]})}
        report["metric_clarification"] = "The fit's family_head_accuracy (historically named family_accuracy) measures the family head's most likely marginal family, not the globally most likely candidate's family; greedy_family here decodes the actual selected candidate."
        report["status"] = "passed"
        trainer.close(); trainer = None
        infer.close(); infer = None
    except BaseException as error:
        report["status"] = "failed"; report["error"] = repr(error)
        raise
    finally:
        for client in (infer, trainer):
            if client:
                client.abort()
        write_json(root / "report.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    parser.add_argument("--imitation-run", type=Path, help="Verify all immutable human labels on PPO import; otherwise use synthetic regression")
    parser.add_argument("--financial-features", choices=FINANCIAL_FEATURES, default="signed-log-actions-v1")
    args = parser.parse_args()
    human_import(args) if args.imitation_run else run(args)
