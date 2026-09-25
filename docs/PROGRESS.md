# Live OpenTTD development progress

## 2026-09-25: minimum recovery correctness and Vast packaging

Added the opt-in existing-C++ PPO recovery mechanisms, guide v4, exact read-only
probe checks, durable reset-resume records, and portable single-GPU study runner.
The full local minimum correctness bundle passed, including historical equivalence,
CPU/CUDA agreement, probe neutrality and exact 256 versus 128+128 reset recovery.
Read-only investigation traced the earlier A0 agreement failure to float32 norm
accumulation. Prospective protocol 2 applies the qualified FP64 clipping-norm mode
to every arm while preserving all scientific settings and the .0001 bound.
The model, gradients and Adam remain float32; historical mode remains available.
Training/development/held-out execution is packaged but has not run as a full
study. A 1,500 GB persistent volume is the capacity target. The pinned Docker image
built locally and passed actual CUDA execution and launcher refusal checks;
native container qualification is in progress. No paid instance or Git push exists
from this work. See [the evidence record](REFACTOR_2026-09-25_STATUS.md) and
[launch instructions](../deployment/vast/README.md) for checks and remaining limits.


The September 25 review execution is active. The complete coverage and current
verification record is in [REFACTOR_2026-09-25_STATUS.md](REFACTOR_2026-09-25_STATUS.md).
Missing V2 options are integrated and match original/retained behavior exactly
on each device. The historical CPU/CUDA gradient-norm failure remains retained;
the prospective numerical correction passes the original bound. Offline reward/time
audits are complete; new recovery tuning has not started. This work resumes under
the new refactor goal; the historical stopped study below remains preserved.
V1 replay and kernel checks now pass in reference/fused builds and real-game
comparisons. V2 reset recovery and checkpoint rejection pass on CPU/CUDA. Host
sanitizer instrumentation is unavailable. The entropy study's failed advancement
has been independently reproduced from 51 hashed cases; full-map registrations
are frozen before tuning. All three comparison reports now preserve historical
statistics while adding per-map/seed/window and paired nested results. Native V2
evidence verification, explicit control modes and development-default inference
are tested. The retained-data estimate is about 41-42 sequential hours (a lower
bound) and 654-656 GiB for the mandatory recovery study, nearly filling Linux
storage before any held-out confirmation. The portable runner now includes the
execution/held-out safeguards and recovery mechanisms and requires a larger
persistent volume. Broader profiling and the registered learning study remain
pending; no new recovery tuning or held-out game has run. Evidence and failed
attempts are in the refactor status linked above.

The horizon-256 run, requested lossless storage cleanup and missing-depot
diagnosis are complete. The 8,192-decision continuation sustains service in all
nine final evaluations and fixes all three greedy stalls, but fails its sampled
economic advancement criteria. The subsequent fixed-budget entropy .001 trial
is complete and regresses service to five of nine cases; advancement fails.
The borrowing-guide retraining also fails (1/9 service), while frozen weights
with the new guide restore 9/9 service and provide a lead for independent replication.
The twelve-game MCP study also fails useful LLM service; all full outcomes
are reviewed below. The first prospective replication seed fails all eighteen service cases. Both
new training runs are complete; the second seed is unevaluated after the user-requested stop.
V1 has demonstrated reproducible sampled bus play;
strong live V2 neural control is the current blocker. Frozen release contracts,
held-out selection rules and the user's ordinary game data remain untouched.
Use [DEVELOPMENT.md](DEVELOPMENT.md) for commands. Detailed prior results and
failed attempts are preserved in [the history](PROGRESS_HISTORY_2026-09-23.md).
Run names below are under `~/.local/share/openttd-rl/runs/` in Ubuntu-24.04.
Readable copies are in the checkout's ignored `runs/2026-09-23/` and `2026-09-24/`.

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

## Completed: lower entropy regresses service

`v2-entropy-study-01` tests one change: native PPO entropy coefficient .01 to
.001 at a fresh, fixed 8,192-decision budget. Registration SHA-256 is
`8b6119ad9eb888b6b2454fb562f400cc38cc274e30872d163acf562361294e9c`.
The .01 reference's greedy profit exceeds its sampled profit, and the public
history audit below does not support extra late-game idling. Lower entropy may
concentrate early choices, but could instead reduce useful exploration or make
bad choices more confident. This is a test, not a causal conclusion.

