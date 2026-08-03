# M21 broad base-game, Game Script, and finite-content contract

## Status

`M21 COMPLETE`; accepted by [`G21_GATE_REPORT.md`](G21_GATE_REPORT.md) on
2026-08-02. The machine authority is
[`m21-broad-contract.json`](../../config/v2/m21-broad-contract.json), SHA-256
`325c9f58d17f1a5e8617fcf5d7ced54e1515c6a1fd1edebaa4991a55240e5906`.

M21 closes the base-game calendar/economy/event, Game Script, finite NewGRF,
capability-discovery, and complete research-disposition boundary left after G20.
It preserves all G14-G20 and V1 acceptance floors. It does not claim arbitrary
NewGRF universality, an M22 learned generalist, the M14 final tournament, or an
M23 release package.

## Native calendar, economy, and event boundary

The calendar corpus contains two independent seeds in each of temperate,
sub-arctic, sub-tropical, and Toyland. Every run takes native catalog snapshots
at 1900, 1930, 1950, 1980, 2000, 2050, and 2100. The oracle requires a
nonconstant engine/facility availability and expiry series, a nonempty
climate-specific cargo catalog, a 200-year span, and exact state restoration
after saving at 2050 and moving the calendar away from that checkpoint.

Two authority/economy seeds exercise native positive and invalid town-rating
commands; town-action test/execute cost equality; competitor rejection and
one-month expiry of exclusive rights; a 12-month subsidy award; price and cargo-
payment inflation; native recession entry and recovery; and exact save/load of
rating, subsidy owner, and remaining duration.

Two event seeds prove that disabled breakdowns do not mutate vehicle state,
enabled native breakdowns are observed and recover within 32 ticks, disabled
disasters leave an empty baseline, and an enabled native small-submarine event
completes its lifecycle within eight ticks. The event projection gives the
breakdown an explicit `-1` penalty and recovery a `+1` bonus, then checks exact
save/load of the recoverable public state.

## Game Script boundary

[`M21CoverageFixture`](../../config/v2/m21-gamescript/info.nut) is a passive,
byte-pinned API-15 Game Script. It proves that the native script runtime is
actually active without letting the company policy acquire deity authority.
Two seeds execute 13 native command paths covering:

- goal creation, progress, completion, and a company-addressed question;
- story page and element creation, title update, display, and company button;
- league table and element creation plus score update; and
- the normal-company goal answer and story-page button responses.

Each command must succeed, one goal/page/element/table/table-element must be
observable, both company responses must be retained, and all projected objects
must survive save/load exactly.

## Finite NewGRF compatibility pack

The request and acquisition lock deliberately select ten open-license packages:

| Runtime ID | Package/version | Capability projection | License |
|---|---|---|---|
| `414e0201` | Squid Ate FISH 2.0.3 | ships | GPL v2 |
| `415a1001` | RattRoads 1.2.1 | road and tram types | GPL v2 |
| `43415000` | OpenGFX+ Airports 0.5.0 | airports | GPL v2 |
| `454e1401` | OpenGFX+ Stations 1.0 | rail stations | GPL v2 |
| `4e445903` | Age of Industry Replacement Set 1.3.2 | cargo and industries | GPL v2 |
| `4f472b31` | OpenGFX+ Trains 0.3.0 | trains | GPL v2 |
| `52415608` | RAV8 1.00 | aircraft | GPL v2 |
| `52580101` | FIRS and CHIPS style objects 0.1.10 | objects | GPL v2 |
| `54574606` | Timberwolf's Tracks 1.3.0 | rail types | CC-BY-SA v3.0 |
| `9787eafe` | Road Hog 1.4.1 | road/tram vehicles and cargo refit | GPL v2 |

The acquisition uses OpenTTD's content server only before qualification. It
closes dependencies, bounds archive/member/expanded sizes, rejects absolute,
parent, duplicate, link, and special-file entries, requires license material,
and records archive, member, GRF, license, catalog, executable, and transcript
hashes. Qualification performs no network access.

