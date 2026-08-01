#!/usr/bin/env python3
"""Validate a native M02 reset report against the frozen scenario contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from typing import Any

import jsonschema

import generate_m02_scenario
import validate_m02_scenario_contract


class M02ResetProjectionError(ValueError):
    """A reset report encoding, schema, identity, or semantic guard failed."""


REPORT_SCHEMA_VERSION = "openttd-rl-v1-m02-reset-projection-1"
OPEN_GFX_SHA256 = "9389bcb0807058c80bd95121e978f05d9ef86b4b1bc3ac2da8da8bb02456043c"
ALLOWED_TILE_TYPES = {0, 2, 3, 4, 7}
FORBIDDEN_TILE_TYPES = {1, 5, 6, 8, 9, 10}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M02ResetProjectionError(message)


def load_canonical_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise M02ResetProjectionError(f"cannot read {path}: {exc}") from exc
    require(not raw.startswith(b"\xef\xbb\xbf"), f"{path}: UTF-8 BOM is forbidden")
    require(raw.endswith(b"\n") and not raw.endswith(b"\n\n"), f"{path}: expected exactly one terminal LF")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise M02ResetProjectionError(f"{path}: duplicate JSON key {key!r}")
            value[key] = item
        return value

    try:
        value = json.loads(
            raw[:-1].decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                M02ResetProjectionError(f"{path}: invalid JSON constant {token}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise M02ResetProjectionError(f"cannot parse {path}: {exc}") from exc
    require(isinstance(value, dict), f"{path}: top level must be an object")
    require(raw == canonical_bytes(value) + b"\n", f"{path}: JSON is not canonical compact sorted-key encoding")
    return value


def validate_schema(report: dict[str, Any], schema: dict[str, Any]) -> None:
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(report)
    except jsonschema.SchemaError as exc:
        raise M02ResetProjectionError(f"reset report schema is invalid: {exc.message}") from exc
    except jsonschema.ValidationError as exc:
        location = "/".join(str(item) for item in exc.absolute_path) or "<root>"
        raise M02ResetProjectionError(
            f"reset report schema validation failed: path={location} error={exc.message}"
        ) from exc


def validate_report_semantics(
    report: dict[str, Any],
    instance: dict[str, Any],
    contract: dict[str, Any],
) -> str:
    require(report.get("schema_version") == REPORT_SCHEMA_VERSION, "reset report schema_version mismatch")
    require(report.get("status") == "PASS", "reset report status is not PASS")
    require(report.get("same_process_byte_identical") is True, "same-process byte comparison did not pass")
    repetitions = report.get("same_process_repetitions")
    require(isinstance(repetitions, int) and 1 <= repetitions <= 16, "same-process repetition count is outside 1..16")
    projection = report.get("projection")
    require(isinstance(projection, dict), "projection must be an object")
    require(
        set(projection) == set(contract["reset_contract"]["projection_fields"]),
        "projection field inventory differs from the frozen contract",
    )

    require(
        projection["compatibility"]
        == {
            "contract_sha256": instance["contract_compatibility_sha256"],
            "corpus_sha256": instance["corpus_sha256"],
            "ledger_sha256": instance["seed_ledger_sha256"],
        },
        "projection compatibility identities mismatch",
    )
    require(
        projection["content"]
        == {
            "ai_company_count": 0,
            "base_graphics_metadata_version": [9499],
            "base_graphics_name": "OpenGFX",
            "game_script": None,
            "multiplayer": False,
            "networking": False,
            "newgrf_count": 0,
        },
        "content isolation or OpenGFX 8.0 metadata identity mismatch",
    )
    require(projection["settings"] == contract["settings"], "runtime settings differ from frozen settings")

    scenario = projection["scenario"]
    for key in ("scenario_sha256", "seed", "split", "template_id"):
        expected_key = "scenario_sha256" if key == "scenario_sha256" else key
        expected = instance["identity"][expected_key] if key == "scenario_sha256" else instance[key]
        require(scenario.get(key) == expected, f"scenario {key} mismatch")

    planned = scenario.get("planned_construction")
    require(isinstance(planned, dict), "planned construction projection is missing")
    expected_route = generate_m02_scenario.route_tiles(instance["template"]["road_waypoints"])
    require(planned.get("road_path_length") == len(expected_route) - 1, "planned road length mismatch")
    expected_stops = instance["template"]["bus_stops"]
    actual_stops = planned.get("bus_stops")
    require(isinstance(actual_stops, list) and len(actual_stops) == 2, "planned bus stop inventory mismatch")
    for expected, actual in zip(expected_stops, actual_stops):
        for key in ("approach", "town_id", "x", "y"):
            require(actual.get(key) == expected[key], f"planned bus stop {key} mismatch")
        require(actual.get("passenger_source_tiles_in_catchment", 0) > 0, "planned bus stop has no passenger source")
    expected_depot = instance["template"]["road_depot"]
    actual_depot = planned.get("road_depot")
    require(isinstance(actual_depot, dict), "planned depot projection is missing")
    for key in ("entrance", "x", "y"):
        require(actual_depot.get(key) == expected_depot[key], f"planned depot {key} mismatch")
    offsets = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
    dx, dy = offsets[expected_depot["entrance"]]
    require(
        (actual_depot.get("front_x"), actual_depot.get("front_y"))
        == (expected_depot["x"] + dx, expected_depot["y"] + dy),
        "planned depot entrance does not face its expected route tile",
    )

    map_value = projection["map"]
    require((map_value.get("width"), map_value.get("height")) == (32, 32), "native map is not 32 by 32")
    require(map_value.get("terrain_height") == 1, "terrain height mismatch")
    counts = map_value.get("tile_type_counts")
    require(isinstance(counts, list) and len(counts) == 11, "tile-type count vector must contain 11 entries")
    require(all(isinstance(value, int) and value >= 0 for value in counts), "tile-type counts must be nonnegative integers")
    require(sum(counts) == 1024, "tile-type counts do not cover exactly 1024 tiles")
    require(all(counts[index] == 0 for index in FORBIDDEN_TILE_TYPES), "forbidden tile type is present at reset")

    tiles = map_value.get("tiles")
    require(isinstance(tiles, list) and len(tiles) == 1024, "raw tile projection must contain 1024 tiles")
    observed_counts = [0] * 11
    for index, tile in enumerate(tiles):
        require(tile.get("index") == index, f"tile index order mismatch at {index}")
        x, y = index % 32, index // 32
        require((tile.get("x"), tile.get("y")) == (x, y), f"tile coordinates mismatch at {index}")
        raw = tile.get("raw")
        require(isinstance(raw, list) and len(raw) == 10, f"tile {index} raw plane width mismatch")
        require(all(isinstance(value, int) and 0 <= value <= 65535 for value in raw), f"tile {index} raw plane is invalid")
        require(raw[0] & 0x0F == 0, f"tile {index} raw type byte has unexpected low bits")
        tile_type = raw[0] >> 4
        require(tile_type in ALLOWED_TILE_TYPES, f"tile {index} has forbidden type {tile_type}")
        observed_counts[tile_type] += 1
        border = x in (0, 31) or y in (0, 31)
        require(tile_type == 7 if border else tile_type != 7, f"tile {index} violates the void-border policy")
        if not border:
            require(raw[1] == 1, f"interior tile {index} terrain height is not 1")
    require(observed_counts == counts, "raw tile planes disagree with tile-type counts")

    roads = projection["roads"]
    require(isinstance(roads, list) and len(roads) == counts[2], "road projection count mismatch")
    road_points: set[tuple[int, int]] = set()
    for road in roads:
        x, y = road.get("x"), road.get("y")
        require(isinstance(x, int) and isinstance(y, int), "road coordinates must be integers")
        require(road.get("index") == y * 32 + x, "road index/coordinate mismatch")
        require(road.get("road_type") == 0, "non-road or tram road type is present")
        require(road.get("owner") != 0, "company-owned road infrastructure is present at reset")
        require(isinstance(road.get("bits"), int) and road["bits"] > 0, "road has no connectivity bits")
        road_points.add((x, y))
    require(set(expected_route) <= road_points, "fixed route is not fully represented by native road tiles")

    companies = projection["companies"]
    require(isinstance(companies, list) and len(companies) == 1, "reset must contain exactly one company")
    company = companies[0]
    require(
        {key: company.get(key) for key in ("id", "is_ai", "money", "loan", "max_loan")}
        == {"id": 0, "is_ai": False, "money": 100000, "loan": 100000, "max_loan": 300000},
        "company identity or finance mismatch",
    )
    for key in ("owned_airport", "owned_rail", "owned_road", "owned_station", "owned_tram", "owned_water"):
        require(company.get(key) == 0, f"forbidden starting infrastructure is nonzero: {key}")

    towns = projection["towns"]
    require(isinstance(towns, list) and len(towns) == 2, "reset must contain exactly two towns")
    require(counts[3] == sum(town.get("house_tiles", 0) for town in towns), "town house counts disagree with map")
    for expected, town in zip(instance["template"]["towns"], towns):
        for key in ("town_id", "name", "x", "y"):
            actual_key = "id" if key == "town_id" else key
            require(town.get(actual_key) == expected[key], f"town {expected['town_id']} {key} mismatch")
        require(250 <= town.get("population", -1) <= 800, f"town {expected['town_id']} population is outside 250..800")
        require(town.get("house_tiles", 0) > 0, f"town {expected['town_id']} has no houses")
        require(town.get("passenger_source_tiles", 0) > 0, f"town {expected['town_id']} has no passenger source")
        require(town.get("growth_enabled") is False and town.get("growth_rate") == 65535, f"town {expected['town_id']} growth is enabled")
        require(town.get("layout") == 0, f"town {expected['town_id']} layout is not original")

    for name in ("vehicles", "stations", "depots", "orders"):
        require(projection[name] == [], f"forbidden {name} exist at reset")
    pools = projection["pools"]
    require(
        pools == {
            "cargo_packets": 0,
            "companies": 1,
            "depots": 0,
            "groups": 0,
            "industries": 0,
            "objects": 0,
            "order_lists": 0,
            "signs": 0,
            "stations": 0,
            "subsidies": 0,
            "towns": 2,
            "vehicles": 0,
        },
        "native pool state contains stale or forbidden entities",
    )

    economy = projection["economy"]
    require(
        economy == {"inflation_payment": 65536, "inflation_prices": 65536, "interest_rate": 2, "maximum_loan": 300000},
        "economy state differs from the frozen reset state",
    )
    time_value = projection["time"]
    require(
        time_value
        == {
            "calendar_date": 712223,
            "calendar_date_fraction": 0,
            "calendar_month": 0,
            "calendar_year": 1950,
            "economy_date": 712223,
            "economy_date_fraction": 0,
            "economy_month": 0,
            "economy_year": 1950,
            "tick": 0,
            "ticks_per_day": 74,
        },
        "calendar, economy date, or tick state differs from 1950-01-01 tick zero",
    )
    rng = projection["rng-streams"]
    require(set(rng) == {"interactive", "simulation"}, "RNG stream inventory mismatch")
    for name, state in rng.items():
        require(
            isinstance(state, list)
            and len(state) == 2
            and all(isinstance(value, int) and 0 <= value <= 0xFFFFFFFF for value in state),
            f"RNG stream {name} state is invalid",
        )

    return hashlib.sha256(canonical_bytes(projection)).hexdigest()


def validate_paths(
    report_path: pathlib.Path,
    instance_path: pathlib.Path,
    contract_path: pathlib.Path,
    contract_schema_path: pathlib.Path,
    report_schema_path: pathlib.Path,
) -> tuple[dict[str, Any], str]:
    report = load_canonical_json(report_path)
    instance = load_canonical_json(instance_path)
    contract = validate_m02_scenario_contract.validate(contract_path, contract_schema_path)
    schema = validate_m02_scenario_contract.load_strict_json(report_schema_path)
    validate_schema(report, schema)
    digest = validate_report_semantics(report, instance, contract)
    return report, digest


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=pathlib.Path)
    parser.add_argument("--instance", required=True, type=pathlib.Path)
    parser.add_argument("--contract", required=True, type=pathlib.Path)
    parser.add_argument("--contract-schema", required=True, type=pathlib.Path)
    parser.add_argument("--report-schema", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        report, digest = validate_paths(
            args.report.resolve(),
            args.instance.resolve(),
            args.contract.resolve(),
            args.contract_schema.resolve(),
            args.report_schema.resolve(),
        )
    except (
        OSError,
        M02ResetProjectionError,
        validate_m02_scenario_contract.M02ScenarioContractError,
    ) as exc:
        print(f"M02_RESET_PROJECTION=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M02_RESET_PROJECTION=PASS "
        f"template={report['projection']['scenario']['template_id']} "
        f"projection_sha256={digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
