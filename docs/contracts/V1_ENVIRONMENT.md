# Version 1 Environment Contract Plan

## Status and scope

This document specifies the contract that milestones `M02` through `M06` must
freeze and implement. Values marked `TBD-BLOCKING` are deliberate design gates,
not defaults an implementer may choose silently.

The environment is actual OpenTTD constrained to a 32 by 32, single-learning-
company, passenger-bus scenario. It exposes semantic state and explicit game
operations. It does not emulate player input.

## Contract artifacts

The human contract must have machine-readable counterparts before `G06`:

| Artifact | Required content |
|---|---|
| Environment manifest | compatibility version, engine/profile, scenario, schemas, step/horizon |
| Scenario schema | allowed settings, bounds, seed derivation, split membership |
| Structured-observation schema | ordered fields, source, type, shape, unit, transform |
| Spatial-channel schema | ordered channels, tile semantics, axes, type, transform |
| Action registry | stable IDs/heads, parameters, preconditions, native operations, outcomes |
| Reward registry | components, boundary, units, weights, clipping, inclusion/disposition |
| Termination registry | terminal/truncated reasons and bootstrap semantics |
| Transition schema | observation/mask/action/result/reward/time/provenance fields |

Every artifact has a format version, semantic version, canonical digest, and
compatibility rules. Unknown required fields and digest mismatches fail closed.

## Environment lifecycle

### States

| State | Allowed calls | Required result |
|---|---|---|
| `UNINITIALIZED` | `initialize`, `close` | load pinned runtime and validate configuration |
| `READY` | `reset`, `close` | no active episode |
| `RESETTING` | internal only | no external state reads |
| `AT_BOUNDARY` | `observe`, `legal_actions`, `step`, `pause`, `close` | synchronized immutable logical snapshot |
| `PAUSED` | `observe`, `legal_actions`, `resume`, `close` | state remains unchanged |
| `EXECUTING` | internal only | one action invocation in progress |
| `ADVANCING` | internal only | deterministic tick interval in progress |
| `TERMINAL` | `observe_final`, `reset`, `close` | final transition already committed |
| `FAILED` | `failure_artifact`, `close` | no further game operation |
| `CLOSED` | none | resources released |

Calls in invalid states return a typed contract error and do not mutate engine
state. A call timeout does not imply cancellation or safe retry; the worker
protocol must establish whether the prior transition committed.

### Reset request

A reset request contains:

- environment compatibility version;
- scenario configuration identity;
- scenario seed;
- episode ordinal and unique episode ID;
- run identity and declared train/development/evaluation split;
- inference/action sampling mode;
- optional exact saved-state identity, only if the scenario contract permits it.

### Reset result

A successful reset returns:

- scenario identity and realized layout digest;
- complete seed ledger;
- initial tick/date/economy counters;
- company/town/map counts and scope-validation summary;
- initial observation and action mask or a boundary token from which both can be
  obtained exactly once;
- compatibility/schema identities;
- no reward and no terminal/truncated flag.

Reset must remove state from the prior episode, including engine pools, company
state, cached route/action state, reward deltas, normalization mutation,
controller state, pending commands, and policy recurrent state if later used.

### Reset reproducibility

The test matrix includes:

1. two fresh processes with identical request;
2. repeated reset in one process;
3. reset after a short successful episode;
4. reset after bankruptcy;
5. reset after an illegal/stale action;
6. reset after a worker failure where recovery is declared supported;
7. adjacent seeds to prove the seed is applied rather than ignored; and
8. different worker counts to prove episode seed assignment is stable.

Each comparison covers the full declared initial semantic projection, not only the
map seed or image.

## Scenario v1 contract

### Fixed properties

- map width and height: 32 tiles each;
- climate: `TBD-BLOCKING`, expected temperate unless evidence favors another
  default-content climate;
- calendar start: `TBD-BLOCKING` and chosen so a documented bus engine is
  available;
- economy: pinned default-economy settings with every behavior-affecting override
  explicit;
- learning companies: exactly one;
- competitor companies during training: zero;
- cargo serviced: passengers only;
- permitted operated vehicles: buses only;
- permitted constructed transport infrastructure: roads, bus stops, and required
  road-vehicle depots;
- disasters, NewGRFs, networking, multiplayer, and arbitrary scripts: disabled;
- initial balance/loan, maximum loan, inflation, breakdowns, town growth,
  construction cost, vehicle availability, and passenger generation:
  `TBD-BLOCKING` in the scenario ADR;
- maximum episode ticks/days/actions: `TBD-BLOCKING` in the step/horizon ADR.

