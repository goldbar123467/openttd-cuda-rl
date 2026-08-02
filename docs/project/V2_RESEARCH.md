# Version 2 OpenTTD feature and competitor research

## Status and boundary

- Status: active V2 research baseline
- Research snapshot: 2026-08-02
- V1 baseline: released `v1.0.0`; all V1 gates remain mandatory regressions
- Engine baseline for the first V2 implementation: OpenTTD 15.3, commit
  `14ec60f248547d4d062a1160f0fc26d742319888`
- Machine companion: [`config/v2/research-baseline.json`](../../config/v2/research-baseline.json)
- Validator: [`scripts/v2/validate_research_baseline.py`](../../scripts/v2/validate_research_baseline.py)
- Delivery plan: [`V2_PLAN.md`](V2_PLAN.md)

This document expands the completed passenger-bus V1 into a broad OpenTTD
generalist and competition benchmark. “Every feature” means every base-game
gameplay system that can affect company decisions or outcomes is either a required
policy capability, a deterministic benchmark control, or an explicitly tested
compatibility surface. It does not mean that the neural policy must operate menus,
audio, social integrations, arbitrary future community content, or pixels. Those
application surfaces are dispositioned, not silently treated as gameplay.

The pinned 15.3 source and actual-engine execution remain semantic authority.
Online material identifies scope and candidate opponents; it cannot overrule the
pinned implementation.

## Research method and completeness rule

The baseline was assembled from four layers:

1. the 145 executable commands in OpenTTD 15.3's `src/command_type.h`;
2. the OpenTTD AI API surface under `src/script/api/` and its generated class
   index;
3. the official manual's gameplay taxonomy; and
4. the live BaNaNaS AI catalog plus primary package/repository metadata.

The machine baseline assigns every 15.3 engine command to exactly one of
`policy-required`, `policy-optional`, or `benchmark-admin`. The validator extracts
the enum from the pinned Git object and rejects an unknown, duplicated, or omitted
command. `CMD_END` is validated separately as the sentinel. This is stronger than
a prose claim that the major transport modes were remembered.

Completeness is still not implementation. A researched or planned row cannot pass
a V2 gate until its native positive, negative, save/load, deterministic replay,
resource, and regression evidence exists where applicable.

## Map sizes, landscapes, and scenario generation

The official map-size documentation states that native map dimensions are powers
of two from 64 through 4096 tiles per side, including rectangular combinations.
V1's 32 by 32 map is therefore a deliberate source-integrated compatibility
environment rather than a normal map-generation choice.

V2 uses five scale tiers:

| Tier | Dimensions | Purpose |
|---|---|---|
| V1 compatibility | 32×32 | byte- and behavior-compatible V1 regression |
| curriculum | 64², 128², 256², 512² | learning progression and matched ablations |
| generalization | rectangular pairs and 1024² | unseen shapes, more towns, longer horizons |
| resource boundary | 2048² and 4096² | reset, observation, bounded-memory, and clear-failure smoke; not a claim that every map is cheap to train |
| exhaustive dimension contract | every side in {64, 128, 256, 512, 1024, 2048, 4096} | schema/feasibility disposition for all 49 native rectangles |

The scenario matrix must also cover random generation, heightmaps, saved scenarios,
flat and mountainous terrain, water/river density, freeform edges, all four
climates, town and industry densities, start dates, vehicle availability, economy
settings, breakdowns, disasters, and cargo distribution settings. Full Cartesian
execution is neither meaningful nor affordable; pairwise interaction coverage and
named adversarial combinations are preregistered, while every setting receives an
explicit supported/controlled/compatibility-only disposition.

Primary online references:

