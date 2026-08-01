# P0 Command and Field Mapping Contract

> **Legacy workstream notice (2026-07-31):** The mappings below govern the earlier
> P0 freight fixture and projection. V1 will create separate bus action,
> observation, mask, reward, and model registries under `GOAL.md`.

## Purpose

This file defines the exact mapping work that must be complete before patches 0003–0005 are implemented. The command portion is source-backed to the six native command families frozen by ADR 0003. The field portion defines the mandatory exhaustive 757-row ledger that Codex must generate from the current `fields-v1.json`, `projection-plan-v1.json`, schemas, generated C registry, completeness matrix, source register, and pinned OpenTTD source.

The handoff intentionally does not fabricate external registry action IDs, JSON property names, field paths, or source expressions that were not included in the uploaded source set. Codex must resolve every repository-derived value in the mandatory ledgers from the exact current checkout before code. A fabricated or partially populated table is worse than an explicit blocker and is prohibited.

## Part A — Six-Action Native Dispatch Contract

### A.1 Authoritative distinction: action family versus command instance

ADR 0003 freezes ten command instances:

1. three `BuildRoadLong` instances;
2. one `BuildRoadDepot` instance;
3. two `BuildRoadStop` instances;
4. one `BuildVehicle` instance;
5. two `InsertOrder` instances;
6. one `StartStopVehicle` instance.

Those ten instances use exactly six native command families. Company context, public-step scheduling, tick advancement, checkpoint emission, and terminal emission are replay control operations, not additional OpenTTD gameplay commands.

### A.2 Pinned native command table

The following enum values are zero-based values of `enum class Commands : uint8_t` at OpenTTD pin `29f808ef0022064e6d9a83c8476d1e0f4686af86`. Codex must add compile-time or test-time assertions against the current pinned source so accidental enum drift cannot silently alter the external registry mapping.

| Family | Native enum | Numeric value | Native procedure | Native result | Trait flags | Command type | Fixture instances |
|---|---|---:|---|---|---|---|---:|
| Road stop construction | `Commands::BuildRoadStop` | `22` | `CmdBuildRoadStop` | `CommandCost` | `Auto`, `NoWater` | `LandscapeConstruction` | 2 |
| Long-road construction | `Commands::BuildRoadLong` | `24` | `CmdBuildLongRoad` | `CommandCost` | `Auto`, `NoWater`, `Deity` | `LandscapeConstruction` | 3 |
| Road-depot construction | `Commands::BuildRoadDepot` | `27` | `CmdBuildRoadDepot` | `CommandCost` | `Auto`, `NoWater` | `LandscapeConstruction` | 1 |
| Vehicle construction | `Commands::BuildVehicle` | `34` | `CmdBuildVehicle` | `std::tuple<CommandCost, VehicleID, uint, uint16_t, CargoArray>` | `ClientID` | `VehicleConstruction` | 1 |
| Order insertion | `Commands::InsertOrder` | `46` | `CmdInsertOrder` | `CommandCost` | `Location` | `RouteManagement` | 2 |
| Vehicle start/stop | `Commands::StartStopVehicle` | `121` | `CmdStartStopVehicle` | `CommandCost` | `Location` | `VehicleManagement` | 1 |

Pinned declarations:

```cpp
CommandCost CmdBuildLongRoad(
    DoCommandFlags flags,
    TileIndex end_tile,
    TileIndex start_tile,
    RoadType rt,
    Axis axis,
    DisallowedRoadDirections drd,
    bool start_half,
    bool end_half,
    bool is_ai);

CommandCost CmdBuildRoadDepot(
    DoCommandFlags flags,
    TileIndex tile,
    RoadType rt,
    DiagDirection dir);

CommandCost CmdBuildRoadStop(
    DoCommandFlags flags,
    TileIndex tile,
    uint8_t width,
    uint8_t length,
    RoadStopType stop_type,
    bool is_drive_through,
    DiagDirection ddir,
    RoadType rt,
    RoadStopClassID spec_class,
    uint16_t spec_index,
    StationID station_to_join,
    bool adjacent);

std::tuple<CommandCost, VehicleID, uint, uint16_t, CargoArray> CmdBuildVehicle(
    DoCommandFlags flags,
    TileIndex tile,
    EngineID eid,
    bool use_free_vehicles,
    CargoType cargo,
    ClientID client_id);

CommandCost CmdInsertOrder(
    DoCommandFlags flags,
    VehicleID veh,
    VehicleOrderID sel_ord,
    const Order &new_order);

CommandCost CmdStartStopVehicle(
    DoCommandFlags flags,
    VehicleID veh_id,
    bool evaluate_startstop_cb);
```

Source anchors:

