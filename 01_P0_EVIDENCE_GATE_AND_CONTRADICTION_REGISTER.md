# P0 Repository Evidence Gate and Contradiction Register

> **Legacy workstream notice (2026-07-31):** This register applies to the earlier
> P0 freight-oracle patch program. Its evidence discipline is reusable, but its
> scope cannot satisfy or redefine the active bus-platform requirements in
> `GOAL.md`.

## Purpose

This gate converts the uploaded architectural contract into verified facts about the current local checkout. The gate is read-only except for a caller-controlled artifact directory outside the repository, a disposable OpenTTD worktree, and a narrowly reviewed correction to the human traceability view when the validated machine registry proves a table-shape defect. No production C++, patch file, schema, registry, fixture, or machine status may be edited until every mandatory row below passes.

A missing file, mismatched hash, moved pin, dirty submodule, wrong assigned branch, malformed existing patch prefix, conflicting future patch reservation, ambiguous command operand, unassigned authoritative field, or unregistered reached source is a hard stop. Codex must report the contradiction instead of selecting a convenient interpretation.

## Gate Result Vocabulary

- `PASS`: observed value agrees with the binding authority and raw output is retained.
- `FAIL`: observed value contradicts the binding authority.
- `BLOCKED`: a required local artifact or prerequisite is unavailable.
- `NOT_RUN`: the row has not executed; never permits implementation.

The overall evidence gate is `PASS` only when every mandatory row is `PASS`.

## E0 — Create an External Evidence Root for a Read-Only Repository Audit

Use a new absolute caller-controlled path outside the repository and every repository ancestor. The path and every existing parent component must be a real directory, not a symlink. Do not use `/`, the workspace root, the repository root, the submodule, an ancestor of the repository, or a path inside the repository. The evidence root is write-only audit output; all repository inspection performed before an expressly authorized focused correction remains read-only.

```bash
set -euo pipefail
umask 077

REPO_ROOT="$(git rev-parse --show-toplevel)"
REQUESTED_ARTIFACT_ROOT="${P0_ARTIFACT_ROOT:?set P0_ARTIFACT_ROOT to a new absolute path}"

case "$REQUESTED_ARTIFACT_ROOT" in
  /*) ;;
  *) printf '%s\n' 'P0_ARTIFACT_ROOT must be absolute' >&2; exit 2 ;;
esac

ARTIFACT_ROOT="$(
python3 - "$REPO_ROOT" "$REQUESTED_ARTIFACT_ROOT" <<'PY'
import os
import stat
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve(strict=True)
target = Path(sys.argv[2])
if target == Path('/'):
    raise SystemExit('artifact root cannot be /')
if '..' in target.parts:
    raise SystemExit('artifact root must not contain .. components')
if target.exists() or target.is_symlink():
    raise SystemExit('artifact root must not pre-exist')
if target.name in {'', '.', '..'}:
    raise SystemExit('artifact root must have a normal final path component')

parent = target.parent
if not parent.is_dir():
    raise SystemExit('artifact-root parent must already exist as a directory')
cur = Path(parent.anchor)
for part in parent.parts[1:]:
    cur /= part
    mode = os.lstat(cur).st_mode
    if stat.S_ISLNK(mode):
        raise SystemExit(f'symlink component is forbidden: {cur}')
    if not stat.S_ISDIR(mode):
        raise SystemExit(f'non-directory path component: {cur}')

parent_real = parent.resolve(strict=True)
target_real = (parent_real / target.name).resolve(strict=False)

def contains(a: Path, b: Path) -> bool:
    try:
        b.relative_to(a)
        return True
    except ValueError:
        return False

if contains(repo, target_real) or contains(target_real, repo):
    raise SystemExit('artifact root may be neither inside nor an ancestor of the repository')
print(target_real)
PY
)"

mkdir -- "$ARTIFACT_ROOT"
EVIDENCE_ROOT="$ARTIFACT_ROOT/p0-patches-0003-0007-evidence-gate"
mkdir -- "$EVIDENCE_ROOT"

python3 - "$REPO_ROOT" "$ARTIFACT_ROOT" "$EVIDENCE_ROOT" <<'PY'
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve(strict=True)
artifact = Path(sys.argv[2]).resolve(strict=True)
evidence = Path(sys.argv[3]).resolve(strict=True)
artifact_stat = artifact.stat()
evidence_stat = evidence.stat()
repo_stat = repo.stat()

payload = {
    'schema_version': 1,
    'purpose': 'p0-patches-0003-0007-evidence-gate',
    'invocation_nonce': secrets.token_hex(16),
    'repository_root': str(repo),
    'repository_device': repo_stat.st_dev,
    'repository_inode': repo_stat.st_ino,
    'repository_head': subprocess.check_output(
        ['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True
    ).strip(),
    'repository_branch': subprocess.check_output(
        ['git', '-C', str(repo), 'branch', '--show-current'], text=True
    ).strip(),
    'artifact_root': str(artifact),
    'artifact_root_device': artifact_stat.st_dev,
    'artifact_root_inode': artifact_stat.st_ino,
    'evidence_root': str(evidence),
    'evidence_root_device': evidence_stat.st_dev,
    'evidence_root_inode': evidence_stat.st_ino,
}

marker = evidence / '.p0-evidence-root.json'
fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    data = (json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError('short marker write')
        view = view[written:]
    os.fsync(fd)
finally:
    os.close(fd)

for directory in (evidence, artifact):
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0)
    dfd = os.open(directory, flags)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)

print(marker)
PY

export REPO_ROOT ARTIFACT_ROOT EVIDENCE_ROOT
{
  printf 'repo_root=%s\n' "$(realpath -e -- "$REPO_ROOT")"
  printf 'artifact_root=%s\n' "$(realpath -e -- "$ARTIFACT_ROOT")"
  printf 'evidence_root=%s\n' "$(realpath -e -- "$EVIDENCE_ROOT")"
  stat -Lc 'artifact_root_device=%d artifact_root_inode=%i mode=%a' -- "$ARTIFACT_ROOT"
  stat -Lc 'evidence_root_device=%d evidence_root_inode=%i mode=%a' -- "$EVIDENCE_ROOT"
  sha256sum -- "$EVIDENCE_ROOT/.p0-evidence-root.json"
} > "$EVIDENCE_ROOT/evidence-root-identity.txt"

python3 - "$EVIDENCE_ROOT/evidence-root-identity.txt" "$EVIDENCE_ROOT" <<'PY'
import os
import sys
from pathlib import Path

identity = Path(sys.argv[1]).resolve(strict=True)
evidence = Path(sys.argv[2]).resolve(strict=True)
with identity.open('rb') as stream:
    os.fsync(stream.fileno())
flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0)
dfd = os.open(evidence, flags)
try:
    os.fsync(dfd)
finally:
    os.close(dfd)
PY
```

