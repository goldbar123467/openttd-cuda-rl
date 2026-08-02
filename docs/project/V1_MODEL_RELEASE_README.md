# OpenTTD RL V1 model and evidence

This archive contains the path-neutral V1 combined CNN/MLP ONNX policy, its
content-addressed deployment manifest, 12-case golden corpus, accepted independent
evaluation link, install instructions, licenses, and publication manifest.

It is not a standalone OpenTTD distribution. OpenTTD, OpenGFX, ONNX Runtime, and
all training/CUDA dependencies are deliberately absent. Build the playable source
at tag `v1.0.0` and acquire the pinned dependencies by following the repository's
`docs/project/V1_RELEASE_REPRODUCTION.md` guide.

## Verify

From the extracted archive root:

```bash
sha256sum --check SHA256SUMS
```

The archive root must contain `LICENSE`, `README.md`,
`THIRD_PARTY_NOTICES.md`, `publication-manifest.json`, `SHA256SUMS`, and one
directory under `models/`.

## Install

Copy the complete directory
`models/e41f2016cdb0aaf8da03c6db0149c040e29e455a48adae34e5f77708f641aeb0`
atomically to the playable build's configured `openttd-rl/models/` directory.
Do not rename, merge, or edit package files. The native inference loader checks
the directory name, manifest identity, every payload digest, compatibility
contracts, ONNX input/output signature, and ONNX Runtime 1.28.0 before control.

The model is an inference-equivalent derivative of accepted M10 package
`0334e6a9da8d5b87d48ecdcd859dc3a5be6b1f7913511bf3336f8d3cf1feeeb9`.
Only ONNX `doc_string` and `metadata_props` values were removed to eliminate
export-host paths. Tensor bytes, graph semantics, and all 12 outputs in both the
standalone and in-game adapters remain byte-exact.

## Accepted result

The frozen G12 campaign passed 12 release campaigns, 217 applicable V1
requirements, and zero nonclosed defects. The selected combined policy's
independent final-set mean was 150 delivered passengers and 424 operating profit.
Visible final playback delivered 15 passengers / 90 income on template 07 and 12
passengers / 72 income on template 08.

This is an independent research artifact and does not imply OpenTTD endorsement.
The project and model package are distributed under GPL-2.0-only; third-party
components retain the terms listed in `THIRD_PARTY_NOTICES.md`.