- `openttd-upstream/src/command_type.h`, literal `enum class Commands : uint8_t`.
- `openttd-upstream/src/road_cmd.h`, literals `CmdBuildLongRoad`, `CmdBuildRoadDepot`, and their `DEF_CMD_TRAIT` rows.
- `openttd-upstream/src/station_cmd.h`, literal `CmdBuildRoadStop` and its `DEF_CMD_TRAIT` row.
- `openttd-upstream/src/vehicle_cmd.h`, literals `CmdBuildVehicle`, `CmdStartStopVehicle`, and their `DEF_CMD_TRAIT` rows.
- `openttd-upstream/src/order_cmd.h`, literal `CmdInsertOrder`, its `DEF_CMD_TRAIT` row, and the canonical `Order` endian operators.

### A.3 Required external-registry dispatch ledger

Codex must create a table with exactly six data rows and the following columns. Every cell must contain a concrete current-checkout value; no cell may be blank, inherited from another row, inferred from prose, or populated with an unverified enum label.

| Required column | Rule |
|---|---|
| Registry action ID | Exact stable numeric or string identifier from `commands-v1.json` |
| Registry action name | Exact case-sensitive name from `commands-v1.json` |
| Registry schema version | Exact version governing the action |
| Native enum | One of the six `Commands::` values above |
| Native numeric value | Exact pinned `uint8_t` value above, verified by test |
| Native procedure | Exact declaration and source path |
| Trait flags | Exact `DEF_CMD_TRAIT` flags |
| Command type | Exact `CommandType` value |
| External operand | One row or nested subtable per operand in registry order |
| Canonical operand type | Exact width, signedness, enum representation, sentinel, and byte order from schema |
| Native parameter | Exact C++ type and positional mapping |
| Normalization | Exact validation, sentinel conversion, or derived value; `none` when no normalization occurs |
| Location handling | State whether location is the leading `TileIndex` or the explicit `Post` location argument |
| Company context | Exact allowed company value and native context mechanism |
| Native test result | Exact normalized result tuple fields and encoding |
| Native execute result | Exact normalized result tuple fields and encoding |
| Returned stable IDs | Exact returned ID, width, sentinel, and later-reference rule |
| Golden fixture instances | Exact public steps and operand values from fixture command input |
| Negative cases | Exact malformed and native-rejection cases |
| Unit test | Exact stable test ID and command |
| Integration test | Exact stable test ID and command |
| Source evidence | Exact repository-relative path, line, and literal symbol |

The generated ledger must be written to the current canonical documentation path. When no canonical path exists, use `docs/implementation/P0_COMMAND_DISPATCH_MAPPING.md` and add the file to traceability ownership.

### A.4 Per-command operand mapping requirements

#### A.4.1 `Commands::BuildRoadLong`

Native parameter order after `DoCommandFlags` is binding:

1. `TileIndex end_tile`;
2. `TileIndex start_tile`;
3. `RoadType rt`;
4. `Axis axis`;
5. `DisallowedRoadDirections drd`;
6. `bool start_half`;
7. `bool end_half`;
8. `bool is_ai`.

Required mapping properties:

- The external schema must state whether endpoint order is encoded as end/start or start/end. The adapter must map explicitly; it may not rely on naming intuition.
- All tile indices must be range-checked against the loaded 64×64 map before exposure to gameplay.
- `RoadType`, `Axis`, and `DisallowedRoadDirections` must use exact reviewed numeric widths and value ranges; raw C++ enum object representation is forbidden.
- Boolean operands must be canonical zero or one.
- The fixture uses three flat horizontal segments at `y=31`: `(10,31)`–`(12,31)`, `(12,31)`–`(48,31)`, and `(48,31)`–`(52,31)`. Exact endpoint ordering and raw enum bytes come from the frozen command input, not from this prose.
- Result is `CommandCost`; record success, signed cost, expense category, error string IDs, and zero-length or schema-defined result tuple data.

#### A.4.2 `Commands::BuildRoadDepot`

Native parameter order after `DoCommandFlags` is binding:

1. `TileIndex tile`;
2. `RoadType rt`;
3. `DiagDirection dir`.

Required mapping properties:

- Fixture tile is `(9,31)` / `TileIndex 1993` on a 64-wide map.
- Fixture direction is `DiagDirection::SW`, frozen raw `uint8_t=2`.
- Fixture road type is the exact native original road type from the command registry.
- Result is `CommandCost`.

#### A.4.3 `Commands::BuildRoadStop`

Native parameter order after `DoCommandFlags` is binding:

1. `TileIndex tile`;
2. `uint8_t width`;
3. `uint8_t length`;
4. `RoadStopType stop_type`;
5. `bool is_drive_through`;
6. `DiagDirection ddir`;
7. `RoadType rt`;
8. `RoadStopClassID spec_class`;
9. `uint16_t spec_index`;
10. `StationID station_to_join`;
11. `bool adjacent`.

Required mapping properties:

