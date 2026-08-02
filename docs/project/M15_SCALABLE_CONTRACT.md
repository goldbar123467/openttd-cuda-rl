# M15 scalable environment contract

## Status

- Contract status: `FROZEN` and mutation-tested on 2026-08-02
- Native reset, bounded observation, complete hierarchical lifecycle/rollback, all-scale exact replay, scalable native policy, and cross-scale passenger competence: `PASS`
- G15 status: `PASS`

[`config/v2/m15-scalable-contract.json`](../../config/v2/m15-scalable-contract.json)
is the implementation target for the first V2 gameplay milestone. It binds the
G14 identities and the exact V1 scenario, bridge, observation, action and
architecture contract digests.

## Map and scenario boundary

The contract lists all 49 native 64–4096 dimension pairs in deterministic
width-major order and retains the separate 32×32 V1 adapter. The useful-play
curriculum is 64, 128, 256 and 512 square maps. Generalization covers 64×256,
128×512, 256×1024, 512×128 and 1024×1024. The 2048 and 4096 squares are resource
boundaries: they require a bounded reset/observation/save/load smoke or a truthful
preallocation rejection, not an unsupported useful-play claim.

Forty-eight deterministic seeds are divided into training, development,
generalization and final sets. Final seeds are forbidden from training,
selection and policy inputs. Native generation must record and reject an
unreachable seed without an implicit retry.

### Executable map qualification

The frozen [`M15 native map evidence`](../../config/v2/m15-map-evidence.json)
executes the complete rectangle list against the accepted OpenTTD binary and
seed `1110312784`. For each in-budget rectangle the qualifier asks native
OpenTTD to generate a game, saves it, parses the OTTX map dimensions, reloads
the save, and records content digests, peak RSS and wall time. Above-budget
requests are rejected before creating an OpenTTD process.

The 2026-08-02 sweep generated and save/load-qualified all 39 rectangles at or
below 1,048,576 tiles. It preflight-rejected the remaining 10 rectangles exactly
as contracted. The generated saves total 2,881,300 bytes, maximum observed RSS
was 89,104 KiB, and summed wall time was 26.623942 seconds. The retained live
artifact tree is
`/home/thecl/.codex/artifacts/openttd-rl/v2-m15-map-matrix-a`; its compact
checked-in projection has SHA-256
`c55befdf90ae1032593e69d0b92fdc9822571621ce3771f3192a58628b258e62`.

Static verification checks every projected result and identity on each V2 run.
Live verification additionally rehashes and semantically validates all 49
per-rectangle manifests:

```text
python3 scripts/v2/run_m15_map_matrix.py --root . \
  --artifact-base /home/thecl/.codex/artifacts/openttd-rl \
  --openttd /home/thecl/.codex/artifacts/openttd-rl/m12-release-final-a/build/openttd-headless/openttd
```

This proves the native generator/save/load boundary and the allocation policy;
it does not yet prove V2 RL reset, bounded observation construction, or useful
play on those maps.

### Source-integrated scalable reset

Patch `0010` adds a separate `rl_v2_environment` translation unit and `-V`/`-U`
manifest/projection entrypoint after the released V1 M11 tree. It does not edit
the frozen V1 environment, bridge, observation, action, reward, or neural-agent
files. The exact base, patch and result-tree identities, accepted build digest,
and 98/98 OpenTTD CTest result are frozen in the
[`native source evidence`](../../config/v2/m15-native-source.json).

The source-integrated reset validates the 20 contracted manifest fields before
generation, derives dimensions with uint16 sides and uint32 tile counts, rejects
more than 1,048,576 tiles before map allocation, invokes native seeded world
generation, creates company zero explicitly, and emits a bounded canonical
projection. Its launcher mode is mutually exclusive with the V1 bridge/reset,
dedicated, and network paths.

The retained sandboxed
[`representative native reset evidence`](../../config/v2/m15-native-reset-evidence.json) covers
64×64 twice, 128×128, 64×256, 512×128, and 1024×1024. The repeated 64×64
projection is byte-identical. The largest run has 128 towns and 846 native
industries, demonstrating that the native pool can exceed the future 256-row
industry observation cap without being reduced. Maximum observed RSS was
61,224 KiB. This was the initial representative executable RL reset subset.

