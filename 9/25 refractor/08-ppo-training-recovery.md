# 08 — PPO training recovery plan (live V2)

This is specific, evidence-backed advice for getting live V2 PPO training back on
track. It is still a static review of commit `0595a72`; nothing was run.

Every number below is either:

- quoted from `docs/PROGRESS.md` or `handoff.md` with a line reference; or
- arithmetic on those numbers and on code constants, marked "derived".

Mechanisms are labeled **Certain** (follows from the code), **Supported** (fits the
recorded audits) or **Hypothesis**.

V1 has a recipe that passed its held-out confirmation (`DEVELOPMENT.md`). "Back on
track" therefore means V2, where every recent learned configuration has failed
advancement. §7 has short V1 notes.

---

## 0. Where training stands

Facts from the progress log:

| Evidence | Source |
| --- | --- |
| No learned V2 configuration beats **uniform-random choice under the same public guide** on sampled profit and cash. The best table is 1,122–1,228 passengers and 3,179–3,833 profit for learned models, versus uniform at 1,182.5 / 3,629. | `PROGRESS.md:1122-1141` |
| The budget8192 eight-map model fixes greedy initiation (2/2 development maps) but its sampled profit is still 242 below uniform. | `PROGRESS.md:571-590` |
| Retraining with guide v3 **collapses to WAIT**: stage-zero WAIT probability .928–.981; greedy repays 9× then WAITs 503 decisions; multi-choice WAIT selections double (1,547 → 3,077). The first 1,728 decisions exactly match the control run, so the collapse emerges from training dynamics, not from different early data. | `PROGRESS.md:113-140` |
| Entropy .01 → .001 regresses service 6/6 → 4/6 sampled. | `PROGRESS.md:334-341` |
| Construction gets **negative** advantage. Mean multi-choice road advantage is −0.79 (λ .95) and −0.25 (λ 1) even when delivery is inside the same 128-step rollout. Depot advantage averages −0.435 (horizon 256). Median road → delivery lag is 59 decisions, with direct GAE weight ≈ .027. | `PROGRESS.md:1066-1070, 1110-1112, 745-748` |
| Most training decisions have **no choice**: 853 choices and 3,243 forced WAITs in 4,096 decisions, with 31/64 rollouts containing no choice (budget8192 extension); 692/4,096 choices at horizon 256; 1,590/4,096 in the eight-map parent. | `PROGRESS.md:558-560, 743-745` |
| Every model makes about 8 repayments before service. Repayment probability is 0.4478 and changes by at most 3e-8 across cash 20,000–1,000,000 on raw features (cash and debt are divided by 1e9). | `PROGRESS.md:1008-1009, 1056-1059`; M15 patch `structured[8..9]` |
| The liquidity trap: 9 repayments leave 3,862 cash after the depot, BUY_BUS disappears, and the game WAITs for 478 decisions. Frozen weights plus borrowing (guide v3) recover 9/9. | `PROGRESS.md:355-374, 62-75` |
| More budget helps greedy: 4,096 → 8,192 decisions moved development greedy 0/2 → 2/2, with mean first START 47.3 → 27.3 during training. | `PROGRESS.md:553-577` |

The pattern is that **the policy drifts toward WAIT and repayment**. When it does
build, it does not build better than uniform timing. Longer horizons, full-return
windows, lower entropy and more maps did not fix this.

---

## 1. Diagnosis: five mechanisms

### M1. Forced steps dilute the policy, entropy and KL terms by about 3–6×. Certain.

**Code.**

- `ppo_loss` averages the surrogate and the entropy over **all** samples in the
  minibatch (`ppo.cpp:191, 193`).
- In V2 a minibatch is one 8-decision sequence (`v2_live_train.cpp:170-188`).
- A forced step (one allowed row in the guide mask) has log-probability exactly 0
  under any parameters, ratio 1, entropy 0 and **zero policy gradient**. It still
  counts in the denominator.
- The value loss has no such dilution, because every step has a value error.

So relative to the intended coefficients, with choice fraction `f`:

