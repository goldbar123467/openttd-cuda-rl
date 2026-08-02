# OpenTTD RL Platform: Current Implementation Handoff

## Executive instruction

Build the project described by `GOAL.md`: a reproducible C++/CUDA PPO platform
around actual OpenTTD, beginning with a headless 32 by 32 passenger-bus environment
and ending with independently evaluated ONNX policies that a user can watch in a
normal OpenTTD game.

Do not continue the former clean-room road-freight gameplay-port roadmap as the
project target. Preserve its unfinished work and reuse only components that pass
the applicability process in `docs/project/LEGACY_P0_TRANSITION.md`.

`M01/G01` is complete. The deterministic probe, both completely clean headless
builds, both completely clean playable builds, the seven-profile contract, two
runtime-resource campaigns, two byte-identical provenance manifests, and two
byte-identical closure audits all pass. Preserve those accepted artifacts; do not
rebuild or modify them without a reproducible invalidation.

`M02/G02` now passes. In addition to the accepted conditional 32 by 32
engine-feasibility slice, the project has a frozen eight-template passenger-bus
corpus, disjoint seed ledger, native controlled reset and complete semantic
projection, fail-closed forbidden-scope validation, and a normal-command
scripted bus trajectory that reaches passenger delivery and positive income on
every template. It remains the frozen scenario/reset prerequisite for M03 and
later gates.

`M03/G03` passes as well. The source-integrated bridge freezes inherited-pipe
framing, typed lifecycle operations, process-based environment isolation, and
configurable 1-through-128-tick stepping.

`M04/G04` now passes. One source-integrated encoder freezes the structured and
32-channel spatial observation, normalization, missing values, coordinate rules,
and canonical bytes shared by trainer, evaluator, ONNX, and in-game consumers.
Two byte-identical campaigns provide 264,192 independent actual-engine semantic
comparisons and matched-control non-perturbation evidence.

`M05/G05` now passes. The action compatibility freezes 41 stable semantic indices,
boundary-bound legality masks, shared safe sampling, normal OpenTTD native command
paths, route rollback, six outcome classes, and detailed subcommand logs. Two
byte-identical campaigns compare 614 native/oracle masks and build profitable
passenger service on every template. The immediate next milestone is M06 reward,
termination, trajectory, and rollout-contract work only; PPO and CUDA training
remain downstream.

## M05/G05 completion checkpoint — 2026-08-01

The action compatibility identity is
`215c7d3ebeea97f1629debee4a2d10301838ccfd3085e4828685591677b58536`.
The native patch has SHA-256
`c512111713b3c03cd9d0fd6c621c69e1881f3aa837efc0d27e78e3f816a2d006`,
produces tree `ad0575b92f7975ef085e5f35bfe182a504d6cb51`, and has composed source
identity `9bb57367151fbf4eedcd802d179c946685a911bec9b99d7573501e0f52a3b2bd`.

Two complete roots, `m05-action-oracle-20260801-a` and `-b`, are retained under
`/home/thecl/.codex/artifacts/openttd-rl/` and are byte-identical. Their common
manifest SHA-256 is
`30700cfb8a556ddd7c23eec7463bac7a7f2bf365b9a94742fdeddd982cb2d7b8`.
All nine action families execute, all 614 production masks match the independent
oracle, route rollback and fatal failure classification pass, and all eight
templates deliver passengers and earn positive income. Preserve this boundary
while beginning M06.

## M04/G04 completion checkpoint — 2026-08-01

The observation compatibility identity is
`7f8a46af1fe2a2c23e755c71b3bc2d04c9a0d057c573e901e5c9ed9178ca13eb`.
The accepted result tree is `fe815570b5c816c6b324a9bf63d965157ea425c6`
and composed source identity is
`820cf3ee0fb36734c318cb260e6cc4567a2a9acc55c831d5b36d1875341b291e`.
The repeated native roots and exact evidence are recorded in
`docs/project/G04_GATE_REPORT.md`; preserve them as M05 and M06 inputs.

## M03/G03 completion checkpoint — 2026-08-01

