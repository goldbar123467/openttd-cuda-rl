# P0 Requirements Traceability

## Purpose and authority

This document is the human review view of the P0 oracle-contract requirement
graph. The machine authority is
`evidence/p0/P0_REQUIREMENTS_TRACEABILITY.json`, validated by
`oracle/manifests/schema/requirements-traceability.schema.json` and
`scripts/dev/validate_traceability.py`. P0 covers only `PORT-001` through
`PORT-005`: reproducible pinned reference construction, one frozen road-freight
fixture, non-perturbing native instrumentation, tape v1 tooling, and the field
and cache contract. `PORT-006`, scalar gameplay implementation, CUDA, RL, GUI
automation, and generalized OpenTTD support are deliberately absent.

The graph is fail-closed. A row is not `PASS` merely because its implementation
exists or a focused test has passed once. `PASS` means the declared production
files exist, every linked test passed in the release profile, every linked
artifact exists and verifies, mapped defects are closed, and the owning gate
passed. Until that point the honest state is `IN_PROGRESS`.

## Status vocabulary

- `PASS`: implementation, bidirectional test mapping, retained evidence, and
  the owning release gate all passed.
- `FAIL`: executed evidence contradicted the requirement.
- `IN_PROGRESS`: implementation or release evidence is incomplete.
- `BLOCKED`: an external condition prevents execution; it never counts as
  completion.

`SKIP` is intentionally not a requirement status. A mandatory release gate may
never close with `SKIP`; failed-run reports may use it only to describe stages
not run after an earlier dependency failed.

## Authority chain

```text
pinned OpenTTD source and verified content
        -> reproducible reference and exact 99-test inventory
        -> frozen fixture and typed native commands
        -> complete non-mutating projection at native boundaries
        -> strict tape v1 bytes and independent decoding
        -> identity-first, earliest-divergence comparison
        -> valid-prefix minimization
        -> field/cache continuation contract and invariants
        -> quality campaigns, evidence bundle, and final result
```

Equality downstream cannot repair incompleteness upstream. Byte-identical tapes
prove repeatability only after source review and runtime coverage prove that the
projection contains every reached future-influencing value. Likewise, a valid
tape is not evidence that instrumentation preserved native behavior; the
plain/off/on and 10,000-tick continuation experiments own that claim.

## Repository, source, and publication safety

| Requirement | Contract | Implementation | Test | Evidence | Gate | Status | Reviewer note |
|---|---|---|---|---|---|---|---|
| `SAFE-REPOSITORY-001` | Dedicated pushed P0 branch; clean outer tree and submodule | `oracle/runner/preflight.sh` | `TEST-SAFE-POLICY` | `evidence/p0/gate0/push-proof.md` | P0-FINAL | IN_PROGRESS | Final clean-tree and remote-tip proof is regenerated at the closing commit. |
| `SAFE-SOURCE-PIN-001` | Preserve exact OpenTTD commit `29f808e`; reject moved or dirty source | `oracle/runner/preflight.sh` | `TEST-SAFE-POLICY` | `evidence/p0/gate0/preflight.md` | P0-FINAL | Every patch/build/record stage rechecks the pin. |
| `SAFE-CREDENTIALS-001` | Reject staged secrets, credential artifacts, and unsafe publication | preflight and static runners | `TEST-SAFE-POLICY` | Gate-0 preflight plus final redacted scans | P0-FINAL | No credential value is evidence and none may enter logs or commits. |
| `SAFE-PUBLICATION-001` | Document visibility/GPL basis; no upstream submission or unreviewed assets | ADR 0001 | `TEST-SAFE-POLICY` | `evidence/p0/gate0/preflight.md` | P0-FINAL | OpenGFX and large assets require distribution-safe handling. |
| `SAFE-SCOPE-001` | Exclude PORT-006+, scalar/CUDA/RL/GUI work and overclaims | `docs/P0_SCOPE.md` | `TEST-SAFE-POLICY` | `evidence/p0/gate0/push-proof.md` | P0-FINAL | Closing policy scan proves later-phase code is absent. |

## PORT-001: reproducible external authority

