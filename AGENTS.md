# Working on OpenTTD RL

## Objective and priorities

Train neural networks that actually make decisions in OpenTTD. The owner is
learning CUDA and PPO; retain understandable C++ training code, measurable GPU
work, and a CPU reference. The long-term research platform pits neural policies,
scripted AIs, and LLMs using MCP against each other in a shared economy.

The October 6 goal is one station/order representation trial, not DAgger yet.
Preserve the ten-game pipeline and merge origin/main locally; do not push.
Implement `signed-log-orders-v3` with the same network/actions/masks, then run
exactly one fresh 186-choice CUDA fit at 256 updates, seed 20261002 and learning
rate 0.0003. Audit all training inputs and game 08, and use the existing frozen
50-case gameplay protocol only if most of the nine adjacent-duplicate insertion
predictions are removed (at most four remain). Stop and report a failed criterion;
do not tune features or refit. Keep games 09–10, DAgger/WAIT labels, the example
cap, PPO, network changes and MCP outside this goal.
The owner approved a v3-only tensor projection because native order slots 14–15
already contain coordinates. Check their old meaning, clear them, require zero
slots 16–19, and bind marker 2; the C++ v3 reader rejects nonzero slots 14–19.
For v3, bind station column 5 to the same public snapshot's passenger count,
because the old column sums all cargo. Preserve raw tensors, earlier modes,
archive compatibility checks and native-only ONNX rejection. See the October 6
section of docs/DEVELOPMENT.md for the slot meanings, tests and artifact paths.
This trial completed with feature commit `6aeb3c4` and one 256-update CUDA fit.
V3 fits 143/186 choices (v2 128), insertions 22/43 (v2 6), and repayments 32/32.
Adjacent duplicates fall from 9/43 to 0/43 while 42/43 insertion states still
predict insertion. Development game 08 falls from 18/34 to 17/34; do not tune
using that result. All 186 native input audits have zero aliases; native CPU/CUDA,
354 Python checks (four skips), fast verification and diff checks pass.
The unchanged 50-case protocol completes all budgets with 50 native final saves,
25,600 verified decisions, 3,276,800 ticks and zero interface failures. First-route
two-distinct-stop structure improves from 0/25 to 24/25 greedy and 7/25 to 24/25
sampled. Including Full Load Any at both stops, validity is 21/25 and 7/25 versus
v2's 0/25 and 2/25. V3 delivers in 23/25 episodes in both modes, versus v2's
0/25 greedy and 24/25 sampled. Mean operating profit remains negative:
-5,276.00 greedy and -11,291.92 sampled, versus -6,551.60 and -12,417.80.
Training Full Load Any falls from 42/43 to 40/43; purchases 23/25 to 22/25;
starts stay 25/29; copies/deletions rise from zero to 1/7 and 1/5; other loading
remains 0/2. One v3 insertion-only fit is not authorized or run. The station
matching fix works, but profitable fleet control and PPO qualification remain
unproved. DAgger round 1 is the owner's next separate goal, not work to start
automatically here. Runtime evidence is
`/home/imsa/.local/share/openttd-rl/runs/human-orders-v3-20261006-01/`; the Windows
summary is under `%LOCALAPPDATA%/OpenTTD-RL/analysis/human-orders-v3-20261006-01/`.

OpenTTD itself runs on the CPU. CUDA accelerates neural training and supported
policy inference, not the simulation. Measure game-worker throughput separately
from network speed; never describe this as a GPU implementation of OpenTTD.

Read `docs/DEVELOPMENT.md` for the current practical workflow and backlog, and
`GOAL.md` for the broader game scope. User instructions take precedence over
historical milestone documents. Prefer one working vertical slice to expanding
the contract/evidence machinery. Do not rewrite working systems merely to rename
them, introduce a second PPO implementation, or replace C++ with Python training.
Python may orchestrate processes, experiments, plotting, and independent tests.

