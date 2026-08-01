<!--
Binding implementation specification for the OpenTTD-RL P0 instrumentation series.
The only top-level sections are the twelve sections required by the task contract.
Every checkout-specific trace, test, runner, generated-binding, and canonical-document
path must be resolved by the mandatory evidence gate before any production edit. Patch
filenames 0003–0007 are fixed because the task states those files do not yet exist.
-->

> **Legacy workstream notice (2026-07-31):** This specification preserves the
> unfinished P0 freight-oracle patch design. It is not the active project roadmap;
> use `NEXT_STAGES_IMPLEMENTATION_HANDOFF.md` for Version 1 work. Do not discard or
> rewrite the user-owned patch work merely because it is off the new critical path.

# 1. AUTHORITATIVE INTERPRETATION

## 1.1 Scope

Patches 0003 through 0007 complete the native OpenTTD instrumentation portion of P0. They do not implement a scalar gameplay backend, CUDA backend, RL environment, GUI automation, generalized OpenTTD support, or later-phase performance work. `P0_SUPPORTED_SCOPE.md:38-53` limits PORT-003 to strict command ingestion, native command submission, exact command-boundary results, complete authoritative projection, separately declared diagnostics, and trace-disabled/enabled/self-checking non-perturbation profiles.

The implementation must preserve the external-oracle architecture:

```text
pinned OpenTTD source and frozen fixture
        -> strict prevalidated command input
        -> native typed command test/execute path
        -> complete read-only authoritative projection
        -> partial tape journal
        -> independent C17 finalization/validation/comparison
        -> determinism, non-perturbation, cache, and continuation evidence
```

A valid tape does not prove non-perturbation. Equal tapes do not prove field completeness. Static field review does not prove runtime projection. Patch-series completion does not imply full P0 completion.

## 1.2 Official Patch Responsibilities

The official sequence remains binding:

| Patch | Binding responsibility | Explicit non-goals |
|---|---|---|
| 0003 | Strict native command-input handling, explicit company context, typed native `Post`, native test/execute result capture, command scheduling, command-boundary records, and fail-closed input/runtime behavior | No gameplay reimplementation; no full state projection beyond boundary integration; no optional route/cargo diagnostics |
| 0004 | Complete singleton/global projection: game state, clocks, timers, both RNG streams, runtime economy globals, global settings, all 4,096 map tiles, raw map planes, animated-tile order, and shared projection framework | No entity/pool projection; no optional diagnostics; no test-only mutation hooks |
| 0005 | Complete entity, pool, allocation, embedded-container, stable-reference, authoritative-cache, and cross-object projection; complete the combined 757-field projection; add source-reviewed named-checkpoint predicates once full state is available | No optional diagnostic payloads; no cache reclassification without the accepted protocol; no forced thread synchronization |
| 0006 | Optional route, controller, cargo, and other registry-declared diagnostic observation; default-off declaration and record isolation | No authoritative field ownership; no extra pathfinding; no cache rebuild; no checkpoint becoming optional |
| 0007 | Test-only consistency facilities, invariant integration, deterministic replay campaigns, non-perturbation campaigns, diagnostics isolation campaigns, first-divergence retention, timeout/crash handling, and final patch-series verification | No release gameplay mutation interface; no weakening of mandatory gates; no later-phase implementation |

## 1.3 Reconciliation of Requested Outcome Labels

The requested outcome labels are acceptance outcomes, not replacement patch names:

| Outcome label | Owning patch or patches | Interpretation |
|---|---|---|
| Native command dispatch | 0003 | All six action families post once through OpenTTD typed command machinery under explicit company context; hooks observe native test/execute results |
| Complete 757-field projection | 0004 + 0005 | 0004 owns singleton/global/map fields; 0005 owns pooled/entity/container/cache fields; union is exactly all 757 authoritative fields and intersection is empty |
| Replay milestones | Codec support from 0001; state predicates and emissions completed in 0005; campaign comparison in 0007 | Checkpoints are required trace records, not optional diagnostics; exact IDs 1–8 and first-occurrence semantics apply |
| Determinism campaigns | 0007, using 0003–0006 behavior and PORT-004 tooling | Two golden, twenty serial, eight isolated parallel recordings, two-load/10,000-tick continuation, and randomized-prefix repetition |
| Non-perturbation campaigns | 0007, with diagnostic isolation from 0006 | Plain, patched-OFF, patched-ON/runtime-disabled, patched-ON/enabled, diagnostics-off/on, and trace output behavior comparisons |

## 1.4 Binding Contradiction Resolutions

1. **Branch name:** the exact assigned working branch is `fix/p0-build-portability`. Codex must not switch or rename branches; a different current branch is a hard stop. ADR 0002's `port/p0-oracle-contract` name remains a final-release policy discrepancy until reviewed.
2. **Six actions versus ten commands:** six denotes native action families; ten denotes frozen fixture command instances.
3. **Patch filenames:** the pre-code `series` must contain only the exact existing 0001/0002 prefix. Create these exact new files sequentially and append each only after its patch-prefix gate passes: `0003-native-command-input-and-boundary-records.patch`, `0004-global-state-and-map-projection.patch`, `0005-pool-and-entity-projection.patch`, `0006-optional-route-controller-cargo-diagnostics.patch`, and `0007-test-consistency-and-nonperturbation-hooks.patch`. A conflicting reserved name is a repository contradiction.
4. **Patches 0001/0002 tested:** prior claims are not current evidence. Reapply, rebuild, retest, and reverse the current bytes before 0003.
5. **Command result grammar:** tape v1 governs. “Result” is not a third command phase: native test data is encoded in `COMMAND_TEST_RESULT`, and final native execute data is encoded in `COMMAND_EXEC_RESULT`. A rejected test has no execute record; an accepted scheduled command has exactly one execute record.
6. **Field completeness:** the static source-owner/continuation review authorizes implementation but does not close runtime or continuation gates.
7. **Caches:** registry v1 classifies no reached future-influencing cache as `derived_rebuild`; do not omit or normalize a reached cache.
7A. **Settings ownership:** the documented sequence assigns global settings to 0004, while source-register rows also associate some settings with 0005/0006. Resolve by owner, not filename convenience: process-wide `_settings_game` values belong to 0004; company-owned service/renewal settings and other entity members belong to 0005; only registry-classified semantic observations belong to 0006. The validated projection plan must encode this split, or Codex must stop on contradiction.
8. **Map representation:** ten raw map planes are authoritative. Semantic decoding may be diagnostic or test logic but cannot replace raw fields.
9. **Manual cargo distribution:** LinkGraph state remains reachable and authoritative. Preserve native worker scheduling; do not join or force synchronous execution.
10. **Milestones:** required checkpoints are independent of optional diagnostics and must appear when diagnostics are disabled.
11. **Dirty outer tree:** preserve intentional uncommitted work. Final P0 release still requires a clean pushed branch.
12. **Known defects:** `DEF-P0-0001` and `DEF-P0-0002` block final P0 release until separately closed; they do not authorize unrelated patch edits.
13. **Traceability table shape:** the uploaded human view contains 56 requirement IDs, but four safety rows omit the explicit Status cell. The validated machine JSON controls the status value; Codex may restore only the missing human cell from machine authority, must preserve the reviewer note, and must not infer or transition status.
14. **Fixture status:** ADR 0003 declares PORT002A accepted/frozen and assigns funding and actual-cost evidence to PORT002B, but stale text still says missing funding evidence prevents PORT002A from passing. Preserve every frozen PORT002A fixture byte, command instance, identity, and accepted artifact; treat PORT002B and overall PORT002 as open; require a reviewed ADR correction before final P0 `PASS`. The contradiction does not block source-backed patch implementation and does not authorize editing the fixture to make the prose agree.

## 1.5 Conservative Decision Rule

When repository evidence cannot resolve an implementation detail:

1. stop before changing production code;
2. identify the exact conflicting files, symbols, hashes, and observed values;
3. choose no fallback behavior;
4. preserve the current submodule and outer changes;
5. report the narrow contradiction to the repository owner.

No placeholder, guessed symbol, fabricated field, speculative enum width, convenience accessor, or silent format migration is permitted.

# 2. GLOBAL INVARIANTS

Each invariant is mandatory and objectively testable.

1. **Exact source pin:** every patched build uses OpenTTD commit `29f808ef0022064e6d9a83c8476d1e0f4686af86`; pre/post checks compare full SHA.
2. **Clean permanent submodule:** `openttd-upstream` remains clean and unchanged; all patch application occurs in a disposable worktree.
3. **Seven-patch order:** exactly seven `series` entries apply in order and reverse in reverse order; every intermediate patch prefix builds and passes its assigned focused tests.
4. **Patch independence:** patch N applies after patches 0001 through N−1 without requiring later patches; patch N can be reviewed and reversed independently.
5. **Native command semantics:** each gameplay action uses one `Command<Commands::X>::Post`; no oracle code reproduces command legality, cost, allocation, or state mutation.
6. **Normalized intent placement:** `COMMAND_INTENT` is emitted exactly once inside the active top-level `InternalPost` path after tile and post prechecks succeed, estimate/network-only modes are excluded, and native `SetClientIds` normalization is complete, immediately before `CommandHelper::Execute`. Intent-write failure returns before native test. A pre-test post-path rejection is a fatal lifecycle error and is never fabricated as a failed native test.
7. **One native test:** each valid posted action reaches exactly one top-level native test call.
8. **Conditional one native execute:** a successful scheduled test reaches exactly one native execute call; a failed native test reaches zero execute calls.
9. **No duplicate command:** instrumentation never calls a command procedure, `Do`, `Post`, callback, or network adapter again to reconstruct trace data.
9A. **Top-level external scope:** command-phase hooks observe only the active externally scheduled oracle command at top-level command depth. Recursive/internal commands retain native behavior but never create extra external intent/test/execute records.
9B. **Bounded observation:** test, execute, and returned-ID hooks copy already-produced values into a preallocated bounded active-command context; they perform no record I/O, allocation, projection, callback, pathfinding, or command invocation.
10. **Explicit company context:** each command runs under the exact validated company context. The replay driver's outer company context is restored immediately after `Post` returns and before result-record publication, context clearing, or authoritative projection; no context may leak between actions.
10A. **Presentation isolation:** the active oracle post uses zero error-message presentation and no callback. It suppresses only `InternalPostBefore`/`InternalPostResult` user-interface effects while preserving every native command decision and gameplay effect. Any pause, estimate-only, send-only, invalid-company, or other pre-test condition that prevents the deterministic offline path is explicit fatal evidence.
11. **Whole-file prevalidation:** command input and canonical tape header validate completely before fixture load or gameplay exposure.
12. **Fail-closed malformed input:** unknown, truncated, corrupt, out-of-range, noncanonical, or trailing input produces no partial command execution.
13. **Accepted lifecycle:** accepted command order is intent, successful test, successful execute, complete post-command projection.
14. **Rejected lifecycle:** rejected command order is intent, failed test, complete post-command projection with no execute record; the post-command authoritative projection equals the immediately preceding authoritative state because no tick or other command may interleave.
15. **Replay-start order:** replay-start record precedes the initial complete projection.
16. **Same-tick order:** actions scheduled for the same native tick execute in strictly increasing public-step order before tick advancement.
17. **Post-tick order:** every completed native tick has one complete post-tick projection at the contract-defined point after the full native tick sequence.
18. **Checkpoint first occurrence:** each checkpoint ID 1–8 emits at most once, at the first complete boundary satisfying its source-reviewed predicate.
19. **Checkpoint independence:** required checkpoint emission is identical with diagnostics off and on.
20. **Complete field set:** every complete projection contains exactly 757 authoritative fields, each exactly once.
21. **Field order:** projection fields are strictly increasing by stable numeric field ID.
22. **Type agreement:** every field type, width, signedness, count, capacity, stable-ID width, sentinel, bitset shape, and padding agrees with the generated registry.
23. **Map completeness:** every complete projection contains exactly 4,096 elements for each registered raw map plane in numeric `TileIndex` order.
24. **Raw map fidelity:** no semantic re-encoding replaces the ten native planes.
25. **Stable identity:** pool and embedded-object references use contract-defined numeric or composite identities; pointers and process addresses never appear.
26. **Allocation fidelity:** exact pool capacity/cursors/used bitmap vector length/words/padding and source-backed free-list absence are preserved where registered.
27. **Native container order:** packet, path, order, flow, schedule, running-list, K-d tree free-list, animated-tile, and other registered container order is preserved exactly.
28. **Explicit absence:** empty, invalid, destroyed, free, optional, or inapplicable state uses the registry-defined count, presence bit, or sentinel; no field is silently omitted.
29. **Read-only projection:** projection performs no gameplay write, allocation, cache fill, cache invalidation, save/load, command, pathfinding, callback scheduling, or thread synchronization.
30. **RNG neutrality:** instrumentation and diagnostics consume zero gameplay or interactive RNG draws and leave all RNG state words identical to control runs.
31. **Timer neutrality:** instrumentation does not alter tick advancement, date fractions, timer counters, callback ordering, pause behavior, or subsystem schedules.
32. **LinkGraph neutrality:** instrumentation does not join, pause, abort, force, race-read, or make synchronous a LinkGraph worker; immutable state only is projected.
33. **Diagnostic isolation:** optional diagnostics are default-off, declared in the header, emitted only in optional record classes, and excluded from authoritative equality.
34. **No extra diagnostic work:** route/controller/cargo diagnostics observe already-computed values; they never invoke pathfinding, cache checks, or gameplay calculations.
35. **Canonical serialization:** output is independent of host padding, pointer size, locale, unordered-container iteration, allocator behavior, absolute paths, PID, and wall-clock time.
36. **Partial-journal contract:** the C++ producer writes only a valid `PARTIAL` journal; the C17 tool alone finalizes and publishes a complete tape.
37. **First-error propagation:** the first trace or projection failure stops recording, preserves the partial artifact, and produces explicit bounded evidence.
38. **No false completion:** write, fsync, finalization, validation, comparison, report, or evidence failure cannot produce a success exit or final tape.
39. **Backward compatibility:** command input and tape v1 bytes remain unchanged unless a proven incompatibility triggers an explicit versioned migration with tests and compatibility analysis.
40. **Source-register closure:** every newly reached source is registered before behavior is encoded.
41. **No unrelated edits:** patches and repository changes touch only files listed in the verified file plan.
42. **Upstream inventory preservation:** the exact 99 upstream tests remain discoverable and pass in every profile assigned by the test strategy.
43. **Deterministic repetition:** identical source/build/fixture/input/schema/feature identities yield byte-identical authoritative tapes at required counts.
44. **Non-perturbation:** plain, patched-OFF, patched-ON/runtime-disabled, and patched-ON/enabled runs have equal authoritative continuation outcomes; enabled mode adds only the trace side effect.
45. **Evidence identity:** every retained result records source, build, executable, fixture, settings, content, command input, command schema, field schema, instrumentation series, profile, argv, status, and artifact digests.
46. **Traceability shape:** machine and human traceability contain exactly the same 56 unique requirement IDs; every human row has all eight declared cells and an explicit machine-backed status.

# 3. PATCH 0003 IMPLEMENTATION SPECIFICATION

## 3.1 Exact Patch Identity

**Patch filename:** `oracle/instrumentation/patches/0003-native-command-input-and-boundary-records.patch`.

Pre-code evidence must prove that the file does not already exist and that no repository authority reserves a conflicting 0003 name. Create the file only after the exact 0001/0002 prefix passes.

## 3.2 Purpose

Patch 0003 must:

- ingest the existing strict command-input v1 format;
- validate the complete command file and canonical run header before fixture load;
- schedule public actions by native tick and public-step order;
- set and restore explicit company context;
- map exactly six registry action families to exact typed native commands;
- post each command once through native `Command<...>::Post`;
- capture the already-produced native test and execute results;
- emit command intent, test result, conditional execute result, and complete post-command boundary requests;
- preserve native returned IDs and exact result tuple data;
- fail closed on any input, dispatch, trace, or lifecycle inconsistency.

