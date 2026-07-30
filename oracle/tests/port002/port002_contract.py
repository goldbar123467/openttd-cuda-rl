#!/usr/bin/env python3
"""Strict PORT-002A fixture and normalized-settings contract validation.

This module deliberately does not parse OpenTTD savegames. A final validation
requires immutable save bytes, but the loaded timer/RNG and reachability proofs
remain PORT-003 responsibilities.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import re
import sys
from collections import deque
from typing import Any

import jsonschema


SOURCE_COMMIT = "29f808ef0022064e6d9a83c8476d1e0f4686af86"
FIXTURE_ID = "road_freight_v1"
PERSONAL_DATA = re.compile(
    r"(?:[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}|/(?:home|Users)/[^/\s]+|"
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b)",
    re.IGNORECASE,
)

# Exact inventory selected from the pinned setting tables. Values are allowed
# to vary during canonicalization so identity-change tests are meaningful; the
# committed profile comparison rejects every differing frozen value.
SETTING_TYPES: dict[str, tuple[str, str]] = {
    "ai.ai_in_multiplayer": ("boolean", "behavior"),
    "construction.autoslope": ("boolean", "behavior"),
    "construction.build_on_slopes": ("boolean", "behavior"),
    "construction.command_pause_level": ("integer", "behavior"),
    "construction.road_stop_on_competitor_road": ("boolean", "behavior"),
    "construction.road_stop_on_town_road": ("boolean", "behavior"),
    "difficulty.construction_cost": ("enumeration", "behavior"),
    "difficulty.competitors_interval": ("integer", "behavior"),
    "difficulty.disasters": ("boolean", "behavior"),
    "difficulty.industry_density": ("enumeration", "behavior"),
    "difficulty.infinite_money": ("boolean", "behavior"),
    "difficulty.initial_interest": ("integer", "behavior"),
    "difficulty.max_loan": ("integer", "behavior"),
    "difficulty.max_no_competitors": ("integer", "behavior"),
    "difficulty.subsidy_duration": ("integer", "behavior"),
    "difficulty.subsidy_multiplier": ("enumeration", "behavior"),
    "difficulty.vehicle_breakdowns": ("enumeration", "behavior"),
    "difficulty.vehicle_costs": ("enumeration", "behavior"),
    "economy.allow_town_roads": ("boolean", "behavior"),
    "economy.cargo_aging_rate": ("integer", "behavior"),
    "economy.feeder_payment_share": ("integer", "behavior"),
    "economy.give_money": ("boolean", "behavior"),
    "economy.industry_cargo_scale": ("integer", "behavior"),
    "economy.inflation": ("boolean", "behavior"),
    "economy.infrastructure_maintenance": ("boolean", "behavior"),
    "economy.minutes_per_calendar_year": ("integer", "behavior"),
    "economy.timekeeping_units": ("enumeration", "behavior"),
    "economy.town_growth_rate": ("enumeration", "behavior"),
    "economy.type": ("enumeration", "behavior"),
    "game_creation.generation_seed": ("integer", "behavior"),
    "game_creation.landscape": ("enumeration", "behavior"),
    "game_creation.map_x": ("integer", "behavior"),
    "game_creation.map_y": ("integer", "behavior"),
    "game_creation.se_flat_world_height": ("integer", "behavior"),
    "game_creation.starting_year": ("integer", "behavior"),
    "gui.autosave_interval": ("integer", "non_authoritative"),
    "gui.autosave_on_exit": ("boolean", "non_authoritative"),
    "gui.pause_on_newgame": ("boolean", "non_authoritative"),
    "linkgraph.accuracy": ("integer", "behavior"),
    "linkgraph.demand_distance": ("integer", "behavior"),
    "linkgraph.demand_size": ("integer", "behavior"),
    "linkgraph.distribution_armoured": ("enumeration", "behavior"),
    "linkgraph.distribution_default": ("enumeration", "behavior"),
    "linkgraph.distribution_mail": ("enumeration", "behavior"),
    "linkgraph.distribution_pax": ("enumeration", "behavior"),
    "linkgraph.recalc_interval": ("integer", "behavior"),
    "linkgraph.recalc_time": ("integer", "behavior"),
    "linkgraph.short_path_saturation": ("integer", "behavior"),
    "order.gradual_loading": ("boolean", "behavior"),
    "order.improved_load": ("boolean", "behavior"),
    "order.no_servicing_if_no_breakdowns": ("boolean", "behavior"),
    "order.selectgoods": ("boolean", "behavior"),
    "pf.roadveh_queue": ("boolean", "behavior"),
    "pf.yapf.max_search_nodes": ("integer", "behavior"),
    "pf.yapf.maximum_go_to_depot_penalty": ("integer", "behavior"),
    "pf.yapf.road_crossing_penalty": ("integer", "behavior"),
    "pf.yapf.road_curve_penalty": ("integer", "behavior"),
    "pf.yapf.road_slope_penalty": ("integer", "behavior"),
    "pf.yapf.road_stop_bay_occupied_penalty": ("integer", "behavior"),
    "pf.yapf.road_stop_occupied_penalty": ("integer", "behavior"),
    "pf.yapf.road_stop_penalty": ("integer", "behavior"),
    "station.modified_catchment": ("boolean", "behavior"),
    "station.serve_neutral_industries": ("boolean", "behavior"),
    "station.station_spread": ("integer", "behavior"),
    "vehicle.max_roadveh": ("integer", "behavior"),
    "vehicle.never_expire_vehicles": ("boolean", "behavior"),
    "vehicle.road_side": ("enumeration", "behavior"),
    "vehicle.roadveh_acceleration_model": ("enumeration", "behavior"),
    "vehicle.roadveh_slope_steepness": ("integer", "behavior"),
    "vehicle.servint_ispercent": ("boolean", "behavior"),
    "vehicle.servint_roadveh": ("integer", "behavior"),
}


class ContractError(ValueError):
    """A deterministic contract validation failure."""


def strict_json_bytes(raw: bytes) -> Any:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ContractError("UTF-8 byte-order mark is forbidden")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("artifact is not UTF-8") from exc

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ContractError(f"duplicate object key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=no_duplicates)
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON: {exc.msg}") from exc


def strict_json(path: pathlib.Path) -> Any:
    return strict_json_bytes(path.read_bytes())


def canonical_bytes(value: Any) -> bytes:
    def reject_float(item: Any) -> None:
        if isinstance(item, float):
            raise ContractError("floating-point values are outside the P0 JSON subset")
        if isinstance(item, dict):
            for child in item.values():
                reject_float(child)
        elif isinstance(item, list):
            for child in item:
                reject_float(child)

    reject_float(value)
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_settings_document(document: Any, *, require_sorted: bool = True) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ContractError("normalized settings root must be an object")
    expected_top = {
        "schema_version",
        "settings_schema_identity",
        "source_commit",
        "exporter_contract",
        "settings",
    }
    if set(document) != expected_top:
        raise ContractError(f"normalized settings keys must equal {sorted(expected_top)}")
    if document["schema_version"] != 1:
        raise ContractError("normalized settings schema_version must equal 1")
    if document["settings_schema_identity"] != "openttd-p0-settings-v1":
        raise ContractError("unknown settings schema identity")
    if document["source_commit"] != SOURCE_COMMIT:
        raise ContractError("normalized settings source commit mismatch")
    if document["exporter_contract"] != "sorted-stable-identifiers/canonical-json/p0-no-floats":
        raise ContractError("unknown settings exporter contract")
    settings = document["settings"]
    if not isinstance(settings, list):
        raise ContractError("settings must be an array")

    seen: set[str] = set()
    identifiers: list[str] = []
    for index, entry in enumerate(settings):
        if not isinstance(entry, dict):
            raise ContractError(f"setting {index} must be an object")
        required = {"id", "scope", "value_type", "value", "authority", "source_anchor", "rationale"}
        optional = {"enum_symbol"}
        if not required <= set(entry) or not set(entry) <= required | optional:
            raise ContractError(f"setting {index} has missing or unknown fields")
        identifier = entry["id"]
        if not isinstance(identifier, str):
            raise ContractError(f"setting {index} id must be a string")
        if identifier in seen:
            raise ContractError(f"duplicate setting identifier: {identifier}")
        seen.add(identifier)
        identifiers.append(identifier)
        if identifier not in SETTING_TYPES:
            raise ContractError(f"unknown required setting: {identifier}")
        expected_type, expected_authority = SETTING_TYPES[identifier]
        if entry["value_type"] != expected_type:
            raise ContractError(f"setting {identifier} value_type mismatch")
        if entry["authority"] != expected_authority:
            raise ContractError(f"setting {identifier} authority mismatch")
        value = entry["value"]
        if expected_type == "boolean" and type(value) is not bool:
            raise ContractError(f"setting {identifier} requires a boolean")
        if expected_type in {"integer", "enumeration"} and type(value) is not int:
            raise ContractError(f"setting {identifier} requires an integer")
        if expected_type == "enumeration" and not isinstance(entry.get("enum_symbol"), str):
            raise ContractError(f"setting {identifier} requires enum_symbol")
        scope = identifier.split(".", 1)[0]
        if entry["scope"] != scope:
            raise ContractError(f"setting {identifier} scope mismatch")
        if not isinstance(entry["source_anchor"], str) or not entry["source_anchor"].startswith("openttd-upstream/src/"):
            raise ContractError(f"setting {identifier} source anchor is not pinned-source relative")
        if not isinstance(entry["rationale"], str) or not entry["rationale"].strip():
            raise ContractError(f"setting {identifier} rationale is empty")

    missing = set(SETTING_TYPES) - seen
    if missing:
        raise ContractError(f"missing required setting: {sorted(missing)[0]}")
    if require_sorted and identifiers != sorted(identifiers):
        raise ContractError("settings are not sorted by stable identifier")
    return document


def normalize_settings_document(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or not isinstance(document.get("settings"), list):
        raise ContractError("normalized settings root/settings has the wrong type")
    candidate = copy.deepcopy(document)
    try:
        candidate["settings"].sort(key=lambda entry: entry["id"] if isinstance(entry, dict) else "")
    except (KeyError, TypeError) as exc:
        raise ContractError("setting entry has no string identifier") from exc
    return validate_settings_document(candidate)


def normalized_settings_bytes(document: Any) -> bytes:
    validated = normalize_settings_document(document)
    return canonical_bytes(validated)


def authoritative_settings_identity(document: Any) -> str:
    validated = normalize_settings_document(document)
    authoritative = {
        "settings_schema_identity": validated["settings_schema_identity"],
        "source_commit": validated["source_commit"],
        "settings": [entry for entry in validated["settings"] if entry["authority"] == "behavior"],
    }
    return sha256_bytes(canonical_bytes(authoritative))


def assert_frozen_settings(candidate: Any, frozen: Any) -> None:
    candidate_identity = authoritative_settings_identity(candidate)
    frozen_identity = authoritative_settings_identity(frozen)
    if candidate_identity != frozen_identity:
        raise ContractError("behavior-affecting settings identity mismatch")
    # Even non-authoritative controls such as autosave are frozen for isolated
    # replay. They are excluded only from the authoritative state identity.
    if normalized_settings_bytes(candidate) != normalized_settings_bytes(frozen):
        raise ContractError("user configuration overrides frozen setting")


def _coord(value: list[int]) -> tuple[int, int]:
    return value[0], value[1]


def _industry_tiles(industry: dict[str, Any]) -> set[tuple[int, int]]:
    return {_coord(tile) for tile in industry["tiles"]}


def _road_tiles(plan: dict[str, Any]) -> set[tuple[int, int]]:
    result: set[tuple[int, int]] = set()
    for segment in plan["road_segments"]:
        x1, y1 = _coord(segment["from"])
        x2, y2 = _coord(segment["to"])
        if x1 != x2 and y1 != y2:
            raise ContractError(f"road segment {segment['id']} is not axis aligned")
        if x1 == x2:
            result.update((x1, y) for y in range(min(y1, y2), max(y1, y2) + 1))
        else:
            result.update((x, y1) for x in range(min(x1, x2), max(x1, x2) + 1))
    return result


def _connected(tiles: set[tuple[int, int]], start: tuple[int, int], target: tuple[int, int]) -> bool:
    if start not in tiles or target not in tiles:
        return False
    queue = deque([start])
    seen = {start}
    while queue:
        x, y = queue.popleft()
        if (x, y) == target:
            return True
        for neighbour in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbour in tiles and neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return False


def _within_catchment(stop: tuple[int, int], industry_tiles: set[tuple[int, int]], radius: int) -> bool:
    sx, sy = stop
    return any(max(abs(sx - x), abs(sy - y)) <= radius for x, y in industry_tiles)


def _adjacent(coord: tuple[int, int], tiles: set[tuple[int, int]]) -> bool:
    x, y = coord
    return any(point in tiles for point in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))


def _reject_personal_data(value: Any, path: str = "$", *, inspect_keys: bool = False) -> None:
    if isinstance(value, str) and PERSONAL_DATA.search(value):
        raise ContractError(f"personal data string present at {path}")
    if isinstance(value, dict):
        for key, child in value.items():
            if inspect_keys and PERSONAL_DATA.search(key):
                raise ContractError(f"personal data string present at {path}.{key}")
            _reject_personal_data(child, f"{path}.{key}", inspect_keys=inspect_keys)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_personal_data(child, f"{path}[{index}]", inspect_keys=inspect_keys)


def validate_fixture_data(
    manifest: Any,
    schema: dict[str, Any],
    base_directory: pathlib.Path,
    *,
    require_final: bool,
    schema_sha256: str | None = None,
) -> None:
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(manifest)
    except jsonschema.ValidationError as exc:
        raise ContractError(f"fixture schema validation failed at {list(exc.absolute_path)}: {exc.message}") from exc
    if not isinstance(manifest, dict):
        raise ContractError("fixture manifest must be an object")
    if schema_sha256 is not None and manifest["schema_sha256"] != schema_sha256:
        raise ContractError("fixture schema SHA-256 mismatch")
    if manifest["source_identity"]["commit"] != SOURCE_COMMIT:
        raise ContractError("fixture source commit mismatch")
    expected_executable = {
        "state": "verified",
        "sha256": "a0f3536b011fcb1af21341c4893c5efefb1b12db1fc0bfb5678edfbfdbc2c3e7",
        "size_bytes": 405127064,
    }
    if require_final and manifest["source_identity"]["creation_executable"] != expected_executable:
        raise ContractError("creation executable identity mismatch")
    if manifest["fixture_id"] != FIXTURE_ID:
        raise ContractError("fixture ID mismatch")
    review_status = manifest["review_status"]
    if require_final and review_status not in {"PORT002A_FROZEN", "PORT002B_PASS"}:
        raise ContractError("review template is not an authoritative frozen fixture")
    if require_final and manifest["source_identity"]["creation_executable"]["state"] != "verified":
        raise ContractError("creation executable identity is not verified")
    expected_runs = [
        ("run-a", "ffe1a275e60ba7e934e8e34cad2426160514de914120be6a6ce961efba631d35"),
        ("run-b", "91ec618ac40c71faa8403430d8995ec7b6b7ba4e330346268d4e374e9e1a64f1"),
    ]
    if require_final and [(run["id"], run["log_sha256"]) for run in manifest["creation"]["release_runs"]] != expected_runs:
        raise ContractError("release creation-log identity mismatch")
    if require_final and manifest["world"]["map"]["map_planes"]["state"] != "verified":
        raise ContractError("final fixture map planes are not verified")
    if require_final and manifest["world"]["map"]["map_planes"] != {
        "state": "verified",
        "format": "tile-index-order:type,height,m1,m2le,m3,m4,m5,m6,m7,m8le",
        "tile_count": 4096,
        "bytes_per_tile": 12,
        "size_bytes": 49152,
        "sha256": "5a933bc43d59c05b0d8fda519aec0aafa71b16d50a03aea83aefade7a57c9dd6",
        "two_run_equal": True,
    }:
        raise ContractError("final fixture map-plane identity mismatch")
    if review_status == "PORT002A_FROZEN" and not manifest["closure_blockers"]:
        raise ContractError("PORT002A fixture must retain explicit PORT002B closure blockers")
    if review_status == "PORT002B_PASS" and manifest["closure_blockers"]:
        raise ContractError("PORT002B fixture still declares closure blockers")

    world = manifest["world"]
    if world["map"]["width"] != 64:
        raise ContractError("map width must equal 64")
    if world["map"]["height"] != 64:
        raise ContractError("map height must equal 64")
    if world["map"]["source"] != "GWM_EMPTY" or world["climate"] != "temperate":
        raise ContractError("world source/climate is outside the frozen fixture")
    if world["network_game"]:
        raise ContractError("network game must be false")

    content = manifest["content"]
    if content["profile"] != "opengfx-8.0" or content["newgrfs"] != []:
        raise ContractError("wrong content profile or nonempty NewGRF list")
    if content["game_script"] is not None or content["ai_scripts"] != []:
        raise ContractError("GameScript and AI scripts must be absent")

    expected_town = {
        "id": 0,
        "tile": [32, 16],
        "tile_index": 1056,
        "name_policy": "fixed-non-personal-fixture-string",
        "name": "P0 Fixture Town",
        "population": 0,
        "house_count": 0,
        "road_tile_count": 0,
        "growing": False,
        "growth_rate": "TOWN_GROWTH_RATE_NONE",
    }
    if manifest["towns"] != [expected_town]:
        raise ContractError("fixture town identity or zero-footprint state mismatch")

    companies = manifest["companies"]
    human = [company for company in companies if company["kind"] == "human"]
    ai = [company for company in companies if company["kind"] == "ai"]
    if len(companies) != 1 or len(human) != 1 or human[0]["id"] != 0:
        raise ContractError("fixture requires exactly human company ID 0")
    if ai:
        raise ContractError("AI company present")
    if human[0]["name_policy"] != "generated-default-no-custom-string":
        raise ContractError("company name policy permits personal strings")
    if human[0]["opening_balance"] != 10000000 or human[0]["opening_loan"] != 0 or human[0]["cheat_state"] is not False:
        raise ContractError("company opening balance, loan, or cheat state mismatch")

    industries = manifest["industries"]
    if len(industries) != 2:
        raise ContractError("fixture requires exactly two industries")
    by_role = {industry["role"]: industry for industry in industries}
    if set(by_role) != {"producer", "acceptor"}:
        raise ContractError("producer and acceptor roles are required")
    producer, acceptor = by_role["producer"], by_role["acceptor"]
    if producer["id"] != 0 or producer["type_id"] != 0 or producer["type"] != "coal-mine":
        raise ContractError("producer identity mismatch")
    if acceptor["id"] != 1 or acceptor["type_id"] != 1 or acceptor["type"] != "power-station":
        raise ContractError("acceptor identity mismatch")
    if producer["selected_layout"] != 2 or producer["footprint"] != {"width": 3, "height": 3}:
        raise ContractError("producer selected layout or footprint mismatch")
    if acceptor["selected_layout"] != 2 or acceptor["footprint"] != {"width": 3, "height": 3}:
        raise ContractError("acceptor selected layout or footprint mismatch")
    if producer["tiles"] != [[8, 27], [9, 27], [10, 27], [8, 28], [9, 28], [10, 28], [8, 29], [9, 29], [10, 29]]:
        raise ContractError("producer tiles do not match selected layout 2")
    if acceptor["tiles"] != [[50, 27], [51, 27], [49, 28], [50, 28], [51, 28], [49, 29], [50, 29], [51, 29]]:
        raise ContractError("acceptor tiles do not match selected layout 2")
    if producer["tile_indices"] != [1736, 1737, 1738, 1800, 1801, 1802, 1864, 1865, 1866]:
        raise ContractError("producer TileIndex inventory mismatch")
    if acceptor["tile_indices"] != [1778, 1779, 1841, 1842, 1843, 1905, 1906, 1907]:
        raise ContractError("acceptor TileIndex inventory mismatch")
    for industry in industries:
        derived_indices = [y * world["map"]["width"] + x for x, y in (_coord(tile) for tile in industry["tiles"])]
        if derived_indices != industry["tile_indices"]:
            raise ContractError(f"industry {industry['id']} coordinate/TileIndex mapping mismatch")

    cargo = manifest["cargo"]
    engine = manifest["vehicle_engine"]
    if cargo["id"] != 1 or cargo["label"] != "COAL" or cargo["type"] != "coal":
        raise ContractError("cargo identity mismatch")
    if cargo["type"] not in producer["produces"] or cargo["type"] not in acceptor["accepts"]:
        raise ContractError("cargo incompatibility between industries")
    if engine["global_engine_id"] != 123 or engine["road_engine_id"] != 7 or engine["cargo"] != cargo["type"]:
        raise ContractError("vehicle engine or cargo compatibility mismatch")
    if not (engine["available_from_year"] <= world["start_date"]["year"] <= engine["available_through_year"]):
        raise ContractError("vehicle unavailable at fixture start date")

    width, height = world["map"]["width"], world["map"]["height"]
    coordinate_values: list[tuple[str, tuple[int, int]]] = []
    for industry in industries:
        coordinate_values.extend((f"industry:{industry['id']}", _coord(tile)) for tile in industry["tiles"])
    plan = manifest["coordinate_plan"]
    for segment in plan["road_segments"]:
        coordinate_values.append((f"road:{segment['id']}:from", _coord(segment["from"])))
        coordinate_values.append((f"road:{segment['id']}:to", _coord(segment["to"])))
        if any(segment["forbidden_branches"].values()):
            raise ContractError(f"road plan intersects forbidden tile branch: {segment['id']}")
    coordinate_values.extend(
        [
            ("pickup-stop", _coord(plan["pickup_stop"]["tile"])),
            ("delivery-stop", _coord(plan["delivery_stop"]["tile"])),
            ("depot", _coord(plan["depot"]["tile"])),
        ]
    )
    for name, (x, y) in coordinate_values:
        if not (0 <= x < width and 0 <= y < height):
            raise ContractError(f"coordinate outside map: {name} ({x},{y})")

    road = _road_tiles(plan)
    pickup = _coord(plan["pickup_stop"]["tile"])
    delivery = _coord(plan["delivery_stop"]["tile"])
    depot = _coord(plan["depot"]["tile"])
    expected_bay_direction = {"source_type": "DiagDirection", "source_symbol": "DiagDirection::SE", "raw_u8": 1}
    expected_depot_direction = {"source_type": "DiagDirection", "source_symbol": "DiagDirection::SW", "raw_u8": 2}
    if plan["pickup_stop"]["direction"] != expected_bay_direction or plan["delivery_stop"]["direction"] != expected_bay_direction:
        raise ContractError("truck-bay DiagDirection source symbol/raw value mismatch")
    if plan["depot"]["direction"] != expected_depot_direction:
        raise ContractError("depot DiagDirection source symbol/raw value mismatch")
    if len({pickup, delivery, depot}) != 3:
        raise ContractError("duplicate planned object coordinate")
    radius = plan["catchment_radius"]
    if radius != 4 or not _within_catchment(pickup, _industry_tiles(producer), radius):
        raise ContractError("pickup stop outside producer catchment")
    if not _within_catchment(delivery, _industry_tiles(acceptor), radius):
        raise ContractError("delivery stop outside acceptor catchment")
    if not _adjacent(depot, road):
        raise ContractError("depot inaccessible from road")
    if not _adjacent(pickup, road) or not _adjacent(delivery, road):
        raise ContractError("stop is inaccessible from road")
    pickup_access = _coord(plan["pickup_stop"]["road_access"])
    delivery_access = _coord(plan["delivery_stop"]["road_access"])
    if pickup_access != (pickup[0], pickup[1] + 1) or delivery_access != (delivery[0], delivery[1] + 1):
        raise ContractError("DiagDirection::SE does not reach declared bay road access")
    if _coord(plan["depot"]["road_access"]) != (depot[0] + 1, depot[1]):
        raise ContractError("DiagDirection::SW does not reach declared depot road access")
    if not _connected(road, pickup_access, delivery_access):
        raise ContractError("route disconnected")
    expected_segments = [
        ("road-west", [10, 31], [12, 31]),
        ("road-middle", [12, 31], [48, 31]),
        ("road-east", [48, 31], [52, 31]),
    ]
    observed_segments = [(segment["id"], segment["from"], segment["to"]) for segment in plan["road_segments"]]
    if observed_segments != expected_segments:
        raise ContractError("road segments differ from the exact frozen coordinate plan")
    if pickup != (12, 30) or pickup_access != (12, 31):
        raise ContractError("pickup stop differs from exact frozen coordinate plan")
    if delivery != (48, 30) or delivery_access != (48, 31):
        raise ContractError("delivery stop differs from exact frozen coordinate plan")
    if depot != (9, 31) or _coord(plan["depot"]["road_access"]) != (10, 31):
        raise ContractError("depot differs from exact frozen coordinate plan")
    if plan["vehicle_spawn_route"] != [[9, 31], [10, 31], [11, 31], [12, 31]]:
        raise ContractError("vehicle spawn route differs from exact frozen plan")

    expected_action_ids = [
        "road-west",
        "road-middle",
        "road-east",
        "depot",
        "pickup-stop",
        "delivery-stop",
        "purchase-vehicle",
        "pickup-order",
        "delivery-order",
        "start-vehicle",
    ]
    actions = manifest["command_plan"]["actions"]
    if manifest["command_plan"]["expected_command_count"] != 10 or [action["id"] for action in actions] != expected_action_ids:
        raise ContractError("native command action plan is not the exact ten-command sequence")
    if [action["sequence"] for action in actions] != list(range(1, 11)):
        raise ContractError("native command action sequence is not contiguous")
    expected_native_commands = [
        "Commands::BuildRoadLong",
        "Commands::BuildRoadLong",
        "Commands::BuildRoadLong",
        "Commands::BuildRoadDepot",
        "Commands::BuildRoadStop",
        "Commands::BuildRoadStop",
        "Commands::BuildVehicle",
        "Commands::InsertOrder",
        "Commands::InsertOrder",
        "Commands::StartStopVehicle",
    ]
    if [action["native_command"] for action in actions] != expected_native_commands:
        raise ContractError("native command symbols differ from the exact ten-command sequence")

    funding = manifest["funding_proof"]
    if funding["state"] == "verified":
        if funding["opening_balance"] < funding["command_cost_total"] + funding["safety_margin"]:
            raise ContractError("insufficient opening funds")
    elif review_status == "PORT002B_PASS":
        raise ContractError("final fixture lacks verified command-cost funding proof")

    bytes_record = manifest["fixture_bytes"]
    settings_record = manifest["normalized_settings"]
    if bytes_record["state"] == "frozen":
        save_path = (base_directory / bytes_record["relative_path"]).resolve()
        if save_path.parent != base_directory.resolve() or not save_path.is_file():
            raise ContractError("fixture save path is missing or escapes fixture directory")
        if save_path.stat().st_size != bytes_record["size_bytes"] or sha256_file(save_path) != bytes_record["sha256"]:
            raise ContractError("fixture save size or SHA-256 mismatch")
    elif require_final:
        raise ContractError("fixture save bytes are not frozen")
    settings_path = (base_directory / settings_record["relative_path"]).resolve()
    if settings_path.parent != base_directory.resolve() or not settings_path.is_file():
        raise ContractError("normalized settings path is missing or escapes fixture directory")
    settings_document = strict_json(settings_path)
    normalized = normalized_settings_bytes(settings_document)
    if settings_path.read_bytes() != normalized:
        raise ContractError("normalized settings file is not canonical JSON")
    if sha256_bytes(normalized) != settings_record["sha256"]:
        raise ContractError("normalized settings SHA-256 mismatch")
    if authoritative_settings_identity(settings_document) != settings_record["authoritative_identity_sha256"]:
        raise ContractError("authoritative settings identity mismatch")

    if review_status == "PORT002B_PASS" and manifest["initial_boundary"]["state"] != "verified":
        raise ContractError("initial timers and both RNG states are not verified")
    if review_status == "PORT002B_PASS" and manifest["milestones"]["state"] != "verified":
        raise ContractError("pickup/delivery/payment milestones are not verified")
    _reject_personal_data(manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", required=True, type=pathlib.Path)
    parser.add_argument("--manifest", type=pathlib.Path)
    parser.add_argument("--settings", type=pathlib.Path)
    parser.add_argument("--allow-review-template", action="store_true")
    parser.add_argument("--print-authoritative-settings-identity", action="store_true")
    args = parser.parse_args()
    try:
        if args.settings is not None:
            document = strict_json(args.settings)
            normalized = normalized_settings_bytes(document)
            if args.settings.read_bytes() != normalized:
                raise ContractError("normalized settings file is not canonical JSON")
            if args.print_authoritative_settings_identity:
                print(authoritative_settings_identity(document))
            else:
                print(sha256_bytes(normalized))
        if args.manifest is not None:
            schema = strict_json(args.schema)
            manifest = strict_json(args.manifest)
            validate_fixture_data(
                manifest,
                schema,
                args.manifest.parent,
                require_final=not args.allow_review_template,
                schema_sha256=sha256_file(args.schema),
            )
            print(f"validated {args.manifest}")
        if args.settings is None and args.manifest is None:
            parser.error("at least one of --settings or --manifest is required")
    except (ContractError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
