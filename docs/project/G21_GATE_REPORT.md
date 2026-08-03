# G21 broad base-game, Game Script, and finite-content gate report

## Decision

`G21 PASS` on 2026-08-02.

The gate accepts all-climate long-calendar behavior, authority/economy and
recoverable event semantics, live Game Script interaction, a finite byte-pinned
NewGRF compatibility pack, fail-closed capability discovery, and exact mapping
of all 18 research domains and 145 command occurrences. It preserves G14-G20
and V1. It makes no arbitrary-NewGRF, learned-M22-generalist, final-tournament,
or V2-release claim.

## Gate evidence

| G21 clause | Result | Evidence |
|---|---|---|
| Four climates and 200 calendar years | `PASS` | Eight cases cross seven 1900–2100 boundaries with nonconstant engine/facility availability and exact 2050 save/load |
| Authority and exclusivity | `PASS` | Native rating positive/negative, town-action cost equality, competitor rejection, one-month exclusive-rights expiry, and exact restoration |
| Subsidy and economy | `PASS` | Native 12-month award, inflation in price/payment/accounting, recession entry/recovery, and two exact seed pairs |
| Breakdowns and disasters | `PASS` | Enabled/disabled behavior, explicit reward semantics, bounded recovery/lifecycle, and exact save/load |
| Game Script | `PASS` | Live pinned API-15 fixture; 13 successful goal/question/story/league/response commands; exact object restoration |
| Finite NewGRF pack | `PASS` | Ten exact runtime IDs, complete archive/GRF/license lock, 14 closed capabilities, and non-vacuous loaded catalogs |
| Capability discovery | `PASS` | Unknown capability, ID, and schema exit nonzero before world/report emission with exact diagnostics |
| Feature coverage | `PASS` | Exact ordered mapping of all 18 research rows, including explicit G22/G23 foundation/stage boundaries |
| Command dispositions | `PASS` | Exact ordered/occurrence mapping of 81 required, 19 optional, and 45 admin commands without optional/admin laundering |
| Determinism and persistence | `PASS` | 16/16 exact report twins and all 14 stateful case pairs have byte-identical native saves |
| Native source regression | `PASS` | Four-file patch, exact result tree/executable, and 98/98 OpenTTD CTests |
| Earlier correctness floors | `PASS` | Aggregate V2 verifier plus unchanged complete V1 traceability and tests |
| Invalidating defects | `PASS` | Calendar-oracle repeatability defect discovered by the second seed was fixed and regression-covered; zero nonclosed ledger entries |

The detailed semantics and limits are in
[`M21_BROAD_CONTENT_CONTRACT.md`](M21_BROAD_CONTENT_CONTRACT.md).

## Accepted machine evidence

- Contract:
  [`m21-broad-contract.json`](../../config/v2/m21-broad-contract.json), SHA-256
  `325c9f58d17f1a5e8617fcf5d7ced54e1515c6a1fd1edebaa4991a55240e5906`.
- Coverage:
  [`m21-broad-coverage.json`](../../config/v2/m21-broad-coverage.json), SHA-256
  `70e097bb717992098c768bee2972893069d2a2c9284b61a7fdccb812387dfbda`.
- Source:
  [`m21-broad-source.json`](../../config/v2/m21-broad-source.json), SHA-256
  `e3965fbc252a518ee06af91d2797fdcfb241e7b1a3eb8dd81088240cbc2560c4`.
- Matrix:
  [`m21-broad-evidence.json`](../../config/v2/m21-broad-evidence.json), SHA-256
  `7f86c0ed45b51989f4eff2fc9be2de702d60d5dc1fa06c41e495e9853f72d61c`.
- Content lock:
  [`m21-content-lock.json`](../../config/v2/m21-content-lock.json), SHA-256
  `31d2ebd04f8eea4226e1f50a4dba28b1f11567bc2f7a1b33d059102d2346e266`.
- Patch:
  [`0001-Add-native-V2-broad-feature-qualification.patch`](../../integration/openttd/patches/15.3/m21/broad/0001-Add-native-V2-broad-feature-qualification.patch),
  SHA-256
  `8f118ae510e8f39c0605e8d96f155af5121275025ccd70ce6b46dac259696101`.
- M21 source commit/tree:
  `6429d55789885e7d144f3c663223384821814149` /
  `4273ecf8d52735b1ccac74c3e2ddd4ee73e3fa2a`.
- Executable SHA-256:
  `c5bd829505a201cc760c31ddcee3d8baff507134d526eae80a92b0fdc52b8d9c`,
  424,406,664 bytes.

## Result summary

The accepted development matrix contains 16 cases, 32 fresh-process native
executions, and three negative launches. All 16 normalized report pairs and all
14 stateful save pairs are exact. The maximum positive-run wall time was
0.162688 seconds. No qualification run used the network.

The content projection loaded ten packages and exposed 131 custom train, 251
custom road, 36 custom ship, and 96 custom aircraft entries, plus 37 industries,
116 objects, ten rail types, two road types, and 31 cargoes. These counts prove
the selected pack is non-vacuous; they are not a compatibility promise for
unselected or arbitrary NewGRFs.

## Defect closure

The first two-seed matrix found that the calendar save/load oracle called native
engine startup again after loading. Introduction randomness could therefore be
consumed during comparison, making one seed fail despite correct restoration.
The accepted source now performs a read-only post-load snapshot and asserts the
restored year. Both seeds in every climate and all 16 exact twins pass. The
closed entry `V2-DEF-0001` records the discovery, cause, fix, and regression.

## Verification result

The source/content and evidence validators pass, all 18 M21 mutation tests pass,
the exact OpenTTD build passes 98/98 CTests, and the aggregate command retains
every earlier V2 and V1 gate:

```text
./scripts/v2/verify.sh
```

## Next stage

M22 is next in dependency order: trusted scalable generalist PPO, recurrent and
graph/attention state, matched architectures, measured CUDA, exact recovery,
retention throughout training, and preregistered independent evaluation across
modes, climates, sizes, cargoes, and opponents.
