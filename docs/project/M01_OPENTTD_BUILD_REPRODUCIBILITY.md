# M01 OpenTTD Clean-Build Reproducibility Evidence

- Build-runner component result: `PASS`
- Headless repeated-build result: `PASS`
- Playable repeated-build result: `PASS`
- M01/G01 result: `PASS` (closed by `G01_GATE_REPORT.md`)
- Date: 2026-08-01
- Source profile: `openttd-15.3-v1`
- Build-input profile: `ubuntu-24.04-x86_64-openttd-15.3`

## Runner and offline inputs

`scripts/v1/openttd_build.sh` creates a new owner-only artifact root and delegates
to `scripts/v1/run_openttd_build.py`. The runner has no dependency-acquisition or
network path. It accepts only a pre-existing local cache, requires an initially
empty artifact root, and rejects any unlisted, missing, non-regular, size-drifted,
digest-drifted, or package-metadata-drifted archive.

The strict lock at `config/v1/openttd-build-input-lock.json` contains 34 exact
Ubuntu 24.04 amd64 packages totaling 37,421,106 bytes. Its SHA-256 is:

```text
099675da5a508cd5a58405767e7713f5dbbc810b7dae52e6fc2687341bbc6985
```

The lock is the exact private-sysroot overlay used by these builds: OpenGFX 7.1;
PNG, LZMA, and CURL development/runtime archives; and the SDL2, FreeType,
Fontconfig, HarfBuzz, ICU, and PulseAudio archives that are not delegated to the
pinned Ubuntu 24.04 host profile. Every accepted run rechecked the full cache
before extraction. The three known OpenGFX documentation symlinks are checked as
package structure; only the seven regular game-data files enter runtime input.

The independent [toolchain-probe report](M01_TOOLCHAIN_PROBE.md) remains the
authority for CUDA 13, LibTorch 2.13 `cu130`, the exporter environment, ONNX opset
18, and ONNX Runtime 1.28. The OpenTTD runner independently observed and required:

| Tool | Exact version |
|---|---|
| GCC | 13.3.0 |
| G++ | 13.3.0 |
| CMake | 3.28.3 |
| CTest | 3.28.3 |
| Ninja | 1.11.1 |

## Build contract

Both variants use the same immutable 15.3 commit and the one-patch prepared tree
proven in the [source-preparation report](M01_SOURCE_PREPARATION.md). Each run
exports the commit, applies the exact patch with no fuzz, moves generated Git
metadata into retained evidence, and writes a fixed `15.3-v1` revision record.

The build contract is Release/C++20 with `-O2 -g0`, assertions enabled, warnings
as errors, path-prefix maps for source and build roots, a canonical variant-specific
install prefix, FHS installation, package-dependency installation disabled, and a
fixed `SOURCE_DATE_EPOCH`. GNU build IDs are disabled because the linker build ID
was the only differing field in otherwise byte-identical executables; no completed
binary is rewritten or normalized after linking.

Configuration fails if PNG, Zlib, LZMA, or CURL is absent. The playable variant
also requires SDL2, FreeType, Fontconfig, HarfBuzz, and both ICU components. CMake
and compiler warnings fail the run. `ldd` output is reduced to a path-independent
sorted SONAME inventory and any `not found` entry fails. The accepted headless
closure contains 38 SONAMEs and the playable closure contains 91.

## Commands and retained evidence

These were the four accepted wrapper invocations, in order:

```bash
./scripts/v1/openttd_build.sh --variant headless \
  --artifact-root /home/thecl/.codex/artifacts/openttd-rl/m01-headless-build-20260801-k \
  --cache-root /home/thecl/.codex/cache/openttd-rl/openttd-build-debs \
  --tools-python /usr/bin/python3.12 --jobs 4

./scripts/v1/openttd_build.sh --variant headless \
  --artifact-root /home/thecl/.codex/artifacts/openttd-rl/m01-headless-build-20260801-l \
  --cache-root /home/thecl/.codex/cache/openttd-rl/openttd-build-debs \
  --tools-python /usr/bin/python3.12 --jobs 4

./scripts/v1/openttd_build.sh --variant playable \
  --artifact-root /home/thecl/.codex/artifacts/openttd-rl/m01-playable-build-20260801-f \
  --cache-root /home/thecl/.codex/cache/openttd-rl/openttd-build-debs \
  --tools-python /usr/bin/python3.12 --jobs 4

./scripts/v1/openttd_build.sh --variant playable \
  --artifact-root /home/thecl/.codex/artifacts/openttd-rl/m01-playable-build-20260801-g \
  --cache-root /home/thecl/.codex/cache/openttd-rl/openttd-build-debs \
  --tools-python /usr/bin/python3.12 --jobs 4
```

Each root's path-normalized `commands.json` records every subprocess, working
directory, argument, and exit code: 81 commands per headless run and 82 per
playable run. The command reports compare byte-for-byte within each repeated pair.
`timing.json` separately records every subprocess duration and total elapsed time.
Named raw logs and CTest JUnit output are retained for diagnosis.

## Test and smoke results

| Variant | Exact CTest count | Runtime validation | Result |
|---|---:|---|---|
| Headless | 96 | OpenGFX load; null video/sound/music; exactly 128 ticks; clean exit | `PASS` |
| Playable | 2 | Same 128-tick null profile plus SDL dummy main-game startup and normal exit | `PASS` |

