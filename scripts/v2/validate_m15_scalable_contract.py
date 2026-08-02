#!/usr/bin/env python3
"""Validate the frozen M15 scalable scenario/observation/action/model contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema


class M15ScalableContractError(ValueError):
    """The M15 scalable contract violates an identity or semantic invariant."""


@dataclass(frozen=True)
class M15ScalableContractSummary:
    rectangles: int
    seeds: int
    spatial_levels: int
    entity_tables: int
    action_families: int
    observation_bytes: int
    candidate_capacity: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15ScalableContractError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15ScalableContractError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15ScalableContractError(f"cannot hash {path}: {exc}") from exc


def derive_seed(domain: str, set_name: str, ordinal: int) -> int:
    digest = hashlib.sha256(f"{domain}:{set_name}:{ordinal}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def validate(
    root: pathlib.Path,
    contract_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
) -> M15ScalableContractSummary:
    root = root.resolve()
    contract_path = contract_path or root / "config/v2/m15-scalable-contract.json"
    schema_path = schema_path or root / "docs/project/schema/v2-m15-scalable-contract.schema.json"
    contract = load_json(contract_path)
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(contract)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15ScalableContractError(f"M15 scalable contract schema failed at {location}: {exc.message}") from exc
    require(contract["schema_sha256"] == sha256_file(schema_path), "M15 scalable contract schema SHA-256 mismatch")

    identity_paths = {
        "g14_gate_report_sha256": "docs/project/G14_GATE_REPORT.md",
        "research_baseline_sha256": "config/v2/research-baseline.json",
        "setting_inventory_sha256": "config/v2/setting-inventory.json",
        "competition_manifest_sha256": "config/v2/m14-competition-manifest.json",
    }
    for field, relative in identity_paths.items():
        require(contract["identity"][field] == sha256_file(root / relative), f"M15 {field} drifted")
    source = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    require(contract["identity"]["engine_source"] == {key: source[key] for key in ("release", "commit", "tree")}, "M15 engine source drifted")
    v1_paths = {
        "scenario": "config/v1/m02-scenario-contract.json",
        "bridge": "config/v1/m03-bridge-contract.json",
        "observation": "config/v1/m04-observation-contract.json",
        "action": "config/v1/m05-action-contract.json",
        "architecture": "config/v1/m08-architecture-cuda-contract.json",
    }
    require(set(contract["identity"]["v1_contracts"]) == set(v1_paths), "M15 V1 compatibility contract inventory drifted")
    for name, relative in v1_paths.items():
        require(contract["identity"]["v1_contracts"][name] == sha256_file(root / relative), f"M15 V1 {name} contract digest drifted")

    research = load_json(root / "config/v2/research-baseline.json")
    sides = research["maps"]["native_side_lengths"]
    expected_rectangles = [[width, height] for width in sides for height in sides]
    maps = contract["map"]
    require(maps["native_side_lengths"] == sides, "M15 native side lengths drifted from research")
    require(maps["native_rectangles"] == expected_rectangles, "M15 native rectangle inventory is incomplete or reordered")
    for tier, research_tier in (("curriculum", "curriculum"), ("generalization", "generalization"), ("boundary", "resource_boundary")):
        require(maps[tier] == research["maps"][research_tier], f"M15 {tier} map tier drifted from research")
    require(contract["verification"]["useful_play"] == maps["curriculum"], "M15 useful-play matrix drifted from curriculum")
    require(contract["verification"]["generalization"] == maps["generalization"], "M15 generalization verification drifted")
    require(contract["verification"]["boundary"] == maps["boundary"], "M15 boundary verification drifted")
    require(max(width * height for width, height in maps["generalization"]) == maps["useful_play_max_tiles"], "M15 useful-play tile limit does not cover generalization tier exactly")

    domain = contract["seeds"]["domain"]
    all_seeds: list[int] = []
    for set_name, seed_set in contract["seeds"]["sets"].items():
        expected = [derive_seed(domain, set_name, seed_set["ordinal_start"] + index) for index in range(len(seed_set["seeds"]))]
        require(seed_set["seeds"] == expected, f"M15 {set_name} seeds do not match deterministic derivation")
        all_seeds.extend(seed_set["seeds"])
    require(len(all_seeds) == len(set(all_seeds)), "M15 seed sets overlap")
    require(len(contract["seeds"]["sets"]["final"]["seeds"]) >= 16, "M15 final seed set is underpowered by contract")

    setting_inventory = load_json(root / "config/v2/setting-inventory.json")
    applicable = sum(setting_inventory["counts"]["by_disposition"][name] for name in ("SCENARIO_PIN", "COMPANY_PIN", "HARNESS_PIN"))
    require(applicable == 240, "M15 applicable setting definition count drifted")
    manifest_fields = set(contract["scenario"]["manifest_fields"])
    required_manifest_fields = {"contract_sha256", "engine_source_tree", "map_width", "map_height", "map_seed", "simulation_seed", "settings_manifest_sha256", "content_manifest_sha256", "resource_tier", "rejection_reason"}
    require(required_manifest_fields <= manifest_fields, "M15 scenario manifest identity fields are incomplete")
    counts = contract["scenario"]["counts"]
    require(counts["towns"]["maximum"] == 128 and counts["industries"]["maximum"] == 256, "M15 town/industry bounds drifted")
    require(counts["companies"]["maximum"] == 15 and counts["companies"]["target_rule"] == "1-for-M15", "M15 company bound/phase scope drifted")

    spatial = contract["observation"]["spatial"]
    require([item["name"] for item in spatial] == ["global", "regional", "local"], "M15 spatial pyramid order drifted")
    require(len({item["name"] for item in spatial}) == len(spatial), "M15 spatial pyramid names are duplicated")
    tables = contract["observation"]["entities"]
    require([item["name"] for item in tables] == ["companies", "towns", "industries", "stations", "vehicles"], "M15 entity table inventory/order drifted")
    table_by_name = {item["name"]: item for item in tables}
    require(table_by_name["towns"]["capacity"] == counts["towns"]["maximum"], "M15 town observation capacity drifted from scenario bound")
    require(table_by_name["industries"]["capacity"] == counts["industries"]["maximum"], "M15 industry observation capacity drifted from scenario bound")
    require(table_by_name["stations"]["capacity"] == counts["stations"]["maximum"], "M15 station observation capacity drifted from scenario bound")
    require(table_by_name["vehicles"]["capacity"] == counts["vehicles"]["maximum"], "M15 vehicle observation capacity drifted from scenario bound")
    structured_bytes = 4
    for dimension in contract["observation"]["structured"]["shape"]:
        structured_bytes *= dimension
    spatial_bytes = sum(item["channels"] * item["height"] * item["width"] * 4 for item in spatial)
    entity_bytes = sum(item["capacity"] * item["features"] * 4 + item["capacity"] for item in tables)
    graph = contract["observation"]["graph"]
    graph_bytes = graph["node_capacity"] * graph["node_features"] * 4 + graph["node_capacity"]
    graph_bytes += graph["edge_capacity"] * graph["edge_features"] * 4 + graph["edge_capacity"]
    calculated_observation_bytes = structured_bytes + spatial_bytes + entity_bytes + graph_bytes
    require(contract["resources"]["observation_bytes"] == calculated_observation_bytes, "M15 observation byte budget does not match tensor capacities")

    action = contract["action"]
    required_families = {"WAIT", "SELECT_TOWN_PAIR", "BUILD_ROAD_PATH", "BUILD_BUS_STOP", "BUILD_ROAD_DEPOT", "BUY_BUS", "SET_ROUTE", "START_VEHICLE", "STOP_VEHICLE", "SEND_TO_DEPOT", "SELL_VEHICLE", "MANAGE_LOAN"}
    require(set(action["families"]) == required_families, "M15 passenger-bus action family inventory drifted")
    candidate = action["candidate_table"]
    calculated_candidate_bytes = candidate["capacity"] * (candidate["features"] * 4 + candidate["parameter_words"] * 4 + 1)
    require(contract["resources"]["candidate_bytes"] == calculated_candidate_bytes, "M15 candidate byte budget does not match table capacity")
    require(contract["resources"]["protocol_payload_bytes"] >= calculated_observation_bytes + calculated_candidate_bytes, "M15 protocol payload cannot hold one observation and candidate table")
    limits = contract["resources"]["map_tier_limits"]
    require([item["tier"] for item in limits] == ["v1", "curriculum", "generalization", "boundary"], "M15 resource tier order drifted")
    require([item["maximum_tiles"] for item in limits] == [1024, 262144, 1048576, 16777216], "M15 resource tier tile bounds drifted")
    require(all(limits[index]["max_rss_kib"] <= limits[index + 1]["max_rss_kib"] for index in range(len(limits) - 1)), "M15 RSS budgets are not monotonic")
    require(all(limits[index]["wall_seconds"] <= limits[index + 1]["wall_seconds"] for index in range(len(limits) - 1)), "M15 wall budgets are not monotonic")
    require(contract["policy"]["memory"]["hidden_size"] == 256, "M15 recurrent-state width drifted")

    return M15ScalableContractSummary(
        rectangles=len(expected_rectangles),
        seeds=len(all_seeds),
        spatial_levels=len(spatial),
        entity_tables=len(tables),
        action_families=len(action["families"]),
        observation_bytes=calculated_observation_bytes,
        candidate_capacity=candidate["capacity"],
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--contract", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        summary = validate(args.root, args.contract, args.schema)
        print(
            f"V2_M15_CONTRACT=PASS rectangles={summary.rectangles} seeds={summary.seeds} spatial={summary.spatial_levels} "
            f"entities={summary.entity_tables} action_families={summary.action_families} "
            f"observation_bytes={summary.observation_bytes} candidates={summary.candidate_capacity}"
        )
        return 0
    except (M15ScalableContractError, OSError) as exc:
        print(f"V2_M15_CONTRACT=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
