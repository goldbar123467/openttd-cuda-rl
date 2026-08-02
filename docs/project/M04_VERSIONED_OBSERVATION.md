# M04 versioned observation and preprocessing contract

## Result and claim boundary

M04 passes. OpenTTD 15.3 now exposes one source-integrated C++ policy encoder
at the accepted M03 boundary. Its native output is a 256-element structured
float32 vector and a 32-channel by 32 by 32 spatial float32 tensor. The same
`RlObservation` object and `EncodeRlObservation` entrypoint are the required
inputs for trainer, evaluator, ONNX Runtime, in-game controller, and bridge
oracle adapters.

M04 does not define M05 policy actions or masks, M06 rewards/trajectories, PPO,
model architectures, CUDA training, final evaluation, export, or neural
playback. Route-path prediction, action context, reward history, and complete
command legality remain deliberately downstream.

## Frozen machine authority

The exhaustive authority is
[`m04-observation-contract.json`](../../config/v1/m04-observation-contract.json),
validated against
[`v1-m04-observation-contract.schema.json`](schema/v1-m04-observation-contract.schema.json).

| Artifact | SHA-256 or identity |
| --- | --- |
| Observation compatibility | `7f8a46af1fe2a2c23e755c71b3bc2d04c9a0d057c573e901e5c9ed9178ca13eb` |
| Contract file | `6139634cf1ae8a1b0d639596e400a12b6b6f56fe3e9a3a1ee5d92d731013877e` |
| Contract schema | `0cafc71df2c8af62f93e0e52df8493b07873ad0bc598fbd5207015dc5836ee92` |
| Golden fixture | `1dce190b8e7216b03c5e45cc6ee0af050bf69aa773aecc051250a4288ccf3ec6` |
| Oracle report schema | `1e194350eeedfa0142b7bb21c4fad3ba2874aba9924f7f4c0f11e77aa8f35c93` |
| M04 patch | `fd63122a88dc86ddd8caacb6be3ddce0445ab889701b779e60d264aa736ebea4` |
| M04 series | `b676ddaaf9cfe3fa1610a25941fac136c91e5c50445f604d0bc2637ada809670` |
| M04 result tree | `fe815570b5c816c6b324a9bf63d965157ea425c6` |
| M04 composed source | `820cf3ee0fb36734c318cb260e6cc4567a2a9acc55c831d5b36d1875341b291e` |

The contract contains one row for every structured field and spatial channel.
Each row fixes its index, name, authoritative OpenTTD source, raw type, unit,
transform, clip, output bounds, missing rule, and update boundary. Its candidate
registry also records every included, excluded, and deferred source family with
a requirement-linked rationale.

## Structured layout

| Indices | Group | Shape and identity rule |
| --- | --- | --- |
| 0–27 | Global | company, counts, ownership, time/budgets, overflow, map summary |
| 28–47 | Towns | 2 direct `TownID` slots × 10 fields |
| 48–127 | Vehicles | 8 direct primary road `VehicleID` slots × 10 fields |
| 128–207 | Stations | 16 direct company bus `StationID` slots × 5 fields |
| 208–255 | Routes | 8 vehicle-owned route slots × 6 fields |

Slot position is the engine pool ID. Deletion clears presence and all other
values at the next boundary. Reuse deliberately replaces the prior entity in
the same slot. IDs beyond a fixed maximum are omitted and set an explicit
overflow feature; entities are never silently reordered or truncated without a
signal.

All normalization constants are reviewed fixed constants. No statistic is fit
from training, development, or evaluation data. Evaluation and playback
therefore have nothing mutable to update. Signed financial/profit fields use
signed clipping; missing slots are zero with an explicit local presence mask;
town rating has its own availability mask.

## Spatial layout

Logical order is `[channel, y, x]`, with flat index
`channel*1024 + TileY(tile)*32 + TileX(tile)`. `TileXY(0,0)` is the map-array
origin; increasing X and Y follow OpenTTD's southeast and southwest map axes.

| Channels | Semantics |
| --- | --- |
| 0–3 | valid, void, terrain height, clear ground |
| 4–9 | any road, company road, NE/SE/SW/NW road-edge bits |
| 10–15 | building, two town-attribution planes, town center, population, passenger-generation potential |
| 16–20 | bus stop plus NE/SE/SW/NW facing one-hot planes |
| 21–25 | road depot plus NE/SE/SW/NW facing one-hot planes |
| 26–31 | route endpoints, vehicle presence, static buildable, static blocked, company infrastructure, station catchment |

Static road buildability means exactly flat `MP_CLEAR` geometry. It is a causal,
cheap observation feature, not a promise of complete command legality. M05 must
combine it with funds, authority, ownership, vehicle, parameter, and normal
OpenTTD command checks when generating masks.

Water is explicitly excluded: the frozen M02 scenario forbids interior water,
the V1 bus policy cannot act on it, and an all-zero plane would have no positive
semantic fixture. Future compatibility versions may add it only with scenario,
schema, and positive-fixture changes.

## Boundary and shared implementation

M04 extends the M03 pipe protocol with `OBSERVE` message type 8 while preserving
M03 types 1 through 7. It is valid only in `AT_BOUNDARY` and `PAUSED`. The bridge
requires the observation compatibility identity before encoding and rejects a
mismatch before tensor use.

The production transform exists once in `src/rl_observation.cpp` and returns the
native `RlObservation` declared by `src/rl_observation.h`. Extraction calls no
`StateGameLoop`, command, RNG API, pathfinder, or catchment recomputation. It
reads the engine's existing catchment bitmap and performs an internal tick/RNG/
pool snapshot equality guard around every bridge call. The optional raw source
projection is oracle-only and policy adapters reject it.

Canonical cross-consumer bytes are little-endian IEEE-754 binary32, structured
then spatial. The common adapter validates schema/compatibility/shape/bounds and
does no second normalization. Trainer, evaluator, ONNX Runtime, and in-game
consumer labels all produce the same golden tensor SHA-256 for each fixture.

## Actual-engine acceptance

Two complete campaigns are retained outside Git:

```text
/home/thecl/.codex/artifacts/openttd-rl/m04-observation-oracle-20260801-a
/home/thecl/.codex/artifacts/openttd-rl/m04-observation-oracle-20260801-b
```

The roots are byte-identical. Their common `manifest.json` SHA-256 is
`a80aa42cbbb3b38e473e48023f04cda4aad5a1a84e8b059619c3d92155ff3485`;
their common `goldens.json` SHA-256 is
`1dce190b8e7216b03c5e45cc6ee0af050bf69aa773aecc051250a4288ccf3ec6`.

Every campaign runs observed and no-observation control workers for all eight
M02 templates. It compares 256 structured values and 32,768 spatial values per
template against an independent transform of the raw OpenTTD source projection:
264,192 comparisons total. Repeated reset and built-route encodings are byte
identical; observed/control post-step snapshots match; wrong compatibility
identities fail without mutation; all 32 channels have a positive fixture
across the orientation-pattern corpus.

## Next allowed work

Preserve the compatibility and source identities above. M05 may now freeze the
explicit passenger-bus action representation and legal mask against this exact
observation boundary. Do not reinterpret static buildability as the M05 legal
mask or add reward/history fields without a reviewed compatibility revision.
