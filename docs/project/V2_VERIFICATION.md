# V2 verification workflow

The V2 verification driver has three cumulative tiers. Full is the no-argument
default. Fast and contract are offline, portable tiers: they can validate source
and committed artifact records, but they cannot make a G23 or V2 release
acceptance claim. Full is live and fail-closed. It requires every declared live
input and never converts a missing mandatory input into a skip.

## Portable developer checks

Run the repository-only fast tier first:

```bash
./scripts/v2/verify.sh --tier fast
```

Fast runs the driver, source-context, artifact-context, and binary-corpus unit
boundary. It does not require the OpenTTD submodule or retained artifact caches.

Initialize the pinned source object repository, then run contract:

```bash
git submodule update --init --recursive
./scripts/v2/verify.sh --tier contract
```

The `openttd-upstream` submodule must be a clean checkout of pinned object
`29f808ef0022064e6d9a83c8476d1e0f4686af86`. Contract uses that object to prove
research and setting source completeness. It otherwise validates committed
artifact records offline; it does not read retained live artifacts.

Neither portable tier validates retained G23 evidence or releases V2. A passing
portable tier is evidence about the repository refactor boundary only.

## Live full verification

Put the complete relocated artifact tree below one absolute root and run full
without a tier argument:

```bash
OPENTTD_RL_ARTIFACT_ROOT=/absolute/openttd-rl-artifacts \
  ./scripts/v2/verify.sh
```

`OPENTTD_RL_ARTIFACT_ROOT` relocates filesystem reads; it does not weaken or
rewrite recorded identities. The root must contain `v2-live-inputs.json`. That
manifest binds every named role to an input below the same root:

- `recovery-v1-artifacts`
- `recovery-v1-executable`
- `recovery-v1-corpus`
- `recovery-v2-artifacts`
- `training-artifacts`
- `qualification-artifacts`
- `v2-campaign-executable`
- `v2-corpus-binary`
- `qualification-executable`
- `final-v1-evaluator`
- `m14-openttd-executable`

Before launching commands, full aggregates every missing or invalid source
repository, live-input role, required tool, artifact set, nested file, and
SHA-256 digest as one aggregate preflight error before any command starts. This
includes the exact Git inputs used for the M23 patches and the Bubblewrap binary
used by retained M22 evaluation. A missing source, role, tool, set, nested input,
or digest therefore stops the tier before command execution; mandatory live work
is not reported as skipped.

The retained final-v1 and follow-up-v1 validators return status `2` for their
expected semantic outcomes: both immutable evidence sets remain validly
recomputed `FAIL` results. The driver treats those two exact statuses as success
for their declared commands. They are distinct from infrastructure or preflight
status `2`, which fails full verification before commands or reports an
unexpected execution failure.

A complete relocated live tree is still required for later live acceptance. A
rootless aggregate preflight result proves that the portable workflow fails
closed; it is not a G23 gate result, a release pass, or retained-evidence
validation.
