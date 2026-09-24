# OpenTTD live PPO continuation handoff

**Ready for continuation.** The 256-step-horizon trial and all nine scheduled
evaluations are complete. The user requested this handoff and explicitly said
**“Pause after this run.”** No next experiment was started. Resume in the new
chat from the completed state below, not the original zero-passenger smoke.

## Continuation update: storage cleanup completed

The new task resumed work, and the owner prioritized lossless cleanup before
learning. All 172,515 selected completed-run logs/tensor files are now verified
gzip archives: 182.11 GiB becomes 32.47 GiB, saving 149.65 GiB. WSL available
space increases 149.01 GiB net. All 527 model/checkpoint/ONNX hashes and 47,763
protected-file records remain unchanged. The latest horizon-256 run, held-out
evidence, qualified worktrees, models and checkpoints remain intact.

Older completed request logs and tensor JSON metadata may now require gzip
reading or exact-path restoration. Main `report_shared_v2.py` accepts `.jsonl.gz`;
archived scripts and worktrees remain unchanged. Use [docs/STORAGE.md](docs/STORAGE.md)
for the retention policy and restore command. Per-file original/archive hashes
and journals live at `$RL_ROOT/maintenance/storage-20260924-01`; the full report
is copied to `runs/2026-09-24/storage-cleanup-01/report.md`. The interrupted
metadata prefix and its continuation are retained explicitly. Nine focused
maintenance tests, 136 portable tests, full shared-report parity, actual restore
checks and the final preservation audit pass. No checkpoints were pruned and no
off-drive moves were made. No new learning experiment started during cleanup;
the missing-depot diagnosis below remains the next step.

## Read first and preserve

Read `AGENTS.md`, `GOAL.md`, `docs/DEVELOPMENT.md`, then this file and
`docs/PROGRESS.md`. The original continuous-goal brief is retained at
`C:\Users\imsa\.codex\attachments\3418631d-8345-4482-b911-b96e970005b1\pasted-text-1.txt`.
It asks for useful real-game learning, reproducible train/resume/export/visible
play, measured CUDA work, live V2 transport, actual MCP opponents, and economic
comparisons, in that order. Continue bounded hypothesis → implementation → real
experiment → evaluation → progress-log iterations. Preserve unsuccessful runs.

- Main checkout: `C:\Users\imsa\Documents\OpenTTD\openttd-cuda-rl`.
- WSL checkout: `/mnt/c/Users/imsa/Documents/OpenTTD/openttd-cuda-rl`, distro
  `Ubuntu-24.04`. Main HEAD: `6a20f1e0fef871a7325811e1eb3d7866df985f91`.
- There is extensive useful dirty/untracked work. **Do not reset, clean, stage
  everything, or replace it with HEAD.** No commits, pushes or publication were
  requested. Frozen release scripts/expected hashes are untouched.
- The parent directory is the user's normal OpenTTD data directory. Preserve
  saves, downloads, AIs and configuration. **Never read or copy `secrets.cfg` or
  `private.cfg`.** Development engines use separate configuration and data paths.
- C++/LibTorch owns PPO. Python orchestrates, analyzes and converts inference
  weights; it must not become a second trainer implementation.
- No subagents were authorized or used. Do not spawn them without authorization.

## Environment and resource limits

In WSL, `RL_ROOT=$HOME/.local/share/openttd-rl`.

| Purpose | Location / version |
| --- | --- |
| Python/Torch | `$RL_ROOT/venv/bin/python`, Torch `2.9.1+cu128` |
| GPU/toolkit | RTX 2070, sm_75; `/usr/local/cuda-12.6` |
| Analysis | `$RL_ROOT/analysis-venv/bin/python` (matplotlib) |
| MCP SDK | `$RL_ROOT/mcp-venv/bin/python` |
| ONNX | Python onnx 1.22.0, onnxruntime 1.28.0 |
| Native ORT | `$RL_ROOT/deps/onnxruntime-linux-x64-1.28.0` |
| Live headless engine | `$RL_ROOT/v2-live-engine/build/openttd` |
| Visible SDL engine | `$RL_ROOT/v2-visible-engine-01/build/openttd` |