## 3.3 Non-Goals

Patch 0003 must not:

- implement command legality, money checks, object allocation, order behavior, or construction logic;
- drive GUI, console, network client, script, or rendering paths;
- call a native command twice;
- implement full 757-field projection;
- add route, controller, or cargo diagnostics;
- change command-input or tape wire format;
- infer returned IDs by scanning pools;
- treat a callback as a replacement for native test/execute hooks;
- run commands from a partially validated file.

## 3.4 Required Existing Files and Symbols

Read and verify completely:

- `oracle/instrumentation/README.md`;
- `oracle/instrumentation/patches/0001-trace-sink-and-codec.patch` and `oracle/instrumentation/patches/0002-build-and-run-identity.patch`;
- existing trace sink, codec, partial-journal, run/build identity, and option plumbing created by 0001/0002;
- `parity/schema/commands-v1.json` and its strict schema;
- `scripts/dev/command_input_v1.py` and `oracle/tests/port003/test_command_input_v1.py`;
- `openttd-upstream/src/command_type.h`;
- `openttd-upstream/src/command_func.h`;
- `openttd-upstream/src/command.cpp`;
- `openttd-upstream/src/network/network_command.cpp` and `network_internal.h` as dispatch precedents only;
- `road_cmd.h`, `station_cmd.h`, `vehicle_cmd.h`, `order_cmd.h` and their implementations;
- the exact fixture command input and manifest.

Approved native entry symbols:

- `Command<Commands::BuildRoadLong>::Post`;
- `Command<Commands::BuildRoadDepot>::Post`;
- `Command<Commands::BuildRoadStop>::Post`;
- `Command<Commands::BuildVehicle>::Post`;
- `Command<Commands::InsertOrder>::Post`;
- `Command<Commands::StartStopVehicle>::Post`.

Approved observation region:

- a preallocated bounded active external-command context installed by the replay driver immediately before the single typed `Post`, containing validated action identity, public step, native tick, company, expected native enum, fixed-capacity result storage, phase counters, side-result presence flags, and first-error state;
- `CommandHelper::InternalPost` after native tile checks, after `InternalPostBefore` returns no error, after `estimate_only == false` and `only_sending == false` are proved, and after native `SetClientIds`, where one normalized `COMMAND_INTENT` is written immediately before `Execute`;
- `CommandHelper::Execute` immediately after `InternalExecuteValidateTestAndPrepExec` has produced the final native test result and immediately after `InternalExecuteProcessResult` has produced the final execute result, where values are copied into the bounded context without record I/O;
- a minimal read-only static query on the existing `RecursiveCommandCounter`, placed under the existing 0001/0002 trace compile guard discovered by E5, that reports whether `_counter == 1`; the query mutates no depth state and exists only to guard the `CmdBuildRoadStop` side-result hook;
- an execute-only `CmdBuildRoadStop` hook inserted immediately after the final `if (st != nullptr) { st->AfterStationTileSetChange(...); }` block and before `return cost;`, copying final nonnull `st->index` into the active context only for the expected top-level external `BuildRoadStop` execute;
- `InternalPostBefore` and `InternalPostResult` presentation branches only as needed to suppress user-interface output for the active oracle path; their command decisions and native result processing remain unchanged;
- a null callback and zero error-message presentation for every oracle `Post` call;
- a narrow trace bridge established by 0001/0002 and extended without changing native result semantics, command signatures, network wire bytes, or normal non-oracle behavior.

The driver must not directly call `CommandTraits<Tcmd>::proc`. The station identity hook must never scan a pool, infer “highest ID,” run during test mode, perform I/O, or expose a pointer. Duplicate or missing expected side results set a bounded context error that the driver treats as fatal after `Post` returns.

## 3.5 Exact Six-Action Mapping

The dispatch table in `03_P0_COMMAND_AND_FIELD_MAPPING_CONTRACT.md` is binding. Before implementation, Codex must complete the current external-registry action IDs, operand bytes, sentinels, location rules, result encodings, and tests.

Pinned native numeric values are:

```text
BuildRoadStop   = 22
BuildRoadLong   = 24
BuildRoadDepot  = 27
BuildVehicle    = 34
InsertOrder     = 46
StartStopVehicle= 121
```

A compile-time or focused runtime test must fail if any value differs.

## 3.6 Command Ingestion Flow

The implementation sequence is exact:

1. Resolve trace option state before fixture load.
2. When trace support is compiled out, no command-input or trace side effect exists.
3. When trace support is compiled in but runtime-disabled, no command file is opened and zero trace payload is serialized.
4. When runtime-enabled, require all mandatory paths and options together: complete command input, canonical header input, and exclusive partial-output destination.
5. Reject partial option sets before fixture load.
6. Open input files read-only with bounded size and regular-file checks.
7. Validate complete command framing, canonical header, identities, checksums, reserved bytes, action checksums, schedules, operand types/ranges, limits, and no trailing bytes.
8. Materialize only the bounded validated command schedule required by the existing codec contract; do not keep unbounded or pointer-bearing state.
9. Verify source/build/fixture/settings/content/command/schema identities before gameplay.
10. Load the frozen fixture in an isolated configuration/data home.
11. Verify initial fixture identity and required initial boundary state.
12. Emit `REPLAY_START`.
13. Request the initial complete authoritative projection; 0004/0005 fulfill the fields in later patch prefixes.
14. At each native tick boundary, dispatch all scheduled actions in increasing public-step order.
15. Resolve every returned-ID reference from a prior validated execute result before posting; reject forward, absent, destroyed, wrong-type, or sentinel-mismatched references before `Post`.
16. Convert canonical external operands to exact reviewed native typed arguments without independently duplicating native `ClientID` normalization.
17. Construct the exact typed `Post` call: tile-leading commands use their native tile overload; `Location` commands use the explicit reviewed location overload; every call uses zero error-message presentation and a null callback.
18. Install a scoped outer `Backup<CompanyID>`, set the exact validated company, and install one empty preallocated bounded active-command context. The context must be inactive and clean before installation.
19. Call the typed native `Post` exactly once.
20. Inside `InternalPost`, perform existing tile bounds and `InternalPostBefore` decisions unchanged. For the active oracle path, suppress only error/cost presentation. Require no precheck error, `estimate_only == false`, and `only_sending == false`; otherwise return a fatal pre-test lifecycle status without inventing an intent, test result, or projection.
21. Apply existing native `SetClientIds` behavior. Immediately afterward, serialize one normalized `COMMAND_INTENT` and then call `Execute`. If intent serialization fails, return before `Execute`; no native test or gameplay action occurs.
22. In `Execute`, require `InternalExecutePrepTest` to succeed. An unexpected failure after intent is a fatal incomplete lifecycle retained only in the partial journal; do not synthesize a failed test.
23. Invoke the native procedure once without `DoCommandFlag::Execute`. After `InternalExecuteValidateTestAndPrepExec` returns, copy the final test result tuple into the bounded context exactly once. Perform no record I/O in the hook.
24. When the final test fails, return with zero execute result and zero returned-ID side result.
25. When the final test succeeds, require the offline non-network execution branch, invoke the native procedure once with `DoCommandFlag::Execute`, process the result through `InternalExecuteProcessResult`, and copy the final processed execute tuple into the bounded context exactly once.
26. During a successful top-level `BuildRoadStop` execute, after the final station-change block and before `return cost;`, copy exactly one final nonnull `st->index` into the bounded context. During `BuildVehicle`, copy the returned `VehicleID` from the native execute tuple. No pool scan, callback inference, or second command is permitted.
27. Skip only `InternalPostResult` user-interface presentation for the active oracle path. Invoke no callback. Return the native `Post` success value unchanged.
28. Immediately after `Post` returns, restore the replay driver's outer company context before serializing result records or projecting state. Verify the live company equals the saved outer value.
29. Validate the bounded context: expected native enum, exactly one intent-written flag, exactly one final test tuple, conditional exactly one final execute tuple, expected returned-ID presence, no duplicate hook, no recursive hook, no overflow, and no first error.
30. Publish the buffered `COMMAND_TEST_RESULT` and conditional `COMMAND_EXEC_RESULT` in grammar order. Result publication occurs outside the native command procedure and after outer company restoration.
31. If a result write fails after native execution, preserve the valid partial prefix, set the first fatal error, exit through the scoped company/context restorers, emit no projection and no later command/tick, expose no final tape, and exit nonzero. Do not roll back gameplay or fabricate a completed lifecycle.
32. On every success or failure exit, clear the active command context through scoped restoration. On the success path, require the context inactive and zeroed before projection.
33. Request one complete post-command projection regardless of native test success. A failed native test therefore projects unchanged authoritative state; a fatal pre-test or trace-lifecycle failure does not project or continue.
34. Continue to the next public step or native tick only after the complete projection succeeds.
35. At EOF, continue deterministic tick advancement until the declared terminal condition; EOF alone is not a successful terminal unless the command contract defines it.
36. On any failure, stop, retain the partial journal and raw evidence, record the first explicit error, and exit nonzero without exposing a final tape.

## 3.7 Test Versus Execute Behavior

Patch 0003 must observe native semantics, not implement two independent calls.

At the pin, native `Post` reaches `CommandHelper::Execute`, which invokes the command procedure for test and conditionally for execute. The instrumentation writes intent immediately before that native flow, then copies already-produced results from narrow hooks into bounded storage. The hooks do not serialize records.

Required assertions:

- the active oracle call uses the typed `Post` overload exactly once, zero error-message presentation, and a null callback;
- `InternalPostBefore` decisions remain native; pause, estimate-only, network-send-only, bounds, or other pre-test rejection is fatal and is not encoded as a failed native test;
- native `SetClientIds` runs before the normalized intent is written;
- intent-write failure prevents `Execute` and therefore prevents native test and gameplay mutation;
- the test call lacks `DoCommandFlag::Execute` and occurs exactly once at top-level depth;
- the final test tuple is copied only after `InternalExecuteValidateTestAndPrepExec` completes;
- a failed native test returns before execute and produces no returned-ID side result;
- the execute call includes `DoCommandFlag::Execute` and occurs exactly once only after a successful test;
- the final execute tuple is copied only after `InternalExecuteProcessResult` completes;
- test and execute costs/results satisfy native consistency processing;
- money and expense effects occur only through native execution;
- `InternalPostResult` display/error/cost animation is suppressed only for the active oracle path and no GUI or rendering function is invoked;
- network-send branches and queued commands are impossible in the offline oracle profile;
- recursive native `Do` calls execute normally but do not populate external phase or station-side-result storage;
- the minimal `RecursiveCommandCounter` query is read-only and reports top-level depth without incrementing, decrementing, or exposing `_counter` outside the guarded instrumentation boundary;
- outer company context is restored before buffered result publication and authoritative projection;
- the active external-command context is inactive and zeroed before dispatch and after result publication;
- a successful road-stop execute captures exactly one final `StationID`; test failure, pre-test failure, test-only execution, recursive execution, wrong command, inactive tracing, and duplicate hook capture none and/or produce the required fatal context error.

## 3.8 Result and Error Capture

For every test and execute result, record exactly the tape-v1 payload:

- payload version;
- success byte;
- native command numeric value;
- signed cost;
- expense type;
- primary error string ID;
- extra error string ID;
- normalized result tuple byte count;
- normalized result tuple bytes.

For `BuildVehicle`, preserve the exact execute return tuple after `CommandCost`, including `VehicleID`, the two native integer results, and `CargoArray` in schema order. For `BuildRoadStop`, the native procedure still returns only `CommandCost`; append only the schema-defined normalized `StationID` captured by the execute-only hook. The remaining `CommandCost`-only commands use zero result-data bytes unless the current command schema explicitly freezes another observational result. Never change an upstream command signature merely to make trace result bytes convenient.

If the current command schema does not already define the normalized road-stop `StationID` execute-result field, width, sentinel, and compatibility behavior even though ADR 0003 requires returned station identities, stop before production code. Produce a format-incompatibility dossier containing the exact missing/contradictory schema bytes, pinned source proof, affected records and consumers, the smallest reviewed versioned migration, validator and test updates, fixture regeneration impact, and backward-compatibility effect. Do not silently append a field, reinterpret reserved bytes, or change a schema/version digest.

Do not serialize C++ tuples, structs, enums, pointers, or padding directly. Use exact field-wise canonical encoding. Result hooks copy into fixed-capacity context storage; canonical record serialization occurs only after `Post` returns and outer company context has been restored.

## 3.9 Boundary Ordering

At patch 0003 prefix, the trace lifecycle must already reject illegal command ordering even though later patches complete projection payloads.

Accepted command:

```text
intent -> successful test -> successful execute -> post-command projection
```

Rejected command:

```text
intent -> failed test -> post-command projection
```

The sequence number is strictly increasing. Public step and native tick are nondecreasing under the current schema. A post-command projection carries the command boundary ordinal defined by tape v1. A pre-test `Post` rejection, intent-write failure, missing final test tuple, network-send branch, context overflow, or result-write failure is not a rejected-command lifecycle; it is a fatal incomplete run retained only as a partial journal and receives no post-command projection.

## 3.10 One-Command and Multi-Command Behavior

One-command input must:

- validate completely;
- execute exactly one scheduled action;
- emit exactly one intent, one test, conditional one execute, and one post-command projection;
- continue or terminate according to the declared horizon.

Multi-command input must:

- validate all actions before fixture load;
- preserve file order and schedule order;
- resolve returned-ID references only through explicit prior execute results: native `BuildVehicle` tuple data and the execute-only `BuildRoadStop` station-identity hook;
- reject forward, invalid, wrong-type, destroyed, or absent references before the affected command is posted;
- restore outer company context, publish buffered results, clear the active context, and complete the post-command projection before posting the next action;
- execute no action when complete-file validation fails;
- never partially accept a trailing malformed action.

## 3.11 EOF and Malformed Input

- Clean EOF is valid only at the exact framed end with a valid trailer/checksum and no trailing byte.
- Truncation at any byte is invalid.
- Unknown action, duplicate or nonmonotonic public step, invalid schedule, invalid enum, noncanonical bool, invalid sentinel, out-of-range tile, overflow, reserved byte, checksum mismatch, or trailing data is invalid.
- Runtime inconsistency after successful prevalidation is an internal contract failure, not a recoverable skip.
- A malformed file produces zero gameplay commands.

## 3.12 Required Tests

Patch 0003 must add or complete tests for:

1. exact six-action registry set;
2. exact native enum numeric values;
3. exact operand-to-native parameter mapping for every action;
4. exact result tuple mapping for every action;
5. all ten golden fixture command instances;
6. accepted and native-rejected commands;
7. one normalized intent, one native test, and one native execute for accepted commands;
8. one normalized intent, one native test, and zero native execute for rejected commands;
9. intent placement after native `ClientID` normalization and before `Execute`;
10. intent-write failure proving zero native test and zero gameplay mutation;
11. pause, estimate-only, send-only, bounds, and invalid-company pre-test failures proving explicit fatal lifecycle handling without fabricated test records;
12. no command execution when any file region is malformed;
13. same-tick public-step ordering;
14. outer company restoration before result publication and projection, including nested and failure paths;
15. zero callback invocation and zero `ShowErrorMessage`, cost-animation, GUI, or rendering invocation for the active oracle path;
16. final test capture after native validation and final execute capture after native result processing;
17. returned-ID propagation, exact station-hook source point, and wrong-reference rejection;
18. recursive/internal native command suppression from external trace phases and station side results;
19. read-only recursive-depth query behavior and no depth-counter perturbation;
20. duplicate, missing, wrong-command, inactive-context, overflow, and wrong-phase side-result failures;
21. result-write failure after execution proving partial retention, no projection, no later command/tick, and no false final tape;
22. trace compile-off and runtime-disabled zero-output behavior;
23. short read, EINTR, checksum, truncation, reserved, trailing, and output-write faults;
24. patch apply/reverse and upstream regression compatibility.

