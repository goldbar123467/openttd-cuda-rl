# Live OpenTTD development progress

The horizon-256 run is complete. Work resumed in the continuation task; the owner
requested lossless storage cleanup before the next learning diagnostic. V1 has demonstrated
reproducible sampled bus play;
strong live V2 neural control is the current blocker. Frozen release contracts,
held-out selection rules and the user's ordinary game data remain untouched.
Use [DEVELOPMENT.md](DEVELOPMENT.md) for commands. Detailed prior results and
failed attempts are preserved in [the history](PROGRESS_HISTORY_2026-09-23.md).
Run names below are under `~/.local/share/openttd-rl/runs/` in Ubuntu-24.04.
Readable copies are in the checkout's ignored `runs/2026-09-23/` and `2026-09-24/`.

## Completed: lossless completed-run storage cleanup

All 172,515 registered archives pass the final compressed-hash audit. Original
artifact bytes decrease from 195,543,599,565 to 34,861,955,625: **149.65 GiB saved**.
Observed WSL available space increases **149.01 GiB**, reaching 825.01 GiB;
that net figure includes audit-record overhead and unrelated host activity.
All 527 model/checkpoint/ONNX hashes and 47,763 protected-file metadata records
remain unchanged. The latest run and held-out evidence are intact. Windows
virtual-disk compaction was not performed.

The owner prioritized storage maintenance before further learning. The registered
first pass covers 545 completed request logs (156,406,689,314 bytes) and 258 raw
binary snapshots (357,120,114 bytes). It uses at most two gzip workers at level 1;
each original is removed only after decompressed SHA-256/size equality and a
second original-file hash, with a durable per-file restore journal. The latest
v2-financial-horizon256-learning-01 run, held-out evidence, model/checkpoint
files, archived source and qualified worktrees are protected. Failed/unmarked
cases are skipped rather than relabeled. No training or game evaluation was run
during this cleanup.
The first pass completed all 803 files, reducing 156,763,809,428 bytes to
24,014,058,099 bytes and freeing 132,749,751,329 bytes (123.63 GiB).

The fresh inventory corrects the earlier broad tensor estimate: about 41.23 GiB
is JSON metadata, versus 2.36 GiB of remaining raw tensor binaries. A separately
planned metadata pass covers 171,712 files / 38,779,790,137 bytes, using the same
verification and protection rules after the first pass. Per-file fsync consumed
80% of a 16-copy profile. The first metadata execution was intentionally stopped;
its source/plan/log and two interrupted derived files remain intact. Its 12,185
verified completed files are retained, and only the 159,527-file remainder
resumed with batches of 128. Linux syncfs makes all archives durable before the
verified journal is flushed and any original is removed. Every file still passes
the same original/decompressed SHA-256 checks. This is storage maintenance,
not a training-speed or learning experiment. Existing native collectors and
compression defaults are unchanged.
The shared economic report reader now accepts `.jsonl.gz`; older consumers can
restore exact original paths. See [STORAGE.md](STORAGE.md) for retention/restore
commands. Off-drive archival and checkpoint pruning have not been performed.

Maintenance records are outside experiment runs at
`~/.local/share/openttd-rl/maintenance/storage-20260924-01`. Before cleanup, 527
model/checkpoint/ONNX hashes and metadata for 47,763 protected files were recorded.
Nine focused maintenance tests and all 136 portable checks pass. A full
512-decision shared economic report is exactly equal when read from gzip. An
actual 1,095,576,351-byte request-log copy restores with its original SHA-256;
the two disposable test copies were removed after verification. Restored metadata
also retains its native tensor binary's hash/size binding. The final audit proves
the interrupted prefix and batched remainder exactly cover the registration
without overlap. Full report and verification are copied to
`runs/2026-09-24/storage-cleanup-01/` on Windows.

The next learning step remains the handoff's missing-depot diagnosis on the
retained horizon-256 training-map case. Storage cleanup has not changed its
failed advancement criteria or any learning setting.

## Completed experiment: extend training episodes to 256 decisions

v2-financial-horizon256-learning-01 completed one fresh CUDA seed, 64 updates /
4,096 decisions in 2,559.68 seconds. All metrics are finite, behavior-replay
error is zero, and the first 64 native decisions/first numeric update exactly
match the eight-map control. The only registered setting change is horizon
128 to 256: eight maps receive two visits instead of four at the same budget.
This cannot separate later service exposure from fewer construction resets.
All nine final 512-decision evaluations complete, with no invalid actions or
bankruptcy. **Registered advancement fails.** No intermediate model selection
or held-out use occurred, and the longer horizon is not adopted.

