# G16 cargo and industry gate report

## Decision

`G16 PASS` on 2026-08-02.

The gate accepts the typed mail/freight/industry extension, all base climate
cargo identities and production edges, real native road-freight delivery,
shared passenger/mail service, exact subsidy behavior, and exploit-free
two-vehicle transfer accounting. It preserves G15 and V1 and makes no claim for
M17–M23.

## Gate evidence

| G16 clause | Result | Evidence |
|---|---|---|
| Mail and shared passenger/mail operation | `PASS` | Two twin-exact coordinated runs, 8 passenger + 8 mail units, exact income 338 |
| Truck stops, freight vehicles, refits, routes and lifecycle | `PASS` | Real native road/station/depot/vehicle/refit/order/movement/delivery path plus retained M15 lifecycle actions |
| Every base cargo identity and instantiated class | `PASS` | 46 climate occurrences, 31 unique labels, 10 instantiated base classes |
| Industry identities, acceptance, production and closure | `PASS` | 37 climate industry specs, 24 distinct shared-core production transitions, pool closure roundtrip |
| Subsidy, distribution and economy state | `PASS` | Exact 265 to 530 subsidy multiplier; manual/asymmetric/symmetric and normal/recession transitions |
| Shared stations and transfers | `PASS` | Feeder credit without intermediate cash; one final 264 payment; no duplicate-payment exploit |
| Four-climate deterministic corpora | `PASS` | Two seeded executions for every climate cargo occurrence plus two catalogs per climate |
| Profitable cargo delivery | `PASS` | All 92 single-leg cases delivered 8 units and positive income; exact twins |
| Native source regression | `PASS` | Accepted executable and result tree; OpenTTD CTest 98/98 |
| Earlier correctness floors | `PASS` | Aggregate V2 suite plus unchanged V1 traceability/document/test suite |
| Invalidating defects | `PASS` | Zero nonclosed entries in [`defects-v2.json`](defects-v2.json) |

The detailed contract, controlled-fixture boundary, matrix composition, source
identities, and isolation disposition are in
[`M16_CARGO_INDUSTRY_CONTRACT.md`](M16_CARGO_INDUSTRY_CONTRACT.md).

## Accepted machine evidence

- Contract: [`m16-cargo-contract.json`](../../config/v2/m16-cargo-contract.json),
  SHA-256 `8d7843995fb02ddc1a9175f3acd2c7d55ccaa523f28fbaa82a6ec2025133a976`.
- Source: [`m16-cargo-source.json`](../../config/v2/m16-cargo-source.json),
  SHA-256 `ec37986e07ae3bcfedd639e67298b50f702b2aa5a3cb38850d0fd2d60f8abc7e`.
- Matrix: [`m16-cargo-evidence.json`](../../config/v2/m16-cargo-evidence.json),
  SHA-256 `f4a8e985b28a6b7e138ad65417e8baa53cd0422898e0cb4ed8a1648ffa9b65c4`.
- Source commit/tree:
  `ceb913106af64d6a1a9c50afb15bf4437297363b` /
  `71571eeb60eeb0b6267e063dcdaa6ec704590102`.
- Executable SHA-256:
  `12ed1f2bb66fa5b2358259c5ff06c185e5a3aef2b24082dc7ad51c621d65cb5f`.

## Acceptance boundary

Source cargo packets and otherwise unavailable sink acceptance are controlled
qualification setup. Roads, stops, depots, vehicles, refits, orders, movement,
loading, ageing, transfer, final delivery, production, subsidy, and payment are
native. The gate consequently accepts exact cargo transport/accounting behavior
and complete pinned base-data coverage; it does not substitute this fixture for
later generalist learning or arbitrary generated-world performance.

Bubblewrap could not create a namespace on this WSL host. Accepted runs use
recorded process resource limits, no network calls, and null drivers; evidence
labels this `rlimit-only` rather than claiming sandbox isolation.

## Verification result

The source/evidence validators rehash the patch, source, executable, contract,
all reports, and all normalized twins. The M16-specific unit suite passes 14/14
and the exact OpenTTD build passes 98/98 CTests. The aggregate command remains:

```text
./scripts/v2/verify.sh
```

## Next authorized work

M17 may now add rail construction, trains, signals, reservations, shared-network
safety, and profitable passenger/freight rail while retaining every G16, G15,
and V1 invariant.
