# Gate 0 Preflight Evidence

- Capture date: 2026-07-30 UTC
- Capture status: credential-safe transcription of the mandatory pre-edit checks
- Initial outer commit: `58895696c8a75eda2fac2ae553654ba4398f5cda`
- P0 branch after isolation: `port/p0-oracle-contract`

## Mandatory command results

| Command | Credential-safe result |
|---|---|
| `pwd` | `/workspace/openttd-cuda-rl` |
| `git status --short --branch` | Before branch creation: `main...origin/main`; untracked handoff, P0 contract, and Jupyter checkpoint directory. After isolation: `port/p0-oracle-contract` with the same preserved user files. |
| `git rev-parse HEAD` | `58895696c8a75eda2fac2ae553654ba4398f5cda` |
| `git remote -v` | fetch and push remote `git@github.com:goldbar123467/openttd-cuda-rl.git` |
| `git submodule status --recursive` | `29f808ef0022064e6d9a83c8476d1e0f4686af86 openttd-upstream (heads/master)`; leading status character is a space, meaning the gitlink matches |
| `git -C openttd-upstream status --short --branch` | detached `HEAD`; no modified or untracked files |
| `git -C openttd-upstream rev-parse HEAD` | `29f808ef0022064e6d9a83c8476d1e0f4686af86` |
| `cmake --version` | 3.28.3 |
| `ctest --version` | 3.28.3 |
| `ninja --version` | 1.11.1 |
| `gcc --version` | GCC 13.3.0, Ubuntu package build |
| `g++ --version` | G++ 13.3.0, Ubuntu package build |
| `clang --version` | unavailable at Gate 0; required LLVM tooling must be acquired and pinned before static/sanitizer/fuzz gates |
| `python3 --version` | Python 3.12.3 |
| `uname -a` | Linux x86-64, kernel 6.8.0-110-generic; hostname omitted as nonauthoritative |
| `cat /etc/os-release` | Ubuntu 24.04.4 LTS (Noble Numbat) |
| `nvidia-smi` | NVIDIA driver 580.126.20; GeForce RTX 5070; reported CUDA capability 13.0; no running GPU process |
| `nvcc --version` | CUDA compiler 13.0, build 13.0.88 |

GPU and CUDA data is diagnostic only in P0. No driver, CUDA metapackage, kernel
module, or GPU implementation was installed or modified.

## Repository and publication inspection

Read-only GitHub metadata reported:

- `nameWithOwner`: `goldbar123467/openttd-cuda-rl`;
- `defaultBranchRef.name`: `main`;
- `isPrivate`: `false`;
- `viewerPermission`: `ADMIN`.

No visibility change was attempted. The remote branch
`port/p0-oracle-contract` did not exist before branch initialization.
Authentication token values and authentication-file contents were neither read
nor recorded.

## Workspace safety

`vast-capabilities` reported `workspace_is_volume: false`. Atomic pushes are
therefore required after valuable milestones. The same manifest reported NVIDIA
driver maximum CUDA 13.0, installed compiler toolkit 13.0, compute capability
12.0, and minimum CUDA wheel generation 12.8. These values do not authorize a
CUDA P0 backend and do not enter authoritative experiment identity.

The complete 441-line instance guide was read from `/workspace/AGENTS.md`; its
SHA-256 is `06914e8fe301bee48b4c9731a35f963a51e7449e9bf3eabd1c761029b221db74`.
`/etc/vast-agents-guide.md` was byte-identical during preflight.

## Authority inputs read

