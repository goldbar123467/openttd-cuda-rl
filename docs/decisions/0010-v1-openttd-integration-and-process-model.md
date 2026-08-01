# ADR 0010: Use a native synchronized bridge with process-isolated environments

- Status: Accepted
- Date: 2026-07-31
- Applies to: headless environment control, vector rollout, and normal-game policy control

## Context

V1 must control actual OpenTTD without screen scraping and must run the exported
model in a normal playable build. OpenTTD's existing AI surface is Squirrel-based,
while the production environment and inference core are required to be C++.

Pinned-source inspection also establishes three constraints:

- `StateGameLoop()` is the engine's state-changing boundary and says state must not
  be changed elsewhere;
- native command helpers require player-originated operations to use the normal
  posted command path, reserving direct execution for the state loop or a command;
- the stock `null` video driver reports no GUI, and new-game startup follows the
  dedicated/spectator path rather than creating the learning company.

Consequently, neither an external GUI driver, an ordinary Squirrel AI, nor simply
starting `openttd -v null` supplies the required lifecycle.

## Decision

### Source-integrated engine boundary

1. V1 adds an optional native C++ integration layer to the pinned OpenTTD patch
   series. The engine remains the sole owner of game rules, commands, ticks, RNG,
   economy, and save state.
2. The bridge observes and acts only at reviewed `StateGameLoop`-aligned boundaries.
   It never mutates pools, tiles, companies, vehicles, orders, money, or timers by
   direct structure writes.
3. Agent operations enter the same validation/test/execution command machinery as
   a real player. Player-context operations use posted commands. Any direct command
   call must be inside the documented state-loop/command context and proven
   equivalent, deterministic, and non-recursive.
4. Observation, mask, action outcome, reward deltas, and termination for one
   transition share one pre/post boundary identity. The coordinator cannot advance
   ticks while a transition response is incomplete.

### Headless worker

5. The worker is a regular OpenTTD build with `OPTION_DEDICATED=OFF`, plus an
   RL-specific headless loop/driver enabled by an explicit build/runtime feature.
   It does not start a network dedicated server and does not inherit the stock
   spectator-company behavior accidentally.
6. RL-mode bootstrap creates the single learning company through reviewed normal
   initialization/command paths, validates the bus-only scenario, and then enters
   the first synchronized boundary. With the feature disabled, upstream startup
   behavior is unchanged.
7. The bridge uses a versioned, length-delimited, bounded binary protocol over
   inherited local byte streams. Standard output remains structured logging, not
   an ambiguous control channel. Message version, environment/session ID,
   transition ID, payload length, and checksum/digest make stale, duplicate,
   truncated, oversized, and replayed requests detectable.
8. One OpenTTD process owns exactly one environment. A C++ coordinator batches
   observations/inference/training across workers and emits results in canonical
   environment order. Worker crash, timeout, or protocol loss ends the affected
   trajectory and retains evidence; the coordinator never guesses whether an
   action executed.
9. In-process multi-environment execution is forbidden for V1 unless a replacing
   ADR proves isolation of all mutable globals, singletons, pools, allocators,
   callbacks, drivers, RNG streams, files, and external resources and passes a
   differential/soak campaign. Performance alone is insufficient.

### Playable controller and existing AI baselines

10. Normal-game playback uses a native C++ `NeuralCompanyController` integration
    linked to the shared encoder, masks, action interpretation, and CPU ONNX
    inference wrapper. It is scheduled at the same logical decision boundary and
    uses normal posted engine commands.
11. The playable build retains the ordinary GUI and normal user workflow. The RL
    bridge may be disabled independently; loading a model never requires a
    headless coordinator, PPO trainer, CUDA toolkit, or training runtime.
12. Existing OpenTTD AIs remain Squirrel baseline competitors/evaluation subjects.
    They are not the transport layer for the neural model and are reported as a
    distinct baseline class when their timing/interface differs.
13. Multiplayer/network control is outside V1. The bridge binds no public network
    listener.

## Required non-perturbation properties

- an integration-disabled build follows upstream behavior for the selected smoke
  and regression inventory;
- observation and mask generation consume no engine RNG and perform no command;
- logging/telemetry on versus off yields the same semantic trace;
- a no-op policy under the bridge matches the declared uncontrolled reference;
- each accepted action has exactly one transition ID and one execution result; and
- playable and headless modes use identical versioned semantic core inputs and
  outputs even though their outer loops differ.

## Rejected alternatives

### Screen capture plus simulated input

Rejected because pixels and UI timing are an unstable, incomplete state/action
contract and cannot prove synchronized reward or legal-action masks.

### Stock Squirrel AI as the production neural controller

Rejected because it would introduce a second language/runtime boundary for the
core C++ inference path and does not directly solve native ONNX packaging.

### Stock null-video or dedicated server as the environment unchanged

Rejected because source inspection shows non-GUI startup follows spectator/server
semantics. V1 needs explicit single-company bootstrap and externally controlled
decision stepping, not a fixed number of unattended ticks.

### Multiple OpenTTD states in one process

Rejected initially because OpenTTD has extensive process-global state. The proof
burden exceeds the value before a correct process-isolated baseline exists.

## Verification

`G03` and `G11` require actual-engine tests for lifecycle, bootstrap, command
rejection, exact tick ranges, duplicate/stale messages, timeout/crash recovery,
two-worker isolation, no-op non-perturbation, and headless/playable semantic golden
vectors. Upstream source evidence includes the
[documented `StateGameLoop`](https://docs.openttd.org/source/d4/d8e/openttd_8cpp)
and [AIController API](https://docs.openttd.org/ai-api/classAIController).

This ADR selects the boundary. Exact hook sites and protocol fields remain
versioned M03 implementation artifacts and must be justified by tests, not by this
record alone.
