# M14 opponent package acquisition

## Status

Package acquisition status: `PASS` on 2026-08-02.

Runtime/sandbox qualification status: `PASS`.

Competition-manifest status: `PASS`. See
[`M14_INVENTORY_AND_COMPETITION.md`](M14_INVENTORY_AND_COMPETITION.md).

The package pass means every member of the ten-AI research pool has either a
byte-locked, dependency-complete archive closure or a retained machine-readable
rejection. It does not mean that every locked AI starts, remains healthy, builds a
vehicle, earns money or qualifies for competition.

## Acquisition contract

[`scripts/v2/acquire_ai_package.py`](../../scripts/v2/acquire_ai_package.py)
starts the accepted dedicated executable in a new absolute artifact directory
with isolated HOME/XDG paths and an explicit writable configuration. It then:

1. waits for map-generation readiness before sending console input;
2. updates only the AI catalog and resolves the exact baseline name/unique ID;
3. selects the numeric content ID and captures every automatic dependency;
4. waits for one completion event per selected content ID;
5. rejects missing, extra, conflicting or duplicate identities;
6. rejects absolute, parent-traversal, link, special, duplicate or over-limit tar
   members without extracting them;
7. records every file and license/copying digest, catalog MD5, archive SHA-256,
   embedded `info.nut` metadata and executable/source identity; and
8. revalidates the completed lock against the actual archive bytes.

Catalog names, archive labels and embedded names are retained separately because
real packages sanitize spaces/apostrophes. Catalog release versions and embedded
`GetVersion()` values are also retained separately; NoOpAI proves they need not
match.

## Frozen outcomes

The committed evidence index is
[`config/v2/opponent-package-evidence.json`](../../config/v2/opponent-package-evidence.json).
Its full live validation passes with 10 outcomes, 8 locks, 2 rejections, 18
packages, 4,341,760 archive bytes and 18 license files.

| AI | Outcome | Closure | Artifact directory |
|---|---|---:|---|
| AAAHogEx 115 | `LOCKED` | 1 package | `v2-m14-ai-aaahogex-a` |
| ChooChoo 434 | `REJECTED` | catalog-listed-unselectable | `v2-m14-ai-choochoo-b` |
| KrakenAI2 3 | `LOCKED` | 5 packages | `v2-m14-ai-krakenai2-b` |
| LuDiAI AfterFix 27 | `LOCKED` | 1 package | `v2-m14-ai-ludiai-afterfix-b` |
| Lufthansa 2 | `LOCKED` | 1 package | `v2-m14-ai-lufthansa-a` |
| NoOpAI 4 | `LOCKED` | 1 package | `v2-m14-ai-noopai-b` |
| ShipAI 10 | `LOCKED` | 1 package | `v2-m14-ai-shipai-a` |
| SimpleAI 14 | `REJECTED` | catalog-listed-unselectable | `v2-m14-ai-simpleai-b` |
| Trans AI 200626 | `LOCKED` | 1 package | `v2-m14-ai-trans-ai-c` |
| WmDOT 16 | `LOCKED` | 7 packages | `v2-m14-ai-wmdot-b` |

All artifact directories are below the evidence-base hint
`/home/thecl/.codex/artifacts/openttd-rl`. Failed development attempts are not
accepted evidence and are not referenced by the index.

The live re-audit command is:

```text
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_opponent_package_evidence.py \
  --root . \
  --artifact-base /home/thecl/.codex/artifacts/openttd-rl \
  --openttd /home/thecl/.codex/artifacts/openttd-rl/m12-release-final-a/build/openttd-headless/openttd
```

## Runtime qualification

[`scripts/v2/qualify_ai_runtime.py`](../../scripts/v2/qualify_ai_runtime.py)
copies and revalidates each locked package closure, then runs it with a private
network/PID/user/IPC/UTS namespace, a read-only host root, a single writable
artifact tree and CPU/address-space/file/descriptor/process limits. It records the
embedded AI identity, company start, elapsed game days, save/load survival, owned
vehicle counts, script crashes, peak RSS, transcript and savegame bytes.

The machine matrix is
[`config/v2/opponent-runtime-evidence.json`](../../config/v2/opponent-runtime-evidence.json).
All ten research candidates now have a terminal M14 package/runtime outcome:

| AI | Final M14 classification | Measured reason/activity |
|---|---|---|
| AAAHogEx | `TOURNAMENT` | 30 days, one train, save/load healthy |
| ChooChoo | `EXCLUDED` | package listed but unselectable |
| KrakenAI2 | `TOURNAMENT` | 30 days, 17 road vehicles, save/load healthy |
| LuDiAI AfterFix | `SCENARIO_REQUIRED` | healthy after 30 days, zero vehicles |
| Lufthansa | `EXCLUDED` | published `info.nut` has Squirrel compile errors from literal `[span_*]` markup |
| NoOpAI | `CONTROL` | expected zero activity, start/save/load healthy |
| ShipAI | `SCENARIO_REQUIRED` | healthy after 30 days, zero vehicles on the generic temperate map |
| SimpleAI | `EXCLUDED` | package listed but unselectable |
| Trans AI | `EXCLUDED` | runtime crash: missing `AILib.Common` version 2, absent from its catalog dependency closure |
| WmDOT | `SCENARIO_REQUIRED` | healthy after 30 days, zero vehicles |

`SCENARIO_REQUIRED` is deliberately not tournament admission. Those AIs need a
mode-appropriate scenario gate in their later transport milestone. A package that
merely starts is not presented as an active competitor.

The full live matrix re-audit is:

```text
PYTHONPATH=scripts/v2 python3 scripts/v2/validate_opponent_runtime_evidence.py \
  --root . \
  --artifact-base /home/thecl/.codex/artifacts/openttd-rl \
  --openttd /home/thecl/.codex/artifacts/openttd-rl/m12-release-final-a/build/openttd-headless/openttd
```

## Rejections

ChooChoo and SimpleAI returned exact catalog rows with the expected unique IDs but
remained absent from `content select` after an isolated selection request. No
archive bytes were accepted for either AI. Each rejection pins the engine,
executable, request, reason code and console-transcript digest.

These are audit-pool rejections, not hidden missing tournament runs. A future
package version may be reconsidered only through a new snapshot and new evidence;
the current rejection record must remain intact.

## Verification

The deterministic suite includes 39 package/runtime acquisition and evidence
tests and covers live protocol emulation, transitive dependencies, version/name distinctions,
no-overwrite behavior, timeouts, catalog drift, missing licenses, hostile archive
paths, byte/manifest mutation and missing evidence. The broader V2 suite also
reruns the complete V1 traceability suite.

Admission to runtime qualification requires `LOCKED`. Admission to a final
tournament additionally requires measured activity, the frozen competition
manifest and later mode/scenario gates; none follows from package acquisition
alone.