The ten human passenger-bus and money-management games are collected and qualified.
Follow `docs/HUMAN_DATASET_10_GAMES.md` for their replay/import evidence. Preserve
whole-game splits and make chosen waiting explicit before exporting WAIT labels.
Each game should have two passenger routes; the owner will add buses when it
makes sense. Do not impose a one-bus fleet limit or require additional routes.
Ten games are hash-preserved and pass native replay and partition-appropriate
input checks. Seven training games supply 186 exact choices; game 08 supplies
34 development choices and games 09–10 supply 64 test choices (31/33). The first four
supply 18, 24, 22 and 15 (79 total).
At the owner's request, a four-game
CUDA imitation pilot ran alongside an equal-update one-game control and the
preserved October 2 1,000-update model. Keep games 08–10 out of this pilot.
The pilot completed: four-game fit is 53/79 unique exact choices, versus 25/79
and 23/79 transfer for the 256- and 1,000-update one-game controls. Station
insertions remain 4/23 and repayments 0/2. All four live continuations still
drift and lose operating money; do not treat this model as qualified for PPO.
At the owner's request, game 02 was verified before game 03: all 11 native replay
checks pass and the consumer accepts 24 supported labels. Game 03 is captured
and passes all 11 checks; the consumer accepts 22 choices, including two repayments.
Its human rationale weighs town population against distance before construction;
keep that annotation separate from exact command labels.
Game 04 is preserved and passes all 11 checks; the consumer accepts 15 choices.
Game 05 adds 39 choices, including ten 10,000 repayments and one loading-mode-0
change. Its three stops serve two route pairs; six buses are running, cash is
110,424 and debt is zero. The owner selected the two largest cities and placed
two stops in the largest. Keep that rationale separate from construction labels;
public nearest-town geometry is consistent, not a direct station-town lookup.
Vehicle cloning is replayed but excluded as a policy action. The five-game
training-only assembler accepts 118 examples; no game-05 model training ran.
Game 06 adds 39 choices and a verified mid-game reassignment: native vehicle 5
moves from stations 2/1 to 0/1, balancing the fleet at two buses per route.
Five supported edits retain exact pre-command states; the intervening unload-mode-1
command is replayed but excluded as a label. Ten repayments leave cash 103,214
and zero debt. Keep the owner's profitability rationale as a retrospective
annotation; causal improvement is unmeasured. The six-game assembler accepts
157 examples; no game-06 model training ran.
Game 07 adds 29 choices, including ten repayments, and ends with three running
buses, cash 103,852 and zero debt. The owner delayed further investment;
retain that retrospective waiting rationale without turning command gaps into
WAIT labels. Later maintenance and one bus purchase replay successfully but are
excluded as policy actions. The seven-game assembler accepts 186 choices,
including 32 repayments; games 08–10 remain outside training. No game-07 model
training ran.
Game 08's completed capture passes all 11 checks and the read-only development
audit for 34 choices. Five buses run on two routes (3/2 allocation),
cash is 109,219 and debt zero. The owner scaled capacity using passenger queues;
retain exact pre-purchase station totals without inventing per-route demand or
numeric thresholds. Game 08 belongs to development; training remains 186 choices.
Training consumers must respect the partition hash-bound in preservation metadata.
Use `audit_human_evaluation_v2.py` for read-only development/test integrity exports;
it creates no trainer manifest and requires completed capture metadata.
Game 09 passes native and read-only test integrity checks for 31 choices. The
saved orders are two two-stop routes across three stops, with two buses on 0/1
and three on 0/2. Preserve the owner's "three city loop" description separately;
no three-station bus order cycle is present in the final save. Both training
input paths reject the capture. Do not use this test game's choices or outcomes
to tune features, rewards or models; no model scores were computed during capture.
Game 10 passes all 11 checks and the read-only test audit with 33 choices.
The owner used two stops in a city with starting population above 2,000 and
scaled the fleet. Preserve that rationale separately from unsupported stop-building
labels. All ten games supply 284 choices across their fixed partitions.
The owner now requests a new training run, comparison with prior runs, a saved
50-game evaluation and all evidence, without questions or stopping early.
The seven-game CUDA fit is frozen at 256 updates, seed 20261002, learning rate
0.0003 and unchanged signed-log-orders-v2 C++ training. It fits 128/186 choices
and matches 41/64 held-out test choices, including all 20 repayments. Excluding
repayments, test accuracy is 21/44 versus the four-game model's 19/44.
Training insertions are 6/43 and copies 0/7; independent auditing finds no
insertion aliases or row-alignment/permutation faults. Insertion errors comprise
11 wrong stations, 12 wrong target vehicles and 14 wrong action/order primitives.
The owner requested an isolated insertion-only CUDA memorization diagnostic;
keep its weights separate from the frozen gameplay actors and test data.
It fits 12/43 at 256 updates and 21/43 at 1,000, with masks, numerical checks and
row permutation passing. It still underfits; investigate entity binding and
optimization before assuming additional demonstrations alone resolve insertion.
Its experiment root is
`runs/human-ten-game-training-20261005-01/`. Keep evaluation off the optimizer.
Compare final weights with prior compatible models on identical native episodes,
separating greedy/sampled results and explicitly disclosing supplied infrastructure.
Native live CHECKPOINT saves must not change state/ticks or consume a policy action;
pending actions reject saves. Preserve original engines and failed qualification runs.
The 50-game-per-actor benchmark is complete with four frozen neural actors and one
script: 250 outcomes and final saves, 247 full budgets and three interface failures.
The new model delivers in 24/25 sampled and 0/25 greedy episodes. Its mean
operating profit is -9,484.7, versus the script's +3,623.16; sustained profitable
service is 0/50 versus 44/50. At matched horizons it improves operating profit
by 17,202.58 over the four-game model but trails the script by 13,107.86.
All 127,427 decisions and 16,310,656 ticks pass native accounting verification.
All three failure captures reproduce their original choices/transitions exactly
(395, 329 and 239 decisions) and pass native save reloads. Report interface failures
explicitly, with native saves, partial budgets and all planned-case denominators.
Do not mask away actions or change features/models in response to evaluation.
The complete comparison is `comparison-evidence-01/` in the experiment root;
the portable Windows report is under `%LOCALAPPDATA%/OpenTTD-RL/analysis/human-ten-game-training-20261005-01/`.
The current multi-game assembler reuses each game's original replay validator,
preserves native game/sample identities and rejects held-out games, repeated
seeds/recordings, changed inputs and incompatible readers. Its campaign manifest
is training-only; it does not manufacture WAIT or construction labels.
Native replay must let StateGameLoop poll link-graph pauses, including the
command-during-pause flag; other pauses still fail when time must advance.
Assess sustained fleet control and imitation retention before longer PPO training; repeated
purchases and route edits remain unresolved.

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
- `scripts/dev/mcp_v2.py`: existing company-scoped MCP adapter, exercised in local
  Gemma matches. Packaging and meaningful competitive play remain unfinished.
- `integration/openttd/patches/15.3`: source integration on pinned upstream.
- `openttd-upstream`: upstream submodule/object repository; keep it pristine.
- `config/v1`, `config/v2`, `evidence`, and `docs/project`: historical contracts,
  provenance, and milestone records. These are not proof of a local reproduction.
- `docs/internal/README.md`: relocated agent handoffs, prompts, September 25
  reviews and the archived README ledger. Put internal reports here rather than
  growing the public README. Preserve historical evidence paths and hashes.

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

Package and extend the existing MCP adapter over the same versioned
observation/action interface used by neural agents. Keep company identity,
action budgets, simulation ticks, timeouts, legal masks, and public information
consistent across participants. Log action attempts, results, costs, and timing.
Separate model inference latency from simulated economic time. Shared-company
matches already execute, but useful economic competition remains unproved.
Qualify model/interface compatibility before putting new policies into matches.

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
