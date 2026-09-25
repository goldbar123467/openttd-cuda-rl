# OpenTTD live PPO continuation handoff

**Experimentation paused at the user's request.** The original task completed the horizon-256 trial and
honored the requested pause. This task completed the requested storage cleanup,
missing-depot diagnosis, an 8,192-decision continuation and all nine evaluations.
All nine sustain service, but the sampled economic advancement criteria fail.
The entropy option passed native qualification and completed fresh 8,192-decision
CUDA training plus all nine evaluations. It regresses service to 5/9 and fails
advancement. The signed-log deployment extension passed all six stages and screenshot review,
and its ten qualified files are now integrated in main. Retained learning
results: borrowing-guide retraining fails, while frozen
weights with recovery sustain 9/9 games. The twelve-game MCP comparison is complete and fails its useful-service criterion.
The first prospective replication seed fails all eighteen service cases. Both
new training runs are complete; the second seed is unevaluated after the user-requested stop.

## Stopped at user request: independent training-seed recovery study

The user requested: "After the training run stop and commit to GitHub."
Both fresh CUDA training seeds finished their full 8,192 decisions / 128 updates
/ 64 episodes. Seed 20260924 completed all eighteen v2/v3 final-weight games;
seed 20260925's eighteen queued evaluations were never launched. No experiment
process remains running. This is an incomplete registered comparison with an
already failed per-seed service criterion, not a completed replication pass.

The study prospectively tested whether the .001/v2 policy's inference-time
borrowing recovery survives independent training seeds. It reused immutable,
qualified `v2-borrow-guide-01` source and C++/LibTorch binaries. No production
implementation changed and no completed native qualification was repeated.
Study SHA: `653372df52cea80855cc92f433211f8623ab00c4ec8c39957a440d6962ce5c8a`.
Execution SHA: `e52b9e241748e856e49f9b749255e8bbaa6df786a01cf471c4a20cdb5363be9d`.

Both runs use guide v2, entropy .001, eight training maps, horizon 128, rollout
64, signed-log inputs, gamma .99, lambda .95, BPTT eight, four optimization epochs
and bootstrap reuse. Only final update-128 models are selected. CUDA is mandatory
with no CPU fallback. Training is serialized, with at most two native evaluation
jobs between seeds. Both final runs have finite metrics, zero behavior-replay
error, zero saved-weight reload error and verified reset checkpoint/model hashes.
The wall times below compare different training seeds; they are not speedups.

- Seed 20260924: 4846.741 seconds; model `b3bcbb3977a3d8c927af6348fb3fda9302177ba2d5d9651cdd0544447a82c78a`.
- Seed 20260925: 4826.652 seconds; model `832f1139d3fc5cf9ab195446e415342fa9ac1b8f9761d0519984ee756b4b940e`.

**Seed 20260924 fails service in all eighteen full games:** zero passengers,
zero sustained-service cases, zero invalid actions and zero bankruptcies.
All nine paired v2/v3 full summaries and native trace SHA-256 values are identical.
The recovery guide changes nothing for this initialization. Each guide's six
sampled games average 0 passengers, -4,578.667 operating profit, 250.50 capital
and -5,554.167 cash excluding financing. All six greedy games choose 512 WAITs.
The registered gate requires every seed to sustain all nine v3 games and match
or exceed all six learned controls on sampled passengers/profit/cash, with
profit/cash strictly above uniform. Pooled means cannot conceal this failed seed.
The original seed23 is a retained development lead; seeds24/25 were prospective
replications. No held-out or intermediate checkpoint selection occurred.

The two complete v2 greedy development traces remain at stage zero, with no
blocked frames and legal road construction/repayment available alongside WAIT.
Initial WAIT probability is about .9858, reaching .9965. This is a preference
failure before construction, rather than the old unaffordable-bus stall. Each
game earns -4,834 profit and -5,559 cash, with no deliveries in any window.
Diagnosis SHA: `8f9a7217193ec2e1f27623994638c3b5c83749256b2e0e37b95a0d84847a8532`.
All eighteen full outcomes are retained in `seed24-completed-review/`; its JSON
SHA is `ada6bdab7a1be288c6a16ae805af312f044ac5a77bcf522f6cac443d9662050e`.

