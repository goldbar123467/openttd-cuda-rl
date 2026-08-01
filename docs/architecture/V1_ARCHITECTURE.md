# Version 1 Target Architecture

## Status

This is the architectural plan for the bus-only Version 1 platform. It defines
component responsibilities and dependency direction. Exact tensor sizes and
gameplay schemas remain milestone decisions. ADRs 0008 through 0013 freeze the
initial source, integration, toolchain, evidence, publication, and legacy
boundaries; their acquisition and ABI claims still require the named
implementation gates.

## Architectural drivers

The design must simultaneously provide:

- actual OpenTTD engine behavior rather than a screen-controlled approximation;
- deterministic reset and synchronized step semantics;
- high-throughput batched rollout without hiding engine crashes or state drift;
- one observation/action/inference meaning across training, evaluation, ONNX, and
  visible gameplay;
- a trusted CPU correctness path before measured CUDA acceleration;
- independent model evaluation and provenance-complete artifacts; and
- normal-game inference without trainer dependencies.

## Selected integration direction

ADR 0010 selects a source-integrated C++ bridge compiled into controlled headless
and playable builds from the OpenTTD 15.3 commit pinned by ADR 0009. The headless
worker is a regular non-dedicated build with an RL-specific loop/bootstrap, not an
unchanged `-v null` or network-server process. The bridge calls normal engine
validation/execution paths and reads state only at reviewed `StateGameLoop`
boundaries. It is not a network-control protocol, screen scraper, GUI automation
layer, Squirrel neural wrapper, or independent reimplementation of OpenTTD
gameplay.

Implementation evidence may still force a replacement ADR. Any replacement must
meet every stable-interface, non-visual, synchronization, equivalence, and in-game
playback requirement; a narrower substitute is not automatically acceptable.

## Logical system view

```text
                            project schemas + compatibility
                                        |
            +---------------------------+---------------------------+
            |                           |                           |
    headless training             independent eval            playable OpenTTD
            |                           |                           |
    +-------v--------+          +-------v--------+          +-------v--------+
    | PPO trainer    |          | policy runner  |          | neural company |
    | rollout/store |          | metrics/report|          | controller/UI  |
    +-------+--------+          +-------+--------+          +-------+--------+
            |                           |                           |
            +---------------------------+---------------------------+
                                        |
                            +-----------v-----------+
                            | shared inference core |
                            | encoder, mask, model, |
                            | action interpretation |
                            +-----------+-----------+
                                        |
                            +-----------v-----------+
                            | environment contract  |
                            | reset/snapshot/step   |
                            +-----------+-----------+
                                        |
                            +-----------v-----------+
                            | pinned OpenTTD engine |
                            | native commands/ticks |
                            +-----------------------+
```

The shared inference core is the semantic waist. Training may have optimizer and
rollout dependencies above it; the playable build may not. Environment and engine
code below it have no dependency on PPO.

## Proposed repository ownership

The final names may change via ADR, but ownership boundaries must remain visible.

```text
apps/
  train/                 C++ training executable and CLI monitor
  evaluate/              independent evaluator
  export_model/          checkpoint-to-ONNX/package entry point
  inspect_model/         package metadata and golden-vector inspector
core/
  schema/                compatibility IDs, generated typed schema bindings
  observation/           authoritative C++ encoder and normalization
  action/                registry, mask generation, decode, execution plan
  model/                 architecture definitions and inference abstraction
  telemetry/             structured metrics/events and terminal view model
environment/
  bridge/                OpenTTD lifecycle/synchronization adapter
  scenario/              32x32 generation/reset/validation
  reward/                components, termination, scalar aggregation
  trajectory/            transition and rollout formats
training/
  ppo/                   GAE, losses, minibatches, optimization, checkpoints
  runtime/               vector environments, rollout orchestration
  cuda/                  measured kernels/backends only
evaluation/
  scenarios/             frozen evaluation suites and split manifests
  baselines/             random/scripted/existing-AI adapters
  metrics/               economic and robustness metrics/reporting
integration/
  openttd/               patch or source-integration layer
  ingame/                playable neural company controller/inspection
models/
  schema/                package schema and compatibility fixtures
tests/
  unit/ integration/ equivalence/ soak/ fault/ golden/
docs/                    governing plans, contracts, ADRs, user guides
legacy/
  ...                    optional later relocation of frozen P0 material
```