## 3.13 Verification Commands

Use the exact current commands established by E10. Mandatory logical commands are:

```text
command codec/schema unit suite
patch 0001-0003 apply/build/focused tests
six-action golden native replay
native rejection corpus
malformed complete-file corpus
trace compile-off/runtime-disabled test
patch 0003 reverse check
```

The final prefix also runs the repository PORT-003 gate and the top-level gate in a failed/progress mode as appropriate; no missing later-patch evidence is misreported as pass.

## 3.14 Expected Artifacts

- exact 0003 patch path and SHA-256;
- six-action mapping ledger and digest;
- native command path audit;
- codec/schema validation result;
- golden ten-command result inventory;
- native rejection inventory;
- command lifecycle count report, including fatal pre-test and intent-write paths;
- normalized-intent placement and native `ClientID` evidence;
- company restoration-before-publication/projection evidence;
- null-callback and user-interface-presentation isolation evidence;
- returned-ID evidence, including proof that station IDs came from the exact execute-only hook point and vehicle IDs came from the native tuple;
- recursive-command suppression and depth-query non-perturbation evidence;
- malformed-input no-execution evidence;
- post-execute result-write failure evidence proving no projection or continuation;
- any required command-schema incompatibility dossier and reviewed migration decision;
- apply/build/test/reverse logs;
- partial-journal failure artifacts.

## 3.15 Exit Criteria

Patch 0003 is complete only when:

- every command mapping row is exact and source-backed;
- every current command-input test passes;
- all ten golden commands execute through native typed `Post` and match expected results;
- negative commands preserve native rejection with no execute;
- fatal pre-test and trace-write paths cannot masquerade as rejected native tests;
- malformed files execute zero actions;
- command phase ordering validates;
- outer company restoration precedes result publication and projection;
- active oracle dispatch invokes no callback or user-interface/rendering presentation;
- no duplicate command call occurs;
- patch 0003 applies, builds, passes focused tests, and reverses cleanly after 0001/0002;
- the permanent submodule remains clean at the pin;
- all evidence artifacts validate and hash.

# 4. PATCH 0004 IMPLEMENTATION SPECIFICATION

## 4.1 Exact Patch Identity

**Patch filename:** `oracle/instrumentation/patches/0004-global-state-and-map-projection.patch`.

## 4.2 Purpose

Patch 0004 implements the complete read-only projection framework and all authoritative singleton/global/map fields assigned to 0004 by the validated projection plan.

## 4.3 Non-Goals

Patch 0004 must not:

- project pooled entities or embedded object containers assigned to 0005;
- emit optional diagnostic fields;
- replace raw map planes with semantic fields;
- call mutating/lazy getters;
- rebuild caches;
- change clocks, RNG, timers, pause, map, or simulation order;
- claim 757-field completion before 0005.

## 4.4 Field Mapping Authority

The exact exhaustive rows are the subset `P4` in the mandatory 757-row field ledger. Each row must contain the columns defined in `03_P0_COMMAND_AND_FIELD_MAPPING_CONTRACT.md`.

No C++ implementation begins until `P4` is complete and source-verified.

## 4.5 Projection Framework

Patch 0004 must provide or extend one canonical projection builder that:

1. begins a projection with explicit boundary kind and ordinal;
2. emits fields only through generated registry-backed typed methods;
3. enforces strictly increasing field IDs;
4. validates exact type, width, count, capacity, stable-ID width, and classification before bytes are accepted;
5. canonicalizes integers field-wise to little-endian;
6. zeroes all required padding and unused high bits;
7. rejects duplicate, missing, unknown, wrong-type, oversized, or nonauthoritative fields;
8. remains bounded by tape v1 limits;
9. propagates the first write/validation failure;
10. cannot expose a partial field as a complete projection;
11. has no process-global mutable serialization state beyond the existing trace context;
12. supports empty arrays/counts without omission.

The builder writes to the partial journal established by 0001. It does not finalize the tape.

## 4.6 Global and Experiment-Control State

Project every 0004-assigned authoritative row for:

- current game mode;
- pause state that affects advancement;
- validated command company context where registered;
- terminal/fault state where registered;
- simulation tick/frame counter;
- exact singleton cursors and control values that influence continuation.

Do not invent revision counters or semantic pending queues when pinned storage has none. Source-backed absence/proof entries follow their registry classification and are not fabricated runtime state.

## 4.7 Simulation, Calendar, and Economy Clocks

Project exact stored state, not display reconstructions:

- global simulation tick;
- calendar date and fraction;
- economy date and fraction;
- stored calendar year/month/day/remainder values assigned by registry;
- stored economy year/month/day/remainder values assigned by registry;
- timeout state and reached subsystem counters;
- tile-loop cursor;
- exact stored timer-manager state that can influence callback timing.

Semantic phase or callback masks classified diagnostic are excluded from the authoritative projection and belong to 0006.

## 4.8 RNG State

Project both internal words for both required RNG streams:

- gameplay state RNG words;
- interactive RNG words.

The adapter reads state directly through source-backed const access. It must not call a random function, seed function, serialization round trip, debug counter, or accessor that advances state. A before/after memory/value test must prove each projection leaves all RNG words unchanged.

## 4.9 Runtime Economy Globals

Project every 0004-assigned singleton runtime economy field, including current values independently stored from settings where the registry assigns them to 0004:

- loan ceiling and fluctuation state;
- interest and inflation increments/accumulators;
- industry daily counter/increment;
- runtime price tables and multipliers;
- cargo initial/current payment rates;
- any other future-influencing singleton economy values in the projection plan.

Computed tables remain authoritative when registry v1 says so. Content identity and settings are not rebuild evidence.

## 4.10 Settings

Project every global setting assigned to 0004 in exact registry order and type. Company-scoped service settings remain with companies in 0005.

Requirements:

- read native stored setting members directly;
- use exact enum widths and booleans;
- preserve runtime-converted values, not source default text;
- emit all reached settings, even when the fixture uses default values;
- do not invoke settings callbacks or setters;
- do not emit GUI/user-path/client-only values excluded by the registry.

## 4.11 Map Dimensions and Traversal

For the frozen fixture:

- width is exactly 64;
- height is exactly 64;
- size is exactly 4,096;
- canonical traversal is `TileIndex` 0 through 4095 inclusive.

Before projection, assert current loaded map dimensions agree with the supported fixture contract. Unsupported dimensions fail explicitly; values are never truncated.

## 4.12 Raw Map Planes

Project the exact native planes registered by ADR 0005:

```text
type
height
m1
m2
m3
m4
m5
m6
m7
m8
```

For each plane:

- read exact native storage/accessor approved by the field ledger;
- emit exactly 4,096 elements;
- preserve overloaded bits;
- preserve exact width;
- use numeric `TileIndex` order;
- do not derive owner, road, station, depot, industry, slope, or semantic flags as substitutes.

## 4.13 Animated-Tile and Map-Schedule State

Project exact registered animated-tile scheduler state:

- count and native vector order;
- each stable tile identity and any exact registered metadata;
- tile-loop cursor and tick context through their fields.

Do not sort the vector. Native tick order and swap-with-back removal make order continuation-relevant.

## 4.14 Invalid or Inapplicable Values

Every 0004 row follows its ledger rule:

- singleton present values always emit;
- invalid typed IDs use exact registry sentinel;
- empty vectors emit zero count plus required offsets/data fields;
- unsupported scope fails before a record is written;
- no missing value is represented by field omission.

## 4.15 Boundary Emission

The mandatory complete projection boundaries are exactly:

- one initial projection immediately after `REPLAY_START`;
- one post-command projection after every accepted or rejected scheduled command;
- one post-tick projection after every completed native tick.

Named checkpoints are evaluated only after a complete projection and are emitted immediately after the projection that first proves the predicate. A checkpoint does not trigger a duplicate projection. At deterministic completion, the order is final post-tick projection → checkpoint 8 `continuation_end` → `TERMINAL`. No projection follows `TERMINAL` in tape v1.

At the 0004 patch prefix, the projection contains the complete `P4` set and an explicit prefix-status test must verify that missing `P5` fields are expected only because 0005 is not yet applied. A full PORT-003 `PASS` remains impossible until 0005.

## 4.16 Required Tests

1. exact `P4` field set and count;
2. strict increasing IDs;
3. type/width/count/capacity agreement;
4. duplicate/missing/unknown/wrong-type rejection;
5. every 0004 row omission detector;
6. representative value mutation for every 0004 family;
7. both RNG streams unchanged by projection;
8. all stored clock/timer values unchanged by projection;
9. settings reads cause no callback or mutation;
10. map dimensions exactly 64×64;
11. ten planes each exactly 4,096 values;
12. map bytes equal direct independent reads from pinned storage;
13. animated-tile order preserved;
14. pointer/address/locale/padding leakage scan;
15. replay-start/post-command/post-tick boundary order;
16. trace sink failure stops projection and retains partial journal;
17. patch apply/build/test/reverse;
18. upstream tests assigned to this prefix.

## 4.17 Expected Artifacts

- exact 0004 patch path and digest;
- complete `P4` mapping extract and digest;
- source-accessor audit;
- projection builder unit report;
- clock/timer/RNG neutrality report;
- settings projection report;
- 4,096-tile raw-plane report and independent digest;
- animated-tile order report;
- boundary coverage report;
- omission/mutation report;
- apply/build/test/reverse logs.

## 4.18 Exit Criteria

Patch 0004 is complete only when every `P4` row emits exactly once at every applicable boundary, all map/RNG/timer/settings tests pass, no projection read mutates native state, the patch applies/builds/reverses cleanly after 0001–0003, and the current submodule remains untouched.

# 5. PATCH 0005 IMPLEMENTATION SPECIFICATION

## 5.1 Exact Patch Identity

**Patch filename:** `oracle/instrumentation/patches/0005-pool-and-entity-projection.patch`.

## 5.2 Purpose

Patch 0005 implements every authoritative pooled, entity, embedded-container, allocation, cache, and cross-reference field assigned to `P5`, completes the exact 757-field projection, and adds source-reviewed required checkpoint predicates now that complete state is available.

## 5.3 Non-Goals

Patch 0005 must not:

- omit empty/free/allocation state;
- normalize native container order;
- infer references from pointers;
- classify a reached cache as derived without the accepted protocol;
- read mutable LinkGraph worker annotations;
- join or force LinkGraph work;
- add optional diagnostic payloads;
- change gameplay object lifecycle or allocation order.

## 5.4 Generic Pool Projection

For each reached `Pool<T>` assigned by registry:

- project exact capacity/items state;
- project `first_free` and `first_unused`;
- project exact `used_bitmap` vector length and every U64 word;
- preserve trailing words and high padding bits;
- project the source-backed absence of a native free-list vector where registered;
- enumerate occupied typed IDs in numeric order for entity columns;
- preserve exact native object/container order inside each owner;
- validate all references against target type, width, sentinel, and occupancy;
- support empty pools without omitting metadata;
- reject unsupported capacity before writing a record.

Tests must fragment every relevant pool class or a source-equivalent generic pool harness and prove the next allocated stable ID.

## 5.5 Companies

Project all assigned company fields, including:

- pool allocation/occupancy;
- `CompanyID`;
- money, fractional remainder, loan, loan ceiling;
- exact expense categories and history/current ledger state;
- bankruptcy, invalid-company, rate-limit, preview, availability, renewal, and service state;
- road/station and all reached infrastructure arrays;
- exact road-vehicle and group `FreeUnitIDGenerator` vector lengths and words;
- company-scoped service settings;
- history, score, value, and owner-offset data where registered.

Do not merge company-scoped settings into global settings. Do not replace exact generator storage with next-number output alone.

## 5.6 Towns and Spatial Indices

Project all assigned Town fields and exact reached Town K-d tree raw state:

- Town pool allocation and typed IDs;
- every continuation-relevant Town member/counter/statistic/cache in registry;
- raw K-d tree node vector, including dead slots;
- each node element and left/right index;
- exact LIFO free-list vector order;
- raw root, including stale ignored values allowed by pinned behavior;
- imbalance counter.

The adapter must not call name resolution, K-d tree lookup, build, rebuild, insert, remove, or clear.

## 5.7 Industries

Project:

- pool allocation/occupancy and typed IDs;
- type, anchor/footprint, town/owner;
- produced/accepted cargo types, rates, waiting values, histories, remainders, offsets;
- production level, counters, closure/change state, founder/exclusive/subsidy continuation;
- nearby-station/capture state;
- RNG-dependent production inputs;
- `_industry_builder.wanted_inds` and every registered 240-entry scheduler array in exact native order.

Do not call cachecheck or production-rebuild helpers.

## 5.8 Stations, Goods, and Road Stops

Project:

- station and road-stop pool allocation state;
- station ID, owner, anchor, facilities, lifecycle;
- catchment bitmap and exact `BitmapTileArea` dimensions;
- acceptance, rating, waiting, service, trigger, nearby-industry, queue, area, and cache state;
- road-stop ID, tile, status, linked stop order, bay dimensions, entry pointer presence, occupancy, and vehicle queues;
- every `(StationID, CargoType)` `GoodsEntry` presence and field;
- packet-map next-hop keys distinct from `CargoPacket::next_hop`;
- exact packet/container order;
- FlowStat origin, unrestricted totals, cumulative share keys, via StationIDs, and two-level offsets;
- exact owner/cargo/flow order defined by registry.

Do not call resolved-name or catchment-building getters. Orientation remains in raw map planes where native `RoadStop` stores no duplicate member.

## 5.9 Vehicles and EffectVehicles

Project:

- shared Vehicle pool allocation state;
- exact sparse type discriminator and road/effect owner-ID lists;
- vehicle ID, engine, subtype, owner, tile, precise position, direction;
- movement, speed, progress, acceleration, controller counters, flags;
- current/next destination, station/depot state, stopped/running state;
- current order/list/index, timetable, lateness, unbunching, service state;
- cargo type/capacity, packet chains, load/unload action partitions, cached totals;
- age, service, reliability, breakdown, random fields;
- native chain and gameplay tile-hash order;
- exact `RoadVehicle::path` vector and any registered owner offsets;
- reached GroundVehicle caches and `cached_vis_effect` where authoritative;
- EffectVehicle stable IDs, animation state, current sprite, and other registered fields;
- staged CargoPayment references and values.

Display-only last speed remains diagnostic when the registry says so. Viewport hash and sprite cache are excluded. `RoadVehicle::path` is read directly; no pathfinder is invoked.

## 5.10 Orders and OrderLists

There is no global `Order` pool. Project:

- OrderList pool allocation and typed IDs;
- sharing/owner state and exact owner offsets;
- vector count and native order;
- each embedded Order identified by `(OrderListID, ordinal)`;
- raw order type, flags, destination, refit cargo, wait time, travel time, maximum speed, and registered fields;
- cached duration/count state where authoritative;
- vehicle current-order and execution progress fields.

Do not invent an Order ID or sort orders by destination.

## 5.11 CargoPackets and CargoPayment

Project:

- CargoPacket pool allocation and IDs;
- amount, age/transit periods, feeder share, source station/industry/tile, distance/routing/provenance;
- exact owning station/vehicle container and native ordinal;
- `next_hop` separately from station packet-map keys;
- split/merge outcome through actual pool/container identity rather than an invented persistent flag;
- CargoPayment pool allocation, IDs, owner references, staged payment, route profit, and all registered fields.

Cargo type is derived only through its registered owner context where pinned `CargoPacket` has no cargo-type member. Do not add a duplicate packet cargo field.

## 5.12 Depots, Engines, Subsidies

Project complete assigned fields for:

- Depot pool identity, tile, town association/counter, and construction date;
- Engine pool identity, class/type discriminator, lifecycle, availability, reliability, preview/company mask;
- sparse road-engine ID discriminator followed by exact `EngineInfo` and `RoadVehicleInfo` properties;
- Subsidy pool identity, cargo, remaining duration, award state, source, and destination.

