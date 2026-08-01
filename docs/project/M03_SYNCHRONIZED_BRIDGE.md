# M03 synchronized headless environment bridge

## Result and claim boundary

M03 passes. OpenTTD 15.3 now exposes a source-integrated, headless,
single-environment worker through inherited anonymous pipes. The bridge provides
typed `reset`, `snapshot`, `legal_actions`, `step`, `pause`, `resume`, and
`close` operations only at complete `StateGameLoop` boundaries. Multiple
environments are isolated by running one worker process per environment.

This milestone does not define the M04 policy observation, M05 policy action
registry or legal-action mask, M06 reward/trajectory contract, PPO, CUDA
training, ONNX, evaluation, or a neural in-game agent. Its two action IDs are
M03 integration fixtures: `WAIT` and the accepted M02 scripted bus setup.

## Frozen contract

The machine authority is
[`config/v1/m03-bridge-contract.json`](../../config/v1/m03-bridge-contract.json),
validated against
[`v1-m03-bridge-contract.schema.json`](schema/v1-m03-bridge-contract.schema.json).
Its compatibility identity is
`4701a21ae106f6fa120db1b89c3929d16c29afafb8e0198126173137ed2af2d6`.

The protocol uses a 56-byte little-endian `ORL1` header, protocol version 1.0,
canonical compact UTF-8 JSON, a 1 MiB payload limit, and CRC32C over the header
with its checksum field zeroed plus the payload. Session, episode, request, and
transition ordinals are explicit. Request IDs are strictly consecutive; stale
handles, boundaries, requests, and lifecycle calls return typed errors without
advancing ticks or mutating engine state.

The lifecycle is `READY`, `RESETTING`, `AT_BOUNDARY`, `EXECUTING`,
`ADVANCING`, `PAUSED`, `FAILED`, and `CLOSED`. Observation-only queries consume
no commands, ticks, or RNG. Pause is bridge-control state and does not change the
engine pause mode.

## Tick policy

The caller records an interval from 1 through 128 complete `StateGameLoop` calls
in every step. The V1 reference interval is 128, which closes the accepted M02
horizons exactly: 512 actions times 128 ticks equals 65,536 ticks. Construction
commands commit before the first advanced tick, and the response commits only
after the final tick and boundary invariants pass. If action and tick horizons
coincide, the reported reason is `action-horizon`.

## Source integration identity

| Input | SHA-256 or identity |
| --- | --- |
| Accepted M02 result tree | `551a99fbd33bd1b0f8c9ec35561deb0e893b81fe` |
| Accepted M02 composed identity | `edc76541bfda23c2916fc85d499e6e0d5a5cefaad09f40bf19972c2d3307385e` |
| M03 patch | `6677d5a32abc5250394133e162236f1b2c5a9acfe19ea867a8b0512b10343c50` |
| M03 series | `bb0f27f2bd530d89433dbf6b32fdbd4e63fed4e08224f8b190298f5185d7959e` |
| M03 result tree | `39ed7069eca2c48c512a9bdd989c049aca3c5329` |
| M03 composed identity | `d5d14398d545c951b04325d91d444e6194553e537d4b1f16615cba44351f2ef1` |
| Oracle report schema | `5f4e69c6414b15c92c43b5d9798edcc316ab5f01c7b6242460cf5b1666be5423` |
| Current Ubuntu executable | `1a14655590e46cee0e7415174d62714092c8691d6bad2e4c89bf87b5065c9794` |

The ordered patch is
[`0004-synchronized-environment-bridge.patch`](../../integration/openttd/patches/15.3/m03/0004-synchronized-environment-bridge.patch).
It applies without fuzz or offset after the accepted M02 tree and is available
only when `OPTION_RL_ENVIRONMENT=ON`. With `-B` absent, the accepted M02 native
batch path remains active and produces its frozen projections and trajectories.

## Native acceptance evidence

Two complete campaigns are retained outside Git at:

```text
/home/thecl/.codex/artifacts/openttd-rl/m03-bridge-oracle-20260801-a
/home/thecl/.codex/artifacts/openttd-rl/m03-bridge-oracle-20260801-b
```

The roots are byte-identical. Their common `manifest.json` SHA-256 is
`0a0664be8345ef79f6d01a7de404ad0f7427071849661a5e6dabd3025a960877`;
their common `commands.json` SHA-256 is
`9fe51ff69535e422db6286c1f5e3e83205fb41a953cdddb66f0129607a3ca4bf`.
The strict oracle report schema accepts both manifests.

Each campaign executes every frozen M02 template twice in clean bridge workers,
repeats reset in the same worker, and runs the bridge-disabled M02 reference.
Every repeated trace is identical and every reference projection and scripted
trajectory retains its accepted M02 digest. A two-process interleaving test proves
that a bus created in worker A never appears in worker B and that each worker's
tick and pool state remain independently controlled.

The scheduler exercise accepts and records intervals 1, 64, and 128, advances
exactly 193 cumulative ticks, and rejects 0, 129, and the narrowing adversary
4,294,967,297 without mutation. The same large value is rejected as an action ID. The
action-free soak performs 512 reference steps and exactly 65,536 ticks without
state desynchronization. Fault coverage includes bad CRC32C classification,
transition to `FAILED`, clean close from `FAILED`, an actually killed worker,
monotonic response timeout, owned-worker termination, and retained stdout/stderr. Invalid lifecycle calls,
stale handles, stale boundaries, repeated setup, and post-horizon steps are
rejected without perturbing the last committed snapshot.

## Next allowed work

Preserve the contract and source identities above. M04 may now freeze the
versioned policy observation and shared preprocessing contract using the M03
snapshot boundary. Do not reinterpret the synchronization snapshot as the M04
observation, and do not begin M05 actions, M06 rewards, or learning work as part
of that step.