Seed 20260923, eight maps, horizon 128, rollout 64, 128 updates, signed-log
features, guide v2, gamma .99, lambda .95, four epochs, BPTT eight, bootstrap
reuse and checkpoint interval eight remain fixed. Inference keeps the ordinary
softmax sampler. Only the final model receives the usual nine 512-decision
evaluations. Forty-two completed sampled control games are reused. Advancement
requires all nine service cases, zero invalid actions/bankruptcy, sampled
passenger/profit/cash means at least all six learned controls, and sampled
profit/cash strictly above uniform. A pass still needs training-seed replication.
No intermediate selection, held-out access or relaxed failed criterion is allowed.

The isolated worktree `v2-entropy-01` was reconstructed exactly from the qualified
`v2-guide-blocked-wait-01` source before adding the optional parameter. Main and
the original qualified worktree are preserved. Native/Python argument validation,
effective-configuration reporting and checkpoint compatibility now bind the
coefficient; native checkpoint identity already contained it. The native build
passes with compiler parallelism two, as do 35 focused tests and whitespace
checking. Source/build records are under `v2-entropy-source-01` and
`v2-entropy-checks-01`. The first implementation-script pattern mismatch was
retained; the corrected change touches seven files only in the new worktree.

Native qualification **passes** over the registered 896 new decisions. Sixteen
zero-update CLI cases pass. Omitted/default .01 exactly reproduces 128 archived
CUDA decisions, both PPO updates, final weights and logical checkpoint state.
The .001 CPU/CUDA pair matches all 128 decisions, six time limits and seven
recurrent resets; maximum metric difference is 2.69e-5, below the unchanged
absolute 1e-4 tolerance. CUDA recovery exactly matches 256 versus 128+128
decisions, metrics, final weights and all 66 model/Adam states plus native/Torch
RNG, hidden state and counters. Python and native cross-coefficient restore
reject; the native identity guard precedes model/optimizer loading. No expected
checkpoint hash or manifest was edited. CPU was an explicit correctness oracle.
Reports are under `runs/2026-09-24/v2-entropy-01/qualification/`.

The qualified fresh CUDA run `v2-entropy-learning-01` completed training and all
nine final evaluations with effective coefficient .001. Training
took 5,032.12 seconds for all 128 updates / 8,192 decisions and 64 episodes.
Every update is finite with zero behavior-replay error. Checkpoint 128 records
next_episode=64, and saved inference weights reload with zero output error.
Final model SHA-256:
`e4cd3ea03a81a50125bbd94ec19c487f962568184144faccaf8f5f39c65af17a`.
**Registered advancement fails; the policy is not adopted or replicated.**
Its execution registration is
`8f03ead9bc88c31d18961e7467f843c8907d4e9498d5c11bd1cf92fb8a9ff736`;
trainer SHA-256 is
`d7ad7d310034c868d0df2f6692df75f7a918189ef321086607ce0d17e314872a`.
The driver captured source/binaries, revalidated all 42 control traces, ran one
CUDA trainer, then at most two evaluations concurrently. All nine final cases
completed, with zero invalid actions or bankruptcy. The completed-run report,
full outcome timelines and training-choice/GAE audit are reviewed. Both full
8,192-decision training histories reproduce their native explained variance
within 4.96e-10. Drivers and readable results are in
`runs/2026-09-24/v2-entropy-01/`; no trial or qualification rerun is needed.

The experiment and `finish_analysis.py` follower both exited successfully.
Their complete execution records and frozen scripts remain under
`v2-entropy-learning-01/analysis-execution/`. Visual inspection found overlapping
category labels in the first plot; that original is retained. The presentation
revision `plot-review-02/comparison.png` is visually reviewed and has byte-identical
plot data. `plot-visual-review.json` records both images and the correction;
the original pending-review status records are also preserved.

Sampled service falls from 6/6 to 4/6 versus entropy .01 at the same budget.
Development greedy falls 2/2 to 1/2; training-map greedy falls 1/1 to 0/1.
The larger development map's greedy result is 1,433 passengers / 5,969 operating
profit / -2,124 cash. The smaller greedy map and its sampled seeds 23 and 24
deliver none / -484 profit / -7,305 cash; none buys a bus. Sampled seed 25
recovers ordinary service: 1,449/5,569/-2,524 on the larger map and
1,023/2,164/-9,578 on the smaller. Training-map greedy 1871197196 also never
buys a bus: zero passengers / -484 profit / -7,275 cash.

