# M06 reward, episode, trajectory, and rollout foundation

## Status

M06 and G06 are `PASS`. This document remains the frozen design record; native
transition projection, the bounded trajectory writer, exploit campaigns, and
repeated actual-engine differential evidence are recorded in
`docs/project/G06_GATE_REPORT.md`.

The normative foundation is
`config/v1/m06-reward-trajectory-contract.json`.

| Identity | SHA-256 |
|---|---|
| Foundation compatibility | `9d8f9c2fc6074d899fa3b0047c55e3fb15cc5c17cddeaceaa1fd5389e53c8c9e` |
| Contract file | `28712c2b7fcf009e3ceda0ebbc2f18d382f28f780adb52186a08ab871998a2e7` |
| Contract schema | `fa6a776fb45649589058f1ea726a6f82b5c3afbb4144edac337383fe6152c2ad` |
| Accepted M05 source input | `9bb57367151fbf4eedcd802d179c946685a911bec9b99d7573501e0f52a3b2bd` |

## Boundary audit

Reward transition `t` is defined only over the synchronized interval
`S_t -> action -> 128 complete StateGameLoop calls -> S_t+1`. Observation and
mask belong to `S_t`; raw reward and termination belong to `S_t+1`; a transition
is committed only after both are finite and internally consistent.

OpenTTD's `Company::cur_economy` income, expenses, and delivered-cargo counters
rotate into `old_economy` every quarter. Subtracting two visible current-quarter
values would therefore create a false negative delta at rollover. M06 instead
sums the current entry and every valid retained history entry at both boundaries,
then differences those lifetime-within-episode totals. The 65,536-tick episode is
shorter than the 24-quarter history window, so no retained entry can age out.

Malformed or masked `ILLEGAL_INPUT` remains the M05 fail-closed non-transition
correctness defect. It is logged and stops the invalid controller path; it is not
laundered into an ordinary shaped reward transition.

## Candidate dispositions

| Candidate | Disposition | Reason |
|---|---|---|
| Operating profit | Included | direct realized income plus operating expenses |
| Passenger delivery | Included | required useful causal event |
| Transported-passenger growth | Diagnostic | quarterly lag and delivery double-count |
| Station-rating improvement | Rejected | farmable proxy |
| Route profitability | Diagnostic | duplicates single-route company economics |
| Utilization | Diagnostic | movement/loading alone is not useful |
| Productive expansion | Rejected | construction is not value until service works |
| Long-term company value | Diagnostic | mixes assets and operating outcome |
| Bankruptcy | Included | terminal game loss |
| Invalid action | Diagnostic/fail closed | controller correctness defect, not transition |
| Repeated construction/native failure | Included | consumes a decision interval without value |
| Idle vehicle | Included | stopped purchased capacity |
| Unused station | Diagnostic | redundant with capital/idle costs in V1 |
| Excessive infrastructure spend | Included | separately bounded capital cost |
| Valueless route duplication | Rejected | identical route is masked in M05 |
| Vehicle loss | Included | destroys owned capacity |
| Destructive loops | Rejected | removal/selling are excluded from M05 |
| Excessive no-op | Included | time may pass, but waiting is not free |

## Frozen scalar foundation

Raw values are checked integers; Python/C++ booleans may not impersonate integer
fields. Each raw value is clamped before multiplying by its exact rational
coefficient. Components are accumulated in the table order with an IEEE-754
binary64 left fold from positive zero.

| Order | Component | Raw clamp | Coefficient | Weighted range |
|---:|---|---:|---:|---:|
| 0 | passenger delivery delta | 0..128 | `1/16` | 0..8 |
| 1 | operating profit delta | -16,384..16,384 | `1/4096` | -4..4 |
| 2 | capital spend | 0..65,536 | `-1/16384` | -4..0 |
| 3 | no-op indicator | 0..1 | `-1/64` | -0.015625..0 |
| 4 | native rejection indicator | 0..1 | `-1/4` | -0.25..0 |
| 5 | stopped primary bus-ticks | 0..1,024 | `-1/65536` | -0.015625..0 |
| 6 | vehicle loss count | 0..8 | `-2` | -16..0 |
| 7 | bankruptcy indicator | 0..1 | `-8` | -8..0 |

Every raw, clamped, weighted, and scalar value is retained. Nonfinite input or an
overflow that cannot satisfy the checked integer boundary is `NONFINITE`/failure,
not a training transition.

## Episode outcomes

Bankruptcy and an optional future solved threshold are terminal and never
bootstrap. Action, tick, and simultaneous action-plus-tick horizons are
administrative truncations and bootstrap from the final valid observation. User
cancellation produces an incomplete, non-trainable segment. Invalid engine
state, worker crash, timeout, integration failure, nonfinite math, and writer I/O
failure are failure records outside ordinary terminal/truncated training data.
Failure has priority over game outcomes, followed by bankruptcy, solved, user
cancellation, combined horizon, individual horizons, and continuation. The V1
solved threshold is disabled in this foundation.

## Trajectory and rollout foundation

The reference format is canonical JSON metadata plus content-addressed M04
observation blobs. Each observation blob is exactly 132,096 bytes: 256 structured
and 32,768 spatial little-endian float32 values. Records and bundles use SHA-256
over canonical JSON with their own integrity field omitted. Mandatory writes use
create-new temporary files, `fsync`, atomic rename, and never overwrite.

A segment contains at most 128 transitions and 129 observation blobs. Observation
bytes are capped at 17,040,384, metadata at 8,388,608, and the complete segment at
25,428,992 bytes. Canonical pre-shuffle order is worker, episode, transition. The
shuffle seed is the first little-endian 64 bits of SHA-256 over canonical
`run_seed`, `rollout_id`, and `update_index`.

`scripts/v1/m06_reward_reference.py` independently implements raw derivation,
component math, termination classification, float bit guards, record integrity,
and shuffle seeds. The initial unit suite covers hand calculations, all clamps,
counter regression, strict typing, every outcome family, stable hashes, schema
drift, duplicate keys, and BOM rejection.

## Accepted implementation

The M06 patch adds the read-only lifetime economy projection and integrates
reward/termination after M05 reaches `S_t+1`. Two byte-identical campaigns prove
quarter rollover, delivery/profit attribution, horizon bootstrap, bankruptcy,
all eight reward components, trajectory corruption rejection, writer safety, and
deliberate construction/cycle/duplicate/idle/no-op/failure policies. G06 passes
and M07 CPU PPO work is unblocked.
