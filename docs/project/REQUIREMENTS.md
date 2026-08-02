# Project Requirements and Traceability

## Purpose and authority

This is the atomic requirements register for the OpenTTD reinforcement-learning
platform. It reconciles both user-provided briefs dated 2026-07-31. The shorter
brief establishes the conservative bus-only milestone and engineering principles;
the longer brief supplies the complete C++/CUDA PPO, evaluation, ONNX, and in-game
playback lifecycle. Where they overlap, the stricter verifiable condition applies.

The source inputs read for this planning reset were:

| Brief | Bytes | Lines | SHA-256 |
|---|---:|---:|---|
| Short goal brief (`pasted-text-1.txt`) | 2,124 | 106 | `03d14e26b4e0b438e419d6f834ca99025c5a980eecee4c536c0cda5f7243b92a` |
| Full platform brief (`pasted-text-2.txt`) | 19,339 | 759 | `a7da553035e44468f29184a69c014f16bd1439fcbdf77275d0762073da306492` |

The attachment paths are session inputs rather than durable repository interfaces;
the digests make the reconciliation basis auditable without making local Codex
attachment storage a build dependency.

`GOAL.md` controls scope and completion. This register makes that scope testable.
An implementation plan may split a row into smaller tasks, but may not merge rows
in a way that hides an unsatisfied requirement.

## Status vocabulary

| Status | Meaning |
|---|---|
| `NOT_STARTED` | No accepted implementation evidence exists. |
| `IN_PROGRESS` | Some implementation exists, but the stated evidence is incomplete. |
| `PASS` | The named acceptance evidence exists, was reviewed, and passes the applicable gate. |
| `BLOCKED` | A recorded external dependency prevents progress; this is not a waiver. |
| `DEFERRED_POST_V1` | Explicitly outside Version 1 and forbidden before its release gate. |
| `LEGACY_ONLY` | Related evidence exists, but it does not satisfy this bus-specific requirement. |

No row becomes `PASS` merely because a document, schema, generated file, or test
name exists. The referenced behavior must execute and the retained evidence must
cover the whole statement.

## Requirement ownership

| Prefix | Area | Primary plan |
|---|---|---|
| `SCOPE` | V1 world and gameplay boundary | environment contract |
| `LIFE` | end-to-end RL lifecycle | roadmap/architecture |
| `STACK` | language and acceleration constraints | architecture |
| `PPO` | PPO algorithm and operations | PPO/model plan |
| `OBS` | structured and spatial observations | environment contract |
| `ACT` | explicit actions and legality | environment contract |
| `REW` | reward semantics | environment contract |
| `AI` | existing AI baselines | verification plan |
| `MODEL` | checkpoint, ONNX, package, and playback | PPO/model plan |
| `RUN` | headless runtime | architecture/environment contract |
| `MON` | terminal monitor and logging | architecture/verification |
| `EVAL` | independent evaluation | verification plan |
| `REPRO` | experiment reproducibility | verification plan |
| `TEST` | mandatory test subjects | verification plan |
| `ARCH` | baseline architectures | PPO/model plan |
| `DONE` | release-level outcome | all governing plans |
| `EXP` | post-V1 expansion | roadmap |

## V1 scope and learned behavior

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `SCOPE-001` | Every V1 scenario is exactly 32 by 32 tiles. | Scenario-schema test and reset-run manifest. | `PASS` |
| `SCOPE-002` | Training and evaluation run OpenTTD without a graphical window. | Headless integration and long-run results. | `PASS` |
| `SCOPE-003` | Initial PPO training uses exactly one learning company. | Reset-state projection and company-count assertion. | `PASS` |
| `SCOPE-004` | V1 uses the default OpenTTD economy under a pinned settings profile. | Settings manifest and runtime projection. | `PASS` |
| `SCOPE-005` | Passengers are the only serviced cargo in V1. | Scenario validation and forbidden-cargo negative test. | `PASS` |
| `SCOPE-006` | Buses are the only operated vehicle type in V1. | Vehicle-pool validation and forbidden-vehicle tests. | `PASS` |
| `SCOPE-007` | Agent-built infrastructure is limited to roads, road-vehicle depots required for buses, and bus stops. | Command registry and forbidden-command tests. | `PASS` |
| `SCOPE-008` | V1 contains no trains or rail construction. | Action-schema absence and runtime invariant. | `PASS` |
| `SCOPE-009` | V1 contains no aircraft or airport construction. | Action-schema absence and runtime invariant. | `PASS` |
| `SCOPE-010` | V1 contains no ships or water-transport construction. | Action-schema absence and runtime invariant. | `PASS` |
| `SCOPE-011` | V1 contains no industrial cargo servicing. | Cargo-flow invariant and scenario audit. | `PASS` |
| `SCOPE-012` | V1 contains no NewGRFs or arbitrary mod content. | Content manifest and negative compatibility test. | `PASS` |
| `SCOPE-013` | V1 training contains no multiplayer or competitive company behavior. | Runtime settings and company invariant. | `PASS` |
| `SCOPE-014` | V1 disables disasters. | Settings/runtime assertion. | `PASS` |
| `SCOPE-015` | Seeds are fixed when requested, configurable, recorded, and applied to all owned RNG streams. | Seed contract tests and run manifest. | `PASS` |
| `SCOPE-016` | Scenario generation is reproducible from its versioned configuration and seed. | Independent repeated-reset digest campaign. | `PASS` |
| `SCOPE-017` | Evaluation is deterministic wherever the pinned OpenTTD engine permits; known nondeterminism is measured and disclosed. | Repeated evaluation report and exception ledger. | `PASS` |
| `SCOPE-018` | The agent can inspect towns, population/economic features, and road state through documented observations. | Observation semantic tests. | `PASS` |
| `SCOPE-019` | The agent can choose two towns or population centers to connect. | Action integration trajectory. | `PASS` |
| `SCOPE-020` | The agent can build required road segments or paths. | Native-command integration tests. | `PASS` |
| `SCOPE-021` | The agent can place valid bus stops and required depots. | Placement and legality integration tests. | `PASS` |
| `SCOPE-022` | The agent can purchase a bus. | Vehicle-purchase integration test. | `PASS` |
| `SCOPE-023` | The agent can create, assign, and update bus routes/orders. | Order-list integration tests. | `PASS` |
| `SCOPE-024` | The agent can start bus service. | Vehicle-state integration test. | `PASS` |
| `SCOPE-025` | The environment detects passenger delivery and resulting revenue. | Controlled delivery/economy test. | `NOT_STARTED` |
| `SCOPE-026` | The policy can be penalized for repeated invalid, wasteful, destructive, idle, or unprofitable behavior. | Reward-component scenario tests. | `NOT_STARTED` |
| `SCOPE-027` | A learned policy can maintain or improve a bus network over a multi-episode evaluation horizon. | Preregistered evaluation results. | `NOT_STARTED` |

