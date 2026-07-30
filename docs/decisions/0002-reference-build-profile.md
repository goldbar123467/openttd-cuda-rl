# ADR 0002: Reference build profile

- Status: accepted for `PORT-001` implementation
- Date: 2026-07-30
- Scope: `PORT-001` reference reconstruction only
- Behavioral source: OpenTTD commit
  `29f808ef0022064e6d9a83c8476d1e0f4686af86`
- Supersedes: no prior ADR

## Decision

The P0 reference is a non-dedicated, assertion-enabled, FHS-layout OpenTTD build
from the pinned submodule commit on Ubuntu 24.04 x86-64. It uses GCC 13.3.0,
G++ 13.3.0 as the compiler/linker driver, GNU ld 2.42, CMake/CTest 3.28.3, and
Ninja 1.11.1. GNU objcopy/readelf 2.42 are frozen for equivalent binary
difference inspection. The build type is `RelWithDebInfo`. OpenGFX 8.0 is the only
approved base-graphics profile for this gate.

The committed JSON files are frozen expected profiles. They are not a claim
that a clean P0 run has occurred. Clean-run scripts must emit separate evidence
statements with actual commands, tool probes, input/output digests, return
codes, and diagnostics. A surviving `/workspace/openttd-build` or
`/workspace/openttd-install` tree is never accepted as reproducibility proof.

## Source profile

The exact source authority is:

| Material | Frozen identity |
|---|---|
| Outer repository basis | `58895696c8a75eda2fac2ae553654ba4398f5cda` |
| P0 branch | `port/p0-oracle-contract` |
| Submodule path | `openttd-upstream` |
| Submodule URL | `https://github.com/OpenTTD/OpenTTD.git` |
| Submodule commit | `29f808ef0022064e6d9a83c8476d1e0f4686af86` |
| `.gitmodules` SHA-256 | `326fef5383bcf7cc8b5c8a2522dca8a86acdcc653968ae2d5306b111ea49e04b` |

The outer basis commit is the immutable main-branch point from which P0 work
began. A committed manifest cannot name its own eventual commit without a
circular identity. Therefore every generated run evidence statement records
the actual executing outer commit, while the frozen source profile records the
basis commit and required branch. The submodule commit and clean-state
requirement are invariant and fail closed.

## Supported host and toolchain

The reference host profile is Ubuntu 24.04 on `x86_64`/Debian package
architecture `amd64`. The tool choices are:

| Role | Path | Tool version | Ubuntu binary package |
|---|---|---:|---|
| C compiler | `/usr/bin/gcc` | 13.3.0 | `gcc-13` `13.3.0-6ubuntu2~24.04.1` |
| C++ compiler/link driver | `/usr/bin/g++` | 13.3.0 | `g++-13` `13.3.0-6ubuntu2~24.04.1` |
| Linker implementation | `/usr/bin/ld` | GNU ld 2.42 | `binutils` `2.42-4ubuntu2.10` |
| Binary rewriter | `/usr/bin/objcopy` | GNU objcopy 2.42 | `binutils` `2.42-4ubuntu2.10` |
| ELF inspector | `/usr/bin/readelf` | GNU readelf 2.42 | `binutils` `2.42-4ubuntu2.10` |
| Configure/build frontend | `/usr/bin/cmake` | 3.28.3 | `cmake` `3.28.3-1build7` |
| Test frontend | `/usr/bin/ctest` | 3.28.3 | `cmake` `3.28.3-1build7` |
| Generator | `/usr/bin/ninja` | 1.11.1 | `ninja-build` `1.11.1-2` |
| Source control | `/usr/bin/git` | 2.43.0 | `git` `1:2.43.0-1ubuntu7.3` |
| Test tooling | `/usr/bin/python3` | 3.12.3 | `python3` `3.12.3-0ubuntu2.1` |

G++ invokes the platform default GNU linker; P0 does not silently substitute
LLD, gold, or another linker. Exact resolved binaries, package versions, and
version output are re-probed for every authoritative run.

The unversioned `clang` command was not on `PATH` during mandatory preflight, but
the versioned `/usr/bin/clang-16` frontend was present. The matching LLVM 16
tools, compiler-rt, libFuzzer, Clang-Tidy, and Static Analyzer packages were then
installed at exact Ubuntu package versions and compile-and-execute probed. They
belong to the separate mandatory P0 harness matrix documented in
`evidence/p0/port001/toolchain-probes.md`; they do not replace GCC/G++ as the
reference OpenTTD compiler/link driver. The full P0 gate remains non-passing
until every required GCC and Clang profile executes successfully on project code.

