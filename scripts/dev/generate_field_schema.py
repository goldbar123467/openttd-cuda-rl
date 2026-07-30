#!/usr/bin/env python3
"""Generate the reviewed PORT-005 field registry and C17 metadata table.

The compact source table in this file is deliberately hand reviewed.  The
generated JSON expands every row to the complete entry contract from section
19.3 of the P0 execution contract and resolves source-line diagnostics against
the pinned OpenTTD checkout.  Line numbers are diagnostic; the file and symbol
are the stable source anchors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PIN = "29f808ef0022064e6d9a83c8476d1e0f4686af86"
ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / "openttd-upstream"
DEV = Path(__file__).resolve().parent
SCHEMA_OUT = ROOT / "parity" / "schema"
INCLUDE_OUT = ROOT / "parity" / "include" / "openttd_rl_parity"
SOURCE_OUT = ROOT / "parity" / "src"

TYPE_NUMBER = {
    "u8": (8, "unsigned", 1),
    "u16": (16, "unsigned", 2),
    "u32": (32, "unsigned", 3),
    "u64": (64, "unsigned", 4),
    "i8": (8, "signed", 5),
    "i16": (16, "signed", 6),
    "i32": (32, "signed", 7),
    "i64": (64, "signed", 8),
    "bytes": (None, None, 9),
    "stable_id": (32, "unsigned", 10),
    "bitset": (None, None, 11),
    "diagnostic_utf8": (None, None, 12),
}

FIELDS: list[dict[str, Any]] = []


def field(
    field_id: int,
    path: str,
    value_type: str,
    source_file: str,
    source_symbol: str,
    description: str,
    rationale: str,
    *,
    owner: str = "game",
    owner_rule: str = "singleton experiment identity",
    shape: str = "scalar",
    fixed_count: int | None = 1,
    count_source: str | None = None,
    maximum_capacity: int = 1,
    order: str = "single value",
    sample: int | str | list[int] = 0,
    sample_scope: str = "complete_value",
    lifecycle_start: str = "fixture load completed",
    lifecycle_end: str = "authoritative run terminates",
    reached: str = "reached",
    cache: str = "not_cache",
    invalidation: str = "not_applicable",
    rebuild: str = "not_applicable",
    reached_path: str = "GameLoop -> StateGameLoop -> authoritative boundary adapter",
    classification: str = "authoritative_full",
    width_override: int | None = None,
) -> None:
    width, signedness, tape_type = TYPE_NUMBER[value_type]
    if width_override is not None:
        width = width_override
    FIELDS.append(
        {
            "field_id": field_id,
            "path": path,
            "value_type": value_type,
            "tape_value_type_id": tape_type,
            "source_file": source_file,
            "source_symbol": source_symbol,
            "description": description,
            "future_influence_rationale": rationale,
            "owner_type": owner,
            "owner_stable_id_rule": owner_rule,
            "shape": shape,
            "fixed_count": fixed_count,
            "count_source_field": count_source,
            "maximum_capacity": maximum_capacity,
            "canonical_element_order": order,
            "sample_logical_value": sample,
            "sample_scope": sample_scope,
            "lifecycle_start": lifecycle_start,
            "lifecycle_end": lifecycle_end,
            "fixture_reachability_status": reached,
            "cache_classification": cache,
            "cache_invalidation_trigger": invalidation,
            "deterministic_rebuild_procedure": rebuild,
            "reached_call_path": reached_path,
            "classification": classification,
            "width_bits": width,
            "signedness": signedness,
        }
    )


def scalar_group(
    start: int,
    prefix: str,
    source_file: str,
    owner: str,
    owner_rule: str,
    rows: list[tuple[str, str, str, int, str]],
    rationale_prefix: str,
    reached_path: str,
) -> None:
    for offset, (suffix, typ, symbol, sample, description) in enumerate(rows):
        field(
            start + offset,
            f"{prefix}.{suffix}",
            typ,
            source_file,
            symbol,
            description,
            f"{rationale_prefix} {description} A mismatch can change a subsequent branch, ordering decision, accounting value, or deterministic identifier.",
            owner=owner,
            owner_rule=owner_rule,
            sample=sample,
            reached_path=reached_path,
        )


def pool_meta(start: int, prefix: str, capacity: int, pool_symbol: str, reached: str = "reached") -> None:
    source = "src/core/pool_type.hpp"
    owner = f"{prefix}_pool"
    rule = "pool identity is the typed numeric slot index; pointer values are forbidden"
    rows = [
        ("occupied_count", "u32", "size_t items", 0, "Number of occupied typed pool slots."),
        ("first_free", "u32", "size_t first_free", 0, "Lowest slot from which native allocation scans for a free entry."),
        ("first_unused", "u32", "size_t first_unused", 0, "Exclusive high-water slot; all higher slots are unallocated."),
    ]
    scalar_group(start, f"{prefix}.pool", source, owner, rule, rows,
                 f"The {pool_symbol} allocation cursor is continuation state.",
                 f"{pool_symbol} -> Pool::Allocate -> authoritative boundary adapter")
    word_count_id = 12531 if prefix == "linkgraph" else start + 5
    field(word_count_id, f"{prefix}.pool.bitmap_word_count", "u32", source, "std::vector<BitmapStorage> used_bitmap",
          "Exact native used_bitmap vector word count.",
          "Vector length and trailing or padding words alter FindFirstFree scanning and cannot be inferred from occupied logical slots.",
          owner=owner, owner_rule=rule, sample=0,
          reached_path=f"{pool_symbol} -> Pool::FindFirstFree -> authoritative boundary adapter")
    field(start + 3, f"{prefix}.pool.occupancy_bitmap", "u64", source, "std::vector<BitmapStorage> used_bitmap",
          "Exact native used_bitmap words, including trailing words and high padding bits.",
          "Pool iteration, validity and exact ID allocation depend on the frozen x86-64 BitmapStorage word sequence and vector length.",
          owner=owner, owner_rule=rule, shape="dynamic_array", fixed_count=None,
          count_source=f"{prefix}.pool.bitmap_word_count", maximum_capacity=(capacity + 63) // 64,
          order="native used_bitmap word index ascending; within each U64, slot bit index ascending", sample=[0], sample_scope="one_element",
          reached=reached, reached_path=f"{pool_symbol} -> Pool::IsValidID -> authoritative boundary adapter")
    field(start + 4, f"{prefix}.pool.native_free_list", "u32", source, "first_free",
          "Proof entry for a native pool free-list or stored free-slot order.",
          "PoolBase stores first_free, first_unused and occupancy only; allocation scans those values and no separate free-list state exists.",
          owner=owner, owner_rule=rule, shape="scalar", fixed_count=1,
          count_source=None, maximum_capacity=1,
          order="single source-backed absence proof",
          sample=0, sample_scope="complete_value", reached="unreachable_absent-from-pinned-PoolBase-storage",
          classification="out_of_scope_unreachable",
          reached_path=f"{pool_symbol} -> Pool::Allocate -> authoritative boundary adapter")


# Experiment and terminal state.
scalar_group(1, "experiment", "src/openttd.cpp", "experiment", "singleton run identity", [
    ("game_mode", "u8", "_game_mode", 1, "Native GameMode value controlling simulation and command legality."),
    ("pause_modes", "u8", "_pause_mode", 0, "Native pause-mode bitset controlling advancement and command legality."),
    ("current_company", "u8", "_current_company", 0, "Company context used by native command execution."),
    ("terminal_state", "u8", "_exit_game", 0, "Terminal-state code sampled before accepting another boundary."),
    ("fault_state", "u8", "_switch_mode", 0, "Pending mode transition or fault-recovery state affecting the next loop."),
], "Global run control is read by command and tick dispatch.", "GameLoop -> StateGameLoop")

# Clocks, deterministic cursors, and both RNG streams.
scalar_group(1000, "time", "src/saveload/misc_sl.cpp", "game_clock", "singleton gameplay clock", [
    ("tick_counter", "u64", "TimerGameTick::counter", 0, "Authoritative game-tick counter."),
    ("calendar_date", "i32", "TimerGameCalendar::date", 712223, "Internal calendar date."),
    ("calendar_fraction", "u16", "TimerGameCalendar::date_fract", 0, "Sub-day calendar fraction."),
    ("economy_date", "i32", "TimerGameEconomy::date", 712223, "Internal economy date."),
    ("economy_fraction", "u16", "TimerGameEconomy::date_fract", 0, "Sub-day economy fraction."),
], "Tick and date state chooses periodic callbacks and age/payment inputs.", "StateGameLoop -> TimerGameTick::counter -> CalendarTimer::Elapsed")
scalar_group(1010, "timer", "src/saveload/misc_sl.cpp", "timer_manager", "fixed semantic timer tag, never registration address", [
    ("tile_loop_cursor", "u32", "_cur_tileloop_tile", 0, "Persistent next tile-loop cursor."),
    ("company_loop_cursor", "u32", "_cur_company_tick_index", 0, "Persistent company-loop cursor."),
], "Persistent cursors and timer phases select which object is updated next.", "StateGameLoop -> timer managers -> subsystem loops")
field(1012, "timer.industry_daily_phase", "u16", "src/industry_cmd.cpp", "_economy_industries_daily",
      "Semantic phase of the daily industry timer relative to the economy clock.",
      "The reached timer callback creates cargo and can consume RNG; the semantic phase makes its exact boundary explicit.",
      owner="timer_manager", owner_rule="fixed semantic timer tag industry.daily", sample=0,
      reached_path="TimerGameEconomy -> _economy_industries_daily -> IndustryDailyLoop")
field(1013, "timer.station_monthly_phase", "u16", "src/station_cmd.cpp", "_economy_stations_monthly",
      "Semantic phase of the monthly station timer relative to the economy clock.",
      "Station rating and cargo bookkeeping callback order affects subsequent loading and delivery.",
      owner="timer_manager", owner_rule="fixed semantic timer tag station.monthly", sample=0,
      reached_path="TimerGameEconomy -> _economy_stations_monthly -> station monthly loop")
field(1014, "timer.pending_callback_tags", "u64", "src/timer/timer_manager.h", "class TimerManager",
      "Semantic bitset of reached timer callbacks pending at the boundary.",
      "Callback semantic order must be compared without serializing registration addresses.",
      owner="timer_manager", owner_rule="fixed semantic timer tag, never registration address",
      shape="scalar", fixed_count=1, count_source=None, maximum_capacity=1, sample=0,
      reached_path="TimerManager::Elapsed -> semantic callback tag adapter")
for item in FIELDS:
    if item["field_id"] in {1012, 1013, 1014}:
        item["classification"] = "diagnostic"
        item["future_influence_rationale"] = "This semantic callback-phase diagnostic is derived from persistent clocks and static timer registration; it is not native stored continuation state."

# The town and station spatial K-d trees are reached gameplay indices.  They
# are deliberately authoritative in v1: native insertion/removal and range
# traversal depend on exact node shape, free-slot stack order, root and the
# rebalance counter.  Rebuilding merely from pool membership is not accepted
# as equivalent without the two-load and 10,000-tick experiment required by
# the contract.
def kdtree_fields(start: int, prefix: str, owner: str, reached_path: str) -> None:
    source = "src/core/kdtree.hpp"
    invalid_index = 0xFFFFFFFFFFFFFFFF
    common = {
        "owner": owner,
        "owner_rule": f"singleton {prefix}; node/free-list positions are zero-based native vector indices",
        "cache": "authoritative_cache",
        "invalidation": "Kdtree::Build, Insert, Remove, Clear, and Rebuild mutate nodes, free_list, root, or unbalanced",
        "rebuild": "not_applicable; v1 serializes the reached cache exactly and makes no derived-rebuild claim",
        "reached_path": reached_path,
    }
    field(start, f"cache.{prefix}.node_count", "u64", source, "std::vector<node> nodes;",
          "Exact native node-vector size, including reusable dead slots.",
          "The vector size bounds child indices and determines whether AddNode appends after the free-slot stack is exhausted.",
          sample=0, **common)
    field(start + 1, f"cache.{prefix}.free_count", "u64", source, "std::vector<size_t> free_list;",
          "Exact native free-list vector size.",
          "Kdtree::Count and AddNode depend on this size, and the vector contents form a LIFO reuse stack.",
          sample=0, **common)
    field(start + 2, f"cache.{prefix}.node_elements", "stable_id", source, "T      element;",
          "Element stored in every native node-vector slot, including dead slots.",
          "Live element placement controls split comparisons and traversal order; dead slots are retained so the exact native vector state is explicit.",
          shape="dynamic_array", fixed_count=None, count_source=f"cache.{prefix}.node_count", maximum_capacity=64000,
          order="native nodes vector index ascending", sample=[0], sample_scope="one_element", **common)
    field(start + 3, f"cache.{prefix}.node_left_indices", "u64", source, "size_t left;",
          "Left-child index of every native node-vector slot; SIZE_MAX means absent.",
          "Tree shape changes traversal and rebuild behavior, so child indices are continuation state.",
          shape="dynamic_array", fixed_count=None, count_source=f"cache.{prefix}.node_count", maximum_capacity=64000,
          order="native nodes vector index ascending", sample=[invalid_index], sample_scope="one_element", **common)
    field(start + 4, f"cache.{prefix}.node_right_indices", "u64", source, "size_t right;",
          "Right-child index of every native node-vector slot; SIZE_MAX means absent.",
          "Tree shape changes traversal and rebuild behavior, so child indices are continuation state.",
          shape="dynamic_array", fixed_count=None, count_source=f"cache.{prefix}.node_count", maximum_capacity=64000,
          order="native nodes vector index ascending", sample=[invalid_index], sample_scope="one_element", **common)
    field(start + 5, f"cache.{prefix}.free_indices", "u64", source, "std::vector<size_t> free_list;",
          "Exact free node indices in native vector order.",
          "AddNode pops the back of this vector; preserving only the free set would change future slot reuse and tree shape.",
          shape="dynamic_array", fixed_count=None, count_source=f"cache.{prefix}.free_count", maximum_capacity=64000,
          order="native free_list order from front to back; the last element is reused first", sample=[0], sample_scope="one_element", **common)
    field(start + 6, f"cache.{prefix}.root_index", "u64", source, "size_t root;",
          "Exact raw native root node index; SIZE_MAX is the constructor value, while Clear or an empty Build may retain an ignored stale index.",
          "Non-empty lookup, insertion, removal, and invariant traversal begin from this index; preserving the raw value also avoids inventing normalization not present in pinned source.",
          sample=invalid_index, **common)
    field(start + 7, f"cache.{prefix}.unbalanced_count", "u64", source, "size_t unbalanced;",
          "Exact native approximate imbalance counter.",
          "Kdtree::IsUnbalanced uses this counter to decide whether the next insertion or removal rebuilds the tree.",
          sample=0, **common)


kdtree_fields(
    10030,
    "town_kdtree",
    "TownKdtree _town_kdtree",
    "fixture town construction/load -> RebuildTownKdtree; station construction -> ClosestTownFromTile -> TownKdtree::FindNearest",
)
kdtree_fields(
    10040,
    "station_kdtree",
    "StationKdtree _station_kdtree",
    "fixture load -> RebuildStationKdtree; road-stop station creation/move -> StationKdtree::Insert/Remove and area queries",
)
field(1015, "time.calendar_year", "i32", "src/timer/timer_game_calendar.cpp", "TimerGameCalendar::Year TimerGameCalendar::year",
      "Stored calendar year.", "Native callbacks and age logic read the stored calendar year directly.", sample=1950,
      reached_path="TimerGameCalendar::SetDate/Elapsed -> calendar callbacks")
field(1016, "time.calendar_month", "u8", "src/timer/timer_game_calendar.cpp", "TimerGameCalendar::Month TimerGameCalendar::month",
      "Stored calendar month.", "Native month rollover and callbacks read the stored calendar month.", sample=0,
      reached_path="TimerGameCalendar::SetDate/Elapsed -> calendar callbacks")
field(1017, "time.calendar_sub_fraction", "u16", "src/timer/timer_game_calendar.cpp", "TimerGameCalendar::sub_date_fract",
      "Stored calendar sub-date fraction.", "Non-default calendar pacing accumulates this remainder before advancing date_fract.", sample=0,
      reached_path="TimerManager<TimerGameCalendar>::Elapsed -> sub_date_fract")
field(1018, "time.economy_year", "i32", "src/timer/timer_game_economy.cpp", "TimerGameEconomy::Year TimerGameEconomy::year",
      "Stored economy year.", "Industry, company and engine periodic behavior reads the stored economy year.", sample=1950,
      reached_path="TimerGameEconomy::SetDate/Elapsed -> economy callbacks")
field(1019, "time.economy_month", "u8", "src/timer/timer_game_economy.cpp", "TimerGameEconomy::Month TimerGameEconomy::month",
      "Stored economy month.", "Monthly callbacks and history rollover read the stored economy month.", sample=0,
      reached_path="TimerGameEconomy::SetDate/Elapsed -> economy callbacks")
field(1020, "time.economy_days_since_last_month", "u32", "src/timer/timer_game_economy.cpp", "days_since_last_month",
      "Economy days accumulated since the prior month.", "Economy month rollover depends on this persistent counter.", sample=0,
      reached_path="TimerManager<TimerGameEconomy>::Elapsed -> month rollover")
scalar_group(1021, "timer.competitor_timeout", "src/saveload/misc_sl.cpp", "TimeoutTimer<TimerGameTick>", "singleton competitor timeout", [
    ("period_value", "u32", "_new_competitor_timeout.period.value", 0, "Competitor timeout period in ticks."),
    ("elapsed", "u32", "_new_competitor_timeout.storage.elapsed", 0, "Elapsed ticks in competitor timeout."),
    ("fired", "u8", "_new_competitor_timeout.fired", 1, "Competitor timeout fired state."),
], "Even with zero competitors, native timeout state is saved and controls AI-start checks.",
"CompanyTick -> _new_competitor_timeout -> MaybeStartNewCompany")
field(1024, "timer.competitor_timeout.priority", "u8", "src/company_cmd.cpp", "TimerGameTick::Priority::CompetitorTimeout",
      "Static semantic priority stored in the timeout period.", "Timer manager callback ordering compares this priority before the period value.", sample=1,
      reached_path="TimerManager<TimerGameTick> -> _new_competitor_timeout")
scalar_group(1025, "timer.saved", "src/saveload/misc_sl.cpp", "misc saved timer state", "singleton subsystem state", [
    ("cargo_age_skip_counter", "u8", "_age_cargo_skip_counter", 0, "Legacy-compatible cargo aging phase counter."),
    ("disaster_delay", "u16", "_disaster_delay", 0, "Next disaster delay, retained even when disasters are disabled."),
    ("tree_loop_counter", "u8", "_trees_tick_ctr", 0, "Persistent tree-loop phase counter."),
], "Saved native counters can change which subsystem work occurs at a subsequent tick.",
"StateGameLoop -> cargo age/disaster/tree loops")
scalar_group(1030, "rng.gameplay", "src/core/random_func.hpp", "Randomizer", "singleton gameplay RNG stream", [
    ("state0", "u32", "uint32_t state[2]", 1536594464, "First internal gameplay randomizer word."),
    ("state1", "u32", "uint32_t state[2]", 1985458814, "Second internal gameplay randomizer word."),
], "The next gameplay random draw is a pure function of both words.", "Random -> _random -> InteractiveRandomRange")
scalar_group(1032, "rng.interactive", "src/core/random_func.hpp", "Randomizer", "singleton interactive RNG stream", [
    ("state0", "u32", "uint32_t state[2]", 1230128689, "First internal interactive randomizer word."),
    ("state1", "u32", "uint32_t state[2]", 1230128689, "Second internal interactive randomizer word."),
], "Instrumentation must prove it does not consume either native random stream.", "InteractiveRandom -> _interactive_random")
scalar_group(1040, "economy", "src/economy_type.h", "Economy", "singleton native economy", [
    ("maximum_loan", "i64", "Money max_loan", 300000, "Runtime maximum loan after inflation and rounding."),
    ("fluctuation", "i16", "int16_t fluct", 0, "Economy fluctuation status."),
    ("interest_rate", "u8", "uint8_t interest_rate", 2, "Monthly loan interest rate."),
    ("inflation_amount_prices", "u8", "uint8_t infl_amount", 0, "Price inflation increment."),
    ("inflation_amount_payments", "u8", "uint8_t infl_amount_pr", 0, "Cargo-payment inflation increment."),
    ("industry_daily_change_counter", "u32", "industry_daily_change_counter", 0, "Persistent industry daily selection accumulator."),
    ("industry_daily_increment", "u32", "industry_daily_increment", 0, "Stored computed increment for industry daily selection."),
    ("inflation_prices", "u64", "uint64_t inflation_prices", 65536, "Accumulated price inflation with 16 fractional bits."),
    ("inflation_payments", "u64", "uint64_t inflation_payment", 65536, "Accumulated cargo-payment inflation with 16 fractional bits."),
], "Runtime economy members control command prices, payments, interest, loan limits and industry callback scheduling.",
"EconomyMonthlyLoop/IndustryDailyLoop -> RecomputePrices/DeliverGoods/industry selection")
for item in FIELDS:
    if item["path"] == "economy.industry_daily_increment":
        item["cache_classification"] = "authoritative_cache"
        item["cache_invalidation_trigger"] = "industry pool size, economy calendar scale, or economy settings change"
        item["deterministic_rebuild_procedure"] = "not claimed; retained until two-load 10000-tick continuation evidence proves recomputation"
field(1050, "economy.runtime_price_table", "i64", "src/economy.cpp", "Prices _price",
      "Runtime Price table for every Price ordinal through Price::End.",
      "Native commands, vehicle running costs and infrastructure maintenance read this table directly.",
      owner="economy", owner_rule="singleton Price ordinal table", shape="fixed_array", fixed_count=71,
      maximum_capacity=71, order="Price ordinal ascending from StationValue through InfrastructureAirport",
      sample=[0], sample_scope="one_element", cache="authoritative_cache",
      invalidation="inflation, difficulty, price-base multiplier or NewGRF property recomputation",
      rebuild="not claimed; retained until two-load 10000-tick continuation evidence proves recomputation",
      reached_path="GetPrice/direct _price consumer -> command/economy branch")
field(1051, "economy.price_base_multipliers", "i8", "src/economy.cpp", "PriceMultipliers _price_base_multiplier",
      "Runtime price-base shift multiplier for every Price ordinal.",
      "RecomputePrices reads these mutable runtime multipliers; settings and content identity do not encode their current table bytes.",
      owner="economy", owner_rule="singleton Price ordinal table", shape="fixed_array", fixed_count=71,
      maximum_capacity=71, order="Price ordinal ascending from StationValue through InfrastructureAirport",
      sample=[0], sample_scope="one_element", reached_path="SetPriceBaseMultiplier -> RecomputePrices -> _price")
field(1052, "economy.cargo_initial_payment", "i32", "src/cargotype.h", "int32_t initial_payment",
      "Initial payment rates for all native CargoType slots.",
      "Inflation recomputation uses this content-derived value to create future current payment rates.",
      owner="CargoSpec", owner_rule="CargoType numeric index 0 through NUM_CARGO-1", shape="fixed_array", fixed_count=64,
      maximum_capacity=64, order="CargoType ascending", sample=[0], sample_scope="one_element",
      reached_path="CargoSpec::Iterate -> RecomputePrices -> current_payment")
field(1053, "economy.cargo_current_payment", "i64", "src/cargotype.h", "Money current_payment",
      "Current inflated payment rates for all native CargoType slots.",
      "DeliverGoods reads the current payment value directly when calculating exact cargo income.",
      owner="CargoSpec", owner_rule="CargoType numeric index 0 through NUM_CARGO-1", shape="fixed_array", fixed_count=64,
      maximum_capacity=64, order="CargoType ascending", sample=[0], sample_scope="one_element",
      cache="authoritative_cache", invalidation="inflation or cargo specification recomputation",
      rebuild="not claimed; retained until two-load 10000-tick continuation evidence proves recomputation",
      reached_path="GetTransportedGoodsIncome -> CargoSpec::current_payment -> DeliverGoods")
field(1090, "rng.native_draw_counter", "u8", "src/core/random_func.hpp", "uint32_t Next();",
      "Proof entry for a native RNG draw counter.",
      "Pinned Randomizer stores only two state words and has no draw counter; optional draw diagnostics cannot be restored or treated as native state.",
      owner="Randomizer", owner_rule="gameplay or interactive singleton stream", sample=0,
      classification="out_of_scope_unreachable", reached="unreachable_absent_from-pinned-Randomizer-storage",
      reached_path="Randomizer::Next source-owner review")
field(1091, "timer.persistent_vehicle_loop_cursor", "u8", "src/vehicle.cpp", "Vehicle::Iterate()",
      "Proof entry for a persistent vehicle-loop cursor.",
      "Pinned vehicle ticks start a fresh stable pool iteration; no vehicle cursor survives a boundary.",
      owner="vehicle_loop", owner_rule="singleton subsystem", sample=0,
      classification="out_of_scope_unreachable", reached="unreachable_absent_from-pinned-vehicle-loop-storage",
      reached_path="CallVehicleTicks -> Vehicle::Iterate")

# Complete behavior-affecting runtime settings for the declared road-freight path.
SETTINGS = [
    ("difficulty.max_no_competitors", "u8", "max_no_competitors", 0, "Maximum AI company count."),
    ("difficulty.competitors_interval", "u16", "competitors_interval", 0, "Competitor creation interval."),
    ("difficulty.industry_density", "u8", "industry_density", 0, "Industry creation density."),
    ("difficulty.max_loan", "u32", "max_loan", 300000, "Maximum company loan."),
    ("difficulty.initial_interest", "u8", "initial_interest", 2, "Loan interest percentage."),
    ("difficulty.vehicle_costs", "u8", "vehicle_costs", 0, "Vehicle cost multiplier table."),
    ("difficulty.vehicle_breakdowns", "u8", "vehicle_breakdowns", 0, "Breakdown model selector."),
    ("difficulty.subsidy_multiplier", "u8", "subsidy_multiplier", 2, "Subsidized delivery multiplier."),
    ("difficulty.subsidy_duration", "u16", "subsidy_duration", 0, "Subsidy lifetime."),
    ("difficulty.construction_cost", "u8", "construction_cost", 0, "Construction cost multiplier table."),
    ("difficulty.disasters", "u8", "disasters", 0, "Disaster enable flag."),
    ("difficulty.infinite_money", "u8", "infinite_money", 0, "Affordability bypass flag."),
    ("game_creation.generation_seed", "u32", "generation_seed", 1380341297, "World generation seed."),
    ("game_creation.starting_year", "i32", "starting_year", 1950, "Starting calendar year."),
    ("game_creation.map_x", "u8", "map_x", 6, "Map X exponent."),
    ("game_creation.map_y", "u8", "map_y", 6, "Map Y exponent."),
    ("game_creation.landscape", "u8", "landscape", 0, "Landscape/climate selector."),
    ("game_creation.se_flat_world_height", "u8", "se_flat_world_height", 1, "Empty-world height."),
    ("construction.build_on_slopes", "u8", "build_on_slopes", 1, "Construction-on-slopes permission."),
    ("construction.autoslope", "u8", "autoslope", 1, "Automatic terraforming behavior."),
    ("construction.road_stop_on_town_road", "u8", "road_stop_on_town_road", 1, "Road-stop placement permission on town roads."),
    ("construction.road_stop_on_competitor_road", "u8", "road_stop_on_competitor_road", 1, "Road-stop placement permission on competitor roads."),
    ("construction.command_pause_level", "u8", "command_pause_level", 1, "Command classes allowed while paused."),
    ("ai.ai_in_multiplayer", "u8", "ai_in_multiplayer", 0, "AI creation permission."),
    ("pf.roadveh_queue", "u8", "roadveh_queue", 1, "Road-vehicle queueing model flag."),
    ("pf.yapf.max_search_nodes", "u32", "max_search_nodes", 10000, "Road pathfinder search-node bound."),
    ("pf.yapf.maximum_go_to_depot_penalty", "u32", "maximum_go_to_depot_penalty", 2000, "Maximum depot detour penalty."),
    ("pf.yapf.road_slope_penalty", "u32", "road_slope_penalty", 200, "Road uphill path penalty."),
    ("pf.yapf.road_curve_penalty", "u32", "road_curve_penalty", 100, "Road curve path penalty."),
    ("pf.yapf.road_crossing_penalty", "u32", "road_crossing_penalty", 300, "Road crossing path penalty."),
    ("pf.yapf.road_stop_penalty", "u32", "road_stop_penalty", 800, "Drive-through road-stop path penalty."),
    ("pf.yapf.road_stop_occupied_penalty", "u32", "road_stop_occupied_penalty", 800, "Occupied drive-through stop penalty."),
    ("pf.yapf.road_stop_bay_occupied_penalty", "u32", "road_stop_bay_occupied_penalty", 1500, "Occupied bay road-stop penalty."),
    ("order.improved_load", "u8", "improved_load", 1, "Improved loading selection flag."),
    ("order.gradual_loading", "u8", "gradual_loading", 1, "Gradual loading cadence flag."),
    ("order.selectgoods", "u8", "selectgoods", 1, "Cargo selection behavior."),
    ("order.no_servicing_if_no_breakdowns", "u8", "no_servicing_if_no_breakdowns", 1, "Automatic service suppression."),
    ("vehicle.roadveh_acceleration_model", "u8", "roadveh_acceleration_model", 0, "Road-vehicle acceleration model."),
    ("vehicle.roadveh_slope_steepness", "u8", "roadveh_slope_steepness", 7, "Road-vehicle slope force parameter."),
    ("vehicle.max_roadveh", "u16", "max_roadveh", 1, "Per-company road-vehicle limit."),
    ("vehicle.never_expire_vehicles", "u8", "never_expire_vehicles", 0, "Engine expiry override."),
    ("vehicle.road_side", "u8", "road_side", 1, "Road driving side."),
    ("economy.inflation", "u8", "inflation", 0, "Inflation enable flag."),
    ("economy.type", "u8", "EconomyType type", 2, "Economy production-change model."),
    ("economy.feeder_payment_share", "u8", "feeder_payment_share", 75, "Transfer feeder-payment percentage."),
    ("economy.give_money", "u8", "give_money", 1, "Company transfer command permission."),
    ("economy.town_growth_rate", "u8", "town_growth_rate", 0, "Town growth rate selector."),
    ("economy.allow_town_roads", "u8", "allow_town_roads", 0, "Town road construction permission."),
    ("economy.infrastructure_maintenance", "u8", "infrastructure_maintenance", 0, "Infrastructure maintenance charging flag."),
    ("economy.timekeeping_units", "u8", "timekeeping_units", 0, "Economy/calendar timekeeping mode."),
    ("economy.minutes_per_calendar_year", "u16", "minutes_per_calendar_year", 12, "Calendar progression rate."),
    ("economy.industry_cargo_scale", "u16", "industry_cargo_scale", 100, "Industry production scaling percentage."),
    ("economy.cargo_aging_rate", "u8", "cargo_aging_rate", 100, "Cargo aging/payment scaling percentage."),
    ("linkgraph.recalc_time", "u16", "recalc_time", 64, "Runtime LinkGraph calculation duration after native day-to-second conversion."),
    ("linkgraph.recalc_interval", "u16", "recalc_interval", 16, "Runtime LinkGraph recalculation interval after native day-to-second conversion."),
    ("linkgraph.distribution_pax", "u8", "distribution_pax", 0, "Passenger distribution mode."),
    ("linkgraph.distribution_mail", "u8", "distribution_mail", 0, "Mail distribution mode."),
    ("linkgraph.distribution_armoured", "u8", "distribution_armoured", 0, "Armoured cargo distribution mode."),
    ("linkgraph.distribution_default", "u8", "distribution_default", 0, "Default cargo distribution mode."),
    ("linkgraph.accuracy", "u8", "accuracy", 16, "LinkGraph solver accuracy."),
    ("linkgraph.demand_size", "u8", "demand_size", 100, "LinkGraph supply weight."),
    ("linkgraph.demand_distance", "u8", "demand_distance", 100, "LinkGraph distance weight."),
    ("linkgraph.short_path_saturation", "u8", "short_path_saturation", 80, "Short-path saturation threshold."),
    ("station.modified_catchment", "u8", "modified_catchment", 0, "Catchment model selector."),
    ("station.serve_neutral_industries", "u8", "serve_neutral_industries", 1, "Neutral-industry service permission."),
    ("station.station_spread", "u8", "station_spread", 12, "Maximum station spread."),
]
scalar_group(2000, "settings", "src/settings_type.h", "GameSettings/CompanySettings", "singleton settings object or company ID", SETTINGS,
             "This frozen behavior-affecting setting is read by the declared command, movement, loading, payment, or timer path.",
             "_settings_game/_settings_client.company -> reached native consumer")
field(2099, "settings.native_revision_counter", "u8", "src/settings_type.h", "struct GameSettings",
      "Proof entry for a native settings revision counter.",
      "Pinned GameSettings stores values directly and has no persistent revision member; every reached behavior value is projected instead.",
      owner="GameSettings", owner_rule="singleton game settings", sample=0,
      classification="out_of_scope_unreachable", reached="unreachable_absent-from-pinned-GameSettings-storage",
      reached_path="GameSettings source-owner member review")
field(2098, "settings.vehicle.smoke_amount", "u8", "src/settings_type.h", "uint8_t smoke_amount",
      "Gameplay smoke/effect spawn intensity.",
      "RoadVehController calls ShowVisualEffect; this setting controls gameplay RNG draws and EffectVehicle allocation in the shared VehiclePool.",
      owner="GameSettings", owner_rule="singleton game settings", sample=2,
      reached_path="RoadVehController -> Vehicle::ShowVisualEffect -> Chance16/CreateEffectVehicleRel")

# Map dimensions and every native plane, not semantic reconstruction.
scalar_group(3000, "map", "src/map.cpp", "map", "singleton map", [
    ("size_x", "u32", "Map::size_x", 64, "Native map X dimension."),
    ("size_y", "u32", "Map::size_y", 64, "Native map Y dimension."),
    ("size", "u32", "Map::size", 4096, "Native tile count."),
    ("tile_mask", "u32", "Map::tile_mask", 4095, "Native map index mask."),
], "Dimensions bound every map access and tile index.", "Map::Allocate -> Map::Iterate")
for off, (name, typ, symbol, sample) in enumerate([
    ("type", "u8", "uint8_t type", 0), ("height", "u8", "uint8_t height", 1),
    ("m1", "u8", "uint8_t m1", 0), ("m2", "u16", "uint16_t m2", 0),
    ("m3", "u8", "uint8_t m3", 0), ("m4", "u8", "uint8_t m4", 0),
    ("m5", "u8", "uint8_t m5", 0), ("m6", "u8", "uint8_t m6", 0),
    ("m7", "u8", "uint8_t m7", 0), ("m8", "u16", "uint16_t m8", 0),
]):
    field(3010 + off, f"map.tile.{name}", typ, "src/map_func.h", symbol,
          f"Raw native Tile::{name} plane for every tile.",
          "Native tile procedures read these bytes directly; semantic labels cannot preserve overloaded per-tile meanings.",
          owner="map_tile", owner_rule="TileIndex in range 0..map.size-1", shape="fixed_array",
          fixed_count=4096, maximum_capacity=4096, order="TileIndex ascending 0 through 4095",
          sample=[sample], sample_scope="one_element", reached_path="Tile accessor -> native tile procedure -> authoritative boundary adapter")
field(3020, "map.animated_tile_count", "u32", "src/animated_tile.cpp", "std::vector<TileIndex> _animated_tiles",
      "Exact number of entries in the saved animated-tile vector.",
      "The tick loop iterates this native vector, and swap-with-back removal makes its size and order persistent continuation state.",
      owner="animated_tile_registry", owner_rule="singleton native vector", sample=0,
      reached_path="industry creation -> AddAnimatedTile -> AnimateAnimatedTiles")
field(3021, "map.animated_tiles", "u32", "src/animated_tile.cpp", "std::vector<TileIndex> _animated_tiles",
      "Animated TileIndices in exact native vector order.",
      "AnimateAnimatedTiles processes this order each tick; map bits do not recover swap-with-back vector order or resulting callback/RNG order.",
      owner="animated_tile_registry", owner_rule="singleton native vector",
      shape="dynamic_array", fixed_count=None, count_source="map.animated_tile_count", maximum_capacity=4096,
      order="native _animated_tiles vector index ascending", sample=[0], sample_scope="one_element",
      reached_path="StateGameLoop -> AnimateAnimatedTiles -> industry/effect animation callbacks")
field(3099, "map.native_revision_counter", "u8", "src/map_func.h", "struct Map",
      "Proof entry for a native map revision counter.",
      "Pinned Map has dimensions, mask, land count and native tile arrays but no persistent mutation revision; raw planes and authoritative caches are projected.",
      owner="map", owner_rule="singleton map", sample=0,
      classification="out_of_scope_unreachable", reached="unreachable_absent-from-pinned-Map-storage",
      reached_path="Map member review -> road/station mutation invalidators")

# Company and ledger.
pool_meta(4000, "company", 15, "_company_pool")
field(4009, "company.ledger.expense_cell_count", "u32", "src/economy_type.h", "ExpensesType::End",
      "Total CompanyID/year/expense-category ledger cell count.",
      "Explicit count prevents construction, vehicle purchase, running cost, income, interest or other categories from being omitted.",
      owner="company_pool", owner_rule="singleton typed pool", sample=0,
      reached_path="Company::yearly_expenses -> ExpensesType canonical order")
scalar_group(4010, "company.item", "src/company_base.h", "Company", "CompanyID numeric pool slot", [
    ("id", "stable_id", "struct Company : CompanyProperties", 0, "Typed company pool ID."),
    ("money", "i64", "Money money", 10000000, "Company money balance."),
    ("money_fraction", "u8", "money_fraction", 0, "Sub-money accounting fraction."),
    ("current_loan", "i64", "current_loan", 0, "Outstanding loan."),
    ("max_loan", "i64", "Money max_loan", 300000, "Effective maximum loan."),
    ("bankruptcy_months", "u8", "months_of_bankruptcy", 0, "Bankruptcy progression counter."),
    ("bankruptcy_timeout", "i16", "bankrupt_timeout", 0, "Bankruptcy offer timeout."),
    ("yearly_expenses", "i64", "yearly_expenses", 0, "Categorized three-year expense ledger entries."),
    ("current_income", "i64", "Money income", 0, "Current-quarter income."),
    ("current_expenses", "i64", "Money expenses", 0, "Current-quarter expenses."),
    ("delivered_cargo", "u32", "delivered_cargo", 0, "Current-quarter delivered amount by cargo type."),
    ("road_infrastructure", "u32", "road{}", 0, "Road and tram infrastructure counts by road type."),
    ("station_infrastructure", "u32", "uint32_t station", 0, "Owned station-tile count."),
    ("road_unit_id_words", "u64", "used_bitmap", 0, "Exact road-vehicle FreeUnitIDGenerator storage words, including trailing cleared words."),
], "Company finance, infrastructure, and ID allocation feed costs, limits, maintenance, and exact future identifiers.",
"Company::Tick -> SubtractMoneyFromCompany -> authoritative boundary adapter")
field(4024, "company.item.settings.vehicle.servint_ispercent", "u8", "src/settings_type.h", "servint_ispercent",
      "Per-company service interval unit selector.",
      "Service scheduling reads this company-owned setting; treating it as a global setting would lose continuation state.",
      owner="Company", owner_rule="CompanyID numeric pool slot", sample=0,
      reached_path="Company::settings.vehicle -> VehicleNeedsService -> RoadVehicle::Tick")
field(4025, "company.item.settings.vehicle.servint_roadveh", "u16", "src/settings_type.h", "servint_roadveh",
      "Per-company default road-vehicle service interval.",
      "A nonzero or differently interpreted interval changes automatic depot routing.",
      owner="Company", owner_rule="CompanyID numeric pool slot", sample=0,
      reached_path="Company::settings.vehicle -> VehicleNeedsService -> RoadVehicle::Tick")
scalar_group(4030, "company.item", "src/company_base.h", "Company", "CompanyID numeric pool slot", [
    ("colour", "u8", "Colours colour", 0, "Company colour value."),
    ("preview_block_quarters", "u8", "block_preview", 0, "Exclusive-preview block counter."),
    ("headquarters_tile", "u32", "location_of_HQ", 4294967295, "Company headquarters tile."),
    ("last_build_tile", "u32", "last_build_coordinate", 0, "Last native construction coordinate."),
    ("inaugurated_economy_year", "i32", "inaugurated_year", 1950, "Company inauguration economy year."),
    ("inaugurated_calendar_year", "i32", "inaugurated_year_calendar", 1950, "Company inauguration calendar year."),
    ("bankruptcy_asked_mask", "u16", "bankrupt_asked", 0, "Companies asked to buy bankrupt company."),
    ("bankruptcy_value", "i64", "bankrupt_value", 0, "Current bankruptcy purchase value."),
    ("terraform_limit", "u32", "terraform_limit", 0, "Terraform command rate-limit fixed-point balance."),
    ("clear_limit", "u32", "clear_limit", 0, "Clear command rate-limit fixed-point balance."),
    ("tree_limit", "u32", "tree_limit", 0, "Tree command rate-limit fixed-point balance."),
    ("build_object_limit", "u32", "build_object_limit", 0, "Object/build command rate-limit fixed-point balance."),
    ("is_ai", "u8", "bool is_ai", 0, "AI-control flag."),
    ("valid_history_entries", "u8", "num_valid_stat_ent", 0, "Number of valid quarterly history entries."),
    ("history_income", "i64", "Money income", 0, "Quarterly historical income cells."),
    ("history_expenses", "i64", "Money expenses", 0, "Quarterly historical expense cells."),
    ("history_delivered_cargo", "u32", "delivered_cargo", 0, "Quarterly historical delivered cargo cells."),
    ("history_performance", "i32", "performance_history", 0, "Quarterly performance score history."),
    ("history_company_value", "i64", "company_value", 0, "Quarterly company-value history."),
    ("available_road_types", "u64", "RoadTypes avail_roadtypes", 0, "Road types currently available to company."),
], "Company limits, histories, availability and bankruptcy/preview counters affect subsequent commands and periodic accounting.",
"Company::Tick/CompaniesGenStatistics -> command affordability and vehicle availability")
scalar_group(4060, "company.item.settings", "src/settings_type.h", "CompanySettings", "CompanyID numeric pool slot", [
    ("engine_renew", "u8", "bool engine_renew", 0, "Automatic engine renewal flag."),
    ("engine_renew_months", "i16", "engine_renew_months", 0, "Renewal age offset."),
    ("engine_renew_money", "u32", "engine_renew_money", 0, "Minimum money for renewal."),
    ("renew_keep_length", "u8", "renew_keep_length", 0, "Autoreplace length-preservation flag."),
], "Per-company renewal settings can allocate replacement vehicles and change the ledger.",
"Vehicle::NeedsAutorenewing -> CmdAutoreplaceVehicle")
scalar_group(4050, "company.item", "src/company_base.h", "Company", "CompanyID numeric pool slot", [
    ("group_unit_id_words", "u64", "FreeUnitIDGenerator freegroups", 0, "Exact group-number generator storage words, including trailing cleared words."),
    ("rail_infrastructure", "u32", "rail{}", 0, "Rail infrastructure counts by native RailType ordinal."),
    ("signal_infrastructure", "u32", "uint32_t signal", 0, "Owned signal infrastructure count."),
    ("water_infrastructure", "u32", "uint32_t water", 0, "Owned canal infrastructure count."),
    ("airport_infrastructure", "u32", "uint32_t airport", 0, "Owned airport infrastructure count."),
    ("available_rail_types", "u64", "RailTypes avail_railtypes", 0, "Rail types currently available to the company."),
], "Company infrastructure and exact allocation-generator storage enter maintenance, value, group allocation, and purchase behavior.",
"Company::Tick/CompaniesGenStatistics -> PayCompanyForRail/Group allocation")
field(4056, "company.nonroad_unit_id_generators", "u8", "src/company_base.h", "VehicleTypeIndexArray<FreeUnitIDGenerator> freeunits",
      "Proof disposition for train, ship and aircraft FreeUnitIDGenerator state.",
      "The declared road-freight command corpus cannot create non-road vehicles; the road generator and independent group generator are projected exactly.",
      owner="Company", owner_rule="CompanyID numeric pool slot", sample=0,
      classification="out_of_scope_unreachable", reached="unreachable-by-road-freight-command-corpus-and-vehicle-type-validation",
      reached_path="validated road command set -> CmdBuildVehicle type Road -> non-road generators excluded")

# Industry production state.
pool_meta(5000, "industry", 64000, "_industry_pool")
scalar_group(5010, "industry.item", "src/industry.h", "Industry", "IndustryID numeric pool slot", [
    ("id", "stable_id", "struct Industry", 0, "Typed industry pool ID."),
    ("location_tile", "u32", "TileArea location", 1736, "Industry anchor tile."),
    ("location_width", "u16", "TileArea location", 3, "Industry footprint width."),
    ("location_height", "u16", "TileArea location", 3, "Industry footprint height."),
    ("town_id", "stable_id", "Town *town", 0, "Nearest town stable ID."),
    ("type", "u8", "IndustryType type", 0, "Industry type ID."),
    ("owner", "u8", "Owner owner", 16, "Industry owner code."),
    ("production_level", "u8", "prod_level", 16, "General production level."),
    ("counter", "u16", "uint16_t counter", 0, "Animation and production counter."),
    ("last_production_year", "i32", "last_prod_year", 1950, "Last production economy year."),
    ("cargo_delivered_flag", "u8", "was_cargo_delivered", 0, "Closest-industry delivery flag."),
    ("control_flags", "u8", "ctlflags", 0, "Closure and external-production control flags."),
    ("selected_layout", "u8", "selected_layout", 2, "Native selected layout value."),
    ("random", "u16", "uint16_t random", 0, "Per-industry random bits."),
    ("produced_cargo_type", "u8", "CargoType cargo", 1, "Produced cargo type per produced slot."),
    ("produced_waiting", "u16", "uint16_t waiting", 0, "Produced cargo waiting at industry."),
    ("produced_rate", "u8", "uint8_t rate", 0, "Production rate per cargo slot."),
    ("produced_history_production", "u16", "uint16_t production", 0, "Monthly production history."),
    ("produced_history_transported", "u16", "uint16_t transported", 0, "Monthly transported history."),
    ("accepted_cargo_type", "u8", "CargoType cargo", 1, "Accepted cargo type per accepted slot."),
    ("accepted_waiting", "u16", "uint16_t waiting", 0, "Accepted cargo waiting for processing."),
    ("accepted_accumulated_waiting", "u32", "accumulated_waiting", 0, "Accepted cargo monthly accumulation."),
    ("accepted_last_date", "i32", "last_accepted", 0, "Last accepted economy date."),
    ("nearby_station_ids", "stable_id", "stations_near", 0, "Canonical nearby-station stable IDs."),
], "Industry production and acceptance state determines packet creation, capture, closure and RNG consumption.",
"IndustryGameLoop -> ProduceIndustryGoods -> authoritative boundary adapter")
scalar_group(5040, "industry.item", "src/industry.h", "Industry", "IndustryID numeric pool slot", [
    ("neutral_station_id", "stable_id", "neutral_station", 65535, "Associated neutral station stable ID."),
    ("valid_history_mask", "u64", "ValidHistoryMask valid_history", 0, "Valid industry history periods."),
    ("produced_slot_owner_count", "u32", "ProducedCargoes produced", 0, "Produced cargo vector count for each industry owner."),
    ("accepted_slot_owner_count", "u32", "AcceptedCargoes accepted", 0, "Accepted cargo vector count for each industry owner."),
    ("accepted_history_amount", "u16", "uint16_t accepted", 0, "Accepted cargo history amounts."),
    ("accepted_history_waiting", "u16", "uint16_t waiting", 0, "Accepted cargo average-waiting history."),
    ("subsidy_role_mask", "u8", "part_of_subsidy", 0, "Industry source/destination subsidy-role mask."),
    ("founder", "u8", "Owner founder", 16, "Industry founder owner code."),
    ("construction_date", "i32", "construction_date", 712223, "Industry construction calendar date."),
    ("construction_type", "u8", "construction_type", 0, "Native industry construction method."),
    ("exclusive_supplier", "u8", "exclusive_supplier", 255, "Exclusive supplier company ID."),
    ("exclusive_consumer", "u8", "exclusive_consumer", 255, "Exclusive consumer company ID."),
], "Industry vector membership, histories, construction and exclusive-rights fields affect production, capture and payments.",
"IndustryDailyLoop/IndustryMonthlyLoop -> ProduceIndustryGoods/DeliverGoodsToIndustry")
field(5052, "industry.item.accepted_history_presence", "u8", "src/industry.h", "std::unique_ptr<HistoryData<AcceptedHistory>> history",
      "Presence of optional accepted-cargo history storage for each accepted slot.",
      "An absent history and an allocated all-zero history are distinct native allocation/lifecycle states.",
      owner="Industry::AcceptedCargo", owner_rule="IndustryID then accepted-slot ordinal", sample=0,
      reached_path="Industry::AcceptedCargo::GetOrCreateHistory -> monthly production/delivery history")
field(5073, "industry.builder.wanted_industries", "u32", "src/industry.h", "uint32_t wanted_inds",
      "Saved fixed-point number of industries wanted by the native industry scheduler.",
      "The daily industry callback compares this value before a gameplay RNG branch and possible industry construction.",
      owner="IndustryBuildData", owner_rule="singleton _industry_builder", sample=0,
      reached_path="economy industry daily timer -> _industry_builder.wanted_inds -> Chance16/TryBuildNewIndustry")
for field_id, suffix, value_type, symbol, description in [
    (5074, "probabilities", "u32", "uint32_t probability", "Relative native construction probability by IndustryType."),
    (5075, "minimum_numbers", "u8", "uint8_t   min_number", "Minimum desired native industry count by IndustryType."),
    (5076, "target_counts", "u16", "uint16_t target_count", "Target native industry count by IndustryType."),
    (5077, "maximum_waits", "u16", "uint16_t max_wait", "Initial scheduler wait by IndustryType."),
    (5078, "wait_counts", "u16", "uint16_t wait_count", "Current scheduler wait counter by IndustryType."),
]:
    field(field_id, f"industry.builder.{suffix}", value_type, "src/industry.h", symbol,
          description, "IndustryBuildData::TryBuildNewIndustry reads this saved array; it can alter RNG selection, construction, and subsequent production state.",
          owner="IndustryBuildData", owner_rule="singleton _industry_builder; element key is numeric IndustryType",
          shape="fixed_array", fixed_count=240, maximum_capacity=240,
          order="IndustryType numeric value 0 through NUM_INDUSTRYTYPES-1", sample=[0], sample_scope="one_element",
          reached_path="economy industry daily timer -> IndustryBuildData::TryBuildNewIndustry")

# Station, road stop, and goods.
pool_meta(6000, "station", 64000, "_station_pool")
scalar_group(6010, "station.item", "src/base_station_base.h", "Station", "StationID numeric pool slot", [
    ("id", "stable_id", "struct BaseStation", 0, "Typed station pool ID."),
    ("anchor_tile", "u32", "TileIndex xy", 0, "Station anchor tile."),
    ("town_id", "stable_id", "Town *town", 0, "Associated town stable ID."),
    ("owner", "u8", "Owner owner", 0, "Station owner."),
    ("facilities", "u8", "facilities", 0, "Station facility bitset."),
    ("delete_counter", "u8", "delete_ctr", 0, "Station deletion counter."),
    ("build_date", "i32", "build_date", 712223, "Station construction date."),
    ("random_bits", "u16", "random_bits", 0, "Station random bits."),
], "Station identity and lifecycle control cargo capture and vehicle destinations.",
"StationBigTick -> Station::Tick -> authoritative boundary adapter")
scalar_group(6030, "station.item", "src/station_base.h", "Station", "StationID numeric pool slot", [
    ("truck_stop_head_id", "stable_id", "RoadStop *truck_stops", 0, "Head RoadStopID of truck-stop order."),
    ("truck_area_tile", "u32", "truck_station", 0, "Truck-station area anchor."),
    ("catchment_tiles", "bitset", "catchment_tiles", 0, "Exact station catchment bitmap."),
    ("time_since_load", "u8", "time_since_load", 0, "Station load timer."),
    ("time_since_unload", "u8", "time_since_unload", 0, "Station unload timer."),
    ("last_vehicle_type", "u8", "last_vehicle_type", 255, "Last visiting vehicle type."),
    ("loading_vehicle_ids", "stable_id", "loading_vehicles", 0, "Vehicles loading at station in list order."),
    ("always_accepted", "u64", "always_accepted", 0, "Always-accepted cargo mask."),
    ("industries_near_ids", "stable_id", "industries_near", 0, "Nearby industries in canonical stable-ID order."),
], "Catchment, service timers, loading order and nearby industry lists influence cargo and movement.",
"Station::RecomputeCatchment -> LoadUnloadVehicle -> authoritative boundary adapter")
scalar_group(6039, "station.item", "src/station_base.h", "Station", "StationID numeric pool slot", [
    ("truck_area_width", "u16", "TileArea truck_station", 0, "Truck-station TileArea width."),
    ("truck_area_height", "u16", "TileArea truck_station", 0, "Truck-station TileArea height."),
    ("had_vehicle_of_type", "u8", "StationVehicleTypes had_vehicle_of_type", 0, "Vehicle-type visit mask used by station behavior."),
    ("industry_name_type", "u8", "IndustryType indtype", 255, "Industry type used by native station identity and naming state."),
    ("neutral_industry_id", "stable_id", "Industry *industry", 65535, "Associated neutral-industry stable ID."),
], "Stored station areas, visit flags, identity, neutral-industry linkage and trigger records can affect subsequent station operations.",
"Station::AddFacility/VehicleEnter_Station/trigger processing -> authoritative boundary adapter")
scalar_group(6044, "station.item", "src/base_station_base.h", "BaseStation", "StationID numeric pool slot", [
    ("custom_roadstop_random_bits", "u8", "custom_roadstop_tile_data", 0, "Custom road-stop random bits by stored tile record."),
    ("custom_roadstop_animation_frames", "u8", "custom_roadstop_tile_data", 0, "Custom road-stop animation frames by stored tile record."),
    ("string_id", "u32", "StringID string_id", 4294967295, "Default station-name StringID, retained because future station-name allocation observes it."),
    ("tile_waiting_trigger_tiles", "u32", "tile_waiting_random_triggers", 0, "Tile keys of per-tile waiting random-trigger records."),
    ("tile_waiting_trigger_values", "u8", "tile_waiting_random_triggers", 0, "Trigger masks paired with per-tile trigger keys."),
], "Base-station custom tile and trigger records preserve exact native order and future naming state.",
"BaseStation trigger/spec state -> station processing -> authoritative boundary adapter")
field(6049, "station.item.industries_near_distances", "u32", "src/station_base.h", "uint distance",
      "Cached squared distance paired with every nearby-industry reference.",
      "IndustryListEntry ordering is (distance, IndustryID), and delivery consumes that exact order; IDs alone do not preserve the authoritative cache.",
      owner="Station", owner_rule="StationID then native IndustryListEntry order",
      shape="dynamic_array", fixed_count=None, count_source="station.nearby_industry_ref_count",
      maximum_capacity=409600000, order="StationID ascending, then native (distance, IndustryID) order",
      sample=[0], sample_scope="one_element", cache="authoritative_cache",
      invalidation="station catchment or nearby-industry membership/distance change",
      rebuild="not claimed; field remains authoritative_full until clear/rebuild plus two-load 10000-tick continuation evidence passes",
      reached_path="Station::AddIndustryToDeliver -> IndustryListEntry ordering -> DeliverGoodsToIndustry")
scalar_group(6050, "station.item", "src/base_station_base.h", "BaseStation", "StationID numeric pool slot", [
    ("station_rect_left", "i32", "StationRect rect", 0, "Cached station rectangle left boundary."),
    ("station_rect_top", "i32", "StationRect rect", 0, "Cached station rectangle top boundary."),
    ("station_rect_right", "i32", "StationRect rect", 0, "Cached station rectangle right boundary."),
    ("station_rect_bottom", "i32", "StationRect rect", 0, "Cached station rectangle bottom boundary."),
    ("waiting_random_triggers", "u8", "StationRandomTriggers waiting_random_triggers", 0, "Pending station random triggers."),
    ("cached_animation_triggers", "u16", "cached_anim_triggers", 0, "Cached station animation triggers."),
    ("cached_roadstop_animation_triggers", "u16", "cached_roadstop_anim_triggers", 0, "Cached road-stop animation triggers."),
    ("cached_cargo_triggers", "u64", "cached_cargo_triggers", 0, "Cached station cargo trigger mask."),
    ("cached_roadstop_cargo_triggers", "u64", "cached_roadstop_cargo_triggers", 0, "Cached road-stop cargo trigger mask."),
    ("custom_roadstop_tiles", "u32", "custom_roadstop_tile_data", 0, "Custom road-stop tile keys in native vector order."),
], "Station rectangles, triggers and custom tile state can affect catchment, animation callbacks and cargo processing.",
"AfterStationTileSetChange -> station trigger processing -> LoadUnloadVehicle")
for field_id, suffix, value_type, symbol, source_file, sample, description in [
    (6081, "catchment_base_tile", "u32", "TileIndex tile", "src/tilearea_type.h", 4294967295, "Base tile of the authoritative catchment bitmap area."),
    (6082, "catchment_width", "u16", "uint16_t w", "src/tilearea_type.h", 0, "Width of the authoritative catchment bitmap area."),
    (6083, "catchment_height", "u16", "uint16_t h", "src/tilearea_type.h", 0, "Height of the authoritative catchment bitmap area."),
]:
    field(field_id, f"station.item.{suffix}", value_type, source_file, symbol, description,
          "BitmapTileArea::Index, HasTile, and iteration consume the inherited tile/width/height together with the data bits; the bit vector alone is ambiguous.",
          owner="Station", owner_rule="StationID numeric pool slot", sample=sample,
          cache="authoritative_cache", invalidation="station catchment initialization/reset/recompute",
          rebuild="not claimed; field remains authoritative_full until clear/rebuild plus two-load 10000-tick continuation evidence passes",
          reached_path="Station::catchment_tiles -> BitmapTileArea::Index/HasTile/iterator -> cargo capture")
for item in FIELDS:
    if item["path"].startswith("station.item.") and any(token in item["path"] for token in ("catchment", "industries_near", "station_rect", "cached_")):
        item["cache_classification"] = "authoritative_cache"
        item["cache_invalidation_trigger"] = "station tile/spec/cargo change, nearby industry change, or after-load rebuild"
        item["deterministic_rebuild_procedure"] = "not claimed; field remains authoritative_full until clear/rebuild plus two-load 10000-tick continuation evidence passes"
pool_meta(6100, "road_stop", 64000, "_roadstop_pool")
scalar_group(6110, "road_stop.item", "src/roadstop_base.h", "RoadStop", "RoadStopID numeric pool slot", [
    ("id", "stable_id", "struct RoadStop", 0, "Typed road-stop pool ID."),
    ("tile", "u32", "TileIndex xy", 0, "Road-stop tile."),
    ("status", "u8", "RoadStopStatusFlags status", 3, "Bay and entry-busy status bits."),
    ("next_id", "stable_id", "RoadStop *next", 0, "Next stop stable ID in station/type order."),
    ("east_length", "u16", "uint16_t length", 0, "East drive-through entry length."),
    ("east_occupied", "u16", "uint16_t occupied", 0, "East drive-through occupied length."),
    ("west_length", "u16", "uint16_t length", 0, "West drive-through entry length."),
    ("west_occupied", "u16", "uint16_t occupied", 0, "West drive-through occupied length."),
], "Road-stop occupancy and linked order affect entry, queueing, allocation and YAPF penalties.",
"RoadStop::Enter/Leave -> RoadVehController -> authoritative boundary adapter")
field(6118, "road_stop.item.entries_present", "u8", "src/roadstop_base.h", "Entries *entries = nullptr",
      "Presence of the optional drive-through entry-state allocation.",
      "Bay stops have a null entries pointer, while drive-through stops may contain an allocated all-zero Entries object; presence is native lifecycle state.",
      owner="RoadStop", owner_rule="RoadStopID numeric pool slot", sample=0,
      reached_path="RoadStop::MakeDriveThrough/ClearDriveThrough -> GetEntry -> RoadStop::Enter/Leave")
scalar_group(6200, "station.goods", "src/station_base.h", "GoodsEntry", "(StationID, CargoType) lexicographic", [
    ("status", "u8", "States status", 0, "Cargo acceptance/rating state bits."),
    ("time_since_pickup", "u8", "time_since_pickup", 255, "Rating intervals since vehicle pickup attempt."),
    ("rating", "u8", "uint8_t rating", 175, "Station cargo rating."),
    ("last_speed", "u8", "last_speed", 0, "Last loading vehicle speed for rating."),
    ("last_age", "u8", "last_age", 255, "Last loading vehicle age for rating."),
    ("amount_fraction", "u8", "amount_fract", 0, "Fractional station cargo production amount."),
    ("max_waiting", "u32", "max_waiting_cargo", 0, "Maximum source cargo waiting network-wide."),
    ("linkgraph_node", "u16", "NodeID node", 65535, "LinkGraph node ID."),
    ("linkgraph_id", "stable_id", "LinkGraphID link_graph", 4294967295, "Associated LinkGraph stable ID."),
    ("packet_ids", "stable_id", "StationCargoList cargo", 0, "Waiting packet IDs preserving native container order."),
    ("flow_origin_station_ids", "stable_id", "FlowStatMap flows", 0, "Flow origin StationIDs in each GoodsEntry map's key order."),
], "GoodsEntry state determines capture, rating, next-hop selection, packet order and cargo amount.",
"UpdateStationRating -> MoveGoodsToStation -> StationCargoList")
scalar_group(6211, "station.goods", "src/station_base.h", "GoodsEntry", "(StationID, CargoType) lexicographic", [
    ("data_presence", "u8", "bool HasData() const", 0, "Whether optional GoodsEntryData storage is present, distinguishing absent from present-and-empty."),
    ("flow_unrestricted", "u32", "uint unrestricted", 0, "Unrestricted cumulative flow limit for each FlowStat owner."),
    ("flow_share_cumulative_key", "u32", "SharesMap shares", 0, "Exact cumulative flow-share keys in native map order."),
    ("flow_share_via_station_id", "stable_id", "SharesMap shares", 0, "Via StationID paired with each cumulative flow-share key."),
], "Optional-data presence and exact FlowStat map storage affect allocation lifetime and RNG-based next-hop selection.",
"GoodsEntry::HasData/GetVia -> FlowStat::GetVia -> StationCargoList")
field(6215, "station.goods.packet_map_next_hop_keys", "stable_id", "src/cargopacket.h", "Tcont packets{}",
      "Next-hop StationID map key paired with each stored station cargo packet reference.",
      "StationCargoList::Append stores the caller-supplied next hop as the multimap key independently of CargoPacket::next_hop; loading uses equal_range and iterator keys.",
      owner="GoodsEntry", owner_rule="(StationID, CargoType), then native StationCargoPacketMap iteration order",
      shape="dynamic_array", fixed_count=None, count_source="station.goods.packet_ref_count",
      maximum_capacity=16773120,
      order="GoodsEntry owner order, then native map key order with equivalent-key insertion order",
      sample=[65535], sample_scope="one_element",
      reached_path="MoveGoodsToStation -> StationCargoList::Append(cp,next) -> StationCargoList::Load/equal_range")
scalar_group(6230, "station.goods", "src/cargopacket.h", "StationCargoList", "(StationID, CargoType) lexicographic", [
    ("cached_count", "u32", "uint count", 0, "Cached unreserved cargo-unit count."),
    ("cached_periods_in_transit", "u64", "cargo_periods_in_transit", 0, "Cached sum of cargo transit periods."),
    ("reserved_count", "u32", "reserved_count", 0, "Cargo units reserved for loading."),
], "Station cargo-list caches and reservation state are read directly by loading and rating code.",
"StationCargoList::Reserve/Load -> LoadUnloadVehicle")
for item in FIELDS:
    if item["path"].startswith("station.goods.") and any(token in item["path"] for token in ("cached_", "reserved_count")):
        item["cache_classification"] = "authoritative_cache"
        item["cache_invalidation_trigger"] = "packet append/remove/reserve/load/merge/split"
        item["deterministic_rebuild_procedure"] = "not claimed; field remains authoritative_full until clear/rebuild plus two-load 10000-tick continuation evidence passes"
for field_id, path, symbol, description in [
    (6090, "station.nonroad.bus_area", "TileArea bus_station", "Bus-station area state excluded by the road-freight truck command corpus."),
    (6091, "station.nonroad.airport_state", "Airport airport", "Airport area, blocks and rotation state excluded by the command corpus."),
    (6092, "station.nonroad.ship_areas", "TileArea ship_station", "Ship and docking area state excluded by the command corpus."),
    (6093, "station.newgrf.rail_spec_list", "speclist{}", "Custom rail-station spec mappings excluded by the base-content manifest."),
    (6094, "station.newgrf.roadstop_spec_list", "roadstop_speclist{}", "Custom road-stop spec mappings excluded by the base-content manifest."),
]:
    source = "src/station_base.h" if field_id <= 6092 else "src/base_station_base.h"
    field(field_id, path, "u8", source, symbol, description,
          "The validated fixture/content/command profile cannot allocate this native family; the source owner is recorded so expansion cannot silently omit it.",
          owner="Station", owner_rule="StationID numeric pool slot", sample=0,
          classification="out_of_scope_unreachable", reached="unreachable-verified-by-base-content-and-road-freight-command-profile",
          reached_path="fixture content identity -> validated command kinds -> excluded station family source review")

# Vehicles and road controller.
pool_meta(7000, "vehicle", 0xFF000, "_vehicle_pool")
scalar_group(7010, "vehicle.item", "src/vehicle_base.h", "Vehicle", "VehicleID numeric pool slot", [
    ("id", "stable_id", "struct Vehicle : VehiclePool", 0, "Typed vehicle pool ID."),
    ("subtype", "u8", "uint8_t subtype", 0, "Native vehicle subtype flags."),
    ("engine_id", "stable_id", "EngineID engine_type", 123, "Engine stable ID."),
    ("owner", "u8", "Owner owner", 0, "Vehicle owner."),
    ("tile", "u32", "TileIndex tile", 0, "Current tile."),
    ("destination_tile", "u32", "TileIndex dest_tile", 0, "Current movement target tile."),
    ("x_position", "i32", "int32_t x_pos", 0, "Precise world X coordinate."),
    ("y_position", "i32", "int32_t y_pos", 0, "Precise world Y coordinate."),
    ("z_position", "i32", "int32_t z_pos", 0, "Precise world Z coordinate."),
    ("direction", "u8", "Direction direction", 0, "Movement direction."),
    ("current_speed", "u16", "cur_speed", 0, "Current speed."),
    ("subspeed", "u8", "subspeed", 0, "Fractional speed."),
    ("acceleration", "u8", "acceleration", 0, "Acceleration state."),
    ("progress", "u8", "uint8_t progress", 0, "Within-tile movement progress."),
    ("motion_counter", "u32", "motion_counter", 0, "Movement/sound cadence counter."),
    ("status", "u8", "VehStates vehstatus", 0, "Stopped, hidden, crashed and related state bits."),
    ("last_station_visited", "stable_id", "last_station_visited", 4294967295, "Last visited station stable ID."),
    ("last_loading_station", "stable_id", "last_loading_station", 4294967295, "Last station eligible for loading."),
    ("last_loading_tick", "u64", "last_loading_tick", 0, "Tick of last eligible loading stop."),
    ("cargo_type", "u8", "CargoType cargo_type", 1, "Vehicle cargo type."),
    ("cargo_capacity", "u16", "cargo_cap", 0, "Vehicle cargo capacity."),
    ("cargo_packet_ids", "stable_id", "VehicleCargoList cargo", 0, "Vehicle cargo packet IDs preserving native order."),
    ("cargo_age_counter", "u16", "cargo_age_counter", 0, "Cargo aging tick counter."),
    ("day_counter", "u8", "day_counter", 0, "Vehicle daily counter."),
    ("tick_counter", "u8", "uint8_t tick_counter", 0, "Vehicle tick-phase counter."),
    ("running_ticks", "u8", "running_ticks", 0, "Ticks run during current day."),
    ("load_unload_ticks", "u16", "load_unload_ticks", 0, "Load/unload phase wait counter."),
    ("order_list_id", "stable_id", "OrderList *orders", 4294967295, "OrderList stable ID or declared null."),
    ("profit_this_year", "i64", "profit_this_year", 0, "Vehicle current-year profit in source fixed-point units."),
    ("value", "i64", "Money value", 0, "Current vehicle value."),
    ("build_year", "i32", "build_year", 1950, "Vehicle build year."),
    ("calendar_age", "i32", "TimerGameCalendar::Date age", 0, "Vehicle calendar age."),
    ("economy_age", "i32", "economy_age", 0, "Vehicle economy age."),
    ("last_service_date", "i32", "date_of_last_service", 712223, "Last service economy date."),
    ("reliability", "u16", "uint16_t reliability", 0, "Vehicle reliability."),
    ("breakdown_counter", "u8", "breakdown_ctr", 0, "Breakdown event counter."),
    ("breakdown_delay", "u8", "breakdown_delay", 0, "Breakdown duration."),
    ("random_bits", "u16", "uint16_t random_bits", 0, "Vehicle random bits."),
    ("next_vehicle_id", "stable_id", "Vehicle *next", 4294967295, "Next consist vehicle stable ID."),
    ("next_shared_vehicle_id", "stable_id", "Vehicle *next_shared", 4294967295, "Next shared-order vehicle stable ID."),
    ("tile_hash_next_id", "stable_id", "Vehicle *hash_tile_next", 4294967295, "Next stable ID in gameplay tile hash chain."),
], "Vehicle physical, order, cargo, age, financial and chain state controls every subsequent controller transition.",
"Vehicle::Tick -> RoadVehicle::Tick -> RoadVehController")
field(7051, "vehicle.item.vehicle_type", "u8", "src/vehicle_type.h", "VehicleType type",
      "Native BaseVehicle type discriminator.",
      "Pool occupancy and subclass-derived counts cannot replace the stored discriminator used by iteration and command dispatch.",
      owner="Vehicle", owner_rule="VehicleID numeric pool slot", sample=1,
      reached_path="Vehicle::type -> Vehicle::Tick/command dispatch -> authoritative boundary adapter")
field(7052, "effect_vehicle.item.count", "u32", "src/effectvehicle_base.h", "struct EffectVehicle final :",
      "Number of occupied Vehicle pool slots whose native type is Effect.",
      "EffectVehicles share VehiclePool allocation and free slots with road vehicles, so subclass columns require an explicit filtered count.",
      owner="vehicle_pool", owner_rule="singleton typed pool", sample=0,
      reached_path="CreateEffectVehicleRel/CreateChimneySmoke -> Vehicle::Iterate type filter Effect")
field(7053, "effect_vehicle.item.ids", "stable_id", "src/effectvehicle_base.h", "struct EffectVehicle final :",
      "Stable VehicleIDs of occupied EffectVehicles.",
      "The discriminator maps subclass behavior columns to shared VehiclePool slots and preserves allocation/freeing effects on future IDs.",
      owner="EffectVehicle", owner_rule="VehicleID numeric pool slot filtered by native type Effect",
      shape="dynamic_array", fixed_count=None, count_source="effect_vehicle.item.count", maximum_capacity=0xFF000,
      order="VehicleID ascending among occupied vehicles whose type is Effect", sample=[0], sample_scope="one_element",
      reached_path="EffectVehicle::Iterate -> EffectVehicle::Tick -> shared VehiclePool")
for field_id, suffix, value_type, symbol, description in [
    (7054, "animation_state", "u16", "uint16_t animation_state", "Effect animation state controlling behavior and lifetime."),
    (7055, "animation_substate", "u8", "uint8_t animation_substate", "Effect animation substate timing counter."),
]:
    field(field_id, f"effect_vehicle.item.{suffix}", value_type, "src/effectvehicle_base.h", symbol,
          description, "EffectVehicle::Tick branches on this value; transition/deletion timing changes shared VehiclePool reuse.",
          owner="EffectVehicle", owner_rule="VehicleID numeric pool slot filtered by native type Effect",
          shape="dynamic_array", fixed_count=None, count_source="effect_vehicle.item.count", maximum_capacity=0xFF000,
          order="effect VehicleID ascending", sample=[0], sample_scope="one_element",
          reached_path="EffectVehicle::Tick -> type handler -> delete/free shared Vehicle slot")
field(7056, "effect_vehicle.item.current_sprite_id", "u32", "src/vehicle_base.h", "std::array<PalSpriteID, 8> seq",
      "Current first sprite ID used as EffectVehicle behavior state.",
      "Chimney and diesel handlers call IncrementSprite and branch on sprite_seq.seq[0].sprite; it is not display-only for EffectVehicles.",
      owner="EffectVehicle", owner_rule="VehicleID numeric pool slot filtered by native type Effect",
      shape="dynamic_array", fixed_count=None, count_source="effect_vehicle.item.count", maximum_capacity=0xFF000,
      order="effect VehicleID ascending", sample=[0], sample_scope="one_element",
      reached_path="EffectVehicle::Tick -> IncrementSprite -> MutableSpriteCache::sprite_seq")
scalar_group(7120, "vehicle.item", "src/vehicle_base.h", "Vehicle", "VehicleID numeric pool slot", [
    ("cargo_payment_id", "stable_id", "CargoPayment *cargo_payment", 4294967295, "Active staged CargoPayment stable ID."),
    ("profit_last_year", "i64", "profit_last_year", 0, "Vehicle prior-year profit in fixed-point units."),
    ("unit_number", "u16", "UnitID unitnumber", 0, "Company-visible vehicle unit ID."),
    ("maximum_age", "i32", "Date max_age", 0, "Maximum vehicle calendar age."),
    ("last_service_calendar_date", "i32", "date_of_last_service_newgrf", 712223, "Last service calendar date."),
    ("reliability_speed_decrease", "u16", "reliability_spd_dec", 0, "Vehicle reliability decay speed."),
    ("breakdowns_since_service", "u8", "breakdowns_since_last_service", 0, "Breakdowns since last service."),
    ("breakdown_chance", "u8", "breakdown_chance", 0, "Current native breakdown chance."),
    ("waiting_random_triggers", "u8", "waiting_random_triggers", 0, "Pending vehicle random triggers."),
    ("cargo_subtype", "u8", "cargo_subtype", 0, "Vehicle cargo subtype."),
    ("refit_capacity", "u16", "refit_cap", 0, "Capacity remaining from prior refit."),
    ("trip_occupancy", "i8", "trip_occupancy", 0, "Current-trip occupancy statistic."),
    ("group_id", "stable_id", "GroupID group_id", 65535, "Vehicle group stable ID."),
], "Vehicle identity, service, reliability, refit, payment and random state can change controller, costs and cargo behavior.",
"Vehicle::Tick/HandleBreakdown/HandleLoading -> authoritative boundary adapter")
scalar_group(7140, "vehicle.item.current_order", "src/order_base.h", "Order", "VehicleID numeric pool slot", [
    ("type_raw", "u8", "uint8_t type", 0, "Embedded current-order type and non-stop bits."),
    ("flags_raw", "u8", "uint8_t flags", 0, "Embedded current-order load/unload/depot flags."),
    ("destination", "u16", "DestinationID dest", 0, "Embedded current-order destination."),
    ("refit_cargo", "u8", "CargoType refit_cargo", 255, "Embedded current-order refit cargo."),
    ("wait_time", "u16", "uint16_t wait_time", 0, "Embedded current-order wait time."),
    ("travel_time", "u16", "uint16_t travel_time", 0, "Embedded current-order travel time."),
    ("maximum_speed", "u16", "uint16_t max_speed", 65535, "Embedded current-order speed limit."),
], "The embedded current order includes implicit/loading/leaving/depot state not recoverable from the OrderList alone.",
"ProcessOrders/HandleLoading -> Vehicle::current_order")
scalar_group(7160, "vehicle.item.order_progress", "src/base_consist.h", "BaseConsist", "VehicleID numeric pool slot", [
    ("current_order_time", "i32", "current_order_time", 0, "Ticks elapsed in current order."),
    ("lateness_counter", "i32", "lateness_counter", 0, "Timetable lateness/earliness."),
    ("timetable_start", "u64", "timetable_start", 0, "Absolute timetable start tick."),
    ("unbunching_last_departure", "u64", "depot_unbunching_last_departure", 0, "Last unbunching-depot departure tick."),
    ("unbunching_next_departure", "u64", "depot_unbunching_next_departure", 0, "Next unbunching-depot departure tick."),
    ("round_trip_time", "i32", "round_trip_time", 0, "Measured order-list round trip time."),
    ("vehicle_flags", "u16", "VehicleFlags vehicle_flags", 0, "Base-consist service/timetable flags."),
    ("service_interval", "u16", "service_interval", 0, "Per-vehicle service interval."),
    ("real_order_index", "u8", "cur_real_order_index", 0, "Current explicit order ordinal."),
    ("implicit_order_index", "u8", "cur_implicit_order_index", 0, "Current implicit order ordinal."),
], "Persistent timetable, service and order indices control order advancement and depot routing.",
"ProcessOrders -> UpdateVehicleTimetable -> NeedsServicing")
scalar_group(7180, "vehicle.item.cargo_cache", "src/cargopacket.h", "VehicleCargoList", "VehicleID numeric pool slot", [
    ("count", "u32", "uint count", 0, "Cached cargo unit count."),
    ("periods_in_transit", "u64", "cargo_periods_in_transit", 0, "Cached sum of cargo transit periods."),
    ("feeder_share", "i64", "Money feeder_share", 0, "Cached feeder-share total."),
    ("transfer_count", "u32", "action_counts", 0, "Cargo units designated for transfer."),
    ("deliver_count", "u32", "action_counts", 0, "Cargo units designated for delivery."),
    ("keep_count", "u32", "action_counts", 0, "Cargo units designated to remain onboard."),
    ("load_count", "u32", "action_counts", 0, "Cargo units designated for loading."),
], "Cargo-list caches and action partitions are consumed during staged load/unload and must conserve the packet total.",
"VehicleCargoList::Stage -> Shift -> CargoPayment")
for item in FIELDS:
    if item["path"].startswith("vehicle.item.cargo_cache."):
        item["cache_classification"] = "authoritative_cache"
        item["cache_invalidation_trigger"] = "packet append/remove/stage/shift/merge/split/age"
        item["deterministic_rebuild_procedure"] = "not claimed; field remains authoritative_full until clear/rebuild plus two-load 10000-tick continuation evidence passes"
scalar_group(7190, "vehicle.item.newgrf_cache", "src/vehicle_base.h", "NewGRFCache", "VehicleID numeric pool slot", [
    ("position_consist_length", "u32", "position_consist_length", 0, "NewGRF variable 40 cache."),
    ("position_same_id_length", "u32", "position_same_id_length", 0, "NewGRF variable 41 cache."),
    ("consist_cargo_information", "u32", "consist_cargo_information", 0, "NewGRF variable 42 cache."),
    ("company_information", "u32", "company_information", 0, "NewGRF variable 43 cache."),
    ("position_in_vehicle", "u32", "position_in_vehicle", 0, "NewGRF variable 4D cache."),
    ("validity_mask", "u8", "cache_valid", 0, "NewGRF cache validity mask."),
], "NewGRF cache state is included only as a source-backed unreachable family under the verified no-NewGRF fixture.",
"GetVehicleNewGRFVariable -> NewGRF callback path")
for item in FIELDS:
    if item["path"].startswith("vehicle.item.newgrf_cache."):
        item["classification"] = "out_of_scope_unreachable"
        item["fixture_reachability_status"] = "unreachable_verified_by-base-content-profile-and-zero-newgrf-callback-mask"
        item["cache_classification"] = "unreachable_cache"
        item["cache_invalidation_trigger"] = "NewGRF callback/property invalidation path excluded by content identity"
        item["deterministic_rebuild_procedure"] = "not applicable because content manifest proves no NewGRF is loaded"
scalar_group(7070, "road_vehicle.item", "src/roadveh.h", "RoadVehicle", "VehicleID numeric pool slot", [
    ("state", "u8", "uint8_t state", 0, "Road controller state/trackdir encoding."),
    ("frame", "u8", "uint8_t frame", 0, "Road movement frame."),
    ("blocked_counter", "u16", "blocked_ctr", 0, "Blocked movement counter."),
    ("overtaking_state", "u8", "uint8_t overtaking", 0, "Overtaking state."),
    ("overtaking_counter", "u8", "overtaking_ctr", 0, "Overtaking attempt counter."),
    ("crashed_counter", "u16", "crashed_ctr", 0, "Crash animation counter."),
    ("reverse_counter", "u8", "reverse_ctr", 0, "Reverse maneuver counter."),
    ("road_type", "u8", "RoadType roadtype", 0, "Current road type."),
    ("path_trackdirs", "u8", "RoadVehPathCache path", 0, "Authoritative cached path trackdirs in vector order."),
    ("path_tiles", "u32", "RoadVehPathCache path", 0, "Authoritative cached path tiles in the same vector order."),
], "RoadVehicle::path and controller counters persist across ticks and directly choose future movement.",
"RoadVehController -> RoadVehicle::path -> YapfRoadVehicleChooseTrack")
field(7080, "road_vehicle.item.compatible_road_types", "u64", "src/roadveh.h", "RoadTypes compatible_roadtypes",
      "Native compatible road and tram type mask for each road vehicle.",
      "Road movement, path selection, stop entry and depot validation read this mask directly.",
      owner="RoadVehicle", owner_rule="VehicleID numeric pool slot restricted to BaseVehicle::type Road", sample=1,
      reached_path="RoadVehicle::compatible_roadtypes -> RoadVehController/YAPF/RoadStop -> movement")
field(7069, "road_vehicle.item.count", "u32", "src/vehicle_base.h", "VehicleType::Road",
      "Number of occupied Vehicle pool slots whose native type is Road.",
      "Road-vehicle column counts must not be inferred from total Vehicle occupancy when other native vehicle types exist.",
      owner="vehicle_pool", owner_rule="singleton typed pool", sample=0,
      reached_path="Vehicle::Iterate -> type filter Road -> authoritative boundary adapter")
field(7068, "road_vehicle.item.ids", "stable_id", "src/roadveh.h", "struct RoadVehicle final :",
      "Stable VehicleIDs of occupied RoadVehicles.",
      "The discriminator maps road/ground subclass columns to shared VehiclePool slots when EffectVehicles are present.",
      owner="RoadVehicle", owner_rule="VehicleID numeric pool slot filtered by native type Road",
      shape="dynamic_array", fixed_count=None, count_source="road_vehicle.item.count", maximum_capacity=0xFF000,
      order="VehicleID ascending among occupied vehicles whose type is Road", sample=[0], sample_scope="one_element",
      reached_path="Vehicle::Iterate -> native type Road -> RoadVehicle controller/cache projection")
scalar_group(7090, "vehicle.item.cache", "src/ground_vehicle.hpp", "GroundVehicleCache", "VehicleID numeric pool slot", [
    ("weight", "u32", "cached_weight", 0, "Cached consist weight."),
    ("slope_resistance", "u32", "uint32_t cached_slope_resistance", 0, "Cached slope resistance."),
    ("maximum_tractive_effort", "u32", "cached_max_te", 0, "Cached maximum tractive effort."),
    ("axle_resistance", "u16", "cached_axle_resistance", 0, "Cached axle resistance."),
    ("maximum_track_speed", "u16", "cached_max_track_speed", 0, "Cached road-type speed limit."),
    ("power", "u32", "cached_power", 0, "Cached consist power."),
    ("air_drag", "u32", "cached_air_drag", 0, "Cached air-drag coefficient."),
    ("total_length", "u16", "cached_total_length", 0, "Cached consist length."),
    ("first_engine_id", "stable_id", "EngineID first_engine", 4294967295, "Cached front EngineID."),
    ("vehicle_length", "u8", "cached_veh_length", 0, "Cached individual vehicle length."),
], "Native acceleration and station-loading code consumes this cache directly.",
"RoadVehicle::CargoChanged/PowerChanged -> GroundVehicleCache -> RoadVehicle::UpdateSpeed")
scalar_group(7100, "vehicle.item.cache", "src/vehicle_base.h", "VehicleCache", "VehicleID numeric pool slot", [
    ("maximum_speed", "u16", "cached_max_speed", 0, "Cached consist maximum speed."),
    ("cargo_age_period", "u16", "cached_cargo_age_period", 0, "Cached number of ticks between cargo aging periods."),
], "Vehicle movement and cargo aging consume these cached values directly.",
"Vehicle::ConsistChanged -> VehicleCache -> Vehicle::Tick")
field(7110, "vehicle.item.ground_vehicle_flags", "u8", "src/ground_vehicle.hpp", "GroundVehicleFlags gv_flags",
      "Ground-vehicle slope and implicit-order suppression flags.",
      "Going-up and going-down flags change exact Z movement, while suppress-implicit-order changes order progression.",
      owner="GroundVehicle", owner_rule="VehicleID numeric pool slot restricted to ground vehicles", sample=0,
      reached_path="GroundVehicle::gv_flags -> UpdateInclination/ProcessOrders -> RoadVehicle::Tick")
field(7111, "vehicle.item.cache.last_display_speed", "u16", "src/ground_vehicle.hpp", "uint16_t last_speed",
      "Last speed copied into the display cache.",
      "Pinned consumers use this member only for redraw and display-speed reporting; it does not feed simulation movement.",
      owner="GroundVehicleCache", owner_rule="VehicleID numeric pool slot", sample=0,
      classification="diagnostic", cache="diagnostic_cache", invalidation="current speed change",
      rebuild="copy current native speed during display-dirty processing",
      reached_path="GroundVehicle::UpdateSpeed -> display dirty check -> GUI consumer")
field(7112, "vehicle.item.cache.visual_effect", "u8", "src/vehicle_base.h", "uint8_t cached_vis_effect",
      "Cached vehicle visual-effect selector.",
      "Vehicle::ShowVisualEffect consumes this cache in gameplay, may draw gameplay RNG, and allocates EffectVehicles in the shared VehiclePool.",
      owner="VehicleCache", owner_rule="VehicleID numeric pool slot", sample=0,
      cache="authoritative_cache", invalidation="vehicle property, consist, or visual callback change",
      rebuild="not claimed; field remains authoritative_full until clear/rebuild plus two-load 10000-tick continuation evidence passes",
      reached_path="RoadVehController -> Vehicle::ShowVisualEffect -> Chance16/CreateEffectVehicleRel")
for item in FIELDS:
    if item["path"].startswith("vehicle.item.cache.") and item["classification"] == "authoritative_full":
        item["cache_classification"] = "authoritative_cache"
        item["cache_invalidation_trigger"] = "consist, engine, road type, cargo, refit, or NewGRF property change"
        item["deterministic_rebuild_procedure"] = "not claimed; field remains authoritative_full until clear/rebuild plus two-load 10000-tick continuation evidence passes"

# OrderList pool. Orders are vector members, not a global Order pool; identity is list plus ordinal.
pool_meta(8000, "order_list", 64000, "_orderlist_pool")
scalar_group(8010, "order_list.item", "src/order_base.h", "OrderList", "OrderListID numeric pool slot", [
    ("id", "stable_id", "struct OrderList", 0, "Typed OrderList pool ID."),
    ("manual_order_count", "u8", "num_manual_orders", 0, "Number of manually inserted orders."),
    ("shared_vehicle_count", "u32", "num_vehicles", 0, "Vehicles sharing this list."),
    ("first_shared_vehicle_id", "stable_id", "Vehicle *first_shared", 4294967295, "First sharing vehicle stable ID."),
    ("order_count", "u32", "std::vector<Order> orders", 0, "Order vector count."),
    ("timetable_duration", "i32", "timetable_duration", 0, "Cached total timetabled duration."),
    ("total_duration", "i32", "total_duration", 0, "Cached total order duration."),
], "Order vector membership and duration caches drive order advancement and timing.",
"InsertOrder -> OrderList::RecalculateTimetableDuration -> ProcessOrders")
for item in FIELDS:
    if item["path"] in {"order_list.item.manual_order_count", "order_list.item.shared_vehicle_count", "order_list.item.timetable_duration", "order_list.item.total_duration"}:
        item["cache_classification"] = "authoritative_cache"
        item["cache_invalidation_trigger"] = "order insertion/deletion/move/modify, timetable change, or shared vehicle change"
        item["deterministic_rebuild_procedure"] = "not claimed; field remains authoritative_full until clear/rebuild plus two-load 10000-tick continuation evidence passes"
field(8039, "order.item.count", "u32", "src/order_base.h", "std::vector<Order> orders",
      "Total explicit orders across occupied OrderLists.",
      "The flattened (OrderListID, ordinal) projection requires an explicit bounded element count.",
      owner="order_list_pool", owner_rule="singleton typed pool", sample=0,
      reached_path="OrderList::Iterate -> orders.size -> authoritative boundary adapter")
field(8099, "order.global_order_pool", "u8", "src/order_base.h", "std::vector<Order> orders",
      "Proof entry for a global Order pool.",
      "Pinned OpenTTD stores Order values inside OrderList::orders; stable identity is (OrderListID, ordinal), so no global Order allocation state exists.",
      owner="order_model", owner_rule="singleton source model", sample=0,
      classification="out_of_scope_unreachable", reached="unreachable_absent-from-pinned-order-model",
      reached_path="OrderList source-owner review")
scalar_group(8040, "order.item", "src/order_base.h", "Order", "(OrderListID, zero-based ordinal); no global Order pool exists", [
    ("type_raw", "u8", "uint8_t type", 0, "Raw order type and non-stop bits."),
    ("flags_raw", "u8", "uint8_t flags", 0, "Raw load/unload/depot flags."),
    ("destination", "u16", "DestinationID dest", 0, "Order destination ID."),
    ("refit_cargo", "u8", "CargoType refit_cargo", 255, "Order refit cargo."),
    ("wait_time", "u16", "uint16_t wait_time", 0, "Order wait time."),
    ("travel_time", "u16", "uint16_t travel_time", 0, "Order travel time."),
    ("max_speed", "u16", "uint16_t max_speed", 65535, "Order speed limit."),
], "Every explicit order member can alter loading, routing, service, or timing.",
"ProcessOrders -> Order getters -> vehicle controller")

# Cargo packet identity, provenance and list/cache state.
pool_meta(9000, "cargo_packet", 16773120, "_cargopacket_pool", reached="reachable_after_industry_production")
scalar_group(9010, "cargo_packet.item", "src/cargopacket.h", "CargoPacket", "CargoPacketID numeric pool slot", [
    ("id", "stable_id", "struct CargoPacket : CargoPacketPool", 0, "Typed cargo packet pool ID."),
    ("count", "u16", "uint16_t count", 0, "Cargo units in packet."),
    ("periods_in_transit", "u16", "periods_in_transit", 0, "Cargo age periods."),
    ("feeder_share", "i64", "Money feeder_share", 0, "Accumulated feeder share."),
    ("source_tile", "u32", "TileIndex source_xy", 4294967295, "Cargo origin/loading tile."),
    ("travelled_x", "i16", "Coord2D<int16_t> travelled", 0, "Signed travelled X vector."),
    ("travelled_y", "i16", "Coord2D<int16_t> travelled", 0, "Signed travelled Y vector."),
    ("source_id", "u16", "Source source", 0, "Cargo source numeric ID."),
    ("source_type", "u8", "Source source", 1, "Cargo source type."),
    ("first_station_id", "stable_id", "first_station", 4294967295, "First station stable ID."),
    ("next_hop_station_id", "stable_id", "next_hop", 4294967295, "Next-hop station stable ID."),
    ("container_kind", "u8", "StationCargoList", 0, "Owning station/vehicle container discriminator."),
    ("container_id", "stable_id", "Tcont packets{}", 0, "Owning station or vehicle stable ID."),
    ("container_ordinal", "u32", "CargoPacketList", 0, "Packet order within owner container."),
], "Packet amount alone is insufficient; provenance, age, ownership and exact list order determine payment and merge behavior.",
"CargoPacket::Split/Merge -> StationCargoList/VehicleCargoList -> DeliverGoods")
field(9099, "cargo_packet.persistent_split_merge_flag", "u8", "src/cargopacket.h", "CargoPacket *Split",
      "Proof entry for persistent packet split/merge operation flags.",
      "Split and Merge mutate packet pool membership, counts and ordered containers atomically; pinned CargoPacket stores no separate persistent operation flag.",
      owner="cargo_packet_model", owner_rule="singleton source model", sample=0,
      classification="out_of_scope_unreachable", reached="unreachable_absent-from-pinned-CargoPacket-storage",
      reached_path="CargoPacket::Split/Merge source-owner review")

# Persistent route/cache values are authoritative until a full two-load 10,000-tick proof exists.
scalar_group(10000, "route", "src/pathfinder/yapf/yapf_road.cpp", "RoadVehPathCache", "VehicleID numeric pool slot", [
    ("path_invocation_ordinal", "u64", "YapfRoadVehicleChooseTrack", 0, "Per-run road pathfinder invocation ordinal."),
    ("start_tile", "u32", "YapfRoadVehicleChooseTrack", 0, "Pathfinder start tile."),
    ("start_direction", "u8", "YapfRoadVehicleChooseTrack", 0, "Pathfinder incoming direction."),
    ("target_tile", "u32", "YapfRoadVehicleChooseTrack", 0, "Pathfinder target tile."),
    ("target_station_id", "stable_id", "YapfRoadVehicleChooseTrack", 0, "Target station stable ID."),
    ("selected_trackdir", "u8", "YapfRoadVehicleChooseTrack", 0, "Selected first trackdir."),
    ("path_cost", "i32", "YapfRoadVehicleChooseTrack", 0, "Winning YAPF path cost."),
    ("no_route", "u8", "YapfRoadVehicleChooseTrack", 0, "No-route result state."),
    ("node_limit_hit", "u8", "YapfRoadVehicleChooseTrack", 0, "Search node-limit result state."),
    ("controller_decision", "u8", "YapfRoadVehicleChooseTrack", 0, "Persistent controller decision at boundary."),
    ("station_entry_state", "u8", "YapfRoadVehicleChooseTrack", 0, "Road-stop/station entry decision state."),
    ("depot_entry_state", "u8", "YapfRoadVehicleChooseTrack", 0, "Depot entry decision state."),
], "Route inputs, tie result and persistent path/controller state select the next physical transition.",
"RoadVehController -> YapfRoadVehicleChooseTrack -> RoadVehicle::path")
for f in FIELDS:
    if f["path"].startswith("route."):
        f["classification"] = "diagnostic"
        f["cache_classification"] = "not_cache"
        f["cache_invalidation_trigger"] = "not_applicable"
        f["deterministic_rebuild_procedure"] = "not_applicable"
        f["sampling_boundary"] = "each native YAPF/controller invocation"
        f["future_influence_rationale"] = "This per-call observation localizes route/controller divergence but is not persistent state consumed by a subsequent simulation step."
    if f["path"].endswith("path_trackdirs") or f["path"].endswith("path_tiles"):
        f["cache_classification"] = "authoritative_cache"
        f["cache_invalidation_trigger"] = "road/station/depot topology mutation, order destination change, or native path consumption"
        f["deterministic_rebuild_procedure"] = "not claimed; field remains authoritative_full until clear/rebuild plus two-load 10000-tick continuation evidence passes"
field(10020, "route.native_topology_revision_counter", "u8", "src/roadveh.h", "using RoadVehPathCache",
      "Proof entry for a native route topology revision counter.",
      "Pinned RoadVehPathCache is only an ordered vector of (trackdir,tile); no revision counter exists and inventing one would misrepresent native state.",
      owner="road_route_model", owner_rule="VehicleID road vehicle", sample=0,
      classification="out_of_scope_unreachable", reached="unreachable_absent-from-pinned-RoadVehPathCache-storage",
      reached_path="RoadVehPathCache source-owner review")

# Cross-family diagnostics make conservation, native cost category and callback
# order directly explainable. They never substitute for the complete fields.
scalar_group(11000, "diagnostic.cargo", "src/economy.cpp", "static Money DeliverGoods(", "singleton boundary diagnostic", [
    ("produced_units", "u64", "DeliverGoods", 0, "Cumulative cargo units produced during the run."),
    ("station_units", "u64", "DeliverGoods", 0, "Cargo units currently in station containers."),
    ("vehicle_units", "u64", "DeliverGoods", 0, "Cargo units currently in vehicle containers."),
    ("delivered_units", "u64", "DeliverGoods", 0, "Cumulative cargo units delivered."),
    ("destroyed_units", "u64", "DeliverGoods", 0, "Cumulative cargo units destroyed by a source-backed native path."),
], "These independently recomputed values identify the phase of a conservation mismatch.",
"ProduceIndustryGoods/MoveGoodsToStation/LoadUnloadVehicle/DeliverGoods")
scalar_group(11010, "diagnostic.ledger", "src/company_cmd.cpp", "SubtractMoneyFromCompany", "last native command/result boundary", [
    ("expense_type", "u8", "ExpensesType", 0, "Native command/payment expense category."),
    ("amount", "i64", "SubtractMoneyFromCompany", 0, "Native command/payment debit or credit."),
], "Boundary diagnostics localize category and rounding mismatch while Company ledger fields remain authoritative.",
"CommandCost -> SubtractMoneyFromCompany -> command result record")
for item in FIELDS:
    if item["path"].startswith("diagnostic."):
        item["classification"] = "diagnostic"
        item["consumed_by_simulation"] = False

# Scope-correcting continuation pools found by the independent audit.
pool_meta(12000, "town", 64000, "_town_pool")
scalar_group(12010, "town.item", "src/town.h", "Town", "TownID numeric pool slot", [
    ("id", "stable_id", "struct Town : TownPool", 0, "Typed town pool ID."),
    ("anchor_tile", "u32", "TileIndex xy", 1056, "Town anchor tile."),
    ("population", "u32", "population", 0, "Town population."),
    ("house_count", "u32", "num_houses", 0, "Town house count."),
    ("growth_rate", "u16", "uint16_t growth_rate", 0, "Town growth interval."),
    ("growth_counter", "u16", "grow_counter", 0, "Town growth countdown."),
    ("flags", "u8", "TownFlags flags", 0, "Native town flags."),
    ("ratings", "i16", "TypedIndexContainer<std::array<int16_t, MAX_COMPANIES>, CompanyID> ratings", 0, "Company authority ratings."),
    ("supplied_slot_owner_count", "u32", "SuppliedCargoes supplied", 0, "Produced-cargo slot count for each town owner."),
    ("zone_radius_squared", "u32", "std::array<uint32_t, NUM_HOUSE_ZONES> squared_town_zone_radius", 0, "Cached squared authority-zone radii."),
    ("building_id_counts", "u16", "std::vector<T> id_count", 0, "Cached native building counts indexed by HouseID."),
], "The fixture retains TownID 0; town counters, ratings and production can influence road construction, commands and cargo.",
"Town::Tick -> TownActions -> GenerateTownCargo")
field(12021, "town.item.building_class_counts", "u16", "src/town.h", "std::vector<T> class_count",
      "Cached native building counts indexed by HouseClassID.",
      "House class and house ID counts are independent native vectors; either can affect subsequent town generation and callbacks.",
      owner="Town", owner_rule="TownID then HouseClassID vector index", sample=[0], sample_scope="one_element",
      shape="dynamic_array", fixed_count=None, count_source="town.building_class_count_total",
      maximum_capacity=1073741824, order="TownID ascending, then native class_count index ascending",
      cache="authoritative_cache", invalidation="house construction/removal or after-load town rebuild",
      rebuild="not claimed; field remains authoritative_full until clear/rebuild plus two-load 10000-tick continuation evidence passes",
      reached_path="TownCache::building_counts.class_count -> house/town callbacks")
scalar_group(12030, "town.item", "src/town.h", "Town", "TownID numeric pool slot", [
    ("subsidy_role_mask", "u8", "part_of_subsidy", 0, "Cached source/destination subsidy-role mask."),
    ("name_grfid", "u32", "townnamegrfid", 0, "Town-name generator GRF identifier."),
    ("name_type", "u16", "townnametype", 0, "Town-name generator type."),
    ("name_parts", "u32", "townnameparts", 0, "Town-name generation random parts."),
    ("noise_reached", "u16", "noise_reached", 0, "Airport noise already attributed to town."),
    ("statue_company_mask", "u16", "CompanyMask statues", 0, "Companies with a town statue."),
    ("rating_present_mask", "u16", "have_ratings", 0, "Companies with an initialized authority rating."),
    ("unwanted_months", "u8", "unwanted{}", 0, "Authority bribe penalty months by CompanyID."),
    ("exclusive_company_id", "u8", "CompanyID exclusivity", 255, "Company holding exclusive transport rights."),
    ("exclusive_months", "u8", "exclusive_counter", 0, "Exclusive-rights remaining months."),
    ("supplied_cargo_type", "u8", "CargoType cargo", 0, "Town supplied-history cargo keys."),
    ("supplied_production", "u32", "uint32_t production", 0, "Town supplied production history by cargo and month."),
    ("supplied_transported", "u32", "uint32_t transported", 0, "Town transported history by cargo and month."),
    ("accepted_cargo_type", "u8", "CargoType cargo", 0, "Town accepted-history cargo keys."),
    ("accepted_amount", "u32", "uint32_t accepted", 0, "Town accepted history by cargo and month."),
    ("growth_goal", "u32", "EnumIndexArray<uint32_t", 0, "Cargo goals controlling town growth."),
    ("valid_history_mask", "u64", "ValidHistoryMask valid_history", 0, "Valid supplied/accepted history periods."),
    ("nearby_station_ids", "stable_id", "StationList stations_near", 0, "Nearby StationIDs in canonical order."),
    ("time_until_rebuild", "u16", "time_until_rebuild", 0, "Town house-rebuild timer."),
    ("fund_buildings_months", "u8", "fund_buildings_months", 0, "Fund-building program remaining months."),
    ("road_build_months", "u8", "road_build_months", 0, "Road reconstruction program remaining months."),
    ("larger_town", "u8", "larger_town", 0, "Larger-town growth multiplier flag."),
    ("layout", "u8", "TownLayout layout", 0, "Town-specific road layout."),
], "Town authority, cargo history, programs and growth state can alter subsequent commands, cargo and map mutation.",
"Town::Tick -> UpdateTownGrowRate/GenerateTownCargo/CheckforTownRating")
scalar_group(12070, "town.item", "src/town_type.h", "TransportedCargoStat", "TownID then TownAcceptanceEffect", [
    ("received_old_max", "u16", "Tstorage old_max", 0, "Prior-month received cargo goal maximum."),
    ("received_new_max", "u16", "Tstorage new_max", 0, "Current-month received cargo goal maximum."),
    ("received_old_actual", "u16", "Tstorage old_act", 0, "Prior-month actual received cargo."),
    ("received_new_actual", "u16", "Tstorage new_act", 0, "Current-month actual received cargo."),
], "Received-cargo statistics determine growth eligibility.",
"Town::NewMonth -> TransportedCargoStat::NewMonth -> UpdateTownGrowRate")
field(12060, "town.item.custom_name", "diagnostic_utf8", "src/town.h", "std::string name",
      "Custom town name diagnostic value.",
      "Names are retained for diagnosis but the declared command corpus never performs name-dependent UI or naming commands.",
      owner="Town", owner_rule="TownID numeric pool slot", sample="", classification="diagnostic",
      reached_path="town save state -> diagnostic trace adapter")
field(12061, "town.item.cached_name", "diagnostic_utf8", "src/town.h", "cached_name",
      "Resolved display-name cache, read without invoking the lazy getter.",
      "The display cache is not consumed by the declared gameplay path; logging must not call GetCachedName because it mutates this cache.",
      owner="Town", owner_rule="TownID numeric pool slot", sample="", classification="diagnostic",
      cache="diagnostic_cache", invalidation="town rename, language/content name invalidation",
      rebuild="display-only FillCachedName; never invoked by authoritative adapter",
      reached_path="direct const trace adapter read; GetCachedName is prohibited")
field(12062, "town.item.newgrf_persistent_storage_ids", "stable_id", "src/town.h", "psa_list",
      "Town NewGRF persistent-storage references.",
      "The verified OpenGFX-only fixture installs no NewGRF and the command corpus cannot create town persistent storage.",
      owner="Town", owner_rule="TownID numeric pool slot", shape="dynamic_array", fixed_count=None,
      count_source="town.pool.occupied_count", maximum_capacity=64000, sample=[65535], sample_scope="one_element",
      classification="out_of_scope_unreachable", reached="unreachable_verified_by_base-content-profile-and-command-set",
      reached_path="NewGRF town callback path excluded by content manifest")
field(12063, "town.item.accepted_slot_owner_count", "u32", "src/town.h", "AcceptedCargoes accepted",
      "Accepted-cargo slot count for each town owner.",
      "Per-owner counts preserve empty-owner boundaries and partition the flattened accepted history columns.",
      owner="Town", owner_rule="TownID numeric pool slot", sample=0,
      reached_path="Town::accepted -> Town::NewMonth -> authoritative boundary adapter")
for item in FIELDS:
    if item["path"] in {"town.item.population", "town.item.house_count", "town.item.zone_radius_squared", "town.item.building_id_counts", "town.item.building_class_counts"}:
        item["cache_classification"] = "authoritative_cache"
        item["cache_invalidation_trigger"] = "house construction/removal, town radius update, or after-load town rebuild"
        item["deterministic_rebuild_procedure"] = "not claimed; field remains authoritative_full until clear/rebuild plus two-load 10000-tick continuation evidence passes"
pool_meta(12100, "depot", 64000, "_depot_pool", reached="reachable_after_depot_command")
scalar_group(12110, "depot.item", "src/depot_base.h", "Depot", "DepotID numeric pool slot", [
    ("id", "stable_id", "struct Depot", 0, "Typed depot pool ID."),
    ("tile", "u32", "TileIndex xy", 0, "Depot map tile."),
    ("town_id", "stable_id", "Town *town", 0, "Associated town stable ID."),
    ("town_sequence", "u16", "town_cn", 0, "Town-local depot number."),
    ("build_date", "i32", "build_date", 712223, "Depot construction date."),
], "Depot allocation and identity affect vehicle construction, servicing and routing.",
"CmdBuildRoadDepot -> Depot::Depot -> CmdBuildVehicle")
pool_meta(12200, "engine", 64000, "_engine_pool")
scalar_group(12210, "engine.item", "src/engine_base.h", "Engine", "EngineID numeric pool slot", [
    ("id", "stable_id", "class Engine : public EnginePool", 123, "Typed engine pool ID."),
    ("company_available_mask", "u16", "company_avail", 1, "Company availability mask."),
    ("intro_date", "i32", "intro_date", 0, "Engine introduction date."),
    ("age_months", "i32", "int32_t age", 0, "Engine age in months."),
    ("reliability", "u16", "uint16_t reliability", 0, "Current engine reliability."),
    ("flags", "u8", "EngineFlags flags", 0, "Engine availability and preview flags."),
    ("preview_company", "u8", "preview_company", 255, "Company receiving preview."),
    ("preview_wait", "u8", "preview_wait", 0, "Preview timeout."),
    ("vehicle_type", "u8", "VehicleType type", 1, "Engine vehicle type."),
    ("list_position", "u16", "list_position", 0, "Stable engine list position used for ordering."),
], "Engine availability, price/capacity inputs and reliability state govern lawful purchase and subsequent vehicle behavior.",
"StartupEngines -> Engine::IsEnabled -> CmdBuildVehicle")
scalar_group(12220, "engine.item", "src/engine_base.h", "Engine", "EngineID numeric pool slot", [
    ("company_hidden_mask", "u16", "company_hidden", 0, "Company hidden-engine mask."),
    ("preview_asked_mask", "u16", "preview_asked", 0, "Companies already offered an engine preview."),
    ("reliability_speed_decrease", "u16", "reliability_spd_dec", 0, "Engine reliability decay speed."),
    ("reliability_start", "u16", "reliability_start", 0, "Initial engine reliability."),
    ("reliability_maximum", "u16", "reliability_max", 0, "Maximum engine reliability."),
    ("reliability_final", "u16", "reliability_final", 0, "Final engine reliability."),
    ("reliability_phase1_months", "u16", "duration_phase_1", 0, "First reliability phase duration."),
    ("reliability_phase2_months", "u16", "duration_phase_2", 0, "Second reliability phase duration."),
    ("reliability_phase3_months", "u16", "duration_phase_3", 0, "Third reliability phase duration."),
], "Engine aging and preview state changes availability, purchase legality and vehicle reliability initialization.",
"EnginesMonthlyLoop -> CalcEngineReliability -> CmdBuildVehicle")
scalar_group(12240, "engine.item.info", "src/engine_type.h", "EngineInfo", "EngineID numeric pool slot", [
    ("base_intro_date", "i32", "Date base_intro", 0, "Base introduction date."),
    ("life_length_years", "i32", "Year lifelength", 0, "Built vehicle lifetime."),
    ("availability_years", "i32", "Year base_life", 0, "Engine availability duration."),
    ("decay_speed", "u8", "decay_speed", 0, "Reliability decay parameter."),
    ("load_amount", "u8", "load_amount", 0, "Cargo units loaded per loading cycle."),
    ("climate_mask", "u8", "LandscapeTypes climates", 1, "Supported climate mask."),
    ("cargo_type", "u8", "CargoType cargo_type", 1, "Default engine cargo type."),
    ("refit_mask", "u64", "CargoTypes refit_mask", 0, "Permitted refit cargo mask."),
    ("refit_cost", "u8", "refit_cost", 0, "Refit cost factor."),
    ("misc_flags", "u8", "EngineMiscFlags misc_flags", 0, "Engine behavior flags."),
    ("callback_mask", "u16", "VehicleCallbackMasks callback_mask", 0, "Enabled property callback mask."),
    ("retire_early", "i8", "retire_early", 0, "Early retirement years."),
    ("extra_flags", "u8", "ExtraEngineFlags extra_flags", 0, "Additional availability flags."),
    ("cargo_age_period", "u16", "cargo_age_period", 0, "Cargo aging period initialized into vehicles."),
    ("variant_engine_id", "stable_id", "EngineID variant_id", 65535, "Engine variant stable ID."),
], "EngineInfo values initialize and continuously parameterize capacity, loading, aging, callbacks and availability.",
"Engine::IsEnabled/DetermineCapacity -> CmdBuildVehicle -> Vehicle::Tick")
scalar_group(12270, "engine.item.road", "src/engine_type.h", "RoadVehicleInfo", "EngineID numeric pool slot", [
    ("image_index", "u8", "uint8_t image_index", 0, "Road engine image index."),
    ("cost_factor", "u8", "cost_factor", 0, "Road vehicle purchase cost factor."),
    ("running_cost", "u8", "uint8_t running_cost", 0, "Road vehicle running-cost factor."),
    ("running_cost_class", "u8", "Price running_cost_class", 0, "Running-cost price class."),
    ("maximum_speed", "u16", "uint16_t max_speed", 0, "Native road vehicle maximum speed."),
    ("capacity", "u8", "uint8_t capacity", 0, "Default cargo capacity."),
    ("weight_quarter_tonnes", "u8", "uint8_t weight", 0, "Vehicle empty weight in quarter tonnes."),
    ("power_tens_hp", "u8", "uint8_t power", 0, "Engine power in tens of horsepower."),
    ("tractive_effort", "u8", "tractive_effort", 76, "Tractive effort coefficient."),
    ("air_drag", "u8", "uint8_t air_drag", 0, "Air-drag coefficient."),
    ("shorten_factor", "u8", "shorten_factor", 0, "Map length shortening factor."),
    ("road_type", "u8", "RoadType roadtype", 0, "Compatible native road type."),
], "RoadVehicleInfo controls purchase cost, capacity, speed and every acceleration calculation.",
"CmdBuildVehicle -> RoadVehicle::GetWeight/GetPower/UpdateSpeed")
field(12208, "engine.road_engine_ids", "stable_id", "src/engine_base.h", "VehicleType type",
      "EngineIDs whose native Engine::type is Road.",
      "The explicit discriminator column maps sparse road-engine property columns back to stable EngineIDs.",
      owner="engine_pool", owner_rule="EngineID numeric pool slot filtered by native type Road",
      shape="dynamic_array", fixed_count=None, count_source="engine.road_engine_count", maximum_capacity=64000,
      order="EngineID ascending among occupied engines whose type is Road", sample=[0], sample_scope="one_element",
      reached_path="Engine::Iterate -> Engine::type filter Road -> road property projection")
pool_meta(12300, "cargo_payment", 0xFF000, "_cargo_payment_pool", reached="reachable_during_unloading")
scalar_group(12310, "cargo_payment.item", "src/economy_base.h", "CargoPayment", "CargoPaymentID numeric pool slot", [
    ("id", "stable_id", "struct CargoPayment", 0, "Typed CargoPayment pool ID."),
    ("current_station_id", "stable_id", "current_station", 65535, "Current unloading station stable ID."),
    ("vehicle_id", "stable_id", "Vehicle *front", 0, "Paid vehicle stable ID."),
    ("route_profit", "i64", "route_profit", 0, "Accumulated route profit."),
    ("visual_profit", "i64", "visual_profit", 0, "Accumulated displayed profit that also feeds vehicle accounting."),
    ("visual_transfer", "i64", "visual_transfer", 0, "Accumulated transfer value."),
], "CargoPayment survives staged unload operations and its accumulators affect exact company and vehicle ledger updates.",
"Vehicle::BeginLoading -> CargoPayment::PayFinalDelivery -> Vehicle::EndLoading")
pool_meta(12400, "subsidy", 256, "_subsidy_pool", reached="reachable_if_native_subsidy_state_exists")
scalar_group(12410, "subsidy.item", "src/subsidy_base.h", "Subsidy", "SubsidyID numeric pool slot", [
    ("id", "stable_id", "struct Subsidy", 0, "Typed subsidy pool ID."),
    ("cargo_type", "u8", "CargoType cargo_type", 0, "Subsidized cargo type."),
    ("remaining", "u16", "remaining", 0, "Subsidy lifetime counter."),
    ("awarded_company", "u8", "CompanyID awarded", 255, "Awarded company ID."),
    ("source_id", "u16", "Source src", 0, "Subsidy source ID."),
    ("source_type", "u8", "Source src", 0, "Subsidy source type discriminator."),
    ("destination_id", "u16", "Source dst", 0, "Subsidy destination ID."),
    ("destination_type", "u8", "Source dst", 0, "Subsidy destination type discriminator."),
], "Any present subsidy changes delivery income; zero duration does not justify omitting native pool identity.",
"SubsidyMonthlyLoop -> CheckSubsidised -> DeliverGoods")
pool_meta(12500, "linkgraph", 65535, "_link_graph_pool", reached="manual_distribution_normally_empty_but_state_must_be_verified")
scalar_group(12510, "linkgraph.item", "src/linkgraph/linkgraph.h", "LinkGraph", "LinkGraphID numeric pool slot", [
    ("id", "stable_id", "class LinkGraph : public LinkGraphPool", 0, "Typed LinkGraph pool ID."),
    ("last_compression", "i32", "last_compression", 0, "Last compression economy date."),
    ("cargo_type", "u8", "CargoType cargo = INVALID_CARGO;", 0, "Graph cargo type."),
    ("node_count", "u32", "nodes", 0, "Graph node count."),
    ("node_station_ids", "stable_id", "StationID station", 0, "Node station IDs in node-index order."),
    ("edge_capacities", "u32", "capacity", 0, "Edge capacity values in canonical matrix order."),
    ("edge_usages", "u32", "usage", 0, "Edge usage values in canonical matrix order."),
    ("edge_travel_times", "u64", "uint64_t travel_time_sum", 0, "Edge travel-time accumulators."),
], "If any graph exists, its node/edge state can alter packet next-hop assignment and subsequent cargo flow.",
"LinkGraphSchedule::SpawnNext -> LinkGraphJob -> GoodsEntry::flows")

# Explicit flattened-count/offset fields make every nested variable-length
# family uniquely decodable, including empty owners. Offsets contain one entry
# per owner plus a final total and are ordered by stable owner ID.
for args in [
    (4070, "company.ledger.delivered_cargo_cell_count", "src/company_base.h", "delivered_cargo", "Flattened company/cargo delivered-ledger cell count."),
    (4071, "company.ledger.road_infrastructure_cell_count", "src/company_base.h", "road{}", "Flattened company/road-type infrastructure cell count."),
    (4072, "company.history.entry_count", "src/company_base.h", "old_economy", "Flattened company/quarter history entry count."),
    (4073, "company.history.delivered_cargo_cell_count", "src/company_base.h", "old_economy", "Flattened company/quarter/cargo delivered-history cell count."),
    (4074, "company.road_unit_word_count_total", "src/company_base.h", "used_bitmap", "Total stored words across road FreeUnitIDGenerator vectors."),
    (4075, "company.owner_offset_count", "src/company_base.h", "struct Company : CompanyProperties", "Company owner-offset count, occupied companies plus one."),
    (4076, "company.ledger.rail_infrastructure_cell_count", "src/company_base.h", "rail{}", "Flattened company/rail-type infrastructure cell count."),
    (4077, "company.group_unit_word_count_total", "src/company_base.h", "FreeUnitIDGenerator freegroups", "Total stored words across group FreeUnitIDGenerator vectors."),
    (8020, "order.owner_offset_count", "src/order_base.h", "std::vector<Order> orders", "OrderList owner-offset count, occupied lists plus one."),
    (5060, "industry.produced_slot_count", "src/industry.h", "ProducedCargoes produced", "Total produced-cargo slots across industries."),
    (5061, "industry.accepted_slot_count", "src/industry.h", "AcceptedCargoes accepted", "Total accepted-cargo slots across industries."),
    (5062, "industry.produced_history_cell_count", "src/industry.h", "HistoryData<ProducedHistory>", "Flattened produced history cell count."),
    (5063, "industry.accepted_history_cell_count", "src/industry.h", "HistoryData<AcceptedHistory>", "Flattened accepted history cell count."),
    (5064, "industry.nearby_station_ref_count", "src/industry.h", "StationList stations_near", "Total industry nearby-station references."),
    (5065, "industry.owner_offset_count", "src/industry.h", "struct Industry", "Industry owner-offset count, occupied industries plus one."),
    (5071, "industry.produced_history_offset_count", "src/industry.h", "ProducedCargoes produced", "Produced-history offset count, produced slots plus one."),
    (5072, "industry.accepted_history_offset_count", "src/industry.h", "AcceptedCargoes accepted", "Accepted-history offset count, accepted slots plus one."),
    (6060, "station.goods.entry_count", "src/cargotype.h", "NUM_CARGO", "Station GoodsEntry count: occupied stations times NUM_CARGO."),
    (6061, "station.catchment_bit_count", "src/station_base.h", "catchment_tiles", "Flattened exact station catchment bit count."),
    (6062, "station.loading_vehicle_ref_count", "src/station_base.h", "loading_vehicles", "Total station loading-vehicle references."),
    (6063, "station.nearby_industry_ref_count", "src/station_base.h", "industries_near", "Total station nearby-industry references."),
    (6064, "station.custom_roadstop_tile_count", "src/base_station_base.h", "custom_roadstop_tile_data", "Total custom road-stop tile records."),
    (6065, "station.owner_offset_count", "src/station_base.h", "struct Station", "Station owner-offset count, occupied stations plus one."),
    (6066, "station.tile_waiting_trigger_record_count", "src/base_station_base.h", "tile_waiting_random_triggers", "Total per-tile waiting-trigger records."),
    (6120, "road_stop.entries_count", "src/roadstop_base.h", "Entries *entries = nullptr", "Number of RoadStops with allocated drive-through Entries storage."),
    (6121, "road_stop.owner_offset_count", "src/roadstop_base.h", "struct RoadStop : RoadStopPool", "RoadStop owner-offset count, occupied RoadStops plus one."),
    (6071, "station.goods.packet_ref_count", "src/station_base.h", "StationCargoList cargo", "Total packet references across GoodsEntry cargo maps."),
    (6072, "station.goods.flow_owner_count", "src/station_base.h", "FlowStatMap flows", "Total FlowStat owners across GoodsEntry flow maps."),
    (6073, "station.goods.flow_share_count", "src/station_base.h", "SharesMap shares", "Total cumulative flow-share pairs across FlowStat owners."),
    (6074, "station.goods.owner_offset_count", "src/station_base.h", "std::array<GoodsEntry, NUM_CARGO> goods", "GoodsEntry owner-offset count, entries plus one."),
    (6075, "station.goods.flow_owner_offset_count", "src/station_base.h", "FlowStatMap flows", "FlowStat share-offset count, flow owners plus one."),
    (7200, "vehicle.cargo_packet_ref_count", "src/vehicle_base.h", "VehicleCargoList cargo", "Total vehicle cargo-packet references."),
    (7201, "vehicle.owner_offset_count", "src/vehicle_base.h", "struct Vehicle : VehiclePool", "Vehicle owner-offset count, occupied vehicles plus one."),
    (7202, "road_vehicle.path_element_count", "src/roadveh.h", "RoadVehPathCache path", "Total cached road path elements."),
    (7203, "road_vehicle.owner_offset_count", "src/roadveh.h", "struct RoadVehicle final :", "Road-vehicle owner-offset count, road vehicles plus one."),
    (12080, "town.supplied_slot_count", "src/town.h", "SuppliedCargoes supplied", "Total town supplied-cargo slots."),
    (12081, "town.accepted_slot_count", "src/town.h", "AcceptedCargoes accepted", "Total town accepted-cargo slots."),
    (12082, "town.supplied_history_cell_count", "src/town.h", "HistoryData<SuppliedHistory>", "Flattened town supplied-history cell count."),
    (12083, "town.rating_cell_count", "src/town.h", "CompanyID> ratings{}", "Flattened TownID/CompanyID rating cell count."),
    (12084, "town.nearby_station_ref_count", "src/town.h", "StationList stations_near", "Total town nearby-station references."),
    (12085, "town.owner_offset_count", "src/town.h", "struct Town : TownPool", "Town owner-offset count, occupied towns plus one."),
    (12092, "town.supplied_history_offset_count", "src/town.h", "SuppliedCargoes supplied", "Supplied-history offset count, supplied slots plus one."),
    (12093, "town.accepted_history_offset_count", "src/town.h", "AcceptedCargoes accepted", "Accepted-history offset count, accepted slots plus one."),
    (12094, "town.accepted_history_cell_count", "src/town.h", "HistoryData<AcceptedHistory>", "Flattened town accepted-history cell count."),
    (12022, "town.zone_radius_cell_count", "src/town.h", "std::array<uint32_t, NUM_HOUSE_ZONES> squared_town_zone_radius", "Flattened TownID/house-zone radius cell count."),
    (12023, "town.building_id_count_total", "src/town.h", "std::vector<T> id_count", "Total stored building ID count cells across towns."),
    (12024, "town.building_class_count_total", "src/town.h", "std::vector<T> class_count", "Total stored building class count cells across towns."),
    (12027, "town.acceptance_effect_cell_count", "src/town.h", "EnumIndexArray<uint32_t, TownAcceptanceEffect", "Flattened TownID/TownAcceptanceEffect cell count."),
    (12207, "engine.road_engine_count", "src/engine_base.h", "VehicleType type", "Count of occupied road-engine entries."),
    (12505, "linkgraph.node_count_total", "src/linkgraph/linkgraph.h", "NodeVector nodes{}", "Total LinkGraph nodes."),
    (12506, "linkgraph.edge_count_total", "src/linkgraph/linkgraph.h", "std::vector<BaseEdge> edges", "Total canonical LinkGraph edges."),
    (12507, "linkgraph.owner_offset_count", "src/linkgraph/linkgraph.h", "class LinkGraph :", "LinkGraph owner-offset count, occupied graphs plus one."),
    (12530, "linkgraph.node_offset_count", "src/linkgraph/linkgraph.h", "NodeVector nodes{}", "LinkGraph edge-offset count, flattened nodes plus one."),
    (12532, "linkgraph.schedule_count", "src/linkgraph/linkgraphschedule.h", "GraphList schedule", "Number of queued LinkGraphs in exact schedule order."),
    (12533, "linkgraph.running_job_count", "src/linkgraph/linkgraphschedule.h", "JobList running", "Number of LinkGraphJobs in exact running-list order."),
]:
    field(args[0], args[1], "u32", args[2], args[3], args[4],
          "This explicit aggregate count makes the flattened canonical field representation uniquely decodable.",
          owner="projection_structure", owner_rule="singleton complete projection", sample=0,
          reached_path="native container sizes -> read-only projection adapter")

# Offset-count values are totals plus one even when the underlying owner set is
# empty. They are explicit scalar projection structure, not native members.
for item in FIELDS:
    if item["path"].endswith("offset_count"):
        item["sample_logical_value"] = 1

def offset_field(field_id: int, path: str, source_file: str, source_symbol: str,
                 count_source: str, maximum: int, description: str, target_count: str) -> None:
    field(field_id, path, "u32", source_file, source_symbol, description,
          "Offsets preserve each empty and non-empty owner's exact nested boundaries in the flattened canonical projection.",
          owner="projection_structure", owner_rule="one offset per stable owner plus final aggregate total",
          shape="dynamic_array", fixed_count=None, count_source=count_source, maximum_capacity=maximum,
          order="stable owner ID ascending; offset zero first; final entry equals aggregate count",
          sample=[0], sample_scope="one_element",
          reached_path="native container sizes -> prefix-sum projection adapter")
    FIELDS[-1]["offset_target_count_field"] = target_count

for args in [
    (4080, "company.ledger.expense_offsets", "src/company_base.h", "yearly_expenses", "company.owner_offset_count", 16, "Per-company expense-ledger offsets.", "company.ledger.expense_cell_count"),
    (4081, "company.ledger.delivered_cargo_offsets", "src/company_base.h", "delivered_cargo", "company.owner_offset_count", 16, "Per-company delivered-cargo offsets.", "company.ledger.delivered_cargo_cell_count"),
    (4082, "company.ledger.road_infrastructure_offsets", "src/company_base.h", "road{}", "company.owner_offset_count", 16, "Per-company road-infrastructure offsets.", "company.ledger.road_infrastructure_cell_count"),
    (4083, "company.ledger.rail_infrastructure_offsets", "src/company_base.h", "rail{}", "company.owner_offset_count", 16, "Per-company rail-infrastructure offsets.", "company.ledger.rail_infrastructure_cell_count"),
    (4084, "company.history.entry_offsets", "src/company_base.h", "old_economy", "company.owner_offset_count", 16, "Per-company quarterly-history offsets.", "company.history.entry_count"),
    (4085, "company.history.delivered_cargo_offsets", "src/company_base.h", "old_economy", "company.owner_offset_count", 16, "Per-company history/cargo offsets.", "company.history.delivered_cargo_cell_count"),
    (4086, "company.road_unit_word_offsets", "src/company_base.h", "used_bitmap", "company.owner_offset_count", 16, "Per-company road unit-generator word offsets.", "company.road_unit_word_count_total"),
    (4087, "company.group_unit_word_offsets", "src/company_base.h", "FreeUnitIDGenerator freegroups", "company.owner_offset_count", 16, "Per-company group unit-generator word offsets.", "company.group_unit_word_count_total"),
    (5066, "industry.produced_slot_offsets", "src/industry.h", "ProducedCargoes produced", "industry.owner_offset_count", 64001, "Per-industry produced-slot offsets.", "industry.produced_slot_count"),
    (5067, "industry.accepted_slot_offsets", "src/industry.h", "AcceptedCargoes accepted", "industry.owner_offset_count", 64001, "Per-industry accepted-slot offsets.", "industry.accepted_slot_count"),
    (5068, "industry.produced_history_offsets", "src/industry.h", "HistoryData<ProducedHistory>", "industry.produced_history_offset_count", 256001, "Per-produced-slot history offsets.", "industry.produced_history_cell_count"),
    (5069, "industry.accepted_history_offsets", "src/industry.h", "HistoryData<AcceptedHistory>", "industry.accepted_history_offset_count", 256001, "Per-accepted-slot history offsets.", "industry.accepted_history_cell_count"),
    (5070, "industry.nearby_station_offsets", "src/industry.h", "StationList stations_near", "industry.owner_offset_count", 64001, "Per-industry nearby-station offsets.", "industry.nearby_station_ref_count"),
    (6067, "station.goods.entry_offsets", "src/station_base.h", "std::array<GoodsEntry, NUM_CARGO> goods", "station.owner_offset_count", 64001, "Per-station GoodsEntry offsets.", "station.goods.entry_count"),
    (6068, "station.catchment_bit_offsets", "src/station_base.h", "catchment_tiles", "station.owner_offset_count", 64001, "Per-station catchment-bit offsets.", "station.catchment_bit_count"),
    (6069, "station.loading_vehicle_offsets", "src/station_base.h", "loading_vehicles", "station.owner_offset_count", 64001, "Per-station loading-vehicle offsets.", "station.loading_vehicle_ref_count"),
    (6070, "station.nearby_industry_offsets", "src/station_base.h", "industries_near", "station.owner_offset_count", 64001, "Per-station nearby-industry offsets.", "station.nearby_industry_ref_count"),
    (6076, "station.custom_roadstop_tile_offsets", "src/base_station_base.h", "custom_roadstop_tile_data", "station.owner_offset_count", 64001, "Per-station custom road-stop record offsets.", "station.custom_roadstop_tile_count"),
    (6077, "station.tile_waiting_trigger_offsets", "src/base_station_base.h", "tile_waiting_random_triggers", "station.owner_offset_count", 64001, "Per-station tile-trigger record offsets.", "station.tile_waiting_trigger_record_count"),
    (6078, "station.goods.packet_offsets", "src/station_base.h", "StationCargoList cargo", "station.goods.owner_offset_count", 4096001, "Per-GoodsEntry packet-reference offsets.", "station.goods.packet_ref_count"),
    (6079, "station.goods.flow_owner_offsets", "src/station_base.h", "FlowStatMap flows", "station.goods.owner_offset_count", 4096001, "Per-GoodsEntry FlowStat-owner offsets.", "station.goods.flow_owner_count"),
    (6080, "station.goods.flow_share_offsets", "src/station_base.h", "SharesMap shares", "station.goods.flow_owner_offset_count", 409600001, "Per-FlowStat cumulative-share offsets.", "station.goods.flow_share_count"),
    (6122, "road_stop.entries_offsets", "src/roadstop_base.h", "Entries *entries = nullptr", "road_stop.owner_offset_count", 64001, "Per-RoadStop optional Entries offsets.", "road_stop.entries_count"),
    (7204, "vehicle.cargo_packet_offsets", "src/vehicle_base.h", "VehicleCargoList cargo", "vehicle.owner_offset_count", 1044481, "Per-vehicle cargo-packet offsets.", "vehicle.cargo_packet_ref_count"),
    (7205, "road_vehicle.path_offsets", "src/roadveh.h", "RoadVehPathCache path", "road_vehicle.owner_offset_count", 1044481, "Per-road-vehicle path offsets.", "road_vehicle.path_element_count"),
    (8021, "order_list.order_offsets", "src/order_base.h", "std::vector<Order> orders", "order.owner_offset_count", 64001, "Per-OrderList order-vector offsets.", "order.item.count"),
    (12086, "town.supplied_slot_offsets", "src/town.h", "SuppliedCargoes supplied", "town.owner_offset_count", 64001, "Per-town supplied-slot offsets.", "town.supplied_slot_count"),
    (12087, "town.accepted_slot_offsets", "src/town.h", "AcceptedCargoes accepted", "town.owner_offset_count", 64001, "Per-town accepted-slot offsets.", "town.accepted_slot_count"),
    (12088, "town.supplied_history_offsets", "src/town.h", "SuppliedCargoes supplied", "town.supplied_history_offset_count", 4096001, "Per-supplied-slot history offsets.", "town.supplied_history_cell_count"),
    (12089, "town.accepted_history_offsets", "src/town.h", "AcceptedCargoes accepted", "town.accepted_history_offset_count", 4096001, "Per-accepted-slot history offsets.", "town.accepted_history_cell_count"),
    (12090, "town.rating_offsets", "src/town.h", "CompanyID> ratings{}", "town.owner_offset_count", 64001, "Per-town authority-rating offsets.", "town.rating_cell_count"),
    (12091, "town.nearby_station_offsets", "src/town.h", "StationList stations_near", "town.owner_offset_count", 64001, "Per-town nearby-station offsets.", "town.nearby_station_ref_count"),
    (12025, "town.building_id_count_offsets", "src/town.h", "std::vector<T> id_count", "town.owner_offset_count", 64001, "Per-town building ID count-vector offsets.", "town.building_id_count_total"),
    (12026, "town.building_class_count_offsets", "src/town.h", "std::vector<T> class_count", "town.owner_offset_count", 64001, "Per-town building class count-vector offsets.", "town.building_class_count_total"),
    (12508, "linkgraph.node_offsets", "src/linkgraph/linkgraph.h", "NodeVector nodes{}", "linkgraph.owner_offset_count", 65536, "Per-LinkGraph node offsets.", "linkgraph.node_count_total"),
    (12509, "linkgraph.edge_offsets", "src/linkgraph/linkgraph.h", "std::vector<BaseEdge> edges", "linkgraph.node_offset_count", 4194241, "Per-LinkGraph-node edge offsets.", "linkgraph.edge_count_total"),
]:
    offset_field(*args)

# LinkGraphs are allocated and queued by UpdateStationWaiting even under manual
# distribution.  Preserve every node/edge column and schedule identity.
scalar_group(12520, "linkgraph.node", "src/linkgraph/linkgraph.h", "LinkGraph::BaseNode/BaseEdge", "LinkGraphID then NodeID/edge ordinal", [
    ("node_supply", "u32", "uint supply", 0, "BaseNode supply family."),
    ("node_demand", "u32", "uint demand", 0, "BaseNode demand family."),
    ("node_tile", "u32", "TileIndex xy", 0, "BaseNode tile family."),
    ("node_last_update", "i32", "TimerGameEconomy::Date last_update", 0, "BaseNode last-update family."),
    ("edge_destination", "u16", "NodeID dest_node", 0, "BaseEdge destination-node family."),
    ("edge_last_unrestricted", "i32", "last_unrestricted_update", 0, "BaseEdge unrestricted-update family."),
    ("edge_last_restricted", "i32", "last_restricted_update", 0, "BaseEdge restricted-update family."),
], "These source owners are behaviorally complete only if LinkGraph allocation becomes reachable.",
"UpdateStationWaiting -> LinkGraph allocation/AddNode -> LinkGraphSchedule::Queue/SpawnNext")
field(12527, "linkgraph.schedule_graph_ids", "stable_id", "src/linkgraph/linkgraphschedule.h", "GraphList schedule",
      "Queued LinkGraphIDs in exact native list order.",
      "SpawnNext rotates and selects this list; membership and order alter which graph is processed next.",
      owner="LinkGraphSchedule", owner_rule="singleton schedule queue",
      shape="dynamic_array", fixed_count=None, count_source="linkgraph.schedule_count", maximum_capacity=65535,
      order="native GraphList order from front to back", sample=[0], sample_scope="one_element",
      reached_path="UpdateStationWaiting -> LinkGraphSchedule::Queue -> SpawnNext")
field(12528, "linkgraph.running_job_ids", "stable_id", "src/linkgraph/linkgraphschedule.h", "JobList running",
      "Running LinkGraphJobIDs in exact native list order.",
      "JoinNext consumes the list front, so identity and order control when completed results enter gameplay state.",
      owner="LinkGraphSchedule", owner_rule="singleton running-job queue",
      shape="dynamic_array", fixed_count=None, count_source="linkgraph.running_job_count", maximum_capacity=65535,
      order="native JobList order from front to back", sample=[0], sample_scope="one_element",
      reached_path="LinkGraphSchedule::SpawnNext -> running.push_back -> JoinNext")
field(12529, "linkgraph_job.pool.occupied_count", "u32", "src/core/pool_type.hpp", "size_t items",
      "Number of occupied LinkGraphJob pool slots.",
      "A spawned job is persistent continuation state until JoinNext; the exact pool allocation state is authoritative.",
      owner="linkgraph_job_pool", owner_rule="typed numeric LinkGraphJobID pool slot", sample=0,
      reached_path="LinkGraphSchedule::SpawnNext -> LinkGraphJob::Create -> JoinNext")
for field_id, suffix, symbol, value_type, shape, count_source, maximum, description in [
    (12540, "first_free", "size_t first_free", "u32", "scalar", None, 1, "Lowest LinkGraphJob slot from which allocation scans."),
    (12541, "first_unused", "size_t first_unused", "u32", "scalar", None, 1, "Exclusive LinkGraphJob pool high-water slot."),
    (12542, "occupancy_bitmap", "std::vector<BitmapStorage> used_bitmap", "u64", "dynamic_array", "linkgraph_job.pool.bitmap_word_count", 1024, "Exact LinkGraphJob pool used-bitmap words."),
    (12544, "bitmap_word_count", "std::vector<BitmapStorage> used_bitmap", "u32", "scalar", None, 1, "Exact LinkGraphJob used-bitmap word count."),
]:
    field(field_id, f"linkgraph_job.pool.{suffix}", value_type, "src/core/pool_type.hpp", symbol,
          description, "LinkGraphJob allocation and iteration depend on exact pool cursor and bitmap state.",
          owner="linkgraph_job_pool", owner_rule="typed numeric LinkGraphJobID pool slot",
          shape=shape, fixed_count=1 if shape == "scalar" else None, count_source=count_source,
          maximum_capacity=maximum, order="single value" if shape == "scalar" else "native used_bitmap word index ascending",
          sample=0 if shape == "scalar" else [0], sample_scope="complete_value" if shape == "scalar" else "one_element",
          reached_path="LinkGraphSchedule::SpawnNext -> LinkGraphJobPool allocation/iteration")
field(12543, "linkgraph_job.pool.native_free_list", "u32", "src/core/pool_type.hpp", "size_t first_free",
      "Proof entry for a separate LinkGraphJob free-list.",
      "Pinned PoolBase stores only first_free, first_unused, and used_bitmap; no separate free-list order exists.",
      owner="linkgraph_job_pool", owner_rule="typed numeric LinkGraphJobID pool slot", sample=0,
      classification="out_of_scope_unreachable", reached="unreachable_absent-from-pinned-PoolBase-storage",
      reached_path="Pool::Allocate source review")

# Running LinkGraphJobs are native continuation state even with manual cargo
# distribution: graphs are still created/queued, and jobs are spawned as soon
# as a component has at least two nodes.  The copied graph and copied settings
# are immutable after spawn and are exactly the inputs native save/load keeps
# before restarting the deterministic worker calculation.
for field_id, path, source_file, source_symbol, description in [
    (12545, "linkgraph_job.owner_offset_count", "src/linkgraph/linkgraphjob.h", "class LinkGraphJob :", "LinkGraphJob owner-offset count, occupied jobs plus one."),
    (12546, "linkgraph_job.graph_node_count_total", "src/linkgraph/linkgraph.h", "NodeVector nodes{}", "Total copied-graph nodes across LinkGraphJobs."),
    (12547, "linkgraph_job.graph_node_offset_count", "src/linkgraph/linkgraph.h", "NodeVector nodes{}", "Copied-graph edge-offset count, total copied nodes plus one."),
    (12548, "linkgraph_job.graph_edge_count_total", "src/linkgraph/linkgraph.h", "std::vector<BaseEdge> edges", "Total copied-graph edges across LinkGraphJobs."),
]:
    field(field_id, path, "u32", source_file, source_symbol, description,
          "This explicit aggregate count makes the immutable per-job graph projection uniquely decodable.",
          owner="projection_structure", owner_rule="singleton complete projection", sample=1 if path.endswith("offset_count") else 0,
          reached_path="LinkGraphJob::Iterate -> immutable copied graph sizes -> read-only projection adapter")

field(12549, "linkgraph_job.item.ids", "stable_id", "src/linkgraph/linkgraphjob.h", "class LinkGraphJob :",
      "Occupied LinkGraphJobIDs in typed pool-slot order.",
      "The stable ID binds each immutable job input and schedule reference to its exact native pool slot.",
      owner="LinkGraphJob", owner_rule="typed numeric LinkGraphJobID pool slot",
      shape="dynamic_array", fixed_count=None, count_source="linkgraph_job.pool.occupied_count", maximum_capacity=64,
      order="occupied LinkGraphJobID ascending", sample=[0], sample_scope="one_element",
      reached_path="LinkGraphSchedule::SpawnNext -> LinkGraphJob::Create -> LinkGraphJob::Iterate")

for field_id, suffix, value_type, source_symbol, sample, description in [
    (12550, "join_date", "i32", "TimerGameEconomy::Date join_date", 0, "Economy date on which this job must be joined."),
    (12551, "copied_graph_id", "stable_id", "const LinkGraph link_graph", 0, "Original LinkGraphID copied into this job."),
    (12554, "settings.recalc_time", "u16", "uint16_t recalc_time", 32, "Copied link-graph recalculation duration setting."),
    (12555, "settings.recalc_interval", "u16", "uint16_t recalc_interval", 16, "Copied link-graph scheduling interval setting."),
    (12556, "settings.distribution_pax", "u8", "DistributionType distribution_pax", 0, "Copied passenger distribution mode."),
    (12557, "settings.distribution_mail", "u8", "DistributionType distribution_mail", 0, "Copied mail distribution mode."),
    (12558, "settings.distribution_armoured", "u8", "DistributionType distribution_armoured", 0, "Copied armoured-cargo distribution mode."),
    (12559, "settings.distribution_default", "u8", "DistributionType distribution_default", 0, "Copied default cargo distribution mode."),
    (12560, "settings.accuracy", "u8", "uint8_t accuracy", 16, "Copied link-graph calculation accuracy."),
    (12561, "settings.demand_size", "u8", "uint8_t demand_size", 100, "Copied supply-size demand weight."),
    (12562, "settings.demand_distance", "u8", "uint8_t demand_distance", 100, "Copied distance demand weight."),
    (12563, "settings.short_path_saturation", "u8", "uint8_t short_path_saturation", 80, "Copied short-path saturation threshold."),
    (12564, "graph.cargo_type", "u8", "CargoType cargo = INVALID_CARGO;", 0, "Cargo type of the immutable copied graph."),
    (12565, "graph.last_compression", "i32", "TimerGameEconomy::Date last_compression", 0, "Last-compression date of the immutable copied graph."),
    (12566, "graph.node_counts", "u32", "NodeVector nodes{}", 0, "Node count of each immutable copied graph."),
]:
    source_file = "src/linkgraph/linkgraphjob.h" if field_id <= 12551 else ("src/settings_type.h" if field_id <= 12563 else "src/linkgraph/linkgraph.h")
    field(field_id, f"linkgraph_job.item.{suffix}", value_type, source_file, source_symbol,
          description,
          "Native job scheduling, deterministic recomputation, and eventual JoinNext output depend on this value.",
          owner="LinkGraphJob", owner_rule="typed numeric LinkGraphJobID pool slot", sample=[sample],
          shape="dynamic_array", fixed_count=None, count_source="linkgraph_job.pool.occupied_count", maximum_capacity=64,
          order="occupied LinkGraphJobID ascending", sample_scope="one_element",
          reached_path="LinkGraphSchedule::SpawnNext -> LinkGraphJob copy -> native save/load restart or JoinNext")

for field_id, path, count_source, maximum, source_symbol, description, target in [
    (12567, "linkgraph_job.graph_node_offsets", "linkgraph_job.owner_offset_count", 65, "NodeVector nodes{}", "Per-job copied-graph node offsets.", "linkgraph_job.graph_node_count_total"),
    (12568, "linkgraph_job.graph_edge_offsets", "linkgraph_job.graph_node_offset_count", 129, "std::vector<BaseEdge> edges", "Per-copied-node edge offsets.", "linkgraph_job.graph_edge_count_total"),
]:
    field(field_id, path, "u32", "src/linkgraph/linkgraph.h", source_symbol, description,
          "Offsets preserve exact empty and non-empty nested boundaries in the immutable copied job graph.",
          owner="projection_structure", owner_rule="LinkGraphJobID then native node ordinal",
          shape="dynamic_array", fixed_count=None, count_source=count_source, maximum_capacity=maximum,
          order="stable owner order; offset zero first; final offset equals aggregate count",
          sample=[0], sample_scope="one_element",
          reached_path="LinkGraphJob::Iterate -> immutable Graph() -> prefix-sum projection adapter")
    FIELDS[-1]["offset_target_count_field"] = target

for field_id, suffix, value_type, source_symbol, count_source, maximum, description in [
    (12569, "graph.node_supply", "u32", "uint supply", "linkgraph_job.graph_node_count_total", 128, "Copied BaseNode supply."),
    (12570, "graph.node_demand", "u32", "uint demand", "linkgraph_job.graph_node_count_total", 128, "Copied BaseNode demand."),
    (12571, "graph.node_station_ids", "stable_id", "StationID station", "linkgraph_job.graph_node_count_total", 128, "Copied BaseNode station IDs."),
    (12572, "graph.node_tiles", "u32", "TileIndex xy", "linkgraph_job.graph_node_count_total", 128, "Copied BaseNode tiles."),
    (12573, "graph.node_last_updates", "i32", "TimerGameEconomy::Date last_update", "linkgraph_job.graph_node_count_total", 128, "Copied BaseNode last-update dates."),
    (12574, "graph.edge_capacities", "u32", "uint capacity", "linkgraph_job.graph_edge_count_total", 256, "Copied BaseEdge capacities."),
    (12575, "graph.edge_usages", "u32", "uint usage", "linkgraph_job.graph_edge_count_total", 256, "Copied BaseEdge usages."),
    (12576, "graph.edge_travel_time_sums", "u64", "uint64_t travel_time_sum", "linkgraph_job.graph_edge_count_total", 256, "Copied BaseEdge accumulated travel times."),
    (12577, "graph.edge_last_unrestricted_updates", "i32", "last_unrestricted_update", "linkgraph_job.graph_edge_count_total", 256, "Copied BaseEdge unrestricted-update dates."),
    (12578, "graph.edge_last_restricted_updates", "i32", "last_restricted_update", "linkgraph_job.graph_edge_count_total", 256, "Copied BaseEdge restricted-update dates."),
    (12579, "graph.edge_destination_nodes", "u16", "NodeID dest_node", "linkgraph_job.graph_edge_count_total", 256, "Copied BaseEdge destination NodeIDs."),
]:
    field(field_id, f"linkgraph_job.{suffix}", value_type, "src/linkgraph/linkgraph.h", source_symbol,
          description,
          "This immutable copied value is a direct deterministic input to LinkGraphSchedule::Run and eventual committed flow state.",
          owner="LinkGraphJob copied LinkGraph", owner_rule="LinkGraphJobID, then NodeID, then native sorted edge ordinal",
          shape="dynamic_array", fixed_count=None, count_source=count_source, maximum_capacity=maximum,
          order="LinkGraphJobID ascending, NodeID ascending, then native BaseEdge order", sample=[0], sample_scope="one_element",
          reached_path="LinkGraphJob constructor copy -> worker Init/handlers -> JoinNext")

def column(path: str, count_source: str, maximum: int, order: str = "stable owner ID ascending") -> None:
    item = next(value for value in FIELDS if value["path"] == path)
    item["shape"] = "dynamic_array"
    item["fixed_count"] = None
    item["count_source_field"] = count_source
    item["maximum_capacity"] = maximum
    item["canonical_element_order"] = order
    if not isinstance(item["sample_logical_value"], list):
        item["sample_logical_value"] = [item["sample_logical_value"]]
    item["sample_scope"] = "one_element"

# Simple one-value-per-owner columns. Aggregate counts remain scalar.
PREFIX_COLUMNS = {
    "company.item.": ("company.pool.occupied_count", 15),
    "industry.item.": ("industry.pool.occupied_count", 64000),
    "station.item.": ("station.pool.occupied_count", 64000),
    "road_stop.item.": ("road_stop.pool.occupied_count", 64000),
    "station.goods.": ("station.goods.entry_count", 4096000),
    "vehicle.item.": ("vehicle.pool.occupied_count", 0xFF000),
    "road_vehicle.item.": ("road_vehicle.item.count", 0xFF000),
    "order_list.item.": ("order_list.pool.occupied_count", 64000),
    "order.item.": ("order.item.count", 16320000),
    "cargo_packet.item.": ("cargo_packet.pool.occupied_count", 16773120),
    "town.item.": ("town.pool.occupied_count", 64000),
    "depot.item.": ("depot.pool.occupied_count", 64000),
    "engine.item.": ("engine.pool.occupied_count", 64000),
    "cargo_payment.item.": ("cargo_payment.pool.occupied_count", 0xFF000),
    "subsidy.item.": ("subsidy.pool.occupied_count", 256),
    "linkgraph.item.": ("linkgraph.pool.occupied_count", 65535),
}
AGGREGATE_SCALARS = {
    "road_vehicle.item.count", "order.item.count", "station.goods.entry_count",
    "station.goods.packet_ref_count", "station.goods.flow_owner_count",
    "station.goods.flow_share_count", "station.goods.owner_offset_count",
    "station.goods.flow_owner_offset_count",
}
for item in list(FIELDS):
    for prefix, (count_source, maximum) in PREFIX_COLUMNS.items():
        if (item["path"].startswith(prefix) and item["path"] not in AGGREGATE_SCALARS and
                item["classification"] == "authoritative_full" and item.get("offset_target_count_field") is None):
            column(item["path"], count_source, maximum)
            break

# Nested dimensions override one-per-owner defaults.
NESTED_COUNTS = {
    "company.item.yearly_expenses": ("company.ledger.expense_cell_count", 585),
    "company.item.delivered_cargo": ("company.ledger.delivered_cargo_cell_count", 960),
    "company.item.road_infrastructure": ("company.ledger.road_infrastructure_cell_count", 960),
    "company.item.rail_infrastructure": ("company.ledger.rail_infrastructure_cell_count", 960),
    "company.item.road_unit_id_words": ("company.road_unit_word_count_total", 1048576),
    "company.item.group_unit_id_words": ("company.group_unit_word_count_total", 1048576),
    "company.item.history_income": ("company.history.entry_count", 360),
    "company.item.history_expenses": ("company.history.entry_count", 360),
    "company.item.history_performance": ("company.history.entry_count", 360),
    "company.item.history_company_value": ("company.history.entry_count", 360),
    "company.item.history_delivered_cargo": ("company.history.delivered_cargo_cell_count", 23040),
    "industry.item.produced_cargo_type": ("industry.produced_slot_count", 256000),
    "industry.item.produced_waiting": ("industry.produced_slot_count", 256000),
    "industry.item.produced_rate": ("industry.produced_slot_count", 256000),
    "industry.item.produced_history_production": ("industry.produced_history_cell_count", 6400000),
    "industry.item.produced_history_transported": ("industry.produced_history_cell_count", 6400000),
    "industry.item.accepted_cargo_type": ("industry.accepted_slot_count", 256000),
    "industry.item.accepted_waiting": ("industry.accepted_slot_count", 256000),
    "industry.item.accepted_accumulated_waiting": ("industry.accepted_slot_count", 256000),
    "industry.item.accepted_last_date": ("industry.accepted_slot_count", 256000),
    "industry.item.accepted_history_amount": ("industry.accepted_history_cell_count", 6400000),
    "industry.item.accepted_history_waiting": ("industry.accepted_history_cell_count", 6400000),
    "industry.item.accepted_history_presence": ("industry.accepted_slot_count", 256000),
    "industry.item.nearby_station_ids": ("industry.nearby_station_ref_count", 409600000),
    "station.item.loading_vehicle_ids": ("station.loading_vehicle_ref_count", 0xFF000),
    "station.item.industries_near_ids": ("station.nearby_industry_ref_count", 409600000),
    "station.item.industries_near_distances": ("station.nearby_industry_ref_count", 409600000),
    "station.item.custom_roadstop_tiles": ("station.custom_roadstop_tile_count", 4096000),
    "station.item.custom_roadstop_random_bits": ("station.custom_roadstop_tile_count", 4096000),
    "station.item.custom_roadstop_animation_frames": ("station.custom_roadstop_tile_count", 4096000),
    "station.item.tile_waiting_trigger_tiles": ("station.tile_waiting_trigger_record_count", 4096000),
    "station.item.tile_waiting_trigger_values": ("station.tile_waiting_trigger_record_count", 4096000),
    "station.goods.packet_ids": ("station.goods.packet_ref_count", 16773120),
    "station.goods.packet_map_next_hop_keys": ("station.goods.packet_ref_count", 16773120),
    "station.goods.flow_origin_station_ids": ("station.goods.flow_owner_count", 409600000),
    "station.goods.flow_unrestricted": ("station.goods.flow_owner_count", 409600000),
    "station.goods.flow_share_cumulative_key": ("station.goods.flow_share_count", 1073741824),
    "station.goods.flow_share_via_station_id": ("station.goods.flow_share_count", 1073741824),
    "road_stop.item.east_length": ("road_stop.entries_count", 64000),
    "road_stop.item.east_occupied": ("road_stop.entries_count", 64000),
    "road_stop.item.west_length": ("road_stop.entries_count", 64000),
    "road_stop.item.west_occupied": ("road_stop.entries_count", 64000),
    "vehicle.item.cargo_packet_ids": ("vehicle.cargo_packet_ref_count", 16773120),
    "road_vehicle.item.path_trackdirs": ("road_vehicle.path_element_count", 67108800),
    "road_vehicle.item.path_tiles": ("road_vehicle.path_element_count", 67108800),
    "vehicle.item.cache.weight": ("road_vehicle.item.count", 0xFF000),
    "vehicle.item.cache.slope_resistance": ("road_vehicle.item.count", 0xFF000),
    "vehicle.item.cache.maximum_tractive_effort": ("road_vehicle.item.count", 0xFF000),
    "vehicle.item.cache.axle_resistance": ("road_vehicle.item.count", 0xFF000),
    "vehicle.item.cache.maximum_track_speed": ("road_vehicle.item.count", 0xFF000),
    "vehicle.item.cache.power": ("road_vehicle.item.count", 0xFF000),
    "vehicle.item.cache.air_drag": ("road_vehicle.item.count", 0xFF000),
    "vehicle.item.cache.total_length": ("road_vehicle.item.count", 0xFF000),
    "vehicle.item.cache.first_engine_id": ("road_vehicle.item.count", 0xFF000),
    "vehicle.item.cache.vehicle_length": ("road_vehicle.item.count", 0xFF000),
    "vehicle.item.ground_vehicle_flags": ("road_vehicle.item.count", 0xFF000),
    "town.item.ratings": ("town.rating_cell_count", 960000),
    "town.item.unwanted_months": ("town.rating_cell_count", 960000),
    "town.item.supplied_cargo_type": ("town.supplied_slot_count", 4096000),
    "town.item.supplied_production": ("town.supplied_history_cell_count", 102400000),
    "town.item.supplied_transported": ("town.supplied_history_cell_count", 102400000),
    "town.item.accepted_cargo_type": ("town.accepted_slot_count", 4096000),
    "town.item.accepted_amount": ("town.accepted_history_cell_count", 102400000),
    "town.item.zone_radius_squared": ("town.zone_radius_cell_count", 320000),
    "town.item.building_id_counts": ("town.building_id_count_total", 1073741824),
    "town.item.building_class_counts": ("town.building_class_count_total", 1073741824),
    "town.item.growth_goal": ("town.acceptance_effect_cell_count", 384000),
    "town.item.received_old_max": ("town.acceptance_effect_cell_count", 384000),
    "town.item.received_new_max": ("town.acceptance_effect_cell_count", 384000),
    "town.item.received_old_actual": ("town.acceptance_effect_cell_count", 384000),
    "town.item.received_new_actual": ("town.acceptance_effect_cell_count", 384000),
    "town.item.nearby_station_ids": ("town.nearby_station_ref_count", 409600000),
    "engine.item.road.image_index": ("engine.road_engine_count", 64000),
    "engine.item.road.cost_factor": ("engine.road_engine_count", 64000),
    "engine.item.road.running_cost": ("engine.road_engine_count", 64000),
    "engine.item.road.running_cost_class": ("engine.road_engine_count", 64000),
    "engine.item.road.maximum_speed": ("engine.road_engine_count", 64000),
    "engine.item.road.capacity": ("engine.road_engine_count", 64000),
    "engine.item.road.weight_quarter_tonnes": ("engine.road_engine_count", 64000),
    "engine.item.road.power_tens_hp": ("engine.road_engine_count", 64000),
    "engine.item.road.tractive_effort": ("engine.road_engine_count", 64000),
    "engine.item.road.air_drag": ("engine.road_engine_count", 64000),
    "engine.item.road.shorten_factor": ("engine.road_engine_count", 64000),
    "engine.item.road.road_type": ("engine.road_engine_count", 64000),
    "linkgraph.item.node_station_ids": ("linkgraph.node_count_total", 4194240),
    "linkgraph.item.edge_capacities": ("linkgraph.edge_count_total", 1073741824),
    "linkgraph.item.edge_usages": ("linkgraph.edge_count_total", 1073741824),
    "linkgraph.item.edge_travel_times": ("linkgraph.edge_count_total", 1073741824),
    "linkgraph.node.node_supply": ("linkgraph.node_count_total", 4194240),
    "linkgraph.node.node_demand": ("linkgraph.node_count_total", 4194240),
    "linkgraph.node.node_tile": ("linkgraph.node_count_total", 4194240),
    "linkgraph.node.node_last_update": ("linkgraph.node_count_total", 4194240),
    "linkgraph.node.edge_destination": ("linkgraph.edge_count_total", 1073741824),
    "linkgraph.node.edge_last_unrestricted": ("linkgraph.edge_count_total", 1073741824),
    "linkgraph.node.edge_last_restricted": ("linkgraph.edge_count_total", 1073741824),
}
for path, (count_source, maximum) in NESTED_COUNTS.items():
    column(path, count_source, maximum, "stable owner ID ascending, then native nested ordinal ascending")

# Array-of-bitset fields retain BITSET shape and explicit flattened bit counts.
for path, count_source, maximum in [
    ("station.item.catchment_tiles", "station.catchment_bit_count", 262144000),
]:
    item = next(value for value in FIELDS if value["path"] == path)
    item["shape"] = "bitset"
    item["fixed_count"] = None
    item["count_source_field"] = count_source
    item["maximum_capacity"] = maximum
    item["canonical_element_order"] = "owner ID ascending; each owner bit zero first; final byte high padding bits zero"

# Stable-ID widths are the pinned PoolID storage widths, never host size_t.
for item in FIELDS:
    if item["value_type"] != "stable_id":
        continue
    path = item["path"]
    if (path in {"vehicle.item.id", "cargo_packet.item.id", "cargo_payment.item.id", "vehicle.item.cargo_payment_id",
                 "road_vehicle.item.ids", "effect_vehicle.item.ids",
                 "town.item.newgrf_persistent_storage_ids",
                 "vehicle.item.cargo_packet_ids", "station.goods.packet_ids"} or
            any(token in path for token in ("vehicle_id", "next_vehicle_id", "next_shared_vehicle_id", "tile_hash_next_id", "container_id"))):
        item["width_bits"] = 32
    elif "company" in path and not any(token in path for token in ("vehicle", "station", "industry")):
        item["width_bits"] = 8
    else:
        item["width_bits"] = 16
    max_value = (1 << int(item["width_bits"])) - 1
    values = item["sample_logical_value"] if isinstance(item["sample_logical_value"], list) else [item["sample_logical_value"]]
    item["sample_logical_value"] = [min(int(value), max_value) for value in values] if isinstance(item["sample_logical_value"], list) else min(int(values[0]), max_value)


def stable_id_null_sentinel(path: str, width_bits: int) -> int:
    """Return the pinned semantic invalid value, not the storage-width maximum."""
    cargo_packet_refs = {
        "cargo_packet.item.id",
        "station.goods.packet_ids",
        "vehicle.item.cargo_packet_ids",
    }
    cargo_payment_refs = {
        "cargo_payment.item.id",
        "vehicle.item.cargo_payment_id",
        "town.item.newgrf_persistent_storage_ids",
    }
    vehicle_refs = {
        "vehicle.item.id",
        "station.item.loading_vehicle_ids",
        "vehicle.item.next_vehicle_id",
        "vehicle.item.next_shared_vehicle_id",
        "vehicle.item.tile_hash_next_id",
        "order_list.item.first_shared_vehicle_id",
        "cargo_payment.item.vehicle_id",
        "road_vehicle.item.ids",
        "effect_vehicle.item.ids",
    }
    if path in cargo_packet_refs:
        return 0xFFFFFF
    if path in cargo_payment_refs or path in vehicle_refs:
        return 0xFFFFF
    if width_bits == 8:
        return 0xFF
    if width_bits == 16:
        return 0xFFFF
    # Tagged projection-only union IDs use an explicit U32 null outside all
    # currently valid owner domains; this is not claimed to be a native PoolID.
    return 0xFFFFFFFF


def source_line(source_file: str, symbol: str) -> int:
    path = UPSTREAM / source_file
    lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
    in_block_comment = False
    for number, line in enumerate(lines, 1):
        code = line
        if in_block_comment:
            if "*/" not in code:
                continue
            code = code.split("*/", 1)[1]
            in_block_comment = False
        while "/*" in code:
            before, after = code.split("/*", 1)
            if "*/" not in after:
                code = before
                in_block_comment = True
                break
            code = before + after.split("*/", 1)[1]
        code = code.split("//", 1)[0]
        if symbol in code:
            return number
    raise SystemExit(f"source declaration/definition locator not found outside comments: {source_file}: {symbol!r}")


def encode_sample(entry: dict[str, Any]) -> str:
    typ = entry["value_type"]
    sample = entry["sample_logical_value"]
    if isinstance(sample, list):
        values = sample
    else:
        values = [sample]
    if typ in {"bytes", "bitset", "diagnostic_utf8"}:
        if not values or not isinstance(values[0], str):
            # Logical zero for compact bitset samples.
            return "00"
        return values[0].encode("utf-8").hex() if typ == "diagnostic_utf8" else values[0]
    width = int(entry["width_bits"]) // 8
    signed = entry["signedness"] == "signed"
    return "".join(int(value).to_bytes(width, "little", signed=signed).hex() for value in values)


def expand() -> dict[str, Any]:
    seen: set[int] = set()
    for item in FIELDS:
        if item["field_id"] in seen:
            raise SystemExit(f"duplicate field id {item['field_id']}")
        seen.add(item["field_id"])
        item["endianness"] = "little" if item["width_bits"] is not None else "not_applicable"
        item.setdefault("sampling_boundary", "after fixture load, after every command result, and after every declared post-tick boundary")
        item["serialization_rule"] = "tape-v1 field entry; canonical fixed-width little-endian elements; no raw enum, pointer, size_t, struct, padding, or object bytes"
        item["comparison_rule"] = "exact type, count, byte length, element order, and byte equality at the earliest boundary"
        item["source_commit"] = PIN
        item["source_line_diagnostic"] = source_line(item["source_file"], item["source_symbol"])
        item["native_member_expression"] = {
            "town.item.population": "Town::cache.population",
            "town.item.house_count": "Town::cache.num_houses",
            "town.item.zone_radius_squared": "Town::cache.squared_town_zone_radius",
            "town.item.building_id_counts": "Town::cache.building_counts.id_count",
            "town.item.building_class_counts": "Town::cache.building_counts.class_count",
        }.get(item["path"], item["source_symbol"])
        item["sample_origin"] = "hand-reviewed canonical type example"
        if item["path"].startswith("rng."):
            item["sample_origin"] = "fixture builder pre-save observation; post-load equality remains a PORT-003 projection gate"
        item["unit_test_id"] = f"P005-FIELD-{item['field_id']:05d}"
        item["review_status"] = "reviewed_source_owner_and_continuation"
        item["null_sentinel"] = None
        if item["value_type"] == "stable_id":
            item["null_sentinel"] = stable_id_null_sentinel(item["path"], int(item["width_bits"]))
            values = item["sample_logical_value"] if isinstance(item["sample_logical_value"], list) else [item["sample_logical_value"]]
            storage_max = (1 << int(item["width_bits"])) - 1
            remapped = [item["null_sentinel"] if int(value) == storage_max else int(value) for value in values]
            item["sample_logical_value"] = remapped if isinstance(item["sample_logical_value"], list) else remapped[0]
        elif item["path"].endswith("tile") or item["path"].endswith("_tile"):
            item["null_sentinel"] = 4294967295
        if item["value_type"] == "u8" and "CargoType" in item["source_symbol"]:
            item["null_sentinel"] = 0xFF
        if item["value_type"] == "u16" and "NodeID" in item["source_symbol"]:
            item["null_sentinel"] = 0xFFFF
        if item["value_type"] == "i32" and "Date" in item["source_symbol"]:
            item["null_sentinel"] = -1
        if item["path"] in {
            "linkgraph_job.graph.node_tiles",
        }:
            item["null_sentinel"] = 0xFFFFFFFF
        if item["path"] in {
            "cache.town_kdtree.node_left_indices",
            "cache.town_kdtree.node_right_indices",
            "cache.town_kdtree.root_index",
            "cache.station_kdtree.node_left_indices",
            "cache.station_kdtree.node_right_indices",
            "cache.station_kdtree.root_index",
        }:
            item["null_sentinel"] = 0xFFFFFFFFFFFFFFFF
        item["sample_encoded_hex"] = encode_sample(item)
        item["enum_encoding_rule"] = "explicit pinned numeric value; raw C++ object representation is forbidden" if any(token in item["path"] for token in ("type", "mode", "direction", "status", "flags", "state", "owner", "classification")) else "not_enum"
        item["consumed_by_simulation"] = item["classification"] not in {"diagnostic", "out_of_scope_unreachable"}
        item["cache_evidence_sha256"] = None
        item.setdefault("offset_target_count_field", None)
    FIELDS.sort(key=lambda value: value["field_id"])
    schema = json.loads((SCHEMA_OUT / "field-schema.schema.json").read_text(encoding="utf-8"))
    return {
        "$schema": "field-schema.schema.json",
        "schema_version": "openttd-p0-fields-v1",
        "schema_sha256": hashlib.sha256(canonical_bytes(schema)).hexdigest(),
        "registry_major": 1,
        "registry_minor": 0,
        "source_commit": PIN,
        "tape_projection_version": 1,
        "canonicalization": "RFC8785 restricted-to-I-JSON-integers-no-floats",
        "field_id_zero_reserved": True,
        "published_ids_never_reused": True,
        "complete_projection_rule": "Every authoritative_full field is present once at every declared full boundary, including empty arrays and empty pool metadata.",
        "stable_reference_rule": "Only typed numeric IDs and documented composite IDs are encoded; process addresses are forbidden.",
        "fields": FIELDS,
    }


def canonical_bytes(value: Any) -> bytes:
    # Registry/schema inputs forbid floats and contain only the RFC 8785 subset
    # whose canonical form is UTF-8, sorted object keys and compact separators.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def write_c_table(registry: dict[str, Any], include_out: Path, source_out: Path) -> None:
    header = [
        "/* Generated by scripts/dev/generate_field_schema.py; do not edit. */",
        "#ifndef OTRL_FIELD_REGISTRY_GENERATED_H",
        "#define OTRL_FIELD_REGISTRY_GENERATED_H",
        "#include <stddef.h>",
        "#include <stdint.h>",
        "#ifdef __cplusplus",
        "extern \"C\" {",
        "#endif",
        "typedef enum otrl_field_class { OTRL_FIELD_AUTHORITATIVE_FULL = 1, OTRL_FIELD_AUTHORITATIVE_PERIODIC = 2, OTRL_FIELD_DERIVED_REBUILD = 3, OTRL_FIELD_DIAGNOSTIC = 4, OTRL_FIELD_OUT_OF_SCOPE_UNREACHABLE = 5 } otrl_field_class;",
        "typedef enum otrl_field_shape { OTRL_FIELD_SCALAR = 1, OTRL_FIELD_FIXED_ARRAY = 2, OTRL_FIELD_DYNAMIC_ARRAY = 3, OTRL_FIELD_BITSET = 4 } otrl_field_shape;",
        "typedef struct otrl_field_meta { uint32_t field_id; uint16_t value_type; uint16_t width_bits; uint32_t fixed_count; uint32_t maximum_capacity; uint32_t count_source_field_id; uint32_t offset_target_count_field_id; uint8_t classification; uint8_t shape; const char *path; const char *source_anchor; const char *cache_class; } otrl_field_meta;",
        "const otrl_field_meta *otrl_field_lookup(uint32_t field_id);",
        "const otrl_field_meta *otrl_field_registry_at(size_t index);",
        "size_t otrl_field_registry_count(void);",
        "size_t otrl_field_authoritative_count(void);",
        f"#define OTRL_FIELD_SCHEMA_SHA256 \"{hashlib.sha256(canonical_bytes(registry)).hexdigest()}\"",
    ]
    for item in registry["fields"]:
        macro = "OTRL_FIELD_" + "".join(ch if ch.isalnum() else "_" for ch in item["path"]).upper()
        header.append(f"#define {macro} UINT32_C({item['field_id']})")
    header += ["#ifdef __cplusplus", "}", "#endif", "#endif"]
    include_out.mkdir(parents=True, exist_ok=True)
    (include_out / "field_schema.h").write_text("\n".join(header) + "\n", encoding="utf-8")

    shape = {"scalar": 1, "fixed_array": 2, "dynamic_array": 3, "bitset": 4}
    klass = {"authoritative_full": 1, "authoritative_periodic": 2, "derived_rebuild": 3, "diagnostic": 4, "out_of_scope_unreachable": 5}
    source = [
        "/* Generated by scripts/dev/generate_field_schema.py; do not edit. */",
        '#include "openttd_rl_parity/field_schema.h"',
        "static const otrl_field_meta OTRL_FIELDS[] = {",
    ]
    id_by_path = {item["path"]: item["field_id"] for item in registry["fields"]}
    for item in registry["fields"]:
        path = json.dumps(item["path"])
        anchor = json.dumps(f"{item['source_file']}:{item['source_symbol']}")
        cache_class = json.dumps(item["cache_classification"])
        source.append("    {UINT32_C(%d), UINT16_C(%d), UINT16_C(%d), UINT32_C(%d), UINT32_C(%d), UINT32_C(%d), UINT32_C(%d), UINT8_C(%d), UINT8_C(%d), %s, %s, %s}," % (
            item["field_id"], item["tape_value_type_id"], item["width_bits"] or 0,
            item["fixed_count"] or 0, item["maximum_capacity"],
            id_by_path.get(item["count_source_field"], 0), id_by_path.get(item["offset_target_count_field"], 0),
            klass[item["classification"]], shape[item["shape"]], path, anchor, cache_class))
    source += [
        "};",
        "size_t otrl_field_registry_count(void) { return sizeof(OTRL_FIELDS) / sizeof(OTRL_FIELDS[0]); }",
        "const otrl_field_meta *otrl_field_registry_at(size_t index) { return index < otrl_field_registry_count() ? &OTRL_FIELDS[index] : NULL; }",
        "size_t otrl_field_authoritative_count(void) {",
        "    size_t count = 0U; for (size_t i = 0U; i < otrl_field_registry_count(); ++i) if (OTRL_FIELDS[i].classification == OTRL_FIELD_AUTHORITATIVE_FULL) ++count; return count;",
        "}",
        "const otrl_field_meta *otrl_field_lookup(uint32_t field_id) {",
        "    size_t lo = 0U; size_t hi = otrl_field_registry_count();",
        "    while (lo < hi) { const size_t mid = lo + (hi - lo) / 2U; const uint32_t value = OTRL_FIELDS[mid].field_id; if (value == field_id) return &OTRL_FIELDS[mid]; if (value < field_id) lo = mid + 1U; else hi = mid; }",
        "    return NULL;",
        "}",
    ]
    source_out.mkdir(parents=True, exist_ok=True)
    (source_out / "field_schema.c").write_text("\n".join(source) + "\n", encoding="utf-8")


def build_projection_plan(registry: dict[str, Any]) -> dict[str, Any]:
    group_rules = [
        ("experiment.", "singleton globals", "one value at each declared boundary"),
        ("time.", "singleton native calendar/economy clocks", "one value at each declared boundary"),
        ("timer.", "singleton saved timer owners", "one value; diagnostics are not in the authoritative plan"),
        ("rng.", "gameplay then interactive singleton Randomizer", "state word ordinal ascending"),
        ("economy.", "singleton Economy/Price/CargoSpec tables", "native enum ordinal ascending for fixed tables"),
        ("settings.", "singleton GameSettings", "registry field-ID order"),
        ("map.tile.", "Map::_m then Map::_me", "TileIndex ascending 0..4095 for each native plane"),
        ("map.", "singleton Map", "one value"),
        ("cache.town_kdtree.", "singleton _town_kdtree", "native node vector and free-list indices in exact stored order"),
        ("cache.station_kdtree.", "singleton _station_kdtree", "native node vector and free-list indices in exact stored order"),
        ("company.", "Company::Iterate()", "occupied CompanyID ascending; nested offsets partition native ordinals"),
        ("industry.", "Industry::Iterate()", "occupied IndustryID ascending; produced/accepted/history offsets partition nested vectors"),
        ("station.goods.", "Station::Iterate() then CargoType 0..NUM_CARGO-1", "GoodsEntry lexicographic; packet/flow/share prefix offsets preserve nesting"),
        ("station.", "Station::Iterate()", "occupied StationID ascending; nested offsets preserve native containers"),
        ("road_stop.", "RoadStop::Iterate()", "occupied RoadStopID ascending"),
        ("effect_vehicle.", "Vehicle::Iterate() filtered by BaseVehicle::type Effect", "effect VehicleID ascending; discriminator column maps shared VehiclePool slots"),
        ("road_vehicle.", "Vehicle::Iterate() filtered by BaseVehicle::type Road", "VehicleID ascending; engine/path discriminator columns explicit"),
        ("vehicle.", "Vehicle::Iterate()", "occupied VehicleID ascending; nested packet offsets preserve list order"),
        ("order_list.", "OrderList::Iterate()", "occupied OrderListID ascending"),
        ("order.", "OrderList::Iterate() then orders vector", "(OrderListID, zero-based ordinal) lexicographic"),
        ("cargo_packet.", "CargoPacket::Iterate()", "occupied CargoPacketID ascending"),
        ("town.", "Town::Iterate()", "occupied TownID ascending; supplied/accepted/history offsets preserve slots"),
        ("depot.", "Depot::Iterate()", "occupied DepotID ascending"),
        ("engine.", "Engine::Iterate()", "occupied EngineID ascending; road properties use engine.road_engine_ids"),
        ("cargo_payment.", "CargoPayment::Iterate()", "occupied CargoPaymentID ascending"),
        ("subsidy.", "Subsidy::Iterate()", "occupied SubsidyID ascending"),
        ("linkgraph_job.", "LinkGraphJob::Iterate() and LinkGraphSchedule::running", "occupied LinkGraphJobID ascending; schedule lists preserve native order"),
        ("linkgraph.", "LinkGraph::Iterate() and LinkGraphSchedule::schedule", "occupied LinkGraphID ascending; node/edge offsets and native schedule order are explicit"),
    ]
    rows = []
    for field in registry["fields"]:
        if field["classification"] != "authoritative_full":
            continue
        prefix, owner_iteration, flatten_rule = next(
            rule for rule in group_rules if field["path"].startswith(rule[0])
        )
        rows.append({
            "field_id": field["field_id"],
            "path": field["path"],
            "value_type": field["value_type"],
            "width_bits": field["width_bits"],
            "shape": field["shape"],
            "fixed_count": field["fixed_count"],
            "count_source_field": field["count_source_field"],
            "offset_target_count_field": field["offset_target_count_field"],
            "owner_iteration": owner_iteration,
            "flatten_rule": flatten_rule,
            "native_member_expression": field["native_member_expression"],
            "canonical_cast": "explicit fixed-width value conversion; stable references convert pointer to typed numeric PoolID" if field["value_type"] == "stable_id" else "explicit declared fixed-width conversion; never memcpy native object",
            "source_anchor": f"{field['source_file']}:{field['source_symbol']}",
        })
    return {
        "plan_version": "openttd-p0-projection-plan-v1",
        "authority": "parity/schema/fields-v1.json; this plan is generated implementation guidance and never a second field authority",
        "field_schema_sha256": hashlib.sha256(canonical_bytes(registry)).hexdigest(),
        "authoritative_field_count": len(rows),
        "group_rules": [
            {"path_prefix": prefix, "owner_iteration": owner, "flatten_rule": flatten}
            for prefix, owner, flatten in group_rules
        ],
        "ordered_authoritative_fields": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path,
                        help="write a parity/ output tree below this directory instead of mutating canonical files")
    args = parser.parse_args()
    if args.artifact_root is None:
        schema_out = SCHEMA_OUT
        include_out = INCLUDE_OUT
        source_out = SOURCE_OUT
    else:
        artifact_root = args.artifact_root.resolve()
        schema_out = artifact_root / "parity" / "schema"
        include_out = artifact_root / "parity" / "include" / "openttd_rl_parity"
        source_out = artifact_root / "parity" / "src"
    registry = expand()
    raw = canonical_bytes(registry)
    schema_out.mkdir(parents=True, exist_ok=True)
    (schema_out / "fields-v1.json").write_bytes(raw + b"\n")
    digest = hashlib.sha256(raw).hexdigest()
    (schema_out / "fields-v1.sha256").write_text(f"{digest}  fields-v1.json\n", encoding="ascii")
    plan = build_projection_plan(registry)
    (schema_out / "projection-plan-v1.json").write_bytes(canonical_bytes(plan) + b"\n")
    write_c_table(registry, include_out, source_out)


if __name__ == "__main__":
    main()