That follow-up is now complete. The
[`49-rectangle source-integrated matrix`](../../config/v2/m15-native-reset-matrix.json)
generated all 39 in-budget rectangles through patch `0010`, with a second
byte-identical 64×64 projection, and applied the frozen source/harness preflight
to all 10 over-budget rectangles. Across the generated matrix, maximum RSS was
61,116 KiB, summed wall time was 8.641477 seconds, the largest town pool was 128,
and the largest native industry pool was 851. This closes the reset/resource
portion of G15; the remaining clauses are evidenced below.

M15 remains passenger-bus and temperate so map scale, variable entity counts and
hierarchical control can be proven before M16 adds the complete cargo/climate
surface. Scenario manifests pin every applicable setting disposition from M14.

## Bounded observation

The V2 observation is fixed-capacity while the world is variable:

- 512 structured float32 features;
- global and regional 32×64×64 spatial tensors plus a local 32×32×32 tensor;
- masked tables for 15 companies, 128 towns, 256 industries, 512 stations and
  1024 vehicles;
- a directed 2,048-node/8,192-edge transport/economy graph; and
- explicit native counts, caps, truncation flags and omitted counts.

Rows use deterministic relevance priority followed by native ID. Truncation
changes only which bounded rows the policy sees; it never deletes native entities
or redefines native legality. The exact tensor and mask capacities total
2,182,927 bytes.

Patch `0001` in the separate M15 observation delta adds the `-W` native
observation output without modifying any frozen V1 RL source file. Its exact
base/result trees, patch digest, executable digest, and 98/98 OpenTTD CTest run
are frozen in the
[`observation source evidence`](../../config/v2/m15-observation-source.json).
The complete 96-field semantic declaration and all 18 contiguous byte sections
are frozen in the
[`detailed observation contract`](../../config/v2/m15-observation-contract.json).

The independent Python decoder checks the binary without using the native
encoder's field implementation. It recomputes SHA-256, parses every float and
mask, rejects NaN/infinity, checks structured and entity data against the
separate reset projection, reconstructs global native tile counts, and checks
graph ordering and directed pairs. On 64×64, where each global cell is exactly
one native tile, it compares every in-map regional and local sample across all
32 channels and verifies explicit zero padding outside the map.

The frozen
[`observation evidence`](../../config/v2/m15-observation-evidence.json) covers
64×64, 64×256, 512×128, and the maximum useful-play 1024×1024 map, plus a
byte-identical 64×64 repeat. Every binary has the same bounded byte count. The
1024×1024 snapshot retains all 846 native industries while selecting 256 rows
and truthfully reporting 590 omitted rows; peak observed RSS was 62,796 KiB.
Mutation tests corrupt offsets, semantic channel order, table capacity, source
and executable identities, deterministic locks, and a live binary byte.

## Hierarchical actions

The action path selects a masked family and then a row from a 4,096-entry
candidate table. M15 covers wait, town-pair selection, road paths, bus stops,
depots, bus purchase, routes, start/stop, depot/service, sale and loan management.

Every exposed legal candidate must pass the authoritative OpenTTD test-mode
command at the issued snapshot. Candidate limits may omit native-legal choices,
but the omission count is reported and omitted choices are never called illegal.
Snapshot tokens bind the contract, session, episode, transition, tick,
observation and candidate bytes. Stale or illegal inputs advance zero ticks and
mutate nothing. Multi-command operations require declared prefix semantics and
exact rollback; rollback failure is fatal.

The detailed [`action contract`](../../config/v2/m15-action-contract.json)
freezes 12 family ranges and quotas, 16 little-endian uint32 parameter words,
32 float32 features, a one-byte mask per row, and exact zero-fill semantics.
The three sections occupy 790,528 bytes: 524,288 feature bytes, 262,144
parameter bytes, and 4,096 mask bytes. Every stable key is recomputed from the
family byte and all parameter words. Candidate order is descending priority and
then ascending stable key inside each fixed family range.