## Configure policy

The CMake generator is `Ninja`; the build type is `RelWithDebInfo`. Every
behavior-affecting argument is explicit in the complete array under
“Exact gate commands” below and in
`oracle/manifests/baseline/build-relwithdebinfo.json`. Those two representations
must remain equal to the command projection emitted by the configure runner.

The variables beginning with `$` above are role tokens, not shell-expanded
values embedded in canonical identity. The runner supplies separate absolute
paths as nonauthoritative invocation diagnostics. It creates a fresh dedicated
build root and never inherits a prior CMake cache.

The explicit policies are:

- assertions are enabled (`OPTION_USE_ASSERTS=ON`);
- a dedicated-only build is forbidden (`OPTION_DEDICATED=OFF`);
- the installed tree uses OpenTTD's FHS layout (`OPTION_INSTALL_FHS=ON`);
- build type drift is a hard failure;
- generator drift is a hard failure;
- every additional behavior-affecting cache variable discovered during
  implementation must be added to the manifest before the gate can pass;
- an executable left over from an earlier build is never accepted after a
  failed build.

## Feature-library policy

The non-dedicated reference requires the installed, version-pinned profile for:

- SDL2;
- libcurl;
- zlib;
- liblzma;
- LZO;
- libpng;
- FreeType;
- Fontconfig;
- HarfBuzz;
- ICU;
- Ogg, Opus, and OpusFile;
- FluidSynth;
- OpenGL, EGL, GLES, and GLX development interfaces.

OpenSSL is pinned for HTTPS/hash-support provenance, and Python `jsonschema`
4.26.0 is the current Draft 2020-12 validator dependency. The latter was found
as an installed Python distribution rather than an Ubuntu package; generated
evidence must preserve that distinction and may not invent an Ubuntu origin.
ShellCheck and `jq` are also pinned because the reference runners depend on
them. The exact binary and source package versions live in
`oracle/manifests/baseline/dependencies-ubuntu-24.04.json`; a free-form library
name is not a substitute for that inventory.

Missing required libraries or a detected feature-profile mismatch stops
configuration. Optional documentation and packaging tools do not enter the
reference behavior identity unless a later reviewed profile change makes them
material.

## Base-content and network boundary

The sole P0 base graphics profile is OpenGFX 8.0 (`OGFX`, content version 9499,
DOS palette, 8-bpp blitter). Its immutable acquisition identity is:

```text
https://cdn.openttd.org/opengfx-releases/8.0/opengfx-8.0-all.zip
sha256:43a0c1dabf39cb865394f3a6cc36d4da5c10ecfaaf55652043104806810903be
```

The installed delivery file is `opengfx-8.0.tar`, 5,396,480 bytes, SHA-256
`9389bcb0807058c80bd95121e978f05d9ef86b4b1bc3ac2da8da8bb02456043c`.
The OpenGFX manifest freezes the size and SHA-256 of every contained file.
OpenGFX is separate GPL-2.0-only content and is not committed by this decision.

Network access is allowed only when the verified content is absent and the
explicit acquisition runner is invoked. That runner must use HTTPS, finite
timeouts and redirects, a temporary download, exact digest verification before
extraction, archive path validation, temporary extraction, and atomic
promotion. Once a verified installation exists, authoritative tests and smoke
runs require no network. Installed-content drift fails preflight; it never
triggers a silent overwrite or fallback download.

## Environment allowlist

Only an explicit allowlist is recorded. The deterministic reference values are:

| Variable | Value | Identity role |
|---|---|---|
| `LC_ALL` | `C.UTF-8` | deterministic UTF-8 text and sort behavior |
| `LANG` | `C.UTF-8` | deterministic UTF-8 locale fallback |
| `TZ` | `UTC` | deterministic timezone |
| `SOURCE_DATE_EPOCH` | `1785314342` | pinned source commit timestamp |
| `P0_PROFILE` | `local-release` | release versus smoke distinction |
| `PYTHONHASHSEED` | `0` | deterministic Python helper ordering and hashes |
| `XDG_CONFIG_HOME` | role below `$ARTIFACT_ROOT` | isolated runtime configuration; diagnostic path |
| `XDG_DATA_HOME` | role below `$ARTIFACT_ROOT` | isolated runtime data; diagnostic path |

