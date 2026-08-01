# Legacy P0 Transition and Reuse Plan

## Purpose

The repository began as an exact C/CUDA port/parity program centered on a 64 by 64
road-freight fixture. The active goal is now a source-integrated, 32 by 32,
passenger-bus RL platform with PPO, ONNX, and visible in-game playback.

This document prevents two damaging outcomes:

1. discarding rigorous user-owned work that can strengthen the new platform; or
2. letting completed-looking freight/parity artifacts redefine or falsely satisfy
   the bus-only Version 1 goal.

No file move or deletion is authorized by this plan. The current dirty worktree
must be preserved before structural migration.

## Scope comparison

| Dimension | Legacy P0 target | Active V1 target | Consequence |
|---|---|---|---|
| Product strategy | clean-room scalar C/CUDA gameplay port judged against oracle | C++/CUDA RL harness around actual OpenTTD | Legacy backend roadmap is superseded. |
| First map | frozen 64 by 64 | controlled 32 by 32 | Fixture cannot pass V1 reset/scenario gates. |
| First transport | road freight/truck and industry delivery | passenger buses | Gameplay projection/actions/reward are not V1 evidence. |
| Learning | forbidden during P0 | required PPO lifecycle | P0 completion is not the product milestone. |
| Engine relation | external oracle for later reimplementation | pinned source-integrated environment and playable controller | Some instrumentation patterns transfer; target boundary changes. |
| GPU purpose | future simulation port | measured neural/training acceleration | Simulation CUDA design is not on V1 critical path. |
| End user | diagnostic/parity substrate | train, evaluate, export, install, and watch model | New executable/docs/evaluation work required. |

## Disposition vocabulary

- `ADAPT`: likely valuable, but requires a V1 contract, bus-specific tests, and new
  evidence.
- `REFERENCE_ONLY`: retain for design evidence; do not link it into production or
  count it as a V1 gate without a new decision.
- `FREEZE`: stop extending it on the V1 critical path; preserve history and active
  user changes.
- `REMOVE_LATER`: possible cleanup only after explicit review and preservation;
  none is authorized now.

## Top-level document disposition

| Document | Disposition | New role |
|---|---|---|
| `OpenTTD_CUDA_RL_REVERSE_ENGINEERING_REPORT.md` | `REFERENCE_ONLY` | Pinned-source/gameplay research and historical plan; its selected product target is superseded. |
| `NEXT_STAGES_IMPLEMENTATION_HANDOFF.md` | `ADAPT` | Rewritten as the live V1 handoff and current critical path. |
| `OPENTTD_P0_ORACLE_CONTRACT_AGENT_PROMPT.md` | `FREEZE` | Historical execution contract for the legacy P0 branch. |
| `00_P0_CODEX_HANDOFF_INDEX.md` | `FREEZE` | In-progress user-owned patch 0003–0007 handoff index. |
| `01_P0_EVIDENCE_GATE_AND_CONTRADICTION_REGISTER.md` | `REFERENCE_ONLY` | Evidence/contradiction methodology input. |
| `02_P0_PATCHES_0003_0007_IMPLEMENTATION_SPEC.md` | `FREEZE` | Legacy instrumentation patch specification. |
| `03_P0_COMMAND_AND_FIELD_MAPPING_CONTRACT.md` | `REFERENCE_ONLY` | Native-command and exhaustive-mapping methods; field/action content is freight-specific. |
| `docs/P0_SCOPE.md` and `docs/scope/P0_*` | `FREEZE` | Accurate legacy phase boundary only. |
| `docs/testing/P0_*` | `REFERENCE_ONLY` | Test, mutation, traceability, and defect practices. |
| `research-notes/*` | `REFERENCE_ONLY` | Source/repository research subject to freshness and V1 applicability review. |

All legacy documents need a clear banner or index context stating that `GOAL.md`
and the new project documents govern the active product. Their internal historical
requirements should not be rewritten as though they had always targeted buses.

## Implementation-family disposition

### Pinned OpenTTD source and manifests — `ADAPT`

Potential reuse:

- exact submodule source identity;
- reproducible out-of-tree build/install techniques;
- dependency and OpenGFX provenance;
- isolated configuration/data roots;
- upstream test inventory and smoke discipline.

Required V1 review:

- confirm the pinned commit supports the intended bridge, bus engine availability,
  ONNX runtime integration, and normal-game controller;
- add headless bridge/playable build variants and C++/CUDA dependencies;
- replace legacy branch/basis identities;
- distinguish reproducible build claims from the bus environment;
- rerun from clean roots under the current host profile.

Existing evidence may prove historical reproducibility but not the new build
feature set.

### Reference runners under `oracle/runner/` — `ADAPT`

Reusable patterns include checked arguments, isolated artifacts, exact command
records, fail-closed behavior, and content verification. Scripts named and scoped
to P0 should remain stable for legacy tests. New V1 runners should not overload P0
flags or silently alter old evidence semantics.

### `road_freight_v1` fixture — `FREEZE`

Preserve save, manifests, builder, and evidence. It may serve as:

- a regression fixture for legacy tape/oracle tooling;
- an optional post-V1 or instrumentation test;
- source evidence for general OpenTTD reset/command research.

It must not:

- seed V1 training;
- define the V1 observation/action/reward schema;
- count toward a 32 by 32 passenger-bus gate;
- justify adding trucks/industries before Version 1.