- Fixture pickup tile is `(12,30)` / `TileIndex 1932`.
- Fixture delivery tile is `(48,30)` / `TileIndex 1968`.
- Both stops are one-by-one, non-drive-through truck bays.
- Both use `DiagDirection::SE`, frozen raw `uint8_t=1`.
- Exact truck-stop enum, default class/index, station-join sentinel, and adjacent flag must come from `commands-v1.json` and pinned declarations.
- The pinned native result type is exactly `CommandCost`; `CmdBuildRoadStop` does not return a `StationID` through its command tuple and the external adapter must not change that signature or the network command wire.
- The approved station-identity source is one narrow execute-only observational hook at an exact pinned source point: immediately after the final `if (st != nullptr) { st->AfterStationTileSetChange(...); }` block and immediately before `return cost;` in `CmdBuildRoadStop`. At that point station construction or joining is complete and the final nonnull `Station *st` is known; the hook copies only `st->index` into the active external-command context.
- The hook is enabled only when all of the following hold: `DoCommandFlag::Execute` is set, an active external oracle command exists, the expected native enum is `Commands::BuildRoadStop`, a minimal read-only `RecursiveCommandCounter` query reports `_counter == 1`, `st != nullptr`, and the context has not already received a station identity for that action.
- The read-only depth query is added only under the existing 0001/0002 trace compile guard found by the evidence audit. It does not increment, decrement, expose, or otherwise mutate recursion state.
- Test-phase calls, rejected tests, test-only estimates, recursive/internal commands, wrong-command contexts, inactive tracing, malformed-input paths, and duplicate hooks populate no valid station identity. A duplicate or missing expected side result records a bounded fatal context error for the replay driver.
- Pool scanning, maximum-ID inference, before/after pool differencing, callback inference, command replay, record I/O inside `CmdBuildRoadStop`, and a modified native return signature are forbidden.
- The normalized execute-result record may include the schema-defined station identity side result only after the current command registry proves that field exists and fixes its width, sentinel, position, and compatibility behavior. The native `CommandCost` remains unchanged.
- When the current command schema lacks that normalized station-result definition despite ADR 0003 requiring returned station identities, stop before code and produce a format-incompatibility dossier: exact missing/contradictory bytes, pinned source evidence, affected producers/consumers, minimal reviewed versioned migration, validator/test updates, fixture impact, and backward-compatibility effect. Never silently consume reserved bytes, append an unversioned field, or change the schema digest.

#### A.4.4 `Commands::BuildVehicle`

Native parameter order after `DoCommandFlags` is binding:

1. `TileIndex tile`;
2. `EngineID eid`;
3. `bool use_free_vehicles`;
4. `CargoType cargo`;
5. `ClientID client_id`.

Required mapping properties:

- Fixture depot tile is `(9,31)` / `TileIndex 1993`.
- Fixture engine is global `EngineID 123`, Balogh Coal Truck.
- Exact cargo argument and `ClientID` sentinel/normalization come from the registry and pinned typed `Post` path.
- `CommandFlag::ClientID` causes non-network posting to replace `ClientID::Invalid` with `ClientID::Server` through native `SetClientIds`. The trace must distinguish external canonical input from the normalized native payload as governed by tape v1; it must not perform a second independent conversion.
- Successful return tuple is `CommandCost`, `VehicleID`, `uint`, `uint16_t`, and `CargoArray` in the exact native order.
- The returned `VehicleID` is the sole approved identity source for later `InsertOrder` and `StartStopVehicle` actions. Pool scanning or “new maximum ID” inference is forbidden.

#### A.4.5 `Commands::InsertOrder`

Native parameter order after `DoCommandFlags` is binding:

1. `VehicleID veh`;
2. `VehicleOrderID sel_ord`;
3. `const Order &new_order`.

The pinned native command serialization order for `Order` is:

1. `order.type`;
2. `order.flags`;
3. `order.dest.value`;
4. `order.refit_cargo`;
5. `order.wait_time`;
6. `order.travel_time`;
7. `order.max_speed`.

Required mapping properties:

- The command does not have a leading `TileIndex`, and its trait includes `CommandFlag::Location`. The adapter must use the explicit-location `Command<Commands::InsertOrder>::Post` overload with the exact registry-defined location. Location is user-feedback context and is not silently inserted into the native command payload.
- `VehicleID` must be the exact returned ID from `BuildVehicle`.
- The two fixture order positions are zero and one.
- Pickup and delivery raw `Order` bytes, type, destination, full-load-any policy, unload-if-accepted policy, refit sentinel, timing values, and speed limit must come from the frozen command input and `Order` accessors. Prose labels cannot replace raw pinned fields.
- Result is `CommandCost`.

#### A.4.6 `Commands::StartStopVehicle`

Native parameter order after `DoCommandFlags` is binding:

