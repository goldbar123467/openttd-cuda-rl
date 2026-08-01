# ADR 0013: Accept the legacy P0 family dispositions for V1

- Status: Accepted
- Date: 2026-07-31
- Applies to: all retained P0 documents, code, tests, fixtures, and evidence
- Implements: the transition rule in ADR 0007

## Context

The dirty worktree contains valuable P0 build, instrumentation, tape, parity, and
evidence work for a 64 by 64 road-freight clean-room port plan. V1 instead targets
a source-integrated 32 by 32 passenger-bus PPO system. The repository needs a
single disposition for each legacy family before new code can reuse it without
silently importing the wrong scope.

`docs/project/LEGACY_P0_TRANSITION.md` contains the detailed scope comparison,
file-level notes, reuse checklist, preservation inventory, and execution order.
This ADR accepts its family decisions and removes `REVIEW` as an ambiguous status.

## Decision

| Legacy family | Accepted disposition | V1 effect |
|---|---|---|
| Historical top-level P0 plan/prompt/scope documents | `FREEZE` | Preserve with supersession banners; do not extend as the active roadmap. |
| Reverse-engineering, contradiction, mapping, and research notes | `REFERENCE_ONLY` | Source leads and methods only; recheck against the V1 pin before use. |
| Existing P0 source/build/content manifests | `ADAPT` | Reuse patterns, not historical identities; build a separate V1 profile. |
| `oracle/runner/` reference-runner family | `ADAPT` | Copy/adapt principles into V1-owned tools; do not overload P0 interfaces. |
| 64 by 64 road-freight fixture | `FREEZE` | Legacy regression only; never V1 scenario/training/completion evidence. |
| Seven-patch freight/full-projection instrumentation design | `FREEZE` | Preserve active user work; reuse individual ideas only through a new V1 implementation review. |
| C17 tape/parity implementation and format | `REFERENCE_ONLY` | Test/parser patterns may inform V1; it is not the live IPC/trajectory format. |
| Freight field and command registries | `REFERENCE_ONLY` | Reuse stable-ID/completeness discipline, not field/action content. |
| Requirements, traceability, mutation, fault, and defect practices | `ADAPT` | V1-owned schemas/tools with fresh bus-specific evidence. |
| Clean-room scalar/batched/CUDA gameplay-port roadmap | `FREEZE` | No implementation on the V1 critical path. |
| `NEXT_STAGES_IMPLEMENTATION_HANDOFF.md` | `ADAPT` | It is rewritten as the current V1 handoff while retaining legacy status. |

No family is `REUSE_AS_IS`: none currently satisfies an atomic V1 bus requirement
with fresh V1 evidence. No family is `REMOVE_LATER`: preservation is still pending
and deletion has no current benefit.

## Reuse rule

An `ADAPT` decision authorizes a new V1-owned implementation or copy only after the
ten-point applicability checklist in `LEGACY_P0_TRANSITION.md` is recorded. It does
not authorize edits that break the P0 validators or obscure user ownership. A
`REFERENCE_ONLY` asset may be cited as context but cannot link into production or
close a V1 requirement until a later ADR promotes a precisely named component.

The V1 namespace remains separate (`scripts/v1/`, V1 schemas, V1 tests, and future
V1 source paths). Both the legacy P0 and active V1 validation suites must pass
during coexistence.

## Rejected alternatives

### Continue the instrumentation series until P0 is complete

Rejected because the freight/full-projection work is not a dependency of the bus
environment and would consume the active critical path.

### Reuse all parsing and command schemas unchanged

Rejected because their semantics and ownership are tied to the former projection
and fixture, even where their defensive engineering is useful.

### Move or delete legacy files now

Rejected because the current worktree contains uncommitted user work and the
preservation record does not yet provide a durable recoverable snapshot.

## Verification

`G00` requires:

- every listed family has exactly one accepted disposition;
- all active documents point to the bus V1 authority set;
- legacy banners remain intact;
- V1 validators reject legacy-only completion evidence;
- both V1 and P0 validation suites pass; and
- no branch switch, file migration, cleanup, or destructive source operation occurs
  before the preservation condition is satisfied.

Accepting this record completes the policy decision, not the preservation task or
any future reuse proof.
