# Version 1 Implementation Roadmap

## Purpose

This roadmap turns `GOAL.md` and `docs/project/REQUIREMENTS.md` into an ordered
delivery program. It plans the whole Version 1 lifecycle; it is not permission to
claim later milestones from partial infrastructure.

## Current-state baseline

As of 2026-08-01, `G00` through `G03` pass. The accepted substrate is a pinned
and reproducible OpenTTD 15.3 profile, a frozen 32 by 32 passenger-bus
scenario/reset corpus, and a synchronized source-integrated headless bridge with
process isolation, exact tick stepping, lifecycle failures, and repeated native
non-perturbation evidence. No V1 policy observation/action schema, reward,
trajectory layer, PPO trainer, CUDA trainer, evaluator, ONNX package, or in-game
neural agent exists.

Legacy P0 completion is not a prerequisite as originally written because its
freight target conflicts with the active bus-only scope. Its reusable pieces enter
Version 1 only through the applicability gate in milestone `M00`.

## Gate rules

1. Milestones are dependency ordered. A downstream prototype may be used to reduce
   risk, but it cannot make a release claim while an upstream gate is open.
2. Each gate has named artifacts, tests, and evidence. A plausible demo is not a
   substitute.
3. A defect capable of invalidating downstream data reopens all dependent gates.
4. Performance work starts only after the scalar/CPU reference path is correct.
5. New gameplay scope is forbidden before `M12` passes.
6. Gate evidence records the exact repository and OpenTTD commits and whether the
   worktree was clean.
7. Any intentional contract break increments a compatibility version and supplies
   migration/rejection tests.

## Milestone graph

```text
M00 authority + legacy triage
  -> M01 reproducible V1 OpenTTD profile
  -> M02 bus scenario + reset
  -> M03 synchronized headless bridge
  -> M04 observation contract
  -> M05 action + mask contract
  -> M06 reward + episode + trajectory
  -> M07 CPU PPO + structured MLP
  -> M08 spatial CNN + combined + measured CUDA
  -> M09 independent evaluation + AI baseline
  -> M10 checkpoint/export/package equivalence
  -> M11 normal-game inference + inspection
  -> M12 full reproduction + V1 release
```

`M04` and early `M05` design work may overlap after `M03` supplies a read-only
snapshot boundary. `M09` evaluator scaffolding may begin beside `M07`, but model
quality claims wait for frozen schemas and trained checkpoints. `M11` may build a
mock-policy playback spine before ONNX is ready, but final playback passes only
with an `M10` package.

## M00 — Authority, preservation, and executable project gates

### Objective

Make the new goal machine-visible while preserving useful P0 work and preventing
old freight assumptions from silently governing V1.

### Required outputs

- canonical project documents in the authority order defined by `GOAL.md`;
- an accepted transition record for every legacy top-level planning document and
  every P0 implementation family;
- a machine-readable V1 requirements registry generated from or checked against
  `docs/project/REQUIREMENTS.md`;
- a bidirectional traceability linter that rejects unknown, duplicate, orphaned,
  or falsely passing requirement/test IDs;
- a V1 defect/divergence ledger with severity, affected gates, disposition, and
  retained evidence;
- a no-loss snapshot or commit strategy for the current dirty worktree before
  structural code migration begins;
- accepted ADRs 0008 through 0013 for integration, supported host/toolchain,
  license/publication boundary, source/dependency pinning, evidence, and legacy
  reuse.

### Legacy applicability decisions

Each existing family receives exactly one status:

- `REUSE_AS_IS`: directly meets the new contract and has passing evidence;
- `ADAPT`: sound foundation but requires bus/V1 changes and fresh tests;
- `REFERENCE_ONLY`: informative but cannot enter production or gate evidence;
- `FREEZE`: preserve as historical artifact, do not continue on the V1 path;
- `REMOVE_LATER`: no continuing value, but removal requires a separate reviewed
  clean-up after user work is preserved.

