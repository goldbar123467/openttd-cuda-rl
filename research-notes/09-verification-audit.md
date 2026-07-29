# Independent verification audit

Audit date: 2026-07-29 UTC  
Audited report: `OpenTTD_CUDA_RL_REVERSE_ENGINEERING_REPORT.md` (2,896 lines)  
Pinned source: `/workspace/openttd-upstream` at
`29f808ef0022064e6d9a83c8476d1e0f4686af86`

## Final verdict

**PASS. No remaining project-direction or requested contract blocker was found.**

The report is now internally consistent as a source-derived exact OpenTTD parity
plan for one frozen 64×64 road-freight slice, implemented first in scalar C and
then batched CPU/CUDA. The 32×32 rules-v1 game is consistently optional plumbing
and cannot substitute for the mandatory OpenTTD oracle/parity gate.

This verdict approves the report as a reverse-engineering specification and
phased implementation plan. It does not claim that the fixture, port, or parity
evidence has already been implemented; the report correctly leaves those as
explicit `PORT-*` execution gates.

## V-B03 re-audit: resolved

Section H now states that everything from `Optional rules-v1 harness
architecture` through the end of H is optional, cannot weaken the selected port,
and cannot supply evidence for it. `Repository layout` through `Verification
planes` are correctly nested `###` subsections. The comparison row now says an
optional harness comparison never substitutes for mandatory OpenTTD parity.

Section L now separates:

- `Selected exact-port required tests`, which require native OpenTTD projection,
  command/result, map/pool/ID, RNG, timer, YAPF/controller, `CargoPacket`, economy,
  snapshot/cache/continuation, scalar/batch/CUDA, ABI/Python/lease, soak,
  performance, side-by-side, and packaging evidence; and
- `Optional rules-v1 harness tests`, which alone contain bounded BFS, invented
  economy/scalar cargo, abstract 32-tick time, 32×32 content, and `RFSV` tests.

The former contradictory `external oracle ... not MVP` statement is gone.
Therefore **V-B03 is resolved**.

## Section C and earlier findings

Section C retains explicit `Selected 64×64 exact-port slice` and `Optional
rules-v1 harness` columns in both feature tables and the normalized interface
matrix. Extracting every selected decision found no BFS, scalar-cargo,
abstract-clock, 32×32, `RFSV`, simplified, reduced, or rules-v1 decision. Selected
cells require exact native state/behavior or explicitly defer/exclude capability.

All earlier requested defects remain resolved:

| Finding | Final status |
| --- | --- |
| V-B01 rejected-action truth table | Resolved |
| V-H01 canonical counter/state ownership | Resolved |
| V-H02 direction and `NO_ROUTE` behavior | Resolved |
| V-H03 single indexed context facade | Resolved |
| V-H04 repeat-aware preview | Resolved |
| V-H05 `uint32[N,8]` Python action mapping | Resolved |
| V-H06 immutable two-bank DLPack leases | Resolved |
| V-H07 normalized feature coverage and UI wireframe/input map | Resolved |
| V-B02 selected versus harness decision columns | Resolved |
| V-B03 optional architecture/test scoping | Resolved |

## Whole-report direction scan

No remaining statement was found that selects invented rules-v1 mechanics over
the exact-port target. Direction is aligned across:

- the title, scope resolution, and executive recommendation;
- the dual-column feature and normalized interface matrices;
- observed versus proposed rules-v1 model/simulation headings;
- selected and optional MVP definitions;
- selected and optional architectures and phase sequences;
- the exact `PORT-001` through `PORT-020` backlog;
- the API preface distinguishing native parity records from illustrative harness
  opcodes;
- the separated exact-port and optional-harness tests;
- exact-port release criteria and risk register; and
- the conclusion and first vertical slice.

The selected port consistently requires exact pinned OpenTTD command status and
cost, authoritative fields, native timers/RNG, pool/ID ordering, road
YAPF/controller, cargo packets, industry/economy effects, snapshot/reset, and
future continuation. Deferred and excluded systems are bounded explicitly, and
rendering is nonauthoritative while remaining available for diagnosis.

## Verification evidence

- Pinned checkout remains at
  `29f808ef0022064e6d9a83c8476d1e0f4686af86` with a clean worktree.
- Fresh run of
  `ctest --test-dir /workspace/openttd-build --output-on-failure`:
  **98/98 tests passed** in 3.84 seconds.
- Report heading hierarchy, selected-decision extraction, exact/harness test
  separation, active phase/backlog, acceptance criteria, risks, and conclusion
  were rechecked after the V-B03 correction.

## Recommendation

Accept the report as the requested comprehensive source-derived
reverse-engineering and exact C/CUDA RL port plan. Begin with `PORT-001` through
`PORT-005`; retain a zero-open-divergence requirement before claiming the
64×64 scalar slice, batching it, or starting CUDA optimization.
