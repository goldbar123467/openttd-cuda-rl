# 01 — Project map

Static review of commit `0595a72` (branch `claude/funny-einstein-q6g19d`). Nothing
was built, run, trained, evaluated, profiled or tested. Line numbers refer to that
commit.

The repository contains two live learning paths that share one PPO core:

- **V1**: a single-company bus scenario with 41 discrete actions and an MLP, CNN or
  combined network. The custom CUDA kernel is on this path. Frozen release scripts
  under `scripts/v1` are reused by development wrappers in `scripts/dev`.
- **V2**: a recurrent "scalable" policy over up to 4,096 candidate actions, driven
  by the development adapter. Current research (`docs/PROGRESS.md`) is here.

A third path, the V2 M22 corpus campaign (`training/v2/src/m22_*`), learns from a
fixed corpus and reward tables rather than live games. It is out of scope except
where noted.

---

## 1. Component inventory

| Role | V1 (kernel path) | V2 (current research) |
| --- | --- | --- |
| Game engine | OpenTTD 15.3 with `integration/openttd/patches/15.3/m02..m09`. One headless worker process per episode: `scripts/v1/m03_bridge_protocol.py` `WorkerProcess` (line 298 onward), started by `scripts/v1/run_m07_cpu_ppo.py:start_environment` (68–96). | Development overlay built by `scripts/dev/enable_v2_live.py`, driven by `scripts/dev/live_v2.py` `LiveV2` with OBSERVE, TENSORS, ACT, STEP and CLOSE requests. |
| Bridge validation | Every response gets a CRC32C check, JSON decode and canonical re-serialization check (`m03_bridge_protocol.py:61-93, 96-103, 187-245`). `scripts/dev/bridge_validation.py` offers a "fast" table/regex variant. | JSON requests plus per-decision binary tensor files, which Python hashes (`scripts/dev/infer_v2.py:checked_tensors`, 24 onward). |
| Observation | Engine `EncodeRlObservation`: 256 structured floats plus a 32×32×32 spatial tensor, delivered as JSON (`integration/.../m04/0005-versioned-policy-observation.patch:193-264`). | Native binary files: a 2,182,927-byte observation and a 790,528-byte candidate file per frame (`training/dev/v2_live_input.cpp:148,181`). |
| Actions and masks | 41 actions with a legal mask from LEGAL_ACTIONS (`scripts/v1/run_m06_reward_trajectory.py:180-196`). | Up to 4,096 candidate rows in 12 families. An optional public-plan guide filters the mask (`scripts/dev/guide_v2.py`); only guide v1 and v2 exist on main (lines 8–10). |
| Reward | Native M06 scalar (`config/v1/m06-reward-trajectory-contract.json`). Optional development transforms in `scripts/dev/training_reward.py`. | Computed in Python by `scripts/dev/train_v2.py:reward_components` (18–32). |
| Rollout collector | `scripts/v1/run_m08_live_architectures.py:train_architecture` (74–207). It is wrapped by `scripts/dev/train_live.py:run` (63–169), which monkeypatches the collector's module globals. | `scripts/dev/train_v2.py:run` (35–212). |
| Network | `training/v1/src/multimodal_model.cpp` (MLP, CNN, combined; forward at 128–158). | `training/v2/src/scalable_policy.cpp`: entity, graph and spatial encoders feeding a GRUCell (forward at 207 onward). |
| PPO math | `training/v1/src/ppo.cpp`: `compute_gae` (90–128), `normalize_advantages` (130–142), `masked_categorical` (144–165), `ppo_loss` (167–201), `minibatch_indices` (203–220). | The same `ppo.cpp` functions (`training/dev/v2_live_train.cpp:139-143, 187-188`). |
| Trainer service | `training/v1/src/m08_trainer_main.cpp`: binary frames over stdin/stdout for ACT, UPDATE, EXPORT, checkpoint save/load (5/6) and EXIT. Trainer class in `training/v1/src/multimodal_trainer.cpp`. | `training/dev/v2_live_train.cpp`: tab-separated requests with JSON responses. |
| **Custom kernel** | `training/dev/fused_policy_kernel.cu`, wrapped by `training/dev/fused_policy.cpp`. Its only production call site is `MultiModalPpoTrainer::act` (`multimodal_trainer.cpp:113-121`), and only when built with `-DRL_DEV_FUSED_POLICY=ON`. | Not used. |
| Reset checkpoints | `training/dev/live_checkpoint.cpp` and `scripts/dev/live_checkpoint.py`. | `v2_live_train.cpp:checkpoint/restore` (265–320) and `scripts/dev/checkpoint_v2.py`. |
| Inference export | `save_evaluation_model` (`training/v1/src/evaluation_model.cpp:250-293`); ONNX via `scripts/dev/export_live.py`. | `v2_live_train.cpp:save` (322–349); ONNX via `scripts/dev/export_v2.py`. |
| Evaluation | `scripts/dev/evaluate_live.py` runs complete episodes through `m09_evaluator` on CPU. `scripts/dev/evaluate_registered.py` runs the frozen held-out protocol. Embedded 64-step probes: `run_m08_live_architectures.py:evaluate_architecture` (210–248). | `scripts/dev/infer_v2.py` (neural), `scripts/dev/evaluate_guide_v2.py` (uniform, scripted and repay-first controls), and MCP drivers (`mcp_v2.py`, `shared_v2.py`, `play_mcp_*`). Registered study drivers live in ignored `runs/`. |
| Reporting | `report_learning.py`, `report_credit_experiment.py`, `report_checkpoints.py`, `summarize_evaluation.py`, `compare_replay.py`. | `report_v2_learning.py`, `compare_v2_training.py`, `report_mcp_matches.py`. |
| Build | `training/dev/CMakeLists.txt`, driven by `scripts/dev/local.py build [--fused-policy] [--v2-policy]`. The CUDA architecture comes from the detected GPU (`local.py:107-118`). | Same file with `RL_DEV_V2_POLICY` (CMakeLists 78–113). |