After stopping, the read-only review independently checked all eighteen completed
games and 72 economic windows, including selected actions, masks, guide stages,
capital and recovery eligibility. Both new full training trajectories also pass
reward/native-transition and scalar GAE reconstruction; maximum explained-variance
differences are seed 20260924: 4.98e-10, seed 20260925: 5e-10, below the unchanged 1e-5 tolerance.
The original seed's completed training audit was reused without rerunning it.

| Training seed | Episodes with START / 64 | Delivering episodes / 64 | Mean training passengers | Mean training profit |
| ---: | ---: | ---: | ---: | ---: |
| 20260923 | 54 | 53 | 160.031 | 450.188 |
| 20260924 | 15 | 15 | 35.562 | -724.859 |
| 20260925 | 64 | 64 | 204.016 | 621.531 |

These changing-policy training outcomes do not substitute for the second seed's
unrun final-policy evaluations. Prepared full-comparison plotting and analysis
remain unexecuted where they require those missing games. The complete-case
review and training audit are in `stopped-completed-review/` and `training-audit/`
under the checkout's ignored `runs/2026-09-24/v2-recovery-replication-01/`.
Their JSON SHA-256 values are `b456ff7b9b260ad798e3f32dc95b0cf0be3f55a51342afb7cdd27cdda50fc552`
and `4fd108c5a22dd6f6e97c28f4432996fe40212eecca7b2824ca3aaa01004428b6` respectively.

The orchestration parent was held while its CUDA training child finished, then
stopped before it could dispatch evaluations. The waiting analysis follower was
cancelled. A first stop-helper attempt hit an exiting-process identity-read race;
that failure and all pre-stop records are preserved. The corrected helper followed
the same live training child without restarting or changing it. Native stop
records are in `v2-recovery-replication-learning-01/user-stop-after-training/`.
Models, checkpoints, failed experiments, qualified worktrees, original study
criteria and closed held-out evidence remain intact. Resume only on a new user
instruction; consume the existing final seed25 model rather than retraining it.

## Completed: borrowing recovery works for frozen weights; retraining regresses

`v2-borrow-guide-study-01` changed only the .001 entropy trial's guide from v2
to v3. Its new option exposes native 10,000 borrowing alongside WAIT when
construction is complete, the first-bus continuation is unavailable, no public
owned vehicle exists and cash is below 10,000. It never forces borrowing or
advances construction on a loan action. The repayment threshold prevents both
loan directions being offered together. Study SHA:
`394f68a1d4e467d0692a3b389dba7f01f53424ac814bcc9b663855240d41f61e`.

The isolated `v2-borrow-guide-01` worktree and original criteria remain intact.
All 144 C++ source files and both native binaries match the qualified entropy
implementation. Qualification passed 92 development tests, whitespace checks,
guide/checkpoint guards and a 128-decision CPU/CUDA frozen-policy pair. Probability
and value differences were 1.19e-7/9.60e-7 within the unchanged 1e-5/1e-4 limits.
Attempt-01's unrelated missing-split test fixture failure is preserved; attempt-02
used the existing main fixture fix. Do not repeat these completed checks.
All 42 retained sampled controls (21,504 frames) lacked a blocked post-construction
state, so v3 cannot alter their masks on those histories. Their original guide
labels and failed criteria are preserved, not relabelled as fresh v3 executions.

Fresh CUDA training and all eighteen final games completed in
`v2-borrow-guide-learning-01`. Training used 8,192 decisions / 128 updates /
64 episodes, eight training maps, horizon 128, rollout 64, signed-log inputs,
entropy .001, gamma .99 and lambda .95. It took 5,061.216 seconds; this is not a
speedup claim. Metrics are finite, behavior replay error and saved-weight reload
error are zero. The final reset checkpoint records update 128, 8,192 transitions
and next episode 64; its bytes and the inference model match their recorded hashes.
Final model SHA:
`50e9d7f5f17d335c1b2723c04fc752a4d43bb4454e6298cccdd9c28d18c5556c`.
Execution SHA:
`cd146fea38adc43cf1a18c1d4f3249625fcefea31e53eaea67b12a4ae8ce9d14`.