The V1 scenario is a new artifact under a bus-specific name and compatibility
version.

### Instrumentation patch series — `FREEZE`

The existing seven-patch design aims to project hundreds of freight/full-engine
fields for clean-room parity. V1 needs a smaller but exact synchronized interface
covering its environment semantics. Continuing the entire legacy projection may
delay the critical path and expand beyond passenger-bus needs.

Reusable ideas:

- disposable patched OpenTTD worktrees;
- patch-series provenance;
- safe boundary and non-perturbation rules;
- native command test/execute/result capture;
- first-divergence traces;
- strict diagnostic versus authoritative separation.

Individual ideas may enter a new V1-owned implementation only after review for:

- current uncommitted changes and authorship;
- dependence on the freight fixture/757-field registry;
- compatibility with a source-integrated runtime rather than external tape only;
- read-side effects and global-state assumptions;
- thread/process isolation and performance.

No V1 milestone requires the old complete 757-field projection as written.

### C17 tape/parity library — `REFERENCE_ONLY` initially, possible `ADAPT`

Valuable capabilities:

- bounded binary parsing/writing;
- canonical identities and digests;
- first-divergence comparison/minimization;
- independent decoder, fuzz, mutation, sanitizer, and fault-injection patterns.

V1 does not yet require the legacy tape format as its live IPC or trajectory
format. Reuse only if a design experiment shows it fits the new transition/state
data without forcing freight-specific schemas or C17 into a C++ inference path.
It can remain a diagnostic trace tool independently.

Current uncommitted fixes in `parity/`, `scripts/ci/`, and related tests must be
preserved even if the library is not on the immediate path.

### Field and command registries — `REFERENCE_ONLY`

The discipline of stable numeric identities, exhaustive mapping, source
expressions, lifecycle, and completeness proof should be reused. The actual
freight command families and 757 authoritative fields do not define V1.

V1 creates separate registries for:

- environment compatibility;
- structured observations;
- spatial channels;
- explicit bus actions and mask semantics;
- reward/termination components;
- model inputs/outputs and packages.

### Evidence, traceability, and defect tooling — `ADAPT`

This is the strongest direct reuse candidate. Preserve:

- stable requirement/test/defect IDs;
- bidirectional machine traceability;
- no false `PASS` policy;
- content-addressed evidence bundles;
- immutable failure history;
- mutation/fuzz/static/sanitizer gates;
- complete source/command/result provenance.

Adaptations:

- project-wide V1 prefixes and aggregate milestones;
- model/training/evaluation/package artifact types;
- dirty versus clean experiment policy;
- GPU/ONNX/toolchain provenance;
- statistical evaluation evidence;
- legacy-path labeling so old artifacts cannot close new rows.

### Clean-room scalar C/CUDA gameplay backend roadmap — `FREEZE`

This is not the active V1 architecture. Do not begin scalar port, batched gameplay
port, or CUDA game simulation work before V1. Any future revival requires an
explicit project scope change and must not replace the actual-OpenTTD training and
playback lifecycle without user direction.

## Current dirty-worktree preservation inventory

The 2026-07-31 inventory includes modified tracked files in:

- reference build/configure/test runners;
- P0 port001/port004 tests;
- tape Python reference and golden artifacts;
- P0 CI scripts;

and untracked work in:

- top-level P0 patch handoff documents;
- `docs/P0_SCOPE.md`;
- instrumentation worktree/patch helpers and tests;
- command/action schemas and developer helper;
- other patch 0003 preparation artifacts shown by `git status`.

This list is descriptive, not exhaustive forever. Before any branch switch,
rename, cleanup, or migration, capture a fresh `git status`, diff/stat, untracked
inventory, and a recoverable preservation mechanism approved for the workflow.
Never use a destructive reset or checkout to obtain a clean V1 base.

## Reuse approval checklist

For each adapted component, record:

1. legacy source path/commit/dirty-state ownership;
2. V1 requirement IDs it is intended to support;
3. assumptions that still hold and those that changed;
4. freight/64x64/clean-room-port coupling removed or isolated;
5. new API/schema/compatibility identity;
6. bus-specific unit and actual-engine tests;
7. non-perturbation/synchronization evidence;
8. security/resource/license review;
9. fresh build/run evidence;
10. rollback path if adaptation harms legacy artifacts.

Until all ten are satisfied, the component remains supporting research, not V1
production evidence.

## Transition execution order

1. preserve current worktree and record ownership/state;
2. make the new project document authority visible from README and top-level legacy
   banners;
3. create V1 machine requirements/defect/evidence schemas without changing legacy
   schemas;
4. accept integration, source-pin, toolchain, and reuse ADRs;
5. reuse/adapt reference build tooling into a separate V1 profile;
6. build new bus scenario and environment artifacts in new paths;
7. freeze legacy freight expansion unless a specific reviewed V1 dependency
   arises;
8. consider later directory archival only after active changes are committed or
   otherwise safely preserved.

## Transition completion condition

The transition is complete when:

- new contributors can identify the bus-only end goal and immediate milestone from
  the repository root;
- no active planning document sends them to implement the scalar freight port as
  the project target;
- legacy artifacts remain intact, accurately labeled, and testable at their prior
  claims;
- every reused component has an explicit applicability decision and fresh V1
  evidence;
- project traceability rejects a legacy-only artifact as proof of a bus-specific
  requirement; and
- the V1 critical path can proceed without completing unrelated freight parity
  scope.
