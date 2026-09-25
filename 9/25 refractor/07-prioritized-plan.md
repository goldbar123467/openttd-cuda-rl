# 07 — Prioritized plan

A staged plan derived from reports 01–06. It covers:

1. correctness and reproducibility;
2. evaluation reliability;
3. kernel and pipeline performance;
4. optional strategy experiments.

Nothing here has been implemented or run.

**Guardrails for every item** (from `AGENTS.md`):

- Do not edit frozen release scripts, records or expected hashes. Add development
  routes under `scripts/dev` and `training/dev` instead.
- Keep `reference` modes available for reproducing old runs.
- Every run records source revision and dirty state, configuration, seeds,
  device/runtime and outputs.
- CUDA requests must fail when unavailable.
- Do not use final-split results for tuning.
- Run `bash scripts/v2/verify.sh --tier fast`, the relevant `ctest` labels and
  `git diff --check` before handing off.

**Equality gate.** "Byte-identical traces" means the design in
`scripts/dev/compare_training_backends.py:33-79`: alternate the order, compare
`episode-metrics/*.jsonl` bytes, PPO metrics and model IDs. For evaluation, use
`scripts/dev/compare_replay.py`.

---

## Stage 1: correctness and reproducibility

These items make results trustworthy and reproducible. They must not change any
learning outcome.

### S1-1. Main must reproduce the current V2 recipe.

- **Files:** `training/dev/v2_live_train.cpp`, `scripts/dev/train_v2.py`,
  `scripts/dev/guide_v2.py`, `scripts/dev/checkpoint_v2.py`, `scripts/dev/infer_v2.py`,
  `tests/dev/test_train_v2.py`, `tests/dev/test_guide_v2.py`, `docs/DEVELOPMENT.md`.
- **Change:** port the worktree-only features into main as default-off options:
  - `--entropy-coefficient` in the native V2 trainer and `train_v2.py`;
  - `--financial-features signed-log-v1` for **training** input (today only
    inference accepts it; training calls `read_live_v2_input` with the raw default
    at `v2_live_train.cpp:84,112`);
  - guide v3 (borrowing option).

  Bind each option in checkpoint identity and compatibility, as the qualified
  worktrees did (`PROGRESS.md:284-292`).
- **Why:** 01 §5.1 and 02 §2.14. Main cannot currently reproduce the reported V2
  models.
- **Verify:**
  1. With default flags, a short CUDA and CPU run from the new main build matches the
     current main build byte for byte (traces, metrics, weights). Use the existing
     verify scripts (`verify_entropy_option.py` pattern) adapted to V2.
  2. With the worktree flags, the first N decisions and updates of a retained
     worktree run are reproduced exactly (the PROGRESS qualification reports list
     the reference artifacts).
  3. Run `pytest tests/dev/test_train_v2.py tests/dev/test_guide_v2.py`.

### S1-2. V1 behavior-replay audit.

- **Files:** `training/v1/src/multimodal_trainer.cpp` (in `update`, before the
  epoch loop), `training/v1/tests/m08_native_tests.cpp`, optionally
  `training/v1/src/m08_trainer_main.cpp` (a development-only query request, not the
  frozen UPDATE response).
