# 03 — Evaluation audit

Static review of commit `0595a72`; nothing was executed. This document describes
exactly how models are evaluated today, then lists the sources of noise, bias and
incomparable results, each labeled **Confirmed**, **Risk** or **Measure**.

## 1. Evaluation routes

| Route | Entry point | Purpose | Counts as evidence? |
| --- | --- | --- | --- |
| E-probe | `run_m08_live_architectures.py:evaluate_architecture` (210–248), called from `train_live.py:151-155` | Deterministic smoke on each development map after training, `--evaluation-steps` actions (default 64) | No. The docs say so (`DEVELOPMENT.md` "The embedded 64-action probes do not count as full evaluation"). |
| E-dev (V1) | `scripts/dev/evaluate_live.py` | Complete 512-action development episodes for neural packages and baselines | Yes, development only |
| E-heldout (V1) | `scripts/dev/evaluate_registered.py` | Frozen, preregistered final-split confirmation of three models | Yes, once; no tuning |
| E-ckpt (V1) | `export_checkpoint.py` → E-dev, compared by `report_checkpoints.py` | Training-only checkpoint selection diagnostic | Diagnostic |
| E-v2 neural | `scripts/dev/infer_v2.py` | Live recurrent policy games (greedy or sampled), optional CPU cross-check | Yes, development |
| E-v2 controls | `scripts/dev/evaluate_guide_v2.py` | Uniform, scripted and repay-first controls under the identical guide mask | Yes, development |
| E-mcp | `mcp_v2.py`, `shared_v2.py`, `play_mcp_*`, `report_mcp_matches.py` | Two-company matches (neural, LLM, scripts) | Development. Read only at the summary level in this review. |

Registered V2 studies, which define the "nine evaluations per model" matrix and the
advancement criteria, are driven by scripts in ignored `runs/` directories
(`PROGRESS.md:201, 326, 375, 539`). **Their logic cannot be audited from the
repository.**

---

## 2. V1 complete-episode development evaluation (`evaluate_live.py`)

### Which checkpoint is tested

The `--package` directory, normally `run.json["model"]["path"]` from a completed
`train_live.py` run. That is the final weights after the last update, exported by
`client.export_evaluation_model` (`train_live.py:145-150`). Earlier checkpoints are
evaluated only when exported with `export_checkpoint.py`.

Package integrity:

- hashes are snapshotted before and after the episode (`evaluate_live.py:110, 194-196`);
- the evaluator hashes the model file on load (`evaluation_model.cpp:315-318`);
- the evaluator checks the parameter-state hash is unchanged at exit
  (`m09_evaluator_main.cpp:252, 273-274`).

### Maps

The development split has exactly two templates, `m02-template-05` and
`m02-template-06` (`run_m07_cpu_ppo.py:349-356`). `--split training` or
`--templates` can select others. The final templates 07 and 08 are refused
(`evaluate_live.py:77-85`).

### Games and steps

Jobs are the product policy × template × seed (`evaluate_live.py:258-259`):

- `random` and `sampled` use every `--seeds` value (default 20260923, 20260924 and
  20260925);
- `wait`, `scripted`, the fleet scripts and `greedy` use only the first seed.

Per neural package that gives **2 greedy + 6 sampled** episodes. Each episode runs
until the engine reports termination, with at most `action_horizon` actions: 512
actions at 128 ticks each for the ordinary reset (`evaluate_live.py:117`,
`run_m06_reward_trajectory.py:113-123`). An episode that ends without a termination
reason raises an error (164–165).

### Seeds

The map, scenario and simulation seed are fixed by the template. `--seeds` only
seeds the policy's action sampling:

- for neural policies, `EvaluatorClient.start(..., sampling_seed=seed)` seeds an
  mt19937_64 in the evaluator (`evaluation_model.cpp:300`);
- for `random`, `random.Random(seed)` is used (`evaluate_live.py:109, 127-128`).

The same sampling seeds are used across models, which gives common random numbers
for paired comparisons. The engine is treated as deterministic given actions;
`deterministic_baselines_repeated: False` is recorded (255).

### Opponents