## Complete platform lifecycle

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `LIFE-001` | Launch one headless OpenTTD environment through a stable programmatic interface. | Environment smoke test. | `PASS` |
| `LIFE-002` | Launch multiple isolated environments for batched rollout. | Isolation and batch integration test. | `PASS` |
| `LIFE-003` | Reset each environment to a controlled initial state. | Reset contract tests. | `PASS` |
| `LIFE-004` | Extract observations only at documented synchronization boundaries. | Boundary assertion and differential trace. | `PASS` |
| `LIFE-005` | Generate legal action masks matching the same state snapshot as the observation. | Mask oracle and stale-state tests. | `PASS` |
| `LIFE-006` | Apply selected actions through explicit OpenTTD operations. | Command-path integration evidence. | `PASS` |
| `LIFE-007` | Advance simulation by a configurable, deterministic stepping rule. | Tick-step tests. | `PASS` |
| `LIFE-008` | Calculate scalar reward from separately retained components. | Reward unit/integration evidence. | `NOT_STARTED` |
| `LIFE-009` | Record complete trajectories with schema and provenance. | Trajectory round-trip and resume tests. | `NOT_STARTED` |
| `LIFE-010` | Train actor-critic PPO policies in the production C++/CUDA path. | Trainer convergence and algorithm tests. | `NOT_STARTED` |
| `LIFE-011` | Evaluate saved policies in a process and dataset independent from training. | Evaluation run artifact. | `NOT_STARTED` |
| `LIFE-012` | Save native training checkpoints and recover from the declared boundary. | Interrupted-run recovery comparison. | `NOT_STARTED` |
| `LIFE-013` | Export compatible trained networks to ONNX. | Export gate result. | `NOT_STARTED` |
| `LIFE-014` | Convert or package an exported model for the in-game inference runtime. | Package schema and install test. | `NOT_STARTED` |
| `LIFE-015` | Load the package in a normal playable OpenTTD build. | In-game load/compatibility test. | `NOT_STARTED` |
| `LIFE-016` | Let a user visibly watch the policy control its bus company. | Documented end-to-end acceptance run. | `NOT_STARTED` |
| `LIFE-017` | Training, ONNX, and in-game paths share equivalent preprocessing, schemas, masks, and output interpretation. | Cross-runtime equivalence suite. | `NOT_STARTED` |

## Implementation stack and boundaries

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `STACK-001` | C++ owns core environment integration, control, training infrastructure, evaluation, export, and inference. | Build graph and source ownership audit. | `NOT_STARTED` |
| `STACK-002` | CUDA accelerates only workloads with a measured correctness-preserving benefit. | CPU baseline, profile, parity, and speed report. | `NOT_STARTED` |
| `STACK-003` | CUDA may cover batched inference, PPO optimization, tensor preprocessing, rollout processing, state encoding, evaluation, or CNN execution. | Per-kernel design and benchmark evidence. | `NOT_STARTED` |
| `STACK-004` | OpenTTD simulation remains on CPU unless an explicit semantic-parity gate approves a subsystem. | Architecture audit and parity result. | `NOT_STARTED` |
| `STACK-005` | Python remains auxiliary and is not the production environment or training authority. | Packaging/build/source audit. | `NOT_STARTED` |
| `STACK-006` | ONNX is the primary portable neural-network interchange format. | Export/package schema. | `NOT_STARTED` |
| `STACK-007` | The ONNX execution backend is pinned and explicitly validated. | Dependency manifest and equivalence tests. | `NOT_STARTED` |
| `STACK-008` | Initial spatial policies use CNNs; new architecture families require baseline validation first. | Model registry and roadmap gate. | `NOT_STARTED` |
| `STACK-009` | The OpenTTD/RL interface does not depend on screen scraping, simulated input, or menu navigation. | Source audit and integration design review. | `PASS` |
| `STACK-010` | Training-only dependencies are not required for normal in-game inference. | Clean inference-only build/install test. | `NOT_STARTED` |
| `STACK-011` | The accepted production training path uses at least one correctness-validated CUDA-accelerated neural/tensor workload with a measured benefit over its CPU reference on declared hardware. | CUDA parity and benchmark report. | `NOT_STARTED` |

