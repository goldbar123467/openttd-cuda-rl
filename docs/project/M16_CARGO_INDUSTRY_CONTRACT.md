# M16 cargo and industry contract

## Status

`M16 COMPLETE`; accepted by [`G16_GATE_REPORT.md`](G16_GATE_REPORT.md) on
2026-08-02. The machine authority is
[`m16-cargo-contract.json`](../../config/v2/m16-cargo-contract.json), SHA-256
`8d7843995fb02ddc1a9175f3acd2c7d55ccaa523f28fbaa82a6ec2025133a976`.

This milestone appends cargo, industry, transfer, subsidy, cargo-distribution,
and economy semantics to the frozen M15 scalable passenger boundary. It does
not claim rail, ship, aircraft, competition, broad-content, learned-generalist,
or V2-release completion.

## Frozen environment extension

The action extension defines ten typed families: cargo-chain and industry-pair
selection, truck-stop construction, freight-road-vehicle purchase, refit, cargo
route, transfer order, distribution-mode selection, subsidy service, and
industry-service management. Native command test mode remains authoritative for
legality, and failed transactions must roll back or leave state unchanged.

The observation extension adds bounded cargo-spec, industry-spec,
industry-instance, industry-edge, station-cargo, vehicle-cargo, subsidy, and
payment-event tables. Graph edges identify production, acceptance, road
service, shared stations, transfers, and subsidies. These additions are typed
and append-only: they do not reinterpret M15 tensor or candidate bytes.

The runtime inventory covers all 46 cargo occurrences in the four base climate
tables—11 temperate, 11 arctic, 12 tropical, and 12 toyland—representing 31
unique labels. The full engine cargo-class vocabulary has 16 names; the pinned
base cargos actually instantiate ten: passengers, mail, express, armoured,
bulk, piece goods, liquid, refrigerated, potable, and non-potable. Qualification
also inventories 37 climate industry specs and 24 distinct input-to-output
production transitions.

## Native execution boundary

The accepted OpenTTD delta is
[`0001-Add-native-V2-cargo-and-industry-qualification.patch`](../../integration/openttd/patches/15.3/m16/cargo/0001-Add-native-V2-cargo-and-industry-qualification.patch),
SHA-256
`cad6059cf04263d3ab19b8583221a94f65baa25e4dde4ab5bf3aae2fe5c5b44a`.
It adds the opt-in `-N <manifest> -O <report>` qualification path and refactors
normal industry input processing into the shared
`ProcessIndustryInputCargo` core. Telemetry and acceptance overrides are off by
default, so ordinary games do not accumulate qualification state.

Each case resets an empty deterministic 64 by 64 native map at 2050 and builds
real roads, road stops, a depot, and road vehicles. Vehicle construction,
refitting, orders, loading, movement, ageing, transfer, final delivery,
production, subsidy, and payment use native OpenTTD paths. Deterministic source
packets and sink acceptance where a generated map lacks the required producer
or receiver are controlled fixture setup. Evidence therefore proves the
transport and accounting transitions, not an uncontrolled-map discovery claim.

## Qualification matrix

The retained matrix at
`/home/thecl/.codex/artifacts/openttd-rl/v2-m16-cargo-matrix-a` contains 102
cases and 204 native executions:

- 92 single-leg cases: two seeds for every one of the 46 climate cargo
  occurrences; every vehicle delivered eight units and earned positive native
  income;
- eight catalog cases: two seeds in each climate, covering cargo identities,
  industry identities, acceptance, production, closure roundtrip, manual,
  asymmetric and symmetric distribution modes, and normal/recession states;
- two coordinated passenger/mail cases: shared stations delivered eight units
  of each cargo for exactly 338 income;
- two two-vehicle transfer cases: feeder credit 107, zero intermediate company
  income, eight final units and exactly one final payment of 264; and
- two subsidy cases: the same eight-unit coal delivery changed from base 265 to
  exactly 530 under the configured multiplier.

Every paired report has an identical normalized hash. The maximum native wall
time was 0.099464 seconds. Bubblewrap namespace creation was unavailable in the
host WSL environment (`Resource temporarily unavailable`); the accepted matrix
records the truthful `rlimit-only` fallback, process limits, no network calls,
and null media drivers. Failed preflights are retained separately and are not
counted as accepted cases.

## Evidence and verification

- [`m16-cargo-source.json`](../../config/v2/m16-cargo-source.json) freezes base
  and result trees, exact patch, executable, OpenGFX, and build arguments.
- [`m16-cargo-evidence.json`](../../config/v2/m16-cargo-evidence.json), SHA-256
  `f4a8e985b28a6b7e138ad65417e8baa53cd0422898e0cb4ed8a1648ffa9b65c4`,
  freezes every case and both report hashes.
- [`validate_m16_cargo_source.py`](../../scripts/v2/validate_m16_cargo_source.py)
  rejects source, patch, touched-file, build, or executable drift.
- [`validate_m16_cargo_evidence.py`](../../scripts/v2/validate_m16_cargo_evidence.py)
  independently reloads all 204 reports, recomputes normalized hashes and
  projections, and rejects inventory, accounting, or production-edge drift.
- Fourteen unit and mutation tests cover both validators. The exact result tree
  passes all 98 OpenTTD CTests.

## Accepted identities

- M15 base commit/tree:
  `abc1912e290d8f49221fb3f68e30f3bcb3190ec9` /
  `fb9a95a7bb03f279a2965516713afd759010a46b`.
- M16 result commit/tree:
  `ceb913106af64d6a1a9c50afb15bf4437297363b` /
  `71571eeb60eeb0b6267e063dcdaa6ec704590102`.
- Native executable: SHA-256
  `12ed1f2bb66fa5b2358259c5ff06c185e5a3aef2b24082dc7ad51c621d65cb5f`,
  404,236,776 bytes.