| Recorded run | Choice fraction f | Effective entropy coefficient (nominal .01 × f) | Value weight relative to policy (0.5 / f) |
| --- | ---: | ---: | ---: |
| Eight-map parent | 1,590/4,096 = 0.388 | ≈ .0039 | ≈ 1.3 |
| Budget8192 extension | 853/4,096 = 0.208 | ≈ .0021 | ≈ 2.4 |
| Horizon 256 | 692/4,096 = 0.169 | ≈ .0017 | ≈ 3.0 |

These are averages; individual minibatches range from 0% to 100% choice.

Three consequences:

1. The "entropy .001" study really tested an effective coefficient around
   .0002–.0004. It regressed, which suggests exploration pressure was already too
   weak at nominal .01.
2. The shared trunk is trained mostly for value regression.
3. The logged `approximate_kl` and clip fraction are averaged the same way
   (`ppo.cpp:195-196`), so **they understate the per-decision policy change by the
   same factor**. Updates that look gentle may be large on the decisions that
   matter.

The global gradient clip at 0.5 (`v2_live_train.cpp:195`) acts on the combined
norm, so a dominant value gradient also shrinks the policy gradient's share.

### M2. Construction is charged immediately; its payoff is 59 decisions away. Supported.

**Code.** `reward_components` charges capital when it is spent:
`−min(capital, 4096)/4096` per decision, which is up to −1.0 for a bus
(`train_v2.py:24-28`). WAIT costs only the −1/64 decision cost. Delivery and profit
arrive about 59 decisions later (median), where the GAE trace weight is about
.027.

A "proceed" step therefore beats WAIT only if the **critic** already values the
progress. The recorded negative road and depot advantages show the critic does not.
Full-return windows (λ = 1, rollout 128) raised road advantage from −0.79 to −0.25
but did not make it positive (`PROGRESS.md:1110-1112`).

### M3. The WAIT attractor. Supported.

M1 and M2 feed back on each other:

- WAIT's advantage is higher, so P(WAIT) rises.
- Fewer completed constructions per episode means less service reward in the data.
- The critic learns even less that progress pays.
- Construction advantages stay negative.
- The only counterforce, entropy, is diluted about 5× (M1).

Identical settings can land on either side of this fixed point, which fits the
guide-v3 retraining diverging after an exact 1,728-decision prefix. It also fits
the full-return and 16-map policies choosing WAIT on every familiar training reset
(`PROGRESS.md:1113-1115`).

### M4. The policy cannot see cash on main, and the guide permits a liquidity trap. Certain.

**Code.**

- On main, the V2 trainer reads raw features with cash and loan divided by 1e9
  (M15 patch, `structured[8..9]`). The signed-log option exists only in a worktree
  (01 §5.1).
- The guide offers repayment whenever `balance ≥ 20,000 and loan ≥ 10,000`
  (`scripts/dev/guide_v2.py:67-70`), without regard to the remaining plan and bus
  cost.

**Recorded.** Repayment probability is insensitive to cash (≤ 3e-8). All models
repay about 8 times before service, and a 9th repayment on the small map traps the
game with no bus.

PPO cannot learn to avoid a rare, episode-fatal, **delayed** consequence of an
action whose input features it cannot see.

### M5. Noisy, over-stepped optimization. Supported for the step count; the Adam-drift part is a Hypothesis.

- Each Adam step uses 8 correlated decisions (`v2_live_train.cpp:68, 170`).
  Rollout 64 gives 32 steps per update, while there are only about 13 choice
  decisions per update on average (derived: 853 / 64 updates).
- In the 31/64 updates with no choice at all, the policy heads get zero gradient,
  but Adam momentum (β1 = .9) keeps moving them for roughly 10 more steps.
- One recorded audit found a WAIT-only update *increased* depot probability on
  four histories (`PROGRESS.md:1155-1160`). This is a secondary suspect, not a
  proven cause.

### M6 (secondary). γ = .99 is short for this task. Supported.

