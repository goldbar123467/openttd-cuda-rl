# PPO Training and Model Pipeline Plan

## Purpose

This plan defines the first trusted learning implementation and the complete path
from rollout to a playable model package. PPO is the only Version 1 algorithm.
The plan covers the structured MLP, spatial CNN, combined architecture, CPU
reference, measured CUDA acceleration, checkpoints, ONNX, and in-game equivalence.

## Dependency boundary

Training begins only after environment contract gates `G02` through `G06` pass.
Tiny mock environments may test PPO math earlier, but no OpenTTD learning claim is
valid while observation, action, reward, stepping, or termination semantics remain
unfrozen.

The trainer consumes an environment/trajectory API. It must not reach around that
API to read hidden OpenTTD state, repair masks, alter rewards, or perform game
commands.

## Trusted implementation strategy

1. implement and test PPO math on CPU using fixed vectors and tiny deterministic
   environments;
2. train the structured MLP through the real bus environment;
3. retain the CPU path as a correctness oracle;
4. add the spatial CNN and combined architecture;
5. profile end-to-end workloads;
6. move only justified tensor/training operations to CUDA;
7. validate checkpoints and independent evaluation;
8. export immutable checkpoints to ONNX;
9. prove native/ONNX/in-game equivalence;
10. package only after all compatibility and provenance checks pass.

## PPO mathematical contract

For rollout transition `t`, the stored data include observation `o_t`, legal mask
`m_t`, selected action `a_t`, behavior log probability `logp_old_t`, value estimate
`V_t`, scalar reward `r_t`, and terminal/truncation semantics.

### Generalized Advantage Estimation

The implementation must define and test:

- discount `gamma` and GAE parameter `lambda` ranges;
- terminal transitions with zero bootstrap;
- time-limit truncation with bootstrap from the valid final observation;
- failure transitions that are excluded or handled by an explicit policy;
- variable episode boundaries inside a rollout batch;
- float precision and accumulation order;
- normalized advantages and zero-variance handling.

Conceptually:

```text
delta_t = r_t + gamma * bootstrap_t * V_(t+1) - V_t
A_t = delta_t + gamma * lambda * continuation_t * A_(t+1)
return_t = A_t + V_t
```

The exact bootstrap/continuation masks are typed fields, not inferred from a single
ambiguous `done` boolean.

### Masked categorical policy

The distribution must:

- validate mask shape/schema against logits;
- set illegal action probability to exactly zero at the semantic level;
- calculate normalization, entropy, sampling, greedy selection, and log
  probability consistently;
- define finite behavior when one action is legal;
- reject an all-illegal mask unless the environment contract's safe wait action is
  inserted before the trainer boundary;
- retain the mask used to sample each rollout action;
- apply the identical old mask when recomputing ratios;
- detect a stored action that is not legal under its stored mask.

### Clipped objective

The implementation records and tests:

```text
ratio_t = exp(logp_new_t - logp_old_t)
policy_loss = -mean(min(ratio_t * A_t,
                        clip(ratio_t, 1-epsilon, 1+epsilon) * A_t))
```

Required edge cases include positive/negative/zero advantage, ratios below/inside/
above the clip interval, extreme but finite log-probability differences, masked
single-action distributions, and mixed episode/minibatch boundaries.

### Value and entropy terms

The value loss choice (plain MSE, clipped value loss, or another reviewed PPO
variant) is frozen in the trainer configuration and tested against hand vectors.
Entropy is calculated from the masked distribution only. Coefficients, reduction
orders, and optional annealing are explicit and logged.

### Optimization

The trainer freezes:

- optimizer family and all hyperparameters;
- learning-rate policy;
- global gradient norm definition and clipping order;
- rollout length and number of environments;
- minibatch size, shuffle algorithm, and incomplete-minibatch policy;
- optimization epochs and early-stop/KL policy;
- parameter initialization and seed stream;
- mixed-precision policy, initially disabled until full-precision validation;
- device transfer and synchronization boundaries.

