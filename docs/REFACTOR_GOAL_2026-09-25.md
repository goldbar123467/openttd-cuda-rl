# Goal prompt: complete the September 25 refactor and PPO recovery

Execute the complete, evidence-backed refactor and live PPO recovery program in
`9/25 refractor/`. Carry it through implementation, verification, profiling,
registered experiments, reporting, and a reproducible handoff. Do not stop after
making a plan, implementing only the easiest fixes, or running a smoke test.

The intended outcome is a locally reproducible C++/CUDA OpenTTD learning pipeline
with trustworthy evaluation, measured performance, and a rigorously assessed V2
recovery recipe. Pursue learned improvement over matched public-guide controls;
never manufacture a successful learning result or confuse planner-provided
service with learned competence.

## Workspace, sources, and authority

Work from `C:\Users\imsa\Documents\OpenTTD\openttd-cuda-rl`, using its WSL/Linux
equivalent for builds and execution. Read the parent instructions, this checkout's
`AGENTS.md`, `docs/DEVELOPMENT.md`, `GOAL.md`, and current progress/handoff notes.
Then read **all eleven original Markdown files**, in full, in `9/25 refractor/`:

- `README.md`
- `00-review-summary.md`
- `01-project-map.md`
- `02-correctness-and-ppo-review.md`
- `03-evaluation-audit.md`
- `04-evaluation-bottlenecks.md`
- `05-custom-kernel-review.md`
- `06-strategy-and-refactor-options.md`
- `07-prioritized-plan.md`
- `08-ppo-training-recovery.md`
- `09-coverage-and-findings-register.md`

This prompt was prepared from the folder fetched from `origin/main` at
`ec5a3f6d5d999d5c525c479105dfc04112a0cd46`. The reports themselves are static reviews
of `0595a72`: their authors did not execute tests or experiments. Reconcile every
claim with the actual checkout and retained artifacts before changing code.
Historical line numbers and statements that a feature is missing may be stale.

Use report 07 for implementation and verification detail. Report 08 supersedes
report 07's earlier learning-experiment ordering; report 09 adds findings and
coverage limits. Resolve contradictions explicitly using current code, executable
evidence, and the user's instructions. In particular:

- Establish committed study drivers, reliable reporting, and the V2 held-out
  protocol **before** launching new tuning studies, even though report 07's final
  summary lists recovery experiments earlier.
- Write timing data to separate files, as S3-0 requires, rather than adding it to
  canonical action traces as an earlier profiling sketch suggests.
- Treat report 08's numerical settings and code sketches as proposals requiring
  validation, not as proof of correctness or guaranteed learning improvements.

Preserve the broader project objective and existing working systems. The review
is scoped to live learning, evaluation, and CUDA/pipeline work; its list of areas
not reviewed does not authorize a rewrite of MCP, cargo, the historical M22 corpus
campaign, or all remaining V2 gameplay milestones. Inspect those areas as needed
to preserve compatibility with changes made here.

## Execution and coverage

Start by inspecting Git status, branches/worktrees, available retained studies,
CPU/CUDA/toolchain capabilities, disk capacity, and existing build/runtime paths.
Preserve unrelated changes. Use an isolated checkout when needed and bring the
review documents with it. Do not assume current `main` contains the user's newest
work or replace newer branch contents with older files.

Maintain one concise progress/checklist document, for example
`docs/REFACTOR_2026-09-25_STATUS.md`. Cross-reference:

- F01-F33 and X1-X10 in report 09;
- S1-1 through S1-6, S2-1 through S2-7, S3-0 through S3-8, and S4-1 through S4-9;
- report 08 Steps 0-5 and arms A0-A5;
- report 04 B1-B13; report 05 K1-K12;
- report 06 P1-P6, R1-R4, O1-O3, A1-A3, C1-C4, and K1-K6;
- actionable recommendations and open questions in reports 00-03 and 05-08 that
  are not already covered by those IDs.

Qualify IDs by report because several reports reuse them. Deduplicate overlapping
work while retaining every source reference. For each item record applicability,
dependencies, implementation/decision, checks, actual result, and artifact paths.
Use statuses such as pending, implemented/unverified, verified, disproved,
already satisfied, optional condition not met, and externally blocked.

Every mandatory item needs execution evidence or a demonstrated reason it no
longer applies. Only explicitly optional/conditional proposals may close with a
reasoned rejection or an unmet trigger. Do not quietly defer required work because
it is expensive. A blocked check remains visibly incomplete, never PASS. Avoid
building a second requirements-management framework around this checklist.

## 1. Restore reproducibility and establish correctness

Complete report 07 Stage 1 and the additional report 09 findings:

