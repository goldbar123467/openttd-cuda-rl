# Working on OpenTTD RL

## Objective and priorities

Train neural networks that actually make decisions in OpenTTD. The owner is
learning CUDA and PPO; retain understandable C++ training code, measurable GPU
work, and a CPU reference. The long-term research platform pits neural policies,
scripted AIs, and LLMs using MCP against each other in a shared economy.

Read `docs/DEVELOPMENT.md` for the current practical workflow and backlog, and
`GOAL.md` for the broader game scope. User instructions take precedence over
historical milestone documents. Prefer one working vertical slice to expanding
the contract/evidence machinery. Do not rewrite working systems merely to rename
them, introduce a second PPO implementation, or replace C++ with Python training.
Python may orchestrate processes, experiments, plotting, and independent tests.

## What exists

- `training/v1`: C++/LibTorch PPO, structured MLP and CNN policies, trainer service.
- `scripts/v1/m03_bridge_protocol.py`: bounded transport to the native game worker.
- `scripts/v1/run_m07_cpu_ppo.py` and `run_m08_live_architectures.py`: real-game
  rollout collection. Their release entry points require historical binary hashes.
- `training/v2`: scalable/recurrent policy work. M22 campaigns currently use a
  fixed corpus and reward tables, not interactive OpenTTD rollouts.
- `training/dev`: portable development build of existing training components.
- `integration/openttd/patches/15.3`: source integration on pinned upstream.
- `openttd-upstream`: upstream submodule/object repository; keep it pristine.
- `config/v1`, `config/v2`, `evidence`, and `docs/project`: historical contracts,
  provenance, and milestone records. These are not proof of a local reproduction.

## Development boundaries

- Use Linux/WSL2 for the POSIX game bridge and training services. Windows hosts
  the checkout and normal game data. Keep source LF; patches are byte-sensitive.
- Keep dependencies, composed engine trees, builds, and run artifacts outside the
  checkout where practical. `build/`, `runs/`, `.venv/` are ignored fallbacks.
- Never overwrite the user's saves, installed game, or unrelated Python envs.
- Preserve frozen release scripts/records; add a clearly labeled development
  route when host versions differ. Never edit expected hashes to manufacture PASS.
- Every executable experiment must record source revision and dirty state,
  configuration, seeds, device/runtime, and actual outputs. Preserve failed runs.
- CPU-only operation must be explicit. A requested CUDA run must fail clearly
  when unavailable, rather than silently training on CPU.
- Keep credentials and runtime artifacts out of Git. Do not push or publish unless
  requested. Do not commit large model weights or downloaded dependencies.

## RL correctness

- Collect observations, legal masks, rewards, and termination from the environment
  boundary. Never read future state, private opponent state, or evaluation labels.
- Store the behavior policy log probability and the exact sampling mask. Reuse
  both during PPO updates. Distinguish terminal from time-limit truncation for GAE.
- Validate finite losses/gradients, masked sampling, checkpoint/resume behavior,
  and CPU/GPU agreement when changing the training path.
- Keep training, development selection, and held-out evaluation separate. Do not
  use final manifests for tuning, even when they are present in the repository.
- Distinguish synthetic learning, corpus learning, live rollouts, and held-out
  gameplay. A successful smoke run is not evidence of improved playing strength.
- Report game outcomes (profit, delivered cargo, service, invalid actions,
  bankruptcy), baselines, seeds, and uncertainty alongside reward.

## CUDA learning and performance

Support the detected GPU; do not hard-code the historical RTX 5070's `sm_120`.
Start with the existing LibTorch CUDA path. For a custom kernel, document tensor
layout, launch dimensions, memory transfers, numerical tolerance, and CPU oracle.
Profile end-to-end rollout/update time before optimizing. Do not claim GPU speedup
from device utilization alone. Small networks can be faster on CPU.

## MCP and economic experiments

Build MCP as an adapter over the same versioned observation/action interface used
by neural agents, not a privileged game-control path. Keep company identity,
action budgets, simulation ticks, timeouts, legal masks, and public information
consistent across participants. Log action attempts, results, costs, and timing.
Separate model inference latency from simulated economic time. Add multiplayer
only after a repeatable single-company training/evaluation loop works locally.

## Verification and handoff

Use the commands in `docs/DEVELOPMENT.md`. Run relevant native tests for C++/PPO
changes and focused Python tests for orchestration. Use
`bash scripts/v2/verify.sh --tier fast` for the repository's portable checks;
contract/full tiers have additional prerequisites. Run `git diff --check`.
Do not treat skipped live checks as passes or repeatedly run unrelated suites.

At handoff, say what changed, which commands passed or failed, where artifacts
live, and the next concrete blocker. Update the development guide when the
supported workflow changes. Explain material PPO/CUDA design choices briefly so
the owner can learn from the implementation.
