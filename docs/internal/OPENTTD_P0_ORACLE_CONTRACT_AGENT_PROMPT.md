# Execution Contract: P0 Oracle Harness for Exact OpenTTD Parity

> **Legacy scope notice (2026-07-31):** This is the frozen execution contract for
> the repository's earlier 64 by 64 road-freight oracle/parity workstream. It does
> not define the active product goal and must not be used to expand Version 1 into
> freight, a clean-room gameplay port, or CUDA simulation. `GOAL.md` and
> `docs/project/REQUIREMENTS.md` govern the active 32 by 32 passenger-bus PPO
> platform. Preserve this document as historical authority for legacy P0 artifacts.

## Copy-paste instruction for the implementation agent

You are the implementation owner for the P0 oracle-contract phase of `goldbar123467/openttd-cuda-rl`.

Complete exactly five backlog deliverables in dependency order:

1. `PORT-001` — reproducible source, toolchain, dependency, build, test, and runtime pinning;
2. `PORT-002` — one frozen lawful deterministic 64×64 road-freight fixture;
3. `PORT-003` — non-perturbing native OpenTTD command and authoritative-state instrumentation;
4. `PORT-004` — a versioned binary tape, strict parser, validator, inspector, comparator, and prefix minimizer;
5. `PORT-005` — a frozen future-complete field schema and explicit cache policy.

Do not stop until the entire P0 oracle-contract deliverable is completely done.

Completion means every mandatory gate in the contract reports `PASS`, every produced claim has raw evidence, every failure mode has a regression test, every authoritative input has a canonical manifest and SHA-256 digest, the pinned OpenTTD submodule remains clean, the working branch has been pushed, and the repository contains no unfinished P0 placeholder, stub, silent fallback, unresolved divergence, or undocumented skip.

A partial implementation, research report, source tour, proposed design, unexecuted test plan, green summary without raw artifacts, or plausible transport simulation does not satisfy the assignment.

---

## 1. Exact end state

A fresh Ubuntu 24.04 x86-64 checkout at outer commit lineage derived from `58895696c8a75eda2fac2ae553654ba4398f5cda`, with OpenTTD submodule commit `29f808ef0022064e6d9a83c8476d1e0f4686af86`, must support one documented top-level P0 gate command that performs the following work without manual GUI input:

1. verifies repository identity, branch state, submodule identity, submodule cleanliness, required tools, required content, and secret-safe environment handling;
2. configures and builds the uninstrumented pinned OpenTTD reference with the frozen `RelWithDebInfo` profile;
3. enumerates the exact CTest inventory and proves the observed reference profile contains 99 tests;
4. runs all 99 upstream tests with zero failures;
5. runs the frozen headless smoke workload with null video, sound, music, and blitter backends;
6. verifies OpenGFX 8.0 by the approved SHA-256 digest before use;
7. verifies the frozen 64×64 fixture, normalized settings, content profile, company state, industry pair, vehicle availability, tile coordinates, timer boundary, and both RNG states;
8. applies a numbered instrumentation patch series to a disposable worktree while leaving `openttd-upstream` clean;
9. builds trace-disabled and trace-enabled instrumented references from the same pinned source and equivalent build options;
10. replays a versioned native command-input script through the native OpenTTD command path rather than direct state mutation;
11. records complete authoritative projections after every declared command and tick boundary;
12. records two independent reference runs whose finalized tape bytes match exactly;
13. proves trace-disabled, trace-enabled, and uninstrumented continuations remain equivalent at declared boundaries;
14. validates both tapes with an independent strict decoder;
15. compares equal tapes and reports equality;
16. injects a known command or field mismatch and reports the exact earliest boundary, exact field, exact oracle value, exact target value, and minimal valid reproducing prefix;
17. rejects malformed, truncated, corrupted, oversized, identity-mismatched, and checksum-invalid tapes without undefined behavior, partial output mutation, or process crash;
18. validates every frozen field-schema entry, source anchor, type, width, signedness, order, ownership rule, boundary rule, cache class, sample encoding, and continuation rationale;
19. runs unit, golden-vector, negative, property, differential, sanitizer, fuzz, determinism, non-perturbation, static-analysis, coverage, mutation, license, security, and clean-tree gates;
20. emits canonical machine-readable evidence and a human-readable completion report;
21. exits nonzero for any unmet mandatory condition;
22. leaves no scalar gameplay port, Python RL wrapper, batched CPU backend, viewer, renderer, or CUDA implementation in the branch.

The P0 phase closes only after the full workflow above passes from a clean checkout.

---

## 2. Scope boundary

### 2.1 Required scope

The implementation agent MUST build the complete oracle-contract foundation needed for a later exact scalar C17 port. Required work includes reproducible reference construction, fixture freezing, native command injection, direct field projection, binary recording, strict decoding, first-divergence analysis, failure minimization, schema governance, cache classification, and evidence retention.

### 2.2 Forbidden scope

The implementation agent MUST NOT perform any work from `PORT-006` or later. The following work remains forbidden during P0:

- scalar OpenTTD gameplay transition code;
- an invented transport simulation;
- the optional `rules-v1` harness;
- Python environment APIs;
- NumPy or tensor observation APIs;
- batched CPU stepping;
- CUDA kernels;
- CUDA data layouts;
- GPU benchmarks;
- reinforcement-learning algorithms;
- PPO code;
- reward shaping;
- neural-network code;
- UI automation;
- SDL viewer work;
- rendering parity;
- rail, ships, aircraft, towns, multiplayer, NewGRFs, GameScript, or procedural-generation breadth;
- broad refactoring of upstream OpenTTD;
- optimization work not required to prevent a correctness or resource-safety failure.

A fast P0 tool has no value when a correctness gate remains open. Correctness, determinism, auditability, and failure localization dominate throughput during P0.

### 2.3 No scope laundering

The implementation agent MUST NOT rename later-phase work as “support code,” “future proofing,” “temporary scaffolding,” “benchmark plumbing,” or “small cleanup.” Any code capable of simulating the road-freight transition outside pinned OpenTTD belongs to a later phase and must remain absent.

---

## 3. Authority hierarchy

When documents, comments, observations, or assumptions disagree, apply the following order:

1. pinned OpenTTD source and pinned OpenTTD tests at commit `29f808ef0022064e6d9a83c8476d1e0f4686af86`;
2. repeated observations from binaries built from that exact commit under the frozen profile;
3. `NEXT_STAGES_IMPLEMENTATION_HANDOFF.md`;
4. `OpenTTD_CUDA_RL_REVERSE_ENGINEERING_REPORT.md`;
5. `research-notes/09-verification-audit.md`;
6. subsystem-specific repository research notes;
7. official language, build-system, file-format, hashing, sanitizer, and license specifications;
8. peer-reviewed software-testing literature;
9. implementation hypotheses, clearly labeled and experimentally tested.

No blog post, generated explanation, memory-based claim, current OpenTTD `master` behavior, or convenience assumption may override pinned source behavior.

---

## 4. Mandatory source register

Create `docs/sources/P0_SOURCE_REGISTER.md`. Record every source below with title, URL or local path, version or commit, access date, relevant sections, affected decision records, and implementation files governed by the source.

### 4.1 Pinned OpenTTD source behavior

Use exact-commit URLs and local source files. Never substitute current `master` source for parity decisions.

- Pinned tree: <https://github.com/OpenTTD/OpenTTD/tree/29f808ef0022064e6d9a83c8476d1e0f4686af86>
- Main loop: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/openttd.cpp>
- Command declarations: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/command_func.h>
- Command execution: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/command.cpp>
- Road GUI command origins: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/road_gui.cpp>
- Road world behavior: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/road_cmd.cpp>
- Station behavior: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/station_cmd.cpp>
- Station state: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/station_base.h>
- General vehicle behavior: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/vehicle_cmd.cpp>
- Road vehicle behavior: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/roadveh_cmd.cpp>
- Order behavior: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/order_cmd.cpp>
- Road YAPF behavior: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/pathfinder/yapf/yapf_road.cpp>
- Economy and delivery: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/economy.cpp>
- Save/load behavior: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/saveload/saveload.cpp>
- Build instructions: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/COMPILING.md>
- Coding rules: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/CODINGSTYLE.md>
- Contribution and AI policy: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/CONTRIBUTING.md>
- License: <https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/COPYING.md>

The named files form starting anchors rather than a complete dependency list. Follow every reached call into tile procedures, pools, timers, settings, caches, cargo packets, engine tables, industry tables, content tables, and helpers. Record every additional reached source file in the source register.

### 4.2 Content and licensing

- OpenGFX 8.0 release and digest: <https://www.openttd.org/downloads/opengfx-releases/latest>
- SPDX `GPL-2.0-only`: <https://spdx.org/licenses/GPL-2.0-only.html>

Freeze the OpenGFX 8.0 archive SHA-256 as:

```text
43a0c1dabf39cb865394f3a6cc36d4da5c10ecfaaf55652043104806810903be
```

Never trust a filename, HTTP status alone, archive metadata, or previously extracted directory. Verify exact bytes before extraction and verify the installed content profile before every authoritative run.

### 4.3 Build and test tooling

- CMake 3.28 manual: <https://cmake.org/cmake/help/v3.28/>
- CMake presets: <https://cmake.org/cmake/help/v3.28/manual/cmake-presets.7.html>
- CTest 3.28: <https://cmake.org/cmake/help/v3.28/manual/ctest.1.html>
- CMake testing guide: <https://cmake.org/cmake/help/v3.28/guide/tutorial/Testing%20and%20CTest.html>
- Git submodules: <https://git-scm.com/docs/git-submodule>

Use features supported by the installed CMake 3.28 profile. Never write a preset requiring a newer schema version. CTest invocations MUST use machine-readable inventory output where available, JUnit output, `--output-on-failure`, explicit timeouts, and `--no-tests=error`.

### 4.4 Data representation and integrity

- JSON Schema Draft 2020-12: <https://json-schema.org/draft/2020-12>
- RFC 8785 JSON Canonicalization Scheme: <https://datatracker.ietf.org/doc/html/rfc8785>
- NIST FIPS 180-4 Secure Hash Standard: <https://csrc.nist.gov/pubs/fips/180-4/upd1/final>
- C17 committee draft N2176: <https://www.open-std.org/jtc1/sc22/wg14/www/docs/n2176.pdf>
- `SOURCE_DATE_EPOCH`: <https://reproducible-builds.org/docs/source-date-epoch/>
- SLSA provenance model: <https://slsa.dev/provenance/v1>

Manifest JSON MUST validate against committed Draft 2020-12 schemas. Hash-bearing JSON MUST use RFC 8785 canonical bytes. SHA-256 MUST use a vetted implementation or operating-system library. Never handwrite a new cryptographic primitive.

### 4.5 Dynamic analysis, fuzzing, and static analysis

- AddressSanitizer: <https://clang.llvm.org/docs/AddressSanitizer.html>
- UndefinedBehaviorSanitizer: <https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html>
- libFuzzer: <https://llvm.org/docs/LibFuzzer.html>
- SanitizerCoverage: <https://clang.llvm.org/docs/SanitizerCoverage.html>
- Clang-Tidy: <https://clang.llvm.org/extra/clang-tidy/>
- Clang Static Analyzer: <https://clang.llvm.org/docs/analyzer/user-docs/>
- ShellCheck: <https://github.com/koalaman/shellcheck>

Every new native parser, codec, comparator, minimizer, and manifest loader MUST run under ASan and UBSan. Every byte-oriented entry point MUST have a coverage-guided fuzz target. Every shell script MUST pass ShellCheck with no suppressed finding unless a source-commented waiver names the exact rule and proves safety.

### 4.6 Testing methodology references

- William M. McKeeman, “Differential Testing for Software,” 1998: <https://www.cs.tufts.edu/comp/150FP/archive/bill-mckeeman/DifferentailTesting.pdf>
- Andreas Zeller and Ralf Hildebrandt, “Simplifying and Isolating Failure-Inducing Input,” 2002: <https://doi.org/10.1109/32.988498>
- SQLite testing strategy: <https://sqlite.org/testing.html>
- SQLite quality-management plan: <https://sqlite.org/qmplan.html>

Use differential comparison against pinned OpenTTD, delta-debugging principles for reproducer minimization, independent test harnesses to reduce common-mode defects, and explicit evidence mapping between requirements and tests.

---

## 5. Requirement language

The words `MUST`, `MUST NOT`, `REQUIRED`, and `FORBIDDEN` define mandatory conditions. The word `MAY` defines an optional action. No optional action may weaken a mandatory condition.

Every deviation from a prescribed representation or directory requires all of the following records before implementation:

1. a numbered architecture decision record;
2. a concrete defect or incompatibility in the prescribed design;
3. a replacement design with narrower or equal ambiguity;
4. backward-compatibility consequences;
5. new tests proving equivalent or stronger guarantees;
6. approval recorded in repository history.

Convenience, personal preference, reduced coding effort, or speculative performance never justifies a deviation.

---

## 6. Repository and machine safety rules

### 6.1 Mandatory preflight

Before any edit, run and record:

```bash
pwd
git status --short --branch
git rev-parse HEAD
git remote -v
git submodule status --recursive
git -C openttd-upstream status --short --branch
git -C openttd-upstream rev-parse HEAD
cmake --version
ctest --version
ninja --version
gcc --version
g++ --version
clang --version || true
python3 --version
uname -a
cat /etc/os-release
nvidia-smi || true
nvcc --version || true
```

Redact credential-bearing output before any committed log. Never print environment variables wholesale.

### 6.2 Branch rules

- Create or continue one P0 branch, preferably `port/p0-oracle-contract`.
- Never work directly on `main`.
- Never force-push.
- Never rewrite user history.
- Never delete unrelated branches or tags.
- Never merge into `main` without explicit human direction.
- Push each valuable atomic milestone because `/workspace` lacks volume persistence.
- Preserve unrelated user changes.
- Stop an edit when an unrelated dirty file would be overwritten.

### 6.3 Submodule rules

- `openttd-upstream` MUST remain at commit `29f808ef0022064e6d9a83c8476d1e0f4686af86`.
- `openttd-upstream` MUST remain clean in the final branch.
- Instrumentation MUST exist as an ordered patch series outside the submodule.
- Apply patches only to a disposable Git worktree or disposable copy.
- Never commit a modified submodule pointer.
- Never use a floating branch for source behavior.
- Never cherry-pick current OpenTTD fixes into the oracle.
- Never normalize or reformat unrelated upstream code.

### 6.4 Credential rules

Never read, print, copy, hash, archive, commit, or expose:

- `/root/.ssh/id_ed25519`;
- `/root/.config/gh/hosts.yml`;
- GitHub tokens;
- cloud credentials;
- Hugging Face tokens;
- API keys;
- shell history;
- process environments containing secrets.

Secret scanning MUST run before every push. A positive finding blocks completion.

### 6.5 Host and dependency rules

- Never install or modify an NVIDIA driver.
- Never install the apt `cuda` metapackage.
- Never alter kernel modules.
- Never remove working system packages.
- Never use an unpinned third-party binary from a random release page.
- Never execute downloaded code before digest and provenance checks.
- Separate dependency acquisition from authoritative tests.
- Authoritative replay tests MUST run without network access after all approved materials are present.
- Record exact package names and versions from `dpkg-query`.
- Record dynamic library resolution from `ldd` or an equivalent tool.

### 6.6 Repository visibility and GPL boundary

The implementation agent MUST inspect repository visibility and record the result in `docs/decisions/0001-project-basis-and-publication.md`.

The implementation agent MUST NOT change repository visibility without explicit human authorization.

When the repository remains public, treat all source-derived instrumentation and later translation work as public `GPL-2.0-only` derivative work. Preserve upstream notices, include the applicable license text, maintain dependency and asset provenance, and avoid branding that implies official OpenTTD ownership or endorsement.

Never submit AI-generated code, issues, comments, or pull requests to upstream OpenTTD. Work only in the user-controlled repository.

---

## 7. Required repository layout

Create or converge on the following P0 layout. A different layout requires a recorded architecture decision and equivalent discoverability.

```text
.github/
  workflows/
    p0-oracle-contract.yml
cmake/
  P0Warnings.cmake
  P0Sanitizers.cmake
  P0Coverage.cmake
docs/
  decisions/
    0001-project-basis-and-publication.md
    0002-reference-build-profile.md
    0003-fixture-selection.md
    0004-tape-format-v1.md
    0005-field-schema-and-cache-policy.md
    0006-evidence-and-release-policy.md
  sources/
    P0_SOURCE_REGISTER.md
  scope/
    P0_SUPPORTED_SCOPE.md
    P0_FORBIDDEN_SCOPE.md
  testing/
    P0_TEST_STRATEGY.md
    P0_REQUIREMENTS_TRACEABILITY.md
    P0_MUTATION_PLAN.md
  P0_COMPLETION_REPORT.md
oracle/
  fixtures/
    road_freight_v1/
      fixture.sav
      fixture.manifest.json
      settings.normalized.json
      command_input.bin
      README.md
  instrumentation/
    series
    0001-trace-sink-and-codec.patch
    0002-build-and-run-identity.patch
    0003-command-boundary-records.patch
    0004-global-time-rng-map-projection.patch
    0005-pool-and-entity-projection.patch
    0006-route-cargo-diagnostics.patch
    0007-nonperturbation-self-checks.patch
  manifests/
    schema/
      source.schema.json
      toolchain.schema.json
      dependency.schema.json
      build.schema.json
      test-inventory.schema.json
      fixture.schema.json
      evidence.schema.json
      gate-result.schema.json
    baseline/
      openttd-source.json
      toolchain-linux-x86_64.json
      dependencies-ubuntu-24.04.json
      build-relwithdebinfo.json
      tests-relwithdebinfo.json
      opengfx-8.0.json
  runner/
    common.sh
    preflight.sh
    fetch_opengfx.sh
    configure_reference.sh
    build_reference.sh
    test_reference.sh
    smoke_reference.sh
    create_instrumented_worktree.sh
    apply_instrumentation.sh
    record_oracle.sh
    compare_nonperturbation.sh
    p0_gate.sh
parity/
  include/openttd_rl_parity/
    status.h
    tape_format.h
    tape_reader.h
    tape_writer.h
    field_schema.h
    comparator.h
    minimizer.h
  src/
    status.c
    checked_arithmetic.c
    sha256_adapter.c
    canonical_json_adapter.c
    tape_reader.c
    tape_writer.c
    field_schema.c
    comparator.c
    minimizer.c
  tools/
    tape_main.c
    schema_main.c
    fault_inject_main.c
  schema/
    tape-header.schema.json
    field-schema.schema.json
    command-set.schema.json
    fields-v1.json
    commands-v1.json
  tape/
    golden/
      README.md
      minimal-valid.tape
      minimal-valid.hex
      malformed/
  python_reference/
    tape_reference.py
    schema_reference.py
  tests/
    unit/
    golden/
    negative/
    property/
    differential/
    integration/
    fuzz/
    mutation/
    fixtures/
scripts/
  ci/
    p0_format.sh
    p0_static.sh
    p0_sanitizers.sh
    p0_fuzz_smoke.sh
    p0_coverage.sh
    p0_mutation.sh
    p0_evidence.sh
  dev/
    inspect_artifact.sh
evidence/
  p0/
    README.md
LICENSES/
  GPL-2.0-only.txt
CMakeLists.txt
CMakePresets.json
```

