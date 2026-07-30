# PORT-005 field-completeness matrix

Status: source-owner and continuation review complete for the pinned source
inventory. Runtime agreement remains a separate gate; this matrix never treats
an unexecuted continuation as evidence. Numeric references are immutable field
IDs in `fields-v1.json`. Ranges are inclusive and name only fields whose paths
are listed in the registry.

## 19.6 Global and time fields

| Required review item | Field IDs / source-backed disposition |
|---|---|
| current game mode | `1` |
| pause state affecting advancement | `2` |
| simulation tick/frame counter | `1000` |
| calendar date and fraction | `1001`, `1002` |
| economy date and fraction | `1003`, `1004` |
| reached periodic timer counters/phases | `1012`, `1013` are diagnostics derived from clocks/static registration; stored clock state is `1015`–`1020`, timeout and subsystem counters are `1021`–`1027` |
| pending reached callbacks | `1014` is a diagnostic semantic mask; pinned interval timers execute synchronously and store no persistent pending queue |
| tile-loop cursor | `1010` |
| reached object-loop cursors | `1011`; `1091` proves no persistent vehicle cursor exists |
| both RNG stream internal states | `1030`–`1033` |
| runtime economy, price and payment continuation | `1040`–`1053`, including stored industry daily accumulator/increment and runtime Price/CargoSpec tables |
| optional RNG draw counters | `1090` proves pinned `Randomizer` stores no counter |
| settings revision | `2099` proves no native counter; complete reached values are `2000`–`2098`, including `vehicle.smoke_amount` |
| pathfinder cache revision | `10020` proves no native counter; native path vectors are `7078`, `7079` |
| terminal/fault state | `4`, `5` |
| command company context | `3` |

## 19.7 Map fields

| Required review item | Field IDs / source-backed disposition |
|---|---|
| dimensions and 4,096 stable indices | `3000`–`3003` |
| native type and height/slope storage | `3010`, `3011` |
| owner, road/tram bits/types, station/depot/industry IDs, auxiliary metadata and reached flags | raw overloaded native planes `3012`–`3019`; semantic re-encoding is forbidden |
| tile-loop schedule state | `1010`, `1000` |
| animated-tile scheduler order | `3020`, `3021`; exact `_animated_tiles` vector order is future-relevant because the loop and swap-with-back removal preserve native order |
| map revision counter | `3099` proves pinned `Map` has no persistent revision member |
| map-tied cache invalidation markers | authoritative station, town, vehicle and path cache fields `6032`, `6050`–`6058`, `7078`–`7101`, `12010`–`12020`; no invented global marker |

## 19.8 Company fields

| Required review item | Field IDs / source-backed disposition |
|---|---|
| pool occupancy and allocation cursors | `4000`–`4003`, `4005`; exact native U64 bitmap words and vector length are authoritative; `4004` proves no native free-list exists |
| CompanyID | `4010` (native 8-bit typed ID) |
| money, fractional remainder, loan and loan ceiling | `4011`–`4014` |
| current/categorized construction, purchase, running and revenue ledger | `4009`, `4017`–`4020`, `11010`, `11011`; category order is native `ExpensesType` |
| value/score/history when future relevant | `4043`–`4048` |
| command context | `3` |
| bankruptcy/invalid-company state | `4003`, `4015`, `4016`, `4036`, `4037` |
| command rate-limit remainders | `4038`–`4041` |
| infrastructure and unit-ID allocation | road/station `4021`, `4022`; exact road generator words `4023`; group/rail/signal/water/airport/availability `4050`–`4055`; non-road generator proof `4056`; totals and owner offsets `4070`–`4087` |
| preview, availability, service and renewal continuation | `4031`, `4049`, `4024`, `4025`, `4060`–`4063` |

## 19.9 Industry fields

| Required review item | Field IDs / source-backed disposition |
|---|---|
| pool occupancy/allocation | `5000`–`5003`, `5005`; `5004` is the no-free-list proof |
| ID, type, footprint/anchor, town/owner | `5010`–`5016` |
| produced cargo types/rates/waiting and accepted cargo types/waiting | `5024`–`5031`, with vector counts `5042`, `5043` |
| production/transport/acceptance histories and remainders | `5025`, `5027`, `5028`, `5030`–`5032`, `5041`, `5044`, `5045`, optional-history presence `5052`, totals/offsets `5060`–`5072` |
| production level/counter/timer boundary | `5017`, `5018`, `1012` |
| closure/production-change state | `5019`–`5021` |
| station-capture interaction | `5020`, `5033`, `5040` |
| RNG-dependent production inputs | `5022`, `5023`, `1030`, `1031` |
| construction/founder/exclusive/subsidy continuation | `5046`–`5051` |
| daily native construction scheduler | `5073`–`5078`: `_industry_builder.wanted_inds` and all 240 probability/minimum/target/max-wait/current-wait entries |

