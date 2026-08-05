# V2 Verification Refactor Design

**Status:** Approved direction

**Date:** 2026-08-05

**Objective:** Shorten and stabilize the development feedback loop on the path to
M23/G23 without reducing any frozen Version 2 requirement, mutation, retained
failure, package identity, campaign, or release invariant.

## Context

The repository is accepted through G22 and has a nonaccepting M23 controller
foundation. The next product work is command-bearing visible gameplay,
controller persistence, eight visible campaigns, two clean-root reproductions,
and publication. The current verification machinery makes that work slower and
less reliable than necessary:

- `scripts/v2/verify.sh` mixes pure unit checks, committed-record validation,
  host-bound live artifacts, native builds, and the V1 regression in one path.
- 29 V2 test files contain 50 hard-coded references to another user's
  `/home/thecl/.codex/artifacts` tree.
- A clean checkout can run the 80 focused M23 tests, but raw full V2 discovery
  cannot distinguish missing retained artifacts from product failures.
- Builders, standalone validators, and repository-pass unit tests repeat the
  same committed-record checks.
- M22 final/follow-up/follow-up-v2 tests and validators copy substantial setup,
  source hashing, report construction, statistics, and mutation logic.
- M23 package and in-game mutation tests repeatedly rebuild identical golden
  corpora and package fixtures.
- Static source-token tests sometimes restate invariants already proven by
  stronger source hashes or semantic validators.

This refactor is the first of three bounded programs:

1. portable tiered verification and shared test infrastructure;
2. command-bearing normal-game executors plus save/load restoration;
3. G23 evidence, reproduction, release transaction, and publication.

Each program receives its own implementation plan and review loop. This design
covers only program 1 while freezing the interfaces needed by programs 2 and 3.

## Non-negotiable invariants

- All 86 V2 requirements remain in scope. The nine `V2-RELEASE-*` rows remain
  `PLANNED` until actual G23 evidence exists.
- Final-v1 and follow-up-v1 remain immutable `FAIL`; follow-up-v2 remains the
  accepted G22 `PASS`. No suite may be retried, replaced, relabeled, or edited.
- Every current mutation category remains exercised with a stable, reviewable
  label, including source/artifact identity, exact case counts, one manifest
  read, zero retry/replacement, public/private separation, statistics, package
  corruption, recurrent state, and fail-closed behavior.
- Checkpoint IDs, package formats, golden corpus, three runtimes, tolerances,
  campaign identities, and V1 bytes do not change.
- `scripts/v2/verify.sh` with no tier argument remains the complete fail-closed
  release gate. A faster tier can never produce a G23 or release claim.
- Missing live artifacts are never interpreted as passing evidence. They are
  outside the fast/contract tier and a hard preflight failure in the full tier.
- Immutable evidence files retain their recorded paths and bytes. Relocation
  affects only how validators find files on the current host.

## Considered approaches

### Selected: layered verification before runtime expansion

Create explicit fast, contract, and full tiers; centralize host context; remove
duplicate passes; consolidate copied fixtures; and cache immutable synthetic
M23 inputs. This adds a small amount of runner structure now and gives every
remaining G23 work package a portable, quick, trustworthy feedback loop.

### Rejected: implement executors first and clean tests opportunistically

This produces a visible command sooner, but every runtime slice would continue
to depend on hard-coded paths, skipped patch application, duplicated validators,
and static token checks. Failures would remain difficult to classify and the
same cleanup would be paid repeatedly.

### Rejected: reduce or rewrite the frozen M23/G23 contract

This would shorten the project only by changing its definition of done. It would
invalidate preregistration and accepted evidence boundaries and would not satisfy
the stated goal of completing all V2 requirements.

## Verification architecture

### Single entry point

`scripts/v2/verify.sh` remains the public shell entry point. It accepts:

```text
scripts/v2/verify.sh [--tier fast|contract|full]
                     [--tools-python /absolute/python]
                     [--artifact-root /absolute/openttd-rl-artifacts]
```

The default tier is `full`. The shell performs argument validation and delegates
the ordered inventory to a Python driver so command selection, preflights, and
result reporting are data-driven rather than a 50-command shell sequence.