Initial planning disposition is in `LEGACY_P0_TRANSITION.md`; implementation must
verify it rather than assume it.

### Exit gate `G00`

- all project-level requirement IDs lint;
- no current top-level document presents road freight or a clean-room gameplay
  port as the active product target;
- all dirty worktree files are inventoried and preserved;
- the immediate V1 branch/worktree strategy is recorded;
- no legacy result is labeled as satisfying a V1 bus gate without fresh evidence.

## M01 — Reproducible V1 OpenTTD build and runtime profile

### Objective

Freeze the actual engine, build, content, runtime, ONNX, and CUDA dependency basis
for Version 1 before building an environment against moving behavior.

### Required outputs

- exact OpenTTD 15.3 source commit from ADR 0009 and clean reconstruction
  procedure;
- supported development and release host profiles;
- the ADR 0011 baseline (GCC/C++20, CMake/Ninja, CUDA 13.0, LibTorch 2.13 `cu130`,
  auxiliary PyTorch exporter, ONNX opset 18, and ONNX Runtime 1.28 CPU), with exact
  archives, ABI/runtime compatibility, graphics/content, and test-tool manifests;
- reproducible headless and playable build variants from the same source basis;
- explicit feature flags for training bridge, in-game inference, assertions,
  sanitizers, and telemetry;
- offline-capable repeat build after approved dependencies are acquired;
- upstream unit/regression test inventory and smoke tests for both variants;
- license and provenance inventory for every distributed dependency.

### Required experiments

1. two clean out-of-tree builds from the same inputs;
2. headless start/stop with isolated user-data roots;
3. playable start to the main game path with inference disabled;
4. dependency/profile drift negative tests;
5. baseline runtime resource measurement.

### Exit gate `G01`

- both build variants pass their exact test inventories;
- manifests describe observed rather than assumed versions;
- the submodule/source basis is immutable and clean for accepted evidence;
- no environment code depends on host GUI configuration;
- ONNX/CUDA choices are pinned or explicitly marked unavailable with an accepted
  resolution task before their dependent milestone.

## M02 — Reproducible 32 by 32 passenger-bus scenario and reset

### Objective

Create the sole initial gameplay distribution and prove controlled reset before
defining learning semantics.

### Current implementation boundary

The prerequisite conditional engine-feasibility slice passes and is documented
in `M02_MAP_FEASIBILITY.md`: flag-off preserves the accepted 64 by 64 behavior,
while flag-on creates, saves, reloads, and soaks true-empty 32 by 32 maps under
assertions, ASan/LSan, and fail-fast UBSan with byte-identical repeated builds.
The frozen scenario schema, eight-template corpus, disjoint seed ledger, native
semantic reset projection, forbidden-scope validator, and scripted economic bus
trajectory also pass. `G02_GATE_REPORT.md` records the repeated current-Ubuntu
evidence and closes G02 without implementing an RL bridge.

### Scenario contract

- 32 by 32 temperate/default-economy map;
- deterministic seed-to-layout generation or a versioned set of deterministic
  scenario templates;
- one learning company with declared initial balance/loan;
- a bounded, validated number of towns suitable for bus connection;
- passengers only, no active industry servicing;
- no other companies during initial training;
- buses, roads, road depots, and bus stops as the only agent-reachable transport
  systems;
- disasters, NewGRFs, multiplayer, and post-V1 systems disabled;
- documented calendar start, vehicle availability policy, inflation/breakdown
  disposition, town-growth policy, passenger-generation policy, and horizon.

### Required outputs

- versioned scenario configuration schema;
- seed ledger and deterministic generation/reset entry point;
- canonical initial-state projection containing every V1-relevant setting, pool,
  tile channel, RNG stream, date/counter, company, town, and economy field;
- reset state machine with clean-process and same-process modes;
- scope validator that fails on forbidden cargo, vehicles, companies, content, or
  settings;
