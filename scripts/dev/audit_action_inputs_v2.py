#!/usr/bin/env python3
"""Audit actual native action inputs and optional tie-free human training fit."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import time

from imitation_warm_start_v2 import checked_imitation_run
from infer_v2 import PolicyClient
from local import capture_source, host, source_identity, write_json

MODES = ("signed-log-loan-v1", "signed-log-actions-v1")
CAPACITY, FEATURE_WIDTH, PARAMETER_WIDTH = 4096, 32, 16
PARAMETER_OFFSET = CAPACITY * FEATURE_WIDTH * 4
CANDIDATE_BYTES = PARAMETER_OFFSET + CAPACITY * PARAMETER_WIDTH * 4 + CAPACITY
OBSERVATION_BYTES = 2182927
PROBABILITY_TOLERANCE = 1e-6


def artifact(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def checked(record):
    actual = artifact(record["path"])
    if actual["sha256"] != record["sha256"]:
        raise ValueError("Action audit input artifact hash differs")
    return actual


def parameter_row(data, row):
    return list(struct.unpack_from("<16I", data, PARAMETER_OFFSET + row * PARAMETER_WIDTH * 4))


def checked_candidate_data(data, label):
    if len(data) != CANDIDATE_BYTES:
        raise ValueError("Archived candidate tensor size differs")
    mask = data[-CAPACITY:]
    if any(value not in (0, 1) for value in mask):
        raise ValueError("Archived native legal mask contains a nonbinary value")
    legal = [row for row, value in enumerate(mask) if value]
    if not legal or legal != label["legal_rows"] or any(type(row) is not int for row in label["legal_rows"]):
        raise ValueError("Archived native legal mask differs from human labels")
    target, family = label["action_row"], label["action_family"]
    if type(target) is not int or target not in legal or type(family) is not int or not 0 <= family < 12:
        raise ValueError("Human target is not a legal native action")
    if parameter_row(data, target)[0] != family:
        raise ValueError("Human target family differs from archived native parameters")
    return legal


def native_aliases(document, data, label):
    """Compare the floats emitted by C++ after preprocessing, never emulate it."""
    legal = checked_candidate_data(data, label)
    rows = document.get("rows")
    if not isinstance(rows, list) or len(rows) != len(legal):
        raise ValueError("Native audit row count differs from the exact legal mask")
    encoded, by_row = defaultdict(list), {}
    digest = hashlib.sha256()
    for item in rows:
        row, family = item.get("row"), item.get("family")
        if type(row) is not int or row not in legal or row in by_row:
            raise ValueError("Native audit contains an illegal or duplicate row")
        parameters = item.get("parameters")
        if (not isinstance(parameters, list) or len(parameters) != PARAMETER_WIDTH or
                any(type(value) is not int or not 0 <= value <= 0xFFFFFFFF for value in parameters) or
                parameters != parameter_row(data, row) or type(family) is not int or
                family != parameters[0] or not 0 <= family < 12):
            raise ValueError("Native audit parameters differ from archived native action")
        features = item.get("features")
        if (not isinstance(features, list) or len(features) != FEATURE_WIDTH or
                any(type(value) not in (int, float) or not math.isfinite(value) for value in features)):
            raise ValueError("Native audit must emit finite 32-float candidate inputs")
        try:
            # +0/-0 are indistinguishable to this policy, despite different bits.
            packed = struct.pack("<32f", *(0.0 if value == 0 else value for value in features))
        except (OverflowError, struct.error) as error:
            raise ValueError("Native audit feature is outside float32 range") from error
        if any(not math.isfinite(value) for value in struct.unpack("<32f", packed)):
            raise ValueError("Native audit feature is outside float32 range")
        encoded[(family, packed)].append(item)
        by_row[row] = item
    for row in sorted(by_row):
        item = by_row[row]
        digest.update(struct.pack("<II32f", row, item["family"], *item["features"]))
    groups = []
    for (family, _), members in encoded.items():
        if len({tuple(item["parameters"]) for item in members}) <= 1:
            continue
        members.sort(key=lambda item: item["row"])
        groups.append({"family": family, "rows": [item["row"] for item in members],
                       "parameters": [item["parameters"] for item in members]})
    groups.sort(key=lambda group: (group["family"], group["rows"]))
    target = by_row[label["action_row"]]
    target_aliases = [row for group in groups if label["action_row"] in group["rows"]
                      for row, params in zip(group["rows"], group["parameters"])
                      if params != target["parameters"]]
    family_counts = defaultdict(int)
    for item in rows:
        family_counts[str(item["family"])] += 1
    return {"legal_candidates": len(legal), "family_candidate_counts": dict(family_counts), "alias_groups": groups,
            "target_alias_rows": target_aliases, "encoded_features_sha256": digest.hexdigest()}


def reverse_legal_rows(data, label):
    """Move complete legal candidate records within family; return new->old rows."""
    legal = checked_candidate_data(data, label)
    families = defaultdict(list)
    for row in legal:
        families[parameter_row(data, row)[0]].append(row)
    permutation = {new: old for rows in families.values() for new, old in zip(rows, reversed(rows))}
    result = bytearray(data)
    for new, old in permutation.items():
        for offset, width in ((0, FEATURE_WIDTH * 4), (PARAMETER_OFFSET, PARAMETER_WIDTH * 4),
                              (CANDIDATE_BYTES - CAPACITY, 1)):
            result[offset + new * width:offset + (new + 1) * width] = data[offset + old * width:offset + (old + 1) * width]
    return bytes(result), permutation


def prediction_result(prediction, label, *, permutation=None):
    legal = label["legal_rows"]
    target = label["action_row"]
    if permutation is not None:
        target = next(row for row, original in permutation.items() if original == target)
    probabilities = prediction.get("probabilities")
    if (not isinstance(probabilities, list) or len(probabilities) != CAPACITY or
            any(type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1 for value in probabilities)):
        raise ValueError("Native prediction probabilities are invalid")
    legal_set = set(legal)
    selected = prediction.get("row")
    if (type(selected) is not int or selected not in legal_set or
            any(value != 0 for row, value in enumerate(probabilities) if row not in legal_set) or
            abs(sum(probabilities) - 1) > 1e-5):
        raise ValueError("Native prediction violates the exact legal distribution")
    maximum = max(probabilities[row] for row in legal)
    if probabilities[selected] != maximum:
        raise ValueError("Native greedy row is not a probability maximum")
    competitors = [row for row in legal if row != target]
    runner_up = max((probabilities[row] for row in competitors), default=0.0)
    tied = [row for row in legal if probabilities[row] == maximum]
    near_tied = [row for row in competitors if abs(probabilities[row] - probabilities[target]) <= PROBABILITY_TOLERANCE]
    margin = probabilities[target] - runner_up
    return {"target_row": target, "greedy_row": selected,
            "original_greedy_row": permutation[selected] if permutation else selected,
            "target_probability": probabilities[target], "runner_up_probability": runner_up,
            "target_margin": margin,
            "greedy_tie_rows": tied, "target_near_tie_rows": near_tied, "exact_row": selected == target,
            "unique_greedy_target": selected == target and margin > PROBABILITY_TOLERANCE}


def mode_summary(rows, mode):
    families = defaultdict(lambda: {"legal_candidates": 0, "alias_groups": 0, "aliased_rows": 0, "aliased_targets": 0})
    for row in rows:
        result = row[mode]
        for family, count in result["family_candidate_counts"].items():
            families[family]["legal_candidates"] += count
        for group in result["alias_groups"]:
            families[str(group["family"])]["alias_groups"] += 1
            families[str(group["family"])]["aliased_rows"] += len(group["rows"])
        if result["target_alias_rows"]:
            families[str(row["target_family"])]["aliased_targets"] += 1
    return {"examples": len(rows), "legal_candidates": sum(row[mode]["legal_candidates"] for row in rows),
            "alias_groups": sum(len(row[mode]["alias_groups"]) for row in rows),
            "aliased_targets": sum(bool(row[mode]["target_alias_rows"]) for row in rows),
            "by_family": dict(sorted(families.items(), key=lambda item: int(item[0])))}


def check_labels(imitation):
    labels_ref = checked(imitation["dataset"]["labels"])
    manifest_ref = checked(imitation["dataset"]["native_manifest"])
    labels = json.loads(Path(labels_ref["path"]).read_text())["records"]
    if not labels or len(labels) != imitation["dataset"]["example_count"]:
        raise ValueError("Archived human label count differs")
    identities, expected_manifest, tensors = set(), ["openttd-rl-development-v2-imitation-1"], []
    for label in labels:
        identity = (label["game_id"], label["sample_id"])
        if label.get("split") != "train" or identity in identities:
            raise ValueError("Audit requires unique original training examples")
        identities.add(identity)
        pair = {name: checked(label["archived_tensors"][name]) for name in ("observation", "candidate")}
        if Path(pair["observation"]["path"]).stat().st_size != OBSERVATION_BYTES:
            raise ValueError("Archived observation tensor size differs")
        checked_candidate_data(Path(pair["candidate"]["path"]).read_bytes(), label)
        expected_manifest.append("\t".join([label["sample_id"], label["game_id"], pair["observation"]["path"],
            pair["candidate"]["path"], str(label["action_row"]), str(label["action_family"]),
            ",".join(map(str, label["legal_rows"]))]))
        tensors.append(pair)
    if Path(manifest_ref["path"]).read_text().splitlines() != expected_manifest:
        raise ValueError("Native imitation manifest differs from archived human labels")
    return labels, tensors, [labels_ref, manifest_ref]


def audit_predictions(args, labels, rows, report, output, imitation):
    prediction, _ = checked_imitation_run(args.prediction_run, observation_schema=imitation["observation_schema_id"],
                                         financial_features=MODES[1])
    prediction_labels, prediction_tensors, refs = check_labels(prediction)
    refs += [ref for pair in prediction_tensors for ref in pair.values()]
    # New runs archive identical inputs at different paths. Compare semantics/hashes.
    def identity(label):
        return (label["game_id"], label["sample_id"], label["action_row"], label["action_family"],
                label["legal_rows"], {name: value["sha256"] for name, value in label["archived_tensors"].items()})
    if list(map(identity, prediction_labels)) != list(map(identity, labels)):
        raise ValueError("Prediction fit did not use these exact original human examples")
    report["prediction"] = {"run": artifact(args.prediction_run / "run.json"), "model": checked(prediction["model"]),
                            "policy_executable": artifact(args.policy), "financial_features": MODES[1]}
    refs += list(report["prediction"][key] for key in ("run", "model", "policy_executable"))
    client = PolicyClient(args.policy.resolve(), output / "inference.log", "cpu", 20261002,
                          mode="greedy", weights=Path(prediction["model"]["path"]), financial_features=MODES[1])
    try:
        client.check_financial_features()
        with (output / "native-predictions.jsonl").open("x") as predictions:
            for index, (label, row) in enumerate(zip(labels, rows)):
                observation, candidate = (row["tensors"][name]["path"] for name in ("observation", "candidate"))
                client.request("RESET")
                original = client.request(f"{observation}\t{candidate}")
                row["prediction"] = prediction_result(original, label)
                permuted_bytes, permutation = reverse_legal_rows(Path(candidate).read_bytes(), label)
                permuted_path = output / f"{index:04d}-permuted-candidates.bin"
                permuted_path.write_bytes(permuted_bytes)
                row["permuted_tensor"] = artifact(permuted_path)
                client.request("RESET")
                permuted = client.request(f"{observation}\t{permuted_path}")
                row["permuted_prediction"] = prediction_result(permuted, label, permutation=permutation)
                error = max(abs(original["probabilities"][old] - permuted["probabilities"][new])
                            for new, old in permutation.items())
                row["permutation_probability_max_error"] = error
                predictions.write(json.dumps({"sample_id": row["sample_id"], "original": original,
                                              "permuted": permuted, "new_to_original": permutation}) + "\n")
                predictions.flush()
        client.close(); client = None
    finally:
        if client:
            client.abort()
    report["prediction"]["summary"] = {"examples": len(rows),
        "exact_rows": sum(row["prediction"]["exact_row"] for row in rows),
        "unique_greedy_targets": sum(row["prediction"]["unique_greedy_target"] for row in rows),
        "permuted_unique_greedy_targets": sum(row["permuted_prediction"]["unique_greedy_target"] for row in rows),
        "minimum_target_margin": min(row["prediction"]["target_margin"] for row in rows),
        "permuted_minimum_target_margin": min(row["permuted_prediction"]["target_margin"] for row in rows),
        "permutation_probability_max_error": max(row["permutation_probability_max_error"] for row in rows)}
    return refs


def run(args):
    if bool(args.policy) != bool(args.prediction_run):
        raise ValueError("Supply both --policy and --prediction-run for tie-free fit verification")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"kind": "native-v2-action-input-audit", "status": "running", "source": source_identity(),
              "runtime": host(), "device": "cpu", "seed": 20261002, "modes": list(MODES),
              "audit_executable": artifact(args.audit_executable), "rows": [],
              "configuration": {"permutation": "reverse legal records within each action family",
                                "probability_tolerance": PROBABILITY_TOLERANCE,
                                "minimum_unique_target_margin_exclusive": PROBABILITY_TOLERANCE},
              "claim": "Native transformed inputs on archived training states; optional training fit only, no held-out gameplay"}
    write_json(output / "report.json", report)
    started = time.monotonic()
    try:
        report["source_capture"] = capture_source(output / "source")
        imitation, _ = checked_imitation_run(args.imitation_run)
        report["imitation_run"] = artifact(args.imitation_run / "run.json")
        labels, tensors, refs = check_labels(imitation)
        refs += [report["imitation_run"], report["audit_executable"], checked(imitation["model"])]
        for index, (label, pair) in enumerate(zip(labels, tensors)):
            refs += list(pair.values())
            row = {"sample_id": label["sample_id"], "game_id": label["game_id"],
                   "source_command_index": label["source_command_index"], "target_row": label["action_row"],
                   "target_family": label["action_family"], "tensors": pair}
            report["rows"].append(row)
            data = Path(pair["candidate"]["path"]).read_bytes()
            for mode in MODES:
                command = [str(args.audit_executable.resolve()), "--observation", pair["observation"]["path"],
                           "--candidates", pair["candidate"]["path"], "--financial-features", mode]
                native_output = output / f"{index:04d}-{mode}.json"
                with native_output.open("x") as stdout, native_output.with_suffix(".log").open("x") as stderr:
                    subprocess.run(command, stdout=stdout, stderr=stderr, check=True, timeout=60)
                row[mode] = {**native_aliases(json.loads(native_output.read_text()), data, label),
                             "command": command, "native_output": artifact(native_output)}
        report["summary"] = {mode: mode_summary(report["rows"], mode) for mode in MODES}
        if args.prediction_run:
            refs += audit_predictions(args, labels, report["rows"], report, output, imitation)
        for ref in refs:
            checked(ref)
        report["inputs_unchanged"] = True
        if report["summary"][MODES[1]]["alias_groups"]:
            raise ValueError("Distinct legal native actions still alias after action preprocessing")
        if args.prediction_run:
            result = report["prediction"]["summary"]
            if (result["unique_greedy_targets"] != len(labels) or result["permuted_unique_greedy_targets"] != len(labels) or
                    result["permutation_probability_max_error"] > report["configuration"]["probability_tolerance"]):
                raise ValueError("Imitation is not uniquely correct and invariant to candidate row order")
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = repr(error)
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        write_json(output / "report.json", report)
    print(json.dumps(report["summary"], sort_keys=True), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--imitation-run", type=Path, required=True)
    parser.add_argument("--audit-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prediction-run", type=Path)
    parser.add_argument("--policy", type=Path)
    run(parser.parse_args())