The playable SDL smoke uses the real `32bpp-anim` blitter and requires diagnostics
confirming that blitter, SDL's `dummy` backend, and OpenTTD's `sdl` video driver.
A private `game_start.scr` runs `exit` only after OpenTTD reaches `OnStartGame`, so
success is a normal engine shutdown. A 20-second hard kill is only a failing
watchdog. The smoke does not depend on a host display, sound device, or user config.

CTest inventory is captured before execution. Empty or duplicate inventories,
renamed/missing result cases, failures, errors, and skips all fail closed. The
headless and playable profiles intentionally expose different upstream CTest
inventories; each accepted repeat matches its own exact canonical inventory.

## Clean-build and artifact comparison

| Variant/run | Total seconds | Tests | Installed files | Build identity | Executable SHA-256 |
|---|---:|---:|---:|---|---|
| Headless `k` | 210.946 | 96 | 161 | `102f07d8595673a06888bb935c809c47ea3326f8d66be158a1588e32ec530de3` | `b24a50994326e2480de38d633ef34c0516e2565ed5aa201ff4e6c13e235b45e3` |
| Headless `l` | 210.714 | 96 | 161 | `102f07d8595673a06888bb935c809c47ea3326f8d66be158a1588e32ec530de3` | `b24a50994326e2480de38d633ef34c0516e2565ed5aa201ff4e6c13e235b45e3` |
| Playable `f` | 218.155 | 2 | 161 | `5e50757e298b5c241655663e94a5ce0dde0a69eb4e5d811c467fe2dc63cf3c7b` | `f55efe3ebda2b5d7b236ffcaefadb7828cfcb44740ab141bb25e3de720d8a1da` |
| Playable `g` | 218.234 | 2 | 161 | `5e50757e298b5c241655663e94a5ce0dde0a69eb4e5d811c467fe2dc63cf3c7b` | `f55efe3ebda2b5d7b236ffcaefadb7828cfcb44740ab141bb25e3de720d8a1da` |

The headless manifest SHA-256 is
`235fb2a9eaa3a9569b8b357db7da9f0933af1ec546031e3aa3255cc0d8233778`
in both roots. The playable manifest SHA-256 is
`e9cc12b94ef1eeefd96e7cac2d9a7e2114f463e52470415a571b7c98b5585046`
in both roots.

Every installed tree contains 161 regular files and zero symlinks. Recursive,
symlink-aware comparisons found no difference in any installed file. Each manifest
also independently records relative path, mode, byte count, and SHA-256 for every
file. The corresponding prepared-source trees, local sysroots, staged OpenGFX
inputs, isolated smoke-test user trees, canonical test inventories/results,
prepared-source manifests, and command reports also compare exactly within each
pair. Both successful runs removed their private `build` directory and verified
that it no longer existed before reporting `PASS`.

Raw command logs, JUnit timestamps/per-test durations, and `timing.json` are
evidence rather than build products and intentionally retain observations that
vary with wall clock or elapsed time. They are excluded from the build identity;
their canonical inventories and pass/fail projections are included. No installed
artifact, canonical manifest field, or command description depends on an artifact
root, timestamp, or build duration.

## Rejected-attempt root causes

Development roots were rejected rather than accepted or overwritten when a gate
found a problem. The resolved causes were:

- missing build libraries were added to the exact archive lock instead of being
  downloaded during a build;
- the GCC 13.3 language-map diagnostic was fixed by the semantic source patch,
  without warning suppression;
- broken package-document symlinks were validated but excluded from runtime game
  data staging;
- a path-sensitive GNU build ID was disabled at link time;
- the complete SDL/PulseAudio runtime closure and linker search path were pinned;
- playable CTest received the same private runtime-library path as the executable;
- the SDL smoke switched from the invalid null blitter to `32bpp-anim`; and
- signal-based termination was replaced with OpenTTD's post-start `exit` hook.

Only the four roots named above are the accepted clean-build evidence.

## Automated runner tests and reproduction

Eleven focused tests cover the exact repository lock, policy/package drift,
version drift, hostile environment-variable removal, CTest inventory, JUnit
results, unresolved libraries, content-addressed install inventory, path-independent
command reports, warning/nonzero-command rejection, and overwrite rejection.

To reproduce either profile, choose a new absolute artifact root and provide the
already-acquired exact local cache:

```bash
./scripts/v1/openttd_build.sh \
  --variant headless \
  --artifact-root /absolute/new/headless-root \
  --cache-root /absolute/locked-deb-cache \
  --tools-python /usr/bin/python3.12 \
  --jobs 4
```

Use `--variant playable` and another new root for the playable profile. Existing
artifact roots, relative paths, missing cache roots, and invalid job counts are
rejected by the wrapper.

## Boundary

The requested two clean headless builds and two clean playable builds are complete.
The remaining build-profile, resource, and provenance evidence later passed in
`M01_BUILD_PROFILE_RESOURCE_PROVENANCE.md`, and the complete gate audit is
`G01_GATE_REPORT.md`. No `M02` scenario or OpenTTD feature implementation was part
of these accepted build runs.