All six sampled episodes sustain service. Means are 1,152.83 passengers / 3,481
operating profit / -6,436.50 cash after capital. These exceed the preceding
horizon-128 eight-map trial, but remain below the three stronger learned
controls and uniform. Paired profit/cash differences are +418.17 versus the
eight-map control (approximate 95% interval [-365.25, 1201.59]) and -201.17 versus
uniform ([-831.50, 429.16]). The intervals describe three action seeds conditional
on one model and two fixed maps; both include zero.

Both development greedy episodes build roads/stops, repay eight installments,
and stall before the depot. Map 1630856436 ends at 0 passengers / -1,234 operating
profit / -4,016 cash; map 155097162 at 0 / -1,334 / -7,765. A legal depot action
remains available, but final WAIT probabilities are .84563 and .84613. The
training-map greedy case 1871197196 ends at 0 / -1,184 / -7,225 after 14 roads,
two stops and eight repayments. Its final guide mask is a different failure:
construction_blocked=true at stage 16 of 17, with the planned depot absent from
the bounded native candidates and only WAIT allowed. The underlying legality or
candidate-priority cause remains unresolved; that final probability 1 is imposed
by the mask rather than a learned preference.

The completed training audit finds only 692/4,096 steps offering a choice,
versus 1,590 in the preceding eight-map run. There are 3,404 forced WAIT steps
and 47/64 entire rollouts without a choice. START appears 16 times (10 positive
normalized advantages; mean +.5944), versus 31 previously (12 positive; mean
-.1649). Depot advantage averages -.4350. All reconstructed native explained
variances agree within 5e-10. These changing-policy state/action groups are
not counterfactual action values. The earlier forced-WAIT-update audit also did
not support blaming its final update for destroying a good greedy preference.

Model: 8b3738e9206b6f552431140ce6d68bca5b8c66c8ab08e28abbea7d481fa61dde.
Registration: fc447691c38a8474f4297d3dd56ffb666bb3383211cd3e77b82fa05fd5cf16ea.
Final checkpoint is train/checkpoints/update-000064. Full report, JSON, reviewed
PNG/SVG plot, final greedy distributions and the training guide diagnostic are
in v2-horizon256-01/completed on Windows; training audits are adjacent.

The user requested pausing after this run and moving to a new chat. No new
experiment has started. [The handoff](../handoff.md) and
[continuation prompt](../continuation-prompt.md) identify source/worktrees,
reproduction commands, qualified deployment, failures, and the recommended next
bounded diagnostic. First distinguish the blocked training depot from the
available-but-rejected development depots. A later horizon-128 budget extension
could test construction exposure, but remains an unexecuted hypothesis.

## Completed experiment: eight training maps at fixed budget

v2-financial-eight-maps-learning-01 completed one fresh CUDA seed for 4,096
decisions: 64 updates of 64, horizon 128, signed-log-v1 inputs, guide version 2,
unchanged reward and lambda .95. Eight maps receive four visits each rather than
four maps receiving eight. Training map eight contains the expensive route
identified below. The first 512 native decisions and eight numeric updates
exactly match the four-map run before the curriculum diverges. All 64 behavior
replays have zero error; training takes 2,522.4 seconds. All nine evaluations
complete 512 decisions with no invalid actions or bankruptcy. **Advancement
fails:** sampled service succeeds 6/6, but means fall to 1,144.83 passengers /
3,062.83 operating profit / -6,854.67 cash. These point estimates are below all
three learned controls and uniform. Paired profit/cash differences are -741
versus the four-map scaled model (95% interval [-1,633.35, 151.35]) and -619.33
versus uniform ([-1,364.30, 125.64]). These are conditional three-action-seed
intervals over two fixed maps and one training seed; both include zero.
Both development greedy episodes buy and route a bus, then leave it stopped: map
1630856436 ends at 0 passengers / -984 operating profit / -9,077 cash; map
155097162 ends at 0 / -1,101 / -12,843. Both repay eight installments and retain
20,000 debt. The expensive training-map greedy case does the same, ending at
0 / -1,084 / -12,796. No checkpoint selection or held-out use occurred. Full
report and reviewed plot: v2-financial-eight-maps-01/completed on Windows.
Model: 923c6cf78599d3018cb89cf1bcd66faa3543ae7267384f723b7fdd4c50a58f8b.
An audit of all 32 sampled training episodes finds a bus purchased on all four
visits to expensive map 1871197196, with deliveries in three and no nine-payment
episode. Adding that map did not expose this learner to the prior funding trap.
All episode boundaries bootstrap correctly. Training-only accounting is in
v2-financial-eight-maps-01/training-audit-corrected on Windows; the initial audit
is retained with a corrected metadata-key note in the replacement JSON.
Registration: 8ca74a31d6353bcaa229a7a4c48723eb04c5a61ad2c9e0c1408f4eaec6c7c69c.

