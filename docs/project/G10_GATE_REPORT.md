# G10 gate report: portable package and three-runtime equivalence

## Result

`G10: PASS` on 2026-08-02. All 17 M10-owned requirements pass. Every V1
architecture has a reproducible ONNX opset 18 deployment package; native,
standalone ONNX Runtime, and the in-game adapter agree within the frozen
tolerances; and all 30 compatibility/corruption mutations fail closed.

## Frozen identities and provenance

| Artifact | Identity |
|---|---|
| Package contract commit | `2a70ff6fb26d5beaf86e63c564483941dff08002` |
| Accepted implementation commit | `4e4b692c183f985bc46c55b0e7e1107d4a0da9fb` |
| M10 compatibility | `e77edf9be1343970a55becbb05da96a6b9a17edbd8df2c7999701dd8fa1f33b6` |
| Accepted report file | `3dc1615f2a54fae568a8e731853aab2ff710b05baf1a835b826f2a17a29d49de` |
| Accepted report semantic identity | `8a685696dab8639c72050c73efb82812c36c562a62d6c3a1aa2d68fe6c610e1d` |
| ONNX Runtime | CPU 1.28.0; archive `a3e1b79d7bb1bf09696ce675f49e4064e6c81f6202b8225624fff0e93f8d6407` |
| Exporter | Python 3.12.3, PyTorch 2.13.0+cpu, ONNX 1.22.0, ONNX Script 0.7.1 |

The retained accepted artifact is
`/home/thecl/.codex/artifacts/openttd-rl/m10-package-acceptance-a`. It contains
both independent export roots, the three promoted packages, graph metadata,
golden JSONL corpora, M09 evaluation links, install instructions, and the gate
report. It has 28 files totaling 32,900,120 bytes.

## Promoted packages

| Architecture | Source M09 package | Deployment package | ONNX SHA-256 |
|---|---|---|---|
| Structured MLP V1 | `e21039cd66eaeb1f54a3e19271d2e2e71695496b54001a8afe17e01a669ed611` | `2fde45ec8dd2cd073654f7ce79729786e4d284a39fb2c067721acd4e7b4572a9` | `37bf76e72abd74f9cc3f0d37cbcf5e979643189eb3e96ece1effa20398268ac4` |
| Spatial CNN V1 | `f58a5db69b4917916c250dddb8822a22c548d21b5fc4f92c91e0c8706e1519a6` | `6a54c0c6cb3ab54f50a7379a59074f8efbf674717bac03be3bdb2b3dff358446` | `e05baacfe9bda63ee553cbde44d9532440f95090aa40f9d04d3b73394b6656fc` |
| Combined CNN/MLP V1 | `074b3c3838d9c4b53235d8f9ccc060047f7ce29929511fda6086f072c53b62e3` | `0334e6a9da8d5b87d48ecdcd859dc3a5be6b1f7913511bf3336f8d3cf1feeeb9` | `10df689ccc6d1cb7f2e98f05f0474f72577cd9328a4589e3b1c7167bcbf08b5b` |

Each C++-controlled export transferred every named source tensor exactly,
checked the ONNX graph, and left the immutable M09 source unchanged. Two
independent export and package roots produced byte-identical ONNX files,
payloads, manifests, and package IDs for all three architectures.

The graph signatures contain only the architecture-appropriate float32
`structured [batch,256]` and/or `spatial [batch,32,32,32]` inputs and float32
`policy_logits [batch,41]` plus `value [batch]` outputs. The graphs contain no
training nodes, optimizer state, RNG state, or recurrent state.

## Three-runtime equivalence

The corpus has 12 cases per architecture: eight seeded synthetic cases spanning
WAIT-only, all-legal, and deterministic-sparse masks, plus four actual OpenTTD
states from final templates 07 and 08. All 36 cases compare native LibTorch,
standalone ONNX Runtime, and the same in-game adapter used for M11 integration.

| Output | Frozen absolute/relative tolerance | Maximum observed absolute error |
|---|---:|---:|
| Policy logits | `2e-5 / 2e-5` | `8.344650268554688e-7` |
| Masked probabilities | `2e-6 / 2e-5` | `8.354577540892194e-8` |
| Value | `2e-5 / 2e-5` | `5.7220458984375e-6` |

All masks are byte-exact, all illegal probabilities are zero, and all greedy
actions are exact and legal. V1 explicitly has no recurrent state. ADR 0014
justifies the float32 tolerances and change-control boundary.

Nine distribution cases—three per architecture—sample each runtime probability
vector 100,000 times. Across 27 runtime-pair comparisons, maximum observed total
variation is `0.01173` against `0.015`, and maximum per-bin difference is
`0.00323` against `0.005`.

## Package integrity and rejection

The canonical manifest records architecture/version, typed inputs/outputs,
normalization, recurrent-state disposition, observation/action/mask/reward/M09/M10
compatibilities, ONNX opset/runtime, OpenTTD/environment versions, training and
deployment commits/configs, model/golden seeds, M09 evaluation identity/results,
installation policy, and every payload digest. The package ID content-addresses
the manifest; its file table covers the exact four-file payload inventory.

The fail-closed matrix rejects all 30 frozen mutations before control or at input
validation: package/version/ID, architecture, every compatibility identity,
opset/runtime/game/environment, every input/output name/shape/dtype,
normalization/recurrent state, digest, missing/unknown/symlink/truncated files,
nonfinite observations, and an all-illegal mask.

## Inference-only installation boundary

The deployment-only CMake configuration returns before LibTorch, CUDA, trainer,
optimizer, or checkpoint discovery. Its dynamic closure contains ONNX Runtime,
OpenSSL, and ordinary C/C++ host libraries; `libtorch`, `libc10`, Python, CUDA,
cuDNN, and optimizer/training libraries are absent. Every package includes atomic
install and exact-directory uninstall instructions under
`openttd-rl/models/<package-id>`.

## Repository verification

- Both full and deployment-only builds compile under the strict warning policy.
- Six native CTest targets pass, including PPO, architecture, and immutable M09
  evaluator coverage.
- The focused M10 suite validates the frozen contract, format separation,
  dependency boundary, tolerances, and complete mutation ownership.
- The full traceability suite passes 221 tests before closure, with document lint,
  JSON schema/semantic validation, ShellCheck, and Git whitespace checks passing.

G10 proves portable package computation and the in-game adapter boundary. It does
not yet claim normal interactive playback, inspection UI, pause/step operation,
clean-user visible acceptance, long soak, or release reproduction; those remain
M11 and M12.
