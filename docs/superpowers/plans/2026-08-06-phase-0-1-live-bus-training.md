# Phase 0/1 Live Bus Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Do not begin
> a later milestone group until the preceding stop gate is reviewed and passes.

**Goal:** Build the first real end-to-end learning increment: an isolated
OpenTTD 15.3 environment streams native M15 observations and legal candidates,
one small generalist neural network chooses real passenger-bus actions, and an
optimizer-free checkpoint builds, operates, saves, reloads, and visibly proves
one profitable 64x64 vanilla bus service.

**Architecture:** Add a versioned `ORL2` inherited-pipe environment beside the
unchanged V1 bridge. Add cumulative OpenTTD patches after the frozen M23
visible-controller foundation; do not edit the accepted 0001/0002 patches. The
bridge emits the frozen M15 observation/candidate tensors and accepts a masked
program/family/candidate selection. A persistent road-passenger transaction
state machine narrows legal choices without choosing for the policy. The
existing 1,457,520-parameter M22 model gains a no-new-parameters full-output
method, behavior-cloning warm start, and joint hierarchical PPO. A new full
ONNX package and runtime are additive to the two frozen compact M23 packages.

**Tech Stack:** OpenTTD 15.3 C++20 command API, inherited POSIX pipes, canonical
JSON, fixed little-endian binary tensors, CRC32C, Python 3.12 standard library,
`jsonschema`, C++20, LibTorch, clipped PPO, ONNX opset 18, ONNX Runtime, CMake,
Ninja, `unittest`, CTest, Git, SHA-256.

---

## Scope and stop gates

This plan implements only design Phases 0 and 1. It does not add bus networks,
128x128 maps, trucks, rail, water, air, multimodal play, opponents, NewGRFs, or
a V2 release claim.

The work is divided into four sequential milestone groups:

1. **A — contracts, device profiles, and wire protocol** (Tasks 1-3);
2. **B — native live environment and deterministic executor proof** (Tasks
   4-8);
3. **C — real neural training and promotion** (Tasks 9-17);
4. **D — deployment, visible playback, and repository integration** (Tasks
   18-20).

At each stop gate:

- run every focused test named in the group;
- run `scripts/v2/verify.sh --tier fast`;
- inspect `git diff --check` and `git status --short`;
- commit only the group's intentional files;
- do not manufacture retained evidence for a live command that did not run.

## Frozen boundaries

- Do not edit `config/v1`, `scripts/v1`, released V1 packages, or V1 evidence.
- Do not edit accepted M15-M22 evidence, checkpoints, seed results, or final
  manifests.
- Do not edit the frozen M23 compact package identities, ONNX graphs, golden
  corpus, equivalence reports, or patches `m23/0001` and `m23/0002`.
- Keep the current M22 `forward()` result byte/float equivalent. The new full
  output is an additive method and checkpoint parameters remain unchanged until
  Phase 1 training begins.
- Keep the existing production compute-capability-12.0 build and evidence
  intact. Local CPU/`sm_75` work uses a new development profile.
- The current PC is used as found. Do not install or replace a global NVIDIA
  driver, CUDA toolkit, LibTorch, or system package. A project-local dependency
  path may be used only when supplied explicitly by the operator.
- No opponent is started in any Phase 0/1 scenario.
- A deterministic teacher may label legal training actions only. It is forbidden
  from evaluation, deployment, reward calculation, or action substitution.

## Patch workflow

Create additive patches under:

```text
integration/openttd/patches/15.3/m23/live/
  0003-Expose-live-M15-boundaries.patch
  0004-Add-road-passenger-transaction-executor.patch
  0005-Add-ORL2-live-training-bridge.patch
  0006-Persist-live-controller-state.patch
  0007-Run-full-policy-bus-actions-in-visible-games.patch
  README.md
  series
```

`series` lists exactly those five names. Every patch uses the fixed project
author and date conventions, applies with `git apply --check
--whitespace=error-all` to the exact preceding tree, and has a source-inventory
test. Generate a patch from an isolated OpenTTD worktree; never hand-edit an
accepted earlier patch to make a new one apply.

## Target Phase 1 contract

- map: 64x64, temperate, vanilla/OpenGFX, 1950, one human-controlled neural
  company, no opponent;
- action program: `wait` and `road-passenger` only;
- action families: the existing 12 M15 families, phase-masked by transaction
  state;
- environment workers: four initially, one OpenTTD process per game;
- training: three deterministic initialization streams, behavior-cloning warm
  start, then joint clipped PPO;
- development: two disjoint 20-case banks, fresh process per case, no retry or
  replacement;
- promotion: at least 18/20 successes on each bank, positive median operating
  profit, no bankruptcy or harness failure, exact save/load continuation, and
  unchanged frozen regression gates;
- success: owned connected road, two owned bus stops, one owned road depot, one
  owned passenger bus with two valid station orders, moving service, positive
  passenger delivery, and positive operating income.

---

### Task 1: Freeze the Phase 0/1 development contract

**Files:**

- Create: `config/v2/m23-road-passenger-development-contract.json`
- Create: `docs/project/schema/v2-m23-road-passenger-development-contract.schema.json`
- Create: `scripts/v2/validate_m23_road_passenger_contract.py`
- Create: `tests/project/v2/test_v2_m23_road_passenger_contract.py`
- Modify: `scripts/v2/verify_driver.py`
- Modify: `tests/project/v2/test_v2_verify_driver.py`

- [ ] **Step 1: Write failing schema, semantic, and inventory tests**

Test exact top-level keys, canonical compact JSON, a self-hash over the schema,
parent identities, 64x64/no-opponent scope, all twelve M15 families, program
mask `{wait, road-passenger}`, protocol limits, seed-set separation, reward
constants, two 20-case development banks, promotion thresholds, hardware
profiles, teacher prohibition at evaluation, and sealed final inputs.

Include named mutants for duplicate JSON keys, changed parent hash, opponent
enablement, map growth, family omission, overlapping seeds, fewer than 20 cases,
success below 18/20, teacher at evaluation, unbounded frame, and rewriting the
compute-12.0 profile.

- [ ] **Step 2: Run the focused tests and confirm the missing module failure**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_road_passenger_contract -v
```

Expected: `ImportError` for `validate_m23_road_passenger_contract`.

- [ ] **Step 3: Implement strict loading and semantic validation**

The validator public boundary is:

```python
class M23RoadPassengerContractError(ValueError): ...