- small fixed scenario corpus for tests plus separate train/evaluation seed sets.

### Exit gate `G02`

- repeated clean-process and same-process resets match at the declared semantic
  boundary;
- every allowed seed produces a valid learnable scenario within resource bounds;
- train and evaluation scenario sets cannot overlap accidentally;
- forbidden-scope mutations are rejected;
- the fixed non-learning bus trajectory uses normal engine commands and reaches
  passenger delivery plus positive income on every frozen template;
- no legacy freight fixture is used as V1 completion evidence.

## M03 — Synchronized headless environment bridge

Status: `PASS` at `G03` on 2026-08-01. The accepted contract and evidence are in
[`M03_SYNCHRONIZED_BRIDGE.md`](M03_SYNCHRONIZED_BRIDGE.md) and
[`G03_GATE_REPORT.md`](G03_GATE_REPORT.md).

### Objective

Expose stable reset/snapshot/step control at safe OpenTTD engine boundaries without
screen scraping or semantic perturbation.

### Required outputs

- source-integrated C++ bridge selected by ADR;
- typed environment handle with lifecycle state machine;
- `reset`, `snapshot`, `legal_actions`, `step`, `pause`, `resume`, and `close`
  operations with explicit error/result types;
- deterministic simulation-tick scheduler and configurable action interval;
- one-process/one-environment reference implementation;
- multi-environment isolation strategy, initially process-based unless a reviewed
  in-process design proves global-state isolation;
- crash/timeout detection and retained failure artifacts;
- synchronization invariants preventing observations and masks from different
  ticks or partially executed commands;
- plain-versus-bridge non-perturbation campaign for action-free and scripted runs.

### Exit gate `G03`

- reset and stepping pass exact tick/counter tests;
- a fixed scripted bus trajectory replays identically across repeated runs;
- stale handles, calls in invalid lifecycle states, and engine failures fail
  closed;
- bridge-disabled and observation-only runs preserve declared engine behavior;
- single-environment soak completes without state desynchronization.

## M04 — Versioned observation and preprocessing contract

### Objective

Freeze the structured vector and spatial tensor consumed identically by trainer,
evaluator, ONNX, and in-game inference.

### Design tasks

1. inventory all candidates in `OBS-002` through `OBS-013`;
2. define causal availability and reject deployment-only leakage;
3. define field sources, shapes, types, units, scales, clipping, normalization,
   missing values, coordinate axes, and update boundaries;
4. define fixed maximum counts and overflow/truncation policies for towns, buses,
   stations, routes, and candidate entities;
5. implement one authoritative C++ encoder library used by all native paths;
6. create human-readable and machine-readable schema artifacts with digests;
7. create synthetic pattern maps and controlled game states for every channel;
8. define normalization-state fitting/freeze rules without evaluation leakage.

### Exit gate `G04`

- every included scalar and tile has an actual-engine semantic comparison test;
- every excluded source candidate has a reviewed rationale;
- repeated encoding is byte-identical for the same snapshot;
- orientation, ownership, catchment, blocked/buildable, route, and vehicle channels
  pass targeted fixtures;
- encoder calls do not mutate or advance the engine;
- schema/digest incompatibility is rejected.

## M05 — Explicit bus actions, masks, and transactional execution

### Objective

Freeze a bounded policy-output/action interface that can build and operate useful
bus routes and distinguish every failure class.

### Required design decisions

- fixed catalog, factored head, or bounded deterministic candidate-set encoding;
- stable entity-slot identity and reuse policy;
- town-selection state versus direct parameterization;
- primitive road segments versus a deterministic road-path macro;
- multi-command transaction and partial-failure semantics;
- vehicle engine choice, depot association, station/order identity, and route
  lifecycle;
- no-op tick count and per-episode action budget;
- sell, removal, and loan-action inclusion or explicit V1 exclusion.

### Required outputs

