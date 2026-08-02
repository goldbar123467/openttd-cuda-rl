# G13 gate report: public distribution readiness

## Result

`G13: PASS` on 2026-08-02. OpenTTD RL V1 is published at
[`v1.0.0`](https://github.com/goldbar123467/openttd-cuda-rl/releases/tag/v1.0.0)
from the exact clean, synchronized source commit
`cdd39723faf3fdb9b9fc03f4fc4e8733489de5c0`. All eight frozen M13 gates pass,
the GitHub-hosted quality workflow passes, and independently downloaded release
assets are byte-for-byte identical to the accepted outputs.

M13 changes no V1 environment, training, evaluation, or playback semantics. It
closes the license, privacy, reproducibility, archive-safety, repository-surface,
and external-publication work left deliberately outside M12.

## Frozen identities

| Artifact | Identity |
|---|---|
| M13 compatibility | `692e91fde04ae8069e89aa2c363e571a8b59724290f704bdc41b20b72150983c` |
| Release source commit | `cdd39723faf3fdb9b9fc03f4fc4e8733489de5c0` |
| Annotated `v1.0.0` tag object | `b8a5a89d7e0cce15e621537d289e73ab1a823367` |
| Accepted M12 semantic manifest | `4593f177b21c92d0e789118896cc66f7534f1a516f2d73a125f52d0149374a6b` |
| Publication package | `e41f2016cdb0aaf8da03c6db0149c040e29e455a48adae34e5f77708f641aeb0` |
| Path-neutral ONNX | `1f43d430c7fe5c58f4d4e5c9688c4d8a92aef3c82cf999f6dc7c228c9c403d29` |
| Publication manifest semantic identity | `e03a4a919ff77fb1dedac364e8d95fa0a128a06ae3077376ccc92b0d7caa15d8` |
| Publication manifest file | `7462e55677860f74effc745a7d743922fed8acd8e8827876e9e2a85dd9fc89f9` |
| Release archive | `959a24e7786a4a464b0c8d2a79589d541831090524318b040b6e939e1dc73450` (4,776,230 bytes) |
| External checksum file | `d17ae6d738bf2027353110535851a3a0d37071f3e29aca1aad3e2140463cea9b` |
| Publication gate report | `6635bd9fdd918f07fce3baac93d70f2642b530b67b187a49de9b3b7a9562e8dd` |

## Gate closure

| Gate | Accepted result |
|---|---|
| Contract and foundation | Frozen strict schemas, compatibility identity, mutation guards, and all M13 tests PASS |
| Repository surface | Actual playback image, concise evidence-backed README, one-command verification, publication guide, and pinned CI workflow present |
| License and provenance | GitHub detects GPL-2.0; project/model license, third-party terms, dependency omissions, and non-endorsement are explicit |
| Accepted package identity | Exact M10 source package and every publication-package byte are content-addressed and provenance-linked |
| Deterministic archive repeat | Two package derivations and two independently built gzip/tar archives are byte-identical |
| Archive safety | Sorted fixed inventory, zeroed metadata, regular files only, no symlinks/hardlinks/special members, safe paths, and complete checksums PASS |
| Credential and host-path scan | Gitleaks history scan plus staged byte scan PASS; no personal path or credential marker enters the archive |
| Clean-main publication | Local `main == origin/main`, tag resolves to the accepted commit, release assets round-trip exactly, and hosted CI passes |

The accepted source-quality run is
[`30746165828`](https://github.com/goldbar123467/openttd-cuda-rl/actions/runs/30746165828).
It checked out the recursive submodule, installed the declared quick-check
dependencies, and passed 234 project tests, traceability/document lint, M12/M13
contract suites, ShellCheck, Bash syntax, Python compilation, and Git whitespace.

## Privacy repair

The accepted M10 ONNX contained exporter stack-trace metadata with local paths.
The immutable M10 evidence was not changed or published. M13 independently
removed 155 `doc_string`/`metadata_props` values twice, producing identical ONNX
bytes. The sanitizer preserved graph semantics, tensor content, input/output
contracts, and byte-exact outputs for all 12 golden cases in both standalone and
in-game adapters.

## Published boundary

The release archive contains the license, self-contained README, third-party
notices, publication manifest, checksums, and the five-file model/evidence
package. It contains no OpenTTD/OpenGFX source or binary, ONNX Runtime, LibTorch,
CUDA or NVIDIA runtime, raw trajectory/checkpoint, or private experiment state.
The tagged repository is the corresponding source distribution and full
reproduction authority.

With G13 passed, the requested publishable V1 product is complete. No gameplay
expansion is implicitly active; `EXP-001` or any alternative future direction
requires a new explicit contract and compatibility gate.
