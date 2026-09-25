# 06 — Strategy and refactor options

Static review of commit `0595a72`; nothing was executed. Each option cites the
repository evidence that motivates it and states expected benefit, tradeoffs,
dependencies and a test.

**None of these is a guaranteed improvement.** The project's own history shows
several plausible changes that failed:

- economic reward;
- entropy 0.05 for the CNN;
- entropy 0.001 for V2;
- horizon 256;
- eight maps at a fixed budget.

Treat every learning-side option as a registered experiment with ≥ 3 training
seeds and the evaluation protocol from 03 §7.

Confidence labels:

- **Strong evidence**: the repository shows the problem directly.
- **Suggestive**: consistent with recorded results.
- **Speculative**: reasoned, but untested here.

---

## A. PPO

### P1. V2: more samples per gradient step. Suggestive.

- **Evidence:** each Adam step uses one 8-decision sequence
  (`training/dev/v2_live_train.cpp:68, 170`), giving 16–64 steps per update on
  8 correlated samples. UPDATE is 33.55% of recorded wall time (`PROGRESS.md:1169`).
- **Option:** process `k` sequences per minibatch (for example k = 4, i.e. the whole
  32-decision rollout, or 4 of 16 at rollout 128). Stack them in the batch
  dimension; `ScalablePolicy::forward` already takes a batch (`scalable_policy.cpp:209-213`).
  Keep the stored-initial-hidden replay per sequence.
- **Benefit:** lower-variance gradients and fewer, larger device calls, so UPDATE
  time should drop.
- **Tradeoffs:** fewer optimizer steps per update, and different effective learning
  dynamics. Learning rate or epochs may need retuning. It is not a pure refactor.
- **Dependencies:** batching all `ScalablePolicyInput` fields (`v2_live_input.cpp:203-212`
  currently uses batch 1).
- **Test:**
  1. A native test that k = 1 reproduces today's metrics exactly.
  2. A CPU/CUDA agreement run.
  3. A registered 3-seed comparison at matched decisions, reporting approx_kl, clip
     fraction and explained variance per update, plus the 03 §7 evaluation.

### P2. Do not spend PPO updates on forced decisions. Strong evidence of waste; benefit Suggestive.

- **Evidence:** the horizon-256 V2 audit found "only 692/4,096 steps offering a
  choice … 3,404 forced WAIT steps and 47/64 entire rollouts without a choice"
  (`PROGRESS.md` "extend training episodes to 256 decisions"). A single-legal-row
  step has log-probability 0 for any parameters, so it contributes no policy
  gradient. It still:
  - enters advantage normalization (`v2_live_train.cpp:141`);
  - enters the minibatch mean (`ppo.cpp:191`), diluting informative steps;
  - costs a forward and backward pass.
- **Options:**
  - (a) **Masked policy mean:** average the policy and entropy terms only over steps
    with ≥ 2 legal rows. Normalize advantages over those steps only. The value loss
    stays over all steps.
  - (b) **Semi-MDP compression:** when the guide or legality leaves exactly one row,
    execute it without a network decision. Fold its rewards into the next real
    decision with per-transition discount γ^k, which requires a per-step discount in
    `compute_gae` (currently a scalar γ, `ppo.cpp:90-128`).
- **Benefit:** stronger signal per update. Option (b) also removes most game→trainer
  round trips in guided phases.
- **Tradeoffs:** (a) changes the loss normalization. (b) changes the decision time
  scale, the value target semantics and checkpoint identity, and must keep "one
  action per STEP" auditing.
- **Dependencies:** (b) needs a versioned GAE API and collector changes on both the
  V1 and V2 development routes.
- **Test:** unit tests for masked means and per-step discounts, reducing exactly to
  today's formulas when all steps are free choices or k = 1; then a 3-seed
  registered comparison.

### P3. Stop reward scale from steering the shared trunk. Suggestive.

- **Evidence:** in V1 and V2, the policy and value heads share the representation
  (`multimodal_model.cpp:153-154`; `scalable_policy.cpp`). The value coefficient is
  fixed at 0.5 (`ppo.h`). Reward modes change the return scale
  (`scripts/dev/training_reward.py:92-109`; `train_v2.py:26-29`). The balanced reward
  changed passengers and cash in opposite directions (`PROGRESS_HISTORY_2026-09-23.md:1130-1139`).
- **Options:** running return normalization (standardize value targets with running
  statistics that are stored in checkpoints), or a separate value MLP head trunk.
