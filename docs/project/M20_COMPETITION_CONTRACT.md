# M20 competitive-company contract

## Status

`M20 COMPLETE`; accepted by [`G20_GATE_REPORT.md`](G20_GATE_REPORT.md) on
2026-08-02. The machine authority is
[`m20-competition-contract.json`](../../config/v2/m20-competition-contract.json),
SHA-256
`0771754a850fca46411003aa903999a9864a31a38bfd3695d8d23397717bf0ef`.

M20 adds native shared-map company creation, exact external-AI selection,
symmetric slot/start-delay blocks, public competitor observations, fault
containment, native interaction probes, and complete tournament accounting to
the accepted M14-M19 boundary. It is a 730-day development qualification, not
the unexecuted 3,650-day M14 final protocol and not the learned generalist
evaluation required by M22.

## Frozen map, settings, content and policy

Every run uses a native 128 by 128 temperate `GWM_NEWGAME` map beginning in
2050, with 16 requested towns, 24 requested industries, and the two paired M14
development map/simulation seed pairs. The setting manifest fixes the economy,
vehicle limits, link-graph modes, station behavior, disabled ending year, and
headless qualification behavior. Plane crashes are disabled to keep the
competition qualification stable; crashed vehicles remain a scored public
field and the interaction probe separately proves native cross-company vehicle
control rejection.

The content closure pins OpenGFX 8.0, AAAHogEx v115, KrakenAI2 v3, NoOpAI, and
all KrakenAI2 libraries by archive digest. NoOpAI's catalog/archive revision is
4 while its selectable `info.nut` runtime declaration is version 3; both
identities are retained rather than conflated. No network acquisition occurs
during a run.

The qualification controller builds and operates a native passenger air service
and must retain positive delivery and gross income. It is a deterministic
competence oracle, not a learned generalist policy. Its accepted M15 policy
contract remains identity-bound, and M22 is still responsible for learning and
broad retained competence.

## Shared-company and visibility boundary

The harness creates the RL company and external AIs in exact native company
slots through OpenTTD's company and `AIConfig` paths. Head-to-head blocks use
four symmetric legs:

| Leg | RL slot/delay | Opponent slot/delay |
|---|---|---|
| A | 0 / 0 days | 1 / 365 days |
| B | 1 / 0 days | 0 / 365 days |
| C | 0 / 365 days | 1 / 0 days |
| D | 1 / 365 days | 0 / 0 days |

Map, settings, content and policy identities remain fixed inside each block.
The policy-visible contract permits public map, station, vehicle, company and
event state plus the RL company's own private state. It denies opponent AI
memory, non-public settings, pathfinder state, private orders, future random
state, and final-suite labels or seeds. Negative mutation tests reject any
unexpected privileged field.

## Matrix and interaction probes

The accepted matrix contains 32 cases and two fresh-process executions of each:

- 24 head-to-head cases: three admitted opponents, two seed pairs, and four
  slot/start-delay legs;
- two solo competence cases;
- two mixed-field cases with RL, AAAHogEx, KrakenAI2, and NoOpAI in four native
  company slots;
- two fault cases that delete a running opponent through native company control,
  retain the scored loss event, and require RL service and save/load to survive;
  and
- two interaction cases that reject wrong-owner vehicle control, create and
  award a native subsidy, execute a native hostile company purchase, and project
  ownership, accounting, subsidy, and collision-disposition events.

Every case saves and reloads the shared simulation at day 700 and completes at
day 730. The public snapshot must restore exactly. Missing, crashed, or timed-out
runs are retained as scored failures and cannot be silently dropped or rerun for
scoring.

## Replay and scoring contract

Exact semantic replay covers manifest identities, settings, slots and delays,
package selection, event/score schemas, public save/load restoration, and score
projection from retained public state. All raw reports and both fresh-process
replicates are retained. Unmodified third-party AIs may make different choices
between fresh processes, so their private decision streams are truthfully
published as stochastic replicates; byte-identical AI decisions are not claimed.
Native save compression byte counts are retained but excluded from semantic
normalization.

