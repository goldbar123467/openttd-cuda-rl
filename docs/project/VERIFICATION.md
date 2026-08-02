# Version 1 Verification, Evaluation, and Evidence Plan

## Purpose

Version 1 is a research platform, so correctness of the data-generating process is
part of the product. This plan defines what proves each class of claim, how defects
propagate, and what evidence must exist before the bus-only platform can release.

## Verification principles

- Test the smallest semantic unit and the complete actual-OpenTTD workflow.
- Use independent oracles where production and test code could share a bug.
- Compare structured fields at the first divergent boundary before relying on a
  final hash.
- Treat fixed seeds as reproducibility inputs, not evidence by themselves.
- Preserve failing artifacts before minimizing them.
- Keep training, development, and final evaluation evidence separate.
- Measure model quality with economic/gameplay metrics, not reward alone.
- Any defect capable of changing accepted transitions, training, model selection,
  or evaluation reopens dependent results.
- A skipped mandatory gate is an incomplete release, never a pass.

## Claim classes and authoritative evidence

| Claim | Minimum authoritative evidence |
|---|---|
| Build reproducibility | two clean builds, manifests, exact tests, drift negatives |
| Reset reproducibility | repeated full semantic initial-state comparisons |
| Observation correctness | actual-engine value comparisons plus targeted pattern fixtures |
| Action correctness | native command results/state deltas and independent legality checks |
| Reward correctness | hand-calculated deltas and controlled actual-engine trajectories |
| Step synchronization | boundary/tick trace and state-machine assertions |
| PPO correctness | hand vectors, independent differential, tiny learning problems |
| CUDA correctness | CPU reference parity before performance claim |
| Checkpoint recovery | interrupted/uninterrupted comparison at declared boundary |
| Policy improvement | preregistered independent multi-seed evaluation |
| ONNX completion | structural validation plus native equivalence |
| In-game equivalence | same golden/live inputs through all three runtimes |
| Visible usability | clean-user documented train/export/install/play acceptance |
| V1 completion | all applicable atomic requirements and zero blocking defects |

## Test layers

### Layer 0 — policy, source, and build integrity

- repository/submodule identity and dirty-state recording;
- dependency/toolchain/content/version manifests;
- license and provenance checks;
- schema/requirements/defect traceability lint;
- credential/absolute-path/environment leak checks;
- build-feature and compatibility drift negatives;
- exact upstream and project test inventory.

### Layer 1 — pure unit tests

- checked arithmetic, IDs, schemas, canonical serialization, hash/integrity;
- seed derivation and deterministic ordering;
- normalization, slot assignment, tensor layout, action encode/decode;
- reward component formulas and termination flags;
- GAE, PPO losses, entropy, clipping, minibatches, gradients, scheduler;
- metrics aggregation and monitor view models;
- model manifest/compatibility comparison.

### Layer 2 — property, randomized, and malformed-input tests

- action/observation/schema round trips;
- all legal parameter boundaries and invalid encodings;
- random valid state projections and action masks versus independent oracle;
- corrupted/truncated/oversized trajectory, checkpoint, package, and IPC messages;
- stable seed assignment under worker reordering;
- reward invariants and exploit-sequence generators;
- model-package compatibility field mutation.

### Layer 3 — actual OpenTTD integration tests

- scenario generation and reset;
- observation fields/channels against engine state;
- road/depot/stop construction;
- bus purchase, route/orders, start/stop, passenger delivery, revenue/profit;
- illegal/native-rejected/stale actions;
- tick stepping, month/year boundaries, bankruptcy, horizon;
- bridge on/off non-perturbation;
- in-game model controller and inspection values.

Mocks are useful for failure injection but cannot be the only proof for an engine
semantic requirement.

### Layer 4 — differential and equivalence tests

- semantic state traces between repeated reference runs;
- fast mask generator versus independent slow legality oracle;
- PPO math/update versus pinned independent implementation;
- CPU versus CUDA model/loss/update paths;
- native versus ONNX versus in-game preprocessing, masks, outputs, and actions;
- structured logs versus terminal display and evaluation aggregates.