## Qualified prerequisite: complete underfunded episodes without planner aborts

The financial-input trial below exposes an unavailable BUY_BUS after aggressive
repayment. The isolated v2-guide-blocked-wait-01 adds optional
one-bus-public-plan-v2: after construction, an unavailable service action proposes
native WAIT instead of aborting. It supplies no financing or automatic commands.
Version 1 remains the default for old runs. Guide identity binds training,
checkpoint/reset, inference and MCP; an explicit development inference override
records both trained and executed guide versions. The 31 focused and 136 portable
tests pass. Both full replays pass: the failed map retains its original 34
decisions exactly, then performs 478 legal WAITs, ending with zero passengers,
-484 operating profit and -7,305 cash. The other map retains all 512 decisions
and its successful economics. CUDA reset recovery passes 256 versus 128+128
decisions, retaining the version 1 model SHA 36e89fd3e98ba6200bf6b35e99844b9b608b8f9e1c7f50eb81e2e44a3c27616f
and native continuation trace. The actual eight-decision MCP smoke records
version 2. Only the nine guide/adapter/test file changes were integrated into
main; financial preprocessing remains isolated. Main source backup and the
bounded change patch are in v2-guide-blocked-wait-integration-01.
This is failure-accounting correctness, not a rescue or a new learning result.
Registration: 2d17bcd0f792c99705b95a9912cba3a906c170a5c953d37e42d133c242037249.

v2-training-reserve-probe-01 completed all four deterministic 512-decision
controls on training map 1871197196 with no invalid actions or bankruptcy.
Build-first delivers 758 passengers / 2,632 operating profit / -9,080 cash;
repay-eight-first delivers 715 / 2,760 / -8,952. Both sustain service. Repaying
nine installments first leaves no bus: 0 / -484 / -7,275; repay-and-WAIT yields
0 / -484 / -1,209. Realized gamma-.99 return at 128 favors repay-and-WAIT
(-1.373 versus -1.771 for eight repayments plus service); at 512, service wins
(-.753 versus -1.893). These returns omit the critic term; actual PPO retains
time-limit bootstrapping. Reward horizon remains an alternative explanation
while the eight-map trial changes coverage alone. Registration:
c9c6b8008a8acdb3f6a0b07f9f3376514c93a2d9f1ddd91997cd003424f8aef8.
Readable results: v2-guide-blocked-wait-01/reserve-completed on Windows.
The return-timing plot recomputes all 2,048 rewards from native traces and matches
the recorded 128/512 totals. Eight repayments plus service stays ahead of
repay-and-WAIT from decision 149 onward. At the 128-step cutoff, a critic value
difference greater than 1.4382 would reverse their bootstrapped-return ordering;
this is an algebraic threshold, not a measured critic estimate.
The integrated main repay-first/version-2 CLI then reproduced all 512 native
decisions and economics exactly (v2-guide-main-repay-check-01).

## Completed prerequisite: live V2 ONNX export and visible playback

The isolated v2-live-export-01 worktree adds an inference-only conversion adapter
for the existing raw-input C++ recurrent policy. Training remains C++/LibTorch.
The first smoke loads all 66 parameter tensors strictly, reproduces eight CPU
decisions and exports identical ONNX bytes twice. v2-live-export-offline-02 then
passes all five outputs (family/candidate logits, value, next memory and action
probabilities) on 1,024 consecutive recorded decisions from both full development
episodes, plus 64 unmasked recurrent steps and 12 malformed-input rejections.
Native/adapter tensors are exact; ONNX probability/value errors remain within
1e-5/1e-4. Attempt 01 is retained: its duplicate-vehicle-ID test fixture activated
two rows without making their IDs equal. Correcting the fixture, not the runtime
or tolerance, resolved that failure.

The generic export command independently verifies 512 recorded native decisions
before qualifying a package. The raw 4,096-decision model exports to graph
1e85eab9f59dc67d5d2709d0d1b96e50c9ff791009a904b4c92a09a28dc40d35.
The separate native ONNX Runtime 1.28.0 executable performs the neural forward
pass and reuses the existing C++ public tensor reader, hierarchical distribution
and seeded sampler. Deployment is explicitly CPU-only and rejects CUDA requests.
Its service qualification passes 1,024 greedy and 768 paired sampled decisions
plus eight native rejection cases. Maximum probability/value error is
1.79e-7/5.25e-6. v2-live-onnx-smoke-02 passes greedy and sampled eight-step native
games against fresh matched-horizon CPU controls, with exact transitions,
candidates and planner masks. Smoke attempt 01 is retained: an eight-step
episode was incorrectly compared to a 512-step prefix, differing only in the
final truncated flag. The corrected smoke preserves exact equality of that
field. All four full headless replays now pass: 2,048 native decisions, selected
candidates, guide masks and full economic summaries exactly match the archived
LibTorch runs. Probability/value maxima are 2.09e-7/4.77e-6. Six new files and
bounded CMake/inference additions are integrated into main; its 37 focused
tests, 136 portable tests and diff check pass. The native reader/model source
bytes match the qualified isolated build. The deployment executable still uses
LibTorch for input validation and sampling; it is not a Torch-free runtime.