def load_strict_json(path: pathlib.Path) -> dict[str, object]: ...
def validate_semantics(value: dict[str, object]) -> None: ...
def validate(contract: pathlib.Path, schema: pathlib.Path) -> dict[str, object]: ...
```

Derive all train/development seeds with the frozen SHA-256-first-31-bits rule
and store the resulting integers in the contract. Reward values are exact:

```text
road_connected_once       +0.10
first_stop_once           +0.05
second_stop_once          +0.05
depot_once                +0.05
bus_owned_once            +0.10
two_orders_once           +0.10
service_started_once      +0.10
first_delivery_once       +0.50
delivery_delta            min(delta, 128) / 512
operating_profit_delta    clamp(delta, -50000, 50000) / 200000
foreseeable_rejection     -0.02
excess_idle_boundary      -0.002 after four avoidable waits
bankruptcy                -2.00
```

Milestone reversal subtracts the exact earlier credit. Total pre-delivery
milestone credit is capped at `0.50`.

- [ ] **Step 4: Add the validator to the contract tier exactly once**

Update the inventory count and ordering tests before changing
`verify_driver.py`. This contract validator belongs to `contract`, not `full`.

- [ ] **Step 5: Run tests and commit**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_road_passenger_contract \
  tests.project.v2.test_v2_verify_driver -v
git diff --check
git add config/v2/m23-road-passenger-development-contract.json \
  docs/project/schema/v2-m23-road-passenger-development-contract.schema.json \
  scripts/v2/validate_m23_road_passenger_contract.py \
  scripts/v2/verify_driver.py tests/project/v2/test_v2_m23_road_passenger_contract.py \
  tests/project/v2/test_v2_verify_driver.py
git commit -m "m23: freeze live bus development contract"
```

### Task 2: Add non-destructive local hardware profiles

**Files:**

- Create: `training/v2/live/CMakeLists.txt`
- Create: `scripts/v2/probe_m23_live_device.py`
- Create: `tests/project/v2/test_v2_m23_live_device.py`
- Create: `docs/project/schema/v2-m23-live-device-report.schema.json`

- [ ] **Step 1: Write profile-selection tests**

Test `cpu`, `local-sm75`, and `production-sm120`. The production profile keeps
the existing exact CUDA 13.0/LibTorch 2.13/architecture 12.0 requirements. The
local profile requires device capability 7.5 but accepts dependency roots only
through explicit absolute CLI arguments. The CPU build must not locate CUDA or
link NVIDIA libraries. The read-only probe may inventory `nvidia-smi` when it is
already present, but CPU configuration cannot require it.

Mock the current inventory and assert the report records RTX 2070, capability
7.5, 8,192 MiB, driver/UMD versions, eight CPUs, 16 GiB RAM, and the absence of
`nvcc` without treating that absence as permission to install anything.

- [ ] **Step 2: Confirm failure**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_live_device -v
```

Expected: missing probe module and live CMake project.

- [ ] **Step 3: Implement the standalone live build profile**

Use `V2_LIVE_DEVICE_PROFILE` with default `cpu`. Require an explicit
`Torch_DIR` for every profile. `local-sm75` sets only its build's
`TORCH_CUDA_ARCH_LIST=7.5`; `production-sm120` sets `12.0`. Never set a cache or
environment value outside the build directory.

The probe exits `0` with `status=CPU_FALLBACK` when no explicitly supplied
project-local CUDA LibTorch/toolkit can build `sm_75`. It exits `2` only for a
malformed request or an identity mismatch in a supplied dependency root.

- [ ] **Step 4: Run the current-device probe**

```bash
python3 scripts/v2/probe_m23_live_device.py \
  --profile cpu --output /tmp/m23-live-device.json
```

Expected on this PC: a canonical report using CPU fallback and recording the
RTX 2070 inventory; no package installation or system mutation.

- [ ] **Step 5: Test and commit**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_live_device -v
git diff --check
git add training/v2/live/CMakeLists.txt scripts/v2/probe_m23_live_device.py \
  tests/project/v2/test_v2_m23_live_device.py \
  docs/project/schema/v2-m23-live-device-report.schema.json
git commit -m "m23: add local live-training device profiles"
```

### Task 3: Define and cross-check the `ORL2` live protocol

**Files:**

- Create: `scripts/v2/m23_live_protocol.py`
- Create: `training/v2/include/openttd_rl/v2/m23_live_protocol.h`
- Create: `training/v2/src/m23_live_protocol.cpp`
- Create: `training/v2/tests/m23_live_protocol_gate.cpp`
- Create: `tests/project/v2/test_v2_m23_live_protocol.py`
- Modify: `training/v2/live/CMakeLists.txt`

- [ ] **Step 1: Write Python and C++ conformance tests**

Freeze a 40-byte little-endian header with magic `ORL2`, version `1`, message
type, flags, zeroed reserved fields, request ID, metadata length, observation
length, candidate length, and CRC32C. Maximum total payload is 8 MiB. Message
types are `RESET`,
`BOUNDARY`, `STEP`, `SAVE`, `LOAD`, `CLOSE`, and `ERROR`.

Test empty/maximum legal frames, chunked pipe reads, timeout, bad magic/version,
unknown type/flags, integer overflow, oversize lengths, truncation, bad CRC,
noncanonical metadata, duplicate JSON keys, trailing bytes, and request-ID
mismatch. Python-encoded fixtures must decode in C++; C++-encoded fixtures must
decode in Python.

- [ ] **Step 2: Confirm the missing-code failures**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_live_protocol -v
```

- [ ] **Step 3: Implement the smallest codec**

Expose these C++ types:

```cpp
enum class M23LiveMessage : std::uint16_t {
    Reset = 1, Boundary = 2, Step = 3, Save = 4,
    Load = 5, Close = 6, Error = 7,
};

struct M23LiveFrame {
    M23LiveMessage type;
    std::uint16_t flags;
    std::uint64_t request_id;
    std::string metadata;
    std::vector<std::uint8_t> observation;
    std::vector<std::uint8_t> candidates;
};
```

Implement exact read/write loops over already-open descriptors. Do not open a
socket, connect to a network address, or accept a path in the codec.

- [ ] **Step 4: Build the CPU protocol gate and run both suites**

```bash
cmake -S training/v2/live -B build/v2-live-cpu -G Ninja \
  -DV2_LIVE_DEVICE_PROFILE=cpu -DTorch_DIR=/absolute/project-local/cpu-libtorch/share/cmake/Torch
cmake --build build/v2-live-cpu --target m23_live_protocol_gate
ctest --test-dir build/v2-live-cpu -R v2_m23_live_protocol --output-on-failure
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_live_protocol -v
```

If no explicit CPU LibTorch root is available yet, run the Python conformance
suite now and record the C++ build as an unmet local dependency, not a passing
gate.

- [ ] **Step 5: Commit**

```bash
git add scripts/v2/m23_live_protocol.py training/v2/live/CMakeLists.txt \
  training/v2/include/openttd_rl/v2/m23_live_protocol.h \
  training/v2/src/m23_live_protocol.cpp training/v2/tests/m23_live_protocol_gate.cpp \
  tests/project/v2/test_v2_m23_live_protocol.py