### Layout validity

A generated scenario is valid only when all machine-checked conditions hold:

- dimensions/settings/content/company/cargo/vehicle scope matches the manifest;
- town count is within frozen minimum/maximum bounds;
- at least one town pair can support the scripted bus acceptance trajectory;
- required construction is possible within the starting financial policy;
- no forbidden existing transport vehicle or infrastructure is present;
- map border/water/terrain constraints do not make every connection impossible;
- all observed entity counts fit schema capacity without silent truncation;
- split membership is deterministic and no final-evaluation seed appears in
  training/development inputs.

If generation fails, the result records the exact predicate. A retry must use a
declared deterministic derived seed; host time and global retry order are
forbidden inputs.

### Split policy

- fixed unit/integration fixtures are never final model-quality scenarios;
- training seeds/layouts are available to the trainer;
- development seeds are available for iteration and checkpoint selection;
- final evaluation seeds are immutable and withheld from trainer/curriculum
  selection code;
- robustness variations are separately labeled so a model is not tuned after
  observing final results.

## Step contract

### Inputs

A step request contains:

- environment handle and episode ID;
- monotonic transition ordinal;
- pre-action boundary token/tick identity;
- action schema/compatibility identity;
- decoded action ID plus bounded parameters, or policy output plus mask only at a
  higher layer that records the decoded action;
- declared simulation advance policy;
- request ID used for exactly-once commit/recovery semantics.

### Processing order

1. validate lifecycle, episode, ordinal, boundary, and schema identities;
2. validate action encoding and mask membership against the frozen pre-action
   snapshot;
3. plan native command(s) without mutating state;
4. execute according to the action's declared atomicity policy;
5. record native results, costs, and final action outcome;
6. advance the exact declared simulation tick interval;
7. reach the next safe boundary and assert synchronization invariants;
8. encode next observation and mask;
9. calculate reward components from pre/post deltas;
10. calculate termination/truncation;
11. atomically commit or fail the transition record;
12. return the result.

No observation callback, metrics scrape, logger, or monitor may advance ticks,
consume engine RNG, execute lazy work with semantic side effects, or reorder engine
operations.

### Step result

A successful or game-level rejected transition returns:

- episode/transition/request IDs;
- pre/post boundary ticks and advanced tick count;
- action ID/parameters and mask bit used;
- typed action outcome;
- native command result list and costs;
- next structured/spatial observation;
- next action mask;
- reward component vector and scalar reward;
- terminal flag, truncated flag, and reason;
- environment/observation/action/reward compatibility IDs;
- diagnostic timing/resource values outside the policy observation.

An internal bridge failure does not masquerade as an ordinary negative reward. It
terminates/fails the trajectory under the run policy and produces a retained
diagnostic artifact.

### Simulation advance policy

The initial choice is `TBD-BLOCKING` between:

- fixed ticks after every agent action;
- decision-boundary stepping that stops at a bounded reviewed event; or
- a hybrid with an explicit fixed upper bound.

The final policy must define tick zero, inclusivity of the interval, whether
construction time is immediate engine time or agent-step time, pause behavior,
vehicle/event processing, reward boundary, terminal detection timing, and no-op
behavior. It must be reproducible and shared by headless and in-game control.

## Observation contract

### General invariants

- fixed shapes for a compatibility version;
- explicit little/big endian only for serialization; tensors use backend-defined
  memory with documented logical order;
- no pointer values, padding bytes, locale text, wall time, process IDs, or
  unordered iteration;
- bounded values or explicit overflow/error behavior;
- no silent NaN/inf; missing/inapplicable values have typed masks/sentinels;
- canonical entity ordering and stable slot identity within an episode;
- same pre-action snapshot as legal mask;
- causal information available to the in-game controller at that boundary;
- diagnostics and reward-only values cannot leak into policy inputs accidentally.

### Structured tensor candidate registry

Before `G04`, each candidate receives an exact row in the machine schema:

| Group | Candidates requiring disposition |
|---|---|
| Company | balance, loan, income, expenses, company value |
| Counts | buses, depots, bus stops/stations, routes, owned road tiles |
| Vehicle slots | identity/presence, age, state, capacity/load, profit, utilization, orders, route |
| Town slots | identity/presence, tile/coordinates, population, passenger production, rating, served state |
| Route slots | endpoint identities, vehicle count, delivery/profit/utilization/status |
| Time | calendar/economy date, tick phase, episode progress, remaining action/tick budget |
| Ownership | infrastructure summaries and relevant company ownership |
| Causal history | recent action outcome and separately selected reward components if approved |
| Map summary | distances/connectivity/buildability summaries used by structured MLP |

