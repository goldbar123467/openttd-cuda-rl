# P0 Oracle-Contract Test Strategy

## Purpose

This strategy verifies the five P0 deliverables as one chain of authority:

```text
pinned source and content
        -> frozen fixture and native commands
        -> non-perturbing projection
        -> strict tape bytes
        -> independent validation/comparison
        -> field and cache continuation contract
```

A downstream pass cannot compensate for an upstream failure. In particular,
equal tapes do not prove that an incomplete projection is correct, and a valid
tape does not prove that instrumentation preserved OpenTTD behavior.

The only release-closing profile is `local-release`. `ci-smoke` runs the same
interfaces with bounded campaign sizes and reports its distinct profile.

## Authority and oracles

Behavioral expectations come first from pinned OpenTTD commit
`29f808ef0022064e6d9a83c8476d1e0f4686af86`, then from repeated binaries built
from that commit under the frozen profile. The production C17 tape code is not
allowed to validate itself as the sole oracle:

- manifests are checked by committed schemas and independent semantic loaders;
- tape bytes are decoded by both the C17 implementation and an independent
  Python reference;
- command results are captured at the native test and execute boundaries;
- field coverage is reviewed both from source reads/writes and backward from
  future continuation decisions;
- cache classifications require clear/rebuild/continuation experiments;
- report contents are schema-validated and cross-checked against raw tapes.

All tests use stable IDs. Range labels are permitted only as grouping labels in
reports; each mandatory assertion still has its own ID, result, evidence path,
and requirement mapping.

## Test layers

### Layer 0: repository and host safety

The preflight layer is read-only except for its declared artifact directory. It
checks outer repository identity, branch, remote, exact submodule commit and
cleanliness, tool paths and versions, Ubuntu profile, required content,
available space, and secret-safe environment handling. Negative tests exercise
wrong commits, dirty submodules, unexpected gitlinks, relative artifact roots,
symlinks, unsafe cleanup targets, missing tools, and synthetic secret canaries.

The pinned submodule is checked before and after every patch/build/recording
stage. Instrumentation is applied only to a disposable worktree.

### Layer 1: reproducible reference and fixture

Two clean reference builds use independent build/install directories and the
same frozen inputs. Tests compare configure metadata, the machine-readable
99-test inventory, installed runtime manifest, headless smoke result, and
normalized executable sections. Every one of the 99 upstream tests runs with a
timeout, `--no-tests=error`, JUnit output, and retained failure logs.

The fixture layer verifies exact save, settings, behavior-settings, content,
map-plane, and builder identities. It checks 64x64 bounds, native map planes,
company finances, no cheats, exact town/industry/engine IDs, route coordinates,
catchment, excluded scripts/NewGRFs/networking, and both RNG streams. Two
isolated configuration homes must load the fixture to the same initial
projection.

### Layer 2: command framing and native execution

The command-input file is tested as a strict versioned binary format. Primitive
tests cover endian encodings, overflow, padding, reserved bytes, canonical
header JSON, full-file checksum, action checksum, monotonic schedules, exact
typed operands, enum ranges, sentinels, and trailing-byte rejection.

Every action goes through the native typed command path. Recording proves one
intent record, one native test result, and—when the test succeeds—one native
execute result. Native rejection is a valid captured outcome for negative
corpora. Golden qualification separately asserts that every frozen golden
action succeeds with the expected returned identity, cost, expense category,
and state transition.

Compile-time trace support with no active trace must serialize zero command
result payloads. Trace-disabled and trace-enabled builds must otherwise use
equivalent options and identities.

### Layer 3: projection and instrumentation

Projection tests validate exact field order, type, element count, byte length,
owner order, nested count/offset partitions, null sentinels, and every-boundary
completeness. The adapter reads source state directly and may not call a lazy or
mutating getter. Every rejected accessor is documented in the source review.

The mandatory boundaries are replay start, post-command, and post-tick. Named
checkpoints cover route completion, first production, first station capture,
first loading, first unloading, first accepted delivery, first payment, and the
continuation end. A deterministic horizon stops after the declared final
post-tick projection and final checkpoint; wall-clock timeout is a safety net,
not normal completion logic.

