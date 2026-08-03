# M23 V2 release contract

M23/G23 is the single final V2 release gate. Its machine authority is
[`config/v2/m23-release-contract.json`](../../config/v2/m23-release-contract.json),
validated by
[`scripts/v2/validate_m23_release_contract.py`](../../scripts/v2/validate_m23_release_contract.py)
and its mutation suite. The contract was frozen before any M23 export,
equivalence, visible-playback, reproduction, or publication result.

This document describes the boundary; it is not G23 acceptance evidence. All
nine `V2-RELEASE-*` requirements remain `PLANNED` until their retained artifacts
and complete gate evidence pass.

## Accepted foundation

M23 starts only from accepted G22 commit
`e027ab69a39cbe929db0fddafebbc1696b26e0d7`, the corrected cumulative OpenTTD
15.3 source tree `f8985045f9ba14bad1e46a81cb58fdbb8037f277`, and exact hashes for the
learning contract, corpus, training, qualification, independent follow-up-v2
evaluation, runtime source, and G22 gate report. The M14 competition protocol,
M21 content lock, and V1 M10–M13 package/playback/release/publication contracts
are also byte-bound. G23 must revalidate V1 without modifying its released tag,
package, or behavior.

## Checkpoint and deployment packages

Both learned architectures are release artifacts:

| Architecture | Role | Frozen checkpoint |
|---|---|---|
| `monolithic-generalist-v1` | G22-selected default in-game policy | `03894fd1238b69b6724d82eb441380312be4e8226efa602fa5e43972f7fa9f5f` |
| `specialist-router-v1` | Matched learned comparison | `458b2b1413ca483cb9b061518ce9d80e5e9afc85852a66015d81da07bcc7fd2f` |

Each checkpoint package is an exact seven-file copy of its atomic M22
checkpoint. Every byte count and SHA-256 is frozen, and each content address is
recomputed from the original M22 algorithm. Both packages must load and resume;
neither may be rewritten for publication.

Each deployment package contains exactly `manifest.json`, `model.onnx`,
`golden.jsonl`, `evaluation.json`, `INSTALL.md`, and `MODEL_CARD.md`. The ONNX
graph uses opset 18 and ONNX Runtime 1.28.0 with a batch-only dynamic axis bounded
to 1–32. Its public interface is:

- `public_features`: float32 `[batch,32]`
- `program_mask`: bool `[batch,17]`
- `hidden_state`: float32 `[batch,256]`
- `recurrent_reset`: bool `[batch]`
- `program_logits`: float32 `[batch,17]`
- `program_value`: float32 `[batch]`
- `next_hidden`: float32 `[batch,256]`

Deployment is CPU-only and inference-only. OpenTTD, ONNX Runtime CPU, and
OpenSSL Crypto are allowed; LibTorch, Python, CUDA, optimizer, and trainer
dependencies are forbidden from the installed runtime closure.

## Three-runtime equivalence

The native LibTorch CPU model, standalone ONNX Runtime CPU adapter, and the
source-integrated in-game ONNX Runtime adapter must agree for both
architectures. The frozen corpus has 24 cases per architecture: eight retained
public-final projections, eight recurrent sequence/reset cases, and eight
finite-boundary/mask adversarial cases. It covers batches 1, 8, and 32, every
public mode and climate, four mask patterns, zero and carried hidden state,
mixed row resets, and four-step sequences.

All 144 runtime-case results must pass absolute and relative `5e-5` tolerances
for logits, value, and next hidden state, with exact legal mask and greedy
program. Twenty-eight package, graph, tensor, recurrence, corruption, and batch
mutations must fail before control.

## Visible normal-game boundary

The learned policy selects one legal recurrent high-level program from public
state. Reviewed deterministic program executors then plan and submit normal
OpenTTD construction, vehicle, order, and recovery commands. M23 does not claim
that low-level construction, pathfinding, or vehicle control is end-to-end
learned. Qualification-only state injection and administrative shortcuts are
forbidden in accepted visible play.

Eight preregistered GUI campaigns cover road passenger, road cargo, rail
passenger, rail freight, water, air, multimodal, and company competition across
all four climates, 128-square and 512-by-128 maps, and the admitted AAAHogEx,
KrakenAI2, and NoOpAI roster. Every campaign is required. Accepted evidence must
retain a screenshot, canonical structured log, savegame, and report and prove
owned infrastructure and vehicles, normal orders and movement, positive
delivery and operating income, and active non-control opponents. Save/load must
preserve controller state and the next policy output for at least one campaign
per mode.

The normal-game controller exposes start, stop, pause, one-boundary step,
atomic reload, native game pause, an inspection window, health, and bounded
canonical JSONL logs. Startup incompatibility fails before company control. A
runtime fault retains the game and evidence and permits only the wait program;
it cannot silently substitute another policy or issue construction, vehicle, or
order commands.

## Reproduction and publication

One operator guide must cover prerequisites, clone, build, train, exact resume,
independent evaluation, export, install, visible play, tournament, verification,
and troubleshooting with complete commands. The model card, benchmark,
publication guide, release manifest, artifact index, license, and notices must
content-address every artifact, dependency, result, and retained failure.

