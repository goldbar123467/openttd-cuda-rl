# OpenTTD Reinforcement Learning Platform

## Document status

- Status: project authority
- Scope: the complete project; Version 1 is released and Version 2 is active
- Last reconciled with the user-provided Version 2 expansion brief: 2026-08-02
- Change rule: narrowing Version 2's map, transport, cargo, competition, or
  broad-gameplay scope, or weakening an accepted Version 1 invariant, requires an
  explicit reviewed change to this document and the applicable requirements
  matrix.

This document defines what the repository is trying to build. Detailed designs,
phase plans, historical reports, and implementation notes may refine how it is
built, but may not narrow or contradict this goal.

## Primary objective

Build a headless reinforcement-learning research platform around OpenTTD that can
train, evaluate, export, package, and visually replay neural-network agents.

The first complete environment is a constrained, reproducible 32 by 32 scenario
in which one learning company builds and operates passenger bus networks. The core
runtime and production training path are C++ and CUDA. PPO is the first and only
required learning algorithm. ONNX is the portable model format, and a validated
in-game inference path must let a user watch the trained policy operate a company
inside a normal OpenTTD session.

Correctness, determinism, reproducibility, observability, and end-to-end usability
take precedence over breadth and headline throughput.

## Version 1 environment boundary

Version 1 is restricted to:

- a 32 by 32 map;
- headless OpenTTD execution for training and evaluation;
- one learning company during initial training;
- the default OpenTTD economy and original base content;
- passengers only;
- buses only;
- roads, road-vehicle depots, and bus stops only;
- fixed, configurable seeds and reproducible scenario generation;
- deterministic evaluation conditions wherever the pinned OpenTTD engine permits
  deterministic execution;
- no trains, aircraft, ships, mail, trucks, industrial cargo, NewGRFs,
  multiplayer, disasters, arbitrary mods, screenshot vision, or simulated mouse
  and keyboard control.

Road-vehicle depots are included because OpenTTD requires them to purchase buses;
they are operational bus infrastructure, not a new transport system.

Existing AIs may be loaded in isolated baseline or evaluation workflows after the
single-company environment is stable. They are not required competitors during
initial PPO training, and their presence must not silently change the training
contract.

The agent must be able to:

1. inspect towns, economic state, and the road network;
2. choose population centers to connect;
3. build or extend roads;
4. build required depots and place valid bus stops;
5. purchase buses;
6. create and assign routes and orders;
7. start service;
8. deliver passengers and generate revenue;
9. avoid repeated invalid, wasteful, destructive, or unprofitable actions; and
10. maintain or improve a profitable network over time.

## Required reinforcement-learning lifecycle

The completed platform must provide one coherent workflow that can:

1. launch one or more headless OpenTTD environments;
2. reset them to controlled initial states;
3. extract versioned structured and spatial observations;
4. construct legal action masks;
5. execute explicit game actions through a stable non-visual interface;
6. advance a configurable number of simulation ticks;
7. calculate and separately log versioned reward components;
8. record trajectories;
9. train PPO actor-critic policies, including batched environments;
10. save and recover checkpoints;
11. evaluate saved policies independently from training;
12. export trained networks to ONNX;
13. prove native, ONNX, and in-game inference equivalence within reviewed
    numerical tolerances;
14. package model, schema, compatibility, provenance, and evaluation metadata;
15. load a compatible package into a playable OpenTTD build; and
16. let a user inspect and watch the trained policy operate the bus company.

Training and in-game inference must use the same versioned observation schema,
preprocessing, normalization, action definitions, action masking semantics, and
model-output interpretation. Compatibility failures must be explicit and fail
closed.

## Implementation constraints

- C++ owns OpenTTD integration, environment control, state encoding, action
  execution, inference, evaluation, training infrastructure, model packaging, and
  the production PPO path.
- CUDA is used only for measured workloads that benefit from it, such as batched
  neural inference, PPO optimization, tensor preprocessing, rollout processing,
  state encoding, CNN execution, or large-scale evaluation.
- OpenTTD simulation remains on the CPU unless a separately proven acceleration
  preserves engine semantics.
- Python is auxiliary: analysis, plotting, debugging, offline inspection,
  conversion support, or experiment tooling. It is not the authoritative
  production environment or trainer.
- ONNX is the portable interchange format. The selected runtime must be pinned,
  tested, and supported in the documented inference deployment.
- The engine/RL boundary must not use screen scraping, GUI automation, or brittle
  menu navigation.
- One trusted PPO implementation must be completed and validated before any
  additional learning algorithm is considered.

## Required model baselines

Version 1 must train and evaluate:

- a structured-feature multilayer perceptron;
- a convolutional network over the versioned 32 by 32 spatial tensor; and
- a combined model using both inputs.

Claims comparing them require matched scenario distributions, seeds, environment
settings, training budgets, evaluation horizons, and reporting. At least the MLP
and CNN must be directly compared for Version 1 completion; the combined model is
part of the required architecture comparison and may not be silently omitted.

## Engineering principles

- Correctness before optimization.
- Deterministic execution and explicit seed ownership.
- Reproducible, provenance-complete experiments.
- Modular architecture and stable, versioned contracts.
- Automated unit, integration, differential, long-run, and end-to-end testing.
- Independent evaluation; training reward is never the sole quality measure.
- Clean separation between OpenTTD engine semantics and RL policy code.
- No deployment-only or training-only semantic drift.
- No hidden privileged observation that is unavailable to the deployed model.
- Structured logs are authoritative; a terminal UI is only a view of them.
- New features preserve all prior-stage behavior and evaluation capability.
- Unverified success is reported as incomplete, not inferred from plausible
  outputs.

## Version 1 definition of done

Version 1 is complete only when all of the following are true:

- the constrained 32 by 32 passenger-bus environment runs headlessly;
- controlled resets and fixed-seed evaluation are reproducible;
- observation, spatial-channel, normalization, action, action-mask, reward,
  termination, and stepping schemas are versioned and tested;
- game-state synchronization and legal-action masking are reliable;
- bus infrastructure, purchasing, routing, service, passenger delivery, economic
  accounting, bankruptcy, and episode termination are integration-tested against
  actual OpenTTD execution;
- PPO supports the complete required algorithm and operational feature set and
  trains without numerical failure;
- at least one learned policy outperforms random and trivial scripted baselines on
  a preregistered independent evaluation suite;
- structured MLP, spatial CNN, and combined policies can be trained, and the MLP
  and CNN comparison is reported over matched budgets and multiple seeds;
- at least one existing OpenTTD AI participates in a documented evaluation,
  baseline, demonstration, curriculum, or stress-test workflow;
- extended training runs do not exhibit unresolved environment desynchronization;
- an SSH- and tmux-readable monitor reports accurate live state while the same
  metrics are retained in structured non-interactive logs;
- checkpoints are saved, recovered, and proven to resume consistently at their
  declared recovery boundary;
- a trained policy exports to a provenance-complete ONNX model package;
- native, ONNX, and in-game outputs pass equivalence tests;
- incompatible packages are rejected with actionable errors;
- a user can follow the documentation from build through training, evaluation,
  export, installation, launch, and visible in-game bus operation;
- all mandatory automated gates pass; and
- no open correctness defect is capable of invalidating training or evaluation
  results.

Passing a subset of these conditions, producing an ONNX file, obtaining positive
training return, or rendering a bus route is not Version 1 completion.

Version 1 passed its release and publication gates on 2026-08-02. Its contracts,
packages and evidence are an immutable compatibility baseline for Version 2.

## Version 2 active expansion

Version 2 builds a scalable OpenTTD generalist and competition benchmark on top of
V1. It must research, implement and test every base-game gameplay domain that can
affect company decisions or outcomes, while explicitly dispositioning non-gameplay
application surfaces and community-content compatibility.

V2 includes:

- the complete V1 lifecycle and 32 by 32 passenger-bus environment as mandatory
  regressions;
- native power-of-two map dimensions from 64 through 4096, rectangular maps,
  varied towns/industries/terrain and longer horizons;
- passengers, mail and all base cargo and industry chains in temperate,
  sub-arctic, sub-tropical and Toyland;
- road vehicles and capability-gated trams, trains and signals, ships and
  waterways, aircraft and airports, and joined multimodal networks;
- construction, landscape, town authority, economy, orders, timetables, vehicle
  lifecycle, servicing, replacement, events, breakdowns and disasters;
- pinned Game Script and NewGRF compatibility suites with capability discovery
  and fail-closed unknown-content behavior;
- multiple companies and byte-pinned open-source NoAI opponents in fair,
  reproducible solo, head-to-head and mixed-field evaluations;
- scalable observations, hierarchical actions and larger generalist policies;
  and
- C++/CUDA PPO training, ONNX packaging, native/in-game equivalence, visible play,
  clean-host reproduction and publication at no lower correctness standard than
  V1.

