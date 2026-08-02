#!/usr/bin/env python3
"""Canonical M05 action codec, mask application, and independent slow mask oracle."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Sequence


ACTION_COUNT = 41
WAIT_INDEX = 0
ACTION_COMPATIBILITY_SHA256 = "215c7d3ebeea97f1629debee4a2d10301838ccfd3085e4828685591677b58536"
CONSUMERS = ("trainer", "evaluator", "onnx-runtime", "in-game-controller", "m05-oracle")


class M05ActionAdapterError(ValueError):
    """An action, mask, or policy output violates the frozen M05 contract."""


@dataclass(frozen=True)
class DecodedAction:
    index: int
    family: str
    parameters: tuple[tuple[str, int | bool], ...]


@dataclass(frozen=True)
class MaskedDistribution:
    probabilities: tuple[float, ...]
    legal_count: int
    all_masked_fallback: bool


def _parameters(**values: int | bool) -> tuple[tuple[str, int | bool], ...]:
    return tuple(sorted(values.items()))


def decode_action(index: int) -> DecodedAction:
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < ACTION_COUNT:
        raise M05ActionAdapterError(f"action index must be an integer in 0..{ACTION_COUNT - 1}")
    if index == 0:
        return DecodedAction(index, "WAIT", ())
    if index <= 2:
        origin = index - 1
        return DecodedAction(index, "SELECT_TOWNS", _parameters(origin_town_slot=origin, destination_town_slot=1 - origin))
    if index == 3:
        return DecodedAction(index, "BUILD_ROAD_CONNECTOR", ())
    if index <= 11:
        value = index - 4
        return DecodedAction(index, "BUILD_BUS_STOP", _parameters(site_town_slot=value // 4, orientation=value % 4))
    if index <= 15:
        return DecodedAction(index, "BUILD_ROAD_DEPOT", _parameters(orientation=index - 12))
    if index == 16:
        return DecodedAction(index, "BUY_BUS", _parameters(depot_site=0, engine_id=116))
    if index <= 24:
        return DecodedAction(index, "ASSIGN_ROUTE", _parameters(vehicle_slot=index - 17))
    if index <= 32:
        return DecodedAction(index, "SET_RUNNING", _parameters(vehicle_slot=index - 25, desired_running=True))
    return DecodedAction(index, "SET_STOPPED", _parameters(vehicle_slot=index - 33, desired_running=False))


def encode_action(family: str, **parameters: int | bool) -> int:
    family = str(family)
    if family == "WAIT" and not parameters:
        return 0
    if family == "SELECT_TOWNS":
        origin = parameters.get("origin_town_slot")
        destination = parameters.get("destination_town_slot")
        if (
            isinstance(origin, int)
            and not isinstance(origin, bool)
            and isinstance(destination, int)
            and not isinstance(destination, bool)
            and origin in (0, 1)
            and destination == 1 - origin
            and len(parameters) == 2
        ):
            return 1 + int(origin)
    elif family == "BUILD_ROAD_CONNECTOR" and not parameters:
        return 3
    elif family == "BUILD_BUS_STOP":
        slot = parameters.get("site_town_slot")
        orientation = parameters.get("orientation")
        if (
            isinstance(slot, int)
            and not isinstance(slot, bool)
            and slot in (0, 1)
            and isinstance(orientation, int)
            and not isinstance(orientation, bool)
            and 0 <= orientation < 4
            and len(parameters) == 2
        ):
            return 4 + int(slot) * 4 + orientation
    elif family == "BUILD_ROAD_DEPOT":
        orientation = parameters.get("orientation")
        if isinstance(orientation, int) and not isinstance(orientation, bool) and 0 <= orientation < 4 and len(parameters) == 1:
            return 12 + orientation
    elif family == "BUY_BUS":
        depot_site = parameters.get("depot_site")
        engine_id = parameters.get("engine_id")
        if (
            isinstance(depot_site, int)
            and not isinstance(depot_site, bool)
            and isinstance(engine_id, int)
            and not isinstance(engine_id, bool)
            and depot_site == 0
            and engine_id == 116
            and len(parameters) == 2
        ):
            return 16
    elif family in ("ASSIGN_ROUTE", "SET_RUNNING", "SET_STOPPED"):
        slot = parameters.get("vehicle_slot")
        if isinstance(slot, int) and not isinstance(slot, bool) and 0 <= slot < 8:
            if family == "ASSIGN_ROUTE" and len(parameters) == 1:
                return 17 + slot
            desired = parameters.get("desired_running")
            if family == "SET_RUNNING" and desired is True and len(parameters) == 2:
                return 25 + slot
            if family == "SET_STOPPED" and desired is False and len(parameters) == 2:
                return 33 + slot
    raise M05ActionAdapterError(f"parameters do not encode one frozen {family} action: {parameters}")


def validate_mask(mask: dict[str, Any], *, compatibility_sha256: str = ACTION_COMPATIBILITY_SHA256) -> tuple[int, ...]:
    if mask.get("compatibility_sha256") != compatibility_sha256:
        raise M05ActionAdapterError("action compatibility identity mismatch")
    if mask.get("schema_version") != "openttd-rl-v1-m05-action-mask-1":
        raise M05ActionAdapterError("action mask schema version mismatch")
    if mask.get("action_count") != ACTION_COUNT or mask.get("dtype") != "uint8":
        raise M05ActionAdapterError("action mask shape or dtype mismatch")
    legal = mask.get("legal")
    if not isinstance(legal, list) or len(legal) != ACTION_COUNT or any(type(value) is not int or value not in (0, 1) for value in legal):
        raise M05ActionAdapterError("action mask must contain exactly 41 binary integer values")
    if mask.get("legal_count") != sum(legal):
        raise M05ActionAdapterError("action mask legal_count disagrees with its bytes")
    return tuple(legal)


def masked_distribution(
    logits: Sequence[float],
    mask: dict[str, Any],
    *,
    consumer: str,
    compatibility_sha256: str = ACTION_COMPATIBILITY_SHA256,
) -> MaskedDistribution:
    if consumer not in CONSUMERS:
        raise M05ActionAdapterError(f"unknown M05 consumer {consumer!r}")
    if len(logits) != ACTION_COUNT:
        raise M05ActionAdapterError("policy logits must have shape [41]")
    values = tuple(float(value) for value in logits)
    if any(not math.isfinite(value) for value in values):
        raise M05ActionAdapterError("policy logits must be finite")
    legal = validate_mask(mask, compatibility_sha256=compatibility_sha256)
    legal_indices = [index for index, value in enumerate(legal) if value]
    if not legal_indices:
        probabilities = [0.0] * ACTION_COUNT
        probabilities[WAIT_INDEX] = 1.0
        return MaskedDistribution(tuple(probabilities), 0, True)
    maximum = max(values[index] for index in legal_indices)
    weights = [0.0] * ACTION_COUNT
    for index in legal_indices:
        weights[index] = math.exp(values[index] - maximum)
    total = math.fsum(weights)
    if not math.isfinite(total) or total <= 0:
        raise M05ActionAdapterError("legal-only softmax normalization failed")
    probabilities = tuple(value / total for value in weights)
    if any(probabilities[index] != 0.0 for index, value in enumerate(legal) if not value):
        raise M05ActionAdapterError("illegal action received nonzero probability")
    return MaskedDistribution(probabilities, len(legal_indices), False)


def greedy_action(distribution: MaskedDistribution) -> int:
    return max(range(ACTION_COUNT), key=lambda index: (distribution.probabilities[index], -index))


def sample_action(distribution: MaskedDistribution, uniform: float) -> int:
    if not math.isfinite(uniform) or not 0.0 <= uniform < 1.0:
        raise M05ActionAdapterError("caller-supplied uniform must be finite and in [0,1)")
    cumulative = 0.0
    last_positive = WAIT_INDEX
    for index, probability in enumerate(distribution.probabilities):
        if probability > 0:
            last_positive = index
        cumulative += probability
        if uniform < cumulative:
            return index
    return last_positive


def independent_oracle_mask(source: dict[str, Any]) -> tuple[int, ...]:
    """Slow contract-level oracle independent of native command-test mask code."""
    result = [0] * ACTION_COUNT
    result[0] = 1
    towns = source["town_slots_present"]
    selected = source["selection"]
    for origin in range(2):
        destination = 1 - origin
        if towns[origin] and towns[destination] and (
            selected["origin_town_slot"], selected["destination_town_slot"]
        ) != (origin, destination):
            result[1 + origin] = 1
    connector = source["connector"]
    depot = source["depot"]
    if not connector["built"] and not depot["present"]:
        result[3] = 1
    for stop in source["stops"]:
        if stop["station_id"] < 0:
            result[4 + stop["town_slot"] * 4 + stop["expected_direction"]] = 1
    if connector["built"] and not depot["present"]:
        result[12 + depot["expected_direction"]] = 1
    vehicles = source["vehicles"]
    if depot["present"] and sum(bool(vehicle["present"]) for vehicle in vehicles) < 8:
        result[16] = 1
    station_ids = [stop["station_id"] for stop in source["stops"]]
    origin = selected["origin_town_slot"]
    destination = selected["destination_town_slot"]
    selection_valid = origin in (0, 1) and destination in (0, 1) and origin != destination
    target_orders = [station_ids[origin], station_ids[destination]] if selection_valid else []
    stations_valid = selection_valid and all(station >= 0 for station in target_orders)
    for vehicle in vehicles:
        slot = vehicle["slot"]
        if not vehicle["present"]:
            continue
        if stations_valid and vehicle["orders"] != target_orders:
            result[17 + slot] = 1
        if vehicle["running"]:
            result[33 + slot] = 1
        elif len(vehicle["orders"]) == 2:
            result[25 + slot] = 1
    return tuple(result)