Generated build trees, installed binaries, temporary worktrees, raw fuzz corpora, and large run artifacts MUST remain outside tracked source directories. Small approved golden vectors, schemas, manifests, minimized regression cases, and compact evidence summaries MUST remain tracked.

---

## 8. Global coding limitations

### 8.1 Language boundaries

- New parity codec, parser, comparator, and minimizer core code MUST use ISO C17.
- OpenTTD instrumentation glue MUST use the pinned project’s C++ standard and coding conventions.
- Python MAY provide an independent test decoder only.
- Python MUST NOT become the production tape authority.
- Shell scripts MUST target Bash on Ubuntu 24.04 and begin with strict failure handling.
- No Rust, Go, Java, JavaScript, TypeScript, database server, web service, or RPC layer belongs in P0.

### 8.2 C17 rules

New C17 code MUST satisfy all rules below:

- fixed-width integer types for binary and authoritative values;
- explicit bounds for every count, length, index, and allocation;
- checked addition, subtraction, multiplication, alignment, and conversion before use;
- no variable-length arrays;
- no implicit integer narrowing;
- no unchecked signed/unsigned conversion;
- no pointer arithmetic outside a proven object range;
- no unaligned typed loads from tape bytes;
- no type-punning through incompatible pointer types;
- no raw struct serialization;
- no dependence on struct padding;
- no dependence on host endianness;
- no dependence on `sizeof(long)`, `sizeof(size_t)`, or pointer width in the file format;
- no floating point in tape framing, identity, counters, command fields, or projection fields unless pinned source evidence requires exact floating-point bits;
- no global mutable parser state;
- no hidden singleton;
- no process-global error buffer;
- no `assert` as the sole validation for untrusted input;
- no unchecked `malloc`, `calloc`, `realloc`, `fread`, `fwrite`, `fseek`, `ftell`, `snprintf`, or system-call result;
- no allocation size derived from input before a configured upper-bound check;
- no silent truncation;
- no silent saturation;
- no silent integer wrap;
- no undefined shift count;
- no fallthrough without an explicit annotation;
- no unreachable default that converts malformed input into success;
- no locale-sensitive parsing;
- no wall-clock dependency in deterministic identity;
- no cryptographic algorithm implemented from memory or generated ad hoc.

### 8.3 C++ instrumentation rules

Instrumentation code MUST satisfy all rules below:

- no direct mutation of gameplay state except native command submission through the same command machinery used by normal gameplay;
- no call to RNG merely for logging;
- no call to pathfinding merely for logging;
- no call to a lazy getter when the getter can create or update a cache;
- no pointer address in output;
- no C++ object-memory dump;
- no RTTI name in authoritative output;
- no unordered-container iteration in output;
- no wall-clock timestamp in authoritative records;
- no locale-sensitive formatted number in authoritative records;
- no string name as a substitute for stable numeric field ID;
- no renderer dependency;
- no GUI event injection;
- no networking dependency;
- no NewGRF callback;
- no modification of native command semantics;
- no changed tick order;
- no changed pool allocation order;
- no changed save/load order;
- no extra simulation tick;
- no extra command test execution;
- no hidden retry after command rejection;
- no exception escape across the trace sink boundary;
- no trace write failure converted into a successful authoritative run.

### 8.4 Shell rules

Every Bash script MUST use:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 022
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export TZ=UTC
```

Shell code MUST NOT use `eval`, unquoted expansions, predictable temporary paths, `curl | sh`, `wget | sh`, broad `rm -rf` paths, glob-dependent deletion, implicit current-directory assumptions, or credential-bearing debug traces.

Every destructive command MUST prove the target path lies under a dedicated generated-artifact root. Use `mktemp -d`, traps, and explicit path-prefix checks.

### 8.5 Build rules

- Use out-of-tree build directories.
- Keep reference, trace-disabled, trace-enabled, ASan, UBSan, coverage, and fuzz builds separate.
- Never reuse a CMake cache across incompatible profiles.
- Record every CMake cache variable affecting behavior.
- Record compiler path, compiler version, linker path, linker version, generator, build type, definitions, feature detection, and dependency versions.
- Treat zero discovered tests as an error.
- Treat warnings in new P0 code as errors.
- Never impose new warning failures across untouched upstream code.
- Never disable upstream assertions for the frozen baseline.
- Never use `-ffast-math`.
- Never use architecture-specific optimization flags in parity evidence.
- Never use link-time optimization in the baseline unless the baseline decision record explicitly freezes and tests the choice.
- Use deterministic archives when the toolchain supports them.
- Record `SOURCE_DATE_EPOCH` from the pinned source commit timestamp for reproducibility experiments.

### 8.6 Test-code rules

- A test MUST assert exact expected behavior rather than “no crash” alone, except dedicated fuzz or sanitizer tests.
- A golden value MUST come from a hand-reviewed specification, pinned oracle observation, or independent implementation.
- Production code MUST NOT generate its own expected golden values during the same test.
- A test MUST fail before the associated defect fix when regression history exists.
- A test MUST name one primary behavior.
- A test MUST use deterministic inputs.
- Randomized tests MUST print and store the replay seed.
- A failed randomized case MUST become a minimized tracked regression case.
- No test may sleep for correctness.
- No test may depend on test execution order.
- No test may depend on network access.
- No test may accept several unrelated error codes.
- No test may compare only a final hash when field-level equality is available.
- No flaky retry may convert a failure into `PASS`.
- `ctest --repeat until-fail` exposes flakiness; the command never excuses flakiness.
- Test skips require an explicit reason and profile. A mandatory P0 gate cannot pass through a skip.
- Every fixed bug requires a regression test and a short entry in the divergence or defect ledger.

---

## 9. Canonical identity and manifest contract

### 9.1 Manifest format

Every manifest MUST:

- use UTF-8 without a byte-order mark;
- validate against a committed JSON Schema Draft 2020-12 schema;
- reject duplicate object keys;
- use integers rather than decimal strings for bounded counters unless a schema explicitly requires a hexadecimal digest string;
- use lowercase hexadecimal SHA-256 strings of exactly 64 characters;
- use RFC 8785 canonical bytes for identity hashes;
- omit host-specific absolute paths from authoritative identity;
- place diagnostic paths under a separate nonauthoritative object;
- record schema version and schema SHA-256;
- record material inputs and produced outputs;
- record the exact command argument array rather than one shell string;
- record an allowlisted environment rather than the complete process environment;
- record status as `PASS`, `FAIL`, or `SKIP`;
- reject unknown required properties and malformed optional properties;
- use an explicit `additionalProperties` policy.

### 9.2 Required identity materials

At minimum, canonical identity MUST cover:

- outer repository commit;
- submodule commit;
- submodule clean-state assertion;
- instrumentation patch-series SHA-256;
- compiler and linker identity;
- CMake and Ninja identity;
- complete behavior-affecting CMake options;
- dependency package versions;
- executable SHA-256;
- base content name, version, and file SHA-256 values;
- fixture save SHA-256;
- normalized settings SHA-256;
- command-input SHA-256;
- command-set schema SHA-256;
- field-schema SHA-256;
- tape-format major and minor version;
- initial tick, date, economy timer state, calendar timer state, and both RNG states;
- platform profile name.

### 9.3 Identity exclusions

The following values MUST NOT influence authoritative identity:

- workspace absolute path;
- username;
- hostname;
- PID;
- wall-clock start time;
- wall-clock duration;
- terminal type;
- console width;
- temporary-directory name;
- GitHub token identity;
- SSH key path;
- GPU serial number;
- nondeterministic file-system inode;
- directory enumeration order.

Diagnostic metadata MAY record safe values above when no secret or privacy risk exists, but diagnostics must remain outside the canonical experiment identity object.

### 9.4 Provenance output

Create a machine-readable evidence statement inspired by SLSA provenance. Record:

- materials;
- invocation parameters;
- builder profile;
- command arrays;
- allowlisted environment;
- outputs and digests;
- start and finish timestamps as diagnostics;
- success or failure;
- source and schema identities.

Never claim a formal SLSA level unless the actual builder and provenance chain meet every requirement for that level.


---

## 10. Gate 0 — preflight, authority, and branch initialization

Gate 0 exists before `PORT-001`. Gate 0 prevents source drift, secret exposure, unreviewed publication changes, and work on an unsafe tree.

### 10.1 Required actions

1. Read `/workspace/AGENTS.md` when present; otherwise read `/etc/vast-agents-guide.md`.
2. Read `NEXT_STAGES_IMPLEMENTATION_HANDOFF.md` completely.
3. Read `OpenTTD_CUDA_RL_REVERSE_ENGINEERING_REPORT.md` completely.
4. Read `research-notes/09-verification-audit.md` completely.
5. Read every research note named by the handoff for build, gameplay, legal, persistence, and verification.
6. Inspect outer repository status, current branch, remote, and commit.
7. Inspect submodule status, exact commit, and cleanliness.
8. Inspect repository visibility without changing visibility.
9. Inspect tracked and ignored files for credentials or generated artifacts.
10. Create the P0 branch when no suitable branch exists.
11. Create `docs/decisions/0001-project-basis-and-publication.md`.
12. Create `docs/scope/P0_SUPPORTED_SCOPE.md` and `docs/scope/P0_FORBIDDEN_SCOPE.md`.
13. Create the initial requirements-traceability matrix.
14. Record all preflight outputs under a generated evidence directory with credential-safe redaction.
15. Commit and push the preflight documentation before source-derived instrumentation begins.

### 10.2 Gate 0 pass conditions

Gate 0 reports `PASS` only when:

- outer repository identity is known;
- submodule commit equals the required 40-hex identifier;
- submodule tree is clean;
- no credential appears in tracked files or staged content;
- repository visibility is documented;
- GPL treatment is documented;
- upstream AI-contribution prohibition is documented;
- branch safety rules are active;
- P0 scope and forbidden scope are explicit;
- no later-phase implementation exists in staged P0 changes.

### 10.3 Gate 0 hard failures

The following conditions force a nonzero exit:

- missing pinned submodule;
- wrong submodule commit;
- dirty submodule with unexplained changes;
- unknown remote;
- uncommitted unrelated user work at risk of overwrite;
- credential found in tracked, staged, or planned evidence files;
- attempt to change repository visibility without authorization;
- attempt to work directly on `main`;
- attempt to submit work upstream;
- attempt to install a host driver or CUDA metapackage;
- attempt to begin scalar or CUDA implementation.

---

## 11. `PORT-001` — reproducible reference pinning

### 11.1 Objective

Create a clean-checkout reproducibility layer that reconstructs the exact reference profile, verifies every material input, enumerates the exact 99-test suite, runs every test, installs the reference, and executes the approved headless smoke workload.

A surviving `/workspace/openttd-build` directory never proves reproducibility. Only committed scripts, schemas, manifests, and replayable evidence prove `PORT-001`.

### 11.2 Required decision record

Create `docs/decisions/0002-reference-build-profile.md` with:

- source commit;
- supported host profile;
- compiler and linker choice;
- CMake generator;
- build type;
- assertion policy;
- dedicated-build policy;
- FHS install policy;
- feature-library policy;
- base-content policy;
- network-acquisition boundary;
- environment allowlist;
- reproducibility caveats;
- exact gate commands;
- expected 99-test inventory statement;
- explanation for the stale 98-test report count;
- profile-change process.

### 11.3 Required scripts

#### `oracle/runner/common.sh`

Provide shared functions for:

- repository-root discovery based on script location;
- generated-root path validation;
- command availability checks;
- safe SHA-256 calculation;
- canonical JSON validation;
- exact commit validation;
- submodule clean-state validation;
- safe temporary directories;
- structured logging;
- machine-readable result emission;
- redaction of paths or values marked sensitive;
- trap-based failure recording;
- deterministic environment setup.

Never duplicate critical hash, path-safety, or error-reporting logic across scripts.

#### `oracle/runner/preflight.sh`

Verify:

- repository root;
- Git worktree;
- expected remote identity;
- branch not equal to `main` for edit mode;
- pinned submodule commit;
- clean submodule;
- required tools and minimum versions;
- OpenGFX presence or approved acquisition need;
- available disk space above a documented floor;
- writable artifact root;
- absence of credential files under artifact roots;
- locale and timezone normalization.

Support a read-only mode for CI and a stricter edit mode for local development.

#### `oracle/runner/fetch_opengfx.sh`

The acquisition script MUST:

- accept an explicit destination;
- fetch only over HTTPS;
- follow redirects with a finite redirect limit;
- fail on HTTP errors;
- use finite connection and transfer timeouts;
- use bounded retries for transient transport failures;
- write to a temporary file;
- calculate SHA-256 before extraction;
- compare against the frozen digest;
- reject mismatched bytes;
- inspect archive paths for absolute paths and parent traversal;
- extract into a temporary directory;
- move verified output atomically into the content root;
- record archive and installed-file digests;
- never overwrite a differing existing file silently;
- never commit the downloaded asset automatically.

#### `oracle/runner/configure_reference.sh`

The configuration script MUST:

- accept explicit source, build, install, and artifact roots;
- reject source paths outside the expected pinned submodule unless a test fixture deliberately overrides the source;
- reject a dirty source tree;
- delete no path outside the dedicated build root;
- create a fresh CMake cache for the profile;
- invoke CMake through an argument array;
- record complete stdout, stderr, command arguments, environment allowlist, cache variables, detected dependencies, and return code;
- emit a canonical build manifest;
- fail when a required feature or content profile differs;
- fail when the source commit differs;
- fail when assertions or required build options differ.

Baseline configuration:

```bash
cmake -S "$SOURCE_ROOT" \
  -B "$BUILD_ROOT" \
  -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_INSTALL_PREFIX="$INSTALL_ROOT" \
  -DOPTION_DEDICATED=OFF
