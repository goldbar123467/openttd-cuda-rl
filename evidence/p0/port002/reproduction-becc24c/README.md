# PORT002A clean-script reproduction at `becc24c`

This bundle records the independent execution of the committed fixture recipe
after commit `becc24c` was pushed. It is distinct from the two native runs that
originally froze `fixture.sav`: the published `build_fixture.sh` was invoked
from a new artifact root, created and patched a fresh detached worktree, built
OpenTTD from zero, ran two isolated creation processes in different UTC
seconds, compared both outputs, compared them with the tracked artifacts, and
removed its disposable source worktree.

The gate result was `PASS` after 315 seconds. Both independently recreated save
files were 10008 bytes with SHA-256
`74c9be53902598061e1e82835c394a37b77bfc71c818de1df8456cdfc2804d20`.
Both 49152-byte canonical map-plane streams had SHA-256
`5a933bc43d59c05b0d8fda519aec0aafa71b16d50a03aea83aefade7a57c9dd6`.

The rebuilt executable had SHA-256
`5f20d5e4e08d0e400624f21c1f47be5dfbd757402c422d6e1a57b7f027f79f0e`.
It is intentionally not required to equal the original creation executable:
OpenTTD debug information includes absolute generated source/build paths. The
source commit, patch bytes, build arguments, behavior, save bytes, and map
planes—not path-bearing debug sections—are the reproducibility contract.

Logical reproduction command:

```bash
oracle/fixtures/road_freight_v1/builder/build_fixture.sh \
  --artifact-root "$ARTIFACT_ROOT" \
  --opengfx-tar "$VERIFIED_OPENGFX_INSTALLED_TAR" \
  --jobs 8
```

`artifact-index.json` binds every retained compact result and raw log. Large
build output is compressed with deterministic `gzip -n -9`; its uncompressed
SHA-256 is also recorded. The full generated build tree and executables are not
tracked because they are reproducible and exceed the repository evidence
policy.

This is PORT002A evidence only. It does not claim the PORT002B two-load native
projection, command, cargo milestone, or payment gates.
