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

The next practical priority is sustained fleet control while preserving imitation
retention. Check that learned order choices survive bounded PPO updates before
running longer training; repeated purchases and route edits remain unresolved.

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
- `scripts/dev/audit_bus_orders_v2.py` and `live_bus_orders_v2.py`: exact bus-order
  input/semantic audits and bounded unforced continuations of supplied contexts.
- `integration/openttd/patches/15.3`: source integration on pinned upstream.
- `openttd-upstream`: upstream submodule/object repository; keep it pristine.
- `config/v1`, `config/v2`, `evidence`, and `docs/project`: historical contracts,
  provenance, and milestone records. These are not proof of a local reproduction.

## Development boundaries

- Use Linux/WSL2 for the POSIX game bridge and training services. Windows hosts
  the checkout and normal game data. Keep source LF; patches are byte-sensitive.
- Keep dependencies, composed engine trees, builds, and run artifacts outside the
  checkout where practical. `build/`, `runs/`, `.venv/` are ignored fallbacks.
- The parent directory is the user's OpenTTD data directory. Run project commands
  in this checkout; never stage parent contents. Preserve saves, downloaded
  content, AIs, configuration, the installed game, and unrelated Python envs.
  Never read or copy `secrets.cfg` or `private.cfg` for project work.
- Preserve frozen release scripts/records; add a clearly labeled development
  route when host versions differ. Never edit expected hashes to manufacture PASS.
- Every executable experiment must record source revision and dirty state,
  configuration, seeds, device/runtime, and actual outputs. Preserve failed runs.
- CPU-only operation must be explicit. A requested CUDA run must fail clearly
  when unavailable, rather than silently training on CPU.
- Keep credentials and runtime artifacts out of Git. Do not push or publish unless
  requested. Do not commit large model weights or downloaded dependencies.

## RL correctness

- **Action semantics must reach the network.** Historical October 2 audits found
  indistinguishable borrow/repay inputs and a START row tied with another vehicle.
  More training cannot distinguish identical inputs. Generic native imitation
  defaults to `signed-log-actions-v1`: slots 20..31 encode the three public uint32
  parameters as log-scaled byte limbs, preserving target identities and ordering.
  The current bus slice explicitly uses native `orders-v1` observations/actions
  and `signed-log-orders-v2` preprocessing. Family 6 exposes exact insert,
  set-loading, independent copy and delete primitives; Full Load Any is native
  mode 3, distinct from Full Load All. Public state includes stopped status and
  up to four independent canonical station orders; shared or unsupported lists
  fail closed. Categorical operation/load/index features in
  slots 0..11 supplement the parameter limbs without changing the architecture.
  Preserve `raw`, `signed-log-v1`, `signed-log-loan-v1`, `signed-log-actions-v1`
  and `signed-log-orders-v1` behavior and archive bindings; reject mismatched
  preprocessing, observation or action modes. Keep fail-closed checks for unknown
  parameters and occupied reserved slots. Order modes are native-only; ONNX
  export/playback rejects them. Audit actual encoded legal inputs,
  require unique exact choices with margin >1e-6, and repeat after row permutation.
- The verified October 2 bus fit reaches **12/12 unique exact choices**, with no
  input aliases or target ties. Minimum margin is 0.733095; permutation error is
  1.19e-7 and all 12 choices remain unique. This is training-recording accuracy.
  Fresh PPO import is verified with zero updates; retention after later PPO
  learning remains unmeasured for this model.
  See `docs/DEVELOPMENT.md` for commands, failed fits and reproducible artifacts.
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
  The latest bus replay matches manual marker 47 at actual date 1958-08-19:
  12 supported decisions and 27 explicit exclusions. Do not infer a reload or
  supervision from the ambiguous save-preview marker or from unlogged waiting.
- Check imitation retention after PPO on the same training examples, labelled as
  retention rather than held-out accuracy. The older financing imitation run's 11/11
  greedy row accuracy included a START alias; four PPO updates retained only 7/11
  and lost all four repayments. Those are historical results, not the latest bus
  fit. Preserve them when testing rewards, curricula or training duration; a fresh
  weight import alone does not establish retention after PPO learning.
- Report greedy and sampled gameplay separately. Both reproduced the target bus
  sequences and set Full Load Any before starting in two supplied human-recording
  contexts. Roads/depot/stations were supplied; the copy/edit context also supplied
  a running configured bus and a purchased stopped bus. Continued decisions
  overbuy and repeat edits, with duplicate endpoints on some extra buses and
  negative operating profit. Do not claim learned construction, held-out
  generalization or sustained service competence from these exercises.
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