**The registered retrained candidate fails advancement.** All eighteen scheduled
512-decision games finished, with zero invalid actions or bankruptcies. The
candidate sustains service in only 1/9 games; the previous .001 weights under an
explicit v3 guide override sustain 9/9. The candidate, control and all full-window
outcomes were inspected. No action was overridden and no intermediate checkpoint
or held-out result was used to select a model.

Sampled means cover all six development games per row (two fixed maps, three
action seeds). The full report includes every retained learned control.

| Controller | Passengers | Operating profit | Cash excluding financing | Sampled service |
| --- | ---: | ---: | ---: | ---: |
| Retrained .001, guide v3 | 359.000 | 1,106.500 | -5,068.500 | 1/6 |
| Frozen .001, guide v3 | 1,230.667 | 4,009.000 | -5,908.500 | 6/6 |
| Previous .001, guide v2 | 889.667 | 3,117.167 | -5,160.000 | 4/6 |
| Previous .01, 8,192 decisions | 1,188.333 | 3,440.000 | -6,477.500 | 6/6 |
| Best retained raw 2,048 model | 1,221.000 | 3,807.000 | -6,110.500 | 6/6 |
| Uniform with public guide | 1,193.833 | 3,682.167 | -6,235.333 | 6/6 |

All three new-model greedy games repay nine 10,000 increments and then WAIT for
503 decisions: zero passengers, profit -484 and cash -1,209. On both development
maps the initial road proposal remains legal and exposed at stage zero, with
WAIT probability .928..981; this is a policy preference failure before construction,
not the old unaffordable-bus stall. All three sampled small-map games never buy a
bus; large-map starts are 227, 211 and 287. Mean capital spending falls to 5,450.
The apparent cash gain of 1,409 versus the .01/8,192 model decomposes into 3,742.50
less capital spending and 2,333.50 less profit; other cash flow stays -725.
`greedy-initial-construction-stall.json` retains complete hashed trace evidence.

The frozen control chooses optional borrowing in four full games: small-map
greedy at 35, sampled at 36/35, and training-map 1871197196 at 27. The small greedy
case buys at 36, starts at 38 and delivers 1,023 passengers / 2,182 profit; the
training case starts at 30 and delivers 791 / 3,281. All four old service failures
are restored. The other five histories do not require recovery. This establishes
the guide's recovery mechanism in these games, not successful retraining.

The complete training audit also regresses: starts 54/64 to 50/64, delivering
episodes 53 to 48, mean passengers 160.031 to 114.156 and mean profit 450.188 to
259.594. Multi-choice WAIT selections rise from 1,547 to 3,077 despite fewer
blocked frames (436 to 188). Independent scalar GAE matches native explained
variance within 4.99e-10, below the unchanged 1e-5 tolerance. This rejects a
return-arithmetic discrepancy, not all possible learning or representation issues.
The first 1,728 decisions / 27 updates exactly match the old v2 control before
recovery can apply. Its first exercised recovery is episode 23 on training map
1871197196: WAIT at 45, borrowing at 46, BUY at 47, START at 62, delivery at 100.
Only two eligible decisions and one borrowing action occur in all training.
The first changed bootstrap is at global step 2,988 because it evaluates the next
mask at 2,989; predictions first differ at 2,989 and actual actions at 2,990.
The prefix, recovery and bootstrap diagnostics are retained in the run.

The frozen-v3 control is a **development lead for a separate training-seed
replication**, not a retroactive pass for this failed candidate. Its point means
exceed all six retained learned controls and uniform. However, the paired profit
and cash advantage over uniform is +326.83 with approximate 95% interval
[-18.82, 672.48]; versus the best retained raw model it is +202.00 with interval
[-120.76, 524.76]. These use three action seeds averaged across two fixed maps
(df=2), not training-seed or map generalization. Next learning work should test
whether this inference-time recovery lead survives independent training seeds
before changing the working playback reference. Keep the retraining failure failed.

The completed driver and analysis follower have exited. Reports are in the
checkout's ignored `runs/2026-09-24/v2-borrow-guide-01/completed/` and
`training-audit/`; `completed-plot/` contains PNG/SVG, plotted data and a passed
visual review. `frozen-control-development-lead.json` records the supplemental
paired comparisons. All eighteen outcome audits pass. No rerun is pending.

