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

Manual cargo distribution does not make LinkGraphs unreachable. Native
`UpdateStationWaiting` still creates graph components and queues them, and a
component with two nodes can spawn a `LinkGraphJob`. The registry therefore
projects exact LinkGraph pool allocation state, every `BaseNode` and
`BaseEdge` member, node/edge offsets, schedule and running-list order, and the
LinkGraphJob pool. For each job it projects the immutable copied graph, all ten
copied `LinkGraphSettings` members, and `join_date` in typed job-ID order.

The worker thread's `NodeAnnotation`, `Path`, demand, edge-flow, and FlowStat
scratch is not read while the job is active: doing so would race the worker and
violate the instrumentation contract. This scratch is intentionally absent
from native `LGRJ` persistence. `GetLinkGraphJobDesc` saves the immutable copied
graph, copied settings, graph identity, and join date; after load,
`AfterLoadLinkGraphs` calls `SpawnAll` and recomputes the worker result. The
atomic completion/abort hints and `std::thread` object are likewise omitted by
native persistence. They affect wall-clock readiness, not deterministic game
state: when a due result is unfinished, production waits before joining it.
P0 keeps the native thread path unchanged and projects only immutable job data;
it does not join, force synchronous execution, or read mutable annotations. The
P0 continuation campaign must exercise an actual queued/running job across two
independent loads and 10,000 ticks and require exact `_pause_mode`, schedule,
running-list, command, and full-projection equality. Any host-scheduling-induced
pause difference is a hard determinism failure, not a tolerated timestamp.

Tape-v1 field byte/count limits are narrower than the theoretical Cartesian
product of every native LinkGraphJob slot and every NodeID. P0's immutable job
columns therefore use an explicit scope bound derived from this fixture and
command corpus: at most 64 simultaneous cargo-component jobs, two station nodes
per component (128 flattened nodes), and two directed links per component with
headroom to 256 flattened edges. Owner/node offset arrays are bounded at 65 and
129. The declared commands cannot create a third station. Exceeding any bound
is a hard unsupported-scope error before a record is written; values are never
truncated or silently split.

Reached scheduler and effect families are also explicit. `_industry_builder`
keeps `wanted_inds` plus 240 entries of probability/minimum/target/wait state;
the daily callback consults them before RNG and construction branches.
`_animated_tiles` preserves native vector order because the tick loop and
swap-with-back removal make order behaviorally relevant. Road smoke and the
power-station chimney create persistent EffectVehicles in the shared Vehicle
pool, so their stable IDs, animation state, current sprite, and the reached
`vehicle.smoke_amount` setting are authoritative.

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
not invent one. The private Town and Station K-d trees use narrow const views of
their raw node vectors and free-list vectors plus direct root/imbalance reads.
The adapter never calls `Build`, `Rebuild`, `Insert`, `Remove`, or a lookup.

## Cache classification protocol

Every reached cache records owner, storage, consumers, invalidation trigger and
classification. Caches consumed by movement, cargo, command, allocation,
payment, timer, tie-breaking, or RNG paths are `authoritative_full`. This includes
Town cache data, company infrastructure/unit allocation, industry nearby
stations, station catchment/nearby/trigger state, GoodsEntry cargo/flow state,
Vehicle/GroundVehicle caches, vehicle cargo-list caches, `OrderList` duration and
count caches, `RoadVehicle::path`, and the reached Town/Station K-d trees.

Both K-d trees are authoritative caches in v1. Exact state means every node
vector slot (including dead slots), each element and left/right index, exact
free-list order, raw `root`, and `unbalanced`. The free list is LIFO and changes
future node reuse; topology changes range traversal; `unbalanced` selects a
future rebuild. `Kdtree::Clear` and an empty `Build` do not reset `root`, so an
empty tree may retain an ignored stale raw root. The projection preserves that
value rather than normalizing it to `SIZE_MAX`.

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
symbol, diagnostic line and reached call path. Generation and validation strip
block and line comments, require the symbol at the reviewed first code locator,
and reject a line that points to a comment or a different occurrence. Lines may
be regenerated only from the same pin; a different commit is a schema failure.
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