- **Tradeoffs:** another piece of state to checkpoint and bind; the ONNX export only
  needs the policy.
- **Test:** check that the value-loss to policy-loss ratio stabilizes across reward
  modes, then run a paired 3-seed evaluation.

### P4. V2 entropy decomposition. Suggestive.

- **Evidence:** the PPO entropy is the joint candidate entropy
  (`v2_live_input.cpp:229-231`), `H(family) + E_f H(candidate|f)`, which grows with
  the number of candidates in likely families. Entropy .001 regressed service
  (`PROGRESS.md` "lower entropy regresses service"); entropy .05 did not prevent CNN
  collapse (`PROGRESS_HISTORY:1141-1145`).
- **Option:** first log the two terms separately (no behavior change). If they
  differ as suspected, use separate coefficients `c_family` and `c_conditional`.
- **Tradeoffs:** one more hyperparameter; it must be bound in checkpoint identity
  as the entropy coefficient already is.
- **Test:** the logging-only change must reproduce traces exactly. The coefficient
  change then needs a registered 3-seed study.

### P5. KL guard. Speculative.

- **Evidence:** `approximate_kl` is computed and logged but never acted on
  (`multimodal_trainer.cpp:183`; `v2_live_train.cpp:200`). V2 uses many small steps.
- **Option:** stop the remaining epochs of an update when mean KL exceeds a target
  (for example 0.02), and record where it stopped.
- **Tradeoffs:** makes the update count data-dependent; deterministic given the same
  data, so resume exactness is preserved.
- **Test:** first read the KL distributions from existing `metrics.jsonl` files. If
  KL rarely exceeds the target, drop this option.

### P6. V1 rollout length above 64. Suggestive; depends on K2 in 05.

- **Evidence:** the V1 launcher allows only 32 or 64 because of the 64 MiB frame
  limit (`train_live.py:53-54`). The spatial tensor is 99% of UPDATE bytes (05 §8).
  The 64-step rollout was the recipe that passed held-out confirmation
  (`DEVELOPMENT.md`).
- **Option:** after a structured-only protocol exists for the MLP, test rollout 128.
- **Test:** a matched-transition paired comparison with `report_credit_experiment.py --axis rollout`.

---

## B. Reward

### R1. Keep native and shaping-only changes as defaults; treat reweighting as a separate objective. Strong evidence.

- **Evidence:**
  - free town-selection toggling exploited the WAIT penalty (`PROGRESS_HISTORY:153-155`);
  - the economic reward collapsed service to 0/6 by avoiding spending
    (`PROGRESS_HISTORY:384-388`);
  - balanced reward traded passengers for cash (1130–1139).
- **Option:** prefer potential-based shaping (`ServicePotentialReward`), which
  provably preserves optimal policies, for exploration help. Keep reweighted
  objectives as separately labeled tasks, judged on the multi-metric acceptance
  already in `evaluate_registered.py:60-66`.
- **Test:** unchanged; follow the existing registered workflow.

### R2. V2 capital clip binds on bus purchases. Strong evidence.

- **Evidence:** `train_v2.py:28` clips capital at 4,096 per decision
  (`-min(capital, 4096)/4096`). `PROGRESS.md` records a bus purchase costing 4,921
  (line 366: "buys the same engine/depot for 4,921"). So buying a bus is penalized as if it
  cost 4,096. Profit is clipped to ±256 per decision (27).
- **Option:** measure first. From `trajectory.jsonl` (`training_reward.raw_capital`
  and `raw_operating_profit`), count how often each clip binds and by how much. If
  the capital clip routinely binds on the key purchase, raise its bound or use a
  smooth transform (for example a signed log, as in the financial inputs).
- **Tradeoffs:** changes the objective, so it needs a new reward schema version
  (`development-v2-live-reward-1` becomes `-2`).
- **Test:** an offline recomputation of rewards on retained trajectories to show
  the difference, then a registered comparison.

### R3. V2 "bankruptcy" is applied to every terminal. Measure.

- **Evidence:** `train_v2.py:29`.
- **Option:** check the terminal reason in the transition, and if non-bankruptcy
  terminals exist, apply the penalty only for bankruptcy.
- **Test:** grep retained trajectories for terminal transitions and their reasons.

### R4. Liquidity traps. Suggestive; prefer observation fixes over reward hacks.