---

## 2. V1 flow: game state to checkpoint and evaluation (kernel marked)

```
OpenTTD worker process (one per episode; 4 in parallel slots, stepped SEQUENTIALLY)
   │  M03 frames. Python checks CRC32C, JSON, canonical form, and validates
   │  32,768 spatial + 256 structured floats per observation.
   ▼
Controller (run_m06_reward_trajectory.py)
   step(): SNAPSHOT (209) + STEP; observe(): OBSERVE (162); mask(): LEGAL_ACTIONS (180)
   = 4 bridge round trips per environment per decision
   ▼
Collector train_architecture (run_m08_live_architectures.py:95-177), per time step:
   1. ACT(sample) for 4 envs ─────────► m08_trainer handle_act (m08_trainer_main.cpp:217-242)
        Python struct.pack of 4×(256+32768) floats      │ decode float-by-float (173-215)
                                                        ▼
                                  MultiModalPpoTrainer::act (multimodal_trainer.cpp:100-135)
                                    structured/spatial/mask .to(device)       (112, 117)
                                    model forward → logits, values            (112)
                                    ┌──────────────────────────────────────────────┐
                                    │ fused_policy() CUDA kernel  [RL_DEV_FUSED]   │ ← CUSTOM KERNEL
                                    │   or masked_categorical() reference          │   (113-121)
                                    └──────────────────────────────────────────────┘
                                    .cpu() logits, values, log-probs          (122-124)
                                    sample_masked_actions on CPU, mt19937_64  (126-130)
   2. env.step(action) for env 0..3, one after another                        (105-114)
   3. ACT(deterministic) on the 4 next observations; only .value is used
      (bootstrap)                                                             (116-121)
   4. Transition(obs, exact mask, action, behavior logp, V(s), reward,
      V(s') if bootstrap, bootstrap flag, continuation flag)                  (138-149)
   5. On termination: close worker, spawn a new OpenTTD process for the next
      episode                                                                 (154-175)
   ▼ after ROLLOUT_LENGTH (32|64) steps × 4 envs
UPDATE frame (includes 32,768 spatial floats per sample) → handle_update (244-315)
   compute_gae [T,E] (283-291) → normalize_advantages (299)
   → MultiModalPpoTrainer::update (137-206): 4 epochs × minibatches of 32,
     reference masked_categorical (never the kernel), clipped loss, grad clip, Adam
   ▼
CheckpointClient.update/save (scripts/dev/live_checkpoint.py:96-138)
   saves only when all 4 envs are at a reset → trainer.pt + checkpoint.json
   ▼ after the last update
EXPORT (m08_trainer_main.cpp:317-339) → models/<sha256 id>/{model.pt, manifest.json}
   ▼
Embedded probes: evaluate_architecture on dev maps 05/06, deterministic,
`--evaluation-steps` (default 64), CUDA trainer (train_live.py:151-155)
   ▼ separately, by the user
evaluate_live.py → m09_evaluator (CPU, reference masked_categorical)
   → full 512-action episodes → run.json → report_learning / report_credit_experiment
```