1. `VehicleID veh_id`;
2. `bool evaluate_startstop_cb`.

Required mapping properties:

- The command has no leading `TileIndex` and its trait includes `CommandFlag::Location`; use the explicit-location `Post` overload.
- `VehicleID` must be the exact ID returned by `BuildVehicle`.
- The exact boolean value and location come from the registry/frozen command input.
- Result is `CommandCost`.

### A.5 Native posting and result capture

The only approved gameplay entry is one typed native posting path:

```cpp
Command<Commands::X>::Post(...);
```

Tile-leading commands use their normal typed overload. `InsertOrder` and `StartStopVehicle`, whose traits include `CommandFlag::Location`, use the explicit-location overload with the registry-defined location. Every oracle call uses zero error-message presentation and a null callback.

At the pin, `CommandHelper::InternalPost` enters `CommandHelper::Execute`. `Execute`:

1. prepares native company and command state;
2. calls `CommandTraits<Tcmd>::proc` once without `DoCommandFlag::Execute`;
3. validates the test result;
4. returns immediately when the native test fails or execution is not permitted;
5. otherwise calls `CommandTraits<Tcmd>::proc` once with `DoCommandFlag::Execute`;
6. compares/processes test and execute results through native result handling.

The approved instrumentation architecture is binding:

1. Before the one typed `Post`, the replay driver installs an outer scoped `Backup<CompanyID>`, sets the exact validated company, and installs an empty preallocated bounded active-command context containing action identity, public step, tick, company, expected native enum, phase counters, fixed-capacity tuple storage, side-result flags, and first-error state.
2. `InternalPost` preserves existing tile checks and `InternalPostBefore` decisions. The active oracle path suppresses only user-interface presentation. It requires no precheck error, no estimate-only mode, and no send-only/network path.
3. Existing native `SetClientIds` normalization runs exactly once. Immediately afterward, `InternalPost` writes one normalized `COMMAND_INTENT`, then calls `Execute`. Intent-write failure returns before `Execute`, proving zero native test and zero gameplay mutation.
4. An `InternalExecutePrepTest` failure after intent is a fatal incomplete lifecycle, not a fabricated failed test.
5. After `InternalExecuteValidateTestAndPrepExec` returns, the hook copies the final native test tuple into fixed-capacity context storage exactly once. The hook performs no I/O and no allocation.
6. A failed native test produces no execute tuple and no returned-ID side result.
7. After a successful test, the offline branch executes the native procedure once with `DoCommandFlag::Execute`. After `InternalExecuteProcessResult` returns, the hook copies the final processed execute tuple exactly once.
8. `BuildVehicle` identity comes from that native execute tuple. `BuildRoadStop` identity comes only from the exact execute-only `st->index` hook in A.4.3.
9. Recursive/internal commands reached through native `Do` execute unchanged. They do not write intent, populate external phase storage, or populate the station side result. The station hook uses the minimal read-only `_counter == 1` query; the top-level `Post` execution path itself already enforces top-level execution.
10. `InternalPostResult` display/error/cost animation is suppressed only for the active oracle path. No `ShowErrorMessage`, cost animation, GUI, or rendering operation is invoked. No callback runs. Command validation, money handling, mutation, and return value remain native.
11. Immediately after `Post` returns, the replay driver restores the outer company context before result publication or projection, verifies restoration, validates all phase/side-result counts, then writes buffered test and conditional execute records in grammar order.
12. On result-write failure after execution, retain the valid partial prefix and first error, exit through scoped company/context restoration, and stop before projection, later command, or tick; expose no final tape. Do not roll back gameplay or fabricate completion.
13. On every exit, clear the active context through scoped restoration. After successful result publication, require the context inactive/zeroed and only then request the complete post-command projection.

The bridge may not call the procedure, `Do`, `Post`, pathfinder, cache checker, UI callback, or network adapter a second time to reconstruct missing data. Normal non-oracle posting behavior must remain byte-for-byte/source-semantically unchanged outside the guarded instrumentation path.

### A.6 Command boundary grammar

Accepted command:

```text
COMMAND_INTENT
COMMAND_TEST_RESULT(success=1)
COMMAND_EXEC_RESULT(success=1)
AUTHORITATIVE_PROJECTION(boundary=post-command, all 757 fields)
```

Rejected native test:

```text
COMMAND_INTENT
COMMAND_TEST_RESULT(success=0)
AUTHORITATIVE_PROJECTION(boundary=post-command, all 757 fields)
```

The following are invalid:

