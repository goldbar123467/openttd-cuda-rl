# G19 aircraft and multimodal gate report

## Decision

`G19 PASS` on 2026-08-02.

The gate accepts the base airport catalog, native airport construction and
aircraft lifecycle, fixed-wing and helicopter service, airport occupancy and
failure recovery, conserved road-water-air transfer accounting, and a stable
four-mode router contract. It preserves G14-G18 and V1 and makes no claim for
M20-M23. This is the requested main-branch checkpoint before competitive-company
work begins.

## Gate evidence

| G19 clause | Result | Evidence |
|---|---|---|
| Airport catalog and construction | `PASS` | Ten base specifications, nine buildable facilities, date/footprint/spread/noise/terrain/ownership legality, and disabled oil-rig rejection |
| Aircraft lifecycle | `PASS` | Airplane/helicopter purchase, refit, orders, timetables, service, clone, native range checks, save/load, actual autoreplace, and sale |
| Occupancy | `PASS` | Four simultaneous aircraft expose native airport blocks, movement states, targets, runway/taxiway/terminal occupancy, and competing arrivals |
| Failure behavior | `PASS` | Native close/reopen, seeded native crash state, vehicle loss/accounting projection, and blocked airport removal |
| Airplane service | `PASS` | Two seeds deliver 25/15 units for 466/551 positive income |
| Helicopter service | `PASS` | Two seeds deliver 40/28 units for 723/996 positive income |
| Congestion recovery | `PASS` | Closed destination produces no delivery; reopen resumes profitable delivery within the frozen horizon |
| Three-mode conservation | `PASS` | Road-to-water-to-air moves all 14 units, creates exactly two feeder-transfer events with no cash, and pays once at final delivery |
| Stable generalist contract | `PASS` | Four-mode road/rail/water/air graph, deterministic specialist selection, exact checkpoint restoration, and no privileged inputs |
| Opponent disposition | `PASS` | AAAHogEx remains the active generalist; Lufthansa remains truthfully rejected because its exact archive is malformed and is not repaired or relabeled |
| Native source regression | `PASS` | Accepted result tree and executable; OpenTTD CTest 98/98 |
| Earlier correctness floors | `PASS` | Aggregate V2 verifier plus unchanged V1 traceability/document/test suite |
| Invalidating defects | `PASS` | Zero nonclosed entries in [`defects-v2.json`](defects-v2.json) |

The detailed action/observation contract, controlled-fixture boundary, matrix,
source identities, third-party dispositions, and isolation limitation are in
[`M19_AIR_MULTIMODAL_CONTRACT.md`](M19_AIR_MULTIMODAL_CONTRACT.md).

## Accepted machine evidence

- Contract: [`m19-air-contract.json`](../../config/v2/m19-air-contract.json),
  SHA-256 `213a416a7a20270261c10e0327043e65267d7a2fe8976c61320a5b7259dea6ca`.
- Source: [`m19-air-source.json`](../../config/v2/m19-air-source.json), SHA-256
  `eaa34874b10114de13465590d92b531c13287aa9ce662e25cfb9eefebf8fb6ec`.
- Matrix: [`m19-air-evidence.json`](../../config/v2/m19-air-evidence.json),
  SHA-256 `c0fe61de03698fef54682cc2b18107090ac3531f3e4a1a1cf112fd6cf01bb1d0`.
- Patch: [`0001-Add-native-V2-aircraft-qualification.patch`](../../integration/openttd/patches/15.3/m19/air/0001-Add-native-V2-aircraft-qualification.patch),
  SHA-256 `dbbab4f4b999bb2af484890ee1527f145f0d9f84b863ca5755e914618c004f4c`.
- M18 base commit/tree:
  `70c13453e2c1c6e122df8323938460778e116f79` /
  `cb30c85604f73cd29b5a12b6d50990847fc2f5e8`.
- M19 result commit/tree:
  `1b07432dc0a196673a461bb49c7ca59d2175e9bf` /
  `ada560ed740f522bf7327703201e657503b6f9b9`.
- Native executable: SHA-256
  `75d262c0b6ed839c16fe8fb341a0541c86fa746078e8253b4581eef10cff19bd`,
  416,293,112 bytes; exact OpenTTD tree passes 98/98 CTests.

## Acceptance boundary

Source cargo packets and sink acceptance are bounded qualification fixtures.
Construction, aircraft, pathfinding, movement, transfer, delivery, payment,
failure/recovery transitions, and save/load are native. Useful service and mode
routing are deterministic qualification oracles, not evidence of the learned
generalist required by M22.

AAAHogEx is active in the retained M14 evidence but chose one train and no
aircraft, so it is not misreported as demonstrating air competence. The native
air oracle supplies that competence boundary. Lufthansa v2 remains `REJECTED`
and `EXCLUDED`: the byte-pinned archive contains invalid generated markup in
`info.nut` and a truncated `main.nut`. No package bytes were repaired.

Bubblewrap could not create a namespace on this WSL host. Accepted matrix runs
record process resource limits, no network calls, and null drivers as
`rlimit-only` rather than claiming namespace isolation.

## Verification result

The M19 matrix contains 20 cases, 40 fresh-process native runs, ten probes, and
20 exact twins. Catalog evidence covers ten airport specifications and 41
aircraft engine entries. Source and matrix validators reject identity, report,
metric, baseline, or twin drift. The exact OpenTTD build passes 98/98 CTests.
The aggregate command is:

```text
./scripts/v2/verify.sh
```

## Stopping point

This is the requested clean G19 checkpoint on `main`. M20 competitive companies
and the external-AI tournament are next in dependency order and are intentionally
absent from this commit.