## PPO algorithm and operational requirements

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `PPO-001` | The first trusted learner is actor-critic PPO. | Model/trainer design and smoke run. | `NOT_STARTED` |
| `PPO-002` | PPO implements the clipped policy objective. | Reference-vector unit and gradient test. | `NOT_STARTED` |
| `PPO-003` | PPO implements a configurable value-function loss. | Unit and optimization test. | `NOT_STARTED` |
| `PPO-004` | PPO implements entropy regularization. | Unit and configuration test. | `NOT_STARTED` |
| `PPO-005` | PPO implements Generalized Advantage Estimation. | Hand-computed and randomized differential tests. | `NOT_STARTED` |
| `PPO-006` | Advantages are normalized with defined zero-variance behavior. | Numerical edge-case test. | `NOT_STARTED` |
| `PPO-007` | Rollout length is configurable and recorded. | Configuration/trajectory test. | `NOT_STARTED` |
| `PPO-008` | Minibatch size is configurable and validated against rollout shape. | Boundary and shuffle tests. | `NOT_STARTED` |
| `PPO-009` | Optimization epoch count is configurable and recorded. | Trainer configuration test. | `NOT_STARTED` |
| `PPO-010` | Gradient clipping is implemented and measured. | Synthetic-gradient test and metric. | `NOT_STARTED` |
| `PPO-011` | Learning rate is configurable and logged. | Scheduler/configuration test. | `NOT_STARTED` |
| `PPO-012` | Native checkpoints include model, optimizer, counters, RNG state, schemas, and configuration. | Checkpoint schema/round-trip test. | `NOT_STARTED` |
| `PPO-013` | Checkpoint recovery resumes from a precisely documented update boundary. | Interrupted/uninterrupted comparison. | `NOT_STARTED` |
| `PPO-014` | Evaluation mode disables training updates and supports deterministic greedy action selection. | Read-only evaluation and repeat test. | `NOT_STARTED` |
| `PPO-015` | Rollout collection supports batched environments. | Batch-shape/isolation test. | `NOT_STARTED` |
| `PPO-016` | Illegal actions receive no sampling probability after masking. | Extreme-logit and all-mask edge tests. | `NOT_STARTED` |
| `PPO-017` | All PPO-owned RNG streams have reproducible independent seeds. | Seed-sweep determinism test. | `NOT_STARTED` |
| `PPO-018` | Losses, activations, gradients, parameters, advantages, and returns are checked for NaN and infinity. | Fault-injection tests. | `NOT_STARTED` |
| `PPO-019` | Numerical failures stop safely and retain a diagnostic checkpoint/artifact. | Failure-path integration test. | `NOT_STARTED` |
| `PPO-020` | Training and evaluation metrics are emitted to structured logs. | Metrics-schema and accuracy tests. | `NOT_STARTED` |
| `PPO-021` | The trainer exports inference networks and required metadata. | Model pipeline gate. | `NOT_STARTED` |
| `PPO-022` | No second RL algorithm is implemented before PPO and V1 gates pass. | Dependency/source audit. | `NOT_STARTED` |

## Observation requirements

All optional feature candidates below must be dispositioned before the observation
schema freezes: included with exact semantics, or excluded with a reviewed reason.
An omitted candidate is not silently assumed irrelevant.

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `OBS-001` | The schema supports structured features and map-aligned spatial channels. | Versioned schemas and encoder tests. | `PASS` |
| `OBS-002` | Company balance, loan, income, and expenses are dispositioned and, if included, precisely scaled. | Feature registry rows and value tests. | `PASS` |
| `OBS-003` | Bus count, station count, and infrastructure ownership are dispositioned. | Registry and controlled-state tests. | `PASS` |
| `OBS-004` | Vehicle profitability and route status are dispositioned without future leakage. | Registry and temporal test. | `PASS` |
| `OBS-005` | Town population, passenger production, and passenger ratings are dispositioned. | Registry and engine-state comparison. | `PASS` |
| `OBS-006` | Current date and remaining action budget are dispositioned. | Registry and boundary tests. | `PASS` |
| `OBS-007` | Recent reward components, if observed, use only causal history available in deployment. | Temporal/no-leakage test. | `PASS` |
| `OBS-008` | Terrain and water spatial channels are dispositioned. | Per-tile fixtures and channel digest. | `PASS` |
| `OBS-009` | Roads and company-owned roads are dispositioned separately where ownership matters. | Per-tile fixtures and ownership test. | `PASS` |
| `OBS-010` | Buildings, town influence, and population density are dispositioned. | Synthetic-map semantic tests. | `PASS` |
| `OBS-011` | Passenger production and station catchment are dispositioned spatially. | Catchment/production fixture tests. | `PASS` |
| `OBS-012` | Bus stops, route occupancy, and vehicle locations are dispositioned spatially. | Controlled route snapshot tests. | `PASS` |
| `OBS-013` | Buildable tiles, blocked tiles, and ownership are dispositioned spatially. | Legality/encoder differential tests. | `PASS` |
| `OBS-014` | Every feature/channel defines semantic source, shape, type, scale, normalization, missing-value rule, and update boundary. | Schema lint and review. | `PASS` |
| `OBS-015` | Spatial tensors have an explicit coordinate origin, axis order, channel order, and tile-to-index mapping. | Pattern-map orientation tests. | `PASS` |
| `OBS-016` | Observation extraction has no mutation, RNG consumption, pathfinding side effect, or lazy-state perturbation. | Instrumented non-perturbation test. | `PASS` |
| `OBS-017` | Training, evaluator, ONNX, and in-game paths use the same encoder implementation or byte-equivalent fixtures. | Cross-runtime golden vectors. | `PASS` |
| `OBS-018` | MLP, CNN, and combined comparisons use equivalent seeds, settings, budgets, and evaluation protocols. | Matched experiment manifest. | `NOT_STARTED` |