At most **two native training/evaluation jobs**, compiler parallelism **two**,
and **one CUDA training job at a time**. A requested CUDA device must fail if
unavailable, never silently fall back to CPU. Use WSL Git in WSL worktrees;
Windows Git cannot resolve their WSL `.git` pointers. Prefer WSL Python for
hashing large files or streaming logs; PowerShell over UNC was slow on these.

## Latest completed run

<!-- CURRENT_RESULT_BEGIN -->
`v2-financial-horizon256-learning-01` **completed; registered advancement FAIL**.
CUDA training: 64 updates / 4,096 decisions, 2,559.68 seconds, finite metrics and
zero behavior-replay error. Both common-prefix checks pass. All nine final
evaluations complete 512 decisions, with zero invalid actions or bankruptcies.

- Sampled service: **6/6**. Means: **1,152.83 passengers / 3,481 operating profit /
  -6,436.50 cash after capital**. These beat the preceding eight-map point means
  but remain below the three stronger learned controls and uniform.
- Development greedy: **0/2** service. Both build roads/stops and repay eight
  installments, then prefer WAIT to a legal depot action. Final WAIT probabilities
  are .84563 and .84613. Map 1630856436 ends at 0 passengers / -1,234 profit /
  -4,016 cash; map 155097162 at 0 / -1,334 / -7,765. Neither buys a bus.
- Training-map greedy 1871197196: **0/1**, ending 0 / -1,184 / -7,225. It builds
  14 roads and two stops, repays eight installments, and never builds a depot.
  The final guide is blocked at construction stage **16 of 17**; the planned depot
  is absent from the bounded native candidate list, leaving **only WAIT**. The
  native-legality versus candidate-priority cause is unresolved. Its WAIT
  probability of 1 is imposed by the mask, unlike the development-map preferences.
- Profit/cash difference versus the eight-map control: +418.17, approximate 95%
  interval [-365.25, 1201.59]; versus uniform: -201.17, [-831.50, 429.16]. These
  three-action-seed intervals are conditional on one model/two maps and include zero.

Final model SHA: `8b3738e9206b6f552431140ce6d68bca5b8c66c8ab08e28abbea7d481fa61dde`.
Final checkpoint: `train/checkpoints/update-000064`, manifest SHA
`6f7910ef5ccc78356fa3166c7caf658a93888cf6c2ac1df6dddb88fcd1af20c3`.
The executor exited successfully; no evaluation remains scheduled. The final
report/JSON, PNG/SVG plot, greedy probabilities and final guide-mask diagnostic
are in `runs/2026-09-24/v2-horizon256-01/completed/`. The plot was visually reviewed.
<!-- CURRENT_RESULT_END -->

The registered change doubles training episode length from 128 to 256 while
holding 4,096 decisions, eight maps, 64-step rollouts, signed-log inputs, guide
v2, gamma .99, lambda .95, four epochs and eight-step recurrent gradients fixed.
Thus each map receives two visits instead of four: longer service exposure and
fewer construction resets cannot be causally separated. No intermediate model
selection or held-out use is allowed. The first 64 native decisions and first
numeric update must equal the previous eight-map trial exactly.

Advancement was registered before results: all nine episodes complete with zero
invalid actions/bankruptcy and sustained service; sampled passenger/profit/cash
means at least all four learned controls; sampled profit/cash strictly above
uniform with the same guide. Keep any failure of these criteria labeled failed.
Paired intervals use three action seeds, averaged across two fixed development
maps. They do **not** estimate training-seed or map-generalization uncertainty.

Key files and execution source:

- Native run: `$RL_ROOT/runs/v2-financial-horizon256-learning-01/`.
- Registration SHA: `fc447691c38a8474f4297d3dd56ffb666bb3383211cd3e77b82fa05fd5cf16ea`.
- Driver: `runs/2026-09-24/v2-horizon256-01/experiment.py`; the run retains its
  exact `orchestrator.py`, source capture, commands, binaries and runtime hashes.
- Execution worktree: `$RL_ROOT/worktrees/v2-guide-blocked-wait-01`.
  **Preserve this qualified worktree.** Main still rejects signed-log weights;
  use this archived source for these experiments and checkpoint continuation.
