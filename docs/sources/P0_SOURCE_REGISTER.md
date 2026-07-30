# P0 Source Register

## Register policy

Access date for all initial entries is 2026-07-30. Exact-commit OpenTTD URLs and
the local pinned submodule are behavioral authority. URLs to current branches are
never substituted. Every additionally reached helper, table, cache, timer, pool,
or content source is added before its behavior is represented in a schema or test.

| ID | Source and location | Version or commit | Relevant subject | Governs |
|---|---|---|---|---|
| `AUTH-001` | `OPENTTD_P0_ORACLE_CONTRACT_AGENT_PROMPT.md` | SHA-256 `8421e6555d9c6f6671862261096010f5c25e23349adb947ba9ab22af5b2c67f2` | Complete P0 execution contract | all P0 files and gates |
| `AUTH-002` | `NEXT_STAGES_IMPLEMENTATION_HANDOFF.md` | SHA-256 `663096b12c8e53b2fce550161385fdb67f25404d47262acf4f0f23d5209834e0` | Approved direction, authority order, next stages | ADRs 0001-0006; all ports |
| `AUTH-003` | `OpenTTD_CUDA_RL_REVERSE_ENGINEERING_REPORT.md` | SHA-256 `534a835e4ad788833f629d82fc8690302bd8d65050e3644081e129a746ec6443` | Consolidated reverse engineering | fixture, projection, parity decisions |
| `AUTH-004` | `research-notes/00-repository-metadata.md` | SHA-256 `72ba9a77626613d2bda8896b47ebd1660432a515dee9929aa85296e5fe142bb9` | Repository identity | ADR 0001; source manifest |
| `AUTH-005` | `research-notes/01-repository-build.md` | SHA-256 `73b7f787434cc90656b3c1e3ba4c7e03f46e89af8324a31ceb6c9412b5ca47ed` | Build graph, dependencies, tests | ADR 0002; PORT-001 runners/manifests |
| `AUTH-006` | `research-notes/02-docs-legal.md` | SHA-256 `25ee61ea6e1fe94b5f7de44a4253e62150fd2c8935b7664fa0e3b5f5f73ad265` | GPL, assets, contribution policy | ADRs 0001 and 0006; licenses/provenance |
| `AUTH-007` | `research-notes/03-gameplay-sim-path.md` | SHA-256 `64bf11ea8e6cab6e6ca46eb13658284a213f2d325d480d123c8621ceaf1a307f` | Commands, clocks, cargo, economy, YAPF | ADRs 0003 and 0005; instrumentation/fields |
| `AUTH-008` | `research-notes/04-end-to-end-workflow.md` | SHA-256 `ae9fc8b73797016f48c77b7f9278636508112bd0fdbc6b6a78d1612b904fbd82` | Construction-to-delivery/save flow | fixture and continuation tests |
| `AUTH-009` | `research-notes/05-clean-room-cuda-mvp.md` | SHA-256 `ed8ce7c2609e273a5ea5fdae61df71e979c398ba6b8c547f4a395f9c40468553` | Historical optional plumbing; not fidelity proof | forbidden-scope boundary only |
| `AUTH-010` | `research-notes/06-ui-persistence-render.md` | SHA-256 `bfaa434fc96c8e4a87f29099007c82abb9308eb7cce4d266dc29a027a9ab6d91` | Command/UI boundary, save, rendering, assets | fixture input boundary; forbidden UI state |
| `AUTH-011` | `research-notes/07-build-verification.md` | SHA-256 `6feb6b7f611b38f8e3aed1cbf6e658c69125c22c8312a752c242939d730be93e` | Earlier build and OpenGFX evidence | PORT-001 hypotheses to reverify |
| `AUTH-012` | `research-notes/08-mvp-product-audit.md` | SHA-256 `f03f8a9ed537e3367628d9d1ccf37c0f7f02da3dd1467fff78627e4e8665f182` | Scope audit and parity corrections | all scope and projection decisions |
| `AUTH-013` | `research-notes/09-verification-audit.md` | SHA-256 `0a51f7818e51e5e0e83026cde1137cf5127b4ce924454a51de4a974c81cb98d6` | Independent audit selecting exact-port direction | authority hierarchy and gate strictness |
| `AUTH-014` | `research-notes/10-netherite-reference.md` | SHA-256 `c2555b640971115608cbeeb8b0cde833c84ab1a6f96f65dc7e8a5648a505c93b` | Testing methodology lessons only | test strategy; never behavioral proof |