NaN/inf checks cover observations after preprocessing, logits, probabilities,
values, rewards, advantages, returns, losses, gradients, gradient norm, optimizer
state, and updated parameters. A failure stops before publishing a normal
checkpoint.

## PPO verification ladder

### Level 1 — scalar/vector unit tests

- hand-computed GAE and returns;
- terminal versus truncated bootstrap;
- ratio/clipping regions;
- entropy over known masked distributions;
- advantage normalization including constant input;
- gradient-norm clipping;
- minibatch index generation and coverage;
- deterministic seeded sampling.

### Level 2 — independent differential

Compare fixed tensors and one or more update steps against a trusted, pinned
independent PPO/tensor implementation used only as a test oracle. Compare inputs,
advantages, returns, logits, values, component losses, gradients where available,
and updated parameters under declared tolerances. The independent reference may be
Python because it is not the production path.

### Level 3 — tiny learning problems

Use deterministic bandit/small-MDP fixtures with known or easily bounded optimum to
prove that masking, advantage signs, clipping, entropy, checkpoint recovery, and
batching learn as expected before OpenTTD complexity.

### Level 4 — scripted OpenTTD trajectory update

Feed a fixed real-environment trajectory with independently reviewed reward and
terminal data. Repeated debug updates must match exactly in the declared CPU
deterministic mode.

### Level 5 — development learning run

The structured MLP must improve beyond random on non-final development scenarios
without numerical failure. This validates integration but is not final model
quality evidence.

## Architecture contracts

All models expose the same semantic outputs:

- policy logits matching the frozen action representation;
- scalar state-value estimate;
- optional recurrent state only after a future ADR updates every checkpoint,
  trajectory, export, and equivalence contract.

Version 1 should begin feed-forward. Recurrent state is not assumed and cannot be
added opportunistically.

### Baseline A — structured MLP

Input is the fixed structured vector plus masks/entity features approved by the
action ADR. The architecture record defines layer widths, activation, normalization,
parameter initialization, policy/value sharing, and output heads.

Purposes:

- simplest end-to-end PPO/environment validation;
- low-cost CPU debug oracle;
- measure how far curated semantic summaries can solve the task.

### Baseline B — spatial CNN

Input is the exact multi-channel 32 by 32 tensor plus only those nonspatial scalars
the architecture comparison protocol permits. If the pure spatial baseline needs
time/economic context, the comparison must label it rather than silently becoming
the combined model.

The record defines convolution shapes, padding, stride, activation, pooling or
flattening, spatial coordinate handling, and policy/value heads.

Purposes:

- test spatial planning and infrastructure decisions;
- measure sample efficiency and compute/memory cost against MLP.

### Baseline C — combined model

Encodes the spatial tensor with a CNN, the structured vector with an MLP, fuses
features at a declared layer, and produces shared or separate heads. The fusion and
parameter-count policy are documented so comparisons remain interpretable.

### Comparison fairness

Matched experiments require:

- identical environment/schema/reward versions;
- same train/development/final seed partitions;
- same number of environment steps and evaluation horizon;
- same checkpoint-selection protocol;
- same number of independent training seeds;
- declared hyperparameter tuning budget per architecture;
- parameter count, wall/GPU time, energy or utilization where available, and peak
  memory reported alongside performance;
- no architecture declared superior from a single best seed.

## Batched runtime

The initial vector runtime uses isolated OpenTTD worker processes unless `M03`
proves safe in-process state. A coordinator:

- assigns deterministic episode/scenario seeds independent of scheduling;
- submits actions with monotonic request/transition IDs;
- collects results in canonical rollout order;
- detects timeout, crash, duplicate, stale, and out-of-order results;
- records worker restarts and never discards failures silently;
- separates environment wait, encoding, inference, transfer, and optimization
  timing;
- bounds queued observations/trajectories and applies backpressure.