- Qualified trainer: `$RL_ROOT/build/v2-financial-features-02/rl_dev_v2_train`;
  inference: same directory, `rl_dev_v2_infer`.
- Reports: `runs/2026-09-24/v2-horizon256-01/completed/` (complete and reviewed).
- Checkpoints: native `train/checkpoints/update-NNNNNN`; final model is
  `train/inference-weights.pt`. Recovery is at native resets, not arbitrary
  mid-game state. Exact recovery at the earlier qualified settings is proven;
  do not imply a separate horizon-256 recovery comparison has been executed.

The original command, run **inside that WSL worktree**, is:

```bash
RL_ROOT=$HOME/.local/share/openttd-rl
"$RL_ROOT/venv/bin/python" scripts/dev/train_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --trainer "$RL_ROOT/build/v2-financial-features-02/rl_dev_v2_train" \
  --device cuda:0 --seed 20260923 --updates 64 --rollout-length 64 \
  --episode-horizon 256 --training-map-count 8 \
  --guidance one-bus-public-plan-v2 --financial-features signed-log-v1 \
  --reuse-bootstrap-tensors --checkpoint-interval 8 --output NEW_ABSOLUTE_DIRECTORY
```

Do not rerun this merely to reproduce a report. Inspect the preserved comparison
and model first. Continuing a checkpoint must retain its archived collector,
binary, guide, preprocessing, return settings and seed identities; `--updates`
then means additional updates. Never compare raw optimizer archive bytes across
fresh processes: LibTorch's parameter IDs/order can vary. Compare logical state
and actual resumed behavior, as the existing checks do.

## What the preceding learning work established

All live V2 numbers here are **neural policy plus a public route planner**.
The planner supplies route geometry; the network controls timing and repayments.
Every full evaluation has 512 decisions of 128 simulation ticks. Finance excludes
loan principal from cash results but includes construction and other fees.

| Final model (one training seed) | Sampled passengers | Operating profit | Cash after capital | Sampled sustained |
| --- | ---: | ---: | ---: | ---: |
| Raw, 2,048 decisions | 1,221.00 | 3,807.00 | -6,110.50 | 6/6 |
| Raw, 4,096 decisions | 1,175.83 | 3,573.33 | -6,344.17 | 6/6 |
| Signed-log, four maps, 4,096 | 1,220.00 | 3,803.83 | -6,113.67 | 6/6 |
| Signed-log, eight maps, 4,096 | 1,144.83 | 3,062.83 | -6,854.67 | 6/6 |
| Signed-log, eight maps, horizon 256, 4,096 | 1,152.83 | 3,481.00 | -6,436.50 | 6/6 |
| Uniform under the same guide | 1,193.83 | 3,682.17 | -6,235.33 | 6/6 |

These six-episode means cover two development maps and three action seeds.
Small conditional differences have wide intervals. The raw 4,096 model has
greedy service on both maps, but fails the sampled advancement comparison.
The four-map scaled model has one good greedy map and one underfunded abort.
The eight-map scaled model buys and routes a bus, then greedily chooses WAIT
instead of START on both development maps and the expensive training map.
Neither financial scaling nor greater map coverage is an adopted learning gain.

Important diagnostics already executed (do not repeat blindly):

- **Funding trap:** nine initial repayments can leave too little to buy a bus.
  Qualified guide v2 keeps unavailable service actions as legal WAIT, preserving
  all 512 failure-accounting steps. It supplies no money or automatic borrowing.
  Main supports it; v1 stays available/default and saved runs bind the version.
- **Training reserve probe:** on training map 1871197196, repay-eight-then-service
  overtakes repay-and-WAIT in cumulative gamma-.99 reward only after decision
  149. This motivated the 256-step horizon. Those are fixed-controller realized
  returns, not exact PPO lambda targets or critic estimates.
- **Choice exposure:** prior four/eight-map training has only 1,385/1,590 steps
  with a choice out of 4,096; both contain just 31 START samples. Most normalized
  START advantages are negative. Logged GAE reconstruction matches all 128 native
  explained-variance values within 5e-10. This is descriptive, not causal.