1. Recover and integrate missing V2 worktree features, preserving newer work and
   their provenance: entropy configuration, signed-log training inputs, and guide
   v3 borrowing. Keep historical behavior reproducible with default/reference
   settings. Bind every behavior-changing option to native and Python checkpoint
   compatibility, inference metadata, and relevant exports. Prove default CPU and
   CUDA equivalence and reproduce retained nondefault behavior where artifacts
   exist; missing artifacts require an explicit finding and fresh evidence.
2. Add the V1 pre-update behavior-log-probability replay audit without changing the
   frozen UPDATE wire format. Keep the V2 audit. Cover clean and deliberately
   corrupted rollouts, both fused and reference builds, with the specified 1e-4
   rejection threshold and tighter recorded kernel error where applicable.
3. Complete kernel diagnostics, boolean-mask normalization, failing-row reporting,
   and edge-case tests: mixed invalid rows, legal nonfinite values, batch-size
   boundaries, extreme finite logits, and noncontiguous masks. Preserve the oracle,
   nondefault-stream behavior, exact illegal outputs, and stated tolerances.
4. Separate pipeline probes from evaluations, correctly name quarter income, and
   report the native ACT distribution backend explicitly. Derive backend identity
   from the binary/build rather than guessing from its filename.
5. Perform the read-only, input-hashed audits of reward clipping and terminal
   reasons, V1 time-feature coverage, V2 advantage/KL distributions, forced-choice
   counts, action-feature aliasing, and existing control provenance. Investigate
   the remaining review questions, including development-map selection rationale.
6. Address X1/X7/X8/X9/X10: prevent accidental evaluation on training maps; verify
   native gamma and configuration rather than merely recording Python defaults;
   restore V1 model mode safely on exceptions; preserve lone-choice advantage
   signal; and support explicit exact comparisons across different binaries.

Run relevant focused Python and native CPU/CUDA tests. Preserve frozen release
scripts, records, expected hashes, and historical behavior; use development
extensions and versioned options for new routes.

## 2. Make evaluation and study decisions reproducible

Complete report 07 Stage 2 before using new studies to select a recipe:

1. Bring retained study/advancement drivers into `scripts/dev/studies/`, with
   registration schemas and tests. Recompute at least one completed study's
   decision from its original inputs. Registrations bind driver/source hashes,
   settings, binaries, budgets, seeds, guide versions, controls, and criteria.
2. Add per-map and per-training-seed results, paired differences, sign counts,
   continuous window outcomes, and a fixed-seed nested bootstrap (training seed,
   then map, then action seed). Preserve existing t-interval results. Test pairing,
   missing/duplicate cases, and uncertainty calculations on independent fixtures.
3. Use all eight V2 development maps, explicitly selected and verified in every
   run, with one greedy and three sampled action seeds per final trained model.
   Evaluate uniform and scripted controls under the identical guide and game
   budget. Reuse controls only after checking all relevant identities. Clearly
   distinguish privileged V1 scripts, public-information controls, and guide
   overrides. Action seeds do not count as independent training seeds.
4. Register a fail-closed V2 held-out protocol before further tuning, reserving an
   untouched generalization/final split without running it. Freeze selection and
   acceptance rules now; bind the selected model, source, and binary hashes in a
   final immutable registration before held-out access. Test refusal without valid
   registration and keep ordinary launchers unable to access held-out games.
5. Add V1 CPU/training-device agreement, sample-size/detectable-effect reporting,
   and actual concurrency determinism checks for V1 and V2. Estimate experiment
   costs from retained timing records before scheduling the larger matrix.

Do not change acceptance thresholds after seeing outcomes, select convenient
intermediate checkpoints, shorten confirmation episodes, or tune on held-out
results. A held-out confirmation follows development selection only when its
registered eligibility criteria are met; if none qualifies, report that fact.

## 3. Implement and test the V2 recovery mechanisms

Follow report 08's mechanism order, retaining an unchanged reference mode:

- **Step 0, instrumentation:** record choice counts, choice-only entropy/KL/clip
  fraction, pre-normalization choice advantage statistics, proposal probability,
  value loss/explained variance, and optional separate actor/value gradient
  diagnostics. Add checkpoint probes of the eight training-map reset states.
  Prove that logging and probes preserve actions, RNG state, updates, and weights.
- **Step 1, choice-weighted PPO:** add an opt-in weighted loss using the existing
  PPO implementation, leaving its original loss path intact. Average actor,
  entropy, KL, and clip terms over transitions whose exact sampling mask offers
  at least two actions; retain value loss on all transitions. Normalize advantages
  over choices, leaving them unnormalized when fewer than two exist. Bind the
  option everywhere required for reproducibility. Test all-choice, mixed,
  zero-choice, one-choice, invalid-weight, and zero-variance cases; require the
  report's float64 all-choice tolerance and CPU/CUDA agreement. A zero policy loss
  does not by itself prove Adam momentum or shared-trunk actor drift is eliminated:
  measure those effects and state the actual optimizer semantics.
