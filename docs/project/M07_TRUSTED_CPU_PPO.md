# M07 trusted CPU PPO and structured MLP

## Status

M07 and G07 are `PASS`. The normative learner contract is
`config/v1/m07-ppo-contract.json`; the acceptance record is
`docs/project/G07_GATE_REPORT.md`.

| Identity | SHA-256 |
|---|---|
| PPO compatibility | `8649da85cee2914d423a7ae8f1bcff0fa6a1c7d749bd04232976fbad6df518c0` |
| Contract file | `cb4311100d12238bc668645321a866e5044e0abb1753ba6145fe27abcb3964ac` |
| Contract schema | `abbaa1154f4c5bbe81e5830ca83b6401781b4fd57517a81951abd3c5b4cd1ac0` |
| Accepted trainer executable | `c45a6589a47f175f041bf151339e38aad79ede207aaf3d4fc107e5d810f4f31f` |
| Accepted checkpoint | `7c4b210f43c06032488c72b613401734a0bf7e6eafcce4d0167d0dc1d3c92360` |

## Trusted backend and model

The first learner is C++20 and LibTorch 2.13.0+cu130, using CPU float32 for the
M07 oracle path. The normal OpenTTD game does not depend on LibTorch. The model
consumes the frozen 256-value M04 structured vector, uses two shared 128-unit
`tanh` layers, and exposes separate 41-logit policy and scalar-value heads.
Weights use deterministic orthogonal initialization with independent seeded RNG
streams for initialization, action sampling, minibatch shuffling, and environment
episode selection.

PPO implements clipped policy loss, plain MSE value loss, entropy regularization,
fixed-order float64 GAE, population advantage normalization with an exact-zero
constant case, Adam, complete seeded minibatches, and global gradient clipping.
Illegal actions have exactly zero probability; an all-illegal row fails closed.

## Rollout and numerical boundary

The native service accepts bounded little-endian typed frames. Python coordinates
the existing OpenTTD bridge but does not own PPO math, sampling, model updates, or
checkpoint state. Live rollouts use time-major `T=32`, `N=4`; the native service
computes typed terminal/truncation GAE and performs four optimization epochs over
32-sample minibatches.

Observations, logits, masked probabilities, values, reward inputs, advantages,
returns, every loss, gradients, global gradient norm, optimizer state, and updated
parameters are finite-checked. A numerical incident is terminal for the trainer
service: it emits a diagnostic-only content-addressed artifact and cannot publish
a normal checkpoint from the affected process.

## Checkpoints and exact recovery

Checkpoints are created only after a completed update and before the next rollout.
They contain model parameters, opaque and stable-semantic Adam state, counters,
PPO configuration, dependency/schema identities, all RNG states and seed ledger,
parent identity, source provenance, and canonical development-evaluation metadata.
Payloads are written to a new temporary directory, synced, content-addressed,
atomically renamed, and never overwritten.

The opaque LibTorch optimizer archive contains process-specific serialization
details, so checkpoint identity uses a stable Adam semantic tensor digest while
still hash-verifying the opaque payload. A fresh resumed process produced the same
actions, transition values, update metrics, parameters, and semantic checkpoint
identity as an uninterrupted process.

## Development selection discipline

Only M02 templates 01–04 are used for training. Templates 05–06 are the trainer-
visible development suite. Templates 07–08 remain forbidden and unlaunched until
the independent final-evaluation milestone.

Every 16 updates, deterministic development evaluation runs without mutating the
trainer. A candidate is eligible only when it beats the seeded-random baseline in
mean return and mean delivered passengers and produces service on every
development template. The highest-return eligible content-addressed checkpoint is
retained, with passenger delivery and earlier update as tie-breakers. A fresh
process must reproduce its evaluation exactly.

The accepted 64-update soak retained candidates at updates 16, 32, 48, and 64.
Updates 16, 48, and 64 were eligible; update 32 was rejected. Update 16 remained
best and exactly reproduced a separate 16-update calibration campaign, including
the same checkpoint identity.

## Metrics and monitor

The authoritative sink is bounded canonical JSONL. Its 41-field source registry
maps each display field to a counter, trainer calculation, environment aggregate,
process measurement, or explicit unavailable value. The wide terminal rendering
shows run provenance, counters, throughput, all PPO metrics, environment outcomes,
checkpoint/best score, CPU/GPU/memory, and warning state. Widths below 100 columns
use a one-line stream-safe rendering with no ANSI control sequences. Missing GPU
telemetry is `null` with `gpu_available=false`, never fabricated as zero.

M08 may now add the spatial CNN, combined architecture, profiling, and measured
CUDA execution. M07 does not claim independent final quality, ONNX export, or
normal-game neural playback.