A retained development reset also establishes a material representation limit
(`loan-input-inspection-01.json` and `candidate-alias-inspection-01.json`). Borrow
and repay have different uint32 command parameters and priorities, but identical
32-float feature bytes and the same family. Their priorities 4,294,967,294 and
4,294,967,293 both normalize to float32 1.0. The live input reader consumes only
the family word as a separate neural input; the candidate encoder has no row
position embedding. Thus their unmasked scores cannot distinguish direction.
The same snapshot contains feature aliases among 856/1,024 road rows,
765/768 stop rows and 509/512 depot rows, with distinct native parameters.
This is a one-state public-input inspection, not a new gameplay result. The guide
chooses one geometric proposal and excludes joint borrow/repay options, preserving
the validity of this guided comparison. Explicit action-parameter representation
is a concrete unresolved prerequisite for broader unguided geometry/debt claims;
do not mistake successful guided service for learning those distinctions.
No active source, mask, training criterion or model changed for these inspections.

## Completed: matched public guides fail useful MCP service

All twelve registered full games completed and passed native action, mask,
company/tick, privacy and archive audits: four actual LLM games, four uniform
baselines and four proposal-priority baselines. Each has 512 global decisions,
256 actions per company and 65,536 simulation ticks, on two fixed development
maps with swapped MCP roles. The first company is always zero. Geometry comes
from the same public planner; no action is selected or replaced automatically.

**The useful-comparison criterion fails:** the LLM sustains service in zero of
four cases, choosing WAIT on all 1,024 turns. The fixed neural actor sustains
service in all four LLM matches. Both actors deliver zero in all eight scripted
matches. There are zero native errors or bankruptcies. All four model-response
to MCP to native-action audits pass; idle choices are actual model choices.
This is not a general model ranking or a successful competitive economy.

| Map | MCP company | Neural passengers | Neural operating profit | Neural capital | Neural cash excluding financing |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1630856436 | 0 | 1,290 | 4,592 | 7,368 | -3,501 |
| 1630856436 | 1 | 1,421 | 5,272 | 7,368 | -2,821 |
| 155097162 | 0 | 930 | 1,524 | 11,017 | -10,218 |
| 155097162 | 1 | 908 | 1,450 | 11,017 | -10,292 |

Every LLM company delivers zero, earns -4,834 operating profit, spends no capital
and has -5,559 cash excluding financing. The neural means are 1,137.25 passengers,
3,209.50 profit, 9,192.50 capital and -6,708 cash. Its mean cash is 1,149 worse
than the idle LLM despite 8,043.50 greater profit: small-map capital remains
unrecovered. Each neural company sustains positive cargo, operating profit and
cash before capital in all final three windows. Loan principal is excluded from
cash comparisons. These are fixed-model development results, not held-out tests.

The eight scripted matches expose a shared-planner defect. Both guides choose
the same exclusive stop/depot sites, and all sixteen company histories become
permanently blocked by global decisions 12..46. Every outstanding primitive is
either a public road already satisfying the requested bits or a stop/depot owned
by the other company; none remains a current native legal proposal. Stages track
only each guide's own construction. Skipping completed roads alone cannot fix
foreign exclusive sites. This does not establish deliberate sabotage. Read-only
replanning on two blocked large-map snapshots finds currently legal alternatives,
but both actors again choose the same endpoints; no alternative was executed.
Complete diagnosis and the eighth-case supplement remain preserved.

Across the four LLM games, independent response-history sums verify 2,632 model
calls, 7,002.787 model seconds, 21,550,261 processed prompt tokens, 94,344 generated
tokens and zero tool errors. Summed driver wall time is 7,973.975 seconds; tool
sequence differences are not CUDA speedups. Provider charges are zero and
hardware/energy costs are unknown. Both company-zero games repeatedly request
oversized full maps and receive explicit context-limit feedback. The first-case
audit verifies exact compact state and current legal choices still reach the
model before every submission; construction is offered on its first 17 turns.
The small-map company-zero case offers construction for its first 36 turns.
Company-one games instead use 255/256 explicit single-turn waits after their
initial queries. The logs establish the choices, not their internal cause.