- execute after failed test;
- successful test without execute when the command is scheduled for execution;
- duplicate test or execute;
- projection before the required result phase;
- omitted post-command projection;
- command execution without a preceding intent record;
- partial command execution after malformed input;
- callback-based success inference when native result data is available;
- an external phase record emitted by a recursive/internal native command;
- a station or vehicle identity populated during test, rejection, or an inactive trace context;
- a pre-test post-path rejection encoded as a failed native test;
- result publication or projection before outer company restoration;
- any callback, `ShowErrorMessage`, cost animation, GUI, or rendering invocation by the active oracle path;
- a post-execute result-write failure followed by projection, another command, or tick advancement.

### A.7 Mandatory command mapping tests

At minimum, the final mapping must be covered by:

1. compile-time/native-value assertions for all six `Commands` numeric values;
2. schema validation for the exact six-action set, exact operand order, exact result fields, and exact station-result compatibility contract;
3. one golden instance of each family;
4. all ten frozen fixture instances with exact costs, IDs, categories, and state transitions;
5. malformed operand width, enum, bool, sentinel, tile, checksum, reserved byte, and trailing-byte rejection;
6. native rejection cases that produce one failed test record, no execute record, no returned ID, and no state change;
7. a test proving one successful action emits normalized intent after `SetClientIds`, invokes native test exactly once, and invokes native execute exactly once;
8. intent-write failure proving no `Execute`, native test, callback, UI presentation, or gameplay mutation;
9. pause, estimate-only, send-only/network, bounds, and invalid-company pre-test cases proving fatal lifecycle handling without fabricated failed-test records;
10. final-test capture after `InternalExecuteValidateTestAndPrepExec` and final-execute capture after `InternalExecuteProcessResult`;
11. a test proving `BuildVehicle` identity is copied from the native execute tuple and `BuildRoadStop` identity is copied from the exact post-station-change/pre-return `st->index` hook, with no pool scan or I/O in the hook;
12. test, rejected-test, test-only, recursive/internal, wrong-command, duplicate-hook, missing-hook, overflow, null-station, and inactive-context cases proving no invalid station identity can be published;
13. a nested-command fixture proving only the top-level external command produces external phases and the read-only depth query does not perturb recursion counts;
14. exact outer-company restoration before test/execute record publication and post-command projection, including success, rejection, and write-fault paths;
15. zero callback, `ShowErrorMessage`, cost-animation, GUI, and rendering calls for active oracle posts while normal non-oracle behavior remains unchanged;
16. a result-write fault after successful execution proving scoped context cleanup, no projection, later command, tick, or final tape;
17. same-tick public-step ordering and complete context clearing between actions;
18. trace-disabled build/runtime paths serialize zero command-result payloads;
19. complete-file prevalidation before fixture load;
20. no partial execution when any later action in the input file is malformed.

## Part B — Exhaustive 757-Field Mapping Contract

### B.1 Completion rule

The field mapping is complete only when a generated Markdown table contains exactly 757 data rows, one for each current registry entry classified `authoritative_full`, and every row is assigned to exactly one of patch 0004 or patch 0005.

Write the ledger to the current canonical documentation path. When no canonical path exists, use `docs/implementation/P0_FIELD_PROJECTION_MAPPING.md`; write the machine-identical representation to `evidence/p0/P0_FIELD_PROJECTION_MAPPING.json`; and write the explicit set proof to `evidence/p0/P0_FIELD_PROJECTION_COMPLETENESS_PROOF.json`. Add every created path to traceability ownership.

A grouped range, wildcard family, “same as above,” repeated-cell inheritance, source-file-only citation, or owner-level test label does not substitute for a row. Ranges may appear in review summaries only after the exact row table exists.

### B.2 Required row columns

Every authoritative row must include:

| Column | Required content |
|---|---|
| Registry field ID | Exact stable nonzero numeric ID |
| Registry field name | Exact case-sensitive registry name |
| Registry field path | Exact case-sensitive fully qualified path |
| Registry version | Exact major/minor version |
| Classification | Must be `authoritative_full` |
| Patch owner | Exactly `0004` or `0005` |
| Canonical type | Exact tape-v1 type |
| Width and signedness | Exact bit width; `n/a` only when type contract makes width inapplicable |
| Units/scaling | Exact unit, scale, or explicit `none` |
| Cardinality | Scalar, fixed count, dynamic count source, offset owner, or bitset shape |
| Capacity | Exact registered hard capacity for dynamic fields |
| Null/invalid sentinel | Exact canonical value and native meaning |
| Native owner | Exact singleton, pool type, object type, embedded container, or scoped owner key |
| Stable owner identity | Exact stable typed ID or composite identity |
| Exact OpenTTD source file | Repository-relative path at pin |
| Exact declaration/definition symbol | Literal current symbol, not only a line number |
| Exact source expression/accessor | Exact read expression or narrow const trace accessor |
| Reached call path | Exact future-consuming or state-owning path justifying inclusion |
| Presence/applicability rule | Exact owner-existence, discriminator, optional-presence, or scope rule |
| Empty/absence encoding | Exact emitted value/count/sentinel; omission is never implicit |
| Lifecycle start | Exact native allocation/creation condition |
| Lifecycle end | Exact native destruction/removal condition |
| Canonical owner order | Exact typed-ID or composite key order |
| Canonical element order | Exact native ordinal/container order |
| Reference validation | Exact target pool/type, invalid rule, and occupancy check |
| Boundary cadence | Replay start, post-command, or post-tick emission; checkpoint and terminal records evaluated immediately after their governing complete projection |
| Read-only proof | Why the source read cannot mutate state, allocate, rebuild, draw RNG, or invoke pathfinding |
| Omission test | Exact test ID that removes the field and must fail |
| Value mutation test | Exact test ID and representative mutation |
| Count/order/type test | Exact test ID that detects structural corruption |
| Runtime projection test | Exact test ID that verifies bytes at all complete boundaries |
| Continuation test | Exact test ID proving future relevance or conservative authority |
| Source-register ID | Existing or newly appended `OTTD-*`/`OTTD-R-*` entry |
| Reviewer note | Narrow source-backed caveat; no speculative prose |

