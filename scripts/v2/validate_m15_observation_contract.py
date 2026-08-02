#!/usr/bin/env python3
"""Validate the detailed M15 bounded-observation field and byte contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from dataclasses import dataclass
from typing import Any

import jsonschema

import qualify_m15_observation


CONFIG = pathlib.Path("config/v2/m15-observation-contract.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m15-observation-contract.schema.json")
SCALABLE = pathlib.Path("config/v2/m15-scalable-contract.json")
SOURCE = pathlib.Path("config/v2/m15-observation-source.json")


class M15ObservationContractError(ValueError):
    """The detailed bounded-observation contract is inconsistent."""


@dataclass(frozen=True)
class M15ObservationContractSummary:
    bytes: int
    sections: int
    fields: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15ObservationContractError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15ObservationContractError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15ObservationContractError(f"cannot hash {path}: {exc}") from exc


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, schema_path: pathlib.Path | None = None) -> M15ObservationContractSummary:
    root = root.resolve()
    config_path, schema_path = config_path or root / CONFIG, schema_path or root / SCHEMA
    config, schema = load_json(config_path), load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(config)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15ObservationContractError(f"M15 observation contract schema failed at {location}: {exc.message}") from exc
    require(config["schema_sha256"] == sha256_file(schema_path), "M15 observation contract schema SHA-256 mismatch")
    require(config["scalable_contract_sha256"] == sha256_file(root / SCALABLE), "M15 scalable contract identity drifted")
    require(config["total_bytes"] == qualify_m15_observation.OBSERVATION_BYTES, "M15 observation exact byte count drifted")

    sections = config["serialization"]["sections"]
    expected = [
        {"name": name, "offset": offset, "bytes": size, "dtype": dtype, "shape": shape}
        for name, offset, size, dtype, shape in qualify_m15_observation.SECTION_LAYOUT
    ]
    require(sections == expected, "M15 observation serialized section layout drifted")
    cursor = 0
    for section in sections:
        require(section["offset"] == cursor, f"M15 observation section is not contiguous: {section['name']}")
        element_bytes = 4 if section["dtype"] == "float32-le" else 1
        size = element_bytes
        for dimension in section["shape"]:
            size *= dimension
        require(size == section["bytes"], f"M15 observation section byte math drifted: {section['name']}")
        cursor += section["bytes"]
    require(cursor == config["total_bytes"], "M15 observation sections do not consume exact payload")

    structured = config["structured"]
    require([field["index"] for field in structured["fields"]] == list(range(16)), "structured field indices drifted")
    require(structured["reserved"]["start"] == len(structured["fields"]) and structured["reserved"]["end"] == structured["features"] - 1, "structured reserved range drifted")
    channels = config["spatial"]["channels"]
    require([field["index"] for field in channels] == list(range(32)), "spatial channel indices drifted")
    require([field["name"] for field in channels[:16]] == ["in_map", "clear", "railway", "road", "house", "trees", "station", "water", "void", "industry", "tunnel_bridge", "object", "height_u8", "flat", "owned_by_company_0", "developed"], "spatial semantic channels drifted")
    require(all(field["encoding"] == "constant-0" for field in channels[16:]), "spatial reserved channels are not constant zero")
    require([(view["name"], view["shape"]) for view in config["spatial"]["views"]] == [("global", [32, 64, 64]), ("regional", [32, 64, 64]), ("local", [32, 32, 32])], "spatial view layout drifted")

    expected_tables = [("companies", 15, 32), ("towns", 128, 24), ("industries", 256, 24), ("stations", 512, 32), ("vehicles", 1024, 40)]
    require([(table["name"], table["capacity"], table["features"]) for table in config["entities"]] == expected_tables, "entity table capacities/features drifted")
    for table in config["entities"]:
        indices = [field["index"] for field in table["fields"]]
        require(indices == list(range(len(indices))), f"entity field indices are not contiguous: {table['name']}")
        require(table["reserved"]["start"] == len(indices) and table["reserved"]["end"] == table["features"] - 1, f"entity reserved range drifted: {table['name']}")
    graph = config["graph"]
    require([field["index"] for field in graph["node_fields"]] == list(range(5)) and [field["index"] for field in graph["edge_fields"]] == list(range(4)), "graph field indices drifted")

    patch_path = root / load_json(root / SOURCE)["patch"]["path"]
    patch_text = patch_path.read_text(encoding="utf-8")
    for token in ("TownID::End().base()", "IndustryID::End().base()", "VehicleID::End().base()", "SpatialGlobal()", "SpatialCrop(", "AppendTable("):
        require(token in patch_text, f"observation source lost detailed-contract token: {token}")
    field_count = len(structured["fields"]) + len(channels) + sum(len(table["fields"]) for table in config["entities"]) + len(graph["node_fields"]) + len(graph["edge_fields"])
    return M15ObservationContractSummary(config["total_bytes"], len(sections), field_count)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    args = parser.parse_args()
    try:
        summary = validate(args.root, args.config, args.schema)
        print(f"V2_M15_OBSERVATION_CONTRACT=PASS bytes={summary.bytes} sections={summary.sections} fields={summary.fields}")
        return 0
    except (M15ObservationContractError, OSError) as exc:
        print(f"V2_M15_OBSERVATION_CONTRACT=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