None. V1 is single-company. Two-company play exists only in V2 MCP matches.

### Action selection

- **Greedy:** `argmax` of masked log-probabilities (`evaluation_model.cpp:339`).
- **Sampled:** CPU `sample_masked_actions` (340).
- **Inference:** CPU LibTorch in `m09_evaluator` with `set_num_threads(6)`
  (`m09_evaluator_main.cpp:319`), or CPU ONNX Runtime with `--backend onnx`.
- **The custom CUDA kernel is never used in evaluation.**

### Metrics per episode

Computed at `evaluate_live.py:166-188` from lifetime reward-source deltas, not
snapshot quarters:

- passengers, operating profit, operating income and expenses;
- capital spend, `operating_profit_less_capital`, final balance and `balance_change`;
- invalid actions (native rejections), vehicle losses, idle bus ticks;
- first delivery and first running bus;
- final buses and routes, action histogram;
- 128-action windows;
- `service_in_all_final_three_windows`: exactly 4 windows, with passengers > 0 and
  operating profit > 0 in each of the last 3.

### Aggregation

- `report_learning.summarize` (22–29) gives per-policy means over **all episodes
  pooled across both maps**, the profit range, a sustained-service count, and
  invalid-action and bankruptcy totals.
- Uncertainty is computed across **three independent training seeds** using a
  Student-t interval with df = 2 (t = 4.3027) on per-seed means (`report_learning.py:60-70`;
  `report_credit_experiment.py:72-75`).
- Paired differences require identical `(template, sampling seed, scenario sha)`
  matrices (`report_credit_experiment.py:78-79, 124-134`; `report_learning.py:97-100`).
- Engine identity must match across compared runs (`report_learning.py:39-40`).

### Parallelism

A `ProcessPoolExecutor` using `spawn`, with 1–4 workers (default 2)
(`evaluate_live.py:266-271, 294`). Results are appended in job order. Timing depends
on the worker count; results do not.

## 3. V1 held-out confirmation (`evaluate_registered.py`)

- The registration file and its `.sha256` companion are required. So are hashes of
  the evaluation code, engine, evaluator and each of three model packages, plus the
  seed-to-manifest match (77–95).
- The protocol is fixed by `validate_registration` (20–37): maps 07 and 08, 512
  actions, balance 100,000, sampling seeds 23/24/25, sampled as primary and greedy as
  diagnostic, baselines wait/random/scripted/one-bus, ≥ 5/6 sustained per model,
  zero bankruptcies and zero invalid actions.
- Episodes run sequentially with `bridge_validation.configure("fast")` (119–133).
- The case matrix is checked exactly (44–54). The seven acceptance checks are at 60–66.

This is methodologically the strongest evaluation in the repository.

## 4. Best-model selection

**V1.**

- The final model of each run is the candidate.
- Recipe choices (reward mode, rollout length, λ, entropy, horizon) come from
  paired development comparisons on maps 05/06 with three training seeds.
- The three held-out models were "selected from development results before held-out
  outcomes" (`DEVELOPMENT.md`, export section).
- Intermediate-checkpoint selection exists only as a registered, **training-only**
  diagnostic (`report_checkpoints.py`). It carries the caveat that it "followed
  observation of final-model failure" (88).

**V2.**

- "Only each final update-128 model is selected" (`PROGRESS.md:40`).
- Each model gets nine 512-decision games: 2 development greedy, 6 development
  sampled (2 maps × 3 action seeds) and 1 training-map greedy (`PROGRESS.md:40-43`).
- Advancement is preregistered per study. Examples: all nine games sustain service;
  zero invalid actions or bankruptcies; sampled means at least all six retained
  learned controls; profit and cash above uniform-with-guide (`PROGRESS.md:46-50`).

## 5. V2 evaluation mechanics (`infer_v2.py`, `evaluate_guide_v2.py`)

Per decision, `infer_v2.py` does the following (197–237):

1. OBSERVE, then TENSORS; Python hashes both binary files (`checked_tensors`, 24 onward).
2. Guide filtering, if the model was trained with a guide. `--guidance-override`
   can substitute a different guide version (159–163), and the substitution is
   recorded.
