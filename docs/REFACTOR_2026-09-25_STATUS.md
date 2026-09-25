# September 25 refactor execution status

Goal: [complete refactor and PPO recovery](REFACTOR_GOAL_2026-09-25.md).
Review: `9/25 refractor/`, fetched at `ec5a3f6`; reviewed source was `0595a72`.
Execution starts from `8ffc5bd` on `codex/local-training-foundation`.
The first implementation checkpoint is local commit `c8f585b`; nothing was pushed.
All eleven original reports were read. This is an implementation record, not a
replacement for their requirements or a claim that their static findings passed.

## Current state

- **Active; incomplete.** Successive goal turns are making implementation progress.
- Existing current-branch source is newer than the review in documentation and
  ONNX/visible inference support. The missing V2 training options are now integrated.
- WSL Ubuntu 24.04 is available; RTX 2070, 8 GiB, driver 610.88, approximately
  674 GiB free on Linux and 323 GiB on the Windows volume at initial inspection.
- Historical Linux worktrees exist. Windows Git's `prunable` labels reflect Linux
  paths; these worktrees must not be pruned. No training process was found running.
- No held-out games have been accessed, new tuning study launched, or source pushed.

## Immediate scope: correctness and portable Vast package

The owner narrowed this handoff to minimum correctness gates and a portable
single-GPU registered-study package, leaving paid execution and publication for
later. The broader refactor remains active and incomplete.

Implemented recovery Steps 0-3: opt-in choice-weighted loss/normalization through
the existing C++ PPO, finite clipped-capital history potential, guide-v4 repayment
only after START, diagnostics and read-only eight-map reset probes. The historical
default UPDATE fields are preserved unless diagnostics are enabled. Native loss
oracles cover all/zero/one/mixed choices, malformed weights, clipping, constant
advantages and shared-trunk/Adam behavior. Measured zero-policy-loss actor-head
momentum drift is .000670058, trunk drift .000999077 and policy-logit drift
.000428992 on both tested devices; the implementation does not claim no actor drift.

`refactor-recovery-core-03/verification.json` passed exact probe neutrality on CPU
and CUDA, including actions, native updates, weights, RNG and Adam state (276/277
fields). LibTorch Adam archive bytes contain process-local pointer keys; the
comparison resolves parameter-group ordering and checks every state value exactly.
Attempt 02 correctly failed its initial raw-archive comparison and remains retained;
attempt 01 was interrupted. Cross-device maximum update difference is
2.2659999999952163e-05, below the unchanged 1e-4 bound. This does not resolve the
separate older guide-v3 discrepancy recorded below.

`refactor-recovery-resume-{cpu,cuda}-01/verification.json` passed 256 uninterrupted
versus 128+128 resumed decisions under guide v4, choice-weighted loss and potential.
Actions, rewards, native traces, metrics and final weights match exactly on each
device. Potential telescoping tests pass to 1e-9, preserving truncation versus true
terminal semantics. The refreshed native build is `refactor-recovery-01`.

The package provides a pinned CUDA/Torch Dockerfile, persistent-volume launcher,
source/build/runtime qualification, immutable arm registration, sequential training,
resume journals, complete development scheduling and matched control reuse, and
held-out permits after all mandatory arms finish. It preserves failed/stopped seeds,
rejects changed inputs, gates disk capacity before work, and consumes held-out
reservations once even after interruption. The frozen protocol is unchanged.
The final package gate found a separate **A0 CPU/CUDA failure** in
`refactor-package-qualification-01/default/verification.json`: second update
pre-clipping gradient norms 3.07306422 (CPU) and 3.07318368 (CUDA), difference
.00011946 against the fixed .0001 limit. All 128 native transitions match; value
error is at most 1.013e-6 and every other compared update metric is below the bound.
`refactor-a0-numeric-audit-01/comparison.json` retains per-metric differences and
input hashes with status **failed**. Numeric comparisons now write their failure
report before raising. The gate remains mandatory; registration cannot bypass it.
This means minimum qualification is **not complete** and the package must not be
called ready for training. Exact default/reference CPU and CUDA comparisons and
the default CPU/CUDA agreement passed within the same failed aggregate run.
`refactor-a0-reference-01/verification.json` then confirmed exact old/new A0
actions, metrics and final weights on **both CPU and CUDA**, reproducing the
cross-device discrepancy in the unchanged pre-recovery binary. It is a retained
baseline numerical limitation, not evidence of a newly introduced loss defect.
The fixed gate still fails; neither the tolerance nor registered arm was changed.
The refreshed `refactor-package-recovery-01/verification.json` separately passed
exact probe/RNG/optimizer equality, wrong-loss checkpoint refusal and CPU/CUDA
agreement with the final native diagnostics flag (maximum update delta 2.266e-5).

