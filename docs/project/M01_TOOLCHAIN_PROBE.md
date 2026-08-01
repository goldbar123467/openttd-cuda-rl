# M01 Reproducible Toolchain-Probe Evidence

- Component result: `PASS`
- M01/G01 result: `PASS` (closed by `G01_GATE_REPORT.md`)
- Date: 2026-07-31
- Profile: `ubuntu-24.04-wsl2-x86_64-cuda13`
- Probe identity:
  `832f1faf8c4927f148bd8933dd43873ef06068afcbeff621481275fb4e6acd3c`

## Proven toolchain and dependency closure

The fail-closed runner at `scripts/v1/toolchain_probe.sh` creates a new owner-only
artifact root and delegates to `scripts/v1/run_toolchain_probe.py`. It has no
acquisition or network mode. Before using any external binary, it revalidates the
strict dependency lock, the lock-schema digest, the complete archive inventory,
all 25 sizes and SHA-256 values, and all six extraction records.

| Component | Accepted value and validation |
|---|---|
| Host | Ubuntu 24.04, x86_64, recorded CPU and GPU inventory |
| C/C++ | GCC/G++ 13.3.0; C++20; warnings are errors for owned native sources |
| Build tools | CMake/CTest 3.28.3 and Ninja 1.11.1 |
| CUDA | nvcc 13.0.88, cuobjdump 13.0.85, GPU compute capability 12.0 |
| CUDA images | compiler command contains `sm_120` real and `compute_120` virtual targets; cuobjdump finds one cubin and one PTX image |
| LibTorch | 2.13.0+cu130, CUDA device execution, C++11 ABI 1, CPU/CUDA parity, and CUDA autograd |
| NVIDIA runtime | cuDNN 9.20.0.48, cuSPARSELt 0.8.1, NCCL 2.29.7, and NVSHMEM 3.4.5 |
| Exporter | fresh Python 3.12 environment containing exactly 17 required locked distributions installed with `--no-index --no-deps` |
| ONNX | byte-fixed opset-18 `Add`/`MatMul`/`Relu` probe graph |
| ONNX Runtime | 1.28.0 CPU ABI/provider plus checked graph names, shapes, values, and tolerance |
| Native closure | every `ldd` dependency resolved; only sorted SONAMEs enter canonical output |

CMake package discovery is explicit for CUDA Toolkit 13.0.88 and `CUDA::cudart`,
exact LibTorch 2.13, all four locked NVIDIA runtime headers/libraries, and the
locked ONNX Runtime include/library pair. LibTorch 2.13 embeds Kineto symbols in
`libtorch_cpu.so` while its upstream config still searches for a standalone
library; the probe declares the bundled symbol provider during discovery and
removes the duplicate link entry. LibTorch's own `TORCH_CUDA_ARCH_LIST` is set
while its package loads, after which project CUDA targets restore the exact CMake
real/virtual architecture pair. The final configuration and build logs contain
no warnings.

## Tests and deterministic failure behavior

The runner discovers exactly these four CTests and rejects a missing, renamed, or
additional test:

```text
v1-cuda-sm120-real-ptx
v1-libtorch-cpu-cuda-abi
v1-onnxruntime-cpu-abi
v1-onnxruntime-opset18-graph
```

All four pass. Ten focused runner tests additionally cover exact-version drift,
missing executables, malformed GPU inventory, incomplete CTest inventory, absent
real/virtual CUDA targets, CUDA image drift, unresolved runtime libraries, wheel
metadata/version drift, canonical identity determinism, and overwrite rejection.

Every subprocess writes a named retained log. A nonzero command, warning from the
owned native configure/build, missing dependency, version mismatch, digest drift,
unexpected test inventory, unresolved shared object, wrong GPU capability, wrong
ONNX graph digest, or wrong CUDA image terminates the run with an explicit
`V1_TOOLCHAIN_PROBE=FAIL` diagnostic. Failed roots are not overwritten or silently
reused.

## Double-run reproducibility evidence

Two completely new artifact roots were used:

```text
/home/thecl/.codex/artifacts/openttd-rl/m01-toolchain-probe-runner-20260731-e
/home/thecl/.codex/artifacts/openttd-rl/m01-toolchain-probe-runner-20260731-f
```

The path-independent JSON manifest and human report compare byte-for-byte. The
exported model and all three native executables also compare byte-for-byte:

| Artifact | SHA-256 in both roots |
|---|---|
| `toolchain-probe.json` | `cce25d7d2dea9e09111a1905d8e29e21e557e1874618e8e3e592dd2827e053de` |
| `toolchain-probe.txt` | `2569f716be647313c46fea3b973d99349000619b03e4fb93110554306f910fd2` |
| `probe-model.onnx` | `2d1bbd70474ae0eae9b97b3349b1285d09b8bca577487a67c24823cdbdc6b31d` |
| `v1_cuda_probe` | `5017132bc8a14819453a0f6f9d7cb4331a95fdcfe587d3e49c15132278bf59ac` |
| `v1_libtorch_probe` | `5fe3ad68df08ae45b928ae388f1b055a4d9ef78d4770a4769d8fb80deaa359f2` |
| `v1_onnxruntime_probe` | `4d9d137be410ceb3a25393c7fadddedc287b85762ef9af680d3effcba93332a0` |

During repeat validation, nvcc was found to retain a process-specific temporary
filename in the CUDA executable's local ELF symbol table. The Release probe does
not need local symbols, so its final link strips that table. This removes the
source of artifact variance; it does not normalize or conceal a changed binary
afterward.

Canonical outputs contain no absolute path, artifact-root name, timestamp, or
duration. Retained diagnostic/build logs are intentionally noncanonical and may
contain their owning root's absolute paths.

## Reproduction

Choose a new absolute output path and name the already-validated offline cache:

```bash
./scripts/v1/toolchain_probe.sh \
  --artifact-root /absolute/new/artifact/path \
  --cache-root /absolute/dependency/cache \
  --tools-python /usr/bin/python3.12
```

The command refuses an existing artifact root, a relative/missing cache, or a
relative/non-executable tools Python. It emits deterministic
`toolchain-probe.json` and `toolchain-probe.txt` files only after every gate passes.

## Boundary

This closes the toolchain-probe-runner portion of `M01`; it does not independently
pass `G01`. The required clean builds and remaining profile/resource/provenance
evidence subsequently passed and are recorded in
[`M01_OPENTTD_BUILD_REPRODUCIBILITY.md`](M01_OPENTTD_BUILD_REPRODUCIBILITY.md).
The complete audit is `G01_GATE_REPORT.md`.
No OpenTTD feature, bus scenario, environment, PPO, production ONNX pipeline, or
`M02` implementation is claimed here.
