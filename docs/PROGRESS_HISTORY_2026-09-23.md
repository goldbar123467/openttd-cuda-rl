# Live OpenTTD learning progress

This log records development experiments. Historical release evidence and final
evaluation scenarios remain untouched. Artifacts below are relative to
`~/.local/share/openttd-rl/runs/` in Ubuntu-24.04 unless stated otherwise.

## 2026-09-23: complete-episode diagnosis (in progress)

- Starting evidence: `live-cuda-02` completed eight C++/LibTorch CUDA updates
  (1,024 transitions). Its two greedy 64-action development probes delivered no
  passengers. Each training worker saw the initial construction state only once;
  no training episode reached the ordinary 512-action/65,536-tick horizon.
- Hypothesis: full episodes and sampled evaluation distinguish delayed service
  from a policy that stalls under greedy action selection. Before inspecting
  complete results, criteria are deliveries, lifetime operating profit, capital
  spend, balance change, invalid actions, bankruptcy, and delivery plus positive
  profit in each of the last three 128-action windows.
- Added `scripts/dev/evaluate_live.py`, using the existing engine controller,
  reward oracle, ordinary reset, scripted baseline and optimizer-free C++ model
  evaluator. Runs save source/binary/model identities, scenario seeds, complete
  action/probability/outcome traces, and failure records. Only training or
  development templates can be selected.
- `baselines-full-01` compares wait, the existing M09 script, seeded-random,
  greedy and sampled inference of the saved model on both development maps.
  Random and sampled policies each use seeds 20260923, 20260924, 20260925;
  deterministic policies run once per map. CPU model evaluation is explicit;
  the model was trained on CUDA. No new training claim is made by this replay.
- Early diagnostic: the existing M09 script buys eight buses but assigns and
  starts only bus 0. It nevertheless delivered 292/304 passengers by action 128
  with operating profits 568/765 on the two maps. These are partial episodes.
- Accounting correction in the new diagnostic: current-quarter snapshot income
  and expenses are not episode totals. Sum unclipped native lifetime reward
  deltas and retain capital spend separately. The historical evaluator is intact.
- Focused verification: 11 development unit tests passed, including quarter
  rollover, raw-versus-clipped economics and incomplete-episode rejection.
- Next: finish the registered baseline matrix, inspect the greedy stall trace,
  add a one-bus scripted comparison, then test repeated full-episode PPO training
  before changing reward or action semantics.
- Follow-up registered before results: `live-cuda-32u-01` uses the same seed,
  architecture, CUDA device, masks, rewards and PPO settings for 32 updates
  (4,096 transitions, two complete episodes per worker), then 512-action greedy
  probes. This tests revisiting construction states before altering semantics.
  Its legacy probe metrics are supplemented by the lifetime-counter evaluator.
- `one-bus-full-01` tests a mask/observation-only script which buys, routes and
  starts exactly one bus, then waits. Two complete development episodes use
  process workers and cProfile instrumentation to locate collection overhead.
  Profiling changes timing; do not treat this as an uninstrumented benchmark.
- Repository verification: `bash scripts/v2/verify.sh --tier fast` passed all
  136 tests; `git diff --check` passed.

### Completed baseline and throughput evidence

| Policy | Dev map | Passengers | Operating profit | Profit less capital | Rejections | Bankrupt |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Wait | 05 / 06 | 0 / 0 | -4,834 / -4,834 | -4,834 / -4,834 | 0 / 0 | no / no |
| Existing M09 script | 05 / 06 | 1,507 / 1,457 | 4,859 / 4,504 | -35,947 / -36,231 | 0 / 0 | no / no |
| One bus | 05 / 06 | 1,523 / 1,469 | 4,960 / 4,577 | -1,399 / -1,711 | 0 / 0 | no / no |

All rows reached 512 actions. Both scripts delivered with positive operating
profit in each of the four windows, but neither recovered capital within this
horizon. One-bus first deliveries were at actions 32/31, versus 39/39 for the
existing script. These hand-written baselines are not learned policies.

The greedy 8-update model's trace on map 05 starts with town selection then
repeated WAIT. At action 2, WAIT probability was 0.21542, stop-building 0.20751,
road-building 0.20331. Greedy replay magnifies a slight preference in an almost
uniform early-state policy. Full greedy and sampled results are still pending.

The one-bus cProfile run on map 05 measured 203.9 seconds: 126.2 seconds in
compact/sorted-response checking and 70.7 seconds in CRC32C; `observe` accumulated
194.9 seconds. This is a Python validation bottleneck, not CUDA computation.
`bridge_validation.py` offers an explicit `fast` development option using a
256-entry CRC table and a string-preserving regex numeric tokenizer. The frozen
bitwise/scanner implementations remain unchanged as the reference. All frame,
canonical-structure, boundary, and reward checks still execute.

`one-bus-fast-01` reproduced **byte-identical complete action traces** on both
maps (including masks, source counters, command outcomes, snapshots and rewards):

- 05 SHA-256: `b9c1c5f232543ad03cfbb142bc4cfcc63e947e47d988d273d02594aef5ee1227`
- 06 SHA-256: `9786522225558c65d7fb1f1b0ff66d4aacfa62c6585bf55edd115adafaf42469`

Fast uninstrumented episodes took 26.0/25.8 seconds. Do not divide profiled
reference time by unprofiled fast time to claim a speedup; `one-bus-reference-01`
is collecting matching uninstrumented reference timings. Sixteen development
tests passed, including differential checksum vectors, string escapes, spatial
payload sizes, number spellings, whitespace/key rejection, and reference restore.

The next matched 32-update training seeds are 20260924 and 20260925, with the
same C++ CUDA trainer and the verified fast bridge option. A shell-loop launch
failed argument parsing before training (`live-cuda-32u-s.log`, retained);
explicit per-seed invocations avoid that quoting issue.

Uninstrumented reference repeats completed in 96.4/96.0 seconds, versus
26.0/25.8 seconds with fast validation (3.70/3.72 times faster locally), again
with byte-identical full traces. Both used two process workers. Other independent
experiments were running, so these are indicative local end-to-end timings,
not an isolated benchmark or a CUDA speedup. The machine-readable comparison is
`one-bus-fast-01/reference-comparison.json`.

### First learning comparison and next hypothesis

- All six full random episodes finished: mean 1,129.5 passengers, operating
  profit -2,075.3; only 1/6 sustained service in all final windows.
- The 8-update model's complete greedy episodes both delivered zero. Each built
  the infrastructure eventually but never purchased a bus. Sampled evaluation
  (`policy-eight-fast-01`) instead averaged 1,687.8 passengers and +1,125.3
  operating profit; all six episodes had positive total profit, but only 3/6
  had sustained final-window service. This is a useful contrast with random,
  not yet reliable competence or superiority to the one-bus script.
- `live-cuda-32u-01` completed 4,096 transitions and eight full training episodes.
  Its two full greedy probes again delivered zero. On full sampled evaluation
  (`policy-32u-s20260923`), mean deliveries rose to 1,946.7 and operating profit
  to +1,557.8; sustained service improved to 5/6 episodes. These compare the same
  training seed and sampling/scenario matrix; other training seeds are pending.
- All three 32-update training seeds finished. Seed 20260924 establishes service
  under greedy replay; 20260923 and 20260925 do not. Use the new lifetime-counter
  evaluations for economic conclusions, not their legacy current-quarter probes.
- Next hypothesis, registered before results: `live-cuda-curr128-s20260923`
  keeps 32 updates/4,096 transitions and identical PPO/reward/action settings,
  but trains with a native 128-action time limit. Each worker sees construction
  eight times instead of twice. Evaluate at the ordinary 512-action limit.
  Native reset variations supply actual termination/bootstrap flags; the
  development adapter never invents a terminal event. New runs also record
  per-episode native rewards, raw economic counters, masks and action outcomes.
- Nineteen development checks passed, including adapter restoration on failure,
  training-only scenario access, and native horizon configuration. No C++ PPO
  math, historical release script, expected hash, or held-out manifest changed.

### Matched three-seed results and controlled follow-ups

`comparison-32u-01/comparison.{json,md}` combines the completed baseline matrix
and all three 32-update models. A Windows-accessible copy is in ignored
`runs/2026-09-23/learning-full-episodes/`.

| Policy | Episodes | Mean passengers | Mean operating profit | Sustained service |
| --- | ---: | ---: | ---: | ---: |
| Random | 6 | 1,129.5 | -2,075.3 | 1/6 |
| One-bus script | 2 | 1,496.0 | 4,768.5 | 2/2 |
| 8-update sampled, one training seed | 6 | 1,687.8 | 1,125.3 | 3/6 |
| 32-update sampled, three training seeds | 18 | 1,939.2 | 1,677.3 | 16/18 |
| 32-update greedy, three training seeds | 6 | 641.5 | -1,618.0 | 2/6 |

The sampled 32-update training-seed mean profit ranges from 1,557.8 to 1,840.8;
its conditional 95% t interval is [1,313.2, 2,041.4]. This describes only three
training seeds on the two fixed development maps and fixed sampling seeds, not
map generalization or held-out strength. Zero native rejections/bankruptcies
were observed. Greedy performance is unstable across training seeds. Native and
fast validation also produced byte-identical complete traces for all eight
old-model greedy/sampled episodes (4,096 transitions); see
`policy-eight-fast-01/reference-comparison.json`.

The successful greedy seed 20260924 selects alternating towns 492 times after
setting up four running buses; it purchases eight. Its native reward avoids
WAIT's 1/64 penalty by issuing free selection toggles. This is a reward loophole,
not evidence of useful ongoing economic decisions.

The 128-action curriculum completed 32 native truncated training episodes.
At full 512-action evaluation it still delivered zero greedily. Sampled means
were 1,907 passengers and 1,692.7 profit, with 5/6 sustained service. It did not
resolve the intended construction failure and is not the default.

`fleet-sweep-01` supplies stable, mask/observation-only fleet controls:

| Running buses | Mean passengers | Mean operating profit | Mean profit less capital |
| --- | ---: | ---: | ---: |
| 1 (earlier control) | 1,496.0 | 4,768.5 | -1,555.0 |
| 2 | 1,600.5 | 4,514.5 | -6,730.0 |
| 4 | 1,887.5 | 4,520.0 | -16,566.5 |
| 8 | 1,951.0 | 1,153.0 | -39,617.5 |

Every fleet control sustained positive final-window profit on both maps. More
buses increase deliveries modestly but reduce economic efficiency. Learned
policies still overpurchase and do not outperform the one-bus economic control.

Two isolated follow-ups are registered before results:

- `live-cuda-cost-s20260924`: 32 updates/4,096 transitions, ordinary 512-action
  episodes, seed 20260924. Extend the existing WAIT decision cost to every
  action by subtracting 1/64 from non-WAIT rewards entering PPO. Native economic
  rewards/traces are retained, and transformed rewards are separately logged.
  Test whether free selection cycling disappears without losing service.
- `live-cuda-roll64-s20260923`: native reward, ordinary 512-action episodes,
  seed 20260923, **64-action rollouts and 16 updates**, still 4,096 transitions.
  Every random baseline first delivered at actions 33-49, beyond the original
  32-action rollout. This tests putting construction and first delivery in one
  update rather than initially relying entirely on an untrained bootstrap value.

Twenty-one development tests passed, including preservation of behavior log
probabilities, exact masks and bootstrap flags through reward transformation,
and restoration of the collector's rollout length after exceptions.

### Follow-up outcomes and progress-potential trial

The uniform decision-cost trial completed but greedy replay chose WAIT for all
512 actions on both maps. Sampled means were 1,942 passengers and 1,692.2 profit,
with 4/6 sustained service, versus 6/6 for its matched native-reward seed. It is
not adopted as a successful policy improvement; it removes the reward advantage
of free toggling but does not solve construction learning.

The 64-action rollout trial also completed without greedy deliveries. Sampled
means were 1,938 passengers and 1,824.8 profit, with 5/6 sustained service. This
does not establish a robust improvement from one training seed, and the default
remains 32. Both trials retain all native outcomes and separate transformed
reward metrics where applicable.