git commit -m "m23: define checksummed live environment protocol"
```

## Stop gate A

Run the three focused Python suites, the C++ protocol gate when its explicit
dependency exists, and the fast tier. Review the frozen contract and binary
protocol before touching OpenTTD source.

---

### Task 4: Expose in-memory M15 observation and candidate boundaries

**Files:**

- Create: `integration/openttd/patches/15.3/m23/live/0003-Expose-live-M15-boundaries.patch`
- Create: `integration/openttd/patches/15.3/m23/live/series`
- Create: `integration/openttd/patches/15.3/m23/live/README.md`
- Create: `tests/project/v2/test_v2_m23_live_boundary_source.py`

- [ ] **Step 1: Write failing patch scope and API tests**

Require 0003 to modify only `src/CMakeLists.txt`, `src/rl_v2_action.cpp/.h`, and
`src/rl_v2_observation.cpp/.h`, plus new
`src/rl_v2_live_boundary.cpp/.h`. Require the patch to apply after 0002 and
forbid V1 files, qualification entrypoints, direct company-money mutation, and
all transport modes except existing M15 road-passenger families.

- [ ] **Step 2: Confirm the missing patch failure**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_live_boundary_source -v
```

- [ ] **Step 3: Refactor the cumulative OpenTTD source in an isolated worktree**

Create a facade without changing the frozen serialized bytes:

```cpp
struct RlV2LiveBoundary {
    std::vector<std::uint8_t> observation;
    std::vector<std::uint8_t> candidates;
    std::array<std::uint8_t, 12> family_mask;
    std::array<std::uint8_t, 4096> candidate_mask;
    std::array<std::uint8_t, 4096> candidate_family;
    std::string observation_sha256;
    std::string candidate_sha256;
    std::string snapshot_token;
};

struct RlV2LiveActionResult {
    std::string status;
    std::string family;
    std::string stable_key;
    std::string state_before;
    std::string state_after;
    std::vector<RlV2CommandReceipt> commands;
    bool rolled_back;
};

RlV2LiveBoundary BuildRlV2LiveBoundary(const RlV2LiveMaskFilter &filter);
RlV2LiveActionResult ExecuteRlV2LiveCandidate(
    std::string_view snapshot_token, std::uint16_t family, std::uint16_t row);
```

`BuildRlV2LiveBoundary` must call the same encoders/enumerator used by M15 file
evidence. Add differential tests proving in-memory bytes and SHA-256 values are
identical to the existing file output. `ExecuteRlV2LiveCandidate` rechecks the
token, row, family, and current native legality before executing.

- [ ] **Step 4: Generate 0003 and run source tests**

The patch must have deterministic author/date metadata and zero whitespace
errors. Add only 0003 to `live/series` at this point.

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_live_boundary_source \
  tests.project.v2.test_v2_m15_action_evidence \
  tests.project.v2.test_v2_m15_observation_evidence -v
```

- [ ] **Step 5: Commit**

```bash
git add integration/openttd/patches/15.3/m23/live \
  tests/project/v2/test_v2_m23_live_boundary_source.py
git commit -m "m23: expose live M15 action boundaries"
```

### Task 5: Implement the persistent passenger-bus transaction

**Files:**

- Create: `integration/openttd/patches/15.3/m23/live/0004-Add-road-passenger-transaction-executor.patch`
- Create: `tests/project/v2/test_v2_m23_bus_executor_source.py`
- Modify: `integration/openttd/patches/15.3/m23/live/series`

- [ ] **Step 1: Write failing state-machine and forbidden-path tests**

Require phases `SELECT_PAIR`, `FUND`, `PLAN_PATH`, `BUILD_PATH`,
`BUILD_STOPS`, `BUILD_DEPOT`, `BUY_BUS`, `SET_ORDERS`, `START_SERVICE`,
`OBSERVE_SERVICE`, `COMPLETE`, and `RECOVERABLE_FAILURE`.

Test that each phase exposes only relevant existing M15 families, always keeps
`WAIT` legal, and filters candidates by stable key/native IDs rather than array
position. Test predictable rejection, stale token, insufficient cash, blocked
road segment, unavailable engine, order rollback, lost vehicle, and no route
found. Forbid `RunPassengerService`, `RunM16*`, direct calls to qualification
runners, direct field writes to company money, and teacher execution.

- [ ] **Step 2: Confirm failure**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_bus_executor_source -v
```

- [ ] **Step 3: Add planner and transaction types in 0004**

The patch adds `src/rl_v2_bus_planner.cpp/.h` and updates
`rl_v2_program_executor.cpp/.h` plus CMake. The planner enumerates distinct town
pairs, legal stop sites, buildable path alternatives, and depot sites. It may
rank and filter legal candidates, but it never issues a command.

Use this boundary:

```cpp
struct RlV2ExecutorSelection {
    std::uint8_t program;
    std::uint8_t family;
    std::uint16_t candidate_row;
    std::string snapshot_token;
};

RlV2LiveMaskFilter RlV2ProgramExecutor::PrepareBoundary(std::uint8_t program);
RlV2ExecutorResult RlV2ProgramExecutor::ExecuteBoundary(
    const RlV2ExecutorSelection &selection);
```

The executor captures selected town/station/depot/vehicle IDs, path progress,
milestones, receipts, and the expected next phase. No command is silently
retried. A recoverable failure produces a new boundary and mask; an invariant
failure throws and faults the controller.

- [ ] **Step 4: Add mutation and deterministic planner tests to the patch**

Add an OpenTTD CTest covering a flat 64x64 fixed seed, two path alternatives,
stable tie-breaking, every phase transition, one injected road rejection, route
rollback, and exact repeated receipts. The test stops before claiming neural
control.

- [ ] **Step 5: Test and commit**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_bus_executor_source \
  tests.project.v2.test_v2_m23_visible_source -v
git add integration/openttd/patches/15.3/m23/live \
  tests/project/v2/test_v2_m23_bus_executor_source.py
git commit -m "m23: add passenger bus transaction executor"
```

### Task 6: Add the isolated `ORL2` OpenTTD worker

**Files:**

- Create: `integration/openttd/patches/15.3/m23/live/0005-Add-ORL2-live-training-bridge.patch`
- Create: `tests/project/v2/test_v2_m23_live_bridge_source.py`
- Modify: `integration/openttd/patches/15.3/m23/live/series`

- [ ] **Step 1: Write failing lifecycle and isolation tests**

Preserve the V1 `-B read_fd:write_fd` and M23 `-B /absolute/config.json`
routes. Add only `-B v2:read_fd:write_fd` for the new worker. Test exact
lifecycle `READY -> RESETTING -> AT_BOUNDARY -> EXECUTING -> ADVANCING ->
AT_BOUNDARY -> CLOSED|FAILED` and request ordering.

Test one world per process, single company, no opponent, no network socket,
descriptor inheritance only, 8 MiB cap, timeouts, broken pipe, stale request,
stale snapshot, invalid family/row, all-illegal filter, and close-after-failure.

- [ ] **Step 2: Confirm failure**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_live_bridge_source -v
```

- [ ] **Step 3: Implement bridge dispatch and messages**