A total engine count cannot substitute for the sparse road-engine owner list.

## 5.13 LinkGraph and LinkGraphJob

Project exact immutable and authoritative state:

- LinkGraph pool allocation;
- graph IDs, cargo, timestamps, node/edge counts and nesting;
- every registered BaseNode and BaseEdge field;
- node/edge owner offsets and native indices;
- schedule list order and running-job order;
- LinkGraphJob pool allocation and typed IDs;
- immutable copied graph;
- copied `LinkGraphSettings` members;
- join date and registered job identity/state.

Do not sample mutable worker annotations, paths, demand scratch, edge-flow scratch, FlowStat scratch, atomics, or `std::thread`. Do not wait, join, abort, pause, or force completion. Enforce the explicit fixture/corpus bounds before record writing; never truncate.

## 5.14 Cross-Object References

For every reference:

- encode exact stable typed width;
- preserve exact invalid sentinel;
- verify target type and current occupancy when valid;
- preserve owner/ordinal context for composite identities;
- reject pointer-derived identities;
- handle destroyed/reused slots exactly at each boundary;
- test invalid, stale, wrong-type, forward, destroyed, and reused references.

Projection itself must not repair or normalize an inconsistent native reference. A failed internal consistency assertion records the first error and stops.

## 5.15 Canonical Iteration Order

- Pools/entities: occupied typed ID ascending where registry defines columnar order.
- Orders: OrderListID then zero-based vector ordinal.
- Station goods: StationID then CargoType.
- Packet/container data: owner identity then exact native container ordinal/key order defined by registry.
- Flows: owner, origin, then exact cumulative-share map order and offsets.
- Vehicle path: exact native vector order.
- Vehicle/native chains: exact native chain order.
- LinkGraph: graph ID, then native node/edge indices and registered nested order.
- Schedule/running jobs: exact native list order.
- K-d tree: raw node-vector slot order plus exact free-list vector order.
- No `unordered_*` iteration or pointer ordering is permitted.

## 5.16 Complete 757-Field Proof

Before patch completion, generate and validate:

```text
|R| = 757
P4 ∩ P5 = empty
P4 ∪ P5 = R
```

At every complete runtime boundary:

- observed field count is 757;
- observed ID sequence equals the validated registry authoritative-ID sequence byte-for-byte;
- every field header and payload agrees with registry metadata;
- no diagnostic or nonauthoritative field appears;
- no authoritative field is absent;
- the C17 and independent Python decoders report the same field inventory.

## 5.17 Required Named Checkpoints

Patch 0005 completes source-reviewed first-occurrence predicates for:

1. `route_completion`;
2. `first_production`;
3. `first_station_capture`;
4. `first_loading`;
5. `first_unloading`;
6. `first_accepted_delivery`;
7. `first_payment`;
8. `continuation_end`.

Rules:

- predicates read only the just-completed authoritative projection and source-reviewed immutable context;
- no elapsed-time guess substitutes for state;
- evaluate predicates after each initial, post-command, or post-tick complete projection;
- emit a newly satisfied checkpoint immediately after that proving projection, before the next command, tick, checkpoint-independent diagnostic event, or terminal record;
- emit multiple newly satisfied checkpoints in increasing checkpoint-ID order at the same boundary;
- emit each ID at most once;
- the golden road-freight qualification run must emit IDs 1 through 8 exactly once in increasing first-occurrence order;
- non-golden negative and no-action corpora emit only predicates actually reached; they must not fabricate route/cargo/payment checkpoints;
- checkpoint 8 emits after the final post-tick projection and immediately before `TERMINAL`;
- a checkpoint never causes a second authoritative projection;
- predicates do not alter state or execute additional work;
- diagnostics off/on produce identical checkpoint IDs, sequence positions relative to authoritative records, public steps, and native ticks.

## 5.18 Required Tests

1. exact `P5` field set and mapping;
2. combined 757 union/disjointness proof;
3. runtime 757 ID sequence at every complete boundary;
4. empty and fragmented pool state;
5. exact bitmap words, padding, cursors, and next allocation;
6. invalid, stale, destroyed, wrong-type, and reused references;
7. company generators and company-scoped settings;
8. industry scheduler arrays;
9. station GoodsEntry presence and nested offsets;
10. packet-map key versus packet `next_hop` distinction;
11. vehicle sparse discriminator, effect vehicles, path and chain order;
12. OrderList composite identity and vector order;
13. CargoPacket provenance, containment order, and conservation;
14. Depot/Engine/Subsidy sparse owner rules;
15. LinkGraph schedule/running/job immutable state without synchronization;
16. K-d tree dead slots, free-list order, raw root, and imbalance;
17. every field omission and representative mutation detector;
18. checkpoint first-occurrence predicates and exact sequence;
19. pointer/address/unordered-order leakage scans;
20. projection read-only and RNG/timer neutrality;
21. two-load and 10,000-tick continuation compatibility in 0007 campaign;
22. patch apply/build/test/reverse.

## 5.19 Expected Artifacts

- exact 0005 patch path and digest;
- complete 757-row field ledger and machine proof;
- runtime every-boundary field inventory;
- source-accessor review;
- per-family projection evidence;
- pool fragmentation and allocation evidence;
- reference lifecycle evidence;
- checkpoint predicate audit and milestone trace;
- omission/mutation results;
- apply/build/test/reverse logs.

## 5.20 Exit Criteria

Patch 0005 is complete only when:

- combined 0004/0005 projection contains exactly all 757 authoritative fields once each;
- every field row has an exact source, encoding, lifecycle, order, and test;
- all pool/reference/container/cache tests pass;
- the golden qualification run emits all eight required checkpoints correctly, while every other corpus emits only reached predicates, all independently of diagnostics;
- projection is read-only and non-perturbing in focused tests;
- patch applies/builds/reverses cleanly after 0001–0004;
- no unregistered source or unresolved field remains.

# 6. PATCH 0006 IMPLEMENTATION SPECIFICATION

## 6.1 Exact Patch Identity

**Patch filename:** `oracle/instrumentation/patches/0006-optional-route-controller-cargo-diagnostics.patch`.

## 6.2 Purpose

Patch 0006 adds only the optional diagnostic features declared by the current registry and tape header schema. Diagnostics explain route choice, controller decisions, cargo movement/conservation, and other source-reviewed observations without becoming authoritative state or triggering additional gameplay work.

## 6.3 Diagnostic Classification Rule

A diagnostic item is permitted only when:

- the field/record is explicitly classified diagnostic in the current registry/schema;
- the value is observational and not required for exact continuation;
- collection reads an already-computed value at an existing source boundary;
- collection can be disabled completely at runtime;
- disabling collection removes diagnostic records but changes no authoritative byte, command result, checkpoint, RNG state, tick, save, or terminal outcome.

Any value discovered to influence continuation must be reclassified through registry/ADR review and moved into authoritative projection; it cannot remain diagnostic for convenience.

## 6.4 Exact Data Collected

The exact set comes from the current diagnostic registry. Expected reviewed families include:

- transient YAPF invocation boundary, start tile/direction, target, selected trackdir, path cost, tie result, no-route/node-limit state;
- controller/station/depot entry decisions already computed by native movement code;
- cargo production/capture/loading/unloading/delivery/payment event summaries and conservation totals derived from already-observed events;
- semantic timer phase or callback masks derived from stored clocks/static registration;
- display-only vehicle speed where current registry classifies it diagnostic;
- trace warnings only in explicitly diagnostic evidence tapes.

Codex must not add an item absent from the registry.

## 6.5 Approved Observation Points

Potential source regions are those registered for diagnostics, including:

- `src/pathfinder/yapf/yapf_road.cpp` after native path selection has completed;
- `src/roadveh_cmd.cpp` where native controller decisions are already available;
- `src/station_cmd.cpp` / station loading paths where event results already exist;
- `src/economy.cpp` after production, delivery, route-profit, and payment values are computed;
- existing timer callbacks for derived semantic labels without altering stored timer state.

The verified file plan must name exact current symbols and minimal hook lines. No hook may invoke a function merely to obtain a diagnostic.

## 6.6 Enable/Disable Mechanism

- Compile-time trace support follows the existing 0001 option.
- Runtime diagnostics are disabled by default.
- The canonical header declares the exact enabled diagnostic feature set.
- Prefix flag `OPTIONAL_DIAGNOSTICS` is set only when one or more declared diagnostic features are active.
- Unknown required diagnostic feature fails before fixture load.
- Unknown optional feature follows tape v1 compatibility rules only when framing remains valid.
- Partial or inconsistent diagnostic options fail before gameplay.

## 6.7 Trace Representation

- Use only registry/schema-declared optional record types and payloads.
- Record bytes remain covered by tape integrity.
- Diagnostic records carry sequence/step/tick through the standard record header.
- Diagnostic strings are bounded, canonical UTF-8, escaped in human output, and never authoritative.
- Diagnostic fields never appear in the 757-field authoritative projection.
- Diagnostic presence cannot shift logical authoritative comparison indices incorrectly; comparator tracks physical indices independently.

## 6.8 Isolation From Authoritative Equality

Comparator behavior:

1. validate both tapes completely, including diagnostic bytes and declarations;
2. verify format and identity compatibility;
3. ignore optional diagnostic records only for semantic authoritative comparison;
4. compare authoritative command phases, checkpoints, projections, terminal state, and identities exactly;
5. report diagnostic mismatch only in a diagnostic comparison mode, never as authoritative divergence.

The minimizer must retain valid causal authoritative prefixes and handle physical versus logical indices correctly when diagnostics are skipped.

## 6.9 Replay Milestone Ownership

Required checkpoints are **not** diagnostic:

- codec/record support exists before 0006;
- complete state predicates and emissions are implemented in 0005;
- 0006 may emit diagnostic context adjacent to a checkpoint when enabled;
- 0007 compares checkpoint IDs, ticks, ordinals, and authoritative projections across campaigns.

Diagnostics off must still produce all required checkpoint records.

## 6.10 Non-Perturbation Requirements

For diagnostics off versus on, require equality of:

- command intent/test/execute outcomes;
- returned IDs, costs, expense categories, and errors;
- every authoritative projection field byte;
- checkpoint IDs, ticks, ordinals, and sequence relative to authoritative records;
- both RNG streams;
- clock/timer/pause/schedule state;
- final native save bytes where the campaign defines save equality;
- terminal reason and tick;
- 10,000-tick continuation outcome.

Only declared diagnostic records and header feature labels may differ.

## 6.11 Required Tests

1. diagnostics default-off;
2. exact feature declaration and prefix flag;
3. each feature independently enabled;
4. invalid/unknown feature rejection before fixture load;
5. no diagnostic field in authoritative projection;
6. diagnostic record validation and bounded payloads;
7. no extra pathfinder call;
8. no extra RNG draw;
9. no command/result/checkpoint/tick difference off versus on;
10. no authoritative tape difference after semantic diagnostic filtering;
11. physical/logical comparator index correctness;
12. minimizer correctness with interleaved diagnostics;
13. diagnostic sink failure propagates and retains partial journal;
14. patch apply/build/test/reverse;
15. upstream compatibility.

## 6.12 Expected Artifacts

- exact 0006 patch path and digest;
- diagnostic registry mapping;
- exact hook/source audit;
- feature declaration tests;
- diagnostics off/on authoritative-equality report;
- RNG/timer/pathfinding invocation neutrality report;
- comparator/minimizer optional-record report;
- failure artifacts;
- apply/build/test/reverse logs.

## 6.13 Exit Criteria

Patch 0006 is complete only when every declared diagnostic is default-off, source-backed, bounded, independently enableable, non-authoritative, and proven not to change any authoritative outcome; no extra gameplay computation occurs; patch applies/builds/reverses cleanly after 0001–0005.

# 7. PATCH 0007 IMPLEMENTATION SPECIFICATION

## 7.1 Exact Patch Identity

**Patch filename:** `oracle/instrumentation/patches/0007-test-consistency-and-nonperturbation-hooks.patch`.

## 7.2 Purpose

Patch 0007 adds test-only consistency and non-perturbation facilities and completes the campaigns required to decide whether the seven-patch instrumentation series is correct, deterministic, and observational.

## 7.3 Test-Only Hook Rules

- Hooks compile only in the explicitly declared test/oracle-debug profile.
- Release gameplay paths expose no hidden mutation interface.
- Hooks may inspect and assert; they may not repair state.
- Fault-injection hooks live in dedicated test builds/tools and are absent from normal release binaries.
- Every hook has a stable test ID, source owner, expected earliest failure signature, and requirement mapping.
- A self-check failure stops recording and retains the partial journal.

## 7.4 Internal Consistency Assertions

After each complete authoritative projection in self-checking profiles, assert at minimum:

- exact 757 field IDs/order/types/counts;
- valid pool bitmap/cursor/capacity relationships;
- simulated next allocation from exact native bitmap state;
- valid typed references and owner lifetimes;
- finite OrderList and cargo container chains;
- exact packet containment uniqueness and cargo amount conservation;
- ledger category and one-command money delta consistency;
- command sequence/public step/native tick monotonicity;
- accepted/rejected command lifecycle grammar;
- timer/date progression consistency;
- checkpoint first-occurrence and order;
- no pointer/address-looking values in prohibited encodings;
- no diagnostic field contaminating authority;
- no partial/silently dropped trace record.

Assertions must use already-projected or directly read immutable state. They must not call mutating cache validators.

## 7.5 Same-Input/Same-Build Determinism Campaign

For each required fixed feature configuration:

1. build from identical source/options/toolchain identities;
2. use isolated configuration/data/output roots;
3. load identical fixture and command input;
4. record two initial golden runs and require byte-identical finalized authoritative tapes;
5. record twenty serial runs and require one identical tape digest;
6. record eight isolated parallel runs to separate outputs and require the same digest;
7. verify no run reads another run's config/data/output;
8. verify all command results, checkpoints, projections, terminal values, and tape bytes;
9. retain all digests and a deterministic count summary.

Diagnostic-enabled tapes form a separate feature identity and must be byte-identical among themselves. Diagnostics-off and diagnostics-on are compared semantically for authority, not as raw files.

## 7.6 Record/Replay Comparison Campaign

Run at least:

- no-action continuation;
- complete golden ten-command continuation;
- each single action family where valid;
- representative native rejections;
- route completion through first payment;
- continuation end;
- two independent loads;
- at least 10,000 native ticks after the declared cache/continuation boundary.

Compare:

- complete identities before state;
- command phase records;
- exact checkpoint IDs/ticks/ordinals;
- all 757 field bytes at each comparable boundary;
- both RNG states;
- pool/allocation/reference state;
- packet/container order;
- ledgers and terminal state.

Hash equality is an integrity shortcut; field comparison remains decisive.

## 7.7 Instrumentation-Enabled Versus Disabled Campaign

Use four configurations:

1. plain unpatched OpenTTD;
2. patched build with trace option OFF;
3. patched build with trace option ON but runtime disabled;
4. patched build with trace option ON and runtime enabled.

Required comparisons:

- plain/OFF/runtime-disabled native outcomes and save/continuation evidence are equal;
- runtime-enabled native outcomes equal controls and additionally produce one valid partial/finalized tape;
- trace support OFF excludes adapter sources and OpenSSL trace dependency as governed by build policy;
- runtime-disabled mode opens no trace input/output and serializes zero trace payloads;
- all profiles retain the exact upstream 99-test inventory and pass assigned tests.

## 7.8 Diagnostics-Enabled Versus Disabled Campaign

Run identical source/build/fixture/input with diagnostics off and each approved diagnostic feature combination. Require exact authoritative equality and equal native outcomes through 10,000 ticks. Differences are permitted only in declared diagnostic header labels and diagnostic records.

## 7.9 Trace-Enabled Versus Trace-Disabled Campaign