| Requirement | Contract | Implementation | Test | Evidence | Gate | Status | Reviewer note |
|---|---|---|---|---|---|---|---|
| `BUILD-MANIFESTS-001` | Strict source/toolchain/dependency/build/test/content manifests | manifest schemas and validator | `TEST-BUILD-CONTRACT` | PORT-001 release bundle | PORT-001 | IN_PROGRESS | Historical run passed; final bundle must durably retain raw artifacts. |
| `BUILD-PROFILE-001` | Exact Ubuntu, compiler, dependency, OpenGFX, and headless profile | configure runner and host verifier | `TEST-BUILD-CONTRACT` | toolchain probes | PORT-001 | IN_PROGRESS | Release uses the hash-locked tools Python and frozen package profile. |
| `BUILD-REPRODUCIBILITY-001` | Two clean independent builds with normalized output equality | `port001_gate.sh`, comparison tool | `TEST-BUILD-CONTRACT` | PORT-001 release bundle | PORT-001 | IN_PROGRESS | Final top gate performs and then repeats this reconstruction. |
| `BUILD-UPSTREAM-TESTS-001` | Discover exactly 99 and pass all 99 with JUnit/raw logs | `test_reference.sh` | `TEST-BUILD-CONTRACT` | PORT-001 release bundle | PORT-001 | IN_PROGRESS | Any inventory drift is a source/profile failure, not an adjusted expectation. |
| `BUILD-HEADLESS-SMOKE-001` | Exactly 128 headless ticks, isolated config, offline | `smoke_reference.sh` | `TEST-BUILD-CONTRACT` | PORT-001 release bundle | PORT-001 | IN_PROGRESS | The executable identity and complete smoke log remain tied to the run. |

## PORT-002: frozen road-freight fixture

| Requirement | Contract | Implementation | Test | Evidence | Gate | Status | Reviewer note |
|---|---|---|---|---|---|---|---|
| `FIX-IDENTITY-001` | Freeze save, map, settings, behavior, content, and builder identities | fixture manifest | `TEST-FIXTURE-CONTRACT` | corrected `ffb34c` reproduction | PORT-002 | IN_PROGRESS | Smoke-setting correction left save and map bytes unchanged. |
| `FIX-STRUCTURE-001` | Prove 64x64 map, company, industries, cargo, route, vehicle, and coordinates | fixture contract runner | `TEST-FIXTURE-CONTRACT` | corrected reproduction README | PORT-002 | IN_PROGRESS | Dynamic facts are confirmed again through native replay. |
| `FIX-SETTINGS-001` | Validate/hash every reached behavior setting | normalized settings | `TEST-FIXTURE-CONTRACT` | runtime setting probe | PORT-002 | IN_PROGRESS | Frozen normalized digest begins `6def2c6d`. |
| `FIX-REPRODUCTION-001` | Two isolated builder runs reproduce exact save and map bytes | fixture builder | `TEST-FIXTURE-CONTRACT` | reproduction JSON | PORT-002 | IN_PROGRESS | Both regenerated 10,008-byte save and 49,152-byte map exactly. |
| `FIX-MILESTONES-001` | Two loads match; native replay reaches pickup, delivery, and payment | native replay driver | `TEST-FIXTURE-RUNTIME` | planned runtime replay result | PORT-002 | IN_PROGRESS | Depends on the completed instrumentation collector. |

## PORT-003: commands and non-perturbing instrumentation

