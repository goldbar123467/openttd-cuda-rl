# Netherite reference audit

Research date: 2026-07-29 UTC

Repository: <https://github.com/Infatoshi/netherite>

Pinned public commit: `3ebc6ccb6b9eaf3a5f720dd979987d60db9bf952`

This note records facts from the public repository for use as a methodological
reference in the OpenTTD-inspired C/CUDA RL design. It does not treat Netherite's
claims as independently reproduced benchmarks.

## Identity and public state

- The relevant project is `Infatoshi/netherite`, not Microsoft's unrelated
  Durable Task Netherite engine or a Minecraft item mod.
- Its README describes it as a from-scratch C/CUDA reimplementation of Minecraft
  1.11.2, checked against the Java game, plus a batched CUDA RL environment.
- The public default branch is `master`. At the pinned revision it has three
  public commits, all dated 2026-07-29, no tags, no releases, and no pull requests.
- The checkout contains 1,710 tracked paths: 1,420 under `c/`, 258 under `java/`,
  and smaller `docs/`, `scripts/`, and `tapes/` trees. The largest source groups
  include 314 `.c`, 206 `.h`, 141 `.cu`, 176 `.py`, and 302 `.java` files.
- The repository is public but has no root `LICENSE` or project-wide license
  declaration. The nested `java/Minecraft/LICENSE-new.txt` is a Minecraft Forge
  LGPL notice and does not clearly license the independently written repository
  as a whole. Public visibility therefore must not be treated as permission to
  copy, modify, or redistribute Netherite code.

Evidence:

- [`README.md`](https://github.com/Infatoshi/netherite/blob/3ebc6ccb6b9eaf3a5f720dd979987d60db9bf952/README.md)
- [`AGENTS.md`](https://github.com/Infatoshi/netherite/blob/3ebc6ccb6b9eaf3a5f720dd979987d60db9bf952/AGENTS.md)
- [Public commit history](https://github.com/Infatoshi/netherite/commits/master/)

Confidence: high for repository state at the research date; license interpretation
is a practical engineering warning, not legal advice.

## Actual architecture

The repository uses three principal native trees:

1. `c/magma/`: the playable native product, C simulation integration, a C
   software rasterizer, an optional CUDA software rasterizer, SDL2 presentation,
   a headless/scripted mode, and the RL subtree.
2. `c/mc-sim/`: decomposed gameplay and world-generation kernels with CPU and
   CUDA versions, Java-oracle fixtures, and per-kernel verification drivers.
3. `c/render-opt/`: renderer-kernel experiments and Java/JNI drop-ins described
   by the project as a closed lab rather than the shipped game path.

The batched RL implementation is `c/magma/rl/blaze/`. It exposes a C ABI through
CPU and CUDA shared libraries and a Python `ctypes` wrapper. The CUDA Python path
accepts PyTorch device tensors and passes their `data_ptr()` directly to the
kernels. Its observations include a small semantic camera, depth, edge, scalar,
reward, termination, pose, and optional status outputs. Its current raw action
ABI is 13 doubles per environment and includes motion, look, jumping, attack,
use, crafting, interaction, hotbar selection, and a smelting extension.

Rendering was not simply removed from the whole project:

- Headless RL uses semantic observations and can run with rendering off.
- The human/playable product has a custom triangle-to-pixel rasterizer in C and
  CUDA. SDL2 is limited to window creation, input, and blitting the completed
  RGBA buffer; OpenGL is explicitly banned from the product render path.
- This split is useful for the OpenTTD-inspired project: semantic observations
  should be the training path, while a separate debug renderer can remain for
  humans and parity diagnosis.

Evidence:

- [`c/magma/SPEC.md`](https://github.com/Infatoshi/netherite/blob/3ebc6ccb6b9eaf3a5f720dd979987d60db9bf952/c/magma/SPEC.md)
- [`c/mc-sim/SPEC.md`](https://github.com/Infatoshi/netherite/blob/3ebc6ccb6b9eaf3a5f720dd979987d60db9bf952/c/mc-sim/SPEC.md)
- [`c/magma/rl/blaze/blaze.py`](https://github.com/Infatoshi/netherite/blob/3ebc6ccb6b9eaf3a5f720dd979987d60db9bf952/c/magma/rl/blaze/blaze.py)
- [`c/magma/rl/blaze/blaze_cuda.cu`](https://github.com/Infatoshi/netherite/blob/3ebc6ccb6b9eaf3a5f720dd979987d60db9bf952/c/magma/rl/blaze/blaze_cuda.cu)

Confidence: high for the source-level structure; no benchmark or parity claim was
independently rerun during this lookup.

## Oracle and differential-verification method

Netherite's strongest transferable idea is the verification flywheel:

1. Bootstrap a locally owned Minecraft 1.11.2 Java oracle with JDK 8 and
   ForgeGradle. Decompiled Mojang sources and Mojang-derived texture headers are
   regenerated locally and are documented as uncommitted.
2. Record a versioned tape from the real Java game. A tape contains tick inputs,
   absolute view, post-tick player state, nearby entities, periodic real-game
   frames, configuration metadata, and the repository revision.
3. Replay the same tape through the C implementation.
4. Stop at the first state divergence. Fix that class or add a reproducible open
   divergence; later mismatches are considered contaminated by the first one.
5. Compare frames with numeric pixel and cluster analysis, while keeping the Java
   game—not a C-generated self-golden—as ground truth.
6. Separately require CPU/CUDA self-consistency. The docs correctly state that
   CPU==CUDA proves backend agreement, not correctness against the Java oracle.
7. Run a layered local sweep: unit/oracle tests, CPU/CUDA parity, vectorized-vs-
   scalar checks, canonical tape replay, pixel gates, and RL smoke checks.

For an OpenTTD oracle this maps naturally to a neutral trace containing scenario
metadata, seed, settings, commands, command results, tick-boundary state slices,
canonical state hashes, rewards/termination, and optional diagnostic frames. The
new implementation should replay that neutral trace through both CPU and CUDA.

Evidence:

- [`c/magma/VERIFY.md`](https://github.com/Infatoshi/netherite/blob/3ebc6ccb6b9eaf3a5f720dd979987d60db9bf952/c/magma/VERIFY.md)
- [`scripts/bootstrap_oracle.sh`](https://github.com/Infatoshi/netherite/blob/3ebc6ccb6b9eaf3a5f720dd979987d60db9bf952/scripts/bootstrap_oracle.sh)
- [`scripts/bootstrap_assets.sh`](https://github.com/Infatoshi/netherite/blob/3ebc6ccb6b9eaf3a5f720dd979987d60db9bf952/scripts/bootstrap_assets.sh)
- [`netherite_sweep.sh`](https://github.com/Infatoshi/netherite/blob/3ebc6ccb6b9eaf3a5f720dd979987d60db9bf952/netherite_sweep.sh)

Confidence: high for the documented procedure.

## What is complete and what remains open

The README's short description is broader than the repository's own acceptance
status. `docs/GATES.md` defines four gates:

- Game quality: open. A 3,617-tick physics tape reportedly has no physics
  divergence, but the documented full spawn-to-End human session has not been
  completed cleanly, pixel residuals remain, and `OPEN_DIVERGENCES.md` lists
  current renderer, content, entity, and scenario gaps.
- RL: the core spawn-to-torch target is reported met, with CPU/oracle and
  CPU/CUDA checks reported green. Real-game transfer is imperfect and varies by
  seed.
- Performance: batched throughput and a sub-one-hour training target are
  reported met on an RTX PRO 6000. The documented 60 FPS at 1080p rendering pin
  is not met: the repository reports about 35.93 FPS for its CUDA renderer and
  4.51 FPS for its CPU renderer in its pinned local measurement.
- Operations: the one-command verification sweep is reported shipped, but its
  quick mode may mark known-broken or artifact-dependent checks as `SKIP`.

The product contract itself begins with: “target contract, not a claim that the
current binary implements every item.” It narrows Minecraft to a speedrun/RL
surface: survival, single-player, in-memory episodes, no saves, no networking,
no redstone/rails/audio, and a constrained entity and content set.

Therefore the accurate takeaway is not “Minecraft was ported exactly one-to-one.”
It is: a deliberately scoped Minecraft-compatible simulation was built around
an aggressive oracle/tape/differential workflow, with mature CUDA batching and
substantial but explicitly unfinished full-game and pixel parity.

Evidence:

- [`docs/GATES.md`](https://github.com/Infatoshi/netherite/blob/3ebc6ccb6b9eaf3a5f720dd979987d60db9bf952/docs/GATES.md)
- [`c/magma/PRODUCT.md`](https://github.com/Infatoshi/netherite/blob/3ebc6ccb6b9eaf3a5f720dd979987d60db9bf952/c/magma/PRODUCT.md)
- [`c/magma/OPEN_DIVERGENCES.md`](https://github.com/Infatoshi/netherite/blob/3ebc6ccb6b9eaf3a5f720dd979987d60db9bf952/c/magma/OPEN_DIVERGENCES.md)

Confidence: high that these are the project's own stated statuses; medium for the
reported numerical results because they were not independently reproduced.

## Lessons to adopt for the OpenTTD-inspired project

Adopt:

- A pinned reference version and immutable scenario/configuration metadata.
- A black-box command/tick trace and first-divergence debugging loop.
- A CPU reference backend before a CUDA batch backend.
- Explicit proof that CPU==CUDA is separate from proof against the reference.
- One authoritative tick function shared by human, scripted, and RL modes.
- Semantic, renderer-independent observations for high-throughput learning.
- Deterministic masked reset from device-resident snapshots.
- Layered gates with failures distinct from unavailable-artifact skips.
- Narrow, task-driven content scope and explicit non-goals.
- A living divergence ledger with a minimal reproduction for every known gap.

Do not copy blindly:

- Do not copy Netherite source: no clear project-wide reuse license is present.
- Do not call a scoped vertical slice a complete one-to-one port.
- Do not hard-code one CUDA architecture (`sm_86` or `sm_120`) as the only build;
  produce a portable architecture policy and CPU fallback.
- Do not make visual pixel parity an MVP dependency for a transport-management RL
  environment; prioritize simulation state, action results, economy, routing, and
  semantic observations.
- Do not permit `SKIP` to satisfy a release gate unless the profile explicitly
  declares that gate non-applicable.
- Do not expose source-derived OpenTTD implementation detail to an independently
  licensed clean-room implementation team without a legally reviewed specification
  and evidence boundary.

## Bottom line

Netherite validates the engineering pattern the user described, but with two
corrections: it retains custom rasterization for human/pixel verification, and its
own documents say exact full-game parity is unfinished. Its most valuable precedent
for this project is the Java-oracle -> versioned tape -> C replay -> first divergence
loop, combined with a CPU reference, a batched CUDA RL backend, direct device-tensor
interop, and explicit acceptance gates.
