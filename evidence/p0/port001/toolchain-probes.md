# PORT-001 Toolchain Probe Evidence

- Probe date: 2026-07-30 UTC
- Platform: Ubuntu 24.04.4 LTS, x86-64
- Result: required native analysis capabilities available
- Authority: signed Ubuntu Noble package archives plus compile-and-execute probes

## Frozen package identities

| Package | Version |
|---|---|
| `clang-16` | `1:16.0.6-23ubuntu4` |
| `clang-tidy-16` | `1:16.0.6-23ubuntu4` |
| `clang-tools-16` | `1:16.0.6-23ubuntu4` |
| `llvm-16` | `1:16.0.6-23ubuntu4` |
| `llvm-16-tools` | `1:16.0.6-23ubuntu4` |
| `libclang-rt-16-dev:amd64` | `1:16.0.6-23ubuntu4` |
| `libfuzzer-16-dev` | `1:16.0.6-23ubuntu4` |
| `gitleaks` | `8.16.0-1ubuntu0.24.04.3` |
| `shellcheck` | `0.9.0-1` |
| `reuse` | `2.1.0-1` |
| `licensecheck` | `3.3.9-1ubuntu1` |
| `time` | `1.9-0.2build1` |

The installation transaction used exact package versions with
`--no-install-recommends`. It proposed no removal and installed no CUDA toolkit,
CUDA metapackage, NVIDIA driver, `libcuda`, or kernel module.

## Versioned executable paths

The frozen local profile uses:

```text
/usr/bin/gcc-13
/usr/bin/g++-13
/usr/bin/clang-16
/usr/bin/clang++-16
/usr/bin/clang-tidy-16
/usr/bin/scan-build-16
/usr/bin/llvm-cov-16
/usr/bin/llvm-profdata-16
```

Absolute paths are toolchain diagnostics and local-profile inputs. They do not
enter platform-independent experiment identity as workspace paths.

## Executed probes

Each probe compiled ISO C17 from standard input into a fresh temporary directory,
then executed the resulting binary. All compilers used `-Wall -Wextra -Werror`.

| Capability | Essential compile options | Runtime check | Result |
|---|---|---|---|
| AddressSanitizer | `-fsanitize=address` | allocation/free with leak detection and halt-on-error | PASS |
| UndefinedBehaviorSanitizer | `-fsanitize=undefined -fno-sanitize-recover=all` | bounded unsigned arithmetic with halt-on-error | PASS |
| libFuzzer with sanitizers | `-fsanitize=fuzzer,address,undefined` | two startup executions from an empty corpus | PASS |
| LLVM source coverage | `-fprofile-instr-generate -fcoverage-mapping` | execute, merge profile, report through LLVM 16 tools | PASS |
| Clang-Tidy | versioned executable startup | reported optimized LLVM 16.0.6 build | PASS |
| Clang Static Analyzer wrapper | versioned executable startup | executable resolved; full analysis runs in the static gate | PASS |

The source-coverage probe reported one of one line and one of one function
executed. This proves the profile runtime and tools interoperate; it is not the
later project coverage result.

## Reference diagnostics available before clean reconstruction

The surviving pre-P0 OpenTTD build was used only to orient the clean rebuild:

- CTest JSON inventory count: exactly 99;
- lexically sorted test-name stream SHA-256:
  `5e4fac93bfa5c0f3d3b124eae2485b9d9f5de99118e1041406ea38d4ecdbea6c`;
- build type: `RelWithDebInfo`;
- generator: Ninja;
- assertions: enabled;
- dedicated-only mode: disabled;
- FHS install: enabled;
- executable SHA-256:
  `2c68071605aa223e156118b3f6ba5cc600fd3235936d5eb6a4c86045d30f9ec5`;
- executable size: 404,942,760 bytes;
- `ldd`: every dependency resolved.

These values are hypotheses and comparison inputs. They do not satisfy
`PORT-001` until committed runners reconstruct two clean builds and retain their
own independent manifests and logs.

## Exact diagnostic smoke

The installed diagnostic binary completed with exit code zero under:

```text
openttd -g -v null:ticks=128 -s null -m null -b null -I OpenGFX -Q -x
```

The working content profile contained OpenGFX 8.0. Its installed inner tar has a
different digest from the official distribution ZIP, as expected; it is not
accepted as the acquisition archive. The immutable approved archive is
`https://cdn.openttd.org/opengfx-releases/8.0/opengfx-8.0-all.zip`, whose official
SHA-256 and contract-frozen SHA-256 are both
`43a0c1dabf39cb865394f3a6cc36d4da5c10ecfaaf55652043104806810903be`.

The clean runner must reacquire or reuse only verified official ZIP bytes, validate
archive paths before extraction, record installed-file digests, and repeat the
smoke against both clean install roots. This diagnostic success alone is not a
P0 pass.