### B.3 Patch assignment rule

`projection-plan-v1.json` is the direct machine authority for patch assignment. The following subsystem split is a validation expectation, not permission to override the plan:

#### Patch 0004 expected ownership

- experiment/game mode, command company context, pause and terminal/fault globals;
- simulation tick and all stored calendar/economy clock state;
- tile-loop and other singleton future-influencing cursors;
- both gameplay and interactive RNG internal states;
- global runtime economy values and global settings owned by singleton state;
- map dimensions and all 4,096 indices;
- ten raw native map planes: `type`, `height`, `m1`, `m2`, `m3`, `m4`, `m5`, `m6`, `m7`, `m8`;
- exact animated-tile scheduler vector and order;
- singleton timer timeout/subsystem state that is stored and future-influencing.

#### Patch 0005 expected ownership

- every pool allocation state, occupancy bitmap, cursor, exact bitmap word vector, padding, and source-backed absence field;
- companies and company-scoped settings/generators;
- towns and reached town caches;
- industries and `_industry_builder` state;
- stations, road stops, `GoodsEntry`, packet maps, flow maps, and nested offsets;
- vehicles, road-vehicle controller/path state, EffectVehicles, vehicle chains, and cargo-list caches;
- OrderLists and embedded Orders;
- CargoPackets and exact container order/provenance;
- Depots, Engines, CargoPayment, Subsidies;
- LinkGraph, BaseNode, BaseEdge, schedule/running order, LinkGraphJob pool, and immutable job inputs;
- reached Town and Station K-d tree raw node vectors, free-list order, root, and imbalance state;
- every other authoritative pooled or embedded owner in the current projection plan.

Company-scoped settings remain with their company owner in 0005 even though global settings are introduced in 0004. Any projection-plan assignment that differs from this expectation must be explained by exact owner/lifecycle evidence rather than silently changed.

### B.4 Required subsystem review coverage

The exact row ledger must cover every current authoritative field represented by these stable-ID review families:

| Family | Reviewed field-ID regions and rules |
|---|---|
| Game/global | `1`–`5`; exact registry entries only |
| Time/timers/RNG/economy globals | `1000` onward, including stored clocks, timeout/subsystem counters, both RNG states, runtime economy/price/payment inputs, and source-backed nonexistence proofs where classified authoritative |
| Settings | `2000` onward plus company-scoped setting fields in company regions; exact registry entries only |
| Map | `3000`–`3021` and exact current entries; ten planes across 4,096 tiles, animated vector order, no semantic replacement |
| Company | `4000` onward; pool allocation, finances, infrastructure, history, service settings, unit/group generators, and exact owner offsets |
| Industry | `5000` onward; pool state, production/acceptance histories, nearby stations, scheduler arrays, and RNG inputs |
| Station/Goods | `6000` onward and `6200` onward; pool state, catchment, queues, packets, flows, caches, nested offsets, and presence bits |
| RoadStop | `6100` onward; pool state, tile, status, linked order, entry/bay state, and occupancy |
| Vehicle | `7000` onward; sparse type discriminators, vehicle/effect IDs, movement/controller/order/cargo/service/random/cache state, chains, and path vectors |
| OrderList/Order | `8000` onward; pool state, sharing, owner offsets, embedded-order raw fields, and native order |
| CargoPacket | `9000` onward; pool state, amount/age/provenance/routing/container ownership and exact order |
| Authoritative spatial/cache state | Exact current K-d tree and other reached authoritative cache entries |
| Town | `12000` onward through the exact current Town region |
| Depot | `12100` onward through the exact current Depot region |
| Engine/RoadVehicleInfo | `12200` onward through exact current engine regions, including sparse road-engine discriminator |
| CargoPayment | `12300` onward through exact current payment region |
| Subsidy | `12400` onward through exact current subsidy region |
| LinkGraph/Jobs | `12500` onward through exact current graph, schedule, job-pool, copied-graph, copied-settings, nesting, node, and edge regions |

