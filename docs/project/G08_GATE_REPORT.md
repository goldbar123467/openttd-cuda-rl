# G08 gate report: spatial, combined, and measured CUDA training

## Result

`G08: PASS` on 2026-08-01. All eight M08-owned requirements are `PASS`. The
independent architecture comparison in M09 is now unblocked.

## Frozen identities

| Artifact | Identity |
|---|---|
| Accepted source commit | `d73ae527ced58031f2b9bcce881537eda463d53a` |
| Architecture/CUDA compatibility | `52c8b622b79d793e85ef749822e6886cd7cdda63194a471d38ab25da910e101d` |
| CUDA gate executable | `a3470c1743ac33d99c0eda315bdccd1282d02e9157a0595fd1a7decfdcbcde23` |
| Architecture smoke executable | `85bed9ad9429db1895ff6e3712150586346cfc48a67f70dce81c503425ae5a6b` |
| Live trainer executable | `d163d44718d7ffda5e768512f6a27494d568fb103511fed7215046cdb342b089` |
| CUDA report content | `c1add8dffba12915e36bf48a685e68d00c28e5a9892b8f86547780710ca539a0` |
| GPU telemetry content | `b9614f93abd3065db7b75197018d8527117156f4e2962479bbf9676b59a193b2` |
| GPU monitor summary content | `a3e5d637c2f7917a312af1419d1fc942539739e7966c32476b6d220cfa11df6e` |
| Unavailable-device failure content | `5cc5ea17839ad13fbe5395c7c320cdd7d1dda455699dec4a515a86d69e6e1f49` |
| Allocator-OOM failure content | `bcb663e94c875ed3c9d4cc6995258b2b85d8a7663385d18d97bb6eaab52e6139` |
| Failure summary content | `da2f280b840cfc08c4640859d60e06485eb858c290b716aa9235674368deada4` |
| CPU architecture smoke content | `954fd1db0c1052905e7abe382fabecc7721a9a867597da0079cd982b68723ba5` |
| CUDA architecture smoke content | `47e541f8ea788f64739e9797c96a31ce7449c9bd45ba20abf944c27af1702f6b` |
| Live manifest content | `df2632870401a2dd364c32120324f06af9bcff13e835b2b4c24e3ab548ab0214` |
| Live manifest semantic identity | `6630e001062e861c5c9b0e3cdba4f6eaaca6143fce27b0bf89d3bcafba70a41e` |

## Exit criteria

| G08 criterion | Result | Evidence |
|---|---|---|
| All three architectures train end to end | PASS | paired CPU/CUDA eight-update learning plus a live 128-transition OpenTTD update per model |
| CPU/CUDA results meet tolerances | PASS | all-close forward, PPO loss, gradients, Adam update, stable greedy actions, and checkpoint recovery |
| Environment/game semantics unchanged | PASS | frozen M06 executable, CPU-only engine/encoding, identical matched reward vectors, no final-seed access |
| Production CUDA workload has measured benefit | PASS | batch-64 update 11.033x and inference 19.314x on the declared RTX 5070 |
| Non-beneficial kernels remain disabled | PASS | batch-one PPO update remains CPU; preprocessing and OpenTTD simulation remain CPU |
| OOM/unavailable/unsupported failures are clear | PASS | real hidden-device and allocator-OOM checks return distinct terminal classes; unsupported device/architecture rejects explicitly |
| Device moves preserve checkpoints | PASS | canonical CUDA-to-CPU save/reload outputs remain within `1e-4`, observed maximum `7.15256e-7` |

## Numerical parity

| Architecture | Forward abs | PPO loss abs | Gradient abs | Adam update abs | Checkpoint abs |
|---|---:|---:|---:|---:|---:|
| structured MLP | `1.78814e-7` | `5.96047e-8` | `1.76952e-7` | `2.08617e-7` | `1.78814e-7` |
| spatial CNN | `5.96047e-7` | `0` | `7.74861e-7` | `1.58698e-6` | `7.15256e-7` |
| combined CNN/MLP | `3.57628e-7` | `5.96047e-8` | `1.93716e-7` | `5.35511e-7` | `4.76838e-7` |

TF32 and mixed precision are disabled. The frozen absolute limits are `1e-4`
for forward/checkpoint, `1e-5` for loss, and `5e-4` for gradients and updates.

## Measured CUDA benefit and monitoring

The accepted report at
`/home/thecl/.codex/artifacts/openttd-rl/m08-cuda-acceptance-b` uses 20 warmups
and 100 measurements for each of six batches and two production workloads.

| Batch | Full PPO update | Batched inference | Peak allocated | Peak reserved |
|---:|---:|---:|---:|---:|
| 1 | 0.971x | 3.715x | 78.2 MiB | 114 MiB |
| 4 | 1.670x | 4.086x | 92.2 MiB | 114 MiB |
| 16 | 3.414x | 9.681x | 102.8 MiB | 140 MiB |
| 64 | 11.033x | 19.314x | 144.6 MiB | 230 MiB |
| 256 | 31.183x | 41.704x | 309.8 MiB | 530 MiB |
| 1024 | 39.201x | 42.481x | 969.6 MiB | 1,670 MiB |

The monitor observed an NVIDIA GeForce RTX 5070, UUID
`GPU-1e2f280f-31f2-c69a-233e-55627e1aefaf`, compute capability 12.0, driver
610.88, and 12,227 MiB. All 630 samples were available; peak utilization was
99%, peak used memory 2,968 MiB, peak power 207.15 W, and peak temperature 55 C.

## Learning, live integration, and failure evidence

The paired controlled run preserves CPU/CUDA sample efficiency exactly. Each
model accepts 256 samples: the MLP reaches the fixed objective at 192, while the
spatial and combined models reach it at 32. CUDA spatial and combined elapsed
times are respectively 1.675x and 1.737x faster than CPU; the small MLP remains
on CPU.

The live run at
`/home/thecl/.codex/artifacts/openttd-rl/m08-live-architecture-acceptance-b`
uses the accepted M06 OpenTTD executable and four isolated training workers.
Every architecture completes a 128-transition update with finite PPO metrics and
a deterministic development smoke. Their matched rollout reward triplets are
exact. No final-evaluation process is launched.

With `CUDA_VISIBLE_DEVICES` empty, the native gate returns code 3 and
`class=cuda-unavailable`. A controlled 23.88 GiB allocation on the 11.94 GiB
device invokes the real LibTorch allocator failure, returns code 4, and emits
`class=cuda-out-of-memory`. Unsupported device and architecture requests are
rejected without fallback.

## Repository verification

- Clean pinned LibTorch/CUDA 13 build: 23 steps, strict warnings, and 5/5 CTest
  targets pass.
- Six native M08 tests cover identities, exact M07 preservation, all model
  shapes/gradients, batch invariance, input rejection, and end-to-end learning.
- Seven focused Python tests cover contract mutation, source ownership,
  environment boundaries, explicit failures, and retained evidence mutation.
- The full repository suite passes 206 tests; all 227 requirement rows, 23 test
  mappings, and 142 passing requirements validate with zero open defects.
- Python compile, ShellCheck 0.9.0, bash syntax, schema validation, documentation
  navigation, and Git whitespace checks pass.

G08 does not claim independent multi-seed economic superiority, final evaluation,
ONNX equivalence, or normal-game deployment. Those remain M09 through M11.
