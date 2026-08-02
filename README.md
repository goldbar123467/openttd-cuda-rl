# OpenTTD Reinforcement Learning Platform

This repository is being developed into a reproducible, headless C++/CUDA
reinforcement-learning platform for OpenTTD. Version 1 is deliberately narrow: a
single learning company must learn profitable passenger-bus operation on controlled
32 by 32 maps with PPO, then export a policy that can be watched inside OpenTTD.

The repository is not at Version 1 yet. Its accepted V1 substrate now passes
M00 through M08: reproducible OpenTTD, the controlled passenger-bus environment,
frozen observations/actions/rewards, trusted C++ PPO, all three initial model
architectures, and a correctness-validated measured CUDA training path. The
unfinished legacy P0 64 by 64 road-freight workstream remains retained for
deterministic tooling and historical evidence, not as bus or RL progress.

## Start here

1. [`GOAL.md`](GOAL.md) — authoritative project scope and Version 1 definition of
   done.
2. [`docs/project/REQUIREMENTS.md`](docs/project/REQUIREMENTS.md) — atomic
   requirements and acceptance evidence.
   The synchronized machine registry is
   [`docs/project/requirements-v1.json`](docs/project/requirements-v1.json),
   validated by `./scripts/v1/traceability.sh`.
3. [`docs/project/ROADMAP.md`](docs/project/ROADMAP.md) — ordered implementation
   phases and gates.
4. [`docs/architecture/V1_ARCHITECTURE.md`](docs/architecture/V1_ARCHITECTURE.md)
   — target component and data-flow design.
5. [`docs/contracts/V1_ENVIRONMENT.md`](docs/contracts/V1_ENVIRONMENT.md) — reset,
   step, observation, action, reward, and termination contracts.
6. [`docs/training/PPO_AND_MODEL_PIPELINE.md`](docs/training/PPO_AND_MODEL_PIPELINE.md)
   — PPO, checkpoint, ONNX, and in-game inference plan.
7. [`docs/project/VERIFICATION.md`](docs/project/VERIFICATION.md) — test,
   evaluation, reproducibility, and evidence gates.
8. [`docs/project/LEGACY_P0_TRANSITION.md`](docs/project/LEGACY_P0_TRANSITION.md) —
   how existing P0 artifacts are preserved, reused, or retired.
9. [`NEXT_STAGES_IMPLEMENTATION_HANDOFF.md`](NEXT_STAGES_IMPLEMENTATION_HANDOFF.md)
   — current implementation handoff and immediate critical path.
10. [`docs/project/M00_WORKTREE_PRESERVATION.md`](docs/project/M00_WORKTREE_PRESERVATION.md)
    — current dirty-worktree identity and preservation boundary.
11. [`docs/decisions/`](docs/decisions/) — accepted project decisions. V1's source,
    integration, toolchain, evidence, publication, and legacy boundaries are ADRs
    0007 through 0013.
12. [`docs/project/G00_GATE_REPORT.md`](docs/project/G00_GATE_REPORT.md) — passed
    authority/preservation gate and its historical M01 handoff boundary.
13. [`docs/project/M01_SOURCE_PREPARATION.md`](docs/project/M01_SOURCE_PREPARATION.md)
    — verified offline OpenTTD 15.3 reconstruction and patch-series guard.
14. [`docs/project/M01_TOOLCHAIN_PROBE.md`](docs/project/M01_TOOLCHAIN_PROBE.md)
    — verified offline dependency, compiler, CUDA, LibTorch, and ONNX probe runner.
15. [`docs/project/M01_OPENTTD_BUILD_REPRODUCIBILITY.md`](docs/project/M01_OPENTTD_BUILD_REPRODUCIBILITY.md)
    — two clean, byte-identical headless builds and two clean, byte-identical
    playable builds with complete commands, tests, hashes, and timing evidence.
16. [`docs/project/M01_BUILD_PROFILE_RESOURCE_PROVENANCE.md`](docs/project/M01_BUILD_PROFILE_RESOURCE_PROVENANCE.md)
    — validated seven-profile matrix, repeated runtime-resource measurements, and
    byte-identical complete dependency-provenance manifests.
17. [`docs/project/G01_GATE_REPORT.md`](docs/project/G01_GATE_REPORT.md) — passed
    reproducible build/runtime gate and the exact conditional 32 by 32 next slice.
18. [`docs/project/M02_MAP_FEASIBILITY.md`](docs/project/M02_MAP_FEASIBILITY.md) —
    passed conditional 32 by 32 engine feasibility, sanitizer matrix, and
    two-run binary/canonical-output reproducibility evidence.
19. [`docs/project/M02_SCENARIO_RESET_CONTRACT.md`](docs/project/M02_SCENARIO_RESET_CONTRACT.md)
    — frozen eight-template passenger-bus scenario, reset projection, and
    scripted native trajectory contract.
20. [`docs/project/G02_GATE_REPORT.md`](docs/project/G02_GATE_REPORT.md) — passed
    controlled scenario/reset gate and repeated current-Ubuntu evidence.
21. [`docs/project/M03_SYNCHRONIZED_BRIDGE.md`](docs/project/M03_SYNCHRONIZED_BRIDGE.md)
    — frozen lifecycle, framed local protocol, process isolation, and tick policy.
22. [`docs/project/G03_GATE_REPORT.md`](docs/project/G03_GATE_REPORT.md) — passed
    synchronized-bridge gate and repeated all-template native evidence.
23. [`docs/project/M04_VERSIONED_OBSERVATION.md`](docs/project/M04_VERSIONED_OBSERVATION.md)
    — frozen native structured/spatial observation and shared preprocessing.