## Pinned OpenTTD starting anchors

All entries below use commit `29f808ef0022064e6d9a83c8476d1e0f4686af86`
and local root `openttd-upstream/`. The repository tree is also available at the
[exact commit](https://github.com/OpenTTD/OpenTTD/tree/29f808ef0022064e6d9a83c8476d1e0f4686af86).

| ID | Exact source | Relevant subject | Initial governed artifacts |
|---|---|---|---|
| `OTTD-001` | [`src/openttd.cpp`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/openttd.cpp) | main loop, game load/start, tick dispatch | instrumentation patches 0002, 0004, 0007 |
| `OTTD-002` | [`src/command_func.h`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/command_func.h) | command declarations and dispatch interfaces | command registry; patch 0003 |
| `OTTD-003` | [`src/command.cpp`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/command.cpp) | command test/execute machinery and results | command registry; patch 0003; comparator fields |
| `OTTD-004` | [`src/road_gui.cpp`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/road_gui.cpp) | normal road command origins | fixture command mapping only; GUI excluded from authority |
| `OTTD-005` | [`src/road_cmd.cpp`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/road_cmd.cpp) | road construction/removal and tile behavior | ADR 0003; command/field registries; patches 0003-0006 |
| `OTTD-006` | [`src/station_cmd.cpp`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/station_cmd.cpp) | road-stop construction and station behavior | fixture, command registry, pool projection |
| `OTTD-007` | [`src/station_base.h`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/station_base.h) | station pool and cargo state | field registry; patch 0005/0006 |
| `OTTD-008` | [`src/vehicle_cmd.cpp`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/vehicle_cmd.cpp) | vehicle construction, sale, start/stop, service | fixture commands; vehicle projection |
| `OTTD-009` | [`src/roadveh_cmd.cpp`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/roadveh_cmd.cpp) | road-vehicle ticks, movement, loading | field registry; patches 0005/0006; continuation |
| `OTTD-010` | [`src/order_cmd.cpp`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/order_cmd.cpp) | order mutation and validation | fixture commands; order pool projection |
| `OTTD-011` | [`src/pathfinder/yapf/yapf_road.cpp`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/pathfinder/yapf/yapf_road.cpp) | road route choice and cache interactions | route diagnostics; cache classification |
| `OTTD-012` | [`src/economy.cpp`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/economy.cpp) | delivery, payment, company ledger | ledger and cargo fields; continuation evidence |
| `OTTD-013` | [`src/saveload/saveload.cpp`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/saveload/saveload.cpp) | save/load boundaries and compatibility | fixture identity; cache/continuation tests |
| `OTTD-014` | [`COMPILING.md`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/COMPILING.md) | supported build procedure and dependencies | ADR 0002; reference runners |
| `OTTD-015` | [`CODINGSTYLE.md`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/CODINGSTYLE.md) | upstream C++ conventions | instrumentation patches |
| `OTTD-016` | [`CONTRIBUTING.md`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/CONTRIBUTING.md) | contribution and AI policy | ADR 0001; publication gate |
| `OTTD-017` | [`COPYING.md`](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/COPYING.md) | GPL terms and notices | ADR 0001; `LICENSES/` |

The reached-source section is intentionally append-only during implementation.
Initial anchors do not claim projection completeness.

## Reached OpenTTD sources registered during P0 design

Every local path below is governed by the same exact pinned commit as the starting
anchors. Line ranges are anchors at that commit; symbol review controls if a later
tool displays shifted diagnostic line numbers.

| ID | Local pinned source and anchor | Reached behavior | Governs |
|---|---|---|---|
| `OTTD-R-001` | `src/command_func.h:132-193,219-247,313-464` | typed command post, validation, native test and execute phases | command-input action mapping; patch 0003 |
| `OTTD-R-002` | `src/command.cpp:175-189,260-263,301-391` | money checks, command log context, test/execute consistency and completion | command records, costs, rejection tests |
| `OTTD-R-003` | `src/command_type.h:205-360` | stable native command identifiers and traits | `commands-v1.json` |
| `OTTD-R-004` | `src/network/network_internal.h:90-103` | `CommandPacket` representation | native-dispatch adapter only; never external raw ABI |
| `OTTD-R-005` | `src/network/network_command.cpp:133-173,256-285,374-407,493-510` | generated dispatch, company context, sanitization and `PostFromNet` | patch 0003 and native-command parity tests |
| `OTTD-R-006` | `src/network/network.cpp:1149-1260` | existing compiled-in command replay precedent | strict replay architecture evidence |
| `OTTD-R-007` | `src/openttd.cpp:856-868,1202-1281` | headless company-creation branch and complete game-tick ordering | fixture creation ADR; post-tick projection hook |
| `OTTD-R-008` | `src/timer/timer_game_tick.cpp:51-59` | tick increment and callback order | tick boundary and global time fields |
| `OTTD-R-009` | `src/timer/timer_game_calendar.cpp:95-161` | calendar progression | calendar fields and continuation |
| `OTTD-R-010` | `src/timer/timer_game_economy.cpp:122-188` | economy-date progression | economy fields and continuation |
| `OTTD-R-011` | `src/timer/timer.h:21-184` | timer period, storage, timeout and fired state | field registry and timer projection |
| `OTTD-R-012` | `src/timer/timer_manager.h:26-123` | timer registry and callback order | timer audit; pointer order excluded |
| `OTTD-R-013` | `src/timer/timer_game_common.h:99-145` | deterministic gameplay timer priorities | timer semantic tags and order tests |
| `OTTD-R-014` | `src/core/random_func.hpp:27-43`; `src/core/random_func.cpp:42-69` | gameplay and interactive RNG state/algorithm/seeding | both RNG field families and startup policy |
| `OTTD-R-015` | `src/os/unix/unix_main.cpp:21-36` | wall-clock startup seed for both RNG streams | deterministic launch-seed control risk |
| `OTTD-R-016` | `src/saveload/misc_sl.cpp:86-112` | saved calendar, economy, tick, cursor, timeout, gameplay RNG and pause state | continuation inventory and fixture load audit |
| `OTTD-R-017` | `src/saveload/randomizer_sl.cpp:16-43` | saved script randomizers | GameScript exclusion and fixture policy |
| `OTTD-R-018` | `src/saveload/afterload.cpp:3442-3456` | human company creation after nonnetworked load | fixture-construction/load strategy |
| `OTTD-R-019` | `src/map.cpp:19-59`; `src/map_func.h:25-55,84-220` | dimensions, native map planes, accessors and stable iteration | complete 4,096-tile projection |
| `OTTD-R-020` | `src/landscape.cpp:800-842,1729-1742` | persistent tile-loop cursor and daily subsystem order | map cursor, tick projection and continuation |
| `OTTD-R-021` | `src/core/pool_type.hpp:49-81,140-163,203-243,416-461` | slot IDs, capacities, used bitmap, allocation cursors and stable iteration | generic pool projection and typed references |
| `OTTD-R-022` | `src/core/pool_func.hpp:35-176` | bitmap growth, first-free search, allocation and free | future ID/allocation-state projection |
| `OTTD-R-023` | `src/company_base.h:23-148`; `src/company_cmd.cpp:277-357,627-703` | company pool, finances, history, infrastructure, unit-ID bitmap and timeout | company/ledger projection and fixture finances |
| `OTTD-R-024` | `src/town.h:37-38,234-238`; `src/town_cmd.cpp:3229-3256` | town pool, lazy name cache and growth-rate command | fixture town freeze and cache policy |
| `OTTD-R-025` | `src/industry.h:25-138,273-276`; `src/industry_cmd.cpp:1234-1255,2449-2490,3082-3141` | industry pool, production/timers, density and name cache | coal fixture, industry fields and cache policy |
| `OTTD-R-026` | `src/table/build_industry.h:1048-1051,1149-1168`; `src/table/cargo_const.h:56-60,103-108` | coal mine/power station and temperate coal mappings | ADR 0003 cargo/industry selection |
| `OTTD-R-027` | `src/table/engines.h:226-228,670-684`; `src/engine.cpp:755-829`; `src/engine_type.h:150-166` | original coal-truck definitions and availability initialization | fixture engine identity and compatibility |
| `OTTD-R-028` | `src/base_station_base.h:19-20,76-87`; `src/station_base.h:336-343,549,561`; `src/station_cmd.cpp:4334-4371` | station/road-stop pools, cargo data, catchment, nearby industry and timing | station/goods projection and cache audit |
| `OTTD-R-029` | `src/vehicle_base.h:47-92,162-317`; `src/vehicle.cpp:985-1071,1874-1914` | vehicle pools, timers/cargo, caches, stable ticks and unit-ID allocation | vehicle/controller/cache projection |
| `OTTD-R-030` | `src/roadveh.h:91-106`; `src/roadveh_cmd.cpp:925-984,1397-1403,1651-1669` | road-path vector consumption/insertion, vehicle tick and invalidation | authoritative road controller/path cache |
| `OTTD-R-031` | `src/order_base.h:23-56,384-547`; `src/order_cmd.h:35-44` | order pool, raw fields, order-list caches and canonical native wire model | order action schema and complete order projection |
| `OTTD-R-032` | `src/cargopacket.h:23-65,288-619` | packet pool, packet fields, list order, reservations and cached totals | cargo packet/list field families |
| `OTTD-R-033` | `src/economy_base.h:15-38`; `src/saveload/economy_sl.cpp:44-120` | cargo-payment pool and saved economy globals/payment state | payment and continuation projection |
| `OTTD-R-034` | `src/economy.cpp:880-895,1085-1129,1172-1222` | production accumulation, delivery statistics, route profit and final delivery | cargo/payment diagnostics and ledger checks |
| `OTTD-R-035` | `src/cachecheck.cpp:31-242` | production cache checking and potential rebuild side effects | prohibition on extra cache checks; checkpoint experiments |
| `OTTD-R-036` | `src/pathfinder/yapf/yapf_road.cpp:338-405` | road path-vector construction | route diagnostics and road-path cache policy |
| `OTTD-R-037` | `src/tests/CMakeLists.txt:1-23`; `cmake/scripts/Regression.cmake:17-127` | native unit inventory and saved-fixture/null-driver regression pattern | PORT-001 inventory and oracle integration tests |
| `OTTD-R-038` | `docs/debugging_desyncs.md:3-25`; `docs/desync.md:20-69,140-151` | command recording, deterministic model and cache-debug guidance | nonperturbation and cache validation strategy |
| `OTTD-R-039` | `src/settings_type.h:84-716` | native difficulty, economy, vehicle, pathfinder, station-catchment and company-service settings | registry `2000`-`2065`, `2099`, `4024`-`4025`, `4060`-`4063`; patches 0005-0006 |
| `OTTD-R-040` | `src/economy_type.h:45-195` | stored `Economy`, `Price`, `Prices` and runtime inflation/payment inputs | registry `1040`-`1048`, `4009`; patches 0005-0006 |
| `OTTD-R-041` | `src/cargotype.h:85-107,190-200` | `CargoSpec` initial/current payment and fixed cargo-type cardinality | registry `1052`-`1053`, `6060`; patches 0005-0006 |
| `OTTD-R-042` | `src/depot_base.h:20-26` | depot identity, tile, town association, town counter and construction date | registry `12110`-`12114`; patches 0005-0006 |
| `OTTD-R-043` | `src/engine_base.h:28-70` | engine class/type discriminator, availability, lifecycle, reliability, preview and company mask | registry `12207`-`12208`, `12210`-`12228`; patches 0005-0006 |
| `OTTD-R-044` | `src/engine_type.h:75-225` | complete `EngineInfo` and road-only `RoadVehicleInfo` properties | registry `12240`-`12254`, `12270`-`12281`; patches 0005-0006 |
| `OTTD-R-045` | `src/subsidy_base.h:22-28` | subsidy cargo, remaining duration, award state, source and destination | registry `12410`-`12417`; patches 0005-0006 |
| `OTTD-R-046` | `src/linkgraph/linkgraph.h:21-201` | graph/node/edge storage, cargo, station, capacity, usage and timestamps | registry `12505`-`12517`, `12520`-`12526`, `12530`; source-backed unreachable proofs under frozen manual distribution; patches 0005-0006 |
| `OTTD-R-047` | `src/linkgraph/linkgraphschedule.h:23-58` | scheduled graph order and running-job ownership/order | registry `12527`-`12528`; source-backed unreachable proofs; patches 0005-0006 |
| `OTTD-R-048` | `src/linkgraph/linkgraphjob.h:20-33` | link-graph job pool and job identity | registry `12529`; source-backed unreachable proof; patches 0005-0006 |
| `OTTD-R-049` | `src/roadstop_base.h:21-74` | road-stop identity, tile, status, linked order, bay length and occupancy | registry `6110`-`6117`; patches 0005-0006 |
| `OTTD-R-050` | `src/base_consist.h:17-51` | current-order timing, lateness, timetable/unbunching state, flags and service interval | registry `7160`-`7169`; patches 0005-0006 |
| `OTTD-R-051` | `src/ground_vehicle.hpp:28-77` | ground-vehicle physics caches, flags, compatibility and display-only last speed | registry `7090`-`7099`, `7110`-`7111`; patches 0005-0006 |
| `OTTD-R-052` | `src/vehicle_type.h:42-53` | native `BaseVehicle` type discriminator | registry `7051`; patches 0005-0006 |
| `OTTD-R-053` | `src/town_type.h:110-125` | transported-stat old/new maxima and actual values | registry `12070`-`12073`; patches 0005-0006 |
| `OTTD-R-054` | `src/base_station_base.h:19-20,31-87`; `src/station_base.h:144-561` | complete base-station owner/lifecycle/cache state, `GoodsEntry`, packet ownership, flows and nested share maps | registry `6010`-`6017`, `6030`-`6094`, `6200`-`6232`; patches 0005-0006 |
| `OTTD-R-055` | `src/company_base.h:23-148` | complete infrastructure arrays, independent unit/group generators, history and allocation-controlling company state | registry `4010`-`4023`, `4030`-`4056`, `4070`-`4087`; patches 0005-0006 |

For the frozen PORT-005 registry, every `source_file` value is now represented by
an initial or reached entry above. This closes source-file registration only for
registry v1 at the pinned commit; completeness still depends on the independent
source-owner and continuation review recorded in the PORT-005 matrix. A new field,
source pin, setting scope or reachable subsystem must append a new reached entry.

## Content and licensing sources

| ID | Source | Version | Relevant subject | Governs |
|---|---|---|---|---|
| `CONTENT-001` | [OpenGFX releases](https://www.openttd.org/downloads/opengfx-releases/latest) | OpenGFX 8.0; archive SHA-256 `43a0c1dabf39cb865394f3a6cc36d4da5c10ecfaaf55652043104806810903be` | verified base graphics acquisition and installed profile | OpenGFX manifest, acquisition runner, fixture identity |
| `LICENSE-001` | [SPDX GPL-2.0-only](https://spdx.org/licenses/GPL-2.0-only.html) | SPDX license list entry accessed 2026-07-30 | license identifier and text reference | ADR 0001, license scan, notices |

## Build, representation, and integrity specifications

| ID | Source | Version | Relevant subject | Governs |
|---|---|---|---|---|
| `BUILD-001` | [CMake manual](https://cmake.org/cmake/help/v3.28/) | 3.28 | configuration and build behavior | CMake files and ADR 0002 |
| `BUILD-002` | [CMake Presets manual](https://cmake.org/cmake/help/v3.28/manual/cmake-presets.7.html) | 3.28 | supported preset schema and inheritance | `CMakePresets.json` |
| `BUILD-003` | [CTest manual](https://cmake.org/cmake/help/v3.28/manual/ctest.1.html) and [testing guide](https://cmake.org/cmake/help/v3.28/guide/tutorial/Testing%20and%20CTest.html) | 3.28 | inventory, JUnit, timeouts, no-tests error | test runners and CI |
| `BUILD-004` | [Git submodule documentation](https://git-scm.com/docs/git-submodule) | installed Git documentation | pinned submodule initialization and verification | preflight and worktree runners |
| `DATA-001` | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) | 2020-12 | manifest and registry validation | all JSON schemas/loaders |
| `DATA-002` | [RFC 8785](https://datatracker.ietf.org/doc/html/rfc8785) | RFC 8785 | canonical JSON identity bytes | canonical JSON adapter and manifests |
| `DATA-003` | [NIST FIPS 180-4](https://csrc.nist.gov/pubs/fips/180-4/upd1/final) | FIPS 180-4 | SHA-256 definition | vetted SHA-256 adapter and digest tools |
| `DATA-004` | [ISO C17 committee draft N2176](https://www.open-std.org/jtc1/sc22/wg14/www/docs/n2176.pdf) | N2176 | C17 language contract | all `parity/` native code |
| `DATA-005` | [`SOURCE_DATE_EPOCH`](https://reproducible-builds.org/docs/source-date-epoch/) | specification accessed 2026-07-30 | reproducible timestamp environment | ADR 0002 and build runners |
| `DATA-006` | [SLSA provenance model](https://slsa.dev/provenance/v1) | v1 | evidence statement vocabulary, without level claim | evidence schema and ADR 0006 |

## Analysis and testing sources

| ID | Source | Version or publication | Relevant subject | Governs |
|---|---|---|---|---|
| `TEST-001` | [AddressSanitizer](https://clang.llvm.org/docs/AddressSanitizer.html) | installed/pinned Clang version recorded in toolchain manifest | memory-safety instrumentation | sanitizer CMake and CI |
| `TEST-002` | [UndefinedBehaviorSanitizer](https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html) | installed/pinned Clang version recorded in toolchain manifest | undefined-behavior instrumentation | sanitizer CMake and CI |
| `TEST-003` | [libFuzzer](https://llvm.org/docs/LibFuzzer.html) and [SanitizerCoverage](https://clang.llvm.org/docs/SanitizerCoverage.html) | installed/pinned LLVM version | coverage-guided fuzzing | fuzz targets and campaigns |
| `TEST-004` | [Clang-Tidy](https://clang.llvm.org/extra/clang-tidy/) and [Clang Static Analyzer](https://clang.llvm.org/docs/analyzer/user-docs/) | installed/pinned LLVM version | static analysis | `p0_static.sh` and CI |
| `TEST-005` | [ShellCheck](https://github.com/koalaman/shellcheck) | installed package version recorded in dependency manifest | shell analysis | every P0 Bash script |
| `TEST-006` | William M. McKeeman, [Differential Testing for Software](https://www.cs.tufts.edu/comp/150FP/archive/bill-mckeeman/DifferentailTesting.pdf) | 1998 | independent differential comparison | decoder/comparator test strategy |
| `TEST-007` | Andreas Zeller and Ralf Hildebrandt, [Simplifying and Isolating Failure-Inducing Input](https://doi.org/10.1109/32.988498) | 2002 | delta-debugging/minimization | valid-prefix minimizer strategy |
| `TEST-008` | [SQLite testing strategy](https://sqlite.org/testing.html) and [quality-management plan](https://sqlite.org/qmplan.html) | accessed 2026-07-30 | adversarial, independent, traceable testing | test strategy, evidence, mutation plan |

## Reached-source expansion rule

Before a new OpenTTD behavior is encoded, its call path is traced to all reached
tile procedures, map accessors, pools and allocation helpers, timer classes,
settings, caches, cargo packets, company/accounting code, engine/industry/content
tables, and helper templates. Each reached file receives a stable `OTTD-R-*` entry
with exact-commit URL, relevant symbols or lines, fields governed, tests governed,
and the patch that observes it. A missing reached source is a traceability failure,
not an invitation to infer behavior.