The primary statistic is the RL-minus-opponent company-value difference. Two
replicates are averaged within each leg, then all four symmetric legs form one
opponent/seed block. The report uses a preregistered opponent-stratified
percentile bootstrap with 10,000 resamples, seed 141414, and 95% intervals.
Secondary fields include survival, operating profit, delivered cargo, company
value, and failures. Every scheduled run is included; winning every matchup is
explicitly not required.

## Accepted results

All 32 cases and 64 native executions pass, all 32 public save/load and score
projections replay exactly, and no scheduled run is missing. The mean company
value differences and 95% intervals are:

| Opponent | Admission | Mean RL difference | 95% interval |
|---|---|---:|---:|
| AAAHogEx | tournament | 9,232,786.000 | [9,173,268.125, 9,292,303.875] |
| KrakenAI2 | tournament | 9,819,310.125 | [9,767,544.500, 9,871,075.750] |
| NoOpAI | control | 9,964,719.750 | [9,961,040.500, 9,968,399.000] |
| Overall | all strata | 9,672,271.958 | [9,635,177.458, 9,709,366.458] |

These figures qualify the frozen development oracle and benchmark machinery;
they are not evidence that an M22 learned policy universally defeats external
AIs. Some AAAHogEx fresh-process replicate values differ, and both values are
included according to the frozen aggregation rule.

## Evidence and accepted identities

- Map manifest:
  [`m20-map-manifest.json`](../../config/v2/m20-map-manifest.json), SHA-256
  `d0f9216a1735de2643db088ae288f89ac3c76b3867ccccb678186f8b3280aaa9`.
- Settings manifest:
  [`m20-settings-manifest.json`](../../config/v2/m20-settings-manifest.json),
  SHA-256
  `fccf0e04040bc360453e39bb88c07c2d3fc7ff43619add791829fed2381b5c30`.
- Content manifest:
  [`m20-content-manifest.json`](../../config/v2/m20-content-manifest.json),
  SHA-256
  `9181ee83d204fc9af95501a699fa583d8240d3f0620ec692b6f67465cc7120de`.
- Source record:
  [`m20-competition-source.json`](../../config/v2/m20-competition-source.json),
  SHA-256
  `45d54206d9e7dc92fe6b5188c063bbbfd95218f369d351c94709917ff23feb20`.
- Matrix evidence:
  [`m20-competition-evidence.json`](../../config/v2/m20-competition-evidence.json),
  SHA-256
  `ab59a139a95878f304b1b1b64167a2664987db5813a5590b006be609c4a85845`.
- Accepted patch SHA-256
  `fd259d000ad55dc8e7fb5eb198cc16fa85c992d86b5144ba5f3124e4e3a1c286`.
- M19 base commit/tree:
  `1b07432dc0a196673a461bb49c7ca59d2175e9bf` /
  `ada560ed740f522bf7327703201e657503b6f9b9`.
- M20 result commit/tree:
  `95af5ebe73d4353e3d50f6bb54c02bb74bf1b8b4` /
  `bca05d858ae5de2a9aa7d3f080ccb2f5677cb7e2`.
- Native executable: SHA-256
  `b1904e3ab79dba3854124ac9450b06b9207a12b5f33496454bda24cbf110cc5e`,
  420,233,440 bytes; the exact source tree passes 98/98 OpenTTD CTests.

The source validator checks the exact four-file delta from the M19 base and
rehashes the retained tree, executable, config, patch, graphics, and AI content.
The evidence validator reloads all 64 raw reports and independently recomputes
case identities, public replay, metrics, fairness blocks, complete-run
accounting, and bootstrap statistics. Thirteen targeted mutation tests cover
source and evidence drift; the aggregate verifier retains every earlier V2 and
V1 gate.