## Action and legality requirements

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `ACT-001` | Actions are explicit typed operations, never uncontrolled GUI imitation. | Versioned registry and source audit. | `PASS` |
| `ACT-002` | The action schema includes a no-op/wait action with defined tick cost. | Schema and step test. | `PASS` |
| `ACT-003` | The agent can select origin and destination towns through bounded, stable parameters. | Schema and town-slot tests. | `PASS` |
| `ACT-004` | The agent can build a road segment or reviewed deterministic road-path macro. | Native-command and atomicity tests. | `PASS` |
| `ACT-005` | The agent can place a bus stop with explicit tile/orientation semantics. | Placement tests. | `PASS` |
| `ACT-006` | The agent can construct the road-vehicle depot required to buy a bus. | Depot tests. | `PASS` |
| `ACT-007` | The agent can purchase a bus under a defined engine-selection policy. | Purchase/cost tests. | `PASS` |
| `ACT-008` | The agent can create and assign vehicle orders/routes. | Order identity and assignment tests. | `PASS` |
| `ACT-009` | The agent can start and stop a vehicle. | Vehicle-state test. | `PASS` |
| `ACT-010` | Sell-vehicle behavior is dispositioned before schema freeze. | Registry row and lifecycle tests. | `PASS` |
| `ACT-011` | Removal of owned invalid or unnecessary infrastructure is dispositioned before schema freeze. | Registry row and ownership tests. | `PASS` |
| `ACT-012` | Loan take/repay actions are dispositioned before schema freeze. | Registry row and economy tests. | `PASS` |
| `ACT-013` | Each action defines parameter domain, legal preconditions, failure modes, native operations, tick/cost semantics, reward effects, and log encoding. | Action registry lint and tests. | `PASS` |
| `ACT-014` | Known-illegal action instances are masked before policy sampling. | Mask differential test. | `PASS` |
| `ACT-015` | Legal action generation is deterministic and bounded for any valid V1 state. | Repeat/property/resource tests. | `PASS` |
| `ACT-016` | Multi-command macro actions are atomic from the agent perspective or expose explicit partial results and rollback policy. | Injected-failure tests. | `PASS` |
| `ACT-017` | Execution distinguishes legal success, stale-state failure, illegal action, no-op, and internal integration failure. | Outcome-enum tests and logs. | `PASS` |
| `ACT-018` | A mask/action schema mismatch fails closed and cannot silently remap logits. | Compatibility negative tests. | `PASS` |
| `ACT-019` | All-masked states have one documented safe resolution and never sample an invalid index. | Edge-case test. | `PASS` |
| `ACT-020` | Action IDs and parameter interpretation remain stable within a compatibility version. | Schema compatibility tests. | `PASS` |

## Reward requirements

Reward candidates must be individually dispositioned before reward-version freeze.
Included terms require exact units, timing, clipping, weighting, and exploit tests.

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `REW-001` | Operating profit, passenger delivery, transported-passenger growth, station-rating improvement, route profitability, utilization, productive expansion, and long-term company value are each reviewed as positive candidates. | Reward design ledger. | `NOT_STARTED` |
| `REW-002` | Bankruptcy, invalid action, repeated construction failure, idle vehicle, unused station, excessive infrastructure spend, valueless route duplication, vehicle loss, destructive loops, and excessive no-op behavior are each reviewed as penalty candidates. | Reward design ledger. | `NOT_STARTED` |
| `REW-003` | Every included reward component is separately calculated and logged before aggregation. | Component schema and accuracy tests. | `NOT_STARTED` |
| `REW-004` | Reward uses deltas over documented boundaries and does not repeatedly pay an unchanged cumulative statistic. | Temporal unit tests. | `NOT_STARTED` |
| `REW-005` | Scalar aggregation is versioned, configured, and provenance-recorded. | Config/schema test. | `NOT_STARTED` |
| `REW-006` | Reward does not use deployment-unavailable privileged information. | Feature/reward information audit. | `NOT_STARTED` |
| `REW-007` | Reward has explicit tests for farming, cycling, construction/destruction, duplication, idling, bankruptcy avoidance, and no-op exploits. | Adversarial scenario suite. | `NOT_STARTED` |
| `REW-008` | Training reward is not accepted as the sole model-quality measure. | Independent evaluation gate. | `NOT_STARTED` |

