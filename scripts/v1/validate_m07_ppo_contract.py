#!/usr/bin/env python3
"""Strict schema, identity, dependency, and semantic validation for M07 PPO."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import sys
from typing import Any

import jsonschema


class M07PpoContractError(ValueError):
    """The M07 PPO contract is malformed or internally inconsistent."""


def load_strict_json(path: pathlib.Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise M07PpoContractError(f"{path}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise M07PpoContractError(f"{path}: UTF-8 BOM is forbidden")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                M07PpoContractError(f"{path}: invalid JSON constant {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M07PpoContractError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise M07PpoContractError(f"{path}: top level must be an object")
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def compatibility_sha256(contract: dict[str, Any]) -> str:
    payload = copy.deepcopy(contract)
    payload["identity"].pop("compatibility_sha256", None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def validate_semantics(contract: dict[str, Any], root: pathlib.Path) -> None:
    expected_inputs = {
        "bridge": ("config/v1/m03-bridge-contract.json", "4701a21ae106f6fa120db1b89c3929d16c29afafb8e0198126173137ed2af2d6"),
        "observation": ("config/v1/m04-observation-contract.json", "7f8a46af1fe2a2c23e755c71b3bc2d04c9a0d057c573e901e5c9ed9178ca13eb"),
        "action": ("config/v1/m05-action-contract.json", "215c7d3ebeea97f1629debee4a2d10301838ccfd3085e4828685591677b58536"),
        "reward_trajectory": ("config/v1/m06-reward-trajectory-contract.json", "9d8f9c2fc6074d899fa3b0047c55e3fb15cc5c17cddeaceaa1fd5389e53c8c9e"),
    }
    for name, (relative, expected) in expected_inputs.items():
        dependency = load_strict_json(root / relative)
        observed = dependency["identity"]["compatibility_sha256"]
        if observed != expected or contract["compatibility"][name] != observed:
            raise M07PpoContractError(f"{name} compatibility identity drifted")

    lock = load_strict_json(root / "config/v1/dependency-lock.json")
    libtorch = next((item for item in lock["artifacts"] if item["id"] == "libtorch-cu130"), None)
    if libtorch is None or libtorch["version"] != contract["backend"]["version"]:
        raise M07PpoContractError("pinned LibTorch dependency is absent or has a different version")
    if libtorch["sha256"] != "945c5a3d946a28b387ad9dc9fddda7ba03e35fae1375b84ebff15df789436f82":
        raise M07PpoContractError("pinned LibTorch archive identity drifted")

    architecture = contract["architecture"]
    if architecture["input"]["shape"] != [256] or architecture["policy_head"]["shape"] != [41]:
        raise M07PpoContractError("model shapes disagree with M04/M05")
    if architecture["trunk"] != [128, 128] or architecture["activation"] != "tanh":
        raise M07PpoContractError("structured MLP architecture drifted")

    ppo = contract["ppo"]
    expected_hyperparameters = {
        "gamma": 0.99,
        "gae_lambda": 0.95,
        "clip_epsilon": 0.2,
        "value_coefficient": 0.5,
        "entropy_coefficient": 0.01,
        "learning_rate": 0.0003,
        "adam_epsilon": 0.00001,
        "max_gradient_norm": 0.5,
        "rollout_length": 128,
        "environment_count": 1,
        "minibatch_size": 32,
        "optimization_epochs": 4,
    }
    if any(ppo[name] != value for name, value in expected_hyperparameters.items()):
        raise M07PpoContractError("trusted CPU PPO default hyperparameters drifted")
    samples = ppo["rollout_length"] * ppo["environment_count"]
    if samples % ppo["minibatch_size"]:
        raise M07PpoContractError("default rollout cannot be divided into complete minibatches")

    expected_streams = [
        "parameter_initialization",
        "action_sampling",
        "minibatch_shuffle",
        "environment_episode",
    ]
    if contract["rng"]["streams"] != expected_streams:
        raise M07PpoContractError("independent RNG stream order drifted")

    required_checks = {
        "preprocessed-observations", "logits", "masked-probabilities", "values", "rewards",
        "advantages", "returns", "component-losses", "total-loss", "gradients",
        "gradient-norm", "optimizer-state", "updated-parameters",
    }
    if set(contract["numerics"]["checks"]) != required_checks:
        raise M07PpoContractError("nonfinite check inventory is incomplete")

    verification = contract["verification"]
    if verification["scenario_partitioning"] != {
        "training_splits": ["training"],
        "development_splits": ["development"],
        "forbidden_splits": ["final-evaluation"],
    }:
        raise M07PpoContractError("training/development/final scenario partitioning drifted")
    if verification["development_selection"] != {
        "evaluation_interval_updates": 16,
        "minimum_completed_updates": 16,
        "score": "mean-return",
        "eligibility": [
            "mean-return-above-seeded-random",
            "mean-delivered-passengers-above-seeded-random",
            "service-success-on-every-development-template",
        ],
        "tie_breakers": ["mean-delivered-passengers", "earlier-update"],
        "retention": "content-addressed-best-eligible-checkpoint",
    }:
        raise M07PpoContractError("development checkpoint selection policy drifted")

    expected_requirements = {
        "LIFE-010", "LIFE-012", "RUN-006", "RUN-007", "TEST-009", "TEST-010",
        "TEST-013", "TEST-014", "ARCH-001", "PPO-001", "PPO-002", "PPO-003",
        "PPO-004", "PPO-005", "PPO-006", "PPO-007", "PPO-008", "PPO-009",
        "PPO-010", "PPO-011", "PPO-012", "PPO-013", "PPO-014", "PPO-015",
        "PPO-016", "PPO-017", "PPO-018", "PPO-019", "PPO-020", "PPO-022",
        "MON-001", "MON-002", "MON-003", "MON-004", "MON-005", "MON-006",
        "MON-007", "MON-008", "MON-009",
    }
    if set(contract["requirements"]) != expected_requirements:
        raise M07PpoContractError("M07 requirement ownership inventory drifted")
    if "PPO-021" in contract["requirements"]:
        raise M07PpoContractError("PPO-021 belongs to M10 export, not M07")


def validate(contract_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    contract = load_strict_json(contract_path)
    schema = load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(contract)
    observed_schema = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    if observed_schema != contract["identity"]["schema_sha256"]:
        raise M07PpoContractError(
            f"schema digest mismatch: expected={contract['identity']['schema_sha256']} actual={observed_schema}"
        )
    observed_contract = compatibility_sha256(contract)
    if observed_contract != contract["identity"]["compatibility_sha256"]:
        raise M07PpoContractError(
            f"compatibility digest mismatch: expected={contract['identity']['compatibility_sha256']} actual={observed_contract}"
        )
    validate_semantics(contract, contract_path.resolve().parents[2])
    return contract


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=pathlib.Path)
    parser.add_argument("schema", type=pathlib.Path)
    args = parser.parse_args()
    try:
        contract = validate(args.contract, args.schema)
    except (M07PpoContractError, OSError, jsonschema.ValidationError) as exc:
        print(f"M07_PPO_CONTRACT=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M07_PPO_CONTRACT=PASS "
        f"compatibility_sha256={contract['identity']['compatibility_sha256']} "
        f"architecture={contract['architecture']['id']} requirements={len(contract['requirements'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
