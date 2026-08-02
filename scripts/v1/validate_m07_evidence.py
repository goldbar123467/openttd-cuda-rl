#!/usr/bin/env python3
"""Validate M07 live-learning and exact-recovery gate evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import pathlib
import sys
from typing import Any

import jsonschema

import validate_m07_ppo_contract


class M07EvidenceError(ValueError):
    """M07 evidence is malformed or does not meet G07."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def validate_document(path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    value = validate_m07_ppo_contract.load_strict_json(path)
    schema = validate_m07_ppo_contract.load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(value)
    return value


def verify_self_hash(value: dict[str, Any], field: str) -> None:
    payload = copy.deepcopy(value)
    expected = payload.pop(field)
    observed = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    if observed != expected:
        raise M07EvidenceError(f"{field} mismatch: expected={expected} actual={observed}")


def evaluation_is_eligible(policy: dict[str, Any], random_baseline: dict[str, Any]) -> bool:
    return (
        policy["mean_return"] > random_baseline["mean_return"]
        and policy["mean_delivered_passengers"] > random_baseline["mean_delivered_passengers"]
        and policy["service_successes"] == len(policy["episodes"])
    )


def validate_evaluation(evaluation: dict[str, Any], expected_templates: list[str]) -> None:
    episodes = evaluation["episodes"]
    if [episode["template_id"] for episode in episodes] != expected_templates:
        raise M07EvidenceError("development evaluation template order or partition drifted")
    if not all(math.isfinite(episode["return"]) for episode in episodes):
        raise M07EvidenceError("development evaluation contains a nonfinite return")
    if evaluation["mean_return"] != sum(episode["return"] for episode in episodes) / len(episodes):
        raise M07EvidenceError("development mean return is not source-derived")
    if evaluation["mean_delivered_passengers"] != sum(
        episode["delivered_passengers"] for episode in episodes
    ) / len(episodes):
        raise M07EvidenceError("development mean passenger count is not source-derived")
    successes = sum(
        episode["delivered_passengers"] > 0 and episode["income"] > 0 for episode in episodes
    )
    if evaluation["service_successes"] != successes:
        raise M07EvidenceError("development service-success count is not source-derived")


def validate_live(run: dict[str, Any]) -> None:
    verify_self_hash(run, "manifest_sha256")
    expected_compatibility = {
        "m06_source_identity": "98693ab0595fb26612079683a192a12f7bce6bb4cb25a7edf895244c50c568a2",
        "openttd_executable_sha256": "765c108213bfbb23df2712956acb9bbf6bbb5b0a1d446b0ec154a94fbf41876c",
        "ppo": "8649da85cee2914d423a7ae8f1bcff0fa6a1c7d749bd04232976fbad6df518c0",
        "trainer_executable_sha256": "c45a6589a47f175f041bf151339e38aad79ede207aaf3d4fc107e5d810f4f31f",
    }
    if run["compatibility"] != expected_compatibility:
        raise M07EvidenceError("live campaign compatibility identity drifted")
    configuration = run["configuration"]
    if configuration["updates"] < 64 or configuration["evaluation_steps"] < 128:
        raise M07EvidenceError("G07 live campaign is shorter than the accepted soak/evaluation")
    updates = run["training"]["updates"]
    if len(updates) != configuration["updates"]:
        raise M07EvidenceError("live update record count drifted")
    samples_per_update = configuration["rollout_length"] * configuration["environment_count"]
    for index, update in enumerate(updates, 1):
        if update["update"] != index or update["samples"] != index * samples_per_update:
            raise M07EvidenceError("live update/sample counters are discontinuous")
        if not all(math.isfinite(value) for key, value in update.items() if key not in {"update", "samples"}):
            raise M07EvidenceError("live training metric is nonfinite")
    expected_candidate_updates = list(range(16, configuration["updates"] + 1, 16))
    if expected_candidate_updates[-1] != configuration["updates"]:
        expected_candidate_updates.append(configuration["updates"])
    candidates = run["evaluation"]["candidates"]
    if [candidate["update"] for candidate in candidates] != expected_candidate_updates:
        raise M07EvidenceError("development checkpoint cadence drifted")
    expected_templates = ["m02-template-05", "m02-template-06"]
    random_baseline = run["evaluation"]["random"]
    validate_evaluation(random_baseline, expected_templates)
    for candidate in candidates:
        validate_evaluation(candidate["evaluation"], expected_templates)
        expected_eligible = evaluation_is_eligible(candidate["evaluation"], random_baseline)
        if candidate["eligible"] != expected_eligible:
            raise M07EvidenceError("candidate eligibility is not source-derived")
        if candidate["checkpoint"]["path"] != f"checkpoints/{candidate['checkpoint']['id']}":
            raise M07EvidenceError("candidate checkpoint path is not content addressed")
    eligible = [candidate for candidate in candidates if candidate["eligible"]]
    if not eligible:
        raise M07EvidenceError("no development checkpoint improved over random")
    selected = max(
        eligible,
        key=lambda candidate: (
            candidate["evaluation"]["mean_return"],
            candidate["evaluation"]["mean_delivered_passengers"],
            -candidate["update"],
        ),
    )
    evaluation = run["evaluation"]
    if (
        run["status"] != "PASS"
        or not evaluation["improved_over_random"]
        or evaluation["selected_update"] != selected["update"]
        or evaluation["selected"] != selected["evaluation"]
        or run["checkpoint"] != selected["checkpoint"]
    ):
        raise M07EvidenceError("selected development checkpoint/result is inconsistent")
    if run["scenario_partitions"]["final_evaluation_accessed"]:
        raise M07EvidenceError("final-evaluation partition was exposed during M07")


def validate_recovery(report: dict[str, Any]) -> None:
    verify_self_hash(report, "report_sha256")
    if report["recovered_checkpoint_id"] != report["uninterrupted_checkpoint_id"]:
        raise M07EvidenceError("recovered and uninterrupted semantic checkpoint identities differ")
    if report["recovered_update"] != report["uninterrupted_update"]:
        raise M07EvidenceError("recovered and uninterrupted update metrics differ")
    for update_name in ("first_update", "recovered_update", "uninterrupted_update"):
        if not all(
            math.isfinite(value)
            for key, value in report[update_name].items()
            if key not in {"update", "samples"}
        ):
            raise M07EvidenceError(f"{update_name} contains a nonfinite metric")
    if report["numerical_failure"] != {
        "diagnostic": report["numerical_failure"]["diagnostic"],
        "normal_checkpoint_published": False,
        "service_terminated": True,
    }:
        raise M07EvidenceError("numerical fault did not terminate safely with diagnostic-only evidence")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", type=pathlib.Path, required=True)
    parser.add_argument("--live-schema", type=pathlib.Path, required=True)
    parser.add_argument("--recovery", type=pathlib.Path, required=True)
    parser.add_argument("--recovery-schema", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        live = validate_document(args.live, args.live_schema)
        recovery = validate_document(args.recovery, args.recovery_schema)
        validate_live(live)
        validate_recovery(recovery)
    except (M07EvidenceError, OSError, jsonschema.ValidationError, ValueError) as exc:
        print(f"M07_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M07_EVIDENCE=PASS "
        f"updates={live['configuration']['updates']} steps={live['training']['updates'][-1]['samples']} "
        f"selected_update={live['evaluation']['selected_update']} checkpoint={live['checkpoint']['id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