Key points:

- **The kernel runs only in `act()`**. It is used for both sampled actions (step 1)
  and deterministic bootstrap calls (step 3), but only on a CUDA trainer compiled
  with the option. PPO updates, the CPU evaluator, ONNX deployment and all of V2
  use the reference `masked_categorical`.
- The behavior log-probability stored for PPO therefore comes from the kernel in a
  fused build. The learner's log-probability in `update()` comes from the reference
  implementation. See 02 §2.1 and 05 §5.
- All tensors cross the process boundary as float32 over pipes. Every
  `MultiModalRolloutBatch` tensor lives on the CPU until minibatch time
  (`multimodal_trainer.cpp:150-157`).

## 3. V2 flow

```
LiveV2 game (one process per episode; one environment)
  OBSERVE → TENSORS (writes ~2.97 MB of binary files per frame) → Python hashes them (checked_tensors)
  → optional guide.prepare filters the candidate mask and rewrites the candidate file
  ▼
rl_dev_v2_train ACT <obs_path> <cand_path> <reset>        (v2_live_train.cpp:77-99)
  read files (~2.97 MB), zero hidden on reset, forward (GRU), hierarchical
  masked distribution (v2_live_input.cpp:214-232), CPU sampling; stores the full
  CPU input, including the hidden state, per transition
  ▼
game ACT(candidate) → STEP (128 ticks) → OBSERVE → TENSORS for the bootstrap frame
  ▼
REWARD <r> <bootstrap> <continuation> <next paths>        (101-125)
  bootstrap value from next frame with post-step hidden; hidden not advanced
  ▼ every rollout_length (32|64|128) decisions
UPDATE (127-213): GAE over [T,1]; normalize; behavior-replay audit of every
  8-step sequence (147-165, fails if |Δlogp| > 1e-4); 4 epochs × one 8-step
  sequence per minibatch (170); every transition's input re-uploaded to the
  device each pass (176)
  ▼
CHECKPOINT at resets (265-283) / SAVE inference weights with reload check (322-349)
  ▼
infer_v2.py / evaluate_guide_v2.py / MCP drivers → summaries (service_v2.summarize)
```

## 4. Where configuration lives

| Setting | Location |
| --- | --- |
| PPO defaults (γ .99, λ .95, clip .2, value coefficient .5, entropy .01, lr 3e-4, Adam ε 1e-5, grad-norm .5, minibatch 32, 4 epochs) | `training/v1/include/openttd_rl/training/ppo.h:12-27` |
| V1 live constants (4 envs, rollout 32, minibatch 32, 4 epochs) | `scripts/v1/run_m08_live_architectures.py:27-30`. Rollout is overridden via a context manager at `scripts/dev/train_live.py:50-60`. |
| V1 development CLI (entropy, λ, horizon, reward mode, validation modes, checkpoints) | `scripts/dev/train_live.py:172-203`. Native flags are parsed at `m08_trainer_main.cpp:432-477`. |
| V2 trainer (rollout 32/64/128, λ, sequence 8, epochs 4, minibatch = one sequence) | `training/dev/v2_live_train.cpp:29, 60-75, 366-391`; `scripts/dev/train_v2.py:216-234` |
| Scenario splits | V1: `config/v1/m02-seed-ledger.json` gives training templates 01–04, development 05–06 and final 07–08 (`run_m07_cpu_ppo.py:341-361`). V2: `config/v2/m15-scalable-contract.json` has seed sets for training (16), development (8), generalization (8) and final (16). |
| Reward, observation and action contracts | `config/v1/m04..m06-*.json`, patches under `integration/openttd/patches/15.3` |
| Kernel build | `training/dev/CMakeLists.txt:6, 51-63, 115-121`; `scripts/dev/local.py:103, 112-116, 174-175` |