3. OBSERVE and TENSORS **again**, to prove the state is unchanged (204–205).
4. A policy request: the native process reads the files, runs the forward pass and
   returns all 4,096 probabilities as JSON (`v2_live_infer.cpp:56-75`).
5. Python checks the probability sum, the mask and nonnegativity (211–213).
6. With `--compare-cpu`, a CPU reference process repeats the inference, with
   tolerances 1e-5 on probabilities and 1e-4 on values (214–219).
7. ACT, then STEP. The game must advance exactly 128 ticks.

Maps come from the V2 seed ledger. The development set holds **8 map seeds**
(`config/v2/m15-scalable-contract.json`), but studies use 2
(`PROGRESS.md:42, 102, 150`). Controls run through `evaluate_guide_v2.py` with the
same guide and legality (45–56). Sampling seeds drive `random.Random` for uniform
play and the native mt19937_64 for neural play.

---

## 6. Sources of noisy, biased or incomparable results

Ranked by expected impact on conclusions.

| # | Issue | Evidence | Label | Effect |
| --- | --- | --- | --- | --- |
| N1 | **Two evaluation maps.** V1 is fixed by contract. For V2 it is a choice: 8 development seeds exist. | `run_m07_cpu_ppo.py:349-356`; `m15-scalable-contract.json`; `PROGRESS.md:42` | Confirmed | Map-level variance is neither estimated nor controlled, and the maps differ strongly (PROGRESS reports large vs small map outcomes). Any "improvement" can be a map-specific interaction. |
| N2 | **V2 studies usually have one training seed.** Intervals come from action seeds with df = 2. | `PROGRESS.md:150-151, 730, 782, 994-995` | Confirmed (acknowledged in docs) | Results are conditional on one trained network, so training-seed variance, which is usually the dominant term in RL, is invisible. Several "advancement fails / lead" conclusions rest on this. |
| N3 | **Greedy is one episode per map per model**, because the engine is deterministic given actions. | `evaluate_live.py:258-259`; `PROGRESS.md:40-43` | Confirmed | Greedy "k/n" rates are counts over at most 2 maps × seeds. A single flipped near-tie argmax changes the result. |
| N4 | **Adaptive reuse of the same development maps** across dozens of studies (V1 05/06; V2's two map seeds). | `PROGRESS.md` and `PROGRESS_HISTORY_2026-09-23.md` | Risk | Winner's curse and recipe overfitting to these maps. V1 mitigated this once with the held-out registration; V2 has no held-out run. |
| N5 | **Pooled means across maps of different scale.** | `report_learning.summarize` (22–29) | Confirmed | The larger-economy map dominates profit and passenger means; improvements on the small map can be masked. |
| N6 | **Retained controls reused across studies**, e.g. "42 retained sampled controls" generated under earlier sources and guides. | `PROGRESS.md:79-81`; report tools check engine hash only | Risk / Measure | Comparisons stay fair only if engine, guide semantics, reward bookkeeping and evaluation code are identical. The V2 driver checks live outside the repository. |
| N7 | **Evaluation under a different guide than training** (`--guidance-override`, e.g. "frozen .001 + guide v3"). | `infer_v2.py:159-163`; `PROGRESS.md:62-75` | Confirmed (labeled) | Measures policy + intervention rather than the trained policy. Fine as a diagnostic; not comparable with native-guide rows. |
| N8 | **Training/evaluation backend mismatch in V1.** CUDA training (optionally with the kernel) vs CPU evaluation; the embedded probe uses the training device. | `train_live.py:151-155`; `evaluate_live.py:91,113` | Risk (low) | Float differences can flip greedy ties; probe and evaluation greedy traces can diverge. V2 has `--compare-cpu`; V1 has only offline replay tools. |
| N9 | **Horizon curriculum.** Training at 128 or 256 but evaluating at 512 with 512-relative time features. | 02 §2.4 | Risk | Late-episode windows (the ones scored) are out-of-distribution for such models, so they are compared at a disadvantage and comparisons against horizon-512 models confound curriculum with extrapolation. |
| N10 | **Embedded probe metrics** (64 steps, quarter income, CUDA backend) stored beside real results. | 02 §2.13 | Confirmed | Easy to cite accidentally as evaluation evidence. |
| N11 | **The "scripted" baseline reads the scenario source projection.** | `run_m09_evaluation.py:135-157` (`mask(include_source=True)`) | Confirmed (documented) | Privileged baseline. `one-bus` is the public-information comparator; keep the labels distinct. |
| N12 | **The sustained-service criterion is binary and threshold-based** (> 0 passengers and > 0 profit in each of the last three windows). | `evaluate_live.py:187-188` | Confirmed (design) | Coarse. Small economic changes flip it; pair it with continuous window metrics. Both are already stored. |
| N13 | **The V2 reward "bankruptcy" component fires on any terminal.** | `train_v2.py:29` | Measure | Affects training, not evaluation metrics, but can confound "bankruptcy" counts if other terminals exist. |
| N14 | **Timing is not controlled across workers.** | `evaluate_live.py:266-271` | Confirmed | Irrelevant to outcomes; relevant to any evaluation-time claims (04). |

### What is already done well

- Final-split access is refused outside the registered route (`evaluate_live.py:77-85`).
- Exact matrix checks and engine-hash checks in every report tool.
- Uncertainty intervals use training seeds as the unit; the report text refuses
  large-sample approximations (`report_learning.py:63-70`).
- Package hashes are checked before and after each episode, and model state is
  checked for immutability at evaluator exit.
- Full per-decision traces make every aggregate recomputable.
- Common sampling seeds across models give common random numbers.

---

## 7. Recommendations for reliable comparisons

In priority order. 07 Stage 2 turns each into an implementable task.

1. **V2: evaluate on all 8 development map seeds.** Keep the three action seeds for
   sampled play, and report per-map paired differences (candidate − control on the
   same map and seed). This costs roughly 4× the games of the 2-map protocol. 04
   explains how to pay for it.
2. **Make training seeds the unit of every advancement decision.** Require ≥ 3
   independent training seeds before a V2 study can "advance". Present
   single-seed studies explicitly as leads, as the queued replication study does.
3. **Hierarchical uncertainty in the report tools.** Add a nested bootstrap
   (training seed → map → action seed) next to the existing t-interval. Add the sign
   count of per-seed differences, and per-map tables to `report_learning.py` and
   `report_credit_experiment.py`.
4. **Hold out V2 maps now.** Register a V2 confirmation protocol on the
   `generalization` or `final` seed sets before more recipe tuning on the two
   development maps, mirroring `evaluate_registered.py`.
5. **Commit the study drivers.** Move the V2 registered study drivers
   (`experiment.py`, `finish_analysis.py`) into `scripts/dev/studies/` with their
   registration schemas, or at least commit their SHA-256 and a copy under
   `docs/project/`, so criteria and control provenance are reviewable.
6. **V1 CPU/training-device agreement.** Add an option in `evaluate_live.py`, or a
   one-off check, that replays the evaluated trace through the trainer's device and
   compares argmax and probabilities within the kernel's documented tolerance, as
   V2 `--compare-cpu` does.
7. **Keep probes out of evidence.** Rename the embedded probe fields (for example
   `probe_quarter_income`) or move them under `run.json["pipeline_probe"]`.
8. **Report per-window continuous metrics** (passengers and profit per window)
   alongside the binary sustained-service flag in summary tables.
9. **Pre-compute sample sizes.** From existing per-seed and per-map results, estimate
   the paired standard deviation per metric. Record in each registration the
   minimum detectable difference for the planned seeds × maps.

## 8. Open questions

- Is the OpenTTD simulation deterministic for a fixed map and action sequence when
  several workers run concurrently? The design assumes it. A byte-identity check of
  two concurrent greedy runs would confirm it cheaply.
- Which retained controls were produced by which source and guide version? This is
  recorded only in `runs/` records.
- Why were 2 of the 8 V2 development seeds chosen? Is it for cost (map size) or map
  properties? The rationale is not in the repository.
- Do any V1 production models come from the fused-kernel build? This matters only
  for N8.
