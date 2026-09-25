# 02 — Correctness and PPO review

Static review of commit `0595a72`. Nothing was executed. Each item gets one label:

- **OK**: verified in code.
- **Defect**: confirmed in code.
- **Risk**: plausible problem, not proven.
- **Measure**: an open empirical question.

"V1" means `training/v1` plus the development wrappers; "V2" means the live
recurrent adapter `training/dev/v2_live_train.cpp`.

## Summary

| # | Topic | V1 | V2 |
| --- | --- | --- | --- |
| 2.1 | Action sampling and behavior log-probabilities | OK; Risk (no replay audit, two implementations when the kernel is built) | OK (replay audit exists) |
| 2.2 | Exact sampling mask stored and reused | OK | OK |
| 2.3 | Value targets and GAE | OK | OK |
| 2.4 | Terminal vs time-limit truncation | OK; Risk (horizon curriculum vs 512-based time features) | OK |
| 2.5 | Advantage normalization | OK | OK; Risk (32 correlated samples) |
| 2.6 | Clipped objective and value loss | OK; Risk (shared trunk with unnormalized returns) | OK |
| 2.7 | Entropy | OK | OK; Risk (joint entropy grows with candidate count) |
| 2.8 | Minibatches and epochs | OK | Risk (one 8-sample sequence per gradient step) |
| 2.9 | Gradient clipping and finiteness checks | OK (performance cost in 04/05) | OK (performance cost) |
| 2.10 | Checkpoint restoration | OK (reset boundaries only, by design) | OK |
| 2.11 | Recurrent state handling | n/a | OK |
| 2.12 | Reward transforms and shaping | OK | Measure (clipping; "bankruptcy" = any terminal) |
| 2.13 | Embedded probe metrics | Defect (low severity: quarter "income") | n/a |
| 2.14 | Reproducibility of reported V2 results from main | n/a | Defect (code absent from main) |

**No confirmed defect in the PPO mathematics.** GAE, the clipped surrogate, masking,
entropy, normalization and checkpoint restore all match standard PPO and are pinned
by native tests (`training/v1/tests/native_tests.cpp:38-106`).

The confirmed defects are about metrics and reproducibility. The largest risks are in
V2 optimization granularity (2.8) and the V1 curriculum and observation interaction
(2.4).

---

## 2.1 Action sampling and behavior log-probabilities

**What happens (V1)**, in `training/v1/src/multimodal_trainer.cpp:100-135`:

1. `act()` switches to eval mode and `NoGradGuard`, then runs the forward pass on the
   training device.
2. The masked distribution comes from `fused_policy` (CUDA, fused build) or
   `masked_categorical` (113–121).
3. Log-probabilities are copied to the CPU (124).
4. `sample_masked_actions` draws from a dedicated `action_sampling` mt19937_64
   stream (`rng.cpp:94-128`, via `multimodal_trainer.cpp:129`).
5. The selected log-probability is gathered from the same tensor used for sampling
   (131).
6. Deterministic calls use `argmax` and consume no RNG (126–127), so the collector's
   bootstrap-only ACT does not perturb the sampling stream. **OK.**

**Precision.** The value returns to Python as a float64 copy of float32
(`m08_trainer_main.cpp:229`) and is stored unchanged in `Transition.old_log_probability`
(`run_m08_live_architectures.py:143`). **OK.**

**Minor.** `sample_masked_actions` accumulates float64 probabilities obtained by
exponentiating float32 log-probabilities. If the draw exceeds the accumulated sum
because of rounding, it selects the last legal action (`rng.cpp:114-124`). The bias
is bounded by 1 − Σp, which is at float32 rounding scale. **Negligible; no action.**

**Risk: two implementations when the kernel is built.** With `RL_DEV_FUSED_POLICY`,
the behavior log-probability comes from the CUDA kernel. The learner's
log-probability in `update()` comes from the reference `masked_categorical`
(`multimodal_trainer.cpp:160`). The committed test bounds the difference at 1e-5
(`training/dev/fused_policy_test.cpp:44-46`). The recorded maximum was 3.8e-6
(`docs/CUDA_EXPERIMENT.md`, "Correctness and limits"). At epoch 0 the importance
ratio is therefore within about 4e-6 of 1, far below the 0.2 clip, so PPO is
unaffected.

However, V1 has **no runtime check** that the stored behavior log-probabilities match
a replay under the pre-update weights. V2 has one
(`v2_live_train.cpp:147-165`, failing above 1e-4).

- *Recommendation:* in `MultiModalPpoTrainer::update`, before the first optimizer
  step, recompute `masked_categorical` log-probabilities for the whole rollout under
  no-grad. Record `behavior_replay_max_error` in `UpdateMetrics` and fail above 1e-4,
  matching V2. This also catches collector bugs such as a mask stored differently
  from the mask sampled with.
