#!/usr/bin/env python3
"""Validate the native non-learning M02 scripted passenger-bus trajectory."""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys
from typing import Any

import validate_m02_reset_projection
import validate_m02_scenario_contract


class M02ScriptedTrajectoryError(ValueError):
    """A trajectory schema, identity, command, economy, or scope guard failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M02ScriptedTrajectoryError(message)


def validate_semantics(
    report: dict[str, Any],
    instance: dict[str, Any],
) -> str:
    require(
        report.get("schema_version")
        == "openttd-rl-v1-m02-scripted-bus-trajectory-1",
        "trajectory schema_version mismatch",
    )
    require(report.get("status") == "PASS", "trajectory status is not PASS")
    trajectory = report.get("trajectory")
    require(isinstance(trajectory, dict), "trajectory payload is missing")
    require(
        set(trajectory)
        == {
            "actions",
            "company",
            "facilities",
            "forbidden",
            "orders",
            "scenario",
            "stations",
            "ticks",
            "vehicle",
        },
        "trajectory field inventory mismatch",
    )
    require(
        trajectory["scenario"]
        == {
            "scenario_sha256": instance["identity"]["scenario_sha256"],
            "seed": instance["seed"],
            "template_id": instance["template_id"],
        },
        "trajectory scenario identity mismatch",
    )

    expected_actions = [
        "build-bus-stop-0",
        "build-bus-stop-1",
        "connect-road-depot",
        "build-road-depot",
        "build-mps-regal-bus",
        "insert-station-order-0",
        "insert-station-order-1",
        "start-bus",
    ]
    actions = trajectory["actions"]
    require(isinstance(actions, list) and len(actions) == len(expected_actions), "scripted action count mismatch")
    balance = 100000
    for index, (expected, action) in enumerate(zip(expected_actions, actions)):
        require(set(action) == {"action", "balance_after", "cost"}, f"action {index} field inventory mismatch")
        require(action["action"] == expected, f"action {index} is not {expected}")
        require(isinstance(action["cost"], int) and action["cost"] >= 0, f"action {index} cost is invalid")
        require(action["balance_after"] == balance - action["cost"], f"action {index} balance/cost arithmetic mismatch")
        balance = action["balance_after"]
    require(all(actions[index]["cost"] > 0 for index in range(5)), "construction or bus purchase had zero cost")
    require(all(actions[index]["cost"] == 0 for index in range(5, 8)), "order/start action unexpectedly changed money")

    company = trajectory["company"]
    require(set(company) == {"balance", "delivered_passengers", "expenses", "id", "income"}, "company trajectory fields mismatch")
    require(company["id"] == 0, "trajectory company ID is not zero")
    require(isinstance(company["delivered_passengers"], int) and company["delivered_passengers"] > 0, "trajectory delivered no passengers")
    require(isinstance(company["income"], int) and company["income"] > 0, "trajectory produced no passenger income")
    require(isinstance(company["expenses"], int) and company["expenses"] <= 0, "trajectory running expenses sign is invalid")
    require(isinstance(company["balance"], int) and company["balance"] > 0, "trajectory company is insolvent")

    require(trajectory["facilities"] == {"depot_count": 1, "station_count": 2}, "trajectory facility count mismatch")
    require(
        trajectory["forbidden"]
        == {"airports": 0, "industries": 0, "rail": 0, "ships": 0, "trams": 0, "trucks": 0},
        "trajectory contains forbidden transport or industry state",
    )
    require(
        trajectory["orders"]
        == [
            {"destination_station_id": 0, "type": "go-to-station"},
            {"destination_station_id": 1, "type": "go-to-station"},
        ],
        "trajectory bus order sequence mismatch",
    )

    stations = trajectory["stations"]
    require(isinstance(stations, list) and len(stations) == 2, "trajectory station inventory mismatch")
    expected_tiles = [stop["y"] * 32 + stop["x"] for stop in instance["template"]["bus_stops"]]
    for index, station in enumerate(stations):
        require(
            set(station) == {"ever_accepted_passengers", "id", "owner", "tile", "waiting_passengers"},
            f"station {index} trajectory fields mismatch",
        )
        require(station["id"] == index and station["owner"] == 0, f"station {index} identity/owner mismatch")
        require(station["tile"] == expected_tiles[index], f"station {index} tile mismatch")
        require(isinstance(station["waiting_passengers"], int) and station["waiting_passengers"] >= 0, f"station {index} waiting cargo is invalid")
    require(any(station["ever_accepted_passengers"] is True for station in stations), "no station recorded accepted passengers")

    ticks = trajectory["ticks"]
    require(set(ticks) == {"executed", "final", "limit"}, "trajectory tick fields mismatch")
    require(ticks["limit"] == 65536, "trajectory tick limit mismatch")
    require(isinstance(ticks["executed"], int) and 1 <= ticks["executed"] <= ticks["limit"], "trajectory tick count is outside its bound")
    require(ticks["final"] == ticks["executed"], "trajectory final tick differs from executed ticks")

    vehicle = trajectory["vehicle"]
    require(
        set(vehicle)
        == {"capacity", "cargo", "cargo_stored", "engine_id", "id", "profit_this_year", "running", "type"},
        "trajectory vehicle fields mismatch",
    )
    require(
        {
            "capacity": vehicle["capacity"],
            "cargo": vehicle["cargo"],
            "engine_id": vehicle["engine_id"],
            "id": vehicle["id"],
            "running": vehicle["running"],
            "type": vehicle["type"],
        }
        == {"capacity": 31, "cargo": "passengers", "engine_id": 116, "id": 0, "running": True, "type": "bus"},
        "trajectory vehicle is not the running 31-passenger MPS Regal Bus",
    )
    require(isinstance(vehicle["cargo_stored"], int) and 0 <= vehicle["cargo_stored"] <= 31, "bus stored cargo is outside capacity")
    require(isinstance(vehicle["profit_this_year"], int), "bus profit is not an integer")
    return hashlib.sha256(
        validate_m02_reset_projection.canonical_bytes(report) + b"\n"
    ).hexdigest()


def validate_paths(
    report_path: pathlib.Path,
    instance_path: pathlib.Path,
    schema_path: pathlib.Path,
) -> tuple[dict[str, Any], str]:
    report = validate_m02_reset_projection.load_canonical_json(report_path)
    instance = validate_m02_reset_projection.load_canonical_json(instance_path)
    schema = validate_m02_scenario_contract.load_strict_json(schema_path)
    validate_m02_reset_projection.validate_schema(report, schema)
    return report, validate_semantics(report, instance)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=pathlib.Path)
    parser.add_argument("--instance", required=True, type=pathlib.Path)
    parser.add_argument("--schema", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        report, digest = validate_paths(
            args.report.resolve(), args.instance.resolve(), args.schema.resolve()
        )
    except (OSError, M02ScriptedTrajectoryError, validate_m02_reset_projection.M02ResetProjectionError) as exc:
        print(f"M02_SCRIPTED_TRAJECTORY=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M02_SCRIPTED_TRAJECTORY=PASS "
        f"template={report['trajectory']['scenario']['template_id']} "
        f"report_sha256={digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