Both integrated visible ONNX replays also pass all 1,024 native decisions and
economic outcomes exactly. Map 1630856436 delivers 1,451 passengers, earns 5,092
operating profit and ends at -3,001 cash after capital. Map 155097162 delivers
984, earns 1,872 and ends at -9,870 cash. Both sustain service with zero invalid
actions and bankruptcy. Both native 1280x800 screenshots have been reviewed;
the finance windows agree with recorded bank balance/debt/own funds. These are
deployment-equivalence results, not a new learning gain. The package, report,
screenshots and source integration are copied to
v2-live-export-01/completed on Windows. DEVELOPMENT.md now includes build,
export, headless and visible commands. All replays finished before the
horizon-256 trial's evaluation stage, within the two-native-job limit.

An offline profile of 36 retained tensor files (45,167,796 raw bytes) measures
gzip level 1 versus the current level 9 in three counterbalanced pairs. Median
compression CPU ratio is 17.63x and compressed size grows 1.553x (512,582 to
796,284 bytes), with every decompressed byte equal. This measures in-memory
compression under background load, not disk or end-to-end training speed.
v2-tensor-compression-profile-01 warrants a separate whole-run comparison under
its registered 20%-CPU / 2x-size gate. No runtime compression setting changed,
and no further experiment will start before the requested handoff.

## Completed experiment: optional financial input scaling

Hypothesis: native cash/debt fields divided by 1e9 make relevant monetary
differences difficult for the live recurrent policy to represent. The isolated
worktree v2-financial-features-01 adds optional signed-log-v1 preprocessing,
leaving raw inputs as the default. It transforms public cash, debt, maximum loan
and candidate quoted cost to a common signed logarithmic currency scale. Zero
and redacted values stay zero; information, masks, reward and PPO do not change.
Training/inference share the C++ transform; checkpoints and saved weights bind
its mode. No learning benefit has been demonstrated. The first qualification
passes seven native gates, exact raw CPU32/CUDA32/CUDA64 behavior, exact new-mode
CPU/CUDA reset recovery, eight CLI cases, 14 checkpoint rejections and inference
parity. Numeric update error is 2.78e-5 (existing limit 1e-4); inference maximum
probability/value errors are 6e-8/7.1e-7. The 29 focused Python tests and 136
portable tests pass.

An additional probe finds that the legacy raw-only reader silently accepts the
new metadata-tagged weights; v2-financial-features-checks-01 therefore is not
qualified for adoption. It remains intact. The corrected version nests only
preprocessed weights so legacy readers cannot find raw model parameters, while
raw archives retain their old structure. v2-financial-features-checks-02 passes
the complete qualification, five weight-loading cases including legacy rejection,
and an actual eight-decision MCP smoke. It preserves every parameter tensor,
768 decisions and twelve PPO updates versus the earlier archive layout; hashes
change only because the container changes. CPU/CUDA new-mode reset models are
8aa106d02eafffb78783de9616bedc1c56a71367432478218f52bd3525092064 /
36e89fd3e98ba6200bf6b35e99844b9b608b8f9e1c7f50eb81e2e44a3c27616f.
Reports and the isolated 16-file review are under v2-financial-features-01 on
Windows; production code in the main checkout remains unchanged.

v2-financial-features-learning-01 completed 4,096 decisions from scratch
(64 updates of 64, seed 20260923, four training maps, horizon 128, lambda .95,
existing reward/guide, qualified tensor reuse), in 2,555.20 seconds. All behavior
replays are exact. Model: 33dd2906774f1c92f8c1d94f61c97decbeff1b9b8be8176de25451d646d46f18.
All eight scheduled evaluations finished execution. Six sampled episodes sustain
service, averaging 1,220 passengers, 3,803.83 operating profit and -6,113.67 cash.
Differences versus raw-2048 are -1 passenger/-3.17 profit/cash; versus raw-4096,
+44.17/+230.50; versus uniform, +26.17/+121.67. All approximate conditional
three-action-seed 95% intervals include zero (profit versus uniform [-89.12,332.45]).
One greedy map completes with 1,433 passengers/5,969 profit/-2,124 cash. The other
aborts after 34 legal decisions: nine repayments leave 10,000, actual construction
spending is 6,096, then cash 3,862 cannot buy a bus. Native WAIT remains exposed, but the guide
raises an unavailable-service error. Those partial economics are not a full
episode. No native invalid actions/bankruptcies occurred in completed episodes;
the planner abort is recorded separately. Advancement FAILS greedy completion
and all three comparisons with raw-2048. No replication/adoption is justified.
The original executor's failed report is intact; completion-audit.json accounts
for all eight queued cases and rechecks all eighteen archived controls. Report,
plot and original execution failure: v2-financial-features-01/learning-completed
on Windows. No held-out use or intermediate-model selection occurred.
Registration: cc5025ac410aed7cc7ae9abd2a15092840b36b8cd096c0cb1638a47a381fbc55.
An audit of all sixteen archived training-map scripts (same engine/guide) finds
capital 6,523..7,806 on the first four maps; none exceeds 10,000. Only training
map eight, 1871197196, exceeds that threshold across the full ledger (10,987).
This is capital accounting, not a simulated nine-repayment intervention; interest,
fees and intermediate income also affect funding. It motivates testing reserve
decisions on that training map before changing the curriculum. Report:
v2-financial-features-01/training-capital-audit on Windows.

