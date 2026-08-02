# Third-party notices

OpenTTD RL is an independent research project. It is not affiliated with,
endorsed by, or sponsored by OpenTTD, its contributors, or the maintainers of
the dependencies listed below.

The V1 model-and-evidence release archive does not redistribute OpenTTD,
OpenGFX, ONNX Runtime, PyTorch/LibTorch, CUDA, NVIDIA runtime wheels, OpenSSL, or
the ONNX Python package. They are acquired separately from their publishers.
Their names and versions are recorded here because they are required to build,
run, or reproduce the accepted system.

| Component | Accepted version or identity | License | Distribution boundary |
|---|---|---|---|
| [OpenTTD](https://github.com/OpenTTD/OpenTTD/tree/29f808ef0022064e6d9a83c8476d1e0f4686af86) | 15.3 source commit `29f808ef0022064e6d9a83c8476d1e0f4686af86` | GPL-2.0 | Source-integrated target; not included in the model archive. Upstream copyright and `COPYING.md` remain authoritative. |
| [OpenGFX](https://github.com/OpenTTD/OpenGFX/releases/tag/8.0) | 8.0; accepted installed tar SHA-256 `9389bcb0807058c80bd95121e978f05d9ef86b4b1bc3ac2da8da8bb02456043c` | GPL-2.0 | Base graphics used by the accepted builds and the repository screenshot; not bundled in the model archive. |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime/releases/tag/v1.28.0) | 1.28.0 Linux x64 CPU archive SHA-256 `a3e1b79d7bb1bf09696ce675f49e4064e6c81f6202b8225624fff0e93f8d6407` | MIT with upstream third-party notices | Required by playable inference; not bundled. |
| [PyTorch/LibTorch](https://github.com/pytorch/pytorch/tree/v2.13.0) | 2.13.0 / 2.13.0+cu130 | BSD-3-Clause with upstream third-party notices | Training and export dependency; not bundled. |
| [ONNX](https://github.com/onnx/onnx/tree/v1.22.0) | 1.22.0 | Apache-2.0 | Export and publication-sanitization tool; not bundled. |
| [NVIDIA CUDA and runtime libraries](https://developer.nvidia.com/cuda-toolkit) | CUDA 13.0 and the exact wheels in `config/v1/dependency-lock.json` | NVIDIA proprietary terms | Training dependency; never bundled in the model archive. |
| [OpenSSL](https://www.openssl.org/) | Ubuntu 24.04 system OpenSSL 3 | Apache-2.0 | Runtime hashing/TLS dependency; not bundled. |

The screenshot at `docs/assets/openttd-rl-v1-playback.png` is retained acceptance
evidence from an actual OpenTTD 15.3/OpenGFX 8.0 playback. OpenTTD and OpenGFX
visual elements remain under their respective upstream copyrights and licenses;
the OpenTTD RL integration and accompanying documentation are distributed under
GPL-2.0-only.

The full machine-readable acquisition, digest, and non-publication inventory is
in the source tag's
[`config/v1/dependency-lock.json`](https://github.com/goldbar123467/openttd-cuda-rl/blob/v1.0.0/config/v1/dependency-lock.json).
The project license text is in [`LICENSE`](LICENSE), and the conservative
integrated-program boundary is documented in the source tag's
[`ADR 0008`](https://github.com/goldbar123467/openttd-cuda-rl/blob/v1.0.0/docs/decisions/0008-v1-license-publication-and-upstream-boundary.md).