Existing repository directories are not to be moved into this layout until the
dirty worktree is preserved and `M00` approves a migration. This is a target
ownership map, not authorization for destructive reorganization.

## Component contracts

### OpenTTD engine basis

Owns all actual game semantics: map/town/company state, commands, construction,
vehicles, orders, cargo flow, economy, date/ticks, and engine RNG. It must remain
pinned for an accepted environment compatibility version.

It does not own observations, reward shaping, PPO state, neural inference, model
packaging, or experiment reporting.

### Scenario manager

Inputs:

- environment compatibility version;
- scenario configuration;
- scenario seed;
- fixed content/settings manifests.

Outputs:

- a valid initialized OpenTTD state at the reset boundary;
- a scenario identity/digest and seed ledger;
- scope-validation results.

It must reject a map that violates V1 dimensions, company/cargo/vehicle/content
restrictions, count bounds, or learnability constraints. Rejection is a recorded
generation result, never an unseeded retry. If bounded resampling is used, every
attempt derives deterministically from the declared seed and attempt number.

### Environment bridge

Owns lifecycle and synchronization, not game rules. Its conceptual state machine
is:

```text
UNINITIALIZED -> READY -> RESETTING -> AT_BOUNDARY
                                  AT_BOUNDARY -> EXECUTING -> ADVANCING -> AT_BOUNDARY
                                  AT_BOUNDARY -> PAUSED -> AT_BOUNDARY
                                  any state -> FAILED -> CLOSED
```

At `AT_BOUNDARY`, observation, action mask, and reward-relevant counters refer to
one immutable logical engine snapshot. An action executes at most once. Simulation
ticks advance according to the step contract. Errors include lifecycle misuse,
invalid schema/version, illegal action, native command rejection, stale state,
timeout, crash, invariant failure, and I/O failure.

The reference implementation is one environment in one process. Because OpenTTD
has substantial global state, ADR 0010 requires one worker process per environment
and batched coordination above those processes. In-process vectorization requires
a replacing ADR and explicit proof that all mutable global state, allocators,
singletons, callbacks, and external resources are isolated.

### Observation encoder

Consumes only a synchronized snapshot and produces:

- fixed-shape structured tensor;
- fixed-shape spatial tensor;
- optional entity/candidate tensors if approved by the action ADR;
- encoder/schema identity;
- diagnostics that are never silently inserted into policy input.

One native library must implement production preprocessing. Training, evaluator,
export validation, and in-game controller either link it or prove byte/numerical
equivalence using the same golden corpus. Normalization parameters are frozen in
the model package; evaluator and playback never refit them.

### Action registry and mask generator

The registry defines a stable policy-output interpretation. The output shape must
be bounded and independent of unconstrained engine pool growth. Entity slots have
explicit allocation/reuse semantics. Legal masks are generated from the same
snapshot as observations.

Mask generation must be free of game mutation and RNG consumption. A slow,
independent legality oracle is retained for tests. The policy cannot rely on
calling every native command in test mode at inference time unless an ADR proves
that this is deterministic, non-perturbing, bounded, and equivalent to execution
preconditions.

### Action executor

Converts one decoded action into zero or more native engine commands. It records:

- action ID and parameters;
- snapshot/tick identity used for masking;
- precondition result;
- each native command, estimated/actual cost, and result;
- total tick/cost effect;
- final typed outcome and failure site.

Macros such as road-path construction or route creation must specify whether
subcommands are validated first, whether execution is atomic, and how partial
success affects state/reward. Silent best-effort behavior is forbidden.

### Reward and episode engine

Computes a vector of causal transition deltas and one versioned scalar. It reads
declared pre/post boundary data and action outcomes; it cannot mutate OpenTTD or
query future state. Training-only convenience values that are unavailable in the
playable controller may not enter policy observations. Reward may use engine state
for learning even if not observed only after a specific information-boundary
review proves this does not make deployment semantics inconsistent.

Termination is a typed result separate from reward. Game terminal outcomes and
administrative truncation are distinct so GAE/bootstrap behavior is correct.

### Vector runtime

Owns worker lifecycle, scenario/seed assignment, step fan-out, ordered result
collection, timeouts, crash handling, and deterministic batching. It may replace a
failed environment only according to a declared recovery policy; it never hides a
failure by silently dropping a trajectory.