- **Change:**
  1. Under `NoGradGuard`, recompute `masked_categorical` on the full rollout (in
     minibatch-sized chunks to bound memory).
  2. Gather the stored actions' log-probabilities.
  3. Compute `max |Δ|` against `old_log_probabilities`.
  4. Throw `runtime_error("behavior replay changed log probabilities")` above 1e-4
     (V2's threshold, `v2_live_train.cpp:164`).
  5. Expose the value through a development-only request type. **Do not change the
     UPDATE wire format**, which `m08_trainer_client.py` unpacks as `<8dQQ`.
- **Why:** 02 §2.1. Behavior and learner distributions come from different code in
  fused builds, and V1 has no runtime check.
- **Verify:**
  1. A native test that corrupts one stored log-probability by 1e-3 and expects
     rejection.
  2. A native test that a clean rollout passes.
  3. `compare_training_backends.py` on identical binaries shows byte-identical
     traces, which proves the audit is read-only.
  4. In a fused vs reference run, the recorded audit error is ≤ the documented
     kernel error.

### S1-3. Kernel hygiene.

- **Files:** `training/dev/fused_policy_kernel.cu` (30, 61), `training/dev/fused_policy.cpp`
  (13, 32–35), `training/v1/src/multimodal_trainer.cpp:117`,
  `training/dev/fused_policy_test.cpp`.
- **Change:**
  - distinct status codes (1 input nonfinite, 2 all-illegal, 3 entropy nonfinite);
  - include the first failing row index in the exception text;
  - at the call site pass `legal_masks.to(device_, torch::kBool)`, which is
    bit-identical for current bool inputs;
  - add the missing tests from 05 §10.2: mixed batch with one bad row, legal ±inf
    and NaN, the B = 65,535/65,536 boundary, a ±1e38 spread, and a non-contiguous
    mask.
- **Why:** 05 §5. There are no correctness defects, but diagnostics and test
  coverage have gaps.
- **Verify:** `ctest -R rl_fused_policy_test` on the GPU. On a native Linux host,
  `compute-sanitizer --tool memcheck|racecheck|synccheck|initcheck`. Record "not
  run" if unavailable.

### S1-4. Honest embedded-probe metrics.

- **Files:** a new `scripts/dev/pipeline_probe.py` (wrapping, not editing,
  `run_m08_live_architectures.evaluate_architecture` logic) and `scripts/dev/train_live.py:151-155`.
- **Change:** store probe results under `run.json["pipeline_probe"]` with
  `quarter_income` renamed and a `claim: "not an evaluation"` field. Optionally
  compute lifetime-delta income as `evaluate_live.py:166-179` does.
- **Why:** 02 §2.13 and 03 N10.
- **Verify:** a unit test in `tests/dev/test_workflow.py` style using a recorded
  fake controller.

### S1-5. Record the ACT distribution backend explicitly.

- **Files:** `scripts/dev/train_live.py` (record building, 86–113), optionally
  `m08_trainer_main.cpp` (a development INFO request reporting
  `RL_DEV_FUSED_POLICY`).
- **Change:** add `record["act_distribution"] = "fused-cuda" | "reference"`. Derive
  it from the native INFO request, or from `trainer_build.configure` containing
  `-DRL_DEV_FUSED_POLICY=ON`.
- **Why:** 01 §5.5 and 03 N8.
- **Verify:** unit test with a fake `development-build.json`.

### S1-6. Offline audits that need no new runs.

- **Files:** new `scripts/dev/audit_v2_reward.py` and `scripts/dev/audit_time_features.py`.
- **Change:**
  - (a) From retained V2 `trajectory.jsonl`: count the binding frequency of each
    reward clip (`train_v2.py:26-28`), and list terminal transitions with their
    reasons (R2, R3).
  - (b) From V1 `episode-metrics` and `actions.jsonl`: histogram structured
    features 16–19 in training versus evaluation for horizon-128/256 models (02 §2.4).
  - (c) From V2 metrics: the pre-normalization advantage mean and standard deviation
    per update, and the KL distribution (02 §2.5, P5).
- **Why:** these turn Risks into facts before any learning change.
- **Verify:** scripts are read-only and hash their inputs, like `report_learning.py`.
  Add unit tests on synthetic rows.

**Stage 1 exit criteria:** S1-1 default-equivalence passes; S1-2 is in both builds;
S1-3 tests pass on the GPU; audit reports S1-6 are committed as run artifacts
(outside Git) and summarized in `docs/PROGRESS.md`.

---

## Stage 2: evaluation reliability

### S2-1. Commit study drivers and registration schemas.

- **Files:** new `scripts/dev/studies/` (drivers currently in `runs/.../experiment.py`
  and `finish_analysis.py`), new `docs/project/schema/dev-study-registration.schema.json`,
  and tests.
- **Change:** move the advancement logic (the nine-game matrix, "at least all six
  controls", "strictly above uniform") into committed, tested code. Registrations
  in `runs/` reference the driver file's SHA-256.
- **Why:** 01 §5.2 and 03 §1. Advancement decisions are not reviewable today.
- **Verify:** re-derive a completed study's pass/fail from its retained inputs with
  the committed driver, offline, with no new games.

### S2-2. Per-map, per-seed and hierarchical uncertainty in reports.

- **Files:** `scripts/dev/report_learning.py`, `report_credit_experiment.py`,
  `report_v2_learning.py`, and a new shared `scripts/dev/eval_stats.py`.
- **Change:**
  - add per-map tables;
  - add paired differences by (map, sampling seed);
  - add a nested bootstrap (training seed → map → action seed) with a fixed RNG
    seed;
  - add sign counts of per-seed differences;
  - keep the existing t-intervals unchanged.
- **Why:** 03 N1, N2 and N5.
- **Verify:** unit tests on synthetic data with known structure. Existing report
  outputs must be unchanged apart from the added keys (snapshot tests).

### S2-3. V2: evaluate on all 8 development maps.

- **Files:** the study driver from S2-1; `scripts/dev/infer_v2.py` and
  `evaluate_guide_v2.py` already accept `--split development --map-seed`.
- **Change:** the default V2 confirmation matrix becomes 8 maps × (1 greedy +
  3 sampled seeds) for the candidate and for each control, paired by map and seed.
- **Why:** 03 N1 and N4. The seeds exist in `config/v2/m15-scalable-contract.json`.
- **Verify:** the matrix check in the driver. Estimate the cost first from the
  existing `wall_seconds` records (no new runs needed for the estimate).

### S2-4. V2 held-out registration.

- **Files:** new `scripts/dev/evaluate_registered_v2.py`, modeled on
  `evaluate_registered.py:20-140`; tests modeled on `tests/dev/test_evaluate_registered.py`.
- **Change:** a frozen protocol on the `generalization` (or `final`) seed set,
  registered before further V2 recipe tuning. Refuse to run unless the
  registration, code, binary and model hashes match. `live_v2.py:25-26` currently
  forbids held-out splits; add the new access only through this registered route.
- **Why:** 03 N4. V2 has no held-out check, and the development maps have been
  reused many times.
- **Verify:** unit tests with fakes, as the V1 counterpart has. The registration
  must precede any access; test that preflight fails without it.

### S2-5. V1 training-device agreement check.

- **Files:** new `scripts/dev/verify_device_agreement.py`, which replays an
  evaluated `actions.jsonl` through `m08_trainer` on the training device via
  deterministic ACT.
- **Change:** compare argmax exactly and probabilities within the kernel tolerance,
  for fused and reference builds.
- **Why:** 03 N8.
- **Verify:** it passes on a known-good package, and fails when a deliberately
  perturbed package is supplied.

### S2-6. Sample-size table.

- **Files:** new `scripts/dev/power_table.py`.
- **Change:** from existing development evaluations, estimate paired standard
  deviations per metric and the minimum detectable difference for {3, 5} training
  seeds × {2, 8} maps × 3 action seeds. Registrations must cite it.
- **Why:** 03 §7.9.
- **Verify:** it reproduces the width of an existing t-interval from the same inputs.

### S2-7. Determinism under concurrency.

- **Files:** a one-off `scripts/dev/check_concurrent_determinism.py`.
- **Change:** run the same greedy V1 episode alone and under `--workers 4` load, and
  the same V2 greedy game twice concurrently. Compare the bytes of the action and
  economic traces.
- **Why:** 03 N3 and 04 B6/B13 depend on this assumption.
- **Verify:** the script's output is the verification. A failure is a finding to
  record, not to hide.

**Stage 2 exit criteria:** S2-1 and S2-2 are merged; S2-3 is the default for new V2
studies; S2-4 is registered before any new V2 tuning study.

---

## Stage 3: kernel and pipeline performance

**Instrument first. Every change must pass the equality gate before any timing is
reported.**

### S3-0. Stage timers, without changing traces.

- **Files:**
  - a development copy of the `evaluate_live.py` episode loop that writes timings to
    a separate `timing.jsonl`, so `actions.jsonl` stays byte-identical;
  - a debug flag in `m08_trainer_main.cpp` `handle_act` and `handle_update` (decode,
    H2D, forward, distribution, D2H, sample, encode) emitting to stderr or a file;
  - V2 per-request timings (OBSERVE, TENSORS, policy, ACT, STEP) and archival time
    in `infer_v2.py`/`train_v2.py`.
- **Why:** 04 §6 and 05 §11. The repository has no evaluation-time breakdown.
- **Verify:** traces identical with and without timing. Report medians over ≥ 3
  counterbalanced pairs.

### S3-1. Evaluation quick wins.

- **Files:** `scripts/dev/evaluate_live.py`.
- **Change:**
  - B1: vectorized spatial validation (`policy_inputs.spatial_validation`);
  - B2: a `--bridge-validation fast` default for new development evaluations, with
    the mode recorded (it already is, at 257);
  - B7: buffered trace flushing at window boundaries and on exit.
- **Why:** 04 §2. These are code-established slow paths.
- **Verify:** `compare_replay.py` equality; paired `elapsed_seconds` medians.

### S3-2. Stop moving unused spatial data for the MLP inside C++ (05 K1).

- **Files:** `training/v1/src/multimodal_trainer.cpp:112, 150-157`.
- **Change:** when `model_->kind() == StructuredMlp`, do not `.to(device_)` or
  `index_select` the spatial tensor. Pass an undefined tensor, since the forward
  ignores it (`multimodal_model.cpp:134-139`).
- **Why:** 512 KB of H2D per ACT and 4 MiB per update minibatch, never used.
- **Verify:** the new binary vs the old on the same seed must give identical traces,
  metrics **and** model IDs. Extend `compare_training_backends.py` with a
  `--require-exact` flag for cross-binary exact comparison. Also run the CNN and
  combined smoke tests to confirm those paths are unchanged.

### S3-3. One device-to-host copy per ACT (05 K4); optional CPU distribution at small B (05 K12).

- **Files:** `multimodal_trainer.cpp:113-131`, `fused_policy.cpp:30`.
- **Change:** concatenate logits, value, log-probabilities and status on the device
  and copy once. Behind an explicit flag recorded in `run.json`, compute the 41-way
  distribution on the CPU from the already-copied logits when B is below a
  threshold chosen from S3-0 data.
- **Why:** 05 §7.2. The recorded microbenchmark had the CPU faster than fused at
  B = 4.
- **Verify:** the single-copy change must be bit-exact. The CPU-distribution flag is
  a backend change: require the S1-2 audit error ≤ 1e-5, greedy agreement on a
  replay corpus, and label runs separately.

### S3-4. A development collector with deferred bootstrap, structured-only protocol and concurrent stepping (06 K1, 05 K2/K3).

- **Files:** new `scripts/dev/collect_live.py`; a new development client for the
  structured-only and VALUE messages; `m08_trainer_main.cpp` (development-only
  message types behind `RL_DEVELOPMENT_CHECKPOINTS` or a new define);
  `scripts/dev/train_live.py` (option `--collector dev`); tests in `tests/dev/`.
- **Change:**
  1. Replace monkeypatching with explicit injection.
  2. Take `next_value` for continuing environments from the next step's ACT value.
     Request values only for truncated environments and the rollout's final state.
  3. For `structured-mlp-v1`, send structured + mask only.
  4. Issue STEP, OBSERVE and LEGAL_ACTIONS to all 4 workers before reading
     responses (or one process per environment), keeping per-environment order.
- **Why:** 05 §8. These are the only changes with a plausible material effect on V1
  collection time.
- **Verify:**
  1. With all options off, byte-identical traces to the current `train_live.py`.
  2. With each option on, byte-identical native traces **and** bit-identical PPO
     inputs. Log the UPDATE payload hash in debug mode and compare. For deferred
     bootstrap, assert that every deferred `next_value` equals the value a
     bootstrap ACT would have returned, by running both once in a check mode.
  3. Then paired timing, ≥ 3 pairs.

### S3-5. V2 UPDATE: device-resident rollout, sync-free checks, batched audit.

- **Files:** `training/dev/v2_live_train.cpp:127-213`, `training/v2/src/scalable_policy.cpp:17-41, 240-251, 294-297`
  (add a trusted-input or deferred-check path; keep the default validating path for
  inference), and `training/dev/v2_live_input.cpp` (move rollout inputs to the
  device once).
- **Change:**
  1. Upload each transition's inputs once per update, not five times
     (`v2_live_train.cpp:151-176`).
  2. Accumulate finiteness flags on the device and check once per minibatch.
  3. Batch the no-grad behavior audit across sequences. The audit does not affect
     optimization, so tolerance-level differences are acceptable there.
- **Why:** UPDATE is 33.55% of recorded V2 wall time (`PROGRESS.md:1169`), and the
  code shows about 3 MB × 5 uploads per decision per update plus about 28 host syncs
  per forward step.
- **Verify:**
  1. Changes 1–2 must reproduce metrics and final weights exactly on CPU and CUDA,
     with deterministic algorithms on (the existing identity requires them).
  2. Injected-NaN tests must still fail with named tensors.
  3. Change 3: the audit value stays within 1e-6 of the current value.
  4. Paired timing.

### S3-6. V2 evaluation I/O (04 B8–B10).

- **Files:** `scripts/dev/infer_v2.py:204-205, 207-213`, `training/dev/v2_live_infer.cpp:56-75`,
  `scripts/dev/live_v2_artifacts.py`.
- **Change:** periodic rather than per-decision duplicate OBSERVE/TENSORS checks;
  binary probability output with native sum and mask checks; archiving off the
  critical path (tmpfs plus background gzip and verify).
- **Why:** 04 §3.
- **Verify:** identical actions and economics in `predictions.jsonl`; archive
  SHA-256 equality; paired timing.

### S3-7. Evaluator reuse and thread/worker tuning (04 B5/B6).

- **Files:** `training/v1/src/m09_evaluator_main.cpp` (a development RESEED
  message), `scripts/dev/evaluate_live.py` (worker-local client reuse).
- **Why:** per-episode start-up and possible oversubscription. Pursue only if S3-0
  shows start-up or contention matters.
- **Verify:** byte-identical traces across settings, or else label as a different
  backend.

### S3-8. Kernel internals as a CUDA learning exercise (05 K7–K9).

- **Files:** `training/dev/fused_policy_kernel.cu`, `fused_policy.cpp`,
  `policy_benchmark.cpp` (add CUDA-event timing of the kernel alone).
- **Change:** warp-per-row shuffles, several rows per block, two-pass
  `(max; Z, Σe·s)`, an optional logp-only output, `const __restrict__`.
- **Why:** educational value and a lower kernel latency floor. **No end-to-end gain
  is expected** (05 §7.2).
- **Verify:** 05 §10 tolerances and tests; sanitizers; kernel-only CUDA-event
  medians alongside wrapper wall time. Never cite as a training speedup without
  S3-4-style end-to-end pairs.

**Stage 3 exit criteria:** S3-0 data exists; each adopted change has an equality
record plus a paired timing report under `runs/`, summarized in
`docs/CUDA_EXPERIMENT.md` or `docs/PROGRESS.md`.

---

## Stage 4: optional strategy experiments

Each item is a registered study with ≥ 3 training seeds, a matched decision budget,
and the Stage 2 evaluation protocol. Report service, profit, cash, invalid actions
and bankruptcy with uncertainty. Stop and record a failure without retuning on the
same maps.

| ID | Experiment | Files | Change | Why (evidence) | Verify / decision rule |
| --- | --- | --- | --- | --- | --- |
| S4-1 | Masked policy mean for forced steps (P2a) | `ppo.cpp` (a new optional per-sample weight in `ppo_loss`), `v2_live_train.cpp`, `multimodal_trainer.cpp` | Average policy and entropy over steps with ≥ 2 legal rows; normalize advantages over them | 3,404/4,096 forced WAIT steps (`PROGRESS.md` horizon-256 section) | Unit test: all-free-choice rollouts give identical loss. Then the study. |
| S4-2 | Multiple sequences per V2 minibatch (P1) | `v2_live_train.cpp:168-203` | k sequences per step, batched forward | One 8-sample sequence per Adam step | k = 1 is exact to current; study at k ∈ {2, 4} |
| S4-3 | Entropy decomposition (P4) | `v2_live_input.cpp:214-232`, `v2_live_train.cpp` | Log `H(family)` and `E H(cand|family)`; then optional separate coefficients | Joint entropy grows with candidate count | The logging step is trace-exact; coefficients need a study |
| S4-4 | V2 reward schema v2 (R2/R3) | `train_v2.py:18-32` | Capital clip ≥ bus cost, or a signed-log transform; bankruptcy-only terminal penalty | S1-6(a) results; the 4,921 bus cost vs the 4,096 clip | Offline reward recomputation, then the study |
| S4-5 | Candidate parameter features (O1) | `enable_v2_live.py` overlay, `v2_live_input.cpp`, `scalable_policy.cpp`, `v2_export_policy.py`, ONNX tests | A versioned candidate schema with normalized parameters | Borrow/repay aliasing; road/stop/depot aliasing (`PROGRESS.md:160-175`) | Offline aliasing audit about 0, then the study; unguided evaluation after C2 |
| S4-6 | Horizon schedule (C1) | `training_environment.py`, `train_v2.py` | Sample or anneal the horizon to 512; bind it in compatibility | 02 §2.4; S1-6(b) | Study with per-window metrics |
| S4-7 | Guide annealing (C2), after S4-5 | `guide_v2.py`, `train_v2.py` | ε-schedule for non-guide legal rows; record the exact masks | Planner supplies the geometry today | Compare to uniform with the identical mask at each stage |
| S4-8 | Return normalization (P3) | `ppo.cpp`, both trainers, checkpoint identity | Running mean and standard deviation of returns, checkpointed | Shared trunk with reward-dependent scales | Resume exactness test, then the study |
| S4-9 | KL guard (P5), only if S1-6(c) shows KL spikes | both trainers | Stop epochs above the target KL | KL logged but unused | Study |

---

## Summary ordering

1. S1-1 (reproducibility)
2. S1-2 (behavior audit)
3. S1-6 (offline audits)
4. S2-1 (study code in repo)
5. S2-2 (reporting)
6. S2-3 (8 maps)
7. S2-4 (V2 held-out)
8. S3-0 (instrumentation)
9. S3-1 (evaluation quick wins)
10. S3-4 (development collector)
11. S3-5 (V2 update)
12. S3-2 and S3-3 (C++ ACT/update transfers)
13. S3-6, S3-7 and S3-8
14. Stage 4, in the order S4-1, S4-5, S4-4, S4-2, S4-3, S4-6, S4-7, S4-8, S4-9.