## 19.10 Station and road-stop fields

| Required review item | Field IDs / source-backed disposition |
|---|---|
| station pool/ID/owner/anchor/facilities/lifecycle | `6000`–`6003`, `6005`, `6010`–`6017`; `6004` proves no native free list |
| catchment configuration and exact coverage | settings `2063`–`2065`; exact bitmap plus `BitmapTileArea` base/width/height `6032`, `6050`–`6053`, `6081`–`6083`, totals/offsets `6061`, `6068` |
| acceptance state | `6037`, `6200`, `6206` |
| road-stop pool/ID/tile | `6100`–`6104`, `6110`, `6111` |
| orientation | native map station plane bytes `3012`–`3019` for stop tile `6111`; `RoadStop` stores no duplicate orientation member |
| linked stop order | `6030`, `6113` |
| entry, exit, bay and vehicle queue/occupancy | `6112`, nullable entry presence and exact conditional dimensions `6114`–`6118`, `6120`–`6122`, and loading queue `6036` |
| selected-cargo `GoodsEntry` status/waiting/rating/service | `6200`–`6206`, `6230`–`6232` |
| packet chain head/order | `6209`, container next-hop keys `6215`, packet owner/order `9021`–`9023`; the map key is distinct from `CargoPacket::next_hop` |
| load/unload state | `6033`, `6034`, `6036`, `6232`, vehicle `7036`, `7183`–`7186`; truck area dimensions and visit mask `6039`–`6041` |
| station caches and invalidation flags/triggers | `6032`, `6038`, `6044`–`6059`, `6081`–`6083`, `6207`, `6208`, `6210`–`6215`, `6230`–`6232`; GoodsEntry presence/packet/flow totals and nested offsets are `6060`–`6080`; all continuation caches remain authoritative |

## 19.11 Vehicle fields

| Required review item | Field IDs / source-backed disposition |
|---|---|
| pool occupancy/allocation, ID and reuse | `7000`–`7003`, `7005`, `7010`; `7004` proves no stored free list; slot IDs may be reused only after native deletion and every reference is revalidated |
| subtype/engine/type/owner | `7011`–`7013`, native BaseVehicle type `7051`, road count `7069`, road type `7077`, compatible road types `7080` |
| tile, precise position and direction | `7014`, `7016`–`7019` |
| current/next movement and destination | `7015`, `7020`–`7024`, `7070`, `7071`, `7078`, `7079` |
| speed/progress/acceleration/controller | `7020`–`7023`, `7070`–`7076`, caches `7090`–`7101`, movement/order flags `7110`; last display speed is diagnostic `7111`, while `cached_vis_effect` is authoritative `7112` because effect spawning reads it |
| stopped/running/depot/station state | `7025`–`7028`, `7033`–`7036`, `7070`, `7163`, `7164` |
| current order index/list/destination/implicit progress | `7037`, `7140`–`7146`, `7160`–`7169` |
| cargo capacity/type/packet chain/loading | `7029`–`7032`, `7036`, `7129`, `7130`, `7180`–`7186` |
| age/service/reliability/breakdown | `7040`–`7046`, `7123`–`7127`, `7167` |
| route-cache references and persistent path scratch | `7078`, `7079` plus total/owner offsets `7202`, `7203`, `7205` are the entire native `RoadVehPathCache`; transient YAPF observations `10000`–`10011` are diagnostic |
| vehicle random fields | `7047`, `7128` |
| native chain and gameplay tile-hash order | `7048`–`7050`; viewport hash is display-only and excluded from authoritative state |
| persistent EffectVehicles and sparse type ownership | effect count/IDs/animation/sprite `7052`–`7056`; road-vehicle count/IDs `7068`, `7069`; GroundVehicle-only columns are counted only over the road discriminator |
| staged CargoPayment and financial values | `7038`, `7039`, `7120`, `7121`, pool `12300`–`12315` |
| future-consumed caches | `7090`–`7101`, `7180`–`7186`, all `authoritative_full`; NewGRF-only family `7190`–`7195` is explicit `out_of_scope_unreachable` under verified base content |