Add `src/rl_v2_live_bridge.cpp/.h` and an `openttd.cpp` dispatch that recognizes
the exact `v2:<read>:<write>` prefix. `RESET` creates the contract-pinned normal
64x64 world and company. `BOUNDARY` returns metadata plus exact M15 observation
and candidate bytes. `STEP` accepts program/family/row/token, executes one
transaction boundary, advances the declared tick interval, computes public
native deltas, and returns the next boundary.

Teacher labels are returned only for an explicit contract-pinned
`training_teacher=true` reset and in a distinct metadata field. The normal
boundary never contains a teacher label.

- [ ] **Step 4: Add native pipe integration tests**

Exercise reset, four real actions, wait/advance, stale token, injected command
failure, clean close, and two identical-process traces. Verify no AI company is
created and no network file descriptor appears.

- [ ] **Step 5: Test and commit**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_live_bridge_source \
  tests.project.traceability.test_v1_m03_bridge_protocol \
  tests.project.v2.test_v2_m23_ingame_source -v
git add integration/openttd/patches/15.3/m23/live \
  tests/project/v2/test_v2_m23_live_bridge_source.py
git commit -m "m23: add isolated live training bridge"
```

### Task 7: Persist game, executor, and controller state

**Files:**

- Create: `integration/openttd/patches/15.3/m23/live/0006-Persist-live-controller-state.patch`
- Create: `tests/project/v2/test_v2_m23_live_persistence_source.py`
- Modify: `integration/openttd/patches/15.3/m23/live/series`

- [ ] **Step 1: Write failing save/load tests**

Require a versioned `RLV2` native save chunk for in-game executor/controller
state and a training-side checkpoint payload for external hidden/optimizer
state. Test every executor phase, selected native IDs, path progress,
milestones, command ordinal, boundary ordinal, recurrent reset, hidden state,
next tick, and contract identity.

Mutate chunk version, contract hash, program, phase, IDs, truncated path,
nonfinite hidden value, future command ordinal, and unknown field. All must fail
before a command is issued.

- [ ] **Step 2: Confirm failure**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_live_persistence_source -v
```

- [ ] **Step 3: Implement additive save/load hooks**

Add `src/saveload/rl_v2_sl.cpp/.h` and register an optional chunk that is absent
from ordinary games. Export/import a plain controller-state DTO; do not
serialize pointers. On load, validate company ownership and native object IDs
after pools exist, rebuild transient caches, and compare the next legal mask.

The bridge `SAVE` response returns the native save hash and semantic state hash.
`LOAD` requires both plus the host checkpoint identity. A mismatched host state
is rejected rather than reset silently.

- [ ] **Step 4: Add twin-branch continuation CTests**

Save at each transaction phase, execute one legal action on branch A, reload in
a fresh process for branch B, and require identical next boundary bytes,
selected action, command receipt, public semantic hash, and reward.

- [ ] **Step 5: Test and commit**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_live_persistence_source \
  tests.project.v2.test_v2_m15_cross_scale_replay_evidence -v
git add integration/openttd/patches/15.3/m23/live \
  tests/project/v2/test_v2_m23_live_persistence_source.py
git commit -m "m23: persist live bus controller state"
```

### Task 8: Build and retain the deterministic native executor gate

**Files:**

- Create: `scripts/v2/prepare_m23_live_source.py`
- Create: `scripts/v2/run_m23_bus_executor_gate.py`
- Create: `scripts/v2/validate_m23_bus_executor_evidence.py`
- Create: `docs/project/schema/v2-m23-bus-executor-evidence.schema.json`
- Create: `tests/project/v2/test_v2_m23_bus_executor_gate.py`
- Create after a real passing run: `config/v2/m23-bus-executor-evidence.json`
- Modify: `scripts/v2/verify_driver.py`
- Modify: `tests/project/v2/test_v2_verify_driver.py`

- [ ] **Step 1: Write source preparation and evidence tests**

Require the exact parent tree, the four-patch 0003-0006 inventory available at
this gate, result tree, executable hash, 98 upstream CTests, new live CTests,
dependency closure, ten deterministic seeds, all transaction phases, exact
repeat traces, injected failure recovery, save/load branches, no opponent, and
all success objects/outcomes.

- [ ] **Step 2: Confirm failure**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_bus_executor_gate -v
```

- [ ] **Step 3: Implement fail-closed preparation and runner**

`prepare_m23_live_source.py` copies an explicit exact post-0002 source into a
new path, applies 0003-0006 in order, verifies the resulting Git tree, and never
edits its input. `run_m23_bus_executor_gate.py` builds a fresh strict headless
target and runs deterministic teacher-labelled actions solely to prove the
executor.

Do not commit evidence until the real executable produces it. The validator
must rebuild semantic summaries from receipts rather than trust `status`.

- [ ] **Step 4: Run the real gate**

```bash
python3 scripts/v2/run_m23_bus_executor_gate.py \
  --source /absolute/post-0002-openttd-source \
  --work-root /absolute/new/m23-bus-executor-work \
  --output /absolute/new/m23-bus-executor-evidence.json
python3 scripts/v2/validate_m23_bus_executor_evidence.py \
  --evidence /absolute/new/m23-bus-executor-evidence.json --live
```

Expected: every normal command and recovery predicate passes. If the exact
source or build dependencies are absent, report the missing preflight inputs;
do not create placeholder evidence.

- [ ] **Step 5: Integrate full-tier validation and commit**

The full tier requires the retained executor artifact set; fast/contract tests
exercise only synthetic mutation fixtures.

```bash
git add scripts/v2/prepare_m23_live_source.py scripts/v2/run_m23_bus_executor_gate.py \
  scripts/v2/validate_m23_bus_executor_evidence.py \
  docs/project/schema/v2-m23-bus-executor-evidence.schema.json \
  tests/project/v2/test_v2_m23_bus_executor_gate.py \
  scripts/v2/verify_driver.py tests/project/v2/test_v2_verify_driver.py
# Add config/v2/m23-bus-executor-evidence.json here only after the real live
# output above passes independent validation.
git commit -m "m23: qualify the native passenger bus executor"
```

## Stop gate B

Do not start neural work until a real OpenTTD executable has issued all required
bus commands, transported passengers, earned income, recovered from the injected
failure, and passed exact save/load continuation. A missing build dependency is
a blocker for this gate, not permission to mock the result.

---

### Task 9: Implement the C++ live environment client and supervisor

**Files:**

- Create: `training/v2/include/openttd_rl/v2/m23_live_environment.h`
- Create: `training/v2/src/m23_live_environment.cpp`
- Create: `training/v2/tests/m23_live_environment_gate.cpp`
- Modify: `training/v2/live/CMakeLists.txt`

- [ ] **Step 1: Write failing fake-worker tests**

Test POSIX spawn with four unique descriptor pairs and work directories,
process-group teardown, timeout, crash, malformed frame, out-of-order request,
oversized tensors, hash mismatch, restart only at episode boundary, and no
replacement of a scored evaluation case.

- [ ] **Step 2: Implement the typed boundary decoder**

