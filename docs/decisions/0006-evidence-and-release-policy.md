# ADR 0006: Evidence, artifact, and P0 release policy

- Status: accepted
- Decision date: 2026-07-30
- Applies to: `PORT-001` through `PORT-005`
- Governing contract: `OPENTTD_P0_ORACLE_CONTRACT_AGENT_PROMPT.md`

## Context

P0 establishes an oracle contract rather than a gameplay implementation. Its
output is trustworthy only when another engineer can connect every claim to the
exact pinned source, command input, executable, tape, test invocation, and raw
result that produced it. A green prose summary is not evidence. A locally
generated artifact with no digest or durable location is also not evidence.

The workspace on the qualifying Vast.ai instance is not backed by a persistent
volume. Large development artifacts may therefore disappear on instance
recycle. Small specifications, schemas, minimized regressions, and evidence
indexes belong in Git. Large passing tapes and raw build/test trees belong in a
caller-supplied artifact root and must be copied to an immutable,
content-addressed location before P0 can close.

Evidence generation is part of the tested product boundary. The release gate
must fail closed when it cannot write, validate, hash, retain, or publish a
mandatory artifact.

## Decision

### One authoritative release profile

`local-release` is the only profile that may close P0. `ci-smoke` is useful for
bounded feedback but cannot satisfy release-only recording counts, long fuzz
campaigns, the 10,000-prefix differential campaign, the 10,000-tick
continuation, or clean-host reconstruction. Every result records its profile;
results from different profiles are never merged to fabricate a release pass.

The release entry point is:

```bash
./oracle/runner/p0_gate.sh --profile local-release \
  --artifact-root /absolute/caller/controlled/path \
  --tools-python /absolute/hash/locked/python
```

The runner accepts only an absolute, non-repository artifact root and an
absolute interpreter path whose frozen dependency lock verifies. It creates a
unique content-derived run directory without following symlinks. It never
silently falls back to `/tmp`, the repository, the process working directory,
or a different Python installation.

### Result vocabulary and aggregation

Every stage uses exactly `PASS`, `FAIL`, or `SKIP`. A mandatory release stage
accepts only `PASS`. `SKIP` exists solely to explain dependency-blocked stages
in a failed run; it never contributes to closure.

The top-level status is computed, not supplied by a caller. It is `PASS` only
when all of these conditions hold:

1. every mandatory stage is present exactly once and equals `PASS`;
2. every declared artifact exists, is a regular file, remains below its
   configured size limit, and matches its recorded SHA-256;
3. every result validates against its committed schema;
4. both authoritative tapes have identical bytes and verified identities;
5. mandatory test counts and recording counts equal their frozen values;
6. defect and divergence ledgers contain no non-closed P0 entry;
7. requirements traceability has no orphan requirement, test, implementation,
   or evidence reference;
8. the outer tree is clean, the pinned submodule is clean and unchanged, and
   the final branch commit is proven present at the configured remote.

No report generator may change an input result, reinterpret `FAIL`, or infer a
missing test as passing.

### Artifact roots and mutation boundary

Generated build trees, temporary worktrees, tape recordings, full logs,
coverage databases, sanitizer outputs, fuzz corpora, and mutation workspaces
remain below the declared artifact root. Tracked source directories contain
only reviewed compact artifacts allowed by the repository layout.

Before a run begins, the runner records the artifact root's resolved absolute
path and device identity. It rejects:

- an empty path;
- `/`, the workspace root, the repository root, or any ancestor of them;
- a path inside the repository or pinned submodule;
- a symlink or a path containing a symlink component;
- a pre-existing nonempty run directory whose identity differs;
- a path without sufficient declared free-space headroom.

Cleanup is limited to a run directory created by the current invocation and
guarded by an identity marker. Failure artifacts and `.partial` tapes are never
removed by automatic cleanup.

### Artifact identity and naming

Every retained artifact has a stable kind, profile, byte size, SHA-256, media
type, producing stage, producing command, requirement IDs, and repository/run
identity. Content-bearing names use this pattern:

```text
<kind>-<profile>-<identity-prefix>-<sha256-prefix>.<extension>
```

`latest`, `final`, a timestamp, or an ordinal alone is not an identity. A
diagnostic timestamp may appear in metadata but is excluded from canonical
experiment identity.

Hash-bearing JSON uses RFC 8785 canonical bytes. Files use SHA-256 over exact
bytes. Hash calculation uses the operating-system or OpenSSL implementation;
the project contains no handwritten cryptographic primitive. The evidence
index is canonicalized and hashed only after every member digest has been
verified independently.

