#!/usr/bin/env python3
"""Validate the detailed M15 hierarchical action and candidate contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from dataclasses import dataclass
from typing import Any

import jsonschema


CONFIG = pathlib.Path("config/v2/m15-action-contract.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m15-action-contract.schema.json")
SCALABLE = pathlib.Path("config/v2/m15-scalable-contract.json")
FAMILY_NAMES = [
    "WAIT", "SELECT_TOWN_PAIR", "BUILD_ROAD_PATH", "BUILD_BUS_STOP", "BUILD_ROAD_DEPOT", "BUY_BUS",
    "SET_ROUTE", "START_VEHICLE", "STOP_VEHICLE", "SEND_TO_DEPOT", "SELL_VEHICLE", "MANAGE_LOAN",
]
FAMILY_QUOTAS = [1, 256, 1024, 768, 512, 256, 256, 192, 192, 192, 192, 255]
SECTION_LAYOUT = [
    {"name": "features", "offset": 0, "bytes": 4096 * 32 * 4, "dtype": "float32-le", "shape": [4096, 32]},
    {"name": "parameters", "offset": 4096 * 32 * 4, "bytes": 4096 * 16 * 4, "dtype": "uint32-le", "shape": [4096, 16]},
    {"name": "mask", "offset": 4096 * 48 * 4, "bytes": 4096, "dtype": "uint8", "shape": [4096]},
]


class M15ActionContractError(ValueError):
    """The detailed M15 action contract is inconsistent."""


@dataclass(frozen=True)
class M15ActionContractSummary:
    bytes: int
    families: int
    capacity: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15ActionContractError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15ActionContractError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15ActionContractError(f"cannot hash {path}: {exc}") from exc


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, schema_path: pathlib.Path | None = None) -> M15ActionContractSummary:
    root = root.resolve()
    config_path, schema_path = config_path or root / CONFIG, schema_path or root / SCHEMA
    config, schema = load_json(config_path), load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(config)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15ActionContractError(f"M15 action contract schema failed at {location}: {exc.message}") from exc
    require(config["schema_sha256"] == sha256_file(schema_path), "M15 action contract schema SHA-256 mismatch")
    require(config["scalable_contract_sha256"] == sha256_file(root / SCALABLE), "M15 scalable contract identity drifted")
    require(config["capacity"] == 4096 and config["binary"]["total_bytes"] == 790_528, "M15 candidate capacity or byte count drifted")
    require(config["binary"]["sections"] == SECTION_LAYOUT, "M15 candidate serialized section layout drifted")
    cursor = 0
    for section in config["binary"]["sections"]:
        require(section["offset"] == cursor, f"M15 candidate section is not contiguous: {section['name']}")
        element_bytes = 1 if section["dtype"] == "uint8" else 4
        expected = element_bytes
        for dimension in section["shape"]:
            expected *= dimension
        require(expected == section["bytes"], f"M15 candidate section byte math drifted: {section['name']}")
        cursor += section["bytes"]
    require(cursor == config["binary"]["total_bytes"], "M15 candidate sections do not consume exact payload")
    features = config["features"]
    require([field["index"] for field in features["fields"]] == list(range(20)), "M15 candidate feature indices drifted")
    require([field["name"] for field in features["fields"][:12]] == [f"family_{name.lower()}" for name in FAMILY_NAMES], "M15 candidate family one-hot features drifted")
    require(features["reserved"] == {"start": 20, "end": 31, "value": 0}, "M15 candidate reserved feature range drifted")

    families = config["families"]
    require([item["index"] for item in families] == list(range(12)), "M15 family indices drifted")
    require([item["name"] for item in families] == FAMILY_NAMES, "M15 family names or order drifted")
    require([item["quota"] for item in families] == FAMILY_QUOTAS, "M15 family quotas drifted")
    offset = 0
    for family in families:
        require(family["row_begin"] == offset and family["row_end"] == offset + family["quota"], f"M15 family range drifted: {family['name']}")
        require(family["parameter_words"][0] == "family" and len(family["parameter_words"]) <= 16, f"M15 family parameter mapping drifted: {family['name']}")
        offset = family["row_end"]
    require(offset == config["capacity"] == sum(FAMILY_QUOTAS), "M15 family ranges do not consume exact capacity")
    require("authoritative test mode succeeds" in families[2]["legality"] and "authoritative test mode succeeds" in families[-1]["legality"], "M15 native legality wording drifted")
    require(config["result"]["statuses"] == ["SUCCESS", "NO_OP", "STALE_TOKEN", "OUT_OF_RANGE", "ILLEGAL_CANDIDATE", "FAMILY_MISMATCH", "NATIVE_REJECTED"], "M15 typed status registry drifted")
    return M15ActionContractSummary(config["binary"]["total_bytes"], len(families), config["capacity"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    args = parser.parse_args()
    try:
        summary = validate(args.root, args.config, args.schema)
        print(f"V2_M15_ACTION_CONTRACT=PASS bytes={summary.bytes} families={summary.families} capacity={summary.capacity}")
        return 0
    except (M15ActionContractError, OSError) as exc:
        print(f"V2_M15_ACTION_CONTRACT=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