24. [`docs/project/G04_GATE_REPORT.md`](docs/project/G04_GATE_REPORT.md) — passed
    observation semantic, compatibility, and non-perturbation gate.
25. [`docs/project/M05_EXPLICIT_BUS_ACTIONS.md`](docs/project/M05_EXPLICIT_BUS_ACTIONS.md)
    — frozen 41-action catalog, masks, typed outcomes, and transactions.
26. [`docs/project/G05_GATE_REPORT.md`](docs/project/G05_GATE_REPORT.md) — passed
    action/mask oracle and useful actual-engine bus-service gate.
27. [`docs/project/M06_REWARD_TRAJECTORY_FOUNDATION.md`](docs/project/M06_REWARD_TRAJECTORY_FOUNDATION.md)
    — frozen native reward, termination, integrity, and trajectory foundation.
28. [`docs/project/G06_GATE_REPORT.md`](docs/project/G06_GATE_REPORT.md) — passed
    reward, episode, and byte-exact trajectory gate.
29. [`docs/project/M07_TRUSTED_CPU_PPO.md`](docs/project/M07_TRUSTED_CPU_PPO.md)
    — trusted C++ PPO, structured MLP, monitoring, and exact recovery.
30. [`docs/project/G07_GATE_REPORT.md`](docs/project/G07_GATE_REPORT.md) — passed
    PPO reference, recovery, soak, and development-readiness gate.
31. [`docs/project/M08_SPATIAL_COMBINED_MEASURED_CUDA.md`](docs/project/M08_SPATIAL_COMBINED_MEASURED_CUDA.md)
    — frozen CNN/combined architectures and measured device policy.
32. [`docs/project/G08_GATE_REPORT.md`](docs/project/G08_GATE_REPORT.md) — passed
    CPU/CUDA parity, performance, monitoring, and live-integration gate.
33. [`docs/project/G09_GATE_REPORT.md`](docs/project/G09_GATE_REPORT.md) — passed
    independent multi-seed evaluation, baselines, profitability, and robustness gate.

## Current status

| Area | Current evidence | Project status |
|---|---|---|
| V1 OpenTTD source/integration/toolchain profile | Offline source preparation, repeated probes/builds/resources/provenance, and deterministic closure audit | `M01/G01 PASS`; frozen baseline only |
| Conditional 32 by 32 engine support | Flag-off/flag-on matrix, true-empty saves, ASan/UBSan soaks, and two byte-identical clean runs | `M02 feasibility PASS`; frozen prerequisite |
| Pinned historical P0 reference build | Existing manifests, scripts, and P0 evidence | Retained legacy evidence; not the V1 source profile |
| Legacy tape/parity tooling | C17 library, schemas, tests, and in-progress fixes | Incomplete legacy workstream |
| 32 by 32 passenger-bus scenario/reset | Frozen contract/corpus/seeds, native reset projection, scope mutations, and repeated scripted delivery/income trajectory | `M02/G02 PASS`; frozen baseline |
| Headless RL environment API | Versioned local framing, typed lifecycle, process isolation, 1–128 tick stepping, repeated all-template oracle | `M03/G03 PASS`; frozen synchronization boundary |
| Structured/spatial observations | Frozen native encoder, exhaustive semantics, shared bytes, and 264,192 actual-engine comparisons | `M04/G04 PASS`; frozen observation boundary |
| Legal bus action masking | Fixed 41-action catalog, boundary tokens, native command test/execute paths, 614 oracle comparisons, and profitable all-template trajectories | `M05/G05 PASS`; frozen action boundary |
| Reward, termination, and trajectories | Native lifetime-delta projection, eight-component scalar, 13 typed outcomes, exploit guards, and byte-exact bounded trajectories | `M06/G06 PASS`; frozen learning-data boundary |
| PPO trainer | Trusted C++/LibTorch clipped PPO, exact recovery, structured monitoring, and development-selected MLP | `M07/G07 PASS`; frozen CPU oracle |
| CNN and combined models | Frozen 32-channel CNN plus structured/spatial fusion, paired learning, and live OpenTTD smoke | `M08/G08 PASS`; ready for independent comparison |
| CUDA training path | All-model numerical parity, measured CNN inference/update benefit, GPU telemetry, and explicit failure classes | `M08/G08 PASS`; enabled only for measured workloads |
| Independent evaluation | Optimizer-free read-only evaluator, matched nine-run architecture campaign, three baselines, unseen final layouts, stochastic seeds, confidence intervals, and robustness matrix | `M09/G09 PASS`; frozen selected package |
| ONNX export/equivalence | No implementation | Not started |
| In-game neural agent | No implementation | Not started |

This table is intentionally conservative. A legacy freight fixture, a buildable
OpenTTD submodule, or a passing tape test does not prove a V1 bus-platform item.

## Version 1 boundary

Included: 32 by 32 maps, default economy, one learning company, passengers,
buses, roads, bus stops, required road-vehicle depots, PPO, MLP/CNN/combined
baselines, headless training, structured monitoring, independent evaluation,
ONNX packaging, and visible in-game playback.

Excluded until Version 1 passes: mail, trucks, industries, trains, ships,
aircraft, larger maps, multiplayer or competitive training, NewGRFs, arbitrary
mods, additional RL algorithms, screenshot vision, GUI input imitation, and
distributed multi-machine training.

## Repository note

The accepted milestone commits are kept synchronized with `origin/main` and the
worktree is expected to be clean at handoff. Any future user-owned changes must
still be preserved. Follow the transition document before deleting, renaming, or
repurposing an existing oracle, parity fixture, or evidence artifact.
