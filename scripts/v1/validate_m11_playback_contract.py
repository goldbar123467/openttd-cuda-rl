#!/usr/bin/env python3
"""Validate the frozen M11 normal-game neural playback contract."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import sys
from typing import Any

import jsonschema

import validate_m07_ppo_contract


class M11ContractError(ValueError):
    """The M11 playback contract or configuration is invalid."""


EXPECTED_COMPATIBILITY = "3f331f7852b0174714de30b8ab6015178d7e01d4691832f8af2085d32bb01e42"
ACCEPTED_PACKAGE_ID = "0334e6a9da8d5b87d48ecdcd859dc3a5be6b1f7913511bf3336f8d3cf1feeeb9"
EXPECTED_REQUIREMENTS = {
    "LIFE-015", "LIFE-016", "STACK-001", "STACK-005", "STACK-010",
    "MODEL-010", "MODEL-011", "MODEL-012", "MODEL-013", "MODEL-014",
    "MODEL-015", "MODEL-016", "MODEL-017", "MODEL-018",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def compatibility_sha256(contract: dict[str, Any]) -> str:
    payload = copy.deepcopy(contract)
    payload["identity"].pop("compatibility_sha256", None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M11ContractError(message)


def validate(contract_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    contract = validate_m07_ppo_contract.load_strict_json(contract_path)
    schema = validate_m07_ppo_contract.load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(contract)
    require(hashlib.sha256(schema_path.read_bytes()).hexdigest() == contract["identity"]["schema_sha256"], "M11 contract schema identity drifted")
    require(compatibility_sha256(contract) == contract["identity"]["compatibility_sha256"] == EXPECTED_COMPATIBILITY, "M11 compatibility identity drifted")

    root = contract_path.resolve().parents[2]
    config_schema = root / contract["configuration"]["schema_path"]
    require(hashlib.sha256(config_schema.read_bytes()).hexdigest() == contract["configuration"]["schema_sha256"], "M11 playback config schema identity drifted")
    dependencies = {
        "observation": ("config/v1/m04-observation-contract.json", "7f8a46af1fe2a2c23e755c71b3bc2d04c9a0d057c573e901e5c9ed9178ca13eb"),
        "action_and_mask": ("config/v1/m05-action-contract.json", "215c7d3ebeea97f1629debee4a2d10301838ccfd3085e4828685591677b58536"),
        "reward_trajectory": ("config/v1/m06-reward-trajectory-contract.json", "9d8f9c2fc6074d899fa3b0047c55e3fb15cc5c17cddeaceaa1fd5389e53c8c9e"),
        "evaluation": ("config/v1/m09-evaluation-contract.json", "c64c9876c1f6cf46dcc2642bd4628ed45f4659d1866a047d4e51def60dab9a5e"),
        "model_package": ("config/v1/m10-model-package-contract.json", "e77edf9be1343970a55becbb05da96a6b9a17edbd8df2c7999701dd8fa1f33b6"),
    }
    for name, (relative, expected) in dependencies.items():
        observed = validate_m07_ppo_contract.load_strict_json(root / relative)["identity"]["compatibility_sha256"]
        require(observed == expected == contract["compatibility"][name], f"{name} compatibility drifted")
    require(contract["accepted_package"]["package_id"] == ACCEPTED_PACKAGE_ID, "accepted playback package drifted")
    interval = contract["controller"]["interval"]
    require(interval == {"minimum_ticks": 128, "maximum_ticks": 1024, "multiple_ticks": 128, "first_action": "tick-zero-before-normal-game-loop"}, "M11 inference interval boundary drifted")
    require(set(contract["requirements"]) == EXPECTED_REQUIREMENTS and len(contract["requirements"]) == len(EXPECTED_REQUIREMENTS), "M11 requirement ownership drifted")
    required_inspection = {"current_action", "confidence", "value", "legal_action_count", "reward_relevant_state", "route_target", "model_name", "model_version"}
    require(set(contract["inspection"]["required_fields"]) == required_inspection, "M11 inspection field inventory drifted")
    require(contract["failure_policy"]["fallback"] == "forbidden-no-policy-substitution", "M11 fail-closed policy drifted")
    return contract


def validate_playback_config(config_path: pathlib.Path, schema_path: pathlib.Path, contract: dict[str, Any]) -> dict[str, Any]:
    config = validate_m07_ppo_contract.load_strict_json(config_path)
    schema = validate_m07_ppo_contract.load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(config)
    require(config["contract_sha256"] == contract["identity"]["compatibility_sha256"], "playback configuration compatibility drifted")
    for name in ("package_path", "scenario_instance"):
        require(pathlib.Path(config[name]).is_absolute(), f"{name} is not absolute")
    for section, name in (("logging", "path"), ("inspection", "report_path")):
        require(pathlib.Path(config[section][name]).is_absolute(), f"{section}.{name} is not absolute")
    interval = config["inference"]["interval_ticks"]
    frozen = contract["controller"]["interval"]
    require(frozen["minimum_ticks"] <= interval <= frozen["maximum_ticks"] and interval % frozen["multiple_ticks"] == 0, "playback interval is outside the frozen safe boundary")
    return config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=pathlib.Path)
    parser.add_argument("schema", type=pathlib.Path)
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--config-schema", type=pathlib.Path)
    args = parser.parse_args()
    try:
        contract = validate(args.contract, args.schema)
        if (args.config is not None or args.config_schema is not None):
            require(args.config is not None and args.config_schema is not None, "both --config and --config-schema are required")
            validate_playback_config(args.config, args.config_schema, contract)
    except (M11ContractError, OSError, ValueError, jsonschema.ValidationError) as exc:
        print(f"M11_PLAYBACK_CONTRACT=FAIL {exc}", file=sys.stderr)
        return 1
    print(f"M11_PLAYBACK_CONTRACT=PASS compatibility_sha256={contract['identity']['compatibility_sha256']} package_id={contract['accepted_package']['package_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