OpenTTD's catalog/runtime MD5 can differ from the MD5 of the complete container-
formatted `.grf` file. Both identities are retained; the engine enforces the
catalog/runtime MD5 while the source record separately enforces the complete
GRF SHA-256 and byte count. Both content twins load exactly ten IDs and project
14 closed capabilities. The loaded catalogs contain 131 custom train entries,
251 custom road entries, 36 custom ship entries, 96 custom aircraft entries,
37 industries, 116 objects, ten rail types, two road types, and 31 cargoes.

Unknown capability names, unknown content identities, and unknown manifest
schemas are rejected before world creation and before a report can be emitted.
The accepted surface is finite; unsupported content never falls through to a
generic or guessed action encoding.

## Complete feature and command dispositions

[`m21-broad-coverage.json`](../../config/v2/m21-broad-coverage.json), SHA-256
`70e097bb717992098c768bee2972893069d2a2c9284b61a7fdccb812387dfbda`,
matches the research baseline in exact order and occurrence. It contains all 18
feature rows and all 145 command occurrences, including the deliberately
duplicated command occurrence in the pinned source inventory.

The command ledger contains 44 directly evidenced native policy commands, 37
bounded higher-level policy transactions with authoritative native test-before-
execute semantics, two native company Game Script responses, one directly
evidenced safe presentation command, 16 deliberate presentation-only paths, 20
native admin fixtures, and 25 admin commands explicitly denied by the closed
policy surface. Presentation-only proof is legal only for the `policy-optional`
disposition; admin denial is legal only for `benchmark-admin`. Neither can be
used to launder a required economic command.

Thirteen feature rows point to accepted G14-G20 regression evidence, the three
M21 rows point to this contract and native matrix, and the G22/G23 rows point to
their already accepted V1/M15 learning and deployment foundations while
explicitly retaining the future-stage boundary. That mapping proves the
foundation and disposition inventory; it does not prematurely mark the M22 or
M23 V2 requirements complete.

## Matrix and replay contract

The accepted matrix has 16 cases and two fresh OpenTTD processes per case:

- eight calendar cases: four climates times two seeds;
- two authority/economy cases;
- two breakdown/disaster cases;
- two live Game Script cases; and
- two exact-content cases.

All 32 positive runs must pass. Reports are normalized only by removing the two
replicate-specific `run_id` fields; every one of the 16 pairs must then be byte-
identical. Stateful probes must also produce byte-identical native saves within
each pair. The three negative cases are separate and must exit nonzero with the
frozen diagnostic and no report. Runs use null video/music/sound drivers,
process resource limits, fresh processes, and no network calls; the WSL host has
no bubblewrap namespace support, so the record truthfully says `rlimit-only`.

## Accepted identities and verification

- Content lock SHA-256:
  `31d2ebd04f8eea4226e1f50a4dba28b1f11567bc2f7a1b33d059102d2346e266`.
- Source record SHA-256:
  `e3965fbc252a518ee06af91d2797fdcfb241e7b1a3eb8dd81088240cbc2560c4`.
- Matrix evidence SHA-256:
  `7f86c0ed45b51989f4eff2fc9be2de702d60d5dc1fa06c41e495e9853f72d61c`.
- Accepted patch SHA-256:
  `8f118ae510e8f39c0605e8d96f155af5121275025ccd70ce6b46dac259696101`.
- M20 base commit/tree:
  `95af5ebe73d4353e3d50f6bb54c02bb74bf1b8b4` /
  `bca05d858ae5de2a9aa7d3f080ccb2f5677cb7e2`.
- M21 result commit/tree:
  `6429d55789885e7d144f3c663223384821814149` /
  `4273ecf8d52735b1ccac74c3e2ddd4ee73e3fa2a`.
- Native executable SHA-256:
  `c5bd829505a201cc760c31ddcee3d8baff507134d526eae80a92b0fdc52b8d9c`,
  424,406,664 bytes; exact source passes 98/98 upstream CTests.

The source/content validator recomputes the finite capability closure, request,
licenses, runtime IDs, complete GRF bytes, source patch scope, required native
tokens, and optional live tree/build identities. The evidence validator reloads
all 32 reports and 28 stateful saves, recomputes every report/save hash and twin
normalization, validates all probe semantics, and independently checks the
three pre-world failures. Eighteen targeted mutation tests cover contract,
coverage, source, executable, report, save, and negative-diagnostic drift.
