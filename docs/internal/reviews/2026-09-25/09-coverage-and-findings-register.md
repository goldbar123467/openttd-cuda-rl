# 09 — Coverage, limits and findings register

This report adds what a grader or an implementing agent needs beyond the original
brief:

1. what this review did and did not cover, and how confident each part is;
2. additional findings not recorded in 00–08;
3. a single register of every finding, cross-referenced to its report section and
   plan item.

Static review of commit `0595a72`; nothing was executed.

---

## 1. Coverage and confidence

| Area | Files | Depth | Confidence |
| --- | --- | --- | --- |
| V1 PPO core | `training/v1/src/ppo.cpp`, `multimodal_trainer.cpp`, `multimodal_model.cpp`, `rng.cpp`, `m08_trainer_main.cpp`, `evaluation_model.cpp`, `m09_evaluator_main.cpp`; tests in `training/v1/tests/native_tests.cpp` | Line by line | High |
| Custom kernel | `training/dev/fused_policy_kernel.cu`, `fused_policy.cpp`, test, benchmark, CMake, `local.py` | Line by line | High |
| V1 collector and wrappers | `scripts/v1/run_m08_live_architectures.py`, `run_m07_cpu_ppo.py`, `run_m06_reward_trajectory.py` (controller), `m03_bridge_protocol.py` (decode, CRC), `m08_trainer_client.py`; `scripts/dev/train_live.py`, `training_environment.py`, `training_reward.py`, `policy_inputs.py`, `bridge_validation.py`, `live_checkpoint.py` | Close reading of the rollout, reward and checkpoint paths | High |
| V1 evaluation and reports | `scripts/dev/evaluate_live.py`, `evaluate_registered.py`, `report_learning.py`, `report_credit_experiment.py`, `report_checkpoints.py`, `summarize_evaluation.py`, `m09_evaluator_client.py` | Close reading | High |
| V2 live trainer and inference | `training/dev/v2_live_train.cpp`, `v2_live_input.cpp`, `v2_live_infer.cpp`; `scripts/dev/train_v2.py`, `infer_v2.py`, `evaluate_guide_v2.py`, `guide_v2.py`, `checkpoint_v2.py`, `live_v2.py` (reset manifest), `live_v2_artifacts.py` | Close reading of the learning path; the planner internals (`service_v2.py`, `route_v2.py`) were **not** reviewed | Medium–High |
| V2 network | `training/v2/src/scalable_policy.cpp` | Forward, validators and recurrent reset only; encoder architecture not assessed | Medium |
| Engine observation patches | V1 M04 patch (time features), V2 M15 observation patch (structured features) | Targeted greps only | Medium (for the cited lines) |
| Project history | `docs/DEVELOPMENT.md`, `docs/CUDA_EXPERIMENT.md`, `docs/PROGRESS.md`, relevant parts of `docs/PROGRESS_HISTORY_2026-09-23.md` and `handoff.md` | Read the sections cited | Medium: large documents, read selectively |

**Not reviewed.** Findings here would need a separate pass.

- The V2 M22 corpus campaign and M23 deployment (`training/v2/src/m22_*`, `m23_*`,
  `training/v2/tests/*`).
- ONNX export and conversion (`scripts/dev/export_live.py`, `export_v2.py`,
  `v2_export_policy.py`, `training/v1/src/deployment_model.cpp`, `m10_*`).
- MCP and LLM economics (`mcp_v2.py`, `shared_v2.py`, `play_mcp_*`, `local_llm.py`,
  `report_mcp_matches.py`).
- Cargo routes (`cargo_live.py`, `coordinated_cargo.py`).
- The planners (`service_v2.py`, `route_v2.py`).
- `parity/`, `oracle/`, `scripts/v2/` verification tooling, CI workflows.
- The historical contracts in `config/` and `docs/project/`.
- The engine patches, apart from the cited observation lines.

**Evidence limits.**

- No command, test, build or game was run, so every "Certain" label means the code
  necessarily behaves that way, not that it was observed.
- Measurements are the repository's own records. I did not re-derive them from raw
  run artifacts, which are outside Git.
- `PROGRESS.md` line numbers were checked by search at this commit; they will drift
  as the log grows.

---

## 2. Additional findings not recorded in 00–08