Where raw tape comparison is impossible because trace-disabled mode emits no tape, compare native outcomes through independent evidence:

- exact command results and returned IDs;
- milestone ticks;
- final save bytes or source-reviewed canonical save projection where exact save bytes are the contract;
- final full authoritative projection from a non-perturbing comparison mechanism approved by the current runners;
- RNG/timer/pause/schedule state;
- terminal tick/reason.

The comparison mechanism must not itself introduce the instrumentation under test into the plain control in a way that makes the test circular.

## 7.10 Randomized Command Prefix Campaign

`local-release` generates 10,000 bounded typed prefixes from a recorded 64-bit seed, with at least 30% deliberately invalid. Every prefix runs twice.

Coverage includes:

- edge tiles;
- duplicate construction;
- legal and illegal ownership;
- order and start/stop variations;
- exact money boundaries;
- safe route-disconnection attempts;
- valid and invalid references;
- operand limits and sentinels.

For every prefix:

- complete input validation is deterministic;
- native acceptance/rejection is structurally valid;
- any produced journal/tape validates;
- two repeats agree exactly for the same feature identity.

A failure is rerun, minimized to the smallest valid causal prefix, retained, and entered in the ledger.

## 7.11 Exact Compared Outputs

### Byte-for-byte comparisons

Use byte equality for:

- finalized tapes with identical complete identities and diagnostic feature set;
- generated registry/metadata regeneration where required;
- fixture/save/map artifacts where their contract requires byte identity;
- repeated evidence manifests after normalization where specified.

### Semantic comparisons

Use field/record semantic comparison for:

- diagnostics off versus on;
- tapes whose nonauthoritative backend labels differ;
- first-divergence reporting;
- valid-prefix minimization;
- plain/off/on outcome comparison where one profile emits no tape.

Identity mismatch stops before state comparison and uses the contract exit status. Diagnostic filtering occurs only after structural and integrity validation.

## 7.12 First-Divergence Reporting

At the earliest mismatch, retain:

- both tape and experiment identities;
- backend/feature labels;
- first differing physical record indices and logical authoritative indices;
- sequence, public step, native tick, boundary kind/ordinal;
- record type;
- command family/operands/results or field ID/path/type/width/element;
- exact decimal and fixed-byte hex values;
- last command phases;
- prior checkpoint;
- source-register ID and cache policy;
- minimized valid prefix path and digest;
- exact argv arrays;
- raw logs and environment/profile identity.

Later differences never overwrite the root cause.

## 7.13 Failure Artifact Retention

For failure, timeout, crash, sanitizer finding, invariant failure, or I/O fault, retain:

- partial journal;
- validated largest complete prefix where available;
- stdout/stderr;
- exit/signal/timeout status;
- source/build/input/schema/feature identities;
- first-error record;
- minimized reproducer when possible;
- artifact sizes and SHA-256;
- ledger entry or explicit mapping to an existing entry.

Never delete a failure artifact merely because a later retry passes.

## 7.14 Timeout and Crash Handling

- Every process has a stage-specific timeout and bounded child count.
- Runner captures and terminates only the process group it created.
- Timeout is a failure, not normal horizon completion.
- Crash/core/sanitizer/OOM is a failure.
- Deterministic horizon uses native tick/checkpoint conditions; wall-clock timeout is only a safety net.
- Output publication remains transactional; a crash cannot expose a final tape.

## 7.15 Required Quality Campaigns

Patch-series closure requires the applicable current repository commands for:

- GCC debug/release;
- Clang debug/release;
- ASan/UBSan and leaks;
- coverage thresholds and required risk branches;
- bounded libFuzzer targets;
- static analysis, compiler warnings, Clang-Tidy, analyzer, ShellCheck, schemas, semantic lint, secret/license/policy scans;
- reviewed mutation plan with every mandatory mutant killed semantically;
- fault injection for identity, tape, command, projection, pool, reference, cargo, ledger, timer, RNG, route, I/O, finalization, report, and minimizer failures;
- traceability lint;
- evidence validation.

The two existing diagnosed static defects remain release blockers until properly closed.

## 7.16 Expected Artifacts

- exact 0007 patch path and digest;
- invariant/test-hook inventory;
- fixed-corpus determinism summary;
- two-golden/twenty-serial/eight-parallel digest report;
- plain/OFF/runtime-disabled/enabled non-perturbation report;
- diagnostics off/on report;
- two-load/10,000-tick continuation report;
- 10,000-prefix differential summary and retained failures;
- first-divergence/minimization evidence;
- sanitizer/static/coverage/fuzz/mutation/fault summaries;
- apply/build/test/reverse logs;
- updated traceability and ledger mappings.

## 7.17 Exit Criteria

Patch 0007 and the seven-patch series are complete only when:

- all consistency hooks detect injected faults and do not mutate normal runs;
- required deterministic recording counts share the correct digest;
- plain/off/disabled/enabled native outcomes are equal;
- diagnostics off/on authority is equal;
- two-load and 10,000-tick continuation is exact;
- randomized prefixes repeat deterministically and failures minimize validly;
- first-divergence reports identify the earliest exact mismatch;
- all assigned quality gates pass;
- all seven patches apply/build/test and reverse cleanly;
- evidence validates and the submodule remains clean.

# 8. FILE-BY-FILE CHANGE PLAN

## 8.1 Fixed Patch Artifacts and Series Prefix

The five new patch paths are fixed:

| Patch | Exact outer-repository path | Operation | Series rule |
|---|---|---|---|
| 0003 | `oracle/instrumentation/patches/0003-native-command-input-and-boundary-records.patch` | Add | Append only after the 0003 prefix applies, builds, tests, and reverses cleanly |
| 0004 | `oracle/instrumentation/patches/0004-global-state-and-map-projection.patch` | Add | Append only after the 0004 prefix gate passes |
| 0005 | `oracle/instrumentation/patches/0005-pool-and-entity-projection.patch` | Add | Append only after the 0005 prefix gate passes |
| 0006 | `oracle/instrumentation/patches/0006-optional-route-controller-cargo-diagnostics.patch` | Add | Append only after the 0006 prefix gate passes |
| 0007 | `oracle/instrumentation/patches/0007-test-consistency-and-nonperturbation-hooks.patch` | Add | Append only after the 0007 prefix gate passes |

Before 0003 exists, the effective `series` is exactly:

```text
0001-trace-sink-and-codec.patch
0002-build-and-run-identity.patch
```

After 0007 passes, the effective `series` is exactly:

```text
0001-trace-sink-and-codec.patch
0002-build-and-run-identity.patch
0003-native-command-input-and-boundary-records.patch
0004-global-state-and-map-projection.patch
0005-pool-and-entity-projection.patch
0006-optional-route-controller-cargo-diagnostics.patch
0007-test-consistency-and-nonperturbation-hooks.patch
```

No later entry may be appended early. No patch may depend on a later entry. A different existing filename or reserved future entry is a repository contradiction, not permission to rename the assigned files.

## 8.2 Exact Touched-File Manifest Requirement

The uploaded set does not contain the current 0001/0002 patch bytes or current trace-source layout. Codex must therefore derive the exact touched-source list from the checkout before editing. The canonical repository document is the existing file-plan document when one exists; otherwise create `docs/implementation/P0_PATCH_0003_0007_FILE_PLAN.md`.

That document must contain one row for every added or modified path with these columns:

| Column | Required content |
|---|---|
| Patch | Exactly one of 0003, 0004, 0005, 0006, 0007, or `repository-side` |
| Path | Exact repository-relative path; no directory-only row |
| Operation | Add, modify, or append-only |
| Existing owner | Patch 0001/0002 symbol, current repository subsystem, or exact governing document |
| Exact responsibility | One bounded behavior; no mixed unrelated work |
| Symbols or generated bindings | Every affected production symbol or generator target |
| Authority | Registry row, source-register ID, ADR, requirement ID, and pinned source anchor |
| Tests | Stable test IDs and exact `cmd[...]` bindings |
| Patch-prefix gate | Exact apply/build/test/reverse stage that owns the row |
| Prohibited collateral change | State that must remain byte-identical or behaviorally unchanged |

The manifest must be complete before production C++ work. Every final patch hunk and repository-side diff must map to exactly one row. A diff in an unlisted file is a failure.

## 8.3 OpenTTD Patch-Content Responsibilities

The following paths are exact where pinned-source evidence already establishes the necessary hook. Rows described as ledger-driven may be touched only when the completed command or field ledger proves that exact file and symbol are required.

| Patch | Exact file or bounded file set | Operation | Exact responsibility | Required symbols or evidence | Validation |
|---|---|---|---|---|---|
| 0003 | current trace context, sink, codec, and replay-driver files introduced by 0001/0002, as enumerated by the architecture audit | Modify | strict input/schedule, preallocated scoped command context, company restoration before result publication, buffered-result publication, boundary requests, and first-error retention | exact 0001/0002 symbols; no parallel trace namespace | codec, restoration ordering, lifecycle, write-fault, apply/reverse |
| 0003 | `openttd-upstream/src/command_func.h` | Minimal patch hunk | emit normalized intent after native prechecks/`SetClientIds`; copy final native test/execute results into bounded context; expose read-only top-level-depth query under existing trace guard; suppress only active-oracle presentation | `CommandHelper::InternalPost`, `CommandHelper::Execute`, `ExtractCommandCost`, `RecursiveCommandCounter`, `InternalPostBefore`, `InternalPostResult` | intent placement, one-test/one-execute, no UI/callback, nested suppression |
| 0003 | `openttd-upstream/src/station_cmd.cpp` | Minimal patch hunk | immediately after final `AfterStationTileSetChange` block and before `return cost`, copy final `st->index` for the expected active top-level `BuildRoadStop` execute without changing signature | `CmdBuildRoadStop`, final `Station *st`, `DoCommandFlag::Execute`, read-only depth query | exact-hook provenance, execute-only and duplicate/missing negatives |
| 0003 | the exact current replay integration point; modify `openttd-upstream/src/openttd.cpp` only when the 0001/0002 audit proves that file owns replay scheduling | Minimal patch hunk | whole-file prevalidation, fixture-load boundary, action scheduling, post-command and post-tick requests | exact game-loop/load symbols at the pin | ten-command golden replay and malformed no-execution |
| 0003 | command declaration headers already identified in the six-action ledger | Include/read or minimal patch only when compile wiring requires it | expose typed command declarations to the established trace bridge | six pinned `Cmd*` declarations and `DEF_CMD_TRAIT` rows | compile assertions and mapping tests |
| 0004 | current projection-builder files in the established trace namespace | Add or modify | canonical projection framing, generated registry lookup, exact P4 emitters | every P4 ledger row and generated binding | P4 omission/type/count/order tests |
| 0004 | exact singleton/global/time/RNG/settings/map owner files named by P4 | Read-only include or narrowly justified const-access hunk | expose exact stored state without mutation | source-register IDs and literal storage symbols | accessor read-only and neutrality tests |
| 0004 | exact boundary integration point from 0003 | Minimal modify | invoke one complete replay-start and one complete post-tick projection at the contract point | projection-completion symbol | boundary-order and 4,096-tile tests |
| 0005 | current projection-builder files | Modify | exact P5 emitters, stable-reference checks, pool/container order, 757 union completion, checkpoint predicates | every P5 ledger row | 757 runtime set proof, omission, reference, checkpoint tests |
| 0005 | exact pool/entity/cache owner files named by P5 | Read-only include or narrowly justified const-access hunk | expose exact stored bytes, counts, offsets, allocation metadata, and immutable schedule state | source-register IDs and literal owner symbols | per-family, reuse, fragmented-pool, continuation tests |
| 0006 | current diagnostic feature declaration and record-emission files | Add or modify | declare default-off feature bits and separately framed optional payloads | diagnostic registry rows only | compile-off/default-off and structural validation |
| 0006 | exact YAPF/controller/cargo/economy hook points named by the diagnostic ledger | Minimal patch hunk | copy already-computed diagnostic values without invoking new work | exact source-register symbols | per-feature no-extra-work and off/on equality |
| 0007 | current trace self-check/test-hook files and test-only build wiring | Add or modify | read-only invariant checks, deterministic injected faults, test-only counters | established trace option namespace | normal-vs-test profile equality and fault detection |
| 0007 | exact projection-completion integration point | Minimal modify | invoke test-only checks only after a complete projection | completion callback from 0004/0005 | invariant ordering and non-perturbation |

The path prefix `openttd-upstream/` above identifies the pinned source path whose changes must be represented inside the outer patch file. Codex must not leave those edits in the permanent submodule worktree.

## 8.4 Repository-Side Files

| Area | Exact path or canonical-path rule | Operation | Responsibility | Validation |
|---|---|---|---|---|
| Series | `oracle/instrumentation/patches/series` | Append one line per passing patch prefix | exact seven-entry order | series parser, apply/reverse, digest |
| Patch documentation | `oracle/instrumentation/README.md` | Modify | exact options, invocation, patch responsibilities, failure and evidence behavior | documentation command audit |
| Command mapping | existing canonical command mapping; otherwise `docs/implementation/P0_COMMAND_DISPATCH_MAPPING.md` | Add or modify | exact six-row external/native mapping | schema/semantic/source audit |
| Field mapping | existing canonical field mapping; otherwise `docs/implementation/P0_FIELD_PROJECTION_MAPPING.md` | Add or modify | exactly 757 complete rows and P4/P5 proof | row-set and digest validator |
| Field mapping machine form | existing canonical machine mapping; otherwise `evidence/p0/P0_FIELD_PROJECTION_MAPPING.json` | Add or modify | machine-identical representation of all 757 rows | strict schema and Markdown/JSON equality |
| Source register | `docs/sources/P0_SOURCE_REGISTER.md` | Append only | register every newly reached exact-pin source before encoding behavior | source-register semantic validator |
| Human traceability | `docs/testing/P0_REQUIREMENTS_TRACEABILITY.md` | Modify honestly | exact implementation/test/evidence mappings and eight-cell row shape | 56-ID shape audit and traceability linter |
| Machine traceability | `evidence/p0/P0_REQUIREMENTS_TRACEABILITY.json` | Modify only for honest reviewed mappings/status transitions | machine authority | schema and semantic linter |
| Test strategy | `docs/testing/P0_TEST_STRATEGY.md` | Modify only when current implementation proves a missing test obligation | preserve frozen counts and profile distinctions | policy/traceability lint |
| Field completeness review | `docs/testing/PORT005_FIELD_COMPLETENESS.md` | Modify only for a genuine newly reached source or corrected owner/continuation fact | preserve static-review audit trail | field semantic validator |
| Command codec tests | `oracle/tests/port003/test_command_input_v1.py` plus exact current native test paths from E10 | Modify/add in current structure | hostile input, mappings, lifecycle, returned IDs | `cmd[TEST-COMMAND-CONTRACT]` |
| PORT-003/005 tests | exact current C++/integration test files from E10 | Modify/add in current structure | projection, pool, diagnostic, invariant, continuation tests | owning stable test IDs |
| Runners | exact current runner paths from E10 | Modify | disposable worktrees, prefix gates, replay/campaign orchestration, bounded evidence | runner self-tests and fault tests |
| Defect/divergence ledgers | current machine ledger and human view | Append or status-update only with required evidence | record new findings and valid closure; preserve history | evidence and traceability validators |
| External evidence | caller-controlled artifact root outside repository | Generate | raw logs, partial/final tapes, reports, corpora, digests, first failures | evidence contract and bundle validation |

## 8.5 Forbidden File Changes

- direct persistent changes inside `openttd-upstream`;
- unrelated PORT-004 C17 fixes unless separately assigned, even though current defects block full P0;
- scalar, CUDA, RL, gameplay-backend, viewer, GUI-automation, or generalized-support files;
- user configuration, credentials, shell history, SSH material, or GitHub authentication;
- fixture facts, schemas, IDs, or expected results changed merely to make implementation pass;
- generated registries rewritten from current-source guesses;
- current upstream OpenTTD repository, issues, pull requests, or contribution content;
- any file absent from the completed touched-file manifest.