The frozen bridge compatibility identity is
`4701a21ae106f6fa120db1b89c3929d16c29afafb8e0198126173137ed2af2d6`.
The ordered native patch has SHA-256
`6677d5a32abc5250394133e162236f1b2c5a9acfe19ea867a8b0512b10343c50`,
produces tree `39ed7069eca2c48c512a9bdd989c049aca3c5329`, and has composed source
identity `d5d14398d545c951b04325d91d444e6194553e537d4b1f16615cba44351f2ef1`.

Two complete roots, `m03-bridge-oracle-20260801-a` and `-b`, are retained under
`/home/thecl/.codex/artifacts/openttd-rl/` and are byte-identical. Their common
`manifest.json` SHA-256 is
`0a0664be8345ef79f6d01a7de404ad0f7427071849661a5e6dabd3025a960877`;
their common `commands.json` SHA-256 is
`9fe51ff69535e422db6286c1f5e3e83205fb41a953cdddb66f0129607a3ca4bf`.
All eight templates replay identically, the bridge-disabled M02 path retains its
accepted hashes, the two-process isolation test passes, 1/64/128-tick steps
advance exactly, invalid intervals fail without mutation, and the action-free
soak reaches 512 actions and 65,536 ticks. Preserve this boundary while beginning
M04.

## M02/G02 completion checkpoint — 2026-08-01

The ordered native scenario/reset patch has SHA-256
`334edfd7b8eca1b3250a074973071905744e55b669548a293022f4d988fa9425`.
It applies exactly after the accepted feasibility tree and produces tree
`551a99fbd33bd1b0f8c9ec35561deb0e893b81fe`, with composed source identity
`edc76541bfda23c2916fc85d499e6e0d5a5cefaad09f40bf19972c2d3307385e`.
The current Ubuntu executable used by the accepted oracle has SHA-256
`91950be18634050d6b74cdfe08c22aba4c4f806a88c2116fa6400ac06dee2185`.

Two complete offline oracle roots, `m02-reset-oracle-20260801-a` and `-b`, are
retained under `/home/thecl/.codex/artifacts/openttd-rl/`. They are byte-identical
in full. Their common `manifest.json` SHA-256 is
`8baeea1e49b04936f3403fec338392aa0ade7c8b1171a6e8fb15ce758ba869ca`;
their common `commands.json` SHA-256 is
`fff7e54f5ccd93fcec72698ceffc4c22a1b047356439ffd41633de2c0e9ef5f5`.
Each root contains two clean-process executions and one same-process two-reset
execution for all eight templates, including canonical reset and trajectory
reports. All 96 upstream unit cases (2,193 assertions), both native regressions,
and the focused 39-test M02 repository suite pass.
The complete V1 traceability gate also passes all 125 repository tests with 227
requirements, 19 test-suite mappings, 19 passing G02 requirements, and zero
nonclosed defects.

The persistent offline cache now contains the exact three requested Ubuntu
binutils 2.42-4ubuntu2.10 archives and the exact OpenGFX 8.0 archive. The gate
contract, identities, automated QA, retained evidence, and manual QA are recorded
in `docs/project/M02_SCENARIO_RESET_CONTRACT.md` and
`docs/project/G02_GATE_REPORT.md`. Preserve this boundary and do not redesign it
while beginning M04.

## M02 feasibility checkpoint — 2026-08-01

Work is again at a safe, passing component boundary. The default-off
`OPTION_RL_ENVIRONMENT` delta is isolated after the immutable M01 source series.
Accepted roots `m02-map-feasibility-20260801-n` and `-o` each pass four clean
profiles, and the authoritative comparison passes with identity
`249ed176c3720f00d41be1504999e35f83ef658dbb2081858126bcbb92382e6c`.

The accepted M02 prepared tree is
`eba8f4bd3c37042c184d968d2f038864184e3132`, composed source identity is
`2140e34ccee8534dbf712487acd2225eda4b66d1c807b9e0ce07243ba40afdbd`,
and report identity is
`5ccf48b693ea4dc2ea0a2143655f1b3dd0e274b6cd84be9bacc7bad7ea884841`.
All four 64 by 64 map projections equal the accepted M01 reference hash
`240f8c1c92731f16e445d0ff7ed097a61b2dd88ce3438e764829a90339b8be77`.
Every flag-on profile produces a true-empty 32 by 32 map containing exactly 900
clear and 124 void tiles with map hash
`7d342e9d3808f180f14ba1c196f9c68d967ed17ea80bdddc0dba47bdc957a003`,
then reloads/soaks it for 4,194,304 ticks and runs generated 32 by 32 terrain for
65,536 ticks.