Across all six sampled games, means are **889.67 passengers / 3,117.17 operating
profit / -5,160 cash**. Reference .01 gives 1,188.33/3,440/-6,477.50; uniform
gives 1,193.83/3,682.17/-6,235.33. Profit differences are -322.83 versus .01
(action-seed interval [-2,720.92, 2,075.25]) and -565 versus uniform
([-2,171.62, 1,041.62]). These are conditional on one model and two maps,
not training-seed or map generalization. Better cash does not rescue failed
transport: the +1,317.50 cash difference versus .01 decomposes into 1,640.33
less mean capital spending offset by 322.83 less operating profit; other cash
flow is unchanged at -725. Failed games avoid purchasing buses.

During training, 54/64 episodes start service and 53/64 deliver, versus 63/64
and 62/64 for .01. Mean passengers fall 190.61 to 160.03 and blocked decisions
rise 152 to 436. Familiar map 1871197196 starts/delivers in only 4/8 visits.
The failure is therefore not confined to unfamiliar evaluation geometry.

The retrospective public-candidate diagnostic `v2-entropy-liquidity-audit-01`
(registration `32dea0bc114598381ed9f591ed6f0aea37712f2d7be076299cdff1c67475ecdf`)
accepts all 478 registered snapshots, decisions 35..512 of the completed failed
game. Nine initial repayments remove 90,000; cash is 3,862 after depot construction.
Every subsequent frame has zero native BUY_BUS candidates, including zero
omitted by quota, and an exposed native 10,000 borrowing action excluded by
the guide. WAIT is the only guided action and is chosen throughout. Thus this
tail is not a voluntary refusal of an available guided purchase. The .01
reference buys the same engine/depot for 4,921 with 13,712 available, but its
history differs. At this audit stage, no native borrowing intervention or failed-command query
had established that cash was the only purchase blocker; the subsequent probe
below tests recovery directly. All inputs stayed byte-identical; no guide, policy, failed
criterion or active run changed. Readable evidence is under
`runs/2026-09-24/v2-entropy-liquidity-audit-01/completed/`.

The single-action recovery probe `v2-entropy-borrow-probe-01` **passes**,
registration SHA `de82df74b81d1a02ae7888f4c213467909bf3c584d9f023d65174036a0d9baac`.
Its driver is `runs/2026-09-24/v2-entropy-borrow-probe-01/probe.py`. It runs one
new 512-decision game against the retained failed greedy control. Only ACT 35
changes from WAIT
to an already-exposed native 10,000 borrowing action; the original guided input,
neural prediction, recurrent update and all subsequent policy choices stay in
the existing collector. It requires exact first-34 transitions and first-35
tokens/candidates/guide decisions, the established output tolerances, precisely
one override, restored native BUY_BUS availability at 36, and sustained service.
Its run metadata explicitly marks a counterfactual. All 512 decisions and prefix
checks pass: first 34 transitions and first 35 tokens/candidates/guide decisions
are exact, with maximum probability/value errors 1.19e-7/2.40e-7. There is exactly
one successful borrowing override. BUY_BUS becomes available and is selected at
36; route and START follow at 37/38. First delivery is at 81. Final results are
**1,023 passengers / 2,182 operating profit / -9,560 cash**, versus 0/-484/-7,305
without intervention. All final three windows sustain profitable service; invalid
actions and bankruptcy remain zero. Buying the 4,921 bus improves operating
profit by 2,666 but worsens cash after capital by 2,255 over this horizon.
All source/model/reference hashes remain unchanged. Full report:
`runs/2026-09-24/v2-entropy-borrow-probe-01/completed/report.md`.
The scheduling plan changed before registration after confirming that the
deployment build and paired oracles had completed: one sequential CPU playback
job may run alongside this CUDA inference job, staying within two native game
jobs. Exact concurrent process/parent identities are recorded. No training,
new build or additional native checks were started while both ran. The probe is
now finished; the earlier idle-only draft is retained. This establishes recovery
from that state/history, not learned borrowing or economic advancement. The next
learning hypothesis is to expose the same native borrowing action as an option
alongside WAIT in a separately versioned guide, then test actual policy choices
and complete outcomes with matched baseline masks. The failed entropy gate stays
failed.