| Requirement | Contract | Implementation | Test | Evidence | Gate | Status | Reviewer note |
|---|---|---|---|---|---|---|---|
| `CMD-FORMAT-001` | Strict binary command input, canonical header, checksums, limits, and trailing-byte rejection | command-input codec/schema | `TEST-COMMAND-CONTRACT` | planned validation result | PORT-003 | IN_PROGRESS | Native and hostile-input evidence remains to execute. |
| `CMD-NATIVE-DISPATCH-001` | Typed native command dispatch only; no state mutation or GUI driving | native command driver | `TEST-COMMAND-CONTRACT` | planned dispatch audit | PORT-003 | IN_PROGRESS | Review records the exact OpenTTD test/execute entry point. |
| `CMD-RESULTS-001` | Capture intent, native test/execute result, IDs, cost, category, rejection, and projection | native command driver | `TEST-COMMAND-CONTRACT` | planned native result inventory | PORT-003 | IN_PROGRESS | Golden actions succeed exactly; negative corpus preserves rejection. |
| `CMD-RANDOM-PREFIXES-001` | 10,000 seeded prefixes, at least 30% invalid, two deterministic repeats | differential runner | `TEST-COMMAND-CONTRACT`, `TEST-DIFFERENTIAL-CAMPAIGN` | planned prefix summary | P0-FINAL | IN_PROGRESS | Failures are rerun, minimized, and retained. |
| `TRACE-PATCH-SERIES-001` | Apply/reverse reviewed patches only in disposable pinned worktrees | instrumentation series | `TEST-INSTRUMENTATION-CONTRACT` | planned series digest | PORT-003 | IN_PROGRESS | Series targets the frozen 816/757 registry. |
| `TRACE-BOUNDARIES-001` | Replay-start, post-command, post-tick, checkpoint, and terminal boundaries in exact order | trace bridge | `TEST-INSTRUMENTATION-CONTRACT` | planned boundary coverage | PORT-003 | IN_PROGRESS | Native, C17, and Python counts must agree. |
| `TRACE-PROJECTION-001` | Every reached authoritative field, fixed-width, registry order, no mutating getter | generated projection adapter | `TEST-INSTRUMENTATION-CONTRACT` | planned runtime coverage | PORT-003 | IN_PROGRESS | Exactly 757 authoritative fields are expected at each full boundary. |
| `TRACE-RNG-TIMERS-001` | Both RNG streams and all future-influencing timer/controller/schedule state | projection adapter | `TEST-INSTRUMENTATION-CONTRACT` | planned RNG/timer audit | PORT-003 | IN_PROGRESS | Native LinkGraph threads remain enabled. |
| `TRACE-MAP-POOLS-001` | All 4,096 tiles plus native pool allocation/free-list/order/stable-ID state | projection adapter | `TEST-INSTRUMENTATION-CONTRACT` | planned map/pool audit | PORT-003 | IN_PROGRESS | Native packet/container order is preserved, not conveniently sorted. |
| `TRACE-IO-FAIL-CLOSED-001` | First-error propagation, bounded I/O, retained partial, no false final tape | trace sink | `TEST-INSTRUMENTATION-CONTRACT` | planned I/O fault report | PORT-003 | IN_PROGRESS | EINTR, short write, ENOSPC, fsync, rename, and permission faults are explicit. |
| `TRACE-DETERMINISM-001` | Two golden, 20 serial, and eight isolated parallel recordings share one digest | oracle campaign | `TEST-ORACLE-DETERMINISM` | planned determinism summary | PORT-003 | IN_PROGRESS | Time, locale, path, and process order never enter authority. |
| `TRACE-NONPERTURBATION-001` | Plain/off/on continuation equality through 10,000 ticks without forced synchronization | oracle campaign | `TEST-ORACLE-DETERMINISM` | planned non-perturbation summary | PORT-003 | IN_PROGRESS | Any pause or native scheduling difference is a hard failure. |

## PORT-004: tape, independent decoding, comparison, and minimization

| Requirement | Contract | Implementation | Test | Evidence | Gate | Status | Reviewer note |
|---|---|---|---|---|---|---|---|
| `TAPE-FORMAT-001` | Reviewed prefix/header/record/projection/terminal/trailer/SHA-256 v1 bytes | C17 reader/writer, ADR 0004 | `TEST-TAPE-NATIVE` | planned unit summary | PORT-004 | IN_PROGRESS | Golden bytes need independent review, not blind regeneration. |
| `TAPE-WRITER-001` | Checked arithmetic, canonical streaming, and atomic finalization | writer and partial finalizer | `TEST-TAPE-NATIVE` | planned writer results | PORT-004 | IN_PROGRESS | Unequal existing output and every output fault are fail-closed. |
| `TAPE-READER-001` | Reject truncation, corruption, overflow, reserved/noncanonical/trailing bytes | tape reader | `TEST-TAPE-NATIVE` | planned reader results | PORT-004 | IN_PROGRESS | Two mapped static defects prevent PASS until closed. |
| `TAPE-PYTHON-REFERENCE-001` | Independent Python acceptance/classification and logical decode | Python decoder | `TEST-TAPE-PYTHON` | planned differential result | PORT-004 | IN_PROGRESS | It does not import or call production parsing logic. |
| `TAPE-NEGATIVE-CORPUS-001` | Every-byte small-vector truncation plus every-region and semantic fault | native unit corpus | `TEST-TAPE-NATIVE`, `TEST-FAULT-INJECTION` | planned malformed inventory | PORT-004 | IN_PROGRESS | Each case declares family and earliest location. |
| `TAPE-RESOURCE-BOUNDS-001` | Bounded memory/work/input/output for reader, writer, comparator, minimizer, fuzz | C17 limits | `TEST-TAPE-NATIVE` | planned resource report | PORT-004 | IN_PROGRESS | Sparse near-limit tests prohibit whole-file theoretical-tape copies. |
| `CMP-IDENTITY-001` | Stop before state comparison and exit 2 on any identity mismatch | comparator | `TEST-COMPARATOR` | planned identity report | PORT-004 | IN_PROGRESS | Every identity component gets a targeted fault. |
| `CMP-FIRST-DIVERGENCE-001` | Exit 1 on exact earliest authoritative boundary/field/element/value difference | comparator | `TEST-COMPARATOR` | planned field report | PORT-004 | IN_PROGRESS | Diagnostics cannot filter or conceal authority. |
| `CMP-REPORT-001` | Bounded schema-valid context, identities, prior checkpoint, last command, source policy, argv | comparator/report schema | `TEST-COMPARATOR` | planned report validation | PORT-004 | IN_PROGRESS | Report write failures are failures. |
| `MIN-SIGNATURE-001` | Minimize against complete divergence signature | minimizer | `TEST-MINIMIZER` | planned signature report | PORT-004 | IN_PROGRESS | A matching field ID alone is insufficient. |
| `MIN-VALID-PREFIX-001` | Emit independently valid finalized smallest logical prefix reproducing the same signature | minimizer/finalizer | `TEST-MINIMIZER` | planned minimized result | PORT-004 | IN_PROGRESS | Raw truncation never qualifies. |