# 9. EXECUTION ORDER FOR CODEX

Every step has one verification and one stop condition. Preserve the first failure and all independently completed earlier evidence.

1. **Create the external evidence root.** Execute E0. Verify absolute, new, symlink-free, nonancestor placement and record device identity. Stop on any unsafe path.
2. **Snapshot repository state.** Execute E1. Retain HEAD, exact branch, upstream, remotes, full dirty inventory, gitlink, and submodule status. Stop on moved or dirty submodule.
3. **Require the assigned branch.** Execute E2 and require `fix/p0-build-portability`. Do not switch or repair branches. Stop on any other branch.
4. **Preserve user work.** Record diffs and untracked paths without stashing, resetting, cleaning, amending, or overwriting. Stop when an unexplained user edit overlaps a proposed task path.
5. **Verify authority files, ADRs, and hashes.** Execute E3 and read every required file completely. Produce `fixture-status-reconciliation.md`, preserve frozen PORT002A artifacts, and treat PORT002B/overall PORT002 as open. Stop on a missing file, registered-hash mismatch, unreadable machine authority, or any attempt to reconcile the ADR by changing fixture facts.
6. **Validate the pre-code series prefix.** Require exactly 0001 and 0002 and prove that all five assigned future patch paths are absent and unreserved. Stop on any additional entry, missing prefix file, or naming conflict.
7. **Audit patches 0001 and 0002.** Read every hunk and produce the exact trace architecture map: namespaces, contexts, sink, codec, options, CMake targets, tests, runners, and integration points. Stop on an unresolved owner.
8. **Apply the two-patch prefix.** Use the committed disposable-worktree runner at the exact pin. Stop on fuzz/offset application, permanent-submodule mutation, or residual diff.
9. **Build and test the two-patch prefix.** Run exact E10 commands for the sink, codec, build identity, run identity, assigned upstream tests, and disabled mode. Stop on any failure or missing artifact.
10. **Reverse the two-patch prefix.** Require the disposable source to return byte-clean to the exact pin and the permanent submodule to remain unchanged.
11. **Validate machine schemas and registries.** Run strict command, field, projection-plan, traceability, and ledger validators. Require 816 fields and 757 authoritative fields. Stop on drift or schema/semantic failure.
12. **Reconcile traceability shape.** Require exact 56-ID machine/human set equality. When the four uploaded safety rows remain malformed, restore only the machine-backed Status cells, preserve notes, record the diff, and rerun the linter. Stop on any remaining mismatch.
13. **Build the exact six-action ledger.** Join every external action and operand/result byte to the pinned enum, typed procedure, trait, location overload, company context, fixture instances, negative cases, and tests. Stop on any blank or inferred cell.
14. **Audit native command hooks.** Prove one typed `Post`, one top-level test, conditional one top-level execute, recursive suppression, native tuple capture, and the execute-only `BuildRoadStop` station-ID hook. Stop when observation would require a second command call or signature change.
15. **Build the exact 757-row field ledger.** Join every authoritative ID to patch, source, canonical encoding, lifecycle, applicability, order, reference rule, and tests. Stop on any incomplete row.
16. **Prove P4/P5 completeness.** Require `|R|=757`, empty intersection, exact union, and explicit empty difference sets. Stop on duplicate, missing, extra, diagnostic, or unassigned IDs.
17. **Close source registration.** Verify every literal source symbol at the pin and append reached-source entries before coding. Stop on unregistered behavior.
18. **Bind exact test commands.** Complete `verified-test-command-inventory.json` with one exact argv array per referenced test ID, validate it, and bind every `cmd[...]` in Section 10. Stop on an invented wrapper, shell-form command, missing argument, or ambiguous owner.
19. **Finalize the touched-file manifest.** Enumerate every exact path and symbol for 0003–0007. Stop on any proposed path without one authority row and one test owner.
20. **Create the 0003 implementation worktree.** Start from the exact pin, apply 0001/0002, verify clean prefix state, then edit only 0003-owned source paths.
21. **Integrate strict command input.** Reuse the existing codec and validate the complete file before fixture load. Run codec and hostile-input tests. Stop on partial acceptance.
22. **Add scoped replay scheduling and preallocated command context.** Establish exact company context, null-callback typed posting, bounded phase storage, and outer-company restoration immediately after `Post`; verify same-tick ordering and restoration-before-publication/projection before adding command families.
23. **Instrument the native posting path once.** Emit normalized intent only after native prechecks and `SetClientIds`, abort before test on intent-write failure, copy final test/execute tuples at the approved hooks, add the read-only top-level-depth query, and suppress only active-oracle presentation. Stop on any UI call, callback, network branch, phase-count, or depth mismatch.
24. **Implement one typed family.** Add the exact ledger mapping, one `Post`, buffered result publication after company restoration, context clearing, projection request, and focused tests. Stop on call-count, ordering, or result mismatch.
25. **Add the remaining five families one at a time.** Rerun the complete focused command suite after each family. Preserve exact native location and single native `ClientID` normalization.
26. **Add returned-ID provenance.** Copy `VehicleID` from the native execute tuple and `StationID` only at the exact guarded source point after the final station-change block and before `return cost;`. Run all test, pre-test, recursive, wrong-command, duplicate, missing, overflow, and inactive-context negatives. Stop for a reviewed format-incompatibility decision when the schema lacks the required station-result field.
27. **Run the ten-command fixture replay and rejection/fatal-lifecycle corpora.** Verify exact results, IDs, costs, categories, ordering, accepted/rejected grammar, explicit pre-test failures, result-write failure behavior, and zero execution for malformed complete files.
28. **Generate 0003.** Use the current repository's verified patch-generation procedure, write the exact assigned patch path, append only the 0003 series entry, and retain patch bytes/digest.
29. **Gate the 0003 prefix.** From a new clean worktree, apply 0001–0003, build, run focused/integration tests, reverse 0003 then the prefix, and require exact clean pin. Stop on any failure.
30. **Create the 0004 implementation worktree.** Apply the passing 0001–0003 prefix and edit only P4-owned paths.
31. **Implement the canonical projection builder.** Enforce registry version/digest, increasing IDs, exact type/count/length, checked arithmetic, and first-error propagation before field emitters.
32. **Implement P4 families in field-ID order.** Add globals, clocks, calendar/economy state, timers, both RNG streams, process-wide settings, and runtime economy globals one source-reviewed family at a time.
33. **Implement the full map projection.** Emit dimensions, ten raw planes with exactly 4,096 values each in `TileIndex` order, and registered animated-tile/order state without semantic replacement.
34. **Run P4 omission, mutation, source-anchor, and neutrality suites.** Stop on any field that can be omitted or changed undetected or any projection-side mutation.
35. **Generate and gate 0004.** Write the exact assigned patch, append only its series entry, then apply/build/test/reverse the 0001–0004 prefix from a fresh pin.
36. **Create the 0005 implementation worktree.** Apply the passing 0001–0004 prefix and edit only P5-owned paths.
37. **Implement generic pool/allocation projection first.** Preserve capacities, cursors, exact bitmap vectors/words/padding, occupancy, free/empty state, and predicted next allocation.
38. **Implement each entity family in field-ID order.** Complete companies, towns, industries, stations, road stops, goods, vehicles/effects, orders, cargo packets, depots, engines, payments, subsidies, LinkGraph/jobs/schedules, K-d trees, and every other P5 owner.
39. **Implement stable references and nested offsets.** Validate type, width, sentinel, occupancy, lifecycle, reuse, composite identity, native container order, and exact offset totals.
40. **Complete the runtime 757 projection.** Compare the emitted ID sequence to the generated authoritative sequence at replay start, every post-command boundary, and every post-tick boundary.
41. **Implement checkpoint predicates.** Evaluate only the completed authoritative projection, emit IDs 1–8 on first occurrence immediately after the proving projection, never duplicate a projection, and place checkpoint 8 immediately before terminal.
42. **Run P5 omission, mutation, fragmented-pool, reference, nested-container, checkpoint, and read-only suites.** Stop on any undetected field or invalid-reference behavior.
43. **Generate and gate 0005.** Write the exact assigned patch, append only its series entry, then apply/build/test/reverse the 0001–0005 prefix from a fresh pin.
44. **Create the 0006 implementation worktree.** Apply the passing prefix and add the declaration/default-off path before any payload hook.
45. **Add one diagnostic feature at a time.** Copy only already-computed registry-declared data. After each feature, compare diagnostics off/on and verify identical authoritative state, commands, RNG, timers, outcomes, and work counters.
46. **Generate and gate 0006.** Write the exact assigned patch, append only its series entry, verify optional-record structural behavior, and apply/build/test/reverse the 0001–0006 prefix.
47. **Create the 0007 implementation worktree.** Apply the passing prefix and add only test/debug-profile facilities and repository-side campaign orchestration.
48. **Add read-only invariants one family at a time.** Pair every invariant with one deterministic injected-fault test and verify normal-profile non-perturbation.
49. **Implement bounded campaign runners.** Reuse current runner/evidence conventions; record exact argv arrays, identities, seeds, timeouts, outputs, and first failures.
50. **Run fixed determinism.** Produce two golden, twenty serial, and eight isolated parallel recordings and require one authoritative digest for equal feature configurations.
51. **Run non-perturbation.** Compare plain, patched-OFF, patched-ON/runtime-disabled, patched-ON/enabled, diagnostics off/on, and no-action/golden continuations without forced synchronization.
52. **Run two-load/10,000-tick continuation and cache experiments.** Preserve native LinkGraph scheduling and pause behavior. Stop on the first exact difference.
53. **Run the 10,000-prefix differential campaign twice.** Require at least 30% invalid, deterministic classifications, bounded reruns, valid-prefix minimization, and failure retention.
54. **Run the native quality matrix.** Execute all seven profiles, sanitizers, static analysis, coverage, fuzz, reviewed mutation, differential, fault injection, CI-policy, traceability, and evidence checks.
55. **Generate and gate 0007.** Write the exact assigned patch, append the final series entry, and apply/build/test/reverse the full seven-patch series from a fresh pin.
56. **Reapply the full series and rerun the patch-series gate.** Require reproducible patch bytes, identities, tests, and campaign results; retain both run manifests.
57. **Update mappings honestly.** Add implementation, test, and evidence links. Do not transition a requirement to PASS until its production files, all linked tests/evidence, mapped defects, and owning gate pass.
58. **Validate and retain evidence.** Verify regular-file type, size limit, SHA-256, schema, identity linkage, retrieval policy, and first-failure records. A retention or report failure fails the task.
59. **Report two statuses separately.** Report `PATCH_SERIES_PASS` only when 0003–0007 and integration dependencies pass. Report full `P0 PASS` only after every PORT, defect, bundle, clean-tree, remote-tip, and twice-run 34-stage condition closes.
60. **Do not commit or push.** Preserve the reviewed outer diff and permanent submodule. Commit, push, merge, reset, clean, stash, or history rewrite requires a separate explicit assignment.
# 10. VERIFICATION MATRIX

## 10.1 Exact Command-Binding Rule

Section 10 covers all 56 requirement IDs present in the uploaded human traceability view, including the four safety rows whose explicit Status cells are malformed. The machine JSON remains status authority.

`cmd[TEST-ID]` is a strict reference to the one exact `argv` array stored under that stable test ID in `verified-test-command-inventory.json`, produced and validated by E10. The reference includes its verified working directory, allowlisted environment, timeout, expected exit code, outputs, and pass predicate. A `cmd[...]` reference is not permission to invent a wrapper or shorten an invocation. Section 10 is executable only after every reference resolves to exactly one current-checkout argv array.

The full release forms for the traceability and top-level gates are printed in their rows. All other shell paths and arguments must remain those read from the current checkout.

## 10.2 Requirement Matrix