The complete evidence, source corrections, executable hashes, commands, and
manual QA procedure are recorded in `docs/project/M02_MAP_FEASIBILITY.md`.
Failed development roots remain diagnostic history and are not accepted evidence.
Do not rebuild the accepted roots unless a reproducible defect invalidates them.

## G01 completion checkpoint — 2026-08-01

Work is at a safe, passing milestone boundary. `G01` passes; no `M02` code had
been written at the instant of this checkpoint.

Completed immediately before the stop:

- the external dependency lock at `config/v1/dependency-lock.json` freezes 25
  files (1,556,894,253 bytes), including every exporter wheel and the four NVIDIA
  runtime wheels needed by LibTorch; lock SHA-256 is
  `600fa461776dd6d014f155c7e124167ba8fdb165ffefc48d09ab9cbd1ce90c9b`;
- `scripts/v1/validate_dependency_cache.py` validates the strict schema, schema
  digest, unique identity/path inventory, every byte count/digest, rejection of
  unlisted archives, and required extraction markers; the real offline cache
  passes with 25 artifacts and six extraction records;
- nine dependency-cache mutation tests pass;
- the pinned Python 3.12/PyTorch 2.13 CPU exporter produced two byte-identical
  opset-18 `Add`/`MatMul`/`Relu` graphs with SHA-256
  `2d1bbd70474ae0eae9b97b3349b1285d09b8bca577487a67c24823cdbdc6b31d`;
- the native probe now passes four tests: LibTorch CPU/CUDA/autograd ABI, CUDA
  compute-capability-12 cubin/PTX execution, ONNX Runtime 1.28 CPU ABI, and actual
  ONNX Runtime execution of that exported graph with checked names/shapes/values;
- `scripts/v1/toolchain_probe.sh` now reconstructs the 17-distribution exporter
  environment from locked wheels, enforces every pinned tool/host version,
  configures and builds without warnings, checks the exact CTest inventory,
  validates `sm_120` cubin plus `compute_120` PTX emission, rejects unresolved
  runtime libraries, and emits strict machine/human reports;
- ten toolchain-runner mutation/unit tests pass;
- two fresh runner roots (`m01-toolchain-probe-runner-20260731-e` and `-f`)
  produced byte-identical JSON and human reports, ONNX models, and native probe
  executables; probe identity is
  `832f1faf8c4927f148bd8933dd43873ef06068afcbeff621481275fb4e6acd3c`.
- the build-input lock freezes 34 exact local Debian archives (37,421,106 bytes)
  for the private OpenTTD sysroot overlay; lock SHA-256 is
  `099675da5a508cd5a58405767e7713f5dbbc810b7dae52e6fc2687341bbc6985`;
- the accepted GCC 13 portability patch has SHA-256
  `0d056466b1abf5df755790f691c99c1db32d3e5f8498fae273abf7d4e4f2ac33`,
  the prepared tree is `c63a866377547631870efb48ac547948da19916a`, and four
  accepted build runs reproduced preparation identity
  `17a41503ab80f3c01f4ed8e4e24b7a32b1cc0092644c2ae421096a4b4ddb15df`;
- clean headless roots `m01-headless-build-20260801-k` and `-l` each passed
  96 tests and installed 161 byte-identical files; both have build identity
  `102f07d8595673a06888bb935c809c47ea3326f8d66be158a1588e32ec530de3`
  and executable SHA-256
  `b24a50994326e2480de38d633ef34c0516e2565ed5aa201ff4e6c13e235b45e3`;
- clean playable roots `m01-playable-build-20260801-f` and `-g` each passed
  their exact two-test inventory, a 128-tick null smoke, and normal SDL dummy
  main-game startup/shutdown; both have build identity
  `5e50757e298b5c241655663e94a5ce0dde0a69eb4e5d811c467fe2dc63cf3c7b`
  and executable SHA-256
  `f55efe3ebda2b5d7b236ffcaefadb7828cfcb44740ab141bb25e3de720d8a1da`;
