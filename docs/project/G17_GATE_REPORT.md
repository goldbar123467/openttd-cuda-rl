# G17 rail network gate report

## Decision

`G17 PASS` on 2026-08-02.

The gate accepts native rail construction and conversion, facilities, all base
signal types, reservations, train lifecycle and rail save/load, deterministic
passenger/freight service, and a long shared-network safety soak. It preserves
G14-G16 and V1 and makes no claim for M18-M23. Work intentionally stops here;
M18 has not started.

## Gate evidence

| G17 clause | Result | Evidence |
|---|---|---|
| Rail types, track and conversion | `PASS` | Four rail types; six orientations; native test/execute/remove; junction, rail/road crossing, slope, invalid-type, foreign-owner, and conversion cases |
| Stations, depots and waypoints | `PASS` | Native build/remove, width 2 by height 1 platform geometry, length 2, catchment 4, rename, and removal preserving rail |
| Consists and lifecycle | `PASS` | Locomotive/wagon assembly, refit, clone, sale, two orders, all station-order flag categories, timetable, service, and actual autoreplace 0 to 8 |
| Save/load state | `PASS` | Native save, service mutation 120 to 180, reload restoration to 120 with orders and flags retained |
| Signals and reservations | `PASS` | Six types times electric/semaphore, three direction-bit states, actual removal, reserve/duplicate reject/release |
| Safety observations | `PASS` | Junction, crossing, platform, congestion, stuck and collision positive/negative projections |
| Shared-network stress | `PASS` | Two trains, two path signals, three terminals, one physical connector and shared destination for 32,768 ticks; maximum wait 2,899; zero unresolved deadlock/collision |
| Useful rail service | `PASS` | Passenger 40/699/1,815 and coal 30/1,002/1,828 delivery/income/ticks, each on two seeds and exact fresh-process twins |
| Qualified rail specialist | `PASS` | AAAHogEx frozen tournament runtime; ChooChoo rejection retained truthfully |
| Native source regression | `PASS` | Accepted result tree and executable; OpenTTD CTest 98/98 |
| Earlier correctness floors | `PASS` | Aggregate V2 verifier plus unchanged V1 traceability/document/test suite |
| Invalidating defects | `PASS` | Zero nonclosed entries in [`defects-v2.json`](defects-v2.json) |

The detailed contract, controlled-fixture boundary, matrix composition, source
identities, baseline disposition, and isolation limitation are in
[`M17_RAIL_NETWORK_CONTRACT.md`](M17_RAIL_NETWORK_CONTRACT.md).

## Accepted machine evidence

- Contract: [`m17-rail-contract.json`](../../config/v2/m17-rail-contract.json),
  SHA-256 `08dee4ec893cf2e26199a698f7847835b78571230f731ab9242fa181bf49297f`.
- Source: [`m17-rail-source.json`](../../config/v2/m17-rail-source.json),
  SHA-256 `5bea9ea4d38f35ef040c2cad672a7cb90955a899ad61e929891c746d12aacaae`.
- Matrix: [`m17-rail-evidence.json`](../../config/v2/m17-rail-evidence.json),
  SHA-256 `d9955d4598bde37e10ccaccb22add01f66ee8a8c4d369e47794719fceb3e9dc7`.
- Source commit/tree:
  `eb7b769eb9339ecbde7ed69015230079e92d3316` /
  `c9fd523f51bfb68c8da114e64f8183dc48496abb`.
- Executable SHA-256:
  `f3a6d9a39cebd171697516b41b5ac5d857e887cfe83e4de0df9f957a0466e9ff`.

## Acceptance boundary

Source packets, sink acceptance, and preloading are controlled fixture setup.
Rail construction, consists, refits, orders, timetables, service and replacement,
signalling, reservations, pathfinding, movement, final delivery, payment, and
save/load are native. Competence is a deterministic useful-service oracle against
zero-service comparators, not a learned-policy claim.

Bubblewrap could not create a namespace on this WSL host. Accepted runs use
recorded process resource limits, no network calls, and null drivers; evidence
labels this `rlimit-only` rather than claiming namespace isolation.

## Verification result

The M17 matrix contains 14 cases, 28 native runs, and 14 exact twins. The
source/evidence validators reject identity, report, metric, baseline, or twin
drift. The M17-specific unit suite passes 14/14 and the exact OpenTTD build passes
98/98 CTests. The aggregate command is:

```text
./scripts/v2/verify.sh
```

## Stopping point

This is the requested clean stopping point. M18 ships/waterways is the next
planned milestone, but no M18 implementation or gate claim is included in this
commit.