The Python driver exposes the same tier operations as importable functions so
unit tests can validate inventories and failure classification without spawning
the complete gate.

### Fast tier

The fast tier contains only deterministic tests over repository files and
synthetic temporary fixtures. It performs no retained-artifact traversal, no
OpenTTD source build, no real evaluator/package invocation, and no V1 release
verification.

It includes:

- pure schema, canonical JSON, statistics, manifest, and mutation logic;
- synthetic M15-M23 contract and validator tests;
- test-driver inventory and preflight tests;
- M23 golden/package/report tests using shared immutable fixtures;
- source-scope guards that do not require an external composed source tree.

The tier must run from a normal checkout with Python alone. It provides local
development feedback only and prints `V2_VERIFY_TIER=fast`, never a gate status.

### Contract tier

The contract tier runs the fast tier plus each committed-record validator exactly
once in offline mode. It verifies canonical bytes, source inventories and hashes
available in the checkout, accepted historical statuses, requirement/defect
traceability, and every mutation that does not require live retained files.

Offline mode validates the immutable record and its declared artifact inventory
but does not dereference the record's original absolute artifact path. Validators
that currently enter a transitive live traversal gain an explicit offline/live
boundary rather than relying on path existence or implicit skips.

The contract tier requires an initialized pinned OpenTTD submodule only for
validators whose frozen source authority genuinely needs it. Its preflight names
that requirement before any validator runs. It prints
`V2_VERIFY_TIER=contract`, never a G23 status.

### Full tier

The full tier runs contract verification, then all host-bound and native evidence:

- live retained-artifact rehash and semantic validation;
- patch-series application, strict build, upstream CTests, and dependency closure;
- real checkpoint load/resume, exporter, package, mutation, and three-runtime
  equivalence commands as they become available;
- visible campaign, controls, fault, and save/load evidence as M23 adds them;
- two-root reproduction and release-asset checks at the final boundary;
- unchanged V1 traceability.

Before execution, full performs one complete artifact/source/tool inventory
preflight. Missing inputs fail with a categorized list; no test silently skips a
mandatory live check. The full tier is the only tier eligible to report a gate
result.

## Host and artifact context

A shared context module owns repository root, initialized OpenTTD source,
artifact root, temporary root, tool paths, and validation mode.

Resolution order is:

1. explicit CLI argument;
2. documented `OPENTTD_RL_ARTIFACT_ROOT` environment variable;
3. no artifact root.

Tests use temporary contexts or an explicit root. They do not embed a user home
or assume `.codex`. Full validators receive a resolved root explicitly.

When a frozen JSON record contains `/home/thecl/...`, the validator continues to
validate that recorded string and all committed bytes. A live validation context
may map its logical artifact-set name to a different host root for filesystem
reads. The mapping cannot rewrite, resign, or canonicalize the frozen record.

## Test and validator consolidation

### Authoritative repository passes

The tier inventory invokes each standalone committed-record validator once.
Unit tests retain mutation and error-class behavior but stop repeating an
identical repository-pass invocation. Standalone manifest builders are removed
from the gate when their validator already rebuilds and byte-compares the same
manifest.

The follow-up-v1 validator's expected exit status remains exactly `2`; an
unexpected pass or a different failure remains a gate failure.

### Shared M22 harness

Shared test support provides:

- canonical temporary-file writers;
- final/follow-up/follow-up-v2 fake case, run, and aggregate factories;
- mutation execution with named `subTest` labels;
- expected immutable-boundary and status policies;
- artifact-context fixtures.

Shared validator support owns only mechanical primitives: Git/source inventory
hashing, report digests, common protocol counts, and common statistics. Thin
suite-specific validators keep their schema, exception type, immutable inputs,
failure classifications, and acceptance function. Parameterization makes the
v1/v2 differences data rather than conditional branches that can blur their
distinct statuses.

### Shared M23 fixtures

M23 tests generate the 48-case/580-row golden corpus once per test class. Package
tests create one canonical package per architecture and clone it into an isolated
temporary directory before each mutation. In-game report tests deep-copy a
validated immutable report template. Filesystem-specific mutations such as
symlink, missing file, unknown file, and truncation remain isolated.

