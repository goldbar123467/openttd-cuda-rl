# ADR 0007: Adopt the passenger-bus RL platform as the project goal

- Status: accepted by explicit user direction
- Date: 2026-07-31
- Applies to: project-level work after the planning reset
- Supersedes: the product-target portions of the original exact C/CUDA gameplay
  port plan and next-stages handoff
- Does not erase: historical P0 evidence or phase-local decisions

## Context

The repository was planned and partially implemented around an exact parity oracle
for a later clean-room C/CUDA OpenTTD gameplay port. Its first fixture is a 64 by 64
road-freight route. The user subsequently supplied two project briefs defining a
different complete outcome:

- a reusable reinforcement-learning harness around OpenTTD;
- a constrained first environment on 32 by 32 maps;
- passenger buses before all other cargo/transport systems;
- C++ and justified CUDA for the production runtime/trainer;
- one trusted PPO implementation;
- structured MLP, spatial CNN, and combined architectures;
- independent evaluation and existing-AI baseline support;
- checkpointing, monitoring, reproducibility, and comprehensive tests;
- ONNX export with native/ONNX/in-game equivalence; and
- a normal OpenTTD workflow in which a user watches the trained model play.

Continuing the former freight-port roadmap as project authority would violate the
new first-scope restriction and omit required learning/export/playback outcomes.
Deleting the existing work would lose rigorous source, build, instrumentation,
parity, and test assets.

## Decision

1. `GOAL.md` becomes the project-level scope and completion authority.
2. Version 1 is the 32 by 32, single-learning-company, passenger-bus PPO platform
   defined by the new project requirements.
3. The target uses actual pinned OpenTTD through a stable source-integrated C++
   bridge unless a later evidence-backed ADR selects another design that still
   satisfies the complete lifecycle.
4. C++ owns the production environment, training, evaluation, export, and
   inference path. CUDA accelerates only measured suitable work. Python is
   auxiliary.
5. A normal-game model controller and three-runtime inference equivalence are
   mandatory Version 1 outcomes, not optional future viewer work.
6. The legacy 64 by 64 freight P0 remains preserved and truthfully labeled. It is
   not a prerequisite or completion proxy for bus Version 1.
7. Legacy components may be reused only through a documented applicability review
   and fresh V1 evidence.
8. Post-Version 1 gameplay expansion is sequential; related legacy code does not
   authorize early scope expansion.
9. Existing dirty worktree changes are user-owned and must be preserved before any
   migration or cleanup.

## Authority consequences

For active project conflicts, use the order in `GOAL.md`. Older ADRs continue to
govern historical P0 artifacts only within their stated `PORT-001` through
`PORT-005` scope. Any reference in an old ADR to a mutable top-level plan is read as
the version that existed at that ADR's accepted commit, not as permission for the
historical phase to override the new project goal.

Pinned OpenTTD source remains behavioral authority for engine semantics. The new
project requirements determine which behavior and product outcomes must be built.

## Consequences

### Positive

- one clear end-to-end product and release definition;
- the first gameplay scope matches both supplied briefs;
- training and deployment semantics are designed together;
- rigorous P0 practices can strengthen the new work without controlling it;
- road-freight and simulation-port work no longer consume the V1 critical path.

### Costs

- the old roadmap and field/command schemas cannot simply be continued;
- a new bus scenario, environment contract, PPO stack, evaluator, ONNX pipeline,
  and in-game controller are required;
- build/toolchain decisions must be revisited for C++/CUDA/tensor/ONNX/playable
  needs;
- some legacy implementation may remain frozen rather than completed;
- machine traceability must distinguish legacy and V1 evidence.

## Rejected alternatives

### Complete the freight parity/port plan first

Rejected because it makes an out-of-scope cargo/transport system the prerequisite
for the user-requested bus-only environment and delays the actual learning
lifecycle.

### Treat the supplied goal as a loose future aspiration

Rejected because the briefs explicitly define the whole project and Version 1
completion, including training, ONNX, evaluation, and visible playback.

### Delete the legacy P0 work and restart

Rejected because its reproducible builds, source research, evidence methods,
bounded parsers, traceability, and active user changes have material value and must
be preserved.

### Keep a clean-room OpenTTD gameplay port as the core environment

Rejected for Version 1 because the requested platform is around OpenTTD and must
load the resulting model into normal OpenTTD. A separate gameplay reimplementation
would add a large semantic-equivalence burden before PPO can learn the requested
task.

### Implement Python PPO/environment first and later rewrite C++

Rejected as the production plan because it contradicts the explicit C++/CUDA core
runtime requirement and risks two semantic implementations. Python remains useful
as an independent test and analysis oracle.

## Verification

This decision is reflected when:

- README links to the new authority set;
- the old top-level plan/report files carry unambiguous legacy/supersession notices;
- requirements cover both supplied briefs;
- the roadmap begins with V1 authority/build/bus scenario rather than freight
  projection or a scalar gameplay backend;
- transition policy preserves the dirty worktree and legacy evidence;
- future machine traceability cannot close a bus requirement with a legacy-only
  artifact.

Final implementation verification remains the `G12` audit in
`docs/project/ROADMAP.md`; accepting this ADR proves direction, not product
completion.