- *Verify:* a new native test that corrupts one `old_log_probabilities` entry by
  1e-3 and expects rejection. Then a live comparison (`compare_training_backends.py`)
  with byte-identical traces, confirming the audit does not change results.

## 2.2 Exact sampling mask

**V1.** The collector builds `masks` from `environment.mask` before ACT
(`run_m08_live_architectures.py:98`) and stores `legal_mask=m07.legal_mask(environment.mask)`
for the same state (141). `environment.mask` is only reassigned after the
transition is recorded (150–153). `RolloutBatch::validate` rejects stored actions
that are illegal under the stored mask (`ppo.cpp:84-87`). **OK.**

**V2.** The guide-filtered candidate file is what the trainer reads at ACT
(`train_v2.py:115-129`). The full CPU input, including `candidate_mask`, is stored
per transition (`v2_live_train.cpp:84-94`) and reused in the replay and update.
**OK.**

## 2.3 Value targets and GAE

`compute_gae` (`ppo.cpp:90-128`) works in float64 over a `[time, environment]` grid:

- `δ_t = r_t + γ · bootstrap_t · V(s'_t) − V(s_t)`
- `A_t = δ_t + γλ · continuation_t · A_{t+1}`
- returns = A + V (λ-returns)

The accumulator starts at 0 after the last row, so the final step of a rollout uses
a one-step bootstrap from `next_value`. That is correct truncated GAE.

**Layout check.** Transitions are appended time-major, with env 0..3 inside each
time step (`run_m08_live_architectures.py:95, 124-149`). The service reshapes them
to `[rollout_length, environment_count]` (`m08_trainer_main.cpp:283-291`). Row
index = time and column = environment, so the layout is consistent. **OK.**

`next_value` is `V(s')` from a deterministic ACT on the next observation, or 0 when
`bootstrap` is false (`run_m08_live_architectures.py:116-121, 146`).

The fixed-vector test covers mixed bootstrap/continuation cases
(`native_tests.cpp:38-51`).

## 2.4 Terminal vs time-limit truncation

The M06 contract flags are at `config/v1/m06-reward-trajectory-contract.json:339-351`:

| Case | bootstrap | continuation |
| --- | --- | --- |
| NONE | true | true |
| ACTION / TICK / ACTION_AND_TICK horizon | true | false |
| BANKRUPTCY / SOLVED | false | false |

The collector passes these through (`run_m08_live_architectures.py:146-148`) and
aborts on untrainable transitions (108). V2 derives `bootstrap = not terminal` and
`continuation = not (terminal or truncated)` (`train_v2.py:144-145`). The C++ side
rejects `continuation && !bootstrap` (`v2_live_train.cpp:108`). **OK.**

**Risk: the horizon curriculum vs time features.** The engine encodes
`episode.actions_remaining = 512 − ordinal` and `ticks_remaining = 65536 − ticks`
regardless of the reset's horizon (`integration/openttd/patches/15.3/m04/0005-versioned-policy-observation.patch:201-202, 261-264`).
`--episode-horizon 128|256` shortens training episodes through the M09 reset
override (`scripts/dev/training_environment.py:41-46`).

- Bootstrapping at the 128-action truncation is consistent with optimizing the
  512-action task: features claim 384 actions remain, and the bootstrap value
  estimates that continuation.
- But training never visits `actions_used > 0.25` or `ticks_used > 0.25`. Evaluation
  always runs 512 actions (`evaluate_live.py:117`), so the last three quarters of
  every evaluation episode have time features never seen in training. That is
  extrapolation in exactly the windows the "sustained service" criterion scores
  (the final three 128-action windows, `evaluate_live.py:187-188`).
- *Measure:* histogram structured features 16–19 in training
  `episode-metrics/*.jsonl` versus evaluation `actions.jsonl` (`structured_before`).
  Compare per-window service for horizon-128 models against horizon-512 models on
  the same maps and seeds.
- *Options:* see 06 §C1.
  - Randomize the training horizon across 128–512.
  - Anneal the horizon up to 512.
  - Train with horizon-relative time features. This changes the observation
    contract and needs a versioned patch.

## 2.5 Advantage normalization

The service normalizes over the whole rollout, not per minibatch
(`m08_trainer_main.cpp:299`). Normalization uses the population variance, with ε
inside the square root; zero variance maps to exact zeros (`ppo.cpp:130-142`,
tested at `native_tests.cpp:53-62`). **OK.**