All 28 package/runtime rejection labels and every current in-game report mutation
remain individually observable.

### Static versus behavioral assertions

A source-token assertion is removed only when an identified stronger check proves
the same invariant:

- exact source inventory/hash plus semantic recomputation may replace source
  ordering or literal spelling assertions;
- a behavior test may replace an implementation-token assertion;
- no static visible-controller guard is removed until the later runtime program
  adds applied-source and normal-game behavior evidence for that invariant.

The refactor therefore does not pretend the current no-op controller is working
gameplay. Runtime program 2 will replace `NO_OP_DISCOVERY` guards with real
command, outcome, control, and persistence tests.

## Data flow

```text
verify.sh
  -> validated CLI and tier
  -> verification driver inventory
  -> host/artifact context preflight
  -> selected unit/validator/native commands
  -> categorized per-command records
  -> tier summary

fast     -> synthetic repository behavior only
contract -> fast + one offline pass per frozen validator
full     -> contract + relocated live evidence + native/V1/release gates
```

The driver stops on an infrastructure preflight failure before partial gate
execution. After preflight, validator or test failures are retained in the
summary with their command, exit status, tier, and category. Historical expected
failure is represented as an explicit expected-status rule, not shell control
flow that conflates it with a crash.

## Error handling

- Invalid tier, Python path, artifact root, or submodule state exits `2` with a
  specific preflight category.
- Fast/contract code attempting a live artifact access is a test-driver defect
  and fails the tier.
- Full missing artifacts fail preflight; mandatory live tests never skip.
- A validator exception, unexpected exit, timeout, or noncanonical output is a
  command failure and cannot be converted to a skip.
- Expected historical `FAIL` means the validator completed semantically and
  returned its frozen status code. Missing files or exceptions are never accepted
  as that expected result.
- Shared fixture caching uses immutable base data and per-test copies so one
  mutation cannot contaminate another.

## Success criteria

1. No V2 test file contains a hard-coded `/home/thecl` or `.codex/artifacts`
   lookup. Immutable record contents and historical prose may retain them.
2. Fast passes from this checkout without retained artifacts or the OpenTTD
   submodule and emits no G23/release claim.
3. Contract passes from a recursive clean clone without retained artifacts and
   validates every frozen offline invariant exactly once.
4. Full is the default, requires explicit live inputs, runs V2 plus unchanged V1,
   and fails before testing when required inputs are absent.
5. The final/follow-up/follow-up-v2 case counts, manifest-read counts,
   retry/replacement rules, statuses, statistics, source identities, and mutation
   labels remain identical.
6. All M23 package, graph, recurrence, corruption, batch, and in-game report
   mutations remain independently rejected.
7. Duplicate repository-pass tests and redundant manifest-builder gate processes
   are removed only after the authoritative invocation is covered by tier
   inventory tests.
8. On the same host, the median of three focused M23 test runs is at least 30%
   faster than the recorded 8.18-second baseline, without a timing assertion in
   the test suite.
9. Fast-tier inventory, contract-tier inventory, default-full selection, artifact
   relocation, expected-status handling, and fail-closed preflights have direct
   automated tests.
10. The worktree contains no changed frozen evidence JSON, checkpoint identity,
    release-contract value, accepted gate report, or V1 release artifact.

## Review and delivery strategy

Implementation is sequential to avoid agents editing shared test infrastructure
concurrently. Each task uses a fresh `gpt-5.6-sol` implementer with `xhigh`
reasoning as requested, followed by a separate `gpt-5.6-sol`/`xhigh` reviewer.
Fixes return to the original implementer and receive scoped re-review. Independent
read-only audits may still run in parallel.

The implementation plan will divide work into independently testable tasks:

1. tier inventory and fail-closed driver;
2. portable artifact context and validator offline/live boundaries;
3. authoritative-pass deduplication;
4. shared M22 fixtures and mechanical validator primitives;
5. cached M23 fixtures and safe static-test replacement;
6. complete tier verification, timing comparison, and documentation.

After this refactor passes review, the next design begins the persistent
road-passenger command executor and save/load vertical slice. It reuses the
verification tiers and does not expand or reopen this design.