Study SHA:
`8c0f5afc6dce9e6a63832b4d7914f1bd6eaeb667cdc092a563ec3aa8fa80d9f3`.
Execution SHA:
`b79865caaa23948c5b43fc1b90eaa845b1674b14ca0870cbf3ddcfddc71c8aa4`.
Neural model SHA:
`8abd3777722a35fdd4b5c0d20093ed05b3dc2518c880db528dbac7f41f44e1a6`.
The frozen source is the isolated `v2-mcp-matched-guide-01` worktree; the optional
matched-guide changes are not integrated into main. All earlier qualification
results remain valid: 16 MCP tests, 102 other development tests, 136 portable
tests, eight-step default parity and four sixteen-step matched native cases.
Do not repeat them without a new change or concern. The fixed neural model's
failed single-company economic criterion remains failed.

The completed driver has exited. Original results remain in
`v2-mcp-matched-guide-economics-01/comparison.json` and `report.md`. The independent
full review checks all 24 company totals and 96 economic windows against native
data. Readable reports, four LLM reviews, baseline diagnoses, and the numerically
verified and visually reviewed PNG/SVG are in the checkout's ignored
`runs/2026-09-24/v2-mcp-matched-guide-01/`. The first crowded-axis chart and the
corrected protocol-wrapper audit attempt are preserved. No failed criterion,
source, prompt, model, held-out result or native action was changed.

## Completed: signed-log neural policy through actual MCP

`v2-mcp-financial-01` closes an adapter gap: `Match.start` previously constructed
its policy with default raw inputs even for signed-log archives. It now validates
training/model preprocessing before creating output, forwards the mode to the
existing PolicyClient, verifies native mode before creating the game, and records
`neural_financial_features`. The C++ reader, company scheduler, public information,
action masks, tools and budgets are unchanged.

Registration SHA:
`3e8650e0db9220362afa664a33f71bf4a9575823140e0d38af5aa698f9bcf91b`.
All four focused tests pass in the separate MCP 2.2.0 environment. The unchanged
actual stdio smoke completes eight global decisions for the budget8192 signed-log
policy and eight for the raw4096 reference. Each company receives four actions;
all native steps are 128 ticks. Saved neural choices agree with native actions,
and all existing stale/pending/read-only/region/wait-budget and archival checks
pass. This is scripted compatibility, not an LLM match or useful economic test.
CPU was explicit for these short inference checks; one separate CUDA trainer
continued within the two-native-job limit. No build or training settings changed.

Main has the adapter and focused tests without staging/commit. The original
adapter and registration are preserved in
`runs/2026-09-24/v2-mcp-financial-01/`; native reports are under the same run name.
The failed policy economic criteria and stronger shared-game comparison remain
open. The qualified raw and signed-log models remain unchanged.

## Continuation update: entropy trial complete; advancement failed

`v2-depot-candidate-audit-01` rejects candidate quota as the missing-depot cause.
Across all 196 absent snapshots, lower-priority farther depots remain exposed;
the source tests every tile/direction before keeping the best 512. The target
therefore fails its native command predicate. The exact command error was not
queried. It was available for 290 depot-stage choices: WAIT 282 times, repayment
eight times. Both development depots stayed legal. No candidate/guide patch was
justified. The diagnosis and control outcomes are retained in docs/PROGRESS.md.

`v2-financial-eight-maps-budget8192-01` completed in the unchanged qualified
`v2-guide-blocked-wait-01` worktree. It resumed the eight-map horizon-128
update-64 checkpoint for another 64 updates / 4,096 decisions, reaching 8,192.
Guide, features, reward, rollout, optimizer and map order remained fixed.
Training took 2,578.36 seconds; all new metrics are finite and replay error is
zero. Final checkpoint: update-000128, next_episode=64.
Model SHA-256: `8abd3777722a35fdd4b5c0d20093ed05b3dc2518c880db528dbac7f41f44e1a6`.
Registration: `a5e26d91a2245897ff213ca0288b2f4c2b9be754adb5a5f44ad372a9ba100d90`.

All 32 additional training episodes start a bus and deliver; mean first START
among started episodes moves from 47.32 to 27.34. All nine final 512-decision
games sustain service with zero invalid actions or bankruptcy. Development
greedy improves 0/2 to 2/2, delivering 1,457/1,028 passengers with operating
profits 5,608/2,028 and cash after capital -2,485/-9,714. Training-map greedy
1871197196 also succeeds: 715 passengers, 2,693 profit, -9,019 cash. All three
start service without pre-service WAIT or construction blockage.