- machine-readable action registry and compatibility digest;
- deterministic legal-action enumeration and mask generator;
- native command adapter that uses normal OpenTTD validation/execution paths;
- explicit outcomes for success, stale-state failure, illegal input, no-op, and
  integration failure;
- structured per-action and per-native-subcommand logging;
- independent slow legality oracle for differential tests;
- scripted route-construction acceptance trajectory.

### Exit gate `G05`

- encode/decode round trips cover every action and boundary parameter;
- masks match the independent oracle over fixed and randomized valid states;
- sampled indices are always legal, including all-mask edge handling;
- each action's cost, tick effect, ownership, and state mutation matches OpenTTD;
- injected native-command failure proves transaction semantics;
- a scripted policy builds stops/depot/roads, buys a bus, assigns orders, starts
  service, delivers passengers, and receives revenue.

## M06 — Reward, termination, trajectory, and rollout contract

### Objective

Turn synchronized transitions into auditable learning data without reward leakage
or ambiguous episode semantics.

### Required outputs

- versioned reward registry dispositioning every `REW-001`/`REW-002` candidate;
- exact component units, sign, timing, weights, clipping, and scalar aggregation;
- termination reasons: horizon, bankruptcy, invalid state, crash/integration
  failure, optional solved threshold, and user cancellation;
- Gym-style distinction between terminal game outcomes and time-limit truncation,
  expressed in native types rather than requiring Python;
- trajectory schema containing observations/references, masks, actions, log
  probabilities, values, component rewards, scalar reward, terminal flags, tick
  ranges, and provenance;
- bounded rollout buffer and deterministic shuffling inputs;
- scripted positive/negative reward fixtures and exploit campaign.

### Exit gate `G06`

- each reward term passes hand-calculated and actual-engine scenario tests;
- cumulative engine counters are converted into correct transition deltas;
- observation/action/reward/next-observation all refer to documented boundaries;
- bankruptcy and every termination/truncation path bootstrap values correctly;
- trajectory round trip preserves exact values and rejects corruption;
- deliberate cycling, duplicate-building, idling, no-op, and invalid-action policies
  do not produce unintended positive return.

## M07 — Trusted CPU PPO and structured MLP baseline

### Objective

Validate the full learning loop using the lowest-complexity required architecture
before adding CNN/CUDA complexity.

### Required outputs

- C++ tensor/model backend decision and pinned dependency;
- structured MLP actor-critic with masked categorical action distribution;
- complete `PPO-001` through `PPO-022` implementation;
- deterministic single-environment debug trainer;
- batched CPU rollout collector;
- native checkpoint and recovery format;
- structured metrics and a non-interactive logger;
- terminal monitor backed only by logged metric sources;
- algorithm reference vectors and tiny deterministic learning problems;
- first bus-environment learning runs with frozen run manifests.

### Exit gate `G07`

- PPO math matches an independent trusted reference on fixed vectors;
- numerical fault injection stops and preserves diagnostics;
- checkpoint round trips match outputs and update counters;
- interrupted and uninterrupted runs match at the documented recovery boundary;
- monitor values match authoritative logs/counters;
- the structured MLP improves over random on a development suite; this is a
  readiness signal, not the final independent quality claim;
- extended CPU training has no unresolved desynchronization.

## M08 — Spatial CNN, combined model, batching, and measured CUDA

### Objective

Complete all required architectures and accelerate proven bottlenecks while
preserving CPU-reference semantics.

### Required outputs

- CNN encoder for the frozen 32 by 32 tensor;
- combined spatial/structured actor-critic;
- shape/dtype/device contract shared by all architectures;
- profiling report locating actual CPU/GPU bottlenecks;
- batched CUDA inference and PPO optimization where justified;
- optional CUDA preprocessing/state encoding only if profiling and parity support
  it;
- CPU/CUDA forward, loss, gradient/update, and checkpoint equivalence suites;
- GPU utilization/memory monitoring with unavailable-state handling;
- throughput, latency, memory, and sample-efficiency measurements.

