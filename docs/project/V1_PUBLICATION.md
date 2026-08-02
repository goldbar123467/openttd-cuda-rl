# Version 1 publication guide

## Release boundary

M13 turns the already accepted M12/G12 system into a reviewed public artifact. It
does not change the frozen V1 environment, trainer, model selection, evaluator,
or playable controller. The GitHub release contains a deterministic
model-and-evidence archive and its checksums; the repository tag supplies source.

The archive includes exactly:

- the project GPL-2.0-only license and third-party notices;
- a path-neutral release README and canonical publication manifest;
- SHA-256 checksums; and
- the five-file content-addressed combined ONNX package.

It excludes OpenTTD source and binaries, OpenGFX, ONNX Runtime, LibTorch, CUDA,
NVIDIA wheels, raw trajectories/checkpoints, and private experiment state. Those
dependencies remain available from their publishers under their own terms.

## Privacy repair and model provenance

The accepted M10 ONNX file contained exporter stack-trace metadata with absolute
host paths. M13 preserves that accepted package as private evidence and derives a
publication package by recursively removing only ONNX `doc_string` and
`metadata_props` fields. Two independent sanitizations produce identical bytes.
ONNX validation passes, graph semantics are unchanged, and all 12 golden cases
are byte-exact against the accepted package in both standalone and in-game
adapters.

| Identity | SHA-256 |
|---|---|
| Accepted M10 package | `0334e6a9da8d5b87d48ecdcd859dc3a5be6b1f7913511bf3336f8d3cf1feeeb9` |
| Accepted M10 ONNX | `10df689ccc6d1cb7f2e98f05f0474f72577cd9328a4589e3b1c7167bcbf08b5b` |
| Publication package | `e41f2016cdb0aaf8da03c6db0149c040e29e455a48adae34e5f77708f641aeb0` |
| Path-neutral ONNX | `1f43d430c7fe5c58f4d4e5c9688c4d8a92aef3c82cf999f6dc7c228c9c403d29` |

The publication manifest explicitly licenses the original project model artifact
as GPL-2.0-only and retains the complete source-package and M12 evidence chain.

## Quick source verification

On Ubuntu 24.04 x86_64:

```bash
bash scripts/v1/setup_and_verify.sh --bootstrap
```

This initializes the pinned OpenTTD submodule, repairs missing apt-provided quick
check dependencies, runs full project traceability and document lint, validates
M12/M13 contracts, runs ShellCheck and Bash syntax checks, compiles tracked Python
sources, and checks Git whitespace. It does not download CUDA/LibTorch or rerun
the 6.7 GiB G12 training/playback campaign.

## Canonical publication gate

The owner-only gate requires the retained accepted M10 package, accepted final
M12 manifest, pinned ONNX 1.22 exporter Python, native ONNX evaluator, a clean
`main` synchronized with `origin/main`, `gitleaks`, and a new output directory:

```bash
python3 scripts/v1/build_v1_publication.py \
  --repo-root /absolute/work/openttd-rl \
  --source-package /absolute/artifacts/m10/packages/0334e6a9da8d5b87d48ecdcd859dc3a5be6b1f7913511bf3336f8d3cf1feeeb9 \
  --m12-manifest /absolute/artifacts/m12/v1-release-manifest.json \
  --exporter-python /absolute/exporter-environment/bin/python \
  --deployment-evaluator /absolute/build/training/m10_onnx_evaluator \
  --artifact-root /absolute/artifacts/m13-publication
```

The gate regenerates the sanitized package twice, proves byte-exact runtime
equivalence, builds the archive twice, rejects unsafe tar members/symlinks,
scans every staged byte for host paths and credential markers, runs repository
secret scanning, validates canonical manifests and checksums, and accepts only
byte-identical archives. `publication-gate-report.json` and the archive checksum
are the release authority for the tagged commit.

## Claims and nonclaims

Verified claims may cite M12's 12 passing campaigns, 217 applicable V1
requirements, zero nonclosed defects, the selected policy's 150-passenger / 424
operating-profit independent mean, and the two visible final playback outcomes.

Do not claim that the archive contains a ready-to-run OpenTTD executable, supports
hosts beyond Ubuntu 24.04 x86_64, proves general OpenTTD competence, supports
post-V1 transport systems, or is official/endorsed OpenTTD software.