**Advancement fails.** Six sampled means are 1,188.33 passengers / 3,440 profit /
-6,477.50 cash. They improve on the parent but profit/cash remain below uniform
(3,682.17 / -6,235.33) and the stronger learned controls. The paired profit/cash
difference against uniform is -242.17, approximate action-seed 95% interval
[-1,161.94, 677.60]. This is one model and two fixed maps, not training-seed
replication. No failed criterion changed and the policy was not adopted.

The largest remaining loss is not delayed START: the worst large-map sampled
case starts at decision 15, seven decisions earlier than greedy, yet delivers
197 fewer passengers. `v2-budget8192-income-expense-audit-02` rejects expense
dominance. Of the mean 378 sampled-versus-greedy profit gap, lower income
accounts for 274.67 (72.66%) and additional expense for 103.33 (27.34%). Income
per passenger on that map stays about 5.19. One small-map case also delays its
last repayment to decision 510. This is descriptive accounting, not causal
attribution. Audit-01's failed sign assumption remains intact; audit-02 follows
the native income-plus-negative-expenses identity with the same hypothesis.

The registered public-history audit `v2-budget8192-service-history-audit-01`
is complete and rejects extra idling as the explanation for weaker large-map
sampled results. Over decisions 64..511, greedy/seed23/seed24/seed25 mean queues
are 156.46/123.52/94.25/41.38, and mean bus loads 27.59/26.98/24.60/22.83.
Zero-speed-with-queue observations also decrease: 99/97/88/82. All four use the
same public route plan and WAIT throughout this interval. Town populations and
road evolution differ. Lower observed supply is consistent with the delivery
gap, but this is not causal proof or a measure of all generated passengers.
No hidden breakdown fields, held-out results or native reruns were consumed.

`v2-entropy-study-01` registers a fresh 8,192-decision comparison changing only
PPO entropy coefficient .01 to .001. Seed 20260923, eight maps, horizon 128,
rollout 64, signed-log features, guide v2 and all other optimizer settings stay
fixed. The .01 reference and 42 sampled control cases are reused. All nine final
games must complete; advance requires service in all nine, zero invalid actions
and bankruptcy, sampled passenger/profit/cash at least all six learned controls,
and profit/cash above uniform. No intermediate selection or held-out tuning.
Registration SHA: `8b6119ad9eb888b6b2454fb562f400cc38cc274e30872d163acf562361294e9c`.

The new isolated worktree/build are `v2-entropy-01`. Native/Python validation,
TRAINING_INFO and checkpoint compatibility bind the optional parameter. The
build and 35 focused tests pass. All registered native checks pass under
`v2-entropy-checks-01/native`: default CUDA exact parity against an archived
128-decision run, .001 CPU/CUDA agreement (max metric error 2.69e-5 versus the
unchanged 1e-4 limit), .001 CUDA reset recovery with exact logical model/Adam/RNG
state, and wrong-coefficient restore rejection. The bound was 896 new decisions,
max two native jobs/one CUDA trainer. No native qualification job remains active.

Fresh CUDA training completed at `$RL_ROOT/runs/v2-entropy-learning-01`:
128 finite updates, 8,192 decisions, 64 episodes, zero replay error and
5,032.12 seconds. Checkpoint 128 is saved with next_episode=64; final weights
reload with zero output error. Model SHA-256:
`e4cd3ea03a81a50125bbd94ec19c487f962568184144faccaf8f5f39c65af17a`.
All nine final evaluations completed through the Windows
`runs/2026-09-24/v2-entropy-01/experiment.py` driver, also
preserved natively as `orchestrator.py`. Execution registration SHA:
`8f03ead9bc88c31d18961e7467f843c8907d4e9498d5c11bd1cf92fb8a9ff736`.
The driver and `finish_analysis.py` both exited successfully. The economic
report, complete outcome timeline and full training audit have been reviewed.
The first plot had overlapping labels; preserve it. The corrected
`plot-review-02/comparison.png` is visually reviewed with byte-identical numeric
data; `plot-visual-review.json` records the correction and original hashes.
No trial or completed qualification rerun is needed. Preserve the first
implementation script's pattern-mismatch failure. The entropy implementation remains
isolated; main now includes the separately qualified deployment extension.