## 19.12 Order fields

| Required review item | Field IDs / source-backed disposition |
|---|---|
| order pool occupancy/stable ID | `8099` proves no global pool; OrderList allocation is `8000`–`8004`; Order identity is `(OrderListID, ordinal)`, total count is `8039`, and owners+1 offsets are `8020`, `8021` |
| OrderList stable ID and sharing | `8010`–`8014` |
| type, destination, flags, load/unload policy | `8040`–`8043`; flags remain raw pinned bytes with accessor semantics documented |
| canonical list order/next order | `8014`, `8039`, `8040`–`8046`, owner/ordinal canonical order |
| current order index and implicit state | `7140`–`7146`, `7168`, `7169` |
| execution/timetable progress | `8044`–`8046`, `8015`, `8016`, `7160`–`7167` |
| service/depot order state | raw order fields `7140`–`7146` plus service state `7043`, `7124`, `7167` |

## 19.13 Cargo packet fields

| Required review item | Field IDs / source-backed disposition |
|---|---|
| pool occupancy/allocation | `9000`–`9003`, `9005`; `9004` proves no native free list |
| packet ID, amount and age | `9010`–`9012` |
| cargo type | packet type is implicit in owning Vehicle cargo `7029` or `(StationID,CargoType)` goods owner `6200`–`6232`; `CargoPacket` has no type member |
| source station/industry/tile/provenance | `9014`, `9017`–`9020` |
| source date | pinned packet stores transit periods rather than a source date: `9012`; calendar/economy dates are `1001`, `1003` |
| distance-related state | `9014`–`9016` |
| feeder share/transfer state | `9013`, vehicle cache/action partitions `7182`–`7186` |
| destination/routing metadata | `9019`, `9020`, station flows `6207`, `6208`, `6210` |
| owning station/vehicle container and chain order | `9021`–`9023`, mirrored heads/orders `6209`, `7031` |
| split/merge state | `9099` proves there is no separate persistent flag; exact result is pool identity/count/container order `9000`–`9023` |
| conservation totals by phase | diagnostics `11000`–`11004`, checked against authoritative packet/container/ledger fields |

## 19.14 Pathfinder and controller fields

| Required review item | Field IDs / source-backed disposition |
|---|---|
| invocation boundary/start tile/direction/target station or tile | diagnostic `10000`–`10004` |
| selected trackdir/path cost/tie result | diagnostic `10005`, `10006`; authoritative cached choice `7078`, `7079` |
| no-route/node-limit state | diagnostic `10007`, `10008`; max-search setting `2025` |
| cached route state | authoritative `7078`, `7079` in exact vector order |
| topology revision | `10020` proves no native revision counter exists |
| controller/station/depot entry decisions | diagnostic `10009`–`10011`; persistent effects `7070`–`7076`, `6112`–`6117` |
| road-stop occupancy interaction | `6112`, `6114`–`6117`, YAPF settings `2030`–`2032` |
| persistent scratch/queue surviving a tick | native path `7078`, `7079`, stop/loading queues `6036`, `6112`–`6117`; YAPF node containers are per-call diagnostics and do not survive |
| reached gameplay spatial indices | exact raw Town K-d tree `10030`–`10037` and Station K-d tree `10040`–`10047`: node slots, topology, LIFO free list, raw root and imbalance counter |

## Scope-correcting native pools

The independent continuation pass also requires native state outside the
minimum lists above: Town `12000`–`12094`, Depot `12100`–`12114`, Engine
`12200`–`12281` (including sparse road EngineID discriminator `12208`),
CargoPayment `12300`–`12315`, and Subsidy `12400`–`12417`. Manual distribution
does not exclude native graph construction. LinkGraph pool, full graph/node/edge
state and schedule/running order are authoritative `12500`–`12533`; exact
LinkGraphJob pool state is `12529`, `12540`–`12544`; and the native-saveable
immutable job input—ID, join date, ten settings, copied graph, nesting and every
node/edge column—is `12545`–`12579` (with unpublished gaps `12552`, `12553`).
Mutable worker annotations and atomics are not sampled: native LGRJ persistence
discards them and `AfterLoadLinkGraphs()->SpawnAll()` recomputes them.

