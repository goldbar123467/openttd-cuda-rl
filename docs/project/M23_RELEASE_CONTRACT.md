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

The schema, semantic validator, and 26 mutation tests pass. No checkpoint copy,
ONNX graph, package ID, equivalence result, visible campaign, clean-root result,
release manifest, tag, or V2 release has yet been accepted. The next work is the
deterministic two-architecture exporter and native/standalone golden harness.
