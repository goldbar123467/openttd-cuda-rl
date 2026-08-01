# ADR 0011: Select LibTorch CUDA training and ONNX Runtime CPU deployment

- Status: Accepted, amended 2026-07-31 before acquisition; ABI probes required by `G01`
- Date: 2026-07-31
- Applies to: supported V1 host, native models/training, export, and deployment inference

## Context

The production trainer must be C++/CUDA, retain a trusted CPU reference, export
ONNX, and install a normal-game inference path without training dependencies. The
development host observed on 2026-07-31 is Ubuntu 24.04 x86-64 under WSL2 with:

| Component | Observed development value |
|---|---|
| GCC/G++ | 13.3.0 |
| CMake | 3.28.3 |
| Ninja | 1.11.1 |
| Python | 3.12.3, auxiliary only |
| CUDA toolkit/NVCC | 13.0 / 13.0.88 |
| GPU | NVIDIA GeForce RTX 5070, compute capability 12.0, 12,227 MiB |
| NVIDIA driver | 610.88 |

OpenTTD uses C++20. The project needs automatic differentiation, optimizers, CNNs,
serialization, and CPU/CUDA parity without writing a second tensor framework.
ONNX Runtime's CUDA packaging has a different CUDA/cuDNN compatibility cadence;
GPU inference is not needed to satisfy normal-game portability.

## Decision

### Supported profile

1. The first supported development and release-evidence host is Ubuntu 24.04
   x86-64 under WSL2 with NVIDIA GPU passthrough. Native Ubuntu 24.04 and other
   hosts may be added only after the same `G01/G12` matrix passes there.
2. Project/OpenTTD C++ code uses C++20 and GCC 13.3.0 as the baseline host compiler.
   CMake 3.28.3 and Ninja 1.11.1 are the baseline generator tools.
3. Custom CUDA compilation, if profiling justifies custom code, uses CUDA Toolkit
   13.0/NVCC 13.0.88. The build emits code for the declared local architecture and
   a reviewed PTX fallback supported by the selected toolkit; the exact CMake
   architecture expression is accepted only after a compile/load probe.

### Native training backend

4. PyTorch/LibTorch C++ frontend 2.13.0 with its CUDA 13.0 (`cu130`) distribution
   is the native tensor, module, autograd, optimizer, and checkpoint backend.
   Training executables link LibTorch; normal-game binaries do not.
5. The project records the exact acquired archive URL/digest, `_GLIBCXX_USE_CXX11_ABI`
   setting, bundled CUDA/cuDNN/runtime versions, transitive shared libraries, and
   load paths. A C++20 compile/link/load/CPU/CUDA tensor probe and ABI probe are
   mandatory before the dependency is accepted.
6. C++ defines the authoritative architecture IDs, tensor names/shapes, forward
   semantics, PPO update, optimizer state, and native checkpoint. The CPU backend
   remains the correctness oracle.
7. The production CUDA path begins with LibTorch batched model forward/backward and
   PPO optimization. At least one neural/tensor training workload must pass
   CPU/CUDA numerical or statistical parity and show a preregistered throughput or
   time-to-update benefit on the declared hardware. Otherwise `G08` remains open.
   Custom CUDA kernels are added only after profiling identifies a material gap.

### ONNX export and deployment

8. ONNX opset 18 is the initial portable graph target for V1 MLP, CNN, and combined
   actor-critic networks. Unsupported or rewritten operations fail export; they do
   not silently fall back to an embedded non-ONNX runtime.
9. A pinned auxiliary Python 3.12 environment using PyTorch 2.13.0 performs the
   mechanical `torch.export`-based ONNX conversion under control of the C++ export
   application. The converter receives a versioned architecture description and
   named tensors from an immutable C++ checkpoint. It cannot train, select, or
   mutate the accepted model.
10. Export promotion proves that every named tensor was transferred exactly and
    runs golden native-versus-exported outputs. Python is therefore a conversion
    implementation, not the production model or training authority.
11. ONNX Runtime C++ CPU 1.28.0 is the V1 deployment backend for standalone ONNX
    validation and normal-game inference. The exact binary/source archive and
    transitive libraries are pinned and scanned in `G01`.
12. The playable package links only the CPU ONNX inference subset and project
    semantic core. It excludes LibTorch, Python, optimizer/checkpoint training
    state, CUDA toolkit, cuDNN, and CUDA training libraries.
13. ONNX Runtime CUDA inference is explicitly not part of V1. It may be evaluated
    later after a stable CUDA 13 package and its cuDNN/runtime compatibility are
    pinned, but it cannot delay or weaken CPU deployment equivalence.

## Dependency graph

```text
OpenTTD + shared semantic C++20 core
  |-- headless worker: no tensor/trainer dependency
  |-- trainer/evaluator native path: LibTorch 2.13.0 CPU/CUDA
  |-- export orchestrator: immutable checkpoint -> pinned Python converter
  `-- playable/ONNX evaluator path: ONNX Runtime C++ CPU 1.28.0
```

The evaluator may load either the immutable native snapshot for equivalence work
or the deployment package for final scoring; the final accepted evaluation names
which representation it used and never updates weights.

## Rejected alternatives

### Write neural tensors, autodiff, and optimizers from scratch

Rejected because it expands correctness risk without improving the OpenTTD
environment and PPO research objectives.

### Use Python as the trainer and rewrite it later

Rejected because it creates two production algorithms and conflicts with the
C++/CUDA ownership requirement. A narrow pinned export subprocess is permitted by
the project goal and is guarded by exact tensor/equivalence tests.

### Link LibTorch into normal OpenTTD

Rejected because it greatly enlarges the install/runtime surface and makes a
training dependency part of ordinary playback.

### Require GPU ONNX inference in the playable build

Rejected because training supplies the mandatory measured CUDA workload, while
CPU deployment is smaller and avoids coupling playback to CUDA/cuDNN compatibility.

## Verification and change control

`G01` must retain acquisition digests, license inventory, C++/CUDA ABI probes,
dependency closure, and offline repeat-build evidence. A missing 2.13.0 `cu130`
artifact, failed ABI probe, or unsupported compiler combination blocks dependent
work and requires a replacement ADR; it does not authorize an unrecorded version
substitution.

`G08` proves CPU/CUDA forward, loss, gradient/update, checkpoint, memory, and
measured-benefit requirements. `G10/G11` prove ONNX structure and
native/standalone/in-game equivalence.

Primary technical references are the
[PyTorch C++ frontend](https://docs.pytorch.org/tutorials/advanced/cpp_frontend.html),
[PyTorch ONNX exporter](https://docs.pytorch.org/docs/stable/onnx.html),
[ONNX Runtime C++ API](https://onnxruntime.ai/docs/get-started/with-cpp.html), and
[CUDA 13 compiler documentation](https://docs.nvidia.com/cuda/archive/13.0.0/cuda-compiler-driver-nvcc/index.html).

## Amendment record

The initial text named ONNX Runtime 1.26.0 based on an earlier release check. A
fresh official release/API inspection before any dependency bytes were accepted
showed that 1.28.0 was released on 2026-07-25 and is the current stable release.
The CPU deployment choice was therefore amended to 1.28.0 before acquisition or
implementation. No evidence or package was migrated, and the CPU-only deployment
boundary/opset decision is unchanged. The official Linux x64 asset publishes size
9,125,960 bytes and SHA-256
`a3e1b79d7bb1bf09696ce675f49e4064e6c81f6202b8225624fff0e93f8d6407`.