Record the resolved paths, device and inode identities, repository HEAD and branch, invocation nonce, marker digest, and directory modes before any other stage. Cleanup may remove only the exact artifact/evidence directories named by the current invocation marker after revalidating the marker, nonce, path, device, inode, and repository identity. Cleanup must refuse a mismatch. Failure artifacts and `.partial` tapes are never automatically removed.

**Pass criterion:** the artifact root is new, absolute, symlink-free, outside and not an ancestor of the repository/submodule, has mode constrained by `umask 077`, has an exclusive fsync-persisted identity marker whose values match live `stat` and Git observations, and contains only the marker, identity record, and newly created evidence-gate content.

## E1 — Snapshot Repository Identity and Dirty State

Run from the repository root and retain all output verbatim.

```bash
set -euo pipefail
cd -- "$(git rev-parse --show-toplevel)"

{
  printf 'repo_root=%s\n' "$(pwd -P)"
  printf 'head=%s\n' "$(git rev-parse HEAD)"
  printf 'branch=%s\n' "$(git branch --show-current)"
  printf 'upstream=%s\n' "$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
  printf 'merge_base_main=%s\n' "$(git merge-base HEAD main 2>/dev/null || true)"
  git remote -v
  printf '%s\n' '--- status porcelain v2 ---'
  git status --porcelain=v2 --branch --untracked-files=all
  printf '%s\n' '--- submodule cached ---'
  git submodule status --cached -- openttd-upstream
  printf '%s\n' '--- submodule worktree ---'
  git -C openttd-upstream status --porcelain=v2 --branch --untracked-files=all
} > "$EVIDENCE_ROOT/repository-state.txt"
```

Required observations:

1. The submodule path is exactly `openttd-upstream`.
2. `git -C openttd-upstream rev-parse HEAD` equals `29f808ef0022064e6d9a83c8476d1e0f4686af86`.
3. `git -C openttd-upstream status --porcelain=v2 --untracked-files=all` is empty apart from branch metadata.
4. The outer dirty state is captured exactly. The task context permits intentional uncommitted outer changes for review; do not clean, reset, stash, amend, or discard them.
5. No unrelated file may be modified by this task.

