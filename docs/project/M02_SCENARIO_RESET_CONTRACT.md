# M02 passenger-bus scenario and reset contract

## Status and compatibility identity

The contract-first portion of `M02` is frozen at semantic version `1.0.0`.
Its machine-readable source is
[`config/v1/m02-scenario-contract.json`](../../config/v1/m02-scenario-contract.json),
validated by
[`v1-m02-scenario-contract.schema.json`](schema/v1-m02-scenario-contract.schema.json).
The compatibility identity is
`45ec1b3beb4d6d50696bf1de75094e1817c6aa7ef8e0d38fc6696999764e5b0f`.

Scenario generation, the native reset oracle, and the non-learning scripted bus
trajectory are implemented and verified. `G02` passes; the accepted closure
evidence is recorded in [`G02_GATE_REPORT.md`](G02_GATE_REPORT.md).

## Frozen scenario

Each scenario is a 32 by 32 temperate, flat, fixed-template map with the required
one-tile void border and no interior water. There are exactly two towns. Each has
population 250 through 800, a passenger-generating building within the proposed
stop catchment, and a usable road path to the other town. The corpus contains
eight templates: four training, two development, and two final evaluation.
Procedural generation and implicit seed retries are not part of compatibility
version 1.

The game begins on 1950-01-01. The sole permitted vehicle is the default-content
MPS Regal Bus: base engine ID 116, original road-vehicle index 0, capacity 31.
It is already available in 1950. Engine expiration is disabled so availability
cannot change during the episode; native vehicle aging remains enabled and
breakdowns are disabled.

There is exactly one learning company, company ID 0, and no competitor. OpenTTD
creates it with 100,000 internal money units and a matching 100,000 loan. The
maximum loan is 300,000 in 10,000-unit increments. Infinite money is forbidden.
Inflation, recessions, subsidies, disasters, town growth, AIs, GameScript,
NewGRFs, networking, and multiplayer are disabled.

Only roads, bus stops, road-vehicle depots, buses, and passenger service are
agent-reachable. Rail, trams, trucks, mail/freight/industry service, ships,
docks, aircraft, and airports are forbidden. A reset begins with no owned
vehicle, station, depot, or road infrastructure; fixed town buildings and roads
may already exist.

## Economy and horizon

The economy uses OpenTTD's smooth mode with low construction and vehicle-running
costs, 2% interest, bitcount town cargo generation at 100%, manual passenger
distribution, gradual loading, modified catchment, and right-hand road traffic.
All behavior-affecting overrides selected for this scope are enumerated in the
machine contract rather than inherited silently from a user configuration.

An episode is bounded by 65,536 simulation ticks and 512 agent actions, with
bankruptcy terminal. At 74 economy ticks per day, the tick bound spans at most
886 economy days. The later M03 step contract must choose the exact action-to-tick
advance policy without changing these outer bounds; action exhaustion takes
precedence over tick exhaustion when both are observed at the same boundary.

## Seed and rejection policy

Scenario seeds are unsigned 32-bit integers recorded in
[`m02-seed-ledger.json`](../../config/v1/m02-seed-ledger.json). The eight fixed
blueprints are recorded in
[`m02-scenario-corpus.json`](../../config/v1/m02-scenario-corpus.json). Their
identities are respectively
`fcfdb820abb6db783df412d6496f68ce41bfd3def630ced637fe1d00dbbcd8ed` and
`07898d94a56fd080c9cea57dbdf90384e1f0f269e360fb35423de16bc89d2e14`.
Training, development, and final-evaluation sets are pairwise disjoint; final
entries are marked unavailable to trainer code and require explicit evaluation
authority at generation time. Invalid layouts produce a named predicate
rejection and fail the requested scenario. Host time, global retry order, and
unrecorded retry-until-valid loops are forbidden.

The offline entry point is `scripts/v1/generate_m02_scenario.py`. It accepts one
known template ID or seed, requires the caller to declare the matching split,
validates every blueprint and identity before selection, and refuses to overwrite
its output. Scenario identity covers the contract, corpus, seed ledger, selected
template/seed, engine profile, content, and scenario-instance schema. Two
executions with unchanged inputs produce byte-identical UTF-8 JSON.

