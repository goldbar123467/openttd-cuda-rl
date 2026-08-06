# Full-Game Vanilla Neural Curriculum Design

**Status:** Approved

**Date:** 2026-08-06

**Objective:** Replace the M23 discovery-only controller with a real normal-game
executor and grow one small neural policy from a single profitable bus service
to the complete gameplay-relevant vanilla OpenTTD action surface. Capability is
added before competitive strength. Every phase is reproducible, retains earlier
skills, and advances only through native evidence on unseen scenarios.

## Context

The repository already contains the difficult foundations for a learning system:

- the M15 public observation projection, bounded 4,096-row typed candidate
  table, native legality checks, transaction semantics, save/load contracts,
  and family/candidate policy heads;
- M16-M21 typed evidence for cargo, rail, water, air, multimodal play,
  competition, and broad vanilla capabilities;
- the M22 1,457,520-parameter generalist policy, 256-value recurrent state,
  deterministic PPO trainer, checkpointing, CPU/CUDA comparison, development
  selection, and retained evaluation machinery;
- an M23 visible-controller foundation that loads the policy and selects one of
  17 bounded programs.

The current M23 program executor does not yet play the game. It records
`NO_OP_DISCOVERY`, reports zero commands, and changes only its internal discovery
phase. The immediate engineering problem is therefore not inventing another PPO
trainer. It is building a trustworthy native executor and connecting it to
live, stepped OpenTTD transitions.

This is intentionally a long-running program. Small accepted increments are
preferred to broad speculative implementation. A phase cannot become the new
baseline because of elapsed training time, a single successful episode, or a
visible demo alone.

## Goals

1. Train a real neural policy that first creates and operates a profitable bus
   service through normal OpenTTD commands.
2. Grow map scale from 64x64 to 128x128 and then the project's initial standard
   target of 256x256 before adding other transport modes.
3. Add road freight, rail, ships, aircraft, multimodal logistics, and remaining
   gameplay-relevant vanilla management actions in explicit phases.
4. Preserve one shared generalist network and its earlier competence while new
   masked action choices are introduced.
5. Use only public state and human-legal game actions for policy input,
   execution, reward, and evaluation.
6. Make every command, transition, reward, checkpoint, and promotion decision
   reproducible and diagnosable.
7. Delay opponent training until the complete vanilla action surface works.
8. Support development with the hardware currently installed on this machine
   while retaining separate compute-capability-12.0 qualification on another PC.

## Non-goals

- NewGRFs, custom industry sets, custom vehicles, modified economies, and
  third-party GameScripts are outside the first complete curriculum.
- Cosmetic operations such as company naming, signs, UI layout, and camera
  control are not learning requirements unless they carry a gameplay effect.
- Cheats, deity/editor commands, privileged opponent state, direct state
  mutation, and administrative shortcuts never enter the policy action surface.
- Beating a champion is not required before full vanilla action coverage.
- Large maps above 256x256 are not a prerequisite for the first complete
  generalist. They are a later scale curriculum.
- Public scripted OpenTTD AIs are not assumed to contain reusable neural
  checkpoints. They are future opponents and possible public-state
  demonstration sources, subject to provenance and action translation.

## Design principles

- **Breadth before strength:** unlock legal capabilities first, then raise the
  success and profit floor.
- **Native authority:** OpenTTD command test/execute results decide legality,
  cost, mutation, and failure.
- **Bounded neural choices:** the network selects masked typed programs,
  families, and candidates; it never invents raw command payloads.
- **Transactional execution:** multi-command work has explicit progress,
  receipts, rollback rules, recovery, and persistence.
- **Retention by construction:** every update rehearses old phases and every
  candidate checkpoint reruns their frozen gates.
- **No lucky promotions:** promotion requires repeated evaluation over unseen
  development scenarios.
- **Immutable recovery:** a candidate never overwrites the last accepted
  checkpoint.
- **Version historical evidence:** new local hardware or action contracts get
  new identities; accepted M15-M23 and RTX 5070 evidence is not rewritten.

## Considered approaches

### Selected: shared hierarchical policy with phase-gated heads

Retain the M15 masked family/candidate policy and M22 program router. A shared
observation encoder and recurrent state feed the program, family, candidate,
and value heads. Each phase makes a bounded set of new action families and
candidates legal. Transport-specific heads may be lightweight, but they share
the encoder and memory.