## Completed: signed-log ONNX compatibility extension

A read-only acceptance review found a concrete lifecycle gap: current live
learning uses `signed-log-v1`, while the otherwise qualified V2 ONNX converter,
package checks and runtime accept only raw features. The completed budget8192
policy starts service in all nine cases but cannot use that portable deployment
route. Its failed sampled economic gate remains failed.

`v2-financial-export-study-01` registers a compatibility-only extension, SHA
`a6df985b2fa384392e6f9b012965e1c8d573804a1e7ce6be6241e9399112322c`.
It uses the completed budget8192 weights
`8abd3777722a35fdd4b5c0d20093ed05b3dc2518c880db528dbac7f41f44e1a6`,
not intermediate entropy weights. The isolated `v2-financial-export-01` worktree
reconstructs main exactly before porting three qualified financial reader/native
inference files byte for byte. The inference-only converter now embeds the same
signed-log transform on structured cash/loan, company financial columns and
candidate cost. Raw public tensors enter the ONNX graph; the native runtime does
not apply the transform again. Package/training/model modes must agree, and
signed-log metadata explicitly binds embedded preprocessing. Raw defaults and
the original qualified raw package are retained. No PPO or training changes are
part of this extension; the active entropy worktree/build/run are untouched.

Forty-one focused Python tests and whitespace checks pass, including four new
preprocessing compatibility checks. The three native targets built successfully
with compiler parallelism two. Archive qualification accepts raw and signed-log
66-tensor models and rejects all eleven mismatched/malformed archives and four
bad argument cases; original weights remain unchanged. Repeated signed-log ONNX
exports are byte-identical (model SHA
`d0fcdee081fd4c083a002c92c10b67203e2ed70da5cf47e950b11a35231249b6`).
All first-map 512 archived actions match, with maximum probability/value errors
4.17e-7/4.77e-6. Offline qualification also passes both full histories (1,024
frames, all five outputs), 64 unmasked recurrent steps and twelve malformed
input rejections. The adapter matches the native CPU oracle exactly on those
full histories; ONNX remains within the registered tolerances. Runtime checks
pass 256 paired sampled actions, 128 unchanged raw-policy regression actions,
and sixteen rejection cases. All four fresh 512-decision headless games match
the original native actions, complete guide records and economics. Maximum
probability/value errors are 4.17e-7/5.25e-6. Both 512-decision visible greedy
replays match headless outputs and transitions exactly. The native 1280x800
screenshots were manually reviewed: maps/UI render normally, bank balances
17,515/10,286 and loans 20,000 agree with the recorded economy.
**All six deployment stages and visual review pass.**
The registered checks retain the existing probability 1e-5 and other-output
1e-4 tolerances: both archived 512-step greedy histories, unmasked recurrent and
reset cases, malformed/mismatched-input rejection, a raw 128-step regression,
four fresh headless ONNX games and two visible greedy games with screenshots.
Repeated exports must have identical bytes. This proves compatibility only;
no stronger play, economic advancement or GPU deployment claim follows.

Source preparation/change records are in `v2-financial-export-source-01`.
The build and qualification followers have completed; do not relaunch them.
Final verification and manual screenshot review are retained under
`v2-financial-export-qualification-01`, with Windows copies in
`runs/2026-09-24/v2-financial-export-01/completed/`. Original pending-review
records remain preserved. The ten qualified deployment files have been applied
to main without staging or committing, and all ten hashes match the isolated
source. Original main files and the exact patch remain in
`integration-preparation/`; main verification is recorded in
`integration-checks/`. All 102 main development tests pass. All 136 portable tests and git diff --check also pass. The raw package and failed learning criteria remain unchanged.

The new replay comparator checks every guide field, normalizing only the run's
absolute storage root. A read-only applicability check matched all 1,024
candidate/guide records in the two retained raw headless/visible episodes. This
validates the stricter comparison procedure without rerunning games or claiming
signed-log deployment parity. The guide, route, tensor archival and economic
summary helpers are byte-identical to the financial model's qualified source;
the bridge difference is the already qualified optional view-only SDL path.

## Completed: public service-history audit rejects extra idling

