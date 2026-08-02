# G15 scalable environment and passenger-competence gate report

## Decision

`G15 PASS` on 2026-08-02.

This gate establishes the scalable V2 passenger-bus environment, bounded native
observation/action boundary, variable-input policy/checkpoint, exact replay and
useful-service floor. It does not claim the M16–M23 cargo, transport, world,
competition, training, packaging or V2 release milestones are complete.

## Accepted implementation identities

- OpenTTD base: release 15.3, commit
  `14ec60f248547d4d062a1160f0fc26d742319888`, tree
  `02d8cbbb0d8c030698d37ca76ab2773b6e23c397`.
- Scalable environment contract SHA-256:
  `b7a4ba1fc20507b77e2ef2ac01347665526cdbd4fc3e036587df5bdb3666d271`.
- Final competence source: commit
  `abc1912e290d8f49221fb3f68e30f3bcb3190ec9`, tree
  `fb9a95a7bb03f279a2965516713afd759010a46b`.
- Final competence executable SHA-256:
  `a8b72d477967743f9f64800ec89d7d9301ce40f7717f1689e2dc8aa1b616b6d1`;
  400,701,752 bytes; OpenTTD CTest 98/98.
- Native scalable policy: 1,239,406 parameters, pinned LibTorch 2.13.0+cu130,
  CPU and real CUDA compute-capability-12.0 gates passed with exact recurrent
  reset and checkpoint recovery.

## Gate evidence

| G15 clause | Result | Evidence |
|---|---|---|
| Native scalable reset and resource bounds | `PASS` | [`m15-native-reset-evidence.json`](../../config/v2/m15-native-reset-evidence.json), [`m15-native-reset-matrix.json`](../../config/v2/m15-native-reset-matrix.json) |
| Bounded multi-resolution observations and variable entity/graph schemas | `PASS` | [`m15-observation-contract.json`](../../config/v2/m15-observation-contract.json), [`m15-observation-evidence.json`](../../config/v2/m15-observation-evidence.json) |
| Hierarchical actions, native legality and exact rollback | `PASS` | [`m15-action-contract.json`](../../config/v2/m15-action-contract.json), [`m15-action-evidence.json`](../../config/v2/m15-action-evidence.json), [`m15-episode-evidence.json`](../../config/v2/m15-episode-evidence.json) |
| Variable-input CPU/CUDA policy and atomic checkpoint recovery | `PASS` | [`m15-policy-contract.json`](../../config/v2/m15-policy-contract.json), [`m15-policy-evidence.json`](../../config/v2/m15-policy-evidence.json) |
| Curriculum/generalization deterministic replay | `PASS` | [`m15-cross-scale-replay-evidence.json`](../../config/v2/m15-cross-scale-replay-evidence.json) |
| Useful passenger service at curriculum and held-out scales | `PASS` | [`m15-competence-source.json`](../../config/v2/m15-competence-source.json), [`m15-competence-evidence.json`](../../config/v2/m15-competence-evidence.json) |
| V1 correctness floor unchanged | `PASS` | Complete V1 traceability/document suite and all 235 V1 tests |
| Invalidating defects | `PASS` | Zero nonclosed entries in [`defects-v2.json`](defects-v2.json) |

## Passenger-service acceptance result

Twelve sandboxed native runs cover paired executions at 64², 128², 256² and
512² plus held-out 512×128 and 1024² scenarios. Every run builds a connected
road between two house-adjacent bus stops, adds a connected depot, buys a real
31-passenger MPS Regal bus, installs two station orders, starts it, delivers
passengers and records positive company income. The minimum case delivers two
passengers for five income; no case exceeds 1,770 simulation ticks. All twin
traces and projections are exact, and every in-process save/load continuation
matches native state, save, observation and candidate bytes plus semantic
candidate identity. Peak RSS is 91,068 KiB and maximum wall time is 25.292794
seconds.

## Aggregate verification

The accepted command is:

```text
./scripts/v2/verify.sh
```

It exited zero, validated all frozen M14/M15 contracts and evidence, and
reported:

```text
V2_M15_CONTRACT=PASS rectangles=49 seeds=48 spatial=3 entities=5 action_families=12 observation_bytes=2182927 candidates=4096
V2_M15_POLICY_EVIDENCE=PASS files=6 devices=2 parameters=1239406 live_source=false live_artifact=false
V2_M15_CROSS_SCALE_REPLAY_EVIDENCE=PASS cases=9 runs=18 max_rss_kib=90916 max_wall_seconds=47.529804 live=false
V2_M15_COMPETENCE_SOURCE=PASS files=1 result_tree=fb9a95a7bb03f279a2965516713afd759010a46b live_source=false live_build=false
V2_M15_COMPETENCE_EVIDENCE=PASS cases=6 runs=12 min_passengers=2 min_income=5 max_ticks=1770 max_rss_kib=91068 max_wall_seconds=25.292794 live=false
V2_TRACEABILITY=PASS requirements=86 passed=17 in_progress=0 planned=69 tests=26 tests_passed=18 nonclosed_defects=0
Ran 248 tests ... OK
V1_TRACEABILITY=PASS requirements=227 tests=19 requirements_passed=217 post_v1_deferred=10 nonclosed_defects=0
V1_DOCS=PASS
Ran 235 tests ... OK
```

Artifact-backed validators were also run against the retained competence source,
build and 12-run matrix. They rehashed every executable, patch, program, trace,
checkpoint, observation and candidate artifact and passed. Static validation
remains in the aggregate suite so a clean checkout does not require host-local
retained artifacts.

## Next authorized work

M16 may now implement all base cargo chains and climates on the G15 environment.
It must preserve the complete G15 and V1 boundaries. G16 cannot inherit a pass
from passenger competence or from contract-only coverage.