| ID | Finding | Evidence | Label | Recommendation |
| --- | --- | --- | --- | --- |
| X1 | **V2 inference defaults to a training map.** `infer_v2.py` uses `--split training` by default (273), and `live_v2.reset_manifest` picks the split's first seed when `--map-seed` is omitted (`live_v2.py:31-32`). A "neural evaluation" run without explicit flags plays training map #1. | Code | Confirmed (footgun) | For evaluation runs, require an explicit `--split` and `--map-seed`, or record a loud `evaluation_on_training_map: true` flag in `run.json`. Study drivers should assert the split. |
| X2 | **V2 structured input carries only 16 set scalars.** 13–15 are redacted seeds that must be zero, so 12 informative scalars remain. Cash and loan are divided by 1e9, and there are **no time or remaining-decision features** (M15 observation patch assigns only `structured[0..15]`; the rest of the 512 are zeros). | Code | Confirmed | Cash blindness: 08 M4 and Step 3a. There is no V1-style horizon mismatch in V2, but the critic cannot know the remaining budget; keep time-limit bootstrapping. |
| X3 | **Forced steps dilute the PPO policy, entropy and KL terms** (`ppo.cpp:191-196` means over all samples; forced V2 steps contribute zero gradient but count in the denominator). | Code plus recorded choice fractions | Confirmed | 08 Step 1 |
| X4 | **Logged `approximate_kl` and `clip_fraction` understate policy change** on real decisions by the same factor as X3. | Code | Confirmed | 08 Step 0: log choice-only statistics |
| X5 | **The guide's repayment rule ignores remaining plan cost** (`guide_v2.py:67-70`: `balance ≥ 20,000 and loan ≥ 10,000`). | Code plus recorded trap (`PROGRESS.md:355-374`) | Confirmed | 08 Step 3b (guide v4) |
| X6 | **The V2 capital clip binds on bus purchases** (`train_v2.py:28` clips at 4,096; recorded bus cost 4,921, `PROGRESS.md:366`). | Code plus record | Confirmed | 06 R2. Under 08 Step 2 the potential uses the same clipped magnitude, so shaping stays consistent. |
| X7 | **The native V2 γ is only verified in some runs.** `train_v2.py` records `gamma: .99` (55) but asks the trainer for `TRAINING_INFO` only when rollout ≠ 32 or λ ≠ .95 (81–90), and the native γ is not configurable. | Code | Confirmed (minor) | Always request `TRAINING_INFO` when the binary supports it, and require γ equality before training, especially before 08 Step 5. |
| X8 | **V1 `act()` restores training mode only on normal return** (`multimodal_trainer.cpp:109-133`). An exception leaves the model in eval mode. It is harmless today (no dropout or batch norm, and `update()` calls `train()`), but fragile. | Code | Confirmed (minor) | Use an RAII mode guard. |
| X9 | **Normalizing advantages over a subset needs a small-sample rule.** Today's zero-variance rule (`ppo.cpp:138`) would zero a rollout with a single choice once normalization is restricted to choice steps. | Code (interaction with the 08 Step 1 change) | Design note | Leave advantages unnormalized when there are fewer than 2 choice steps (08 Step 1). |
| X10 | **There is no cross-binary exact-comparison mode.** `compare_training_backends.py` checks exact equality only when both runs use the same binary with vectorized validation (16–19, 59-60). Output-preserving C++ changes (05 K1/K4, 07 S3-2/S3-3) need exact checks across binaries. | Code | Confirmed | Add a `--require-exact` flag (07 S3-2). |

---

## 3. Findings register

Label key:

- **C**: confirmed in code.
- **R**: plausible risk.
- **M**: needs measurement.
- **Rec**: taken from repository measurements.