### Layer 5 — end-to-end campaigns

- scripted policy completes the bus economic loop;
- random policy and trivial scripted baseline evaluation;
- development PPO learning run;
- multi-seed MLP/CNN/combined matched comparison;
- existing AI baseline/evaluation workflow;
- checkpoint interruption/recovery;
- export/package/install/play workflow;
- clean-host reproduction.

### Layer 6 — soak, fault, and operational resilience

- long headless idle/scripted/random/legal-policy runs;
- extended CPU and CUDA training;
- environment worker crash/hang/duplicate/stale message;
- disk full, short write, permission failure, corrupt checkpoint/log/package;
- GPU OOM/unavailable device/runtime error;
- graceful user interruption and checkpoint boundary;
- repeated reset for state leakage;
- terminal resize/non-TTY/SSH behavior;
- profiling/telemetry enabled versus disabled semantic parity.

## Required build and quality matrix

Exact toolchains are frozen in `M01`; the minimum conceptual profiles are:

| Profile | Purpose | Mandatory scope |
|---|---|---|
| C++ debug/assertions CPU | deterministic correctness oracle | all unit/integration/equivalence tests |
| C++ optimized CPU | production CPU behavior | full tests plus soak |
| ASan + leak checks | memory safety | all practical native entry points |
| fail-fast UBSan | undefined behavior | all practical native entry points |
| static analysis + strict warnings | defect discovery | all owned C/C++/CUDA and scripts |
| CUDA debug/check profile | launch/memory correctness | every CUDA path |
| CUDA optimized | parity/performance/soak | enabled production GPU paths |
| playable inference-only | deployment dependency boundary | package/equivalence/playback tests |
| coverage | test-risk audit | unit and integration sources |
| fuzz/property | hostile byte/shape/state boundaries | every untrusted parser/protocol |

Profiles are separate when tool combinations are incompatible. A release report
lists exact executed commands, tests, counts, skips, failures, versions, and
artifact paths. Merely configuring a profile does not pass it.

## Environment verification

### Reset and seed campaign

For a frozen corpus and randomized valid seeds:

- compare map/town/company/settings/RNG/time/economy/entity semantic projections;
- compare first observation and legal mask;
- execute the same scripted prefix and compare every boundary;
- repeat across fresh and reused worker processes;
- perturb one seed/config field at a time and prove the identity/output changes or
  the field is intentionally non-semantic;
- prove final evaluation seeds cannot be requested by training code.

### Observation campaign

Each structured field and spatial channel gets:

- nonzero positive fixture;
- zero/absent fixture;
- minimum/maximum/overflow or clipped fixture;
- ownership and entity-deletion/reuse fixture where relevant;
- spatial orientation/corner/edge pattern;
- source engine value and expected encoded value;
- normalization and missing-value check;
- cross-runtime golden vector.

Coverage of encoder lines is not a substitute for semantic fixtures. A channel
that is always zero in the corpus remains unproven.

### Action and mask campaign

For every action family:

- minimum/maximum valid parameters;
- each precondition false separately;
- ownership and insufficient-funds cases;
- action legal at mask time and successful at execution;
- deliberately stale state between mask and execution;
- native rejection despite optimistic mask;
- macro failure at each subcommand position;
- exact cost/tick/state/result comparison;
- log encoding and reward attribution;
- illegal logit masking with extreme logits;
- all-mask/single-legal-action behavior.

Random valid states compare the production mask with an independent legality
oracle. Any false legal bit is safety/correctness critical; any false illegal bit
is a capability defect and also blocks schema freeze until understood.

### Reward exploit campaign

Scripted adversaries attempt:

- infinite wait/no-op;
- repeated invalid actions;
- build/remove cycling;
- duplicated stops/routes/vehicles;
- buying and idling buses;
- servicing a route at operating loss;
- unnecessary road construction;
- station-rating proxy farming without deliveries;
- bankruptcy delay without useful transport;
- oscillating loans if loan actions exist;
- repeated collection of unchanged cumulative profit/delivery values.