For slotted groups, schema freezes maximum count, sort key, tie breaker, overflow
policy, presence mask, and what happens when an engine ID is deleted/reused.

### Spatial tensor candidate registry

Logical shape is channels by 32 by 32 unless the architecture ADR selects another
explicit order. Each candidate requires exact per-tile semantics:

- terrain class and/or height;
- water;
- any road and learning-company-owned road;
- buildings/houses;
- town identity/influence and population density;
- passenger production;
- bus stops and depot tiles;
- route/road usage and vehicle presence;
- buildable and blocked tiles for relevant action families;
- ownership;
- station catchment;
- optional selected-origin/selected-destination or action-context planes.

Binary, categorical, ordinal, and continuous channels are not conflated. A
channel cannot be declared correct from one all-zero fixture.

### Normalization

For every numerical field/channel, choose one:

- exact categorical/boolean encoding;
- fixed transform derived from engine bounds or a reviewed physical/economic
  constant;
- running statistic fitted on training data and frozen at checkpoint/export;
- clipping plus an overflow indicator; or
- explicit exclusion.

Evaluation and playback load frozen constants. They never update them. Zero
variance, negative financial values, large debt/profit, missing entities, maximum
population/counts, and overflow all have tests.

## Action contract

### Output representation gate

PPO requires a bounded output distribution. `M05` must select and prove exactly
one of:

- a fixed flat action catalog;
- multiple factored categorical heads with a deterministic validity/joint-action
  rule; or
- a bounded deterministic candidate table with candidate features and a stable
  scorer.

The decision must measure output size, legal-mask density, semantic stability of
indices, compute/memory cost, ability to express all required bus operations, and
native/ONNX/in-game support. A variable list whose order can change nondeterministically
is forbidden.

### Initial action families

| Family | Required V1 disposition | Minimum semantic content |
|---|---|---|
| Wait/no-op | Include | fixed tick cost and no engine command |
| Select town endpoints | Include or encode directly | bounded stable town slots |
| Build road segment | Include | tile, direction/connectivity, ownership/cost |
| Build road path | Include or explicitly replace with repeated segments | deterministic planner and transaction semantics |
| Place bus stop | Include | tile, orientation/type, catchment/authority legality |
| Build road depot | Include | tile, orientation, ownership |
| Purchase bus | Include | depot, engine selection, cost, created vehicle identity |
| Create/assign orders | Include | vehicle/route/station slots, order sequence semantics |
| Start/stop vehicle | Include | vehicle slot and desired state |
| Sell vehicle | Review before freeze | ownership, depot/state requirements, proceeds |
| Remove infrastructure | Review before freeze | owned target, dependency checks, cost/refund |
| Loan take/repay | Review before freeze | amount step, limits, balance result |

### Per-action definition

Every registry entry/family defines:

- stable numeric identity and human name;
- exact parameter fields and domains;
- referenced entity-slot lifetime rules;
- cheap pre-mask conditions;
- complete legal preconditions;
- native test/execute operations and ordering;
- expected cost/tick behavior;
- success state changes;
- stale-state and native-rejection behavior;
- partial-success/rollback policy;
- reward-component effects;
- structured log representation;
- unit, property, negative, and actual-engine tests.

### Legality and masks

Masks represent what is known legal at `S_t`. They must not claim that a legal
action is guaranteed to succeed after asynchronous/stale state; such a failure has
its own outcome. Mask generation uses deterministic canonical iteration and has a
frozen resource bound.

The mask application rule must:

- verify identical action schema and length/shape;
- exclude illegal logits before normalization/sampling;
- avoid NaN from negative infinity/all-masked cases;
- define one safe all-masked behavior, expected to be an always-legal wait action;
- validate a sampled action again before execution;
- count any mask violation as a correctness defect, not ordinary exploration.

### Action outcomes

| Outcome | Meaning | Episode policy |
|---|---|---|
| `SUCCESS` | Legal action completed under its transaction contract. | Continue unless terminal state reached. |
| `NO_OP` | Declared wait/no-op completed and ticks advanced. | Continue; reward may penalize excess. |
| `STALE_REJECTED` | Legal at mask boundary, rejected because relevant state changed. | Continue or terminate per synchronization ADR; count separately. |
| `ILLEGAL_INPUT` | Encoding/parameters/mask membership invalid. | Correctness failure for policy/runtime; never silently execute. |
| `NATIVE_REJECTED` | Preconditions appeared legal but native command rejected. | Record full reason; may continue, but opens mask/action defect review. |
| `INTEGRATION_FAILURE` | Bridge, invariant, timeout, crash, I/O, or internal failure. | Fail trajectory/run according to severity; not shaped reward. |

