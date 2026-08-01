# ADR 0009: Pin OpenTTD 15.3 and maintain an external V1 patch series

- Status: Accepted
- Date: 2026-07-31
- Applies to: V1 engine semantics and all V1 OpenTTD build variants
- Source identity: OpenTTD commit `14ec60f248547d4d062a1160f0fc26d742319888`

## Context

The historical P0 submodule is pinned at
`29f808ef0022064e6d9a83c8476d1e0f4686af86`, described locally as
`16.0-beta2-82-g29f808ef00`. That revision is valid authority for retained P0
evidence, but it is a development commit after a beta and is coupled to a dirty
outer worktree containing user-owned P0 changes.

On 2026-07-31, the [official OpenTTD release page](https://www.openttd.org/downloads/openttd-releases/latest)
identified 15.3 as the stable release, and the upstream Git tag `15.3` resolved to
commit `14ec60f248547d4d062a1160f0fc26d742319888`. V1 needs a stable reproducible
engine basis without switching the historical submodule worktree or erasing its
role in P0 evidence.

## Decision

1. OpenTTD commit `14ec60f248547d4d062a1160f0fc26d742319888` is the immutable
   V1 engine source and behavioral authority. The human tag `15.3` is descriptive;
   the full commit ID is normative.
2. The upstream remote is `https://github.com/OpenTTD/OpenTTD.git`. Acquisition
   verifies the requested commit and a reviewed source-tree digest; a floating
   branch or tag name is not accepted as build input.
3. The existing `openttd-upstream` working tree and outer gitlink remain at their
   historical P0 identity until a separate preservation/migration operation is
   explicitly approved. V1 source preparation must not check out 15.3 in that
   working tree.
4. A V1 source-preparation runner creates a detached, disposable worktree or copy
   at the pinned commit in a caller-selected generated-artifact root. The generated
   source tree and build directory are never committed.
5. Project modifications are an ordered patch series stored outside the upstream
   working tree under a V1-owned path such as
   `integration/openttd/patches/15.3/`. Every patch has a stable order, purpose,
   affected requirements, and digest.
6. Patch application is fail-closed and produces a manifest containing base commit,
   patch names/digests, resulting tree identity, tool versions, dirty status, and
   source root. Fuzzed, offset, partially applied, or locally edited accepted
   sources are rejected.
7. Headless training/evaluation and playable inference are feature variants built
   from the same base and patch-series identity. Build flags may remove training
   dependencies, but may not create different environment/action/preprocessing
   semantics.
8. An upstream security or correctness fix is adopted only through a new ADR that
   records the replacement commit, semantic-compatibility assessment, regenerated
   fixtures, migration policy, and reopened evidence. Cherry-picks are patches and
   cannot masquerade as the original 15.3 tree.
9. The compatibility identity includes both the base commit and patch-series
   digest. An unpatched upstream binary and a patched V1 binary are never described
   as the same environment version.

## Why stable 15.3

- it is an official stable release rather than a post-beta development snapshot;
- it provides a reviewable support target for a long-running research platform;
- using an exact commit avoids later tag/ref movement; and
- separating it from the historical submodule prevents V1 work from rewriting P0
  evidence or the user's current changes.

This is a lifecycle decision, not a claim that 15.3 has already passed the V1 bus,
bridge, CUDA, or ONNX test matrix.

## Rejected alternatives

### Continue on the current P0 development commit

Rejected because the post-beta commit was selected for the former P0 effort and
has no V1 stability advantage. Keeping it would couple the active product to a
historical worktree for convenience rather than evidence.

### Track `master`, `release/*`, or the newest tag at build time

Rejected because moving inputs invalidate deterministic resets, command semantics,
save compatibility, and published experiment comparisons.

### Switch or edit `openttd-upstream` in place

Rejected because it risks the user's active P0 work and obscures reconstruction of
both source bases.

### Fork the complete upstream tree into the outer repository

Rejected because a compact ordered patch series exposes the integration delta and
preserves upstream provenance more clearly.

## Verification

`G01` requires:

- two clean preparations independently resolve the exact commit and yield the same
  base-tree and applied-tree identities;
- a wrong commit, reordered/changed patch, patch offset, or local edit fails;
- both build variants report the same base and patch identities;
- the historical P0 working tree/gitlink remains unchanged by V1 preparation; and
- source reconstruction works after approved dependencies are cached, without a
  network lookup changing any selected bytes.

The commit can be inspected at the
[upstream source record](https://github.com/OpenTTD/OpenTTD/commit/14ec60f248547d4d062a1160f0fc26d742319888).