- **Evidence:** repayments leave too little cash to buy the first bus; the policy
  then WAITs for hundreds of decisions (`PROGRESS.md:361` "Nine initial repayments remove
  90,000; cash is 3,862 …"; the borrowing guide v3 study).
- **Option:** before adding reward terms, expose the relevant quantity (cash versus
  the cheapest next required purchase) as a public observation feature, and fix
  action aliasing (O1). Reward penalties for repayment would bake in one strategy.
- **Test:** an offline check that the feature is public and computable from the
  existing observation, then a registered comparison.

---

## C. Observation

### O1. Represent action parameters, not just families. Strong evidence.

- **Evidence:** borrow and repay have different command parameters and priorities
  but identical 32-float candidate features, and both priorities normalize to
  float32 1.0. There are feature aliases among 856/1,024 road rows, 765/768 stop
  rows and 509/512 depot rows. The live reader consumes only the family word
  (`PROGRESS.md:160-175`; `v2_live_input.cpp:190-195` reads only `parameters[row*16]`).
  "Explicit action-parameter representation is a concrete unresolved prerequisite"
  (`PROGRESS.md:172-173`).
- **Option:** version a new candidate schema that adds normalized command parameters:
  - loan direction and amount;
  - endpoint tile offsets relative to the company HQ or map center;
  - orientation one-hots;
  - optionally a hashed embedding of `stable_key`.

  Train it as a new architecture version.
- **Benefit:** the policy can finally distinguish actions that the guide currently
  disambiguates for it. This is a prerequisite for unguided play.
- **Tradeoffs:** a native TENSORS schema bump invalidates checkpoints, ONNX packages
  and retained controls for neural comparisons. Retained scripted and uniform
  controls stay valid if the engine is unchanged.
- **Dependencies:** `enable_v2_live.py` overlay, `v2_live_input.cpp`,
  `v2_export_policy.py`, the ONNX golden tests.
- **Test:**
  1. An offline aliasing audit on retained frames, which should drop to about zero
     aliases.
  2. A CPU/CUDA agreement run.
  3. A registered 3-seed comparison.

### O2. Horizon-consistent time features. Suggestive.

- **Evidence:** 02 §2.4 (`m04` patch lines 201–202, 261–264, which hard-code 512).
- **Options:** (a) do not use `--episode-horizon` below 512 for final recipes; or
  (b) randomize or anneal the horizon (C1); or (c) a versioned observation with
  horizon-relative features.
- **Test:** 03 N9 measurement (feature histograms plus per-window evaluation).

### O3. Remove the unused spatial input from the MLP pipeline. Strong evidence of cost; no learning effect.

- **Evidence:** the MLP forward ignores spatial (`multimodal_model.cpp:134-139`), yet
  it is validated, serialized, decoded and uploaded everywhere (05 §7.2, 04 §2).
- **Option:** K1 and K2 in 05. There is no learning change.
- **Test:** byte-identical traces and models.

---

## D. Action space

### A1. V1: shorten the town-selection credit path. Suggestive.

- **Evidence:** free selection toggles (`PROGRESS_HISTORY:153-155`). Greedy traces
  alternate town selection instead of building (`PROGRESS_HISTORY:1036`).
- **Option:** keep universal decision cost (already available), or offer compound
  "select + build" actions in a new action-contract version.
- **Tradeoffs:** a V1 action-contract change is expensive (frozen M05); consider it
  only if V1 remains a research target.

### A2. V2: semi-MDP compression of forced actions. See P2(b).

### A3. V2: expose the family/candidate factorization to PPO. Speculative.

- **Evidence:** the distribution is built hierarchically (`v2_live_input.cpp:214-232`).
- **Option:** keep the same joint log-probability for the ratio (mathematically
  unchanged), but report and optionally regularize family and conditional terms
  separately (P4).

---

## E. Curriculum

### C1. Horizon schedule instead of a fixed short horizon. Suggestive.

- **Evidence:**
  - short horizons give more construction resets per budget (`DEVELOPMENT.md`
    curriculum section);
  - horizon 256 failed advancement with more forced WAIT steps (`PROGRESS.md`
    "extend training episodes to 256");
  - time features are 512-relative (O2).
- **Option:** sample the horizon from {128, 256, 512}, or anneal 128 → 512 over
  training. Record the schedule in checkpoint compatibility.
- **Test:** a registered 3-seed matched-budget comparison, with per-window metrics.

### C2. Guide annealing. Suggestive.

- **Evidence:** "Route geometry comes from the planner, so passenger service by
  itself does not demonstrate learning" (`DEVELOPMENT.md` V2 guide section).
  Uniform-with-guide rivals the learned policies (`PROGRESS.md` tables).
- **Option:** a schedule that gradually allows non-guide legal rows (for example
  with probability ε, or only in selected families), keeping the exact sampling
  mask recorded.
- **Dependencies:** O1. Without parameter features, unguided choices are aliased.
- **Test:** compare against uniform-with-the-same-mask controls at every stage.

### C3. More maps, with budget scaled to match. Suggestive.

- **Evidence:** 8 maps at a fixed 4,096-decision budget lowered point estimates
  relative to 4 maps (`PROGRESS.md` "eight training maps at fixed budget"). That
  experiment confounds diversity with visits per map.
- **Option:** scale decisions with map count, or evaluate generalization on the 8
  development seeds (03 §7.1) to see whether fewer maps are overfitting.

### C4. Mid-game starts. Speculative.

- **Option:** begin some episodes from saved post-construction states to train
  operations and finance separately.
- **Dependency:** engine save and load at arbitrary points. The repository supports
  exact recovery only at resets (`DEVELOPMENT.md`).

---

## F. Code organization

### K1. Replace monkeypatching with a development collector. Strong evidence.

- **Evidence:** module-global patches in five places (01 §5.3). Correctness depends
  on context-manager nesting (`train_live.py:128-138`) and one run per process
  (`training_environment.py:4-5`).
- **Option:** a new `scripts/dev/collect_live.py` that imports only pure helpers
  from `scripts/v1`: `structured`, `legal_mask`, `partition_templates` and the
  controller class. Pass the rollout length, controller factory, environment factory,
  validator and reward adapter explicitly. Keep `run_m08_live_architectures.py`
  frozen.
- **Benefit:** a place to implement 05 K2/K3, P2 and concurrent environment
  stepping without touching release code.
- **Test:** traces byte-identical to the current `train_live.py` for the same seed
  and settings (the `compare_training_backends.py` design).

### K2. Bring the worktree-only V2 features into main behind default-off flags. Strong evidence.

- **Evidence:** 01 §5.1. The entropy option, signed-log training inputs and guide v3
  exist only in worktrees.
- **Option:** port each feature with its existing default-equivalence proof pattern
  (`verify_entropy_option.py`, `verify_gae_option.py`). Defaults must reproduce
  current main exactly.
- **Test:** default-equivalence runs, plus nondefault CPU/CUDA agreement, following
  the documented qualification recipes.

### K3. Commit study drivers and registration schemas. Strong evidence.

- **Evidence:** 03 §1. The advancement logic lives in `runs/`.
- **Option:** `scripts/dev/studies/<study>.py` plus a JSON schema for registrations.
  Keep per-run registrations in `runs/`, but have them reference committed driver
  hashes.

### K4. Sync-free validation in training paths. Strong evidence of syncs; benefit Measure.

- **Evidence:** V1 already has `require_finite_without_cuda_synchronization`
  (`multimodal_model.cpp:27-30`). V2's validators `.item()` on every input
  (`scalable_policy.cpp:17-41, 240-251`), and both update loops check every parameter
  with `.item()` (`multimodal_trainer.cpp:34-40, 172-178`; `v2_live_train.cpp:191-198`).
- **Option:** accumulate `isfinite(...).all()` flags on the device and check once per
  minibatch, and once per ACT for inference. Keep the fail-closed behavior and the
  diagnostic names; on failure, re-run the precise per-tensor checks to name the
  culprit.
- **Test:** outputs bit-identical, with injected-NaN tests still failing with named
  tensors. Measure with the paired timing design.

### K5. One evaluation-summary library. Suggestive.

- **Evidence:** V1 `report_learning.summarize`; V2 `service_v2.summarize` and
  `report_v2_learning.py`; differing metric names across routes.
- **Option:** a shared module that emits per-map, per-seed and hierarchical-bootstrap
  summaries for both (03 §7.3).

### K6. A versioned development trainer protocol. Suggestive.

- **Option:** add message types (structured-only ACT/UPDATE, VALUE) to a development
  copy of the M08 service, with a protocol version in `run.json` and checkpoint
  compatibility. Release frames stay unchanged.

---

## Suggested dependency order

```
K2 (main reproduces current V2 recipe)  ─┐
K3 (study code reviewable)               ├─► evaluation reliability (03 §7) ─► learning experiments (P1–P4, R2, O1, C1–C3)
K1 (dev collector) ─► 05 K1–K4, P2 ─────┘
O1 (parameter features) ─► C2 (guide annealing)
```