- The completed horizon-256 audit has just **692 choice steps**, **3,404 forced
  WAIT steps**, and **47/64 entire rollouts without a choice**. It has 16 START
  samples, 10 with positive normalized advantage (mean +.5944); depot advantage
  averages -.4350. The changed exposure is evidence, not an isolated causal
  explanation. See `v2-horizon256-01/choice-audit-with-horizon256/`.
- An earlier forced-WAIT-update replay increased depot probability on fixed
  histories; it **did not** show that the final critic-only update destroyed
  a good greedy policy. Do not recycle that rejected explanation as a finding.
- Raw 16-map coverage and 128-step rollout/lambda-1 trials also failed their
  registered advancement criteria. More maps/longer credit is not a proven fix.

Native roots for these are `v2-roll64-sampling-variation-01`,
`v2-financial-features-learning-01`, `v2-financial-eight-maps-learning-01`,
`v2-training-reserve-probe-01`, and `v2-full-return-learning-01`.
Readable reports/plots are under the corresponding `runs/2026-09-24/` folders.

## Newly completed and integrated: live V2 ONNX deployment

Main now contains `export_v2.py`, `v2_export_policy.py`, `v2_onnx_package.py`,
native `v2_export_oracle.cpp`/`v2_onnx_infer.cpp`, focused package tests, and bounded
CMake/`infer_v2.py` additions. Training remains native C++/LibTorch. The export
adapter is inference conversion only, not a Python training implementation.

Qualified raw policy:

- Training: `$RL_ROOT/runs/v2-roll64-budget4096-01/train`.
- Weights SHA: `3338f827674485b072b6544cd97e665feef03b5c16674201ff4bac37b488951a`.
- Package: `$RL_ROOT/runs/v2-live-onnx-package-01`.
- ONNX SHA: `1e85eab9f59dc67d5d2709d0d1b96e50c9ff791009a904b4c92a09a28dc40d35`.
- Runtime: `$RL_ROOT/build/v2-live-export-01/rl_dev_v2_onnx_infer`.

The graph is exported twice with identical bytes. Native/adapter/ONNX recurrent
tests, reset tests and malformed-input/runtime rejections pass. Four full fresh
headless games match 2,048 native decisions exactly; two integrated visible games
match another 1,024 exactly, including masks and economic outcomes. Maximum
probability/value error in those full replays is 2.09e-7/4.77e-6 (limits 1e-5/1e-4).
Both native screenshots were viewed. Greedy map results are 1,451 passengers /
5,092 operating profit / -3,001 cash and 984 / 1,872 / -9,870. All six episodes
sustain service with zero invalid actions or bankruptcy. This is deployment
equivalence, **not** a new learning improvement.

The runtime is **CPU ONNX Runtime 1.28.0**, retaining LibTorch for the native
reader/distribution/sampler. It rejects CUDA ONNX and signed-log weights. The
view-only SDL engine disables game commands from keyboard/mouse; window redraw
preserves native state, simulation ticks and RNG. Closing the viewer aborts.

Main checks: **37 focused tests, 136 portable tests, `git diff --check` passed**.
Integration backups/review: `$RL_ROOT/runs/v2-live-export-integration-01`.
Report/package/screenshots: `runs/2026-09-24/v2-live-export-01/completed/`.
Follow **“Export and watch a live V2 ONNX policy”** in `docs/DEVELOPMENT.md` for
the exact working commands. No new native rebuild of main was claimed; the
integrated native files/core match the qualified isolated build byte for byte.

## Other capabilities retained

- V1 live MLP: three training seeds sustain 18/18 sampled development episodes.
  Its frozen held-out confirmation passed all registered criteria, also 18/18
  sampled service. Greedy is 4/6; the one-bus script is more cash-efficient.
  **The held-out results are closed: never use them for tuning.** Exact reset
  resume, 4,096 native/ONNX replay decisions, and visible play are proven.
- Live V2 bootstrap tensor reuse preserves behavior/checkpoints and reduces
  total wall time by 5.81% over three registered pairs. Optional/default off.
- A V1 CUDA masked-distribution kernel improves its operation 9.62x but only
  1.00470x end to end. It stays optional. WSL Nsight/sanitizer limitations were
  recorded as unsupported, not passes. Do not claim GPU utilization as speedup.