```bash
test "$(git -C openttd-upstream rev-parse HEAD)" = \
  '29f808ef0022064e6d9a83c8476d1e0f4686af86'
test -z "$(git -C openttd-upstream status --porcelain=v1 --untracked-files=all)"
```

**Hard stop:** any moved or dirty submodule.

## E2 — Resolve the Working-Branch Contradiction

The explicit task assignment names `fix/p0-build-portability`. ADR 0002 records the older P0 branch name `port/p0-oracle-contract`. The assigned branch controls this implementation task; the ADR name remains a separate release-policy discrepancy.

Binding resolution:

1. Record `git branch --show-current` and require the exact value `fix/p0-build-portability`.
2. Do not switch, create, rename, merge, rebase, reset, force-push, or rewrite any branch.
3. If the current branch differs, stop and report `STOP_WRONG_WORKING_BRANCH`; do not repair the branch automatically.
4. Record whether `fix/p0-build-portability` descends from the registered P0 basis and whether an upstream is configured, but do not treat missing push state as a patch-implementation failure.
5. Preserve the ADR discrepancy as an explicit release blocker. Before final P0 `PASS`, a reviewed ADR or branch-policy update must identify the canonical release branch and prove the final clean pushed tip.

Required artifact: `branch-resolution.md`, containing current branch, HEAD, upstream, merge base, relevant authority paths, and exactly one result: `ACCEPT_FIX_P0_BUILD_PORTABILITY_FOR_TASK` or `STOP_WRONG_WORKING_BRANCH`.

## E3 — Verify Required Authority Files and Registered Hashes

The following current-checkout files must exist and be read completely before code:

```text
oracle/instrumentation/README.md
oracle/instrumentation/patches/series
oracle/instrumentation/patches/0001-trace-sink-and-codec.patch
oracle/instrumentation/patches/0002-build-and-run-identity.patch
OPENTTD_P0_ORACLE_CONTRACT_AGENT_PROMPT.md
NEXT_STAGES_IMPLEMENTATION_HANDOFF.md
docs/P0_SCOPE.md
docs/testing/P0_REQUIREMENTS_TRACEABILITY.md
docs/testing/P0_TEST_STRATEGY.md
docs/testing/PORT005_FIELD_COMPLETENESS.md
docs/sources/P0_SOURCE_REGISTER.md
parity/schema/fields-v1.json
parity/schema/projection-plan-v1.json
parity/schema/commands-v1.json
parity/schema/command-set.schema.json
scripts/dev/command_input_v1.py
oracle/tests/port003/test_command_input_v1.py
evidence/p0/P0_REQUIREMENTS_TRACEABILITY.json
evidence/p0/P0_DEFECT_DIVERGENCE_LEDGER.json
```

Run:

```bash
set -euo pipefail
while IFS= read -r path; do
  test -f "$path" || { printf 'missing=%s\n' "$path" >&2; exit 3; }
done <<'PATHS'
oracle/instrumentation/README.md
oracle/instrumentation/patches/series
oracle/instrumentation/patches/0001-trace-sink-and-codec.patch
oracle/instrumentation/patches/0002-build-and-run-identity.patch
OPENTTD_P0_ORACLE_CONTRACT_AGENT_PROMPT.md
NEXT_STAGES_IMPLEMENTATION_HANDOFF.md
docs/P0_SCOPE.md
docs/testing/P0_REQUIREMENTS_TRACEABILITY.md
docs/testing/P0_TEST_STRATEGY.md
docs/testing/PORT005_FIELD_COMPLETENESS.md
docs/sources/P0_SOURCE_REGISTER.md
parity/schema/fields-v1.json
parity/schema/projection-plan-v1.json
parity/schema/commands-v1.json
parity/schema/command-set.schema.json
scripts/dev/command_input_v1.py
oracle/tests/port003/test_command_input_v1.py
evidence/p0/P0_REQUIREMENTS_TRACEABILITY.json
evidence/p0/P0_DEFECT_DIVERGENCE_LEDGER.json
PATHS

sha256sum \
  oracle/instrumentation/README.md \
  oracle/instrumentation/patches/series \
  oracle/instrumentation/patches/0001-trace-sink-and-codec.patch \
  oracle/instrumentation/patches/0002-build-and-run-identity.patch \
  OPENTTD_P0_ORACLE_CONTRACT_AGENT_PROMPT.md \
  NEXT_STAGES_IMPLEMENTATION_HANDOFF.md \
  docs/P0_SCOPE.md \
  docs/testing/P0_REQUIREMENTS_TRACEABILITY.md \
  docs/testing/P0_TEST_STRATEGY.md \
  docs/testing/PORT005_FIELD_COMPLETENESS.md \
  docs/sources/P0_SOURCE_REGISTER.md \
  parity/schema/fields-v1.json \
  parity/schema/projection-plan-v1.json \
  parity/schema/commands-v1.json \
  parity/schema/command-set.schema.json \
  scripts/dev/command_input_v1.py \
  oracle/tests/port003/test_command_input_v1.py \
  evidence/p0/P0_REQUIREMENTS_TRACEABILITY.json \
  evidence/p0/P0_DEFECT_DIVERGENCE_LEDGER.json \
  > "$EVIDENCE_ROOT/authority-files.sha256"
```

