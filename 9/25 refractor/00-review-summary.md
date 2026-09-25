# 00 — Review summary

**Scope.** Static technical review of `goldbar123467/openttd-cuda-rl` at commit
`0595a72` (branch `claude/funny-einstein-q6g19d`), covering:

- the C++/LibTorch PPO core (`training/v1`);
- the V2 live recurrent trainer (`training/dev/v2_live_train.cpp`);
- the Python collectors and evaluators (`scripts/v1`, `scripts/dev`);
- the custom CUDA kernel (`training/dev/fused_policy_kernel.cu`).

**Method.** Files were read and searched only. **Nothing was built, run, trained,
evaluated, benchmarked, profiled or tested.** Performance numbers quoted are the
repository's own recorded measurements, with citations. Byte counts are arithmetic
on code constants.

Two versions of the brief were supplied. This set follows the second, which adds the
custom-kernel review. The reports are 00–07 in this folder. Later additions:

- **08** gives specific PPO advice to get V2 training back on track;
- **09** records coverage limits, ten additional findings and a findings register
  with IDs;
- **README.md** gives the reading order, label definitions and a PPO/CUDA glossary.

## Overall assessment

The PPO implementation is careful and, as far as static reading can establish,
**mathematically correct**:

- GAE separates terminal from time-limit truncation;
- behavior log-probabilities and exact sampling masks are stored and reused;
- masked entropy and the clipped surrogate are standard and unit-tested;
- reset-boundary checkpoints capture model, Adam, all RNG streams and counters, and
  are verified on resume.

The CUDA kernel is also correct, well-validated numerically, and honestly measured.

The project's weaknesses are elsewhere:

1. **Reproducibility.** The newest V2 results come from code that is not on main,
   and the advancement logic lives outside Git.
2. **Evaluation strength.** Two maps, one training seed for most V2 studies, and
   repeated reuse of the same development maps.
3. **Throughput is bounded by the pipeline, not GPU math.** Python bridge validation
   and serialization, a duplicate inference call per step, unused spatial data for
   the MLP, many blocking host–device syncs, and per-decision multi-megabyte frame
   I/O in V2. This is why the kernel's 9.62× operation speedup became 1.0047× end
   to end.

## What appears sound

| Area | Evidence |
| --- | --- |
| GAE and truncation | `ppo.cpp:90-128`; contract flags `m06-reward-trajectory-contract.json:339-351`; collector `run_m08_live_architectures.py:146-148`; test `native_tests.cpp:38-51` |
| Behavior log-prob and mask reuse | `multimodal_trainer.cpp:126-131`; `run_m08_live_architectures.py:98,141-143`; `ppo.cpp:84-87`; V2 replay audit `v2_live_train.cpp:147-165` |
| Loss, entropy, normalization | `ppo.cpp:130-201`; tests `native_tests.cpp:53-106` |
| Checkpoint and resume | `live_checkpoint.cpp:76-170`; `live_checkpoint.py:48-60, 102-166`; V2 `v2_live_train.cpp:265-320` with deterministic algorithms |
| Recurrent handling (V2) | Stored hidden state, reset masking (`scalable_policy.cpp:286`), bootstrap without advancing state (`v2_live_train.cpp:110-115`) |
| Evaluation hygiene | Final split refused outside the registered route (`evaluate_live.py:77-85`); exact matrix and engine checks in the report tools; t-intervals over training seeds; a preregistered V1 held-out run (`evaluate_registered.py`) |
| Kernel | Barrier-uniform, race-free, max-subtracted, fail-closed, stream-correct; 6,984-row oracle test (05 §5) |
| Experiment records | Source archives, hashes, failed runs preserved, claims scoped conservatively in `docs/PROGRESS.md` |

## Highest-priority concerns

