# G06 gate report: reward, episodes, and trajectories

## Result

`G06: PASS` on 2026-08-01. All fourteen M06-owned requirements are `PASS`.
CPU PPO work in M07 is now unblocked; no training or model-quality claim is made
by this gate.

## Frozen identities

| Artifact | Identity |
|---|---|
| M06 reward compatibility | `9d8f9c2fc6074d899fa3b0047c55e3fb15cc5c17cddeaceaa1fd5389e53c8c9e` |
| Reward contract file | `28712c2b7fcf009e3ceda0ebbc2f18d382f28f780adb52186a08ab871998a2e7` |
| M06 native patch | `ce2a423e5f78aed861d0ca032a21509ce976267f17718cea8e3a973f8d24e912` |
| M06 patch series | `b001a2bffe511d1814dd820373b129d887d35cce7ad38bd02dcce5ccc106bbff` |
| M06 result tree | `56b7f68297cb1ec7548c25ac9dfa0d0088e70547` |
| M06 composed source | `98693ab0595fb26612079683a192a12f7bce6bb4cb25a7edf895244c50c568a2` |
| Accepted executable | `765c108213bfbb23df2712956acb9bbf6bbb5b0a1d446b0ec154a94fbf41876c` |
| Oracle report schema | `76eae7214a0bb061d573eda4ddca3e5fa82312550d8492b767b5b005a15d43e3` |
| Accepted oracle manifest | `6b72ac4e4a21667bcbc40ae4dde6a0b2e16ebad53109b45f4d03c4939c6dfce7` |
| Accepted trajectory bundle | `0417d8ece711f8e1025a86eb3d96662133afab8521ccbc70ec8fc12797a62f3a` |

The native patch applies only after the accepted M05 tree and produces the exact
M06 result tree. The composed identity includes the parent identity, patch-series
digest, ordered patch descriptor, and result tree.

## Native transition evidence

`src/rl_reward.cpp` in the composed source captures the learning company's
current economy plus all valid retained quarterly entries at both synchronized
boundaries. OpenTTD already excludes construction and vehicle-purchase categories
from `cur_economy.expenses`, so operating profit and separately logged capital
spend do not double-count one command cost.

The native step returns:

- all eight raw, clamped, weighted, and float-bit-guarded components;
- an IEEE-754 binary64 left-fold scalar from positive zero;
- pre/post lifetime engine projections;
- typed terminal, truncation, bootstrap, and trainable flags;
- optional next observation and next mask from the committed post-boundary.

The independent Python reference recalculated every actual-engine transition and
matched every integer, component, scalar, and binary64 guard exactly. The prior
M05 campaign also passed unchanged against the M06 executable: all eight maps,
nine action families, 614 mask states, rollback, rejections, delivery, and income.

## Actual-engine campaigns

Two complete retained campaigns are byte-identical:

- `/home/thecl/.codex/artifacts/openttd-rl/m06-reward-oracle-20260801-g`
- `/home/thecl/.codex/artifacts/openttd-rl/m06-reward-oracle-20260801-h`

Their report manifests both hash to
`6b72ac4e4a21667bcbc40ae4dde6a0b2e16ebad53109b45f4d03c4939c6dfce7`;
their complete directory trees have no differences.

Every frozen M02 template constructed service and produced positive passenger
delivery and operating-income deltas in 29 to 33 decisions. Actual transitions
also exercised capital spend, no-op, native rejection, idle bus-ticks, controlled
vehicle loss through a normal OpenTTD sell command, and native bankruptcy state.
Pure reference tests cover all clamp extrema and component combinations.

The long actual-engine episode reached exactly 512 actions and 65,536 ticks,
crossed nine visible current-quarter counter resets, and retained monotonic
lifetime counters. It classified the simultaneous limit as
`ACTION_AND_TICK_HORIZON`, truncated with bootstrap from a final valid observation.
The additive typed reason does not break the legacy bridge field, which remains
the original lowercase `action-horizon` value at the simultaneous limit.
The controlled bankruptcy scenario returned `-8.015625`, classified terminal,
and did not bootstrap.

All thirteen outcome reasons are covered by the typed classifier tests. Disabled
`SOLVED`, user cancellation, invalid state, worker crash, timeout, integration,
nonfinite, and I/O failure remain failure/incomplete control paths rather than
ordinary reward transitions.

## Trajectory and exploit evidence

The accepted actual rollout contains the hard maximum of 128 transitions and 129
exact M04 observation blobs. Each blob is 132,096 bytes of structured-then-spatial
little-endian float32 data and is addressed by SHA-256. Record and bundle digests,
finite float guards, deterministic ordering, create-new writes, `fsync`, atomic
rename, and refusal to overwrite are executable behavior.

Round-trip tests preserve exact records and reject blob corruption, metadata
corruption, duplicate keys, BOMs, nonfinite values, boundary discontinuity,
incorrect bootstrap values, and segment overflow before rollout consumption.

Adversarial actual-engine returns were all non-positive:

| Policy | Return/effect |
|---|---:|
| pure construction | `-0.39190673828125` |
| route-selection cycling | `-0.072021484375` |
| eight idle waits | `-0.181396484375` |
| 32 no-ops | `-0.540771484375` |
| four native rejections | `-1.0078125` |
| controlled vehicle loss | `-2.015625` |
| duplicate connector attempt | zero ticks, no reward transition |

Destruction and selling remain absent from the agent's M05 catalog; the sell
command is reachable only through the explicit M06 vehicle-loss oracle fixture.

## Verification

- M06 focused repository suite: 21 tests pass.
- Full repository traceability suite: 191 tests pass.
- Native OpenTTD suite in the complete development source: 98 of 98 CTest entries pass.
- Two complete M06 campaigns and their 128-transition bundles are byte-identical.
- Native patch whitespace and apply-after-M05 tree checks pass.
- Full traceability, schema, documentation, shell, and repository suites are run
  by the repository gate before the G06 commit is accepted.

G06 does not pass PPO, CNN/CUDA, independent evaluation, checkpoint/ONNX
equivalence, in-game neural playback, or release reproduction. Those remain M07
through M12 work.