## Existing AI and scripted baseline requirements

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `AI-001` | The platform can run an existing OpenTTD AI or scripted agent in at least one isolated baseline/evaluation workflow. | Reproducible baseline run. | `NOT_STARTED` |
| `AI-002` | Supported uses are dispositioned: economic comparison, learning-progress baseline, demonstrations, imitation data, curriculum, stress test, robustness, shared-map competition, and non-neural baseline. | Baseline registry. | `NOT_STARTED` |
| `AI-003` | Every external AI record includes name, version, source, configuration, seed, transport support, limitations, scenario, and result. | Schema-valid baseline manifest. | `NOT_STARTED` |
| `AI-004` | An established AI is not presumed correct; its behavior is measured and limitations are reported. | Baseline review and anomaly log. | `NOT_STARTED` |
| `AI-005` | Initial PPO training does not depend on competitive multiplayer behavior. | Trainer scenario audit. | `NOT_STARTED` |
| `AI-006` | Competitive evaluation remains post-single-company-stability work. | Roadmap gate enforcement. | `NOT_STARTED` |

## Model, package, equivalence, and in-game requirements

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `MODEL-001` | Every architecture has a stable identifier and versioned definition. | Model registry. | `NOT_STARTED` |
| `MODEL-002` | Native training checkpoints are distinct from deployment packages. | File schemas and round-trip tests. | `NOT_STARTED` |
| `MODEL-003` | Export includes all inference outputs required by deployment, including policy and value outputs. | ONNX graph inspection. | `NOT_STARTED` |
| `MODEL-004` | Each package contains ONNX bytes, model version, architecture ID, observation schema, spatial schema, input shapes/types, normalization, action schema, mask schema, output definitions, training commit/config, OpenTTD commit, environment version, seeds, evaluation results, and compatibility version. | Package-schema validation. | `NOT_STARTED` |
| `MODEL-005` | Every packaged file has a cryptographic digest and the manifest covers the complete package. | Package integrity test. | `NOT_STARTED` |
| `MODEL-006` | Incompatible environment, schema, runtime, or game versions fail clearly before control begins. | Compatibility mutation tests. | `NOT_STARTED` |
| `MODEL-007` | Native, ONNX, and in-game inference compare policy logits, probabilities, values, masks, greedy actions, and recurrent state if introduced. | Equivalence report. | `NOT_STARTED` |
| `MODEL-008` | Sampled-action distributions are statistically compared under a preregistered tolerance and sample count. | Distribution-test artifact. | `NOT_STARTED` |
| `MODEL-009` | Numerical tolerances are justified, versioned, and reject out-of-bound exports. | Tolerance ADR and negative tests. | `NOT_STARTED` |
| `MODEL-010` | The documented workflow covers train, export, validate, package install, launch, agent selection/configuration, game start, and visible play. | Clean-machine acceptance run. | `NOT_STARTED` |
| `MODEL-011` | In-game inference supports deterministic greedy mode. | Repeated playback test. | `NOT_STARTED` |
| `MODEL-012` | In-game inference may use an explicitly seeded stochastic mode. | Configuration and distribution test. | `NOT_STARTED` |
| `MODEL-013` | Inference interval is adjustable within validated safe bounds. | Boundary/timing tests. | `NOT_STARTED` |
| `MODEL-014` | Playback exposes model metadata and actionable compatibility errors. | UI/console acceptance tests. | `NOT_STARTED` |
| `MODEL-015` | Playback supports optional action logging and optional debug overlays. | Configuration and render/trace tests. | `NOT_STARTED` |
| `MODEL-016` | Playback provides pause and step controls where engine integration makes them practical; unsupported cases are documented. | Control test or reviewed disposition. | `NOT_STARTED` |
| `MODEL-017` | Inspection mode reports current action, confidence, value, legal action count, reward-relevant state, route target, model name, and version. | Inspection-output accuracy tests. | `NOT_STARTED` |
| `MODEL-018` | Normal in-game inference installs without trainer, optimizer, or CUDA-training dependencies. | Inference-only package test. | `NOT_STARTED` |