Final Python suite: **188 tests, 184 passed and four unchanged MCP-environment
skips**. This includes the numeric-failure-report regression test. Portable
fast checks passed **136/136**, and refreshed native CTest passed **17/17**.
Logs: `refactor-package-final-tests-02/python.log`,
`refactor-package-final-tests-01/fast.log`, and
`refactor-package-qualification-01/native-tests.xml`. Tests of the supervisor's
complete A0-A3 schedule, restart ancestry, no failed-seed replacement, qualification
rejection, and one-use held-out receipts use temporary fixtures, not held-out games.

Read [deployment/vast/README.md](../deployment/vast/README.md) for exact commands,
capacity estimates, retained paths and Vast SSH on-start setup.

Docker is unavailable on this host. No image build, remote Vast execution, paid
rental, held-out access or full A0-A3 learning study has occurred. The remote
launcher reruns mandatory checks on its actual GPU before learning. WSL results
must not be described as a container qualification or a successful learning study.

## Evidence and continuation

`runs/2026-09-25/refactor-reconcile-01/source-comparison.json` binds pre-edit source
hashes to the retained `v2-borrow-guide-01` implementation, with per-file diffs.
Eight reviewed files were ported (trainer, collection, guide, checkpoint/recovery,
and tests); only the entropy client argument was added to current `infer_v2.py`,
preserving its newer ONNX/visible behavior.
The imported trainer always reports/verifies gamma and entropy before collection.

Earlier entries below preserve the prior checkpoints; the coverage table reflects the current state.

All run names below are under `/home/imsa/.local/share/openttd-rl/runs/` in WSL.
Builds are under its sibling `build/`; local command logs are in the reconciliation
directory above. Failed attempts are retained.

- `refactor-v2-reference-01` (clean `8ffc5bd` worktree) and
  `refactor-v2-integration-01` built successfully; candidate CTest **13/13 passed**.
  Latest development Python suite **136 passed, 4 skipped** in the Torch
  environment; the four unchanged MCP tests separately **passed** in `mcp-venv`.
  Repository fast suite **136/136 passed** with `/usr/bin/python3`. The first
  fast-suite attempt used the unsuitable UV environment and failed to find Git
  and jsonschema; both attempts' logs are retained. `git diff --check` passed.
- `refactor-v2-options-01/verification.json`: **all four same-device comparisons
  passed exactly** (default CPU/CUDA, retained CPU/CUDA), including causal traces,
  tensor hashes, PPO metrics, and inference weights. The retained recipe is signed
  log, entropy .001, guide v3, rollout 64, eight maps, bootstrap reuse.
  Default CPU/CUDA comparison passed its 1e-4 absolute bound. The retained
  CPU/CUDA comparison **failed**, so the aggregate report remains failed:
  update 2 gradient norm is 3.08823111 vs 3.08836046 (difference .00012935).
  Log-probability/value errors are at most 8.34e-7. Exact agreement with the
  retained implementation on each device establishes that this discrepancy is
  pre-existing. The bound has not been relaxed; numerical follow-up remains open.
