# M18 ship and waterway contract

## Status

`M18 COMPLETE`; accepted by [`G18_GATE_REPORT.md`](G18_GATE_REPORT.md) on
2026-08-02. The machine authority is
[`m18-ship-contract.json`](../../config/v2/m18-ship-contract.json), SHA-256
`4f82983b88f7f1722ac85bbdc11f3293af4a668cabb752edc4d2a1c21d396a91`.

This milestone appends ship construction, lifecycle, water connectivity,
profitable service, transfer accounting, and route recovery to the frozen M17
rail, M16 cargo, and M15 scalable boundaries. It does not claim aircraft,
generalist multimodal learning, competitive play, broad-content coverage, or V2
release completion.

## Frozen water extension

The action extension defines 25 typed families covering water-class selection;
canal, dock, depot, buoy, lock, and aqueduct construction/removal; dock joining;
ship purchase, refit, clone, sale, orders, timetables, service, autoreplace,
start/stop, transfer orders, and route recovery. Native command test mode remains
the legality authority.

The observation extension adds 17 bounded tables for water classes, ship engines,
water tiles/regions/patches, coasts, rivers, canals, locks, aqueducts, facilities,
ships, orders, timetables, and route health. Seven graph-edge types describe
connectivity, facility service, orders, transfers, locks, and aqueduct spans. The
extension is append-only; accepted M15-M17 meanings remain unchanged.

Runtime catalog evidence covers sea, canal, and river water classes plus all 11
base ship engine entries. The connectivity probe compares native water-region
patch traversal with an independent tile flood fill before a cut, after the cut,
and after native reconstruction.

## Native execution boundary

The accepted OpenTTD delta is
[`0001-Add-native-V2-ship-qualification.patch`](../../integration/openttd/patches/15.3/m18/ship/0001-Add-native-V2-ship-qualification.patch),
SHA-256
`1d44884404ac1abf1887ec2fa3e69b85ba8f700ba607370cd75f83c036e97ac4`.
It adds the opt-in `-u <manifest> -w <report>` qualification path without
changing ordinary game startup or the M15-M17 entry points.

Each matrix case resets a deterministic empty 64 by 64 temperate map at 2050.
Water/facility construction, ownership checks, vehicles, refits, orders,
timetables, service intervals, replacement, pathfinding, movement, transfer,
delivery, payment, and save/load use native OpenTTD paths. Source cargo packets
and otherwise unavailable sink acceptance are bounded qualification fixtures.
They prove downstream native movement and accounting, not uncontrolled cargo
generation or learned route discovery.

The lifecycle probe exercises passenger and freight ship selection, refit, order
flags, timetable wait/travel/speed, a 120-tick service interval, native save/load,
clone, actual autoreplace, sale, and lost/crash state projections. The recovery
probe disconnects a live route, observes the lost state, stops safely, reconnects
through a native command, and completes profitable service within the frozen
horizon.

## Qualification matrix

The retained matrix at
`/home/thecl/.codex/artifacts/openttd-rl/v2-m18-ship-matrix-c` contains 16 cases
and 32 fresh-process native executions: two seeds for catalog, construction,
connectivity, lifecycle, natural service, constructed service, transfer, and
recovery. All 16 report pairs have identical normalized hashes.

- Natural sea/river service delivers 100 passengers for 1,763 income or 160 coal
  for 5,263 income.
- Constructed-water service delivers 100 passengers for 1,756 income or 160 coal
  for 5,263 income, with observed lock and aqueduct traversal.
- Road-to-ship transfer moves 20 coal units with zero first-leg cash, retained
  feeder accounting, one final payment, 20 delivered, and 722 final income.
- Recovery delivers 100 passengers for 1,756 income or 160 coal for 5,263 income
  after disconnection, safe stop, and reconstruction.

The maximum native wall time was 0.114685 seconds. Bubblewrap namespaces are not
available on this WSL host, so the evidence truthfully records `rlimit-only`,
process limits, no network calls, and null media drivers.

## ShipAI specialist boundary

M14 retained ShipAI v10 as `QUALIFIED_HEALTHY_INACTIVE` and
`SCENARIO_REQUIRED`; that result is not rewritten. M18 generates a byte-pinned
128 by 128 two-town coastal save and reruns the exact M14 package/executable for
30 game days. ShipAI is `QUALIFIED_ACTIVE`, owns two ships and no other vehicles,
and retains the same two-ship fleet across native save/load.

This is a scenario-specific specialist qualification and a zero-service
comparator for M18. It is not a competitive result or proof of a learned
generalist policy.

## Evidence and accepted identities

- [`m18-ship-source.json`](../../config/v2/m18-ship-source.json), SHA-256
  `d831d5b5f1959cce765a2978f170349f5dcdb51d4d1ebaeee6c3e2ff4cf094f7`.
- [`m18-shipai-evidence.json`](../../config/v2/m18-shipai-evidence.json), SHA-256
  `d9f6df42f6638e2293dfa3abf772068115c357e0fd037cb0ef205997b2783e6f`.
- [`m18-ship-evidence.json`](../../config/v2/m18-ship-evidence.json), SHA-256
  `9963f4bee47c9870cd2725516af6c79eb4de60c8a694b17f55fd46e6f3cb2491`.
- M17 base commit/tree:
  `eb7b769eb9339ecbde7ed69015230079e92d3316` /
  `c9fd523f51bfb68c8da114e64f8183dc48496abb`.
- M18 result commit/tree:
  `70c13453e2c1c6e122df8323938460778e116f79` /
  `cb30c85604f73cd29b5a12b6d50990847fc2f5e8`.
- Native executable: SHA-256
  `a21afaedc696d25a807b10b920ad14b86886a9d8d9870c35c8636d1234d360a9`,
  411,995,424 bytes; exact OpenTTD tree passes 98/98 CTests.

The source validator rehashes and checks the exact four-file patch against the
M17 base. The matrix validator reloads all 32 reports and recomputes their
identities, normalized twins, metrics, catalog, probes, and ShipAI baseline. The
ShipAI validator binds its scenario result back to the M14 package/runtime
indexes and retained qualification manifest.