Next hypothesis, registered before outcomes: `live-cuda-potential-s20260924`
adds a bounded service-progress potential to the uniform decision-cost reward,
at the same 32 updates/4,096 transitions, seed and ordinary 512-action horizon.
Phi is the sum of up to two existing stations, one depot, one primary bus, and
the presence of any running bus; it never grows for purchasing surplus buses.
The addition is `0.99 * Phi(next) - Phi(current)`, matching native PPO gamma.
True terminal states have Phi zero; time-limit truncations retain the potential
of the bootstrap state. Native rewards remain unchanged in the bridge and logs.
Only public/own-company counts enter the potential; multiple-company use fails
explicitly. The discounted shaping sum telescopes, preventing a repeatable
stop/start bonus. This follows [Ng, Harada and Russell's potential shaping](https://people.eecs.berkeley.edu/~russell/papers/icml99-shaping.pdf);
finite PPO performance is still determined by ordinary delivery/profit tests.

Twenty-four development tests passed, including discounted telescoping,
terminal versus truncation treatment, no reward for surplus buses, and
rejection of a misaligned reward stream before PPO. No held-out scenarios have
been accessed. An earlier, more detailed progress-log snapshot is preserved at
`runs/2026-09-23/learning-full-episodes/progress-initial-iterations.md`.

### Longer experience budget and reset-boundary recovery

The potential trial completed: greedy waited for all 512 actions on both maps;
sampled replay sustained service in 6/6 episodes, with mean 1,943.3 passengers
and 2,042.5 operating profit. All sampled episodes still purchased eight buses.
This does not solve the greedy construction or capital-efficiency problems.

`live-cuda-128u-s20260923` now tests a larger **16,384-transition** budget (128
updates, 32 complete training episodes), retaining the original native reward,
32-action rollout, and 512-action horizon. Hypothesis: the earlier eight training
episodes were insufficient for reliable greedy construction. Evaluate the saved
policy on the same complete development matrix; do not select held-out scenarios.

Alongside that run, add a development-only native checkpoint path as a prerequisite
for longer experiments. It saves model, Adam, counters, native RNG streams and
Torch CPU/CUDA RNG state. Environment recovery is restricted to synchronized
native resets, with saved episode indices and matching reset observation/mask
hashes. Configuration, executables, collection code and training templates must
match; no arbitrary mid-game or cross-device exact-recovery claim is intended.

The first native checkpoint test passed CPU but failed bitwise CUDA continuation
in the spatial CNN (value loss differed by roughly 6e-8); MLP continuation passed.
Deterministic cuDNN convolution selection eliminated the discrepancy across all
three architectures. This selection is explicit in checkpoint-enabled launches
and recorded/checked on restore; the failing evidence remains in
`checkpoint-native-tests-01.log`. The subsequent native suite passed **9/9**,
including CPU reference differential, CPU/CUDA checkpoint continuation, and
CPU/CUDA export preserving the live trainer. Twenty-eight Python tests passed.

`live-resume-cpu-01` executed an uninterrupted eight-update real-game run and a
four-update prefix followed by four resumed updates. All continuation PPO metrics
matched exactly, all four 128-transition episode traces were byte-identical, and
the final exported model ID matched. This is recovery evidence, not gameplay
strength. Its original trainer executable is retained alongside the result.
`live-resume-cuda-01` applies the same real-game comparison to the integrated CUDA
workflow. Source patches/new development files are now retained with new runs and
builds so dirty working-tree hashes are backed by reconstructable source.

`live-resume-cuda-01` passed the real-game differential: exact continuation
metrics, 512 byte-identical transitions across four completed training episodes,
and identical exported model ID. The three native architectures also passed
same-device CPU/CUDA checkpoint tests; real-game continuation was tested with the
structured MLP. The larger-budget study now continues with seed 20260924 using
128 updates and checkpoints every 16, retaining the native reward and ordinary
512-action horizon. Checkpointing selects deterministic cuDNN; the MLP has no
convolution layers. No held-out scenarios are involved.

### Native budget outcome and economic objective audit

The first 128-update seed completed 16,384 transitions. Its greedy model built a
road/depot then waited, delivering zero on both development maps. Sampled means
were 1,909.2 passengers and 2,001.8 operating profit, with 5/6 sustained service;
all six still bought eight buses. Four times the experience did not solve this
seed's construction reliability or capital-efficiency problem. The second seed
is still running; do not infer an across-seed conclusion yet.

`reward-audit-01` recomputed every native reward from the frozen CPU reference
across eight full fleet-control traces before rescoring them. Native mean returns
favor eight buses (111.93) over one (86.40), despite operating profit falling from
4,768.5 to 1,153 and much higher capital spending. Passenger reward dominates the
present objective. This is a measured incentive conflict, not simply failed PPO.

Next registered trial: `live-cuda-economic-s20260924`, 32 updates/4,096 transitions,
ordinary 512-action episodes, structured MLP, seed 20260924. Rescale the existing
bounded native terms to passenger delivery /128, operating profit /256, and
capital spend -/1024, with a uniform 1/64 decision cost. Preserve the existing
rejection, idle, vehicle-loss and bankruptcy terms; add no progress potential.
Raw rewards and game ledgers remain unchanged. On the already-executed fleet
traces, the proposed return ranks one/two/four/eight buses as 16.14/11.14/3.75/-28.32.
Those are offline objective checks, not learned outcomes. Evaluate capital per
delivered passenger, operating profit, fleet size and sustained service alongside
greedy construction and native reward. Thirty-one development tests pass,
including uniform decision cost and preservation of on-policy rollout fields.

The second native 128-update seed also lost greedy construction, delivering zero
on both maps. Sampled means were 1,822.8 passengers and 3,094.8 operating profit,
with 6/6 sustained service and 7.83 buses. Longer training is not a reliable greedy
fix across these two seeds. The economic 32-update trial averaged 1,342.2 passengers,
2,170.5 operating profit, 6.5 buses, and 5/6 sustained service. Capital per delivered
passenger worsened to 24.88 from the matched native policy's 20.98 because service
started later. Retain the failed/tradeoff results; neither change becomes default.

### Native ONNX export and visible playback

Use the earlier seed-20260924 32-update native policy as the development playback
example; it built service on both development maps and had 6/6 sustained sampled
evaluations. This is explicit development selection, not an independent held-out
strength claim. ONNX Runtime 1.28.0's official CPU archive matched the historical
SHA-256, so deployment runtime checks remain unchanged. Local conversion uses
Torch 2.9.1+cu128, ONNX 1.22.0 and ONNXScript 0.7.2 through a labeled development
exporter; historical exporter/runtime gates and selected-package hashes are intact.

`export-32u-s20260924-01` passed: two byte-identical exports, exact source weights,
opset/signature validation, and comparison against native standalone/in-game ONNX
adapters on 128 recorded development states. Maximum absolute differences were
1.43e-6 logits, 1.08e-7 probabilities and 9.54e-6 values; all greedy actions matched.
`policy-onnx-32u-s20260924` then replayed all eight complete episodes.
`onnx-full-replay-comparison-01` confirmed **4,096 identical actions, masks, native
states, rewards and economic outcomes**, with prediction errors within existing
M10 tolerances (largest value difference 1.53e-5).

The isolated GUI build reuses the M11 C++ controller with a development-only
compile option, separate configuration/report schemas, dynamic model labels and
training/development scenario guards. Frozen package/final-map acceptance checks
remain in the non-development branch. The SDL2 dependency was installed after the
initial configure failure; 98 native engine tests passed on the resulting build.
`-X`, explicit per-run configuration and a separate working directory isolate
playback from normal OpenTTD data. No private/secrets configuration was read or copied.

`visible-policy-32u-01` executed 512 decisions in an actual SDL window and delivered
1,840 passengers. Its launcher was marked failed because it expected PNG, while
the build legitimately wrote BMP without optional libpng. Preserve that failure.
The native bitmap was inspected and the subsequent `comparison.json` passed for
all actions/masks and delivery/income/expense counters at matching decision
boundaries. M11 records after the command but before its following 128 ticks;
do not compare those counters to the headless post-advance state. The launcher
now accepts verified 1280x800 PNG or BMP output. A second-map visible replay is
checking the corrected workflow.

`visible-policy-32u-02` completed successfully on map 06: 512 decisions and 2,009
passengers. Its comparison passed with zero prediction error and exact actions,
masks and matching-boundary lifetime counters. The BMP was visually inspected.
All 34 development Python tests passed. `ldd` confirms the standalone ONNX
evaluator and GUI engine link ONNX Runtime without LibTorch/CUDA dependencies.
The development guide now gives export, full replay and native-window commands.

Next bounded learning experiment: resume the economic seed-20260924 policy at
update 32 for 96 further updates (`live-cuda-economic-128u-s20260924`). Hypothesis:
additional on-policy experience may reduce excess purchases without delaying
service. Keep architecture, reward, horizon, seed and optimizer state fixed.
Compare its full development traces with both its 32-update prefix and the
native-reward 128-update seed, judging passenger delivery, sustained operating
profit and capital per passenger. No extra seeds or adoption before this check.

### Measured CUDA inference experiment

The native 128-update run spent 1,216.8 seconds in collection/optimization,
including 137.4 seconds in inference calls and 67.8 seconds in update calls.
The remainder is chiefly game collection/validation, so GPU-only improvements
have a limited end-to-end ceiling. `profile-live-cuda-01` captures two real
updates with cProfile and Nsight Systems. The profiled collection took 34.8
seconds; cProfile attributes 14.9 seconds to repeated spatial validation and
16.0 seconds to bridge decoding (instrumented, overlapping call totals).
CUDA API tracing recorded 16,825 launches, 3,052 stream synchronizations and
3,573 asynchronous copies. The installed Nsight 2024.5 warns that driver 13.3 is
unsupported; device kernel/copy timing tables are absent. Do not treat these
API times as GPU execution times. Another learning run was active, so this is
bottleneck discovery, not an isolated throughput benchmark.

The standalone trusted masked-distribution benchmark passed CPU/CUDA numerical
checks. Initial CUDA wall cost at batch four was 793.9 microseconds/call versus
53.9 microseconds on CPU, including validation. This motivates a bounded
inference-only fused CUDA experiment: one 64-thread block per 41-action row,
shared reductions, float32 contiguous inputs, explicit invalid-mask/nonfinite
errors, and one status synchronization. No autograd replacement or changed PPO
loss is proposed. The optional build is separate; validate numerical behavior
and then measure complete live collection before considering adoption.

The economic continuation completed 16,384 total transitions and failed all eight
full development evaluations: zero passengers, -4,834 operating profit, no invalid
actions or bankruptcy. Its sampled service regressed from 5/6 sustained episodes
at update 32 to 0/6 at update 128. Capital spending fell by avoiding service, not
by improving efficiency. `economic-budget-comparison-01/comparison.json` retains
the matched prefix/native comparisons. Keep native reward as default.

Next learning hypothesis, after isolated performance measurements: native reward,
seed 20260924, 128 updates/16,384 transitions, but a 128-action training horizon.
That gives 128 completed training episodes instead of 32 and more construction
states per unit experience. Evaluation remains the ordinary 512 actions on maps
05/06. The earlier 4,096-transition short-horizon seed did not solve construction;
this larger matched-budget comparison is unproven, not an adopted curriculum.

The fused CUDA implementation passed 6,984 CPU-reference rows across full/sparse/
single-action masks and logit scales 0–1,000, including a nondefault stream.
Maximum absolute errors: log probability 3.8147e-6, probability 1.78814e-7, entropy
9.53674e-7; greedy actions matched. Invalid shapes/devices/dtypes, autograd inputs,
nonfinite illegal logits and all-illegal masks are rejected. The first compilation
failure (missing math_constants.h) is retained in fused-build-01.log.
Compute Sanitizer did **not** run successfully: its WSL WDDM debugger interface
requires host administrator setup and reported unsupported device. The numerical
test inside that invocation passed, but this is not a sanitizer pass; no host
debugger settings were changed. PPO optimization still uses the trusted autograd
path. Default builds leave the inference experiment disabled.

`fused-microbenchmark-01` ran five isolated repetitions per device. At batch four,
median validated masking costs were CPU 53.91 us, reference CUDA 763.70 us, fused
CUDA 79.39 us (9.62x within that operation). At batches 64/512, fused CUDA medians
were 79.38/82.33 us versus CPU 97.86/371.42 us. Host/device input transfers and the
rest of training are excluded from those microbenchmarks.

`fused-live-comparison-01` passed both paired four-update real-game runs, with
2,048 byte-identical native action/state/economic transitions and PPO metrics
within preregistered rtol 1e-4/atol 1e-5. Order was reference/candidate then
candidate/reference. Total collection/update times were 38.423/38.397 seconds
and 38.642/38.308 seconds. Median speedup was only 1.0047x (range 1.0007–1.0087),
despite inference calls improving from 4.54–4.59 to 3.80–3.90 seconds. This is not
a convincing end-to-end throughput gain with two pairs. Keep the correct kernel
as an optional CUDA learning experiment; do not change default training. All ten
native tests, including CPU/CUDA checkpoint/export checks, passed with it enabled.

The registered construction-frequency experiment is now
`live-cuda-curr128-128u-s20260924`, using the unchanged reference CUDA trainer.
Separately prepare the existing M15 V2 native bus source in an isolated tree as
the prerequisite for a sequential control loop. Existing program-replay/corpus
qualification remains distinct from a live observation/action interaction.

### First interactive V2 native boundary

`prepare_v2.py` composed the frozen M15 native reset, observation, candidate,
episode and bus-service patches onto the retained pristine V1 engine. Every
intermediate Git tree matched its recorded source identity. The separate
`v2-live-engine` headless build passed 97 native tests; the original binary is
preserved as `build/openttd-m15-baseline`. No evaluation manifests were used.

The development-only `integration/dev/rl_v2_live.inc` reuses native candidate
enumeration and execution through bounded inherited pipes. It exposes versioned
own-company/public observations and candidates, token-checked ACT, fixed-budget
STEP and CLOSE. One action must be followed by one step; observation and rejected
requests do not advance simulation. The initial adapter explicitly supports one
company, maps up to 128x128 and up to 512 decisions/128 ticks per decision. These
are development-slice bounds, not a reduction of the broader V2 objective.

`v2-live-smoke-01` and `v2-live-smoke-02` passed eight real interactive decisions:
the reactive script observed no depot, built one, observed no bus, bought one,
then waited. Repeated native action/state/economic traces matched byte for byte.
Wrong-company, stale-token, illegal-candidate, step-without-action and duplicate
action checks rejected without extra simulation ticks. This is executable
interactive control, not yet passenger service, V2 neural learning, or shared-map
competition. The second build also removes a vector-allocation compiler warning
and tightens integer configuration checks.

The current development Python suite passed 34 tests and the repository fast
suite passed 136. The first fast-suite attempt used the UV virtual environment;
the historical verifier resolves its interpreter symlink and restricts PATH,
losing jsonschema/Git. Rerunning with the system `/usr/bin/python3` passed without
changing release scripts or tests; the guide now states that interpreter explicitly.

The 128-update, 128-action curriculum seed 20260924 completed its full evaluation
in `policy-curr128-128u-s20260924`. Greedy maps 05/06 delivered 1,519/1,659
passengers with 3,307/4,286 operating profit and sustained service in both maps.
Both bought four buses and assigned three routes; repeated route-action toggles
remain. Sampled results averaged 1,950.33 passengers and 1,542.33 operating profit,
with 5/6 sustained episodes and eight buses each. All eight episodes had zero
invalid actions or bankruptcy. This improves deterministic construction over the
matched native 128-update seed, but does not establish economic superiority over
the efficient one-bus script or consistent improvement in sampled service.

Next registered test: repeat the unchanged native-reward 128-action curriculum
for 128 updates on seeds 20260923 and 20260925, reference CUDA trainer, with full
512-action greedy and sampled evaluation on development maps 05/06. Judge all
three training seeds together: successful construction, sustained final-window
profit/delivery, capital efficiency, failures and bankruptcy. Keep each seed's
result; do not select only the successful policy. In parallel, the next V2 slice
will construct a complete bus service from public map facts and currently exposed
legal candidates, issuing one ACT/STEP pair per decision. Native service macros
and corpus reward tables are excluded from this interactive gameplay claim.

`v2-service-live-01` completed 512 ACT/STEP decisions from public map/own-company
observations. It built seven road primitives, two stops, one depot, bought one
bus, assigned its observed station IDs and started it, then waited. Native state
advanced exactly 65,536 ticks. It delivered 707 passengers with 1,816 income,
-4,028 operating profit, no failed actions and no bankruptcy. This establishes
live sequential service, not profitability or V2 neural competence. The public
map now reports visible clear/house tiles; hidden RNG/reset seeds remain absent.

Next matched economic test: keep the same route and map, then use exposed loan
repayment actions after service starts while retaining at least 10,000 cash.
Compare all 512 decisions and separate capital, loan principal, operating profit
and balance change. The original carried its full 100,000 loan, so interest may
dominate the short local route's fares. Preserve a wait-only control and exact
repeat of the original script as boundary checks; do not infer efficiency from
reduced loan balance alone.

`v2-service-comparison-01` confirmed the original script's 512 native transitions
repeat byte for byte. WAIT delivered zero and lost 4,834 in operating profit.
Repaying 70,000 after service started retained the same 707 passengers and reduced
the loss to 677; all four windows remained negative. Capital was unchanged at
10,436. Principal repayments are reported separately, never counted as operating
expenses. No failed actions or bankruptcies occurred in these controls.

A public-state feasibility check found no straight 10- or 12-tile route among
the current legal candidates, even allowing existing public roads inside it.
Next hypothesis: routing around the town's existing roads can connect more
separated catchments and earn sufficient fares. Add an optional graph planner
over public road bits and exposed construction candidates, with one native action
and fixed step per primitive. First test only the same training map; preserve the
straight planner and failed-site evidence. No candidate quotas or native commands
change, and no development-map result is consulted to choose the route.

`v2-service-graph-01` completed all 512 decisions on the initial training map:
728 passengers, 2,082 operating profit, 7,086 capital, -5,004 profit less capital.
It used public roads with three added road primitives, two stops and one depot;
service started at decision 9. Eight explicit loan actions repaid 80,000 while
retaining the 10,000 reserve. Delivery/profit windows were 128/239, 187/523,
217/748 and 196/572. There were no failed commands or bankruptcy. This is useful
scripted service through the live V2 boundary; it is not a trained V2 policy or
capital payback. Four client preflight tests and 97 native engine tests passed.

Next registered check: run the unchanged graph/repayment baseline (minimum
12-tile endpoint separation setting) on the first three development seeds from
the existing M15 ledger, each with 512 decisions. Include every failure and
compare one-bus service, sustained windows, operating/capital accounting, survival
and action counts. Do not change planner weights from these results during this
check. A matching training-map replay will separately verify deterministic traces.

The unchanged graph baseline passed sustained service on only one of three
development seeds. Seed 1630856436 failed after one decision: a second road-axis
primitive on tile 2221 was no longer legal after the first axis was built.
Seed 155097162 completed 512 decisions with zero passengers and -1,983 operating
profit; its bus visited both stops repeatedly, so this is not missing orders.
Seed 1456534872 delivered 772 passengers, earned 2,298 operating profit and had
positive delivery/profit in all four windows, with 7,024 capital. No completed
run had invalid commands or bankruptcy. Retain these as a failed reliability
check, not three successes. The training-map graph replay retained identical
economics; its native trace comparison is checked separately.

Diagnostic hypothesis: the public-state planner counted houses within radius
four, borrowed from the old qualification, but native bus catchment can be three.
It also treated individually legal road axes as a legal intersection. The adapter
now exposes public flat-terrain tiles, configured bus catchment, native present
acceptance/production for stop candidates, actual station waiting/acceptance,
and own bus cargo/speed/destination. These are present-state construction/vehicle
information, not future outcomes. Replay the two failed development configurations
for 64 decisions without changing the planner first, to inspect those fields and
verify the observation additions preserve the original native trace prefix.

`v2-service-diagnostic-01/02` reproduced those failures. Tile 2221 is non-flat.
The zero-delivery route's origin stop had native acceptance 0/8 and production
zero; the other accepted passengers, and its bus was carrying 28 passengers back
to that accepting stop. Radius-three catchment explains the incorrect radius-four
house estimate. The 64-step diagnostic's native actions/states/economics matched
the original prefix exactly; only its deliberate final truncation flag differed.

The optional `--native-site-checks` graph planner now requires native present
passenger acceptance >=8 and production >0 at both endpoints, uses the configured
catchment radius, and carries incoming road direction in its graph search. It
avoids constructing new turns/intersections on non-flat tiles while allowing
already existing road connections. The same three development seeds are rerunning
as `v2-service-checked-dev-01/02/03`; this is development diagnosis/selection,
not held-out evaluation. The original failures and source archives remain.

The existing M15 scalable recurrent policy now builds with the local Torch/CUDA
runtime through an opt-in `local.py build --v2-policy` target in a separate
`build/v2-live-policy` directory. No policy/PPO source or frozen release profile
was rewritten. Its CPU/CUDA gates are the next check before attaching that model
to live observations; merely compiling this model is not V2 learning evidence.

The corrected planner completed all three development seeds with sustained
service: passengers 1,422/1,054/1,557; operating profit 5,344/1,685/5,451;
capital 7,368/11,017/6,366. All had one bus, no invalid actions or bankruptcy.
These are selected development results after diagnosing the preceding failures,
not an independent generalization claim. None recovered its full capital within
512 decisions. The explicit native-site checks are the supported graph workflow.

The local M15 policy passed both CPU/CUDA gates. Next is a bounded eight-decision
untrained recurrent-policy interaction, comparing CPU and CUDA probabilities
(absolute tolerance 1e-5), values (1e-4) and selected rows on identical live
observations. The `TENSORS` operation reuses native serialization while redacting
seed features and vehicle breakdown delay/countdown columns before returning
paths. The latter can expose a future failure and must not enter live policies.
New metadata labels this public development view; historical encoders/records are
unchanged. Native state hashes must remain equal across tensor reads, and exposed
candidate keys/parameters/features must match the tensors exactly. This is an
inference-boundary check, not PPO training or a gameplay-competence claim.

The eight-decision live neural check passed: CPU/CUDA selected the same candidate
rows, with maximum probability error 6e-8 and value error 2.39e-7. Four native
policy/distribution gates passed. The initial weights issued legal construction
actions but do not establish service competence.

Next bounded V2 correctness experiment: two PPO updates (64 actual decisions)
each on explicit CPU and CUDA, with training-only map rotation and a 20-decision
episode horizon. This horizon deliberately resets inside an eight-step recurrent
sequence. Require exact stored masks/context to reproduce behavior probabilities
before optimization (absolute tolerance 1e-4), finite gradients/parameters, correct
time-limit bootstrap without carrying recurrent state into the next episode,
64 legal native actions and 128 ticks per action. Reuse the trusted V1 GAE/PPO
loss with the existing V2 recurrent policy; Python only transports game data.
The new reward records delivery, operating profit, capital and decision cost
separately, excluding loan principal. Saved V2 weights are inference-only; V2
optimizer/RNG resume is not yet supported. These short runs test the pipeline,
not learned gameplay.

The 128-update, 128-decision MLP curriculum replication finished on all three
training seeds. Greedy service succeeded on seeds 20260923/24 but failed on
20260925 (zero delivery, no buses); this is two of three reliable constructors,
not a solved task. Full results are retained in `comparison-curr128-128u-01`.
Next Goal 1 hypothesis: spatial information may improve construction reliability
over the structured MLP. Run the existing spatial CNN on all three matching
training seeds, the same 16,384 transitions, 128-decision training horizon,
native reward and reference CUDA policy math. Evaluate each on both development
maps for 512 decisions with greedy and the same three sampling seeds. Compare
all seeds, sustained service, operating/capital outcomes and invalid actions
against the MLP curriculum and existing baselines; no held-out maps are accessed.

`v2-live-ppo-cpu-smoke-01` and `v2-live-ppo-cuda-smoke-01` both completed two
updates. All 64 native transitions matched exactly, including three time-limit
bootstraps and four recurrent resets. Maximum CPU/CUDA errors were 9.6e-7 in
behavior log probability, 7.2e-7 in current/next values and 2.492e-5 in update
metrics. Each run had three complete 20-decision episodes plus four decisions
of a fourth episode, zero deliveries and no failed commands/bankruptcy. These
are real-game optimization checks, not sustained-service evidence. The comparison
is reproducible with `compare_v2_training.py`. Three reward-accounting tests pass.
The next revision checks every recurrent sequence before optimization (the first
smoke checked one shuffled sequence), and reloads saved weights to verify all
model outputs on an actual input before marking the save successful. Repeat the
same bounded CPU/CUDA check because those validation paths changed.

The stronger CPU replay check passed all 64 probabilities exactly and saved
weights reloaded with zero output error (`v2-live-ppo-cpu-smoke-02`). Loading the
first CUDA smoke's weights in fresh CPU/CUDA inference processes also passed
eight live actions with probability error 5.9e-8 and value error 4.8e-7.

Information audit found a further issue: historical M15 vehicle ordering uses
private breakdown counters. Zeroing feature columns alone did not remove the
ordering side channel. The live encoder now opts into public vehicle-ID ordering
before selection and graph construction; the historical default path is retained.
This changes the development observation ID to `v2-m15-public-development-v2`.
The neural decoder enforces public row order, and inference rejects old-schema
weights. Existing smoke runs remain historical pipeline checks, not evidence for
the corrected information boundary. Repeat the same CPU/CUDA two-update check
on this new schema, then load its saved weights for the eight-action comparison.
The rebuilt engine passed 2,160 assertions in 95 native test cases.

The corrected public-v2 CPU/CUDA checks passed 64 identical native transitions
again, with maximum update-metric error 2.489e-5. Every recurrent sequence is now
checked before optimization, and both saved models reload with zero output
error. Eight live actions using saved CUDA weights also passed CPU comparison.

Next Goal 4 prerequisite: a bounded two-company smoke using the same native
candidate/ACT/STEP code. Alternate actors for eight total decisions, 128 ticks
per global decision, four actions each, equal initial cash/debt, no automatic AI.
Each company must build its own depot/bus; require out-of-turn and cross-company
vehicle commands to be rejected without advancing time. Own finances remain
visible, while opponent financial/internal fields are zero in the neural view.
Public entity ordering must not reveal fields that were redacted. Repeat with
the first actor swapped, and compare the prior single-company neural trace.
This is a scope/timing check, not yet an economic match or an MCP-connected LLM.
The first shared build failed for a missing company-context header; retain that
failed revision and rebuild with the correct declaration included.

`v2-shared-scope-01` failed after the first company's action. The retained native
crash log identified `StateGameLoop`'s `IsLocalCompany()` assertion: the adapter
had passed company 1's command context into world stepping. Entering the normal
local-company context for stepping and restoring the actor afterward fixes the
cause without disabling the assertion. `v2-shared-scope-02` and the swapped-first
check both passed eight steps, four per actor, with one owned depot/bus each and
three rejected cross-company vehicle commands. Opponent financial tensor fields
were zero and ownership markers matched both identities. Single-company loaded
neural inference also completed eight actions after this change; exact prior
trace comparison is next.

The first registered CNN seed completed its eight full development episodes
with zero delivery in every episode. It failed both greedy and sampled service.
The other two matching seeds are still running; retain the complete matrix.

Next bounded live-V2 training experiment: 16 CUDA updates, 512 real decisions,
128-decision episodes over the first four training maps, seed 20260923, unchanged
public-v2 inputs and explicitly versioned economic reward. Require all numerical
and recurrent replay checks, then full 512-decision development inference on
separate maps. This tests whether the current large primitive action space finds
any service at a small budget; zero service remains a failure, not an optimization
success. Shared match accounting will retain simultaneous company economies only
in researcher traces, never in either actor's response.

`v2-single-shared-regression-01` verified all eight native single-company
transitions byte-for-byte after company scoping. An exploratory exact assertion
on floating inference outputs failed; maximum probability difference was 3e-8,
within the already registered 1e-5 tolerance. Do not describe these predictions
as byte-identical. The swapped-first shared scope run also passed.

The 16-update V2 run completed 512 actual decisions and four 128-decision
training episodes with finite gradients, replay error <=9.54e-7 and saved-weight
reload error <=9.54e-7. All four episodes delivered zero passengers. Two separate
development maps (the first two existing M15 development seeds) now each receive
512-decision greedy and sampled evaluations. This small primitive-action run is
not yet a useful V2 policy.

MCP SDK 2.2.0 is installed in its own `mcp-venv`; the Torch environment is
unchanged, and the exact dependency list is retained under `deps/`. The first
actual stdio client test failed because the SDK returned standard text JSON
instead of structured content; the parser now accepts both valid MCP forms.
`v2-mcp-stdio-smoke-02` passed actual SDK client/server calls and eight shared
native steps, including stale-action, repeated-start and step-before-action
rejection. Its controller was a script, not an LLM. `v2-mcp-smoke-accounting-01`
separates native capital, operating profit, loan changes, action attempts and
market share (undefined when neither company delivers). The one intentional stale
submission is recorded as a rejection, not hidden. Provider financial inference
cost remains unknown rather than being recorded as zero.

The completed first-map V2 greedy and sampled development episodes delivered no
passengers; greedy repeated town selection, sampled bought disconnected assets
and earned -7,653 operating profit. The second map's greedy episode also delivered
zero; its sampled episode is still running. Initial public observations from all
four training episodes admit the existing native-checked graph plan (6--8
construction primitives before purchasing/orders/start), suggesting a concrete
exploration bottleneck in thousands of largely uncoordinated primitive choices.

Next optional curriculum hypothesis: restrict the sampling mask to WAIT, the next
public planner proposal, and affordable debt repayment. PPO must still choose
and execute each primitive; all actions retain one 128-tick native step. The
planner supplies route geometry, so this tests execution timing/finance learning,
not unassisted route discovery. Native legality remains unchanged and retained
separately; behavior log probabilities use the exact narrower sampling mask.
Planner preview/bootstrap must not advance plan state, and choosing WAIT must
not skip construction. Three focused tests passed those mask/progression checks.
Next run two updates each on CPU/CUDA with horizon 20, requiring the same trace
and numeric tolerances as the prior recurrent check. If that passes, compare a
matched 16-update assisted run with uniform random choices under the same guide
and the deterministic script before attributing any service to learning.

The unassisted 16-update V2 development matrix is complete: zero passengers in
all four episodes. Both greedy runs select town pairs for all 512 decisions;
sampled map 1630856436 reaches 512 decisions with -7,653 operating profit and
map 155097162 reaches bankruptcy at decision 457 with -10,596 operating profit.
No submitted action was invalid. These are exploration/economic failures.

`v2-mcp-console-probe-01` completed eight native turns through the interactive
official SDK client, negotiated MCP 2026-07-28, rejected step-before-action and
saved the economic summary automatically. This was a scripted console probe.
An actual fresh-context LLM opponent awaits the explicit subagent authorization
required by this session; no API credentials are available. Training can continue
independently. Unknown financial inference cost remains null.

The first guided CPU launch used a wrong engine path and never started a game
(`v2-guided-ppo-cpu-smoke-01`). The corrected `...smoke-02` failed at the fourth
training map: repayment changed the native bounded candidate set, removing the
next planned road while its public tile remained clear. The guide now proposes
another currently exposed primitive from the same plan, or WAIT when all are
unavailable. Reordering is committed only when that construction action executes;
native legality is never bypassed. Five focused tests pass. The CPU/CUDA repeat
`...smoke-03` is in progress; failures remain preserved.

Next V1 architecture comparison, registered before its runs: combined-cnn-mlp-v1
on seeds 20260923/24/25, 128 updates (16,384 transitions), horizon 128, native
reward, identical CUDA reference trainer, checkpoint interval 16 and fast bridge.
Evaluate every model for 512 decisions on the same two development maps with
greedy and the same three sampling seeds. Compare all seeds with the completed
MLP and ongoing CNN matrix; do not select a winning seed. This tests whether
structured economic inputs recover service absent in the spatial-only runs.

`v2-guided-ppo-smoke-comparison-03` passed 64 identical native transitions and
planner masks, including three time-limit bootstraps and four recurrent resets.
Maximum log-probability/value/next-value errors were 2.40e-7/5.07e-7/5.36e-7;
maximum update-metric error 1.914e-5 is below the unchanged 1e-4 tolerance.
The matched `v2-guided-ppo-16u-01` then completed all 512 training decisions:
four episode deliveries [279,279,230,35], operating profit [1000,1226,496,-123].
Only 139 decisions had more than one sampling choice; 19 had blocked
construction. Saved weights reload within 2.98e-8. Full greedy/sampled episodes
and uniform/scripted controls on the first two development maps are running.
Training delivery alone does not separate planner benefit from learned benefit.

The complete three-seed spatial CNN matrix delivered zero in all six greedy and
18 sampled episodes. `architecture-comparison-mlp-cnn-01` checks identical
training budgets/binaries/templates and full evaluation matrices across all six
models: MLP sampled means 1959.4 passengers / 1975.4 operating profit, sustained
17/18; CNN means 0 / -4834, sustained 0/18. MLP greedy is sustained in 4/6,
CNN in 0/6. The report includes training-seed means and conditional paired
Student-t intervals, not episode-as-independent confidence intervals. Combined
model runs have started with the preregistered same three seeds/budget.

Single-company economic summary version 2 now distinguishes gross capital from
vehicle resale and net capital, consistent with shared accounting. Three native
sales in the first unassisted sampled development run returned 12,794: net capital
82,662 and profit less net capital -90,315. Passenger/operating-profit results
are unchanged. `v2-unassisted-16u-accounting-03` rederives this from saved traces
and preserves original reports. An earlier in-memory analysis was stopped for
excessive memory use; the completed version streams observations. All 48 focused
development tests and `git diff --check` passed after the guide/accounting edits.

The MLP/CNN comparison is copied into the ignored Windows workspace artifact
`runs/2026-09-23/architecture-comparison-mlp-cnn-01/`. Its inspected PNG/SVG plot
shows individual training-seed means, conditional 95% t intervals, operating
profit and profit after capital; broad greedy intervals and unrecovered capital
remain visible. Plotting dependencies are isolated in `analysis-venv` with an
exact requirements freeze, preserving the Torch and MCP environments.

MCP adapter 0.2.0 adds optional compact observations, a filtered public map region,
and an eight-own-turn maximum WAIT batch to bound individual client calls. An
offline check on the recorded native public observation verified identical
region fields, unchanged compact state and four rejected invalid rectangles;
JSON sizes were 37,759 bytes full, 857 compact and 2,396 for a 16x16 region.
This projection check is not a new game or an LLM match. The updated actual SDK
smoke is pending a free native-run slot; the prior console/transport results are
for the earlier interface revision.

The first full guided development map is complete: learned greedy 0 passengers /
-4834 operating profit; learned sampled 1374 / 5187; uniform choices under the
same guide 1421 / 5402; deterministic guided control 1422 / 5344. All service
controllers sustained deliveries/profit in the final three windows, but none
recovered capital. The learned sampled policy is not ahead of the uniform
control. The second map's corresponding matrix remains in progress.

Training diagnostics sharpen the CNN failure: all three CNNs delivered in
30--32 of their first 32 complete 128-action training episodes, but in zero of
their last 32. The MLPs delivered in all first/last 32 episodes. CNN final entropy
falls to 0.004--0.016, with no large KL explosion (maximum observed per-update
mean KL below 0.012). `architecture-training-diagnostic-02` excludes four final
zero-action reset artifacts per run accidentally included in audit-01's final
window; audit-01 remains preserved and superseded. This is loss of previously
observed training service, not merely failure to encounter any service.

MCP full-match preparation exposed an SDK lifecycle constraint: mcp 2.2.0 gives
the server two seconds after stdin closes before terminating it. Bulk tensor
compression during lifespan shutdown could be interrupted. The adapter now
archives each consumed immutable neural snapshot after its world step; the
updated native smoke checks all eight tensor files survive as verified gzip
before the client closes. Full scripted SDK matches use only public tool results,
and remain explicitly labeled scripted. After the smoke passes, run 512 global
decisions on each of the first two development seeds, swapping script/neural
company roles with company 0 moving first. This tests shared economic execution,
action budgets, survival and market share with the saved unassisted 16-update
neural policy; it is not a strong-policy or LLM comparison.

Cash reconciliation found a stable -25 monthly difference: the pinned
`economy.cpp` charges `EXPENSES_OTHER` alongside interest, while `company_cmd.cpp`
excludes that category from `cur_economy.expenses`. Full 512-decision episodes
therefore incur 725 not present in the native operating subtotal. Native counters
remain unchanged. V2 reports now additionally give cash excluding financing,
cash before net capital, the other-cash-flow residual, and a separate positive
cash service-window flag. The original native operating-service criterion stays
visible. `v2-guided-first-map-comparison-01` rederives the four first-map results
from original traces: sampled learned cash after capital -2906, uniform -2691,
scripted -2749, all excluding loan principal. All three remain positive before
capital in every final window. This does not establish a learned advantage.

The complete two-map guided/unassisted pilot is now rederived in
`v2-guided-unassisted-comparison-01` (also copied under the ignored Windows
`runs/2026-09-23/` directory). Guided sampled means 1152 passengers / 3514.5
native operating profit; same-guide uniform means 1182.5 / 3629; scripted means
1238 / 3514.5. All three sustain positive cash service in both maps, but mean
cash after capital is -6403 / -6288.5 / -6403 respectively. Both guided greedy
episodes remain WAIT-only. Unassisted sampled delivers zero and goes bankrupt
on one map. This is one training seed and one sampling seed, so the comparison
is descriptive, with no learned-advantage or generalization claim.

`v2-mcp-stdio-smoke-03` passed the current 0.2.0 interface through the real SDK:
eight native shared decisions, compact state and region fidelity, rejected
invalid bounds/oversized wait batch, and all eight consumed neural tensor files
archived before client shutdown. No LLM participated in that smoke.

Local Ollama 0.32.5 already has the original
`hf.co/unsloth/gemma-4-E2B-it-qat-GGUF:UD-Q4_K_XL` model, digest
`900efb9b639f0331b153454a97f8cc156764702542534490db18325298074851`.
No download, API credential or Codex subagent is required. A loopback-only host
Python bridge lets the WSL MCP client call it without changing network settings.
`local-llm-tool-probe-01` emitted the correct call but failed an overly strict
checker rejecting Ollama's optional function index. Probe-02 checks name and
arguments, disables optional model thinking, and passed in 0.897 seconds warm.
The runtime reported its loaded model entirely in VRAM (1,666,334,064 bytes).
The first actual LLM smoke failed before any native turn with an Ollama HTTP 500
after game_info/start/observe/legal_actions. The same continuation succeeded in
an offline provider probe; the original cause is not established. Error bodies
and attempted requests are now retained. Smoke-02 requests concise tool calls
with a 768-token output limit instead of 384. All game choices still come from
model tool calls; provider failure, 16 stalled calls, or exhausted call budget
abort rather than substituting a scripted controller. Native idle limits remain
unchanged. These probes do not establish a completed LLM match yet.

LLM smoke-02 stopped after 14 invalid string-valued `parameter1` calls and no
native turns. Model-facing optional nullable scalar schemas now expose the
non-null scalar type (omission selects the unchanged server default), with
explicit ID/filter descriptions; two conversion tests passed. Smoke-03 then
made valid commands but stalled with an accepted action awaiting STEP. MCP
0.2.1 now returns `next_required_tool=step` on acceptance and specific pending
errors. SDK smoke-04 passed rejection-without-time-advance checks.
`v2-mcp-local-llm-smoke-04` completed eight global decisions / 1,024 ticks with
four actions per company. Gemma issued four stop-building commands at the same
tile: the first created one stop for 382, the next three succeeded at zero cost
without adding a stop. The neural policy issued one town selection, two
stop-building commands and one road command. Neither delivered passengers.
The LLM made 20 model calls, generated 937 tokens and used 32.357 seconds of
model wall time, with one recoverable MCP error and zero native action failures.
This is an actual local LLM/MCP-versus-neural smoke, not service competence.
The same prompt/model/configuration now has a preregistered full 512-global-step
development run on map 1630856436, LLM company 0 moving first, 1,600 model calls
maximum, 45-second inference deadline and 16-consecutive-stalled-call limit.
Its economics and failure outcomes will be retained regardless of completion.

`v2-mcp-local-llm-smoke-audit-04` independently matched all 20 model responses,
15 tool calls (one rejected), actual MCP responses and four player native
actions, then rederived the economic result. The audit expands declared server
defaults when comparing omitted optional arguments; it does not alter model
choices. It proves recorded controller-to-native correspondence, not exact LLM
replay or playing strength. The repeated zero-cost construction noted above
corrects the initial shorthand description of four stops; final public state
contains one owned stop. Both successful command counts and physical service
outcomes must remain visible.

Next goal-1 experiment: `balanced-economic` reuses the existing ordered reward
adapter with passenger /64, native operating profit /1024, capital -/4096 and
uniform 1/64 decision cost, retaining native clipping and failure terms. This is
between the passenger-heavy default and the earlier economic setting that
converged to inactivity. Hypothesis: less reward for excess passenger throughput
relative to capital/operating costs can retain service with fewer purchased
buses. Register one MLP seed 20260923, 128 updates / 16,384 transitions, 128-action
training episodes on the same four training templates, CUDA, fast validation,
checkpoint interval 16. Evaluate full 512-action greedy and three sampling seeds
on both development maps. Compare delivery, sustained operating service, capital
and profit against the matched native-reward MLP seed and one-bus/random controls;
do not treat reduced spending without delivery as success. Replicate only if
this bounded diagnostic warrants it; no held-out maps are used. Six reward tests
passed, including unchanged behavior probabilities/masks/GAE flags and identical
decision cost across WAIT and free toggling. No PPO or native binary was changed.

MCP 0.2.2 now has a separate deployment path for saved planner-assisted weights:
it reconstructs the same public guide, uses the exact filtered mask, commits only
executed proposals, checks probability support, and records the guide at every
neural turn. Controllers are explicitly labeled neural+public-planner. Native
CPU/CUDA guided smoke and unassisted regression are pending a free run slot;
the current full LLM match continues with its archived 0.2.1 unassisted server.

The completed nine-model/72-episode architecture matrix is in
`architecture-comparison-all-three-01`, with an inspected PNG/SVG under Windows
`runs/2026-09-23/architecture-comparison-all-three-01/figure-readable-02/`.
Combined greedy means 1126.5 passengers / 1783.5 native operating profit,
sustained 4/6; sampled means 1964.7 / 2768.6, sustained 16/18. Corresponding MLP
means are 1136.7 / 1472.7 (4/6) and 1959.4 / 1975.4 (17/18); CNN still delivers
zero in all 24 evaluations. Combined seed 20260925 fails both greedy maps,
so first-two-seed success did not establish improved greedy reliability.
All architectures use the same 16,384-transition budget, seeds, training maps,
native binaries and complete evaluation matrix. Cash change is now also shown
directly from existing episode records: combined sampled mean -38,726.9 versus
MLP -39,520.1, exposing unrecovered capital and monthly other expenses. Earlier
reports/figures remain intact. The preregistered balanced-reward MLP diagnostic
has started, followed automatically by its full eight-episode evaluation.

MCP 0.2.2 passed guided CPU and CUDA native smokes plus the unassisted regression.
`v2-mcp-guided-parity-01` records eight byte-identical guided native transitions,
four identical neural choices and exact native/sampling mask hashes. Maximum
CPU/GPU probability/value differences are 6.0e-8 / 2.4e-7. Unassisted 0.2.1 and
0.2.2 traces are byte-identical. All 12 guided tensor files are archived before
SDK shutdown. This preserves the trained guide on deployment; it does not turn
planner-supplied route geometry into a learned capability.

The combined-minus-MLP sampled operating-profit difference is +793.2 on these
maps, with a three-seed paired 95% t interval [-354.9,1941.3]. This does not resolve
an architecture advantage. Its greedy passenger difference is -10.2 with interval
[-204.5,184.2]. The full matrix supersedes impressions from the first two seeds;
further objective changes are development experiments, not held-out validation.

A separate recovery diagnostic will select a CNN checkpoint using training data
only: among saved updates 16,32,...,128, maximize mean delivered passengers over
the immediately preceding four complete episodes per training environment;
break ties by operating profit, lower capital cost, then earlier update. The
four-map window is fixed before scoring. Export each selected checkpoint without
another PPO update, then evaluate the same two development maps and selection
seeds. First verify that exporting a final checkpoint reproduces the training
run's final model identity. The original final-update architecture matrix stays
unchanged. This tests preservation of an earlier useful policy, not a cure for
the CNN training collapse; all 16,384 transitions used for selection are counted.
`export_checkpoint.py` is implemented but native validation is waiting for a
free experiment slot. It binds the saved trainer binary/configuration/payload
and never resumes collection under changed Python sources.

`balanced-objective-audit-02` rescores existing executed full episodes using the
new weights and the frozen CPU reward reference. The native-reward MLP seed23's
greedy service scores 19.150, one-bus control 18.484, its sampled policy 13.865,
and WAIT -12.721. Useful service therefore exists with higher full-episode return
under this objective; this offline audit is not new learning evidence. Audit-01
pooled old/current models under common greedy/sampled labels and is superseded:
the auditor now groups by evaluation root and policy and retains package identity.

A source check ruled out a different initial clock normalization between short
training and full evaluation. The pinned native `rl_observation.cpp` always
normalizes remaining actions/ticks against 512/65,536, independently of the
bridge's shorter truncation limit. States after action128 are nevertheless absent
from the short curriculum; this remains a possible longer-episode transfer issue,
not an established explanation for the initial greedy construction failure.

The balanced-reward seed23 diagnostic completed. All six sampled episodes have
sustained native operating service: means 1,671.3 passengers, 4,716.7 operating
profit, 14,525.2 capital and -10,533.5 cash change. Matched native-reward sampling
delivered 1,935.2 with 2,536.3 operating profit and -38,959.2 cash change. Both
balanced greedy episodes still deliver zero; one-bus cash (-2,280) remains better.
`comparison-balanced-curr128-128u-s20260923-02` reports this one-seed result without
a confidence interval; report-01 had an incorrect generic three-seed footer and
is superseded. The spending reduction warrants two registered replications:
seeds 20260924/20260925, otherwise identical 128-update/h128 configuration and
eight full development episodes each. Run after the current two-job queue frees
a slot. Keep all three seeds, including any service failures, in the comparison.

`cnn-final-checkpoint-export-01` passed native restoration/export and reproduced
the final CNN seed23 model identity exactly. Training-only selection chose
updates 32,16,16 for seeds 20260923/24/25 (`cnn-checkpoint-selection-01`). Their
exports and full evaluations are now running; no further training is performed.

The actual Gemma MCP match `v2-mcp-local-llm-full-map1630856436-c0-01` completed
512 global decisions / 65,536 ticks, 256 actions per company. Neither agent
delivered passengers or went bankrupt. The LLM issued three stop commands (one
physical stop, two zero-cost repeats) and 253 WAITs; operating profit -4,834,
cash -5,941. The unassisted neural opponent spent 96,272 net capital, with
operating profit -6,134 and financing-adjusted cash -103,131. All native actions
succeeded, but the LLM made 252 recoverable MCP errors among 767 calls. Its 1,272
model calls processed 10,993,181 prompt tokens, generated 16,854 tokens and took
2,725.109 seconds excluding warmup. Local provider charges are zero; hardware
and electricity are unpriced. `v2-mcp-local-llm-full-audit-01` independently
matched model choices, MCP calls/results, all player actions, timing/token sums
and native economics. This demonstrates actual shared-game participation, not
either agent's competence or deterministic LLM replay. The four preregistered
scripted MCP controls (two development maps, both company roles, fixed first
company zero) have started against the same unassisted neural weights.

The offline discounted audit (`balanced-discounted-objective-audit-01`) now also
uses native PPO gamma=0.99, from the first action through the executed episode,
without a critic bootstrap. Under balanced weights, one-bus return is +1.203,
balanced sampled +0.154 and WAIT -2.399; ordinary native-reward sampled actions
score -3.498. Capital timing changes the ranking relative to undiscounted totals,
but does not make inactivity optimal among the observed controls. This supports
replicating balanced sampling while retaining the cheaper one-bus target. The
balanced greedy trace builds two stops, then alternates town-selection actions
510 times. It retains roughly 1.06 nats of policy entropy: this greedy loop is
distinct from the final CNNs near-deterministic collapse.

`cnn-selected-checkpoint-comparison-01` completed all 24 selected-checkpoint
evaluations. Sampled means are 1,457.1 passengers / 1,147.6 native operating
profit / -38,707.6 cash, sustained 10/18, with no invalid actions or bankruptcy.
Greedy still fails all six episodes. Final CNN weights deliver zero in all 24.
The paired selected-minus-final sampled passenger difference is +1,457.1 with
three-seed conditional 95% t interval [967.2,1947.0], but cash worsens by 32,669.8
because construction resumes. This confirms recoverable earlier service, not
efficient CNN learning or a resolution of later collapse. Total selection cost
remains 16,384 training transitions per seed. Balanced-reward replications
20260924/25 have started with the original native binary and matched settings.

All four fixed scripted MCP controls completed (`v2-mcp-full-comparison-02`, also
including the audited LLM match). On map1630856436 the script delivered 1,457 /
1,359 passengers by company role, with operating profit 5,418 / 4,815. On
map155097162 both roles delivered zero despite building, routing and starting
one bus; there were no tool/native failures or bankruptcy. Company0 public road
bits at tile937 changed from 10 to 8 at global decision70 when the opponent
successfully built a depot there, then to 2 at decision100. The original planned
through-route used tile937. This is a native shared-world obstruction; the fixed
controller never repairs its plan. Do not infer an intentional neural strategy.

Register a separate adaptive scripted control on map155097162/company0, 512
global decisions, same neural opponent/seed and first company0. It checks current
public road connectivity every 16 own turns after service starts, and when
disconnected proposes primitive detour roads from current exposed candidates.
Every construction still uses one ordinary action/STEP. No researcher economics
or opponent-private state enters its choices; old fixed controls remain intact.
Three focused graph checks pass (unchanged route costs nothing, depot obstruction
requires exposed detour roads, slopes/edges reject false routes). A read-only
reconstruction of the actual public decision70 observation detects disconnection
and finds an eight-command detour costing 1,226 at that instant. This is a plan,
not proof the dynamic opponent will leave that detour intact. The full native
match will test whether adaptive repair restores service and at what cost.

The repair pilot completed: 818 passengers, native operating profit +547,
financing-adjusted cash -12,391 versus the fixed controller's 0 / -2,725 /
-14,467. Eight road commands reconnected the route; full-run native costs and
service windows remain in the match trace. This is an adaptive scripted-control
improvement, not neural learning. Opponent behavior can still disrupt later
plans; no general shared-game reliability claim is made from this one match.

Next learning hypothesis: entropy regularization may be too weak to retain
useful stochastic CNN service as training continues. Register one seed20260923
CNN at entropy coefficient0.05 instead of0.01, keeping native reward, 128-action
training episodes, 128 updates / 16,384 transitions, deterministic CUDA and the
full eight-episode development evaluation. A development-only native CLI option
now exposes this existing PPO coefficient; loss/GAE/optimization code is unchanged.
Default launches omit the new flag and preserve older binaries. Checkpoints bind
the coefficient, exports restore it, and comparison reports reject confounded
entropy settings. Before the pilot, build separately, verify default CPU/CUDA
behavior against the original binary, reject invalid coefficients and run native
checkpoint/configuration checks. Existing balanced runs continue on the original
trainer. This is a one-seed exploration diagnostic, not a replacement for the
matched three-seed architecture results.

The separate `build/ppo-entropy` build passed native M08 tests and CPU/CUDA
checkpoint tests. `native-entropy-option-check-01` then verified all three
architectures on both devices: default actions, PPO metrics and exported model
identities are exact against the original binary; coefficient0.05 preserves
initialization, changes optimization, and has exact optimizer/RNG checkpoint
continuation. Five invalid native values are rejected. These are synthetic
numerical checks, not gameplay evidence. The registered CNN0.05 pilot and its
full development evaluation have now started. The original binaries remain
unchanged for the balanced-reward replications.

Balanced seed20260924 completed all eight development episodes with zero
deliveries and operating profit -4,834 each. Greedy makes 512 town selections;
sampled makes 426–438 selections plus WAIT and at most two construction actions.
Its final training entropy is 0.406, so this is not the near-zero-entropy CNN
failure in every detail. The uniform decision cost did not eliminate the learned
selection loop. Seed20260925 is still running; do not generalize seed23's useful
sampled result across seeds. The CNN recovery curves and per-seed development
bars are rendered and visually checked in Windows
`runs/2026-09-23/cnn-selected-checkpoint-comparison-01/figure-03/` (PNG/SVG).
Earlier figure drafts are superseded. All54 development tests and136 repository
fast tests passed after the entropy/repair changes, with `git diff --check` clean;
these software checks do not change the failed gameplay results.

A V2 recovery prerequisite is implemented but not yet verified natively. New
development CHECKPOINT/RESTORE requests save policy, Adam, three native RNG
streams, Torch CPU/CUDA RNG, recurrent state, mode and update counters only after
a complete update ending at an episode reset. The controller binds binary,
schema, reward, guide, collection source and training-map identities; a read-only
probe records the next reset's public observation and native/sampling tensor
hashes. Resume recreates and checks that reset before native restoration.
Mid-game recovery remains unsupported. Four focused Python rejection tests pass.
The next gate is a separate build, then sequential native full-versus-resumed
training comparisons on CPU and CUDA with no more than two active experiment
jobs. Neither these unit tests nor implementation alone establish exact recovery.

The balanced reward replication is complete: sampled passenger means across
seeds23/24/25 are 1,671.3 / 0 / 1,486.7; operating profit 4,716.7 / -4,834 /
4,609.2. Across18 episodes, passengers fall from the matched native objective's
1,959.4 to1,052.7, sustained service from17/18 to12/18, and cash losses improve
from-39,520.1 to-6,546.6. All six greedy episodes fail. The paired three-seed cash
improvement is32,973.6, conditional95% t interval[22,787.3,43,159.8]; passenger and
operating-profit differences have wide intervals crossing zero. This reduces
spending but does not establish a reliable overall improvement or beat one-bus
economics. Full results: balanced-three-seed-comparison-01, also copied to Windows
runs/2026-09-23. Final maps remain untouched.

The entropy0.05 CNN pilot also finished: all eight full development episodes
deliver zero, operating profit-4,834 each, versus the same failure at0.01.
Final entropy rises from0.01094 to0.05896 nats, but service still collapses.
cnn-entropy005-comparison-01 retains the failed one-seed intervention. Raising
entropy fivefold is not retained as a demonstrated learning fix. Next investigate
the credit assigned to construction and value learning before another sweep.

The V2 recovery build first failed because the finite-tensor helper's declaration
was not included. That failed build/log is retained; adding its existing header
produced trainer6693cf96121bf52deea3a84b4bb6c23a19ff830bec570f8c196e00cdfcfcce75.
Four native V2 policy/distribution gates pass on CPU/CUDA. Real uninterrupted
versus resumed comparisons are now running, not yet passed.

Register the remaining adaptive-road-repair controls before executing them:
map155097162/company1 and map1630856436/companies0 and1, firstcompany0,
512global decisions, same unassisted16-update neural opponent and CUDA inference.
Compare all four map/role cells with the already executed fixed one-bus control;
report failures and spending as well as deliveries. The first adaptive pilot
alone does not establish robustness across these cells.

Register a paired credit-assignment experiment on structured MLP seed20260924,
the failed balanced-reward seed: 64-action rollouts,64updates,4environments,
128-action native training episodes,16,384transitions, balanced-economic reward,
entropy0.01, deterministic CUDA, checkpoints every8updates. Compare GAE lambda0.95
with1.0 using the same new native build and ordinary full eight-episode development
matrix. The previous64-action trial used native reward and4,096transitions; it
failed greedy construction and remains negative evidence, not this matched control.
The test asks whether longer within-rollout credit reduces the dependence on an
initially inaccurate critic enough to recover efficient service. Native GAE/loss
math is unchanged; only its existing coefficient is exposed by a development flag.
Use service, operating/cash outcomes, failures and greedy reliability to judge it.
Optional scalar credit traces record the exact transformed reward, stored value,
next value and boundary flags sent to C++; logging does not compute training GAE.
Seven checkpoint-launch tests and the transformed-credit logging test pass.
Native default-equivalence, nondefault recovery and invalid-configuration checks
must pass before either real training run. This pair is a one-seed diagnostic.

V2 CPU recovery passed: v2-live-resume-cpu-01 compared8 uninterrupted updates
with4+4, requiring identical continuation actor/value/feedback and PPO metrics,
128 byte-identical native transitions, and final inference archive
0ccab66e9da482760e044558d8a4428f41912b45266801be3eefcb6c32219f38. This is
same-runtime reset-boundary recovery, not arbitrary game restoration. CUDA is
still executing. The repair controller's second map155097162 role finished with
899passengers and873operating profit; the two remaining map/role checks continue.

The first CUDA V2 recovery check failed exact metrics. Divergence already appears
at inference step13 in the independent prefix, before any checkpoint or update:
value0.690979183 versus0.690979123. All128 prefix actions and128 continuation
actions/native economic transitions remain exact, but weights/metrics are not.
Thus missing checkpoint state is not the only possible explanation. The V2 graph
uses scatter_add; deterministic cuDNN alone does not control that reduction.
[PyTorch2.9](https://docs.pytorch.org/docs/2.9/generated/torch.use_deterministic_algorithms.html)
documents deterministic CUDA scatter/gather alternatives and the cuBLAS workspace
requirement. The development trainer now requires strict deterministic algorithms
(unsupported operations throw) plus process-local CUBLAS_WORKSPACE_CONFIG=:4096:8.
Both settings enter native checkpoint identity and capability reporting.
The failed run and original6693cf96binary remain archived. New trainer
581168c6b65a8a2511fbc460e23fbd8379bf2efb781ac0fdb7341dad414fa892 is running
fresh CUDA full/prefix/resume checks, then the same check with public-plan guidance.
Do not label CUDA recovery exact until those checks pass.

The GAE option passed native M08 and CPU/CUDA checkpoint checks, and all six
architecture/device cases against the previous default binary. Default actions,
PPO metrics and final model IDs are exact; lambda1 preserves initial behavior,
changes optimization, and exactly resumes its optimizer/RNG state. Six invalid
values and mismatched checkpoint lambda are rejected. Trainer
449a4e73fdfc4e44594661876b19f3dd9d70569a40e5deae4831ab9328cc453e is retained in
build/ppo-credit. The registered lambda0.95/64-step control has started; lambda1
will follow when an experiment slot is available. Sixty development tests and136
fast repository tests passed before the added offline-credit reference check;
that focused check also passes, including terminal and truncated boundaries.
The balanced-reward three-seed PNG/SVG was rendered using analysis-venv and
visually checked under runs/2026-09-23/balanced-three-seed-comparison-01/figure-01.

All four adaptive repair cells completed and the eight-run paired report was
rederived from native traces in v2-mcp-repair-paired-comparison-01. Map1630856436
has identical deliveries/profit/cash for fixed and adaptive control in both roles
(1,457/5,418/-2,675 and1,359/4,815/-3,278). On map155097162, repair improves
company0 from0/-2,725/-14,467 to818/547/-12,391, and company1 from0/-2,723/-14,465
to899/873/-13,703. Extra construction costs are1,196 and2,834. All four adaptive
episodes have positive deliveries, operating profit and cash before capital in
each final window; all remain cash-negative over the full construction horizon.
No native failures, rejected submissions, MCP errors or bankruptcies occurred.
This is a supported scripted-baseline improvement on these fixed cases; the
neural opponent still delivered zero throughout. The Windows copy retains the
full paired comparison. Economic reporting now streams >1.5GiB request logs;
the streamed map155097162/company1 report exactly matches its saved native summary.

Strict-determinism CUDA V2 recovery passed in v2-live-resume-cuda-02: full8 versus
4+4 has identical prefix/continuation predictions, PPO metrics and128native
continuation transitions. Final inference archive is
575674a3962dda772de067dc0dd355d5079204bbb1ee6e81feb81a23610fd118. The native
continuation trace SHA ac08b57f25fffd21d93e1e8e033bd583d61955899ac4a083875821414042970b
also matches the prior CPU action/economic trace, though CPU/CUDA weights are
not claimed identical. This supports same-host reset recovery on the tested
devices, not arbitrary mid-game restoration. The separate public-plan-guided
CUDA roundtrip is now running. DEVELOPMENT includes runnable V2 save/resume
commands and the deterministic-runtime limitation. All61development tests pass
after the credit-audit reference fixture and streaming analysis changes.


## Credit and validation iteration before held-out confirmation

## Current iteration: delayed construction credit

Hypothesis: a longer rollout and GAE trace may retain useful credit for early
construction instead of relying heavily on an inaccurate critic before deliveries.
The random baseline first delivered at decisions 33–49, beyond the original
32-decision rollout. This is a hypothesis, not a demonstrated fix.

Both registered lambda runs and the lambda 0.95 replication on seed 20260923 are
complete. Seed 20260925 is executing. Collection is sequential within each job:

| Setting | Control | Intervention |
| --- | --- | --- |
| Run suffix | balanced-roll64-lambda095-64u-s20260924 | balanced-roll64-lambda1-64u-s20260924 |
| GAE lambda | 0.95 | 1.0 |
| Everything else | Structured MLP, balanced reward, CUDA, seed 20260924, entropy 0.01 | Same |
| Experience | 64 updates × 64 decisions × 4 environments = 16,384 transitions | Same |
| Native training horizon | 128 actions; checkpoints every 8 updates | Same |
| Evaluation | Two greedy and six sampled full development episodes | Same |

Training directories have prefix `live-cuda-`; evaluation directories `policy-`.
Judge deliveries, sustained service, operating/cash results, capital, invalid
actions and bankruptcy. This one-seed pair is a diagnostic; do not generalize it
across training seeds. The earlier native-reward 64-rollout/4,096-transition trial
failed greedy construction and remains negative evidence.

The new flag changes an existing C++ GAE coefficient, not the trusted GAE/PPO
implementation. Trainer SHA is
`449a4e73fdfc4e44594661876b19f3dd9d70569a40e5deae4831ab9328cc453e`
in `build/ppo-credit`. `native-gae-option-check-01` passed all three architectures
on CPU/CUDA: exact default actions, metrics and model IDs against the prior
binary; changed optimization with lambda 1; exact nondefault checkpoint recovery;
six invalid coefficients rejected. Native checkpoint tests reject changed lambda.

Optional scalar credit traces retain actual transformed rewards, old/next values,
behavior probabilities and boundary flags entering C++. `audit_credit.py` is
offline analysis only and cross-checks reconstructed targets against native
explained variance. Its terminal/truncation fixture matches the frozen Python
reference. The completed control audit reproduces native explained variance for
all 64 updates (maximum absolute difference 2.22e-16).

`balanced-roll64-control-comparison-01`: all eight control episodes sustain
service, with zero invalid actions or bankruptcies. Greedy means are 1,495
passengers, 4,754.5 operating profit and -2,294 cash; sampled means are 1,481.2,
4,630.2 and -2,418.3. This approaches the one-bus script (1,496 / 4,768.5 / -2,280),
without beating its economics. Each greedy episode builds one bus, then repeatedly
cycles town selections while service runs: purposeful fleet management is not
demonstrated. The original balanced 32-step seed delivered zero in all eight
episodes. Success in the control cannot establish a benefit from lambda 1.

Registered next experiment: repeat the **lambda 0.95 control** with training seeds
20260923 and 20260925, preserving every setting and full evaluation matrix in the
table. Use run suffixes `balanced-roll64-lambda095-64u-s20260923` and
`balanced-roll64-lambda095-64u-s20260925`. Compare all three independent seeds with
their original balanced 32-step counterparts at the same 16,384-transition budget;
report all seeds, including failures. Different rollout lengths also change update
frequency and minibatches per update, so attribute any result to this configuration,
not exclusively to longer temporal credit.

Next: finish both control replications with full evaluations and credit audits.
No held-out tuning. Keep at most two training/evaluation jobs
active and builds at two compiler jobs.

The lambda pair is now resolved in `balanced-roll64-lambda-comparison-01`.
Lambda 1 sustains all eight episodes with zero invalid actions/bankruptcies.
Greedy means: 1,496 passengers / 4,681 operating profit / -2,367.5 cash.
Sampled means: 1,633.7 / 5,059.7 / -7,730; five of six sampled episodes buy
additional buses. Relative to lambda 0.95, sampled passenger delivery increases
152.5 and operating profit 429.5, but cash worsens 5,311.7. This one-seed tradeoff
does not justify replacing lambda 0.95. Both offline credit audits match all
64 native explained-variance values within 2.22e-16.

`report_credit_experiment.py` verifies matched experience/PPO/reward/scenarios
before reporting paired seed differences. Cross-binary rollout comparisons require
the recorded exact-default verification chain; those finite checks are supporting
evidence, not a universal equivalence proof. Three focused comparison tests pass.
`balanced-roll64-control-matched-comparison-03` is the checked single-seed rollout
report; draft 02 included unrelated historical neural baselines and is superseded.
Windows `credit-diagnostics/figure-01/` contains the reviewed PNG/SVG explaining
GAE on the first recorded control rollout. Its lambda 1 curve is an offline
counterfactual on unchanged data/critic values, not new training evidence.

Registered follow-up verification when a slot is free: real CUDA reset recovery
for the 64-step balanced configuration at seed 20260926, lambda 0.95, entropy
0.01, horizon 128 and scalar credit logging. Compare four uninterrupted updates
against two plus two restored (1,024 total transitions, 512 continuation
transitions), including exact native traces, all PPO metrics, scalar inputs and
final model identity. `verify_live_resume.py` now accepts these settings and
defaults to sequential execution; its original 32-step mode remains available.
`live-resume-balanced-roll64-cuda-01` passes: exact PPO metrics, scalar inputs,
512 native continuation transitions and final model
`e51b6b9b88bed604a5f1a804dfb147c80979763dc8872aa456359ee4d454121e`.

Independent performance prerequisite: the earlier two-update cProfile attributed
14.9 of 34.6 collector seconds to repeatedly validating 32,768 spatial values.
That instrumentation exaggerates Python-call overhead, so it is a bottleneck
lead, not a speedup prediction. New opt-in `--spatial-validation vectorized`
validates decoded JSON numerics with NumPy and returns the original list; no
observations, masks, PPO math or defaults change. Boundary/type/shape and scoped
restoration tests pass, as do seven existing checkpoint adapter tests. Checkpoint
identity binds mode, NumPy version and the validator source. Existing archived
runs require their archived collection code for restoration.

Registered performance check, **after both learning jobs finish**: run three
alternating reference/vectorized pairs, four updates each, with identical
`ppo-credit/m08_trainer`, CUDA, MLP, native reward and seeds 20260927–29. Require
byte-identical native traces, exact PPO metrics and final model IDs before timing
is accepted. Adoption requires median end-to-end speedup above 1.05 and every
pair above 1.0; otherwise keep the reference default. Run in isolation. The
existing `compare_training_backends.py` now supports this stricter input check.

Seed 20260923 replication is complete: all eight episodes sustain service, zero
invalid actions/bankruptcies; greedy means 1,475 passengers / 4,603.5 operating
profit / -2,445 cash, sampled means 1,518 / 4,835.3 / -3,033.3. Mean sampled
capital is 7,143.7 (one episode buys an additional bus). All 64 native credit
diagnostics match within 2.22e-16. Both completed lambda 0.95 training seeds now
pass all eight development episodes each; wait for the third before concluding
the registered three-seed comparison. The focused input/reward/credit/checkpoint/
comparison test set passes 23 tests.

Seed 20260925 evaluation is still running. Both greedy episodes fail with zero
deliveries. On development map 05, actions are road / select towns / two stops /
508 WAITs; the legal depot initially has probability 0.3309 versus WAIT 0.5880,
and remains below WAIT through the episode. All four depot orientations occur
in training, so this is not an unseen-action case. Completed sampled episodes
do establish service; their complete matrix and economics remain pending. Do not
claim the configuration fixes greedy reliability across all three seeds.

## Active-log snapshot after 2026-09-24 snapshot-reuse timing

Preserved active-log text SHA256: f58ab9315382b3d01a41e574b66b3817cffe318b1262ab1058177a65476a98d7

# Live OpenTTD development progress

Active objective: reliable, economically useful neural play, followed by broader
live V2 gameplay and reproducible MCP competition. **The overall goal is not
complete.** The preregistered V1 held-out confirmation passed; its results cannot
drive tuning. V2 longer rollouts improve sampled outcomes modestly, but still
fail greedy service; broader training-map coverage did not help at the matched
budget. Episode-length return settings are now undergoing qualification. Frozen release
contracts remain untouched.

Use [DEVELOPMENT.md](DEVELOPMENT.md) for commands. The complete earlier log,
including registered hypotheses, failures and binary identities, is preserved in
[PROGRESS_HISTORY_2026-09-23.md](PROGRESS_HISTORY_2026-09-23.md). Run names below are
under `~/.local/share/openttd-rl/runs/` in Ubuntu-24.04. Selected readable reports
and figures are copied to the checkout's ignored `runs/2026-09-23/` and
`runs/2026-09-24/` directories.

## Completed V1 learning and frozen held-out confirmation

The 64-step balanced-reward experiment is complete across training seeds
20260923/24/25. Each used the structured MLP, CUDA, 64 updates × 64 decisions ×
4 environments = 16,384 transitions, horizon 128, entropy 0.01, lambda 0.95,
reference spatial validation and checkpoints every eight updates. All comparisons
below are full 512-action development episodes; no model was selected by final data.

| Configuration | Sampled passengers | Operating profit | Cash after capital | Sustained sampled | Sustained greedy |
| --- | ---: | ---: | ---: | ---: | ---: |
| Balanced, 32-step rollout | 1,052.7 | 1,497.3 | -6,546.6 | 12/18 | 0/6 |
| Balanced, 64-step rollout | 1,513.7 | 4,670.3 | -3,745.1 | 18/18 | 4/6 |
| One-bus script | 1,496.0 | 4,768.5 | -2,280.0 | 2/2 | n/a |

balanced-roll64-three-seed-comparison-01 verifies matching experience, PPO/reward,
engine and evaluation matrices. All learned episodes have zero invalid actions
and bankruptcies. Sampled operating-profit means are 4,835.3 / 4,630.2 / 4,545.5;
cash means are -3,033.3 / -2,418.3 / -5,783.7. Paired rollout improvements have
wide three-seed 95% t intervals crossing zero: operating profit +3,173.1
[-10,363.1, 16,709.2], cash +2,801.4 [-9,722.3, 15,325.2]. These are conditional
development results, not a broad superiority claim. Rollout length also changes
update frequency and within-update normalization.

Seed 20260925 greedy play builds a road and two stops, then waits instead of
building its legal depot: initial WAIT probability 0.5880 versus depot 0.3309.
All four depot orientations occur in training. The two other greedy seeds build
one bus; seed 23 then waits, while seed 24 cycles town selections. Sampled play
is the supported primary operating mode; reliable greedy construction is unresolved.

The one-seed lambda 1 trial sustains all eight episodes, but increases sampled
cash loss to -7,730 while raising passengers/profit to 1,633.7 / 5,059.7.
balanced-roll64-lambda-comparison-01 retains that tradeoff. Lambda 0.95 remains
the chosen configuration. All four completed 64-update credit audits reproduce
native explained variance within 2.22e-16. Windows credit-diagnostics/ includes
reports and the reviewed offline GAE explanation in figure-01/.
The reviewed paired-seed figure and its reproducible plotting script are in
credit-diagnostics/balanced-roll64-three-seed-comparison-01/figure-01/ (script in
the parent directory). It shows the gain is mainly recovery of seed 24, while
seed 25 spends more; it does not hide those counterexamples.

The three model identities and a 36-episode final-case protocol are now frozen in
heldout-balanced-roll64-registration-01/registration.json, SHA
1cd892bff813befd0f49f0f2f2d408e7116a28f3925a11e1b57c5306c80d340a.
heldout-balanced-roll64-confirmation-01 failed before executing any episode:
the reserved instances were absent from the six-scenario development setup.
The unchanged frozen generator created only the two registered final
instances, with provenance in heldout-balanced-roll64-instance-generation-01;
confirmation-02 then failed before any episode because the legacy M09 override
only accepts horizons 64/128/256. A setup-only amendment uses the ordinary native
512-action reset and asserts cash/tick budgets; no frozen release code or gate
was changed. Registration-02 preserves all models, protocol and criteria, links
both zero-episode failures and original registration, and has SHA
872a46c8e91d9d8c4a89c0481730017a40a7d9e3f5f8f5ef8711396556874357.
confirmation-03 completed all 36 full native episodes. Primary sampled
play was required to sustain at least five of six episodes for each trained model, have
positive mean operating profit, exceed seeded random on operating profit and
cash, exceed the original script on cash, and have zero invalid actions and
bankruptcies. All greedy and one-bus results are reported without a superiority
requirement. Budgets are 512 actions × 128 ticks, starting cash 100,000, maps 07/08
and sampling seeds 20260923/24/25. Final results cannot drive tuning. Seed 24 is
also fixed for visible demonstration using development cash before final results.
The dedicated runner checks registered code/binary/model identities before final
scenario access; ordinary evaluation refuses reserved files. Three boundary and
acceptance-matrix tests pass. All seven registered acceptance checks passed.

| Held-out controller | Episodes | Passengers | Operating profit | Cash after capital | Sustained service |
| --- | ---: | ---: | ---: | ---: | ---: |
| WAIT | 2 | 0 | -4,834 | -5,559 | 0/2 |
| Seeded random | 6 | 1,733.3 | -133 | -41,724 | 1/6 |
| Original script | 2 | 1,823 | 5,098 | -36,493 | 2/2 |
| One-bus script | 2 | 1,855.5 | 5,279 | -1,865 | 2/2 |
| Neural greedy | 6 | 1,237.3 | 1,910 | -3,448.7 | 4/6 |
| Neural sampled | 18 | 2,017.4 | 6,022.6 | -2,488.3 | 18/18 |

All 36 episodes have zero invalid actions and bankruptcies. Each sampled model
sustains 6/6 episodes. Conditional three-training-seed 95% t intervals are
passengers [1,529.0, 2,505.8], operating profit [3,762.2, 8,283.0] and cash
[-4,472.4, -504.3]. The 18 sampled episodes are not 18 independent trained
models. The one-bus control preserves more cash; greedy seed 25 still fails both
maps. This confirms useful sampled play on two reserved V1 maps, not broad
OpenTTD competence or cash profitability after construction. The full readable
table, reviewed PNG/SVG, plotting script and immutable result copies are in
Windows credit-diagnostics/heldout-balanced-roll64-confirmation-03/.

## Supported input-validation improvement

spatial-validation-live-comparison-01 passes three alternating, isolated pairs
with the same CUDA trainer: all 1,536 paired native transitions, every PPO metric
and all final model IDs are exact. End-to-end speedups are 1.228x / 1.147x / 1.144x
(median 1.147x), meeting the preregistered adoption criterion. The new development
CLI default is vectorized spatial validation; explicit reference mode reproduces
the learning experiment above. NumPy only checks decoded JSON numerics and returns
the original list. Native inputs/PPO/CUDA math remain unchanged. Checkpoints bind
mode, NumPy version and validator source; archived runs need their archived code.
The non-isolated synthetic microcheck (4.09 ms → 1.11 ms) is only supporting data.

live-resume-balanced-roll64-cuda-01 passes exact four-versus-two-plus-two CUDA
recovery: all PPO metrics, scalar training inputs, 512 native continuation
transitions and final model e51b6b9b88bed604a5f1a804dfb147c80979763dc8872aa456359ee4d454121e.
The same registered reset check with vectorized validation at seed 20260926 in
live-resume-balanced-roll64-vectorized-cuda-01 passes with the same final model
ID, all scalar inputs/metrics and the same 512 native continuation transitions
as reference mode.
The focused input/reward/credit/checkpoint/comparison suite passes 23 tests.
Keep at most two training/evaluation jobs and two compiler jobs active.

demo-balanced-roll64-s20260924-01 completed for the development-selected model
0ccefa9c60c198c661240720bb04771f0c3853751d1cd53d1c83dc55302d9c49.
Repeated export is byte-identical; 128 recorded inputs pass numerical checks.
ONNX package fa5f64fc95cebf3ebd71e20eb8f9402078f7875de05407c8f97446d79bbe077f
matches all 4,096 full native replay actions, masks and economic transitions
(max logit error 3.815e-6). Both 512-action visible sampled playbacks match the
headless actions and counters exactly; both 1280x800 screenshots were inspected
and show bus service and readable economic/agent panels. GUI counters are after
the command, before the final advance; the comparison handles that boundary.
Windows reproducible-playback/balanced-roll64-s20260924-01/ contains reports and
images. Selection predates final results; user saves/configuration are untouched.

## Learning evidence and limitations

All figures below use full 512-action development episodes. Sustained service
means deliveries and positive native operating profit in each final 128-action
window. Action-sampling repetitions are not independent training seeds.

| Policy / study | Sampled mean passengers | Native operating profit | Cash after capital | Sustained episodes |
| --- | ---: | ---: | ---: | ---: |
| Seeded random | 1,129.5 | -2,075.3 | -43,570.8 | 1/6 |
| One-bus script | 1,496.0 | 4,768.5 | -2,280.0 | 2/2 |
| Native-reward MLP, three seeds, 128 updates | 1,959.4 | 1,975.4 | -39,520.1 | 17/18 |
| Combined CNN+MLP, same budget/seeds | 1,964.7 | 2,768.6 | -38,726.9 | 16/18 |
| Balanced-reward MLP, same budget/seeds | 1,052.7 | 1,497.3 | -6,546.6 | 12/18 |

- `architecture-comparison-all-three-01`: nine models, 72 episodes. Native MLP
  and combined greedy service succeeds in 4/6 episodes each; final CNN policies
  fail in all episodes. Combined-minus-MLP sampled profit has a wide paired
  three-seed 95% t interval crossing zero. No architecture superiority claim.
- `balanced-three-seed-comparison-01`: all six balanced greedy episodes fail.
  Sampled passenger means by training seed are 1,671.3 / 0 / 1,486.7. Paired cash
  improvement over native reward is 32,973.6, conditional 95% t interval
  [22,787.3, 43,159.8]. Spending improves while reliability worsens. The plotted
  three-seed tradeoff is in its Windows `figure-01/` directory.
- `cnn-selected-checkpoint-comparison-01`: training-only earlier-checkpoint
  selection recovers 1,457.1 sampled passengers and 1,147.6 operating profit,
  sustained in 10/18 episodes; greedy still fails. Full training budgets count.
  This posthoc recovery diagnostic does not fix collapse or spending. Windows
  `figure-03/` is the reviewed PNG/SVG; earlier figure drafts are superseded.
- `cnn-entropy005-comparison-01`: increasing entropy weight fivefold still gives
  zero passengers in all eight episodes. It is not retained as a successful fix.
- Native reward overvalues fleet purchases relative to economic efficiency.
  Stronger economics, uniform decision cost, progress potential and larger
  budgets have mixed or failed results; the history retains them all. Rising
  shaped reward alone is never evidence of playing competence.

The learned V1 policies improve service over random but do not reliably combine
greedy construction, passenger throughput and the one-bus control's economics.

## Reproduction, export and CUDA

- V1 reset recovery passed real CPU/CUDA eight-versus-four-plus-four comparisons:
  exact continuation metrics, 512 native continuation transitions and model ID.
  Native tests also cover all three architectures on both devices.
- `export-32u-s20260924-01` and `onnx-full-replay-comparison-01`: repeated export
  is byte-identical; native/ONNX agree on 4,096 full replay transitions. The model
  ran visibly in isolated OpenTTD on both development maps. User saves/configs
  were preserved. See Windows `reproducible-playback/` and the history for hashes.
- [CUDA_EXPERIMENT.md](CUDA_EXPERIMENT.md): 6,984-row custom masked-policy kernel
  checks pass. Its small operation improves 9.62× over Torch CUDA but full training
  improves only 1.00470×. No meaningful end-to-end GPU speedup claim. Fast bridge
  validation improves collection about 3.7× with exact full native traces.
  WSL Compute Sanitizer/Nsight prerequisites failed and are not counted as passes.
- Current software checks: 61 development tests and 136 fast repository tests
  passed, plus the new focused guided-comparison path test; `git diff --check`
  passes. GAE changes passed native M08 and CPU/CUDA checkpoint tests.

## Live V2 recovery and learning

Completed experiment: v2-guided-budget-02 tests the hypothesis that increasing
experience from 512 to 2,048 decisions improves construction timing under the
unchanged public planner. It trains 16 updates, then restores that reset checkpoint
for 48 more, using strict CUDA trainer 581168c6..., seed 20260923, 128-decision
training episodes, the same four training maps, reward, 32-step rollouts and
eight-step recurrent sequences. Each checkpoint gets full greedy and sampled
episodes on development maps 1630856436/155097162; fresh uniform/scripted guide
controls use those same maps and seed. Before results, replication requires both
greedy episodes to sustain service, sampled profit/cash at least uniform, sampled
service/profit/cash at least the earlier checkpoint, and no invalid/bankrupt cases.
This is one-seed development diagnosis, not learned geometry or held-out evidence.
The experiment-01 setup failed before training because the checkpoint-only build
directory lacked an inference executable. It is preserved; experiment-02 uses the
existing qualified inference executable. No algorithm change was made.
Both training stages completed; the 64-update inference weights are
5996f7e5c4fd08e46788efac51472c4fc1ac9b2cf8b18fae085d17dc74ca94a3.
All 12 full development evaluations completed with no invalid actions or
bankruptcy. The registered advance-to-replication criterion fails:

| Controller | Mean passengers | Mean operating profit | Mean cash after capital | Sustained service |
| --- | ---: | ---: | ---: | ---: |
| 16-update greedy | 0 | -4,834 | -5,559 | 0/2 |
| 16-update sampled | 1,152 | 3,514.5 | -6,403 | 2/2 |
| 64-update greedy | 0 | -4,834 | -9,440.5 | 0/2 |
| 64-update sampled | 1,171.5 | 3,179 | -6,738.5 | 2/2 |
| Uniform + same guide | 1,182.5 | 3,629 | -6,288.5 | 2/2 |
| Scripted + same guide | 1,238 | 3,514.5 | -6,403 | 2/2 |

More experience alone did not improve economic control. Greedy builds incomplete
infrastructure; sampled service persists but profit/cash regress. No replication
or learning-advantage claim is justified. budget-comparison-01 and the Windows
v2-guided-budget-01/completed copy preserve all seven registered checks.
recorded-credit-audit-01 matches
all 64 native explained-variance values within 4.62e-10 after native float32 input
and return conversion. Across the first versus last four training episodes,
multi-choice WAIT counts rise 66→141; chosen depot probability falls 0.395→0.140
and route probability 0.455→0.083. Training-map deliveries do not consistently
improve. This is recorded credit/behavior evidence, not a causal diagnosis or
permission to replace the preregistered full comparisons.

Recorded continuation timing attributes 337.1/1,027.4 seconds to native PPO
update requests, 78.7 to actor requests and 294.8 to game requests (103.5 OBSERVE,
130.4 TENSORS, 59.3 ACT, 1.55 STEP). The remaining 316.8 seconds include bootstrap
inference, processing, compression, startup/reset probes and orchestration.
These are concurrent-run counters, not an isolated CPU/GPU benchmark; they do
not justify accelerating game simulation or claim a new CUDA speedup. The
recorded-credit-audit-01/timing.json retains operation counts and request hashes.

The completed v2-snapshot-cache-probe-01 passes all 512 paired native transitions,
public observations, native/sampling tensor bytes, guide states and choices
exactly. Four counterbalanced pairs cover two training maps and two sampling
seeds, 128 decisions each, using a uniform public-guide script and no optimizer.
Reusing a validated bootstrap frame at the same native token reduces TENSORS
requests from 256 to 129 per case. The median observed reference/reuse time
ratio is 1.179; these exploratory timings include startup/close, exclude archival
and ran concurrently with CUDA training. This is not an isolated benchmark or
full-training speedup. Adoption requires native PPO/model/checkpoint equivalence
and isolated end-to-end timing, recorded below.
Windows runs/2026-09-24/v2-snapshot-cache-01/completed retains the readable report.

An isolated current-source worktree at
/home/imsa/.local/share/openttd-rl/worktrees/v2-snapshot-reuse-01 now implements
an opt-in --reuse-bootstrap-tensors collector mode. It caches only a validated
continuing frame at the same native token/company, clears on reset, preserves
guide preview/commit semantics, and binds the option into checkpoint compatibility.
Six focused checkpoint tests pass there.
v2-bootstrap-reuse-training-checks-01 passes full native
qualification: default CUDA matches all 128 recorded decisions, two PPO updates
and model 8fd939e1... exactly. Enabled CUDA also matches every actor/mask/value,
feedback/native transition, update and model, reducing TENSORS from 256 to 129.
CPU reuse matches all 64 transitions and its update across three time-limit
bootstraps/four recurrent resets, reducing requests 128 to 68. Cached CUDA reset
recovery passes exact 128-transition continuation and model 0fb2b27b... .
The default/cached logical checkpoint states match exactly across all 66 model
tensors, 66 Adam states and every RNG/hidden/counter field (digest 18dbd51c1f8f08f22f53ad36deaaba2c6577edd3c8bbff677f01548d7434d497).
Cached CPU versus the preserved CUDA reference matches all 64 native transitions,
max update error 1.489e-5 within the existing 1e-4 limit. All 22 focused V2 tests
pass in the isolated checkout. These concurrent timings cannot establish an
isolated performance gain. Windows
runs/2026-09-24/v2-snapshot-cache-01/training-checks contains the proof summary.
The prepared sequential benchmark requires three counterbalanced 256-decision
pairs, exact native/PPO/model equality, median outer wall ratio above 1.05 and
every pair above 1.0. After the map-coverage evaluations completed, the three
qualified collector files were staged in the main checkout for this timing run;
their original bytes and source identities are retained in
v2-cache-timing-integration-01. Default reuse remains off.

v2-bootstrap-reuse-end-to-end-01 completes all three counterbalanced pairs.
Reference/reuse outer times are 185.412/170.811, 180.235/169.764 and
177.080/172.880 seconds. Every pair improves; median ratio 1.06168 exceeds the
registered 1.05 threshold (5.81% less wall time). All 768 paired decisions,
masks, actor/feedback/native records, twelve PPO updates and final model hashes
match exactly. Each 256-decision run reduces TENSORS requests 512 to 258.
The timer includes process startup, source/config capture, collection, PPO,
tensor archival, validated model save and close. No other project native job
ran during these six sequential cases; desktop background activity is uncontrolled.
Keep the optional collector mode. This is a local end-to-end optimization with
the unchanged CUDA trainer, not a CUDA kernel gain. Registration:
76e704e9ffbc1ad01fe979250c7241158898275f5dccbf1575fe4979cce19420.
Windows v2-snapshot-cache-01/end-to-end-completed contains the readable result.
The separate timing-breakdown.json shows native TENSORS round-trip time remains
about 21 seconds in both modes despite halving the request count. The unmeasured
collector remainder falls from 51.8–54.7 to 46.3–47.0 seconds, while actor/PPO
timing also varies. Redundant Python checking is removed by the implementation,
but these coarse timers do not attribute the entire end-to-end gain to one stage.

Live mail now works in the separate v2-live-mail-engine-01. The opt-in cargo schema
adds truck-stop and mail-purchase candidates plus public mail acceptance/supply
and delivery counts; ordinary bus mode remains available. It rejects old neural
TENSORS in cargo mode. No M16 fixture cargo/acceptance injection is used.
live-mail-validation-01 (engine ad603af1...) passes exact 512-transition bus
equivalence, shared-company scope/scheduler checks, and read-only, stale/illegal,
company and duplicate-action rejection. Its training-map script delivers 959 mail,
profit 5,307 and cash -2,268. Full development results are:

| Map | Mail delivered | Operating profit | Capital | Cash after capital | Final-window service |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1630856436 | 777 | 3,865 | 7,163 | -4,023 | 3/3 |
| 155097162 | 671 | 1,542 | 10,812 | -9,995 | 3/3 |

Both have zero invalid actions/bankruptcy. WAIT loses 5,559 on each map, so the
larger mail construction remains worse on cumulative cash despite positive final
service. These are scripted transport results, not learned mail control.

Coordinated passenger/mail run 01 failed one map and destroyed passenger service
on the other: a legal road command could clear an existing bus stop. Run 02
protects stations/depots and recovers both services on map 155097162 (1,054
passengers, 431 mail, profit 3,419, capital 18,733, cash -16,039), but fails the
other map because a joined truck stop's tile differs from its station anchor.
live-mail-comparison-01/02 preserve all outcomes, including the zero-passenger
and failed cases. This is a public-observation/planner limitation, not a hidden
command or cargo injection issue.

The facility-aware engine 82e75d33d26e062b7edfa9b2a685fad03a36fd3b44af86bf90176ffdaa39ede0
now exposes each own station's bus/truck stop tiles. Coordinated run 03 protects
all facilities and resolves joined stops to their native station IDs. Run 03
passes both fixed development maps: 1,488/1,054 passengers, 745/431 mail, combined
profit 8,749/3,419, capital 15,387/18,733 and cash -7,363/-16,039. Each final-three
window has both deliveries and positive operating profit; neither run has invalid
actions or bankruptcy. live-mail-facility-validation-02 passes all five exact
512-transition comparisons (bus and four standalone mail/WAIT episodes) plus
shared scope/scheduler checks. live-mail-comparison-03 compares all six final
cargo-engine cases, including WAIT, standalone mail and coordinated services.
Both earlier engine revisions are preserved. Four focused tests pass for identity,
cash accounting, infrastructure preservation and joined-stop resolution. Learned
mail control, shared mail and broad reliability remain open.

The 64-update greedy evaluation on its first map builds eight road segments and
two stops, then takes 502 WAITs: zero passengers and cash -7,616.
The recorded construction-delay audit finds delivery in the same 32-step rollout
as 1/64 road, 3/32 stop, 5/16 depot and 5/16 purchase actions. Bootstrap credit
still exists, so this is a timing observation rather than proof of causation.
The next bounded hypothesis is a 64-step rollout at the same 2,048-decision
budget. The separate v2-live-rollout build adds only a bounded 32/64 rollout option;
default remains 32. The trusted PPO/GAE and eight-step recurrent sequences remain
unchanged. A compiler sign-conversion failure is preserved in build-v2-rollout-01;
explicit conversions pass build-v2-rollout-02. Six native CPU/CUDA/reference gates
and 23 focused Python tests pass, as do all 136 portable repository tests.
Default CPU and CUDA runs reproduce their preserved 128 transitions, all four
PPO updates and final model archives exactly. The 64-decision CPU/CUDA check
crosses three real time limits with four recurrent resets, matches all native
transitions, and has maximum metric error 1.489e-5 against the existing 1e-4
tolerance. The 64-step CPU reset comparison passes exact continuation, including
all 128 transitions, update metrics and model b4f6fc70fc4528ace33be543763fdb96c4a3de9efade0068ce944e93d9847dff.
CUDA reset recovery also passes exactly: final model
0fb2b27b6f42dd6a6411d41e984b024d08be538650490d8f0652d32ecc3553a2.
CPU and CUDA continuation traces both hash to b518d9b8f6fa721534dba94a8125d65b9fb75136122a156981507720cd9e2537;
weights differ between devices. All 12 native rejection cases pass, including
wrong rollout length, premature update and overfilled rollout. Existing checkpoint
destinations and source archives remain unchanged.
The candidate trainer is
a4cd6807188334b6be989a9ae60e16dc036e6449589c88da903d2778c856c4ce.
Longer rollouts also change update timing and advantage-normalization grouping.

v2-guided-roll64-32u-01 completed with registration
27e49ab06aeddc6e1a4826eeee076e26faf0be2aa317effae84d1ecdaf16adc8.
It holds seed 20260923, guide/reward/maps, horizon 128, eight-step sequences and
four epochs constant: 32 updates × 64 decisions = the same 2,048 transitions as
the completed control. Before outcomes, replication requires both greedy maps
to sustain service, sampled service/profit/cash at least the fixed-32 control,
sampled profit/cash at least uniform, and zero invalid/bankrupt cases. The
planner/native-boundary source hashes match the control. No held-out maps are
used. Training completed with model
28aeb6d26c0fb66f1931a51b7a005175872ed69cad98afce608018b9988a936a;
all four full native evaluations completed with zero invalid actions/bankruptcy.
The registered advance-to-replication result is FAIL: greedy still sustains 0/2.

| Controller | Passengers | Operating profit | Cash after capital | Sustained |
| --- | ---: | ---: | ---: | ---: |
| Fixed-32, greedy | 0 | -4,834 | -9,440.5 | 0/2 |
| Fixed-32, sampled | 1,171.5 | 3,179 | -6,738.5 | 2/2 |
| Roll64, greedy | 0 | -967 | -5,573.5 | 0/2 |
| Roll64, sampled | 1,228 | 3,833 | -6,084.5 | 2/2 |
| Uniform, same guide | 1,182.5 | 3,629 | -6,288.5 | 2/2 |
| Scripted, same guide | 1,238 | 3,514.5 | -6,403 | 2/2 |

Sampled roll64 clears the registered control/uniform comparisons, but its small
advantage is one training seed and one sampling seed on two fixed development
maps. Greedy repays 80,000 of debt on each map, then waits at the exposed legal
depot proposal 494/480 times. Initial WAIT probabilities are 0.5694/0.5663,
averaging 0.5376/0.5375 during those stalls. Repayment reduces interest losses;
zero bus purchases still means zero passenger service. This does not pass the
criteria for replication. Windows runs/2026-09-24/v2-rollout-01/completed contains
the comparison, native checks, stall audit and model identity.

Its offline credit audit
reproduces all 32 native explained-variance values within 4.983e-10. Delivery
occurs in the same rollout as 39/64 road, 20/32 stop, 10/16 depot and 10/16 bus
purchase actions, compared with 1/64, 3/32, 5/16 and 5/16 in the fixed-32 control.
These are descriptive training results, not a causal attribution of the modest
sampled improvement. Longer rollouts also alter update cadence and normalization.

The unchanged guide needs only 4/3/5/4 road commands on the four current training
maps, versus 8/22 on the two development maps. v2-training-coverage-01 completes
the unchanged scripted guide on all 16 training-ledger seeds at the current
128-action training horizon. All 16 establish a running bus and deliver
passengers, without invalid actions/bankruptcy. First delivery ranges from
action 24 to 58. The additional twelve maps require 0–15 road actions; the
original four already cover every depot orientation. Fourteen maps have positive
initial operating profit, but all have negative cash after capital. This is a
training-distribution and initial-service diagnostic; it cannot certify full-episode
sustained profit or neural competence. No final maps are used. The readable table,
data and PNG/SVG chart are in runs/2026-09-24/v2-training-coverage-01/completed.
The collector now accepts an explicit --training-map-count, retaining default 4
and selecting only the training-ledger prefix. Existing checkpoint compatibility
already binds the complete ordered seed list. Six focused checkpoint tests pass,
including rejection of changed coverage/order before native restore.
v2-training-map-count-checks-01 passes unchanged default CUDA behavior: 128 native
transitions, all actor/feedback/guide records, PPO metrics and model
8fd939e10aa88dcd5a1fa55b26810726773c1e3d4eb41af44ae2e4eda90bed00 match exactly.
With all 16 maps configured, reset recovery also passes exact 128-transition
continuation, all metrics and final model
0fb2b27b6f42dd6a6411d41e984b024d08be538650490d8f0652d32ecc3553a2.
That recovery check executes only the first two maps; the separate script above
exercises all sixteen. Counts 0/17 fail before creating an output directory.
All 22 focused V2 and 136 portable repository tests pass; git diff --check passes.

v2-guided-sixteen-maps-32u-01 was registered under
25b816645b36b888142456622013ee13d73ffc1f2cc2dc6633aa93a105970dcd.
The single change is sixteen training maps visited once instead of four visited
four times, at the same 2,048 decisions. Seed 20260923, 64-step rollouts, horizon
128, four epochs, eight-step sequences, reward, guide and native trainer remain
fixed. The first 512 actions, actor/feedback/guide records, eight updates and
native checkpoint bytes were required to match the control before the first new map.
Replication requires greedy service on both full development episodes and sampled
service/profit/cash at least the four-map roll64 and uniform controls, with zero
invalid actions/bankruptcy. The early audit passes every prefix actor/feedback,
native transition and update, but fails checkpoint container-byte equality.
The run was stopped and retained as failed after 844 decisions, without a
development evaluation. LibTorch's installed optim/serialize.h writes TensorImpl
pointer addresses as Adam-state keys and iterates an unordered state map. The
archive audit finds differing pointer IDs/order; container hashes are not a
cross-process identity for the logical optimizer state.

v2-training-map-prefix-state-comparison-01 verifies exact logical state using the
same parameter-group order as native restore: all 66 named weight tensors, 66
Adam moment pairs and steps, optimizer options, identity, native/Torch RNG,
hidden state and counters agree byte-for-byte. Semantic digest:
2479a3dc21f889ab415a442a2d03ebf621bea9677afd0a033cfad39dcd42f946.
No legacy hash or native checkpoint acceptance rule changes.
v2-guided-sixteen-maps-32u-02 completed with setup-amended registration
1a7fc505e9c349078bdd9dc9cb3dd11382b70f812118b54214c2781004edb34d.
It resumes the verified update-8 checkpoint and collects 24 further updates,
retaining the same 2,048 model-training decisions and unchanged gameplay criteria.
The failed trial's 332 additional decisions are unused diagnostic overhead.
All four full development evaluations completed; the registered advance criterion
fails. Greedy delivers zero on both maps (mean operating profit -484, cash after
capital -1,209), making nine loan repayments then waiting without construction.
Sampled sustains service on both maps, averaging 1,161 passengers, operating
profit 3,562 and cash after capital -6,355.5. This is below both the four-map
roll64 model (1,228 / 3,833 / -6,084.5) and uniform guide (1,182.5 / 3,629 /
-6,288.5). All four cases have zero invalid actions and bankruptcy. Model:
3227f3c57600e11b82ad164072d80d0e218e70cdffa9d4153c85fe8e8f182904.
The Windows learning-completed report retains the registration, exact prefix
proof and outcome table. No replication is warranted for this configuration.

The recorded-credit-audit-01 reproduces all 32 native explained-variance values
(maximum error 4.96e-10). Only 35 of 116 road actions share a 64-step rollout
with later delivery, versus 101 that precede delivery within the episode; the
median lag is 59 decisions. At gamma .99 and lambda .95, the direct GAE weight
at that lag is about .027. Offline lambda=1 sensitivity within the same windows
improves buy/route/start advantages but worsens roads. This is not trained-policy
evidence. A return window covering the full construction episode is the next
learning hypothesis; the native PPO algorithm and reward remain unchanged so far.

The next bounded implementation adds optional rollout 128 and GAE lambda in
[0,1], keeping defaults 32/.95, eight-step recurrent gradients and four epochs.
Configuration is checked against native TRAINING_INFO and bound into reset
checkpoint compatibility. Original source bytes are retained in
v2-full-return-source-change-01. Qualification v2-full-return-checks-01 failed
before compilation because the new launcher omitted the explicit nvcc path
used by local.py; CMake could not detect its default CUDA architecture. Its
failed configuration log and build directory are retained. The launcher now
uses /usr/local/cuda-12.6/bin/nvcc in a fresh build, and
v2-full-return-checks-02 is running:
new build, trusted native gates, preserved 32/64 behavior, 128/lambda1 CPU/CUDA
time-limit agreement, scalar return audit, exact CPU/CUDA reset continuation and
native rejection boundaries. All 26 focused V2 unit tests pass.
The prepared learning experiment compares 128/.95 and 128/1 at 2,048 decisions
over all 16 training maps. No experiment has launched yet. Both arms must pass
full greedy/sample development service and the previous best/uniform economic
controls before replication; no held-out data informs this change.

The completed v2-roll64-greedy-training-fit-01 fails initial service on all four
familiar training maps. Every case repays 80,000, builds roads/two stops, then
waits without a depot/bus: zero passengers, operating profit -233, zero invalid
actions/bankruptcy. Thus unseen map geometry alone cannot explain the stall.

v2-forced-action-update-audit-01 replays recorded steps 1,537–2,048 from native
checkpoint 24: all 512 predictions/feedback and eight updates match exactly,
and the final archive is the original 28aeb6d2... model. Inference copies at
updates 30/31/32 probe the same four recorded histories through their first legal
depot proposal. The extra exact inference assertion fails on tiny GPU differences;
that failure is preserved. A separate difference probe measures at most 6e-8
probability and 9e-8 value differences, with identical actions. Audit-02 uses
the pre-existing recorded inference limits (1e-5 / 1e-4); all four final-model
comparisons pass, max probability 6e-8 and value 1.2e-7. Native training replay
and final weights remain exact.
Mean depot probability at updates 30/31/32 is 0.3810/0.3692/0.4299. Updates 30
and 32 contain only forced WAIT; update 32 increases depot probability, so the
tested final forced-action update does not explain the stall by destroying a
previous greedy preference. All snapshots still prefer WAIT on these histories.
This is an offline sensitivity audit, not checkpoint selection, new gameplay,
or causal isolation of value gradients versus Adam momentum. No optimizer change
is justified by this result.

The C++ recurrent V2 policy trains through actual native actions, stored masks,
behavior log probabilities, eight-step sequences and trusted V1 GAE/PPO. Four
training-map seeds remain the default; all sixteen are explicitly supported.
The older M22 corpus path is a separate capability.

- `v2-live-ppo-16u-01`: 512 live training transitions, no passenger service; full
  development replay also fails. This is pipeline evidence, not competence.
- `v2-guided-ppo-16u-01`: a public planner supplies geometry; the neural policy
  controls timing and repayment. Sampled service succeeds, greedy waits, and
  uniform/scripted controls using the same guide perform at least as well.
  No learned V2 advantage has been demonstrated.
- New reset checkpoints save model, Adam, three native RNGs, Torch CPU/CUDA RNGs,
  recurrent state, mode and counters. Binary/source/contract identities and the
  next reset's public observation/native/sampling tensors are checked. Arbitrary
  mid-game recovery and V2 ONNX export remain unsupported.
- `v2-live-resume-cpu-01` passes exact continuation. Initial CUDA recovery fails
  before saving: step 13 inference differs because cuDNN determinism does not
  cover graph scatter reductions. The original binary and failed run remain.
- Strict deterministic algorithms plus process-local cuBLAS workspace fix the
  tested CUDA failure. Trainer
  `581168c6b65a8a2511fbc460e23fbd8379bf2efb781ac0fdb7341dad414fa892`
  passes `v2-live-resume-cuda-02`: 128 continuation transitions, all metrics and
  final weights match exactly. Same-host claims only; CPU/CUDA weights differ.
- `v2-guided-resume-cuda-audit-02` also passes. Its executed full/prefix/resumed
  stages are in `v2-guided-resume-cuda-01`. The original verifier incorrectly
  compared absolute storage paths and is preserved as failed. The corrected audit
  normalizes only the run root, retains relative paths and every mask/guide field,
  and adds exact prefix actor comparison. Final weights are
  `abc02ee862a32ca7cb177fcd543ea9505edc58c0f9e5afec69da498111205742`.

`v2-live-resume-cpu-02` passes with that same final trainer: exact prefix and
continuation actor/feedback, all update metrics, 128 native continuation
transitions and final weights. `v2-checkpoint-native-rejections-01` passes nine
native rejection cases: fresh save, incompatible seed, repeated restore, existing
destination, relative destination, pending action, partial rollout, completed
update mid-game and corrupt archive. Preparatory requests succeed, the invalid
request terminates the service, and existing/source checkpoints remain unchanged.
Those rejection inputs reuse a recorded public reset snapshot; they are synthetic
boundary checks, not additional gameplay evidence. Windows copies are in
`v2-reset-recovery/`.

## Shared games and actual MCP opponents

Two companies alternate ordinary actions on one public map: 512 global decisions,
256 per company and 65,536 shared ticks. Own finances and public information are
scoped; researcher economic snapshots never enter policies. Native idle timeouts
abort without advancing the game. Official MCP SDK participation is executed.

- `v2-mcp-local-llm-full-map1630856436-c0-01`: actual local Gemma via Ollama and
  MCP completed 256 actions with no scripted fallback. Neither it nor the weak
  neural opponent delivered passengers. The LLM made 1,272 model calls, 252
  recoverable tool errors and used 2,725.1 model seconds excluding warmup.
  `v2-mcp-local-llm-full-audit-01` verifies model-to-MCP-to-native action mapping,
  tokens/timing and economics. Local provider charges are zero; energy/hardware
  cost is unknown. This is participation, not competence or exact LLM replay.
- `v2-mcp-full-comparison-02` includes the actual LLM and four fixed scripted
  map/role controls. The script's route fails when an opponent depot interrupts
  a public road; intentional sabotage is not inferred.
- `v2-mcp-repair-paired-comparison-01` compares fixed versus adaptive public-road
  repair in all four cells. On map 1630856436, service/economics remain identical.
  On map 155097162, repair restores 818/899 passengers and operating profit
  547/873; extra capital is 1,196/2,834. All four repair runs sustain service and
  positive cash before capital in the final three windows, but cumulative cash
  remains negative. No native failures, tool errors or bankruptcies occur. The
  neural opponent still delivers zero. This is a supported scripted improvement
  on these fixed cases, not neural learning or general shared-game reliability.

Broader mail/truck/rail gameplay, strong live V2 neural control, stronger LLM
opponents and broader paired economic research remain open. Continue the highest
priority learning experiment before expanding those domains.