Patch `0001` in the action delta adds separate `rl_v2_action` source and the
`-J` candidate/`-K` request/`-L` result entrypoint. The frozen
[`action source evidence`](../../config/v2/m15-action-source.json) binds its
observation-tree base, patch, result tree, executable, and 98/98 CTest result.
It does not modify the released V1 RL files. The generator exhaustively invokes
native test-mode legality across each declared domain while retaining only the
best quota-sized heap for each family, so memory remains bounded independently
of map area.

The independent decoder behind the frozen
[`action evidence`](../../config/v2/m15-action-evidence.json) reconstructs every
binary row, mask, feature, parameter, key, ordering decision, omission count,
and snapshot token. On 64×64 it found 35,632 legal choices, selected 2,309, and
reported 33,323 omitted. On 1024×1024 it exhaustively tested 9,824,391 legal
choices, retained 2,563, reported 9,821,828 omitted, and stayed at 69,020 KiB
peak RSS. A repeated 64×64 run matched observation, metadata, candidate bytes,
and token exactly.

The initial one-shot cases cover wait, town-pair selection, road, bus stop,
depot, and loan families. Stale-token, out-of-range, masked-row, and
family-mismatch requests all returned typed failures with zero ticks, zero
commands, and zero state mutation.

The follow-up [`stateful episode program`](../../config/v2/m15-episode-program.json)
regenerates the authoritative candidate table at every boundary and executes all
12 families in one native game. It builds two stations and a depot, purchases a
bus, assigns two orders, starts and stops it, sends it to depot, sells it, and
exercises loan and wait transitions. Fourteen successful native commands cover
the normal lifecycle. A forced second-route-insert rejection then proves the
declared transaction: clear and first insert execute, the second insert rejects,
and clear plus both prior-order inserts roll back. Order type and destination are
included in the before/after state digest; state and tick are exactly unchanged.

The isolated episode patch and build are bound by the
[`episode source evidence`](../../config/v2/m15-episode-source.json). Its final
source tree retains all frozen V1 paths, and all 98 OpenTTD tests pass. The
[`episode evidence`](../../config/v2/m15-episode-evidence.json) repeats the full
22-step program twice with byte-identical traces. Within each run it saves the
route-ready boundary, executes a loan-plus-64-tick suffix, reloads, and repeats
that suffix. Native state, save bytes, the 2,182,927-byte observation, the
790,528-byte candidate table, and an independently recomputed candidate
fingerprint are all exact. Peak RSS was 56,876 KiB.

The compact
[`cross-scale replay program`](../../config/v2/m15-cross-scale-replay-program.json)
then repeats a checkpoint, loan-plus-16-tick suffix, capture, reload and identical
suffix at every curriculum and generalization size. The frozen
[`cross-scale replay evidence`](../../config/v2/m15-cross-scale-replay-evidence.json)
contains 18 native processes: paired runs at 64², 128², 256², 512², 64×256,
128×512, 256×1024, 512×128 and 1024². Every pair matches its full trace and
projection; every in-process continuation matches native state, save,
observation bytes, candidate bytes and the semantic candidate fingerprint.
The 1024² case peaked at 90,916 KiB and 47.529804 seconds. This closes
`V2-SCALE-005`, `V2-SCALE-006` and `V2-SCALE-008`.

## Scalable policy and V1 preservation

The frozen [`policy contract`](../../config/v2/m15-policy-contract.json) turns the
model outline into a 25-input, four-output native ABI. The 1,239,406-parameter
C++/LibTorch model combines structured MLP, a shared three-level spatial CNN,
masked entity attention, graph message passing and candidate scoring with a
256-wide GRU. It emits masked family logits, masked candidate logits, value and
the next hidden state. The ONNX opset-18 design has a dynamic batch axis, fixed
contract capacities, explicit masks, hidden-state input/output and an explicit
reset input; training state is excluded.

