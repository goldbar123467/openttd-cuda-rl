# M00 Worktree Preservation Inventory

## Status

- Capture date: 2026-07-31
- Outer commit: `76574e7e65494b72ed3c07cbf973722865c3569f`
- Branch: `fix/p0-build-portability`
- OpenTTD submodule commit: `29f808ef0022064e6d9a83c8476d1e0f4686af86`
- Submodule state at capture: clean at the recorded gitlink
- Preservation state: recoverable local snapshot created and restoration verified
- Snapshot timestamp: `20260731T231051Z`
- M00-A gate state: `PASS`

This inventory began as a non-destructive identity record before executable V1
traceability artifacts were added. It is now paired with a verified local recovery
snapshot. The snapshot permits byte recovery after an accidental workspace edit;
it does not authorize a destructive clean, reset, checkout, branch switch, or bulk
relocation, and it does not protect against loss of the entire host.

## Durable local recovery snapshot

The snapshot directory is:

```text
/home/thecl/.codex/artifacts/openttd-rl/m00-preservation-20260731T231051Z
```

Its parent is owner-only. The four retained artifacts are:

| Artifact | Bytes | SHA-256 | Purpose |
|---|---:|---|---|
| `outer-repository.bundle` | 1,010,547 | `8fb8904c57401f2b1075a1bb33d1679a03e52d12cd779b3c8bbbfaa00f975af9` | Complete outer Git ref history at capture. |
| `openttd-submodule.bundle` | 675,006,717 | `89ba162d23f0493284b15206e0f4b288cad6575102d66b158048b2fec5c2a1ee` | Complete locally available OpenTTD ref history, including historical worktree commits and the V1 15.3 object/ref. |
| `worktree-files.tar.gz` | 1,109,677 | `fd7ff5ca135787dde42b0b1414d78d952a28cf9aee654598c2ab6cb5dff0bcd6` | Current bytes and modes for 398 tracked/untracked, non-ignored outer-worktree files; the submodule directory is intentionally represented by its bundle. |
| `tracked-working-tree.patch` | 373,519 | `e83d889dad2587d3235a5004c073f8c5e0c6ad73a665ebc2068aa925d00ca9bb` | Redundant binary-capable review/recovery patch for tracked modifications. |

There were no staged changes at snapshot time. The submodule worktree was clean at
`29f808ef0022064e6d9a83c8476d1e0f4686af86`. Ignored build/cache artifacts were
not preserved because they are not source or user-authored work.

Both bundles passed `git bundle verify`. A disposable restoration then:

1. cloned the outer bundle;
2. cloned the OpenTTD bundle at `openttd-upstream`;
3. extracted the worktree archive over the outer checkout;
4. byte-compared all 398 archived members with the live capture;
5. compared complete `git status --porcelain=v1 -uall` output; and
6. verified the outer and submodule commits and clean submodule state.

Observed result:

```text
RESTORE=PASS files=398
outer=76574e7e65494b72ed3c07cbf973722865c3569f
submodule=29f808ef0022064e6d9a83c8476d1e0f4686af86
```

To recover into a new empty directory, set `SNAPSHOT_DIR` to a verified copy of the
snapshot directory, clone `outer-repository.bundle`, clone
`openttd-submodule.bundle` into the resulting `openttd-upstream` path, and extract
`worktree-files.tar.gz` at the outer repository root. Verify all four SHA-256
values before use. Recovery must target a new directory; it must not overwrite the
live worktree.

## Tracked diff identity

At capture, `git diff --binary` was 372,276 bytes with SHA-256:

```text
e4657400b12f68f3e86d5ab01eac9ae4b6793b2921d9e67f19f19ae4133abc4c
```

The tracked changes comprised:

- the new project-planning rewrite and legacy notices in top-level Markdown;
- legacy P0 reference runner changes;
- legacy P0 PORT-001/PORT-004 test changes;
- legacy tape-reference and golden-artifact changes;
- legacy P0 CI script changes.

Exact modified tracked paths at capture:

```text
NEXT_STAGES_IMPLEMENTATION_HANDOFF.md
OPENTTD_P0_ORACLE_CONTRACT_AGENT_PROMPT.md
OpenTTD_CUDA_RL_REVERSE_ENGINEERING_REPORT.md
README.md
docs/scope/P0_FORBIDDEN_SCOPE.md
docs/scope/P0_SUPPORTED_SCOPE.md
oracle/runner/build_reference.sh
oracle/runner/common.sh
oracle/runner/configure_reference.sh
oracle/runner/test_reference.sh
oracle/tests/port001/port001_comparator_tests.py
oracle/tests/port001/port001_contract_tests.py
parity/python_reference/tape_reference.py
parity/tape/golden/README.md
parity/tape/golden/minimal-valid.hex
parity/tape/golden/minimal-valid.tape
parity/tests/golden/golden.py
parity/tests/integration/test_port004.py
scripts/ci/p001_contract_tests.sh
scripts/ci/p002_fixture_contract_tests.sh
```