| Requirement | Patch or integration owner | Implementation symbol or file | Test ID | Exact test-command binding | Evidence artifact | Exact pass criterion |
|---|---|---|---|---|---|---|
| `SAFE-REPOSITORY-001` | Precondition for every patch; final P0 closure | `oracle/runner/preflight.sh` | `TEST-SAFE-POLICY` | `cmd[TEST-SAFE-POLICY]` | `evidence/p0/gate0/push-proof.md` plus task-phase repository-state audit | Task-phase audit preserves all user changes; final P0 evidence proves a clean outer tree, clean pinned submodule, and final local commit equal to the configured remote tip. |
| `SAFE-SOURCE-PIN-001` | Precondition for every patch; final P0 closure | `oracle/runner/preflight.sh` | `TEST-SAFE-POLICY` | `cmd[TEST-SAFE-POLICY]` | `evidence/p0/gate0/preflight.md` plus per-stage pre/post pin records | Every apply, build, replay, and reverse stage records the full pin; any moved or dirty submodule fails before work continues. |
| `SAFE-CREDENTIALS-001` | Precondition for every patch; final P0 closure | preflight and static runners | `TEST-SAFE-POLICY` | `cmd[TEST-SAFE-POLICY]` | Gate-0 preflight, synthetic-canary result, and final redacted scan reports | Synthetic canaries are detected and redacted; no credential value, token, cookie, SSH material, signed URL, or authorization header appears in tracked files or retained logs. |
| `SAFE-PUBLICATION-001` | Precondition for every patch; final P0 closure | ADR 0001 | `TEST-SAFE-POLICY` | `cmd[TEST-SAFE-POLICY]` | `evidence/p0/gate0/preflight.md` and publication/license scan | GPL, visibility, asset, and no-upstream-submission policy checks pass; no unreviewed content or upstream contribution action occurs. |
| `SAFE-SCOPE-001` | Precondition for every patch; final P0 closure | `docs/P0_SCOPE.md` | `TEST-SAFE-POLICY` | `cmd[TEST-SAFE-POLICY]` | `evidence/p0/gate0/push-proof.md` and owned-file scope scan | Owned-file and policy scans show no PORT-006+, scalar, CUDA, RL, GUI automation, viewer, or generalized-backend implementation and no P0 overclaim. |
| `BUILD-MANIFESTS-001` | PORT-001 prerequisite; consumed by 0007 release campaign | manifest schemas and validator | `TEST-BUILD-CONTRACT` | `cmd[TEST-BUILD-CONTRACT]` | PORT-001 release bundle | All strict manifests validate, identify exact inputs and outputs, and are retained with verified SHA-256 values. |
| `BUILD-PROFILE-001` | PORT-001 prerequisite; consumed by 0007 release campaign | configure runner and host verifier | `TEST-BUILD-CONTRACT` | `cmd[TEST-BUILD-CONTRACT]` | toolchain probes | Host, compiler, linker, dependencies, options, content, interpreter, and environment match the frozen profile exactly; no silent fallback occurs. |
| `BUILD-REPRODUCIBILITY-001` | PORT-001 prerequisite; consumed by 0007 release campaign | `port001_gate.sh`, comparison tool | `TEST-BUILD-CONTRACT` | `cmd[TEST-BUILD-CONTRACT]` | PORT-001 release bundle | Two independent clean builds produce the required normalized equality and identical declared inventories with no source change between runs. |
| `BUILD-UPSTREAM-TESTS-001` | PORT-001 prerequisite; consumed by 0007 release campaign | `test_reference.sh` | `TEST-BUILD-CONTRACT` | `cmd[TEST-BUILD-CONTRACT]` | PORT-001 release bundle | CTest discovers exactly 99 mandatory upstream tests; all 99 pass with no skip, timeout, inventory drift, or missing JUnit/raw log. |
| `BUILD-HEADLESS-SMOKE-001` | PORT-001 prerequisite; consumed by 0007 release campaign | `smoke_reference.sh` | `TEST-BUILD-CONTRACT` | `cmd[TEST-BUILD-CONTRACT]` | PORT-001 release bundle | The approved executable runs exactly 128 offline headless ticks in an isolated home and exits successfully with complete identity-linked logs. |
| `FIX-IDENTITY-001` | PORT-002 prerequisite | fixture manifest | `TEST-FIXTURE-CONTRACT` | `cmd[TEST-FIXTURE-CONTRACT]` | corrected `ffb34c` reproduction | Save, map, normalized settings, behavior settings, content, builder, and command-input identities equal the frozen manifest. |
| `FIX-STRUCTURE-001` | PORT-002 prerequisite | fixture contract runner | `TEST-FIXTURE-CONTRACT` | `cmd[TEST-FIXTURE-CONTRACT]` | corrected reproduction README | Runtime/source checks prove the exact 64×64 one-company coal-road-freight structure, IDs, coordinates, route, stops, depot, vehicle, cargo, and exclusions. |
| `FIX-SETTINGS-001` | PORT-002 prerequisite | normalized settings | `TEST-FIXTURE-CONTRACT` | `cmd[TEST-FIXTURE-CONTRACT]` | runtime setting probe | Every reached behavior setting is present, normalized, runtime-verified, and hashes to the frozen settings identity. |
| `FIX-REPRODUCTION-001` | PORT-002 prerequisite | fixture builder | `TEST-FIXTURE-CONTRACT` | `cmd[TEST-FIXTURE-CONTRACT]` | reproduction JSON | Two isolated fixture builds reproduce the exact frozen save and map bytes and their declared sizes/digests. |
| `FIX-MILESTONES-001` | 0003 native replay; 0005 predicates; 0007 two-load evidence | native replay driver, 0005 projection predicates, and 0007 two-load continuation runner | `TEST-FIXTURE-RUNTIME` | `cmd[TEST-FIXTURE-RUNTIME]` | two-load native replay tapes and checkpoint-first-occurrence report | Two isolated loads have equal initial projections and native replay reaches all eight state-backed checkpoint predicates, including delivery and payment, at identical first occurrences. |
| `CMD-FORMAT-001` | 0003 | command-input codec/schema | `TEST-COMMAND-CONTRACT` | `cmd[TEST-COMMAND-CONTRACT]` | command validation summary and content-addressed hostile-input corpus index | Every valid command vector decodes canonically; every malformed, truncated, overflowed, reserved, checksum-invalid, nonmonotonic, or trailing-byte vector fails before fixture load with zero commands. |
| `CMD-NATIVE-DISPATCH-001` | 0003 | six generated typed bindings to `Command<Commands::X>::Post` plus scoped external-command context | `TEST-COMMAND-CONTRACT` | `cmd[TEST-COMMAND-CONTRACT]` | six-action ledger, compile assertions, and native call-count report | Exactly six registry actions map to the pinned enums and typed `Post` overloads; each scheduled action posts once; no GUI path, direct procedure call, gameplay reimplementation, or second command call exists. |
| `CMD-RESULTS-001` | 0003 | `CommandHelper::Execute` observation hooks, native tuple copier, and execute-only `CmdBuildRoadStop` station-ID hook | `TEST-COMMAND-CONTRACT` | `cmd[TEST-COMMAND-CONTRACT]` | ten-command result inventory, rejected-command inventory, and returned-ID provenance report | Accepted actions emit one intent, one successful test, one execute, exact cost/category/errors/result bytes, returned IDs, then one post-command projection; rejected tests emit no execute and no ID side result. |
| `CMD-RANDOM-PREFIXES-001` | 0007, exercising 0003 command handling | differential runner | `TEST-COMMAND-CONTRACT`, `TEST-DIFFERENTIAL-CAMPAIGN` | `cmd[TEST-COMMAND-CONTRACT]`, `cmd[TEST-DIFFERENTIAL-CAMPAIGN]` | prefix seed/index JSON, invalid proportion, repeat digests, and minimized failures | Exactly 10,000 seeded prefixes with at least 30% invalid execute twice with identical classifications/results; every failure is rerun, minimized to a valid causal prefix, and retained. |
| `TRACE-PATCH-SERIES-001` | 0003–0007 | `oracle/instrumentation/patches/series` and the seven exact patch files | `TEST-INSTRUMENTATION-CONTRACT` | `cmd[TEST-INSTRUMENTATION-CONTRACT]` | series file/digest, per-prefix apply/build/test/reverse logs, and clean-pin proofs | The exact seven filenames apply in order, each prefix builds/tests independently, reverse in reverse order, and return the disposable worktree to the exact clean pin. |
| `TRACE-BOUNDARIES-001` | 0003 framing; 0004–0005 complete projection; 0007 comparison | trace lifecycle state machine, projection completion callback, checkpoint evaluator, terminal writer | `TEST-INSTRUMENTATION-CONTRACT` | `cmd[TEST-INSTRUMENTATION-CONTRACT]` | boundary coverage JSON from native, C17, and Python decoders | Native, C17, and Python views agree on replay-start, command phases, one post-command projection per action, one post-tick projection per completed tick, checkpoint-after-projection ordering, and terminal ordering. |
| `TRACE-PROJECTION-001` | 0004–0005; 0007 omission and runtime audit | generated projection adapter driven by the validated 757-row ledger | `TEST-INSTRUMENTATION-CONTRACT` | `cmd[TEST-INSTRUMENTATION-CONTRACT]` | 757-row runtime inventory, omission report, and projection digests | Every complete projection has exactly the 757 authoritative IDs once in increasing order with exact type/count/payload metadata and no mutating read. |
| `TRACE-RNG-TIMERS-001` | 0004 globals; 0005 entity schedules; 0007 neutrality | 0004 global/RNG/timer emitters and 0005 scheduler/controller fields | `TEST-INSTRUMENTATION-CONTRACT` | `cmd[TEST-INSTRUMENTATION-CONTRACT]` | RNG/timer source audit and before/after neutrality comparison | Both RNG streams and every registered future-influencing clock, timer, pause, controller, schedule, and cursor value are projected exactly; observation changes none. |
| `TRACE-MAP-POOLS-001` | 0004 map; 0005 pools; 0007 validation | 0004 ten-plane map emitters and 0005 exact pool/allocation emitters | `TEST-INSTRUMENTATION-CONTRACT` | `cmd[TEST-INSTRUMENTATION-CONTRACT]` | map/pool exactness report and fragmented-allocation vectors | All ten raw map planes contain 4,096 values in `TileIndex` order and every registered pool emits exact capacity, cursors, bitmap words/padding, occupancy, allocation state, stable IDs, order, and references. |
| `TRACE-IO-FAIL-CLOSED-001` | 0001 sink; 0003 integration; 0007 fault campaign | existing trace sink first-error state plus propagated replay/projection abort path | `TEST-INSTRUMENTATION-CONTRACT` | `cmd[TEST-INSTRUMENTATION-CONTRACT]` | fault matrix, retained `.partial` files, and no-final-output assertions | Every declared read/write/fsync/rename/permission/space fault returns nonzero, retains the first error and valid partial, executes no forbidden recovery, and never publishes a final tape. |
| `TRACE-DETERMINISM-001` | 0007 | 0007 deterministic recording campaign runner | `TEST-ORACLE-DETERMINISM` | `cmd[TEST-ORACLE-DETERMINISM]` | recording manifest and digest-equivalence summary for 2+20+8 runs | Two golden, twenty serial, and eight isolated parallel same-feature recordings share one verified authoritative tape digest and identical identities. |
| `TRACE-NONPERTURBATION-001` | 0006 isolation; 0007 campaign | 0007 plain/OFF/disabled/enabled and diagnostics-off/on comparator campaigns | `TEST-ORACLE-DETERMINISM` | `cmd[TEST-ORACLE-DETERMINISM]` | plain/OFF/disabled/enabled and diagnostics-off/on comparison reports | Plain, patched-OFF, patched-ON/runtime-disabled, and patched-ON/enabled runs have equal native and authoritative continuation outcomes; diagnostics alter only declared optional records. |
| `TAPE-FORMAT-001` | PORT-004 integration dependency; 0007 consumes and verifies | C17 reader/writer, ADR 0004 | `TEST-TAPE-NATIVE` | `cmd[TEST-TAPE-NATIVE]` | native tape unit summary and independently reviewed golden bytes | All produced partial/final files satisfy the exact tape-v1 prefix, header, records, projection, terminal, trailer, counters, padding, and digest grammar. |
| `TAPE-WRITER-001` | PORT-004 integration dependency; 0007 consumes and verifies | writer and partial finalizer | `TEST-TAPE-NATIVE` | `cmd[TEST-TAPE-NATIVE]` | writer/finalizer atomicity and fault result set | Checked streaming and atomic finalization pass all arithmetic and output-fault tests; unequal existing files are never overwritten and no partial is mislabeled final. |
| `TAPE-READER-001` | PORT-004 integration dependency; 0007 consumes and verifies | tape reader | `TEST-TAPE-NATIVE` | `cmd[TEST-TAPE-NATIVE]` | reader malformed-corpus result plus closure evidence for mapped defects | The reader accepts every golden vector and rejects all truncation, corruption, overflow, noncanonical, reserved, and trailing cases; mapped reader/static defects are closed before final P0 PASS. |
| `TAPE-PYTHON-REFERENCE-001` | PORT-004 integration dependency; 0007 consumes and verifies | Python decoder | `TEST-TAPE-PYTHON` | `cmd[TEST-TAPE-PYTHON]` | C17/Python acceptance and logical-decode differential report | Independent Python and C17 implementations agree on acceptance, error family/location, identities, record structure, and logical decode without shared production parsing code. |
| `TAPE-NEGATIVE-CORPUS-001` | PORT-004 integration dependency; 0007 consumes and verifies | native unit corpus | `TEST-TAPE-NATIVE`, `TEST-FAULT-INJECTION` | `cmd[TEST-TAPE-NATIVE]`, `cmd[TEST-FAULT-INJECTION]` | malformed inventory with family, byte/region, owner, and expected location | Every byte of small vectors and every structural region/semantic rule has a declared malformed case with expected owner and earliest failure; all cases reject deterministically. |
| `TAPE-RESOURCE-BOUNDS-001` | PORT-004 integration dependency; 0007 consumes and verifies | C17 limits | `TEST-TAPE-NATIVE` | `cmd[TEST-TAPE-NATIVE]` | near-limit sparse-file RSS/work/output report | Near-limit sparse inputs keep reader, writer, comparator, minimizer, and fuzz targets within frozen memory/work/output limits and show no whole-file theoretical-size allocation. |
| `CMP-IDENTITY-001` | PORT-004 tool; 0007 campaign integration | comparator | `TEST-COMPARATOR` | `cmd[TEST-COMPARATOR]` | identity fault reports and exit-code inventory | Each identity-component mutation exits with identity-mismatch status before any state comparison and reports the exact unequal components. |
| `CMP-FIRST-DIVERGENCE-001` | PORT-004 tool; 0007 campaign integration | comparator | `TEST-COMPARATOR` | `cmd[TEST-COMPARATOR]` | command/field fault reports naming exact first divergence | Every command/field mutation exits with divergence status and reports the exact earliest boundary, sequence, field/element or command result, and both values; diagnostics cannot hide it. |
| `CMP-REPORT-001` | PORT-004 tool; 0007 campaign integration | comparator/report schema | `TEST-COMPARATOR` | `cmd[TEST-COMPARATOR]` | schema validation and output-failure report | Every report validates, remains bounded, contains both complete identities, argv arrays, prior checkpoint, last command, source/cache policy, and safe exact context; report-write failure fails the test. |
| `MIN-SIGNATURE-001` | PORT-004 tool; 0007 campaign integration | minimizer | `TEST-MINIMIZER` | `cmd[TEST-MINIMIZER]` | original/minimized signature comparison report | Minimization preserves the complete divergence signature, including public step, tick, boundary, sequence, record, field/element, and both differing values. |
| `MIN-VALID-PREFIX-001` | PORT-004 tool; 0007 campaign integration | minimizer/finalizer | `TEST-MINIMIZER` | `cmd[TEST-MINIMIZER]` | minimized finalized tapes, digests, and independent validation | The emitted minimum is an independently valid finalized tape, is the smallest tested logical prefix that preserves the signature, and is never raw truncation. |
| `FIELD-REGISTRY-001` | Pre-code gate; 0004–0005 generated bindings | strict registry/schema validators and generated field bindings | `TEST-FIELD-SCHEMA` | `cmd[TEST-FIELD-SCHEMA]` | registry digest, schema/semantic validation, and regeneration comparison | Registry/schema/semantic validation and regeneration pass; exactly 816 unique typed fields exist, exactly 757 are authoritative, and all metadata/source anchors/count dependencies are valid. |
| `FIELD-COMPLETENESS-001` | 0004–0005; 0007 runtime omission campaign | 757-row Markdown/JSON ledger, P4/P5 set proof, runtime ID-sequence auditor | `TEST-FIELD-SCHEMA` | `cmd[TEST-FIELD-SCHEMA]` | 757-row Markdown/JSON ledgers, P4/P5 set proof, omission/runtime audit | The 757-row ledger has one complete row per authoritative ID; P4 and P5 are disjoint and union exactly to the authoritative set; omission and runtime every-boundary audits detect every missing row. |
| `FIELD-INVARIANTS-001` | 0007 over 0004–0005 projection | test-only invariant adapter invoked after a complete projection | `TEST-INVARIANTS` | `cmd[TEST-INVARIANTS]` | normal and injected-fault invariant summaries plus retained partials | All normal projections satisfy every structural/economic/cargo/timer invariant; each injected fault fails at its declared earliest invariant, retains the partial, and records evidence. |
| `CACHE-CLASSIFICATION-001` | 0005 projection policy; 0007 experiments | registry classification plus 0005 authoritative cache emitters | `TEST-CACHE-EXPERIMENTS` | `cmd[TEST-CACHE-EXPERIMENTS]` | classification table and source-reviewed derivation decisions | Every reached cache is explicitly classified; no reached future-influencing cache is omitted as derived without the complete approved clear/rebuild/continuation proof. |
| `CACHE-CONTINUATION-001` | 0007 | 0007 production clear/rebuild and continuation experiment runner | `TEST-CACHE-EXPERIMENTS` | `cmd[TEST-CACHE-EXPERIMENTS]` | clear/rebuild/next-step/two-load/10,000-tick comparison artifacts | Approved clear/rebuild experiments match immediate state, next command/tick, two independent loads, and 10,000-tick continuation; any mismatch keeps or reclassifies the cache authoritative. |
| `TEST-NATIVE-MATRIX-001` | 0007 orchestration or final P0 infrastructure | presets and warnings | `TEST-BUILD-MATRIX` | `cmd[TEST-BUILD-MATRIX]` | seven-profile configure/build/test matrix | All seven genuinely distinct GCC/Clang debug/release/sanitizer/coverage/fuzz profiles configure, build, and pass their assigned suites; no alias profile qualifies. |
| `TEST-SANITIZERS-001` | 0007 orchestration or final P0 infrastructure | sanitizer runner | `TEST-SANITIZERS` | `cmd[TEST-SANITIZERS]` | ASan, leak, and UBSan raw reports | ASan, leak detection, and fail-fast UBSan cover every native entry point with zero finding, leak, recovery, timeout, or suppressed mandatory failure. |
| `TEST-STATIC-ANALYSIS-001` | 0007 orchestration or final P0 infrastructure | static runner | `TEST-STATIC-ANALYSIS` | `cmd[TEST-STATIC-ANALYSIS]` | warnings/Tidy/analyzer/ShellCheck/semantic/policy scan bundle | Compiler warnings, Clang-Tidy, analyzer, ShellCheck, semantic/schema, secret, license, and policy scans report zero unwaived finding; diagnosed defects are honestly mapped until closed. |
| `TEST-COVERAGE-001` | 0007 orchestration or final P0 infrastructure | coverage runner | `TEST-COVERAGE` | `cmd[TEST-COVERAGE]` | coverage summary, raw data, threshold result, and risk-branch proof | Frozen line/function thresholds pass and every declared high-risk branch has an asserting test, not execution-only coverage. |
| `TEST-MUTATION-001` | 0007 orchestration or final P0 infrastructure | mutation runner/plan | `TEST-MUTATION` | `cmd[TEST-MUTATION]` | mutant inventory, expected detector mapping, and kill report | Every reviewed mandatory killable mutant is killed by its expected semantic detector; build failure or unrelated crash does not count as a kill. |
| `TEST-FUZZ-001` | 0007 orchestration or final P0 infrastructure | fuzz targets/runner | `TEST-FUZZ` | `cmd[TEST-FUZZ]` | target budgets, logs, corpus indexes, and finding regressions | Every byte-entry fuzz target completes the frozen local-release budget with no crash, sanitizer finding, OOM, timeout, or unexpected acceptance; findings become content-addressed regressions. |
| `TEST-DIFFERENTIAL-001` | 0007 orchestration or final P0 infrastructure | 0007 external-oracle and C17/Python differential campaign runner | `TEST-DIFFERENTIAL-CAMPAIGN` | `cmd[TEST-DIFFERENTIAL-CAMPAIGN]` | external and internal differential summary plus retained divergences | Fixed external-oracle and independent C17/Python differentials agree across the required corpus; differences produce retained earliest-divergence evidence and no scalar-backend claim. |
| `TEST-FAULT-INJECTION-001` | 0007 orchestration or final P0 infrastructure | fault runner | `TEST-FAULT-INJECTION` | `cmd[TEST-FAULT-INJECTION]` | fault inventory and expected-owner/actual-owner summary | Every required identity, tape, command, projection, invariant, I/O, and report fault reaches exactly its expected owner and earliest signature with no false pass. |
| `TEST-CI-001` | Repository CI policy; not release authority | P0 workflow | `TEST-CI-POLICY` | `cmd[TEST-CI-POLICY]` | workflow policy report and thirteen job results | The workflow contains exactly the thirteen mandatory SHA-pinned least-privilege jobs and each passes its bounded contract; CI results remain distinct from local-release closure. |
| `TEST-TRACEABILITY-001` | All patches and final P0 | machine registry, human view, semantic validator, and exact 56-ID shape audit | `TEST-TRACEABILITY-LINT` | `cmd[TEST-TRACEABILITY-LINT]`; release form: `./scripts/ci/p0_traceability.sh --tools-python /absolute/path/to/python` | validated machine registry, corrected human view, 56-ID shape audit, and linter output | Machine and human views contain the same 56 unique IDs, every row is bidirectionally mapped and has eight cells, all owned files/tests/evidence/defects/gates are covered, and no dishonest PASS or mandatory SKIP exists. |
| `EVID-BUNDLE-001` | All patches; final P0 closure | evidence bundler | `TEST-EVIDENCE-CONTRACT` | `cmd[TEST-EVIDENCE-CONTRACT]` | canonical evidence bundle manifest and verified member digests | Every mandatory artifact is durable, regular, bounded, identity-linked, retrievable where external, and matches its recorded SHA-256; no passing claim depends on ephemeral local-only data. |
| `EVID-LEDGER-001` | All patches; final P0 closure | machine ledger/human view | `TEST-EVIDENCE-CONTRACT` | `cmd[TEST-EVIDENCE-CONTRACT]` | machine ledger, human view, closure artifacts, and validator output | Append-only machine and human ledgers validate; every entry has evidence and traceability; final P0 PASS has zero nonclosed P0 defect or divergence. |
| `EVID-FINAL-RESULT-001` | All patches; final P0 closure | `oracle/runner/p0_gate.sh`, result schema, and exact 26-section completion report | `TEST-EVIDENCE-CONTRACT` | `cmd[TEST-EVIDENCE-CONTRACT]`; release form: `./oracle/runner/p0_gate.sh --profile local-release --artifact-root /absolute/caller/controlled/path --tools-python /absolute/hash/locked/python` | two `P0_GATE_RESULT.json` files, exact 26-section report, clean-tree proof, and push proof | All 34 mandatory stages are present exactly once and PASS in two unchanged local-release runs; the machine result and 26-section report validate; trees are clean and the final local tip equals the remote tip. |