This approach matches the existing contracts, keeps the policy small, prevents
irrelevant actions from flooding early exploration, and naturally supports
multimodal decisions later.

### Rejected: one flat command-and-parameter action space

A flat space would expose many thousands of mostly illegal or irrelevant
choices, combine unrelated parameter types, and make command failures difficult
to attribute. It also discards the repository's existing hierarchical masks.

### Rejected: independent network per transport mode

Mode specialists simplify early training but duplicate the expensive state
encoder, fragment checkpoint and retention semantics, and postpone the central
multimodal routing problem. Specialists remain useful as diagnostic baselines,
not as the product architecture.

## System architecture

```text
public OpenTTD snapshot
  -> M15/M16-M21 observation and typed domain tables
  -> shared multimodal encoder
  -> 256-value recurrent state
  -> masked M22 program selection (17 programs)
  -> masked M15 family and candidate selection (bounded 4,096 rows)
  -> persistent program transaction state machine
  -> authoritative test-mode legality at the issued snapshot
  -> normal OpenTTD command execution
  -> command receipt, public next snapshot, reward, termination
  -> rollout and atomic checkpoint
```

### Policy

The first implementation preserves the accepted 1,457,520-parameter M22
generalist unless measurement proves a contract-versioned change is necessary.
Its shared encoder and 256-value GRU carry knowledge across transport modes. The
existing program indices remain stable:

0. wait;
1. road passenger;
2. road cargo;
3. rail passenger;
4. rail freight;
5. ship on natural water;
6. ship on constructed water;
7. air service;
8. helicopter service;
9. multimodal transfer;
10. mode routing;
11. competition;
12. calendar inspection;
13. authority and economy;
14. event recovery;
15. GameScript response;
16. content discovery.

Program choice does not replace primitive choice. After selecting a program,
the policy selects an allowed M15-style family and one native-qualified
candidate. New families receive versioned schemas and transport-specific
candidate features while preserving stable candidate keys, deterministic
ordering, capacity accounting, and authoritative legality.

### Environment boundary

Each OpenTTD instance is an isolated CPU simulation. A step barrier pauses the
world between decisions, captures observation and action masks from the same
snapshot, executes the selected transaction boundary, advances a declared
number of ticks, and captures the result. Policy inference and optimization use
the selected CPU or CUDA device; simulation remains CPU-only.

One environment process owns one game. A supervisor assigns deterministic
ports and writable directories, enforces timeouts and resource limits, retains
stdout/stderr and the last valid receipt, and replaces only failed environment
workers. A worker crash never converts a partial episode into a successful one.

### Program executor

Every non-wait program is a persistent state machine. For a bus service, states
include target selection, financing, path planning, construction, stops, depot,
vehicle purchase, orders, startup, service observation, maintenance, and
recovery. Each boundary records:

- program, state, family, candidate stable key, and snapshot token;
- test-mode result and quoted native cost;
- issued command and native execute result;
- changed object IDs and finance delta;
- ticks advanced and postcondition result;
- retry, compensation, rollback, or terminal classification.

An ordinary native rejection is returned to the policy as a typed outcome when
the snapshot is still valid. Stale snapshots, ownership violations, all-illegal
masks, rollback failure, state corruption, and receipt mismatch fail closed.

### Save and load

A resumable boundary includes the native save, observation normalization,
policy recurrent state, program transaction state, curriculum phase, episode
and transition cursors, optimizer state when training, and every random stream.
A load is accepted only if contract and executable identities match and the
continued public state, legal mask, and transaction state pass semantic checks.

## Capability curriculum

