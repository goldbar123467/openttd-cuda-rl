# M14 setting inventory and competition protocol

## Status

- Pinned setting inventory: `PASS` on 2026-08-02
- Competition protocol/schema: `PASS` on 2026-08-02
- G14 aggregate gate: [`PASS`](G14_GATE_REPORT.md)

## Complete setting inventory

[`config/v2/setting-inventory.json`](../../config/v2/setting-inventory.json)
is generated directly from every `*_settings.ini` blob under
`src/table/settings` at the pinned OpenTTD 15.3 commit. It retains each `SD*`
source section, including versioned duplicate definitions, rather than collapsing
rows by display name.

The frozen result contains 20 source files, 435 source definitions, 424 unique
scope/key pairs and 11 retained duplicate variants. The dispositions are:

| Disposition | Definitions | Contract consequence |
|---|---:|---|
| `SCENARIO_PIN` | 198 | Native simulation value must be explicit in applicable scenario/run manifests. |
| `COMPANY_PIN` | 9 | Per-company behavior must be explicit and symmetric where roles are compared. |
| `HARNESS_PIN` | 33 | Network/competition runtime value must be pinned by the harness. |
| `PRESENTATION_ONLY` | 179 | May affect client presentation or artifact format; never enters policy input or simulation claims. |
| `SECRET_FORBIDDEN` | 7 | Credential values are not evidence and must not be committed or passed to the policy. |
| `LEGACY_LOAD_ONLY` | 9 | Retained for old-save compatibility, not treated as a current gameplay control. |

The generator rejects a new, missing or unclassified source file. The validator
checks the schema, source/tree identity, contiguous row IDs and source ordinals,
per-file counts, scopes, flags, dispositions and totals. With `--object-repo`, it
re-extracts every blob from the pinned commit and requires byte-equivalent JSON:

```text
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_setting_inventory.py \
  --root . --object-repo openttd-upstream
```

## Frozen competition protocol

[`config/v2/m14-competition-manifest.json`](../../config/v2/m14-competition-manifest.json)
binds the source tree, accepted executable, research baseline, complete setting
inventory, runtime qualification matrix and every admitted package/runtime
evidence digest.

Its M14 roster is exact: AAAHogEx and KrakenAI2 are tournament opponents, and
NoOpAI is the inactive control. The other seven audit candidates retain their
`SCENARIO_REQUIRED` or `EXCLUDED` outcomes; the manifest validator rejects adding
them without later qualification evidence.

The protocol freezes:

- 8 development, 8 preliminary and 20 final seeds derived by a named SHA-256
  rule, with no overlap;
- four legs per opponent/scenario/seed that independently cross both company
  slots and 0/365-day start delays;
- identical maps, settings and policy bytes within paired comparisons;
- per-run hashes for engine, executable, policy, opponent, map, settings and
  content identities;
- public/own-state policy inputs and explicit denial of opponent AI internals,
  future randomness and final-suite identifiers;
- company-value paired difference as primary score plus survival, profit,
  delivery, vehicle and infrastructure results;
- retained bankruptcy, launch/crash/timeout and infrastructure-failure outcomes,
  with no listwise deletion; and
- a preregistered paired bootstrap, complete-cell publication and a new-manifest
  requirement for any protocol change.

This is the immutable protocol contract, not a claim that M20 tournaments have
already run. M15–M20 must fill scenario, settings, policy and result manifests
that satisfy it.

The validator and mutation suite reject roster drift, floating package evidence,
seed edits, underpowered final seeds, asymmetric slots/delays, missing run
identity, private-state leakage, missing-run deletion and post-result selection:

```text
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_competition_manifest.py --root .
```
