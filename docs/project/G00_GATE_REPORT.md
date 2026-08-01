# G00 Authority, Preservation, and Executable-Gates Report

- Gate: `G00`
- Result: `PASS`
- Date: 2026-07-31
- Outer baseline commit: `76574e7e65494b72ed3c07cbf973722865c3569f`
- Historical OpenTTD submodule commit:
  `29f808ef0022064e6d9a83c8476d1e0f4686af86`
- Worktree condition: intentionally dirty, fully inventoried, locally snapshotted,
  and restoration-tested

## What this pass means

The project has one executable authority system for the active 32 by 32
passenger-bus V1 plan, while the unfinished 64 by 64 road-freight P0 work remains
preserved and independently testable. New V1 work may proceed into `M01` using
separate paths and generated worktrees without completing the historical freight
port plan.

This is an `M00` infrastructure pass only. It does not claim that any V1 bus
environment, trainer, model, CUDA path, ONNX package, evaluator, or playable agent
exists. The machine registry truthfully reports zero passing V1 atomic
requirements, and every later gate remains open.

## Gate evidence

| G00 condition | Evidence | Result |
|---|---|---|
| Canonical project authority | `GOAL.md`, README read order, requirements, roadmap, architecture, contracts, training, and verification plans | `PASS` |
| Machine requirement inventory | Draft 2020-12 schema plus 227 exact Markdown/JSON-synchronized requirement rows and 18 test-suite records | `PASS` |
| Defect propagation | Schema-valid V1 ledger with recomputed counts and fail-closed downstream blocking | `PASS` |
| False-completion resistance | Mutation tests for duplicates, missing mappings/artifacts, status drift, P0 evidence laundering, aggregates, defects, and early post-V1 activation | `PASS` |
| Source-brief provenance | Both supplied brief identities, sizes, line counts, and SHA-256 values are frozen and validated | `PASS` |
| Legacy disposition | ADR 0013 gives every implementation family exactly one accepted status; no family is reused as-is | `PASS` |
| Blocking project decisions | ADRs 0008-0013 select publication/license, OpenTTD source/patching, integration/process, toolchain, evidence, and legacy boundaries | `PASS` |
| Dirty-worktree preservation | Four content-addressed local recovery artifacts; both Git bundles verify; all 398 archived files restore byte-for-byte with matching status/commits | `PASS` |
| Document authority | 22 active documents, 19 local links, 9 historical banners, and 7 accepted V1 ADRs lint | `PASS` |
| Legacy coexistence | The original P0 traceability suite still accepts its 56 requirements/25 tests without giving them V1 status | `PASS` |

## Reproducible checks

Run from the repository root:

```bash
./scripts/v1/traceability.sh --tools-python /usr/bin/python3
./scripts/ci/p0_traceability.sh --tools-python /usr/bin/python3
git diff --check
```

Observed V1 result:

```text
V1_TRACEABILITY=PASS requirements=227 tests=18 requirements_passed=0 post_v1_deferred=10 nonclosed_defects=0
V1_DOCS=PASS active_docs=22 local_links=19 legacy_banners=9 accepted_v1_adrs=7
Ran 63 tests
OK
```

Observed legacy result:

```text
TRACEABILITY=PASS requirements=56 tests=25 requirements_passed=0
Ran 7 tests
OK
```

The registry also reproduced byte-for-byte from `bootstrap_registry.py`; the V1
shell/Python entry points passed syntax compilation, and changed-file whitespace
validation passed.

## Remaining risks carried into M01

- The recovery snapshot is on the same host. Its digests make copies verifiable,
  but off-host protection still requires an owner-approved copy/publication action.
- At this historical G00 checkpoint, source preparation and the toolchain probe
  passed independently. `M01/G01` subsequently passed on 2026-08-01; see
  `G01_GATE_REPORT.md`.
- At this historical checkpoint no headless/playable V1 feature build had run;
  the later M01 baseline builds contain no RL feature implementation.
- Scenario and all learning semantics remain design-only and nonpassing.

These are `M01` and later tasks; none invalidates the narrower `G00` pass.