### Evidence bundle contents

The local-release bundle contains, at minimum:

- credential-safe preflight, repository, branch, and submodule proofs;
- source register and ADRs;
- source, toolchain, dependency, build, test-inventory, fixture, command,
  schema, content, and instrumentation identities;
- CMake cache export, build logs, exact executable digests, full CTest JSON
  inventory, JUnit output, all-99 test log, install proof, and headless smoke;
- fixture validation, two isolated-load projections, native command results,
  costs, milestone boundaries, and 10,000-tick continuation evidence;
- ordered instrumentation patches and series digest;
- two byte-identical finalized tapes plus independent validation reports;
- trace-disabled, trace-enabled, and uninstrumented non-perturbation reports;
- comparator identity/command/field fault reports and minimized valid prefixes;
- malformed-corpus inventory and deterministic fault-injection results;
- field/command schemas and canonical digests, source-owner review,
  continuation review, omission tests, and cache experiments;
- GCC, Clang, ASan, UBSan, static-analysis, ShellCheck, schema, secret,
  license, coverage, mutation, and fuzz results;
- randomized-prefix corpus index, seeds, invalid-prefix proportion, repeat
  results, and minimized failures if any;
- human and machine requirements traceability;
- defect/divergence ledgers;
- final gate JSON, completion report, clean-tree proof, and remote push proof.

If repository policy excludes a large passing artifact, the tracked bundle
index records its immutable external URL, exact byte count, SHA-256, retrieval
command, retention policy, and an independently verified retrieval result. An
expiring `/workspace` path is not an external location.

### Failure retention

The first root failure stops dependent gameplay work. The runner preserves all
completed earlier evidence and writes a bounded root-failure record containing
the stage, test ID, status family, safe error text, exact rerun command, and
paths/digests for the first failing input and logs.

For a tape, comparator, sanitizer, fuzz, invariant, or randomized differential
failure, retention additionally includes the command input and seed, original
failing artifact, minimized artifact when minimization is safe, executable and
schema identities, and stack trace or earliest-divergence report. A failed
trace remains `.partial` and can never be renamed or indexed as authoritative.

Diagnostic output is bounded. Environment variables are allowlisted rather
than dumped. Tokens, credentials, cookies, SSH material, signed URLs, and
authorization headers are redacted before persistence. Redaction itself has a
regression test using synthetic canaries.

### Atomic publication

Writers create new files with exclusive creation and restrictive permissions,
write and hash complete content, `fsync` the file, atomically rename within one
filesystem, and `fsync` the parent directory. Existing unequal content is never
overwritten. An interrupted write remains nonauthoritative and discoverable as
partial evidence.

Publication occurs only after local validation of the complete bundle. Git
commits contain no secret, dirty gitlink, generated build tree, unapproved
asset, or later-phase implementation. Valuable coherent milestones are pushed
without force. P0 closes only when the final local commit equals the configured
remote branch tip.

### Reproduction and idempotence

Every evidence stage records an argv array, not a shell-form command string.
The array uses repository-relative inputs and artifact-root-relative outputs
where possible. It records the allowlisted environment values that influence
behavior, with secrets represented only by presence booleans.

Two unchanged local-release runs must produce equal authoritative identities,
test inventory, tape bytes, and canonical machine-result content after excluded
diagnostic timestamps and artifact-root paths are normalized. A pre-existing
equal content-addressed artifact may be reused only after byte count and digest
verification; a cache hit never substitutes for validation.

## Alternatives rejected

### Commit every raw artifact

Rejected because multi-gigabyte tapes and build logs would make Git unusable
and may redistribute assets under an unreviewed policy. Compact schemas,
indexes, vectors, and minimized regressions remain tracked; large evidence uses
immutable content-addressed storage.

### Keep evidence only on the qualifying instance

Rejected because the instance workspace is not a persistent volume. Local-only
passing artifacts cannot support a release claim.

### Let CI be the release authority

Rejected because bounded CI cannot execute every local-release campaign and
does not replace the frozen Vast.ai host profile. CI remains mandatory
independent feedback.

### Allow a report author to waive failed or absent checks

Rejected because it breaks the fail-closed contract. A reviewed contract change
requires an ADR and new tests; it cannot be encoded as a report exception.

## Consequences

- P0 completion takes longer and requires durable artifact storage.
- Failures remain reproducible instead of becoming prose-only incidents.
- Machine results can be recomputed and independently audited.
- A passing claim cannot outrun source, tape, test, and publication evidence.
- Later `PORT-006` work receives a stable oracle authority rather than an
  unverifiable local harness.