- `refactor-v2-reward-audit-01/audit.json`: **passed**, 20,480 retained transitions.
  Native reward accounting and reconstructed GAE match; maximum explained-variance
  error <5e-10. Capital clips occur 32/61/58 times in the financial/entropy/borrow
  runs, each removing 825 currency units. No profit/delivery clips or terminal
  rows were found. Choice fractions are .20825/.36450/.54541. Choice road-building
  advantages average -.05856/-.19190/-.22158; all-step KL maxima
  .02506/.05491/.05491. Historical choice-only KL cannot be reconstructed from
  all-step summaries and remains explicitly unavailable.
- `refactor-v1-time-audit-02/audit.json`: **passed**. Reconstructed clocks for
  16,384 horizon-128 training transitions span [0,.248046875] for features 16/18;
  3,072/4,096 observed full-development transitions lie outside that range.
  Training observations themselves were not logged; this limitation is explicit.
  Attempt 01 rejected four empty, unused reset traces; attempt 02 accepts only
  declared partial episodes with zero actions, with a regression test.
- S1-4 labels new embedded results `pipeline_probe`, `quarter_income`, and
  `claim: not an evaluation`. Historical records and frozen collectors are intact.
- V1 replay auditing, exception-safe ACT mode restoration, separate development
  INFO/replay queries, build-derived fallback identity, kernel diagnostics/edge
  tests, and explicit cross-binary exact comparison are verified. Fresh
  `refactor-v1-reference-01`/`refactor-v1-fused-01` builds passed **11/11** and
  **12/12** CTest checks. All three architectures exercise clean/corrupt replay,
  RNG/parameter preservation and mode restoration on CPU/CUDA.
- `refactor-v1-audit-exact-01/comparison.json`: old versus audited V1 reference
  trainer passes exact native trace, PPO metric and final model equality for two
  live updates (256 decisions). `refactor-v1-fused-audit-01` also passes; all
  measured metric differences happened to be zero, with replay error at most
  2.384185791015625e-7 (below kernel test error 3.8147e-6). These runs overlapped
  other qualification work, so their timings are **not performance evidence**.
  New native INFO reports `reference`/`fused-cuda` correctly in real run records;
  older baseline identity comes from its explicit build configure flag.
- Kernel tests pass the new invalid-row/dtype/boundary/noncontiguous/extreme-value
  cases and the existing nondefault-stream oracle. At ordinary tested scales,
  max errors are logp 3.8147e-6, probability 1.78814e-7, entropy 9.53674e-7.
  `refactor-v1-sanitizers-01`: all four sanitizer commands were attempted and
  **failed to initialize the host WDDM debugger interface / unsupported device**.
  This is unavailable instrumentation, not a sanitizer pass or a kernel defect.
  Enabling an administrator-level host debugger was not part of this check.
- Signed-log guide-v3 exact reset recovery **passed on CPU and CUDA** in
  `refactor-v2-resume-{cpu,cuda}-01`: 256 uninterrupted vs 128+128 resumed decisions,
  exact actor/feedback, metrics, native traces and weights. Both
  `refactor-v2-checkpoint-{cpu,cuda}-01` pass **15 rejection cases**, including
  wrong entropy/financial mode, partial rollout and publication boundaries.
- `refactor-v2-cli-02` passes **15 cases**: malformed/duplicate/unknown options
  and verified native gamma/entropy/financial configuration at valid boundaries.
  Attempt 01 used the wrong close verb in its harness and failed; it is retained.
  A mistyped guide name was also rejected before a resume run started.
- `refactor-legacy-advancement-01`: `studies/legacy_advancement.py` independently
  rederives all **51** original entropy-study cases from hashed native traces and
  reproduces its summaries, paired t intervals and **failed advancement** exactly.
  Four fixture tests cover pairing, failures, duplicates, missing cases and strict
  uniform comparisons. Historical controls actually mix guides v1/v2; reproducing
  their old decision does not qualify them for new same-guide studies.
- `eval_stats.py` adds balanced per-seed/per-map paired differences, sign counts,
  and fixed-seed nested bootstrap. Four tests cover known intervals, training-seed
  dependence, ordering and missing/duplicate/nonfinite cases. It now feeds all
  three required reports; one-model intervals explicitly omit training-seed
  uncertainty. Prospective full-map execution drivers remain outstanding.