Reports retain raw economic state, every reward component, scalar total, action
outcomes, and the expected exploit detector.

### Synchronization and long-run campaign

At selected boundaries, record a compact semantic state digest plus enough typed
context to locate first divergence. Compare repeated scripted/random/legal-policy
runs, bridge observation on/off, telemetry on/off, and debug overlay on/off. A final
equal balance is insufficient if intermediate states diverged.

`G03` closes the bridge subset of this campaign with two byte-identical
all-template native roots. It proves exact 1/64/128-tick advances, rejects 0 and
129 without mutation, replays every scripted trace twice, preserves accepted M02
results with the bridge entrypoint disabled, interleaves two isolated workers,
and soaks one action-free worker for 512 steps and 65,536 ticks. Bad checksum,
killed-worker, timeout, stale-handle, stale-boundary, invalid-lifecycle, and
post-horizon cases are classified without silently committing another
transition. The policy observation, mask, random/legal-policy, telemetry, and
debug-overlay portions remain owned by later gates.

`G04` closes the observation subset with two byte-identical all-template native
roots. For each template, an independent oracle compares 256 structured values
and 32,768 spatial values to a raw actual-engine source projection, for 264,192
comparisons overall. Observed and no-observation control workers have identical
post-step snapshots; repeated encodings are byte-identical; wrong compatibility
identities fail without mutation; and every spatial channel has a positive
orientation-pattern fixture. Trainer, evaluator, ONNX Runtime, in-game, and
oracle consumer adapters receive identical canonical native tensor bytes.

`G05` closes the action and mask subset with two byte-identical all-template
native roots. The fixed and deterministic-random campaigns compare the 41-bit
production mask with an independent slow oracle at 614 actual-engine states.
Every accepted step advances exactly 128 ticks; native command costs match company
balance deltas; ownership, stop/depot/vehicle/order projections match expected
mutation; and identity, masked-index, and stale-boundary errors commit no
transition. An injected route failure restores the prior order list, while an
unsupported internal hook is a fatal `INTEGRATION_FAILURE` at transition zero.
All nine action families are exercised and each scripted template creates a
running passenger service with positive delivery and revenue. Extreme-logit,
single-legal, and all-zero mask sampling share one adapter across trainer,
evaluator, ONNX, and in-game consumers. Telemetry and debug-overlay portions
remain owned by later gates.

## PPO and model verification

### Algorithm reference corpus

The repository retains small, reviewed tensors for:

- GAE with terminal, truncated, and continuing transitions;
- clipped objectives in all ratio/advantage regions;
- value and entropy losses;
- masked logits/probabilities/log probabilities;
- advantage normalization edge cases;
- minibatch ordering and epoch coverage;
- gradient clipping and one optimizer update.

Expected values come from hand calculation or a pinned independent reference and
are never regenerated silently from production code.

### Learning-readiness criteria

Before expensive OpenTTD runs:

- fixed-vector/differential tests pass;
- tiny environments learn under multiple seeds;
- zero reward, all terminal, single legal action, and extreme reward/logit cases
  remain finite;
- checkpoint/resume passes;
- metrics match recomputed source values;
- a scripted real trajectory updates without schema/mask mismatch.

### CPU/CUDA parity

Compare:

- preprocessing output if accelerated;
- logits, values, probabilities, selected greedy action;
- component/total losses;
- gradients or reviewed aggregate norms/per-parameter samples;
- updated parameters/optimizer state after fixed steps;
- checkpoint load/save across devices;
- seeded distribution statistics.

Parity tolerances are specific to dtype, device, batch shape, and operation. The
performance report follows parity; it cannot excuse a correctness failure.

### ONNX/in-game equivalence

The golden corpus spans:

- each architecture;
- minimum/maximum/typical normalized observations;
- diverse masks including one legal action and dense/sparse sets;
- greedy ties under declared tie-breaking;
- multiple scenario/entity layouts;
- adversarial finite logits/values;
- live snapshots captured from actual games.

