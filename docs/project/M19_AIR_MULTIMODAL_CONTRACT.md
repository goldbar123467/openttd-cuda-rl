# M19 aircraft and multimodal contract

## Status

`M19 COMPLETE`; accepted by [`G19_GATE_REPORT.md`](G19_GATE_REPORT.md) on
2026-08-02. The machine authority is
[`m19-air-contract.json`](../../config/v2/m19-air-contract.json), SHA-256
`213a416a7a20270261c10e0327043e65267d7a2fe8976c61320a5b7259dea6ca`.

M19 appends airport construction, aircraft lifecycle and movement, air service,
failure recovery, a conserved three-mode transfer, and a deterministic
mode-specialist router to the accepted M15-M18 contracts. It does not claim
competitive-company evaluation, broad Game Script/NewGRF coverage, release
packaging, or V2 completion.

## Pinned OpenTTD 15.3 boundary

The base catalog contains ten airport specifications. Nine are buildable:
country (4 by 3, 0-1959), city (6 by 6, 1955 onward), heliport (1 by 1,
1963 onward), metropolitan (6 by 6, 1980 onward), international (7 by 7,
1990 onward), commuter (5 by 4, 1983 onward), helidepot (2 by 2, 1976 onward),
intercontinental (9 by 11, 2002 onward), and helistation (4 by 2, 1980 onward).
The tenth is the disabled, non-buildable oil-rig specification. The catalog
oracle also projects catchment, noise, maintenance, layouts, depots, airplane
and helicopter capability, short-strip risk, terminals, helipads, and movement
state-machine size.

Native command test mode is authoritative for availability, footprint, terrain,
town authority, station spread, noise, ownership, joining, cost, removal, and
transaction failure. Vehicle commands remain authoritative for aircraft build,
refit, orders, timetable, service, replacement, hangar routing, start/stop,
clone, save/load, and sale. Aircraft range comes from the cached native engine
property and native order-distance checks.

## Occupancy, failure, and competence

Airport occupancy is not reconstructed from sprites. The oracle reads the
station's native 64-bit `AirportBlocks` plus each primary aircraft's position,
previous position, movement heading/state, target airport, stopped/crashed
status, range, cargo, and orders. It time-steps these fields to expose terminal,
helipad, runway, taxiway, hangar, holding, and queue behavior.

Airplane and helicopter service must each deliver cargo or passengers and earn
positive company income on two deterministic seeds. Congestion and a closed
destination must be observable and recover within a fixed horizon after native
open/close or vehicle-management actions. A bounded fixture may initiate a
seeded crash/disaster case; the resulting native crash state, vehicle loss, and
accounting transitions are the evidence. Fixture use cannot stand in for normal
service competence.

## Multimodal and router boundary

The end-to-end multimodal probe uses road, water, and air legs. Cargo identity
and count are checked at each handoff; feeder legs do not create company cash,
and exactly one final delivery pays for all delivered units. The graph contract
still projects all four base modes—road, rail, water, and air—through stable node
and edge identities.

The deterministic router consumes only the frozen observations and action masks,
selects an explicit mode specialist, and restores byte-identical routing state
after checkpoint. Hidden engine objects, opponent state, future random outcomes,
and fixture-only fields are not router inputs.

## Third-party baseline integrity

M14 byte-pinned Lufthansa v2, content ID `4c554654`, but rejected it at runtime.
Inspection confirms that the archive contains generated markup inside Squirrel
source and a truncated `main.nut`; it cannot compile. M19 retains that rejection
and its exact archive SHA-256
`ac313debff38dc9937439f90068930653fc7ce2c8d6e94ee11dc4c10cb3e3a3b`.
It will not patch, rename, or claim active qualification for that package.

The active generalist baseline is the unmodified, already qualified AAAHogEx
v115 package, content ID `484f4745`, paired with the deterministic native air
oracle. G19 evidence must distinguish generalist activity from actual air-mode
activity. If AAAHogEx does not choose aircraft on the retained scenario, that is
reported as a limitation rather than rewritten as success.

## Frozen matrix

The native matrix contains ten probes—catalog, construction, lifecycle,
occupancy, failure, airplane service, helicopter service, multimodal transfer,
congestion recovery, and router checkpoint—with two seeds and two fresh-process
runs per case: 20 cases and 40 executions. Normalized reports must be
byte-identical within every twin. G19 additionally requires the retained
third-party baseline evidence, all OpenTTD CTests, the full V2 verifier, and all
V1 regressions.

## Accepted results

All 20 cases and 40 native executions pass, and every one of the 20 report pairs
has a byte-identical normalized hash. Airplane service delivers 25 and 15 units
for 466 and 551 income; helicopter service delivers 40 and 28 units for 723 and
996 income. Closed-destination recovery resumes to 25/269 and 15/342
delivery/income results. Both multimodal seeds move all 14 units through road,
water, and air, record exactly two unpaid feeder transfers, and produce one final
payment worth 573.

The catalog observes ten airport specifications, nine buildable facility types,
and 41 aircraft engine entries (38 airplanes and three helicopters). Construction,
lifecycle, occupancy, failure, service, multimodal, recovery, and router probes
all pass. Bubblewrap namespaces are unavailable on the WSL host, so the evidence
records process limits, no network calls, null drivers, and the truthful
`rlimit-only` isolation level.

## Evidence and accepted identities

- [`m19-air-source.json`](../../config/v2/m19-air-source.json), SHA-256
  `eaa34874b10114de13465590d92b531c13287aa9ce662e25cfb9eefebf8fb6ec`.
- [`m19-air-evidence.json`](../../config/v2/m19-air-evidence.json), SHA-256
  `c0fe61de03698fef54682cc2b18107090ac3531f3e4a1a1cf112fd6cf01bb1d0`.
- Accepted patch SHA-256
  `dbbab4f4b999bb2af484890ee1527f145f0d9f84b863ca5755e914618c004f4c`.
- M18 base commit/tree:
  `70c13453e2c1c6e122df8323938460778e116f79` /
  `cb30c85604f73cd29b5a12b6d50990847fc2f5e8`.
- M19 result commit/tree:
  `1b07432dc0a196673a461bb49c7ca59d2175e9bf` /
  `ada560ed740f522bf7327703201e657503b6f9b9`.
- Native executable: SHA-256
  `75d262c0b6ed839c16fe8fb341a0541c86fa746078e8253b4581eef10cff19bd`,
  416,293,112 bytes; the exact source tree passes 98/98 OpenTTD CTests.

The source validator checks the exact four-file patch against the M18 base and
rehashes the retained source tree and executable. The evidence validator reloads
all 40 reports and recomputes their identities, normalized twins, metrics,
catalog, probes, and baseline bindings. Thirteen mutation tests cover source and
evidence drift, and the aggregate verifier retains every G14-G18 and V1 test.
