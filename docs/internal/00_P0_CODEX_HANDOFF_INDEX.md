# P0 Patches 0003–0007 Codex Handoff Index

> **Legacy workstream notice (2026-07-31):** This index preserves unfinished,
> user-owned P0 freight-oracle work. It is not the active project handoff. Follow
> `NEXT_STAGES_IMPLEMENTATION_HANDOFF.md` for the 32 by 32 passenger-bus platform
> critical path, and do not discard the artifacts indexed here.

## Status

| Item | Status |
|---|---|
| Handoff package | `READY_FOR_REPOSITORY_EVIDENCE_GATE` |
| Patch implementation | `NOT ESTABLISHED BY THIS HANDOFF` |
| Patch-series result | `NOT RUN` |
| Full P0 release | `IN_PROGRESS` |

This package is a binding implementation and verification contract for completing OpenTTD oracle instrumentation patches 0003 through 0007. The package does not claim that the five patches exist, compile, pass, or close P0. Codex must establish current-checkout facts, preserve all user work, implement only the authorized scope, and retain objective evidence.

The uploaded documents define the architectural contract, exact OpenTTD source pin, fixture, tape format, field/cache policy, testing strategy, mutation obligations, traceability graph, defect ledger, and release boundary. They do not contain the current uncommitted outer diff, current 0001/0002 patch bytes, current trace-source layout, command registry, field registry, projection plan, generated bindings, exact runner argv arrays, or the local pinned source worktree. Codex has repository access and must resolve those facts through the evidence gate before production C++ work.

No command operand, registry action, field source, enum width, sentinel, C++ symbol, test command, existing trace path, or machine status may be guessed.

## Required Read Order

1. `00_P0_CODEX_HANDOFF_INDEX.md`.
2. `01_P0_EVIDENCE_GATE_AND_CONTRADICTION_REGISTER.md`.
3. `03_P0_COMMAND_AND_FIELD_MAPPING_CONTRACT.md`.
4. `02_P0_PATCHES_0003_0007_IMPLEMENTATION_SPEC.md`.
5. Every current-checkout authority required by E3.
6. Every pinned source file reached by the six-command and 757-field audits.
7. `04_P0_HANDOFF_VALIDATION_REPORT.md` before accepting the handoff package itself.

Codex must not begin production C++ edits until E0 through E13 pass. When a gate fails, Codex must report the first root contradiction with exact paths, hashes, symbols, commands, and observed values rather than select a fallback architecture.

## Binding Authority Order

Conflicts are resolved in this order:

1. Pinned OpenTTD source and tests at commit `29f808ef0022064e6d9a83c8476d1e0f4686af86`.
2. Repeatable observations from binaries built from that commit under the frozen reference profile.
3. Current repository machine authorities, strict schemas, generated registries, validated manifests, machine traceability, machine ledger, and effective patch `series`.
4. `NEXT_STAGES_IMPLEMENTATION_HANDOFF.md` and `OPENTTD_P0_ORACLE_CONTRACT_AGENT_PROMPT.md` at their registered SHA-256 values.
5. Accepted ADRs 0001–0006.
6. Current human source register, test strategy, field-completeness matrix, traceability view, and append-only defect/divergence view.
7. This package, which binds procedure and patch ownership but never overrides pinned source or stricter validated machine authority.

Current OpenTTD `master`, remembered APIs, GUI call sites, generated prose summaries, convenience assumptions, and later scalar/CUDA/RL plans are not behavioral authority.

## Handoff Files

| File | Purpose | Acceptance condition |
|---|---|---|
| `00_P0_CODEX_HANDOFF_INDEX.md` | Authority, source identity, read order, fixed patch names, and claim boundary | Read before all work |
| `01_P0_EVIDENCE_GATE_AND_CONTRADICTION_REGISTER.md` | Read-only repository audit, narrow traceability-shape correction, contradiction resolutions, exact pre-code outputs, and hard stops | E0–E13 pass with retained evidence |
| `02_P0_PATCHES_0003_0007_IMPLEMENTATION_SPEC.md` | Binding 12-section implementation, test, execution, verification, and finished-product contract | Every owned patch and integration criterion passes |
| `03_P0_COMMAND_AND_FIELD_MAPPING_CONTRACT.md` | Source-backed six-family native command contract and mandatory exhaustive 757-row mapping procedure | Six-row command ledger and 757-row field ledger validate |
| `04_P0_HANDOFF_VALIDATION_REPORT.md` | Static validation of this generated handoff package, source hashes, structure, and known information boundary | Every package check passes or is explicitly identified as a repository-side prerequisite |

## Uploaded Source Digest Inventory