Two distinct empty clean clones must run after clone with network disabled and
declared caches validated. They use the same empty canonical symlink path
sequentially with prefix-mapped builds and must match source, native and in-game
binaries, checkpoints, ONNX, package IDs, goldens, equivalence, visible play,
tournament semantics, release manifest, and publication archive at the exact
semantic or byte boundary named by the contract.

Only a clean, origin-synchronized `main` commit that passes all 86 V2
requirements, the complete V2 and unchanged V1 test suites, strict quality
checks, zero nonclosed defects, deterministic archive reconstruction, and asset
round-trip verification may be tagged `v2.0.0`. Published bytes are immutable;
any later change requires a new version.

## Current state

The schema, semantic validator, and 26 mutation tests pass. The first
implementation foundation now includes a deterministic two-architecture
opset-18 exporter, the full native compact-input projection, independent C++ and
Python definitions of the 48-case/580-row golden corpus, an inference-only ONNX
Runtime 1.28.0 adapter, and a deployment-only build with no LibTorch, Python,
CUDA, optimizer, or trainer dependency. Seventeen source and corruption tests
cover the frozen interface, strict checkpoint loading, deterministic export,
case inventory, recurrent reset/carry, malformed binaries, nonfinite outputs,
illegal actions, and build separation.

Two isolated prototype export directories matched byte-for-byte. The
monolithic and specialist graphs have respective SHA-256 values
`c3da3106ece85ec4248698d6d9db35b07dfa7f6ce27194a3bafdf6feb887cbb0`
and `b114616d46631827bf1fda875d99bfe736f540deb57b982e9f4405dc7b7abb07`.
The native golden binary has SHA-256
`caae59eb8465bc225f2d9ea7bfdd8c22350260ecdb41f47fc022fff2fd71f93d`.
The standalone native/ONNX comparison passed all 48 architecture cases and 580
rows with exact legal greedy actions and maximum absolute tensor error
`1.33514e-05`; report SHA-256 is
`7b8b785e6140fb190eb82c40512bd27e659211f83c084293948bd0e1b7b22fa9`.

The next implementation foundation exact-copies both seven-file checkpoint
inventories and constructs both exact six-file deployment layouts. Two builds
from the independent export/golden roots are byte-identical. Their monolithic
and specialist development package IDs are
`50060fd871d3c737b41bb4523748fbaac5047fed106e9ce0a9d1b36c7637f955`
and `d280683090b65eeea8e6cba1ab6ece3ca561a1b1d1708840f8616855ff44ac5a`;
the package-build report SHA-256 is
`d9e533a0c948ec7096017597fb1f4bca6f184fe8da8fe733d39ecd09ee2dfa90`.
The independent Python validator and inference-only C++ loader accept both. The
loader links ONNX Runtime, OpenSSL Crypto, and standard system libraries only.
All 28 frozen rejection labels pass: both validators reject all 24 package,
manifest, graph, and file mutations, while the runtime rejects all four invalid
input/mask/batch requests. Mutation report SHA-256 is
`33b6311b526bdb7fbadd94b982eb5032576c0769418562cd1ee8a1fc5836c906`.
Fifteen package tests independently cover canonical identity, exact inventory,
graph and golden semantics, recurrence, evaluation links, path leakage, and the
C++ load/request boundary.

The source-integrated implementation foundation now applies one bounded patch
to accepted M22 tree `f8985045f9ba14bad1e46a81cb58fdbb8037f277`, yielding
tree `df143cb3ad2ada1023ce63c98ec90f941e48afd8`. It preserves V1 `-A` and
the M03 `-B read_fd:write_fd` route, while an absolute JSON argument selects the
M23 `openttd -B` path. The joint build passed all 98 upstream CTests and its
runtime dependency closure includes ONNX Runtime 1.28.0 and OpenSSL Crypto but
no LibTorch, CUDA, or Python. A network-isolated OpenTTD process validated both
development packages and reproduced all 48 cases/580 rows with exact legal
actions and maximum absolute tensor error `1.33514e-05`. Together with the 48
native and 48 standalone records, all 144 frozen runtime-case results pass; the
standalone and in-game reports differ only in their runtime identity. The
in-game report SHA-256 is
`23f784c7c29580f4faeceda34ba75bef539bb7c46b1664d87e709ba3949b9532`,
and the independently validated foundation report SHA-256 is
`7f3794d75a5b736334fd3a34196a1cc9347a952414dcb64cd6f6898a8af1d67a`.
Fourteen additional tests cover exact patch scope/application, legacy CLI
compatibility, shared recurrent/output comparison, configuration and package
pinning, inference-only build separation, and report rejection mutations.

These are development prototype measurements, not retained G23 evidence. No
checkpoint package, deployment package, package ID, retained three-runtime
result, visible campaign, clean-root result, release manifest, tag, or V2 release has yet been
accepted. All nine `V2-RELEASE-*` requirements remain `PLANNED`. Copied-
checkpoint load/resume, the visible controller/controls, eight campaigns, and
clean-root reproduction must pass before the prototype packages can become
retained G23 candidates.