## Untracked legacy work at capture

These files predated or belong to the unfinished P0 instrumentation/command work.
They are user-owned and must be preserved independently of V1 applicability:

| Path | SHA-256 |
|---|---|
| `00_P0_CODEX_HANDOFF_INDEX.md` | `ce9c5b08e7231a1d60d6b5e6a5e97f11c210cfa428837b2298c98c0ed1f1c063` |
| `01_P0_EVIDENCE_GATE_AND_CONTRADICTION_REGISTER.md` | `479617c482b91fd0aa934f4c9de4d85c9984a3b4c0fe85cec937ce41c1a8c12b` |
| `02_P0_PATCHES_0003_0007_IMPLEMENTATION_SPEC.md` | `2c2a55b8bc7fb72873e50ea2ea86c8226f9061ff619935533c3e7916cca34648` |
| `03_P0_COMMAND_AND_FIELD_MAPPING_CONTRACT.md` | `de7e2d48581aac4e0524cc322663a99f2ba10771f4695037caa90fc7e54f3ad3` |
| `docs/P0_SCOPE.md` | `f524ec5a5bdb3b2f46322ba16c534c1c38310034922541208997a6de948c52ff` |
| `oracle/instrumentation/README.md` | `66ef5ca757e02399ecd1385814b287713f29c901cd3748dc237d49d4d9270d6a` |
| `oracle/instrumentation/patches/0001-trace-sink-and-codec.patch` | `33d368c18ac44684679886f3214a0a5fbac295b3ee7d9fc79ff305c54697adbe` |
| `oracle/instrumentation/patches/0002-build-and-run-identity.patch` | `b2900210ec517392e4d57a114d2bda2490ec803a6f1ecc4911da2b51298842c7` |
| `oracle/instrumentation/patches/series` | `32d57ef97757217239a7a33d364a06e8096a125c7011ad1b08dae38c043548e2` |
| `oracle/runner/apply_instrumentation.sh` | `9372cbed2844ef2f0a54d3ae53b7f8ac29412ef368d173ab70b6ffdc09e80528` |
| `oracle/runner/create_instrumented_worktree.sh` | `5f4edf1616b84a7ae2731b755771b72b27514d54e5dc5dbeb042c4c36999264e` |
| `oracle/tests/port003/test_command_input_v1.py` | `b21fa854f69e866e911b88a83ce4ccae78a3a4b3a684ce29e35bd1689260cbce` |
| `parity/schema/command-set.schema.json` | `b11791cbe5d2f7910dad8bd56ab05bf422cee1db39de72f65510ae726cc8a2c3` |
| `parity/schema/commands-v1.json` | `d1f7b8f3c102bde575d44b2ef2319f37185ba285394955c077adacf7dd2026b0` |
| `scripts/ci/p003_instrumentation_tests.sh` | `b368a456bb69369d3ee44b65d91987301a9697df44463f98208ecb034997c544` |
| `scripts/dev/command_input_v1.py` | `9f030fb483c60416dc11cacc6faefca69e1ead28051d89ee62456a88cba28999` |

## New planning work present at capture

The following untracked files are the planning reset, not legacy P0 production
work. Their identities are recorded only to distinguish the layers; they continue
to change during M00:

```text
GOAL.md
docs/architecture/V1_ARCHITECTURE.md
docs/contracts/V1_ENVIRONMENT.md
docs/decisions/0007-v1-product-goal-and-legacy-p0-transition.md
docs/project/LEGACY_P0_TRANSITION.md
docs/project/REQUIREMENTS.md
docs/project/ROADMAP.md
docs/project/VERIFICATION.md
docs/training/PPO_AND_MODEL_PIPELINE.md
```

## Preservation rules after capture

1. Do not modify the listed legacy implementation files for V1 convenience.
2. Add V1 schemas, tools, tests, and evidence under distinct names/paths.
3. Re-run status and content identities before any operation that changes branch,
   index, worktree layout, or legacy path ownership.
4. Re-capture before any later operation if relevant bytes or paths have changed;
   this snapshot is an immutable point in time, not a continuously updated backup.
5. Copy the snapshot off-host before relying on it for machine-loss recovery or
   before deleting the only live copy of any user-owned work.

## Publication and history remain separate

This local snapshot does not commit, push, publish, relicense, or resolve how the
mixed legacy/planning work should be divided into Git history. Those actions still
require an intentional reviewed scope. Snapshot creation changed no branch, index,
working file, or submodule checkout.