The registry, not the ranges above, determines whether a specific ID exists and whether it is authoritative. Unpublished gaps, diagnostic entries, and source-backed unreachable proofs must not be counted as authoritative rows.

### B.5 Canonical map mapping

The map projection must emit:

1. exact dimensions and map size;
2. stable `TileIndex` values zero through 4095 where registered;
3. exactly 4,096 values for each of the ten raw planes;
4. plane values in numeric `TileIndex` order;
5. exact native widths without semantic normalization;
6. animated-tile vector elements in exact native vector order;
7. tile-loop cursor and tick context through their registered singleton fields.

Forbidden substitutions include:

- owner labels instead of raw `m` bytes;
- decoded road/station/depot/industry fields instead of source planes;
- slope or tile-type names instead of exact reviewed numeric values;
- sorting animated tiles when native vector order differs;
- omitting unused or inapplicable bits;
- reading a getter that constructs semantic cache state.

### B.6 Pool and allocation mapping

For every reached `Pool<T>`:

- emit exact `items`/capacity state required by registry;
- emit `first_free` and `first_unused`;
- emit exact `used_bitmap` vector length and every canonical U64 word;
- preserve trailing words and high padding bits;
- emit source-backed proof that no native free-list vector exists when the registry includes that proof field;
- emit occupied IDs in typed numeric order;
- emit every required free/empty slot or bitmap state exactly as registry defines;
- validate each reference against target type, width, sentinel, and current occupancy;
- test fragmented words and simulate `FindFirstFree` to prove next allocation identity;
- never replace native allocation state with a sorted hole list.

`Company::FreeUnitIDGenerator` is a different owner and requires its own exact vector lengths, U64 words, offsets, and next-number tests.

### B.7 Composite and nested identity rules

- Pool object identity: exact typed slot ID plus current occupancy/validity.
- Order identity: `(OrderListID, zero-based ordinal)`; there is no global `Order` pool.
- Station goods identity: `(StationID, CargoType)` plus explicit presence.
- Flow identity: station/cargo owner, origin, and native share ordinal through registered nested offsets.
- CargoPacket identity: typed `CargoPacketID`; containment order is separate authoritative state.
- Road-engine property owner: explicit sparse `EngineID` discriminator before property columns.
- LinkGraph node/edge identity: owning graph plus native node/edge index and registered offsets.
- K-d tree slot identity: raw node-vector index; dead slots and free-list order remain observable when registered.

No pointer, allocator node address, RTTI name, hash bucket order, or process-specific token may enter identity.

### B.8 Presence, absence, and inapplicability

Every row must define one of:

- always present singleton;
- present while occupied pool owner exists;
- present only for an explicit discriminator value;
- present only when a native optional pointer/member is nonnull, accompanied by a separate presence field;
- fixed empty array/count at a valid boundary;
- explicit invalid sentinel;
- source-backed unreachable proof entry, which is not part of the 757 authoritative row set unless the registry explicitly classifies its proof value as authoritative.

The adapter may never silently omit a field because the fixture currently has no owner or because a value appears irrelevant. Empty arrays, zero counts, invalid references, free slots, and absent optional state must follow the exact registry representation.

### B.9 Read-only source-expression proof

Each source expression/accessor must be audited for all of the following:

- declared `const` or direct read semantics where applicable;
- no lazy fill, allocation, invalidation, sorting, rebuilding, save/load, pathfinding, RNG draw, command execution, pool mutation, callback scheduling, or thread synchronization;
- no race with mutable LinkGraph worker annotations;
- no pointer/address serialization;
- deterministic native iteration or explicit stable reordering permitted by registry;
- exact source register coverage.

Narrow const trace accessors or friend adapters are allowed only when private storage cannot otherwise be read. Each accessor must expose exact typed storage and must not create a second source of truth.

Prohibited examples include resolved-name getters that populate caches; K-d tree `Build`, `Rebuild`, lookup, insertion, or removal; pathfinder invocation; `cachecheck.cpp` helpers that may rebuild; save/load as a projection mechanism; and any gameplay command or tick executed solely for observation.

### B.10 Diagnostics exclusion

The 757-row ledger contains only `authoritative_full` fields. Diagnostic registry entries receive a separate patch 0006 ledger with:

- exact diagnostic feature name and declaration bit;
- exact observation hook;
- exact payload schema;
- default-off behavior;
- proof that collection uses already-computed data and does not invoke work;
- explicit exclusion from authoritative field count, hash, equality, and minimization signature except where the structural position of optional records must be validated.

