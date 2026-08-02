# Version 1 release reproduction and operator guide

## Supported release profile

Version 1 is accepted on Ubuntu 24.04 x86_64 with GCC 13.3, CMake 3.28,
Ninja 1.11, OpenTTD 15.3 at upstream commit
`29f808ef0022064e6d9a83c8476d1e0f4686af86`, OpenGFX 8.0, ONNX Runtime
1.28.0 CPU, LibTorch 2.13.0 with CUDA 13.0, and the pinned NVIDIA runtime.
The measured GPU release path is an RTX 5070 with compute capability 12.0.

The release gate requires a fresh local clone at a clean `main` commit equal to
`origin/main`; it never builds in the working checkout. Build, test, training,
and playback outputs must be new absolute paths outside the repository. A clean
host means this supported software and pinned dependency cache are already
present. M12 does not install a display driver or CUDA toolkit onto a bare OS.

## Verify a clean source and dependency boundary

Clone without local modifications, initialize the upstream object repository,
and verify the two source identities before doing any work:

```bash
git clone https://github.com/goldbar123467/openttd-cuda-rl.git /absolute/work/openttd-rl
cd /absolute/work/openttd-rl
git checkout main
git submodule update --init openttd-upstream
git status --short
git rev-parse HEAD
git rev-parse origin/main
git -C openttd-upstream rev-parse HEAD
```

The first command must print no status records, the two outer commits must be
equal, and the upstream commit must be the pinned value above. Validate the
project, release contract, and dependency cache before building:

```bash
./scripts/v1/traceability.sh
./scripts/v1/run_m12_foundation_tests.sh
python3 scripts/v1/validate_m12_release_contract.py \
  config/v1/m12-release-contract.json \
  docs/project/schema/v1-m12-release-contract.schema.json
python3 scripts/v1/validate_dependency_cache.py \
  --lock config/v1/dependency-lock.json \
  --schema docs/project/schema/v1-dependency-lock.schema.json \
  --cache-root /absolute/cache/root
```

`shellcheck` must resolve to an executable. On the accepted Ubuntu profile the
normal repair is `sudo apt-get install shellcheck`, followed by
`command -v shellcheck` and `shellcheck --version`. Do not replace it with a
non-executable download or a shell alias.

## Canonical full release command

`scripts/v1/run_m12_release_gate.py` is the authoritative clean-room workflow.
It validates all accepted M01 through M11 inputs, clones the current commit,
composes the frozen OpenTTD result tree, builds headless and playable variants,
runs all native and repository tests, rebuilds the C++/CUDA training stack,
reproduces reset/training/recovery/playback, and writes the canonical V1 release
manifest. Use `--help` for the complete argument inventory.

Provide absolute paths for the following input classes:

- the repository and `openttd-upstream` object repository;
- the OpenGFX archive, ONNX Runtime root, `Torch_DIR`, and NVIDIA runtime root;
- the accepted combined ONNX package and M02 template directory;
- the accepted M06 training OpenTTD executable;
- each retained M01 through M11 evidence root, including the separate M07
  recovery, M08 CUDA, and M09 training roots; and
- one new artifact root that does not already exist.

Run without `--allow-preclosure` for an accepted release. A successful final
line has this form:

```text
M12_RELEASE_GATE=PASS mode=final campaigns=12 requirements_passed=217 manifest_sha256=<semantic-sha256>
```

Validate the emitted file independently:

```bash
python3 scripts/v1/validate_m12_release_contract.py \
  config/v1/m12-release-contract.json \
  docs/project/schema/v1-m12-release-contract.schema.json \
  --manifest /absolute/artifacts/v1-release-manifest.json \
  --manifest-schema docs/project/schema/v1-m12-release-manifest.schema.json
sha256sum /absolute/artifacts/v1-release-manifest.json
```

The manifest records source/host/build/dependency identities, every compatibility
contract, all seed families, counters, content hashes, 12 campaign results,
quality checks, traceability, defects, and clean reproduction state. The
top-level `manifest_sha256` is its semantic canonical identity; `sha256sum` is
the digest of the complete file and is intentionally recorded separately.

## Build and test the components directly

The release runner is preferred because it also composes the exact M11 OpenTTD
tree. For diagnosis after composition, its build commands are equivalent to:

```bash
cmake -S /absolute/composed/openttd -B /absolute/build/headless -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DOPTION_RL_ENVIRONMENT=ON -DOPTION_RL_NEURAL_AGENT=OFF \
  -DOPTION_USE_ASSERTS=ON
cmake --build /absolute/build/headless --parallel 4
ctest --test-dir /absolute/build/headless --output-on-failure

cmake -S /absolute/composed/openttd -B /absolute/build/playable -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DOPTION_RL_ENVIRONMENT=ON -DOPTION_RL_NEURAL_AGENT=ON \
  -DOPTION_USE_ASSERTS=ON \
  -DOPENTTD_RL_PROJECT_ROOT=/absolute/work/openttd-rl \
  -DOPENTTD_RL_ONNXRUNTIME_ROOT=/absolute/dependencies/onnxruntime-1.28.0
cmake --build /absolute/build/playable --parallel 4
ctest --test-dir /absolute/build/playable --output-on-failure

cmake -S training/v1 -B /absolute/build/training -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DTorch_DIR=/absolute/dependencies/libtorch/share/cmake/Torch \
  -DV1_NVIDIA_RUNTIME_ROOT=/absolute/dependencies/nvidia-runtime \
  -DV1_ONNXRUNTIME_ROOT=/absolute/dependencies/onnxruntime-1.28.0
cmake --build /absolute/build/training --parallel 2
ctest --test-dir /absolute/build/training --output-on-failure
```

Copy the exact OpenGFX 8.0 tar into each OpenTTD build's `baseset` directory
before CTest or runtime. The playable binary must resolve ONNX Runtime and
OpenSSL, and must not resolve LibTorch, CUDA, Python, a trainer, or optimizer.

## Train, resume, evaluate, and export

The accepted training campaign is preregistered; do not alter budgets or inspect
final templates during model selection. Run all three architectures with:

```bash
python3 scripts/v1/run_m09_training.py \
  --root /absolute/work/openttd-rl \
  --trainer /absolute/build/training/m08_trainer \
  --openttd /absolute/build/headless/openttd \
  --instance-dir /absolute/instances \
  --artifact-root /absolute/artifacts/m09-training
```

Check exact interrupted-process recovery with
`scripts/v1/run_m07_recovery.py`. The service executable also accepts
`--resume /absolute/checkpoint`; a resumed service obtains its run seed and RNG
states from the checkpoint, so do not also pass a new seed. Corrupt,
incompatible, incomplete, or numerically failed checkpoints must not be used.

Evaluate in a separate optimizer-free process:

```bash
python3 scripts/v1/run_m09_evaluation.py \
  --root /absolute/work/openttd-rl \
  --openttd /absolute/build/headless/openttd \
  --evaluator /absolute/build/training/m09_evaluator \
  --instance-dir /absolute/instances \
  --training-root /absolute/artifacts/m09-training \
  --artifact-root /absolute/artifacts/m09-evaluation
```

Export and validate packages with `scripts/v1/run_m10_package_gate.py`. The gate
requires the frozen M10/PPO/architecture/reward contracts, exporter Python and
script, native and deployment evaluators, source-package root, independent
evaluation report, OpenTTD executable, and templates. Promotion is allowed only
after all native/standalone/in-game equivalence and mutation checks pass.

## Install and watch a policy

Install the complete content-addressed package atomically under
`openttd-rl/models/<package-id>`. Never merge or edit files in an installed
package. The directory must contain exactly `INSTALL.md`, `evaluation.json`,
`golden.jsonl`, `manifest.json`, and `model.onnx`.

Create the canonical playback JSON documented in
`docs/project/M11_NORMAL_GAME_PLAYBACK.md`, then launch:

```bash
/absolute/build/playable/openttd \
  -I OpenGFX \
  -A /absolute/run/playback.json
```

The normal-game controller supports greedy or explicitly seeded stochastic
inference, intervals from 128 through 1024 ticks in multiples of 128, an action
log, a native inspection window, agent pause/resume, and one-agent-action step.
Missing or incompatible packages fail before control. A runtime inference fault
disables the agent and never substitutes scripted, random, or stale actions.

## Troubleshooting

- A dirty repository, detached/non-`main` checkout, or `main` unequal to
  `origin/main` is a hard release failure. Commit intentional work and push it,
  then start from a fresh output root.
- An existing artifact root is rejected to prevent evidence mixing. Choose a
  new absolute directory; do not reuse a failed root as accepted evidence.
- Missing graphics during CTest means the exact OpenGFX tar was not staged in
  the build `baseset` directory.
- `libonnxruntime.so.1 => not found` means the pinned runtime is absent from the
  loader path or was not supplied at configure time. Do not silently substitute
  another ONNX Runtime version.
- A CUDA device/profile rejection is expected on unsupported hardware. The V1
  release claim is only the frozen CUDA 13.0, compute-capability-12 path.
- CUDA out-of-memory, NaN/Inf, protocol corruption, or worker loss are terminal
  failure classes. Preserve their diagnostics and resume only from the last
  verified checkpoint.
- Package/schema/digest failures are integrity failures. Re-export to a new
  content-addressed package instead of repairing an immutable package in place.

The accepted identities and campaign outcomes are summarized in
`docs/project/G12_GATE_REPORT.md`; the machine release manifest remains the
authority for a particular reproduction.