The in-game test compares encoded inputs before blaming model output. It reports the
first differing tensor, index, native/ONNX/in-game value, tolerance, package IDs,
and action context.

## Independent evaluation protocol

### Freeze before final evaluation

The following are reviewed and hashed before final results:

- model/checkpoint-selection rule;
- final scenario/seed matrix;
- evaluation horizon and inference modes;
- random/scripted/existing-AI baseline versions/configuration;
- primary and secondary metrics;
- superiority threshold and statistical reporting;
- architecture training budgets and seed count;
- failure/bankruptcy/missing-run handling;
- aggregation and confidence-interval method.

Changing one after seeing final results creates a new protocol/version and the old
and new results remain distinguishable.

### Scenario matrix

At minimum:

- fixed known layouts for regression;
- unseen seeds/layouts for generalization;
- multiple town arrangements and passenger distributions;
- reviewed starting-balance variations;
- short and long evaluation horizons;
- minor in-scope variations that preserve the bus-only compatibility version or
  are explicitly a robustness suite;
- greedy and seeded stochastic policy modes.

### Baselines

#### Random

Samples uniformly or under another precisely declared distribution over legal
actions. It uses the same mask, step, horizon, and scenario suite. Its seed is
independent and recorded.

#### Trivial scripted

At least one low-complexity policy follows fixed bus-building heuristics without
learning. Its access to observations/engine state is documented so advantage from
privileged state is not hidden.

#### Existing OpenTTD AI

At least one AI/scripted agent is run in a compatible documented workflow. If it
cannot obey the exact step/action contract or 32 by 32 scenario, its results are
reported in a separate baseline class and not used for an invalid direct
superiority claim. Name, version, source, configuration, seed, transport modes,
limitations, scenario, and raw results are mandatory.

### Metrics

The metric registry dispositions every candidate from `EVAL-009`. At least the
following must be final-report visible where defined:

- survival/bankruptcy;
- final balance and net/operating profit;
- passenger deliveries;
- route and vehicle profitability;
- infrastructure cost and return on investment;
- network coverage/station service quality;
- invalid/native-rejected actions and mask violations;
- action efficiency/no-op share;
- stability across seeds;
- training/evaluation compute and environment steps.

Each metric defines source fields, unit, time window, aggregation, missing/failed
episode handling, and whether higher/lower is better.

### Superiority claim

`EVAL-012` passes only when at least one immutable learned policy exceeds the
preregistered random and trivial-scripted thresholds across the required final seed
set. `EVAL-013` additionally requires preregistered positive operating/economic
profit and cross-seed reliability thresholds; outperforming two bad baselines is
not enough. Neither may omit failed seeds or coexist with a release-blocking
correctness defect. Best-seed anecdotes and training return do not pass.

## Existing AI verification

External AI acquisition is content/version pinned and license-reviewed. The
baseline runner uses isolated user-data roots, records settings/content/logs, and
does not allow the AI to alter final evaluation definitions. Results are sanity
checked against repeated seeds and known limitations; established reputation is
not treated as an oracle.

Demonstration/imitation datasets, if later used, record action/state translation
and cannot bypass the rule that PPO is the only required learning algorithm.

## Fault injection matrix

| Fault family | Injection points | Expected owner/result |
|---|---|---|
| Identity/schema drift | scenario, observation, action, reward, model package | fail before state mutation/inference |
| Engine command rejection | each action/native subcommand | typed result; exact partial/atomic semantics |
| Worker crash/hang | reset, observe, execute, advance, reply | detect once, preserve request/boundary artifact |
| IPC corruption/order | length, checksum, duplicate, stale, out-of-order | reject; never double-apply action |
| I/O failure | logs, trajectory, checkpoint, package, evidence | no false persisted/success result |
| Numerical failure | observations, logits, values, rewards, losses, gradients, parameters | stop before corrupt update/package |
| Resource exhaustion | host memory, GPU memory, disk, descriptor/process limits | bounded clear failure and cleanup |
| Package corruption | every file/manifest/hash/compatibility field | reject before controller activation |
| Telemetry failure | GPU/CPU counters, terminal output, external tracker | mark unavailable; semantics continue if nonmandatory |
| User interrupt | rollout, update, export, evaluation | exit at documented recoverable boundary |