## Independent source-owner and continuation findings

The generated `source_line_diagnostic` values are navigation checks, not the
review itself. The two required review passes recorded these independent
findings against pin `29f808ef0022064e6d9a83c8476d1e0f4686af86`:

| Source owner | Source-owner finding | Continuation finding / registry consequence |
|---|---|---|
| `Pool<T>` in `src/core/pool_type.hpp` and `pool_func.hpp` | Native storage is `items`, `first_free`, `first_unused`, `data`, and `used_bitmap`; there is no free-list vector. `ResizeFor` writes high padding bits and `FindFirstFree` scans exact `size_t` words. | Word count, x86-64 U64 words, padding and cursors can change the next allocated stable ID. Exact words are full fields; the separate native-free-list entry records source-backed absence. |
| `CompanyInfrastructure` / `FreeUnitIDGenerator` in `src/company_base.h` | Infrastructure owns rail/road arrays plus signal/water/station/airport. Unit and group generators own independent private bitmap-word vectors. | Maintenance, company value and later allocation read these values. All road-relevant infrastructure and exact road/group vector storage are full fields, including owner offsets. |
| `Economy` in `src/economy_type.h`; `_price` and recomputation in `src/economy.cpp`; `CargoSpec` in `src/cargotype.h` | Runtime economy counters and tables are stored separately from settings. | Prices, interest, loan ceiling, payment and industry daily selection read current runtime values. Computed tables remain authoritative caches without continuation proof. |
| `Station`, `BaseStation`, `GoodsEntry` and `FlowStat` | Truck and catchment areas include tile/width/height; nearby industries store paired IDs/distances; packet maps store independent next-hop keys; `GoodsEntryData` has independent pointer presence. Flows are nested origin maps whose shares are cumulative-key/via maps. | Station entry/loading/rating and random next-hop selection observe these members. Presence, exact packet/key order, origins, unrestricted totals, shares and both offset levels are full fields. |
| `Vehicle`, `GroundVehicle`, `RoadVehicle`, `EffectVehicle` | `BaseVehicle::type`, `gv_flags`, `compatible_roadtypes`, controller counters and path vector are distinct native members. Road smoke and the power-station chimney create EffectVehicles; cached visual effect is read during spawn decisions. | Sparse road/effect ID discriminators prevent mis-shaping shared VehiclePool columns. Type/flags/compatibility/path and effect animation/sprite state are full. Only last display speed remains diagnostic. |
| `Engine` / `RoadVehicleInfo` | Road properties are a sparse subset of the Engine pool. | A total count cannot identify sparse owners, so `engine.road_engine_ids` precedes every road-property column. |
| `LinkGraph`, `LinkGraphSchedule`, `LinkGraphJob` | `UpdateStationWaiting` allocates/queues graphs even under manual distribution. LGRJ persistence stores immutable copied graph, settings and join date, then restarts workers after load. | Every live/copy BaseNode/BaseEdge member, nesting, schedule/running order and both pool allocators are full fields. Race-prone worker scratch is never read; two-load/10,000-tick equality must also prove exact pause behavior. |
| `Kdtree` town/station indices | Native storage is node vector `(element,left,right)`, LIFO `free_list`, raw `root`, and `unbalanced`; empty Clear/Build may retain stale root. | Insertion slot reuse, future rebuild selection, tree topology and contained-query order depend on the raw state. Both reached trees remain authoritative caches. |
| `_industry_builder` and `_animated_tiles` | The industry scheduler stores one scalar plus five 240-entry arrays. Animated tiles are saved and ticked in exact vector order with swap-with-back removal. | Scheduler branches can consume RNG/build industries; animated callback order can affect state/RNG. Both families are full. |
| timer managers and saved misc state | Interval callbacks are synchronously registered static objects; no persistent callback queue/phase is stored. Calendar/economy derived members, timeout state and subsystem counters are stored. | Semantic phase/tag values are diagnostics. Stored dates/fractions/year/month/remainders/timeouts/counters are full continuation fields. |

Pass A followed each declaration through writes, invalidation and native
consumers. Pass B started from command legality, allocation, movement, cargo,
timer, RNG and accounting branches and traced every prior controlling value
back to an owner above. A future source pin or scope expansion invalidates both
passes and requires a new signed review, not only regenerated line numbers.
