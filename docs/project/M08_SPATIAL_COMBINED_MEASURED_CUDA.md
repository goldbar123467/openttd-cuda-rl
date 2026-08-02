# M08 spatial, combined, and measured CUDA training

## Status

M08 and G08 are `PASS`. The normative model/device contract is
`config/v1/m08-architecture-cuda-contract.json`; the acceptance record is
`docs/project/G08_GATE_REPORT.md`.

| Identity | SHA-256 |
|---|---|
| Architecture/CUDA compatibility | `52c8b622b79d793e85ef749822e6886cd7cdda63194a471d38ab25da910e101d` |
| Accepted implementation commit | `d73ae527ced58031f2b9bcce881537eda463d53a` |
| CUDA gate executable | `a3470c1743ac33d99c0eda315bdccd1282d02e9157a0595fd1a7decfdcbcde23` |
| Architecture smoke executable | `85bed9ad9429db1895ff6e3712150586346cfc48a67f70dce81c503425ae5a6b` |
| Live multimodal trainer | `d163d44718d7ffda5e768512f6a27494d568fb103511fed7215046cdb342b089` |

## Frozen architectures

All models consume float32 tensors and expose the same 41-logit policy and
scalar value heads. The existing M07 model remains the exact CPU oracle.

| Architecture | Input | Encoder/fusion | Parameters |
|---|---|---|---:|
| `structured-mlp-v1` | structured `[256]` | `256→128→128`, tanh | 54,826 |
| `spatial-cnn-v1` | spatial `[32,32,32]` | three CNN layers, `4096→128`, tanh | 594,506 |
| `combined-cnn-mlp-v1` | both | CNN 128 + structured 128, concat `256→128` | 660,298 |

The spatial path preserves the M04 `channel-y-x` flat order without a semantic
transform. The CNN uses `32→32` stride 1, `32→64` stride 2, and `64→64` stride 2
3-by-3 convolutions, yielding an 8-by-8 feature map before projection. Native
tests prove exact parameter and output identity between the unified structured
model and the M07 CPU model at a common seed.

## Device boundary and production policy

OpenTTD simulation, synchronized observation extraction, reward calculation,
GAE, and immutable rollout storage remain on CPU. Only bounded inference batches
and PPO minibatches cross to the selected neural device. Structured MLP stays on
CPU. The live CNN and combined paths use `cuda:0` with 32-sample PPO minibatches;
that size is inside the measured-benefit region. A batch-one combined PPO update
is retained on CPU because the final median speedup was only `0.970757`.

CUDA runs with float32 IEEE math and TF32 disabled. Mixed precision is not
accepted. Missing CUDA, compute capability below 12.0, unsupported devices, and
CUDA allocator OOM have distinct terminal error classes. Checkpoints are moved
to and serialized from canonical CPU tensors; loading can then target a validated
runtime device.

## Correctness and performance

CPU/CUDA parity covers all three architectures with identical canonical inputs.
The maximum observed absolute errors were `5.96047e-7` forward, `5.96047e-8` PPO
loss, `7.74861e-7` gradient, `1.58698e-6` post-Adam parameter, and `7.15256e-7`
after CUDA-to-CPU checkpoint recovery. All are well inside the frozen tolerances;
every stable greedy action matched.

The accepted full benchmark uses 20 warmups and 100 synchronized samples per
device and batch on an NVIDIA GeForce RTX 5070 (compute capability 12.0):

| Batch | PPO update speedup | Inference speedup | CUDA update samples/s | CUDA inference samples/s |
|---:|---:|---:|---:|---:|
| 1 | 0.971x | 3.715x | 570 | 5,676 |
| 4 | 1.670x | 4.086x | 2,189 | 14,487 |
| 16 | 3.414x | 9.681x | 8,967 | 57,901 |
| 64 | 11.033x | 19.314x | 30,930 | 122,691 |
| 256 | 31.183x | 41.704x | 55,510 | 148,266 |
| 1024 | 39.201x | 42.481x | 63,182 | 141,652 |

Observation preprocessing remains a direct CPU copy because there is no
transform kernel to accelerate. OpenTTD simulation remains CPU because it is a
semantic boundary rather than a tensor bottleneck.

## End-to-end and live evidence

A controlled paired learning task runs eight real PPO updates and 256 samples on
both devices for every architecture. CPU and CUDA reach the objective at identical
sample counts: 192 for the MLP and 32 for both CNN models. CUDA is intentionally
slower for the small MLP, but is 1.675x faster for the spatial CNN and 1.737x for
the combined model.

The accepted live smoke launches four isolated instances of the unchanged M06
OpenTTD executable for each architecture. Each model consumes actual M04 spatial
and structured observations, completes one 128-transition PPO update, and runs a
16-step deterministic development evaluation. The three seeded pre-update reward
vectors match exactly, all metrics are finite, final-evaluation templates remain
unlaunched, and the OpenTTD executable identity remains
`765c108213bfbb23df2712956acb9bbf6bbb5b0a1d446b0ec154a94fbf41876c`.
This is an integration gate, not a model-quality comparison; matched multi-seed
economic quality remains M09.

## Monitoring and retained artifacts

The accepted CUDA root is
`/home/thecl/.codex/artifacts/openttd-rl/m08-cuda-acceptance-b`. Its 630 telemetry
samples have no unavailable interval, 99% peak utilization, 2,968 MiB peak used
device memory, 207.15 W peak power, and 55 C peak temperature. The paired learning
root is `/home/thecl/.codex/artifacts/openttd-rl/m08-architecture-acceptance-b`.
The live root is
`/home/thecl/.codex/artifacts/openttd-rl/m08-live-architecture-acceptance-b`.

M08 does not select a superior architecture, inspect final-evaluation seeds,
export ONNX, or install a normal-game neural agent. Those claims remain with
M09 through M11.
