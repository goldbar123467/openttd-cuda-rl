# G14 V2 authority, inventory and opponent-qualification gate report

## Decision

`G14 PASS` on 2026-08-02.

This gate establishes the V2 authority and reproducible inputs. It does not claim
that scalable gameplay, new transport modes, learning, tournaments or V2 release
are complete; those remain M15–M23 work.

## Accepted identities and inventories

- OpenTTD source: release 15.3, commit
  `14ec60f248547d4d062a1160f0fc26d742319888`, tree
  `02d8cbbb0d8c030698d37ca76ab2773b6e23c397`.
- Accepted headless executable SHA-256:
  `8b27f06113d08fa3a21f81c01721873194f35bf885963be2697cc9da52e1ef9a`.
- Research baseline: 18 feature domains, 145/145 executable commands, 49 native
  map rectangles, ten external-AI candidates and 26 cited sources.
- Setting inventory: 20 pinned source blobs, 435/435 `SD*` definitions, 424
  unique scope/key pairs and 11 retained version variants.
- Package evidence: ten terminal outcomes, eight dependency/license-complete
  locks, two retained catalog rejections, 18 archives, 4,341,760 archive bytes
  and 18 license files.
- Runtime evidence: two active tournament admissions, one control, three
  scenario-required candidates and four excluded candidates.
- Competition contract: two exact tournament opponents, one control, 36
  deterministic disjoint seeds, four symmetric slot/start-delay legs and frozen
  complete-run scoring/failure/integrity rules.
- V2 traceability: 86 mandatory atomic requirements, eight M14 requirements
  passed, 78 later requirements planned, 16 registered tests, seven passed test
  authorities and zero nonclosed defects.

## Aggregate verification

The accepted command was run from the repository root:

```text
./scripts/v2/verify.sh
```

It exited 0 and reported:

```text
V2_RESEARCH=PASS commands=145 feature_domains=18 opponents=10 sources=26 native_rectangles=49
V2_SETTING_INVENTORY=PASS files=20 definitions=435 unique_keys=424 duplicates=11 live=true
V2_OPPONENT_EVIDENCE=PASS opponents=10 locked=8 rejected=2 packages=18 archive_bytes=4341760 licenses=18 live=false
V2_OPPONENT_RUNTIME=PASS opponents=10 package_rejected=2 runtime_rejected=2 tournament=2 control=1 scenario_required=3 live=false
V2_COMPETITION_MANIFEST=PASS tournament=2 controls=1 audit_pool=10 seeds=36 legs=4
V2_TRACEABILITY=PASS requirements=86 passed=8 in_progress=0 planned=78 tests=16 tests_passed=7 nonclosed_defects=0
Ran 96 tests ... OK
V1_TRACEABILITY=PASS requirements=227 tests=19 requirements_passed=217 post_v1_deferred=10 nonclosed_defects=0
V1_DOCS=PASS
Ran 235 tests ... OK
```

Before aggregate closure, the artifact-backed package and runtime validators were
also run against the accepted executable and retained evidence base. They passed
with the same ten package outcomes and the same runtime admission matrix. Static
validation remains in the quick suite so a clean checkout does not require the
host-specific evidence base; all referenced evidence and executable identities
remain content-addressed.

## Gate-clause disposition

| G14 clause | Result | Evidence |
|---|---|---|
| Active scope, research, plan and atomic traceability | `PASS` | [`GOAL.md`](../../GOAL.md), [`V2_RESEARCH.md`](V2_RESEARCH.md), [`V2_PLAN.md`](V2_PLAN.md), [`requirements-v2.json`](requirements-v2.json) |
| Every pinned command exactly once | `PASS` | [`research-baseline.json`](../../config/v2/research-baseline.json), 14 research mutation tests |
| Complete base feature/map/setting dispositions | `PASS` | Research baseline plus [`setting-inventory.json`](../../config/v2/setting-inventory.json), live source regeneration and 12 setting mutation tests |
| Measured source decision | `PASS` | [`M14_ENGINE_SOURCE_DECISION.md`](M14_ENGINE_SOURCE_DECISION.md) |
| AI packages locked or truthfully rejected | `PASS` | [`opponent-package-evidence.json`](../../config/v2/opponent-package-evidence.json), 13 acquisition plus 8 index tests |
| Sandboxed runtime qualification | `PASS` | [`opponent-runtime-evidence.json`](../../config/v2/opponent-runtime-evidence.json), 7 runtime plus 11 matrix tests |
| Fair preregistered competition protocol | `PASS` | [`m14-competition-manifest.json`](../../config/v2/m14-competition-manifest.json), 17 mutation tests |
| V1 correctness floor unchanged | `PASS` | Complete 235-test V1 suite and 217 applicable requirements |
| Invalidating defects | `PASS` | Zero nonclosed entries in [`defects-v2.json`](defects-v2.json) |

## Next authorized work

M15 may now alter scalable environment contracts and native integration. Every
M15 artifact must retain the G14 source, setting, package and competition digests,
and the unchanged V1 suite remains mandatory. G15 cannot inherit a pass merely
from this planning/qualification gate.