### Exit gate `G08`

- all three architectures train end-to-end;
- CPU/CUDA results meet reviewed numerical/statistical tolerances;
- no kernel changes environment/game semantics;
- at least one production neural/tensor training workload uses CUDA and provides a
  measured benefit on the declared hardware; individual non-beneficial candidate
  kernels remain disabled and documented;
- OOM, unavailable-device, and unsupported-architecture failures are clear;
- inference/training device moves preserve checkpoint compatibility.

## M09 — Independent evaluator, baselines, and architecture comparison

### Objective

Measure actual policy quality using a preregistered suite that training cannot
mutate or tune after results are observed.

### Required outputs

- separate evaluator executable/library mode with no optimizer dependency;
- frozen train/development/final seed partitions;
- scenario matrix covering `EVAL-002` through `EVAL-008`;
- metric registry covering every `EVAL-009` candidate;
- random and trivial scripted policies;
- at least one documented existing OpenTTD AI/scripted-agent workflow;
- matched MLP/CNN/combined experiment manifests;
- seed-level results, confidence intervals/dispersion, aggregate report, and raw
  structured outputs;
- robustness and failure-case analysis.

### Exit gate `G09`

- evaluator is proven read-only with respect to policy/normalization state;
- baseline provenance is complete and baseline limitations are disclosed;
- matched budget checks reject unfair comparisons;
- at least one learned policy beats random and trivial scripted baselines and meets
  preregistered reliable-profitability/stability thresholds;
- MLP/CNN/combined comparison is complete over multiple seeds;
- training reward is reported alongside, never instead of, economic metrics.

## M10 — Checkpoint, ONNX, package, and three-runtime equivalence

### Objective

Produce a portable, self-describing model package that fails closed on drift and
has equivalent native, ONNX, and in-game computations.

### Required outputs

- native checkpoint schema/migration policy;
- ONNX export for every supported V1 architecture;
- pinned ONNX runtime and inference wrapper;
- complete package manifest required by `MODEL-004` plus per-file hashes;
- compatibility-version and rejection matrix;
- golden inference corpus containing observations, masks, expected logits,
  probabilities, values, greedy actions, and stochastic seeds;
- reviewed tolerance ADR for each output/data type/device;
- native-versus-ONNX deterministic and sampled-distribution reports;
- install/uninstall instructions that do not require training dependencies.

### Exit gate `G10`

- ONNX graph inspection confirms inputs/outputs and no training-only state;
- every golden input passes native/ONNX tolerance;
- every mutated compatibility field and corrupt file is rejected;
- package provenance and evaluation result links are complete;
- export is reproducible at the declared model/ONNX stability level;
- an inference-only build loads and executes the package.

## M11 — Normal-game neural agent, inspection, and visible playback

### Objective

Integrate the validated inference core into a playable OpenTTD build so a user can
watch, inspect, pause, and diagnose the trained bus policy.

### Required outputs

- normal-game C++ controller using the same encoder/action/mask/inference core;
- documented model directory and agent selection/configuration path;
- greedy and seeded stochastic modes;
- validated adjustable inference interval;
- metadata/compatibility display and actionable errors;
- optional action logs and debug overlays;
- pause/step controls or explicit engine-supported disposition;
- inspection view required by `MODEL-017`;
- native-versus-ONNX-versus-in-game golden equivalence suite;
- scripted clean-user playback acceptance procedure.

### Exit gate `G11`

- a packaged `G09` policy loads in the playable build;
- in-game outputs pass the `G10` golden corpus and selected live-state comparisons;
- a clean user can start a game and watch the policy build and operate a bus route;
- inspection values match structured logs;
- incompatibility, missing model, corrupt model, and runtime failures do not crash
  or silently hand control to a different policy;
- normal playback has no training dependency.

## M12 — Full workflow reproduction and Version 1 release

### Objective

Prove the complete story from clean build through visible play and freeze a
reproducible research release.

