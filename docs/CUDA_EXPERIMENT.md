# CUDA masked-distribution experiment

This optional development kernel accelerates **inference only**. The default
trainer and all PPO losses, gradients, Adam updates and CPU reference calculations
retain their existing LibTorch implementations. It is a performance experiment,
not a new learning algorithm or a claim of better gameplay.

## Why this operation

The measured 128-update live MLP run spent 1,216.8 seconds collecting/updating,
including 137.4 seconds in inference calls and 67.8 in update calls. Collection
dominates. A two-update Nsight API trace showed many small launches and stream
synchronizations. The initial standalone four-row distribution cost about 794
microseconds on CUDA versus 54 on CPU, including validation. These initial timings
overlapped another training run; use the repeated isolated comparison for results.

Nsight Systems 2024.5 did not provide GPU kernel/copy activity with the installed
13.3 driver. Its API durations are CPU-side durations, not kernel execution times.
The trace, diagnostic warnings and cProfile data are retained under
`~/.local/share/openttd-rl/runs/profile-live-cuda-01*`.

## Layout and execution

`training/dev/fused_policy_kernel.cu` receives contiguous row-major float32 logits
and bool masks shaped `[batch,41]`. It writes log probabilities and probabilities
of the same shape, plus one entropy and one integer status per row. Each block
owns one row and has 64 threads (two warps). Threads 0–40 load adjacent elements;
the remaining 23 use neutral reduction values and still reach every barrier.
Rows have a 41-element stride, so subsequent rows are not warp aligned.

The block reduces the maximum legal logit, sums exponentials after subtracting
that maximum, and then reduces entropy. It reuses 256 bytes of shared float
storage plus 256 bytes for validation flags. The finite check includes illegal
logits to preserve the reference's behavior. Invalid rows report an error before
their outputs can be used. Illegal probabilities are exactly zero and illegal
log probabilities are negative infinity. No fast-math compiler option is used.

The C++ wrapper selects the tensor's CUDA device and current LibTorch stream;
it does not assume stream zero. Inputs are already on the GPU. A single small
status copy back to the CPU synchronizes validation for all rows. This replaces
several separate validation reductions/synchronizations, while retaining explicit
errors. The surrounding trainer still transfers observations and returns sampled
actions through its existing service; the microbenchmark excludes those transfers.
The NVIDIA [SIMT programming guide](https://docs.nvidia.com/cuda/cuda-programming-guide/02-basics/writing-simt-kernels.html)
explains the execution model behind this block/reduction design.

## Correctness and limits

The trusted CPU `masked_categorical` is the oracle. Preregistered tolerances are
relative 1e-5, absolute 1e-6 for probabilities and 1e-5 for log probabilities and
entropy. Greedy actions and zero probability for illegal actions must match.
The native test covers 6,984 rows, scales through 1,000, sparse/full/single-action
masks, invalid inputs and a nondefault stream. Observed maximum absolute errors
were 3.8147e-6, 1.78814e-7 and 9.53674e-7 respectively for log probability,
probability and entropy.

The wrapper rejects autograd inputs: there is no custom backward implementation.
PPO stores the actual behavior log probability and exact sampling mask as before.
Small float rounding differences between backends may change training weights;
cross-backend bitwise checkpoint equivalence is not claimed. Resume comparisons
bind the executable hash and apply within the same backend/build.

Compute Sanitizer was attempted but failed because the host WDDM debugger
interface was unavailable and it reported unsupported device. Numerical checks
passed in that process; memory/race sanitizer verification remains unavailable.
No host administrator/debugger configuration was changed.

## Reproduce

Use the existing WSL Torch environment and a separate build directory:

```bash
RL_ROOT=$HOME/.local/share/openttd-rl
python scripts/dev/local.py build --build-dir "$RL_ROOT/build/ppo-fused" \
  --cuda-root /usr/local/cuda-12.6 --fused-policy --jobs 2
ctest --test-dir "$RL_ROOT/build/ppo-fused" --output-on-failure
python scripts/dev/benchmark_policy.py \
  --executable "$RL_ROOT/build/ppo-fused/rl_policy_benchmark" \
  --output "$RL_ROOT/runs/fused-microbenchmark-new"
python scripts/dev/compare_training_backends.py \
  --reference "$RL_ROOT/build/ppo/m08_trainer" \
  --candidate "$RL_ROOT/build/ppo-fused/m08_trainer" \
  --openttd "$RL_ROOT/engine/build/openttd" \
  --instance-dir "$RL_ROOT/engine/instances" \
  --output "$RL_ROOT/runs/fused-live-comparison-new"
```

The build uses the detected compute capability (7.5 on this RTX 2070) and fails
if CUDA is unavailable; it does not substitute CPU training. The paired live
comparison alternates reference/candidate order, checks byte-identical native
action/state/economic traces and bounded update-metric error, then reports total
collection/update wall time. Run it without other training or evaluation jobs.
Source archives, executable hashes and raw repetitions accompany the reports.
See [PROGRESS.md](PROGRESS.md) for executed results and whether adoption is supported.

## Subsequent measured CPU bottleneck

The retained cProfile capture attributes 14.9 of 34.6 collector seconds to repeated
validation of the 32,768-element spatial input. Instrumentation amplifies Python
call overhead, so this identified a candidate rather than predicting speedup.
The development `policy_inputs.py` checks the same decoded JSON array with NumPy,
rejects nonnumeric/nonfinite/out-of-range or incorrectly shaped values, and returns
the original list. It changes neither the serialized float32 inputs nor PPO math.

`spatial-validation-live-comparison-01` uses the same CUDA trainer for both sides,
three alternating process pairs, four updates per run and no concurrent training
or evaluation. All 1,536 paired native transitions, every PPO metric and final
model IDs match exactly. End-to-end speedups are 1.228x, 1.147x and 1.144x; median
1.147x. The new development CLI default is `--spatial-validation vectorized`, with
`reference` retained for reproducing older comparisons. This is a CPU validation
improvement, not a CUDA-kernel speedup. Actual 64-step CUDA checkpoint continuation
also matches reference mode, including 512 continuation transitions and final model.

```bash
python scripts/dev/compare_training_backends.py \
  --reference "$RL_ROOT/build/ppo-credit/m08_trainer" \
  --candidate "$RL_ROOT/build/ppo-credit/m08_trainer" \
  --openttd "$RL_ROOT/engine/build/openttd" \
  --instance-dir "$RL_ROOT/engine/instances" \
  --candidate-spatial-validation vectorized --pairs 3 --updates 4 \
  --output "$RL_ROOT/runs/spatial-validation-comparison-new"
```
