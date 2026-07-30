# ADR 0005: authoritative field schema and cache policy

- Status: accepted for registry v1; runtime continuation evidence is a release gate
- Date: 2026-07-30
- Pinned behavior source: OpenTTD `29f808ef0022064e6d9a83c8476d1e0f4686af86`
- Registry: `parity/schema/fields-v1.json`
- Completeness review: `docs/testing/PORT005_FIELD_COMPLETENESS.md`

## Decision

The P0 oracle uses one append-only numeric field registry. A complete projection
is a columnar snapshot of every `authoritative_full` field after fixture load,
after every native command result, and after every declared post-tick boundary.
Diagnostics accompany a boundary but never replace complete state.

The registry defaults every value that can influence continuation to
`authoritative_full`. No cache is classified `derived_rebuild` in v1. This is a
deliberately conservative decision: the required clear/rebuild experiment,
immediate command and tick comparisons, two independent loads, and 10,000-tick
continuation have not proved any reached cache safely derivable. The cost of
larger oracle tapes is acceptable; an unobserved continuation dependency is not.

## Versioning and stable IDs

Registry versions are `(major, minor)`. Additive entries increment the minor
version. A changed encoded meaning, comparison rule, type, width, signedness,
owner identity, or canonical order requires a new field ID; incompatible format
changes require a new major version. Field ID zero is permanently reserved.

Published IDs are never reused. Deletion leaves a reserved deprecated entry.
Renaming a path does not change an ID when encoded meaning is identical. Numeric
ranges follow the P0 subsystem allocation in the execution contract, with
reviewed expansion pools at 12000 and above. Registry order is strictly numeric.

