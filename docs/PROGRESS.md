# Live OpenTTD development progress

Active objective: reliable, economically useful neural play, followed by broader
live V2 gameplay and reproducible MCP competition. **The overall goal is not
complete.** The preregistered V1 held-out confirmation passed; its results cannot
drive tuning. V2 longer rollouts improve sampled outcomes modestly, but still
fail greedy service; a broader training-map diagnostic is running. Frozen release
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
full-training speedup. The real learning collector is unchanged; adoption still
requires native PPO/model/checkpoint equivalence and isolated end-to-end timing.
Windows runs/2026-09-24/v2-snapshot-cache-01/completed retains the readable report.

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
v2-guided-sixteen-maps-32u-02 is now running with setup-amended registration
1a7fc505e9c349078bdd9dc9cb3dd11382b70f812118b54214c2781004edb34d.
It resumes the verified update-8 checkpoint and collects 24 further updates,
retaining the same 2,048 model-training decisions and unchanged gameplay criteria.
The failed trial's 332 additional decisions are unused diagnostic overhead.
Its four full development evaluations follow training automatically.

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
training-map seeds are used. The older M22 corpus path is a separate capability.

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
