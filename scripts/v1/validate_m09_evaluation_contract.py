#!/usr/bin/env python3
"""Strict preregistration, identity, partition, metric, and fairness checks for M09."""

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


class M09ContractError(ValueError):
    """The M09 independent evaluation contract is invalid."""


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
        raise M09ContractError("M09 schema identity drifted")
    if compatibility_sha256(contract) != contract["identity"]["compatibility_sha256"]:
        raise M09ContractError("M09 compatibility identity drifted")

    root = contract_path.resolve().parents[2]
    dependencies = {
        "reward_trajectory": ("config/v1/m06-reward-trajectory-contract.json", "9d8f9c2fc6074d899fa3b0047c55e3fb15cc5c17cddeaceaa1fd5389e53c8c9e"),
        "architecture_cuda": ("config/v1/m08-architecture-cuda-contract.json", "52c8b622b79d793e85ef749822e6886cd7cdda63194a471d38ab25da910e101d"),
    }
    for name, (relative, expected) in dependencies.items():
        observed = validate_m07_ppo_contract.load_strict_json(root / relative)["identity"]["compatibility_sha256"]
        if observed != expected or contract["compatibility"][name] != observed:
            raise M09ContractError(f"{name} compatibility identity drifted")
    ledger_path = root / "config/v1/m02-seed-ledger.json"
    ledger = validate_m07_ppo_contract.load_strict_json(ledger_path)
    if ledger["identity"]["ledger_sha256"] != contract["compatibility"]["seed_ledger"]:
        raise M09ContractError("M02 seed-ledger semantic identity drifted")
    by_split = {
        split: [entry["template_id"] for entry in ledger["entries"] if entry["split"] == split]
        for split in ("training", "development", "final-evaluation")
    }
    if by_split["training"] != contract["partitions"]["training"] or by_split["development"] != contract["partitions"]["development"] or by_split["final-evaluation"] != contract["partitions"]["final_evaluation"]:
        raise M09ContractError("M09 scenario partitions disagree with the frozen seed ledger")
    budget = contract["training_budget"]
    if budget["updates"] * budget["rollout_length"] * budget["environment_count"] != budget["accepted_samples_per_run"]:
        raise M09ContractError("M09 accepted-sample budget arithmetic drifted")
    expected_metrics = {
        "survival", "bankruptcy", "final-balance", "net-profit", "operating-profit",
        "passenger-deliveries", "route-profit", "profitable-vehicles", "infrastructure-cost",
        "roi", "station-rating", "coverage", "invalid-actions", "action-efficiency", "seed-stability",
    }
    if {metric["id"] for metric in contract["metrics"]} != expected_metrics:
        raise M09ContractError("EVAL-009 metric disposition inventory drifted")
    if contract["metrics"][10]["id"] != "station-rating" or contract["metrics"][10]["availability"] != "unavailable":
        raise M09ContractError("station-rating unavailable-state disclosure drifted")
    expected_baselines = ["seeded-random-legal-v1", "wait-only-trivial-v1", "m05-scripted-bus-v1"]
    if [baseline["id"] for baseline in contract["baselines"]] != expected_baselines:
        raise M09ContractError("M09 baseline registry order or coverage drifted")
    if contract["evaluation_suite"]["primary"]["templates"] != contract["partitions"]["final_evaluation"]:
        raise M09ContractError("primary evaluation is not the frozen final partition")
    if set(contract["evaluation_suite"]["robustness"]["starting_balances"]) == {100000}:
        raise M09ContractError("robustness suite lacks a starting-balance variation")
    if len(contract["training_budget"]["run_seeds"]) < 3:
        raise M09ContractError("architecture comparison lacks multiple matched seeds")
    return contract


def validate_runtime_lock(lock_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    lock = validate_m07_ppo_contract.load_strict_json(lock_path)
    schema = validate_m07_ppo_contract.load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(lock)
    if hashlib.sha256(schema_path.read_bytes()).hexdigest() != lock["identity"]["schema_sha256"]:
        raise M09ContractError("M09 runtime-lock schema identity drifted")
    if compatibility_sha256(lock) != lock["identity"]["compatibility_sha256"]:
        raise M09ContractError("M09 runtime-lock compatibility identity drifted")
    root = lock_path.resolve().parents[2]
    native = lock["native_delta"]
    patch = root / native["patch_path"]
    series = root / native["series_path"]
    if hashlib.sha256(patch.read_bytes()).hexdigest() != native["patch_sha256"]:
        raise M09ContractError("M09 native patch identity drifted")
    if hashlib.sha256(series.read_bytes()).hexdigest() != native["series_sha256"]:
        raise M09ContractError("M09 native series identity drifted")
    if series.read_text(encoding="utf-8") != patch.name + "\n":
        raise M09ContractError("M09 native series inventory drifted")
    if lock["evaluation_compatibility_sha256"] != "c64c9876c1f6cf46dcc2642bd4628ed45f4659d1866a047d4e51def60dab9a5e":
        raise M09ContractError("M09 runtime/evaluation compatibility drifted")
    return lock


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=pathlib.Path)
    parser.add_argument("schema", type=pathlib.Path)
    args = parser.parse_args()
    try:
        contract = validate(args.contract, args.schema)
        validate_runtime_lock(
            args.contract.resolve().with_name("m09-runtime-lock.json"),
            args.schema.resolve().with_name("v1-m09-runtime-lock.schema.json"),
        )
    except (M09ContractError, OSError, ValueError, jsonschema.ValidationError) as exc:
        print(f"M09_EVALUATION_CONTRACT=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M09_EVALUATION_CONTRACT=PASS "
        f"compatibility_sha256={contract['identity']['compatibility_sha256']} seeds=3 metrics=15"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