**Entropy .001 advancement fails.** Sampled service is 4/6 versus .01's 6/6;
development greedy is 1/2 versus 2/2 and training greedy is 0/1 versus 1/1.
All nine games have zero invalid actions or bankruptcy. Sampled means are
889.67 passengers / 3,117.17 operating profit / -5,160 cash, compared with
.01's 1,188.33/3,440/-6,477.50 and uniform's 1,193.83/3,682.17/-6,235.33.
The +1,317.50 cash difference versus .01 consists of 1,640.33 less mean capital
spending offset by 322.83 less operating profit, with other cash flow unchanged.
It does not rescue failed transport. The small-map greedy and sampled seeds
23/24 never buy a bus; seed 25 does. Training-map greedy also never buys a bus.
During training, starts/delivering episodes regress from 63/62 to 54/53 of 64;
blocked decisions rise 152 to 436. This is one training seed; conditional
action-seed uncertainty remains wide. No held-out data was used or gate relaxed.

A separate compatibility extension was prepared during that learning run.
The current raw-only V2 ONNX route rejects the signed-log inputs used by live
learning. `v2-financial-export-study-01` registers exact deployment parity for
the completed budget8192 model, preserving its failed economic gate. Registration
SHA: `a6df985b2fa384392e6f9b012965e1c8d573804a1e7ce6be6241e9399112322c`.
The new `v2-financial-export-01` worktree contains the qualified financial
reader/inference code plus an inference-only graph transform, explicit embedded
preprocessing metadata, package/runtime checks and playback support. Forty-one
focused tests and whitespace checks pass. The native build, archive checks and
byte-identical repeated export plus first 512 archived actions pass. ONNX SHA:
`d0fcdee081fd4c083a002c92c10b67203e2ed70da5cf47e950b11a35231249b6`.
Full five-output checks pass 1,024 archived frames, 64 unmasked recurrent steps
and twelve malformed inputs. Runtime checks pass 256 paired sampled actions,
128 raw regression actions and sixteen rejections. All four full headless games match native actions, guide masks and economic
outcomes; maximum probability/value errors are 4.17e-7/5.25e-6. Both full visible
greedy games match headless transitions and outputs exactly. Both screenshots
were reviewed: native UI/maps render correctly, and balances 17,515/10,286 with
loans 20,000 agree with the recorded economy. All six stages and manual visual
review pass. Final records are under `v2-financial-export-qualification-01` and
Windows `runs/2026-09-24/v2-financial-export-01/completed/`. Original pending-review
records are preserved. The build and qualification followers have exited; no
rerun is needed. CPU deployment/oracles were explicit, never training fallback.

The ten-file deployment patch is now applied to main without staging or
committing. All ten file hashes match the qualified source; preserved originals,
patch and verification are under `integration-preparation/` and
`integration-checks/` on Windows. Main's 102 development tests, all 136 portable tests and git diff --check pass. Updated DEVELOPMENT.md documents both raw and signed-log
playback. This establishes compatibility, not learning adoption; the budget8192
model's failed economic gate and the raw visible reference remain unchanged.

Readable artifacts are under `runs/2026-09-24/v2-eight-map-budget8192-01/`:
`completed/` has the full report, comparison, reviewed plot and source check;
`outcome-audit/`, `training-audit/`, `choice-audit/`, `economic-audit/` and
`service-history-audit/` retain
full timelines and accounting. The driver is experiment.py, preserved natively
as orchestrator.py. Do not relaunch it. Main acquired local commit `67d89ea`
outside this task; the qualified execution source remains exactly equal to the
experiment registration. No commit/stage/push/publish command was issued here.

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
off-drive moves were made. No learning experiment ran during cleanup; the
subsequent diagnosis and active continuation are recorded above.

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
  `Ubuntu-24.04`. Main HEAD now: `67d89ea07e4041db6db62dd91072e9a9e2ba9b35` (observed local commit outside this task; prior HEAD was `6a20f1e`).
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
  **Preserve this qualified worktree.** Main now supports signed-log deployment;
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
reader/distribution/sampler. CUDA ONNX remains rejected; the later signed-log
extension is qualified separately. The
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