| ID | Finding | Label | Severity | Report | Plan |
| --- | --- | --- | --- | --- | --- |
| F01 | No defect in the PPO mathematics (GAE, masks, loss, entropy, normalization, checkpoints) | C (sound) | n/a | 02 summary | n/a |
| F02 | Main cannot reproduce the current V2 recipe (entropy, signed-log training inputs, guide v3 are worktree-only) | C | High | 01 §5.1, 02 §2.14 | S1-1 |
| F03 | Study drivers and advancement logic live outside Git (`runs/`) | C | High | 01 §5.2, 03 §1 | S2-1 |
| F04 | Forced-step dilution of the policy, entropy and KL terms (X3, X4) | C | High | 08 M1 | 08 Step 0–1 |
| F05 | Immediate capital charge vs 59-decision payoff gives negative construction advantages | Rec + C | High | 08 M2 | 08 Step 2 |
| F06 | WAIT-attractor dynamics; the same config can collapse | Rec (supported) | High | 08 M3 | 08 Steps 1–3, §3 early stop |
| F07 | Cash blindness on main (1e9 scaling) plus a guide repayment trap (X2, X5) | C + Rec | High | 08 M4 | S1-1, 08 Step 3 |
| F08 | Two evaluation maps; greedy is one episode per map; V2 mostly single training seed; development maps reused | C | High | 03 N1–N4 | S2-2, S2-3, S2-4 |
| F09 | V2 has 8 development seeds available but uses 2; there is no V2 held-out protocol | C | High | 03 §7 | S2-3, S2-4 |
| F10 | The kernel is correct but only on V1 CUDA `act()`: 1.0047× end to end, and the CPU distribution is faster at B = 4 | C + Rec | Medium | 05 §6–7 | S3-3, S3-8 |
| F11 | Duplicate bootstrap ACT per V1 step | C | Medium | 05 §8, 04 | S3-4 |
| F12 | The MLP pipeline moves an unused 32×32×32 spatial tensor (≈ 99% of UPDATE bytes), which also limits rollout ≤ 64 | C | Medium | 05 §7.2, 06 O3 | S3-2, S3-4 |
| F13 | Evaluation uses slow reference validation paths by default (spatial, bridge) | C | Medium | 04 §2 | S3-1 |
| F14 | V2 UPDATE re-uploads about 3 MB inputs 5× per decision and runs about 28 host syncs per forward | C (volume) / M (time) | Medium | 04 §3, 05 §9 | S3-5 |
| F15 | V2 frame I/O: about 1.5 GB written per 512-decision game; hash, gzip and verify on the critical path | C (volume) / M (time) | Medium | 04 §3 | S3-6 |
| F16 | V2 optimizer granularity: 8 samples per Adam step, 32 steps per update | C | Medium | 02 §2.8, 08 M5 | 08 Step 4 |
| F17 | Joint candidate entropy scales with candidate counts | R | Medium | 02 §2.7 | S4-3 |
| F18 | V1 horizon curriculum vs 512-relative time features | R | Medium | 02 §2.4 | S1-6(b), S4-6 |
| F19 | Shared trunk with reward-scale-dependent value loss | R | Medium | 02 §2.6 | S4-8 |
| F20 | V2 capital clip binds on bus purchase (X6) | C | Medium | 06 R2 | S4-4 |
| F21 | V2 "bankruptcy" penalty applies to any terminal | M | Low | 02 §2.12 | S1-6(a) |
| F22 | V1 lacks the behavior-replay audit that V2 has | C | Medium | 02 §2.1 | S1-2 |
| F23 | Embedded probes store quarter income as "income" | C | Low | 02 §2.13 | S1-4 |
| F24 | Kernel status code 1 is ambiguous; latent mask-dtype contract; unused outputs | C | Low | 05 §5–6 | S1-3 |
| F25 | Kernel test gaps; no sanitizer evidence | C | Low | 05 §5 | S1-3 |
| F26 | Run records do not state the ACT distribution backend explicitly | C | Low | 01 §5.5 | S1-5 |
| F27 | Monkeypatched frozen modules for development behavior | C | Medium | 01 §5.3, 06 K1 | S3-4 |
| F28 | CPU and training-device inference are not routinely cross-checked in V1 | R | Low | 03 N8 | S2-5 |
| F29 | V2 inference defaults to a training map (X1) | C | Medium | 09 §2 | S2-3 (driver asserts the split) |
| F30 | The native γ is not always verified (X7) | C | Low | 09 §2 | before 08 Step 5 |
| F31 | V1 `act()` mode restore is not exception-safe (X8) | C | Low | 09 §2 | opportunistic |
| F32 | No cross-binary exact comparison mode (X10) | C | Medium | 09 §2 | S3-2 |
| F33 | The assumption of concurrent-evaluation determinism is untested | M | Medium | 03 §8 | S2-7 |

---

## 4. How to challenge this review

For an agent verifying or refuting these findings:

- **Code-level claims (C):** open the cited lines at commit `0595a72`. Every claim
  names a file and line range.
- **Dilution claims (F04):** in a retained V2 run's `trajectory.jsonl`, count rows
  whose `guidance.sampling_legal_count == 1`, then compare with that run's recorded
  choice counts. The guide records `sampling_legal_count` (`guide_v2.py:95`).
- **Kernel performance claims (F10):** re-read `PROGRESS_HISTORY_2026-09-23.md:410-423`.
  Only re-measure with the protocol in 05 §11.
- **Anything labeled R or M:** use the offline audits in 07 S1-6 before changing
  code or training.