| File | Lines | SHA-256 |
|---|---:|---|
| `NEXT_STAGES_IMPLEMENTATION_HANDOFF.md` | 1,383 | `663096b12c8e53b2fce550161385fdb67f25404d47262acf4f0f23d5209834e0` |
| `OPENTTD_P0_ORACLE_CONTRACT_AGENT_PROMPT.md` | 3,948 | `8421e6555d9c6f6671862261096010f5c25e23349adb947ba9ab22af5b2c67f2` |
| `OpenTTD_CUDA_RL_REVERSE_ENGINEERING_REPORT.md` | 2,896 | `534a835e4ad788833f629d82fc8690302bd8d65050e3644081e129a746ec6443` |
| `research-notes/00-repository-metadata.md` | 68 | `72ba9a77626613d2bda8896b47ebd1660432a515dee9929aa85296e5fe142bb9` |
| `research-notes/01-repository-build.md` | 371 | `73b7f787434cc90656b3c1e3ba4c7e03f46e89af8324a31ceb6c9412b5ca47ed` |
| `research-notes/02-docs-legal.md` | 427 | `25ee61ea6e1fe94b5f7de44a4253e62150fd2c8935b7664fa0e3b5f5f73ad265` |
| `research-notes/03-gameplay-sim-path.md` | 912 | `64bf11ea8e6cab6e6ca46eb13658284a213f2d325d480d123c8621ceaf1a307f` |
| `research-notes/04-end-to-end-workflow.md` | 149 | `ae9fc8b73797016f48c77b7f9278636508112bd0fdbc6b6a78d1612b904fbd82` |
| `research-notes/05-clean-room-cuda-mvp.md` | 725 | `ed8ce7c2609e273a5ea5fdae61df71e979c398ba6b8c547f4a395f9c40468553` |
| `research-notes/06-ui-persistence-render.md` | 792 | `bfaa434fc96c8e4a87f29099007c82abb9308eb7cce4d266dc29a027a9ab6d91` |
| `research-notes/07-build-verification.md` | 96 | `6feb6b7f611b38f8e3aed1cbf6e658c69125c22c8312a752c242939d730be93e` |
| `research-notes/08-mvp-product-audit.md` | 988 | `f03f8a9ed537e3367628d9d1ccf37c0f7f02da3dd1467fff78627e4e8665f182` |
| `research-notes/09-verification-audit.md` | 104 | `0a51f7818e51e5e0e83026cde1137cf5127b4ce924454a51de4a974c81cb98d6` |
| `research-notes/10-netherite-reference.md` | 188 | `c2555b640971115608cbeeb8b0cde833c84ab1a6f96f65dc7e8a5648a505c93b` |

## Credential and generated-artifact inspection

The inspection covered:

- tracked file inventory with `git ls-files`;
- untracked and ignored status with `git status --ignored --short`;
- tracked/ignored overlap with `git ls-files -ci --exclude-standard`;
- repository-local file inventory excluding `.git` and the pinned submodule;
- filename-only searches for common private-key, GitHub token, AWS access-key, and
  Google API-key signatures in tracked and planned files;
- staged content before publication, performed separately at the push gate.

No credential signature was found. No ignored file was already tracked. One
Jupyter checkpoint duplicated the handoff; it is preserved as unrelated user work
and ignored by `.gitignore`, not deleted. Environment files, caches, generated
builds, profiler output, and `.p0-artifacts/` are ignored.

The initial filename-only signature search reported no match. After installing the
signed Ubuntu `gitleaks` package, a no-Git recursive scan reported four
`generic-api-key` heuristic findings, all inside two immutable files in the public
pinned submodule:

- `openttd-upstream/src/network/core/network_game_info.cpp` (two findings);
- `openttd-upstream/src/tests/test_network_crypto.cpp` (two findings).

These are public source/test material at the recorded OpenTTD commit, not outer
repository credentials, and the outer commit contains only the unchanged submodule
gitlink. They are retained as classified scanner false positives rather than
silently baselined. The publication scan uses `gitleaks protect --staged --redact`,
which reported no leak in the exact staged outer-repository content. `gitleaks` is
recorded by its Ubuntu package identity `8.16.0-1ubuntu0.24.04.3` because that
package's CLI version string is noninformative. ShellCheck `0.9.0-1` was installed
from the same signed Ubuntu archive for forthcoming Bash gates.

Secret scanning is defense in depth rather than proof that arbitrary text cannot
contain a secret. Every push repeats the staged scan and blocks on any positive
finding; scanner matches are classified by path and rule without printing the
matched value.

## Gate 0 disposition

All read-only preflight, authority, publication, scope, and branch-isolation checks
passed. The reviewed documentation commit was pushed and independently resolved
from the remote as recorded in `push-proof.md`; Gate 0 is `PASS`. No source-derived
instrumentation or later-phase implementation began before that push.
