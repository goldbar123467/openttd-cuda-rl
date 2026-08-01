# P0 Supported Scope

> **Legacy scope notice (2026-07-31):** This scope is preserved for historical P0
> verification. It is not the active project scope; see `GOAL.md`.

## Purpose

P0 builds the deterministic OpenTTD oracle and the independent host-side parity
contract needed to judge later implementations. It does not implement a gameplay
backend. The only completed scope claim allowed for this phase is the conjunction
of `PORT-001` through `PORT-005` after every mandatory gate passes.

## `PORT-001`: reproducible reference pinning

P0 supports reconstructing the exact pinned OpenTTD reference on Ubuntu 24.04
x86-64 with committed source, toolchain, dependency, build, test, content, and
runtime manifests. It verifies:

- outer repository and exact clean submodule identity;
- approved compiler, linker, CMake, Ninja, dependency, and environment profiles;
- deterministic out-of-tree configuration, build, and install procedures;
- the exact 99-test upstream inventory with zero skipped mandatory tests;
- OpenGFX 8.0 archive digest
  `43a0c1dabf39cb865394f3a6cc36d4da5c10ecfaaf55652043104806810903be`;
- an approved headless smoke workload;
- clean-checkout reproducibility and drift-negative tests.

## `PORT-002`: deterministic road-freight fixture

P0 supports one audited, deterministic 64 by 64 map fixture using original base
content and a single road-freight route. The selected scenario must be source- and
observation-verified, structurally validated, fully manifested, and replayable
without network access. Its frozen identities include the save, normalized
settings, initial state, content, and native command input.

The intended narrow gameplay path is one company, one road vehicle, one cargo
source, one cargo destination, two compatible road stops, a road depot, a simple
unbranched road plan, explicit orders, and a delivery/economy continuation. Exact
industry and cargo choices remain governed by ADR 0003 and pinned-source evidence.

## `PORT-003`: external oracle instrumentation

P0 supports a seven-patch, reviewable C++ instrumentation series applied only to a
disposable worktree made from the pinned submodule. It may:

- read a strict prevalidated native command stream;
- submit commands through OpenTTD's native command machinery;
- emit run/build identities and exact command-boundary results;
- project all required authoritative state at the prescribed command and tick
  boundaries;
- emit diagnostics explicitly separated from authoritative state;
- run trace-disabled, trace-enabled, and self-checking nonperturbation profiles.

Instrumentation may observe but must not otherwise mutate gameplay, consume RNG,
run extra pathfinding, change tick or allocation order, invoke GUI or rendering,
or hide trace failures.

## `PORT-004`: tape and parity tooling

P0 supports strict ISO C17 production tooling for command-input and tape v1 files,
including bounded reading, writing, validation, inspection, first-divergence
comparison, valid-prefix minimization, fault injection, checked arithmetic,
canonical identity handling, and SHA-256 verification. Python is limited to an
independent standard-library reference decoder and schema test oracle; it is not
the production tape authority.

## `PORT-005`: schema, cache, and completion contract

P0 supports a versioned command registry, stable numeric field registry, explicit
authoritative/diagnostic/derived-cache classification, complete projection audit,
cache-erasure and cache-rebuild experiments, schema validation, deterministic
continuation evidence, fuzzing, sanitizers, static analysis, coverage, mutation
testing, CI, traceability, and a digest-verifiable evidence bundle.

## Supported execution profile

The required top-level entry point is:

```bash
./oracle/runner/p0_gate.sh --profile local-release
```

It runs mandatory gates in dependency order, retains the first root failure and
its raw evidence, and reports `PASS` only when every contract requirement passes.
Authoritative replay occurs offline after approved materials are acquired.

## Completion boundary

P0 is complete only with exact parity across the required deterministic oracle
runs, zero open defects or divergences, a clean pinned submodule, a clean pushed
branch, validated artifact digests, and the required completion report. Partial
success is recorded as progress, never represented as P0 completion.