```

Any additional cache variable affecting behavior MUST appear explicitly in the manifest. Never rely on an old cache default.

#### `oracle/runner/build_reference.sh`

The build script MUST:

- require a valid configuration manifest;
- run Ninja with a configurable bounded parallelism value;
- record the actual parallelism;
- record build command, logs, result, binary path, binary size, and SHA-256;
- inspect dynamic dependencies;
- verify no unresolved shared library;
- never hide a failed build behind a stale executable;
- verify executable modification occurs during the current build or verify a content-addressed cache entry with provenance.

#### `oracle/runner/test_reference.sh`

The test script MUST:

1. run `ctest -N --show-only=json-v1`;
2. store the complete JSON inventory;
3. normalize and hash the inventory;
4. require exactly 99 tests for the frozen profile;
5. compare names and properties against the committed baseline inventory;
6. run all tests with `--output-on-failure` and `--no-tests=error`;
7. emit JUnit XML;
8. emit a plain log;
9. record start, finish, duration diagnostics, return code, passed count, failed count, skipped count, and test names;
10. fail for any failure, unexpected skip, timeout, missing test, extra test, or inventory drift.

The release gate MUST also run the new P0 harness tests under randomized scheduling and repeated-until-fail modes. Do not randomize upstream tests when upstream fixtures or resource constraints make random scheduling invalid; document any boundary precisely.

#### `oracle/runner/smoke_reference.sh`

Run the exact headless profile:

```bash
openttd -g -v null:ticks=128 -s null -m null -b null -I OpenGFX -Q -x
```

Record:

- executable SHA-256;
- command array;
- content profile;
- return code;
- stdout and stderr;
- wall duration as diagnostics;
- detected OpenTTD version;
- available video, sound, music, and blitter drivers;
- installed OpenGFX identity.

Never treat a smoke pass as a substitute for the 99-test suite.

### 11.4 Required manifests

Create and validate:

- `oracle/manifests/baseline/openttd-source.json`;
- `oracle/manifests/baseline/toolchain-linux-x86_64.json`;
- `oracle/manifests/baseline/dependencies-ubuntu-24.04.json`;
- `oracle/manifests/baseline/build-relwithdebinfo.json`;
- `oracle/manifests/baseline/tests-relwithdebinfo.json`;
- `oracle/manifests/baseline/opengfx-8.0.json`.

Each baseline manifest MUST have a matching schema and at least one positive and one negative validation test.

### 11.5 Dependency inventory

Record at minimum:

- OS release and architecture;
- GCC and G++ paths and versions;
- linker path and version;
- CMake path and version;
- CTest path and version;
- Ninja path and version;
- Git path and version;
- Python path and version used by test tooling;
- SDL2;
- libcurl;
- zlib;
- liblzma;
- LZO;
- libpng;
- Freetype;
- Fontconfig;
- Harfbuzz;
- ICU;
- Ogg;
- Opus;
- OpusFile;
- FluidSynth;
- OpenGL-related packages;
- any new OpenSSL or JSON-schema validator dependency;
- package source and exact installed version.

No dependency may appear only as a free-form prose note.

### 11.6 Reproducibility policy

Two clean builds from separate build and install directories MUST produce:

- equal source identity;
- equal configuration identity;
- equal test inventory;
- equal test results;
- equal runtime version output;
- equal OpenGFX identity;
- equal headless smoke behavior.

Binary byte identity is a research measurement rather than a mandatory P0 claim when compiler or linker metadata prevents equality. Record binary digests from both builds. Any difference requires an explanation based on diffoscope or equivalent binary inspection. Never call a build reproducible when only functional outputs match. Use “behaviorally reproduced under the frozen profile” unless byte identity has been proven.

### 11.7 `PORT-001` exit gate

`PORT-001` reports `PASS` only when:

- all baseline schemas validate;
- source and submodule pins fail closed under deliberate mutation;
- OpenGFX digest mutation fails closed;
- CMake option mutation fails closed;
- toolchain version mutation fails closed;
- exact 99-test inventory is committed and verified;
- all 99 tests pass;
- headless smoke passes;
- two clean build roots reproduce the required behavior;
- raw logs and machine-readable results exist;
- no generated build product is tracked accidentally;
- a clean checkout can run the documented commands.

---

## 12. `PORT-001` mandatory tests

The tests below form a minimum set. Add more tests whenever implementation structure creates another reachable failure mode.

### 12.1 Repository and pin tests

| ID | Test | Required result |
|---|---|---|
| `P001-REP-001` | Correct outer repository and submodule | `PASS` |
| `P001-REP-002` | Wrong submodule commit | hard failure naming expected and actual commit |
| `P001-REP-003` | Dirty submodule | hard failure listing changed paths without file contents |
| `P001-REP-004` | Missing submodule | hard failure with recovery command |
| `P001-REP-005` | Modified submodule URL | hard failure |
| `P001-REP-006` | Edit mode on `main` | hard failure |
| `P001-REP-007` | Read-only CI mode on detached commit | allowed only when commit identity matches |
| `P001-REP-008` | Credential-like staged content | hard failure |
| `P001-REP-009` | Generated build tree staged | hard failure |
| `P001-REP-010` | Absolute workspace path inside canonical identity | schema or semantic-validation failure |

### 12.2 Manifest tests

| ID | Test | Required result |
|---|---|---|
| `P001-MAN-001` | Minimal valid source manifest | valid |
| `P001-MAN-002` | Missing required commit | invalid |
| `P001-MAN-003` | Short digest | invalid |
| `P001-MAN-004` | Uppercase digest | invalid unless schema deliberately normalizes before validation; canonical stored form remains lowercase |
| `P001-MAN-005` | Unknown required property | invalid |
| `P001-MAN-006` | Duplicate JSON key | invalid |
| `P001-MAN-007` | Non-UTF-8 bytes | invalid |
| `P001-MAN-008` | UTF-8 byte-order mark | invalid |
| `P001-MAN-009` | Negative test count | invalid |
| `P001-MAN-010` | Floating-point test count | invalid |
| `P001-MAN-011` | Canonicalization across property order | equal canonical bytes and equal digest |
| `P001-MAN-012` | Canonicalization across insignificant whitespace | equal canonical bytes and equal digest |
| `P001-MAN-013` | Changed authoritative value | changed digest |
| `P001-MAN-014` | Changed diagnostic path | unchanged experiment identity digest |
| `P001-MAN-015` | Secret-named environment entry | rejected by allowlist |

### 12.3 OpenGFX tests

| ID | Test | Required result |
|---|---|---|
| `P001-GFX-001` | Approved archive bytes | accepted |
| `P001-GFX-002` | One-bit archive mutation | rejected before extraction |
| `P001-GFX-003` | Wrong filename with correct bytes | accepted only through digest and explicit destination policy |
| `P001-GFX-004` | Correct filename with wrong bytes | rejected |
| `P001-GFX-005` | Archive with `../` path | rejected |
| `P001-GFX-006` | Archive with absolute path | rejected |
| `P001-GFX-007` | Existing differing destination | rejected without overwrite |
| `P001-GFX-008` | Interrupted download | partial file never promoted |
| `P001-GFX-009` | Network unavailable after verified install | authoritative tests continue without network |
| `P001-GFX-010` | Installed content drift | preflight failure |

### 12.4 Build and test inventory tests

| ID | Test | Required result |
|---|---|---|
| `P001-BLD-001` | Fresh reference configure | success |
| `P001-BLD-002` | Reuse incompatible cache | rejected or isolated by profile |
| `P001-BLD-003` | Wrong build type | failure |
| `P001-BLD-004` | Assertions disabled | failure |
| `P001-BLD-005` | Dedicated-only build | failure |
| `P001-BLD-006` | Wrong generator | failure unless decision record changes profile |
| `P001-BLD-007` | Missing required dependency | clear configuration failure |
| `P001-BLD-008` | Stale executable after failed build | never accepted |
| `P001-BLD-009` | Unresolved shared library | failure |
| `P001-BLD-010` | Executable digest omitted | failure |
| `P001-TST-001` | Exact 99-test inventory | success |
| `P001-TST-002` | Inventory with 98 tests | failure |
| `P001-TST-003` | Inventory with 100 tests | failure |
| `P001-TST-004` | Renamed test | failure |
| `P001-TST-005` | Zero discovered tests | failure through `--no-tests=error` |
| `P001-TST-006` | One upstream test failure | nonzero gate result with JUnit and log path |
| `P001-TST-007` | One unexpected skip | failure |
| `P001-TST-008` | One timeout | failure |
| `P001-TST-009` | JUnit path unwritable | failure |
| `P001-TST-010` | Inventory JSON malformed | failure |

### 12.5 Smoke tests

| ID | Test | Required result |
|---|---|---|
| `P001-SMK-001` | Exact null-backend 128-tick command | success |
| `P001-SMK-002` | Missing OpenGFX | failure naming content problem |
| `P001-SMK-003` | Wrong executable digest | failure before run |
| `P001-SMK-004` | Nonzero OpenTTD exit | failure with retained logs |
| `P001-SMK-005` | Unexpected graphical backend | failure |
| `P001-SMK-006` | Version output differs | failure |

---

## 13. `PORT-002` — frozen 64×64 road-freight fixture

### 13.1 Objective

Freeze one minimal scenario that reaches construction, vehicle creation, orders, movement, production, station capture, loading, delivery, acceptance, and payment without unrelated OpenTTD breadth.

The fixture must make later parity failures diagnosable. The fixture must not maximize gameplay variety.

### 13.2 Fixture selection process

Create `docs/decisions/0003-fixture-selection.md` before final save creation. The decision record MUST include:

- climate;
- exact start date and year;
- exact map dimensions;
- exact terrain and map source;
- exact company identifier, name policy, and opening balance;
- exact producer industry type, pool ID, and tile footprint;
- exact accepting industry type, pool ID, and tile footprint;
- exact cargo type and compatibility evidence;
- exact road vehicle engine identifier and availability evidence;
- exact road path coordinates;
- exact pickup-stop coordinates;
- exact delivery-stop coordinates;
- exact depot coordinate and orientation;
- exact vehicle spawn route;
- exact two-stop order sequence;
- exact station catchment proof;
- exact command schedule boundary;
- exact initial tick, date counters, timer counters, and both RNG states;
- exact settings affecting reached behavior;
- exact content profile;
- proof of no NewGRFs;
- proof of no AI company;
- proof of no network game;
- proof that all coordinates lie in bounds;
- proof that no bridge, tunnel, rail crossing, water crossing, one-way road, tram, articulated vehicle, or slope branch appears unless explicitly required;
- proof that sufficient funds cover every command plus a safety margin;
- proof that the selected route reaches accepted cargo delivery;
- reasons for every simplification.

Prefer a temperate coal mine to power station route with a compatible coal road vehicle only after pinned-source and executable verification. Select another pair when source evidence exposes a narrower or more deterministic candidate. Any alternate choice requires explicit rationale.

### 13.3 Required settings policy

Freeze every setting that can influence the reached loop. At minimum, inspect and record settings governing:

- map size;
- climate;
- start year and date;
- economy mode;
- inflation;
- industry production changes;
- cargo distribution;
- vehicle availability;
- vehicle breakdowns;
- road vehicle acceleration model;
- servicing;
- station spread;
- station catchment;
- construction costs;
- maintenance costs;
- loan and interest;
- disasters;
- competitors;
- town growth when a town can affect the route;
- industry closure;
- autosave;
- pause behavior;
- calendar and economy timekeeping;
- NewGRF loading;
- GameScript;
- AI scripts;
- networking;
- language and naming only when a recorded string could enter authoritative output.

Disable unrelated stochastic or breadth-producing behavior when the pinned source exposes a valid setting. Record every disabled feature and source-defined default. Never assume a GUI setting label maps directly to one internal field.

### 13.4 Fixture construction limitations

- Do not use random map generation as an implicit release input.
- A generated map MAY seed fixture creation only when the seed, generator settings, generator version, output save bytes, and final map planes are frozen.
- Do not rely on manual cursor placement without recording exact final coordinates.
- Do not include prebuilt road, stops, depot, vehicle, or orders unless the decision record proves a necessity.
- Prefer a save containing only world, company, producer, acceptor, and frozen state; leave network and service construction to the command input.
- Do not include personal names or personal data.
- Do not include downloaded NewGRFs.
- Do not use cheat state unless a declared company-balance fixture operation requires one; a direct fixture creation operation must not remain reachable during replay.
- Do not use a scenario editor mutation after the final fixture hash is frozen.
- Do not permit autosave or user configuration directories to alter the fixture.
- Run with an isolated OpenTTD home/config directory.

### 13.5 Fixture manifest

`fixture.manifest.json` MUST include:

- fixture ID `road_freight_v1`;
- fixture schema version;
- fixture save relative path and SHA-256;
- file size;
- OpenTTD commit;
- OpenTTD executable SHA-256 used for creation;
- creation method and command log;
- map width and height;
- climate;
- date and tick boundary;
- timer state;
- RNG state;
- content profile and digests;
- normalized settings and digest;
- NewGRF empty-list assertion;
- company data;
- industry data;
- cargo data;
- vehicle-engine data;
- coordinate plan;
- expected command count;
- expected first pickup boundary;
- expected first delivery boundary;
- expected first payment boundary;
- source evidence references;
- known unreachable subsystems;
- review status.

### 13.6 Normalized settings

Create a deterministic settings exporter. The exporter MUST:

- enumerate all behavior-affecting settings rather than only nondefault values;
- use stable setting identifiers;
- encode exact integer, boolean, enumeration, and string values;
- sort by stable identifier;
- exclude comments, GUI layout, recent-file history, and user paths;
- reject duplicate setting identifiers;
- include source commit and settings-schema identity;
- produce canonical JSON;
- prove repeated export equality.

### 13.7 Two-stage closure rule

`PORT-002A` freezes save bytes, settings, content, and coordinate decisions. `PORT-002B` closes only after the minimal `PORT-003` projection records two independent loads with equal initial authoritative state, equal timers, and equal RNG state.

Never claim full `PORT-002` completion before `PORT-002B` passes.

### 13.8 `PORT-002` exit gate

`PORT-002` reports `PASS` only when:

- fixture ADR is complete;
- fixture save is immutable and hashed;
- normalized settings are complete and hashed;
- OpenGFX and no-NewGRF assertions pass;
- exact company, industry, cargo, vehicle, and coordinate data are recorded;
- command plan is solvable;
- every planned command lies within supported scope;
- two independent loads yield equal initial projection, timers, and RNG state;
- the fixture reaches pickup, delivery, acceptance, and payment under the native oracle command script;
- no hidden user configuration changes behavior;
- all fixture tests pass.

---

## 14. `PORT-002` mandatory tests

### 14.1 Fixture structure tests

| ID | Test | Required result |
|---|---|---|
| `P002-FIX-001` | Width equals 64 | pass |
| `P002-FIX-002` | Height equals 64 | pass |
| `P002-FIX-003` | Any other dimension | failure |
| `P002-FIX-004` | NewGRF list empty | pass |
| `P002-FIX-005` | One NewGRF present | failure |
| `P002-FIX-006` | Exactly one human company | pass |
| `P002-FIX-007` | AI company present | failure |
| `P002-FIX-008` | Producer present at declared ID and tiles | pass |
| `P002-FIX-009` | Acceptor present at declared ID and tiles | pass |
| `P002-FIX-010` | Cargo incompatibility | failure |
| `P002-FIX-011` | Vehicle unavailable at start date | failure |
| `P002-FIX-012` | Insufficient opening funds | failure |
| `P002-FIX-013` | Coordinate outside map | failure |
| `P002-FIX-014` | Road plan intersects forbidden tile branch | failure |
| `P002-FIX-015` | Stop outside producer catchment | failure |
| `P002-FIX-016` | Stop outside acceptor catchment | failure |
| `P002-FIX-017` | Depot inaccessible from road | failure |
| `P002-FIX-018` | Route disconnected | failure |
| `P002-FIX-019` | Duplicate planned object coordinate | failure unless native command semantics intentionally test rejection |
| `P002-FIX-020` | Personal data string present | failure |

### 14.2 Settings tests

| ID | Test | Required result |
|---|---|---|
| `P002-SET-001` | Repeated normalized export | byte-identical |
| `P002-SET-002` | Setting order shuffled before canonicalization | equal canonical bytes |
| `P002-SET-003` | Behavior-affecting setting changed | changed identity and preflight failure |
| `P002-SET-004` | GUI-only setting changed | no authoritative identity change only when classification proves irrelevance |
| `P002-SET-005` | Duplicate setting key | failure |
| `P002-SET-006` | Unknown required setting | failure |
| `P002-SET-007` | Missing required setting | failure |
| `P002-SET-008` | User config overrides frozen setting | failure before replay |
| `P002-SET-009` | Locale changes | equal normalized settings and state |
| `P002-SET-010` | Timezone changes | equal normalized settings and state |

### 14.3 Load and reachability tests

| ID | Test | Required result |
|---|---|---|
| `P002-LOD-001` | First isolated load | success |
| `P002-LOD-002` | Second isolated load | same initial projection |
| `P002-LOD-003` | Save one-bit mutation | load or digest failure before authoritative replay |
| `P002-LOD-004` | Wrong content profile | identity failure |
| `P002-LOD-005` | Command script constructs full route | success |
| `P002-LOD-006` | Vehicle purchase | success with expected cost |
| `P002-LOD-007` | Two-stop orders | success with expected order state |
| `P002-LOD-008` | Vehicle start | success |
| `P002-LOD-009` | First cargo capture | reached within declared bound |
| `P002-LOD-010` | First loading | reached within declared bound |
| `P002-LOD-011` | First accepted delivery | reached within declared bound |
| `P002-LOD-012` | First payment | exact native ledger event observed |
| `P002-LOD-013` | Replay from second load | same milestone boundaries and projections |
| `P002-LOD-014` | Isolated home directory | no undeclared config or content read |


---

## 15. `PORT-003` — non-perturbing native oracle instrumentation

### 15.1 Objective

Instrument the pinned OpenTTD reference so one versioned command-input stream can enter through native command machinery and one deterministic tape can capture command intent, command test result, command execute result, complete authoritative state, timers, RNG, pools, reached caches, and diagnostic traces at declared safe boundaries.

The instrumentation must expose behavior without changing behavior.

### 15.2 Patch-series discipline

Create `oracle/instrumentation/series` with one patch filename per line in application order. Every patch MUST:

- apply cleanly to the pinned commit;
- contain one coherent concern;
- compile independently when all earlier patches are applied;
- include tests or enable tests in the same patch when practical;
- avoid unrelated formatting;
- include a clear commit-style subject and body;
- name source anchors and boundary rationale;
- preserve upstream style;
- avoid generated bulk changes.

Recommended patch concerns:

1. `0001-trace-sink-and-codec.patch` — compile-time option, sink interface, primitive writers, strict error path;
2. `0002-build-and-run-identity.patch` — header identity and fixture identity;
3. `0003-command-boundary-records.patch` — command input, test, execute, result, and post-command projection;
4. `0004-global-time-rng-map-projection.patch` — global state, clocks, timers, RNG streams, settings, and all 4,096 map tiles;
5. `0005-pool-and-entity-projection.patch` — companies, industries, stations, road stops, vehicles, orders, cargo packets, pool occupancy, free lists, IDs, and references;
6. `0006-route-cargo-diagnostics.patch` — optional route/controller and cargo diagnostics with default-off flags;
7. `0007-nonperturbation-self-checks.patch` — test-only hooks and trace consistency assertions.

A different split is allowed only when each patch remains narrow and independently reviewable.

### 15.3 Build variants

Produce three reference variants from the same source commit and equivalent gameplay options:

1. `reference-plain` — no instrumentation patches;
2. `reference-instrumented-off` — patches applied, tracing compiled, tracing disabled at runtime;
3. `reference-instrumented-on` — same instrumented executable, tracing enabled at runtime.

Record exact configuration differences. The only allowed gameplay-affecting difference is none.

Never compare a debug build against a release build and call the comparison a non-perturbation proof. Use equivalent build types, assertions, dependencies, settings, content, fixture, command input, and environment.

### 15.4 Command-input contract

Create a separate versioned binary command-input format. The command-input stream MUST contain only exogenous actions and timing instructions. The stream MUST NOT contain expected results or projected state.

Required command-input header fields:

- magic and format version;
- little-endian marker;
- OpenTTD commit;
- fixture identity digest;
- command-set identity digest;
- settings identity digest;
- content identity digest;
- initial boundary identity;
- record count;
- complete-stream SHA-256;
- reserved-zero fields.

Required action-record fields:

- monotonically increasing action sequence;
- scheduled public step;
- scheduled native tick boundary;
- native command identifier;
- company context;
- command flags;
- raw operands with exact widths;
- optional stable object IDs needed by later actions;
- no pointer;
- no string-form command lookup;
- no direct target-state bytes.

The command driver MUST parse and validate the complete command-input file before advancing gameplay. A malformed command-input file must fail before any command or tick mutates state.

### 15.4.1 Command-input v1 baseline binary layout

Use a fully specified framing rather than an ad hoc script parser. All integers use little-endian encoding.

#### File prefix — 64 bytes

| Offset | Size | Field | Rule |
|---:|---:|---|---|
| 0 | 8 | magic | ASCII `OTRLCMD\0` |
| 8 | 2 | format major | `1` |
| 10 | 2 | format minor | `0` initially |
| 12 | 1 | byte-order code | `1` |
| 13 | 1 | hash code | `1` for SHA-256 |
| 14 | 2 | prefix bytes | `64` |
| 16 | 4 | canonical header bytes | maximum 1 MiB |
| 20 | 4 | flags | only defined bits allowed |
| 24 | 8 | action count | maximum 1 million |
| 32 | 8 | action-region bytes | exact padded byte count |
| 40 | 8 | maximum scheduled public step | exact |
| 48 | 8 | maximum scheduled native tick | exact |
| 56 | 8 | reserved | zero |

The canonical header MUST identify source, fixture, settings, content, command-set schema, company context policy, initial boundary, and all action-payload schema digests.

#### Action header — 48 bytes

| Offset | Size | Field | Rule |
|---:|---:|---|---|
| 0 | 2 | action type | stable action-record type |
| 2 | 2 | action version | starts at `1` |
| 4 | 4 | flags | only command-set-defined bits |
| 8 | 8 | sequence | starts at zero and increments by one |
| 16 | 8 | scheduled public step | monotonic nondecreasing |
| 24 | 8 | scheduled native tick | monotonic nondecreasing |
| 32 | 4 | native command ID | exact pinned numeric command identifier |
| 36 | 4 | company context | exact fixed-width company identifier or declared null sentinel |
| 40 | 4 | payload bytes | command-schema-defined and bounded |
| 44 | 4 | reserved | zero |

Command-specific payload bytes follow and receive zero padding to an 8-byte boundary. Every command schema MUST define operand order, width, signedness, enum domain, stable-ID domain, null sentinel, coordinate encoding, and validation limits.

#### File trailer — 64 bytes

| Offset | Size | Field | Rule |
|---:|---:|---|---|
| 0 | 8 | magic | ASCII `OTRLCME\0` |
| 8 | 8 | action count | equals prefix count |
| 16 | 8 | covered bytes | prefix + header + action region |
| 24 | 32 | SHA-256 | digest of all covered bytes |
| 56 | 8 | reserved | zero |

No byte may follow the trailer. The command parser MUST apply the same strict truncation, overflow, canonicality, padding, reserved-bit, checksum, and transactional-failure rules required for tape v1.

### 15.5 Native command-path rule

Every construction, purchase, order, start, stop, and control action MUST enter through the pinned native command dispatcher. Never mutate a tile, pool, vehicle, order, station, company balance, or cargo field directly to make the fixture work.

Record both native test/quote and native execute behavior when the source path performs both. Preserve command flags, company context, error payload, cost, expense type, and rejected-command behavior.

Never invoke a command test twice solely for logging. Capture results already produced by the native path or add a single deliberate test/execute pair matching normal command semantics.

### 15.6 Safe boundaries

Declare exact instrumentation boundaries in `docs/decisions/0004-tape-format-v1.md` and the field schema. At minimum, record:

- replay start after fixture load and before the first scripted command;
- command intent before native validation;
- command test result after native validation and before execute;
- command execute result after command completion;
- complete post-command authoritative projection;
- complete post-tick authoritative projection after one native simulation tick fully completes;
- named milestones for route completion, first production, first station capture, first loading, first unloading, first accepted delivery, first payment, and continuation end;
- terminal record after the final projection.

Never sample halfway through a mutation sequence unless a diagnostic record explicitly labels a nonauthoritative internal phase.

### 15.7 Complete projection rule for P0

For the first fixture, record a complete canonical authoritative projection after every command and every simulation tick. Do not replace field output with one aggregate hash.

The projection MAY include a supplementary digest for fast equality checks. The comparator MUST still expose exact field values and MUST verify field-level equality when a digest differs.

The complete projection MUST cover every frozen field in `PORT-005`, including all 4,096 map tiles and every reached pool slot in stable slot order.

### 15.8 Trace sink rules

The trace sink MUST:

- open an output path supplied explicitly by the runner;
- create a `.partial` file with exclusive creation;
- reject an existing destination unless an explicit safe overwrite flag targets a generated directory;
- write fixed-endian primitive values;
- check every write;
- propagate disk-full, permission, short-write, and close errors;
- flush and finalize only after a valid terminal record;
- calculate and append the required stream digest through a vetted SHA-256 provider;
- fsync file data when the platform supports the required guarantee;
- atomically rename `.partial` to final tape name only after validation;
- leave an invalid `.partial` artifact for debugging after failure;
- never claim success after any trace error;
- never emit authoritative bytes through formatted text;
- never compress tape v1 internally;
- use zero-filled alignment padding;
- enforce maximum record and file sizes;
- reject counter overflow;
- produce deterministic bytes independent of path, PID, hostname, locale, and wall clock.

### 15.9 Instrumentation read rules

For every projected field, document the read mechanism:

- direct primitive field read;
- stable pool slot traversal;
- stable indexed table traversal;
- explicit serialization helper already proven read-only;
- deterministic cache rebuild observation;
- diagnostic-only derived computation.

The instrumentation MUST NOT:

- call a function whose const qualifier hides mutable cache activity without source proof;
- call a getter that updates statistics;
- call a naming function that consumes a random value;
- call a pathfinder to obtain a route for logging;
- call save code as a per-tick projection shortcut;
- allocate or free gameplay pool objects;
- sort a native container and thereby change later iteration;
- mutate a cache-valid flag;
- change a command result object after capture;
- read uninitialized padding;
- observe race-prone state outside the single-threaded safe boundary.

### 15.10 RNG instrumentation

Record both relevant RNG stream states at every authoritative boundary. Optional per-draw diagnostics MAY record:

- stream identifier;
- draw sequence number;
- caller source identifier assigned at compile time;
- pre-draw state;
- output value;
- post-draw state.

Per-draw diagnostics MUST remain disabled for normal golden tapes unless needed to isolate a divergence. Adding per-draw diagnostics must not create another RNG call or change evaluation order.

### 15.11 Timer instrumentation

Record every reached timer domain and pending callback state that can influence continuation, including:

- game tick or frame counter;
- calendar date and fraction;
- economy date and fraction;
- reached interval timer counters;
- reached event or callback queues;
- tile-loop cursor when relevant;
- vehicle-loop position when relevant;
- industry production timing state;
- station cargo aging or loading timing state;
- any pause or mode flag affecting tick advancement.

A displayed date alone never substitutes for internal counters.

### 15.12 Pool instrumentation

For every reached pool, record:

- capacity;
- occupied count;
- occupancy bitmap or equivalent canonical slot markers;
- free-list state;
- allocation cursor when present;
- slot order;
- typed ID and generation semantics;
- object fields influencing continuation;
- references as stable typed IDs;
- iteration order;
- deletion and reuse state.

Never omit unoccupied slots when free-list or reuse behavior can affect a later ID.

### 15.13 Map instrumentation

Record all native map planes for every tile index from `0` through `4095` in native index order. Record map width, height, and index mapping. Never serialize a rendered tile, sprite, GUI color, or textual description as authoritative map state.

### 15.14 Instrumentation non-perturbation proof

The proof MUST include all comparisons below:

1. `reference-plain` versus `reference-instrumented-off`;
2. `reference-instrumented-off` versus `reference-instrumented-on`;
3. two independent `reference-instrumented-on` runs;
4. continuation after fixture load with no scripted command;
5. continuation under the complete golden command input;
6. continuation after one rejected command;
7. continuation through first accepted delivery and payment;
8. continuation for 10,000 additional deterministic ticks.

Compare native command outcomes, authoritative projections, milestone boundaries, both RNG states, timers, pools, cargo, company ledger, and a final native save or canonical snapshot when available.

Wall-clock speed, heap addresses, trace file descriptors, and log timestamps are not compared.

### 15.15 `PORT-003` exit gate

`PORT-003` reports `PASS` only when:

- patch series applies cleanly;
- plain and instrumented builds compile;
- all 99 upstream tests pass for the baseline and instrumented profiles required by the decision record;
- command input validates before replay;
- every command travels through native dispatch;
- complete projections exist at every declared boundary;
- repeated traced recordings are byte-identical;
- tracing does not change continuation;
- trace I/O failures fail closed;
- all instrumentation tests pass under sanitizers where applicable;
- submodule remains clean;
- source register and schema references cover every reached source path.

---

## 16. `PORT-003` mandatory tests

### 16.1 Patch and build tests

| ID | Test | Required result |
|---|---|---|
| `P003-PAT-001` | Apply full series to pinned clean worktree | success |
| `P003-PAT-002` | Apply series to wrong commit | failure before partial application |
| `P003-PAT-003` | Apply series twice | second application fails clearly without corrupting worktree |
| `P003-PAT-004` | Reverse series | restores clean pinned worktree |
| `P003-PAT-005` | Omit one middle patch | later dependency fails clearly |
| `P003-PAT-006` | Plain build after patch workflow | source submodule still clean |
| `P003-PAT-007` | Instrumented-off build | success |
| `P003-PAT-008` | Instrumented-on runtime | success |
| `P003-PAT-009` | Unsupported trace option | configuration failure |
| `P003-PAT-010` | Patch files contain unrelated bulk formatting | review gate failure |

### 16.2 Command-input parser tests

| ID | Test | Required result |
|---|---|---|
| `P003-CMD-001` | Minimal valid no-action stream | accepted |
| `P003-CMD-002` | Golden construction stream | accepted |
| `P003-CMD-003` | Bad magic | rejected before load advancement |
| `P003-CMD-004` | Unsupported major version | rejected |
| `P003-CMD-005` | Unknown optional minor feature | accepted only under declared compatibility rule |
| `P003-CMD-006` | Wrong fixture digest | identity failure |
| `P003-CMD-007` | Wrong command-set digest | identity failure |
| `P003-CMD-008` | Truncated header | rejected |
| `P003-CMD-009` | Truncated action | rejected |
| `P003-CMD-010` | Oversized action count | rejected before allocation |
| `P003-CMD-011` | Length addition overflow | rejected |
| `P003-CMD-012` | Duplicate sequence | rejected |
| `P003-CMD-013` | Decreasing sequence | rejected |
| `P003-CMD-014` | Decreasing scheduled boundary | rejected unless same-boundary order remains explicit and stable |
| `P003-CMD-015` | Unknown required command type | rejected |
| `P003-CMD-016` | Unknown optional record | skipped only under format rule |
| `P003-CMD-017` | Nonzero reserved field | rejected |
| `P003-CMD-018` | Bad stream checksum | rejected |
| `P003-CMD-019` | Trailing bytes | rejected |
| `P003-CMD-020` | Existing gameplay state before full validation | no mutation allowed |

### 16.3 Native command-path tests

| ID | Test | Required result |
|---|---|---|
| `P003-NAT-001` | Build one legal road tile | native quote, execute result, cost, ledger, and tile change recorded |
| `P003-NAT-002` | Build road on invalid tile | native rejection recorded; authoritative state unchanged except native rejection-side fields |
| `P003-NAT-003` | Build pickup stop | exact native result and pool allocation recorded |
| `P003-NAT-004` | Build delivery stop | exact native result and pool allocation recorded |
| `P003-NAT-005` | Build depot | exact native result and orientation recorded |
| `P003-NAT-006` | Buy vehicle | exact engine, owner, ID, cost, and initial fields recorded |
| `P003-NAT-007` | Assign first order | exact order-list state recorded |
| `P003-NAT-008` | Assign second order | exact circular order state recorded |
| `P003-NAT-009` | Start vehicle | exact status and controller transition recorded |
| `P003-NAT-010` | Repeat invalid purchase with insufficient funds in a negative fixture | exact rejection and nonmutation |
| `P003-NAT-011` | Command company context mismatch | exact native rejection |
| `P003-NAT-012` | Direct-state mutation hook attempted | compile-time or test failure |

### 16.4 Trace sink tests

| ID | Test | Required result |
|---|---|---|
| `P003-IO-001` | New output path | success |
| `P003-IO-002` | Existing final path | rejected by default |
| `P003-IO-003` | Unwritable directory | failure before replay |
| `P003-IO-004` | Disk-full fault injection | run fails; `.partial` retained; final name absent |
| `P003-IO-005` | Short-write fault injection | run fails |
| `P003-IO-006` | Flush failure | run fails |
| `P003-IO-007` | Close failure | run fails |
| `P003-IO-008` | Process interruption before terminal record | validator rejects partial tape |
| `P003-IO-009` | Zero padding verification | all alignment bytes equal zero |
| `P003-IO-010` | File-size limit exceeded | clean bounded failure |
| `P003-IO-011` | Record-size limit exceeded | clean bounded failure |
| `P003-IO-012` | Sequence counter overflow injection | clean failure |
| `P003-IO-013` | Atomic promotion | final path appears only after full finalize |
| `P003-IO-014` | Diagnostic path changed | finalized bytes remain equal |

### 16.5 Determinism and non-perturbation tests

| ID | Test | Required result |
|---|---|---|
| `P003-DET-001` | Two traced runs | byte-identical tape |
| `P003-DET-002` | Twenty serial traced runs | one unique SHA-256 |
| `P003-DET-003` | Eight isolated parallel processes | one unique SHA-256 per identical input profile |
| `P003-DET-004` | Different output directory | same tape bytes |
| `P003-DET-005` | Different PID | same tape bytes |
| `P003-DET-006` | Different hostname diagnostic | same tape bytes |
| `P003-DET-007` | Different locale | same tape bytes |
| `P003-DET-008` | Different timezone | same tape bytes |
| `P003-DET-009` | Plain versus instrumented-off | equal continuation |
| `P003-DET-010` | Instrumented-off versus instrumented-on | equal continuation |
| `P003-DET-011` | No-command 10,000-tick continuation | equal projections |
| `P003-DET-012` | Golden-command 10,000-tick continuation | equal projections |
| `P003-DET-013` | Rejected-command continuation | equal after native rejection semantics |
| `P003-DET-014` | Optional RNG diagnostics on versus off | equal gameplay projection |
| `P003-DET-015` | Optional route diagnostics on versus off | equal gameplay projection |
| `P003-DET-016` | Trace output to slow storage | equal gameplay projection |

### 16.6 Projection completeness tests

| ID | Test | Required result |
|---|---|---|
| `P003-PRJ-001` | Start projection contains every required field ID | pass |
| `P003-PRJ-002` | One required field omitted by fault injection | validator failure |
| `P003-PRJ-003` | Duplicate field ID | validator failure |
| `P003-PRJ-004` | Fields out of canonical order | validator failure |
| `P003-PRJ-005` | Wrong field width | validator failure |
| `P003-PRJ-006` | Map tile count other than 4,096 | validator failure |
| `P003-PRJ-007` | Pool slot order shuffled | comparator divergence |
| `P003-PRJ-008` | Pointer value inserted | schema and policy failure |
| `P003-PRJ-009` | Padding bytes serialized | golden-vector failure |
| `P003-PRJ-010` | Post-command projection missing | tape validation failure |
| `P003-PRJ-011` | Post-tick projection missing | tape validation failure |
| `P003-PRJ-012` | Timer field altered | earliest field divergence reported |
| `P003-PRJ-013` | RNG state altered | earliest field divergence reported |
| `P003-PRJ-014` | Company balance altered | earliest field divergence reported |
| `P003-PRJ-015` | Cargo packet order altered | earliest field divergence reported |

---

## 17. `PORT-004` — tape format, parser, comparator, and minimizer

### 17.1 Objective

Define and implement one strict binary tape v1 whose bytes can be emitted by instrumented OpenTTD, validated independently, inspected by humans, compared field by field, and minimized to the shortest valid prefix preserving the first divergence.

The tape format becomes a compatibility contract. Never change encoded meaning without a format-version change and migration tests.

### 17.2 Required architecture decision

Create `docs/decisions/0004-tape-format-v1.md`. Include:

- byte order;
- integer encoding;
- alignment;
- file prefix;
- canonical header encoding;
- record header;
- record types;
- required and optional feature rules;
- size limits;
- sequencing rules;
- projection encoding;
- trailer and checksum;
- version compatibility;
- parser transaction semantics;
- CLI exit codes;
- minimization semantics;
- security model;
- corruption behavior;
- golden hex vectors.

### 17.3 Tape v1 baseline binary layout

Use the following layout unless a reviewed ADR proves a concrete defect and supplies stronger tests.

#### 17.3.1 File prefix — 64 bytes

All integers use little-endian encoding.

| Offset | Size | Field | Rule |
|---:|---:|---|---|
| 0 | 8 | magic | ASCII `OTRLTAP\0` |
| 8 | 2 | format major | `1` |
| 10 | 2 | format minor | `0` initially |
| 12 | 1 | byte-order code | `1` for little-endian |
| 13 | 1 | hash code | `1` for SHA-256 |
| 14 | 2 | prefix bytes | `64` |
| 16 | 4 | header bytes | bounded canonical JSON byte count |
| 20 | 4 | flags | only defined bits allowed |
| 24 | 8 | record count | exact count excluding trailer |
| 32 | 8 | record bytes | total record region bytes including record padding |
| 40 | 8 | maximum public step recorded | exact final public step |
| 48 | 8 | maximum native tick recorded | exact final tick |
| 56 | 8 | reserved | all zero |

The parser MUST reject bad magic, unsupported major version, unknown required flag, non-little-endian code, unsupported hash code, wrong prefix length, nonzero reserved bits, impossible lengths, and arithmetic overflow.

#### 17.3.2 Canonical header region

The header region contains RFC 8785 canonical JSON. The header MUST validate against `parity/schema/tape-header.schema.json` and MUST include:

- format identity;
- source identity;
- build identity;
- executable digest;
- fixture identity;
- settings identity;
- content identity;
- command-input identity;
- command-set identity;
- field-schema identity;
- instrumentation patch-series identity;
- initial boundary;
- initial timers;
- both initial RNG states;
- projection policy;
- declared record limits;
- optional diagnostic-feature list.

The prefix stores header byte count. No null terminator follows the JSON bytes.

#### 17.3.3 Record header — 40 bytes

| Offset | Size | Field | Rule |
|---:|---:|---|---|
| 0 | 2 | record type | stable numeric ID |
| 2 | 2 | record version | starts at `1` per type |
| 4 | 4 | flags | required/optional and type-specific bits |
| 8 | 8 | sequence | starts at zero and increments by one |
| 16 | 8 | public step | monotonic nondecreasing |
| 24 | 8 | native tick | monotonic nondecreasing |
| 32 | 4 | payload bytes | bounded |
| 36 | 4 | reserved | zero |

Payload bytes follow immediately. Zero padding extends each complete record to an 8-byte boundary. Padding never contributes semantic data but does contribute to the stream digest.

#### 17.3.4 File trailer — 64 bytes

| Offset | Size | Field | Rule |
|---:|---:|---|---|
| 0 | 8 | magic | ASCII `OTRLEND\0` |
| 8 | 8 | record count | equals prefix count |
| 16 | 8 | covered bytes | prefix + header + record region |
| 24 | 32 | SHA-256 | digest of every covered byte in order |
| 56 | 8 | reserved | zero |

No trailing byte may follow the trailer.

### 17.4 Tape limits

Freeze conservative v1 limits in a public header and schema:

- header bytes: maximum 1 MiB;
- one record payload: maximum 64 MiB;
- record count: maximum 50 million;
- total tape bytes: maximum 1 TiB for 64-bit tooling;
- field count in one projection: maximum 10 million;
- one field byte count: maximum 64 MiB;
- string bytes in diagnostics: maximum 1 MiB;
- nesting depth in header JSON: maximum 64;
- command count: maximum 1 million.

A lower operational limit MAY exist for CI. The parser MUST distinguish format limit from local resource limit.

### 17.5 Record type registry

Reserve stable numeric IDs. Never reuse an ID after publication.

| ID | Name | Required for golden tape |
|---:|---|---|
| 1 | `REPLAY_START` | yes |
| 2 | `COMMAND_INTENT` | when a command exists |
| 3 | `COMMAND_TEST_RESULT` | when native test occurs |
| 4 | `COMMAND_EXEC_RESULT` | when execute occurs |
| 5 | `AUTHORITATIVE_PROJECTION` | yes |
| 6 | `NAMED_CHECKPOINT` | yes for declared milestones |
| 7 | `RNG_DRAW_DIAGNOSTIC` | no |
| 8 | `ROUTE_DIAGNOSTIC` | no |
| 9 | `CARGO_DIAGNOSTIC` | no |
| 10 | `TRACE_WARNING` | forbidden in release golden tapes; allowed only in failing diagnostics |
| 11 | `TERMINAL` | yes and last |

Unknown record types with the required flag cause rejection. Unknown optional records may be skipped only when framing remains valid and the comparison policy explicitly ignores the optional feature.

### 17.6 Projection payload layout

Every `AUTHORITATIVE_PROJECTION` payload begins with:

| Size | Field |
|---:|---|
| 2 | projection payload version |
| 1 | boundary kind |
| 1 | reserved zero |
| 4 | field count |
| 8 | boundary ordinal |
| 8 | projection digest prefix or zero when unused |

Each field entry begins with:

| Size | Field |
|---:|---|
| 4 | stable field ID |
| 2 | value type |
| 2 | field flags |
| 4 | element count |
| 4 | byte count |

Field bytes follow, then zero padding to an 8-byte boundary. Field IDs MUST be strictly increasing. Element count and byte count MUST agree with the field schema and value type. Dynamic-capacity fields require an explicit schema rule.

Supported v1 value types MUST remain fixed-width and explicit:

- unsigned 8, 16, 32, and 64 bit;
- signed 8, 16, 32, and 64 bit;
- fixed byte array;
- typed stable ID encoded through one fixed integer width;
- bitset with declared bit count and zero high padding bits;
- UTF-8 diagnostic string only for fields classified diagnostic.

No native `bool`, enum storage width, pointer, `size_t`, `long`, raw float, or raw struct belongs in the file format.

### 17.7 Parser contract

The production C17 parser MUST:

- accept `const uint8_t *` plus length or a bounded streaming reader;
- validate before exposing a completed object;
- leave caller-owned output unchanged after failure;
- return a stable status code;
- return byte offset, record sequence, field ID when available, and a bounded diagnostic message;
- perform checked arithmetic before every offset or allocation calculation;
- enforce all global and local limits;
- reject duplicate keys in canonical JSON;
- verify canonical header bytes rather than accepting arbitrary equivalent JSON;
- verify all reserved bits and padding bytes equal zero;
- verify sequence and boundary monotonicity;
- verify one terminal record appears last;
- verify prefix and trailer counts;
- verify the complete-stream SHA-256;
- reject trailing bytes;
- free all partial allocations after failure;
- tolerate empty and malformed fuzz inputs without crash, leak, hang, or excessive allocation.

### 17.8 Independent Python decoder

Create a small Python 3 standard-library decoder that independently parses prefix, header, records, projection entries, trailer, and digest. The Python decoder MUST NOT call the C library through FFI.

Use the independent decoder to cross-check:

- golden vectors;
- production writer output;
- malformed corpus classifications;
- first record offsets;
- field values;
- complete-stream digest;
- minimized prefix validity.

Common constants MAY come from a generated language-neutral registry only when a test verifies generated bytes against hand-reviewed numeric assignments. Do not share parser logic.

### 17.9 CLI contract

Implement one `tape` CLI with subcommands:

```text
tape inspect FILE
tape validate FILE
tape compare ORACLE TARGET
tape minimize ORACLE TARGET OUTPUT_PREFIX
tape dump FILE --from-tick N --to-tick M --fields FILTER
tape hash FILE
tape finalize PARTIAL OUTPUT
tape schema-check FILE
tape fault-inject INPUT OUTPUT SPEC
```

Required exit codes:

| Code | Meaning |
|---:|---|
| 0 | operation succeeded; comparison equal when comparison requested |
| 1 | valid inputs differ at a gameplay or field boundary |
| 2 | experiment identity mismatch prevents comparison |
| 3 | invalid or corrupted input |
| 4 | I/O or local resource failure |
| 5 | internal invariant failure |
| 64 | command-line usage error |

Never return zero after printing an error.

### 17.10 Comparator contract

The comparator MUST perform checks in order:

1. validate both files independently;
2. compare tape-format compatibility;
3. compare source, build, fixture, settings, content, command input, command set, and field schema identity;
4. reject incomparable experiments with exit code `2`;
5. compare record sequence and required record classes;
6. compare command intent and command outcomes;
7. compare projection field IDs and field values in canonical order;
8. stop at the first divergence;
9. report no later divergence as an independent failure;
10. emit human text and canonical JSON.

The divergence report MUST include:

- both tape digests;
- both complete identities;
- backend labels;
- logical environment ID, fixed to zero for P0;
- earliest public step;
- earliest native tick;
- boundary kind and ordinal;
- record sequence and record type;
- stable field ID;
- hierarchical field path;
- field type, width, signedness, and element index;
- oracle value in decimal and fixed-width hexadecimal when numeric;
- target value in decimal and fixed-width hexadecimal when numeric;
- last command intent;
- command test and execute results;
- previous matching checkpoint;
- minimal prefix output path and digest;
- source anchor from field schema;
- cache classification;
- reproducible command arrays.

### 17.11 Prefix minimizer contract

The minimizer MUST create the shortest valid record prefix that still reproduces the same first divergence under prefix comparison semantics.

The minimizer MUST:

- preserve the complete file prefix and canonical header;
- preserve every record required to interpret the retained divergence;
- preserve sequence numbering or rewrite sequence numbers under an explicit canonical-prefix rule;
- rewrite prefix counts, record byte counts, maximum step, maximum tick, terminal record, trailer counts, and digest;
- never output a malformed tape;
- use binary search over boundary prefixes when monotonicity holds;
- fall back to a verified linear boundary search when monotonicity cannot be proven;
- verify the minimized output reproduces the same divergence signature;
- report original and minimized byte count, record count, final boundary, and digest;
- never remove a causally required command before a later projection.

A second minimization layer MAY minimize command-input prefixes by rerunning the oracle, but P0 closure requires at least valid tape-prefix minimization.

### 17.12 Human dump contract

Human-readable output MUST:

- remain nonauthoritative;
- use stable field paths from the schema;
- print exact integers without locale formatting;
- print fixed-width hexadecimal for binary inspection;
- escape untrusted strings;
- support bounded tick and field filters;
- avoid dumping secrets or host paths;
- never truncate a value silently;
- mark truncation explicitly when a user-requested display limit applies.

### 17.12.1 C17 library API contract

Expose a versioned C API for P0 tools. Public request, option, result, and error structs MUST begin with `uint32_t size` and `uint32_t version`. Reserved fields MUST equal zero. Internal parser structs remain opaque.

Required stable status families:

```c
typedef enum otrl_status {
    OTRL_OK = 0,
    OTRL_E_USAGE,
    OTRL_E_IO,
    OTRL_E_TRUNCATED,
    OTRL_E_MAGIC,
    OTRL_E_VERSION,
    OTRL_E_ENDIAN,
    OTRL_E_HASH_ALGORITHM,
    OTRL_E_CHECKSUM,
    OTRL_E_CANONICAL,
    OTRL_E_RESERVED,
    OTRL_E_LIMIT,
    OTRL_E_OVERFLOW,
    OTRL_E_SEQUENCE,
    OTRL_E_STRUCTURE,
    OTRL_E_SCHEMA,
    OTRL_E_IDENTITY,
    OTRL_E_DIVERGENCE,
    OTRL_E_INVARIANT,
    OTRL_E_INTERNAL
} otrl_status;
```

Required API capabilities:

- validate bytes without ownership transfer;
- validate a file through a bounded streaming reader;
- inspect header identity;
- iterate records without exposing internal pointers beyond a documented callback lifetime;
- decode one projection through schema validation;
- compare two files;
- minimize one divergent pair;
- write and finalize a tape;
- convert every status value to one stable string;
- return structured error location containing byte offset, record sequence, public step, native tick, field ID, and bounded message when available;
- accept an optional caller allocator or use one documented library allocator consistently;
- destroy every allocated object through the matching library function;
- support independent contexts concurrently without shared mutable state.

API functions MUST reject undersized public structs, unsupported versions, nonzero reserved fields, null required pointers, length mismatches, and overlapping input/output buffers when overlap could corrupt results. A failed call MUST leave caller-owned result storage in a documented zero or unchanged state.

The ABI test suite MUST compile both C and C++ callers, verify symbol names, verify status totality, verify struct prefix layout, verify reserved-zero enforcement, and verify no CUDA or Python runtime dependency enters the library.

### 17.13 `PORT-004` exit gate

`PORT-004` reports `PASS` only when:

- format ADR is complete;
- production C17 codec compiles under GCC and Clang;
- independent Python decoder agrees on every golden vector;
- strict validation rejects every malformed corpus case;
- two equal oracle tapes compare equal;
- an injected identity mismatch returns exit code `2`;
- an injected first field mismatch returns exit code `1` and exact field data;
- prefix minimization preserves the divergence signature;
- fuzzers find no crash, leak, timeout, or sanitizer defect under the release campaign;
- coverage and mutation thresholds pass;
- CLI and library APIs have stable documented status codes;
- no unknown or corrupted input can cause unbounded allocation.


---

## 18. `PORT-004` mandatory tests

### 18.1 Primitive and golden-vector tests

Every primitive encoding test MUST compare exact bytes against a hand-reviewed hexadecimal vector.

| ID | Test | Required result |
|---|---|---|
| `P004-ENC-001` | `u8` values `0`, `1`, `255` | exact bytes |
| `P004-ENC-002` | `u16` values `0`, `1`, `0x1234`, `65535` | little-endian exact bytes |
| `P004-ENC-003` | `u32` values `0`, `1`, `0x12345678`, maximum | little-endian exact bytes |
| `P004-ENC-004` | `u64` values `0`, `1`, `0x0123456789abcdef`, maximum | little-endian exact bytes |
| `P004-ENC-005` | signed minimum and maximum for every width | two’s-complement bit pattern verified against C17 implementation assumptions and source needs |
| `P004-ENC-006` | zero-length byte array | valid where schema allows |
| `P004-ENC-007` | maximum allowed byte array | valid without overflow |
| `P004-ENC-008` | one byte above maximum | `OTRL_E_LIMIT` |
| `P004-ENC-009` | alignment from every payload remainder `0..7` | exact zero padding |
| `P004-ENC-010` | nonzero alignment byte | rejection |
| `P004-ENC-011` | checked add at maximum boundary | correct success or overflow failure |
| `P004-ENC-012` | checked multiply at maximum boundary | correct success or overflow failure |
| `P004-ENC-013` | host-endian simulation | encoded bytes remain little-endian |
| `P004-ENC-014` | struct padding variation | no encoded-byte change because structs are not serialized |
| `P004-ENC-015` | canonical header property reordering before canonicalization | identical header bytes |
| `P004-ENC-016` | canonical header whitespace variation before canonicalization | identical header bytes |
| `P004-ENC-017` | noncanonical header bytes with equal JSON meaning | strict tape validator rejects |
| `P004-ENC-018` | one authoritative header value changed | tape digest and identity change |
| `P004-ENC-019` | one diagnostic path changed outside identity | authoritative identity remains equal |
| `P004-ENC-020` | SHA-256 known-answer vectors | exact NIST-compatible digests |

### 18.2 File-prefix tests

| ID | Test | Required result |
|---|---|---|
| `P004-PFX-001` | Exact valid 64-byte prefix | accepted |
| `P004-PFX-002` | Empty input | truncated error at byte zero |
| `P004-PFX-003` | Prefix lengths `1..63` | truncated error at exact available length |
| `P004-PFX-004` | Wrong magic byte at every magic position | magic error at exact position |
| `P004-PFX-005` | Major version zero | version error |
| `P004-PFX-006` | Major version two | version error |
| `P004-PFX-007` | Supported major with unsupported required feature | feature error |
| `P004-PFX-008` | Wrong endian code | endian error |
| `P004-PFX-009` | Wrong hash code | hash-algorithm error |
| `P004-PFX-010` | Prefix byte count not 64 | format error |
| `P004-PFX-011` | Header length zero | schema or format error |
| `P004-PFX-012` | Header length above 1 MiB | limit error before allocation |
| `P004-PFX-013` | Record count inconsistent with empty region | structural error |
| `P004-PFX-014` | Record byte count addition overflow | overflow error |
| `P004-PFX-015` | Maximum step lower than a retained record | structural error |
| `P004-PFX-016` | Maximum tick lower than a retained record | structural error |
| `P004-PFX-017` | Nonzero reserved value | reserved-field error |
| `P004-PFX-018` | Unknown nonrequired flag under declared compatibility | handled according to ADR |
| `P004-PFX-019` | Unknown required flag | rejection |
| `P004-PFX-020` | Prefix parsed on deliberately misaligned input pointer | safe exact parse |

### 18.3 Header JSON tests

| ID | Test | Required result |
|---|---|---|
| `P004-HDR-001` | Valid canonical header | accepted |
| `P004-HDR-002` | Valid JSON with noncanonical whitespace | rejected as noncanonical tape bytes |
| `P004-HDR-003` | Duplicate object key | rejected |
| `P004-HDR-004` | Invalid UTF-8 | rejected |
| `P004-HDR-005` | Byte-order mark | rejected |
| `P004-HDR-006` | Missing source commit | rejected |
| `P004-HDR-007` | Commit length 39 or 41 | rejected |
| `P004-HDR-008` | Nonhex commit character | rejected |
| `P004-HDR-009` | Missing fixture digest | rejected |
| `P004-HDR-010` | Uppercase digest | rejected under canonical storage rule |
| `P004-HDR-011` | Wrong field-schema digest length | rejected |
| `P004-HDR-012` | Unknown required header property | rejected |
| `P004-HDR-013` | Excessive nesting depth | limit error |
| `P004-HDR-014` | Excessive string length | limit error |
| `P004-HDR-015` | Floating value where integer required | schema error |
| `P004-HDR-016` | Negative tick | schema error |
| `P004-HDR-017` | Initial RNG state missing | schema error |
| `P004-HDR-018` | NewGRF list nonempty | identity or fixture-policy error |
| `P004-HDR-019` | Absolute path inside identity object | semantic-validation error |
| `P004-HDR-020` | Secret-key-shaped environment name | semantic-validation error |

### 18.4 Record-framing tests

| ID | Test | Required result |
|---|---|---|
| `P004-REC-001` | One valid replay-start record | accepted |
| `P004-REC-002` | One valid terminal record after required projection | accepted |
| `P004-REC-003` | Record header truncated at every byte boundary | exact truncated error |
| `P004-REC-004` | Payload truncated at every byte boundary for a small golden tape | exact truncated error |
| `P004-REC-005` | Padding truncated | exact truncated error |
| `P004-REC-006` | Payload length above limit | limit error before allocation |
| `P004-REC-007` | Payload length plus header overflow | overflow error |
| `P004-REC-008` | Sequence starts at one | sequence error |
| `P004-REC-009` | Duplicate sequence | sequence error |
| `P004-REC-010` | Sequence gap | sequence error |
| `P004-REC-011` | Public step decreases | boundary-order error |
| `P004-REC-012` | Native tick decreases | boundary-order error |
| `P004-REC-013` | Nonzero reserved field | reserved-field error |
| `P004-REC-014` | Unknown required record type | rejection |
| `P004-REC-015` | Unknown optional record type | skip only under compatibility rule |
| `P004-REC-016` | Record version zero | version error |
| `P004-REC-017` | Unsupported required record version | version error |
| `P004-REC-018` | Terminal record missing | structural error |
| `P004-REC-019` | Two terminal records | structural error |
| `P004-REC-020` | Record after terminal | structural error |
| `P004-REC-021` | Trace warning in release golden tape | policy failure |
| `P004-REC-022` | Missing replay-start record | structural error |
| `P004-REC-023` | Command result without command intent | structural error |
| `P004-REC-024` | Execute result before test result when source contract requires test | structural error |
| `P004-REC-025` | Projection omitted after command result | structural error |

### 18.5 Projection tests

| ID | Test | Required result |
|---|---|---|
| `P004-FLD-001` | Valid minimal projection | accepted |
| `P004-FLD-002` | Field count zero at required boundary | rejected |
| `P004-FLD-003` | Field count above limit | limit error |
| `P004-FLD-004` | Field entries truncated at every byte boundary | exact truncated error |
| `P004-FLD-005` | Field ID zero when registry reserves zero | rejected |
| `P004-FLD-006` | Duplicate field ID | rejected |
| `P004-FLD-007` | Decreasing field ID | rejected |
| `P004-FLD-008` | Unknown required field ID | schema mismatch |
| `P004-FLD-009` | Wrong value type | schema mismatch |
| `P004-FLD-010` | Wrong element count | schema mismatch |
| `P004-FLD-011` | Wrong byte count | schema mismatch |
| `P004-FLD-012` | Byte count multiplication overflow | overflow error |
| `P004-FLD-013` | Nonzero high bitset padding | canonicality error |
| `P004-FLD-014` | Diagnostic string invalid UTF-8 | rejected |
| `P004-FLD-015` | Authoritative string field attempted without schema approval | rejected |
| `P004-FLD-016` | Numeric field with extra padding bytes inside value | rejected |
| `P004-FLD-017` | Map array has 4,095 elements | rejected |
| `P004-FLD-018` | Map array has 4,097 elements | rejected |
| `P004-FLD-019` | Pool capacity differs from schema and fixture | rejected |
| `P004-FLD-020` | Stable ID width differs | rejected |
| `P004-FLD-021` | Signed minimum value | exact decode |
| `P004-FLD-022` | Signed maximum value | exact decode |
| `P004-FLD-023` | Unsigned maximum value | exact decode |
| `P004-FLD-024` | Field value one-bit mutation | exact first divergence |
| `P004-FLD-025` | Field order mutation | validation failure before comparison |

### 18.6 Trailer and digest tests

| ID | Test | Required result |
|---|---|---|
| `P004-TRL-001` | Valid trailer | accepted |
| `P004-TRL-002` | Trailer truncated at every byte boundary | exact truncated error |
| `P004-TRL-003` | Wrong trailer magic | trailer error |
| `P004-TRL-004` | Prefix and trailer record count differ | structural error |
| `P004-TRL-005` | Covered byte count differs | structural error |
| `P004-TRL-006` | One-bit mutation in covered prefix | checksum error |
| `P004-TRL-007` | One-bit mutation in header | checksum error |
| `P004-TRL-008` | One-bit mutation in record header | checksum error or earlier structural error |
| `P004-TRL-009` | One-bit mutation in payload | checksum error |
| `P004-TRL-010` | One-bit mutation in padding | checksum error or canonical-padding error |
| `P004-TRL-011` | One-bit mutation in stored digest | checksum error |
| `P004-TRL-012` | Nonzero trailer reserved field | reserved-field error |
| `P004-TRL-013` | One trailing byte | trailing-data error |
| `P004-TRL-014` | 1 KiB trailing data | trailing-data error without excessive processing |
| `P004-TRL-015` | Valid data concatenated twice | rejection |

### 18.7 Comparator tests

| ID | Test | Required result |
|---|---|---|
| `P004-CMP-001` | File compared with exact copy | equal, exit `0` |
| `P004-CMP-002` | Different tape-format major | incomparable or invalid, never gameplay divergence |
| `P004-CMP-003` | Different source commit | identity mismatch, exit `2` |
| `P004-CMP-004` | Different executable digest | identity mismatch, exit `2` |
| `P004-CMP-005` | Different fixture digest | identity mismatch, exit `2` |
| `P004-CMP-006` | Different settings digest | identity mismatch, exit `2` |
| `P004-CMP-007` | Different content digest | identity mismatch, exit `2` |
| `P004-CMP-008` | Different command-input digest | identity mismatch, exit `2` |
| `P004-CMP-009` | Different field-schema digest | identity mismatch, exit `2` |
| `P004-CMP-010` | First command ID differs | first command divergence, exit `1` |
| `P004-CMP-011` | First command operand differs | exact operand divergence |
| `P004-CMP-012` | Command status differs | exact result divergence |
| `P004-CMP-013` | Command cost differs by one | exact signed numeric divergence |
| `P004-CMP-014` | Error payload differs | exact payload divergence |
| `P004-CMP-015` | First projection field missing | exact field-presence divergence |
| `P004-CMP-016` | First field value differs | exact field divergence |
| `P004-CMP-017` | Later field differs after earlier mismatch | report only earliest mismatch as root divergence |
| `P004-CMP-018` | One tape ends early | exact end-of-stream divergence |
| `P004-CMP-019` | Optional diagnostics differ under ignore policy | equality of authoritative stream plus diagnostic-difference note |
| `P004-CMP-020` | Required diagnostics differ under compare policy | exact divergence |
| `P004-CMP-021` | Decimal signed interpretation | exact correct sign |
| `P004-CMP-022` | Hex fixed width | exact leading zeros |
| `P004-CMP-023` | Array element differs | exact element index |
| `P004-CMP-024` | Bitset bit differs | exact bit index |
| `P004-CMP-025` | Human report string contains control byte | escaped safely |
| `P004-CMP-026` | Machine report validates against schema | pass |
| `P004-CMP-027` | Output path unwritable | exit `4`, no false equality |
| `P004-CMP-028` | Invalid oracle tape and valid target | input error, exit `3` |
| `P004-CMP-029` | Valid oracle and invalid target | input error, exit `3` |
| `P004-CMP-030` | Both invalid | deterministic input-order error policy |

### 18.8 Minimizer tests

| ID | Test | Required result |
|---|---|---|
| `P004-MIN-001` | Divergence at first comparable record | shortest valid prefix ending at first divergence |
| `P004-MIN-002` | Divergence in middle | prefix ends at exact boundary |
| `P004-MIN-003` | Divergence at final projection | complete prefix required |
| `P004-MIN-004` | Equal tapes | usage or no-divergence result; no misleading prefix |
| `P004-MIN-005` | Identity mismatch | no minimization |
| `P004-MIN-006` | Invalid input | no output final file |
| `P004-MIN-007` | Output destination exists | reject by default |
| `P004-MIN-008` | Prefix counts rewritten | validator accepts |
| `P004-MIN-009` | Maximum step and tick rewritten | exact retained values |
| `P004-MIN-010` | Terminal and trailer rewritten | digest valid |
| `P004-MIN-011` | Minimized comparison | same divergence signature |
| `P004-MIN-012` | One record removed from minimized prefix | divergence no longer reproducible or file invalid |
| `P004-MIN-013` | Monotonicity assumption deliberately broken in synthetic case | verified fallback finds correct prefix |
| `P004-MIN-014` | Very large record count synthetic tape | bounded memory and correct prefix |
| `P004-MIN-015` | Interrupted minimization | partial output never promoted |

### 18.9 CLI tests

| ID | Test | Required result |
|---|---|---|
| `P004-CLI-001` | No subcommand | exit `64` |
| `P004-CLI-002` | Unknown subcommand | exit `64` |
| `P004-CLI-003` | Missing file argument | exit `64` |
| `P004-CLI-004` | Extra unexpected argument | exit `64` |
| `P004-CLI-005` | `--help` | exit `0` and complete command list |
| `P004-CLI-006` | Equal comparison | exit `0` |
| `P004-CLI-007` | Divergent comparison | exit `1` |
| `P004-CLI-008` | Identity mismatch | exit `2` |
| `P004-CLI-009` | Corrupt file | exit `3` |
| `P004-CLI-010` | Missing file | exit `4` |
| `P004-CLI-011` | Human output to terminal | stable, bounded, escaped |
| `P004-CLI-012` | JSON output | schema-valid canonical JSON where requested |
| `P004-CLI-013` | Broken output pipe | nonzero I/O result unless SIGPIPE policy documents a standard shell result |
| `P004-CLI-014` | Tick filter start above end | usage error |
| `P004-CLI-015` | Unknown field filter | explicit error, no silent empty output |

### 18.10 Fuzz targets

Create at least the following independent fuzz targets:

- `fuzz_tape_prefix`;
- `fuzz_tape_header`;
- `fuzz_tape_records`;
- `fuzz_projection_payload`;
- `fuzz_full_tape`;
- `fuzz_command_input`;
- `fuzz_field_schema_json`;
- `fuzz_manifest_json`;
- `fuzz_comparator_pair`;
- `fuzz_minimizer_pair`.

Fuzz targets MUST:

- accept arbitrary bytes;
- avoid `exit`;
- avoid unbounded memory;
- avoid unbounded recursion;
- cap synthetic work;
- run under ASan and UBSan;
- include valid and invalid seed corpus files;
- store minimized crashing inputs;
- convert every discovered defect into a tracked regression test;
- record compiler, sanitizer options, seed corpus digest, run count, and final corpus digest.

P0 release fuzz campaign minimum:

- at least 1,000,000 executions per byte-parser target;
- at least 250,000 executions per pair-input comparator or minimizer target;
- zero crash;
- zero sanitizer finding;
- zero timeout above the per-input bound;
- zero uncontrolled allocation;
- zero corpus input that produces nondeterministic status across ten repeats.

Execution counts rather than wall-clock duration define the minimum. A stronger campaign may run longer.

### 18.11 Coverage gate

For new P0 production code excluding third-party libraries and generated schema tables:

- line coverage MUST equal 100 percent for checked-arithmetic, primitive codec, status mapping, and tape-framing modules;
- branch coverage MUST equal 100 percent for checked-arithmetic functions;
- line coverage MUST reach at least 95 percent for parser, comparator, minimizer, and schema modules;
- branch coverage MUST reach at least 90 percent for parser, comparator, minimizer, and schema modules;
- every uncovered line or branch requires a reviewed entry naming source location, reason, reachability analysis, and compensating test;
- no coverage exclusion pragma may appear without a reviewed waiver;
- fatal hardware or operating-system branches may use deterministic fault injection rather than remain untested.

Coverage percentages never substitute for requirement coverage or mutation testing.

### 18.12 Mutation gate

Create deterministic seeded mutants for at least:

- disabled prefix-magic check;
- disabled major-version check;
- disabled reserved-zero check;
- unchecked length addition;
- unchecked length multiplication;
- disabled sequence check;
- disabled padding-zero check;
- disabled trailer-count check;
- disabled SHA-256 comparison;
- comparator skipping first field;
- comparator treating signed value as unsigned;
- comparator continuing after first divergence and overwriting root cause;
- minimizer retaining one unnecessary boundary;
- minimizer producing stale trailer digest;
- schema allowing duplicate field ID;
- schema allowing width mismatch;
- identity comparison ignoring fixture digest;
- identity comparison ignoring settings digest;
- command parser mutating state before full validation;
- trace sink promoting `.partial` after failure.

Every seeded mutant MUST be killed by at least one named test. Surviving mutant count must equal zero. Do not weaken mutant code to make killing trivial; each mutant must model a plausible defect.

---

## 19. `PORT-005` — future-complete field schema and cache policy

### 19.1 Objective

Freeze a versioned field registry that contains every piece of state capable of changing future behavior for the declared fixture and every field required to diagnose command, movement, cargo, timer, RNG, pool, and accounting divergence.

The schema must distinguish authoritative state, derived state, diagnostics, and proven unreachable state. A missing future-relevant field leaves P0 incomplete even when current golden tapes compare equal.

### 19.2 Required decision record

Create `docs/decisions/0005-field-schema-and-cache-policy.md`. Record:

- field-registry versioning policy;
- stable ID allocation policy;
- field deletion and deprecation policy;
- scalar and array type rules;
- canonical order;
- boundary sampling rule;
- complete-projection rule;
- owner and lifecycle definitions;
- cache classification procedure;
- cache clearing and rebuild procedure;
- omitted-field experiment procedure;
- 10,000-tick continuation procedure;
- source-anchor standard;
- schema review signoff checklist.

### 19.3 Field registry entry contract

Every entry in `parity/schema/fields-v1.json` MUST include:

- stable numeric field ID;
- hierarchical field path;
- human description;
- classification;
- value type;
- width in bits when numeric;
- signedness when numeric;
- endianness;
- scalar, fixed-array, dynamic-array, or bitset shape;
- fixed count or count-source field;
- maximum capacity;
- canonical element order;
- owner type;
- owner stable ID rule;
- lifecycle start;
- lifecycle end;
- sampling boundary;
- serialization rule;
- comparison rule;
- source commit;
- source file;
- source symbol;
- source line or source-range diagnostic;
- reached call path;
- future-influence rationale;
- cache classification when applicable;
- cache invalidation trigger when applicable;
- deterministic rebuild procedure when applicable;
- fixture reachability status;
- sample logical value;
- sample encoded hexadecimal bytes;
- unit test ID;
- review status.

No field may remain with `TBD`, `unknown`, `later`, placeholder text, or an empty rationale at P0 closure.

### 19.4 Stable ID policy

- Field ID zero remains reserved.
- Published field IDs are never reused.
- Renaming a path does not change an ID unless encoded meaning changes.
- Encoded meaning change requires a new ID or major schema version.
- Deleted fields remain reserved and marked deprecated.
- IDs use explicit ranges by subsystem.
- Registry order follows numeric ID.
- Source array index never substitutes for a stable field ID when array meaning differs by subsystem.

Recommended v1 ranges:

| Range | Subsystem |
|---:|---|
| `1–999` | experiment, mode, fault, and terminal state |
| `1000–1999` | clocks, dates, timers, and RNG |
| `2000–2999` | settings and global revision counters |
| `3000–3999` | map dimensions and map planes |
| `4000–4999` | company pool and ledger |
| `5000–5999` | industry pool and production |
| `6000–6999` | station, road-stop, and goods state |
| `7000–7999` | vehicle pool and road-vehicle controller |
| `8000–8999` | order pool and order lists |
| `9000–9999` | cargo packet pool and cargo chains |
| `10000–10999` | pathfinder and route caches |
| `11000–11999` | diagnostic-only trace fields |
| `12000+` | reserved for reviewed expansion |

The exact ranges may change before publication through the ADR. The final registry must have no collision.

### 19.5 Required classification values

Every field MUST use exactly one class:

1. `authoritative_full` — emitted at every declared boundary;
2. `authoritative_periodic` — allowed only after a reviewed reason and explicit full-snapshot schedule;
3. `derived_rebuild` — omitted from canonical stored state only after deterministic rebuild and continuation proof;
4. `diagnostic` — not consumed by simulation and never required for continuation;
5. `out_of_scope_unreachable` — source path proven unreachable under fixture and command corpus.

For P0 golden tapes, default every future-relevant field to `authoritative_full`. Use `authoritative_periodic` only when complete per-boundary emission creates a demonstrated technical impossibility rather than inconvenience.

### 19.6 Required global and time fields

At minimum, review and freeze fields for:

- current game mode;
- pause state affecting advancement;
- simulation tick or frame counter;
- calendar date;
- calendar fraction;
- economy date;
- economy fraction;
- reached periodic timer counters;
- pending reached timer callbacks;
- tile-loop cursor;
- reached object-loop cursors;
- both RNG stream internal states;
- optional RNG draw counters;
- settings revision or topology revision counters;
- pathfinder cache revision counters;
- terminal or fault state;
- current company context when command behavior depends on the context.

### 19.7 Required map fields

Record exact native map dimensions and every reached underlying map plane for all 4,096 tile indices. Review at least:

- tile type;
- height and slope representation;
- owner;
- road bits;
- road type;
- tram bits or explicit unreachable proof;
- station identifier;
- depot identifier or depot bits;
- industry identifier where represented;
- auxiliary metadata bytes;
- reached tile flags;
- tile-loop scheduling state;
- map revision counters;
- cache invalidation markers tied to map mutations.

Do not replace native planes with semantic labels alone.

### 19.8 Required company fields

Review at least:

- company pool occupancy;
- company ID;
- money balance;
- loan when reached;
- current expense category;
- categorized construction expense;
- vehicle purchase expense;
- running cost when reached;
- delivered-cargo income;
- company value or score only when reached or future-relevant;
- command context;
- bankruptcy or invalid-company flags when reachable;
- any rounding remainder influencing later ledger values.

### 19.9 Required industry fields

Review at least:

- industry pool occupancy;
- industry ID;
- type;
- tile footprint or anchor;
- produced cargo type;
- accepted cargo types;
- production rate;
- production counters;
- production remainders;
- transported amount or percentage when future-relevant;
- production timer state;
- closure or production-change state even when disabled, with explicit fixture value;
- station-capture interaction state;
- RNG-dependent production inputs.

### 19.10 Required station and road-stop fields

Review at least:

- station pool occupancy;
- station ID;
- owner;
- anchor tile;
- facility flags;
- catchment configuration;
- acceptance state;
- road-stop pool occupancy;
- road-stop ID;
- road-stop tile;
- orientation;
- linked-list or indexed order among stops;
- entry and exit state;
- vehicle queue state when reached;
- `GoodsEntry` state for the selected cargo;
- waiting amount;
- rating or service counters when future-relevant;
- cargo packet chain head and order;
- load/unload state;
- cache state and invalidation flags.

### 19.11 Required vehicle fields

Review at least:

- vehicle pool occupancy;
- vehicle stable ID and generation rule;
- subtype and engine/type ID;
- owner;
- current tile and precise position;
- direction;
- track or road direction;
- current and next movement state;
- speed;
- progress;
- acceleration-related state;
- controller state;
- stopped/running flags;
- depot state;
- station state;
- current order index;
- order-list ID;
- destination target;
- cargo capacity;
- cargo packet chain;
- loading or unloading progress;
- age, service, reliability, and breakdown state when reached or explicitly disabled;
- route-cache references;
- pathfinder scratch that persists across ticks;
- random bits or counters attached to the vehicle;
- next vehicle in any native pool iteration chain.

### 19.12 Required order fields

Review at least:

- order pool occupancy;
- order stable ID;
- order-list stable ID;
- order type;
- destination station ID;
- flags;
- load/unload policy;
- next-order link or canonical list order;
- current order index;
- implicit order state when reached;
- order execution progress;
- service or depot order state when reached.

### 19.13 Required cargo packet fields

Review at least:

- cargo packet pool occupancy;
- packet stable ID;
- amount or count;
- cargo type when packet type is not implicit;
- source station or industry;
- source tile or provenance;
- source date;
- age;
- distance-related fields;
- feeder share;
- transfer state;
- destination or routing metadata when reached;
- owning station or vehicle container;
- chain order;
- split and merge state;
- allocation and free-list order;
- conservation totals at each phase.

Packet identity and packet order are mandatory even when total cargo amount matches.

### 19.14 Required pathfinder and controller fields

Review at least:

- pathfinder invocation boundary;
- start tile and direction;
- target tile or station;
- selected trackdir;
- path cost;
- tie-break inputs;
- no-route state;
- node limit state;
- cached route state;
- topology revision used by cache;
- controller decision state;
- station-entry state;
- depot-entry state;
- road-stop occupancy interaction;
- persistent scratch or queue state that survives a tick.

Transient diagnostic traces may record candidate nodes without classifying every candidate as authoritative. Persistent route choices and cache inputs require authoritative treatment.

### 19.15 Cache review protocol

For every reached cache:

1. identify owner, storage, validity marker, invalidation sites, rebuild function, and consumers;
2. trace whether any getter mutates cache state;
3. determine whether cache content can affect tie resolution, iteration order, command result, movement, cargo, cost, or RNG consumption;
4. classify cache as authoritative or derived;
5. create a test-only cache-clearing operation that does not alter underlying authoritative inputs;
6. clear the cache at an approved boundary;
7. rebuild through the normal production path;
8. compare rebuilt fields with the original cache when cache bytes are stable and meaningful;
9. compare the next command and next tick;
10. compare a 10,000-tick continuation;
11. repeat across two independent loads;
12. record raw evidence and decision rationale.

A cache may use `derived_rebuild` only when every test above passes. Immediate next-tick equality alone is insufficient.

### 19.16 Field-omission experiment

For each field family, perform deliberate omission or mutation experiments:

- remove the field from a copied projection schema;
- mutate one representative value in a copied tape;
- verify the validator or comparator detects the inconsistency;
- where feasible, restore from a snapshot lacking the field and test continuation;
- classify any delayed divergence;
- update future-influence rationale.

The goal is not random destructive editing. The goal is evidence that the schema can reveal and preserve every future-relevant dependency.

### 19.17 Schema review rule

At least two independent passes must review the field schema:

- source-owner pass: follows pinned source reads and writes;
- continuation pass: starts from future behavior and asks which prior state controls every branch.

An AI subagent MAY perform an independent review, but the main implementation owner must verify every accepted finding against pinned source or oracle evidence. No generated review statement counts as evidence alone.

### 19.18 `PORT-005` exit gate

`PORT-005` reports `PASS` only when:

- every reached field has a complete schema entry;
- every field ID is unique and stable;
- every sample encoding matches hand-reviewed bytes;
- every field maps to pinned source evidence;
- every field has a future-influence rationale;
- every reached cache has an explicit class;
- every derived cache passes clear, rebuild, immediate comparison, and 10,000-tick continuation;
- every out-of-scope field family has a source-backed unreachability proof;
- complete projections validate at every boundary;
- deliberate omission and mutation tests detect the targeted faults;
- no `TBD`, placeholder, unknown owner, or undocumented skip remains;
- schema and command registries have canonical digests;
- a final independent review finds no open future-state gap.


---

## 20. `PORT-005` mandatory tests

### 20.1 Registry integrity tests

| ID | Test | Required result |
|---|---|---|
| `P005-REG-001` | Valid complete registry | accepted |
| `P005-REG-002` | Field ID zero | rejected |
| `P005-REG-003` | Duplicate field ID | rejected |
| `P005-REG-004` | Duplicate field path | rejected unless one path alias has an explicit deprecation rule |
| `P005-REG-005` | Decreasing numeric ID order | rejected as noncanonical |
| `P005-REG-006` | Unknown classification | rejected |
| `P005-REG-007` | Missing owner | rejected |
| `P005-REG-008` | Missing lifecycle | rejected |
| `P005-REG-009` | Missing source commit | rejected |
| `P005-REG-010` | Source commit differs from pin | rejected |
| `P005-REG-011` | Missing source file | rejected |
| `P005-REG-012` | Source file absent from pinned tree | rejected |
| `P005-REG-013` | Missing source symbol | rejected |
| `P005-REG-014` | Missing future-influence rationale | rejected |
| `P005-REG-015` | Placeholder token | rejected by semantic lint |
| `P005-REG-016` | Numeric width not in allowed set | rejected |
| `P005-REG-017` | Signedness omitted for numeric field | rejected |
| `P005-REG-018` | Dynamic array without count source | rejected |
| `P005-REG-019` | Dynamic array without maximum capacity | rejected |
| `P005-REG-020` | Derived cache without rebuild procedure | rejected |
| `P005-REG-021` | Out-of-scope field without unreachability proof | rejected |
| `P005-REG-022` | Diagnostic field consumed by simulation according to source review | classification failure |
| `P005-REG-023` | Sample byte length differs from declared width | rejected |
| `P005-REG-024` | Sample byte order wrong | golden-vector failure |
| `P005-REG-025` | Registry canonicalization repeated | byte-identical output |

### 20.2 Source-anchor tests

| ID | Test | Required result |
|---|---|---|
| `P005-SRC-001` | Every source file exists at pinned commit | pass |
| `P005-SRC-002` | Every source symbol search yields expected declaration or definition | pass or reviewed exact locator when overloads exist |
| `P005-SRC-003` | Source line diagnostic outside file | failure |
| `P005-SRC-004` | Current `master` URL used as behavior authority | policy failure |
| `P005-SRC-005` | Field rationale cites only a research note | review failure until pinned source or oracle evidence appears |
| `P005-SRC-006` | Reached helper file absent from source register | traceability failure |
| `P005-SRC-007` | Field write site omitted from ownership analysis | review failure |
| `P005-SRC-008` | Field read site affecting continuation omitted | review failure |
| `P005-SRC-009` | Stable ID semantics conflict with source | test or review failure |
| `P005-SRC-010` | Cache invalidation site missing | cache review failure |

### 20.3 Projection-schema agreement tests

| ID | Test | Required result |
|---|---|---|
| `P005-AGR-001` | Every required registry field appears in every full projection | pass |
| `P005-AGR-002` | Projection contains unknown required field | failure |
| `P005-AGR-003` | Projection omits one global timer | failure |
| `P005-AGR-004` | Projection omits one RNG stream | failure |
| `P005-AGR-005` | Projection omits map plane | failure |
| `P005-AGR-006` | Projection omits one occupied pool slot | failure |
| `P005-AGR-007` | Projection omits one free-list entry | failure |
| `P005-AGR-008` | Projection omits cargo packet order | failure |
| `P005-AGR-009` | Projection reports field with wrong class at boundary | failure |
| `P005-AGR-010` | Fixed count differs from schema | failure |
| `P005-AGR-011` | Dynamic count exceeds capacity | failure |
| `P005-AGR-012` | Stable owner ID missing for dynamic element | failure |
| `P005-AGR-013` | Field encoded using host `size_t` width | cross-compiler golden failure |
| `P005-AGR-014` | Field encoded through raw enum storage | cross-compiler golden failure |
| `P005-AGR-015` | Full projection digest matches while one field differs through faulted digest implementation | field comparator still reports divergence |

### 20.4 Cache tests

| ID | Test | Required result |
|---|---|---|
| `P005-CAC-001` | Enumerate every reached cache | no unclassified cache |
| `P005-CAC-002` | Clear one derived cache | underlying authoritative projection unchanged |
| `P005-CAC-003` | Rebuild one derived cache | declared rebuilt fields equal |
| `P005-CAC-004` | Next command after rebuild | equal result and projection |
| `P005-CAC-005` | Next tick after rebuild | equal projection |
| `P005-CAC-006` | 10,000 ticks after rebuild | zero divergence |
| `P005-CAC-007` | Two independent rebuilds | equal results |
| `P005-CAC-008` | Cache validity marker left stale after clear | test detects defect |
| `P005-CAC-009` | Cache rebuild consumes RNG unexpectedly | RNG divergence detected |
| `P005-CAC-010` | Cache rebuild changes pool allocation | pool divergence detected |
| `P005-CAC-011` | Cache rebuild changes route tie result | path divergence detected |
| `P005-CAC-012` | Cache declared diagnostic but read by controller | classification failure |
| `P005-CAC-013` | Cache declared unreachable but fixture touches source path | reachability failure |
| `P005-CAC-014` | Authoritative cache omitted from projection | schema failure |
| `P005-CAC-015` | Derived cache serialized accidentally | policy failure unless ADR changes class |

### 20.5 Pool and identity tests

| ID | Test | Required result |
|---|---|---|
| `P005-ID-001` | Initial occupied slots | exact oracle values |
| `P005-ID-002` | Initial free-list order | exact oracle values |
| `P005-ID-003` | Road-stop allocation | expected slot and ID |
| `P005-ID-004` | Depot allocation when pooled | expected slot and ID |
| `P005-ID-005` | Vehicle allocation | expected slot and ID |
| `P005-ID-006` | Order allocation | expected slot and ID |
| `P005-ID-007` | Cargo packet allocation | expected slot and ID |
| `P005-ID-008` | Rejected command | no unintended allocation |
| `P005-ID-009` | Allocation-order fault injection | first exact pool field divergence |
| `P005-ID-010` | ID reuse synthetic vector | schema captures generation or reuse rule |
| `P005-ID-011` | Reference encoded as pointer | rejected |
| `P005-ID-012` | Reference to unoccupied slot | validator or invariant failure |
| `P005-ID-013` | Pool count differs from occupancy bitmap | invariant failure |
| `P005-ID-014` | Free-list contains occupied slot | invariant failure |
| `P005-ID-015` | Iteration order differs while object values match | comparator divergence |

### 20.6 Cargo conservation and ledger tests

| ID | Test | Required result |
|---|---|---|
| `P005-CAR-001` | Production creates exact cargo amount | exact source and station fields |
| `P005-CAR-002` | Station capture | packet amount and provenance match |
| `P005-CAR-003` | Loading | station decrease equals vehicle increase under native rules |
| `P005-CAR-004` | Packet split | packet IDs, amounts, and order match |
| `P005-CAR-005` | Packet merge | packet IDs, amounts, and order match native behavior |
| `P005-CAR-006` | Cargo aging | exact age fields at boundary |
| `P005-CAR-007` | Unloading | vehicle decrease and destination state match |
| `P005-CAR-008` | Accepted delivery | delivered amount matches native acceptance |
| `P005-CAR-009` | Payment | exact income and ledger category |
| `P005-CAR-010` | Packet-order swap fault | comparator detects even when total amount matches |
| `P005-CAR-011` | Packet provenance mutation | comparator detects |
| `P005-CAR-012` | One cargo unit dropped | conservation invariant detects |
| `P005-CAR-013` | One cargo unit duplicated | conservation invariant detects |
| `P005-CAR-014` | Money debit off by one | ledger divergence detects |
| `P005-CAR-015` | Income rounding off by one | ledger divergence detects |

### 20.7 Timer and RNG tests

| ID | Test | Required result |
|---|---|---|
| `P005-TIM-001` | Initial tick state | exact match across loads |
| `P005-TIM-002` | One tick advancement | exact counters |
| `P005-TIM-003` | Calendar boundary | exact rollover behavior |
| `P005-TIM-004` | Economy boundary | exact rollover behavior |
| `P005-TIM-005` | Industry production timer | exact trigger boundary |
| `P005-TIM-006` | Station loading timer | exact trigger boundary |
| `P005-TIM-007` | Vehicle controller timer or progress | exact transition boundary |
| `P005-TIM-008` | RNG stream A initial state | exact match |
| `P005-TIM-009` | RNG stream B initial state | exact match |
| `P005-TIM-010` | First draw sequence under golden run | exact optional diagnostic vector |
| `P005-TIM-011` | One extra diagnostic RNG call fault | immediate RNG divergence |
| `P005-TIM-012` | Timer field omitted | schema failure |
| `P005-TIM-013` | Timer callback order swapped in synthetic trace | comparator detects order or resulting field divergence |
| `P005-TIM-014` | Date display equal but internal fraction differs | comparator detects internal field |
| `P005-TIM-015` | 10,000-tick continuation | no timer or RNG divergence |

---

## 21. Cross-cutting invariant system

Create explicit invariant checks that run after every authoritative projection during test and oracle-debug profiles. Invariants MUST never mutate gameplay state.

### 21.1 Structural invariants

- map dimensions equal 64×64;
- every map index lies within `0..4095`;
- every stable reference targets a valid occupied object or declared null value;
- every pool occupied count equals occupancy representation;
- every free-list slot is unoccupied;
- no free-list slot appears twice;
- every allocated typed ID maps to exactly one occupied slot;
- every order list has a valid finite traversal;
- every cargo packet chain has a valid finite traversal;
- no cycle appears unless native structure explicitly uses a cycle and the schema documents the cycle;
- company, station, industry, and vehicle ownership references remain valid;
- command sequence and boundary ordinals remain monotonic.

### 21.2 Economic invariants

- command debit equals native command cost and category under reached rules;
- rejected command has no unauthorized debit;
- vehicle purchase cost appears exactly once;
- road, stop, and depot construction costs appear in native categories;
- delivered-cargo income appears exactly once;
- balance delta equals categorized ledger deltas plus any separately documented native adjustment;
- no NaN or floating rounding enters authoritative accounting;
- signed money arithmetic remains within source-established valid range for the fixture.

### 21.3 Cargo invariants

- cargo amount never becomes negative;
- packet amount equals the declared integer width and native limit;
- station plus vehicle plus delivered plus destroyed accounting follows native conservation boundaries;
- every packet has valid provenance;
- packet chain order is deterministic;
- split amounts sum to the source amount under native rules;
- merge amount equals native input sum under native limits;
- delivered amount cannot exceed unloaded accepted amount;
- payment references the correct delivered amount and distance/date inputs.

### 21.4 Determinism invariants

- identical experiment identity and command input produce identical tape bytes;
- diagnostic output location never enters authoritative bytes;
- wall clock never enters authoritative bytes;
- locale never changes authoritative bytes;
- timezone never changes authoritative bytes;
- host process order never changes per-process output;
- optional diagnostics never change authoritative projection;
- trace sink failure never produces a valid final tape;
- schema order never depends on hash-table iteration.

### 21.5 Invariant failure behavior

An invariant failure MUST:

- stop authoritative recording at the earliest safe point;
- emit a nonzero process result;
- retain the `.partial` tape;
- emit a bounded machine-readable failure artifact;
- name invariant ID, boundary, field IDs, object IDs, and last command;
- avoid running later contaminated ticks as independent evidence;
- enter the defect ledger;
- gain a regression test before closure.

---

## 22. Requirements traceability

Create `docs/testing/P0_REQUIREMENTS_TRACEABILITY.md` and a machine-readable equivalent. Map every mandatory requirement to:

- requirement ID;
- source document or standard;
- implementation file;
- test IDs;
- evidence artifact;
- gate;
- status;
- reviewer note.

No mandatory requirement may have an empty test or evidence cell at closure.

Use requirement prefixes:

- `SAFE-*` for repository, credential, host, and publication safety;
- `BUILD-*` for reference construction;
- `FIX-*` for fixture rules;
- `CMD-*` for command injection;
- `TRACE-*` for instrumentation;
- `TAPE-*` for file format;
- `CMP-*` for comparison;
- `MIN-*` for minimization;
- `FIELD-*` for schema;
- `CACHE-*` for cache policy;
- `TEST-*` for verification process;
- `EVID-*` for artifacts and reports.

Traceability lint MUST fail when:

- a required requirement lacks a test;
- a required test lacks a requirement;
- a passing requirement points to a missing artifact;
- an implementation file has no owning requirement;
- an open defect maps to a passing requirement without a reviewed exception;
- a mandatory gate uses `SKIP`.

---

## 23. Test-first implementation workflow

For every P0 module, follow the sequence below:

1. identify the source-backed behavior or format rule;
2. assign a requirement ID;
3. add or update the schema or ADR;
4. write a failing focused test;
5. confirm the test fails for the expected reason;
6. implement the minimum correct behavior;
7. run the focused test;
8. run all tests for the affected label;
9. run ASan and UBSan for affected native code;
10. run static analysis for affected files;
11. run a fuzz smoke campaign for affected byte entry points;
12. update traceability and evidence;
13. inspect the diff for scope leakage;
14. commit one coherent change;
15. push the valuable commit.

Never write several thousand lines followed by one late integration test.

### 23.1 Red-green evidence

For high-risk parser, comparator, minimizer, command, RNG, timer, and cache behaviors, retain a compact red-green record:

- test ID;
- failing revision or injected mutant;
- expected failure signature;
- passing revision;
- evidence paths.

A temporary failing revision need not enter public branch history when an injected mutant proves the red state deterministically.

### 23.2 No test weakening

Never make a failing test green through any of the following actions unless source evidence proves the original expectation wrong:

- deleting the assertion;
- broadening expected status codes;
- changing exact equality to approximate equality;
- comparing only a hash;
- ignoring a field;
- increasing a timeout without diagnosis;
- adding a retry;
- skipping a profile;
- disabling a sanitizer;
- reducing fuzz input size below the failing case;
- updating a golden file from current output without independent review;
- marking a future-relevant field diagnostic;
- changing experiment identity so comparison no longer runs;
- suppressing a static-analysis warning without source-commented proof.

When source evidence invalidates a test expectation, update the test, requirement, ADR, and rationale together.

---

## 24. Compiler, sanitizer, and analysis matrix

### 24.1 Required native build matrix

| Profile | Compiler | Optimization | Checks |
|---|---|---:|---|
| `gcc-debug` | GCC 13.x frozen path | `-O0` or `-Og` | warnings as errors for new P0 C code |
| `gcc-release` | GCC 13.x frozen path | `-O2` | normal P0 test suite |
| `clang-debug` | installed pinned Clang | `-O0` or `-Og` | warnings as errors for new P0 C code |
| `clang-release` | installed pinned Clang | `-O2` | normal P0 test suite |
| `clang-asan-ubsan` | same Clang | `-O1` | ASan + UBSan + frame pointers |
| `clang-coverage` | same Clang | suitable | source-based coverage |
| `clang-fuzz` | same Clang | suitable | libFuzzer + ASan + UBSan |

Do not combine incompatible sanitizers blindly. Record exact sanitizer options and runtime environment.

### 24.2 Required warning policy for new C code

Enable at least:

```text
-Wall
-Wextra
-Wpedantic
-Wconversion
-Wsign-conversion
-Wshadow
-Wformat=2
-Wundef
-Wcast-align
-Wstrict-prototypes
-Wmissing-prototypes
-Wwrite-strings
-Werror
```

Compiler-specific warnings MAY supplement the list. A warning disabled for a reviewed false positive requires a narrow file or line waiver with rationale.

### 24.3 ASan policy

ASan runs MUST enable leak detection when supported and MUST fail for:

- heap, stack, or global out-of-bounds access;
- use after free;
- use after return when enabled;
- use after scope;
- double free;
- invalid free;
- memory leak in test-owned or production-owned allocation;
- allocator mismatch.

### 24.4 UBSan policy

UBSan runs MUST trap or fail for every enabled undefined behavior class relevant to C17 code, including:

- signed integer overflow;
- invalid shift;
- out-of-bounds index;
- null pointer misuse;
- misaligned access;
- invalid conversion where enabled;
- unreachable behavior;
- invalid enum assumptions in glue code where supported.

No sanitizer recovery may allow a gate to report `PASS` after a finding.

### 24.5 Static analysis

Run:

- Clang-Tidy with a committed check list and warnings as errors;
- Clang Static Analyzer;
- compiler warnings under GCC and Clang;
- ShellCheck for Bash;
- JSON Schema validation;
- semantic manifest and registry lint;
- secret scanning;
- license and provenance checks;
- banned-pattern scan for raw struct writes, pointer serialization, `eval`, unsafe temporary paths, and TODO markers.

Every finding must be fixed or receive a narrow, source-commented, reviewed waiver. Final P0 report lists every active waiver. Target active waiver count: zero.

---

## 25. Differential-testing campaign

Differential testing has two layers.

### 25.1 External differential layer

Compare repeated pinned OpenTTD oracle runs under identical identity. Required corpora:

- no-action idle continuation;
- golden legal construction sequence;
- each accepted command in isolation when fixture preconditions allow;
- each rejected command case in isolation;
- complete route construction;
- vehicle purchase and orders;
- start and movement;
- production and station capture;
- loading and unloading;
- accepted delivery and payment;
- 10,000-tick continuation;
- optional diagnostic features on and off.

### 25.2 Internal differential layer

Compare production C17 tape tooling against the independent Python decoder for:

- file validity;
- prefix values;
- header canonicality;
- record offsets;
- record count;
- boundary values;
- projection field values;
- trailer values;
- SHA-256;
- malformed-case classification family;
- minimized-prefix validity.

Exact error wording may differ. Error family, byte offset where defined, and acceptance or rejection must agree.

### 25.3 Randomized command-prefix differential tests

Generate bounded legal and illegal command prefixes from the frozen command set. Generation MUST:

- use a reproducible 64-bit seed;
- respect fixture identity;
- draw from exact typed command schemas;
- include edge coordinates and exact money boundaries;
- include legal and illegal ownership contexts;
- include duplicate construction attempts;
- include route-disconnecting attempts when safely representable;
- include start/stop and order variations within P0 command breadth;
- cap commands and ticks;
- record the generated command input and seed;
- rerun every failure;
- minimize every failure;
- retain minimized corpus.

P0 release minimum:

- 10,000 generated command prefixes;
- at least 30 percent deliberately invalid prefixes;
- all oracle runs deterministic across two repeats;
- every accepted or rejected native result structurally valid;
- zero trace invariant failure;
- zero tape validation failure;
- zero unexplained nondeterminism.

Randomized prefixes do not prove scalar parity because no scalar backend exists during P0. The campaign validates oracle harness behavior, command framing, rejection capture, determinism, and failure localization.

---

## 26. Fault-injection campaign

Create deterministic fault injection at the tooling boundary. Avoid arbitrary source corruption during normal runs.

### 26.1 Required fault classes

- wrong source commit identity;
- wrong fixture digest;
- wrong settings digest;
- wrong content digest;
- wrong schema digest;
- bad tape magic;
- unsupported version;
- nonzero reserved field;
- truncated file at every byte for small golden tapes;
- sampled truncation around every structural boundary for large tapes;
- one-bit corruption in each file region;
- length overflow;
- count mismatch;
- sequence mismatch;
- field omission;
- duplicate field;
- wrong field type;
- wrong signedness interpretation;
- wrong element count;
- map tile count mismatch;
- pool occupancy mismatch;
- cargo packet order swap;
- one-unit cargo loss;
- one-unit ledger error;
- timer increment error;
- RNG state error;
- route choice error;
- trace short write;
- trace disk full;
- output permission denial;
- final rename failure;
- comparator output failure;
- minimizer interruption.

### 26.2 Fault-injection limitations

- Fault injection MUST compile only under a dedicated test option or live in standalone tools.
- Release binaries MUST not expose a hidden gameplay mutation interface.
- Fault IDs and parameters MUST be explicit and versioned.
- Every fault MUST target one requirement.
- Every fault MUST have one expected earliest failure signature.
- A fault must never modify source or fixture files in place.
- A faulted artifact must carry a clearly nonauthoritative marker outside experiment identity.

---

## 27. CI contract

Create `.github/workflows/p0-oracle-contract.yml` for the user-controlled repository only.

### 27.1 CI jobs

At minimum, define:

1. `format-and-policy`;
2. `manifest-schema`;
3. `gcc-unit`;
4. `clang-unit`;
5. `asan-ubsan`;
6. `static-analysis`;
7. `coverage`;
8. `fuzz-smoke`;
9. `reference-build-and-99-tests`;
10. `fixture-validation`;
11. `oracle-determinism`;
12. `comparator-injection`;
13. `p0-final-gate`.

### 27.2 CI limitations

- Pin action revisions by full commit SHA.
- Pin container images by digest when containers are used.
- Never use a floating third-party action tag for a security-sensitive step.
- Use least-privilege permissions.
- Default repository contents permission to read.
- Grant artifact upload permission only where required.
- Never expose repository secrets to pull requests from forks.
- Never print secrets.
- Never cache credentials.
- Cache only content-addressed dependency or build data with explicit keys.
- A cache hit never substitutes for hash verification.
- Upload failing logs, minimized inputs, JUnit XML, coverage reports, and gate JSON.
- Retain enough raw artifacts for diagnosis under repository policy.
- CI must fail when no tests are found.
- CI must fail when a mandatory job skips.
- Final gate depends on every mandatory prior job.
- CI does not replace local clean-checkout reproduction on the declared Vast.ai profile.

### 27.3 Release versus smoke profiles

CI MAY run a bounded fuzz smoke profile and a smaller repeated-recording count. The local P0 release gate MUST run the full campaign. Machine-readable results must distinguish `ci-smoke` and `local-release` profiles. A smoke profile never satisfies release closure alone.

---

## 28. Evidence and artifact contract

Create `docs/decisions/0006-evidence-and-release-policy.md`.

### 28.1 Required evidence bundle

The final P0 evidence bundle MUST contain:

- preflight output;
- repository and submodule identity;
- source register;
- all ADRs;
- toolchain manifest;
- dependency manifest;
- build manifests;
- CMake cache export;
- full CTest JSON inventory;
- full CTest JUnit result;
- upstream test log;
- headless smoke log;
- OpenGFX digest evidence;
- fixture manifest;
- normalized settings;
- command-input file and digest;
- instrumentation patch series and series digest;
- plain and instrumented executable digests;
- two byte-identical golden oracle tapes or a content-addressed external location plus verified digest when file size exceeds repository policy;
- non-perturbation comparison reports;
- malformed-corpus inventory;
- comparator injected-divergence report;
- minimized divergence prefix;
- field schema and digest;
- command schema and digest;
- cache experiment reports;
- 10,000-tick continuation reports;
- sanitizer logs;
- static-analysis logs;
- fuzz campaign summaries and corpus digests;
- coverage report;
- mutation report;
- requirements traceability;
- final gate JSON;
- human completion report;
- clean-tree and pushed-branch proof.

### 28.2 Artifact naming

Use content-addressed or run-identity names. Never use only `latest`, `final`, `new`, or a wall-clock date as unique identity.

Recommended pattern:

```text
<artifact-kind>-<profile>-<identity-prefix>-<sha256-prefix>.<extension>
```

### 28.3 Raw failure retention

During development, retain:

- first failing tape;
- minimized tape;
- command input;
- seed;
- logs;
- sanitizer output;
- stack trace;
- source and build identities;
- exact reproduction command.

Never retain only a screenshot or prose summary.

### 28.4 Repository size policy

- Commit schemas, scripts, ADRs, compact manifests, small golden vectors, minimized regression cases, and compact reports.
- Compress large text logs deterministically when repository policy allows.
- Store large passing tapes and bundles as release assets or approved content-addressed artifacts when Git size policy requires external storage.
- Record external artifact URL, immutable digest, size, and retrieval procedure.
- Never depend on an expiring local `/workspace` file as the only copy.
- Never commit OpenGFX unless asset-distribution obligations and repository policy explicitly approve the copy.

### 28.5 Result vocabulary

Every gate result MUST use exactly:

- `PASS`;
- `FAIL`;
- `SKIP` with reason and profile.

Mandatory P0 release gates accept only `PASS`. A `SKIP` never counts as completion.

---

## 29. Defect and divergence ledger

Create a machine-readable ledger and a human view. Every entry MUST include:

- stable defect or divergence ID;
- discovery date diagnostic;
- discovering test ID;
- source and build identity;
- fixture identity;
- command-input identity;
- earliest boundary;
- field ID or subsystem;
- expected value;
- observed value;
- minimized reproducer;
- impact;
- root cause;
- owner;
- fix revision;
- regression test;
- closure evidence;
- status.

Allowed status values:

- `OPEN`;
- `DIAGNOSED`;
- `FIXED_PENDING_GATE`;
- `CLOSED`;
- `REJECTED_NOT_A_DEFECT` with evidence.

P0 closure requires zero `OPEN`, zero `DIAGNOSED`, and zero `FIXED_PENDING_GATE` entries for P0 scope.

Never delete a closed entry. Preserve history.

---

## 30. Performance and resource limitations during P0

P0 performance measurements serve only resource safety and regression diagnosis.

### 30.1 Allowed measurements

- build duration;
- test duration;
- tape byte count;
- record count;
- average projection byte count;
- peak resident memory;
- parser throughput for capacity planning;
- comparator throughput for capacity planning;
- trace overhead diagnostic;
- disk usage;
- fuzz executions per second diagnostic.

### 30.2 Forbidden performance claims

Do not claim:

- OpenTTD gameplay speedup;
- GPU speedup;
- RL environment throughput;
- environments per second;
- training acceleration;
- scalar C performance;
- CUDA occupancy;
- whole-game performance.

No later backend exists during P0.

### 30.3 Resource safety gates

- Parser memory use must remain bounded by configured limits.
- Comparator must stream or bound retained state for large tapes.
- Minimizer must avoid copying an entire 1 TiB theoretical tape into memory.
- Fuzz targets must cap input size and work.
- Trace sink must fail cleanly before disk exhaustion corrupts unrelated files.
- Generated artifacts must remain under one declared root.
- CI artifact upload must use explicit size limits.
- No process may spawn unbounded children.
- No test may hang without a timeout.

---

## 31. Commit and push plan

Use atomic commits. The following sequence is recommended:

1. `docs(p0): freeze scope authority and publication basis`;
2. `build(p0): add manifest schemas and strict runner foundation`;
3. `build(p0): reproduce pinned OpenTTD and lock 99-test inventory`;
4. `test(p0): add drift negative tests and clean-build evidence`;
5. `fixture(p0): record road-freight selection and freeze inputs`;
6. `test(p0): validate fixture structure settings and reachability`;
7. `oracle(p0): add trace sink and run identity patch`;
8. `oracle(p0): add native command-boundary recording`;
9. `oracle(p0): add complete global map timer and RNG projection`;
10. `oracle(p0): add pool vehicle order cargo and ledger projection`;
11. `parity(p0): add tape v1 codec and strict validator`;
12. `parity(p0): add independent decoder and golden vectors`;
13. `parity(p0): add first-divergence comparator and reports`;
14. `parity(p0): add valid-prefix minimizer and fault injection`;
15. `schema(p0): freeze field registry and cache policy`;
16. `test(p0): add fuzz sanitizer coverage and mutation gates`;
17. `ci(p0): add full oracle-contract workflow`;
18. `docs(p0): publish evidence traceability and completion report`.

A smaller or larger count is acceptable when each commit remains coherent. Never place all P0 work in one opaque commit. Never push a commit known to contain a secret, corrupted fixture, broken build, or dirty submodule pointer.

After each valuable commit:

- run focused tests;
- inspect staged diff;
- scan for secrets;
- verify submodule identity;
- push the branch;
- record the pushed commit in progress evidence.

---

## 32. P0 top-level gate command

Provide one command:

```bash
./oracle/runner/p0_gate.sh --profile local-release
```

The command MUST execute all mandatory P0 gates in dependency order and MUST stop on the first root failure after preserving evidence.

Recommended ordered stages:

1. repository preflight;
2. policy and secret checks;
3. manifest and schema validation;
4. GCC and Clang harness builds;
5. unit and golden tests;
6. sanitizer tests;
7. static analysis;
8. coverage gate;
9. mutation gate;
10. fuzz release campaign;
11. clean reference build A;
12. clean reference build B;
13. 99-test inventory comparison;
14. all 99 upstream tests;
15. headless smoke;
16. fixture validation;
17. patch application;
18. instrumented build;
19. command-input validation;
20. oracle recording campaign;
21. byte-determinism comparison;
22. non-perturbation comparison;
23. tape independent-decoder cross-check;
24. injected identity mismatch;
25. injected command mismatch;
26. injected field mismatch;
27. prefix minimization;
28. cache clear and rebuild experiments;
29. 10,000-tick continuation;
30. requirements traceability lint;
31. evidence-bundle validation;
32. clean-tree and branch-push verification;
33. final machine result;
34. final human report.

### 32.1 Gate failure semantics

On failure, the top-level command MUST:

- return nonzero;
- stop later contaminated gameplay work;
- retain all completed prior evidence;
- retain failing raw artifacts;
- produce one root-failure summary;
- name the exact failed stage and test;
- provide the exact rerun command;
- avoid deleting a failing `.partial` tape;
- avoid marking later stages `PASS`;
- mark unrun stages `SKIP` with dependency reason in the failed run report only;
- preserve mandatory closure status as incomplete.

### 32.2 Gate idempotence

Running the gate twice against unchanged inputs MUST:

- leave tracked source unchanged;
- produce equal authoritative identities;
- produce equal golden tape bytes;
- produce equal test inventory;
- produce equal machine result content after diagnostic timestamps are excluded from identity;
- avoid overwriting prior evidence without explicit content-addressed equality;
- avoid leaking temporary worktrees.

---

## 33. Final completion report

Create `docs/P0_COMPLETION_REPORT.md` with the following exact sections:

1. **Outcome** — `PASS` or `FAIL` only;
2. **Scope completed** — `PORT-001` through `PORT-005`;
3. **Scope deliberately absent** — `PORT-006` and later;
4. **Source identities**;
5. **Repository visibility and license basis**;
6. **Reference build profile**;
7. **99-test evidence**;
8. **Headless smoke evidence**;
9. **Fixture definition**;
10. **Command-input definition**;
11. **Instrumentation patch series**;
12. **Tape v1 definition**;
13. **Determinism evidence**;
14. **Non-perturbation evidence**;
15. **Comparator and minimizer evidence**;
16. **Field schema summary**;
17. **Cache-policy evidence**;
18. **Sanitizer results**;
19. **Fuzz results**;
20. **Coverage results**;
21. **Mutation results**;
22. **Static-analysis results**;
23. **Open defect and divergence count**;
24. **Evidence bundle location and digest**;
25. **Git branch and final commit**;
26. **Exact next allowed task** — `PORT-006` only after full `PASS`.

No marketing language belongs in the report. No claim may exceed the frozen road-freight fixture and P0 tooling.

---

## 34. Final machine result

Emit `evidence/p0/P0_GATE_RESULT.json` validated against a committed schema. Required top-level fields:

```json
{
  "schema_version": 1,
  "profile": "local-release",
  "status": "PASS",
  "source_identity": {},
  "build_identity": {},
  "fixture_identity": {},
  "command_identity": {},
  "field_schema_identity": {},
  "tape_format": {"major": 1, "minor": 0},
  "gates": [],
  "tests": {},
  "artifacts": [],
  "open_defects": 0,
  "open_divergences": 0,
  "final_commit": "",
  "branch": "port/p0-oracle-contract"
}
```

The actual object requires complete schema-defined contents. The `status` field may equal `PASS` only when every mandatory gate equals `PASS`, all artifact digests verify, open counts equal zero, and branch-push proof succeeds.

---

## 35. Absolute prohibitions

The implementation agent MUST NOT:

1. change the pinned OpenTTD commit;
2. edit the pinned submodule in place and leave changes behind;
3. begin scalar gameplay translation;
4. write CUDA;
5. add PPO or any RL algorithm;
6. invent simplified game rules;
7. treat visual plausibility as parity;
8. use final-state hash equality as the sole parity proof;
9. serialize raw C or C++ structs;
10. serialize pointers;
11. serialize host-dependent widths;
12. omit pool free-list or iteration state when future IDs can depend on those values;
13. omit RNG stream state;
14. omit timer fractions or callback state merely because displayed dates match;
15. call RNG for logging;
16. call pathfinding for logging;
17. call a mutating lazy getter for logging;
18. inject commands through direct state mutation;
19. drive the fixture through GUI clicks;
20. rely on user configuration directories;
21. allow NewGRFs;
22. use a network service during authoritative replay;
23. continue after a trace write failure;
24. promote an incomplete tape;
25. accept trailing tape bytes;
26. accept nonzero reserved bits;
27. allocate from untrusted lengths before limit and overflow checks;
28. handwrite a cryptographic primitive;
29. use approximate numeric comparison for authoritative integer state;
30. hide a mismatch through field filtering;
31. compare experiments with different identity as though gameplay diverged;
32. report multiple contaminated later mismatches as independent root causes;
33. minimize a tape without revalidating the output;
34. update golden files blindly from production output;
35. weaken a test to achieve green status;
36. skip a mandatory sanitizer, fuzz, coverage, mutation, or determinism gate;
37. suppress a warning without a narrow reviewed rationale;
38. add a silent fallback;
39. catch and ignore an I/O or parse error;
40. return success after any mandatory failure;
41. print or commit a credential;
42. change repository visibility without authorization;
43. submit generated work upstream;
44. install or alter NVIDIA drivers;
45. install the apt `cuda` metapackage;
46. commit OpenGFX without explicit distribution review;
47. claim full OpenTTD support;
48. claim CUDA readiness;
49. claim scalar parity;
50. stop after documentation or partial scaffolding while a P0 gate remains incomplete.

---

## 36. Required final verification checklist

Before declaring completion, verify every checkbox through an executable test or evidence artifact.

### Repository and policy

- [ ] P0 branch differs from `main`.
- [ ] Branch is pushed.
- [ ] Working tree is clean.
- [ ] Submodule is clean.
- [ ] Submodule commit matches the pin.
- [ ] No secret scan finding remains.
- [ ] Repository visibility is documented.
- [ ] GPL basis is documented.
- [ ] No upstream submission occurred.
- [ ] No later-phase code exists.

### `PORT-001`

- [ ] Source manifest validates.
- [ ] Toolchain manifest validates.
- [ ] Dependency manifest validates.
- [ ] Build manifest validates.
- [ ] Test inventory manifest validates.
- [ ] OpenGFX manifest validates.
- [ ] OpenGFX archive digest matches.
- [ ] Clean build A passes.
- [ ] Clean build B passes.
- [ ] Exactly 99 upstream tests are discovered.
- [ ] All 99 tests pass.
- [ ] JUnit and raw logs exist.
- [ ] Headless 128-tick smoke passes.
- [ ] Drift tests fail closed.

### `PORT-002`

- [ ] Fixture ADR is complete.
- [ ] Fixture save digest matches.
- [ ] Map is exactly 64×64.
- [ ] NewGRF list is empty.
- [ ] One human company exists.
- [ ] Producer and acceptor match declared IDs and tiles.
- [ ] Cargo compatibility is source-proven.
- [ ] Vehicle availability is source-proven.
- [ ] Coordinates are exact and in bounds.
- [ ] Route is connected and within scope.
- [ ] Opening funds are sufficient.
- [ ] Normalized settings validate and hash.
- [ ] Two independent initial loads match.
- [ ] Native replay reaches first pickup.
- [ ] Native replay reaches first delivery.
- [ ] Native replay reaches first payment.

### `PORT-003`

- [ ] Patch series applies cleanly.
- [ ] Patch series reverses cleanly.
- [ ] Plain build passes.
- [ ] Instrumented-off build passes.
- [ ] Instrumented-on run passes.
- [ ] Native command input fully validates before replay.
- [ ] Every action uses native command dispatch.
- [ ] Command test and execute results are captured.
- [ ] Full projection follows every command.
- [ ] Full projection follows every tick.
- [ ] Both RNG states appear at every boundary.
- [ ] Required timer state appears at every boundary.
- [ ] All 4,096 tiles appear in canonical order.
- [ ] Reached pools include occupancy and free-list state.
- [ ] Trace I/O failure tests pass.
- [ ] Twenty serial recordings have one digest.
- [ ] Eight isolated parallel recordings have one digest.
- [ ] Plain versus instrumented-off continuation matches.
- [ ] Instrumented-off versus instrumented-on continuation matches.
- [ ] 10,000-tick continuation matches.

### `PORT-004`

- [ ] Tape ADR is complete.
- [ ] Tape v1 golden hex vector is reviewed.
- [ ] C17 writer passes GCC and Clang tests.
- [ ] C17 parser passes GCC and Clang tests.
- [ ] Independent Python decoder agrees.
- [ ] Every-byte truncation tests pass for small vectors.
- [ ] Region corruption tests pass.
- [ ] Canonical-header tests pass.
- [ ] Reserved-zero tests pass.
- [ ] Sequence tests pass.
- [ ] Trailer and SHA-256 tests pass.
- [ ] Equal tapes compare equal.
- [ ] Identity mismatch returns exit `2`.
- [ ] Injected field mismatch returns exit `1`.
- [ ] Earliest field and boundary are exact.
- [ ] Machine divergence report validates.
- [ ] Minimized prefix validates.
- [ ] Minimized prefix reproduces the same divergence.
- [ ] Fuzz release counts pass.
- [ ] Coverage thresholds pass.
- [ ] Every seeded mutant is killed.

### `PORT-005`

- [ ] Field-schema ADR is complete.
- [ ] Field registry validates.
- [ ] Field IDs are unique.
- [ ] Field paths are unique or explicitly deprecated aliases.
- [ ] Every entry has owner and lifecycle.
- [ ] Every entry has source evidence.
- [ ] Every entry has future-influence rationale.
- [ ] Every entry has sample bytes and test ID.
- [ ] Every reached global field is classified.
- [ ] Every reached timer is classified.
- [ ] Both RNG streams are classified.
- [ ] Every reached map plane is classified.
- [ ] Every reached pool is classified.
- [ ] Every reached vehicle and order field is classified.
- [ ] Every reached cargo packet field is classified.
- [ ] Every reached ledger field is classified.
- [ ] Every reached cache is classified.
- [ ] Every derived cache rebuild passes immediate comparison.
- [ ] Every derived cache rebuild passes 10,000-tick continuation.
- [ ] Every unreachable claim has source-backed proof.
- [ ] Deliberate omission tests detect faults.
- [ ] No placeholder remains.

### Cross-cutting quality

- [ ] Requirements traceability has no gap.
- [ ] ASan has no finding.
- [ ] UBSan has no finding.
- [ ] Clang-Tidy has no unwaived finding.
- [ ] Clang Static Analyzer has no unwaived finding.
- [ ] GCC warnings are zero for new P0 code.
- [ ] Clang warnings are zero for new P0 code.
- [ ] ShellCheck findings are zero or narrowly reviewed.
- [ ] Coverage gate passes.
- [ ] Mutation gate passes.
- [ ] Fuzz gate passes.
- [ ] CI mandatory jobs pass.
- [ ] Evidence bundle validates.
- [ ] Evidence bundle digest verifies.
- [ ] Open defect count equals zero.
- [ ] Open divergence count equals zero.
- [ ] Final machine result equals `PASS`.
- [ ] Final human report contains no overclaim.

---

## 37. Required progress behavior

The implementation agent must work continuously through failures rather than stopping after the first obstacle. For each failure:

1. preserve the earliest failing artifact;
2. identify the owning requirement;
3. minimize the reproducer;
4. inspect pinned source or official specification;
5. fix the root cause rather than the symptom;
6. add a regression test;
7. rerun the focused gate;
8. rerun every dependent gate;
9. update evidence and ledger;
10. continue to the next unmet requirement.

Do not ask for approval for reversible implementation details already constrained by the contract. Do not pause after producing a plan. Do not report completion while any mandatory item remains `FAIL`, `SKIP`, absent, stale, unverified, or undocumented.

When an external condition truly blocks execution, such as lost repository access or unavailable required source bytes, preserve all evidence and produce a precise blocked report. A blocked report never equals completion and never permits a false `PASS`.

---

## 38. Final command to the implementation agent

Execute the full P0 oracle-contract phase now. Work only on `PORT-001` through `PORT-005`. Preserve the pinned source. Build the oracle before any port. Handwrite the correctness-critical harness with strict C17 and reviewable C++ instrumentation. Use pinned OpenTTD behavior as the external authority. Use independent decoders, differential tests, fault injection, sanitizers, fuzzing, coverage, mutation tests, cache-erasure experiments, and 10,000-tick continuation evidence. Retain raw artifacts. Commit and push atomic progress. Never weaken a gate. Never overclaim scope.

Do not stop until the entire P0 oracle-contract deliverable is completely done.