**V2 risk.** The rollout is a single environment of 32 (default), 64 or 128
consecutive decisions (`v2_live_train.cpp:141`). The mean and variance come from
one short, highly correlated trajectory segment, so advantage scale can swing
between updates, for example when a delivery lands inside the window.
`docs/DEVELOPMENT.md` already notes that rollout length changes "advantage-normalization
grouping". *Measure:* log the pre-normalization advantage mean and standard deviation
per update in `metrics.jsonl`, and correlate them with approx_kl and clip fraction.

## 2.6 Clipped objective and value loss

`ppo_loss` (`ppo.cpp:167-201`) implements:

- `−mean(min(r·A, clip(r, 1±ε)·A))`
- value loss `mean((V − R)^2)`, total `policy + c_v·value − c_e·entropy`
- approx_kl `mean((r − 1) − log r)` (the "k3" estimator)
- clip fraction

The value loss is unclipped, and `c_v = 0.5` multiplies the plain MSE, not ½·MSE.
That is a documented choice pinned by the test at `native_tests.cpp:102-104`.
**OK.**

**Risk: shared trunk with unnormalized returns.** In every V1 architecture, policy and
value heads read the same hidden vector (`multimodal_model.cpp:153-154`). V2 is also
shared (`scalable_policy.cpp`). Return scale differs by reward mode:

- native, `universal-decision-cost`, `service-potential`, `economic` and
  `balanced-economic` in `training_reward.py`;
- the V2 reward components in `train_v2.py:26-29`.

There is no return or value normalization, so the value gradient's share of the
shared representation changes with reward scale. That confounds reward-mode
comparisons with an implicit value-coefficient change. *Measure:* the ratio of value
loss to policy loss per update, using the existing metrics. *Option:* running return
normalization, or a separate value trunk (06 §P3).

## 2.7 Entropy

**V1.** Illegal actions contribute exactly zero to entropy (`ppo.cpp:159-162`); the
single-legal-action case is tested (`native_tests.cpp:64-81`). **OK.**

**V2.** `live_v2_distribution` builds `log P(candidate) = log P(family) + log P(candidate | family)`
(`v2_live_input.cpp:214-232`). The entropy used by PPO is the entropy of that joint
candidate distribution:

`H = H(family) + Σ_f P(f) · H(candidate | f)`