- all four successful runs retained complete normalized command records, exact
  compiler/build-tool versions, per-command timing, runtime dependency closure,
  tests, smoke evidence, and per-installed-file hashes, then removed their build
  directories.
- `config/v1/build-profile-matrix.json` freezes seven conceptual profiles and the
  independent RL bridge, in-game inference, telemetry, and assertion flags; its
  canonical identity is
  `677619eff8daa697340e0de28abdad4a9472e83578da2b9591376f8c8ea05450`;
- the accepted dedicated binary is explicitly build evidence only; the eventual
  worker remains a regular non-dedicated process with controlled null video;
- runtime-resource roots `m01-runtime-resources-20260801-c` and `-d` each passed
  four workloads with one warm-up and five retained samples, including startup,
  CPU time, RSS, headless ticks/second, and paused playable idle use;
- provenance roots `m01-dependency-provenance-20260801-a` and `-b` are
  byte-identical and cover 25 toolchain artifacts, 34 build-overlay packages,
  explicit OpenGFX, OpenTTD source, and 90 file-backed runtime dependencies;
- closure roots `m01-g01-audit-20260801-a` and `-b` emitted byte-identical reports
  with 15 independent checks and audit identity
  `7312e80f167a282c3b2d297737f64352838605fb3a28a0b07f7334008e67a5b7`.

The consolidated reports are `docs/project/M01_TOOLCHAIN_PROBE.md`,
`docs/project/M01_OPENTTD_BUILD_REPRODUCIBILITY.md`,
`docs/project/M01_BUILD_PROFILE_RESOURCE_PROVENANCE.md`, and
`docs/project/G01_GATE_REPORT.md`. Durable final generated evidence is under the
owner-only paths
`/home/thecl/.codex/artifacts/openttd-rl/m01-toolchain-probe-runner-20260731-e`
and `-f`, the headless `k`/`l` roots, and the playable `f`/`g` roots named above.
Earlier manual/development roots are diagnostic history, not accepted evidence.

Historical G01 resumption point (now completed by the M02 feasibility checkpoint):

1. preserve the accepted probe and four build roots; do not rebuild or modify them
   unless a reproducible failure invalidates their evidence;
2. keep `M01/G01` `PASS` unless a reproducible defect invalidates its accepted
   identities;
3. begin `M02` with the conditional 32 by 32 feasibility patch only;
4. do not begin the bridge, observations/actions/reward, PPO, CUDA workload, or
   production ONNX integration before their owning gates.

No M02 scenario work, environment bridge, or learning code had started at that
historical checkpoint. The later completed scenario/reset, bridge, observation,
and action/mask work is recorded above; rewards, trajectories, and learning code
have not begun.

## Authority and read order

Read and apply in this order:

1. `GOAL.md` — active scope and Version 1 completion authority;
2. `docs/project/REQUIREMENTS.md` — atomic normative requirements;
3. `docs/project/ROADMAP.md` — milestone graph and exit gates;
4. `docs/architecture/V1_ARCHITECTURE.md` — component boundaries;
5. `docs/contracts/V1_ENVIRONMENT.md` — reset/step/observation/action/reward plan;
6. `docs/training/PPO_AND_MODEL_PIPELINE.md` — trainer/export/playback plan;
7. `docs/project/VERIFICATION.md` — required proof;
8. `docs/project/LEGACY_P0_TRANSITION.md` — existing-work disposition;
9. accepted V1 ADRs and machine schemas after they are created;
10. legacy P0 contracts and reverse-engineering notes as historical evidence only.

Pinned OpenTTD source and reproducible execution remain authority for actual engine
semantics. If a plan guesses incorrectly about the engine, investigate and update
the design through an ADR rather than forcing the engine into the guess.

## Hard truth about the checkout

At the 2026-07-31 planning audit:

- the outer repository is on `fix/p0-build-portability` at the same recorded tip as
  `main`/`origin/main`;
- the worktree is dirty with modified tracked P0 scripts/tests/tape artifacts and
  untracked instrumentation/contract work;
- that work is user-owned and must not be reset, overwritten, or casually moved;
- a pinned OpenTTD source/build/evidence substrate exists;
- the implemented gameplay fixture is 64 by 64 road freight, not the V1 scenario;
- C17 tape/parity tooling exists but has unfinished changes;
- no accepted V1 environment, observation/action/reward contract, PPO trainer,
  CUDA learning path, evaluator, ONNX pipeline, or in-game neural agent exists.

