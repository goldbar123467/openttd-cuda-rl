#!/usr/bin/env python3
"""Validate the frozen M12 release contract and produced release manifest."""

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


class M12ContractError(ValueError):
    """The M12 contract or release manifest is invalid."""


EXPECTED_COMPATIBILITY = "e644f6e31163f9eb91008fe0bcb5d6830f3f3bb89104b229f3d974085b287879"
EXPECTED_REQUIREMENTS = {
    *(f"REPRO-{number:03d}" for number in range(1, 10)), "TEST-016",
    *(f"DONE-{number:03d}" for number in range(1, 9)),
}
EXPECTED_CAMPAIGNS = [
    "clean-dual-build", "scenario-reset-reproduction", "cpu-cuda-training",
    "checkpoint-recovery", "independent-evaluation", "onnx-package-equivalence",
    "visible-playback", "long-run-soak", "quality-matrix",
    "clean-operator-documentation", "traceability-defect-closure",
    "fresh-root-release-repeat",
]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def compatibility_sha256(contract: dict[str, Any]) -> str:
    payload = copy.deepcopy(contract)
    payload["identity"].pop("compatibility_sha256", None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M12ContractError(message)


def validate(contract_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    contract = validate_m07_ppo_contract.load_strict_json(contract_path)
    schema = validate_m07_ppo_contract.load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(contract)
    require(sha256_file(schema_path) == contract["identity"]["schema_sha256"], "M12 contract schema identity drifted")
    require(compatibility_sha256(contract) == contract["identity"]["compatibility_sha256"] == EXPECTED_COMPATIBILITY, "M12 compatibility identity drifted")
    require(contract["campaigns"] == EXPECTED_CAMPAIGNS, "M12 campaign order/inventory drifted")
    require(set(contract["requirements"]) == EXPECTED_REQUIREMENTS and len(contract["requirements"]) == 18, "M12 requirement inventory drifted")
    require(len({item["id"] for item in contract["accepted_evidence"]}) == 14, "M12 evidence IDs are not unique")
    require(len({item["argument"] for item in contract["accepted_evidence"]}) == 14, "M12 evidence arguments are not unique")

    root = contract_path.resolve().parents[2]
    manifest_schema = root / contract["release_manifest"]["schema_path"]
    require(sha256_file(manifest_schema) == contract["release_manifest"]["schema_sha256"], "M12 manifest schema identity drifted")
    dependency_paths = {
        "scenario": "config/v1/m02-scenario-contract.json",
        "bridge": "config/v1/m03-bridge-contract.json",
        "observation": "config/v1/m04-observation-contract.json",
        "action_and_mask": "config/v1/m05-action-contract.json",
        "reward_trajectory": "config/v1/m06-reward-trajectory-contract.json",
        "ppo": "config/v1/m07-ppo-contract.json",
        "architecture": "config/v1/m08-architecture-cuda-contract.json",
        "evaluation": "config/v1/m09-evaluation-contract.json",
        "model_package": "config/v1/m10-model-package-contract.json",
        "playback": "config/v1/m11-playback-contract.json",
    }
    for name, relative in dependency_paths.items():
        value = validate_m07_ppo_contract.load_strict_json(root / relative)
        require(value["identity"]["compatibility_sha256"] == contract["compatibility"][name], f"{name} compatibility drifted")
    return contract


def validate_manifest(path: pathlib.Path, schema_path: pathlib.Path, contract: dict[str, Any]) -> dict[str, Any]:
    payload = path.read_bytes()
    require(payload.endswith(b"\n") and not payload.endswith(b"\n\n"), "release manifest must end in exactly one LF")
    manifest = validate_m07_ppo_contract.load_strict_json(path)
    require(canonical_bytes(manifest) + b"\n" == payload, "release manifest is not canonical compact sorted JSON plus one LF")
    schema = validate_m07_ppo_contract.load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(manifest)
    semantic = copy.deepcopy(manifest)
    observed = semantic.pop("manifest_sha256")
    require(observed == hashlib.sha256(canonical_bytes(semantic)).hexdigest(), "release manifest semantic identity drifted")
    require(manifest["contract_sha256"] == contract["identity"]["compatibility_sha256"], "release manifest contract identity drifted")
    require([item["id"] for item in manifest["campaigns"]] == contract["campaigns"], "release manifest campaign order drifted")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("contract", type=pathlib.Path)
    parser.add_argument("schema", type=pathlib.Path)
    parser.add_argument("--manifest", type=pathlib.Path)
    parser.add_argument("--manifest-schema", type=pathlib.Path)
    args = parser.parse_args()
    try:
        contract = validate(args.contract, args.schema)
        if args.manifest is not None or args.manifest_schema is not None:
            require(args.manifest is not None and args.manifest_schema is not None, "manifest and manifest schema are both required")
            validate_manifest(args.manifest, args.manifest_schema, contract)
    except (M12ContractError, OSError, ValueError, jsonschema.ValidationError) as error:
        print(f"M12_RELEASE_CONTRACT=FAIL {error}", file=sys.stderr)
        return 1
    print(f"M12_RELEASE_CONTRACT=PASS compatibility_sha256={contract['identity']['compatibility_sha256']} campaigns={len(contract['campaigns'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