## Reset oracle

Clean-process reset is the correctness oracle. Same-process reset may be enabled
only after it reproduces the oracle. Comparisons use byte-identical canonical
UTF-8 JSON and SHA-256 over the semantic projection.

The projection includes compatibility and scenario identities, content,
settings, map/tile state, all engine RNG streams, time/date/tick counters,
economy, company finance, towns and passenger state, vehicles, stations, depots,
orders, roads, and relevant pool state. Absolute paths, process IDs, durations,
wall clock, and OpenTTD's unique save-session ID are diagnostic only and cannot
enter the semantic digest.

The native implementation is the ordered `0003` delta in
[`integration/openttd/patches/15.3/m02/scenario`](../../integration/openttd/patches/15.3/m02/scenario).
It applies after, and does not modify, the accepted feasibility tree
`eba8f4bd3c37042c184d968d2f038864184e3132`. The resulting tree is
`551a99fbd33bd1b0f8c9ec35561deb0e893b81fe`; its composed source identity is
`edc76541bfda23c2916fc85d499e6e0d5a5cefaad09f40bf19972c2d3307385e`.

With `OPTION_RL_ENVIRONMENT=ON`, the executable accepts four gated options:

- `-Z <instance>` selects a canonical generated scenario instance.
- `-Y <report>` selects a new reset-report path and refuses overwrite.
- `-R <1..16>` repeats reset and projection in the same process.
- `-T <trajectory-report>` executes the bounded non-learning bus trajectory and
  writes its canonical report to a new path.

The runner materializes the native empty 32 by 32 map, fixed roads, two native
towns, and company 0. It then validates map borders and height, population and
passenger catchment, route connectivity, the proposed depot site, all frozen
settings and content exclusions, every relevant pool, raw tile planes, both RNG
streams, time, finance, and forbidden transport state. The report is compact
sorted-key UTF-8 JSON with one terminal LF.

The Ubuntu `openttd-opengfx` package supplies version 7.1 and is therefore not a
valid M02 content input. The reset runner stages the independently frozen
`opengfx-8.0.tar` (`SHA-256 9389bcb0...6043c`) into an isolated local-only
runtime. OpenGFX 8.0's internal metadata version is `9499`; native execution
checks that exact value as well as the `OpenGFX` name.

## Automated reset verification

Run the complete oracle against the current Ubuntu build and its isolated
runtime sysroot:

```bash
python3 scripts/v1/run_m02_reset_oracle.py \
  --root "$PWD" \
  --executable /path/to/current-ubuntu-build/openttd \
  --opengfx-tar /path/to/offline-cache/opengfx-8.0.tar \
  --sysroot /path/to/current-ubuntu-sysroot \
  --artifact-root /new/absolute/artifact-root \
  --allow-final-evaluation
```

The command performs two independent clean processes and one two-reset process
for each of all eight templates. Every process also executes the scripted bus
trajectory. It requires byte-identical clean reports and trajectories,
byte-identical clean/same-process semantic projections and trajectories, the
pinned projection and trajectory digest for every template, empty stderr,
canonical human output, and no warning, assertion, sanitizer, error, failure,
fatal, or crash diagnostic. It also emits deterministic `commands.json` and
`manifest.json` files without host paths or timings.

The current Ubuntu validation produced these frozen projection identities:

| Template | Projection SHA-256 |
| --- | --- |
| `m02-template-01` | `2845e3f3d1a1b9eb240c86fb2a60390b7d867bcced5e063790958ff0b9c001c5` |
| `m02-template-02` | `7388f46079ab4086db3620c167c95e4b87286f728d12e1af89e68e2e8839a71e` |
| `m02-template-03` | `d79e3e55f196ddfb74ed0e1773e3c701f9d84af4becd9ad64267e93398c4d12b` |
| `m02-template-04` | `ad77c66de648404d6867d193ba49c28b62b8795b915fb49e7a322d120d096c31` |
| `m02-template-05` | `22dacec91244d6c7b4bf5fa3e9bf60c6dd1acfc206f77de799803d4cab92c0ba` |
| `m02-template-06` | `d3c801cba4ec3001275c583b3c74f4c166da789e89b79566444e9e653f8f532c` |
| `m02-template-07` | `c1b67455fcc5946cd9969ec8ab14f17a46abf7b750e3a8cc78e7079abea605e9` |
| `m02-template-08` | `6d48d9a54194a50cd57a2532621820bf24a4a7a80c348c91a9ebe6f7a73db531` |