| Input | SHA-256 | Governing role |
|---|---|---|
| `Pasted text(58).txt` | `de64bbbb144b715bcacca082e3d4d5d9729a9b8461f8955f80b20194a0ed3712` | Required response structure, limitations, and patch deliverables |
| `P0_SUPPORTED_SCOPE.md` | `7016948c6bd36e2be248f1fdfacb73a96e0dbabd9341284b8149ddb28f5642ae` | PORT-001 through PORT-005 scope and completion boundary |
| `P0_SOURCE_REGISTER.md` | `6de435ceb2ef1f5a1603c27968f2f5efd87416183ceb732db0b520270a4b20eb` | Exact-commit source anchors and reached-source expansion rule |
| `P0_TEST_STRATEGY.md` | `b21415139c5e3abdf2ed33c95fc3f0f7d16b85e530cc2cb768fbf07ec0a8c3e1` | Test layers, build matrix, campaigns, and release evidence |
| `PORT005_FIELD_COMPLETENESS.md` | `aec9a42356d8c10b96c856d0fc69cd3280c60f0117ff9288396e6436b86feaf0` | Field-family source-owner and continuation review |
| `P0_DEFECT_DIVERGENCE_LEDGER.md` | `ca1792fd6a89321bbd07679d16e6ba1c062288a853a7ea234082873812e65b64` | Current nonclosed defect state and closure policy |
| `P0_MUTATION_PLAN.md` | `ed97effe82fe19c91dd6a1d1151f962e1d4db87423eb70132b1b664e245ca5ed` | Mandatory mutation operators and semantic kill requirements |
| `P0_REQUIREMENTS_TRACEABILITY.md` | `f5aab096f8256db634be45e2dbe5e5650741da87769ccd884010105888c582e2` | Requirement, implementation, test, evidence, defect, and gate graph |
| `0004-tape-format-v1.md` | `68dd7aab2444a5d69acdc6954ac09cafc40f3e88e6020ef78312d174dea74847` | Tape-v1 bytes, command lifecycle, projection, checkpoints, terminal, and finalization |
| `0005-field-schema-and-cache-policy.md` | `5f6369b14e06673c8c482f94599341f8047fb53531ff54bf02b269702b3552bc` | Stable field IDs, canonical types, ownership, caches, and continuation policy |
| `0006-evidence-and-release-policy.md` | `61094615156caba8b570f74ac7c67f20ee90c5552c6e1f67952c79f99b6ba238` | Release profile, evidence retention, aggregation, and publication |
| `0001-project-basis-and-publication.md` | `b88ee23d1b63de275573282c8b69c9173c6ce216cc30ee2482f3443d465b8b8c` | Project authority, branch/publication policy, GPL boundary, and submodule rules |
| `0002-reference-build-profile.md` | `25b5542b37406278b5047bd7388479ea387f95a3563f3b94e9476ff87388c358` | Frozen host, tools, options, exact 99-test inventory, and reproducibility profile |
| `0003-fixture-selection.md` | `e726d479701f1ccea7d0f94b710965b6096e355342404953cacb94a209997618` | Exact 64×64 coal route, ten command instances, six native families, and eight checkpoints |

## Fixed Task Facts

1. The working branch for this task is exactly `fix/p0-build-portability`. Codex must not switch or rename branches. ADR 0002's older `port/p0-oracle-contract` name remains a release-policy discrepancy requiring later review.
2. The permanent submodule path is `openttd-upstream`, pinned to `29f808ef0022064e6d9a83c8476d1e0f4686af86`, and must remain clean.
3. Before implementation, the effective patch series contains only:
   - `0001-trace-sink-and-codec.patch`;
   - `0002-build-and-run-identity.patch`.
4. The five assigned new patch filenames are exactly:
   - `0003-native-command-input-and-boundary-records.patch`;
   - `0004-global-state-and-map-projection.patch`;
   - `0005-pool-and-entity-projection.patch`;
   - `0006-optional-route-controller-cargo-diagnostics.patch`;
   - `0007-test-consistency-and-nonperturbation-hooks.patch`.