## Headless runtime and monitoring requirements

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `RUN-001` | Runtime supports single- and multi-environment modes. | Integration tests. | `PASS` |
| `RUN-002` | Simulation speed and tick stepping are configurable and recorded. | Step contract tests. | `PASS` |
| `RUN-003` | Runtime supports controlled pause, resume, and reset. | State-machine tests. | `PASS` |
| `RUN-004` | Runtime supports seeded scenario generation. | Reproducibility campaign. | `PASS` |
| `RUN-005` | Environment crashes are detected, classified, and recovered or fail closed without corrupting the run. | Crash fault-injection test. | `PASS` |
| `RUN-006` | Training resumes from valid checkpoints after process interruption. | Recovery campaign. | `NOT_STARTED` |
| `RUN-007` | Logs are structured, schema-versioned, bounded, and usable non-interactively. | Log schema/resource tests. | `NOT_STARTED` |
| `RUN-008` | Runtime supports batch evaluation and long unattended runs. | Evaluation and soak results. | `NOT_STARTED` |
| `RUN-009` | CPU/GPU/environment performance can be profiled without changing authoritative semantics. | Profile on/off parity test. | `NOT_STARTED` |
| `RUN-010` | The OpenTTD/RL interface is stable, versioned, and synchronized. | ABI/API contract tests. | `PASS` |
| `MON-001` | Interactive monitor remains readable over SSH and in tmux. | Terminal acceptance capture. | `NOT_STARTED` |
| `MON-002` | Monitor shows run name, repository commit, OpenTTD version, environment version, seed, environment count, and device. | Metric-source accuracy test. | `NOT_STARTED` |
| `MON-003` | Monitor shows elapsed time, environment steps, simulation ticks, steps/second, and updates. | Counter accuracy test. | `NOT_STARTED` |
| `MON-004` | Monitor shows policy loss, value loss, entropy, approximate KL, clip fraction, explained variance, and learning rate. | Trainer-metric test. | `NOT_STARTED` |
| `MON-005` | Monitor shows mean episodic return/length, company profit, passenger deliveries, vehicles, routes, invalid actions, mask violations, and resets. | Aggregation accuracy test. | `NOT_STARTED` |
| `MON-006` | Monitor shows checkpoint, best evaluation score, GPU utilization/memory when available, CPU utilization, process memory, and warning state. | System/metric-source tests. | `NOT_STARTED` |
| `MON-007` | Missing hardware telemetry is shown as unavailable, never fabricated or coerced to zero. | No-GPU/permission negative tests. | `NOT_STARTED` |
| `MON-008` | Every important monitor value is also written to structured logs. | Display/log correspondence test. | `NOT_STARTED` |
| `MON-009` | Non-interactive mode is suitable for files, CI, automated experiments, and external trackers. | Pipe/file/CI acceptance tests. | `NOT_STARTED` |

## Evaluation and research requirements

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `EVAL-001` | Evaluation is independent from training and cannot update policy or normalization state. | Read-only evaluator test. | `NOT_STARTED` |
| `EVAL-002` | The evaluation suite includes fixed seeds and unseen seeds. | Scenario manifest/results. | `NOT_STARTED` |
| `EVAL-003` | It includes multiple town layouts and passenger distributions. | Scenario manifest/results. | `NOT_STARTED` |
| `EVAL-004` | It includes reviewed starting-balance and horizon variations. | Scenario manifest/results. | `NOT_STARTED` |
| `EVAL-005` | It evaluates greedy and explicitly seeded stochastic policies. | Mode-comparison report. | `NOT_STARTED` |
| `EVAL-006` | It compares random, trivial scripted, and at least one existing-AI baseline where scenario support permits. | Baseline report. | `NOT_STARTED` |
| `EVAL-007` | It compares structured MLP, spatial CNN, and combined architectures with matched budgets. | Architecture report. | `NOT_STARTED` |
| `EVAL-008` | It tests robustness to minor in-scope environment variation. | Robustness report. | `NOT_STARTED` |
| `EVAL-009` | Metrics disposition survival, bankruptcy, final balance, net/operating profit, passenger deliveries, route profit, profitable vehicles, infrastructure cost, ROI, station rating, coverage, invalid actions, action efficiency, and seed stability. | Metric registry and report. | `NOT_STARTED` |
| `EVAL-010` | Primary success metrics and superiority thresholds are preregistered before the final comparison. | Reviewed evaluation protocol. | `NOT_STARTED` |
| `EVAL-011` | Claims report confidence intervals or seed-level dispersion and do not rely on a best seed. | Statistical report lint. | `NOT_STARTED` |
| `EVAL-012` | At least one learned policy is superior to random and trivial scripted baselines under the preregistered protocol. | Final V1 evaluation gate. | `NOT_STARTED` |
| `EVAL-013` | At least one learned policy reliably operates profitably across the preregistered deterministic evaluation set, under explicit profit and stability thresholds. | Final profitability/reliability report. | `NOT_STARTED` |

## Reproducibility and provenance requirements

Every accepted training or evaluation run records the following. Unknown values
are errors unless a reviewed schema explicitly marks them inapplicable.

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `REPRO-001` | Record outer repository commit, dirty-state policy, and OpenTTD upstream commit. | Run manifest validation. | `NOT_STARTED` |
| `REPRO-002` | Record build configuration, compiler version, operating system, CPU model, GPU model, and CUDA version when applicable. | Run manifest validation. | `NOT_STARTED` |
| `REPRO-003` | Record PPO configuration and neural architecture identifier/configuration. | Run manifest validation. | `NOT_STARTED` |
| `REPRO-004` | Record observation, action, mask, reward, environment, and compatibility schema versions/digests. | Run manifest validation. | `NOT_STARTED` |
| `REPRO-005` | Record all scenario, environment, model initialization, sampling, shuffle, and evaluation seeds. | Seed-ledger validation. | `NOT_STARTED` |
| `REPRO-006` | Record wall duration, environment steps, simulation ticks, updates, and evaluation results. | Counter/log validation. | `NOT_STARTED` |
| `REPRO-007` | Record hashes of checkpoints and exported model packages. | Artifact-manifest validation. | `NOT_STARTED` |
| `REPRO-008` | A model lacking required provenance cannot become an accepted research artifact. | Package rejection test. | `NOT_STARTED` |
| `REPRO-009` | Documentation reconstructs the complete accepted workflow from a clean supported host. | Independent reproduction report. | `NOT_STARTED` |

