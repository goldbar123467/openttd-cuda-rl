#!/usr/bin/env python3
"""Strict schema, identity, dependency, and semantic validation for M08."""

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


class M08ContractError(ValueError):
    """The M08 architecture/CUDA contract is invalid."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def compatibility_sha256(contract: dict[str, Any]) -> str:
    payload = copy.deepcopy(contract)
    payload["identity"].pop("compatibility_sha256", None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def validate(contract_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    contract = validate_m07_ppo_contract.load_strict_json(contract_path)
    schema = validate_m07_ppo_contract.load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(contract)
    if hashlib.sha256(schema_path.read_bytes()).hexdigest() != contract["identity"]["schema_sha256"]:
        raise M08ContractError("M08 schema identity drifted")
    if compatibility_sha256(contract) != contract["identity"]["compatibility_sha256"]:
        raise M08ContractError("M08 compatibility identity drifted")
    root = contract_path.resolve().parents[2]
    dependencies = {
        "observation": ("config/v1/m04-observation-contract.json", "7f8a46af1fe2a2c23e755c71b3bc2d04c9a0d057c573e901e5c9ed9178ca13eb"),
        "action": ("config/v1/m05-action-contract.json", "215c7d3ebeea97f1629debee4a2d10301838ccfd3085e4828685591677b58536"),
        "ppo": ("config/v1/m07-ppo-contract.json", "8649da85cee2914d423a7ae8f1bcff0fa6a1c7d749bd04232976fbad6df518c0"),
    }
    for name, (relative, expected) in dependencies.items():
        observed = validate_m07_ppo_contract.load_strict_json(root / relative)["identity"]["compatibility_sha256"]
        if observed != expected or contract["compatibility"][name] != observed:
            raise M08ContractError(f"{name} compatibility identity drifted")
    architecture_ids = [architecture["id"] for architecture in contract["architectures"]]
    if architecture_ids != ["structured-mlp-v1", "spatial-cnn-v1", "combined-cnn-mlp-v1"]:
        raise M08ContractError("architecture order or identity drifted")
    if contract["inputs"]["spatial"]["logical_order"] != "channel-y-x":
        raise M08ContractError("M04 channel-y-x layout was not preserved")
    if contract["device_semantics"]["openttd_simulation"] != "cpu-only":
        raise M08ContractError("OpenTTD simulation left the accepted CPU semantic boundary")
    profiling = contract["profiling"]
    if profiling["minimum_accepted_speedup"] < 1.1 or 1024 not in profiling["batch_sizes"]:
        raise M08ContractError("CUDA benefit gate is too weak or lacks a production-sized batch")
    if profiling["candidate_dispositions"]["observation-preprocessing"] != "cpu-retained-no-transform-to-accelerate":
        raise M08ContractError("unmeasured observation preprocessing was enabled")
    expected_requirements = {
        "STACK-002", "STACK-003", "STACK-004", "STACK-008", "STACK-011", "RUN-009", "ARCH-002", "ARCH-003"
    }
    if set(contract["requirements"]) != expected_requirements:
        raise M08ContractError("M08 requirement ownership drifted")
    return contract


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=pathlib.Path)
    parser.add_argument("schema", type=pathlib.Path)
    args = parser.parse_args()
    try:
        contract = validate(args.contract, args.schema)
    except (M08ContractError, OSError, ValueError, jsonschema.ValidationError) as exc:
        print(f"M08_ARCHITECTURE_CONTRACT=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M08_ARCHITECTURE_CONTRACT=PASS "
        f"compatibility_sha256={contract['identity']['compatibility_sha256']} architectures=3"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
