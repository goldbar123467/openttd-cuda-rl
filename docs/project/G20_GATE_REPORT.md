# G20 competitive-company gate report

## Decision

`G20 PASS` on 2026-08-02.

The gate accepts native shared-map competition against every admitted M14 audit
opponent, symmetric company-slot and start-delay blocks, public-state-only policy
inputs, shared save/load replay, opponent fault containment, native ownership and
subsidy interactions, and complete preregistered scoring. It preserves G14-G19
and V1 and makes no claim for M21-M23, the unexecuted M14 final protocol, or a
learned M22 generalist. This is the requested main-branch checkpoint before
broad base-game, Game Script, and NewGRF work begins.

## Gate evidence

| G20 clause | Result | Evidence |
|---|---|---|
| Shared native simulation | `PASS` | Solo, head-to-head, and four-company mixed fields use exact native company slots and one generated map |
| Fairness | `PASS` | Three opponents, two seed pairs, four symmetric slot/delay legs, two fresh-process replicates, and fixed block identities |
| Public observations | `PASS` | Declared public/self field allowlist, opponent-private denylist, zero privileged inputs, and mutation rejection |
| Interaction projection | `PASS` | Wrong-owner vehicle command rejection, native subsidy creation/award, hostile purchase, ownership/accounting events, and explicit collision disposition |
| Fault containment | `PASS` | Native opponent deletion records a failure/loss floor while RL service and day-700 save/load continue to day 730 |
| Solo competence | `PASS` | Both solo seeds retain positive native passenger delivery and gross income |
| Manifest replay | `PASS` | Exact identities/settings/slots/packages/event schema, 32 exact public save/load and score projections, and both raw replicates retained |
| External-AI stochasticity | `PASS` | Unmodified AI decisions are published as stochastic fresh-process replicates; byte equality is not claimed or required |
| Complete scoring | `PASS` | All 64 scheduled executions included, paired four-leg block effects, 10,000-resample 95% intervals, no scoring reruns or dropped failures |
| Opponent coverage | `PASS` | AAAHogEx v115, KrakenAI2 v3, and NoOpAI control all receive paired multi-seed coverage |
| Native source regression | `PASS` | Accepted result tree and executable; OpenTTD CTest 98/98 |
| Earlier correctness floors | `PASS` | Aggregate V2 verifier plus unchanged V1 traceability/document/test suite |
| Invalidating defects | `PASS` | Zero nonclosed entries in [`defects-v2.json`](defects-v2.json) |

The detailed qualification boundary, fairness design, visibility fields,
interaction/failure behavior, replay definition, results, and limitations are in
[`M20_COMPETITION_CONTRACT.md`](M20_COMPETITION_CONTRACT.md).

## Accepted machine evidence

- Contract:
  [`m20-competition-contract.json`](../../config/v2/m20-competition-contract.json),
  SHA-256
  `0771754a850fca46411003aa903999a9864a31a38bfd3695d8d23397717bf0ef`.
- Source:
  [`m20-competition-source.json`](../../config/v2/m20-competition-source.json),
  SHA-256
  `45d54206d9e7dc92fe6b5188c063bbbfd95218f369d351c94709917ff23feb20`.
- Matrix:
  [`m20-competition-evidence.json`](../../config/v2/m20-competition-evidence.json),
  SHA-256
  `ab59a139a95878f304b1b1b64167a2664987db5813a5590b006be609c4a85845`.
- Patch:
  [`0001-Add-native-V2-competition-qualification.patch`](../../integration/openttd/patches/15.3/m20/competition/0001-Add-native-V2-competition-qualification.patch),
  SHA-256
  `fd259d000ad55dc8e7fb5eb198cc16fa85c992d86b5144ba5f3124e4e3a1c286`.
- M19 base commit/tree:
  `1b07432dc0a196673a461bb49c7ca59d2175e9bf` /
  `ada560ed740f522bf7327703201e657503b6f9b9`.
- M20 result commit/tree:
  `95af5ebe73d4353e3d50f6bb54c02bb74bf1b8b4` /
  `bca05d858ae5de2a9aa7d3f080ccb2f5677cb7e2`.
- Native executable: SHA-256
  `b1904e3ab79dba3854124ac9450b06b9207a12b5f33496454bda24cbf110cc5e`,
  420,233,440 bytes; exact OpenTTD tree passes 98/98 CTests.

## Result summary

The accepted development matrix has 32 cases and 64 native executions: 24
head-to-head cases, two solo cases, two four-company mixed fields, two opponent
faults, and two ownership/subsidy/purchase interactions. All scheduled runs are
present and all 32 public projections replay exactly.

RL-minus-opponent mean company-value differences are 9,232,786.000 against
AAAHogEx (95% interval 9,173,268.125 to 9,292,303.875), 9,819,310.125 against
KrakenAI2 (9,767,544.500 to 9,871,075.750), and 9,964,719.750 against NoOpAI
(9,961,040.500 to 9,968,399.000). The stratified overall mean is
9,672,271.958 (9,635,177.458 to 9,709,366.458). Universal victory is not an
acceptance criterion, and these qualification-oracle results are not presented
as learned-policy performance.

## Acceptance boundary

The controller is a deterministic native air-service qualification oracle. The
shared map, companies, aircraft, service, delivery, accounting, opponent AIs,
company deletion, wrong-owner command rejection, subsidy, purchase, and save/load
transitions are native. Physical plane crashes are disabled in the frozen
settings; the scored crash field and native ownership collision rejection remain
explicit. Bubblewrap namespaces are unavailable on the WSL host, so runs record
process limits, null drivers, no network calls, and truthful `rlimit-only`
isolation.

External AI packages are unmodified. Their decision streams may vary across
fresh processes, so exact replay is deliberately limited to manifest/state/score
semantics and exact public projection restoration. Both replicates are retained
and scored. The M14 3,650-day final protocol remains unexecuted at M20.

## Verification result

The source and evidence validators pass, 13 M20 mutation/unit tests pass, the
exact OpenTTD build passes 98/98 CTests, and the aggregate command retains all
earlier V2 and V1 gates:

```text
./scripts/v2/verify.sh
```

## Stopping point

This is the requested clean G20 checkpoint on `main`. M21 broad base-game,
Game Script, NewGRF, and event coverage is next in dependency order.