Decode the frozen M15 observation sections directly into CPU tensors and the
candidate payload into features, parameters, masks, and family IDs. Verify
lengths and SHA-256 before constructing `GeneralistPolicyInput`.

```cpp
struct M23LiveStep {
    GeneralistPolicyInput input;
    M23NativeDeltas deltas;
    M23ExecutorInspection executor;
    std::string snapshot_token;
    bool terminated;
    bool truncated;
};

class M23LiveEnvironment {
public:
    M23LiveStep reset(const M23Scenario &scenario, bool teacher_allowed);
    M23LiveStep step(const M23HierarchicalAction &action);
    M23SavedBoundary save();
    M23LiveStep load(const M23SavedBoundary &saved);
};
```

- [ ] **Step 3: Run fake-worker and one-real-worker tests**

```bash
cmake --build build/v2-live-cpu --target m23_live_environment_gate
ctest --test-dir build/v2-live-cpu -R v2_m23_live_environment --output-on-failure
```

- [ ] **Step 4: Commit**

```bash
git add training/v2/include/openttd_rl/v2/m23_live_environment.h \
  training/v2/src/m23_live_environment.cpp \
  training/v2/tests/m23_live_environment_gate.cpp training/v2/live/CMakeLists.txt
git commit -m "m23: add supervised live environment client"
```

### Task 10: Expose full hierarchical outputs without changing M22 behavior

**Files:**

- Modify: `training/v2/include/openttd_rl/v2/generalist_policy.h`
- Modify: `training/v2/src/generalist_policy.cpp`
- Create: `training/v2/tests/m23_full_policy_gate.cpp`
- Modify: `training/v2/live/CMakeLists.txt`

- [ ] **Step 1: Write exact backward-compatibility tests**

Load the accepted M22 checkpoint and require old `forward()` program logits,
program value, and next hidden to remain bit-exact on CPU. Require parameter
names/count (`1,457,520`) and checkpoint load semantics to remain unchanged.

Add gradient tests proving family and selected-candidate heads receive finite
nonzero gradients through the new method.

- [ ] **Step 2: Add an additive output type**

```cpp
struct FullGamePolicyOutput {
    torch::Tensor program_logits;
    torch::Tensor family_logits;
    torch::Tensor candidate_logits;
    torch::Tensor value;
    torch::Tensor next_hidden;
};

FullGamePolicyOutput GeneralistPolicyImpl::forward_full(
    const GeneralistPolicyInput &input);
```

Refactor a private `forward_impl` to compute the base output once. `forward()`
returns exactly its current three tensors. `forward_full()` returns planner
program/value plus base family/candidate logits and the same next hidden. Add no
parameters or buffers.

- [ ] **Step 3: Test and commit**

```bash
cmake --build build/v2-live-cpu --target m23_full_policy_gate
ctest --test-dir build/v2-live-cpu -R v2_m23_full_policy --output-on-failure
git add training/v2/include/openttd_rl/v2/generalist_policy.h \
  training/v2/src/generalist_policy.cpp training/v2/tests/m23_full_policy_gate.cpp \
  training/v2/live/CMakeLists.txt
git commit -m "m23: expose full generalist action outputs"
```

### Task 11: Implement joint hierarchical action sampling and PPO math

**Files:**

- Create: `training/v2/include/openttd_rl/v2/m23_hierarchical_ppo.h`
- Create: `training/v2/src/m23_hierarchical_ppo.cpp`
- Create: `training/v2/tests/m23_hierarchical_ppo_gate.cpp`
- Modify: `training/v2/live/CMakeLists.txt`

- [ ] **Step 1: Write analytical tests first**

Cover deterministic logits where the expected program/family/candidate and
joint log probability can be calculated by hand. Test stochastic sampling with
a fixed generator, greedy selection, conditional candidate masking by selected
family, entropy, all-illegal program/family/candidate rows, invalid family IDs,
nonfinite values, PPO clipping, GAE termination versus truncation, and gradient
flow to all three heads.

- [ ] **Step 2: Implement conditional policy composition**

```cpp
joint_log_probability =
    program_log_probability[selected_program] +
    family_log_probability[selected_family] +
    candidate_log_probability[selected_candidate];
```

The candidate legal mask is
`native_candidate_mask && candidate_family == selected_family &&
executor_phase_filter`. Never sample family and candidate independently from
incompatible masks. Reuse `m22_compute_gae` and `m22_ppo_loss`; do not duplicate
their numerics.

- [ ] **Step 3: Test and commit**

```bash
cmake --build build/v2-live-cpu --target m23_hierarchical_ppo_gate
ctest --test-dir build/v2-live-cpu -R v2_m23_hierarchical_ppo --output-on-failure
git add training/v2/include/openttd_rl/v2/m23_hierarchical_ppo.h \
  training/v2/src/m23_hierarchical_ppo.cpp \
  training/v2/tests/m23_hierarchical_ppo_gate.cpp training/v2/live/CMakeLists.txt
git commit -m "m23: add hierarchical PPO action math"
```

### Task 12: Implement the audited reward ledger

**Files:**

- Create: `training/v2/include/openttd_rl/v2/m23_bus_reward.h`
- Create: `training/v2/src/m23_bus_reward.cpp`
- Create: `training/v2/tests/m23_bus_reward_gate.cpp`
- Modify: `training/v2/live/CMakeLists.txt`

- [ ] **Step 1: Write reward and exploit tests**

Test every exact contract coefficient, milestone paid once, reversal debit,
pre-delivery cap, delivery/profit clipping, waiting before revenue, excessive
idle after useful actions exist, foreseeable/unforeseeable rejection,
bankruptcy, save/load ledger equality, and finite bounds.

Add adversarial traces for build/remove loops, buy/sell loops, loan cycling,
order rewrite loops, repeatedly reporting the same delivery, and integer
overflow. None may produce positive net shaping.

- [ ] **Step 2: Implement a pure ledger**

```cpp
struct M23RewardResult {
    double total;
    std::map<std::string, double> components;
    M23RewardLedger next;
};

M23RewardResult m23_bus_reward(
    const M23RewardLedger &prior,
    const M23LiveStep &before,
    const M23LiveStep &after,
    const M23LiveActionResult &action);
```

Only native deltas and durable object predicates enter the function. Teacher
labels, logits, action probabilities, and opponent data are not inputs.

- [ ] **Step 3: Test and commit**

```bash
cmake --build build/v2-live-cpu --target m23_bus_reward_gate
ctest --test-dir build/v2-live-cpu -R v2_m23_bus_reward --output-on-failure
git add training/v2/include/openttd_rl/v2/m23_bus_reward.h \
  training/v2/src/m23_bus_reward.cpp training/v2/tests/m23_bus_reward_gate.cpp \
  training/v2/live/CMakeLists.txt
git commit -m "m23: add audited passenger bus rewards"
```

### Task 13: Generate demonstrations and behavior-clone the new heads

**Files:**

