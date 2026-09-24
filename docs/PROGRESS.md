# Live OpenTTD development progress

The continuous goal is active. V1 has demonstrated reproducible sampled bus play;
strong live V2 neural control is the current blocker. Frozen release contracts,
held-out selection rules and the user's ordinary game data remain untouched.
Use [DEVELOPMENT.md](DEVELOPMENT.md) for commands. Detailed prior results and
failed attempts are preserved in [the history](PROGRESS_HISTORY_2026-09-23.md).
Run names below are under `~/.local/share/openttd-rl/runs/` in Ubuntu-24.04.
Readable copies are in the checkout's ignored `runs/2026-09-23/` and `2026-09-24/`.

## Current iteration: optional financial input scaling

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

v2-financial-features-learning-01 is now training from scratch for a fixed
4,096 decisions (64 updates of 64, seed 20260923, four training maps, horizon
128, lambda .95, existing reward/guide, qualified tensor reuse). It will run
two greedy and six sampled full development episodes, without intermediate
model selection. Advancement requires service in all eight, sampled passenger/
profit/cash means at least both old raw-input models, profit/cash above uniform,
and zero invalid actions/bankruptcy. Only passing that test permits replication
across training seeds. No held-out evaluation is involved.
Registration: cc5025ac410aed7cc7ae9abd2a15092840b36b8cd096c0cb1638a47a381fbc55.

While that fixed trial runs, v2-visible-playback-01 is preparing an independent
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
execution. Full visible replays are pending until the financial
trial and its two evaluation jobs finish, preserving the global concurrency cap.
This does not change the training trial or its engine. Reports/image:
v2-visible-playback-01/smoke-completed on Windows. No full replay claim yet.

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
