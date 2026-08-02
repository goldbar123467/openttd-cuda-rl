# M14 engine-source decision

## Decision

Status: `ACCEPTED` on 2026-08-02.

V2 retains the V1 OpenTTD 15.3 source identity for M14 through M23:

- release `15.3`;
- commit `14ec60f248547d4d062a1160f0fc26d742319888`;
- tree `02d8cbbb0d8c030698d37ca76ab2773b6e23c397`; and
- the exact ordered V1 patch/profile lineage in
  [`config/v1/openttd-source-profile.json`](../../config/v1/openttd-source-profile.json).

The V2 command inventory, native oracles, opponent qualification, training,
evaluation and packages all use this identity. A rebase is a new source-contract
decision and cannot be introduced as an incidental implementation change.

## Measured rebase comparison

The comparison target was the clean local upstream object-repository head
`29f808ef0022064e6d9a83c8476d1e0f4686af86` on 2026-08-02. These commands were
run from the repository root:

```text
git -C openttd-upstream rev-list --count 14ec60f248547d4d062a1160f0fc26d742319888..29f808ef0022064e6d9a83c8476d1e0f4686af86
git -C openttd-upstream diff --shortstat 14ec60f248547d4d062a1160f0fc26d742319888..29f808ef0022064e6d9a83c8476d1e0f4686af86
git -C openttd-upstream diff --shortstat 14ec60f248547d4d062a1160f0fc26d742319888..29f808ef0022064e6d9a83c8476d1e0f4686af86 -- src/script/api
git -C openttd-upstream apply --check ../integration/openttd/patches/15.3/0001-gcc13-language-map-emplace.patch
git -C openttd-upstream apply --reverse --check ../integration/openttd/patches/15.3/0001-gcc13-language-map-emplace.patch
```

Measured results:

| Measurement | Result |
|---|---:|
| Commits after the pin | 1,082 |
| Whole-tree diff | 1,177 files, 60,574 insertions, 47,465 deletions |
| Script/NoAI API diff | 88 files, 1,235 insertions, 1,063 deletions |
| V1 portability patch | 1 patch, 3 files, 12 insertions, 8 deletions |
| Forward apply to comparison target | `FAIL`, all 3 paths rejected |
| Reverse apply to comparison target | `FAIL`, all 3 paths rejected |

The forward and reverse failures mean the patch is neither directly reusable nor
merely already applied at that target. Its three paths independently changed by
138 insertions and 125 deletions relative to 15.3. A rebase would therefore need
a semantic rewrite and renewed native, script-API, training, inference and
visible-play evidence—not just a clean compile.

## NoAI compatibility observation

The M14 content audit used the accepted V1 release executable, whose SHA-256 is
`8b27f06113d08fa3a21f81c01721873194f35bf885963be2697cc9da52e1ef9a`.
Eight audit-pool AIs were dependency-completely downloaded. Their embedded API
declarations are all at or below API 15: AAAHogEx and Trans AI declare 14,
LuDiAI AfterFix declares 15, and the remaining locked packages declare older
1.x APIs. This establishes content/API eligibility, not runtime competence. The
separate runtime results in
[`M14_OPPONENT_ACQUISITION.md`](M14_OPPONENT_ACQUISITION.md) reject packages that
fail to load or crash despite catalog eligibility.

ChooChoo and SimpleAI were visible in the catalog but could not enter the selected
dependency state. Their byte acquisition was rejected and their transcripts were
retained. The decision does not claim those packages are compatible.

## Alternatives

### Rebase V2 immediately

Rejected for this release line. It would discard the already accepted V1 source
and oracle baseline while creating a large, measured validation surface before
any V2 transport feature exists.

### Support both 15.3 and current master

Deferred. A dual-engine matrix doubles native observations, actions, savegame
compatibility, package eligibility, training and tournament validity. It can be
proposed after G23 as an independently gated compatibility track.

### Retain 15.3

Accepted. It preserves all V1 results, gives every V2 milestone one source
identity, and permits exact comparisons while the environment expands.

## Consequences and reversal rule

- Every V2 schema and manifest must carry the retained source identity.
- BaNaNaS packages must declare an API supported by the retained engine and pass
  an actual runtime qualification before tournament admission.
- Newer OpenTTD features outside 15.3 are not silently included in the V2
  base-game completeness claim.
- A future rebase proposal must pin its target, port every patch without fuzz,
  disposition command/API drift, rerun V1 and all passed V2 gates, and produce a
  compatibility migration for models, saves and opponent manifests.
