"""Read-only structural/economic invariants for PORT-005 test projections."""

from __future__ import annotations

from collections import Counter
from typing import Any


class InvariantError(ValueError):
    pass


def validate_pool(pool: dict[str, Any], references: list[int] | None = None) -> None:
    required = {"capacity", "storage_capacity", "first_free", "first_unused", "occupied_count", "bitmap_word_count", "bitmap_words", "next_id"}
    if set(pool) != required:
        raise InvariantError("P005-INV-POOL-SHAPE")
    capacity = pool["capacity"]
    storage_capacity = pool["storage_capacity"]
    first_free = pool["first_free"]
    first_unused = pool["first_unused"]
    words = pool["bitmap_words"]
    if not all(isinstance(value, int) for value in (capacity, storage_capacity, first_free, first_unused, pool["occupied_count"], pool["bitmap_word_count"])):
        raise InvariantError("P005-INV-POOL-TYPE")
    if not 0 <= first_free <= first_unused <= storage_capacity <= capacity:
        raise InvariantError("P005-INV-POOL-BOUNDS")
    if pool["bitmap_word_count"] != len(words) or len(words) != (storage_capacity + 63) // 64:
        raise InvariantError("P005-INV-POOL-WORD-COUNT")
    if any(not isinstance(word, int) or not 0 <= word <= 0xFFFFFFFFFFFFFFFF for word in words):
        raise InvariantError("P005-INV-POOL-WORD-WIDTH")
    if storage_capacity % 64 and words:
        required_padding = ((1 << 64) - 1) ^ ((1 << (storage_capacity % 64)) - 1)
        if words[-1] & required_padding != required_padding:
            raise InvariantError("P005-INV-POOL-HIGH-PADDING")
    occupied = [slot for slot in range(first_unused) if words[slot // 64] & (1 << (slot % 64))]
    if pool["occupied_count"] != len(occupied):
        raise InvariantError("P005-INV-POOL-COUNT")
    if any(not (words[slot // 64] & (1 << (slot % 64))) for slot in range(first_free)):
        raise InvariantError("P005-INV-POOL-FIRST-FREE-PREFIX")
    next_id = None
    for slot in range(first_free, storage_capacity):
        if not (words[slot // 64] & (1 << (slot % 64))):
            next_id = slot
            break
    if next_id is None and first_unused < capacity:
        next_id = first_unused
    if pool["next_id"] != next_id:
        raise InvariantError("P005-INV-POOL-NEXT-ID")
    if references is not None and any(ref not in occupied for ref in references):
        raise InvariantError("P005-INV-POOL-DANGLING-REFERENCE")


def validate_cargo(snapshot: dict[str, Any]) -> None:
    required = {"produced", "delivered", "destroyed", "packets", "containers", "ledger_delivery_units"}
    if set(snapshot) != required:
        raise InvariantError("P005-INV-CARGO-SHAPE")
    packets = snapshot["packets"]
    ids = [packet["id"] for packet in packets]
    if len(ids) != len(set(ids)):
        raise InvariantError("P005-INV-CARGO-PACKET-ID")
    amounts: dict[int, int] = {}
    for packet in packets:
        if set(packet) != {"id", "amount", "source_id", "source_type", "periods_in_transit"}:
            raise InvariantError("P005-INV-CARGO-PACKET-SHAPE")
        if packet["amount"] < 0 or packet["amount"] > 65535:
            raise InvariantError("P005-INV-CARGO-AMOUNT")
        if packet["source_id"] < 0 or packet["source_type"] < 0 or packet["periods_in_transit"] < 0:
            raise InvariantError("P005-INV-CARGO-PROVENANCE")
        amounts[packet["id"]] = packet["amount"]
    flattened: list[int] = []
    for owner in sorted(snapshot["containers"]):
        chain = snapshot["containers"][owner]
        flattened.extend(chain)
    counts = Counter(flattened)
    if any(count != 1 for count in counts.values()) or set(flattened) != set(ids):
        raise InvariantError("P005-INV-CARGO-CONTAINER-ORDER")
    in_flight = sum(amounts.values())
    if snapshot["produced"] != in_flight + snapshot["delivered"] + snapshot["destroyed"]:
        raise InvariantError("P005-INV-CARGO-CONSERVATION")
    if snapshot["ledger_delivery_units"] != snapshot["delivered"]:
        raise InvariantError("P005-INV-CARGO-LEDGER")


def validate_ledger(before: int, after: int, categorized_deltas: list[int], adjustment: int = 0) -> None:
    if after - before != sum(categorized_deltas) + adjustment:
        raise InvariantError("P005-INV-LEDGER-BALANCE")


def validate_timer_rng(before: dict[str, int], after: dict[str, int], expected_tick_delta: int) -> None:
    keys = {"tick", "calendar_date", "calendar_fraction", "economy_date", "economy_fraction", "rng0", "rng1", "interactive0", "interactive1"}
    if set(before) != keys or set(after) != keys:
        raise InvariantError("P005-INV-TIMER-SHAPE")
    if after["tick"] - before["tick"] != expected_tick_delta:
        raise InvariantError("P005-INV-TIMER-TICK")
    if expected_tick_delta == 0 and before != after:
        raise InvariantError("P005-INV-DIAGNOSTIC-PERTURBATION")
    if any(not 0 <= after[key] <= 0xFFFFFFFF for key in ("rng0", "rng1", "interactive0", "interactive1")):
        raise InvariantError("P005-INV-RNG-WIDTH")