## Mandatory test subjects

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `TEST-001` | Test environment reset and seed reproducibility. | Unit/integration/repeat campaign. | `PASS` |
| `TEST-002` | Test observation extraction, normalization, and every spatial channel. | Golden/differential tests. | `PASS` |
| `TEST-003` | Test action encoding, decoding, legality, and masking. | Unit/property/integration tests. | `PASS` |
| `TEST-004` | Test every reward component and scalar aggregation. | Unit/scenario tests. | `NOT_STARTED` |
| `TEST-005` | Test tick stepping and game-state synchronization. | Boundary/differential tests. | `PASS` |
| `TEST-006` | Test bus purchasing, depot/stop placement, road construction, route creation, order assignment, and vehicle start. | Actual OpenTTD integration tests. | `PASS` |
| `TEST-007` | Test passenger delivery and profit calculation against actual OpenTTD state. | Controlled economic integration tests. | `NOT_STARTED` |
| `TEST-008` | Test bankruptcy and every episode termination/truncation reason. | Scenario tests. | `NOT_STARTED` |
| `TEST-009` | Test PPO advantages, clipping, losses, minibatching, shuffling, masking, gradients, and optimizer updates. | Reference-vector and differential tests. | `NOT_STARTED` |
| `TEST-010` | Test checkpoint save, reload, incompatibility, and interruption recovery. | Round-trip/recovery tests. | `NOT_STARTED` |
| `TEST-011` | Test ONNX export and native/ONNX/in-game equivalence. | Cross-runtime gate. | `NOT_STARTED` |
| `TEST-012` | Test incompatible model rejection for every compatibility field. | Mutation matrix. | `NOT_STARTED` |
| `TEST-013` | Test headless long-run stability and desynchronization detection. | Soak and fault campaign. | `NOT_STARTED` |
| `TEST-014` | Test every CLI metric against its authoritative counter/source. | Monitor accuracy suite. | `NOT_STARTED` |
| `TEST-015` | Critical gameplay behavior has both code-level assertions and actual-engine integration coverage. | Traceability lint. | `PASS` |
| `TEST-016` | Release gates include sanitizer, static-analysis, resource-bound, malformed-input, and failure-artifact checks appropriate to changed native code. | Quality-matrix result. | `NOT_STARTED` |

## Required architecture comparison

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `ARCH-001` | Baseline A is a structured MLP using company, town, vehicle, route, and simplified map-summary features. | Model definition and train/eval run. | `NOT_STARTED` |
| `ARCH-002` | Baseline B is a CNN using the versioned multi-channel 32 by 32 map tensor. | Model definition and train/eval run. | `NOT_STARTED` |
| `ARCH-003` | Baseline C combines CNN spatial features with structured numerical features. | Model definition and train/eval run. | `NOT_STARTED` |
| `ARCH-004` | The comparison measures economic quality, computational cost, and sample efficiency. | Matched report. | `NOT_STARTED` |
| `ARCH-005` | No architecture is declared superior without multiple seeds and matched training/evaluation budgets. | Experiment-manifest lint. | `NOT_STARTED` |

## V1 release assertions

These rows summarize conjunctions; they do not replace lower-level rows.

| ID | Normative requirement | Acceptance evidence | Status |
|---|---|---|---|
| `DONE-001` | All V1 scope, lifecycle, environment, PPO, model, runtime, monitoring, evaluation, reproducibility, and test rows pass. | Machine-generated traceability closure plus review. | `NOT_STARTED` |
| `DONE-002` | Extended training has no unresolved desynchronization or numerical defect. | Soak reports and zero release-blocking ledger entries. | `NOT_STARTED` |
| `DONE-003` | At least one policy passes both baseline superiority (`EVAL-012`) and reliable profitability (`EVAL-013`). | Final independent evaluation report. | `NOT_STARTED` |
| `DONE-004` | MLP, CNN, and combined models are trainable and the required matched comparison is complete. | Architecture comparison report. | `NOT_STARTED` |
| `DONE-005` | Existing AI support passes `AI-001` through `AI-004`. | Baseline workflow report. | `NOT_STARTED` |
| `DONE-006` | The complete model pipeline passes export, package, equivalence, rejection, install, and visible-play gates. | End-to-end acceptance bundle. | `NOT_STARTED` |
| `DONE-007` | A clean supported host can reproduce the documented workflow. | Independent reproduction evidence. | `NOT_STARTED` |
| `DONE-008` | No known correctness defect can invalidate accepted results. | Reviewed defect ledger and final gate. | `NOT_STARTED` |

## Post-V1 expansion requirements

