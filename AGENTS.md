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
- `scripts/dev/replay_human.py` and `imitate_v2.py`: checkpoint-verified native
  human replay and a separate C++ imitation objective feeding a fresh PPO policy.
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

- **Action semantics must reach the network.** The October 2 human-learning
  experiment found that native `MANAGE_LOAN` borrow and repay candidates had
  bit-identical 32-float feature vectors: their direction parameters were dropped,
  their costs were both zero, and their normalized priorities rounded to the same
  float. More training cannot distinguish identical inputs. Check actual encoded
  tensors for economically distinct actions, not just legal masks or command IDs.
  The opt-in `signed-log-loan-v1` native preprocessing exposes the public loan
  direction in reserved candidate slots 30/31 and binds the change to model
  metadata. Preserve `raw` and `signed-log-v1` archives; fail closed on mismatched
  preprocessing. See the current evidence and qualification status in
  `docs/DEVELOPMENT.md` before reusing a model or claiming financing competence.
  That historical mode fixes loan direction only. The archived input audit also found omitted
  road/stop/depot orientation and route/vehicle distinctions. One demonstrated
  START row ties with a different co-located vehicle's candidate, so greedy row
  accuracy alone can hide an unlearnable semantic distinction. New native
  imitation defaults to `signed-log-actions-v1`: reserved slots 20..31 encode
  all three active public uint32 parameter words as log-scaled byte limbs.
  This preserves vehicle identity, orientation and ordered route endpoints;
  unknown trailing parameters or occupied reserved slots fail closed. Preserve
  the older preprocessing modes and reject mismatched archives. Audit actual
  encoded legal candidate equivalence classes and require unique exact-action
  accuracy with a positive probability margin, including after row permutation.
  Read the current development evidence before claiming learned route choices;
  the human recording still labels only purchases, starts and repayments.
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
- Human command logs are raw intentions until native replay matches a saved
  checkpoint and confirms execution/cost accounting. Use only exact supported
  actions from the legal candidate list at the pre-command state. Keep unsupported
  GUI actions, failed/estimate commands, and gaps out of supervised labels; never
  infer WAIT or unobserved borrowing decisions from them. Human examples train the
  separate imitation objective, never the on-policy PPO rollout buffer. Report
  exact-action accuracy by action type: aggregate loss can hide failed repayments.
- Check imitation retention after PPO on the same training examples, labelled as
  retention rather than held-out accuracy. The October 2 greedy fit reached
  11/11 (including one indistinguishable START pair), but four PPO updates
  retained only 7/11 and lost all four repayment choices. Report
  greedy and sampled gameplay separately: sampled service on three development
  maps coexisted with greedy loan cycling and poor liquidity. Neither successful
  weight import nor service alone establishes sensible debt management. Preserve
  this small baseline before changing rewards, curricula, or training duration.
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