## PORT-005: field completeness, caches, and invariants

| Requirement | Contract | Implementation | Test | Evidence | Gate | Status | Reviewer note |
|---|---|---|---|---|---|---|---|
| `FIELD-REGISTRY-001` | Unique typed 816-field registry with source, owner, lifecycle, rationale, samples, counts, offsets, sentinels | field registry/validator | `TEST-FIELD-SCHEMA` | registry digest | PORT-005 | IN_PROGRESS | Frozen registry digest begins `76221444`; 757 fields are authoritative. |
| `FIELD-COMPLETENESS-001` | Every reached global/timer/RNG/map/pool/object/ledger/LinkGraph/kdtree/cache classified | completeness matrix/generator | `TEST-FIELD-SCHEMA` | planned runtime projection audit | PORT-005 | IN_PROGRESS | Static audit passed; runtime and omission evidence remain. |
| `FIELD-INVARIANTS-001` | Structural, economic, cargo, and determinism invariants after each projection | invariant adapter | `TEST-INVARIANTS` | planned invariant fault summary | PORT-005 | IN_PROGRESS | Earliest failure retains partial tape and enters the ledger. |
| `CACHE-CLASSIFICATION-001` | Reached cache defaults authoritative unless full derived-rebuild protocol passes | ADR 0006 | `TEST-CACHE-EXPERIMENTS` | planned classification result | PORT-005 | IN_PROGRESS | Static cache tooling alone is diagnostic. |
| `CACHE-CONTINUATION-001` | Production clear/rebuild, immediate/next-step/two-load/10,000-tick equality | cache experiment runner | `TEST-CACHE-EXPERIMENTS` | planned continuation result | PORT-005 | IN_PROGRESS | A failed cache experiment reclassifies the cache authoritative. |

## Cross-cutting verification and evidence