Every injected fault has one expected first owner, typed result, exit status, log
event, retained artifact policy, and cleanup assertion.

## Soak gates

Exact durations/steps are frozen with performance data, but release must include:

- repeated-reset soak sufficient to expose pool/cache/state leakage;
- single-worker scripted and randomized legal-action soak;
- multi-worker headless rollout soak with worker replacement disabled and enabled
  in separate profiles;
- CPU PPO extended run;
- CUDA PPO extended run if CUDA is a release path;
- evaluator batch across all final scenarios;
- repeated in-game inference/playback session;
- checkpoint rotation/recovery under long execution.

Soak success requires zero unexplained crashes, hangs, mask violations,
desynchronizations, nonfinite values, corrupt artifacts, lost mandatory logs, or
unbounded resource growth.

## Evidence layout and contents

The final layout is selected in `M00`, but every gate bundle contains:

- gate/profile/run identity and exact command arrays;
- source/submodule/dependency/build/configuration manifests;
- stdout/stderr and structured results with secret-safe environment handling;
- test inventories, counts, durations, failures/skips;
- raw semantic comparison or evaluation records;
- artifact hashes and a complete bundle index;
- linked requirements and defects;
- machine-readable gate result and concise human report;
- first failure and retained minimizer/reproducer when nonpassing.

Evidence is written to unique temporary/output roots and promoted atomically after
validation. A later passing rerun never deletes the earlier failure needed to
understand flakiness or defect history.

## Defect and divergence policy

Each entry includes stable ID, discovery time, affected requirements/gates/runs,
severity, first divergent boundary/field, reproducer, root cause, fix, regression
test, evidence, and status.

Statuses are `OPEN`, `DIAGNOSED`, `FIXED_PENDING_VERIFICATION`, `CLOSED`, or
`ACCEPTED_LIMITATION`. A limitation cannot waive an explicit V1 requirement;
scope/requirements must be explicitly revised if fulfillment is impossible.

Severity propagation:

- transition-data corruption reopens environment, training, and all dependent
  model/evaluation/export claims;
- PPO/checkpoint defect reopens trained policies and dependent evaluations;
- evaluator/metric defect reopens comparison/superiority claims;
- preprocessing/action/model drift reopens export and playback equivalence;
- documentation-only defects reopen reproduction/usability but not necessarily
  already retained numerical results.

## Traceability gate

A machine registry/linter must prove:

1. every applicable project requirement has implementation ownership, tests, and
   evidence;
2. every mandatory test maps back to at least one requirement;
3. each `PASS` path exists, validates, and comes from the named gate/profile;
4. no open affected defect coexists with a pass without an explicit impossible
   state rejected by the linter;
5. aggregate `DONE-*` rows are computed from lower-level states;
6. legacy P0 evidence is labeled and cannot satisfy bus-specific gates by path
   naming alone;
7. no post-V1 item is required for V1, and no V1 item is mislabeled post-V1;
8. schema digests and compatibility IDs agree across evidence;
9. final evaluation manifests predate or cryptographically bind the final result
   generation; and
10. a final `PASS` contains no mandatory `SKIP`, missing artifact, or unreviewed
    tolerance exception.

## V1 completion audit

Before `G12` passes, reviewers walk every row in
`docs/project/REQUIREMENTS.md` and classify its evidence as:

- proves the whole requirement;
- contradicts it;
- proves only a narrower subset;
- indirect/too weak;
- missing.

Only the first classification can support `PASS`. The top-level workflow is then
repeated from fresh build and evidence roots. Version 1 completes only if both the
atomic audit and repeated end-to-end gate pass with zero release-blocking defects.