Rollout tensors have explicit time-major or batch-major order. Flattening and
minibatch shuffling are tested so terminal boundaries and masks remain aligned.

## CUDA plan

CUDA is not an architectural requirement for OpenTTD simulation. Candidate owned
workloads are:

- batched MLP/CNN forward inference;
- actor-critic backward pass and PPO optimizer;
- tensor normalization/packing when host-device transfer analysis justifies it;
- GAE/advantage normalization for sufficiently large batches;
- batched evaluation inference.

Every CUDA addition requires:

1. CPU reference implementation and passing semantic tests;
2. profile showing the candidate matters at the intended scale;
3. supported device/toolkit/dtype/shape contract;
4. deterministic/debug policy and disclosure of nondeterministic operations;
5. forward/loss/update parity within reviewed tolerances;
6. error checks after launches and synchronization at contract boundaries;
7. OOM/device-loss/unsupported-device behavior;
8. throughput, latency, memory, transfer, and break-even report;
9. no regression to CPU-only training/evaluation/inference support.

Version 1's accepted production training path must include at least one such
validated, beneficial CUDA neural/tensor workload. A correct CPU fallback remains
mandatory, but documenting that every attempted CUDA path was slower does not by
itself satisfy the project's C++/CUDA production-stack requirement.

Custom kernels are preferred only when the chosen tensor backend cannot provide a
correct efficient operation. The project does not reimplement mature primitives
for appearance.

## Native checkpoint contract

An accepted training checkpoint is an atomic, content-addressed artifact containing
or referencing:

- checkpoint format/version and integrity hashes;
- model architecture/version and parameters;
- optimizer family/state and learning-rate state;
- update, environment-step, simulation-tick, episode, and sample counters;
- all trainer RNG algorithm/state and seed ledger;
- scenario split/configuration identity;
- environment/observation/action/mask/reward/termination schema IDs/digests;
- normalization state/constants and freeze status;
- PPO hyperparameters and runtime configuration;
- OpenTTD, repository, build, compiler, tensor/CUDA dependency provenance;
- best/evaluation score metadata clearly distinguished from final evaluation;
- parent checkpoint/run identity.

Rollout buffers are either included for mid-rollout recovery or the recovery
boundary is only after an atomically completed update. Version 1 should prefer the
simpler completed-update boundary unless unattended-runtime evidence requires
otherwise.

### Checkpoint recovery gate

- load/save round trip preserves parameters and inference outputs;
- corrupt/truncated/unknown/incompatible files fail before mutation;
- interrupted write leaves the previous valid checkpoint intact;
- resumed counters and seed streams do not repeat or skip accepted work;
- exact-debug interrupted versus uninterrupted runs match at the declared boundary;
- production statistical mode reports any backend nondeterminism honestly.

## Structured logging and monitor

The event/metric schema defines each value's name, units, type, source, aggregation
window, timestamp/counter basis, and unavailable encoding. Required monitor groups
map to `MON-002` through `MON-006`.

The terminal monitor:

- reads the structured metric state rather than calculating private values;
- supports bounded refresh rate and non-TTY fallback;
- avoids cursor/control corruption over SSH/tmux;
- adapts to terminal width and exposes a compact mode;
- shows stale/unavailable/warning states explicitly;
- does not block rollout or hold synchronization locks during rendering.

Non-interactive JSON Lines or another reviewed structured format remains the
authority for CI, files, experiment analysis, and external tracking. External
tracking is an optional sink and cannot be required to preserve local evidence.

## Export pipeline

### Inputs

- immutable accepted native checkpoint;
- selected architecture/export implementation;
- frozen normalization and schemas;
- golden inference corpus;
- target ONNX opset/runtime compatibility profile;
- accepted evaluation summary.

### Stages