- [OpenTTD map-size limits](https://wiki.openttd.org/en/Archive/Manual/Settings/Map%20size)
- [new-game generation controls](https://wiki.openttd.org/en/Manual/New%20game)
- [heightmap behavior](https://wiki.openttd.org/en/Manual/Heightmap)

## Complete gameplay feature inventory

### Shared construction and landscape

Required capabilities include clearing, raising, lowering and leveling land;
foundations and slopes; trees; company-buildable objects; rail/road bridges;
tunnels; canals, locks and aqueducts; demolition and reconstruction; construction
costs; ownership; town-authority restrictions; and transactions whose later
subcommand can fail. Bridge/tunnel endpoints, slopes, crossings, occupancy, height,
length, availability date, transport type and cost are observable and maskable.

### Towns and local authority

The policy observes population, growth, transported percentages, cargo goals,
station catchment, authority rating and permissions. It can select town services,
advertising/funding/bribery actions where enabled, and can plan passenger, mail,
food, water and goods delivery effects. Founding towns is a conditional capability
when the game setting allows it; scenario-only town expansion/deletion/rating
commands remain benchmark controls.

### Economy and company management

V2 includes starting capital, loans and interest, inflation, running and
infrastructure costs, construction expenses, vehicle profit, company value,
bankruptcy, engine previews, subsidies, exclusive rights, company purchase,
competitor payments where permitted, maintenance, autoreplace and renewal. League
score is reported but cannot replace economic and service metrics.

### Cargo, industries, and production chains

The base game has four climate-specific cargo/industry graphs. V2 covers every
base cargo label available in each climate, including passengers and mail, primary
production, secondary/tertiary processing, industry acceptance/production,
station catchment, ratings, waiting cargo, transfers, cargo distribution,
refitting, subsidies, industry closure/change, and multi-leg/multimodal chains.
NewGRF cargo labels are handled by identity and capability discovery rather than
hard-coded V1 indices.

Primary online references:

- [cargo and all four base-climate flow tables](https://wiki.openttd.org/en/Manual/Cargo)
- [industry behavior and funding](https://wiki.openttd.org/en/Manual/Industries)
- [subsidy behavior](https://wiki.openttd.org/en/Manual/Subsidy)

### Road vehicles and tramways

V1 bus behavior remains supported. V2 adds mail vehicles, cargo trucks, drive-through
and terminal stops, road waypoints, all compatible road types, refits, articulated
vehicles, crossings, congestion, route sharing, replacement and tram discovery.
Trams are compatibility-gated because they require a vehicle NewGRF; absence of a
tram type must be handled without invalid actions.

Primary online references:

- [road vehicles](https://wiki.openttd.org/en/Manual/Road%20vehicles)
- [tram availability and NewGRF dependency](https://wiki.openttd.org/en/Manual/Tramways)

### Rail

Rail scope includes steam, diesel, electric, monorail and maglev availability;
track types and conversion; engines, wagons, consists and multiheaded vehicles;
stations of variable shape and platform count; depots; rail and road waypoints;
junctions; bridges; tunnels; crossings; path, block and legacy pre-signal types;
one-way/two-way behavior; reservations; train reversal/force-proceed; refitting;
shared orders; timetables; servicing; replacement; collisions; and throughput.

Primary online references:

- [trains and rail types](https://wiki.openttd.org/en/Manual/Trains)
- [signals and reservations](https://wiki.openttd.org/en/Manual/Signals)
- [waypoints](https://wiki.openttd.org/en/Manual/Waypoints)

### Ships and waterways

Ship scope includes natural water, rivers, coast, canals, locks, aqueducts, docks,
ship depots, buoys, oil rigs, passenger and freight ships, refits, transfers,
service orders, water-region/path selection, replacement and unprofitable-route
retirement. The action oracle must test turning space, dock approach, slope/height
rules, navigability and route continuity.

Primary online references:

- [waterway construction](https://wiki.openttd.org/en/Manual/Waterway%20construction)
- [canals, locks and aqueducts](https://wiki.openttd.org/en/Manual/Building%20canals)
- [ship purchase, refit and orders](https://wiki.openttd.org/en/Manual/Buying%20ships)

### Aircraft

Aircraft scope includes airplanes and helicopters; small, commuter, city,
metropolitan, international and intercontinental airports; heliports, helidepots
and helistations; hangars; airport availability dates; catchment; airport noise and
town constraints; aircraft range; terminal/runway occupancy; airport open/close;
servicing; replacement; refits; breakdowns; crashes and disaster interaction.

Primary online reference:

- [airport types, footprints, dates, capacities, noise and crash behavior](https://wiki.openttd.org/en/Manual/Airports)

### Orders, schedules, and multimodal networks

Every vehicle type shares a versioned order model: insert, delete, move and skip;
station, depot, waypoint/buoy and nearest-depot destinations; full/no load;
unload, transfer and no-unload; non-stop/via; conditional jumps; order refit;
copy/share/unshare; service/stop-in-depot; timetable dwell/travel/speed limits;
autofill, start dates and lateness correction. Multimodal tests join station
facilities and move cargo through transfer hubs without paying at intermediate
stations.

Primary online references:

- [complete order options](https://wiki.openttd.org/en/Manual/Orders)
- [timetables and automatic spacing](https://wiki.openttd.org/en/Manual/Timetable)

### Vehicle and network lifecycle

All modes cover build, assemble/clone, start/stop, group, order, refit, service,
reliability, age, breakdown, lost state, profit, depot visit, renewal, autoreplace,
upgrade, sell, crash, cleanup, and identifier reuse. Observations distinguish
owned, competitor, neutral/town and unavailable infrastructure. Network planning
must reason over capacity, congestion, waiting cargo, transfers and failures, not
only local construction legality.

### Climates, time, events, and content

Temperate, sub-arctic, sub-tropical and Toyland are mandatory base-game suites.
Snow/desert effects, water/food town goals, vehicle/airport introduction and
expiry, recession, inflation, industry change, engine preview, disasters,
subsidies and company events receive deterministic seeds and event logs.

NewGRF and Game Script support is layered:

1. base content with no mods is the release correctness authority;
2. a pinned compatibility pack exercises added rail/road types, tram vehicles,
   cargo labels, engines, stations/airports/objects and an industry replacement;
3. unknown content fails closed or uses capability discovery—never V1 numeric
   assumptions; and
4. arbitrary community content is not claimed supported merely because it loads.

Game Scripts may configure goals, story pages, league tables, questions, towns,
industries and subsidies. These are observed and benchmarked; deity commands are
never exposed as normal-company actions.

### Multiplayer and competitive companies

V2's first competitive path is multiple companies in one authoritative OpenTTD
simulation: one RL company plus controlled NoAI opponents. This avoids conflating
economic competition with network transport, while exercising shared map state,
town ratings, cargo capture, subsidies, collisions, company failure and purchase.
A later network-process campaign checks multiplayer synchronization and
reconnection separately. Opponent actions are not leaked as privileged policy
inputs.

OpenTTD's manual documents up to 15 companies and the AI settings allow a specific
AI per company slot. Console operations can list, start, reload and stop AIs.

Primary online references:

- [AI selection, per-instance settings and console controls](https://wiki.openttd.org/en/Manual/AI%20settings)
- [multiplayer companies and synchronization](https://wiki.openttd.org/en/Manual/Multiplayer)
- [AI API class hierarchy](https://docs.openttd.org/ai-api/hierarchy)

## External-AI research and tournament pool

The live [BaNaNaS AI catalog](https://bananas.openttd.org/package/ai) is the
discovery authority, but a tournament uses downloaded bytes pinned by full digest,
package version, API version, dependency closure, settings and license. “Latest”
is never a reproducible identity.

The first audit pool deliberately mixes active generalists, mode specialists,
classic baselines and a no-op control:

| AI | Frozen research version | Role and advertised support | License at snapshot |
|---|---:|---|---|
| AAAHogEx | 115 | strong generalist; rail, road/tram, ships, aircraft | GPL v3 |
| LuDiAI AfterFix | v27 | passenger/mail generalist over rail, road, water and air | GPL v2 |
| Trans AI | 200626 | broad transporter; bus, truck, tram, ship, airplane, helicopter and current rail work | GPL v2 |
| ChooChoo | 434 | rail specialist and network-shape stressor | CC-BY-SA 3.0 |
| Lufthansa | 2 | long-distance aircraft specialist | GPL v2 |
| ShipAI | 10 | ship specialist including canals, locks and aqueducts | GPL v2 |
| KrakenAI2 | 3 | truck specialist | GPL v3 |
| SimpleAI | 14 | classic rail/road/air all-cargo baseline | GPL v2 |
| WmDOT | 16 | MinchinWeb road-network builder with ship revenue | custom; redistribution review required |
| NoOpAI | 4 | installed-AI/no-action control | CC0 1.0 |

Package descriptions are claims to test, not accepted performance facts. Each
opponent must pass installation, API/dependency resolution, start, deterministic
configuration recording, bounded execution, save/load and metrics extraction
before it enters rankings. Failures and bankruptcy remain valid measured results.

### “Minimax 2 / Minimax 3” name resolution

No package with an exact `Minimax`, `Minimax 2`, or `Minimax 3` name was found in
the current BaNaNaS catalog, its historical AI comparison, or direct web searches.
Two plausible confusions were found:

- **KrakenAI2 version 3**, a current truck AI; and
- **MinchinWeb**, the author of WmDOT, whose name resembles “Minimax” but is not an
  AI of that name.

V2 records both candidates and does not claim either is the user's intended AI.
If exact package bytes or a link surface later, they enter the same provenance and
sandbox audit without changing tournament rules.

## Competition design

Tournament comparisons are paired, seeded and symmetric:

- identical map/scenario bytes, start date, settings, content and horizon;
- randomized or mirrored company slots and start delays;
- isolated solo runs distinguish competence from interference effects;
- head-to-head, one-versus-many and mixed-specialist fields;
- at least three map scales and all four climates after mode qualification;
- economic, service, network, robustness, resource and rule-violation metrics;
- bootstrap confidence intervals and paired seed differences;
- timeout, crash, bankruptcy, unavailable dependency and incompatibility are
  explicit outcomes, never silently dropped; and
- final opponents, settings, seeds, scenarios and scoring are preregistered before
  the selected V2 policy sees final results.

Primary ranking uses a declared composite only after reporting its components:
survival, operating profit, delivered cargo by type, cargo-chain completion,
company value, service coverage, vehicle profitability, infrastructure efficiency,
subsidies captured and invalid actions. League-table score is secondary because a
community AI may optimize a different objective.

The experiment-manifest principles overlap with
[OpenTTDLab](https://pypi.org/project/OpenTTDLab/), a published framework for
repeatable OpenTTD AI experiments. V2 uses it as a research/design reference, not
as the production runtime: its published compatibility notes do not cover OpenTTD
15.3, and this repository's source-integrated C++ boundary remains authoritative.

## Architecture consequences

The V1 fixed 32×32 CNN and flat 41-action catalog cannot simply be enlarged.
V2 requires:

- size-independent global, regional and local spatial views;
- typed entity tables and transport/cargo graphs with explicit masks;
- hierarchical action heads (intent → object/region → parameters) with stable
  semantic IDs;
- variable-length attention or graph processing plus bounded candidate sets;
- recurrent or memory-capable planning over longer horizons;
- self/competitor/neutral ownership channels without hidden information;
- per-mode specialists behind a shared generalist router, with a monolithic
  baseline for comparison;
- curriculum state in checkpoints and exact recovery boundaries; and
- compatibility adapters that keep every released V1 package runnable and
  evaluable.

PPO remains the required trusted algorithm until the V2 PPO generalist is correct.
Self-play, population training or a second learning algorithm may be studied only
after the external-opponent benchmark and broad PPO baseline pass; breadth is not
an excuse to abandon V1's equivalence and evidence standards.

## Research limitations and next evidence

This snapshot proves scope disposition and source/catalog coverage, not V2 gameplay
support. The immediate evidence sequence is:

1. freeze the V2 requirements, source decision and feature/command inventory;
2. qualify actual downloaded opponent packages on the pinned engine;
3. implement scalable observation and hierarchical action contracts while keeping
   the V1 environment byte-compatible;
4. expand modes in dependency order with native legality/reward oracles; and
5. run the preregistered competition only after solo multimodal competence passes.

The ordered gates and definition of done are in [`V2_PLAN.md`](V2_PLAN.md).
