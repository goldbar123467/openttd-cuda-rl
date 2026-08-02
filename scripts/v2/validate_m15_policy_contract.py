#!/usr/bin/env python3
"""Validate the frozen M15 scalable native-policy, checkpoint, and ONNX design contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema


CONFIG = pathlib.Path("config/v2/m15-policy-contract.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m15-policy-contract.schema.json")
SCALABLE = pathlib.Path("config/v2/m15-scalable-contract.json")


class M15PolicyContractError(ValueError):
    """The scalable policy contract is inconsistent."""


@dataclass(frozen=True)
class M15PolicyContractSummary:
    inputs: int
    outputs: int
    parameters: int
    devices: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15PolicyContractError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15PolicyContractError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(
    root: pathlib.Path,
    config_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
) -> M15PolicyContractSummary:
    root = root.resolve()
    config_path, schema_path = config_path or root / CONFIG, schema_path or root / SCHEMA
    config, schema = load_json(config_path), load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(config)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15PolicyContractError(f"M15 policy contract schema failed at {location}: {exc.message}") from exc
    require(config["schema_sha256"] == sha256_file(schema_path), "M15 policy contract schema SHA-256 mismatch")
    scalable = load_json(root / SCALABLE)
    require(config["compatibility"]["scalable_contract_sha256"] == sha256_file(root / SCALABLE), "scalable contract identity drifted")
    require(config["architecture"]["schema_id"] == scalable["policy"]["schema_id"], "policy schema identity drifted")
    require(config["architecture"]["encoders"] == scalable["policy"]["encoders"], "policy encoder inventory drifted")
    require(config["architecture"]["heads"] == scalable["policy"]["heads"], "policy head inventory drifted")
    require(config["architecture"]["memory"]["hidden_size"] == scalable["policy"]["memory"]["hidden_size"], "policy recurrent width drifted")
    require(config["compatibility"]["observation_schema_id"] == scalable["observation"]["schema_id"], "observation schema identity drifted")
    require(config["compatibility"]["action_schema_id"] == scalable["action"]["schema_id"], "action schema identity drifted")
    names = [item["name"] for item in config["inputs"]]
    require(len(names) == len(set(names)), "policy input names are not unique")
    require(config["onnx"]["inputs"] == names, "ONNX input order differs from native input order")
    output_names = [item["name"] for item in config["outputs"]]
    require(config["onnx"]["outputs"] == output_names, "ONNX output order differs from native output order")
    expected_shapes = {
        "structured": ["batch", *scalable["observation"]["structured"]["shape"]],
        "global_spatial": ["batch", 32, 64, 64], "regional_spatial": ["batch", 32, 64, 64],
        "local_spatial": ["batch", 32, 32, 32], "companies": ["batch", 15, 32],
        "towns": ["batch", 128, 24], "industries": ["batch", 256, 24],
        "stations": ["batch", 512, 32], "vehicles": ["batch", 1024, 40],
        "graph_nodes": ["batch", 2048, 24], "graph_edge_index": ["batch", 8192, 2],
        "graph_edge_features": ["batch", 8192, 16], "candidate_features": ["batch", 4096, 32],
        "candidate_family": ["batch", 4096], "candidate_mask": ["batch", 4096],
        "family_mask": ["batch", len(scalable["action"]["families"])], "hidden_state": ["batch", 256],
        "recurrent_reset": ["batch"],
    }
    input_by_name = {item["name"]: item for item in config["inputs"]}
    for entity in ("companies", "towns", "industries", "stations", "vehicles"):
        expected_shapes[f"{entity}_mask"] = expected_shapes[entity][:-1]
    expected_shapes["graph_node_mask"] = ["batch", 2048]
    expected_shapes["graph_edge_mask"] = ["batch", 8192]
    require(set(input_by_name) == set(expected_shapes), "policy input inventory drifted")
    for name, shape in expected_shapes.items():
        require(input_by_name[name]["shape"] == shape, f"policy input shape drifted: {name}")
    require(config["checkpoint"]["state"] == [
        "model", "optimizer", "normalization_mean", "normalization_variance", "normalization_count", "rng_state",
        "curriculum_tier", "map_dimensions", "episode", "transition", "completed_updates", "hidden_state", "contract_identity",
    ], "checkpoint state inventory drifted")
    source = (root / "training/v2/src/scalable_policy.cpp").read_text(encoding="utf-8")
    checkpoint = (root / "training/v2/src/checkpoint.cpp").read_text(encoding="utf-8")
    for token in ("masked_attention_pool", "scatter_add", "GRUCell", "candidate_logits", "recurrent_reset"):
        require(token in source, f"native scalable policy lost required implementation token: {token}")
    for token in ("torch::save(model", "torch::save(optimizer", "normalization_mean", "rng_state", "curriculum", "hidden_state", "never overwriting"):
        require(token in checkpoint, f"native checkpoint lost required implementation token: {token}")
    return M15PolicyContractSummary(len(names), len(output_names), config["architecture"]["parameter_count"], len(config["backend"]["devices"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    args = parser.parse_args()
    try:
        summary = validate(args.root, args.config, args.schema)
        print(f"V2_M15_POLICY_CONTRACT=PASS inputs={summary.inputs} outputs={summary.outputs} parameters={summary.parameters} devices={summary.devices}")
        return 0
    except (M15PolicyContractError, OSError) as exc:
        print(f"V2_M15_POLICY_CONTRACT=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