There is no global `Order` pool at the pin. `OrderList` is pooled and owns a
`std::vector<Order>`, so an order's stable identity is `(OrderListID, zero-based
ordinal)`. Pool objects use their typed numeric slot IDs. IDs may be reused only
after native deletion; every reference is validated against current occupancy.
Pointers, process addresses, RTTI names, host `size_t`, and container node
addresses are never identities.

Pinned `Pool<T>` has no stored free-list or free-slot ordering vector. Its
authoritative allocation state is `items`, `first_free`, `first_unused`, and
the exact `used_bitmap` vector. Because the reference build is frozen to
x86-64, each native `BitmapStorage=size_t` word is converted explicitly to
canonical `U64`. The projection records vector word count and every word,
including trailing words and `ResizeFor` high padding bits. A sorted list of
holes would lose vector length and padding, so the registry records only the
source-backed absence of a native free list. Tests simulate `FindFirstFree` on
fragmented words and reject word-count, padding, cursor, and next-ID mutations.

`Company::FreeUnitIDGenerator` is a distinct source owner. Its vector length
and exact words directly control the next road-vehicle or group number,
including trailing cleared words. Road and group generators therefore have
separate totals, per-company offsets, and U64 word columns. Other vehicle-type
generators are source-recorded as unreachable under the validated
road-freight-only command corpus.

## Types, widths, nulls and canonical encoding

Values use tape-v1 types `U8/U16/U32/U64`, `I8/I16/I32/I64`, `BYTES`,
`STABLE_ID`, `BITSET`, and diagnostic UTF-8. Numeric fields declare exact 8, 16,
32, or 64-bit widths and signedness. Stable IDs declare their pinned `PoolID`
storage width: Company IDs are 8-bit; Town, Industry, Station, RoadStop, Depot,
Engine, OrderList, Subsidy and LinkGraph IDs are 16-bit; Vehicle, CargoPacket and
CargoPayment IDs are 32-bit. Each field states its exact null sentinel.

All numeric elements are little-endian. Raw C++ enum or object representation is
forbidden: enum values are converted to the explicitly reviewed integer width.
No struct padding, pointer bytes, `sizeof(size_t)`, locale, or host endianness can
enter a projection. Scalar count is one. Fixed arrays have their declared exact
count. Dynamic arrays carry a registered count-source field and a hard capacity.
Bit zero of a bitset's first byte represents stable index zero.

Flattened nested containers are never decoded from totals alone. Every
variable-length family has an `owners + 1` U32 offset array: its first value is
zero, values are nondecreasing, and its final value equals the registered
flattened target total. Empty owners therefore remain distinguishable. The
validator forbids self-referential or cyclic count sources and requires count
sources and offset targets to be registered scalars. GoodsEntry uses two
nesting levels: per-`(StationID,CargoType)` packet and flow-owner offsets, then
per-FlowStat share offsets. Flow origin, unrestricted total, cumulative share
key, and via StationID are separate fixed-width columns, never opaque bytes.

The native map is ten separate columnar fields—`type`, `height`, `m1`, `m2`,
`m3`, `m4`, `m5`, `m6`, `m7`, `m8`—each ordered by TileIndex 0 through 4095.
This preserves all overloaded native bits. Semantic road, station, depot,
industry, owner, slope, tram and auxiliary labels must not replace the planes.

Entity columns are ordered by occupied typed ID. Nested data uses owner ID then
native ordinal: OrderList then order ordinal, station then CargoType, owner then
packet/container ordinal, and LinkGraph node/edge index. Container order is
authoritative even when values and totals are otherwise equal.

## Owners and lifecycle

Singleton owners include experiment control, clocks, timer manager, map,
settings and RNG streams. Pooled owners begin at successful native allocation
and end at native destruction. Embedded orders begin with their owning
OrderList/vector entry. Cargo packet ownership changes only through native
station/vehicle container operations. A field remains present at every full
boundary while its owner exists; empty pools and arrays still emit their count
and allocation metadata.

Company service settings belong to `Company::settings.vehicle`, not global
`GameSettings`. Engine, Town, Depot, CargoPayment, Subsidy and LinkGraph pools
are included because each can affect lawful purchase, movement, cargo,
accounting, allocation or timer behavior. The gameplay vehicle tile hash chain
is included in native order; the viewport hash and sprite cache are display
diagnostics only.

Runtime `Economy` state is independent of settings and is projected directly:
loan ceiling, fluctuation, interest, inflation increments and accumulators,
industry daily counter/increment, all 71 runtime Price values, price-base
multipliers, and cargo initial/current payment rates. The computed industry
increment, Price table, and current cargo payments remain
`authoritative_cache`; content identity plus settings is not a rebuild proof.

The fixture fixes all cargo-distribution modes to manual and the validated
command corpus cannot change them. LinkGraph pool occupancy is still emitted
as a full zero-state assertion. Detailed node/edge families, schedule order,
running-job order, and LinkGraphJob pool are explicit
`out_of_scope_unreachable` source entries. If later scope permits non-manual
distribution, that proof expires; every BaseNode/BaseEdge member plus schedule
and job continuation state must be added before publishing a new version.

## Read-only projection adapters

Instrumentation may add narrow `const` trace accessors or friend adapters solely
for private fields. An adapter returns explicitly typed values or iterates a
native container in documented order. It must not call an accessor that lazily
allocates, fills or invalidates a cache; invoke pathfinding; draw RNG; save/load;
rebuild a subsystem; change pool allocation; or mutate a native object.

For example, Town and station resolved-name getters are prohibited because they
fill display caches. CargoPacket private fields and Order private members require
narrow const reads. `RoadVehicle::path` is read directly as ordered `(trackdir,
tile)` elements. `RoadVehPathCache` has no topology revision member, so v1 does
not invent one.

## Cache classification protocol

Every reached cache records owner, storage, consumers, invalidation trigger and
classification. Caches consumed by movement, cargo, command, allocation,
payment, timer, tie-breaking, or RNG paths are `authoritative_full`. This includes
Town cache data, company infrastructure/unit allocation, industry nearby
stations, station catchment/nearby/trigger state, GoodsEntry cargo/flow state,
Vehicle/GroundVehicle caches, vehicle cargo-list caches, `OrderList` duration and
count caches, and `RoadVehicle::path`.

To propose `derived_rebuild`, a future change must:

1. add a test-only clear operation that changes no underlying authoritative input;
2. clear at an approved complete boundary and prove the underlying projection unchanged;
3. rebuild only through the normal production path;
4. compare meaningful rebuilt fields and both RNG streams;
5. compare the next native command and next native tick;
6. compare a 10,000-tick continuation;
7. repeat from two independent fixture loads;
8. prove pool allocation, route ties and callback order unchanged;
9. retain raw tapes and a reviewed evidence statement; and
10. change the registry/ADR together.

Immediate equality, a save/load rebuild, or a cache-check helper is insufficient.
Until all ten steps pass, the cache remains authoritative.

## Omitted-field and mutation experiments

For every field family, tests copy the registry/projection, remove one required
field, mutate a representative value, change count/order/type/width/class, or
break a source anchor. The strict validator must report the first exact fault.
Pool tests independently check exact bitmap word count/values, high padding,
allocation cursors, simulated next allocation, references and iteration order.
Cargo tests check packet identity/order,
provenance, amount and conservation diagnostics. Ledger tests change native
expense categories and one-unit amounts. Timer/RNG tests change internal
fractions and one state word, not display dates or final hashes alone.

Where a field does not exist in pinned native storage, the registry contains a
source-backed `out_of_scope_unreachable` proof entry rather than an invented
value. Examples are a global Order pool, RNG draw counter, map/settings/path
revision counters and persistent split/merge flags.

## 10,000-tick continuation

The release experiment starts two independent loads with equal complete initial
projections, executes the same validated command input, and records every
declared boundary for at least 10,000 native ticks after the cache experiment.
Equality means exact command results, complete field bytes, both RNG states,
pool/allocation state, packet order, ledgers and terminal state. Hash equality is
only an integrity shortcut; the independent field comparator remains decisive.
Any divergence invalidates a `derived_rebuild` proposal.

## Source-anchor standard

Every entry names the pin, source-relative file, literal declaration/definition
symbol, diagnostic line and reached call path. The validator checks the file at
the pinned checkout and requires the symbol on the recorded line. Lines may be
regenerated only from the same pin; a different commit is a schema failure.
Research notes are navigation aids, never sole behavioral authority.

## Review signoff

Publication requires both independent passes:

- source-owner: follow declarations, writes, reads, pool/container ownership,
  invalidation and native consumers;
- continuation: start at every future command, movement, cargo, timer, RNG,
  allocation and accounting branch and identify prior controlling state.

The completeness matrix must contain no unaccounted bullet. Registry/schema/C
metadata regeneration must be byte-identical. Sample bytes, source anchors,
projection agreement, mutation cases and fixture RNG/settings identities must
pass. Runtime two-load and 10,000-tick artifacts must exist before PORT-005 is
reported `PASS`; this ADR does not convert their absence into a skip.