v2-visible-playback-01 qualified an independent
view-only SDL route for the already completed raw-input 4,096-decision model.
The separate v2-visible-engine-01 reuses the native command/tick boundary and
yields the game-state lock to draw while waiting for requests. GUI game input
is suppressed; redraw checks require unchanged simulation RNG, ticks and
native state. The build and actual eight-decision SDL/null smoke pass: actions,
native states and CPU predictions match exactly; errors versus the old CUDA
reference are at most 6e-8 probability and 2.4e-7 value. The reviewed native
1280x800 screenshot shows the game map, and SDL explicitly uses the real X11
display. The isolated Python path passes 27 focused tests, including rejection
of dummy/missing displays, and all 136 portable tests. v2-visible-idle-01 also
leaves the real display open across two ten-second waits: observations remain
identical, and its subsequent native WAIT transition exactly matches headless
execution. v2-visible-full-01 passes both full visible replays: all 1,024 native
decisions, candidates, guide masks and economic outcomes match the archived
CUDA reference. Maximum CPU/CUDA probability/value errors are 1.2e-7/1.91e-6.
Both native screenshots were visually reviewed. Five reviewed files were copied
into main only after original/current hashes matched; all 25 focused main tests,
136 portable tests and diff check passed. The source backup and
integration record are in v2-visible-integration-01. The development guide now
documents building and launching this optional viewer.
This does not change the training trial or its engine. Reports/image:
v2-visible-playback-01/smoke-completed and completed on Windows.

The main baseline evaluator now exposes a fixed repay-first controller using the
same existing public mask. Its first queued diagnostic, v2-repay-first-control-01,
stops before any native game because its scheduling guard required a successfully
completed financial executor. That setup failure is preserved. The subsequent
v2-guide-main-repay-check-01 passes all 512 decisions on the expensive training
map exactly against the completed reserve probe.
It is a post hoc diagnostic and does not replace the financial advancement rules.

## Completed diagnostic: sampling variability of fixed models

v2-roll64-sampling-variation-01 evaluated the frozen 2,048/4,096-decision
models and uniform control at sampling seeds 20260924/20260925 on both full
development maps. It reuses their six completed seed-20260923 episodes, totaling
18 completed cases. Hypothesis: the sampled regression may depend on action
randomness. All twelve new cases ran, with at most two jobs.
Paired differences average the two maps within each sampling seed; approximate
df=2 t intervals describe only this small conditional sampling distribution.
There is one training seed and two fixed maps. No training, held-out selection,
or replacement of the failed advancement gate is part of this diagnostic.
All three controllers sustain service 6/6, with zero invalid actions/bankruptcy.
The 2,048/4,096/uniform means are 1,221/1,175.83/1,193.83 passengers,
3,807/3,573.33/3,682.17 operating profit and -6,110.50/-6,344.17/-6,235.33 cash.
The longer-trained model's paired difference versus the earlier model is
-45.17 passengers (approximate 95% interval [-135.53,45.19]) and -233.67 profit
([-699.54,232.20]). Versus uniform, profit differs by -108.83
([-433.04,215.38]). These results do not establish sampled improvement or a
precise regression magnitude. The original failed advancement gate remains
failed. Report: v2-budget-extension-01/sampling-completed.
Registration: b3242dd118b06efeeae3e8c8711d9271eb7bd880f0d194cdda592cc5b2679aaf.
Retrospective trace timing finds mean service starts at 36.17/39.33/47.83
decisions for old/new/uniform, with 7.17/10.33/18.83 earlier WAITs. All make
eight pre-service repayments, retaining loan 20,000. The longer model waits
3.17 more decisions than the earlier one, but timing alone does not explain
economic ranking: uniform starts later yet earns more than the longer model.