- Create: `scripts/v2/build_m23_bus_demonstrations.py`
- Create: `docs/project/schema/v2-m23-bus-demonstration-manifest.schema.json`
- Create: `training/v2/include/openttd_rl/v2/m23_bus_imitation.h`
- Create: `training/v2/src/m23_bus_imitation.cpp`
- Create: `training/v2/tests/m23_bus_imitation_gate.cpp`
- Create: `tests/project/v2/test_v2_m23_bus_demonstrations.py`
- Create after real generation: `config/v2/m23-bus-demonstration-manifest.json`
- Modify: `training/v2/live/CMakeLists.txt`

- [ ] **Step 1: Write provenance and leakage tests**

Require exact executable/contract/seed identities, observation/candidate hashes,
legal teacher program/family/row, command receipts, and no final seeds. Mutate
one label, mask, hash, command, seed split, or teacher permission and require
rejection.

Assert evaluation reset requests cannot set `teacher_allowed`, normal boundary
frames contain no teacher field, and the trainer cannot substitute a label after
the behavior-cloning stage.

- [ ] **Step 2: Build real demonstrations**

Drive all training seeds through the planner-label mode. Store content-addressed
compressed transition bundles outside Git and commit only a canonical manifest
after validation. Replaying a manifest must reproduce every legal label and
receipt.

- [ ] **Step 3: Implement the imitation loss**

Use the sum of masked program, family, and conditional candidate cross-entropy.
Train the full model with a lower learning rate on shared layers and the normal
rate on family/candidate heads. Stop warm-up when a disjoint demonstration
development set reaches 95 percent exact joint-action accuracy; a step count
alone cannot pass.

- [ ] **Step 4: Test one learning step and overfit a tiny fixture**

Require finite gradients, lower loss after the update, changed family/candidate
parameters, unchanged illegal probabilities, and 100 percent accuracy on an
eight-transition synthetic fixture.

- [ ] **Step 5: Commit**

```bash
git add scripts/v2/build_m23_bus_demonstrations.py \
  docs/project/schema/v2-m23-bus-demonstration-manifest.schema.json \
  training/v2/include/openttd_rl/v2/m23_bus_imitation.h \
  training/v2/src/m23_bus_imitation.cpp training/v2/tests/m23_bus_imitation_gate.cpp \
  tests/project/v2/test_v2_m23_bus_demonstrations.py training/v2/live/CMakeLists.txt
# Add config/v2/m23-bus-demonstration-manifest.json only after real generation
# and replay validation.
git commit -m "m23: add bus demonstration warm start"
```

### Task 14: Build the live trainer and exact checkpoint recovery

**Files:**

- Create: `training/v2/include/openttd_rl/v2/m23_bus_trainer.h`
- Create: `training/v2/src/m23_bus_trainer.cpp`
- Create: `training/v2/src/m23_bus_trainer_main.cpp`
- Create: `training/v2/tests/m23_bus_trainer_gate.cpp`
- Create: `scripts/v2/run_m23_bus_training.py`
- Create: `docs/project/schema/v2-m23-bus-training-report.schema.json`
- Modify: `training/v2/live/CMakeLists.txt`

- [ ] **Step 1: Write trainer-state and recovery tests**

Test four environments, 32 boundaries per environment per rollout, complete
minibatches, deterministic environment shuffling, recurrent reset/carry,
termination/truncation GAE, reward components, joint actions, finite checks,
gradient clipping, rehearsal quota, atomic checkpoint, never-overwrite, and
exact fresh-process recovery.

The checkpoint inventory is:

```text
COMMITTED
manifest.json
model.pt
optimizer.pt
normalization.pt
runtime.bin
curriculum.json
environment-state.json
```

- [ ] **Step 2: Implement training without automatic promotion**

The trainer may write candidate checkpoints at complete updates. It must not
mark one accepted. Store model/optimizer, all RNG streams, recurrent states,
per-worker scenario/episode cursors, reward ledgers, completed update, rollout
cursor, BC state, retention history, and every contract identity.

Use three parameter groups: new action heads, planner heads, and shared encoder.
The shared encoder starts at one tenth of the action-head learning rate. Default
to CPU on this machine until an explicitly supplied `local-sm75` build passes.

- [ ] **Step 3: Prove exact recovery on fake and live environments**

Run eight updates continuously and as four updates + fresh-process resume + four
updates. Compare actions, logits, log probabilities, values, rewards, gradients,
optimizer tensors, parameters, RNGs, hidden states, receipts, and checkpoint ID.

- [ ] **Step 4: Test and commit**

```bash
cmake --build build/v2-live-cpu --target m23_bus_trainer_gate m23_bus_trainer
ctest --test-dir build/v2-live-cpu -R v2_m23_bus_trainer --output-on-failure
git add training/v2/include/openttd_rl/v2/m23_bus_trainer.h \
  training/v2/src/m23_bus_trainer.cpp training/v2/src/m23_bus_trainer_main.cpp \
  training/v2/tests/m23_bus_trainer_gate.cpp scripts/v2/run_m23_bus_training.py \
  docs/project/schema/v2-m23-bus-training-report.schema.json \
  training/v2/live/CMakeLists.txt
git commit -m "m23: add recoverable live bus trainer"
```

### Task 15: Require a real CPU neural-learning smoke

**Files:**

- Create: `scripts/v2/run_m23_bus_learning_smoke.py`
- Create: `scripts/v2/validate_m23_bus_learning_smoke.py`
- Create: `docs/project/schema/v2-m23-bus-learning-smoke.schema.json`
- Create: `tests/project/v2/test_v2_m23_bus_learning_smoke.py`
- Create after a real passing run: `config/v2/m23-bus-learning-smoke.json`

- [ ] **Step 1: Write evidence mutation tests**

Require real executable and checkpoint hashes, at least four workers, BC loss
decrease, at least two PPO updates, finite tensors, changed family/candidate
parameters, nonzero normal command count, at least four distinct action
families, teacher disabled during PPO, no opponent, and exact recovery smoke.

- [ ] **Step 2: Run the real CPU smoke**

```bash
python3 scripts/v2/run_m23_bus_learning_smoke.py \
  --trainer /absolute/build/v2-live-cpu/m23_bus_trainer \
  --openttd /absolute/build/m23-live/openttd \
  --device cpu --workers 4 --updates 2 \
  --output-root /absolute/new/m23-bus-learning-smoke
```

Expected: the actual neural parameters change and the policy controls every PPO
action. Profit is not yet a smoke-test requirement.

- [ ] **Step 3: Independently validate and commit code**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_bus_learning_smoke -v
git add scripts/v2/run_m23_bus_learning_smoke.py \
  scripts/v2/validate_m23_bus_learning_smoke.py \
  docs/project/schema/v2-m23-bus-learning-smoke.schema.json \
  tests/project/v2/test_v2_m23_bus_learning_smoke.py