`v2-budget8192-service-history-audit-01` compares the saved large-map greedy
case with all three sampled cases. Registration SHA-256:
`fffb58c35982b13d2e94c23122286d34115936ce96f2b5f6c151b03d7ccc399b`.
It verifies every public state token and economic observation against all four
512-decision traces. No native game reruns or private/redacted fields are used.
The hypothesis required both weaker sampled cases to have more running,
zero-speed observations with queued passengers and at least the greedy mean
queue during decisions 64..511. **Both conditions fail; the hypothesis is rejected.**

| Large-map case | Final deliveries | Mean station queue | Zero-speed observations with queue | Mean bus load |
| --- | ---: | ---: | ---: | ---: |
| Greedy, seed 23 | 1,457 | 156.46 | 99 | 27.59 |
| Sampled, seed 23 | 1,448 | 123.52 | 97 | 26.98 |
| Sampled, seed 24 | 1,322 | 94.25 | 88 | 24.60 |
| Sampled, seed 25 | 1,260 | 41.38 | 82 | 22.83 |

All use the same public route plan, retain a running bus and choose WAIT from
decision 64 onward. Weaker cases have lower queues/loads and higher mean speed,
not extra observed idling. Mean station ratings remain about 147–151. Final town
populations and road-network hashes differ despite identical initial towns and
route plan. This is consistent with different passenger supply after early
action differences, but does not prove a causal mechanism. Delivered+waiting+
onboard cargo is not total generation; whole-town population is not catchment
population. Coarse 128-tick observations cannot separate loading, traffic and
breakdowns. Hidden breakdown countdown/delay fields remain excluded. Reports
and the four reduced public histories are in the budget8192 Windows run's
`service-history-audit/`; original observations and hashes remain native.

## Completed: eight-map horizon-128 budget extension

v2-financial-eight-maps-budget8192-01 resumes the qualified eight-map
horizon-128 update-64 checkpoint, preserving native model, Adam and RNG state.
It adds 64 updates / 4,096 decisions, reaching 128 updates / 8,192 decisions and
eight visits per training map. Source, binaries, map order, signed-log features,
guide version 2, reward, rollout 64, gamma .99, lambda .95 and optimizer settings
are fixed. The hypothesis is that four more construction/initiation visits per
map can resolve the greedy stalls; more experience could also reinforce them.

Registration SHA-256:
`a5e26d91a2245897ff213ca0288b2f4c2b9be754adb5a5f44ad372a9ba100d90`.
All checkpoint/source/contract/binary identity checks passed before launch.
The native CUDA trainer resumed at update 65 / decision 4,160 and completed
update 128 / decision 8,192 in 2,578.36 seconds. All 64 new updates are finite
with zero behavior-policy replay error. The final reset checkpoint has
next_episode=64. The final inference model hash was independently verified:
`8abd3777722a35fdd4b5c0d20093ed05b3dc2518c880db528dbac7f41f44e1a6`.
The driver passed its complete continuation checks and launched evaluation.
Training completion alone does not satisfy learning advancement.

The final model alone received nine full 512-decision cases: two development
greedy, six development sampled (two maps crossed with three action seeds), and
one greedy diagnostic on training map 1871197196. Thirty-six completed sampled
controls are reused after native trace/hash and full economic-summary checks;
no completed game evaluation is repeated. Advance requires all nine cases to
sustain service with zero invalid actions/bankruptcy, sampled passenger/profit/
cash means at least all five learned controls, and sampled profit/cash strictly
above uniform. Failed earlier criteria remain failed. No intermediate selection
or held-out use is allowed; a pass still requires training-seed replication.

Execution uses the unchanged qualified `v2-guide-blocked-wait-01` worktree and
`v2-financial-features-02` native trainer/inference binaries. One CUDA training
job runs first; at most two evaluations run after it exits. Registration,
source capture, logs and evolving `comparison.json` are in the native run;
the driver is `runs/2026-09-24/v2-eight-map-budget8192-01/experiment.py` in the
Windows checkout. Training and all nine evaluations are finished; no native
job from this experiment remains active. Preserve the final model and checkpoint.