- γ = .99 gives an effective horizon of about 100 decisions (derived).
- The payoff lag is about 59 decisions and evaluation lasts 512.
- A realized-return probe found repayment-only beating service at γ .99 on a weak
  training map (`PROGRESS.md:1041-1049`).

This matters mainly on marginal maps. Address it after M1–M4.

---

## 2. The recovery recipe

Apply the steps in order. Each is small, testable, and fixes a specific mechanism
above.

### Step 0. Instrument first (no behavior change)

Add to every V2 UPDATE record (`v2_live_train.cpp:206-210`) and `metrics.jsonl`:

- `choice_steps`: the count of transitions whose sampling mask has ≥ 2 rows. Store
  `candidate_mask.sum() >= 2` per transition at ACT (84–94).
- `entropy_choice`, `approx_kl_choice`, `clip_fraction_choice`: means over choice
  steps only.
- `advantage_choice_mean` / `advantage_choice_std` before normalization.
- `p_proceed`: mean probability of the guide's proposal on choice steps where a
  construction or service proposal is allowed. This is the WAIT-attractor gauge.
- `value_loss`, `explained_variance` (already present), and
  `policy_grad_norm` / `value_grad_norm` (two extra backward passes behind a debug
  flag, or separate norms of the head parameters).

Also add a **training-only probe**: at each checkpoint (every 8 updates), run CPU
inference on the 8 training maps' reset states and record P(proposal). This is the
existing idea from `v2-full-return-initial-choice-probe-01`, made routine; it uses
no development or held-out data.

*Verify:* traces, updates and weights must be byte-identical to a run without
instrumentation (logging only).

### Step 1. Choice-only loss accounting (fixes M1, and the M5 no-choice drift)

In `ppo.cpp`, add a weighted variant and keep `ppo_loss` unchanged so V1 and
existing binaries stay bit-exact:

```cpp
// w: float64 0/1 per sample, 1 = the sampling mask had >= 2 rows
LossResult ppo_loss_choice_weighted(nlp, olp, adv, v, ret, ent, const torch::Tensor &w, const PpoConfig &c)
{
    // same validation as ppo_loss, plus w in {0,1} and same shape
    const auto n = torch::clamp_min(w.sum(), 1.0);
    const auto log_ratio = (nlp - olp) * w;                 // forced rows are already 0
    const auto ratio = torch::exp(log_ratio);
    const auto surrogate = torch::minimum(ratio * adv, torch::clamp(ratio, 1 - c.clip_epsilon, 1 + c.clip_epsilon) * adv);
    const auto policy = -(surrogate * w).sum() / n;         // 0 when no choice: value-only step
    const auto value = torch::mean(torch::square(v - ret)); // unchanged: all steps
    const auto entropy = (ent * w).sum() / n;
    const auto total = policy + c.value_coefficient * value - c.entropy_coefficient * entropy;
    const auto kl = (((ratio - 1.0) - log_ratio) * w).sum() / n;
    const auto clip = (((ratio - 1.0).abs() > c.clip_epsilon).to(torch::kFloat64) * w).sum() / n;
    return {total, policy, value, entropy, kl, clip};
}
```

Normalize advantages over choice steps only: compute the mean and population
variance over entries where `w == 1`, and apply them to all entries (forced entries
never affect the policy term). If fewer than 2 choice steps exist in the rollout,
**leave advantages unnormalized** rather than zeroing them. The current
zero-variance rule (`ppo.cpp:138`) would erase a lone choice's signal.

Enable it with `--policy-loss choice-weighted` in `v2_live_train.cpp` and
`train_v2.py`. Bind the option in `checkpoint_identity()` (215–228) and in
`checkpoint_v2.compatibility()` (`checkpoint_v2.py:21-27`).

**Re-state coefficients after this change.** It raises the effective entropy and
policy weight about 2.5–6× (§1 M1 table). Two settings are sensible:

- **entropy .003**, which reproduces the historical *effective* exploration of
  the best runs (≈ .002–.004); and
- **entropy .01**, which gives the originally intended strength.

Do not reuse ".001".