No row may be changed to `PASS` based only on compilation, a focused test, documentation completion, or one historical run. The machine registry controls status; the human view must preserve the same explicit value.

# 11. FINISHED PRODUCT DEFINITION

## 11.1 Exact Patch-Series State

The patch-series task is complete only when `oracle/instrumentation/patches/series` has exactly these effective entries in this order:

```text
0001-trace-sink-and-codec.patch
0002-build-and-run-identity.patch
0003-native-command-input-and-boundary-records.patch
0004-global-state-and-map-projection.patch
0005-pool-and-entity-projection.patch
0006-optional-route-controller-cargo-diagnostics.patch
0007-test-consistency-and-nonperturbation-hooks.patch
```

All seven files exist as regular outer-repository files, have recorded SHA-256 values, apply without fuzz or offset to a disposable worktree at the exact pin, pass every prefix-owned test, and reverse in exact reverse order to a clean pin. Patches 0001 and 0002 remain byte-identical unless a separately reviewed correction explicitly changes their registered identities.

## 11.2 Required Repository Artifacts

The outer repository contains or updates, at minimum:

- the exact five new patch files and seven-entry `series`;
- `oracle/instrumentation/README.md` with verified commands and failure behavior;
- one exact six-row command dispatch ledger plus machine validation data;
- one exact 757-row field projection ledger plus machine JSON and P4/P5 difference-set proof;
- the complete touched-file manifest;
- all newly required source-register entries;
- focused command, projection, diagnostic, invariant, continuation, and campaign tests in the existing repository structure;
- exact runner updates and `verified-test-command-inventory.json`;
- machine/human traceability with the same 56 IDs and valid eight-cell human rows;
- evidence/defect mappings and content-addressed indexes.

No build tree, full tape corpus, credential, mutable workspace-only path, or direct submodule edit is added to tracked source.

## 11.3 Required Runtime Behavior

From a clean pinned disposable worktree, the complete series must:

1. validate the complete command file and canonical identities before fixture load;
2. load only the frozen fixture under isolated deterministic paths;
3. dispatch the ten fixture command instances through exactly six typed native command families;
4. emit one external intent, one top-level native test, conditional one top-level execute, and one post-command projection per action;
5. obtain `VehicleID` from the native execute tuple and `StationID` only from the guarded execute-only final `st->index` hook;
6. suppress external phase records for recursive/internal native commands;
7. emit one initial complete projection after `REPLAY_START`, one complete post-command projection after every accepted or rejected action, and one complete post-tick projection after every completed native tick;
8. evaluate checkpoints after the proving complete projection, emit each reached ID once, and emit checkpoint 8 after the final post-tick projection immediately before terminal;
9. keep all optional diagnostics default-off, separately declared, and outside authoritative equality;
10. write only a valid partial journal from C++ and finalize transactionally through the C17 authority;
11. fail closed with retained first-error evidence on malformed input, projection failure, trace failure, comparator/report failure, or evidence failure.

## 11.4 Exact Definition of Complete 757-Field Projection

A complete projection satisfies all of the following simultaneously:

- the validated current registry version and digest govern the output;
- exactly the 757 IDs classified `authoritative_full` appear once each in strictly increasing numeric order;
- every field header and payload matches registry type, width, signedness, count, capacity, stable-ID, sentinel, presence, offset, padding, and owner-order rules;
- the P4 and P5 emitted sets are disjoint and union exactly to the authoritative set;
- every dynamic and nested count/offset range is internally valid and terminates at the exact flattened payload length;
- each of the ten raw map planes contains exactly 4,096 values in numeric `TileIndex` order;
- all required occupied, free, empty, destroyed, optional, allocation, cursor, bitmap, container-order, and stable-reference state is present;
- no diagnostic, pointer, address, host padding, allocator token, locale artifact, wall-clock value, or unordered iteration leaks into authority;
- projection performs no mutation, allocation, cache fill/rebuild, RNG draw, command, pathfinding, save/load, callback scheduling, or thread synchronization;
- C17 and independent Python decoders report the same 757 IDs, metadata, and canonical bytes.

A count of 757 without row-complete source proof and runtime omission coverage is not completion.

## 11.5 Exact Definition of Deterministic Replay

For identical source, build, executable, fixture, settings, content, command input, schema, series, feature, and environment identities:

- command acceptance/rejection, phase counts, costs, expense categories, error IDs, native result tuple bytes, returned IDs, and state transitions match;
- boundary sequence, public steps, native ticks, ordinals, checkpoint IDs/first occurrences, and terminal state match;
- every authoritative projection byte matches;
- RNG, timers, pause, pool allocation, packet/container order, LinkGraph schedule state, ledgers, and continuation outcomes match;
- both golden tapes are byte-identical;
- all two golden, twenty serial, and eight isolated parallel recordings share one authoritative digest for the same feature configuration;
- two independent loads and the 10,000-tick continuation match;
- the two 10,000-prefix campaign executions classify and reproduce every prefix identically.

## 11.6 Exact Definition of Non-Perturbation

Instrumentation is non-perturbing only when:

- plain, patched-OFF, patched-ON/runtime-disabled, and patched-ON/enabled binaries produce equal native command and authoritative continuation outcomes;
- trace-enabled mode adds only declared trace I/O;
- diagnostics-enabled mode changes only declared optional diagnostic records and header feature identity;
- command timing, native tick order, both RNG streams, all timer/date/pause state, pool allocation order, path/controller choices, cargo movement, LinkGraph scheduling, ledgers, checkpoints, save-visible state, and terminal outcomes remain equal;
- no extra command, callback, pathfinder, cache checker/rebuilder, RNG draw, gameplay allocation, save/load, or worker synchronization occurs.

## 11.7 Command-Line and Failure Behavior

- compile-off: no trace adapter linkage or trace dependency;
- compile-on/runtime-disabled: no input/output open and zero trace payload while native behavior remains equal;
- compile-on/runtime-enabled with complete valid options: deterministic replay and a partial journal suitable for C17 finalization;
- incomplete options, malformed input, identity mismatch, unknown action/field, invalid reference, incomplete projection, duplicate/missing phase, write error, or retention error: explicit nonzero failure before any false final artifact;
- tape finalization: exclusive temporary creation, checked streaming, file `fsync`, independent validation, no-overwrite atomic link, and parent-directory `fsync`; general evidence publication uses same-filesystem atomic rename and parent-directory `fsync`; unequal existing content is never overwritten.

## 11.8 Patch-Series Completion Versus Full P0 Completion

An independent reviewer may issue `PATCH_SERIES_PASS` only when every requirement owned by patches 0003–0007 and every necessary integration dependency passes with validated evidence. Because this task prohibits commit and push, a reviewed uncommitted patch-series result may still be reported while the full release remains `IN_PROGRESS`.

Full `P0 PASS` additionally requires:

- all PORT-001 through PORT-005 gates;
- closure of every nonclosed defect/divergence, including `DEF-P0-0001` and `DEF-P0-0002`;
- exact durable evidence bundle and retrieval proof;
- reviewed correction of the ADR 0003 PORT002A/PORT002B status contradiction without changing frozen fixture artifacts;
- valid machine/human traceability and zero orphan mappings;
- clean outer tree and clean pinned submodule;
- final local commit equal to the configured remote branch tip;
- the 34-stage `local-release` gate passing twice without tracked-source change;
- schema-valid `P0_GATE_RESULT.json` and exact 26-section completion report.

# 12. FINAL CODEX HANDOFF

```text
CODEX — BINDING EXECUTION INSTRUCTION

Work only on the current branch fix/p0-build-portability. Do not switch, create,
rename, merge, rebase, reset, clean, stash, commit, push, force-push, or rewrite
history. Preserve all existing outer-tree user changes. Keep openttd-upstream
clean at commit 29f808ef0022064e6d9a83c8476d1e0f4686af86 and apply source changes
only in disposable worktrees.

Before production C++ work, pass E0 through E13. Prove the exact 0001/0002 prefix
applies, builds, tests, and reverses. Validate the command, field, projection,
traceability, and ledger machine authorities. Produce the exact six-row native
dispatch ledger, exact 757-row field ledger, disjoint P4/P5 union proof, source-
register closure audit, exact argv inventory, and exact touched-file manifest.
Stop on the first unresolved command operand, result byte, field row, source
symbol, file owner, test command, schema conflict, or repository contradiction.

Create these exact patch files in order and append each series entry only after
its complete prefix gate passes:
  oracle/instrumentation/patches/0003-native-command-input-and-boundary-records.patch
  oracle/instrumentation/patches/0004-global-state-and-map-projection.patch
  oracle/instrumentation/patches/0005-pool-and-entity-projection.patch
  oracle/instrumentation/patches/0006-optional-route-controller-cargo-diagnostics.patch
  oracle/instrumentation/patches/0007-test-consistency-and-nonperturbation-hooks.patch

Patch 0003 owns strict whole-file command input, preallocated scoped company/action
context, exact six-family typed Post dispatch with no callback, normalized intent
emission after native prechecks and SetClientIds, buffered final native test/execute
observation, outer-company restoration before result publication/projection,
recursive-command suppression, execute-tuple VehicleID capture, and execute-only
final st->index capture at the exact post-station-change/pre-return BuildRoadStop
source point. Suppress only active-oracle presentation. Do not change native command
signatures or network wire bytes. Stop for a reviewed format migration when the
current schema lacks the required normalized station-result field.

Patch 0004 owns canonical projection framing and every P4 singleton/global/time/
timer/RNG/process-setting/economy/map field, including all ten raw 4,096-element
map planes in TileIndex order. Patch 0005 owns every P5 pool/entity/container/
cache/reference field, exact 757 completion, and state-backed checkpoint predicates.
Patch 0006 owns only default-off separately framed non-authoritative diagnostics
that copy already-computed values. Patch 0007 owns test-only invariants and the
determinism, replay, continuation, non-perturbation, differential, fault, quality,
traceability, and evidence campaigns.

Never reimplement gameplay, call a gameplay command twice, emit external phases
for recursive/internal commands, scan pools to infer returned IDs, consume RNG,
advance timers, invoke pathfinding, rebuild/fill a cache, force LinkGraph worker
synchronization, normalize native container order, serialize a pointer/address,
omit free or empty allocation state, silently drop a field/record, or fabricate a
schema/source/test value.

Mandatory evidence includes exact command results for all ten fixture instances;
accepted and rejected lifecycle counts; malformed-file zero-execution proof; all
757 authoritative fields at replay-start, every post-command, and every post-tick
projection; all ten raw map planes; fragmented pool/allocation/reference/container
coverage; checkpoint first occurrences; diagnostics isolation; two golden, twenty
serial, and eight isolated parallel recordings; plain/OFF/disabled/enabled equality;
two-load and 10,000-tick continuation; two deterministic 10,000-prefix campaigns;
seven build profiles; sanitizers; static analysis; coverage; fuzzing; reviewed
mutation; differential and fault injection; 56-ID traceability; and validated,
digest-linked evidence retention.

A failed write, fsync, no-overwrite link, evidence rename, finalization,
comparison, report, digest, retrieval, or evidence-validation step is a task
failure. Preserve raw argv arrays, logs,
partials, tapes, identities, first-divergence reports, minimized valid prefixes,
seeds, sizes, SHA-256 values, and defect/requirement mappings.

Completion condition for PATCH_SERIES_PASS: the exact seven patches apply in order,
every prefix and assigned test passes, all six command families use exact native
typed dispatch, every complete projection contains exactly all 757 authoritative
fields once, checkpoints and diagnostics obey their contracts, deterministic and
non-perturbation campaigns pass at frozen counts, the full series reverses to the
exact clean pin, all required evidence validates, and the permanent submodule
remains unchanged. Report full P0 status separately and keep every external release
blocker visible.
```