The exact feature research, map tiers, external-AI audit pool, ambiguity around the
requested “Minimax 2/3” name, milestone gates and V2 definition of done are
governed by `docs/project/V2_RESEARCH.md`,
`config/v2/research-baseline.json`, `docs/project/V2_PLAN.md`,
`docs/project/requirements-v2.json`, `docs/project/defects-v2.json`,
`docs/project/M14_ENGINE_SOURCE_DECISION.md`, and
`docs/project/M14_OPPONENT_ACQUISITION.md`. The complete M14 setting/competition
contract and passed gate are recorded in
`docs/project/M14_INVENTORY_AND_COMPETITION.md` and
`docs/project/G14_GATE_REPORT.md`. The accepted scalable, cargo, and rail
boundaries are recorded in `docs/project/M15_SCALABLE_CONTRACT.md`,
`docs/project/G15_GATE_REPORT.md`,
`docs/project/M16_CARGO_INDUSTRY_CONTRACT.md`,
`docs/project/G16_GATE_REPORT.md`,
`docs/project/M17_RAIL_NETWORK_CONTRACT.md`, and
`docs/project/G17_GATE_REPORT.md`. The 86-row atomic V2 registry is frozen; a
scope change must update its schema-valid traceability rather than only editing
prose. The current implementation intentionally stops after G17; M18 remains
planned and unstarted.

## Version 2 dependency order

Expansion is sequential and gate-controlled:

1. more varied 32 by 32 passenger-bus scenarios, curriculum work, stronger AI
   baselines, reward analysis, and generalization tests;
2. larger maps, more towns, and longer planning horizons;
3. mail and coordinated passenger/mail service;
4. trucks, industrial cargo, and production chains;
5. trains, track, signals, stations, and schedules;
6. ships and water transportation;
7. aircraft and multimodal transport;
8. competitive companies, existing-AI opponents, and multi-agent evaluation;
9. broad OpenTTD gameplay, generalist policies, larger architectures, and a
   reusable benchmark suite.

Every expansion stage must retain the ability to run, reproduce, and evaluate all
earlier stages. These stages are now authorized V2 scope, but related legacy code
or old fixtures do not satisfy a gate without fresh V2 applicability and native
acceptance evidence.

## Legacy P0 relationship

The repository contains an unfinished, highly rigorous P0 oracle/parity program
centered on a 64 by 64 road-freight fixture. Its source pinning, evidence,
deterministic tape tooling, instrumentation discipline, and testing patterns are
valuable inputs. Its product target and freight fixture are not V2 evidence merely
because V2 now includes larger maps and road freight; V2 has different contracts,
scenarios, actions, observations and release requirements.

Legacy P0 artifacts must be preserved and truthfully labeled. They may be reused
only after an explicit applicability review. They do not satisfy a Version 1 gate
unless that gate's bus-specific contract and evidence independently pass.

## Governing documents

The project document order is:

1. `GOAL.md` — scope, end state, and completion authority;
2. `docs/project/V2_RESEARCH.md` and `config/v2/research-baseline.json` — active
   V2 feature, map, command and external-AI research boundary;
3. `docs/project/V2_PLAN.md` — active V2 dependency order, gates and definition of
   done;
4. `docs/project/requirements-v2.json` and `docs/project/defects-v2.json` — frozen
   V2 atomic requirements, tests, dependencies, status and defect accounting;
5. `docs/project/M14_ENGINE_SOURCE_DECISION.md`,
   `docs/project/M14_OPPONENT_ACQUISITION.md`,
   `docs/project/M14_INVENTORY_AND_COMPETITION.md`, and
   `docs/project/G14_GATE_REPORT.md` — accepted M14 source, inventory, package,
   runtime, competition and gate evidence;
6. `docs/project/M15_SCALABLE_CONTRACT.md`,
   `docs/project/M16_CARGO_INDUSTRY_CONTRACT.md`,
   `docs/project/M17_RAIL_NETWORK_CONTRACT.md`, and their G15-G17 gate reports —
   accepted V2 scalable passenger, cargo/industry, and rail boundaries;
7. `docs/project/REQUIREMENTS.md` and `docs/project/requirements-v1.json` — frozen
   V1 atomic requirements and compatibility floor;
8. `docs/project/ROADMAP.md` — frozen V1 dependency order and release gates;
9. `docs/architecture/V1_ARCHITECTURE.md` and the versioned contracts under
   `docs/contracts/` — technical boundaries and semantics;
10. `docs/project/VERIFICATION.md` — V1 proof rules inherited by V2;
11. accepted decision records that explicitly apply to the platform; and
12. legacy P0 contracts and reverse-engineering reports as historical evidence.

Pinned OpenTTD source remains the authority for actual OpenTTD engine behavior.
No planning document may invent engine semantics that contradict the pinned source
or observed, reproducible execution.