Verify registered SHA-256 values for `OPENTTD_P0_ORACLE_CONTRACT_AGENT_PROMPT.md` and `NEXT_STAGES_IMPLEMENTATION_HANDOFF.md` against `P0_SOURCE_REGISTER.md`. Resolve the canonical current-checkout paths for accepted ADRs 0001–0006 from the repository ADR index or registered authority references, require exactly one regular file for each ADR, hash all six, and append those hashes to `authority-files.sha256`. The ADR 0003 hash and exact contradictory passages must be retained in `fixture-status-reconciliation.md`. A missing path, duplicate ADR identity, or hash mismatch is a hard stop until the register and governing document are deliberately reconciled.

## E4 — Verify the Existing Prefix and Freeze New Patch Filenames

The task context states that patches 0001 and 0002 exist and patches 0003–0007 do not yet exist. The pre-code gate must therefore validate the existing two-patch prefix, not demand five nonexistent patch files.

The exact new filenames assigned by this handoff are:

```text
0003-native-command-input-and-boundary-records.patch
0004-global-state-and-map-projection.patch
0005-pool-and-entity-projection.patch
0006-optional-route-controller-cargo-diagnostics.patch
0007-test-consistency-and-nonperturbation-hooks.patch
```

Pre-code requirements:

1. The first two effective `series` entries are exactly:
   - `0001-trace-sink-and-codec.patch`
   - `0002-build-and-run-identity.patch`
2. No effective entry follows 0002 before implementation begins.
3. None of the five assigned new patch files exists before implementation begins.
4. No README, manifest, machine registry, or untracked file reserves a conflicting 0003–0007 filename. A conflicting reservation is a hard contradiction; do not silently rename either side.
5. Patches 0001 and 0002 exist as regular files outside the submodule, apply in order to a disposable worktree at the exact pin, and reverse in exact reverse order to a clean pin.
6. The permanent submodule remains untouched throughout.

Required pre-code validation:

```bash
python3 - <<'PY'
from pathlib import Path

series = Path('oracle/instrumentation/patches/series')
entries = []
for raw in series.read_text(encoding='utf-8').splitlines():
    line = raw.strip()
    if line and not line.startswith('#'):
        entries.append(line)

expected = [
    '0001-trace-sink-and-codec.patch',
    '0002-build-and-run-identity.patch',
]
if entries != expected:
    raise SystemExit(f'pre-code series must equal {expected!r}; observed {entries!r}')
for entry in expected:
    path = series.parent / entry
    if not path.is_file():
        raise SystemExit(f'missing existing patch: {path}')

future = [
    '0003-native-command-input-and-boundary-records.patch',
    '0004-global-state-and-map-projection.patch',
    '0005-pool-and-entity-projection.patch',
    '0006-optional-route-controller-cargo-diagnostics.patch',
    '0007-test-consistency-and-nonperturbation-hooks.patch',
]
for entry in future:
    path = series.parent / entry
    if path.exists() or path.is_symlink():
        raise SystemExit(f'future patch unexpectedly exists before implementation: {path}')
print('\n'.join(entries))
PY
```

Implementation rule: create and append one assigned patch at a time. After patch N passes its prefix apply/build/test/reverse gate, `series` must contain exactly 0001 through N in order. Do not append a later filename before its patch exists and passes focused review.

