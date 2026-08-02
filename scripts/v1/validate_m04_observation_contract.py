#!/usr/bin/env python3
"""Strict schema, identity, and cross-field validation for the M04 observation."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import sys
from typing import Any

import jsonschema


class M04ObservationContractError(ValueError):
    """The frozen M04 observation contract is malformed or inconsistent."""


def load_strict_json(path: pathlib.Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise M04ObservationContractError(f"{path}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise M04ObservationContractError(f"{path}: UTF-8 BOM is forbidden")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                M04ObservationContractError(f"{path}: invalid JSON constant {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M04ObservationContractError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise M04ObservationContractError(f"{path}: top level must be an object")
    return value


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
    structured = contract["tensors"]["structured"]
    fields = structured["fields"]
    if [item["index"] for item in fields] != list(range(256)):
        raise M04ObservationContractError("structured indices must be the exact ordered range 0..255")
    names = [item["name"] for item in fields]
    if len(set(names)) != len(names):
        raise M04ObservationContractError("structured field names must be unique")

    spatial = contract["tensors"]["spatial"]
    channels = spatial["channels"]
    if [item["index"] for item in channels] != list(range(32)):
        raise M04ObservationContractError("spatial indices must be the exact ordered range 0..31")
    channel_names = [item["name"] for item in channels]
    if len(set(channel_names)) != len(channel_names):
        raise M04ObservationContractError("spatial channel names must be unique")

    expected_groups = (
        ["global"] * 28
        + ["town"] * 20
        + ["vehicle"] * 80
        + ["station"] * 80
        + ["route"] * 48
    )
    if [item["group"] for item in fields] != expected_groups:
        raise M04ObservationContractError("structured group layout is not 28/20/80/80/48")

    slots = contract["slots"]
    if {name: value["maximum"] for name, value in slots.items()} != {
        "town": 2,
        "vehicle": 8,
        "station": 16,
        "route": 8,
    }:
        raise M04ObservationContractError("entity slot maxima drifted")

    registry = contract["candidate_registry"]
    candidate_ids = [item["id"] for item in registry]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise M04ObservationContractError("candidate registry IDs must be unique")
    covered = {requirement for item in registry for requirement in item["requirements"]}
    required = {f"OBS-{index:03d}" for index in range(2, 14)}
    if not required <= covered:
        raise M04ObservationContractError(
            f"candidate registry misses requirements {sorted(required - covered)}"
        )
    for item in registry:
        if item["disposition"] != "INCLUDED" and len(item["rationale"]) < 30:
            raise M04ObservationContractError(
                f"excluded/deferred candidate rationale is too short: {item['id']}"
            )

    consumers = contract["shared_preprocessing"]["consumers"]
    if consumers != [
        "trainer",
        "evaluator",
        "onnx-runtime",
        "in-game-controller",
        "m04-bridge-oracle",
    ]:
        raise M04ObservationContractError("shared consumer inventory or order drifted")
    if contract["boundary"]["message_type"] != 8:
        raise M04ObservationContractError("OBSERVE must extend M03 with message type 8")


def validate(contract_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    contract = load_strict_json(contract_path)
    schema = load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(contract)
    observed_schema = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    expected_schema = contract["identity"]["schema_sha256"]
    if observed_schema != expected_schema:
        raise M04ObservationContractError(
            f"schema digest mismatch: expected={expected_schema} actual={observed_schema}"
        )
    observed_contract = compatibility_sha256(contract)
    expected_contract = contract["identity"]["compatibility_sha256"]
    if observed_contract != expected_contract:
        raise M04ObservationContractError(
            f"compatibility digest mismatch: expected={expected_contract} actual={observed_contract}"
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
    except (M04ObservationContractError, OSError, jsonschema.ValidationError) as exc:
        print(f"M04_OBSERVATION_CONTRACT=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M04_OBSERVATION_CONTRACT=PASS "
        f"compatibility_sha256={contract['identity']['compatibility_sha256']} "
        f"structured=256 spatial=32x32x32 candidates={len(contract['candidate_registry'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