1. validate checkpoint integrity, compatibility, and provenance;
2. instantiate inference-only architecture and load parameters;
3. run native golden inference and retain outputs;
4. export policy/value graph to ONNX;
5. validate ONNX structure, input/output names, shapes, dtypes, opset, and checker;
6. run ONNX golden inference;
7. compare native/ONNX outputs and greedy actions;
8. perform sampled-distribution comparison using fixed protocol;
9. build manifest and copy exact schema/normalization/evaluation artifacts;
10. hash every package file and canonical manifest;
11. run compatibility-negative tests on a copy;
12. atomically promote the package under a unique identity.

An ONNX file produced before equivalence is a candidate export, not a release
artifact.

## Model package contract

Required package contents include:

```text
model.onnx
manifest.json
observation.schema.json
spatial-channels.schema.json
action.schema.json
action-mask.schema.json
normalization.json
outputs.schema.json
evaluation-summary.json
golden/
  inputs...
  expected-native-outputs...
LICENSES-or-provenance-reference...
```

The canonical manifest includes every field in `MODEL-004`, package/file hashes,
ONNX opset/runtime range, endianness/logical tensor order where relevant, inference
interval constraints, stochastic sampler version, and installation compatibility.

The package contains no arbitrary executable scripts, pickle-like code execution,
absolute developer paths, credentials, optimizer state, or training-only shared
libraries.

## Equivalence contract

### Compared paths

1. native model in the trainer/evaluator inference core;
2. ONNX model through the pinned deployment runtime;
3. the exact inference core embedded in playable OpenTTD.

### Compared values

- structured and spatial inputs after preprocessing;
- action mask and masked logits;
- raw policy logits;
- action probabilities or stable log-softmax results;
- scalar value estimate;
- greedy action and decoded parameters;
- recurrent state if ever introduced;
- seeded sampled actions/distribution statistics.

### Tolerances

The tolerance ADR must state absolute/relative comparison, per-output threshold,
dtype/device/backend, NaN/inf/sign-zero policy, tie-breaking for greedy logits,
sample size/statistical test, false-positive budget, and failure examples. A
tolerance cannot be widened merely to accept a failing model; the underlying cause
must be diagnosed and the change reviewed.

Exact equality is expected for integer inputs, schema IDs, masks, action decode,
and deterministic tie-breaking. Floating outputs use the smallest justified
reviewed tolerance.

## In-game runtime plan

The playable build links the shared observation/action/package/inference core and
an OpenTTD company controller. At each inference boundary it:

1. validates active model/environment compatibility;
2. captures synchronized state;
3. encodes inputs and mask;
4. executes greedy or seeded stochastic ONNX inference;
5. validates finite outputs and mask consistency;
6. selects/decodes one action;
7. submits it through the same action executor semantics;
8. logs optional inspection data;
9. waits until the next configured inference boundary.

The user can see model name/version, current action/confidence, value, legal count,
route target, and reward-relevant state. Debug overlays are diagnostic and do not
alter the policy input. Pause/step controls follow engine capabilities and are
tested for boundary consistency.

## Pipeline release gates

| Gate | Required result |
|---|---|
| `PPO-MATH` | all algorithm, masking, minibatch, numerical, and differential tests pass |
| `MLP-LEARN` | structured MLP improves on development scenarios without correctness defects |
| `ARCH-TRAIN` | MLP, CNN, and combined models train under frozen contracts |
| `CUDA-PARITY` | enabled CUDA paths pass parity and measured-benefit requirements |
| `CHECKPOINT` | atomic save/reload/recovery/incompatibility campaign passes |
| `EVAL-READY` | immutable policy loads in independent evaluator without training mutation |
| `ONNX-EXPORT` | ONNX structure and native equivalence pass |
| `PACKAGE` | complete, hashed, provenance-valid package passes mutation/rejection tests |
| `INGAME-EQUIV` | all three runtime paths pass golden/live equivalence |
| `PLAYBACK` | clean-user documented visible bus operation succeeds |

None of these gates alone is Version 1 completion; `G12` is their conjunction with
the environment, evaluation, reproducibility, and quality gates.