- [The prospective protocol](V2_RECOVERY_PROTOCOL.md) is now frozen before new
  tuning, binding the complete eight-map development matrix and reserving the
  eight generalization maps. Its identity is
  `50b27a8d31b54485af847ae2478454a401efe9d0f0f8ab16c8a84398aa26f3d0`.
  `protocol_v2.py` and the execution-registration schema bind seeds, exact arm
  settings, driver/source/binary/runtime identities and cost/qualification inputs.
  Four tests pass, covering altered protocols, wrong splits/maps/modes, missing
  matrix entries and changed settings. The schema initially depended on an
  unavailable optional date-time checker; explicit standard-library validation
  corrected that failed test. No execution registration or held-out permission
  has been issued. Driver execution and held-out preflight/refusal tests remain.
- `studies/recovery_decision.py` implements the frozen A0-A3 advancement and
  first-eligible-arm selection. **Six fixture tests pass**, including the
  same-two-seeds profit/cash condition, seven-map service threshold, retained
  stopped seeds, failed games, guide mismatch and complete-arm selection. It
  consumes identity-verified cases. The native reader is now implemented/tested;
  execution registration preflight and the actual study runner still need wiring.
- `studies/evidence_v2.py` hashes raw/compressed native evidence, checks the reset
  projection, clock/state/economics chain, true terminal or complete time limit,
  and completed training/final-model identities. It rejects changed summaries,
  ambiguous traces and mismatched registered case/source/backend identities.
  Historical controls lacking mode require an explicit legacy option and cannot
  pass prospective verification. Fixtures and 14 retained games pass.
- `refactor-evaluation-reports-04/verification.json`: **passed**. All three
  reports now include per-map/seed/window outcomes, exact pairs, signs and nested
  intervals. V1 averages and both sets of historical t intervals remain exact;
  credit-study matched settings and all 14 V2 native summaries remain exact.
  Mixed v1/v2 guide controls are explicitly unpaired. Attempt 01 rejected added
  default metadata (lambda/spatial validation); 02 passed before credit-report
  integration; 03 exposed a harness misclassification of the baseline batch's
  unused neural package. All attempts are retained; 04 corrects the classification.
- `infer_v2.py` now defaults to development maps; explicit training diagnostics
  remain available, and the ordinary parser/native launcher still reject held-out
  splits. The control evaluator records mode and supports the registered greedy
  uniform lowest-row tie break without consuming RNG. Sampled RNG behavior and
  public-script ordering are preserved by fixtures. Full live matrix still pending.
- `refactor-power-table-01/power.{json,md}`: **passed**, all four historical
  paired t half-widths reproduced within 1e-9. Tables cover 3/5 training seeds,
  2/8 maps and three action seeds using explicit nested variance assumptions and
  noncentral-t 80% planning power. Negative component estimates remain visible.
  This is a retained V1 planning estimate, **not measured V2 recovery power**.
  In the operating-profit contrast, seed SD is 5,116.27 and the old half-width
  12,709.53; increasing maps alone barely reduces the projected width.
- `refactor-study-cost-01/cost.{json,md}`: **passed offline estimate**, using one
  matched-budget training run, eight neural games and six controls. A0-A3 require
  12 models, 98,304 training decisions, 384 candidate and 128 reused-control games
  (256 control games without reuse). Retained medians/maxima imply 40.97/41.54
  sequential hours **as lower bounds** and 653.97/655.56 GiB of artifacts with
  reuse; request logs alone account for 501.33/502.80 GiB. Free space was 670.33
  GiB. An eligible held-out confirmation adds 160 games, excluded from these
  totals. Lossless I/O reduction is needed before the full study; a numerical
  storage fit is not adequate headroom. No concurrency speedup is assumed.
- Current Python verification: **165 tests run, 161 passed, four known MCP-env
  skips** (`refactor-report-tests-01/python-tests.log`); all **22** final focused
  report/evidence/planning checks pass after credit-report integration. Fast
  repository suite **136/136 passed** (`refactor-report-fast-01/fast.log`). No
  native PPO math changed in this reporting pass; prior native results stand.