- **Step 2, asset-potential shaping:** preserve raw native rewards and economics;
  version and log the potential/shaping separately. Use the exact clipped capital
  magnitude charged, the native trainer's verified gamma, zero terminal potential,
  correct truncation bootstrap, and episode-reset handling. Verify the discounted
  telescoping identity to 1e-9 and boundary cases. Check the potential's state and
  boundedness assumptions: cumulative spend must not silently be treated as a
  state-only asset value when sales, demolition, or differing histories invalidate
  that claim. Restrict/version the supported setting or represent the necessary
  state explicitly; bind any added state to recovery.
- **Step 3, finance and guide:** support signed-log training inputs consistently
  through inference/export. Add guide v4 with no repayment before the whole plan,
  including START, completes; retain the specified affordability condition and
  v3 borrowing recovery. Preserve v1/v2/v3 semantics. Test masks remain subsets of
  native legality and rerun controls under v4.
- **Step 4, optimizer granularity:** after reading the first study, evaluate
  multiple recurrent sequences per minibatch and the choice-KL guard (report 08
  proposes four sequences and 0.03). Preserve stored initial hidden states,
  sequence/reset boundaries, and behavior replay. Prove one-sequence/default
  equivalence; treat changed batching as a learning experiment, not a pure speedup.
- **Step 5, gamma:** consider .995 only if the documented construction-credit
  condition persists after Steps 1-3. Register value-scale handling, update shaping
  consistently, and test gamma/configuration/checkpoint agreement.

Do not substitute a second PPO implementation or Python training for the trusted
C++/LibTorch path.

## 4. Execute the registered recovery study

Use report 08 section 3 as the starting protocol. Freeze any justified amendments
before execution and record why they were necessary.

Run A0-A2 first, then A3, with three independent training seeds per arm:
20260923, 20260924, and 20260925. Per seed use 8,192 decisions, horizon 128,
rollout 64, eight training maps, signed-log inputs, and bootstrap-tensor reuse.
Preserve gamma .99, lambda .95, four epochs, BPTT 8, learning rate 3e-4, clip .2,
gradient norm .5, and value coefficient .5 unless the registered arm changes them.

- A0: guide v2, historical loss, entropy .01.
- A1: A0 plus choice-weighted loss and entropy .003.
- A2: A1 plus asset-potential shaping.
- A3: A2 plus guide v4, with freshly matched controls.
- A4/A5: conditional follow-ups for four-sequence minibatches with a KL guard,
  and entropy .01, respectively; decide from the preceding registered evidence.

An old A0 run is reusable only if every relevant setting and provenance condition
matches. Register the training-only early stop: after update 32, proposal
probability below .1 on at least six of eight training maps at two consecutive
checkpoints. Preserve stopped seeds as failures; do not replace them or omit them
from results. Any screening variant must be registered beforehand and its results
kept separate from confirmation.

Evaluate eligible final models at the complete 512-decision horizon on the full
development matrix. Pre-register the proposed advancement conditions: zero
invalid actions and bankruptcies for every seed; greedy sustained service on at
least seven of eight maps for each seed; positive paired sampled profit **and**
cash differences versus same-guide uniform for at least two of three seeds and
positive pooled means. Report nested intervals without overstating significance
from three training seeds. Report passengers, operating profit, cash after
capital/excluding financing, service windows, failures, and survival separately.

Use report 08's decision tree to choose the next registered investigation when an
arm fails. Do not repeat already-failed recipes without a new, testable reason or
declare a weak model improved because a smoke test succeeds. Keep engineering
completion and scientific success as separate outcomes.

## 5. Profile and finish the pipeline/CUDA work

Complete report 07 Stage 3 and disposition every B/K proposal from reports 04/05.
Cheap logging can precede the study; behavior-preserving performance work may help
pay for the larger evaluation matrix only after its equality gates pass. Freeze
the chosen implementation for each matched study.

Instrument actual collection, evaluation, ACT, UPDATE, bridge, validation,
serialization, simulation, transfer, inference, frame I/O, and archival costs.
Keep timing separate from canonical evidence and compare with instrumentation
disabled. Record kernel-only CUDA-event time separately from wrapper and complete
application wall time.

Implement and verify the applicable changes:

- Vectorized evaluation validation, the recorded fast bridge mode, and buffered
  traces, with reproducible reference options.
- Skip unused MLP spatial transfers/indexing; retain CNN/combined behavior.
- Consolidate ACT device-to-host copies without weakening failure handling.
- Add an explicit development collector and versioned structured-only ACT/UPDATE
  and VALUE messages. Replace module-global monkeypatching with injected
  dependencies; defer continuing-state bootstrap values correctly; step workers
  concurrently while retaining per-environment order and RNG ownership.
