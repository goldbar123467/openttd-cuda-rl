#!/usr/bin/env python3
"""Validate the frozen M02 passenger-bus scenario and reset contract."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import sys
from typing import Any

import jsonschema


class M02ScenarioContractError(ValueError):
    """The scenario contract is malformed, inconsistent, or has identity drift."""


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise M02ScenarioContractError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_strict_json(path: pathlib.Path) -> Any:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise M02ScenarioContractError(f"UTF-8 BOM is forbidden: {path}")
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                M02ScenarioContractError(f"nonstandard JSON constant: {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise M02ScenarioContractError(f"invalid JSON in {path}: {exc}") from exc


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def compatibility_sha256(contract: dict[str, Any]) -> str:
    payload = copy.deepcopy(contract)
    payload["identity"].pop("compatibility_sha256", None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def validate_semantics(contract: dict[str, Any]) -> None:
    company = contract["company"]
    if company["initial_balance"] != company["initial_loan"]:
        raise M02ScenarioContractError("initial balance must equal the engine-created initial loan")
    if company["initial_loan"] > company["maximum_loan"]:
        raise M02ScenarioContractError("initial loan exceeds maximum loan")
    if company["maximum_loan"] % company["loan_interval"] != 0:
        raise M02ScenarioContractError("maximum loan is not aligned to the loan interval")

    corpus = contract["corpus_policy"]
    split_count = sum(
        corpus[key]
        for key in (
            "training_templates",
            "development_templates",
            "final_evaluation_templates",
        )
    )
    if split_count != corpus["template_count"]:
        raise M02ScenarioContractError(
            f"template split count mismatch: expected={corpus['template_count']} actual={split_count}"
        )

    if contract["map"]["width"] != 1 << contract["settings"]["game_creation.map_x"]:
        raise M02ScenarioContractError("map width disagrees with game_creation.map_x")
    if contract["map"]["height"] != 1 << contract["settings"]["game_creation.map_y"]:
        raise M02ScenarioContractError("map height disagrees with game_creation.map_y")
    if contract["episode"]["calendar_day_horizon_ceiling"] != (
        contract["episode"]["tick_horizon"] + contract["time"]["ticks_per_economy_day"] - 1
    ) // contract["time"]["ticks_per_economy_day"]:
        raise M02ScenarioContractError("calendar-day horizon ceiling disagrees with tick horizon")

    reachable = set(contract["transport_scope"]["agent_reachable"])
    forbidden = set(contract["transport_scope"]["forbidden"])
    if reachable & forbidden:
        raise M02ScenarioContractError(
            f"reachable and forbidden transport scope overlaps: {sorted(reachable & forbidden)}"
        )
    projection = contract["reset_contract"]["projection_fields"]
    if projection != sorted(set(projection)):
        raise M02ScenarioContractError("reset projection fields must be sorted and unique")


def validate(contract_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    contract = load_strict_json(contract_path)
    schema = load_strict_json(schema_path)
    if not isinstance(contract, dict) or not isinstance(schema, dict):
        raise M02ScenarioContractError("contract and schema must be JSON objects")
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(contract)
    except jsonschema.SchemaError as exc:
        raise M02ScenarioContractError(f"invalid scenario contract schema: {exc.message}") from exc
    except jsonschema.ValidationError as exc:
        location = "/".join(str(item) for item in exc.absolute_path) or "<root>"
        raise M02ScenarioContractError(
            f"scenario contract schema validation failed at {location}: {exc.message}"
        ) from exc

    observed_schema_sha256 = sha256_file(schema_path)
    expected_schema_sha256 = contract["identity"]["schema_sha256"]
    if observed_schema_sha256 != expected_schema_sha256:
        raise M02ScenarioContractError(
            "scenario contract schema digest mismatch: "
            f"expected={expected_schema_sha256} actual={observed_schema_sha256}"
        )
    validate_semantics(contract)
    observed_compatibility = compatibility_sha256(contract)
    expected_compatibility = contract["identity"]["compatibility_sha256"]
    if observed_compatibility != expected_compatibility:
        raise M02ScenarioContractError(
            "scenario compatibility digest mismatch: "
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
                raise M02ScenarioContractError("contract must be a JSON object")
            print(f"schema_sha256={sha256_file(args.schema)}")
            print(f"compatibility_sha256={compatibility_sha256(contract)}")
            return 0
        contract = validate(args.contract, args.schema)
    except (OSError, M02ScenarioContractError) as exc:
        print(f"M02_SCENARIO_CONTRACT=FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "M02_SCENARIO_CONTRACT=PASS "
        f"compatibility_sha256={contract['identity']['compatibility_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