The final economic report, visually reviewed seven-controller plot and completed
training choice/GAE audit are complete beside the driver. `audit_outcomes.py`
records all nine full
action timelines and four-window outcomes, separating choice WAIT, forced WAIT,
construction blockage, bus purchase, routing and START. Its joins match all
4,608 decisions in the previous nine saved games and reproduce the diagnosed
196 blocked decisions starting at 317. This validates the new read-only analysis,
without rerunning any native qualification or inspecting unfinished evaluation
outcomes. Full-game reports wait for the complete registered comparison;
training-only audits require completed training.

The completed-training audits are now available. All 32 new episodes buy, route
and start a bus and deliver passengers, versus 31 starts and 30 delivery episodes
in the parent. Mean first START among started episodes moves from 47.32 to 27.34;
mean training deliveries increase from 161.28 to 219.94. All four new visits to
expensive training map 1871197196 deliver. The added experience contains 853
choice decisions and 3,243 forced WAITs, versus 1,590 choices in the parent;
31/64 new rollouts contain no choice. All 32 START actions have mean normalized
advantage +.4167, with 26 positive, versus 12/31 positive in the parent. Native
explained variances agree with independent target reconstruction within 4.8e-10.
These changing-policy training results do not establish final-policy strength
or a causal credit mechanism. Both periods retain 76 temporarily blocked
construction steps on training map 583478638; they do not prevent those episodes
from starting service. Full accounting and per-map data are in `training-audit/`
and `choice-audit/` beside the Windows driver. All 64 compared episode boundaries
retain time-limit bootstrap and stop GAE continuation across resets.

All nine full games complete with sustained service, zero invalid actions and
zero bankruptcy. Development greedy improves 0/2 to 2/2: map 1630856436 delivers
1,457 passengers / 5,608 operating profit / -2,485 cash after capital, and map
155097162 delivers 1,028 / 2,028 / -9,714. The expensive training-map greedy case
also improves from no service to 715 / 2,693 / -9,019. Greedy START occurs at
decisions 22, 36 and 28 respectively, with no pre-service WAIT or construction
blockage in any of the three. These results establish service initiation for
this one model under the public route guide, which still supplies geometry.

**Registered advancement fails.** All six sampled episodes sustain service,
but their means are 1,188.33 passengers / 3,440 operating profit / -6,477.50 cash
after capital. They exceed the parent eight-map trial (1,144.83 / 3,062.83 /
-6,854.67), while profit/cash remain below horizon 256, raw 2,048, raw 4,096,
four-map signed-log and uniform (1,193.83 / 3,682.17 / -6,235.33). Paired
profit/cash difference is +377.17 against the parent, approximate 95% interval
[-584.41, 1,338.74], and -242.17 against uniform, [-1,161.94, 677.60]. These
three-action-seed intervals condition on one model and two maps; they do not
measure training-seed or map generalization. No replication or deployment
adoption is claimed, and no failed criterion is changed.

The remaining economic failure is not simply slower initial service. On map
1630856436, the worst sampled case starts at decision 15 with no pre-service
WAIT, yet delivers 1,260 passengers / 4,485 profit, versus greedy START at 22
and 1,457 / 5,608. Sampled repayment/construction timing and native income versus
expense need separate accounting before another learning change. Full nine-case
timelines and four-window outcomes are in `outcome-audit/`; the report, exact
checks, paired differences and reviewed plot are in `completed/` beside the driver.

The follow-up `v2-budget8192-income-expense-audit-02` rejects expense dominance:
the sampled-versus-same-map-greedy mean profit shortfall of 378 consists of 274.67
lower income (72.66%) and 103.33 additional operating expense (27.34%). On map
1630856436, income per passenger stays about 5.19, so lower delivery quantity is
the larger issue. On the other map, action seed 25 postpones its eighth repayment
until decision 510, with 459 additional operating expenses despite 26 more
passengers than greedy. These totals do not attribute all expenses to interest
or causally explain service differences. This unblinded retrospective audit uses
all six sampled and both greedy full games and no held-out evidence. Audit-01's
failed identity assumption is retained: native expenses are signed negative and
the pinned source defines operating_profit=income+expenses. The corrected audit
keeps its hypothesis and majority threshold; no learning criterion changes.
Report/registration: `economic-audit/` beside the driver.

Next inspect retained public station cargo/ratings, vehicle movement and delivery
timing on the large map to distinguish weaker service from lower passenger supply.
Do not consume redacted breakdown delay/countdown fields or alter the guide,
reward or curriculum based on the aggregate income gap alone. No new training
experiment is registered yet. Main now points to local commit `67d89ea`, created
outside this task; the isolated execution source still exactly matches the
trial registration. The source-identity check is in `completed/source-preservation.json`.

