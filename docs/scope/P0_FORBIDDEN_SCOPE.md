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