Completion rule: after 0007, `series` contains exactly all seven assigned filenames in order; every referenced file exists; the full series applies and reverses cleanly.

Use the repository's committed disposable-worktree runner when present. Retain apply/reverse logs plus pre/post permanent-submodule identity.

**Hard stop:** the pre-code prefix differs, a future patch already exists unexpectedly, a conflicting future name is reserved, 0001/0002 fail apply or reverse, or the permanent submodule changes.

## E5 — Verify Baseline 0001/0002 Build and Tests

Before 0003:

1. Apply only 0001 and 0002 to a fresh disposable worktree.
2. Configure with the exact frozen profile plus only the already-approved trace option state.
3. Build the relevant OpenTTD target.
4. Execute the focused trace sink, codec, build identity, and run identity tests documented in `oracle/instrumentation/README.md`.
5. Execute the exact upstream 99-test inventory where the repository contract assigns that requirement to this stage.
6. Verify runtime trace support disabled produces no trace payload and no new gameplay behavior.
7. Reverse both patches and verify exact clean pin.

Do not continue when the baseline is only known from an earlier log. Current branch content and current patch bytes must be tested.

Required artifact: `baseline-0001-0002-result.json` plus raw configure, build, test, apply, and reverse logs.

## E6 — Verify the Six Native Command Families

The fixture contains ten command instances but exactly six native command families. This is not a contradiction.

The pinned `Commands : uint8_t` enum and command declarations establish the following expected native identities:

| Native command | Pinned numeric value | Native procedure | Pinned declaration |
|---|---:|---|---|
| `Commands::BuildRoadStop` | `22` | `CmdBuildRoadStop` | `src/station_cmd.h` |
| `Commands::BuildRoadLong` | `24` | `CmdBuildLongRoad` | `src/road_cmd.h` |
| `Commands::BuildRoadDepot` | `27` | `CmdBuildRoadDepot` | `src/road_cmd.h` |
| `Commands::BuildVehicle` | `34` | `CmdBuildVehicle` | `src/vehicle_cmd.h` |
| `Commands::InsertOrder` | `46` | `CmdInsertOrder` | `src/order_cmd.h` |
| `Commands::StartStopVehicle` | `121` | `CmdStartStopVehicle` | `src/vehicle_cmd.h` |

Codex must compare `commands-v1.json` to this set and produce an exact operand/result mapping. The registry may use project-specific action IDs or names; those external identifiers must be copied exactly from the registry. They may not be replaced with the native enum value.

Control-plane operations are not additional native command families:

- company context is set explicitly before posting a command;
- public-step scheduling and fixed tick advancement are replay-driver control;
- checkpoint and terminal records are trace lifecycle events;
- the vehicle ID is copied from the native `BuildVehicle` execute tuple; each road-stop station ID is copied from the final execute-path `Station *st` through the guarded trace context; both become references for later actions without pool scanning.

**Hard stop:** the registry contains a seventh gameplay action, omits one of the six required families, maps a family to a different native command, or leaves an operand/result ambiguous.

## E7 — Verify Native Test/Execute Semantics

Pinned source requires top-level posting through `Command<Commands::X>::Post`. `CommandHelper::Execute` performs one native test call without `DoCommandFlag::Execute`, exits on a rejected test, and otherwise performs one native execute call with `DoCommandFlag::Execute` before `InternalExecuteProcessResult`.

Required source audit:

- `src/command_func.h`: `CommandHelper`, `Post`, `InternalPost`, `Execute`, test call, execute call, and result processing;
- `src/command.cpp`: money, company, test/execute consistency, and final result paths;
- `src/network/network_command.cpp`: generated typed dispatch, company context, sanitization, and `PostFromNet` precedent;
- every command declaration and `DEF_CMD_TRAIT` row for the six native families.

The implementation may add observational hooks around already-produced test and execute results. Because `CmdBuildRoadStop` returns only `CommandCost`, the audit must also identify the minimal execute-only hook that copies final `st->index` into the active top-level external-command context without changing the native signature or network wire. The implementation may not call `CommandTraits<Tcmd>::proc`, `Command<...>::Do`, or a command procedure a second time to manufacture a trace result.

Required artifact: `native-command-path-audit.md` with exact current line numbers, literal symbols, command signatures, trait flags, result tuple types, and approved hook points.

## E8 — Verify Registry Counts and Field Assignment

Use the current validators and generated registry APIs. Required facts:

- total registered entries: exactly `816`;
- `authoritative_full` entries: exactly `757`;
- every authoritative field assigned to exactly one of patch 0004 or patch 0005;
- no diagnostic field assigned to an authoritative projection;
- no reached future-influencing cache classified `derived_rebuild` in registry v1;
- every source file has a current source-register entry;
- every field has exact type, width, source symbol/accessor, owner, lifecycle, presence/absence rule, count source, ordering rule, null sentinel, and test mapping;
- no duplicate field ID, duplicate path, cyclic count dependency, missing offset terminal, or unresolved source anchor.

Do not infer the JSON object shape. Read `field-registry.schema.json`, `projection-plan` schema, and the committed validators before writing any audit script.

Required artifacts:

- `field-registry-summary.json` produced by current validated tooling;
- the existing canonical field mapping, or `docs/implementation/P0_FIELD_PROJECTION_MAPPING.md` when no canonical path exists, containing exactly 757 data rows;
- the existing canonical machine mapping, or `evidence/p0/P0_FIELD_PROJECTION_MAPPING.json` when no canonical path exists, containing the identical 757 rows;
- `evidence/p0/P0_FIELD_PROJECTION_COMPLETENESS_PROOF.json` proving set equality and disjointness;
- source-anchor validation report;
- omission/mutation coverage report identifying the test that detects removal or mutation of every field row.

**Hard stop:** count differs, any authoritative field lacks a patch owner, any row relies only on a line-number diagnostic, or a field source cannot be verified at the pin.

## E9 — Verify Projection and Tape Contract Compatibility

The current projection adapter design must agree with tape v1:

1. complete boundaries emit every `authoritative_full` field once;
2. fields are strictly increasing by stable field ID;
3. types, widths, counts, bitset shapes, stable-ID widths, and padding match the generated C registry;
4. map fields are ten raw native planes in `TileIndex` order;
5. rejected command grammar is intent → failed test → projection, with no execute;
6. accepted command grammar is intent → successful test → successful execute → projection;
7. replay start precedes the initial complete projection;
8. every completed native tick has a post-tick projection;
9. checkpoint IDs are exactly 1 through 8 with their accepted meanings, are evaluated after a complete projection, and never trigger a duplicate projection;
10. partial journals are finalized only by the C17 finalizer;
11. optional diagnostic records are declared and ignored only after structural and integrity validation;
12. trace write failure leaves a partial artifact, produces explicit failure, and never exposes a false final tape.

Required artifact: `projection-tape-compatibility-audit.md` mapped to the current schema symbols and record IDs.

## E10 — Verify Current Test Entry Points

Read the current runner scripts and documentation. Record exact argument arrays; do not invent a missing wrapper.

At minimum, establish the current commands for:

- command codec unit and hostile-input tests;
- patch apply/reverse tests;
- patched OpenTTD configure/build;
- six-family, ten-command native golden replay;
- rejected-command corpus;
- 757-field completeness at replay-start, post-command, and post-tick boundaries;
- diagnostics off/on equality;
- plain, patched-OFF, patched-ON/runtime-disabled, and patched-ON/enabled comparison;
- two golden, twenty serial, and eight isolated parallel recordings;
- two-load and 10,000-tick continuation;
- randomized 10,000-prefix differential campaign;
- invariant and fault-injection tests;
- sanitizer, static analysis, coverage, fuzz, and mutation gates;
- final top-level gate.

The full documented release command is:

```bash
./oracle/runner/p0_gate.sh --profile local-release \
  --artifact-root /absolute/caller/controlled/path \
  --tools-python /absolute/hash/locked/python
```

A shorter invocation without the required artifact root and hash-locked interpreter does not satisfy ADR 0006 release closure.

Required artifacts:

- `verified-test-command-inventory.md`, where every command is copied from current scripts/docs and every expected artifact and pass criterion is stated;
- `verified-test-command-inventory.json`, validated by a strict local schema and containing one object per stable test ID with an exact `argv` array, working directory, allowlisted environment, timeout, expected exit code, required outputs, and pass predicate.

Every `cmd[TEST-ID]` reference in the implementation specification resolves to the corresponding exact `argv` array in this JSON artifact. A missing, empty, shell-form, ambiguous, or multiply defined command entry fails E10. No production edit may begin while any referenced command lacks one verified argv array.

## E11 — Verify Source Register Closure

For every file or helper reached while mapping commands and fields:

1. confirm an existing `OTTD-*` or `OTTD-R-*` entry at the exact pin;
2. confirm the entry names the relevant symbols/lines, governed fields/tests, and owning patch;
3. append a new reached-source entry before encoding behavior when coverage is absent;
4. never use a current-branch OpenTTD URL in place of the exact commit;
5. never use a research note as sole behavioral proof.

Required artifact: `source-register-delta.md`. A zero-delta result must still list every audited source and its existing register ID.

## E12 — Current Defect and Divergence State

Read the machine ledger, validate it, and reconcile it to the human view. At the uploaded state, `DEF-P0-0001` and `DEF-P0-0002` are `DIAGNOSED` and therefore block final release.

Rules:

- never delete or rewrite a ledger entry;
- never convert a defect to `CLOSED` without fix commit, regression test, content-addressed closure artifact, and full owning gate;
- never mark a mapped requirement `PASS` while its nonclosed defect remains unless the contract contains an explicit reviewed exception;
- patch-series completion may be reported independently from full P0 completion, but the open release blockers must remain visible.

Required artifact: `ledger-state-before-implementation.json` plus the validator output.


## E13 — Validate Human and Machine Traceability Shape

The uploaded human review view contains 56 requirement IDs. Four safety rows—`SAFE-SOURCE-PIN-001`, `SAFE-CREDENTIALS-001`, `SAFE-PUBLICATION-001`, and `SAFE-SCOPE-001`—contain seven table cells rather than the declared eight because the explicit `Status` cell is absent. The current checkout may already correct this defect; Codex must verify rather than assume.

Required procedure:

1. validate `evidence/p0/P0_REQUIREMENTS_TRACEABILITY.json` against its committed schema and semantic linter;
2. enumerate all machine requirement IDs and require exact set equality with the human Markdown view;
3. require exactly 56 unique IDs unless a reviewed authority change deliberately changes the frozen graph;
4. require every human data row to contain the declared columns `Requirement`, `Contract`, `Implementation`, `Test`, `Evidence`, `Gate`, `Status`, and `Reviewer note`;
5. derive no missing status from neighboring rows or prose;
6. when the current human file remains malformed, copy only the explicit machine-authority status into the missing human Status cell, preserve the reviewer note unchanged, record the exact diff, and make no status transition;
7. rerun `./scripts/ci/p0_traceability.sh --tools-python /absolute/path/to/python` after correction.

Required artifact: `traceability-shape-audit.json`, containing machine count, human count, both sorted ID sets, per-row cell counts, machine statuses, human statuses, and exact differences.

**Hard stop:** any ID-set difference, duplicate ID, schema failure, unresolved missing status, or human/machine disagreement after the focused correction. The formatting defect does not authorize guessing and does not alter patch architecture.

## Contradiction Register and Binding Resolutions