Known diagnostic families include semantic timer phase/mask observations, transient YAPF route decisions, cargo conservation summaries, controller decision observations, and display-only vehicle speed where the current registry classifies them as diagnostic. The current registry is the sole authority for the exact set.

### B.11 Exhaustive table generation procedure

Codex must use current committed validators and generated APIs rather than assume JSON property names. The logical procedure is:

1. validate `fields-v1.json` against its strict schema;
2. validate `projection-plan-v1.json` against its strict schema;
3. run semantic registry validation;
4. enumerate every registry entry in strictly increasing field-ID order;
5. select exactly entries classified `authoritative_full`;
6. assert selected count is 757;
7. join each selected field to exactly one projection-plan row;
8. assert patch owner is exactly 0004 or 0005;
9. join source-register ID, source file, literal symbol/accessor, owner, lifecycle, count source, offsets, sentinel, and tests;
10. verify every literal source symbol at the exact pin after comment stripping using the repository validator;
11. reject duplicate IDs, duplicate paths, duplicate plan rows, unresolved joins, ambiguous sources, and cyclic count dependencies;
12. render one Markdown row per field with no inherited cells;
13. render machine JSON containing the same rows and its schema/version/digests;
14. compare Markdown and JSON row counts and IDs;
15. produce the completeness proof below;
16. run omission and representative mutation tests before implementation begins.

### B.12 Completeness proof

Let:

- `R` be the set of field IDs in the validated registry whose classification is `authoritative_full`;
- `P4` be the set of field IDs assigned to patch 0004;
- `P5` be the set of field IDs assigned to patch 0005.

Required proof:

```text
|R| = 757
|P4| + |P5| = 757
P4 ∩ P5 = ∅
P4 ∪ P5 = R
R \ (P4 ∪ P5) = ∅
(P4 ∪ P5) \ R = ∅
```

Additional assertions:

- no diagnostic or other nonauthoritative field appears in `P4 ∪ P5`;
- every row has one source-register ID;
- every row has one implementation symbol or generated projection binding;
- every row has at least one omission/mutation detector and one runtime projection test;
- every dynamic row has valid count source/capacity and, where nested, correct owner offsets;
- every stable reference row names target type and invalid rule;
- every map plane has exactly 4,096 elements at the frozen fixture boundary;
- every complete projection contains exactly the same 757 field IDs in strictly increasing order.

The proof output must list any missing, extra, duplicate, unassigned, nonauthoritative, or multiply assigned ID. A summary count without the explicit difference sets is insufficient.

### B.13 Required field-level tests

The final test inventory must include:

1. strict schema and semantic registry validation;
2. byte-identical registry regeneration;
3. exact 816 total / 757 authoritative count;
4. exact 757-row plan union/disjointness proof;
5. one-field omission detection for every authoritative field;
6. representative value mutation for every field family and all high-risk fields;
7. type, width, signedness, count, capacity, sentinel, classification, owner-order, and offset corruption detection;
8. source-anchor drift, wrong symbol occurrence, comment-only symbol, and wrong-pin detection;
9. replay-start every-boundary completeness;
10. post-command completeness for accepted and rejected commands;
11. post-tick completeness for every completed tick;
12. map 4,096-element and raw-plane equality;
13. fragmented pool, bitmap padding, cursor, and next-allocation tests;
14. invalid reference, destroyed owner, slot reuse, and wrong-type reference tests;
15. OrderList composite identity and order-vector order tests;
16. station GoodsEntry two-level offset and map-key/packet-next-hop distinction tests;
17. vehicle sparse discriminator, effect vehicle, path-vector order, and chain-order tests;
18. CargoPacket containment/provenance/conservation tests;
19. LinkGraph schedule/running/job immutable-state tests without worker scratch reads;
20. Town/Station K-d tree dead slots, LIFO free list, raw root, topology, and imbalance tests;
21. two independent loads and 10,000-tick continuation equality;
22. instrumentation projection read-only/non-perturbation tests;
23. pointer/address/allocator/locale/unordered-order leakage scans;
24. trace-write failure and partial-journal retention tests.

## Part C — Mapping Approval Gate

Implementation may begin only when all of the following are true:

- the six-row command ledger is complete and source-verified;
- all six native numeric IDs are compile/test asserted;
- every registry operand and result byte maps to an exact native typed value;
- the accepted/rejected command grammar is testable without an extra command call;
- the field ledger contains exactly 757 complete rows;
- the 0004/0005 completeness proof passes;
- every source expression is read-only and source-registered;
- every field has an omission/mutation detector and runtime test mapping;
- no field or command row contains an unresolved marker;
- current schemas, generated APIs, and documentation agree on all counts and classifications;
- Codex records reviewer-visible digests for the command ledger, field ledger, schemas, source pin, and projection plan.

When the mapping gate fails, Codex must stop before production C++ changes and report the exact first missing or contradictory row.