Non-perturbation comparison runs uninstrumented, trace-compiled-but-disabled,
and trace-enabled binaries from isolated homes. It compares state at declared
boundaries and full continuation outcomes. Required repetition includes two
byte-equal authoritative tapes, twenty serial recordings, eight concurrent
recordings to separate outputs, no-action continuation, golden continuation,
and optional diagnostics both off and on. Diagnostic records may differ by
feature declaration; authoritative projections must not.

### Layer 4: tape, comparator, and minimizer

Tape tests are split by responsibility:

- primitive and file-prefix vectors;
- strict canonical header and identity validation;
- record framing and projection payload validation;
- trailer, counters, terminal record, and digest validation;
- streaming reader/writer resource limits;
- comparator first-divergence reports;
- valid-prefix minimization;
- CLI exit codes, stdout/stderr separation, and atomic output behavior;
- independent Python/C17 differential decoding.

Every byte-oriented C entry point has a bounded libFuzzer target. Small golden
tapes are truncated at every byte. Larger tapes are truncated around every
structural boundary and sampled internally. Corruption covers prefix, header,
records, padding, projection fields, terminal data, and trailer.

The parser, comparator, and minimizer stream large inputs with bounded memory.
Sparse-file tests near configured limits measure peak RSS and prevent a future
whole-file allocation regression.

Comparator fault tests mutate identity, command outcome, field type/count/value,
optional diagnostics, and output failures. Reports must name both tape
identities, backend/environment identities, earliest boundary/ordinal/sequence,
exact command or field metadata and values, last command, prior checkpoint,
source/cache policy, minimized prefix path/digest, and argv reproduction arrays.

The minimizer preserves the exact divergence signature: public step, native
tick, boundary kind/ordinal, sequence, record type, field and element identity,
and both differing values. It emits a valid finalized prefix and never treats a
corrupt/truncated file as a successful minimum.

### Layer 5: registry, caches, and invariants

Registry tests validate Draft 2020-12 structure plus semantics that JSON Schema
alone cannot express: unique ordered IDs and paths, valid count sources,
acyclic dependencies, exact offset-array terminal totals, sample encoding,
source anchors, stable owner rules, cache consistency, and classification
constraints. Regeneration must be byte-identical and may not silently rewrite a
reviewed registry from current source guesses.

Each accepted field receives two reviews:

1. source-owner review follows every reached read/write, helper, timer, pool,
   packet, cache, and controller path;
2. continuation review starts at future commands/ticks and traces every input
   capable of changing a branch, order, ID, cost, RNG draw, cargo movement, or
   accounting result.

Generic OpenTTD pool allocation tests preserve exact `items`, `first_free`,
`first_unused`, bitmap vector length, bitmap words, and padding bits. They
fragment pools and prove the next allocated stable ID. This is distinct from
company `FreeUnitIDGenerator`, whose own exact word-vector length and contents
are projected separately.

Every reached cache remains authoritative unless the full cache protocol proves
`derived_rebuild`: clear at an approved boundary, rebuild through production
code, compare reconstructed content where meaningful, compare the next command
and tick, run 10,000 ticks, repeat across two loads, and retain raw evidence.

Read-only invariants execute after each authoritative projection in test and
oracle-debug profiles. They cover pool/reference structure, finite order and
cargo chains, command and boundary monotonicity, categorized money deltas,
cargo conservation/provenance/order, timer progression, and determinism. An
invariant failure stops recording, leaves the partial tape, produces bounded
machine evidence, and enters the defect ledger.

## Required native build matrix

The harness uses seven distinct profiles rather than aliases for one build:

| Profile | Compiler and mode | Mandatory outcome |
|---|---|---|
| `gcc-debug` | frozen GCC 13, `-O0`/`-Og` | strict warnings, unit/golden/negative tests |
| `gcc-release` | frozen GCC 13, `-O2` | normal complete suite |
| `clang-debug` | pinned installed Clang, `-O0`/`-Og` | strict warnings, unit/golden/negative tests |
| `clang-release` | same Clang, `-O2` | normal complete suite |
| `clang-asan-ubsan` | same Clang, `-O1`, frame pointers | zero sanitizer finding/leak |
| `clang-coverage` | same Clang, source coverage | thresholds and required-branch proof |
| `clang-fuzz` | same Clang, libFuzzer + ASan/UBSan | all bounded targets complete |