- Native passenger/mail service runs on two maps using the separate mail engine.
  Both cargo services work; cumulative cash still includes unrecovered capital.
  A learned neural mail policy has **not** been implemented.
- Fair two-company shared control and actual MCP SDK integration work. An actual
  local Gemma LLM played a full MCP match, but failed to establish service; the
  weak neural opponent also failed. Do not describe protocol participation as
  competent competition. Inference latency/token usage and simulated time are
  separate. No external model API spend was used in that local match.
- Public-road repair in scripted shared play improved service on both role/map
  pairs affected by the opponent's depot. It was not proof of intentional sabotage.

## Pending work and next decision

<!-- NEXT_STEP_BEGIN -->
The longer horizon is not adopted or advanced to replication. No preprocessing,
optimizer, reward or compression setting in main changed as a result.

Recommended first step in the new chat: inspect the saved training-map case to
locate when the planned depot disappears from the exposed candidates. Distinguish
native legality from bounded-candidate omission before attributing that deadlock
to policy preference or changing the guide. The two development failures are
already a separate neural-choice problem: the depot is legal, but WAIT wins.
Use the retained public snapshots and source first; there is no reason to rerun
4,096 training decisions just to inspect this failure.

A concrete subsequent learning hypothesis is insufficient construction/service
initiation exposure. A bounded test would continue the **eight-map horizon-128**
control from its update-64 checkpoint for another 4,096 decisions (8,192 total),
keeping guide, signed-log inputs, reward, rollout and optimizer fixed. This
increases construction visits instead of adding mostly forced-WAIT steps. That
source/checkpoint is under `v2-financial-eight-maps-learning-01` and the same
qualified `v2-guide-blocked-wait-01` worktree. Register full final-model evaluation
and control comparisons before launch; do not select intermediate checkpoints
or treat this unexecuted suggestion as a proven fix. First resolve whether the
blocked-depot diagnosis requires a different bounded prerequisite.

Keep the qualified raw 4,096-decision ONNX policy as the working visible-play
reference. Any later learning improvement still needs training-seed replication
and compatible deployment qualification before replacing it.
<!-- NEXT_STEP_END -->

One independent performance lead is ready for a later bounded experiment:
`$RL_ROOT/runs/v2-tensor-compression-profile-01` measures gzip level 1 versus 9
on 36 retained real tensor files, in three counterbalanced pairs. Median
compression CPU ratio is 17.63x; size grows 1.553x; decompressed bytes are exact.
This is an **in-memory microbenchmark under background load**, not an end-to-end
training speedup. No runtime setting changed. A whole-run matched comparison
is required before adoption; the user handoff request stopped further work here.

When resuming, inspect the completed run and source first, then choose one bounded
next hypothesis. Keep learning and development/held-out claims separate. Update
`docs/PROGRESS.md` with actual outputs and material limitations. Read
`docs/PROGRESS_HISTORY_2026-09-23.md` only for a specific older result; it is long.

## Handoff verification

<!-- FINAL_CHECKS_BEGIN -->
- Training and all nine scheduled evaluations: complete; advancement failed.
- Final economic report, comparison plot and greedy/choice diagnostics: complete;
  plot visually reviewed. No partial episode was used as a full-horizon metric.
- Live V2 ONNX export, four headless replays and both visible replays: passed;
  main checks passed 37 focused tests, 136 portable tests and whitespace checking.
- Both native ONNX screenshots: visually reviewed; finance agrees with logs.
- Historical progress bytes match both the trial's pre-run source archive and
  the pre-integration source capture. An initial check against a different hash
  carried in compacted context failed; it is preserved as
  `v2-horizon256-01/handoff-reference-check-failure.json`. The source archives,
  rather than that contextual hash, establish preservation for this handoff.
- New runtime compression experiment: not started; only the retained offline
  profile exists. No runtime compression setting changed.
- Files: this `handoff.md` and `continuation-prompt.md` in the project root.
- The user explicitly authorized goal pausing at this boundary. No further
  experiment is authorized in the old chat before the requested pause.
<!-- FINAL_CHECKS_END -->
