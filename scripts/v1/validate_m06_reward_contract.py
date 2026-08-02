#!/usr/bin/env python3
"""Strict schema, identity, and semantic validation for the M06 foundation."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import sys
from typing import Any

import jsonschema


class M06RewardContractError(ValueError):
    """The M06 reward/trajectory foundation is malformed or inconsistent."""


def load_strict_json(path: pathlib.Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise M06RewardContractError(f"{path}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise M06RewardContractError(f"{path}: UTF-8 BOM is forbidden")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                M06RewardContractError(f"{path}: invalid JSON constant {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M06RewardContractError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise M06RewardContractError(f"{path}: top level must be an object")
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def compatibility_sha256(contract: dict[str, Any]) -> str:
    payload = copy.deepcopy(contract)
    payload["identity"].pop("compatibility_sha256", None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def validate_semantics(contract: dict[str, Any]) -> None:
    expected_candidates = [f"POS-{number:03d}" for number in range(1, 9)] + [
        f"NEG-{number:03d}" for number in range(1, 11)
    ]
    candidates = contract["candidate_dispositions"]
    if [item["candidate_id"] for item in candidates] != expected_candidates:
        raise M06RewardContractError("reward candidate identities or order drifted")
    if any(item["requirement"] != "REW-001" for item in candidates[:8]) or any(
        item["requirement"] != "REW-002" for item in candidates[8:]
    ):
        raise M06RewardContractError("positive and penalty candidates do not map to REW-001/REW-002")

    expected_components = [
        ("RC-001", 0, "passenger_delivery", "delivered_passengers_delta", 0, 128, 1, 16),
        ("RC-002", 1, "operating_profit", "operating_profit_delta", -16384, 16384, 1, 4096),
        ("RC-003", 2, "capital_spend", "capital_spend", 0, 65536, -1, 16384),
        ("RC-004", 3, "noop", "noop", 0, 1, -1, 64),
        ("RC-005", 4, "native_rejection", "native_rejected", 0, 1, -1, 4),
        ("RC-006", 5, "idle_bus_ticks", "idle_bus_ticks", 0, 1024, -1, 65536),
        ("RC-007", 6, "vehicle_loss", "vehicle_loss_count", 0, 8, -2, 1),
        ("RC-008", 7, "bankruptcy", "bankruptcy", 0, 1, -8, 1),
    ]
    components = contract["reward"]["components"]
    observed_components = [
        (
            item["component_id"],
            item["order"],
            item["name"],
            item["raw_field"],
            item["raw_min"],
            item["raw_max"],
            item["coefficient_numerator"],
            item["coefficient_denominator"],
        )
        for item in components
    ]
    if observed_components != expected_components:
        raise M06RewardContractError("reward component identities, transforms, or order drifted")
    included_components = [
        item["component_id"] for item in candidates if item["disposition"] == "INCLUDED"
    ]
    if sorted(included_components) != [f"RC-{number:03d}" for number in range(1, 9)]:
        raise M06RewardContractError("included candidate mapping must cover every reward component exactly once")
    for item in candidates:
        if (item["disposition"] == "INCLUDED") != (item["component_id"] is not None):
            raise M06RewardContractError(f"candidate disposition/component mismatch: {item['candidate_id']}")
    for item in components:
        if item["raw_min"] > item["raw_max"]:
            raise M06RewardContractError(f"raw component bounds are reversed: {item['component_id']}")
        endpoints = sorted(
            raw * item["coefficient_numerator"] / item["coefficient_denominator"]
            for raw in (item["raw_min"], item["raw_max"])
        )
        if endpoints != [item["weighted_min"], item["weighted_max"]]:
            raise M06RewardContractError(f"weighted bounds disagree with transform: {item['component_id']}")

    expected_reasons = [
        "NONE",
        "BANKRUPTCY",
        "SOLVED",
        "ACTION_HORIZON",
        "TICK_HORIZON",
        "ACTION_AND_TICK_HORIZON",
        "USER_CANCELLED",
        "INVALID_STATE",
        "WORKER_CRASH",
        "TIMEOUT",
        "INTEGRATION_FAILURE",
        "NONFINITE",
        "IO_FAILURE",
    ]
    reasons = contract["termination"]["reasons"]
    if [item["name"] for item in reasons] != expected_reasons:
        raise M06RewardContractError("termination reason identities or order drifted")
    if contract["termination"]["priority"] != [
        "FAILURE", "BANKRUPTCY", "SOLVED", "USER_CANCELLED", "ACTION_AND_TICK_HORIZON",
        "ACTION_HORIZON", "TICK_HORIZON", "NONE",
    ]:
        raise M06RewardContractError("termination priority drifted")
    for item in reasons:
        if item["terminal"] and item["truncated"]:
            raise M06RewardContractError(f"reason cannot be terminal and truncated: {item['name']}")
        if item["kind"] == "FAILURE" and (item["terminal"] or item["truncated"] or item["bootstrap"] or item["trainable"]):
            raise M06RewardContractError(f"failure reason has ordinary transition semantics: {item['name']}")
        if item["kind"] == "TERMINAL" and (not item["terminal"] or item["truncated"] or item["bootstrap"] or not item["trainable"]):
            raise M06RewardContractError(f"terminal reason semantics drifted: {item['name']}")
        if item["kind"] == "TRUNCATED" and (item["terminal"] or not item["truncated"] or not item["bootstrap"] or not item["trainable"]):
            raise M06RewardContractError(f"horizon truncation semantics drifted: {item['name']}")

    observation = contract["trajectory"]["observation_blob"]
    if (observation["structured_values"] + observation["spatial_values"]) * 4 != observation["byte_length"]:
        raise M06RewardContractError("M04 observation blob shape and byte count disagree")
    rollout = contract["rollout"]
    if rollout["maximum_observation_blobs_per_segment"] != rollout["maximum_transitions_per_segment"] + 1:
        raise M06RewardContractError("rollout must allow one more observation than transitions")
    if rollout["maximum_observation_blob_bytes"] != observation["byte_length"] * rollout["maximum_observation_blobs_per_segment"]:
        raise M06RewardContractError("rollout observation byte bound drifted")
    if rollout["maximum_total_segment_bytes"] != rollout["maximum_observation_blob_bytes"] + rollout["maximum_metadata_bytes"]:
        raise M06RewardContractError("rollout total byte bound drifted")

    expected_requirements = {
        "SCOPE-025", "SCOPE-026", "LIFE-008", "LIFE-009", "REW-001", "REW-002", "REW-003",
        "REW-004", "REW-005", "REW-006", "REW-007", "TEST-004", "TEST-007", "TEST-008",
    }
    if set(contract["requirements"]) != expected_requirements:
        raise M06RewardContractError("M06 requirement ownership inventory drifted")


def validate(contract_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    contract = load_strict_json(contract_path)
    schema = load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(contract)
    observed_schema = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    if observed_schema != contract["identity"]["schema_sha256"]:
        raise M06RewardContractError(
            f"schema digest mismatch: expected={contract['identity']['schema_sha256']} actual={observed_schema}"
        )
    observed_contract = compatibility_sha256(contract)
    if observed_contract != contract["identity"]["compatibility_sha256"]:
        raise M06RewardContractError(
            f"compatibility digest mismatch: expected={contract['identity']['compatibility_sha256']} actual={observed_contract}"
        )
    validate_semantics(contract)
    return contract


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=pathlib.Path)
    parser.add_argument("schema", type=pathlib.Path)
    args = parser.parse_args()
    try:
        contract = validate(args.contract, args.schema)
    except (M06RewardContractError, OSError, jsonschema.ValidationError) as exc:
        print(f"M06_REWARD_CONTRACT=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M06_REWARD_CONTRACT=PASS "
        f"compatibility_sha256={contract['identity']['compatibility_sha256']} "
        f"candidates={len(contract['candidate_dispositions'])} "
        f"components={len(contract['reward']['components'])} "
        f"termination_reasons={len(contract['termination']['reasons'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