Next: resolve the retained A0/guide-v3 numerical agreement failures without
weakening their fixed bounds, then qualify the container on its actual target.
The portable package supplies capacity and sequential execution; paid provisioning,
publication and study execution remain outstanding. The broader V1 agreement,
concurrency, profiling and strategy work remains on the original goal checklist.
Do not run A0-A3 until their prerequisite bundle passes.

## Mandatory coverage and dependencies

IDs below refer to report 07 unless prefixed otherwise. Grouped entries share a
deliverable; no member is complete until its own evidence is recorded.

| Work | Review findings / extra references | Status | Required evidence |
| --- | --- | --- | --- |
| S1-1 reproducible V2 options | F02/F07/F30; X2/X7; 06:K2; 08:3a | Default/retained/recovery verified; cross-device discrepancy open | See results above |
| S1-2 V1 behavior replay | F01/F22 | Verified | Clean/corrupt native tests; read-only live equality |
| S1-3 kernel hygiene | F24/F25; 05:K9 | Functional GPU checks verified; sanitizer unavailable | Edge cases/oracle pass; host debugger failure recorded |
| S1-4 honest probes | F23; 03:N10 | Verified by focused tests and live runs | Recorded quarter-income fixture and probe labeling |
| S1-5 backend identity | F26 | Verified | Native/build-derived provenance tests and live records |
| S1-6 offline audits | F18/F20/F21; X6; 03:N9/N13; 06:R2/R3/O2 | Reward/time audit verified; remaining historical questions pending | Hashed input reports; clips/terminal/time/advantages/KL |
| S2-1 study drivers/schema | F03; 06:K3 | Historical rederivation verified; full execution driver implemented/fixture-tested; live study pending | 51 hashed cases; executable full-map study still required |
| S2-2 statistics | F08; 03:N1/N2/N5/N12; 04:B12; 06:K5 | Verified in all three reports | Fixtures, retained V1/credit exact t intervals and V2 native summaries |
| S2-3 eight development maps | F09/F29; X1; 03:N3/N6/N7 | Frozen matrix, modes, evidence reader/default split verified; study launch pending | Explicit split/map matrix, guide/control provenance; cost estimated |
| S2-4 held-out protocol | F09; 03:N4 | Frozen protocol and registered access implemented; refusal/one-use tests verified | No held-out access; model registration after development eligibility |
| S2-5 device agreement | F28; 03:N8 | Pending | Reference/fused CPU-CUDA replay; perturbed-model rejection |
| S2-6 power/sample-size table | 03:section 7.9; 04:B11/B12 | Verified, scoped to retained V1 contrasts | Exact historical half-width; explicit extrapolation assumptions and V2 limit |
| S2-7 concurrent determinism | F33; 03:N3; 04:B6/B13 | Pending | Solo/concurrent native action/economic trace identity |
| S3-0 timers | 04:section 6; 05:section 11; 03:N14 | Pending | Separate timings, unchanged canonical traces, 3 paired runs |
| S3-1 evaluation quick wins | F13; 04:B1/B2/B7 | Pending | Full replay equality and paired timing |
| S3-2 MLP spatial transfers | F12/F32; X10; 05:K1; 06:O3 | Pending | Cross-binary exact mode; all architecture regressions |
| S3-3 ACT copies/backend | F10; 05:K4/K12 | Pending | Exact consolidated copies; measured/toleranced backend |
| S3-4 development collector | F11/F12/F27; 05:K2/K3/K5; 06:K1/K6 | Pending | Injection, deferred values, structured protocol, concurrent traces/payloads |
| S3-5 V2 UPDATE | F14; 06:K4 | Pending | Exact CPU/CUDA updates; finite-input failures; audit tolerance; timing |
| S3-6 V2 I/O | F15; 04:B8/B9/B10 | Pending | Replay/integrity/storage/failure handling and paired timing |
| S3-7 evaluator reuse/tuning | 04:B5/B6 | Pending, profiling conditional | Stage-timing trigger, exact traces or distinct backend |
| S3-8 kernel learning exercise | 05:K7/K8 | Pending, optional | Oracle, CUDA events vs wrapper vs full run; reasoned disposition |
| Recovery 08:0 | F04/F06; X3/X4; 06:P4/A3 | Required instrumentation/probes verified; optional separate gradient diagnostics not added | Exact CPU/CUDA actions, updates, weights, optimizer and RNG with probes |
| Recovery 08:1 / S4-1 | F04; X3/X4/X9; 06:P2a | Mechanism verified; learning study pending | Float64 oracle, zero/one/mixed choices, CPU/CUDA and measured actor drift |
| Recovery 08:2 | F05/F06 | Verified for the explicit bounded history ledger | Telescoping to 1e-9, terminal/truncation boundaries and native reset recovery |
| Recovery 08:3b | F07; X5; 06:R4 | Guide mechanism verified; full matched controls pending study | No repayment before START; existing guide behavior/legality preserved |
| Recovery A0-A3 | 08:section 3 | Packaged; blocked by A0 qualification and target-container verification | Three training seeds, 8192 decisions, 8-map evaluation, registered failure rule |
| S4-2 / 08:4 / A4 | F16; 06:P1 | Pending, after A0-A3 | Sequence batching k=1 exact; registered k>1/KL study |
| S4-3 / A5 | F17; 06:P4/A3 | Pending, conditional | Entropy decomposition before coefficient studies |
| S4-4 | F20/F21; X6; 06:R1/R2/R3 | Pending, audit conditional | New reward objective explicitly separate; offline recomputation |
| S4-5 | 06:O1/R4 | Pending, recovery decision tree | Versioned parameters, alias audit, native/CUDA/export/live checks |
| S4-6 | F18; 06:O2/C1 | Pending, audit conditional | Registered horizon schedule, input coverage/window outcomes |
| S4-7 | 06:C2 | Pending, S4-5 required | Guide annealing and same-mask controls |
| S4-8 | F19; 06:P3 | Pending, critic-evidence conditional | Value-scale/critic study; exact recovery for new state |
| S4-9 / 08:4-5 | 06:P5 | Pending, KL/credit conditional | Choice-KL evidence; gamma/shaping/value-scale consistency |
| Exception-safe V1 mode | F31; X8 | Verified | All architectures CPU/CUDA, initial train/eval modes |

