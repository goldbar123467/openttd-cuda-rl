# Local training and the path to agentic economies

## What we are continuing

Keep the existing C++ PPO and source-integrated OpenTTD environment. The immediate
target is a small passenger-bus agent that learns from real game observations,
legal actions, and economic rewards. Extend to the V2 transport systems after this
loop is reproducible on the owner's machine. MCP opponents come after a reliable
shared observation/action boundary, not before basic training works.

There are two different learning paths in the repository:

| Path | What supplies transitions and rewards | What a successful run establishes |
| --- | --- | --- |
| V1 live PPO | OpenTTD worker processes through the M03-M06 bridge | Full development episodes demonstrate learned passenger service; greedy reliability and efficiency remain open |
| V2 M22 campaign | Fixed native-qualified corpus and per-action reward tables | Program-selection learning on that corpus |

`scripts/dev/train_live.py` reuses `m08.train_architecture`, the existing trainer
client, PPO implementation, masks, GAE semantics, and development evaluator.
It records locally compiled binary hashes instead of demanding the historical
release executable hash. Release validators and their expected hashes are intact.

Current development evidence: three independently trained balanced-reward MLPs
with 64-step rollouts sustain all 18 sampled development episodes, averaging
1,514 passengers and 4,670 operating profit. Mean cash after capital is -3,745;
the one-bus script is more cash-efficient. Greedy construction succeeds in 4/6
episodes. The frozen 36-episode held-out confirmation passed all its registered
criteria: sampled play sustained 18/18 episodes, averaging 2,017 passengers,
6,023 operating profit and -2,488 cash after capital. One-bus remains more
cash-efficient, and greedy succeeds in 4/6. Final results must not drive tuning.
Reset-boundary CUDA resume reproduced 512 continuation transitions exactly;
native/ONNX replay matched 4,096 transitions; the exported network ran visibly on
both development maps, including the newly selected 64-step model. These are
narrow V1 results on fixed maps, not general OpenTTD competence.
[PROGRESS.md](PROGRESS.md) retains the comparisons,
failed experiments and current hypotheses. The initial smoke below is historical.

## Initial local validation (2026-09-23)

The RTX 2070/WSL2 setup completed `live-cuda-02`: eight PPO updates, 1,024 real
OpenTTD transitions, model export, and both development evaluations. The seed was
20260923 and the architecture was `structured-mlp-v1`. Mean training rollout
reward went from -0.044775 on update 1 to +0.206734 on update 8. Both 64-step
development probes delivered **zero passengers and zero income**. This validates
the pipeline, not playing competence or a generalization claim. No training
episode reached its 512-action horizon during this short run.

Checks passed: 136 repository fast tests, 97 native game tests, seven native PPO
tests (including the CPU/CUDA export regression), eight development orchestration
tests, nine existing M09 evaluation tests, and all three architecture learning
smokes on CPU and CUDA. The full historical release/evidence suite was not run.

The Linux artifacts are in `~/.local/share/openttd-rl/runs/live-cuda-02`.
A local copy of the successful run, model, smoke reports, and test logs is in
`runs/2026-09-23/` inside the checkout (ignored by Git). The failed first run is
retained separately. The immediate research task is longer, matched-budget
training with full-episode development baselines before claiming improvement.

## Host and dependencies

Use Ubuntu 24.04, directly or under WSL2. The services use POSIX pipes. Keep build
outputs on the Linux filesystem for speed even if source lives on the Windows
drive. The current checkout is at:

```text
C:\Users\imsa\Documents\OpenTTD\openttd-cuda-rl
/mnt/c/Users/imsa/Documents/OpenTTD/openttd-cuda-rl
```

The parent is OpenTTD's user-data folder. Do not install development executables
over the normal game or write experiments into the user's saves/configuration.

The local development profile uses Python 3.12, GCC 13, CMake 3.28+, Ninja,
OpenSSL development headers, and PyTorch 2.9.1's C++ libraries. An RTX 2070 is
compute capability 7.5. `local.py` discovers this instead of using the historical
RTX 5070 `12.0` setting. CUDA runs are explicit and never fall back to CPU.

One-time environment setup in a WSL terminal (the current machine is already set
up):

```bash
cd /mnt/c/Users/imsa/Documents/OpenTTD/openttd-cuda-rl
python3 -m venv ~/.local/share/openttd-rl/venv
source ~/.local/share/openttd-rl/venv/bin/activate
python -m pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cu128
python -m pip install jsonschema==4.26.0 numpy==2.2.6
python scripts/dev/local.py doctor
```

`uv venv` and `uv pip install --python ...` are equivalent. The wheel provides
the CUDA 12.8 tensor runtime; this machine also has a CUDA 12.6 toolkit at
`/usr/local/cuda`. The current native targets are C++ callers of LibTorch, with
no project CUDA kernels. Do not assume that this combination validates future
custom kernels: add a compatible toolkit/kernel test when introducing `.cu` code.
GPU drivers are managed separately; the scripts do not install or replace them.

## Build and verify the existing C++ implementation

```bash
source ~/.local/share/openttd-rl/venv/bin/activate
python scripts/dev/local.py build --cuda-root /usr/local/cuda --jobs 2
python scripts/dev/local.py test
python scripts/dev/local.py smoke --device cpu \
  --output ~/.local/share/openttd-rl/runs/cpu-smoke-01
python scripts/dev/local.py smoke --device cuda:0 \
  --output ~/.local/share/openttd-rl/runs/cuda-smoke-01
```

Default build directory: `~/.local/share/openttd-rl/build/ppo`. Override with
`--build-dir`. Use a different directory when changing Torch environments to
avoid CMake retaining another environment's libraries. Output run directories
must be new; old results are never overwritten. `run.json` records the source
state, host, binary hash, result, and claim boundary; `learning.json` contains
the three-architecture learning smoke results. These are synthetic PPO checks.

The native CTests cover PPO math, independent differential vectors, learning,
architectures, checkpoint recovery/corruption, and evaluation serialization.
The export regression also verifies that saving preserves live parameter storage,
device, values, inference, Torch RNG, and subsequent optimizer updates for all
three architectures. The local build enables its CUDA variant when a GPU is
visible (seven tests on this host; six for a CPU-only test configuration).
The development build links GCC's standard library before Torch to avoid wheel
filesystem symbols intercepting checkpoint directory operations on this host.

The first live CUDA run exposed a separate existing export bug:
`save_evaluation_model` moved the trainer's own module to CPU, leaving its device
contract set to CUDA. The model file was valid, but the next inference failed.
Export now writes a CPU tensor snapshot without moving or reinitializing the
module. This also preserves optimizer parameter references and avoids reseeding
Torch. The original failed experiment remains under `runs/live-cuda-01` in the
Linux artifact directory; it must not be relabeled as a completed run.

## Prepare and build the existing game integration

```bash
python scripts/dev/prepare_engine.py --output ~/.local/share/openttd-rl/engine
cmake -S ~/.local/share/openttd-rl/engine/source \
  -B ~/.local/share/openttd-rl/engine/build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DOPTION_RL_ENVIRONMENT=ON \
  -DOPTION_RL_NEURAL_AGENT=OFF -DOPTION_USE_ASSERTS=ON -DOPTION_DEDICATED=ON
cmake --build ~/.local/share/openttd-rl/engine/build --parallel 4
```

Preparation calls the existing V1 source composer, validates every resulting
Git tree, and generates only the four training and two development scenarios.
It preserves the upstream submodule and produces an isolated source tree.