The runtime assigns globally unique episode and transition IDs independent of
worker process IDs. Result ordering is canonical so thread scheduling does not
change rollout/minibatch contents when deterministic mode is requested.

### PPO trainer

Consumes rollout tensors and owns model parameters, optimizer, RNG, learning-rate
state, update counters, and native checkpoints. It does not call OpenTTD directly.
The trainer validates all shapes/schema IDs at the boundary and stops on nonfinite
data.

A CPU/debug mode must remain available as the correctness oracle even when CUDA is
used in production. CUDA paths are compared against this reference for forward
outputs, losses, and updates under reviewed tolerances.

### Metrics and monitor

Metrics/events are written first to a structured, versioned sink. The terminal
monitor subscribes to or renders the same data and owns no unique values. Metric
definitions specify source counter, units, aggregation window, reset behavior, and
unavailable value. System telemetry is diagnostic and must not affect training
semantics.

### Independent evaluator

Loads an immutable deployment-compatible policy or checkpoint snapshot and a
frozen evaluation suite. It cannot construct an optimizer, update model weights,
refit normalization, or alter final scenario partitions. It emits per-episode raw
records before aggregate statistics.

Baselines implement the same environment contract where possible. Existing AIs
that cannot expose identical action timing are reported as separate baseline
classes, not forced into a misleading apples-to-apples score.

### Model exporter and package

The exporter translates an immutable native checkpoint into ONNX and a complete
manifest. Packaging is content-addressed. It validates golden vectors before
promotion and never overwrites a different existing package under the same model
identity.

Training state such as optimizer tensors and rollout buffers does not enter the
deployment package. Observation/action schemas, normalization, compatibility,
provenance, and evaluation summaries do.

### Shared inference core

Owns:

- package loading and integrity/compatibility checks;
- observation preprocessing entry points;
- action-mask application;
- native or ONNX model invocation;
- greedy and seeded stochastic selection;
- output validation and action decoding;
- optional structured inference events.

It must be usable in evaluator and playable builds without linking PPO/CUDA
training code. ADR 0011 selects ONNX Runtime C++ CPU as the V1 deployment backend;
CUDA inference is outside V1, while LibTorch CUDA owns the measured production
training workload.

### In-game neural company controller

Runs at a documented inference interval on normal OpenTTD game boundaries. It uses
the same scenario-independent encoder/action/model semantics as headless mode.
It owns user configuration, model selection, metadata/error display, pause/step
integration, and debug overlays. It may not silently modify invalid model inputs or
choose a fallback model after compatibility failure.

## Data flow for one training transition

```text
reset/previous step
  -> synchronized pre-action snapshot S_t
  -> encoder produces O_t
  -> mask generator produces M_t from S_t
  -> policy produces logits/value from O_t
  -> mask is applied; seeded sampler chooses A_t
  -> executor validates/applies A_t once
  -> engine advances [tick_begin, tick_end)
  -> synchronized post-action snapshot S_t+1
  -> reward computes component vector R_t and scalar r_t
  -> termination computes terminal/truncation reason D_t
  -> trajectory stores O_t, M_t, A_t, logp_t, V_t, R_t, r_t, D_t,
     tick range, outcome, schema IDs, episode/transition IDs
  -> next step reuses or encodes O_t+1 under the explicit buffer contract
```

The action mask never comes from `S_t+1`; reward never comes from a partially
advanced state; the executor never applies `A_t` more than once after a timeout.

## Determinism model

Determinism is defined per mode, not as a vague global promise.

### Engine reproducibility

Same engine commit, build profile, content, scenario config, seed ledger, and
action/tick sequence must yield the same declared semantic projection. Binary
savegame identity is required only if the scenario/reset ADR proves it stable and
useful; semantic state is the minimum authority.

### Inference reproducibility

Greedy inference on the same input/package/backend produces outputs within exact
or reviewed numerical tolerance and the same selected action. Stochastic inference
also fixes sampler algorithm, RNG implementation/state, and seed derivation.

### Training reproducibility

The project distinguishes:

- `exact-debug`: fixed CPU/device/thread settings intended for repeatable update
  tensors and checkpoints;