| Phase | Map | Newly enabled choices and actions | Promotion capability |
|---|---:|---|---|
| 0. Real executor | 64x64 | Wait, observe, masks, receipts, save/load, rollback, recovery | Deterministic real commands; no learning claim |
| 1. First bus | 64x64 | Town pair, loan, road, stops, depot, bus, orders, start, wait | One working profitable bus service |
| 2. Bus operations | 64x64 | Stop/restart, depot, sell, replace, add buses, edit orders | Maintain and repair one service |
| 3. Bus network | 128x128 | Multiple town pairs, multiple services, capital and vehicle allocation | Operate a small passenger company |
| 4. Standard-map buses | 256x256 | Long paths, bridges, tunnels, bounded terraforming, demolition, failed-build recovery | Reliable bus company at initial standard scale |
| 5. Road freight | 256x256 | Industries, cargo selection, truck stops, trucks, refit, supply routes | Passenger and freight road transport |
| 6. Basic rail | 256x256 | Track, stations, depot, engines, wagons, consist, orders, simple signals | Passenger and freight rail service |
| 7. Advanced rail | 256x256 | Double track, blocks, junctions, bridges, tunnels, electrification, upgrades | Scalable reliable rail networks |
| 8. Natural-water ships | 256x256 | Docks, ship depots, ships, buoys, water orders | Services on existing water |
| 9. Constructed water | 256x256 | Canals, locks, aqueducts, legal landscape work | Full ship capability |
| 10. Aircraft | 256x256 | Airport siting, airports, hangars, planes, helicopters, orders, replacement | Full air capability |
| 11. Multimodal logistics | 256x256 | Transfers, feeders, shared/joined stations, cargo handoffs, mode choice | Combined road, rail, water, and air |
| 12. Full vanilla management | 256x256 | Finance, groups, autoreplace, timetables, shared/conditional orders, expansion, authority, land, events | Complete gameplay-relevant vanilla actions |
| 13. Breadth certification | 64-256 | All prior choices over unseen seeds, climates, densities, and save/load continuations | Complete opponent-free neural player |
| 14. Raise the floor | 256x256 | Harder economy and longer horizon; no new action requirement | Higher reliability, efficiency, and profit |
| 15. Opponent ladder | 256x256 | Rival-aware siting, competition, adaptation | Passive through strong scripted opponents |
| 16. Beyond standard | 512x512+ | Regional planning, longer horizons, large-map budgeting | Large-map generalist |

Phases are cumulative. New masks never make previously required choices
unrepresentable. Phase 13 certifies breadth, not expert play. Phase 14 raises
the floor only after the full vanilla interface works.

## Per-phase training cycle

Every capability phase uses the same controlled cycle:

1. Specify the new native commands, candidate schemas, postconditions, failure
   classes, persistence, rewards, and promotion cases.
2. Implement and mutation-test candidate generation and executor behavior
   without learning.
3. Run deterministic real-game golden paths and negative paths.
4. Generate public-state/legal-action demonstrations with a deterministic
   planner. The planner is a teaching fixture, not a competitor or evaluation
   substitute.
5. Warm-start only the newly exposed choices with behavior cloning while
   retaining shared parameters and rehearsing accepted phases.
6. Fine-tune the full neural policy with clipped PPO on real stepped games.
7. Evaluate optimizer-free greedy checkpoints on development scenarios.
8. Run the complete retention suite and save/load continuation gate.
9. Require two consecutive passing evaluations before promotion.
10. Freeze the selected checkpoint and its evidence before starting the next
    phase.

The teacher is removed from evaluation. No scripted decision may replace a
policy action, repair an evaluation episode, or supply a reward unavailable from
the public native state.

## Reward design

Reward is an auditable sum of native deltas and one-time verified milestones.
Each component records its source fields.

### Positive components

- first completion of a connected, owned, usable route;
- valid vehicle orders and successful service startup;
- passengers, mail, or cargo actually delivered;
- vehicle operating profit, company operating profit, and company-value growth;
- stable vehicle utilization and sustained service over declared windows;
- recovery of a stopped, lost, or unprofitable service when the recovery itself
  does not create an exploit.

### Negative components

- typed native command rejection, weighted by whether it was foreseeable from
  public state;
- stranded, perpetually stopped, or unusable vehicles;
- excessive idle boundaries when useful legal work exists;
- interest burden, negative cash, and insolvency;
- repeated build/remove or buy/sell churn without durable service progress;
- bankruptcy and unrecoverable episode failure.

Construction cost or command count alone never earns reward. Milestone rewards
are keyed to durable native objects and paid once. Reversing the milestone
removes its shaping credit where practical. Rewards are phase-versioned,
normalized from training data only, and frozen before development comparison.

## Evaluation and promotion

Each phase owns disjoint deterministic training and development seed sets. The
overall final manifest stays sealed until the complete policy is selected.
Promotion requires:

- at least 90 percent task success over the phase's unseen development cases;
- positive median operating profit for phases whose service has had enough
  in-game time to earn revenue;
- zero harness crashes, ownership violations, corrupt saves, unauthorized
  commands, or missing cases;