| ID | Normative requirement | Gate | Status |
|---|---|---|---|
| `EXP-001` | Add more varied 32 by 32 passenger-bus scenarios, curricula, AI baselines, reward analysis, and generalization. | Only after all `DONE-*` pass. | `DEFERRED_POST_V1` |
| `EXP-002` | Add larger maps, more towns, and longer horizons. | After `EXP-001`. | `DEFERRED_POST_V1` |
| `EXP-003` | Add mail and passenger/mail coordination. | After larger-map regression gates. | `DEFERRED_POST_V1` |
| `EXP-004` | Add trucks, industries, cargo types, and production chains. | After mail-stage regression gates. | `DEFERRED_POST_V1` |
| `EXP-005` | Add trains, track, signals, stations, and scheduling. | After road-cargo regression gates. | `DEFERRED_POST_V1` |
| `EXP-006` | Add ships and water transportation. | After rail regression gates. | `DEFERRED_POST_V1` |
| `EXP-007` | Add aircraft and multimodal transportation. | After ship-stage regression gates. | `DEFERRED_POST_V1` |
| `EXP-008` | Add competitive companies, AI opponents, and multi-agent evaluation. | After multimodal single-agent gates. | `DEFERRED_POST_V1` |
| `EXP-009` | Add broad gameplay, generalist policies, larger architectures, and benchmark releases. | After all preceding expansion gates. | `DEFERRED_POST_V1` |
| `EXP-010` | Every expansion preserves executable and evaluable prior stages. | Full regression matrix at each stage. | `DEFERRED_POST_V1` |

## Explicit V1 non-goals

Before `DONE-001` passes, the following are forbidden product work: full OpenTTD
play, additional transport types or cargo systems, competitive multiplayer,
large-map training, NewGRF/mod compatibility, human-level general play,
language-model control, rendered-screen vision, mouse/keyboard imitation,
multi-machine distributed training, multiple RL algorithms, complex hierarchical
agents, and perfect economic optimization.

Exploratory notes are allowed only when labeled non-implementation and when they
do not delay or alter the V1 critical path.

## Traceability closure rule

Before a milestone or release can pass:

1. every applicable row must name concrete implementation ownership, tests, and
   retained evidence in `docs/project/requirements-v1.json`;
2. every test must point back to the requirements it proves;
3. every `PASS` must be contradicted by neither an open defect nor a failed later
   regression;
4. aggregate `DONE-*` rows pass only as the verified conjunction of their
   underlying rows; and
5. a legacy P0 artifact may be cited as supporting evidence, but bus-specific
   acceptance remains independently required.

## Source-brief coverage audit

This table is a completeness index from the two supplied briefs into the atomic
register. It does not replace the individual rows.

| Source brief section | Governing requirements/evidence |
|---|---|
| Short brief: primary objective and engineering principles | `GOAL.md`, `LIFE-*`, `REPRO-*`, `TEST-*`, `DONE-*` |
| Short brief: 32x32/default economy/single company/passenger buses and exclusions | `SCOPE-001` through `SCOPE-017` |
| Short brief: roads, stops, buses, connections, profit, maintenance | `SCOPE-018` through `SCOPE-027`, `EVAL-013` |
| Short brief: staged expansion through full gameplay | `EXP-001` through `EXP-010` |
| Short brief: reliably profitable deterministic V1 success | `EVAL-010` through `EVAL-013`, `DONE-003`, `DONE-008` |
| Full brief: platform objective and complete RL lifecycle | `LIFE-001` through `LIFE-017` |
| Full brief: C++/CUDA/ONNX/PPO/CNN stack and justified acceleration | `STACK-001` through `STACK-011`, `PPO-*`, `ARCH-*` |
| Full brief: PPO feature list | `PPO-001` through `PPO-022` |
| Full brief: structured/spatial observations and comparison | `OBS-001` through `OBS-018`, `ARCH-001` through `ARCH-005` |
| Full brief: explicit actions, definitions, masks, and outcomes | `ACT-001` through `ACT-020` |
| Full brief: positive/negative rewards and information boundary | `REW-001` through `REW-008` |
| Full brief: existing AIs, uses, metadata, and competition timing | `AI-001` through `AI-006` |
| Full brief: model lifecycle, package contents, and incompatibility | `MODEL-001` through `MODEL-006`, `MODEL-010`, `MODEL-018` |
| Full brief: native/ONNX/in-game equivalence and tolerances | `MODEL-007` through `MODEL-009`, `TEST-011`, `TEST-012` |
| Full brief: headless runtime | `RUN-001` through `RUN-010`, `LIFE-001` through `LIFE-009` |
| Full brief: CLI monitor and non-interactive logs | `MON-001` through `MON-009`, `PPO-020` |
| Full brief: in-game workflow, controls, and inspection | `MODEL-010` through `MODEL-018` |
| Full brief: independent scenarios, baselines, metrics, robustness | `EVAL-001` through `EVAL-013` |
| Full brief: experiment provenance | `REPRO-001` through `REPRO-009` |
| Full brief: mandatory test inventory | `TEST-001` through `TEST-016` plus the finer owning rows |
| Full brief: MLP/CNN/combined research comparison | `ARCH-001` through `ARCH-005`, `OBS-018`, `EVAL-007` |
| Full brief: expansion roadmap | `EXP-001` through `EXP-010` |
| Full brief: Version 1 non-goals | “Explicit V1 non-goals” plus `SCOPE-*`/`EXP-*` gate policy |
| Full brief: Definition of Done | `DONE-001` through `DONE-008` as conjunctions of all lower rows |
