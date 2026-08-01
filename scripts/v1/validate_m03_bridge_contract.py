#!/usr/bin/env python3
"""Validate the frozen M03 synchronized environment-bridge contract."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import sys
from typing import Any

import jsonschema


class M03BridgeContractError(ValueError):
    """The bridge contract is malformed, inconsistent, or has identity drift."""


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise M03BridgeContractError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_strict_json(path: pathlib.Path) -> Any:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise M03BridgeContractError(f"UTF-8 BOM is forbidden: {path}")
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                M03BridgeContractError(f"nonstandard JSON constant: {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise M03BridgeContractError(f"invalid JSON in {path}: {exc}") from exc


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def compatibility_sha256(contract: dict[str, Any]) -> str:
    payload = copy.deepcopy(contract)
    payload["identity"].pop("compatibility_sha256", None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def validate_semantics(contract: dict[str, Any]) -> None:
    framing = contract["framing"]
    if framing["header_bytes"] != 56:
        raise M03BridgeContractError("wire header must remain exactly 56 bytes")
    if len(framing["header_layout"]) != 12:
        raise M03BridgeContractError("wire header layout must contain exactly 12 fields")

    operations = contract["operations"]
    message_types = [operation["message_type"] for operation in operations.values()]
    if sorted(message_types) != list(range(1, 8)):
        raise M03BridgeContractError("operation message types must be the unique range 1..7")

    lifecycle = contract["lifecycle"]
    states = set(lifecycle["states"])
    if lifecycle["initial_state"] not in states or {"FAILED", "CLOSED"} - states:
        raise M03BridgeContractError("lifecycle state inventory is incomplete")
    for name, operation in operations.items():
        unknown = set(operation["valid_states"]) - states
        if unknown:
            raise M03BridgeContractError(
                f"operation {name} references unknown lifecycle states: {sorted(unknown)}"
            )

    scheduler = contract["scheduler"]
    interval = scheduler["v1_reference_action_interval_ticks"]
    if interval != scheduler["default_action_interval_ticks"]:
        raise M03BridgeContractError("reference and default action intervals differ")
    if not scheduler["minimum_action_interval_ticks"] <= interval <= scheduler[
        "maximum_action_interval_ticks"
    ]:
        raise M03BridgeContractError("reference action interval is outside declared bounds")
    if scheduler["action_horizon"] * interval != scheduler["tick_horizon"]:
        raise M03BridgeContractError(
            "action horizon times reference interval must equal the tick horizon"
        )

    actions = contract["m03_test_actions"]
    if actions["policy_action_registry"]:
        raise M03BridgeContractError("M03 integration actions must not become policy actions")
    ids = [action["id"] for action in actions["actions"]]
    if ids != [0, 1] or len(ids) != len(set(ids)):
        raise M03BridgeContractError("M03 integration action IDs must be exactly [0, 1]")

    snapshot_fields = contract["snapshot"]["fields"]
    if snapshot_fields != sorted(set(snapshot_fields)):
        raise M03BridgeContractError("snapshot fields must be sorted and unique")

    error_codes = contract["error_codes"]
    if error_codes != sorted(set(error_codes)):
        raise M03BridgeContractError("error codes must be sorted and unique")


def validate(contract_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    contract = load_strict_json(contract_path)
    schema = load_strict_json(schema_path)
    if not isinstance(contract, dict) or not isinstance(schema, dict):
        raise M03BridgeContractError("contract and schema must be JSON objects")
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(contract)
    except jsonschema.SchemaError as exc:
        raise M03BridgeContractError(f"invalid bridge contract schema: {exc.message}") from exc
    except jsonschema.ValidationError as exc:
        location = "/".join(str(item) for item in exc.absolute_path) or "<root>"
        raise M03BridgeContractError(
            f"bridge contract schema validation failed at {location}: {exc.message}"
        ) from exc

    observed_schema_sha256 = sha256_file(schema_path)
    expected_schema_sha256 = contract["identity"]["schema_sha256"]
    if observed_schema_sha256 != expected_schema_sha256:
        raise M03BridgeContractError(
            "bridge contract schema digest mismatch: "
            f"expected={expected_schema_sha256} actual={observed_schema_sha256}"
        )
    validate_semantics(contract)
    observed_compatibility = compatibility_sha256(contract)
    expected_compatibility = contract["identity"]["compatibility_sha256"]
    if observed_compatibility != expected_compatibility:
        raise M03BridgeContractError(
            "bridge compatibility digest mismatch: "
            f"expected={expected_compatibility} actual={observed_compatibility}"
        )
    return contract


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True, type=pathlib.Path)
    parser.add_argument("--schema", required=True, type=pathlib.Path)
    parser.add_argument("--print-computed-identities", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.print_computed_identities:
            contract = load_strict_json(args.contract)
            if not isinstance(contract, dict):
                raise M03BridgeContractError("contract must be a JSON object")
            print(f"schema_sha256={sha256_file(args.schema)}")
            print(f"compatibility_sha256={compatibility_sha256(contract)}")
            return 0
        contract = validate(args.contract, args.schema)
    except (OSError, M03BridgeContractError) as exc:
        print(f"M03_BRIDGE_CONTRACT=FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "M03_BRIDGE_CONTRACT=PASS "
        f"compatibility_sha256={contract['identity']['compatibility_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
