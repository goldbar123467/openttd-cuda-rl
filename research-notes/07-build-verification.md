# Local build and test verification

Date: 2026-07-29 UTC. Source: `/workspace/openttd-upstream` at
`29f808ef0022064e6d9a83c8476d1e0f4686af86`, branch `master`.

## Commands and result

```sh
cmake -S /workspace/openttd-upstream \
      -B /workspace/openttd-build \
      -G Ninja \
      -DOPTION_DEDICATED=ON \
      -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build /workspace/openttd-build --parallel 8
ctest --test-dir /workspace/openttd-build --output-on-failure
```

- Configuration and the 902-step initial build completed successfully with GCC
  13.3.0 and CMake 3.28.3. Reconfiguration after adding compression libraries
  rebuilt 510 affected targets and succeeded.
- `ctest` registered 98 tests. Final result: **100% passed, 0 failed**, total
  reported test time 3.97 seconds.
- The test count comprises 94 Catch2-style/unit cases and four executable-driven
  Squirrel regression suites (`regression_regression`, `regression_stationlist`,
  `regression_gs`, and `regression_gs_compat`).
- One compiler warning was observed in `src/road_gui.cpp`: GCC reported that local
  `started` in `BuildRoadToolbarWindow::OnClick` may be used uninitialized. This is
  build output, not a confirmed runtime defect; no conclusion beyond the warning
  is supported. **Confidence: High.**

## Dependency observations

- The first configuration succeeded without `liblzma` and `liblzo`, consistent
  with the optional/encouraged dependency treatment in `COMPILING.md`, but CMake
  warned that omitting `liblzma` is strongly discouraged.
- The compiled unit tests passed in that configuration, while all four regression
  suites initially failed before execution because no graphics base set was
  installed. This confirms the `README.md` statement that OpenTTD needs additional
  graphics data even when the test runs use the null video driver.
- Installing official OpenGFX 8.0 removed the graphics-set error, but regression
  output was still empty. Running the generated command directly exposed the
  underlying load failure: `Loader for 'lzma' is not available` when opening the
  supplied `test.sav` fixtures.
- Installing `liblzma-dev` and `liblzo2-dev`, then reconfiguring/rebuilding, made
  all four regression suites pass. For a useful developer/test build, treating
  LZMA and a graphics base set as practical requirements is more accurate than
  saying all libraries are optional.
- Doxygen, Breakpad, and GRFCodec were not found. They were not required for this
  dedicated build or the registered tests. PNG, zlib, curl, SSE, threads, LZMA,
  and LZO were detected in the final build.

## OpenGFX acquisition and integrity

The graphics set was obtained from the official URL linked by `README.md` and the
official download page:

```text
https://cdn.openttd.org/opengfx-releases/8.0/opengfx-8.0-all.zip
```

The archive matched the official SHA-256 published at
`https://www.openttd.org/downloads/opengfx-releases/latest`:

```text
43a0c1dabf39cb865394f3a6cc36d4da5c10ecfaaf55652043104806810903be
```

The archive's `opengfx-8.0.tar` contents were extracted beneath the build
`baseset/` directory. This is a local test dependency and is not part of the
upstream Git checkout.

## Regression command evidence

`cmake/scripts/Regression.cmake` launches the built executable with:

```text
-x -c regression/regression.cfg -g <fixture>/test.sav
-snull -mnull -vnull:ticks=30000 -d script=2 -Q
```

It captures output, normalizes platform-dependent pointer/timestamp/log syntax,
compares the result line-by-line to each fixture's `result.txt`, and fails on
unexpected output or generated crash logs. This verifies broad AI/GameScript API
behavior against fixture output; it is not evidence that all gameplay subsystems,
rendering, networking, or save compatibility are covered.

## Scope and reproducibility caveats

- This was a Linux dedicated build, so it does not verify SDL/OpenGL GUI backends,
  sound/music drivers, packaging, or Windows/macOS/Emscripten compilation.
- It verifies the pinned commit only. The default branch moves; future results
  require recording the new commit and dependency versions.
- The build directory and downloaded OpenGFX are outside the upstream checkout.
  `git -C /workspace/openttd-upstream status --short` remained empty after the
  verification.