Download [OpenGFX 8.0](https://cdn.openttd.org/opengfx-releases/8.0/opengfx-8.0-all.zip),
extract `opengfx-8.0.tar`, verify its SHA-256, and copy it into the engine build's
`baseset/` directory:

```text
9389bcb0807058c80bd95121e978f05d9ef86b4b1bc3ac2da8da8bb02456043c
```

This is the asset required by the existing scenario contract. The current local
download is cached in `.cache/opengfx/`, excluded from Git. Then run:

```bash
cp .cache/opengfx/opengfx-8.0.tar ~/.local/share/openttd-rl/engine/build/baseset/
ctest --test-dir ~/.local/share/openttd-rl/engine/build --output-on-failure
```

## Train on real OpenTTD transitions

```bash
python scripts/dev/train_live.py \
  --trainer ~/.local/share/openttd-rl/build/ppo/m08_trainer \
  --openttd ~/.local/share/openttd-rl/engine/build/openttd \
  --instance-dir ~/.local/share/openttd-rl/engine/instances \
  --device cuda:0 --architecture structured-mlp-v1 --seed 20260923 \
  --updates 2 --evaluation-steps 64 \
  --output ~/.local/share/openttd-rl/runs/live-cuda-01
```

Start small: each update collects 128 transitions across four real games. Use
`--device cpu` for the reference, and `spatial-cnn-v1` or `combined-cnn-mlp-v1`
to exercise the existing spatial networks. More GPU work does not necessarily
mean faster end-to-end training; report collection and update time separately.

Each successful run retains the training metrics, development returns/deliveries/
income on both scenarios, and inference weights under `models/`. The exported
model is not an optimizer-resume checkpoint; use the separate native reset
checkpoints below to continue training. Failed runs retain a failure
record, `training.log`, and available diagnostics. This developer route does not run any held-out
final manifest or claim a release gate.

## Checkpoint and resume at native resets

For ordinary 512-action episodes with 32-action rollouts, all four games normally
reset every 16 updates. Request checkpoint publication at those boundaries:

```bash
python scripts/dev/train_live.py \
  --trainer ~/.local/share/openttd-rl/build/ppo/m08_trainer \
  --openttd ~/.local/share/openttd-rl/engine/build/openttd \
  --instance-dir ~/.local/share/openttd-rl/engine/instances \
  --device cuda:0 --seed 20260923 --updates 16 --evaluation-steps 512 \
  --bridge-validation fast --checkpoint-interval 16 \
  --output ~/.local/share/openttd-rl/runs/checkpoint-training-new

python scripts/dev/train_live.py \
  --trainer ~/.local/share/openttd-rl/build/ppo/m08_trainer \
  --openttd ~/.local/share/openttd-rl/engine/build/openttd \
  --instance-dir ~/.local/share/openttd-rl/engine/instances \
  --device cuda:0 --seed 20260923 --updates 16 --evaluation-steps 512 \
  --bridge-validation fast --checkpoint-interval 16 \
  --resume ~/.local/share/openttd-rl/runs/checkpoint-training-new/checkpoints/update-000016 \
  --output ~/.local/share/openttd-rl/runs/checkpoint-resumed-new
```

`--updates` means **additional** updates after restoration; native counters remain
cumulative. Keep the seed, architecture, device, horizon, rollout length and reward
mode identical. Checkpoints bind the trainer/engine hashes, training templates,
collection code and configuration. Recreated reset observations and masks must
match before training resumes. An early terminal can desynchronize games; such a
boundary is recorded as skipped instead of publishing a misleading recovery file.

The native archive includes model parameters, Adam moments/steps, counters, the
three mutable native RNG streams, Torch CPU and training-device RNG state, and
model mode. Checkpoint-enabled training uses deterministic cuDNN convolution
selection and records that choice. This matters for CNNs: preserving seeds alone
does not remove nondeterministic GPU reductions. Exactness is a same-host,
same-runtime claim at synchronized resets, not arbitrary mid-game or cross-device
recovery. Historical M07 checkpoint files and release trainer options remain
separate; the new requests are compiled only by the development build.

New runs retain a source patch plus new development files under `source/`.
Development builds retain the corresponding archive path in
`development-build.json`. Reconstruct older source in an isolated checkout before
resuming an older checkpoint if collection code has changed.

To evaluate an earlier saved checkpoint without collecting more experience:

```bash
python scripts/dev/export_checkpoint.py \
  --trainer ~/.local/share/openttd-rl/build/ppo/m08_trainer \
  --training-run ~/.local/share/openttd-rl/runs/checkpoint-training-new \
  --checkpoint ~/.local/share/openttd-rl/runs/checkpoint-training-new/checkpoints/update-000016 \
  --output ~/.local/share/openttd-rl/runs/checkpoint-export-new
```

The completed training run must register that checkpoint. Export verifies the
native binary, configuration, payload and counters before restoring into C++.
Use the resulting `run.json` model path with `evaluate_live.py` or the ONNX export
workflow. This is inference-only export; it neither resumes the environment nor
weakens the collection-source checks for training recovery. Final-checkpoint
export reproduced the original CNN model identity exactly in the native check.

To exercise a bounded real-game recovery comparison:

```bash
python scripts/dev/verify_live_resume.py \
  --trainer ~/.local/share/openttd-rl/build/ppo/m08_trainer \
  --openttd ~/.local/share/openttd-rl/engine/build/openttd \
  --instance-dir ~/.local/share/openttd-rl/engine/instances \
  --device cuda:0 --output ~/.local/share/openttd-rl/runs/resume-check-new
```

This compares eight uninterrupted updates with four updates plus a restored four,
using 128-action training episodes. It requires identical continuation metrics,
four full action/economic traces, and final exported model identity. Its one-step
development probes are only workflow checks, not gameplay evaluations.

## Complete-episode development baselines and policy replay

The completed held-out confirmation is a separate, frozen route. Its registration
binds all three selected models, evaluation code, native executables, simulation
budgets and acceptance criteria. Reproduce it from the matching archived source:

```bash
python scripts/dev/evaluate_registered.py \
  --registration "$RL_ROOT/runs/heldout-balanced-roll64-registration-02/registration.json" \
  --output "$RL_ROOT/runs/heldout-reproduction-new"
```

The registration's companion SHA-256 file and original model paths are required.
Ordinary `evaluate_live.py` refuses reserved final instances. The confirmation
passed all seven criteria in 36 episodes; see `PROGRESS.md` for the complete
comparison and the two zero-episode setup failures preceding the explicit
registration amendment. Future training must use training/development evidence,
not these reserved results.

The default training command above is a short pipeline check. A normal V1
episode is 512 actions at 128 ticks per action. Use the following evaluator for
gameplay claims; it runs every selected episode to an engine-reported terminal
or time limit and rejects unfinished episodes. It never selects final scenarios.

Development builds also expose the existing PPO coefficients through
`train_live.py --entropy-coefficient 0.01 --gae-lambda 0.95`. These defaults are
unchanged. Checkpoints bind nondefault values, and inference checkpoint export
restores them. A nondefault value requires a rebuilt development trainer; older
binaries fail explicitly. Higher entropy and longer GAE traces are experimental
options, not demonstrated improvements. `--credit-trace` records scalar rewards,
values and boundary flags entering C++ after any reward transform. After training,
`audit_credit.py --training-run RUN --output NEW_REPORT` reconstructs them offline,
checks native explained variance and groups advantages by action family. This
analysis never supplies training advantages or changes the native PPO update.
`plot_credit_trace.py --training-run RUN --output NEW_FIGURE` draws the first
rollout with an explicitly offline lambda counterfactual; use the analysis Python
environment with matplotlib. `report_credit_experiment.py --axis rollout` (or
`lambda`) compares complete final-model evaluations using `--reference` and
`--candidate` run directories, plus `--baseline`, `--one-bus` and `--output`.
Supply one matched seed pair or all three independent seeds. Different trainer
binaries additionally require the passed verification JSONs via
`--default-equivalence`; settings and experience must otherwise match the declared
comparison. Consult the current progress log before treating either setting as an
improvement.

```bash
python scripts/dev/evaluate_live.py \
  --openttd ~/.local/share/openttd-rl/engine/build/openttd \
  --instance-dir ~/.local/share/openttd-rl/engine/instances \
  --policies wait random scripted one-bus \
  --seeds 20260923 20260924 20260925 --workers 2 \
  --hypothesis 'Compare complete-episode service and economics before tuning PPO' \
  --output ~/.local/share/openttd-rl/runs/full-baselines-new
```

`scripted` preserves the existing M09 baseline (eight purchases, only bus 0
assigned and started). `one-bus` constructs and operates one bus using only the
public observation and legal mask. `random` samples uniformly over legal actions.
Deterministic baselines run once per map; action-sampling seeds are not new map
seeds or independent training runs. The default uses separate Python processes
so bridge decoding can use multiple CPU cores. `--executor thread` is available
for comparison. `--profile` saves per-episode cProfile data and affects timing.
`--bridge-validation fast` selects the differentially tested table/regex
implementation of the same checksum and canonical-response checks. The default
`reference` preserves the original bitwise/scanner implementation. This option
is also supported by `train_live.py`; it changes validation cost, not PPO or game
semantics. Full-episode byte-equivalence evidence is recorded in the progress log.

To replay saved neural weights, supply `--evaluator`, `--package` using the
`model.path` from a successful training `run.json`, and `--policies greedy sampled`:

```bash
python scripts/dev/evaluate_live.py \
  --openttd ~/.local/share/openttd-rl/engine/build/openttd \
  --instance-dir ~/.local/share/openttd-rl/engine/instances \
  --evaluator ~/.local/share/openttd-rl/build/ppo/m09_evaluator \
  --package /absolute/path/from/training/run.json \
  --policies greedy sampled --workers 2 \
  --hypothesis 'Test the saved policy for sustained service across full episodes' \
  --output ~/.local/share/openttd-rl/runs/policy-replay-new
python scripts/dev/summarize_evaluation.py \
  ~/.local/share/openttd-rl/runs/policy-replay-new
```

The optimizer-free evaluator explicitly runs inference on CPU. CUDA training is
unchanged. Visible playback uses the separate ONNX workflow below.
Each episode keeps actions, exact legal masks, neural probabilities, command
outcomes, rewards, engine termination, and lifetime economic counters. Profit
uses unclipped lifetime deltas, since snapshot income/expenses describe the
current quarter. Capital spend and balance change are separate metrics. Window
metrics require passenger delivery and positive operating profit in every final
128-action window; reward alone is insufficient. See [PROGRESS.md](PROGRESS.md)
for experiment hypotheses, actual results, limitations, and the next iteration.

## Next concrete milestones

1. **Stronger live V2 learning:** the recurrent policy now trains from native
   sequential decisions and resumes at verified resets. Establish improvement
   over uniform/scripted controls under the same public route guide; current
   guided service alone does not show a learned advantage.
2. **More transport:** native scripted passenger/mail service now works together
   on two development maps. Extend useful neural cargo control and then industrial
   freight. Historical M16 qualification fixtures are not live play.
   Retain executable bus regressions and version new policy inputs explicitly.
3. **Reproduction across changes:** retain V1 reset recovery, ONNX and visible
   replay checks; extend deployment to V2 once useful control is established.
4. **CUDA practice:** preserve the trusted reference and measured masked-policy
   experiment. Its large operation-level speedup did not improve full training
   materially; profile again before choosing another GPU target.
5. **Stronger MCP competition:** a real local LLM has completed a full match
   through the shared boundary, but neither it nor the weak neural opponent
   delivered passengers. Improve competence and retain fair map/role controls.
6. **Economic experiments:** expand the executed paired comparisons with stronger
   agents, reporting service, cash, survival, market share and inference costs
   separately, with uncertainty across independently trained models.

Keep new work small and executable. Historical frozen artifacts are retained;
they should not force every development experiment to reproduce an entire release.

For a construction-frequency experiment, `train_live.py --episode-horizon 128`
uses the engine's existing bounded reset variation on training maps, retaining
native time-limit and bootstrap flags. `256` and the ordinary `512` are also
supported. Development evaluation always restores the normal 512-action reset.
This is an explicitly labeled curriculum: short training episodes do not count
as full-horizon evaluations. New training runs retain native transition outcomes
and economic summaries under `episode-metrics/`, including partial final workers.
The scoped adapter restores the frozen controller after training or an exception;
run each training job in its own Python process.

The current 64-step balanced-reward experiment uses the following explicit
settings. Seed 20260924 has completed service in all eight development episodes;
the three-seed replication is recorded in the progress log. This is a development
recipe, not a held-out qualification:

```bash
python scripts/dev/train_live.py \
  --trainer "$RL_ROOT/build/ppo-credit/m08_trainer" \
  --openttd "$RL_ROOT/engine/build/openttd" \
  --instance-dir "$RL_ROOT/engine/instances" \
  --device cuda:0 --seed 20260924 --updates 64 --evaluation-steps 64 \
  --episode-horizon 128 --rollout-length 64 --training-reward balanced-economic \
  --gae-lambda 0.95 --entropy-coefficient 0.01 --credit-trace \
  --bridge-validation fast --spatial-validation reference --checkpoint-interval 8 \
  --output "$RL_ROOT/runs/balanced-roll64-new"
```

The embedded 64-action probes do not count as full evaluation. Use the completed
run's model path with the eight-episode evaluator command above. Keep
`--spatial-validation reference` for this registered comparison. New development
runs now default to `vectorized`: the isolated three-pair check reproduced all
native traces, PPO metrics and final models exactly, with median 1.147x end-to-end
speedup (range 1.144–1.228x). This is a CPU input-validation improvement. The
vectorized path needs NumPy, retains the original input list, and binds the NumPy
version/mode in checkpoint compatibility. The Torch environment already supplies
the dependency. Native PPO and CUDA math are unchanged.

Further opt-in development experiments leave native game rewards and the
C++ PPO implementation intact:

- `--rollout-length 64 --updates 16` collects the same 4,096 transitions as
  length 32 with 32 updates. The longer segment can contain construction and
  first delivery together. The existing service's frame bound currently limits
  this launcher to 32 or 64 decisions per worker.
- `--training-reward universal-decision-cost` extends M06's 1/64 WAIT penalty to
  all decisions, preventing free town-selection toggles from avoiding it.
- `--training-reward service-potential` adds `0.99 * Phi(next) - Phi(current)`
  to that uniform-cost reward. In the single-company bus scenario, Phi counts
  up to two stops, one depot, one purchased bus, and the presence of a running
  bus (maximum five). Extra buses get no extra potential. True terminals use
  zero potential; time-limit truncations retain the bootstrap state's potential.
- `--training-reward economic` rescales the native bounded terms to delivery
  /128, operating profit /256, and capital spend -/1024, with a uniform 1/64
  decision cost. Other native penalties remain. It adds no progress potential
  and is an explicit alternative economic objective, not a game-accounting change.
- `--training-reward balanced-economic` uses intermediate weights: delivery /64,
  native operating profit /1024, capital -/4096 and a uniform 1/64 decision cost.
  It retains the same clipping, failure terms, rollout masks, behavior log
  probabilities and C++ PPO implementation. This is an opt-in experiment;
  judge passenger service and cash outcomes against complete-episode controls.
- `--entropy-coefficient 0.05` increases the existing native PPO entropy bonus
  from its default0.01. It encourages a broader action distribution; it neither
  changes legal masks nor supplies a scripted action. Nondefault values require
  a newly compiled development trainer. Records/checkpoints preserve the value,
  and invalid/nonfinite values fail explicitly. The default omits the new CLI
  option so earlier development binaries remain usable. Treat changes as
  separately labeled experiments, not matched architecture comparisons.

The potential uses only own-company/public infrastructure counts; it does not
read RNG state, future deliveries, or evaluation data. Per-transition shaping
and raw rewards are retained separately. The ordered reward stream is checked
against the collector before entering PPO. This follows the discounted
[potential-shaping construction](https://people.eecs.berkeley.edu/~russell/papers/icml99-shaping.pdf),
but finite neural training still requires empirical evaluation. These switches
are research options, not established improvements or changed defaults.

## Export and watch a development policy

Run these commands inside the same WSL virtual environment. The development
exporter currently supports the structured MLP. It requires a completed full
development evaluation of that exact model; it does not assign a release PASS.
Install `onnx==1.22.0 onnxscript==0.7.2 onnxruntime==1.28.0` into the existing
environment without replacing its Torch installation. The C++ runtime is the
official `onnxruntime-linux-x64-1.28.0.tgz` release (SHA-256
`a3e1b79d7bb1bf09696ce675f49e4064e6c81f6202b8225624fff0e93f8d6407`).

```bash
RL_ROOT=$HOME/.local/share/openttd-rl
cmake -S training/v1 -B "$RL_ROOT/build/deployment" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DV1_DEPLOYMENT_ONLY=ON \
  -DV1_ONNXRUNTIME_ROOT="$RL_ROOT/deps/onnxruntime-linux-x64-1.28.0"
cmake --build "$RL_ROOT/build/deployment" --parallel 2
python scripts/dev/export_live.py \
  --package /absolute/path/to/native-model-package \
  --evaluation /absolute/path/to/completed-development-evaluation \
  --evaluator "$RL_ROOT/build/ppo/m09_evaluator" \
  --deployment-evaluator "$RL_ROOT/build/deployment/m10_onnx_evaluator" \
  --output "$RL_ROOT/runs/export-new"
```

The resulting `export.json` identifies the ONNX package and numerical comparison.
Use that package with `evaluate_live.py --backend onnx --evaluator
"$RL_ROOT/build/deployment/m10_onnx_evaluator"` and the other evaluation arguments
above. `compare_replay.py --reference NATIVE_EVALUATION --candidate ONNX_EVALUATION
--output NEW_DIRECTORY` checks complete action/state/economic replay equivalence.
Both deployment executables use CPU ONNX Runtime and require no LibTorch.

For an actual native window, install the SDL2 development dependency
(`sudo apt-get install libsdl2-dev`), then build a separate engine tree. The
preparation script applies a development-only overlay; historical patches,
release acceptance checks, and the headless training engine remain intact.

```bash
python scripts/dev/prepare_playback.py \
  --engine-root "$RL_ROOT/playback-engine" \
  --onnxruntime "$RL_ROOT/deps/onnxruntime-linux-x64-1.28.0" \
  --baseset "$RL_ROOT/engine/build/baseset/opengfx-8.0.tar" --jobs 2
python scripts/dev/play_live.py \
  --openttd "$RL_ROOT/playback-engine/build/openttd" \
  --package /absolute/path/from/export.json \
  --instance "$RL_ROOT/playback-engine/instances/m02-template-05.json" \
  --mode greedy --actions 512 --output "$RL_ROOT/runs/visible-new"
```

This bounded command opens a WSLg/SDL window, completes 512 decisions, saves a
native BMP or PNG screenshot and inspection trace, then exits. Add `--watch` to
keep the window open at normal speed; `--actions 0 --watch` runs without a preset
decision limit. Native inspector buttons pause the agent/game or step one action.
Playback accepts only training/development maps 01–06, uses an explicit empty
per-run configuration and OpenTTD `-X` local paths, and refuses the dummy video
driver. Normal OpenTTD saves and configuration are not needed.

The current demonstrated package can be watched without retraining:

```bash
python scripts/dev/play_live.py \
  --openttd "$RL_ROOT/playback-engine/build/openttd" \
  --package "$RL_ROOT/runs/demo-balanced-roll64-s20260924-01/export/fa5f64fc95cebf3ebd71e20eb8f9402078f7875de05407c8f97446d79bbe077f" \
  --instance "$RL_ROOT/playback-engine/instances/m02-template-05.json" \
  --mode sampled --seed 20260923 --actions 512 --watch \
  --output "$RL_ROOT/runs/watch-balanced-roll64-new"
```

This package was selected from development results before held-out outcomes.
Its full native/ONNX replay and both visible development maps passed comparison.
Use a fresh output directory for each launch; maps 05/06 are both supported.

`compare_visible.py --visible VISIBLE_RUN --reference HEADLESS_EPISODE` checks
the same decisions and lifetime economic counters. The GUI records immediately
after each command, before its next 128 ticks; it must be compared with headless
pre-state counters, not the final post-advance totals. See the progress log for
executed replay results and the selected policy's gameplay limitations.

## Interactive V2 development slice

The existing V2 M22 corpus campaign still selects prequalified programs. A new,
separate development adapter exposes the actual M15 bus environment through
OBSERVE, ACT, STEP and CLOSE requests. It currently controls company 0 on maps up
to 128x128; it is not shared-company competition or a trained V2 policy.

```bash
RL_ROOT=$HOME/.local/share/openttd-rl
python scripts/dev/prepare_v2.py \
  --base-source "$RL_ROOT/engine/source" \
  --output "$RL_ROOT/v2-live-engine" --through m15-competence --build \
  --baseset "$RL_ROOT/engine/build/baseset/opengfx-8.0.tar" --jobs 2
python scripts/dev/enable_v2_live.py --engine-root "$RL_ROOT/v2-live-engine" --jobs 2
python scripts/dev/live_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --policy reactive-build --decisions 8 \
  --output "$RL_ROOT/runs/v2-interactive-new"
```

Preparation verifies each frozen source-tree boundary and preserves the original
executable. The overlay reuses native legal-candidate predicates and commands;
it does not alter frozen patches. After editing the development include, use
`enable_v2_live.py --refresh` to archive and rebuild the recorded adapter.
Each experiment needs a new output directory. Default seeds come from the
training split; `--split development` selects only that separate ledger.

The smoke observes the live game, builds a depot and buys a bus, then waits.
It verifies read-only observations, stale/illegal/company rejection, one action
per step and exactly 128 ticks per step. It does not establish passenger service
or learned competence. `worker/transitions.jsonl` contains native before/after
economics; `worker/requests.jsonl` records all requests, rejections and wall time
separately from ticks. The native transport has a 60-second idle timeout that
ends a failed run without advancing simulation. Shared-match scheduling and
company-scoped shared control are described below; timeout outcomes are aborted
matches, not automatic opponent victories.

For complete scripted service through that same live boundary:

```bash
python scripts/dev/service_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --policy one-bus-repay --planner graph --native-site-checks --minimum-route-length 12 \
  --decisions 512 --output "$RL_ROOT/runs/v2-service-new"
```

The planner uses exposed candidates, visible houses and road bits. It connects
two catchments, buys/orders/starts one bus and optionally repays debt while
retaining 10,000 cash. Every primitive still requires its own legal ACT and
128-tick STEP; it never calls the old native SERVICE macro. `--policy wait`,
`--policy one-bus` (no repayment), and `--planner straight` provide controls.
`--split development` uses a separate seed ledger. Planning and execution failures
remain failed runs; a completed episode can still have zero deliveries or losses.
`summary.json` separates operating profit, capital, loan principal and balance
change, with 128-action service windows. These scripts establish interactive
baselines, not neural V2 training or shared-map competition.

The current V2 summaries also reconcile cash: `cash_result_excluding_financing`
is the balance change minus the loan-principal change; `cash_result_before_capital`
adds back net construction/vehicle spending, including resale proceeds. Native
`cur_economy` operating counters exclude `EXPENSES_OTHER`, including the monthly
charge in the pinned engine, so they are a narrower measure. Both native-profit
and positive-cash service-window flags are retained. `report_v2_learning.py
--runs RUN_A RUN_B ... --output NEW_REPORT` rederives these measures from original
native traces without rewriting historical summaries, and rejects mismatched
map/repetition matrices.

`--native-site-checks` uses the engine's actual bus catchment and present cargo
acceptance/production, and avoids constructing new intersections on slopes.
The earlier uncorrected graph planner remains an explicit experimental control;
its development failures are retained in the progress log.

The existing M15 neural architecture can be built on the same local Torch runtime
with `local.py build --v2-policy --build-dir "$RL_ROOT/build/v2-live-policy"
--cuda-root /usr/local/cuda-12.6 --jobs 2`. This separate build preserves V1
checkpoint binaries. CPU/CUDA policy gates use `ctest --test-dir
"$RL_ROOT/build/v2-live-policy" -R rl_dev_v2_ --output-on-failure`.

The live recurrent PPO adapter uses the same C++ GAE and PPO loss as V1. A small
correctness run (not a gameplay training budget) is:

```bash
python scripts/dev/train_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --trainer "$RL_ROOT/build/v2-live-policy/rl_dev_v2_train" \
  --device cuda:0 --updates 2 --episode-horizon 20 \
  --output "$RL_ROOT/runs/v2-ppo-new"
python scripts/dev/infer_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --policy "$RL_ROOT/build/v2-live-policy/rl_dev_v2_infer" \
  --training-run "$RL_ROOT/runs/v2-ppo-new" --device cuda:0 \
  --compare-cpu --decisions 8 --output "$RL_ROOT/runs/v2-inference-new"
```

Use `--device cpu` explicitly for a reference run; compare matching runs with
`compare_v2_training.py --cpu CPU_RUN --cuda CUDA_RUN --output NEW_COMPARISON`.
The trainer collects 32 decisions per update by default, replays consecutive eight-step
sequences with stored initial hidden states and exact masks, and shuffles whole
sequences for four PPO epochs. Native episode resets cut recurrent state and GAE
continuation; time limits still bootstrap the final physical state. By default,
the first four training ledger seeds are used. `--training-map-count N` chooses
the first N seeds from the training ledger in fixed order (currently 1 through
16); no development or final seeds enter collection. The exact ordered seed list
is recorded and bound into checkpoint compatibility. Resume must use the same
map count/order and archived collector source. The reward version and each raw
delivery/profit/capital contribution remain in `trajectory.jsonl`.

`--reuse-bootstrap-tensors` optionally reuses the validated native input frame
from bootstrap at the next action when its state token and company still match.
Every action runs fresh neural inference, including after a PPO update. A real
reset clears the frame, and checkpoint compatibility binds the option. Three
sequential counterbalanced 256-decision CUDA training pairs match all actions,
masks, PPO updates and final weights exactly, with median reference/reuse wall
ratio 1.06168 (5.81% less total time). Startup, source capture, archival and save
are included. This is a local collector optimization, not a CUDA kernel result;
the option remains off by default. The native TENSORS handler already writes
each decision's files once; reuse avoids requesting, rereading and validating
that same frame again in Python, rather than eliminating its first encoding.

The development trainer also accepts `--rollout-length 64`. This collects twice
as many observations before an update, while keeping eight-step recurrent
sequences and four PPO epochs. GAE sees the longer observed return window;
backpropagation through recurrent state still spans eight decisions at a time.
At matched experience, halve the update count: 32 updates of 64 decisions equal
64 updates of 32 decisions. Update timing and advantage-normalization grouping
also change, so this is not an isolated test of reward delay. The new build's
default CUDA behavior matches the preserved fixed-32 trainer exactly, and its
64-decision CPU/CUDA time-limit check passes the existing 1e-4 tolerance. Guided
64-step reset recovery also passes exactly on CPU and CUDA. The matched-budget
single-seed diagnostic improves sampled operating profit modestly, from 3,179
to 3,833 across two development maps, but greedy still fails both depot stages;
it does not meet the registered criterion for replication. Continuing that
archived run to 4,096 decisions establishes greedy service on both maps. Across
three action-sampling seeds, however, its mean sampled profit is 3,573 versus
3,807 for the earlier model and 3,682 for uniform with the same guide. Conditional
sampling intervals are wide; the failed advancement criterion remains failed.
See the progress log for full economic results and the preserved source needed
to resume that older checkpoint.

With a fresh build containing the rollout option, reproduce
the 256 versus 128-plus-128-decision check using `verify_v2_resume.py --trainer
TRAINER --openttd ENGINE --device cuda:0 --guidance one-bus-public-plan-v1
--rollout-length 64 --output NEW_CHECK`. At horizon 128, checkpoint intervals are
multiples of two 64-step updates. Resume with the same rollout length, binaries
and archived collector source.

The current development adapter additionally accepts `--rollout-length 128`
and `--gae-lambda NUMBER` in [0,1] (default .95). Build into a fresh directory
using `local.py build --v2-policy --build-dir NEW_BUILD --cuda-root /usr/local/cuda-12.6 --jobs 2`.
Native GAE/PPO remains the trusted implementation, with four epochs and eight-step
recurrent gradients. A rollout of 128 at horizon 128 aligns each update with a
reset; 16 updates collect 2,048 decisions. This changes return boundaries,
normalization and update cadence, and removes mid-episode weight changes with
carried recurrent state. It has not yet demonstrated improved learning.

The new binary exactly preserves the recorded 32-step CPU/CUDA and 64-step CUDA
defaults. The 128/lambda1 CPU/CUDA check passes all 128 native decisions across
six time limits, with max metric error 2.25e-5 within the existing 1e-4 tolerance.
Exact 128-step reset recovery passes for CPU/.95 and CUDA/1. Reproduce with:

```bash
python scripts/dev/verify_v2_resume.py \
  --trainer "$RL_ROOT/build/v2-live-full-return-02/rl_dev_v2_train" \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" --device cuda:0 \
  --guidance one-bus-public-plan-v1 --rollout-length 128 --gae-lambda 1 \
  --training-map-count 16 --reuse-bootstrap-tensors \
  --output "$RL_ROOT/runs/v2-return-resume-new"
```

Checkpoint intervals at horizon/rollout 128 can be any positive whole update
count. Resume requires the same return settings, tensor-reuse mode, binaries
and archived collector source. The numeric/return/rejection proofs are in
`runs/2026-09-24/v2-full-return-01/checks/`; they demonstrate correctness, not
playing strength.

Checkpoint file hashes bind a particular saved artifact. Do not use raw native
checkpoint bytes to compare independently started runs: LibTorch's Adam archive
contains process-specific parameter IDs and unordered state serialization.
Compare the model and optimizer tensors, steps/options, RNG, recurrent state
and counters by native parameter order, then verify resumed behavior. The
development map-coverage diagnostic preserves a failed byte-equality check and
its exact logical-state comparison in the progress log.

`inference-weights.pt` is **inference-only**. Development V2 optimizer/RNG recovery
uses separate reset checkpoints; raw-input V2 ONNX export is described below. Build the
current adapter into a separate directory before using the new requests:

```bash
python scripts/dev/local.py build --v2-policy \
  --build-dir "$RL_ROOT/build/v2-live-resume" \
  --cuda-root /usr/local/cuda-12.6 --jobs 2
python scripts/dev/train_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --trainer "$RL_ROOT/build/v2-live-resume/rl_dev_v2_train" \
  --device cuda:0 --seed 20260923 --updates 4 --episode-horizon 128 \
  --checkpoint-interval 4 --output "$RL_ROOT/runs/v2-checkpoint-new"
python scripts/dev/train_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --trainer "$RL_ROOT/build/v2-live-resume/rl_dev_v2_train" \
  --device cuda:0 --seed 20260923 --updates 4 --episode-horizon 128 \
  --checkpoint-interval 4 \
  --resume "$RL_ROOT/runs/v2-checkpoint-new/checkpoints/update-000004" \
  --output "$RL_ROOT/runs/v2-resumed-new"
```

Updates are additional after restoration. Save intervals must align with episode
resets (four updates for 128 decisions); early terminals can make a boundary
ineligible, in which case it is recorded as skipped. Checkpoints retain model,
Adam, recurrent state, native/Torch RNGs, mode and counters. The next training-map
reset is recreated and its public observation and native/sampling tensor hashes
must match before restoration. Binary, collection code, guide, reward and schema
identities must also match. Source archives allow older runs to be reconstructed.

Same-host reset recovery passed an unassisted real-game comparison on CPU and
CUDA: eight uninterrupted updates versus four plus four restored, with exact
continuation metrics, 128 native action/economic transitions and final weights.
`verify_v2_resume.py --trainer TRAINER --openttd ENGINE --device cuda:0
--output NEW_CHECK` reruns that check. This does not establish arbitrary mid-game
or cross-device recovery. CUDA initially failed even before saving because the
graph encoder's scatter reductions were nondeterministic. The current native
trainer requires strict deterministic algorithms and a process-local cuBLAS
workspace profile; these settings are part of checkpoint identity. Merely setting
a seed or deterministic cuDNN did not suffice. Unsupported deterministic operations
fail instead of silently relaxing the claim.

The final deterministic trainer also passed the guided CUDA comparison, including
every saved guide mask and actor value. `verify_v2_checkpoint_boundaries.py
--trainer TRAINER --checkpoint SAVED_RESET_DIRECTORY --output NEW_CHECK` verifies
nine native state/publication rejection cases using that checkpoint's archived
public reset tensors. It does not collect a new game trajectory. Exact recovery
remains limited to the declared reset boundary and matching host/runtime.

The V1 recovery/export workflow above remains available. Completed V2 workers retain tensor binaries as verified
lossless `.bin.gz` files alongside their original metadata (decompress to the
metadata's `.bin` filename before offline native replay). Public tensors redact
map/simulation seeds and private future breakdown timers. Live inference and
scripted control share the same candidate keys, native commands and tick budget.

An optional planner-assisted curriculum adds
`--guidance one-bus-public-plan-v1` to `train_v2.py`. It restricts sampling to the
next exposed primitive from a public road plan, WAIT, and affordable repayment.
Native legality is retained separately. The exact filtered mask and behavior
log probability enter C++ PPO, and previewing a bootstrap state never commits a
construction step. If the bounded candidate list drops the next primitive, the
guide tries another exposed step in the same plan or waits. The saved run binds
this configuration and `infer_v2.py --training-run ...` applies it automatically.
Route geometry comes from the planner, so passenger service by itself does not
demonstrate learning. Compare with `evaluate_guide_v2.py --controller uniform`
and `--controller scripted`, using the same engine, development map and full
512-decision budget. `--controller repay-first` adds a fixed financing-order
diagnostic: repay whenever the same guide allows it, otherwise execute its
proposal. All controls use exactly the same guide and legality. This rule can
leave too little cash to buy a bus; guide version 1 aborts when that service
continuation is unavailable. Such an abort is a failed evaluation.
MCP 0.2.2 also loads this guide from the saved run configuration and records its
exact sampling mask at each neural turn. Such opponents are explicitly labeled
neural+public-planner; route geometry is not attributed to learned discovery.
CPU/CUDA shared smoke checks match native actions and masks. Unknown guide
versions fail rather than silently dropping a sampling restriction.

`--guidance one-bus-public-plan-v2` is an optional continuation fix for new
training and baseline runs. When construction is complete but the next bus
purchase/order/start action is unavailable, it proposes the already legal WAIT
action and keeps the episode running. It adds no borrowing or cash. The
underfunded policy replay now records all 512 decisions and zero deliveries;
the fix improves failure accounting, not policy competence. Successful native
play remains unchanged. CUDA reset recovery is exact, with the same qualified
final model bytes, and the actual MCP smoke records the new guide version.

Saved runs bind their guide version, and checkpoint recovery rejects a version
change. For an explicit development diagnostic of existing planner-trained
weights, `infer_v2.py --guidance-override one-bus-public-plan-v2 ...` records
both the original training guide and the execution override. Keep these results
separate from the original evaluation. Omit the override to reproduce the saved
configuration; version 1 remains available. Preserve the archived collector
source when recovering an older checkpoint, as with other collector changes.

### Watch the live V2 network

The optional view-only SDL route uses the same OBSERVE/ACT/STEP boundary and
C++/LibTorch inference. The frozen raw-input 4,096-decision model replayed both
development maps visibly: all 1,024 native decisions and economic outcomes
matched its archived headless runs. CPU/CUDA probability and value errors were
at most 1.2e-7 and 1.91e-6. Native screenshots are retained. This is live neural
control with a public route planner. The optional ONNX deployment path below also
reproduces these complete visible episodes.

Build an isolated display engine, then launch one complete replay:

```bash
python scripts/dev/prepare_v2_playback.py \
  --base-engine-root "$RL_ROOT/v2-live-engine" \
  --engine-root "$RL_ROOT/v2-visible-engine-new" --jobs 2
python scripts/dev/infer_v2.py \
  --openttd "$RL_ROOT/v2-visible-engine-new/build/openttd" \
  --policy "$RL_ROOT/build/v2-live-policy/rl_dev_v2_infer" \
  --training-run "$RL_ROOT/runs/v2-roll64-budget4096-01/train" \
  --device cpu --mode greedy --seed 20260923 --split development \
  --map-seed 1630856436 --decisions 512 --visible \
  --output "$RL_ROOT/runs/v2-visible-new"
```

The qualified local display engine already exists at
`$RL_ROOT/v2-visible-engine-01/build/openttd`; reuse it to skip the build. Use
map seed 155097162 and a fresh output directory for the second development map.
The original headless engine remains available for training. The display build
uses SDL2 and a real X11/Wayland display (WSLg locally); dummy/offscreen drivers
are rejected. It currently supports one company and raw or signed-log weights.

Mouse and keyboard game commands are disabled in this viewer so they cannot
bypass the agent's action budget. Redrawing while waiting for requests preserves
native state, ticks and simulation RNG; closing the window aborts the replay.
The final native 1280x800 image is under `worker/screenshot/`; `run.json` records
its hash and display settings. Each run uses its own empty configuration and
local paths, preserving the user's ordinary game data.

### Export and watch a live V2 ONNX policy

The development exporter supports raw and `signed-log-v1` recurrent V2 weights.
It converts the C++ model's saved parameters, exports twice with identical
bytes, and checks all 512 archived inputs against native C++ inference. A package
binds the graph, source weights, observation schema, preprocessing and guide.
The optional C++ deployment target uses ONNX Runtime 1.28.0 on CPU for the neural
forward pass and retains LibTorch for input validation, masking and sampling.
Raw public tensors enter the graph; signed-log preprocessing is embedded once
inside the exported graph. Training, archive and package modes must agree.
The wrapper selects the recorded mode automatically. CUDA ONNX inference is
still rejected explicitly; CUDA PPO training remains separate.

To watch the already qualified local raw 4,096-decision model:

```bash
RL_ROOT=$HOME/.local/share/openttd-rl
source "$RL_ROOT/venv/bin/activate"
python scripts/dev/infer_v2.py \
  --openttd "$RL_ROOT/v2-visible-engine-01/build/openttd" \
  --policy "$RL_ROOT/build/v2-live-export-01/rl_dev_v2_onnx_infer" \
  --training-run "$RL_ROOT/runs/v2-roll64-budget4096-01/train" \
  --onnx-package "$RL_ROOT/runs/v2-live-onnx-package-01" \
  --device cpu --mode greedy --seed 20260923 --split development \
  --map-seed 1630856436 --decisions 512 --visible \
  --output "$RL_ROOT/runs/v2-onnx-visible-new"
```

Use a fresh output directory for each run. Choose map 155097162 for the second
development scenario. For headless evaluation, omit `--visible` and use
`$RL_ROOT/v2-live-engine/build/openttd`. `--mode sampled` uses the same native
seeded action sampler. The ONNX option requires `--training-run` and explicit
`--device cpu`; omit `--onnx-package` for the existing LibTorch path.

The completed signed-log 8,192-decision model also has a qualified package:

```bash
python scripts/dev/infer_v2.py \
  --openttd "$RL_ROOT/v2-visible-engine-01/build/openttd" \
  --policy "$RL_ROOT/build/v2-financial-export-01/rl_dev_v2_onnx_infer" \
  --training-run "$RL_ROOT/runs/v2-financial-eight-maps-budget8192-01/train" \
  --onnx-package "$RL_ROOT/runs/v2-financial-onnx-package-01" \
  --device cpu --mode greedy --seed 20260923 --split development \
  --map-seed 1630856436 --decisions 512 --visible \
  --output "$RL_ROOT/runs/v2-financial-onnx-visible-new"
```

This model still fails its learning economic gate. Its deployment qualification
does not replace the raw reference or establish stronger play.

For a new build, use the dependency versions and official ONNX Runtime archive
from the V1 export section above. Configure a fresh directory in the existing
Torch environment; the CUDA toolkit below is needed by that installed Torch
build, even though this deployment target runs on CPU:

```bash
cmake -S training/dev -B "$RL_ROOT/build/v2-onnx-new" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DRL_DEV_V2_POLICY=ON \
  -DCMAKE_PREFIX_PATH="$RL_ROOT/venv/lib/python3.12/site-packages/torch/share/cmake" \
  -DPython3_EXECUTABLE="$RL_ROOT/venv/bin/python" \
  -DCUDAToolkit_ROOT=/usr/local/cuda-12.6 \
  -DCUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda-12.6 \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.6/bin/nvcc \
  -DTORCH_CUDA_ARCH_LIST=7.5 \
  -DRL_DEV_ONNXRUNTIME_ROOT="$RL_ROOT/deps/onnxruntime-linux-x64-1.28.0"
cmake --build "$RL_ROOT/build/v2-onnx-new" --parallel 2 \
  --target rl_dev_v2_infer rl_dev_v2_onnx_infer rl_dev_v2_export_oracle
python scripts/dev/export_v2.py \
  --training-run "$RL_ROOT/runs/v2-roll64-budget4096-01/train" \
  --evaluation "$RL_ROOT/runs/v2-visible-full-01/map-1630856436" \
  --policy "$RL_ROOT/build/v2-onnx-new/rl_dev_v2_infer" \
  --output "$RL_ROOT/runs/v2-onnx-package-new"
```

To export another raw or signed-log model, supply its completed training directory and
a complete 512-step greedy development evaluation of those exact weights with
the same guide. Export reads retained tensor archives and never enters a final
evaluation split. `export.json`, `verification.json` and `golden.jsonl` record
the numeric comparison; `manifest.json` is written only after it passes. This
archived-input check is separate from running the package in a fresh game.

The local package has passed four full headless runs (greedy and sampled on both
development maps), with every one of 2,048 native decisions and economic outcomes
equal to its LibTorch references. Complete visible qualification and screenshots
are recorded in the progress log. The public planner continues to supply route
geometry; these checks establish deployment equivalence, not stronger learning.

## Native passenger and mail service

The separate cargo engine adds ordinary truck-stop construction and mail-vehicle
purchase to the live boundary. Build it from the existing composed bus engine:

```bash
python scripts/dev/prepare_cargo_live.py \
  --base-engine "$RL_ROOT/v2-live-engine" \
  --output "$RL_ROOT/v2-live-mail-engine-new" --jobs 2
python scripts/dev/cargo_live.py \
  --openttd "$RL_ROOT/v2-live-mail-engine-new/build/openttd" \
  --controller mail --split development --seed 1630856436 --decisions 512 \
  --output "$RL_ROOT/runs/live-mail-new"
python scripts/dev/coordinated_cargo.py \
  --openttd "$RL_ROOT/v2-live-mail-engine-new/build/openttd" \
  --split development --seed 1630856436 --decisions 512 \
  --output "$RL_ROOT/runs/live-passenger-mail-new"
```

Use `--controller wait` for the standalone control, and repeat with development
map seed `155097162` for the paired comparison. `report_cargo.py --runs RUN_A
RUN_B ... --output NEW_REPORT` requires the same engine, map set and full budget
for each controller and rederives economics from the native traces. It retains
failed episodes. Every run uses a fresh isolated configuration and output path.
The original bus engine, frozen patches and ordinary game data are preserved.
`prepare_cargo_live.py --refresh` archives a prior cargo executable before
rebuilding an edited development include.

Cargo mode advertises `openttd-rl-development-v2-cargo-live-1`, discovers native
mail-capable road vehicles, and exposes current public mail acceptance/supply,
own-vehicle cargo and each own station's bus/truck facility tiles. The controller
uses these locations to protect existing stops and resolve facilities that join
an existing station. Each road, stop, purchase, order and start still consumes
an ordinary action and 128 simulation ticks. Towns produce the mail naturally;
no fixture cargo, forced acceptance or SERVICE macro is used.

The coordinated script sustains both cargo types on the two fixed development
maps, with combined operating profits of 8,749 and 3,419. Construction leaves
cash after capital at -7,363 and -16,039. The earlier failed controllers remain
in the progress log. This is scripted native transport integration. Cargo mode
explicitly rejects the old bus `TENSORS` request; neural mail control and shared
cargo games are not implemented.

## Shared-company games and MCP

The optional shared slice alternates two companies on the same map. A 512-action
global budget gives each company 256 decisions and advances the whole economy
65,536 ticks. `shared_v2.py --openttd ENGINE --output NEW_RUN` checks eight steps;
add `--first-company 1` to reverse the actor order. It verifies ownership,
out-of-turn rejection and redaction of opponent internal fields. Research traces
retain simultaneous financial snapshots for both companies; actor responses do
not include those private snapshots. This is still a limited bus environment.

The MCP adapter uses the [official Python SDK](https://github.com/modelcontextprotocol/python-sdk)
over [stdio](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).
Keep its dependencies separate from the Torch environment:

```bash
uv venv "$RL_ROOT/mcp-venv"
uv pip install --python "$RL_ROOT/mcp-venv/bin/python" 'mcp==2.2.0'
"$RL_ROOT/mcp-venv/bin/python" scripts/dev/smoke_mcp_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --policy "$RL_ROOT/build/v2-live-policy/rl_dev_v2_infer" \
  --training-run "$RL_ROOT/runs/v2-ppo-new" --device cuda:0 \
  --output "$RL_ROOT/runs/mcp-smoke-new"
```

The smoke is a scripted MCP client controlling one company against saved neural
weights; it is **not** an LLM match. `mcp_v2.py` is the actual stdio server and
accepts the same binary/model arguments plus `--company`, `--first-company`,
`--decisions`, `--split` and an optional ledger `--map-seed`. Its tools are
`game_info`, `start_match`, `observe`, `legal_actions`, `submit_action`, `step`
and `wait_turns`, plus `map_region` for a public rectangle up to 32 by 32 tiles.
Company identity is fixed at launch. Stepping also executes the opponent's equal
turn. WAIT batches are limited to eight own turns and still consume every native
action/tick.
The adapter accepts raw and `signed-log-v1` weights. It validates the saved
training/model modes and checks the native policy's preprocessing before starting
the game. For the completed financial-feature policy, use
`--policy "$RL_ROOT/build/v2-financial-export-01/rl_dev_v2_infer"` and
`--training-run "$RL_ROOT/runs/v2-financial-eight-maps-budget8192-01/train"`.
This is LibTorch inference; the MCP adapter does not load an ONNX package.
Both preprocessing modes passed the actual eight-step scripted MCP checks.
The optional focused tests run in the SDK environment:
`"$RL_ROOT/mcp-venv/bin/python" -m unittest discover -s tests/dev -p test_mcp_financial_features.py -v`.
`start_match` and `observe` include the public map; `observe(include_map=false)`
and step results omit its large tile arrays while retaining own state and token.
`start_match(include_map=false)` also permits a compact first observation.
Call `observe` to inspect the updated map after either company constructs.
The native 60-second idle timeout aborts without simulating extra time. Calls,
model outputs, inference wall time and native economics are retained separately.
`mcp_player_console.py` relays JSON-line tool requests through an SDK client for
interactive controllers; it does not choose actions. Completed shared accounting
can be reproduced with `report_shared_v2.py --worker WORKER --output NEW_REPORT`.

The local LLM runner uses the existing Windows Ollama service through a
loopback-only Python bridge. It requires an already-installed model; it does not
download weights, use an external paid API, or alter Ollama/network settings.
First run `local_llm.py --host-python HOST_PYTHON --model MODEL --output NEW_PROBE`
to record a structured tool-call probe. For the installed model used here:

```bash
HOST_PYTHON=/mnt/c/Users/imsa/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe
LOCAL_MODEL=hf.co/unsloth/gemma-4-E2B-it-qat-GGUF:UD-Q4_K_XL
"$RL_ROOT/mcp-venv/bin/python" scripts/dev/play_mcp_llm_v2.py \
  --openttd "$RL_ROOT/v2-live-engine/build/openttd" \
  --policy "$RL_ROOT/build/v2-live-policy/rl_dev_v2_infer" \
  --training-run "$RL_ROOT/runs/v2-live-ppo-16u-01" --device cuda:0 \
  --host-python "$HOST_PYTHON" --model "$LOCAL_MODEL" \
  --company 0 --first-company 0 --map-seed 1630856436 \
  --decisions 8 --maximum-model-calls 64 --output "$RL_ROOT/runs/llm-smoke-new"
"$RL_ROOT/venv/bin/python" scripts/dev/verify_mcp_llm.py \
  --run "$RL_ROOT/runs/llm-smoke-new" --output "$RL_ROOT/runs/llm-audit-new"
```

This launches an actual LLM controller through the official MCP client. Use
`--decisions 512 --maximum-model-calls 1600` for the registered full development
budget. The model digest, prompt, tool schemas, bounded context, generation
settings, responses, tool errors, tokens and model wall time are saved. Warmup
precedes native game startup; model requests time out at 45 seconds. Sixteen
consecutive calls without advancing a turn or exhausting the model-call budget
abort with retained evidence. No script replaces unsuccessful model choices.
Optional nullable tool arguments are represented as optional scalar types for
Ollama; native validation remains unchanged. MCP 0.2.1 explicitly identifies
pending actions requiring `step`.

The completed eight-global-step LLM smoke proves this connection, not playing
strength: the LLM issued four stop-building commands at one tile, creating only
one stop, and neither company delivered passengers.
The full 512-decision development match also completed and passed the independent
audit: 256 actions per company, neither delivered passengers. Gemma made 1,272
model calls and 252 recoverable tool errors, taking 2,725.1 seconds excluding
warmup. This establishes actual MCP participation, not playing competence.
Temperature zero and a fixed seed do not
establish exact LLM reproducibility; recorded requests/responses and model
identity support audit. Provider cost is zero for these local requests; hardware
and electricity cost remain unknown. Neural and LLM runtime placement and wall
time are recorded separately from the shared economic clock.

`play_mcp_baseline_v2.py --controller one-bus-repay` (or `wait`) runs a distinctly
labeled scripted controller through the same MCP tools. It accepts the same
engine/policy/training-run/device/output/company/first-company/map-seed/decisions
arguments; it does not invoke an LLM. Use role swaps on the same registered maps
for descriptive comparisons, and preserve failed matches.

`--controller one-bus-repair` adds public road-connectivity checks every 16 own
turns after service starts. If the two existing stops become disconnected, it
plans a detour using currently exposed primitive road candidates; each road
command still consumes its ordinary turn. It does not rebuild the whole service
or use opponent-private observations. Four full map/role comparisons preserved
the fixed script's successful outcomes on one map and restored 818 and899
deliveries in the two roles on the disrupted map. The fixed script delivered zero
there after the opponent built a depot across a public through-road. All four
adaptive runs sustained positive operating/cash service in the final three
windows, but construction still left cumulative cash losses. This is an adaptive
scripted baseline, not a neural capability or a general reliability claim. Its
`repair_checks` and native action trace retain failed plans, spending and
subsequent connectivity checks.

Compare completed/failed registered full matches with:

```bash
python scripts/dev/report_mcp_matches.py \
  --runs "$RL_ROOT/runs/mcp-match-a" "$RL_ROOT/runs/mcp-match-b" \
  --output "$RL_ROOT/runs/mcp-comparison-new"
```

The report verifies common game/neural settings, rederives economic outcomes
from the shared native trace, and audits actual LLM calls when present. It keeps
tool failures, model identity, token counts and inference costs separate from
simulated cash and time; small map/role comparisons do not establish a ranking.

## Repository checks

For lossless compression of completed development logs and tensor snapshots,
see [artifact retention and restoration](STORAGE.md). Keep the latest run,
held-out evidence, source, models and checkpoints protected. This maintenance
workflow does not change training or its archived collector identities.

The optional inference CUDA experiment, its tensor layout, CPU oracle, numerical
tolerances and paired timing commands are described in
[CUDA_EXPERIMENT.md](CUDA_EXPERIMENT.md). It is disabled in ordinary builds.

```bash
python -m unittest discover -s tests/dev -v
bash scripts/v2/verify.sh --tier fast --tools-python /usr/bin/python3
git diff --check
```

The fast suite is a repository check, not live-game evidence. Use contract/full
tiers only with their documented dependencies and artifact roots. See
[V2 verification](project/V2_VERIFICATION.md) for those historical workflows.
On this Ubuntu host, `/usr/bin/python3` has `jsonschema` and shares its directory
with Git. The historical verifier resolves interpreter symlinks and restricts
PATH to tool directories, so the UV training virtual environment is unsuitable
for that wrapper: resolution loses its packages and leaves Git off PATH.