`P0_ARTIFACT_ROOT`, `P0_JOBS`, `CI`, and `GITHUB_ACTIONS` may be read where the
runner explicitly permits them. Artifact roots and parallelism are invocation
parameters, not source/gameplay identity. Runtime probes set `XDG_CONFIG_HOME`
and `XDG_DATA_HOME` to fresh role paths below the artifact root so host user
configuration and data cannot affect help or smoke behavior. No runner records
the complete process environment. Secret-named or unallowlisted entries fail
validation.

## Exact test inventory

The frozen RelWithDebInfo inventory contains exactly 99 distinct test names:
95 discovered Catch2 cases and four executable regression suites. The four
regression tests have `RUN_SERIAL=true`:

- `regression_regression`;
- `regression_stationlist`;
- `regression_gs`;
- `regression_gs_compat`.

All tests use the build root as their working-directory role; the absolute path
is normalized to `$BUILD_ROOT` and excluded from experiment identity. The
lexicographically sorted, UTF-8, LF-terminated name stream is 3,952 bytes and
has SHA-256
`5e4fac93bfa5c0f3d3b124eae2485b9d9f5de99118e1041406ea38d4ecdbea6c`.
The complete names are committed in
`oracle/manifests/baseline/tests-relwithdebinfo.json`.

The older reverse-engineering report's `98/98` is not rewritten into the
current profile. It described an earlier discovery state. Direct
`ctest -N --show-only=json-v1` on the pinned current build reports the extra
Catch2 case and a total of 99. The current live inventory was independently
recounted with `ctest -N`. The clean runner must rediscover the same 99 names and
properties; it must never force a count by deleting or renaming a test.

## Exact gate commands

From the repository root, the `PORT-001` closure entry point is:

```bash
./oracle/runner/port001_gate.sh \
  --profile local-release \
  --artifact-root /absolute/generated/port001-release \
  --tools-python /absolute/hash-locked-p0-venv/bin/python
```

The final `PORT-001` through `PORT-005` workflow will wrap this stage from
`oracle/runner/p0_gate.sh`; this ADR does not claim that later-stage wrapper is
available before its dependent ports exist.

The `PORT-001` portion must perform the following logical command arrays in
fresh generated roots. The runner chooses and records the concrete role paths:

```text
oracle/runner/preflight.sh --mode edit --artifact-root $ARTIFACT_ROOT --content-root $BUILD_ROOT/baseset
oracle/runner/configure_reference.sh --source-root $SOURCE_ROOT --build-root $BUILD_ROOT --install-root $INSTALL_ROOT --artifact-root $ARTIFACT_ROOT
oracle/runner/fetch_opengfx.sh --destination $BUILD_ROOT/baseset --artifact-root $ARTIFACT_ROOT
oracle/runner/build_reference.sh --build-root $BUILD_ROOT --install-root $INSTALL_ROOT --artifact-root $ARTIFACT_ROOT --configuration-manifest $ARTIFACT_ROOT/manifests/configure-reference.json --parallel $P0_JOBS
oracle/runner/test_reference.sh --build-root $BUILD_ROOT --artifact-root $ARTIFACT_ROOT --baseline-inventory $REPOSITORY_ROOT/oracle/manifests/baseline/tests-relwithdebinfo.json
oracle/runner/smoke_reference.sh --install-root $INSTALL_ROOT --artifact-root $ARTIFACT_ROOT --build-manifest $ARTIFACT_ROOT/manifests/build-reference.json
```

Under those wrappers, the frozen upstream operations are:

```text
/usr/bin/cmake -S $SOURCE_ROOT -B $BUILD_ROOT -G Ninja
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
  -DCMAKE_INSTALL_PREFIX=$INSTALL_ROOT
  -DCMAKE_C_COMPILER=/usr/bin/gcc
  -DCMAKE_CXX_COMPILER=/usr/bin/g++
  -DCMAKE_CXX_FLAGS=
  -DCMAKE_CXX_FLAGS_DEBUG=-g
  "-DCMAKE_CXX_FLAGS_MINSIZEREL=-Os -DNDEBUG"
  "-DCMAKE_CXX_FLAGS_RELEASE=-O3 -DNDEBUG"
  "-DCMAKE_CXX_FLAGS_RELWITHDEBINFO=-O2 -g -DNDEBUG"
  -DCMAKE_EXE_LINKER_FLAGS=
  -DCMAKE_MODULE_LINKER_FLAGS=
  -DCMAKE_SHARED_LINKER_FLAGS=
  -DPERSONAL_DIR:STRING=.openttd
  "-DSHARED_DIR:STRING=(not set)"
  -DGLOBAL_DIR:STRING=$INSTALL_ROOT/share/games/openttd
  -DHOST_BINARY_DIR=
  -DOPTION_DEDICATED=OFF
  -DOPTION_INSTALL_FHS=ON
  -DOPTION_PACKAGE_DEPENDENCIES=OFF
  -DOPTION_USE_ASSERTS=ON
  -DOPTION_FORCE_COLORED_OUTPUT=OFF
  -DOPTION_USE_NSIS=OFF
  -DOPTION_TOOLS_ONLY=OFF
  -DOPTION_DOCS_ONLY=OFF
  -DOPTION_ALLOW_INVALID_SIGNATURE=OFF
  -DOPTION_LINE_IN_DOXYGEN_WARNINGS=ON
  -DOPTION_SURVEY_KEY=
  -DOPTION_DOXYGEN_WARN_FILE=
  -DOPTION_DOXYGEN_GS_WARN_FILE=
  -DOPTION_DOXYGEN_AI_WARN_FILE=
/usr/bin/cmake --build $BUILD_ROOT --parallel $P0_JOBS
ctest --test-dir $BUILD_ROOT -N --show-only=json-v1
ctest --test-dir $BUILD_ROOT --output-on-failure --no-tests=error --timeout 300 --output-junit $ARTIFACT_ROOT/test-results/ctest-results.junit.xml
/usr/bin/cmake --install $BUILD_ROOT
$INSTALL_ROOT/games/openttd -g -v null:ticks=128 -s null -m null -b null -I OpenGFX -Q -x
```

The wrapped presentation above is one argument array per operation; spaces in
flag values are part of single arguments. The scripts do not pass these arrays
through `eval` or store them as one shell command string. The exact canonical
arrays are also frozen in
`oracle/manifests/baseline/build-relwithdebinfo.json`, and the build stage
compares its observed configure projection against that file before compiling.

## Reproducibility claim boundary

Two separate clean source-equivalent configurations, build roots, and install
roots must produce equal:

1. source identity;
2. configuration identity;
3. 99-test inventory;
4. 99-test results;
5. runtime version output;
6. OpenGFX identity; and
7. 128-tick null-backend smoke behavior.

Both executable SHA-256 values are recorded. Binary byte identity is measured,
not assumed. A mismatch requires retained binaries and `diffoscope` or an
equivalent inspection before explanation. Unless exact bytes match, the only
permitted claim is “behaviorally reproduced under the frozen profile.” A
surviving pre-P0 executable was observed at SHA-256
`2c68071605aa223e156118b3f6ba5cc600fd3235936d5eb6a4c86045d30f9ec5`;
that diagnostic is explicitly nonauthoritative and does not satisfy either
clean-build run.

Other caveats are:

- `/workspace` is not guaranteed to survive instance recycle or destruction;
- absolute build, install, artifact, user, host, PID, and wall-clock values are
  diagnostics, not canonical identity;
- Ubuntu security updates may change package versions and must fail profile
  comparison until reviewed;
- an available old cache, installed binary, or content directory cannot replace
  current command/output evidence;
- smoke success never substitutes for all 99 upstream tests;
- `ci-smoke` never satisfies the `local-release` closure gate.

## Profile-change process

Any source commit, host/architecture, compiler, linker, generator, CMake option,
dependency version, test name/property, content version/digest, environment
identity value, or command change requires all of the following:

1. open a user-repository change on a non-`main` branch; never submit generated
   work upstream;
2. add evidence explaining the necessity and behavioral risk;
3. update this ADR and every affected strict schema and baseline manifest;
4. update each schema SHA-256 reference after the schema is final;
5. add positive, negative, drift, and fault-injection regression tests for the
   new profile;
6. rerun both clean reference builds, all 99 or deliberately revised tests,
   the headless smoke workload, and every dependent P0 gate;
7. retain old profile evidence rather than rewriting history; and
8. obtain review before merging or describing the profile as supported.

A profile change is never implemented by weakening a schema, accepting an
unknown property, lowering a test count, converting a failure to `SKIP`, or
silently normalizing an authoritative mismatch.

## Consequences

This decision makes reference reconstruction deliberately strict and somewhat
slower. In return, every behavior claim is tied to exact source, tools,
libraries, content, commands, and a committed test inventory. The frozen files
provide reviewable expectations; only generated, digest-bearing clean-run
evidence can advance `PORT-001` to `PASS`.