The native checkpoint is a new, fsynced, atomically renamed generation with an
exact six-file inventory. It retains model, Adam optimizer, normalization,
serialized RNG, curriculum/map counters, contract identity and recurrent state,
and validates every payload digest before load. The frozen
[`policy evidence`](../../config/v2/m15-policy-evidence.json) is built from clean
source commit `96f2424bb0ef4501578defe572462e079d3f3154`. Both CPU and real `cuda:0`
compute-capability-12.0 tests pass shapes, finite values, masks, gradients,
recurrent retain/reset, invalid inputs, never-overwrite and exact checkpoint
recovery. Explicit recurrent reset and recovered forward outputs both have zero
maximum absolute error. Peak process RSS was 680,304 KiB on CPU and 1,812,332
KiB on CUDA. This closes `V2-SCALE-007`.

The V1 model is not zero-padded into this schema. A separate adapter must keep its
32×32 tensors, 41 actions, checkpoint/package identity and behavior bit-exact.

## Passenger-service competence

The isolated competence delta adds a single `SERVICE` episode operation without
editing any frozen V1 RL path. Its deterministic native planner searches around
generated houses for two buildable terminal bus stops, a straight connected road
and a side-connected depot. It uses OpenTTD test-mode commands to reject terrain
whose combined road/depot junction is illegal, then executes native commands to
build the route, buy an MPS Regal bus, assign two station orders and start it.
The oracle advances real game ticks until the company has delivered passengers
and recorded positive income, with a hard 65,536-tick limit and passenger-only,
running-vehicle and entity-delta assertions.

The exact patch, source commit `abc1912e290d8f49221fb3f68e30f3bcb3190ec9`,
tree `fb9a95a7bb03f279a2965516713afd759010a46b`, executable and 98/98
OpenTTD tests are frozen in the
[`competence source evidence`](../../config/v2/m15-competence-source.json).
The compact competence program saves the useful service state, captures it,
loads it and captures it again.

The frozen
[`competence evidence`](../../config/v2/m15-competence-evidence.json) contains
paired isolated runs on 64², 128², 256² and 512² curriculum maps plus held-out
512×128 and 1024² scenarios using previously unused generalization seeds. All
12 runs are twin-process exact and every save/load continuation matches native
state, save, observation and candidate bytes plus the semantic candidate
fingerprint. Each scale builds one connected two-stop passenger route and a
depot, runs one real 31-passenger MPS Regal bus, and produces both delivery and
positive income. The minimum result is 2 delivered passengers and 5 income;
the largest service wait is 1,770 ticks. Peak RSS is 91,068 KiB and the longest
run is 25.292794 seconds. This closes `V2-SCALE-009` without weakening the
retained V1 passenger-service result.

## Verification boundary

The contract, observation, action and map-evidence validators recompute all source/document digests, the 49-rectangle
cross product, seed derivation, tensor byte counts, table/scenario caps, candidate
bytes, resource-tier monotonicity and V1 identities. Mutation tests
reject omissions, forged map outcomes, artifact drift, and weakened resource,
legality, final-seed or V1 compatibility rules:

```text
python3 scripts/v2/validate_m15_scalable_contract.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_m15_policy_contract.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_m15_policy_evidence.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/run_m15_map_matrix.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_m15_native_source.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_m15_native_reset_evidence.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/run_m15_native_reset_matrix.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_m15_observation_contract.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_m15_observation_source.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/freeze_m15_observation_evidence.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_m15_action_contract.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_m15_action_source.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/freeze_m15_action_evidence.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_m15_episode_source.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/freeze_m15_episode_evidence.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_m15_cross_scale_replay_evidence.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_m15_competence_source.py --root .
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_m15_competence_evidence.py --root .
```

This evidence satisfies G15. Native bounded reset, observation construction,
candidate enumeration, all-family lifecycle, transaction rollback, all-scale
replay, the scalable CPU/CUDA policy/checkpoint boundary and useful passenger
service through 512 with held-out rectangle/1024 evaluation are all evidenced.
The complete disposition is recorded in
[`G15_GATE_REPORT.md`](G15_GATE_REPORT.md).
