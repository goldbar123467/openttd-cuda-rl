# M17 rail network contract

## Status

`M17 COMPLETE`; accepted by [`G17_GATE_REPORT.md`](G17_GATE_REPORT.md) on
2026-08-02. The machine authority is
[`m17-rail-contract.json`](../../config/v2/m17-rail-contract.json), SHA-256
`08dee4ec893cf2e26199a698f7847835b78571230f731ab9242fa181bf49297f`.

This milestone appends rail construction, signalling, train lifecycle, safety,
and useful passenger/freight rail service to the frozen M16 cargo and M15
scalable boundaries. It does not claim ships, aircraft, multimodal generalist
learning, competitive play, broad-content coverage, or V2 release completion.

## Frozen rail extension

The action extension defines 24 typed families for rail-type selection and
conversion; track, station, depot, waypoint, signal, and reservation operations;
and train purchase, assembly, refit, clone, sale, orders, timetables, service,
autoreplace, and start/stop. Native command test mode remains authoritative for
legality. A failed transaction must roll back or leave native state unchanged.

The observation extension adds bounded rail-type, train-engine, track, junction,
crossing, station, platform, waypoint, depot, signal, reservation, consist,
order, timetable, congestion, and safety tables. Versioned graph edges identify
track connectivity, junction branches, served platforms, order targets, consist
links, reservations, and crossings. These are append-only additions; M15 tensor
and candidate bytes retain their accepted meanings.

Catalog evidence covers four base rail types, 116 train engine entries, all six
track orientations, and all six base signal types in electric and semaphore
forms. Construction evidence executes positive and negative track, junction,
crossing, slope, ownership, station, depot, waypoint, rename, removal, and rail
conversion cases through native commands.

## Native execution boundary

The accepted OpenTTD delta is
[`0001-Add-native-V2-rail-qualification.patch`](../../integration/openttd/patches/15.3/m17/rail/0001-Add-native-V2-rail-qualification.patch),
SHA-256
`f9f073c9771af2e3048050948f25cafdccb74c013f72c7fcb3f899349283cc65`.
It adds the opt-in `-C <manifest> -P <report>` qualification path. Ordinary
games do not enter the probe path.

Each case resets an empty deterministic 64 by 64 temperate map at 2050. Track,
facilities, consists, refits, orders, timetables, service settings, signalling,
pathfinding, movement, delivery, and payment use native OpenTTD paths. The
passenger and freight competence probes create deterministic source packets and
sink acceptance, then load those packets through the native `StationCargoList`
into real consists before vehicle ticks. This controlled setup proves rail
movement, delivery, safety, and accounting; it is not a claim that a learned
policy discovered the route or that cargo generation was uncontrolled.

The lifecycle probe also performs an actual native save, mutates the service
interval from 120 to 180, reloads, and observes restoration to 120 while
preserving orders and their flags. It exercises locomotive/wagon assembly,
refit, all station-order flag categories, timetable wait/travel/speed fields,
clone, autoreplace from engine 0 to engine 8, clearing, and sale. Stuck and
collision observation fixtures include both positive and negative projections
while vehicles remain safely stopped.

## Qualification matrix

The retained matrix at
`/home/thecl/.codex/artifacts/openttd-rl/v2-m17-rail-matrix-a` contains 14 cases
and 28 fresh-process native executions: two seeds for each of catalog,
construction, signals, lifecycle, passenger, freight, and stress. Every paired
report has an identical normalized hash.

- Passenger runs deliver 40 units for 699 income in 1,815 ticks.
- Freight runs deliver 30 coal units for 1,002 income in 1,828 ticks.
- The 32,768-tick stress runs operate two trains on a junction-connected
  physical network with two path signals, three terminal stations, a shared
  destination, and one connector. They deliver 80 units for 1,382 income, with
  maximum observed wait 2,899 and no unresolved deadlock or unexplained
  collision.
- Signal runs cover 12 signal variants, direction states 4, 8, and 12, actual
  removal, and reservation acquire, duplicate rejection, and release.

The maximum native wall time was 0.136081 seconds. Bubblewrap namespaces were
unavailable in the host WSL environment. Accepted evidence therefore records
the truthful `rlimit-only` fallback, process limits, no network calls, and null
media drivers.

## Opponent and competence boundary

The preferred ChooChoo package remains a retained
`catalog-listed-unselectable` rejection; it was not silently treated as a
qualified runtime. G17 instead uses the byte-pinned, tournament-qualified
AAAHogEx rail specialist, whose retained 30-day solo run built one train and
passed save/load health. Passenger and freight qualification use deterministic
useful-service controllers and beat frozen no-build and no-start zero-service
comparators. This is service-oracle evidence, not learned-policy evidence; the
generalist learning requirement remains in M22.

## Evidence and accepted identities

- [`m17-rail-source.json`](../../config/v2/m17-rail-source.json), SHA-256
  `5bea9ea4d38f35ef040c2cad672a7cb90955a899ad61e929891c746d12aacaae`,
  freezes the M16 base, result source, patch, executable, OpenGFX, and build.
- [`m17-rail-evidence.json`](../../config/v2/m17-rail-evidence.json), SHA-256
  `d9955d4598bde37e10ccaccb22add01f66ee8a8c4d369e47794719fceb3e9dc7`,
  freezes all 14 cases, 28 report hashes, normalized twins, and baselines.
- M16 base commit/tree:
  `ceb913106af64d6a1a9c50afb15bf4437297363b` /
  `71571eeb60eeb0b6267e063dcdaa6ec704590102`.
- M17 result commit/tree:
  `eb7b769eb9339ecbde7ed69015230079e92d3316` /
  `c9fd523f51bfb68c8da114e64f8183dc48496abb`.
- Native executable: SHA-256
  `f3a6d9a39cebd171697516b41b5ac5d857e887cfe83e4de0df9f957a0466e9ff`,
  407,996,528 bytes.

The source validator rehashes the base/result trees, four touched files, patch,
executable, and build metadata. The evidence validator reloads all reports and
recomputes every hash, twin, metric, and baseline projection. Fourteen dedicated
unit/mutation tests cover the two validators, and the exact OpenTTD result tree
passes all 98 CTests.