Two complete runner executions produced byte-identical native reports,
trajectory reports, scenario instances, runtime inputs, `commands.json`, and
`manifest.json`. The repeated manifest SHA-256 is
`8baeea1e49b04936f3403fec338392aa0ade7c8b1171a6e8fb15ce758ba869ca`;
the repeated command-record SHA-256 is
`fff7e54f5ccd93fcec72698ceffc4c22a1b047356439ffd41633de2c0e9ef5f5`.
The retained roots and every trajectory digest are listed in the G02 gate
report.

## Scripted passenger-bus trajectory

The `-T` path is deliberately not an RL bridge. After a successful controlled
reset it invokes normal native OpenTTD commands to build two bus stops, connect
and build one road depot, purchase engine 116 (the 31-seat MPS Regal Bus), add
the two station orders, and start service. It then advances the ordinary game
loop until passenger delivery and positive income are both observed, failing if
the 65,536-tick outer bound is reached first.

`scripts/v1/validate_m02_scripted_trajectory.py` checks canonical encoding,
scenario identity, exact action ordering and finance arithmetic, vehicle and
facility inventories, the two-stop order list, tick bounds, positive delivery
and income, and zero forbidden transport/industry state. All eight templates
pass. Their observed completion interval is 2,720 through 3,249 ticks, passenger
delivery is 9 through 31 units, and income is 64 through 190 internal money
units.

## Manual QA

Manual QA should inspect evidence rather than changing or playing through the
fixed reset by hand:

1. Verify the OpenGFX archive with `sha256sum` and require the exact digest above.
2. Run the complete oracle command in a new artifact directory and require eight
   template PASS lines followed by `M02_RESET_ORACLE=PASS templates=8`.
3. Open one `instances/m02-template-XX.json` and the matching
   `runs/m02-template-XX/clean-1/report.json` and `trajectory.json`; confirm the
   template, seed, town coordinates, route, stop, depot, content, and settings
   agree.
4. Confirm `vehicles`, `stations`, `depots`, and `orders` are empty; forbidden
   pool values and owned infrastructure are zero; the map contains 1,024 raw
   tile records with a 124-tile void border.
5. Run `validate_m02_reset_projection.py` on the chosen instance/report pair and
   `validate_m02_scripted_trajectory.py` on the instance/trajectory pair.
6. Run the oracle again in another new directory and compare every report plus
   `commands.json` and `manifest.json` byte for byte.
7. Confirm the trajectory has one running passenger bus, two stations, one
   depot, the exact two-stop orders, positive delivery/income, and no forbidden
   transport or industry state.
8. Run `test_v1_m02_reset_oracle.py`; its mutations introduce rail, tram,
   aircraft, water, stations, depots, vehicles, orders, industries, NewGRFs,
   GameScript, networking, encoding defects, and other scope drift and require
   explicit rejection.

## Validation

Validate the frozen artifact directly with:

```bash
python3 scripts/v1/validate_m02_scenario_contract.py \
  --contract config/v1/m02-scenario-contract.json \
  --schema docs/project/schema/v1-m02-scenario-contract.schema.json
```

Repository tests mutate every decision family, compatibility identity, split
accounting, horizon arithmetic, JSON strictness, reset coverage, forbidden
transport state, and passenger-bus scope. They also apply the native delta
exactly and cross-check the frozen year, tick, loan, and MPS Regal data against
the pinned OpenTTD source.

## Next allowed work

Stop at the passed G02 boundary. M03 may next define and implement the
synchronized source-integrated headless environment bridge. Do not begin PPO,
production ONNX, or in-game neural control, and do not treat this non-learning
trajectory as an RL action API.