All nine entropy games and their analyses are complete; advancement fails.
The completed read-only `v2-entropy-liquidity-audit-01`
finds that after repaying 90,000 and building the depot, the failed small-map
case has 3,862 cash. In every remaining decision 35..512, native BUY_BUS is
absent (not omitted by quota), native borrowing is exposed but excluded by the
guide, and WAIT is the sole allowed action. A native borrowing intervention
now proves restored service in this one history. The bounded one-game diagnostic
completed successfully through
`runs/2026-09-24/v2-entropy-borrow-probe-01/probe.py`, using the unchanged
collector and weights. Registration SHA:
`de82df74b81d1a02ae7888f4c213467909bf3c584d9f023d65174036a0d9baac`.
It replaces
only ACT 35 with exposed borrowing while retaining the original inference input
and hidden-state update. Prefix identity and exactly one override are checked.
The native borrowing command succeeds, BUY_BUS is exposed and chosen at 36,
and the policy starts service at 38. All 512 decisions complete with sustained
service: 1,023 passengers / 2,182 operating profit / -9,560 cash versus
0/-484/-7,305 without intervention. Exact prefix and single-override checks pass;
maximum probability/value differences are 1.19e-7/2.40e-7. Extra bus capital
cost is 4,921, so improved service still leaves cash 2,255 worse in this horizon.
All source/model/reference hashes remain unchanged. Report:
`runs/2026-09-24/v2-entropy-borrow-probe-01/completed/report.md`.
The schedule was revised before registration because the build/paired-oracle
stages had finished. One sequential CPU playback job and this CUDA inference
job shared the two-job budget. Both the probe and playback qualification
have finished. Preserve the earlier idle-only draft; do not relaunch this probe.
This is not learned debt management. The separately versioned v3 guide described
above has completed qualification, training and all eighteen matched games.
Retraining fails; frozen weights recover service. Both reports are reviewed; do
not relaunch the completed driver or analysis follower.

<!-- NEXT_STEP_BEGIN -->
Do not start another experiment without the user's instruction to resume.
Both prospective training seeds have complete final weights and reset checkpoints.
Seed24 fails all eighteen v2/v3 games; seed25's eighteen registered evaluations
were cancelled before launch at the user's request. The old driver and follower
have stopped. A later continuation should consume the existing final seed25
weights and original settings, preserving the stop record and failed seed24 gate.
Do not restart training, select an intermediate model or relax the criteria.

The completed twelve-game MCP study also fails useful LLM service. Preserve its
all-WAIT choices, eight shared-construction baseline failures and four neural
service outcomes. The matched-guide source remains an isolated experiment.
The qualified raw 4,096-decision ONNX policy remains the working visible-play
reference. Signed-log deployment qualifications are complete; do not repeat
them without a new change or unresolved concern. Held-out data stays closed.
<!-- NEXT_STEP_END -->

One independent performance lead is ready for a later bounded experiment:
`$RL_ROOT/runs/v2-tensor-compression-profile-01` measures gzip level 1 versus 9
on 36 retained real tensor files, in three counterbalanced pairs. Median
compression CPU ratio is 17.63x; size grows 1.553x; decompressed bytes are exact.
This is an **in-memory microbenchmark under background load**, not an end-to-end
training speedup. No runtime setting changed. A whole-run matched comparison
is required before adoption; the user handoff request stopped further work here.

The continuation's completed retrospective `v2-reference-timing-audit-01`
attributes 33.55% of the 8,192-decision reference wall time to UPDATE roundtrips,
8.16% to ACT requests and 58.29% to an unattributed remainder. It rejects UPDATE
majority, not the usefulness of optimizing it. These are host timers, not CUDA
kernel profiling; game/REWARD/archival/checkpoint work cannot be separated yet.
Halving UPDATE alone implies only a conditional 1.202x whole-run speedup with
everything else fixed. No native rerun, held-out access or runtime change occurred.

When resuming, inspect the completed comparison and current qualification status
first. Budget8192 and entropy training/evaluation are finished. Keep
learning and development/held-out claims separate. Update
`docs/PROGRESS.md` with actual outputs and material limitations. Read
`docs/PROGRESS_HISTORY_2026-09-23.md` only for a specific older result; it is long.

## Original task's completed handoff verification

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