*Verify:*

1. A unit test where all `w = 1` reproduces `ppo_loss` within 1e-12 in float64.
2. A test where all `w = 0` gives a zero policy term and an unchanged value term.
3. A native gate: default flags stay byte-identical to the current binary.
4. CPU/CUDA agreement at the existing 1e-4 metric tolerance.

### Step 2. Amortize capital through a potential (fixes M2, weakens M3)

Keep native rewards. Add policy-invariant potential-based shaping whose potential
is the **book value of what the company has built**, in reward units:

```
Φ(s)  = Σ over successful construction/purchase decisions so far in this episode of min(cost, 4096) / 4096
        (exactly the magnitudes the capital component charged; reset to 0 at episode start)
r'    = r + γ·Φ(s') − Φ(s),   with γ = the trainer's γ (.99)
Φ(s') = 0 at a true terminal; unchanged at time-limit truncation
```

What it does, algebraically:

- A build step charged `−k` now nets `−(1−γ)(Φ + k)`. For k = 1 (a bus) and Φ ≈ 1,
  that is about −0.02 instead of −1.0.
- Each later decision pays a "depreciation" of `(1−γ)·Φ`.
- The discounted total capital charge is **unchanged**, because shaping telescopes:
  it only re-times the charge. That is why optimal policies are unchanged
  (potential-based shaping).
- Bankruptcy additionally forfeits Φ.

The owned infrastructure is part of the public state, so Φ is a state function in
guided play, where nothing is sold or demolished.

**Implementation.** Only `scripts/dev/train_v2.py` changes:

```python
GAMMA = 0.99                       # assert equal to TRAINING_INFO gamma when reported
potential = 0.0                    # set to 0.0 whenever a new LiveV2 game starts
...
shaped = reward_components(transition)
spent = -shaped["components"]["capital"]                 # = min(capital, 4096) / 4096
next_potential = 0.0 if transition["terminal"] else potential + spent
shaping = GAMMA * next_potential - potential
reward = shaped["reward"] + shaping
potential = next_potential                               # truncation keeps it; reset handles new games
```

- Log `potential_before`, `potential_after` and `shaping` in `trajectory.jsonl`.
- Rename the schema to `development-v2-live-reward-2-asset-potential`. It is already
  bound in checkpoint compatibility (`checkpoint_v2.py:23`).
- Evaluation metrics are unaffected; they use native economics.

*Verify:*

1. An offline recomputation on retained trajectories. Per episode,
   `Σ γ^t shaping_t = γ^T Φ(s_T) − Φ(s_0)` to 1e-9.
2. Build-step shaped rewards equal `−(1−γ)(Φ + k) − 1/64` plus any delivery/profit.
3. Unit tests for terminal and truncation boundaries (mirror `tests/dev/test_training_reward.py`).

### Step 3. Remove the trap and give the policy eyes (fixes M4)

- **(a) Signed-log financial inputs** for all new V2 training. This requires 07 S1-1
  (port the worktree feature to main). Without it, liquidity-dependent decisions are
  unlearnable by construction.
- **(b) Guide v4: no repayment before service.** Add a new guidance constant; do not
  change v1 or v2. Allow `MANAGE_LOAN` repay only when the whole plan, including
  START, has executed (`self.policy.stage >= len(self.policy.plan["actions"])`)
  **and** the existing cash condition holds (`guide_v2.py:67-70`).
  - Rationale: repayment before service currently has almost no immediate reward
    effect, and its failure mode (no bus) is delayed and rare. That is the hardest
    case for PPO credit assignment.
  - Cost: some extra interest before service. The recorded interest effects are
    hundreds, not thousands (`PROGRESS.md:596-606`).
  - Keep v3 borrowing as the recovery path if a trap still arises.
  - **All controls (uniform, scripted) must be re-run under v4**; the retained v2/v3
    controls are not comparable.

*Verify:* the guide unit tests (`tests/dev/test_guide_v2.py`) prove v1/v2 masks are
unchanged, that v4 never exposes repayment before START, and that the masks remain
subsets of native legality.

