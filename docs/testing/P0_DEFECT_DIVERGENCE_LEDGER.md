# P0 Defect and Divergence Ledger

The canonical ledger is
`evidence/p0/P0_DEFECT_DIVERGENCE_LEDGER.json`; this file is its human view.
The JSON ledger is append-only: a closed or rejected entry is retained forever,
and its status may not be used to erase the discovery history.

## Entry policy

Every observed implementation defect or oracle divergence receives a stable
`DEF-P0-NNNN` or `DIV-P0-NNNN` identifier. An entry records the discovering test,
all experiment identities, the earliest boundary, exact expected and observed
values, a minimized content-addressed reproducer, impact, diagnosis, owner, fix,
regression test, and closure evidence. Diagnostic discovery dates do not enter
experiment identity.

The only nonterminal statuses are `OPEN`, `DIAGNOSED`, and
`FIXED_PENDING_GATE`. `CLOSED` requires a fix commit, regression test, and
content-addressed closure artifact. `REJECTED_NOT_A_DEFECT` has the same evidence
threshold and must explain the source-backed reason for rejection.

## Current view

| ID | Discovery | Earliest location | Status | Impact |
|---|---|---|---|---|
| `DEF-P0-0001` | `TEST-STATIC-SCAN-BUILD-001` | `parity/src/tape_reader.c:1013` | `DIAGNOSED` | Dead assignment fails the zero-finding static gate and obscures cleanup ownership. |
| `DEF-P0-0002` | `TEST-STATIC-SCAN-BUILD-001` | `parity/tools/tape_main.c:718` | `DIAGNOSED` | Filter parsing does not express a provable nonnull guard for `end_filter`. |

The local-release gate recomputes machine counts and requires zero nonclosed
defects and divergences before a final `PASS`.