## Completed experiment: additional experience under fixed settings

v2-roll64-budget4096-01 resumes the strongest earlier four-map, 64-step model
at update 32 for 32 more updates: 2,048 additional decisions, 4,096 total.
Hypothesis: repeated construction experience improves greedy service without
changing the algorithm. Engine, trainer, collector, reward, guide, maps/order,
horizon, optimizer and RNG state remain fixed. The exact archived source was
reconstructed and hash-verified in v2-roll64-budget-source-recovery-01; current
collector options are not substituted into an older checkpoint.

Training completed all 4,096 cumulative decisions (32 continuation updates,
1,342.48 seconds); every behavior replay is exact. Model:
3338f827674485b072b6544cd97e665feef03b5c16674201ff4bac37b488951a.
All four development evaluations are complete. Both full greedy episodes sustain
service in all three final windows: 1,451/984 passengers, operating profit
5,092/1,872 and cash -3,001/-9,870, with zero invalid actions/bankruptcies.
Means are 1,217.5/3,482/-6,435.5. Service starts at decisions 21/36 without any
pre-service WAIT (7/8 repayments), replacing the previous construction stall.
The first map retains loan 30,000. Sampled means are 1,141 passengers, operating
profit 3,383.5 and cash -6,534, with sustained service 2/2 and zero invalid
actions/bankruptcies. The registered advancement test fails all five sampled
economic comparisons against the previous model/uniform, while greedy service
improves 0/2→2/2. Only the final model was evaluated. This is a budget comparison
on one training seed, with no held-out use; neither broad competence nor better
sampled control is established. Report: v2-budget-extension-01/completed.
Registration: 8f442936761253813e4b1171911b15f081f654f20c0bf4a9e4f5210a565b32a3.
Restore and initial continuation updates pass exact behavior replay.

Separately, v2-training-reward-objective-probe-01 completed deterministic service
and repayment-only play for 512 decisions on training maps 1110312784/583478638.
Service delivers 1,571/392 passengers with operating profit 6,176/-94 and cash
-1,604/-7,342; only the first sustains operating service. Repayment alone delivers
zero, with profit -484 and cash -1,209 on both. Realized gamma-.99 reward prefers
service on the first map (4.0147 vs -1.8925) and repayment on the fourth
(-2.4423 vs -1.8925), also true at horizon 128. All four controls have zero
invalid actions/bankruptcies. This diagnostic map selection is not representative,
omits the time-limit critic term, and does not explain failure on profitable maps.
It identifies a curriculum concern without changing the running experiment.
Read-only encoder inspection also finds cash/debt divided by 1e9 in structured
features 8/9 and company fields 2/3; a 10,000 repayment changes them by 1e-5.
This suggests a feature-scale hypothesis, not an established defect. The main
preprocessing and frozen encoder remain unchanged; an optional development
transform is being qualified in the isolated worktree described above.
v2-financial-input-sensitivity-01 replays the same 21 public frames, then varies
only four cash/debt floats in the next observation. Repayment probability is
0.447816074 and changes by at most 3e-8 across cash 20,000..1,000,000 and debt
10,000..100,000. Original-repeat is exact and CPU matches recorded CUDA within
existing tolerances. This is synthetic local sensitivity on one history, not
native gameplay or proof that rescaling would improve learning.

## Completed experiment: native credit over a complete training episode

Hypothesis: 64-step boundaries and GAE decay prevent later delivery from giving
construction useful credit. The 16-map audit finds only 35/116 road actions
share a rollout with later delivery, versus 101 followed by delivery in the same
episode. Median lag is 59 decisions; the direct weight at gamma=.99/lambda=.95
is about .027. Changing lambda to 1 offline within those same 64-step windows
helps buy/route/start credit but worsens roads. This is descriptive evidence.

The bounded change adds optional rollout 128 and lambda in [0,1], retaining
32/.95 defaults, trusted native GAE/PPO, eight-step recurrent backpropagation,
four epochs and the reward/guide. Native configuration and checkpoints bind the
return settings. Original source is retained in v2-full-return-source-change-01.

v2-full-return-checks-01 failed before compilation because its launcher omitted
the explicit nvcc path used by local.py. The failure remains intact.
v2-full-return-checks-02 passes with CUDA 12.6 and sm_75. All six native gates,
preserved 32-step CPU/CUDA and 64-step CUDA behavior, and both 128-step reset
recovery tests are exact. CPU/.95 model: cd49e3e2d7d2a5563ddd28e1fd87ba049cea977aba357090ead68f2f340b3bf4;
CUDA/1 model: b2eb9ba6c5a04457608291213d934b21bc60e08dc6cef29c316c8dbc71e4182f.
128/lambda1 CPU/CUDA matches all native decisions across six time limits/seven
resets; max update error 2.25e-5 is within the existing 1e-4 limit. Independent
scalar GAE matches native explained variance within 4.20e-11. All 18 CLI cases
and 13 native rejection cases pass without changing checkpoints/destinations.
Trainer: db8ead4e24e9dab2c8a37d4939198aa4c45f50d275380cffcc625d194bba39db.
The 26 focused V2 unit tests, 136 portable tests and git diff check pass.