### Step 4. Fewer, better optimizer steps (fixes the rest of M5); optional in the first study

- Batch 4 sequences (32 decisions) per minibatch at rollout 64. That gives 2
  minibatches × 4 epochs = **8 Adam steps per update instead of 32**. Stack
  `ScalablePolicyInput` along the batch dimension; the forward already supports
  batches (`scalable_policy.cpp:209-213`). Keep each sequence's stored initial
  hidden state and reset masks.
- Add a **KL guard on choice steps**: stop the remaining epochs of an update when
  `approx_kl_choice > 0.03`, and record the epoch at which it stopped.

*Verify:* sequences-per-minibatch = 1 reproduces today's updates exactly; run the
behavior-replay audit unchanged.

### Step 5 (conditional). γ = .995

- Use only if, after Steps 1–3, construction advantages on choice steps are still
  negative on maps where service is profitable.
- Add `--gamma` to the V2 trainer; γ is already in `checkpoint_identity()` and
  compatibility.
- Returns roughly double in scale, so either halve the value coefficient to .25 or
  add value-target normalization.
- Re-derive the Step 2 potential with the same γ.

### Recommended starting configuration

| Setting | Current reference (budget8192) | Recovery arm |
| --- | --- | --- |
| Policy/entropy averaging | all steps | **choice steps only** (Step 1) |
| Advantage normalization | all 64 steps | **choice steps; unnormalized if < 2** |
| Entropy coefficient | .01 nominal (≈ .002 effective) | **.003** (matched effective); second arm **.01** |
| Reward | native V2 components | **+ asset potential, γ .99** (Step 2) |
| Financial inputs | signed-log (worktree only) | signed-log, **ported to main** (Step 3a) |
| Guide | v2 | **v4: no repayment before service** (Step 3b) |
| Decisions per seed | 8,192 (128 updates × 64) | 8,192 (the budget that fixed greedy initiation) |
| Horizon / rollout / maps | 128 / 64 / 8 training maps | unchanged |
| γ / λ | .99 / .95 | unchanged (Step 5 only if needed) |
| Epochs / BPTT / minibatch | 4 / 8 / 1 sequence | unchanged in the first study (Step 4 second) |
| lr / clip / grad-norm / value coefficient | 3e-4 / .2 / .5 / .5 | unchanged |
| Seeds | 1 | **3 per arm** |

Change one mechanism per arm (§3). The table shows the final combination, not a
single jump.

---

## 3. Experiment protocol

Register the study before running it, per `AGENTS.md`.

**Arms**, all at 8,192 decisions per seed, 3 training seeds each (20260923, 20260924,
20260925), horizon 128, rollout 64, 8 training maps, signed-log inputs, bootstrap
reuse:

| Arm | Change vs previous arm | Tests |
| --- | --- | --- |
| A0 | Reference (guide v2, current loss, entropy .01). Seed 20260923 is the existing budget8192 run only if every setting matches; otherwise retrain it. | Baseline variance across training seeds |
| A1 | + choice-weighted loss, entropy .003 | M1 in isolation, at matched effective entropy |
| A2 | + asset potential | M2/M3 |
| A3 | + guide v4 (controls re-run under v4) | M4 |
| (A4) | A3 + 4-sequence minibatches + KL guard | M5; run only after A1–A3 are read |
| (A5) | A3 + entropy .01 | Exploration strength |

**Early stop (training data only).** Stop a seed and record it as failed if the
Step 0 probe shows P(proposal) < 0.1 on ≥ 6 of the 8 training maps at two
consecutive checkpoints after update 32. The protocol must pre-register this rule.

**Evaluation** (per 03 §7), final models only:

- **all 8 V2 development map seeds** × (1 greedy + 3 sampled action seeds);
- uniform and scripted controls under **the same guide version** as the arm,
  paired by map and action seed;
- no held-out access.

**Suggested advancement rule** (pre-register; thresholds are proposals):

