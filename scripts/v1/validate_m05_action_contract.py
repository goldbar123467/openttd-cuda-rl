#!/usr/bin/env python3
"""Strict schema, identity, and semantic validation for the M05 action contract."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import sys
from typing import Any

import jsonschema


class M05ActionContractError(ValueError):
    """The frozen M05 action contract is malformed or inconsistent."""


def load_strict_json(path: pathlib.Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise M05ActionContractError(f"{path}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise M05ActionContractError(f"{path}: UTF-8 BOM is forbidden")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                M05ActionContractError(f"{path}: invalid JSON constant {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M05ActionContractError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise M05ActionContractError(f"{path}: top level must be an object")
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def compatibility_sha256(contract: dict[str, Any]) -> str:
    payload = copy.deepcopy(contract)
    payload["identity"].pop("compatibility_sha256", None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def validate_semantics(contract: dict[str, Any]) -> None:
    expected = [
        ("FAM-001", "WAIT", 0, 0),
        ("FAM-002", "SELECT_TOWNS", 1, 2),
        ("FAM-003", "BUILD_ROAD_CONNECTOR", 3, 3),
        ("FAM-004", "BUILD_BUS_STOP", 4, 11),
        ("FAM-005", "BUILD_ROAD_DEPOT", 12, 15),
        ("FAM-006", "BUY_BUS", 16, 16),
        ("FAM-007", "ASSIGN_ROUTE", 17, 24),
        ("FAM-008", "SET_RUNNING", 25, 32),
        ("FAM-009", "SET_STOPPED", 33, 40),
    ]
    observed = [
        (item["family_id"], item["name"], item["index_start"], item["index_end"])
        for item in contract["families"]
    ]
    if observed != expected:
        raise M05ActionContractError("action family identities or ranges drifted")
    indices = [
        index
        for family in contract["families"]
        for index in range(family["index_start"], family["index_end"] + 1)
    ]
    if indices != list(range(41)):
        raise M05ActionContractError("action ranges must cover the exact ordered range 0..40")
    for family in contract["families"]:
        if family["count"] != family["index_end"] - family["index_start"] + 1:
            raise M05ActionContractError(f"family count disagrees with range: {family['family_id']}")
    slots = contract["slots"]
    if {key: value["maximum"] for key, value in slots.items()} != {
        "town": 2,
        "vehicle": 8,
        "station_site": 2,
        "depot_site": 1,
    }:
        raise M05ActionContractError("slot maxima drifted")
    dispositions = {item["candidate"]: item for item in contract["dispositions"]}
    if set(dispositions) != {"sell-vehicle", "remove-infrastructure", "loan-take-repay"}:
        raise M05ActionContractError("sell/removal/loan disposition inventory drifted")
    covered = {requirement for item in dispositions.values() for requirement in item["requirements"]}
    if covered != {"ACT-010", "ACT-011", "ACT-012"}:
        raise M05ActionContractError("dispositions do not cover ACT-010 through ACT-012 exactly")
    outcomes = [item["name"] for item in contract["outcomes"]]
    if outcomes != ["SUCCESS", "NO_OP", "STALE_REJECTED", "ILLEGAL_INPUT", "NATIVE_REJECTED", "INTEGRATION_FAILURE"]:
        raise M05ActionContractError("outcome order or inventory drifted")
    if contract["mask"]["shape"] != [contract["representation"]["action_count"]]:
        raise M05ActionContractError("mask shape and action count disagree")
    if contract["boundary"]["fixed_tick_cost"] * contract["boundary"]["episode_action_budget"] != contract["boundary"]["episode_tick_budget"]:
        raise M05ActionContractError("action and tick horizons do not close exactly")


def validate(contract_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    contract = load_strict_json(contract_path)
    schema = load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(contract)
    observed_schema = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    if observed_schema != contract["identity"]["schema_sha256"]:
        raise M05ActionContractError(
            f"schema digest mismatch: expected={contract['identity']['schema_sha256']} actual={observed_schema}"
        )
    observed_contract = compatibility_sha256(contract)
    if observed_contract != contract["identity"]["compatibility_sha256"]:
        raise M05ActionContractError(
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
    except (M05ActionContractError, OSError, jsonschema.ValidationError) as exc:
        print(f"M05_ACTION_CONTRACT=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M05_ACTION_CONTRACT=PASS "
        f"compatibility_sha256={contract['identity']['compatibility_sha256']} "
        f"actions={contract['representation']['action_count']} families={len(contract['families'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