v2-full-return-learning-01 completed 128/.95 and 128/1, each trained from scratch
for 2,048 decisions over all sixteen training maps. Training stages are serialized
on CUDA; evaluation may overlap the other arm's training, with at most two
native jobs. Each must sustain both greedy and sampled service on both full
development maps, match the previous best sampled passenger/profit/cash results,
match uniform on profit/cash, and avoid invalid actions/bankruptcy before
replication. No held-out data informs this test. At matched experience, a longer
rollout also changes update cadence and advantage normalization; BPTT stays eight.
With horizon 128, updates now occur at resets, removing mid-episode parameter
changes with carried recurrent state. This is another limit on causal attribution.
Registration: 5ab609147b2d16a0bc7b2a48559f7551cac770ca93bfcd943da24d092048b95c.
Both arms completed all training and four full development evaluations each.
Independent scalar GAE audits pass within 4.98e-10, and all 116 road actions per
arm now precede delivery within
the same rollout (versus 35/116 in the 64-step control). This confirms the return
window mechanism, not improved evaluation performance.
All four complete greedy development episodes deliver zero passengers,
each with operating profit -4,834 and cash after capital -5,559, without bankruptcy.
Both arms fail their registered criteria. Sampled .95/1 means are 1,122/1,120.5
passengers, operating profit 3,332.5/3,379 and cash -6,585/-6,538.5, with service
on both maps; all are below the four-map model and uniform control. There are
no invalid actions or bankruptcies. Mean multi-choice road advantage is
-0.7875/-.2451 despite sharing the delivery window. Neither is adopted as a
learning improvement. Frozen CPU probes on the same sixteen public training
resets choose WAIT for both models on every map (v2-full-return-initial-choice-probe-01);
failure also occurs on familiar initial states. Report: v2-full-return-01/learning-completed.
The sampled lambda-1 traces contain 17/35 extra WAIT actions before initial service
relative to the old four-map model. Timing is descriptive, not a causal isolation.
v2-realized-reward-horizon-audit-02 exactly reconstructs all 2,048 old training
rewards. Its partial-return tables omit the critic term retained by actual PPO
at time limits; they must not be mistaken for the native training target.

## Recent live V2 learning results

All rows use the same public geometry planner. Neural policies decide timing
and repayment; this is not learned route geometry. Each evaluation runs all
512 decisions of 128 ticks. Means cover two development maps and one sampling
seed; these single-model diagnostics do not establish uncertainty or generality.

| Training configuration | Sampled passengers | Operating profit | Cash after capital | Sampled / greedy sustained |
| --- | ---: | ---: | ---: | ---: |
| 32-step, 4 maps, 2,048 decisions | 1,171.5 | 3,179 | -6,738.5 | 2/2; 0/2 |
| 64-step, 4 maps, 2,048 decisions | 1,228 | 3,833 | -6,084.5 | 2/2; 0/2 |
| 64-step, 4 maps, 4,096 decisions | 1,141 | 3,383.5 | -6,534 | 2/2; 2/2 |
| 64-step, 16 maps, 2,048 decisions | 1,161 | 3,562 | -6,355.5 | 2/2; 0/2 |
| 128-step, lambda .95, 16 maps, 2,048 decisions | 1,122 | 3,332.5 | -6,585 | 2/2; 0/2 |
| 128-step, lambda 1, 16 maps, 2,048 decisions | 1,120.5 | 3,379 | -6,538.5 | 2/2; 0/2 |
| Uniform, same guide | 1,182.5 | 3,629 | -6,288.5 | 2/2; n/a |
| Scripted, same guide | 1,238 | 3,514.5 | -6,403 | 2/2; n/a |

All six completed learned configurations fail their registered advance criteria. The
16-map greedy policy repays then waits without construction. Four-map greedy
also fails initial service on all four familiar training maps; unfamiliar
geometry alone is insufficient to explain failure. All full cases have zero
invalid actions and bankruptcy. Broader coverage trades off repetitions and
map order; it is not a pure diversity effect.