Ranked. Labels are Confirmed (in code), Risk (plausible) or Recorded (from the
repository's measurements).

0. **Why V2 training stalls (see 08). Confirmed mechanism plus recorded evidence.**
   - `ppo_loss` averages the policy, entropy and KL terms over **every** step
     (`ppo.cpp:191-196`), but 61–83% of recorded V2 training decisions are forced
     single-action WAITs that carry no policy gradient (`PROGRESS.md:558-560, 743-745`).
     That cuts the effective entropy coefficient to about .002 at a nominal .01, and
     makes value regression dominate the shared network.
   - Construction is charged its capital cost immediately, while payoff arrives about
     59 decisions later. Recorded construction advantages are negative.
   - On main, the policy cannot see cash (divided by 1e9), and the guide allows a
     repayment trap.

   Together these explain the recorded collapse toward WAIT. 08 gives the fix order:
   instrument; choice-only loss averaging; capital-amortizing potential shaping;
   signed-log inputs and no pre-service repayment; then optimizer granularity.
   Each step comes with code sketches, settings and a 3-seed protocol.
1. **Main cannot reproduce the current V2 recipe. Confirmed.** Entropy .001,
   signed-log *training* inputs and guide v3 exist only in worktrees:
   - `v2_live_train.cpp` has no entropy option and reads raw finances (84, 112);
   - `guide_v2.py:8-10` has only v1 and v2.

   The registered study drivers are in ignored `runs/`. See 01 §5.1–5.2 and 02 §2.14.
2. **Evaluation evidence is thin where it matters. Confirmed design limits.**
   - Two evaluation maps, with greedy runs being one deterministic episode per map.
   - Most V2 studies use one training seed, with intervals over action seeds (df = 2).
   - The same development maps have been reused across dozens of studies.
   - V2 has **8** development map seeds available but uses 2, and has no held-out run.

   See 03 §6 N1–N5.
3. **The custom kernel cannot move end-to-end time where it sits. Recorded plus
   code-established.**
   - It runs only in V1 CUDA `act()` (`multimodal_trainer.cpp:113-121`), never in
     updates, evaluation, ONNX or V2.
   - Its recorded operation speedup (763.70 → 79.39 µs) gave 1.0047× end to end.
   - At the collector's batch of 4, the recorded **CPU** distribution (53.91 µs) was
     faster than the fused GPU path.
   - The surrounding code dominates: a duplicate bootstrap ACT per step, the unused
     spatial tensor for the MLP (99% of UPDATE bytes), and 4 blocking D2H copies.

   See 05 §7–8.
4. **V2 optimization granularity and forced decisions. Risk, with strong evidence
   of waste.**
   - Each Adam step sees one 8-decision sequence (`v2_live_train.cpp:68,170`).
   - A recorded audit found 3,404 of 4,096 training steps forced (single legal row).
     They add nothing to the policy gradient but dilute minibatch means and
     normalization.

   See 02 §2.8 and 06 P1–P2.
5. **V2 action representation aliasing. Recorded in `PROGRESS.md:160-175`.**
   Borrow and repay, and most road/stop/depot candidates, have identical features,
   so the policy depends on the planner guide to distinguish them. See 06 O1.
6. **The horizon curriculum trains outside the evaluation's time-feature range.
   Risk.** Time features are hard-coded to 512 actions (`m04` patch 201–202,
   261–264). Horizon-128 training never sees the late-episode feature range that the
   scored final windows use. See 02 §2.4.
7. **Smaller confirmed issues.**
   - Embedded probes store *quarter* income as `"income"`
     (`run_m08_live_architectures.py:239`; `DEVELOPMENT.md:353-354`).
   - The V2 capital clip (4,096) binds on a recorded 4,921 bus purchase
     (`train_v2.py:28`; `PROGRESS.md:366`).
   - V1 lacks V2's behavior-replay audit.
   - Kernel test gaps (mixed bad rows, boundary sizes) and no sanitizer evidence.

## Ranked next actions

Full detail in 07.

1. **S1-1:** port the worktree V2 features into main behind default-off flags, with
   default-equivalence proofs.
2. **08 Steps 0–2:** V2 choice-step instrumentation, choice-only loss averaging and
   the asset-potential reward. Run the 08 §3 study (arms A0–A2, 3 seeds each,
   8,192 decisions) before any other V2 learning experiment.
3. **S1-2:** add a V1 behavior-replay audit (read-only; the frozen wire format stays
   unchanged).
4. **S1-6:** offline audits of existing runs (V2 reward clips and terminal reasons,
   V1 time-feature ranges, V2 advantage and KL statistics).
5. **S2-1 / S2-2:** commit study drivers; add per-map and hierarchical uncertainty
   to the report tools.
6. **S2-3 / S2-4:** V2 evaluation on all 8 development maps; register a V2 held-out
   protocol before more tuning.
7. **S3-0:** stage timers written to separate files, so traces stay byte-identical.
8. **S3-1:** evaluation quick wins (vectorized spatial validation and the fast
   bridge mode already exist but are not defaults in `evaluate_live.py`).
9. **S3-4 / S3-5:** a development collector (deferred bootstrap, structured-only MLP
   protocol, concurrent stepping); V2 UPDATE with device-resident inputs and
   sync-free checks.
10. **S3-2 / S3-3 / S3-8:** C++ ACT transfer fixes; kernel internals as a learning
    exercise only.
11. **Stage 4:** registered 3-seed studies, starting with forced-step masking and
    candidate parameter features.

## The three findings to read first

Updated after the follow-up request.

1. **08 §1 (M1–M4): why V2 training collapses toward WAIT.**
   - Forced-step dilution of the entropy and policy terms, about 3–6×.
   - An immediate capital charge against a 59-decision payoff.
   - Cash blindness and the repayment trap.

   §2 gives the ordered fixes.
2. **05 §7.2–§8: the kernel's context.** The kernel is correct, but the pipeline
   around it erases its gain. The changes that could matter are at the call site
   and in the collector, not inside the kernel.
3. **01 §5.1, 02 §2.14 and 03 §6 N1–N4: reproducibility and evaluation
   reliability.**
   - Main cannot retrain the current V2 recipe, and the study logic is outside the
     repository.
   - Comparisons rest on two maps and single training seeds, although V2 has 8
     development seeds and an unused held-out split.

## Open questions

These are collected from the individual reports; the repository does not answer
them.

- Which evaluated models, if any, were trained with the fused-kernel build?
- How large is a V1 OBSERVE response, and how is per-decision time split among
  simulation, bridge validation, JSON and inference? There is no committed
  evaluation profile.
- Is the engine byte-deterministic under concurrent workers? The design assumes it.
- Does any V2 terminal occur other than bankruptcy?
- Why were these 2 of the 8 V2 development seeds chosen?
