# P0 Scope

> **Legacy scope notice (2026-07-31):** This document remains canonical only for
> historical P0 artifacts. It is subordinate to `GOAL.md` for active project scope
> and cannot authorize road freight before passenger-bus Version 1.

This is the canonical P0 scope path referenced by machine traceability. Its normative contents aggregate the reviewed supported and forbidden scope documents without changing their requirements.

# P0 Supported Scope

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

# P0 Forbidden Scope

The following boundaries are hard failures for the P0 branch unless the oracle
contract itself is revised by explicit human direction. An ADR cannot silently
expand the phase.

## Later backends and product features

P0 must not contain:

- a scalar C gameplay simulation or port;
- a Python gameplay simulation or reinforcement-learning environment;
- a batched CPU simulation backend;
- CUDA kernels, CUDA gameplay state, GPU execution, GPU optimization, or device
  parity claims;
- training loops, agents, policies, rewards, curriculum, vector environments, or
  benchmark leaderboards;
- viewers, renderers, web applications, RPC services, databases, dashboards, or
  interactive product UI;
- savegame authoring for a later custom backend;
- performance work for the future port, including SIMD, occupancy, throughput,
  or whole-game optimization.

The installed CUDA toolchain and GPU may be inventoried as host diagnostics. They
are not an implementation target during P0.

## Unsupported OpenTTD gameplay

The oracle fixture must not expand into:

- rail, trains, signals, ships, aircraft, airports, docks, canals, or waterways;
- bridges, tunnels, rail crossings, water crossings, trams, one-way roads, road
  waypoints, road conversion, or articulated vehicles;
- multiplayer, networking, companies beyond the frozen fixture, scripts, AIs,
  GameScripts, NewGRFs, content downloads, or online services;
- GUI input replay, rendering, audio, music, news, windows, viewport state, or
  localization as authoritative simulation state;
- arbitrary maps, climates, industries, cargos, vehicle types, engines, orders,
  depots, stations, or settings outside the frozen fixture;
- terraforming, demolition, town construction, subsidies, disasters, cheats,
  inflation variants, breakdown variants, or unreviewed economy branches;
- arbitrary savegame compatibility or general OpenTTD emulation.

If pinned behavior unexpectedly reaches one of these branches, the run fails and
the fixture or scope decision must be reviewed. The branch is not accepted merely
because the unexpected behavior appears deterministic.

## Forbidden instrumentation behavior

Instrumentation must not:

- edit the pinned submodule or move its gitlink;
- mutate gameplay except by one native command submission at its intended boundary;
- inject GUI events or bypass the normal command dispatcher;
- test or execute a command more times than native behavior requires;
- consume RNG, pathfind, call stateful lazy getters, or rebuild caches only for
  logging;
- alter command semantics, tick ordering, pool allocation, save/load ordering,
  cache validity, error handling, or simulation duration;
- serialize pointer addresses, object memory, struct padding, RTTI names,
  unordered iteration, locale-sensitive text, or wall-clock values as authority;
- hide command rejection, trace write failure, disk exhaustion, or schema mismatch;
- depend on graphics, audio, a display server, network access, or unpinned content.

## Forbidden implementation shortcuts

P0 must not:

- use Python as the production parser, writer, comparator, minimizer, or identity
  authority;
- implement a cryptographic primitive from memory or generated ad hoc;
- serialize native structs or depend on host padding, endianness, pointer width,
  `long`, or `size_t`;
- use unchecked arithmetic, unchecked allocation sizes, variable-length arrays,
  silent truncation, saturation, wrapping, or malformed-input fallbacks;
- weaken a test, skip a mandatory gate, retry a flaky test into success, or accept
  a final hash when a field-level comparison is available;
- use current OpenTTD `master`, a floating download, an unverified binary, or a
  previously extracted content directory as behavioral authority;
- perform authoritative replay while network access is required;
- install or modify an NVIDIA driver, install the apt `cuda` metapackage, alter
  kernel modules, or remove working system packages;
- read, copy, hash, archive, log, or commit credentials, shell history, process
  environments, SSH private keys, or GitHub authentication stores;
- change repository visibility, force-push, rewrite history, delete unrelated refs,
  merge to `main`, or publish to upstream OpenTTD without explicit authorization.

## Claim discipline

No document, test name, manifest, or report may call an unexecuted gate `PASS`.
Existing local build products are diagnostics only. Generated expectations cannot
validate the production code that generated them. An unresolved difference is a
blocking divergence, not an accepted approximation.