Consequently, `G00`, `G01`, and `G02` pass. The M02 controlled passenger-bus
scenario/reset and scripted trajectory are accepted, while every downstream
product gate remains nonpassing regardless of how much legacy P0 machinery
exists.

Always re-run `git status --short` and inspect actual files because this status can
change after the handoff was written.

## Active scope

Version 1 includes only:

- 32 by 32 default-economy scenarios;
- one learning company during initial training;
- passengers and buses;
- roads, required road-vehicle depots, and bus stops;
- deterministic controlled reset/evaluation;
- structured and spatial observations;
- explicit actions with legal masks;
- separately logged reward components;
- C++ PPO with structured MLP, spatial CNN, and combined models;
- measured CUDA acceleration;
- batched headless environments;
- terminal and structured monitoring;
- independent evaluation including random, scripted, and an existing-AI workflow;
- checkpoints, ONNX export, complete model packages, three-runtime equivalence;
- normal-game neural-agent playback and inspection.

Version 1 excludes every post-V1 transport/cargo/gameplay system and every
additional RL algorithm. The presence of a legacy truck/industry fixture is not
authorization to expand scope.

## Milestone state

| Milestone | Description | Status at audit | Blocking fact |
|---|---|---|---|
| `M00` | authority, preservation, machine traceability, reuse ADRs | `PASS` | `G00_GATE_REPORT.md` records restored snapshot and combined V1/P0 validation |
| `M01` | reproducible V1 OpenTTD/toolchain/headless/playable profile | `PASS` | `G01_GATE_REPORT.md` records the deterministic 15-check closure audit |
| `M02` | 32x32 passenger-bus scenario/reset | `PASS` | `G02_GATE_REPORT.md` records repeated native reset and scripted trajectory evidence |
| `M03` | synchronized headless bridge | `PASS` | `G03_GATE_REPORT.md` records repeated lifecycle, tick, isolation, and non-perturbation evidence |
| `M04` | observation/preprocessing contract | `PASS` | `G04_GATE_REPORT.md` records exhaustive semantics and non-perturbation |
| `M05` | action/mask/execution contract | `PASS` | `G05_GATE_REPORT.md` records mask-oracle and useful-service evidence |
| `M06` | reward/episode/trajectory contract | `NOT_STARTED` | no V1 artifacts |
| `M07` | CPU PPO and structured MLP | `NOT_STARTED` | G06 remains open |
| `M08` | CNN/combined/measured CUDA | `NOT_STARTED` | PPO/CPU baseline absent |
| `M09` | independent evaluation/baselines | `NOT_STARTED` | evaluator and policies absent |
| `M10` | checkpoint/ONNX/package/equivalence | `NOT_STARTED` | model pipeline absent |
| `M11` | normal-game neural agent/inspection | `NOT_STARTED` | inference package absent |
| `M12` | clean reproduction and V1 release | `NOT_STARTED` | all preceding gates open |

## Completed work package: M00

### M00-A — preserve and classify current work

Before any structural edit or branch change:

1. capture full tracked/untracked/submodule status and diff statistics;
2. identify which changes belong to the unfinished legacy patch series;
3. choose a recoverable preservation mechanism appropriate to the user's workflow;
4. record the exact snapshot identity in the V1 transition evidence;
5. do not use destructive reset/checkout/clean commands.

Outputs:

- current-worktree inventory;
- preservation record and recovery instructions;
- explicit list of files that V1 work may safely add/change.

### M00-B — V1 machine requirements and defects

The initial separate project-level artifacts now exist without mutating the
historical P0 registries:

```text
docs/project/schema/requirements-v1.schema.json
docs/project/schema/defect-ledger-v1.schema.json
docs/project/requirements-v1.json
docs/project/defects-v1.json
scripts/v1/traceability.sh
scripts/v1/validate_traceability.py
tests/project/traceability/test_v1_traceability.py
```

The validator currently covers 227 atomic requirements, 19 planned/implemented
test suites, all eight `DONE-*` aggregates, source-brief identities, legacy-evidence
separation, and defect propagation. It must continue to:

- include every ID from `docs/project/REQUIREMENTS.md` exactly once;
- track implementation, tests, evidence, milestone/gate, status, and reviewer
  notes;
- enforce bidirectional test mapping;
- compute aggregate `DONE-*` states from dependencies;
- reject `PASS` without existing schema-valid evidence;
- reject `PASS` affected by an open defect;
- distinguish `LEGACY_ONLY` evidence and prevent it closing a V1 bus row;
- reject post-V1 work as a substitute for an open V1 requirement.

Write self-tests that prove each rejection rule by mutating a small valid fixture.

### M00-C — blocking ADR set (accepted; implementation evidence pending)

ADRs 0008 through 0013 now record evidence-backed decisions for:

1. project basis, license, publication, and upstream boundary;
2. exact OpenTTD source revision and patch-maintenance strategy;
3. headless/playable integration design and safe engine boundaries;
4. supported hosts, C++/CUDA toolchains, tensor backend, ONNX runtime/opset;
5. legacy P0 component disposition and preservation;
6. experiment/evidence storage, clean/dirty run policy, and model artifact policy.

Their acceptance does not pass `G01`, `G03`, `G08`, `G10`, or `G11`. Exact
dependency archives, ABI probes, source preparation, integration hooks, and runtime
equivalence remain implementation evidence rather than assumptions.

### M00-D — document authority enforcement (implemented)

- add a concise supersession banner to historical top-level planning/report files;
- ensure all README/navigation links resolve;
- check that active documents do not call road freight, 64 by 64, scalar gameplay
  port, or CUDA simulation the active first product;
- keep legacy internal wording intact where it records historical truth;
- add a doc-lint test for broken project links and conflicting active-scope phrases.

### M00 exit evidence

`G00` passed after verifying that:

- worktree changes are recoverable;
- machine requirements/defect registries and mutation/self-tests pass;
- all blocking ADRs are accepted or explicitly leave `G00` nonpassing;
- top-level authority is unambiguous;
- no user-owned legacy artifact was lost;
- a clean V1 implementation work strategy is ready.

## Completed work package: M01 reference profile

After `G00`, the project adapted rather than silently reused the existing build
machinery. The following M01 work now passes.

### Required decisions and implementation

- acquire and verify the ADR 0009 OpenTTD 15.3 commit without switching the P0
  submodule worktree (implemented and double-preparation tested; see
  `docs/project/M01_SOURCE_PREPARATION.md`);
- define headless-training, playable-inference, debug/assert, sanitizer, CPU release,
  and CUDA build profiles;
- acquire and validate the ADR 0011 LibTorch/PyTorch/ONNX Runtime pins and opset;
- inventory supported CUDA toolkit, driver, GPU architectures, and CPU fallback;
- isolate runtime configuration/content and disable disallowed content/systems;
- retain exact upstream tests and add feature smoke tests;
- ensure training dependencies are absent from inference-only installation;
- record all commands, manifests, results, hashes, and license/provenance.
- preregister and execute repeated runtime-resource measurements;
- run the deterministic `G01` closure audit twice.

### Reuse candidates

Review these first:

- `oracle/runner/{common,configure_reference,build_reference,test_reference}.sh`;
- `oracle/manifests/baseline/*` and schemas;
- `evidence/p0/port001/*` as historical reproducibility evidence;
- P0 contract tests for drift/identity behavior.

Do not rename their P0 outputs into V1 outputs. Create new profiles/results and
preserve backward tests where practical.

### G01 completion test

Two clean build/install/test/smoke runs of both headless and playable V1 variants
must match their declared manifests, fail on dependency/profile drift, run offline
after acquisition, and retain complete evidence. This test now passes; see
`docs/project/G01_GATE_REPORT.md`.

## Completed work package: M02 bus scenario/reset

The prerequisite conditional 32 by 32 engine-feasibility slice and the completed
scenario/reset layer pass. Preserve their accepted source identities and
repeated evidence; do not broaden those patches while designing M03.

The implementation did not adapt `road_freight_v1` by changing a label. It uses
a separate scenario contract and fixture generator for 32 by 32 passenger buses.

### First design questions to resolve from pinned engine evidence