## Remaining option catalogue and open questions

All below are **pending assessment**, not silently omitted. Close optional options
only with evidence for the reported condition, not with a generic "out of scope".

- 04:B3 native CRC; B4 structured-only evaluator; B11 screening; B13 engine reuse.
- 05:K6 pinned staging; K10 CUDA Graphs; K11 batch-bound relaxation. No new V2
  custom backward before the report's profiling prerequisites.
- 06:P2b/A2 semi-MDP compression; P6 larger V1 rollouts; A1 compound selection;
  C3 map diversity/visits; C4 mid-game starts. These require their specified
  semantics, protocol/engine support, and registered evidence.
- 00/01/03/04/05 questions: which models used fused builds; V1 observation bytes
  and stage costs; simulation time by map; actual validation modes; storage
  filesystem; terminal reasons; rationale for the two development seeds; retained
  control identities; supported GPU/tooling scope; and whether profiling supports
  broader kernel use. Preserve unknown historical rationale as unknown when it
  cannot be established, and document the prospective replacement policy.
- 02:2.1-2.14 correctness coverage maps to the table above; F01 is a preservation
  requirement, not permission to skip verification of changed math. 03:N11 keeps
  privileged scripted baseline labels separate from public-information controls.

## Completion gate

Required stage, native, Python, live recovery/equality, deployment, fast repository,
and whitespace checks remain outstanding. No learning or speedup claim is made.
Engineering completion, study execution, and demonstrated learning improvement
will be reported separately. The active goal remains the entire pasted objective.
