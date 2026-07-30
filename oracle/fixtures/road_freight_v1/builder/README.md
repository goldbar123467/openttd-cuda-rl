# Deterministic `road_freight_v1` fixture builder

This directory contains the complete, reviewable recipe that produced the
native OpenTTD save committed one level above. The patch is deliberately not
part of the oracle instrumentation series and is never applied to the normal
`openttd-upstream` worktree. It adds one hidden, creation-only `-Z` entry point
to a disposable build of the exact pinned OpenTTD commit.

The builder uses native world, town, landscape-clear, industry, and company
initialization paths. It leaves the save immediately before replay: no road,
stop, depot, road vehicle, or order exists. The direct opening-balance write is
a declared fixture-creation operation and has no counterpart in the replay
command schema.

Run it with an already verified OpenGFX 8.0 installed tar:

```bash
oracle/fixtures/road_freight_v1/builder/build_fixture.sh \
  --artifact-root /workspace/p002-fixture-reproduction \
  --opengfx-tar /absolute/path/to/opengfx-8.0.tar \
  --jobs 8
```

The artifact root must be new and outside the repository. The script creates a
detached source worktree, applies the patch after `git apply --check`, uses the
same GCC/Ninja RelWithDebInfo profile as PORT001, builds the native executable,
and invokes it twice in isolated XDG trees. The two invocations begin in
different real UTC seconds; wall clock is not declared as a fixed input. The
generation seed, persisted gameplay state, interactive RNG, and savegame ID are
explicitly fixed by the patch.

Success requires all four byte comparisons:

- run A save equals run B save;
- run A map-plane stream equals run B map-plane stream;
- reproduced save equals the committed `fixture.sav`;
- reproduced map-plane stream equals committed `map-planes-v1.bin`.

The executable digest is recorded but is not required to equal the historical
creation executable digest. OpenTTD embeds absolute source/build paths in debug
information, so raw executable bytes vary with the chosen artifact root. The
source commit, patch digest, complete build arguments, compiled behavior, save
bytes, and map-plane bytes are the reproducibility contract.

`evidence/` retains the raw native diagnostics from the two authoritative
release runs and a later wall-clock-independence run. Absolute output paths in
those logs are diagnostic only and are excluded from canonical fixture
identity.