## Reward contract

### Component design record

The reward registry includes every candidate from `REW-001` and `REW-002` with:

- `included`, `diagnostic_only`, or `rejected` disposition;
- source engine fields and pre/post boundary;
- signed unit and formula;
- weight, scale, clip, and aggregation order;
- causal/deployment information analysis;
- known exploit and targeted detector;
- version introduced/removed;
- tests and evidence.

### Baseline policy

The first trusted reward should be as simple as evidence permits: realized
passenger delivery/operating economics, bankruptcy, and small explicit action-cost
or invalid/no-op penalties. Speculative network value and dense proxy rewards enter
only when the sparse baseline is measured and each proxy has exploit tests.

This is a design bias, not a license to omit candidate disposition or the goal of
learning useful network construction.

### Timing

For transition `t`, each delta is calculated from synchronized values at `S_t` and
`S_t+1`, adjusted only for explicitly attributed action costs/results. A cumulative
monthly/yearly profit counter must not be paid repeatedly. Delayed cargo delivery
belongs to the interval in which OpenTTD records it.

### Logging

Trajectory and metrics retain:

- every raw component before weighting;
- every weight/scale/clip result;
- total scalar reward;
- action outcome and engine economic deltas;
- reward schema/digest;
- terminal/truncation reason.

Changing a coefficient creates a new reward configuration identity even when the
component schema is unchanged.

## Termination and truncation

| Reason | Terminal? | Bootstrap? | Required evidence |
|---|---:|---:|---|
| Bankruptcy/company deletion | yes | no | controlled bankruptcy scenario |
| Success threshold, if enabled | yes | no | exact threshold boundary test |
| Irrecoverable invalid engine state | failure, not normal terminal | no accepted rollout past failure | invariant fault test |
| Fixed action/tick/calendar horizon | no, truncated | yes from final valid observation | horizon edge test |
| User cancellation | no, truncated/incomplete | configurable; never accepted silently | interruption test |
| Worker crash/timeout | failure | only under explicit recovery protocol | fault-injection test |
| Integration/nonfinite/I/O failure | failure | no ordinary training transition | retained artifact test |

An episode length metric states whether it counts decisions, actions, ticks, days,
or months. All are available separately where useful.

## Trajectory contract

Each transition record includes at minimum:

- format and compatibility versions;
- run, worker, environment, episode, transition, and request IDs;
- scenario identity and seed ledger reference;
- pre/post boundary ticks/dates;
- observation tensors or content-addressed references;
- action mask;
- action ID/parameters, selection mode, log probability, and pre-action value;
- action/native results;
- reward vector and scalar;
- next value when required for bootstrap;
- terminal/truncated flags and reason;
- model/checkpoint identity;
- observation/action/reward schema identities;
- integrity checksum and bounded size/count fields.

Writer failure is visible to the trainer. Production code does not continue an
accepted provenance-required run after losing mandatory trajectory/log data unless
the run configuration explicitly allows a diagnosed degraded mode that cannot
produce release evidence.

## Required contract test families

1. machine schema validation and semantic lint;
2. reset/reseed/split/scope-negative tests;
3. tick and lifecycle state-machine tests;
4. observation golden, per-channel, orientation, scaling, overflow, and
   non-perturbation tests;
5. action encode/decode, property, boundary, mask differential, stale-state,
   atomicity, and actual-engine tests;
6. reward hand-vector, actual-engine, temporal-delta, and adversarial exploit tests;
7. terminal/truncation/GAE-boundary tests;
8. trajectory round-trip, corruption, truncation, size-limit, and I/O-fault tests;
9. fixed scripted complete bus route and passenger-delivery trajectory;
10. long randomized legal-action run with invariants after every boundary; and
11. cross-runtime golden observation/mask/action vectors.

## Freeze conditions

Environment contract v1 freezes only when:

- all `TBD-BLOCKING` values have reviewed ADRs and machine artifacts;
- every candidate feature/action/reward has a disposition;
- one scripted agent can complete the bus economic loop;
- observation and action masks refer to identical snapshots;
- actual-engine integration tests cover every core operation;
- all schemas have stable IDs/digests and rejection tests;
- no known defect can invalidate transition data; and
- trainer, evaluator, exporter, and in-game teams can implement without inventing
  missing semantic choices.