1. every seed has zero invalid actions or bankruptcies;
2. greedy sustains service on ≥ 7/8 development maps for each seed;
3. the paired sampled profit **and** cash difference versus uniform (same guide) is
   > 0 for ≥ 2 of 3 seeds, and the pooled mean is > 0;
4. report nested-bootstrap intervals (training seed → map → action seed). With 3
   seeds, do not claim significance.

**Cost.** Recorded 8,192-decision CUDA training took about 5,030–5,060 s
(`PROGRESS.md:308, 86`). Four arms × 3 seeds is about 12 × 1.4 h ≈ 17 h of
serialized training (derived), before evaluation. To cut cost:

- run A0–A2 first (9 runs ≈ 12.6 h);
- or screen A1/A2 with 1 seed each on the training-only probe, then run full seeds
  for survivors (04 B11).

Get evaluation cost from existing `wall_seconds` records before scheduling.

---

## 4. What not to do next

Each item has already failed or is confounded here:

- lowering entropy (.001 failed, and is ≈ .0002 effective);
- longer training horizons (256 failed, with more forced WAITs);
- λ = 1 or rollout 128 alone (failed; road advantage still negative);
- more maps at a fixed budget (confounds diversity with visits; failed);
- retraining with guide v3 as the only change (collapsed);
- picking intermediate checkpoints or re-tuning on the two development maps
  already used;
- reward reweighting such as "economic" (V1 service collapse, `PROGRESS_HISTORY:384-388`).

Use potential shaping instead of reweighting.

## 5. Decision tree after the first study

- **A1 ≫ A0** (the WAIT collapse disappears, `p_proceed` stays high): M1 was the
  main problem. Keep choice-weighting as the V2 default, then evaluate A2 for
  economics.
- **A1 ≈ A0, A2 ≫ A1:** credit (M2) dominates. Keep A2 and then try Step 5 (γ .995)
  for the weak-map tail.
- **A2 ≈ A1 while construction advantage stays negative with a low choice-step
  explained variance:** the critic is the bottleneck. Next, try a separate value
  trunk or value-target normalization (06 P3), then a critic warm start from
  **training-map** uniform-guide rollouts (Hypothesis; new code). Never use
  development games for this.
- **A3 ≫ A2:** the trap mattered. Keep v4 during training. Test whether a
  signed-log policy trained under v4 still repays sensibly when evaluated under v2
  (this is a diagnostic; label it as an override).
- **All ≈ uniform:** the guide leaves little to learn beyond timing. Move effort to
  06 O1 (candidate parameter features) and C2 (guide annealing). Beating uniform
  under a planner that supplies geometry may not be a meaningful target.

## 6. Things to keep exactly as they are

- The behavior-replay audit (`v2_live_train.cpp:147-165`).
- Deterministic algorithms and the cuBLAS workspace.
- Time-limit bootstrap and GAE cuts at resets.
- The exact recorded sampling masks.
- The training/development/held-out separation.
- Failed runs, preserved rather than overwritten.

## 7. V1 notes

V1's balanced-reward, rollout-64 recipe passed its registered held-out check, so it
is not "off track". Three items still apply:

- Do not use `--episode-horizon 128/256` for any recipe that will be evaluated at
  512 without the 02 §2.4 feature check. V1's time features are 512-relative;
  V2's structured vector has no time features (M15 patch assigns only
  `structured[0..15]`).
- Add the V1 behavior-replay audit (07 S1-2).
- M1 is minor in V1, because WAIT and other actions are usually legal together.
  Confirm this by counting single-legal-action steps in `episode-metrics/*.jsonl`
  before assuming it.

## 8. Risks and open questions

- Step 2 shifts value targets by −Φ. Critic learning dynamics change even though the
  optimal policy does not. Watch explained variance.
- Step 3b changes the task (a mask restriction). Report every comparison against
  controls under the same guide.
- The effective-coefficient table uses average choice fractions. Actual per-update
  fractions come from Step 0 instrumentation.
- The Adam-momentum drift (M5) is only a hypothesis. The one related recorded audit
  did not support it.