---

## 5. Unclear or missing connections

1. **Main does not contain the code behind the newest V2 results.** Confirmed by
   static search. `PROGRESS.md` reports V2 training with entropy .001, signed-log
   financial inputs and guide v3 (lines 36–48, 62–75). On main:
   - `v2_live_train.cpp` has no entropy option. Its CLI accepts only `--rollout-length`
     and `--gae-lambda` (366–391).
   - Training input always uses raw finances: `read_live_v2_input(request[1], request[2])`
     at 84 and 112 takes the default `FinancialFeatures::Raw`.
   - `train_v2.py` has no financial-features or entropy argument.
   - `guide_v2.py:8-10` defines only v1 and v2.

   `PROGRESS.md` places this work in isolated worktrees: `v2-entropy-01` (line 284),
   `v2-borrow-guide-01` (72) and `v2-financial-features-01` (899). Line 186 says the
   same about the MCP matched-guide changes ("not integrated in main yet"). Inference
   (`infer_v2.py:138-147`) accepts signed-log models that main cannot train.
2. **Registered study drivers, registrations and advancement code are outside the
   repository.** Examples are `experiment.py`, `finish_analysis.py` and `probe.py`
   under `runs/2026-09-24/...` (PROGRESS.md:201, 326, 375, 539). The V2 "nine
   evaluations per model" matrix and its pass/fail logic cannot be reviewed from the
   checkout.
3. **The collector is changed by monkeypatching frozen modules**, not through
   interfaces:
   - `m08.ROLLOUT_LENGTH` (`train_live.py:55-60`)
   - `bridge.Controller` (`training_environment.py:103-107`)
   - `m07.start_environment` (`live_checkpoint.py:169-184`)
   - `m08.spatial` (`policy_inputs.py:262-272`)
   - `protocol.crc32c` and `_response_is_compact_sorted` (`bridge_validation.py:43-51`)

   Correctness depends on context-manager nesting order and on one run per process
   (`training_environment.py:4-5`).
4. **Embedded probes and full evaluation run on different backends.** Probes use the
   training device, possibly with the kernel (`train_live.py:151-155`). Full
   evaluation uses the CPU LibTorch evaluator (`evaluate_live.py:91,113`). V1 has no
   routine agreement check between the two; V2 offers `infer_v2.py --compare-cpu`.
5. **Run records do not state the kernel build explicitly.** `run.json` stores
   `trainer_sha256` and, when present, `development-build.json`, which contains the
   configure command with `-DRL_DEV_FUSED_POLICY` (`local.py:128-131`,
   `train_live.py:111-113`). There is no first-class field naming the
   inference-distribution backend.
6. **Two V1 trainer services exist.** The M07 structured-only service
   (`trainer_main.cpp`/`service.cpp`/`trainer.cpp`) is the CPU oracle; the
   development route uses M08 (`m08_trainer_main.cpp`). The kernel is linked into
   both libraries but called only from `MultiModalPpoTrainer::act`.
7. **The time-remaining observation assumes 512 actions**
   (`m04 patch:201, 261-264`), while `--episode-horizon 128/256` truncates training
   episodes earlier (`training_environment.py:41-46`). The link between the
   curriculum and the observation is implicit. See 02 §2.4.

## 6. Open questions the repository does not answer

- Which trainer build (fused or reference) produced each model evaluated in
  `PROGRESS.md`? This is recoverable only from the per-run `development-build.json`
  under `~/.local/share/openttd-rl/runs`, which is not in Git.
- How many bytes does a V1 OBSERVE response carry, and how are they split among
  JSON decode, CRC and canonical checks? No evaluation-time breakdown is committed.
- Is OpenTTD's simulation byte-deterministic across process restarts and concurrent
  workers for every map? Byte-identical traces in paired comparisons suggest so
  (`compare_training_backends.py:61-71`), but no dedicated check exists for
  evaluation.
- Is every V2 `terminal` a bankruptcy? `train_v2.py:29` applies the −5
  "bankruptcy" component to any terminal transition.