Sources: v2-guided-budget-02, v2-guided-roll64-32u-01 and
v2-guided-sixteen-maps-32u-02. The first 16-map setup was stopped after its
registered raw-checkpoint equality test failed. All first 512 native decisions
and eight updates matched; an independent comparison later proved exact model,
Adam/RNG/recurrent/counter state. LibTorch serializes process-specific optimizer
IDs. Setup-02 resumes that verified prefix; 332 extra decisions remain unused
failure overhead. No legacy expected hash or native acceptance rule changed.

The forced-action audit exactly replays the final 512 decisions/eight updates
of the four-map model. Its final WAIT-only update increases depot probability
on four fixed histories; it does not support blaming that update for destroying
a previous greedy preference. No optimizer change was made. Tiny separate
inference differences pass the pre-existing tolerances; the earlier exact
inference assertion failure remains preserved.

## Retained performance and recovery improvements

Optional --reuse-bootstrap-tensors passes exact actor/mask/feedback/native/PPO,
logical checkpoint and CUDA continuation checks, plus CPU/CUDA agreement across
real time limits. It caches input frames at the same state token/company, clears
on reset and runs fresh neural inference after every update. Default remains off.
v2-bootstrap-reuse-end-to-end-01 has three sequential counterbalanced pairs:
185.412/170.811, 180.235/169.764 and 177.080/172.880 reference/reuse seconds.
All 768 paired decisions, twelve updates and final models match exactly.
Median ratio 1.06168 meets the registered threshold: 5.81% less total wall time,
including startup, source capture, archival and validated save. This is a local
collector optimization with an unchanged CUDA trainer, not a kernel speedup.
Native TENSORS time remains about 21 seconds despite 512→258 requests; the
untimed remainder and actor/PPO times also vary. Do not attribute all savings
to one operation. The native handler already reuses per-decision tensor files;
the optional collector skips their duplicate request/read/validation in Python.
Reports: v2-snapshot-cache-01/end-to-end-completed on Windows.

Earlier V1 spatial validation vectorization preserves 1,536 paired transitions,
PPO/model bytes and reset recovery, with median isolated end-to-end ratio 1.14714.
The CUDA masked-distribution kernel is 9.62x faster for its tested operation but
only 1.00470x end to end; it is optional. WSL sanitizer/Nsight limitations are
recorded as unsupported, not passes. RTX 2070 CUDA requests never fall back to CPU.

V2 reset checkpoints retain Adam, three native RNGs, Torch CPU/CUDA RNG, hidden
state and counters. Strict deterministic algorithms plus the cuBLAS workspace
fixed the tested CUDA recovery failure. Source/configuration/contract identities
remain strict; use archived source to resume older runs. Arbitrary mid-game
recovery and V2 ONNX export are still unsupported.

## Established V1 and broader integration

V1 balanced-reward 64-step CUDA training across three seeds sustains all 18
sampled development episodes, versus 12/18 for the matched 32-step control.
Greedy succeeds 4/6. Sampled means are 1,513.7 passengers, 4,670.3 operating
profit and -3,745.1 cash after capital; the one-bus script is more cash-efficient.
Three-seed paired uncertainty is wide; no broad superiority claim is made.

The frozen heldout-balanced-roll64-confirmation-03 completed all 36 episodes and
passed all seven preregistered checks. Primary sampled service succeeds 18/18,
with means 2,017.4 passengers, 6,022.6 operating profit and -2,488.3 cash after
capital. One-bus cash remains better; greedy is 4/6. These results cannot guide
further tuning. Setup failures and model identities remain in the history.

The development-selected seed-24 model exports reproducibly to ONNX; all 4,096
paired native/ONNX decisions across eight complete episodes match actions,
masks and economics within reviewed output tolerances. Two visible native
replays also pass. Package/workflow: demo-balanced-roll64-s20260924-01 and
Windows reproducible-playback/balanced-roll64-s20260924-01.

The separate native mail/truck extension sustains both passenger and mail
service with a scripted controller on two development maps: 1,488/745 and
1,054/431 passenger/mail deliveries, combined operating profits 8,749 and 3,419.
Construction leaves cash losses. Earlier stop-destruction/station-join failures
are preserved. Neural mail, shared cargo and rail remain open.

An actual local Gemma LLM completed a full MCP match against the earlier weak
neural policy: 256 decisions each, neither delivered passengers. The LLM made
1,272 model calls, 252 recoverable tool errors and used 2,725.1 model seconds.
Provider charges are zero; energy/hardware costs are unknown. This proves
participation, not competence or exact LLM replay. The same adapter already
supports guided neural weights. Company identity, public information, alternating
turns, tick budgets and timeout behavior are enforced at the shared boundary.

Four paired map/role tests show that public road-repair scripting restores
818/899 deliveries on a disrupted map while preserving the two successful cases.
All four sustain operating service, but cumulative cash remains negative.
Stronger neural/LLM play and broader economic replication remain open. Continue
the current learning experiment before expanding transport or research scope.