| ID | Apparent contradiction or gap | Binding resolution | Stop condition |
|---|---|---|---|
| `CR-001` | Task assignment names `fix/p0-build-portability`; ADR 0002 names `port/p0-oracle-contract` | Require the exact assigned branch for this task without switching; preserve the ADR name as a final-release policy blocker | Current branch is not `fix/p0-build-portability` |
| `CR-002` | Requested six-action table; fixture has ten replay commands | Six means action families; ten means instances: three roads, one depot, two stops, one vehicle, two orders, one start | Registry action set differs from the six pinned families |
| `CR-003` | Static field review is complete; runtime projection is still `IN_PROGRESS` | Static closure authorizes implementation, not a `PASS`; runtime every-boundary and continuation evidence remains mandatory | Any document or report treats static review as runtime proof |
| `CR-004` | Task says patches 0001/0002 exist and were tested; uploads do not contain patch bytes or current logs | Re-run apply/build/test/reverse against current patch bytes and current pin | Current patch bytes or tests are unavailable or fail |
| `CR-004A` | Task says patch files 0003–0007 do not exist, while a seven-patch end state is required | Pre-code `series` must contain only 0001/0002; create the five assigned filenames sequentially and append each only after its prefix gate passes | A conflicting future patch/file/series entry already exists or an assigned filename conflicts with repository authority |
| `CR-005` | Scope document shows a short top-level command; ADR 0006 requires artifact root and tools Python | Full ADR 0006 invocation governs release closure | Runner silently defaults either required path |
| `CR-006` | Scope mentions derived-cache classification; registry ADR says no reached cache is `derived_rebuild` | Classification vocabulary exists, but v1 keeps reached continuation caches authoritative unless the ten-step protocol passes | Implementation omits a reached cache as reconstructible without approved evidence |
| `CR-007` | General prose mentions test, execute, result records for commands | Tape v1 grammar governs: rejected test has no execute; accepted test has exactly one execute | Rejected command executes or accepted command lacks a captured execute result |
| `CR-008` | User-facing map semantics could be easier to project than raw storage | Ten raw map planes are authoritative; semantic interpretations cannot replace or normalize them | Projection emits semantic replacements instead of exact planes |
| `CR-009` | Manual cargo distribution could appear to make LinkGraph unreachable | Pinned source review proves native graph construction and possible jobs remain reachable; include immutable authoritative graph/job state and preserve threads | LinkGraph state is omitted, joined, forced synchronous, or sampled racefully |
| `CR-010` | Patch 0006 owns optional diagnostics while replay milestones are a requested outcome | Required checkpoint framing is established by tape codec; state predicates become possible after 0004/0005; 0006 adds only optional diagnostics; 0007 owns comparison campaigns | Checkpoints are treated as optional diagnostics or omitted when diagnostics are off |
| `CR-011` | Outer changes are intentionally uncommitted; final P0 requires a clean pushed branch | Dirty outer state is permitted during review; no completion claim until reviewed changes are committed, pushed, and final clean proof passes | Codex cleans/discards user work or claims release from a dirty/unpushed tree |
| `CR-012` | Existing static C defects are outside patches 0003–0007 but block P0 | Preserve as explicit release blockers unless separately assigned; do not hide them in patch work | Final result omits or closes them without required evidence |
| `CR-013` | Four safety rows in the uploaded human traceability table omit the explicit Status cell | Machine JSON and schema are authoritative; verify all 56 IDs, record the defect, and correct the human view before status transition or release | Any status is inferred, any ID differs, or final traceability remains malformed |
| `CR-014` | ADR 0003 declares PORT002A accepted/frozen and assigns funding and actual-cost evidence to PORT002B, while stale text says missing funding evidence prevents PORT002A from passing | Preserve the frozen PORT002A fixture, command input, identities, and accepted artifacts; treat PORT002B and overall PORT002 as open; create `fixture-status-reconciliation.md`; require a reviewed ADR correction before final P0 `PASS` | Codex changes frozen fixture facts to reconcile prose, claims overall PORT002 complete, or closes final P0 without the reviewed ADR correction |

## Mandatory Pre-Code Outputs

Codex must create or update repository-local review documents only after checking for existing canonical paths. Do not create parallel documents when an existing canonical file serves the role.

Required logical outputs:

1. `repository-state-and-authority-audit`.
2. `branch-resolution`.
3. `patch-series-apply-reverse-audit`.
4. `baseline-0001-0002-build-test-audit`.
5. `six-action-native-dispatch-ledger`.
6. `757-field-patch-assignment-ledger`.
7. `source-register-closure-audit`.
8. `projection-tape-compatibility-audit`.
9. `verified-test-command-inventory`.
10. `file-by-file-change-plan`.
11. `ledger-state-before-implementation`.
12. `traceability-shape-audit`.
13. `fixture-status-reconciliation`.

Each output must cite repository-relative paths and exact current lines or literal C++ symbols. Each machine-readable result must validate against an existing schema or a newly reviewed strict schema before being treated as evidence.

## Evidence Gate Completion Condition

The gate passes only when:

- E0 through E13 are all `PASS`, and any confirmed human-view cell-shape correction is limited to restoring the machine-authority status without changing that status;
- every raw command and output is retained below the external evidence root;
- the submodule remains clean at the exact pin;
- no outer user change is discarded or rewritten;
- the existing two-patch prefix is exact and the five handoff-assigned future filenames have no repository conflict;
- the six-action mapping is exact and source-backed;
- the 757-row field mapping is complete, disjoint between 0004/0005, and set-equal to the authoritative registry;
- every source needed by the design is registered;
- current focused test commands are known, executable, and bound to exact argv arrays;
- machine and human traceability contain the same 56 unique IDs and every human row has an explicit status cell;
- the ADR 0003 PORT002A/PORT002B status contradiction is recorded without changing frozen fixture artifacts, and is preserved as a reviewed-document requirement for final P0 closure;
- no unresolved contradiction requires an architectural guess.

When any condition fails, stop before code and report the first root contradiction plus all independently safe audit results already collected.
