#!/usr/bin/env python3
"""Validate the frozen M13 publication contract and produced manifest."""

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


class M13ContractError(ValueError):
    """The M13 contract or publication manifest is invalid."""


EXPECTED_COMPATIBILITY = "692e91fde04ae8069e89aa2c363e571a8b59724290f704bdc41b20b72150983c"
EXPECTED_GATES = [
    "contract-and-foundation",
    "repository-surface",
    "license-and-provenance",
    "accepted-package-identity",
    "deterministic-archive-repeat",
    "archive-safety",
    "credential-and-host-path-scan",
    "clean-main-publication",
]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


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
        raise M13ContractError(message)


def validate(contract_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    contract = validate_m07_ppo_contract.load_strict_json(contract_path)
    schema = validate_m07_ppo_contract.load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(contract)
    root = contract_path.resolve().parents[2]
    require(
        sha256_file(schema_path) == contract["identity"]["schema_sha256"],
        "M13 contract schema identity drifted",
    )
    require(
        compatibility_sha256(contract)
        == contract["identity"]["compatibility_sha256"]
        == EXPECTED_COMPATIBILITY,
        "M13 compatibility identity drifted",
    )
    require(contract["gates"] == EXPECTED_GATES, "M13 gate order/inventory drifted")
    manifest_schema = root / contract["identity"]["manifest_schema_path"]
    require(
        sha256_file(manifest_schema)
        == contract["identity"]["manifest_schema_sha256"],
        "M13 publication-manifest schema identity drifted",
    )
    m12 = validate_m07_ppo_contract.load_strict_json(root / "config/v1/m12-release-contract.json")
    require(
        m12["identity"]["compatibility_sha256"]
        == contract["accepted_m12"]["contract_sha256"],
        "accepted M12 contract identity drifted",
    )
    require(
        set(contract["model_package"]["files"])
        == {"INSTALL.md", "evaluation.json", "golden.jsonl", "manifest.json", "model.onnx"},
        "M13 model package file inventory drifted",
    )
    return contract


def validate_manifest(
    path: pathlib.Path,
    schema_path: pathlib.Path,
    contract: dict[str, Any],
) -> dict[str, Any]:
    payload = path.read_bytes()
    require(
        payload.endswith(b"\n") and not payload.endswith(b"\n\n"),
        "publication manifest must end in exactly one LF",
    )
    manifest = validate_m07_ppo_contract.load_strict_json(path)
    require(
        canonical_bytes(manifest) + b"\n" == payload,
        "publication manifest is not canonical compact sorted JSON plus one LF",
    )
    schema = validate_m07_ppo_contract.load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(manifest)
    semantic = copy.deepcopy(manifest)
    observed = semantic.pop("manifest_sha256")
    require(
        observed == hashlib.sha256(canonical_bytes(semantic)).hexdigest(),
        "publication manifest semantic identity drifted",
    )
    require(
        manifest["model_package"]["files"] == contract["model_package"]["files"],
        "publication manifest model package differs from M13 contract",
    )
    require(
        sorted(manifest["files"])
        == sorted(contract["archive"]["required_payload_files"]),
        "publication manifest payload inventory differs from M13 contract",
    )
    require(
        manifest["exclusions"] == contract["archive"]["excluded_components"],
        "publication manifest exclusions differ from M13 contract",
    )
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
            require(
                args.manifest is not None and args.manifest_schema is not None,
                "manifest and manifest schema are both required",
            )
            validate_manifest(args.manifest, args.manifest_schema, contract)
    except (M13ContractError, OSError, ValueError, jsonschema.ValidationError) as error:
        print(f"M13_PUBLICATION_CONTRACT=FAIL {error}", file=sys.stderr)
        return 1
    print(
        "M13_PUBLICATION_CONTRACT=PASS "
        f"compatibility_sha256={contract['identity']['compatibility_sha256']} "
        f"gates={len(contract['gates'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