New C code uses the warning set frozen in `cmake/P0Warnings.cmake`, including
conversion, sign, shadow, format, undefined-macro, alignment, prototype, and
write-string checks as errors.

## Static and policy gates

The static gate runs compiler warnings under both compilers, Clang-Tidy with a
committed checks file, Clang Static Analyzer, ShellCheck, JSON Schema plus
semantic lint, secret scanning, license/provenance checks, and banned-pattern
scans. The banned set includes raw struct/pointer/`size_t` serialization,
`eval`, unsafe temp creation, unbounded subprocesses, scope-forbidden code, and
unfinished markers. A waiver is narrow, source-commented, reviewed, listed in
the completion report, and targeted to zero at release.

## Coverage, mutation, and fuzz gates

Coverage is measured only from tests that assert behavior. Line coverage alone
cannot close branches concerning overflow, truncation, identity mismatch,
short writes, output atomicity, or first-divergence selection. Thresholds and
required functions/branches are declared in the coverage runner and cannot be
reduced in a test-fix commit without an ADR.

Mutation testing uses the reviewed operators in `P0_MUTATION_PLAN.md`. Every
required mutant must be killed by a named test. Equivalent mutants need a
source-backed review record; timeouts and build failures are not counted as
semantic kills unless the mutation specifically targets liveness/build policy.

Fuzz targets cap input bytes, allocation, records, recursion, output, and run
time. A crash, sanitizer finding, timeout, OOM, or unexpected accept becomes a
retained regression input. Corpus merge and digesting are deterministic.

## Differential campaigns

### Repeated fixed corpus

The external corpus covers idle/no-action, each frozen action, representative
native rejections, complete construction, order/start, movement, production,
capture, loading, unloading, accepted delivery, payment, 10,000 ticks, and
diagnostics off/on. Each authoritative run repeats with identical bytes.

### Randomized command prefixes

`local-release` generates 10,000 bounded typed prefixes from a recorded 64-bit
seed. At least 30 percent are deliberately invalid. The generator includes
edge coordinates, duplicate construction, legal/illegal ownership, order and
start/stop variations, exact money boundaries, and safe route-disconnection
attempts. Each prefix runs twice. Native acceptance/rejection must be
structurally valid, recordings must validate, and repeats must match. A failure
is rerun, minimized, and retained.

This campaign tests the oracle harness; it does not claim scalar-port parity.

### Internal decoder differential

The C17 and Python implementations agree on acceptance/rejection family,
structural offsets where defined, header canonicality, counters, projections,
digest, comparator boundary, and minimized-prefix validity. Exact prose error
messages need not match.

## Fault injection

Faults live in standalone tools or builds compiled with a dedicated test option.
Release binaries expose no hidden gameplay mutation interface. Each versioned
fault maps to one requirement and expected earliest signature. The campaign
covers identity drift, every tape region, arithmetic/count errors, field and
pool faults, cargo/ledger/timer/RNG/route faults, short writes, disk exhaustion,
permissions, rename/fsync/output failures, and minimizer interruption.

Fault tools copy inputs into the artifact root and never edit source, fixtures,
or golden tapes in place. Faulted outputs carry a nonauthoritative marker
outside experiment identity.

## Timeouts and resource safety

Every process has a stage-specific timeout and bounded child count. The runner
captures the process group and terminates it on failure without killing
unrelated jobs. Parser, comparator, minimizer, fuzz, and recording stages have
explicit byte, record, field, and output limits. Trace recording checks free
space before launch and fails cleanly before unrelated files are endangered.

Resource measurements—duration, tape size, records, projection size, RSS,
parser throughput, and disk usage—are diagnostic capacity data only. They do
not support gameplay, GPU, RL, or later-backend performance claims.

## Evidence and closure

Every test result records requirement IDs, exact argv, source/build/fixture/
command/schema identities, start/end diagnostic time, exit status, bounded log
paths, and artifact digests. The traceability linter rejects missing evidence,
orphan tests, orphan implementation files, passing requirements with open
defects, or release `SKIP`.

P0 closes only when the full gate succeeds twice without tracked-source changes,
the two authoritative tapes remain byte-identical, all mandatory artifacts
verify from durable storage, both Git trees are clean, and the final branch tip
is present at the remote. The next permitted implementation task is then
`PORT-006`; no later-phase code is part of this strategy.
