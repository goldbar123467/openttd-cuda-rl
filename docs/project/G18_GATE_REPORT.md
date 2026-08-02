# G18 ship and waterway gate report

## Decision

`G18 PASS` on 2026-08-02.

The gate accepts native water/facility construction, water-region connectivity,
ship lifecycle and save/load, natural and constructed profitable service,
road-to-ship accounting, bounded disconnected-route recovery, and a
scenario-qualified ShipAI specialist. It preserves G14-G17 and V1 and makes no
claim for M19-M23. Work stops here for the requested main-branch checkpoint.

## Gate evidence

| G18 clause | Result | Evidence |
|---|---|---|
| Docks, depots and buoys | `PASS` | Native test/execute/remove, explicit distant dock join, facility state, cost, and foreign-owner rejection |
| Natural water and regions | `PASS` | Sea, river, and canal catalog; native region/patch graph agrees with independent flood fill across cut/reconnect |
| Canals, locks and aqueducts | `PASS` | Native positive/negative construction, ownership/class state, removal, and forced lock/aqueduct traversal |
| Ship lifecycle | `PASS` | Purchase, refit, orders/flags, timetable, 120-tick service, clone, actual autoreplace, sale, and passenger/freight capacity |
| Save/load and safety | `PASS` | Native state restoration plus lost-positive/lost-cleared and no-crash projections |
| Natural useful service | `PASS` | Passenger and coal service over sea/river routes with positive native delivery and income on two seeds |
| Constructed useful service | `PASS` | Passenger and coal canal service with observed lock/aqueduct traversal and positive delivery/income |
| Transfer conservation | `PASS` | Road feeder leg creates no company cash; exactly one final ship payment delivers all 20 transferred coal units |
| Recovery | `PASS` | Disconnection and lost state detected, ship safely stopped, route reconstructed, profitable service completed within bound |
| Qualified specialist | `PASS` | Byte-pinned ShipAI v10 builds two ships on the retained coastal scenario and preserves both across save/load |
| Native source regression | `PASS` | Accepted result tree and executable; OpenTTD CTest 98/98 |
| Earlier correctness floors | `PASS` | Aggregate V2 verifier plus unchanged V1 traceability/document/test suite |
| Invalidating defects | `PASS` | Zero nonclosed entries in [`defects-v2.json`](defects-v2.json) |

The detailed action/observation contract, controlled-fixture boundary, matrix,
source identities, ShipAI disposition, and isolation limitation are in
[`M18_SHIP_WATERWAY_CONTRACT.md`](M18_SHIP_WATERWAY_CONTRACT.md).

## Accepted machine evidence

- Contract: [`m18-ship-contract.json`](../../config/v2/m18-ship-contract.json),
  SHA-256 `4f82983b88f7f1722ac85bbdc11f3293af4a668cabb752edc4d2a1c21d396a91`.
- Source: [`m18-ship-source.json`](../../config/v2/m18-ship-source.json),
  SHA-256 `d831d5b5f1959cce765a2978f170349f5dcdb51d4d1ebaeee6c3e2ff4cf094f7`.
- ShipAI: [`m18-shipai-evidence.json`](../../config/v2/m18-shipai-evidence.json),
  SHA-256 `d9f6df42f6638e2293dfa3abf772068115c357e0fd037cb0ef205997b2783e6f`.
- Matrix: [`m18-ship-evidence.json`](../../config/v2/m18-ship-evidence.json),
  SHA-256 `9963f4bee47c9870cd2725516af6c79eb4de60c8a694b17f55fd46e6f3cb2491`.
- Source commit/tree:
  `70c13453e2c1c6e122df8323938460778e116f79` /
  `cb30c85604f73cd29b5a12b6d50990847fc2f5e8`.
- Executable SHA-256:
  `a21afaedc696d25a807b10b920ad14b86886a9d8d9870c35c8636d1234d360a9`.

## Acceptance boundary

Source packets and sink acceptance are bounded fixtures. Construction, vehicles,
pathfinding, movement, transfer, delivery, payment, recovery transitions, and
save/load are native. Useful service is a deterministic oracle against frozen
zero-service comparators, not learned-generalist evidence. ShipAI is qualified
only for this retained water scenario, not yet for shared-map competition.

Bubblewrap could not create a namespace on this WSL host. Accepted matrix runs
record process resource limits, no network calls, and null drivers as
`rlimit-only` rather than claiming namespace isolation.

## Verification result

The M18 matrix contains 16 cases, 32 native runs, eight probes, and 16 exact
twins. Catalog evidence covers 11 ship engines and three water classes. The
source, ShipAI, and matrix validators reject identity, report, metric, package,
baseline, or twin drift. The exact OpenTTD build passes 98/98 CTests. The
aggregate command is:

```text
./scripts/v2/verify.sh
```

## Stopping point

This is the requested clean G18 stopping point. M19 aircraft and broader
multimodal work is next in the dependency order and is intentionally absent from
this commit.