# Add config/v2/m23-bus-learning-smoke.json only after the real run passes.
git commit -m "m23: require real neural bus learning smoke"
```

### Task 16: Qualify only the hardware that is actually available

**Files:**

- Create: `scripts/v2/run_m23_live_device_qualification.py`
- Create: `scripts/v2/validate_m23_live_device_qualification.py`
- Create: `tests/project/v2/test_v2_m23_live_device_qualification.py`

- [ ] **Step 1: Write CPU, local-sm75, and production-sm120 tests**

CPU qualification is mandatory on the current PC. `local-sm75` runs only with
explicit compatible project-local dependency roots; otherwise it records
`NOT_RUN_DEPENDENCY_UNAVAILABLE` and CPU remains the accepted development path.
It must never silently build for another architecture.

The separate PC runs `production-sm120` later. Results from the two hosts are
separate records and cannot overwrite one another.

- [ ] **Step 2: Compare CPU/CUDA when local CUDA is genuinely available**

Use batches 1 and 4. Compare forward outputs, greedy joint actions, loss,
gradients, update, checkpoint reload, and a fixed live rollout. Reuse frozen M22
tolerances unless a stricter versioned Phase 1 tolerance is declared before the
run.

- [ ] **Step 3: Run the current host without installing anything**

```bash
python3 scripts/v2/run_m23_live_device_qualification.py \
  --profile cpu --build /absolute/build/v2-live-cpu \
  --output /absolute/new/m23-live-device-cpu.json
```

Optionally, only if explicit roots already exist:

```bash
python3 scripts/v2/run_m23_live_device_qualification.py \
  --profile local-sm75 --torch-dir /absolute/project-local/Torch \
  --cuda-root /absolute/project-local/cuda \
  --output /absolute/new/m23-live-device-sm75.json
```

- [ ] **Step 4: Test and commit**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_live_device_qualification -v
git add scripts/v2/run_m23_live_device_qualification.py \
  scripts/v2/validate_m23_live_device_qualification.py \
  tests/project/v2/test_v2_m23_live_device_qualification.py
git commit -m "m23: qualify available live-training devices"
```

### Task 17: Train, select, and independently promote the Phase 1 policy

**Files:**

- Create: `scripts/v2/run_m23_bus_evaluation.py`
- Create: `scripts/v2/validate_m23_bus_training_evidence.py`
- Create: `scripts/v2/validate_m23_bus_evaluation_evidence.py`
- Create: `docs/project/schema/v2-m23-bus-training-evidence.schema.json`
- Create: `docs/project/schema/v2-m23-bus-evaluation-evidence.schema.json`
- Create: `tests/project/v2/test_v2_m23_bus_evaluation.py`
- Create after real passing runs: `config/v2/m23-bus-training-evidence.json`
- Create after real passing runs: `config/v2/m23-bus-evaluation-evidence.json`
- Modify: `scripts/v2/verify_driver.py`
- Modify: `tests/project/v2/test_v2_verify_driver.py`

- [ ] **Step 1: Write selection and leakage tests**

Require three declared initialization streams and matched transition budgets.
Development bank A selects among eligible candidates. Freeze the selected
checkpoint before reading bank B. Bank B is one-shot qualification. Each bank
has 20 unique cases and requires at least 18 successes.

Mutate bank order, omit a failure, retry a case, replace a seed, access B before
selection, train on either bank, enable teacher, use an opponent, change a
checkpoint after selection, or compute profit from a non-native source. Each
must be rejected.

- [ ] **Step 2: Run training to evidence, not to a time deadline**

Train on CPU with four workers initially. Stop only for an explicit operator
budget, numerical failure, or eligible candidate; elapsed hours do not imply
promotion. Retain learning curves and every failed candidate.

- [ ] **Step 3: Evaluate bank A, freeze selection, then run bank B**

Each case launches a fresh optimizer-free process and uses greedy masked joint
actions. Success requires all native objects/outcomes listed in the target
contract, positive operating income, no bankruptcy, and exact save/load
continuation in the designated cases.

Report per-case result, mean/median/range, 95-percent interval, command failure
counts, profit, deliveries, steps, wall time, and comparison with wait-only,
seeded-random-legal, and deterministic planner baselines.

- [ ] **Step 4: Add validators to the full tier only after real evidence exists**

The contract tier validates committed record structure and identities offline;
the full tier rehashes live checkpoints, saves, logs, and executable artifacts.

- [ ] **Step 5: Run mutation tests and commit**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_bus_evaluation \
  tests.project.v2.test_v2_verify_driver -v
git add scripts/v2/run_m23_bus_evaluation.py \
  scripts/v2/validate_m23_bus_training_evidence.py \
  scripts/v2/validate_m23_bus_evaluation_evidence.py \
  docs/project/schema/v2-m23-bus-training-evidence.schema.json \
  docs/project/schema/v2-m23-bus-evaluation-evidence.schema.json \
  tests/project/v2/test_v2_m23_bus_evaluation.py \
  scripts/v2/verify_driver.py tests/project/v2/test_v2_verify_driver.py
# Add both config/v2/m23-bus-*-evidence.json files only after the one-shot runs
# pass their independent validators.
git commit -m "m23: promote the first live neural bus policy"
```

## Stop gate C

Stop if either 20-case bank fails, any earlier frozen test regresses, or the
policy depends on teacher output. Diagnose and resume from the last immutable
candidate; do not weaken the contract or reuse bank B for training.

---

### Task 18: Export and validate an additive full-policy ONNX package

**Files:**

- Create: `scripts/v2/export_m23_live_policy.py`
- Create: `scripts/v2/build_m23_live_package.py`
- Create: `scripts/v2/validate_m23_live_package.py`
- Create: `config/v2/m23-live-package-contract.json`
- Create: `docs/project/schema/v2-m23-live-package-contract.schema.json`
- Create: `training/v2/include/openttd_rl/v2/m23_live_onnx.h`
- Create: `training/v2/src/m23_live_onnx.cpp`
- Create: `training/v2/tests/m23_live_deployment_gate.cpp`
- Create: `tests/project/v2/test_v2_m23_live_package.py`
- Modify: `training/v2/live/CMakeLists.txt`

- [ ] **Step 1: Freeze failing signature and package tests**

The full graph has the existing 25 M15 inputs plus `domain_tokens`,
`domain_token_kind`, `domain_token_mask`, `program_features`, and
`program_mask`: exactly 30 inputs. Outputs are `program_logits`,
`family_logits`, `candidate_logits`, `value`, and `next_hidden`: exactly five.
Batch is dynamic; all capacity axes are fixed.

Require the package to be a new format and ID. Assert both frozen compact
package IDs and all their files remain byte-identical.

- [ ] **Step 2: Implement deterministic two-pass export**

Strictly load the selected full checkpoint, export opset 18 twice, canonicalize
metadata, and reject byte differences. Load all parameters exactly once and
reject missing, extra, duplicate, wrong-shape, wrong-dtype, or nonfinite tensors.

- [ ] **Step 3: Implement the full ONNX Runtime adapter**

Validate all 30 names, dtypes, ranks, capacities, and masks before `Run()`. Apply
the selected-family conditional mask outside the graph with the same helper as
native evaluation. Reject nonfinite outputs and any illegal greedy joint action.

- [ ] **Step 4: Run native/ONNX parity**

Use real Phase 1 boundaries with recurrent reset/carry, batches 1 and 4,
success/failure states, and save/load continuation. Require identical stable
greedy program/family/candidate choices and errors within the versioned
tolerances.

- [ ] **Step 5: Test and commit**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_live_package \
  tests.project.v2.test_v2_m23_packages -v
cmake --build build/v2-live-cpu --target m23_live_deployment_gate
ctest --test-dir build/v2-live-cpu -R v2_m23_live_deployment --output-on-failure
git add scripts/v2/export_m23_live_policy.py scripts/v2/build_m23_live_package.py \
  scripts/v2/validate_m23_live_package.py \
  config/v2/m23-live-package-contract.json \
  docs/project/schema/v2-m23-live-package-contract.schema.json \
  training/v2/include/openttd_rl/v2/m23_live_onnx.h \
  training/v2/src/m23_live_onnx.cpp training/v2/tests/m23_live_deployment_gate.cpp \
  tests/project/v2/test_v2_m23_live_package.py training/v2/live/CMakeLists.txt
git commit -m "m23: package the full neural action policy"
```