| Requirement | Contract | Implementation | Test | Evidence | Gate | Status | Reviewer note |
|---|---|---|---|---|---|---|---|
| `TEST-NATIVE-MATRIX-001` | Seven distinct GCC/Clang debug/release/sanitizer/coverage/fuzz profiles | presets and warnings | `TEST-BUILD-MATRIX` | planned build matrix | P0-FINAL | IN_PROGRESS | Build aliases do not qualify. |
| `TEST-SANITIZERS-001` | ASan+leaks and fail-fast UBSan over every native entry point | sanitizer runner | `TEST-SANITIZERS` | planned sanitizer report | P0-FINAL | IN_PROGRESS | Recovery after a finding cannot pass. |
| `TEST-STATIC-ANALYSIS-001` | Compiler warnings, Tidy, analyzer, ShellCheck, semantic/schema, secret/license/policy scans | static runner | `TEST-STATIC-ANALYSIS` | planned static report | P0-FINAL | IN_PROGRESS | Two diagnosed C defects remain open. |
| `TEST-COVERAGE-001` | Frozen line/function thresholds and explicit risk-branch proof | coverage runner | `TEST-COVERAGE` | planned coverage report | P0-FINAL | IN_PROGRESS | Tests must assert behavior, not merely execute lines. |
| `TEST-MUTATION-001` | Every reviewed mandatory mutant killed by expected semantic detector | mutation runner/plan | `TEST-MUTATION` | planned mutation report | P0-FINAL | IN_PROGRESS | Unrelated crash/build failure is not a kill. |
| `TEST-FUZZ-001` | Independent bounded release campaign for every byte entry point | fuzz targets/runner | `TEST-FUZZ` | planned fuzz summary | P0-FINAL | IN_PROGRESS | Interesting failures become content-addressed regressions. |
| `TEST-DIFFERENTIAL-001` | Fixed external oracle and C17/Python internal differentials | differential runner | `TEST-DIFFERENTIAL-CAMPAIGN` | planned differential summary | P0-FINAL | IN_PROGRESS | This makes no scalar parity claim. |
| `TEST-FAULT-INJECTION-001` | Required deterministic identity/tape/command/projection/invariant/I/O/output faults | fault runner | `TEST-FAULT-INJECTION` | planned fault summary | P0-FINAL | IN_PROGRESS | Every fault has one expected owner and earliest signature. |
| `TEST-CI-001` | Thirteen mandatory SHA-pinned least-privilege jobs | P0 workflow | `TEST-CI-POLICY` | planned CI job report | P0-FINAL | IN_PROGRESS | CI smoke cannot substitute for local-release counts. |
| `TEST-TRACEABILITY-001` | Bidirectional requirement/test, implementation ownership, evidence, defect, and gate lint | traceability validator | `TEST-TRACEABILITY-LINT` | machine registry | P0-FINAL | IN_PROGRESS | All rows stay honest until closure evidence exists. |
| `EVID-BUNDLE-001` | Content-addressed complete evidence with verified digests and no local-only dependency | evidence bundler | `TEST-EVIDENCE-CONTRACT` | planned bundle manifest | P0-FINAL | IN_PROGRESS | Large assets need durable approved storage. |
| `EVID-LEDGER-001` | Append-only defect/divergence history and zero nonclosed P0 entries | machine ledger/human view | `TEST-EVIDENCE-CONTRACT` | ledger documents | P0-FINAL | IN_PROGRESS | Two current diagnosed defects block release. |
| `EVID-FINAL-RESULT-001` | 34 ordered stages twice, schema-valid PASS JSON, exact 26-section report, clean pushed tip | top gate/result schema/report | `TEST-EVIDENCE-CONTRACT` | planned `P0_GATE_RESULT.json` | P0-FINAL | IN_PROGRESS | PASS is impossible while any gate, digest, count, tree, or push proof is incomplete. |

## Semantic lint rules

`./scripts/ci/p0_traceability.sh --tools-python /absolute/path/to/python`
performs checks that JSON Schema cannot express:

1. every mandatory requirement has at least one declared test and evidence path;
2. every test points back to every requirement that names it, and vice versa;
3. all requirement and test IDs are unique and use the allowed stable prefixes;
4. every P0 implementation file selected by the owned source inventory matches
   at least one explicit ownership rule;
5. every `PASS` row points only to existing production and evidence files;
6. every ledger entry has a traceability mapping;
7. an open/diagnosed/fixed-pending defect cannot map to a `PASS` requirement
   without an explicit reviewed exception;
8. a final machine gate result containing a mandatory `SKIP` is rejected;
9. every machine requirement ID appears in this human review view;
10. the registry records the exact SHA-256 of its committed schema.

The final closure transition is intentionally mechanical but not automatic:
reviewers inspect raw evidence, update a row to `PASS`, and rerun the linter.
The top-level gate then independently validates all artifacts and counts. This
prevents a documentation edit from manufacturing a release result.

## Current critical path

The remaining dependency chain is:

1. finish the PORT-003 native collector and prove full 757-field runtime
   projection without altering LinkGraph scheduling;
2. finish the PORT-004 reader/writer/comparator/minimizer corrections and close
   both static-analysis defects;
3. run fixture milestones, determinism, non-perturbation, independent decode,
   divergence, minimization, cache, invariant, and 10,000-tick experiments;
4. execute the native quality matrix, release fuzz counts, mutation campaign,
   coverage thresholds, randomized prefixes, and all fault classes;
5. assemble and verify durable evidence, close the append-only ledger, run the
   34-stage gate twice, prove the clean pushed branch, and only then change every
   satisfied row and the final machine result to `PASS`.

No later-phase task is allowed before this graph closes.
