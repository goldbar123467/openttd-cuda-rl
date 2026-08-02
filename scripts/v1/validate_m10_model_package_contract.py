#!/usr/bin/env python3
"""Validate the frozen M10 export, package, and equivalence contract."""

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


class M10ContractError(ValueError):
    """The M10 package/equivalence contract is invalid."""


EXPECTED_COMPATIBILITY = "e77edf9be1343970a55becbb05da96a6b9a17edbd8df2c7999701dd8fa1f33b6"
ARCHITECTURES = ["structured-mlp-v1", "spatial-cnn-v1", "combined-cnn-mlp-v1"]
SOURCE_PACKAGES = [
    "e21039cd66eaeb1f54a3e19271d2e2e71695496b54001a8afe17e01a669ed611",
    "f58a5db69b4917916c250dddb8822a22c548d21b5fc4f92c91e0c8706e1519a6",
    "074b3c3838d9c4b53235d8f9ccc060047f7ce29929511fda6086f072c53b62e3",
]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def compatibility_sha256(contract: dict[str, Any]) -> str:
    payload = copy.deepcopy(contract)
    payload["identity"].pop("compatibility_sha256", None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M10ContractError(message)


def validate(contract_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    contract = validate_m07_ppo_contract.load_strict_json(contract_path)
    schema = validate_m07_ppo_contract.load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(contract)
    require(hashlib.sha256(schema_path.read_bytes()).hexdigest() == contract["identity"]["schema_sha256"], "M10 schema identity drifted")
    require(compatibility_sha256(contract) == contract["identity"]["compatibility_sha256"] == EXPECTED_COMPATIBILITY, "M10 compatibility identity drifted")
    root = contract_path.resolve().parents[2]
    dependencies = {
        "observation": ("config/v1/m04-observation-contract.json", "7f8a46af1fe2a2c23e755c71b3bc2d04c9a0d057c573e901e5c9ed9178ca13eb"),
        "action_and_mask": ("config/v1/m05-action-contract.json", "215c7d3ebeea97f1629debee4a2d10301838ccfd3085e4828685591677b58536"),
        "reward_trajectory": ("config/v1/m06-reward-trajectory-contract.json", "9d8f9c2fc6074d899fa3b0047c55e3fb15cc5c17cddeaceaa1fd5389e53c8c9e"),
        "architecture": ("config/v1/m08-architecture-cuda-contract.json", "52c8b622b79d793e85ef749822e6886cd7cdda63194a471d38ab25da910e101d"),
        "evaluation": ("config/v1/m09-evaluation-contract.json", "c64c9876c1f6cf46dcc2642bd4628ed45f4659d1866a047d4e51def60dab9a5e"),
    }
    for name, (relative, expected) in dependencies.items():
        observed = validate_m07_ppo_contract.load_strict_json(root / relative)["identity"]["compatibility_sha256"]
        require(observed == expected == contract["compatibility"][name], f"{name} compatibility drifted")
    ledger = validate_m07_ppo_contract.load_strict_json(root / "config/v1/m02-seed-ledger.json")
    require(ledger["identity"]["ledger_sha256"] == contract["compatibility"]["seed_ledger"], "seed ledger compatibility drifted")
    lock = validate_m07_ppo_contract.load_strict_json(root / "config/v1/dependency-lock.json")
    artifacts = {item["id"]: item for item in lock["artifacts"]}
    runtime = artifacts["onnxruntime-cpu"]
    require(runtime["version"] == contract["runtime"]["version"] and runtime["sha256"] == contract["runtime"]["archive_sha256"], "ONNX Runtime pin drifted")
    exporter_versions = {
        "exporter-torch-cpu": contract["exporter"]["torch"],
        "exporter-onnx": contract["exporter"]["onnx"],
        "exporter-onnxscript": contract["exporter"]["onnxscript"],
    }
    for artifact_id, expected in exporter_versions.items():
        require(artifacts[artifact_id]["version"] == expected, f"{artifact_id} pin drifted")
    require([item["architecture_id"] for item in contract["models"]] == ARCHITECTURES, "model registry order drifted")
    require([item["source_package_id"] for item in contract["models"]] == SOURCE_PACKAGES, "development-selected source package registry drifted")
    expected_inputs = [["structured"], ["spatial"], ["structured", "spatial"]]
    require([[value["name"] for value in item["inputs"]] for item in contract["models"]] == expected_inputs, "architecture ONNX input signatures drifted")
    require(contract["exporter"]["opset"] == 18 and contract["exporter"]["fallback"] is False, "ONNX opset/fallback policy drifted")
    require(contract["runtime"]["provider"] == "CPUExecutionProvider" and not contract["runtime"]["training_dependency"] and not contract["runtime"]["cuda_dependency"], "deployment dependency boundary drifted")
    corpus = contract["golden_corpus"]
    require(corpus["cases_per_architecture"] == corpus["synthetic_cases"] + corpus["live_cases"] == 12, "golden corpus case accounting drifted")
    require(contract["sampled_distribution"]["samples_per_case_per_runtime"] >= 100_000, "sampled distribution budget is too small")
    require(set(contract["package"]["payload_files"]) == {"model.onnx", "golden.jsonl", "evaluation.json", "INSTALL.md"}, "deployment package payload inventory drifted")
    required_mutations = {
        "package-format", "compatibility-version", "package-id", "architecture-id", "architecture-version",
        "observation-compatibility", "action-compatibility", "mask-compatibility", "reward-compatibility",
        "m09-evaluation-compatibility", "m10-compatibility", "onnx-opset", "onnxruntime-version",
        "openttd-upstream-commit", "environment-version", "file-digest", "missing-file", "unknown-file",
        "symlink", "truncated-onnx", "nonfinite-input", "all-illegal-mask",
    }
    require(required_mutations <= set(contract["rejection_matrix"]), "compatibility/corruption rejection matrix is incomplete")
    expected_requirements = {
        "LIFE-013", "LIFE-014", "LIFE-017", "STACK-006", "STACK-007", "PPO-021",
        "MODEL-001", "MODEL-002", "MODEL-003", "MODEL-004", "MODEL-005", "MODEL-006",
        "MODEL-007", "MODEL-008", "MODEL-009", "TEST-011", "TEST-012",
    }
    require(set(contract["requirements"]) == expected_requirements, "M10 requirement ownership drifted")
    return contract


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=pathlib.Path)
    parser.add_argument("schema", type=pathlib.Path)
    args = parser.parse_args()
    try:
        contract = validate(args.contract, args.schema)
    except (M10ContractError, OSError, ValueError, jsonschema.ValidationError) as exc:
        print(f"M10_MODEL_PACKAGE_CONTRACT=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        f"M10_MODEL_PACKAGE_CONTRACT=PASS compatibility_sha256={contract['identity']['compatibility_sha256']} "
        f"models={len(contract['models'])} golden_cases={len(contract['models']) * contract['golden_corpus']['cases_per_architecture']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