## Completed: missing-depot diagnosis

v2-depot-candidate-audit-01 reads all 512 saved observations in the three
horizon-256 greedy cases without rerunning a game. Its registered clear-site/
candidate-quota hypothesis is **rejected**. The expensive training map's depot
tile 3096 starts clear and flat, becomes road after decision 304, remains an
exposed depot through the observation after decision 315, and disappears after
decision 316. The largest-town priority anchor is unchanged. Every one of the
196 absent snapshots still exposes strictly lower-priority depots farther from
that anchor. The native enumerator tests every tile/direction and retains the
best 512 successful tests, so quota cannot explain omitting this target if it
were legal. Its native command predicate must fail. This is a source-and-snapshot
inference; the exact road-removal error has not been directly queried.

The learner had 290 depot-stage decisions with the depot available (27 through
316), choosing WAIT 282 times and repayment eight times. Immediately before the
depot disappears, WAIT probability is .84794414 and depot probability .152055904.
Only decision 317 onward is forced WAIT. Both development depots remain legal
throughout their 512-decision failures. Prolonged neural waiting precedes the
training-map blockage; the evidence does not justify a quota or guide patch.

Full saved outcomes on the same training map are rederived from all 512 native
transitions and checked against trace hashes:

| Controller | Passengers | Operating profit | Cash after capital | Sustained service |
| --- | ---: | ---: | ---: | --- |
| Horizon-256 greedy | 0 | -1,184 | -7,225 | no |
| Build first | 758 | 2,632 | -9,080 | yes |
| Repay eight first | 715 | 2,760 | -8,952 | yes |
| Repay nine first | 0 | -484 | -7,275 | no |
| Repay and WAIT | 0 | -484 | -1,209 | no |

All finish with zero invalid actions/bankruptcy. These are descriptive controls,
not a counterfactual isolation of action timing. Priority witnesses, per-state
hashes, registration, timelines and limitations are retained in the native run
and `runs/2026-09-24/v2-depot-candidate-audit-01/` on Windows. No held-out results
were consulted. The diagnosis permits the already suggested fixed-settings
budget extension; it does not establish that more exposure will work.

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

Storage cleanup has not changed any failed advancement criterion or learning
setting. The subsequent diagnosis and registered continuation are recorded above.

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

The user requested pausing after this run and moving to a new chat. The original
task stopped at that boundary; the continuation task's later work is recorded
above. [The handoff](../handoff.md) and
[continuation prompt](../continuation-prompt.md) identify source/worktrees,
reproduction commands, qualified deployment, failures, and the recommended next
bounded diagnostic. The completed diagnosis now distinguishes the blocked
training depot from the available-but-rejected development depots; the later
horizon-128 budget extension subsequently completed with 9/9 service but failed
economic advancement criteria; see its completed section above.

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

The retrospective `v2-reference-timing-audit-01` rejects the hypothesis that
PPO UPDATE roundtrips dominate the completed 8,192-decision reference's recorded
wall time. Registration SHA is
`897864ef530ee489531cfc2ca4c4733f0d369e079954ab8fc0ef3487ce7b552e`.
Both run/metrics records and all 8,192 trajectory rows agree; input hashes remain
unchanged. Across 5,100.77 seconds, UPDATE accounts for 1,711.28 (33.55%), ACT
requests for 416.34 (8.16%), and the unattributed remainder for 2,973.15 (58.29%).
UPDATE is host roundtrip time including CPU/CUDA work and replay validation,
not GPU kernel time. Initial source capture is outside the wall timer; REWARD,
game requests, archival, checkpoints and resets have no separate attribution.
Native response emission precedes some UPDATE cleanup. Halving UPDATE alone
would imply a conditional 1.202x whole-run speedup, with an ideal zero-cost
UPDATE bound of 1.505x if everything else stayed fixed. No speedup was measured.
This used completed development records only and does not change the live trial.
Readable results: `runs/2026-09-24/v2-reference-timing-audit-01/completed/`.

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
recovery remains unsupported. Live V2 ONNX export and visible playback were
subsequently qualified for the raw-feature reference policy, as recorded above.

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
