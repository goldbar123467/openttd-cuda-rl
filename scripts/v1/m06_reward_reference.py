#!/usr/bin/env python3
"""Independent M06 reward, termination, integrity, and shuffle reference."""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import math
import struct
from typing import Any

from validate_m06_reward_contract import M06RewardContractError, canonical_bytes


class M06RewardReferenceError(ValueError):
    """Raw transition data violates the frozen M06 foundation."""


@dataclasses.dataclass(frozen=True)
class RewardResult:
    raw: tuple[int, ...]
    clamped: tuple[int, ...]
    weighted: tuple[float, ...]
    scalar: float


@dataclasses.dataclass(frozen=True)
class TerminationResult:
    reason: str
    kind: str
    terminal: bool
    truncated: bool
    bootstrap: bool
    trainable: bool


def _integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise M06RewardReferenceError(f"{name} must be an integer and never bool")
    return value


def _keys(value: dict[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise M06RewardReferenceError(f"{name} fields differ: expected={sorted(expected)} actual={sorted(value)}")


def derive_raw(pre: dict[str, Any], post: dict[str, Any], action: dict[str, Any]) -> dict[str, int]:
    state_fields = {
        "company_present",
        "delivered_passengers_total",
        "operating_income_total",
        "operating_expenses_total",
        "primary_bus_count",
        "stopped_primary_bus_count",
    }
    _keys(pre, state_fields, "pre state")
    _keys(post, state_fields, "post state")
    _keys(action, {"advanced_ticks", "native_commands", "status"}, "action")
    for name, state in (("pre", pre), ("post", post)):
        if not isinstance(state["company_present"], bool):
            raise M06RewardReferenceError(f"{name}.company_present must be boolean")
        for field in state_fields - {"company_present"}:
            _integer(state[field], f"{name}.{field}")
        if state["delivered_passengers_total"] < 0 or state["operating_income_total"] < 0:
            raise M06RewardReferenceError(f"{name} lifetime delivery/income totals cannot be negative")
        if state["operating_expenses_total"] > 0:
            raise M06RewardReferenceError(f"{name} lifetime operating expenses must be zero or negative")
        if not 0 <= state["stopped_primary_bus_count"] <= state["primary_bus_count"] <= 8:
            raise M06RewardReferenceError(f"{name} vehicle counts violate the M05 bound")
    if post["delivered_passengers_total"] < pre["delivered_passengers_total"]:
        raise M06RewardReferenceError("lifetime delivered-passenger total regressed")
    if post["operating_income_total"] < pre["operating_income_total"]:
        raise M06RewardReferenceError("lifetime operating-income total regressed")
    if post["operating_expenses_total"] > pre["operating_expenses_total"]:
        raise M06RewardReferenceError("lifetime operating-expense total regressed toward zero")

    ticks = _integer(action["advanced_ticks"], "action.advanced_ticks")
    if ticks < 0 or ticks > 128:
        raise M06RewardReferenceError("advanced_ticks must be in 0..128")
    if action["status"] not in {"SUCCESS", "NO_OP", "NATIVE_REJECTED"}:
        raise M06RewardReferenceError("only accepted M05 outcomes can form a reward transition")
    commands = action["native_commands"]
    if not isinstance(commands, list):
        raise M06RewardReferenceError("native_commands must be an array")
    capital_spend = 0
    for index, command in enumerate(commands):
        if not isinstance(command, dict) or "cost" not in command:
            raise M06RewardReferenceError(f"native_commands[{index}] lacks cost")
        cost = _integer(command["cost"], f"native_commands[{index}].cost")
        capital_spend += max(cost, 0)

    return {
        "delivered_passengers_delta": post["delivered_passengers_total"] - pre["delivered_passengers_total"],
        "operating_profit_delta": (
            post["operating_income_total"]
            + post["operating_expenses_total"]
            - pre["operating_income_total"]
            - pre["operating_expenses_total"]
        ),
        "capital_spend": capital_spend,
        "noop": int(action["status"] == "NO_OP"),
        "native_rejected": int(action["status"] == "NATIVE_REJECTED"),
        "idle_bus_ticks": post["stopped_primary_bus_count"] * ticks,
        "vehicle_loss_count": max(pre["primary_bus_count"] - post["primary_bus_count"], 0),
        "bankruptcy": int(pre["company_present"] and not post["company_present"]),
    }


def compute_reward(raw: dict[str, Any], contract: dict[str, Any]) -> RewardResult:
    components = contract["reward"]["components"]
    expected = {item["raw_field"] for item in components}
    _keys(raw, expected, "raw reward")
    raw_values: list[int] = []
    clamped_values: list[int] = []
    weighted_values: list[float] = []
    scalar = 0.0
    for item in components:
        value = _integer(raw[item["raw_field"]], item["raw_field"])
        if item["raw_unit"] == "indicator" and value not in (0, 1):
            raise M06RewardReferenceError(f"{item['raw_field']} indicator must be zero or one")
        clamped = min(max(value, item["raw_min"]), item["raw_max"])
        weighted = clamped * item["coefficient_numerator"] / item["coefficient_denominator"]
        if not math.isfinite(weighted):
            raise M06RewardReferenceError(f"{item['component_id']} produced a nonfinite value")
        scalar += weighted
        if not math.isfinite(scalar):
            raise M06RewardReferenceError("scalar reward became nonfinite")
        raw_values.append(value)
        clamped_values.append(clamped)
        weighted_values.append(weighted)
    return RewardResult(tuple(raw_values), tuple(clamped_values), tuple(weighted_values), scalar)


def classify_termination(
    contract: dict[str, Any],
    *,
    failure_reason: str | None = None,
    bankruptcy: bool = False,
    solved: bool = False,
    user_cancelled: bool = False,
    action_horizon: bool = False,
    tick_horizon: bool = False,
) -> TerminationResult:
    flags = (bankruptcy, solved, user_cancelled, action_horizon, tick_horizon)
    if any(not isinstance(value, bool) for value in flags):
        raise M06RewardReferenceError("termination inputs must be booleans")
    reason_map = {item["name"]: item for item in contract["termination"]["reasons"]}
    failures = {name for name, item in reason_map.items() if item["kind"] == "FAILURE"}
    if failure_reason is not None and failure_reason not in failures:
        raise M06RewardReferenceError(f"unknown failure reason {failure_reason!r}")
    if failure_reason is not None:
        reason = failure_reason
    elif bankruptcy:
        reason = "BANKRUPTCY"
    elif solved:
        if contract["termination"]["solved_threshold"] is None:
            raise M06RewardReferenceError("SOLVED is disabled by the frozen foundation")
        reason = "SOLVED"
    elif user_cancelled:
        reason = "USER_CANCELLED"
    elif action_horizon and tick_horizon:
        reason = "ACTION_AND_TICK_HORIZON"
    elif action_horizon:
        reason = "ACTION_HORIZON"
    elif tick_horizon:
        reason = "TICK_HORIZON"
    else:
        reason = "NONE"
    item = reason_map[reason]
    return TerminationResult(
        reason,
        item["kind"],
        item["terminal"],
        item["truncated"],
        item["bootstrap"],
        item["trainable"],
    )


def float64_bits(value: float) -> str:
    if not isinstance(value, float) or not math.isfinite(value):
        raise M06RewardReferenceError("trajectory float must be a finite float64")
    return struct.pack("<d", value).hex()


def record_sha256(record: dict[str, Any]) -> str:
    payload = copy.deepcopy(record)
    payload.pop("integrity_sha256", None)
    try:
        encoded = canonical_bytes(payload)
    except (TypeError, ValueError) as exc:
        raise M06RewardReferenceError(f"trajectory record is not finite canonical JSON: {exc}") from exc
    return hashlib.sha256(encoded).hexdigest()


def rollout_shuffle_seed(*, run_seed: int, rollout_id: int, update_index: int) -> int:
    values = {"rollout_id": rollout_id, "run_seed": run_seed, "update_index": update_index}
    for name, value in values.items():
        if _integer(value, name) < 0 or value > (1 << 64) - 1:
            raise M06RewardReferenceError(f"{name} must fit uint64")
    digest = hashlib.sha256(canonical_bytes(values)).digest()
    return int.from_bytes(digest[:8], "little")


__all__ = [
    "M06RewardContractError",
    "M06RewardReferenceError",
    "RewardResult",
    "TerminationResult",
    "classify_termination",
    "compute_reward",
    "derive_raw",
    "float64_bits",
    "record_sha256",
    "rollout_shuffle_seed",
]