- save/load continuation with equivalent public semantics, masks, action, and
  recurrent/transaction state;
- every earlier phase still passing and no earlier success rate dropping more
  than five percentage points from its accepted floor;
- finite training and evaluation metrics;
- improvement over wait-only and seeded-random-legal baselines;
- two consecutive passing optimizer-free evaluations from fresh processes.

Evaluation retains every seed result, including failures. There is no retry,
replacement, post-result checkpoint selection, or final-seed training.

## Retention and controlled growth

Each rollout mix contains the current phase plus rehearsal from every accepted
phase. Sampling initially favors the new capability but guarantees a minimum
old-phase quota. Development runs occur at fixed update intervals. A candidate
that crosses a catastrophic-regression threshold is ineligible for checkpoint
promotion even if its new skill improves.

When a new action head destabilizes the shared policy, recovery order is:

1. restore the last accepted checkpoint;
2. reduce the learning rate for shared parameters;
3. increase earlier-phase rehearsal;
4. freeze lower encoder layers temporarily;
5. reset only the new head and its optimizer slots;
6. inspect candidate masks, rewards, and demonstrations before further training.

Architecture growth is not an automatic response to poor learning. It requires
profile evidence that representation capacity, rather than executor, reward,
data, or optimization defects, is the bottleneck.

## Checkpointing and recovery

Accepted checkpoints are immutable content-addressed directories. A new
checkpoint is written to a staging directory, synchronized, validated, and
atomically renamed; it never overwrites an earlier one. State includes model,
optimizer, normalization, all RNG streams, curriculum, environment cursor,
recurrent state, program transaction, retention history, contract identities,
and source/executable identity.

An interrupted run resumes from the last complete semantic boundary in a fresh
process and must reproduce the uninterrupted suffix within frozen tolerances.
Nonfinite values, checkpoint corruption, invalid masks, or native invariant
failure stop the candidate run and preserve its diagnostics.

## Hardware profiles

### Current development and initial-training PC

The current device is an NVIDIA GeForce RTX 2070 with 8 GiB, compute capability
7.5, an eight-core Intel i7-9700K, and 16 GiB system RAM. Work must use the CUDA,
driver, compiler, and system software already installed on this device for now.
The project must not replace or globally reconfigure that installation.

The repository currently hard-pins `TORCH_CUDA_ARCH_LIST` and M22 qualification
to compute capability 12.0. A versioned local development target may enable
`sm_75` if the installed LibTorch supports it. Otherwise CPU is the correctness
and temporary training fallback. This local target cannot rewrite or claim the
accepted RTX 5070 qualification evidence.

Begin with four isolated OpenTTD environments. Measure wall time, CPU, RSS, GPU
allocation, simulator utilization, and transition throughput before changing
parallelism. Increase workers only after repeated stress and recovery runs.

### Separate qualification PC

The user has another PC for separate compute-capability-12.0 testing. That
machine validates the existing production CUDA profile and any final cross-device
claim. Runs from the two machines retain distinct device/toolchain identities.

Checkpoint payloads remain canonical and CPU-loadable. CPU, RTX 2070, and the
compute-capability-12.0 device must choose the same stable greedy actions and
remain within documented forward, gradient, update, and checkpoint tolerances.

## Opponent and champion policy

Opponents begin only after Phase 13 establishes full vanilla breadth and Phase
14 raises the opponent-free floor. The ladder is:

1. no opponent;
2. passive/no-op company;
3. simple single-mode scripted AI;
4. moderate generalist or mode specialist;
5. strong byte-pinned generalist such as AAAHogEx;
6. frozen versions of the project's own accepted neural policies;
7. optional population/self-play sampling after the single-policy baseline is
   stable.

Every external AI package is pinned by source/version, BaNaNaS content ID,
bytes, hash, configuration, dependencies, and license. Paired matches use the
same seeds with controlled company-slot ordering. Public outcomes are retained;
universal victory is never assumed.

Online research found mature scripted OpenTTD AIs and experiment frameworks,
but no credible reusable pretrained neural checkpoint for this task. AAAHogEx is
a strong future scripted opponent, not imported neural weights. OpenTTDLab
provides useful patterns for reproducible AI experiments and savegame analysis.
The newer `nttd` project demonstrates an OpenTTD 15.3 structured API, stepped
barrier, scenario/result separation, and parallel-agent semantics. These are
research references; this project does not add either as an unchecked runtime
dependency.