- start year and selected available bus engine;
- default-economy settings and every necessary deterministic override;
- number/range/layout of towns on 32 by 32;
- town-growth and passenger-production behavior;
- initial balance/loan and build affordability;
- breakdown/inflation/vehicle-aging policy;
- fixed fixture versus seeded procedural family;
- action/tick/calendar horizon;
- semantic state required to prove reset equality;
- train/development/final seed split derivation.

### Required acceptance trajectory

A non-learning scripted controller must, using only future V1-legal operations:

1. inspect/select two towns;
2. construct or reuse a road connection;
3. place two valid bus stops and a depot;
4. buy a bus;
5. create/assign the two-stop route;
6. start service;
7. reach pickup and delivery;
8. record passenger delivery and revenue;
9. continue long enough to exercise operating profit/expenses.

This trajectory becomes a core integration fixture for `M03` through `M06`.

## Subsequent implementation order

After `G03`, follow `docs/project/ROADMAP.md` exactly:

- `M04`: structured/spatial observations;
- `M05`: bounded actions and legal masks;
- `M06`: rewards, episode semantics, trajectories;
- `M07`: CPU PPO and structured MLP;
- `M08`: CNN, combined model, profiling, measured CUDA;
- `M09`: evaluator and baselines;
- `M10`: ONNX/package/equivalence;
- `M11`: normal-game playback;
- `M12`: clean full reproduction/release.

Never move CUDA, model export, or playback earlier by weakening the environment
contract; early interface prototypes are allowed only when clearly nonpassing.

## Required implementation discipline

### Contracts before data generation

Freeze schema/version identities before accepting training data. If a contract
changes, old data/checkpoints/packages are migrated through a tested transformation
or rejected explicitly.

### One semantic implementation

Share C++ observation preprocessing, action/mask interpretation, and inference
logic among trainer, evaluator, exporter validation, and in-game controller.
Where binary sharing is impossible, golden equivalence is mandatory.

### Actual-engine tests

Mocks cannot prove bus purchase, stops, orders, passenger delivery, profit,
bankruptcy, or tick behavior. Pair code-level unit tests with actual pinned OpenTTD
integration at safe boundaries.

### CPU truth before CUDA speed

Keep a deterministic CPU/debug reference. Profile the real workload, implement the
smallest justified CUDA path, prove parity, then claim performance with workload and
hardware stated.

### Independent evaluation

Training code cannot update final evaluation partitions, normalization, policy, or
metric definitions. Freeze final protocols before results and retain per-seed raw
records.

### Failure honesty

Mask violation, environment desynchronization, nonfinite training, corrupt
checkpoint/package, or lost mandatory log/evidence is not an ordinary low reward.
Stop or quarantine the affected result according to the defect policy.

## Completion vocabulary

- `implemented`: code exists; tests/evidence may not.
- `verified`: named focused requirements pass with authoritative evidence.
- `gate pass`: every requirement assigned to that gate passes and no blocking
  defect applies.
- `development policy improvement`: useful `M07` signal, not final quality.
- `accepted model`: passes independent evaluation and provenance requirements.
- `export candidate`: ONNX bytes exist but equivalence/package may be open.
- `playback candidate`: model takes actions in game but full equivalence/usability
  may be open.
- `Version 1 complete`: only `G12`, after the atomic completion audit.

Do not use “done”, “complete”, or “reproducible” without naming the relevant scope
and evidence.

## Handoff checklist for every implementation turn

Before changing code:

1. inspect current worktree/submodule state;
2. identify governing requirement IDs and milestone gate;
3. inspect applicable ADRs and legacy disposition;
4. preserve overlapping user changes;
5. define tests/evidence that prove the exact requirement.

Before handing off:

1. run focused tests and the proportional quality matrix;
2. inspect the diff and confirm no forbidden scope or accidental legacy loss;
3. update machine traceability and defect state honestly;
4. record commands/results/artifacts and any unverified assumptions;
5. state the next dependency, not an unrelated attractive feature.

## Current next action

Begin M06 only: freeze reward components, timing, units, aggregation, termination,
truncation, trajectory records, and rollout storage on the accepted M04/M05
boundaries. Prove reward deltas against engine state, run exploit policies, and
retain repeated serialization evidence. Do not begin PPO, production ONNX, or
neural in-game control before their owning gates.