5. P0 is a deterministic external oracle and host-side parity contract, not a gameplay backend.
6. The frozen field registry contains 816 entries, exactly 757 of which are authoritative at every complete projection.
7. Registry v1 classifies no reached future-influencing cache as `derived_rebuild`; reached caches remain authoritative unless the full accepted protocol proves otherwise.
8. The fixture has ten command instances from six native families: three `BuildRoadLong`, one `BuildRoadDepot`, two `BuildRoadStop`, one `BuildVehicle`, two `InsertOrder`, and one `StartStopVehicle`.
9. Accepted command grammar is intent → successful native test → successful native execute → complete post-command projection. Rejected grammar is intent → failed native test → complete post-command projection, with no execute and no returned-ID side result.
10. `BuildVehicle` returns `VehicleID` through its native execute tuple. `CmdBuildRoadStop` returns only `CommandCost`; station identity must be copied from the final execute-path `st->index` through the narrowly guarded active trace context, without changing the native signature or scanning pools.
11. Mandatory complete projection emissions occur after `REPLAY_START`, after every command, and after every completed native tick. Checkpoint and terminal records are evaluated and emitted immediately after their governing complete projection; they do not trigger duplicate projections.
12. Map authority is the ten raw native planes, each with exactly 4,096 elements in numeric `TileIndex` order.
13. Optional diagnostics are default-off, separately declared and framed, excluded from authoritative equality, and prohibited from invoking extra work.
14. Determinism counts are two golden recordings, twenty serial recordings, and eight isolated parallel recordings for the same feature configuration.
15. Randomized command coverage is exactly 10,000 seeded prefixes, at least 30% invalid, executed twice deterministically.
16. The continuation campaign uses two independent loads and 10,000 native ticks.
17. The uploaded human traceability view contains 56 unique requirement IDs. Four safety rows omit the explicit Status cell; the validated machine JSON is the only permitted source for restoring those missing cells.
18. `local-release` is the only release-closing profile. `ci-smoke` cannot close P0.
19. For an active external action, `COMMAND_INTENT` is emitted only inside the top-level native `InternalPost` path after native prechecks succeed, estimate/network-only modes are excluded, and native `ClientID` normalization is complete, immediately before `CommandHelper::Execute`. Test and execute hooks copy already-produced results into a preallocated bounded context; they perform no record I/O and invoke no command again.
20. The replay driver restores its outer company context immediately after the single typed `Post` returns and before result-record publication or authoritative projection. The active oracle path uses no callback and suppresses only user-interface presentation side effects; any pre-test condition that prevents the deterministic offline post path is an explicit fatal lifecycle error.
21. ADR 0003 contains an internal status contradiction: its accepted/frozen PORT002A language assigns remaining funding and actual-cost evidence to PORT002B, while stale text still says missing funding evidence prevents PORT002A from passing. Preserve the frozen PORT002A artifacts, treat PORT002B and overall PORT002 as open, and require a reviewed ADR correction before final P0 `PASS`.

## Current Known Full-P0 Blockers

| ID | Uploaded status | Location | Effect |
|---|---|---|---|
| `DEF-P0-0001` | `DIAGNOSED` | `parity/src/tape_reader.c:1013` | Static gate failure and ambiguous cleanup ownership |
| `DEF-P0-0002` | `DIAGNOSED` | `parity/tools/tape_main.c:718` | Filter parsing lacks a statically provable nonnull guard |
| `TRACEABILITY-SHAPE-001` | Confirmed in uploaded human view | Four safety requirement rows | Human table lacks explicit Status cells and must be reconciled to validated machine authority |
| `BRANCH-POLICY-001` | Documentation discrepancy | Task branch versus ADR 0002 branch name | Final release requires a reviewed canonical release-branch decision and remote-tip proof |
| `FIXTURE-STATUS-001` | ADR 0003 internal status contradiction | PORT002A is declared accepted/frozen and funding evidence is assigned to PORT002B, but stale text says PORT002A cannot pass without that evidence | Preserve the frozen PORT002A fixture and identities; treat PORT002B and overall PORT002 as open; require a reviewed ADR correction before final P0 `PASS` |

The first two defects block full P0 until separately fixed, regression-tested, evidenced, and closed. They do not authorize unrelated changes in patches 0003–0007. The traceability shape issue permits only the narrow machine-backed human-table correction defined by E13. The fixture-status contradiction does not authorize changing fixture bytes, command instances, identities, or expected results to make the prose agree.

## Required Codex Outputs Before Production C++

- complete repository/branch/submodule/authority audit;
- baseline 0001/0002 apply, build, test, and reverse evidence;
- exact six-row command dispatch ledger with native symbols, operands, results, locations, company context, fixture instances, and negative cases;
- exact 757-row field mapping ledger plus machine JSON and explicit P4/P5 set-difference proof;
- exact source-register closure audit;
- exact projection/tape compatibility audit;
- exact current test argv inventory keyed by stable test ID;
- exact touched-file manifest covering every planned patch hunk and repository-side change;
- validated 56-ID traceability shape audit;
- current defect/divergence ledger state.

## Patch-Series Completion Boundary

`PATCH_SERIES_PASS` requires all seven exact patches to apply in order, every prefix to build and pass its owned tests, the full series to reverse to the exact clean pin, all six command families to use one typed native `Post`, every complete projection to contain exactly all 757 authoritative fields once, checkpoints and diagnostics to obey their contracts, deterministic/non-perturbation campaigns to pass at frozen counts, and every required artifact to validate.

`PATCH_SERIES_PASS` does not imply `P0 PASS`. Full P0 additionally requires all PORT-001 through PORT-005 gates, zero nonclosed defects/divergences, durable evidence, valid 56-ID traceability, a clean outer tree and submodule, final local commit equal to the configured remote tip, and the exact 34-stage `local-release` gate passing twice without tracked-source change.