### Task 19: Run the full policy in a visible normal game

**Files:**

- Create: `integration/openttd/patches/15.3/m23/live/0007-Run-full-policy-bus-actions-in-visible-games.patch`
- Create: `scripts/v2/run_m23_bus_visible_gate.py`
- Create: `scripts/v2/validate_m23_bus_visible_evidence.py`
- Create: `docs/project/schema/v2-m23-bus-visible-evidence.schema.json`
- Create: `tests/project/v2/test_v2_m23_bus_visible_runtime.py`
- Create after a real passing run: `config/v2/m23-bus-visible-evidence.json`
- Modify: `integration/openttd/patches/15.3/m23/live/series`

- [ ] **Step 1: Write failing visible-runtime tests**

Require a normal GUI game, one neural company, no opponent, full package
validation before control, exact M15 live tensors, greedy program/family/
candidate output, real executor receipts, recurrent carry, controller controls,
wait-only fault state, native save, load continuation, screenshot, bounded log,
and atomic report.

Forbid teacher labels, deterministic action substitution, qualification
runners, compact-package action claims, direct state mutation, retries, and
headless evidence masquerading as visible evidence.

- [ ] **Step 2: Add 0007 after persistence**

Update the M23 controller to use `M23LiveOnnxModel`, build a filtered live
boundary, select a legal joint action, and pass it to the transaction executor.
Keep compact `operation=equivalence` and the discovery foundation available for
their frozen tests; the new operation/config schema is versioned.

- [ ] **Step 3: Run one retained visible campaign**

Use an offscreen SDL driver for automation but a normal GUI build and viewport.
Retain configuration, log, report, save, screenshot, dependency closure, process
telemetry, and package/executable identities. Load the save in a fresh process
and require the same next policy output and executor state.

- [ ] **Step 4: Validate native outcomes independently**

The validator parses report/log, hashes save/screenshot, and checks owned road,
two stops, depot, moving passenger bus, two orders, positive delivery, positive
operating income, nonzero normal commands, and zero teacher/opponent use.

- [ ] **Step 5: Test and commit**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest \
  tests.project.v2.test_v2_m23_bus_visible_runtime \
  tests.project.v2.test_v2_m23_visible_source \
  tests.project.v2.test_v2_m23_ingame_source -v
git add integration/openttd/patches/15.3/m23/live \
  scripts/v2/run_m23_bus_visible_gate.py \
  scripts/v2/validate_m23_bus_visible_evidence.py \
  docs/project/schema/v2-m23-bus-visible-evidence.schema.json \
  tests/project/v2/test_v2_m23_bus_visible_runtime.py
# Add config/v2/m23-bus-visible-evidence.json only after the real visible run
# and fresh-process load continuation pass.
git commit -m "m23: play a visible neural passenger bus service"
```

### Task 20: Integrate verification and document the Phase 1 boundary

**Files:**

- Create: `docs/project/M23_LIVE_BUS_PHASE1.md`
- Modify: `README.md`
- Modify: `scripts/v2/verify_driver.py`
- Modify: `tests/project/v2/test_v2_verify_driver.py`

The accepted `docs/project/requirements-v2.json` remains unchanged. Phase 1 is
reported as development progress, not retrofitted into a historical gate row.

- [ ] **Step 1: Write documentation and inventory tests first**

Require one copy-paste CPU workflow, an optional explicit `local-sm75` workflow,
the separate `production-sm120` command for the other PC, artifact locations,
resume, evaluation, export, visible playback, troubleshooting, and exact claims.

README must say Phase 1 is a development milestone, not G23, V2 release, full
vanilla breadth, or competitive competence.

- [ ] **Step 2: Add each new command to exactly one verification tier**

- fast: pure unit/mutation/source-scope tests;
- contract: committed contract/manifests and offline evidence validation;
- full: live source application/build, executor, training artifacts, selected
  checkpoint, full ONNX parity, visible playback, complete V2, and unchanged V1.

Update inventory count tests before the driver. Full preflight names every live
artifact instead of skipping it.

- [ ] **Step 3: Run focused and fast verification**

```bash
PYTHONPATH=scripts/v2 python3 -m unittest discover \
  -s tests/project/v2 -p 'test_v2_m23_*bus*.py' -v
scripts/v2/verify.sh --tier fast
git diff --check
```

- [ ] **Step 4: Run full verification on a host with retained artifacts**

```bash
scripts/v2/verify.sh --tier full \
  --artifact-root /absolute/openttd-rl-artifacts
```

Expected: all V2 and unchanged V1 checks pass. The current M23 release rows
remain `PLANNED`; Phase 1 does not satisfy the frozen eight-campaign release
contract.

- [ ] **Step 5: Final review and commit**

Inspect every claimed evidence path and rerun validators from a clean process.
Then:

```bash
git status --short
git diff --check
git add docs/project/M23_LIVE_BUS_PHASE1.md README.md \
  scripts/v2/verify_driver.py tests/project/v2/test_v2_verify_driver.py
git commit -m "docs: record the live neural bus phase"
```

## Stop gate D and handoff

Phase 1 is complete only when all of the following are simultaneously true:

- the deterministic native executor gate passes;
- behavior cloning and PPO changed the real generalist policy;
- teacher output is absent from PPO, evaluation, export, and playback;
- both disjoint 20-case development banks pass at least 18 cases;
- the selected checkpoint has positive median operating profit;
- CPU qualification and exact recovery pass on the current PC;
- the additive full ONNX package matches native actions;
- a visible normal game proves real neural bus actions, delivery, income, save,
  load, and screenshot;
- all earlier V2 and V1 gates remain valid;
- no G23, release, opponent, or full-game claim is made.

After this stop gate, review real failures, throughput, action distribution,
reward behavior, and model capacity. Only then write the separate Phase 2 bus
operations plan.