- Cache V2 rollout inputs on-device within measured memory limits, aggregate
  finite checks without losing named failures, and batch the read-only replay
  audit where permitted.
- Reduce V2 duplicate frame checks, probability serialization, and archival
  critical-path work while retaining stale-token rejection, replayability,
  integrity verification, bounded storage, and truthful run completion.
- Measure before adopting native CRC, evaluator/process reuse, worker/thread
  tuning, pinned staging, CPU small-batch distributions, or CUDA Graph capture.
- Complete the useful CUDA learning experiment described in S3-8 with its oracle
  and separate measurements, or document an evidence-backed reason the explicitly
  optional experiment is not applicable. Do not make an optimized kernel the
  default solely because its microbenchmark improves.

Require exact traces, PPO inputs, metrics, and model identities for changes claimed
to preserve outputs; add explicit cross-binary exact comparison. Verify deferred
values against the original calculation and compare UPDATE payload hashes.
Use the reports' stated tolerances for deliberately different numerical backends,
label them separately, and never silently relax an exactness claim after failure.

Run at least three counterbalanced timing pairs after correctness passes. Report
medians, ranges, absolute time, workload/device/runtime, and whether end-to-end
benefit exists. Run kernel edge tests and available sanitizer/profiler checks;
unsupported tooling is recorded as unavailable, not passed. Preserve checkpoint
roundtrip, export-preserves-trainer, and CPU/CUDA regressions.

## 6. Resolve the remaining strategy options

Address every report 06 option and S4 item using the audits and recovery results.
Run justified follow-ups as preregistered, matched-budget, multi-seed studies.
Do not stack untested changes into a purported causal comparison.

In particular, assess versioned candidate-parameter features and aliasing before
guide annealing/unguided claims; entropy-family decomposition before extra entropy
coefficients; clipping/terminal semantics before changing the reward objective;
time-feature coverage before horizon schedules; and critic/gradient evidence
before return normalization, a separate value trunk, or training-only warm starts.
Cover larger V1 rollouts after the structured protocol, map diversity with matched
visits, semi-MDP discount semantics, compound actions, and mid-game starts as the
conditional alternatives they are. Do not implement mutually exclusive options
merely to tick boxes.

Any new observation/action/reward architecture needs explicit versioning,
checkpoint rejection tests, CPU/CUDA agreement, and relevant ONNX/native/visible
replay checks. Keep inference inputs public and preserve the common fair game
boundary for future MCP competition.

## Safeguards and persistence

Preserve the parent OpenTTD data directory, saves, installed game, content, AIs,
configuration, and unrelated environments. Never read or copy `secrets.cfg` or
`private.cfg`. Keep the upstream submodule pristine; use isolated composed engine
trees and Linux build/run storage. Retain source LF and byte-sensitive patches.

Every executable experiment records source revision and dirty state, source
archive, configuration, seeds, binary/model identities, device/runtime, and actual
outputs. Preserve failed runs. CUDA requests must fail clearly if unavailable;
CPU operation must be explicit. Detect the GPU rather than hard-coding historical
hardware. Keep large weights, dependencies, credentials, and runtime artifacts out
of Git. Do not push, publish, or use paid remote compute without authorization.

Continue through routine debugging, builds, local runs, and verification within
the requested scope. Keep concise progress updates and an accurate continuation
record during long work. If an external dependency blocks one item, preserve the
failure and continue independent work; ask only for genuinely missing information
or authorization. Do not mark the goal complete merely because time or context is
running low.

## Completion and handoff

The refactor program is complete only when every mandatory item has been verified
or demonstrated inapplicable, every optional/conditional item has an evidenced
disposition, and the required eligible studies and reports have actually finished.
Unresolved correctness defects or blocked mandatory checks keep that portion
incomplete. A failed learning study is a valid scientific result, never a passed
learning objective; state explicitly whether the advancement goal was achieved.

Run the relevant native, focused Python, live equivalence/recovery, and
export/deployment checks, plus `bash scripts/v2/verify.sh --tier fast` using the
documented environment and `git diff --check`. Do not treat skips as passes or
rerun unrelated suites without a reason.

Update `docs/DEVELOPMENT.md`, `docs/PROGRESS.md`, and `docs/CUDA_EXPERIMENT.md` where
the supported workflow or measured conclusions change. Preserve the original
review as historical source material. Provide a final finding-by-finding status,
tests passed/failed/not run, exact commands to reproduce the selected recipe,
source/build/model/run/report locations, matched learning results and uncertainty,
measured performance, and any remaining external blocker. Explain material
PPO/CUDA choices so the owner can learn from the implementation.

Begin with repository/artifact reconciliation, build the small coverage checklist,
and proceed directly to the first unresolved executable task.
