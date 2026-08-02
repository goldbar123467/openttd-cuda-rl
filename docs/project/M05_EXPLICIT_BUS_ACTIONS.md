# M05 explicit bus actions, masks, and transactions

## Accepted contract

M05 freezes one flat, semantic catalog of 41 actions. The policy head is 164
bytes of little-endian float32 logits and the aligned legality mask is 41 bytes
of `uint8`. Catalog order is semantic rather than derived from engine pool
iteration, so save/load order and entity allocation cannot silently remap a
logit.

| Identity | SHA-256 |
|---|---|
| Action compatibility | `215c7d3ebeea97f1629debee4a2d10301838ccfd3085e4828685591677b58536` |
| Contract file | `33d42081e05abc6e2bb62623a460e3153111e3b253ca90e4b48d39ef9e843d47` |
| Contract schema | `8548f92fdad6ca1e44af1749212d01609739a7f23889e4d9bc7b057662d74803` |
| M05 patch | `c512111713b3c03cd9d0fd6c621c69e1881f3aa837efc0d27e78e3f816a2d006` |
| M05 series | `50d3a06c62bf3fe3535d06260142dcabcd7f5bdf4ad1d842099414b5345904c1` |
| M05 result tree | `ad0575b92f7975ef085e5f35bfe182a504d6cb51` |
| Composed source | `9bb57367151fbf4eedcd802d179c946685a911bec9b99d7573501e0f52a3b2bd` |

The normative machine artifact is
`config/v1/m05-action-contract.json`; its exhaustive schema is
`docs/project/schema/v1-m05-action-contract.schema.json`.

## Catalog

| Indices | Family | Frozen parameters |
|---|---|---|
| 0 | `WAIT` | none; advances exactly 128 ticks |
| 1–2 | `SELECT_TOWNS` | ordered M02 town slots 0/1 |
| 3 | `BUILD_ROAD_CONNECTOR` | deterministic M02 planned connector |
| 4–11 | `BUILD_BUS_STOP` | two planned sites by four orientations |
| 12–15 | `BUILD_ROAD_DEPOT` | planned depot site by four orientations |
| 16 | `BUY_BUS` | depot 0, engine 116 (`MPS Regal Bus`) |
| 17–24 | `ASSIGN_ROUTE` | direct vehicle slots 0–7 |
| 25–32 | `SET_RUNNING` | direct vehicle slots 0–7 |
| 33–40 | `SET_STOPPED` | direct vehicle slots 0–7 |

Town, stop, depot, and road candidates are inherited from the frozen M02
instance rather than rediscovered. Vehicle slots are the direct bounded native
IDs 0 through 7 and are never compacted or reused as aliases during an episode.
The action budget is 512 transitions and 65,536 ticks. Sell-vehicle,
infrastructure removal, and loan control are explicitly `EXCLUDED_V1`; they add
destructive/economic lifecycle branches that are unnecessary for the first
profitable passenger-bus route and remain forbidden without a compatibility
change.

## Boundary and mask rules

`LEGAL_ACTIONS` computes the mask at one M03 boundary and returns an FNV-1a token
over that boundary identity and all 41 bytes. `STEP` requires that exact token,
boundary, action compatibility identity, and bridge compatibility identity.
Changed state is `STALE_REJECTED`; malformed or masked input is
`ILLEGAL_INPUT`; neither advances a tick nor mutates the snapshot.

Cheap structural gates are followed by the normal OpenTTD command test path via
`Command<...>::Do({})`. Production enumeration is bounded to 41 entries and has
no GUI, execution flag, tick loop, RNG call, or async command post. At a paused
boundary the native mask is all zero and non-executable. The shared trainer,
evaluator, ONNX, and in-game adapter resolves an all-zero mask to the safe
catalog `WAIT` index without presenting an illegal sample to the engine.

`scripts/v1/m05_action_adapter.py` owns encode/decode, strict mask validation,
stable legal-only softmax, deterministic greedy tie-breaking, caller-seeded
sampling, and the independent slow oracle. Extreme illegal logits always receive
exactly zero probability.

## Native execution and transactions

The adapter uses normal synchronous OpenTTD commands:

- `CMD_BUILD_LONG_ROAD`, `CMD_BUILD_ROAD_STOP`, and `CMD_BUILD_ROAD_DEPOT`;
- `CMD_BUILD_VEHICLE` with the frozen bus engine;
- `CMD_DELETE_ORDER` and `CMD_INSERT_ORDER` for route replacement; and
- `CMD_START_STOP_VEHICLE` for service state.

Construction, purchase, and lifecycle actions expose command cost, company
balance delta, owner projection, and resulting object state. Commands execute at
the boundary and the scheduler then advances exactly 128 ticks for every
accepted action.

Route replacement is a macro with an explicit transaction. It snapshots the
prior order list, clears it, inserts origin and destination, and on any rejection
restores the old list through normal order commands. The injected
`route-after-first-order` failure proves `NATIVE_REJECTED` with a successful
rollback and no partial route. A rollback command failure escalates to fatal
`INTEGRATION_FAILURE`; it is never disguised as an exploration penalty.

The complete result classes are `SUCCESS`, `NO_OP`, `STALE_REJECTED`,
`ILLEGAL_INPUT`, `NATIVE_REJECTED`, and `INTEGRATION_FAILURE`. Each action log
records boundary/mask identity, selected index/family/parameters, ticks, balance,
cost, outcome, rollback state, and every native subcommand phase/status/error.

## Actual-engine evidence

Two clean campaigns are byte-identical. Across eight frozen templates they
compare every production mask to the independent oracle at 614 fixed and
randomized actual-engine states. Every scripted worker selects endpoints, builds
the connector, two stops and a depot, buys a bus, proves failed and successful
route replacement, starts/stops/restarts service, delivers passengers, and
receives positive revenue.

| Template | Transitions | Waits | Delivered | Income | Final balance |
|---|---:|---:|---:|---:|---:|
| `m02-template-01` | 36 | 21 | 26 | 145 | 93,325 |
| `m02-template-02` | 35 | 20 | 20 | 112 | 93,467 |
| `m02-template-03` | 36 | 21 | 27 | 151 | 93,331 |
| `m02-template-04` | 36 | 21 | 28 | 157 | 93,539 |
| `m02-template-05` | 39 | 24 | 24 | 172 | 93,377 |
| `m02-template-06` | 38 | 23 | 20 | 144 | 93,422 |
| `m02-template-07` | 37 | 22 | 23 | 138 | 93,286 |
| `m02-template-08` | 37 | 22 | 31 | 186 | 93,334 |

The frozen golden fixture is `tests/fixtures/v1/m05-action-goldens.json`. The
complete retained manifest SHA-256 is
`30700cfb8a556ddd7c23eec7463bac7a7f2bf365b9a94742fdeddd982cb2d7b8`;
the asserted executable SHA-256 is
`ed23eeaea1f9deba1333c7ae3be1a8d16f30c203e706ce61b5a5138241f79094`.

## Downstream boundary

M06 may consume this action index, mask, result, and subcommand log contract to
freeze rewards, termination, trajectories, and rollout storage. It may not
change action meaning, tick cost, mask application, or failure classification
without a new compatibility identity and explicit migration/rejection tests.