### Required campaigns

1. clean supported-host build of headless and playable variants;
2. controlled scenario generation/reset reproduction;
3. CPU debug training smoke and selected production C++/CUDA training run;
4. checkpoint interruption/recovery;
5. independent fixed/unseen-seed evaluation and baseline comparison;
6. ONNX export, packaging, compatibility mutation, and equivalence;
7. model installation and visible in-game playback;
8. long-run environment/training soak;
9. sanitizer/static/resource/fault/malformed-input test matrix;
10. documentation run by an independent operator or clean environment;
11. requirements/defect/evidence closure audit; and
12. repeat of the top-level release gate from fresh output roots.

### Required release artifacts

- source/build/dependency/run manifests;
- versioned environment/action/observation/reward/model schemas;
- training logs and checkpoint hashes;
- final independent evaluation and architecture-comparison reports;
- packaged model and equivalence report;
- terminal-monitor and in-game acceptance evidence;
- complete requirement-to-test-to-evidence registry;
- zero open release-blocking correctness defects;
- user guide covering build, train, resume, evaluate, export, install, play, and
  troubleshoot.

### Exit gate `G12`

Every applicable `SCOPE-*` through `DONE-*` row in the project requirements
register is `PASS`, every result is backed by retained authoritative evidence, and
no contradiction or unverified completion claim remains. Only then may Version 1
be called complete and the post-V1 roadmap activate.

## Post-Version 1 roadmap

The expansion sequence is governed by `EXP-001` through `EXP-010`. Each stage
creates a new environment compatibility version, adds only its declared gameplay
systems, reruns the complete earlier-stage regression/evaluation matrix, and
retains prior model packages or supplies an explicit migration/rejection policy.

## Program-level risks

| Risk | Early detector | Required response |
|---|---|---|
| Global OpenTTD state prevents in-process vectorization. | Two-instance isolation prototype in `M03`. | Use process isolation first; optimize only with proof. |
| Action space is too large or unstable for a fixed PPO head. | `M05` catalog-size and mask-density study. | Freeze a bounded factored/candidate contract before trainer work. |
| Reward is exploitable. | `M06` scripted adversarial policies. | Simplify/version reward and rerun prior evidence. |
| Observation leaks hidden deployment state. | `M04` information-source audit. | Remove or expose equivalently in game before training. |
| CPU engine throughput dominates. | `M03`/`M08` profiles. | Parallelize environments; do not move semantics to GPU casually. |
| Native/ONNX/in-game drift. | Golden vectors from `M10` onward. | Reject package/release; use one shared preprocessing/action core. |
| Existing AI cannot run on the exact 32 by 32 restrictions. | Baseline feasibility probe in `M09`. | Use it in another allowed evaluation/demonstration workflow and document limits. |
| Legacy P0 consumes the critical path. | `M00` disposition and milestone accounting. | Freeze non-applicable work; reuse only verified infrastructure. |
| Long episodes hide desynchronization. | Boundary hashes and soak checks. | Stop at first divergence and retain smallest reproducer. |
| CUDA adds complexity without benefit. | CPU baseline and per-stage benchmarks. | Keep correct CPU path and disable unjustified kernel. |

## Immediate critical path

`G00` through `G03` are recorded as passing. The synchronized bridge now supplies
the safe read-only boundary required by M04. The next implementation path is:

1. preserve the accepted M01 through M03 source/evidence identities;
2. begin M04 only by freezing the versioned policy observation and shared
   preprocessing contract;
3. prove every observation field/channel against actual engine state without
   perturbing the M03 boundary;
4. retain the M02 scripted trajectory and M03 lifecycle oracle as fixed
   downstream integration fixtures;
5. do not begin M05 actions, M06 rewards, or PPO before their owning gates.

Continuing the legacy freight instrumentation patch series is not on the V1
critical path unless its transition review identifies a specific bus-platform gate
that it uniquely and economically satisfies.