Primary references:

- <https://github.com/rei-artist/AAAHogEx>
- <https://bananas.openttd.org/package/ai/484f4745>
- <https://github.com/michalc/OpenTTDLab>
- <https://joss.theoj.org/papers/10.21105/joss.08014>
- <https://github.com/deepsaia/nttd>
- <https://docs.openttd.org/ai-api/>

## Telemetry and provenance

Every transition records enough information to explain and replay it:

- repository commit, OpenTTD tree and executable hash;
- policy, checkpoint, contract, schema, reward, and curriculum identities;
- hardware, driver, CUDA, LibTorch, build target, and process identity;
- scenario, settings, content, seed streams, company, episode, tick, and step;
- observation and candidate hashes, truncation counts, legal masks, selected
  program/family/candidate, log probability, value, and recurrent-state hash;
- command test and execute receipts, changed objects, cost, income, delivery,
  finance, service, failure, reward components, termination, and timing.

Training, development, qualification, visible playback, and final evaluation
artifacts are separate. Training code cannot read sealed final manifests.

## Verification ladder

Every new action cluster passes these checks in order:

1. candidate enumeration, ordering, capacity, and native-legality unit tests;
2. native command success and mutation differentials on a tiny deterministic
   game;
3. stale token, rejection, rollback, ownership, resource, and corruption
   mutations;
4. transaction save/load and exact continuation;
5. short neural-learning smoke with finite parameters and changing policy;
6. unseen development evaluation for the active phase;
7. every accepted phase's regression suite;
8. visible playback showing the optimizer-free policy issuing normal commands;
9. cross-device checks when the relevant hardware is available;
10. complete V2 and unchanged V1 verification before a release claim.

Code, contracts, tests, and evidence for one bounded action cluster are committed
together. Visible playback is supporting evidence, not a replacement for native
headless evaluation.

## Definition of full vanilla breadth

Phase 13 is complete when one neural checkpoint can, using public state:

- legally select and execute every gameplay-relevant vanilla action family;
- operate passenger and freight services by road, rail, natural/constructed
  water, airplane, and helicopter;
- construct and maintain multimodal transfers;
- manage financing, vehicles, orders, replacement, timetables, infrastructure,
  land, authorities, and recoverable events;
- recover from expected native failures without privileged intervention;
- save, load, and continue with equivalent native, recurrent, and transaction
  state;
- pass all phased development and retention cases on maps through 256x256.

This definition does not require expert efficiency or victory over strong AIs.
Those are Phase 14 and Phase 15 objectives.

## Principal risks and mitigations

- **Executor complexity:** introduce one command cluster at a time with native
  differential and rollback tests before learning.
- **Sparse long-horizon reward:** use durable one-time milestone shaping,
  deterministic demonstrations, recurrent state, and progressively longer
  episodes without rewarding construction churn.
- **Catastrophic forgetting:** mandatory rehearsal, frozen retention floors,
  conservative shared-layer learning rates, and rejection of regressed
  checkpoints.
- **CPU simulation bottleneck:** measure before increasing workers; optimize
  snapshot/candidate work only after profiles identify the bottleneck.
- **GPU mismatch:** separate the current `sm_75` development profile from the
  existing compute-capability-12.0 qualification profile and keep CPU canonical.
- **Action-space explosion:** program/family masks, deterministic candidate
  caps, overflow telemetry, and phase-gated heads.
- **Reward exploitation:** native outcome sources, once-only durable milestones,
  reversal accounting, audit traces, and adversarial reward tests.
- **Evaluation leakage:** sealed final inputs, optimizer-free fresh processes,
  no retry/replacement, and content-addressed provenance.
- **Opponent overfitting:** opponents only after breadth, paired unseen seeds,
  a versioned ladder, and later sampling from multiple scripted and frozen
  neural policies.

## Delivery boundaries

The implementation plan will divide the work into small sequential milestones.
The first executable product increment ends at Phase 1: a real neural policy
builds and operates one profitable bus route in a fresh 64x64 vanilla game and
passes save/load plus retained visible playback. It does not attempt road cargo,
rail, water, air, opponents, or release publication.

Later phase plans are written only after the preceding phase produces accepted
evidence and its design assumptions are reviewed against what was learned. This
keeps the long program deliberate and prevents a speculative all-game rewrite.
