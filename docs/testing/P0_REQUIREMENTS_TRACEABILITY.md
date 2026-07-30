# P0 Requirements Traceability

## Status vocabulary

- `PASS`: the requirement has executed evidence satisfying its exit condition.
- `IN PROGRESS`: implementation or evidence is incomplete and no completion claim
  is made.
- `BLOCKED`: an external dependency or unresolved source fact prevents progress.

This is the initial matrix established at Gate 0. It is expanded to named test,
source, code, evidence, and digest granularity as each port lands. A row may move
to `PASS` only after its referenced gate runs successfully.

## Gate 0

| ID | Requirement | Governing artifact | Evidence | Status |
|---|---|---|---|---|
| `G0-001` | Read the complete instance guide before acting | `/workspace/AGENTS.md` | `evidence/p0/gate0/preflight.md` | PASS |
| `G0-002` | Read the handoff, report, verification audit, and every named research note | Authority-input digest table | `evidence/p0/gate0/preflight.md` | PASS |
| `G0-003` | Identify outer repository, starting commit, remote, and branch | ADR 0001 | `evidence/p0/gate0/preflight.md` | PASS |
| `G0-004` | Verify the exact pinned, clean submodule | ADR 0001 | `evidence/p0/gate0/preflight.md` | PASS |
| `G0-005` | Inspect visibility without changing it | ADR 0001 | `evidence/p0/gate0/preflight.md` | PASS |
| `G0-006` | Inspect tracked, untracked, and ignored content for credentials and generated artifacts | `.gitignore`; publication policy | `evidence/p0/gate0/preflight.md` | PASS |
| `G0-007` | Work on the dedicated non-main P0 branch | ADR 0001 | `evidence/p0/gate0/push-proof.md` | PASS |
| `G0-008` | Document public GPL treatment and upstream AI-contribution prohibition | ADR 0001 | ADR review and staged-content check | PASS |
| `G0-009` | Define supported and forbidden P0 scope | scope documents | scope review | PASS |
| `G0-010` | Create the initial requirements matrix and source register | this file; source register | tracked files | PASS |
| `G0-011` | Preserve credential-safe preflight outputs | evidence policy | `evidence/p0/gate0/preflight.md` | PASS |
| `G0-012` | Commit and push Gate 0 before instrumentation | atomic Git milestone | `evidence/p0/gate0/push-proof.md` | PASS |
| `G0-013` | Stage no scalar, CUDA, viewer, or other later-phase implementation | forbidden-scope policy | `evidence/p0/gate0/push-proof.md` | PASS |

## Port exit-gate matrix

| ID | Exit claim | Primary decisions and specifications | Required evidence families | Status |
|---|---|---|---|---|
| `PORT-001` | Clean checkout reconstructs the pinned reference, verified OpenGFX profile, exact 99-test inventory, full test pass, install, and headless smoke run | ADR 0002; source/toolchain/dependency/build/test/content schemas and manifests | preflight, acquisition, configure, build, CTest inventory/JUnit, install, smoke, clean rebuild, drift negatives | IN PROGRESS |
| `PORT-002` | One deterministic 64x64 road-freight fixture is structurally, semantically, and dynamically frozen | ADR 0003; fixture schema; normalized settings; command registry | save/content/settings/command digests, structural inspector, forbidden-branch checks, route and delivery proof | IN PROGRESS |
| `PORT-003` | Seven-patch disposable-worktree instrumentation records native commands and a complete nonperturbing projection | instrumentation series; field schema; source register | patch identity, build identities, plain/off/on comparisons, command/tick records, 2/20/parallel repeatability | IN PROGRESS |
| `PORT-004` | Strict C17 command/tape v1 tooling validates, compares, reports, and minimizes without common-mode authority | ADR 0004; tape and command schemas | unit/golden/negative/property/differential/integration/fuzz/mutation evidence, independent Python decode | IN PROGRESS |
| `PORT-005` | Field registry and cache policy are complete, cache experiments preserve continuation, and every quality/evidence gate passes | ADRs 0005 and 0006; field/schema/evidence/gate-result registries | projection audit, cache erase/rebuild, 10,000-tick continuation, sanitizers, static, ShellCheck, fuzz, coverage, mutation, CI | IN PROGRESS |

## Cross-cutting mandatory gates

| ID | Requirement | Planned test or checker family | Status |
|---|---|---|---|
| `P0-X-001` | Every manifest validates as Draft 2020-12 and rejects duplicate keys and unknown required properties | schema positive/negative and independent loader tests | IN PROGRESS |
| `P0-X-002` | Hash-bearing identities use RFC 8785 canonical bytes and vetted SHA-256 | canonicalization golden/differential tests and digest verifier | IN PROGRESS |
| `P0-X-003` | Every native parser/codec/comparator/minimizer/loader passes ASan and UBSan | `p0_sanitizers.sh` | IN PROGRESS |
| `P0-X-004` | Every byte-oriented native entry point has a bounded coverage-guided fuzz target | parser and pair-target fuzz campaigns | IN PROGRESS |
| `P0-X-005` | New P0 native code meets warnings, Clang-Tidy, static analyzer, coverage, and mutation thresholds | static, coverage, and mutation gates | IN PROGRESS |
| `P0-X-006` | Every shell script passes ShellCheck without an unproved suppression | `p0_static.sh` | IN PROGRESS |
| `P0-X-007` | Authoritative replay is offline, deterministic, bounded, and retains raw evidence | runner and CI policy tests | IN PROGRESS |
| `P0-X-008` | Every source claim, field, command, test, defect, and evidence artifact is traceable | source register, field/command registries, defect/divergence ledgers | IN PROGRESS |
| `P0-X-009` | No credential, unapproved license, dirty submodule, unexpected gitlink, or later-phase implementation is published | secret/license/policy/branch checkers | IN PROGRESS |
| `P0-X-010` | Top-level gate emits a schema-valid result and only reports `PASS` when all subgates and artifact digests pass | `p0_gate.sh`; gate-result schema negative tests | IN PROGRESS |

## Update rules

For every implementation milestone:

1. add or refine a stable requirement ID;
2. link exact pinned-source locations and the governing ADR/schema;
3. link production and test files;
4. record the exact command, result, raw-evidence location, and SHA-256;
5. add any discovered defect or divergence and its regression test;
6. change status only after the focused gate passes;
7. keep the final matrix free of unimplemented placeholders, undocumented skips,
   orphan fields, orphan tests, and unverified claims.