**Risk.** The conditional term can reach `log(#candidates in f)`, and road rows
alone can number around a thousand (PROGRESS.md reports 856 aliased road rows out of
1,024). The bonus therefore rewards probability mass on families with many
candidates, and its magnitude depends on the state. The entropy study (.01 vs .001)
changed service in ways that are hard to attribute (PROGRESS.md "lower entropy
regresses service").

*Measure:* log `H(family)` and `E_f H(candidate|f)` separately from the existing
tensors; no model change is needed. *Option:* separate coefficients for the two
terms (06 §P4).

## 2.8 Minibatches and epochs

**V1.** Each epoch reshuffles the full rollout with a dedicated RNG stream and
splits it into equal minibatches (`ppo.cpp:203-220`; coverage tested at
`native_tests.cpp:108-128`). With 4 environments × rollout 32 or 64, minibatch 32 and
4 epochs, that is 16 or 32 Adam steps per update. There is no KL early stop and no
learning-rate schedule; approx_kl is only logged (`multimodal_trainer.cpp:183`).
**OK** as implemented.

**V2 risk.**

- `config_.minibatch_size = kSequence` (8) and
  `minibatch_indices(rollout_length / kSequence, 1, …)` make each gradient step use
  **one** eight-decision sequence (`v2_live_train.cpp:68, 170`).
- A 32-decision rollout gives 16 Adam steps, each on 8 temporally correlated
  samples; rollout 128 gives 64 steps.
- Gradient clipping at 0.5 and Adam normalization limit step size, but per-step
  gradient variance is high. The advantages within one sequence share a normalization
  computed over the entire rollout.
- Late minibatches in the last epochs reuse stored initial hidden states computed by
  much older weights (stale recurrent state). This is standard for stored-state
  recurrent PPO but compounds with many small steps.

*Measure:* approx_kl and clip fraction per update from `metrics.jsonl`, and the
spread of per-minibatch KL. *Option:* batch several sequences per step (06 §P1).

## 2.9 Gradient clipping and finiteness checks

V1: `clip_grad_norm_` with `error_if_nonfinite=true`, finite gradients checked before
and after clipping, and parameters checked after the step
(`multimodal_trainer.cpp:170-178`). V2 does the same (`v2_live_train.cpp:189-198`).
**OK.**

Each check is a host synchronization. This is a performance matter, covered in
04 §3 and 05 §7; it does not affect correctness.

## 2.10 Checkpoint restoration

**V1** (`training/dev/live_checkpoint.cpp:76-170`) saves:

- an identity string: Torch version, architecture, device, seed, every PpoConfig
  field in hexfloat, cuDNN determinism and benchmark flags, and thread count;
- model and Adam state;
- three mt19937_64 streams;
- Torch CPU and CUDA RNG;
- counters and training mode.

Load requires a fresh trainer and an identical identity (135–142), then re-checks
finiteness and device placement.

The Python side (`scripts/dev/live_checkpoint.py`):

- binds configuration, template hashes and collector-source hashes (48–60);
- saves only when every environment is at a reset (102–109);
- on resume, recreates each environment at its saved episode index and verifies
  observation and mask hashes (153–166).

**OK.** The design limitation (reset-boundary only) is documented.

Two notes:

- The identity string does not mention the fused kernel. Python compatibility binds
  `trainer_sha256` (`live_checkpoint.py:54-56`), so a fused and a reference binary
  cannot be mixed. **OK.**
- The Python-side reward-adapter queue and `completed_episodes` are not checkpointed.
  This is acceptable because the adapter queue is cleared at every update
  (`training_reward.py:78`) and potentials reset per controller (`training_environment.py:28`).

**V2** (`v2_live_train.cpp:265-320`) additionally saves the recurrent hidden state
and requires deterministic algorithms plus the cuBLAS workspace setting (396–400).
**OK.**

## 2.11 V2 recurrent state handling

- **ACT** zeroes `hidden_` on reset, stores the pre-forward hidden state and reset
  flag with the transition, and advances `hidden_` (`v2_live_train.cpp:85-95`).
- **REWARD** computes the bootstrap value from the next frame using the post-step
  hidden state, without advancing it (110–115).
- **Replay** starts each 8-step sequence from the stored hidden state. The forward
  pass multiplies by `¬recurrent_reset` (`scalable_policy.cpp:286`), which cuts
  state and gradients at episode starts inside a sequence.
- **The audit** replays every sequence before any parameter change (147–165). It runs
  after `model_->train()`, which is harmless because the model uses only LayerNorm
  and GRUCell, whose behavior does not depend on training mode.

**OK.**

## 2.12 Reward transforms and shaping

**V1 potential shaping** is `γΦ(s') − Φ(s)` with Φ(terminal) = 0; time-limit
truncation keeps Φ(s') (`training_reward.py:6-15, 43-79`;
`training_environment.py:57-62`). This matches the potential-based construction the
docs cite. The adapter checks the ordered action and reward stream against the
collector before transforming (`training_reward.py:65-69`). **OK.**

**V2** `reward_components` (`train_v2.py:18-32`):

- clips per-decision delivery to [0, 64]/64, profit to ±256/256 and capital to
  4096/4096;
- applies −5 "bankruptcy" to **any** terminal transition (29).

*Measure:*

- how often each clip binds, using the retained `training_reward` components in
  `trajectory.jsonl`;
- whether any non-bankruptcy terminal exists in the V2 overlay. If one exists, the
  label is wrong and the penalty is misapplied.

## 2.13 Embedded development probes report quarter income (Defect, low)

`evaluate_architecture` stores `snapshot["company"]["income"]` as `"income"`
(`run_m08_live_architectures.py:236-243`) after at most `--evaluation-steps`
deterministic actions (default 64). `docs/DEVELOPMENT.md:353-354` states that
snapshot income and expenses describe the **current quarter**, which is why
`evaluate_live.py` uses lifetime deltas. The probe values land in
`run.json["development"]` (`train_live.py:151-155`). They are labeled as
non-evaluations in the docs, but the field name invites misuse.

*Fix:* in a development route, rename it to `quarter_income`, or compute
lifetime-delta income as `evaluate_live.py` does. Leave the frozen v1 script
untouched and wrap it. *Verify:* a unit test on a recorded transition list.

## 2.14 The newest V2 results cannot be reproduced from main (Defect)

This is covered in 01 §5.1. Main lacks the V2 entropy option, signed-log training
inputs and guide v3. Any future agent retraining "the current recipe" from main will
silently train a different recipe. *Fix and verification:* 07 Stage 1, item S1-4.

---

## Checks a future agent should run (not run here)

- `ctest --test-dir <build> --output-on-failure` for the native PPO tests, both
  with and without `--fused-policy`.
- `python scripts/dev/verify_gae_option.py` and `verify_entropy_option.py`, the
  existing default-equivalence tools.
- After adding the V1 behavior-replay audit: `compare_training_backends.py` with
  `--candidate-spatial-validation vectorized` on identical binaries. Traces must
  stay byte-identical and the recorded audit error must stay ≤ the kernel's
  documented error.