- `seed-reproducible`: same seed/config yields statistically consistent outcomes,
  while nondeterministic accelerated kernels are disclosed;
- `evaluation-deterministic`: fixed package/scenarios/mode yield the same semantic
  actions and metrics where OpenTTD permits.

Run manifests declare the mode. A statistical claim may not be described as
bitwise reproducibility.

## Seed ownership

At minimum, independently derived streams cover:

- scenario generation;
- OpenTTD gameplay RNG state;
- model initialization;
- policy action sampling;
- environment/seed assignment;
- minibatch shuffling;
- dropout or other stochastic layers if introduced;
- evaluation stochastic sampling; and
- existing AI baseline configuration when supported.

Seed derivation uses a versioned deterministic function and stable stream IDs.
Worker count or scheduling must not silently change scenario seeds.

## Compatibility model

A deployment environment identity is the reviewed conjunction of:

- OpenTTD source/behavior profile;
- environment version;
- scenario contract version;
- structured observation schema/digest;
- spatial schema/digest;
- preprocessing/normalization version and constants;
- action registry and mask schema/digest;
- reward version for provenance, even if reward is not used in playback;
- model architecture/output contract;
- ONNX opset/runtime compatibility; and
- package compatibility version.

The loader compares every required field before inference. Compatibility is not
inferred from tensor shape alone.

## Error and failure policy

- Programmer/contract violations fail fast in tests and debug builds.
- User package/configuration errors return actionable messages without starting
  control.
- Engine command rejection is a typed transition outcome, not an exception that
  corrupts the worker.
- Timeout/crash/invariant/nonfinite failures terminate the affected trajectory,
  retain the smallest useful artifact, and follow the configured run-stop policy.
- I/O failure for checkpoints, trajectories, or mandatory logs cannot be reported
  as successful persistence.
- Recovery never guesses whether an action executed. Process-isolated workers need
  an action/transition identity protocol or are restarted from the last confirmed
  boundary.

## Performance strategy

1. measure single-environment tick and encoder cost;
2. measure process-isolated rollout scaling;
3. batch inference on CPU and GPU;
4. profile PPO forward/backward/optimizer cost;
5. implement only dominant, batchable CUDA work;
6. compare correctness first, then throughput/latency/memory;
7. retain CPU fallbacks and publish the break-even batch size;
8. require at least one validated beneficial CUDA neural/tensor path for the
   accepted production trainer; and
9. never remove checks or alter engine stepping to manufacture speed.

Potential metrics include environment steps/s, simulation ticks/s, inference
latency distribution, rollout wait fraction, GPU occupancy/utilization, host-device
transfer bytes, optimizer time, peak CPU/GPU memory, worker restart rate, and
scenario-reset latency.

## Security and robustness boundary

Model packages, trajectory files, logs, and external AI content are untrusted
inputs at parse boundaries. Parsers require size/count limits, checked arithmetic,
canonical schema validation, digest checks, and fail-closed behavior. Model paths
must not escape the configured model root. Logs must not capture credentials or
the complete process environment.

Existing legacy P0 bounded-parser, fault-injection, and evidence practices should
be adapted where applicable, but their field/tape schemas are not automatically
the new environment interface.

## Decision status

The following architectural choices are accepted and now require their named gate
evidence:

- OpenTTD 15.3 exact source and external ordered patch series: ADR 0009 / `G01`;
- native synchronized bridge and one-environment-per-process model: ADR 0010 /
  `G03`;
- LibTorch 2.13 CUDA training, auxiliary ONNX export, and ONNX Runtime 1.28 CPU
  deployment: ADR 0011 / `G01`, `G08`, `G10`, and `G11`;
- content-addressed evidence and preregistered experiments: ADR 0012 / every gate;
  and
- integrated-program publication and dependency provenance: ADR 0008 / `G01` and
  `G12`.

The following still block their dependent production work and require later
ADRs/experiments:

1. action output representation and entity-slot policy;
2. road-path macro planner and atomicity;
3. observation feature/channel disposition and normalization;
4. reward V1 coefficients and episode horizon;
5. exact normal-game controller UI/inspection behavior;
6. reproducibility levels and numeric tolerances by device/backend; and
7. exact model-package schema, retention duration, and release locations.

No open decision may be resolved by implementation accident. The relevant gate
must record the decision, alternatives, evidence, and consequences.
