# 05 — Custom CUDA kernel review

Static review of commit `0595a72`. The kernel was not compiled, run, sanitized or
profiled for this report. Numbers quoted as "recorded" come from the repository's
own documents, with citations. All other quantities are arithmetic on code
constants.

The kernel is CUDA C++ (`.cu`, nvcc via CMake `enable_language(CUDA)`), called from
C++/LibTorch. There is no Python or Triton layer, so the advice below is written for
CUDA C++ with LibTorch streams and allocators.

---

## 1. Location and every call site

| Item | Path | Lines |
| --- | --- | --- |
| Kernel `policy_kernel` | `training/dev/fused_policy_kernel.cu` | 8–63 |
| Host launcher `launch_fused_policy` | `training/dev/fused_policy_kernel.cu` | 66–70 |
| Launcher declaration | `training/dev/fused_policy_kernel.h` | 3–4 |
| LibTorch wrapper `openttd_rl::development::fused_policy` | `training/dev/fused_policy.cpp` | 10–37 |
| Wrapper declaration | `training/dev/fused_policy.h` | 7 |
| **Production call site** | `training/v1/src/multimodal_trainer.cpp` in `MultiModalPpoTrainer::act` | 113–121 (`#ifdef RL_DEV_FUSED_POLICY`, and only when `device_.is_cuda()`) |
| Test | `training/dev/fused_policy_test.cpp` | 20–80 |
| Microbenchmark | `training/dev/policy_benchmark.cpp` | 50–67 (fused block) |
| Build option | `training/dev/CMakeLists.txt` | 6, 51–63, 115–121 |
| Build switch and architecture | `scripts/dev/local.py` | 103, 112–116, 174–175 |
| Benchmark and live comparison drivers | `scripts/dev/benchmark_policy.py`; `scripts/dev/compare_training_backends.py` | whole files |
| Design and results | `docs/CUDA_EXPERIMENT.md`; `docs/PROGRESS_HISTORY_2026-09-23.md:361-423`; `docs/PROGRESS.md:1198-1200` | |

**Reachability of the production call site.** `MultiModalPpoTrainer::act` is
invoked by:

- the M08 service `handle_act` (`m08_trainer_main.cpp:227`), which is what the live
  collector uses;
- `m08_architecture_smoke_main.cpp:99,110` (synthetic learning smoke);
- tests (`m08_native_tests.cpp:188,212`);
- development checks (`export_preserves_trainer.cpp:32-61`, `checkpoint_roundtrip.cpp:30`).

The live collector reaches it twice per time step
(`run_m08_live_architectures.py:100` for the sampled ACT and 116–121 for the
deterministic bootstrap ACT) and in the embedded probes (223–228).

**Paths that do not use the kernel:**

- `MultiModalPpoTrainer::update` uses reference `masked_categorical`
  (`multimodal_trainer.cpp:160`) for autograd.
- The M09 CPU evaluator (`evaluation_model.cpp:337`).
- ONNX deployment.
- All of V2, which uses a hierarchical 4,096-candidate distribution
  (`v2_live_input.cpp:214-232`).
- The M07 structured-only trainer (`trainer.cpp`).

The option defaults to OFF, so **default builds never run the kernel**.

---

## 2. What it computes

For each row `b` with logits `x ∈ R^41` and legal mask `m ∈ {0,1}^41`:

```
M        = max_{i: m_i} x_i                                   (reduction 1, plus a nonfinite OR over all 41)
s_i      = x_i − M                         (legal)            -∞ (illegal)
Z        = Σ_{i: m_i} exp(s_i)                                 (reduction 2)
logp_i   = s_i − log Z                     (legal)            -∞ (illegal)
p_i      = exp(logp_i)                     (legal)             0 (illegal)
H        = Σ_{i: m_i} −p_i · logp_i                            (reduction 3)
status_b = 1 if any x_i nonfinite (legal or not) or H nonfinite;
           2 if no legal action (M = −∞); 0 otherwise
```

This matches the reference `masked_categorical` (`ppo.cpp:144-165`):

- `masked_fill(-inf)` then `log_softmax`;
- probabilities `where(mask, exp(logp), 0)`;
- entropy with zeroed illegal log-probabilities;
- rejection of any nonfinite logit, including illegal ones, and of all-illegal rows.

The only numerical difference is summation order in the tree reduction versus
ATen's softmax kernels.

## 3. Inputs, shapes and memory layout

| Tensor | dtype | Shape | Layout | Bytes per row |
| --- | --- | --- | --- | --- |
| `logits` (in) | float32 | `[B, 41]` | contiguous, row-major, row stride 41 elements | 164 |
| `mask` (in) | bool (1 byte) | `[B, 41]` | contiguous, row stride 41 | 41 |
| `log_probabilities` (out) | float32 | `[B, 41]` | `empty_like(logits)` | 164 |
| `probabilities` (out) | float32 | `[B, 41]` | `empty_like(logits)` | 164 |
| `entropy` (out) | float32 | `[B]` | contiguous | 4 |
| `status` (out) | int32 | `[B]` | contiguous | 4 |

Wrapper preconditions (`fused_policy.cpp:12-18`): CUDA, same device, float32 and
bool dtypes, 2-D, 41 columns, `1 ≤ B ≤ 65,535`, contiguous inputs, no
`requires_grad`.

Rows start at byte `164·b` for floats and `41·b` for the mask, so they are not
aligned to 128-byte segments. Lanes 0–31 of a row read one contiguous 128-byte span
and lanes 32–40 read the next 36 bytes. In practice B = 4 in collection (the
ENVIRONMENT_COUNT) and ≤ 64 at the service boundary (`m08_trainer_main.cpp:220`).

## 4. Launch configuration

- `policy_kernel<<<rows, 64, 0, stream>>>` (`fused_policy_kernel.cu:69`): **one
  block per row, 64 threads (2 warps)**, no dynamic shared memory.
- Static shared memory: `float reduction[64]` + `int invalid[64]` = 512 bytes.
- Stream: `c10::cuda::getCurrentCUDAStream()` under a `CUDAGuard` for the input's
  device (`fused_policy.cpp:19, 26`). This respects LibTorch stream semantics; a
  nondefault stream is tested (`fused_policy_test.cpp:28`).
- `C10_CUDA_KERNEL_LAUNCH_CHECK()` runs after the launch (27). Asynchronous faults
  surface at the following `status.cpu()` (30).
- Architecture: a single detected compute capability (`local.py:112-116` →
  `CMAKE_CUDA_ARCHITECTURES`). A bare `75` generates both SASS and PTX, so newer
  GPUs can JIT it. There is no hard-coded `sm_120`. **OK** per AGENTS.md.

---

## 5. Correctness review

| Check | Finding | Label |
| --- | --- | --- |
| Barrier uniformity | All 64 threads reach every `__syncthreads()`. The early `return` at 32–35 depends only on `reduction[0]` and `invalid[0]`, read after the loop's final barrier, so it is block-uniform. The comment at 31 is accurate. | OK |
| Shared-memory races | `reduction[0]` is read at 29 before the array is rewritten at 39; the barrier at 37 separates them. The same holds for 45→48→49 and for the final read at 60 after the loop barrier. `invalid[]` is never reused. | OK |
| Out-of-bounds reads | Inactive lanes (41–63) never dereference `mask` or `logits`: `active && mask[offset]` short-circuits, and the ternary guards `logits[offset]` (14–16). Reduction reads are at most `lane + stride = 63`. | OK |
| Index overflow | `row * 41 + lane` is `int`; `B ≤ 65,535` gives < 2.7M. | OK |
| Numerical stability | The max is subtracted; Z ≥ 1 because the max element contributes exp(0), so `logf` is finite. Underflowing exps give p = 0 with a finite logp, so the entropy term is 0, not NaN. There is no fast-math (`CUDA_EXPERIMENT.md`). | OK |
| Nonfinite inputs | The flag includes illegal lanes, matching the reference's fail-closed behavior. A legal ±inf or NaN gives status 1. | OK |
| All-illegal row | M = −∞ gives status 2, which the wrapper maps to `invalid_argument("all-illegal action mask")` (`fused_policy.cpp:33`), matching the reference message. | OK |
| Outputs on error | The error branch leaves `logp`, `probability` and `entropy` uninitialized (`torch::empty`), but the wrapper throws before returning (32–35). | OK |
| Status encoding | Code 1 means both "nonfinite input" and "nonfinite entropy" (30, 61). | Minor (diagnostics only) |
| Mask dtype contract | The wrapper requires `kBool` (13). The reference accepts any dtype via `.to(kBool)` (`ppo.cpp:155`). The call site passes `legal_masks.to(device_)` without normalizing the dtype (`multimodal_trainer.cpp:117`). Every current caller passes bool (`m08_trainer_main.cpp:205`; tests), so this is latent. | Minor latent API difference |
| Device and stream | The guard and current stream are used, and the status copy is on the same stream. | OK |
| Test coverage | 6,984 rows: B ∈ {1, 4, 64, 513}; scales {0, 1, 20, 1000}; three mask patterns; invalid dtypes, devices and strides; autograd rejection; NaN and inf in an illegal lane; nondefault stream (`fused_policy_test.cpp:31-72`). **Missing:** a *mixed* batch where only one row is all-illegal or nonfinite; a legal-lane inf; the B = 65,535 and 65,536 boundary; extreme finite spreads (±1e38) against the reference; non-contiguous `mask`. | Gap |
| Memory checker | Compute Sanitizer could not run under WSL/WDDM (`CUDA_EXPERIMENT.md`). There is no memcheck, racecheck, synccheck or initcheck evidence. | Gap (recorded honestly) |

**No correctness defect was found in the kernel.**

## 6. Is the output used correctly?

At the call site (`multimodal_trainer.cpp:116-131`):

- Only `device_policy.log_probabilities` is consumed. It is copied to the CPU (124),
  used for sampling or `argmax` (126–130), and gathered for the selected action
  (131). **`probabilities` and `entropy` are computed, written and discarded.**
- Greedy actions: argmax over logp with −∞ on illegal lanes always picks a legal
  action. The test checks that greedy matches the reference
  (`fused_policy_test.cpp:47`).
- Sampling: `sample_masked_actions` re-derives p = exp(logp) in float64 on the CPU
  and re-validates the mask and finiteness (`rng.cpp:103-108`). This duplicates the
  kernel's validation but is correct.
- **Behavior versus learner.** The stored behavior logp comes from the kernel. The
  PPO ratio's numerator comes from the reference `masked_categorical` on the same
  device (`multimodal_trainer.cpp:160-161`). The documented error bound (maximum
  recorded 3.8e-6 in logp) keeps the ratio within about 4e-6 of 1 at epoch 0.
  **This use is valid**, but it rests on test evidence rather than a runtime check.
  See 02 §2.1: add a behavior-replay audit to V1, as in V2.
- Checkpoint and resume: exactness claims apply within one binary. The recorded
  compatibility binds `trainer_sha256` (`live_checkpoint.py:54-56`), so fused and
  reference runs cannot be silently mixed. **OK.**

---

## 7. Performance analysis

### 7.1 Inside the kernel

| Aspect | Observation | Consequence at B = 4…64 |
| --- | --- | --- |
| Memory access | About 205 bytes read and about 336 bytes written per row, with coalesced but unaligned rows. The whole working set is a few KB. | Bandwidth is irrelevant; the kernel is latency-bound. |
| Redundant work | `probabilities` and `entropy` are unused by `act()`. `p = expf(lp)` recomputes an exponential already taken as `expf(shifted)`; it could be `e/Z`, but that changes rounding relative to the reference. `status` duplicates checks that `sample_masked_actions` repeats on the CPU. | A few extra instructions per lane. Negligible. |
| Parallelism | One block per row, so B = 4 means 4 blocks. Most SMs sit idle; there is no intra-row parallel slack beyond 41 lanes. | GPU utilization is necessarily tiny. That is inherent to the problem size, not a kernel flaw. |
| Occupancy | 64 threads, 512 B of shared memory and few registers per block. Theoretical occupancy is high, but grid size, not occupancy, is the limit. | Occupancy tuning cannot help. |
| Branch divergence | Warp 1 has 9 active lanes (32–40) and 23 idle. In reductions `if (lane < stride)` idles warp 1 from stride 32 down and diverges within warp 0 for stride ≤ 16. `legal ? … : …` compiles to selects. | Minor, standard for tree reductions. |
| Synchronization | The success path has **23 `__syncthreads()`** (1 + 6 + 1 + 1 + 6 + 1 + 1 + 6). Three sequential reductions form a long dependency chain. | It sets the kernel's latency floor. Warp shuffles would shorten it (§9, K7). |
| Launch overhead | 1 launch per call plus 4 caching-allocator `empty` calls (`fused_policy.cpp:20-23`). | Comparable to or larger than the kernel's execution time (Hypothesis). The repository has no kernel-only timing, because Nsight lacked kernel tables (`PROGRESS_HISTORY:369-372`). |
| Host sync | 1 blocking D2H copy of `status` (`fused_policy.cpp:30`). | Replaces the reference path's 4 `.item()` syncs (`ppo.cpp:154, 156, 160, 163`). This is the kernel's real advantage. |
| Batching | The collector issues two ACTs of B = 4 per time step. There is no batching across time or across calls. | See §8: this call structure, not the kernel, bounds throughput. |

### 7.2 Surrounding code that erases the kernel-level speedup

One sampled ACT at B = 4 in the fused build passes through these stages:

| # | Stage | Code | Volume or ops (code-derived) |
| --- | --- | --- | --- |
| 1 | Python row validation: structured, spatial (reference or vectorized), mask | `run_m08_live_architectures.py:96-98` | 4 × 32,768 spatial values |
| 2 | Python `struct.pack` and pipe write | `m08_trainer_client.py:164-170` | ≈ 528 KB request (4 × 132,096 + 164 + 5) |
| 3 | C++ element-wise decode | `m08_trainer_main.cpp:173-215` | 132,096 `Reader::f32` calls + 164 mask bytes |
| 4 | H2D: structured, **spatial**, mask; pageable, blocking | `multimodal_trainer.cpp:112, 117` | 4 KB + **512 KB** + 164 B. For `structured-mlp-v1`, **spatial is never read by the forward pass** (`multimodal_model.cpp:134-139`). |
| 5 | Forward | `multimodal_model.cpp:128-158` | MLP: about 6–8 small kernels; the CUDA path avoids syncs (27–30) |
| 6 | **Kernel** + status D2H + sync | `fused_policy.cpp:24-35` | 1 launch, 1 blocking copy |
| 7 | 3 more D2H copies: logits, values, log-probabilities | `multimodal_trainer.cpp:122-124` | 3 blocking copies |
| 8 | CPU sampling and checks | `rng.cpp:94-128`; `multimodal_trainer.cpp:131-132` | small |
| 9 | Response encode and Python decode | `m08_trainer_main.cpp:228-241` | 4 × 24 bytes |

Then per time step:

- the collector steps 4 games **sequentially** through 4 bridge round trips each
  (`run_m08_live_architectures.py:105-114`; see 04 §2);
- it issues a **second full ACT** (stages 1–9 again) whose only used output is
  `value` (116–121, 146).

**Recorded consequences:**

- **Microbenchmark** (`PROGRESS_HISTORY:410-414`): at B = 4, the reference CUDA path
  took 763.70 µs, the fused path 79.39 µs and the **CPU path 53.91 µs**. So even the
  fused GPU distribution was slower than the CPU distribution at the collector's
  batch size. The fused path wins only at B ≥ 64 (79.38 vs 97.86 µs) and B = 512.
- **Live paired runs** (`PROGRESS_HISTORY:416-423`): inference-call time fell
  4.54–4.59 s → 3.80–3.90 s per four-update run, out of about 38.4 s total; the
  end-to-end median was **1.0047×**. By arithmetic on those recorded values, the
  saving was about 0.7 s of about 38.4 s (under 2%), so even a perfect transfer to
  wall time could not exceed about 1.02×.
- **Ceiling for any inference work in V1:** 137.4 s of 1,216.8 s in the 128-update
  run (`PROGRESS_HISTORY:362-364`). Removing inference entirely would bound the
  speedup at about 1.13× (arithmetic on recorded values). Inference-call time
  includes stages 1–3 and 7–9, which the kernel does not touch.

**Conclusion.** The kernel correctly and substantially speeds up its own operation.
The surrounding Python serialization, per-element decoding, unused-spatial
transfers, blocking copies and the duplicate bootstrap ACT erase that gain end to
end. Further kernel tuning cannot change this.

---

## 8. What would actually move ACT and collection time

These are call-site and pipeline changes. They are listed here because the task
asks which surrounding code erases kernel speedups. Each is output-preserving and
verifiable with byte-identical traces.

1. **Defer the bootstrap value.** For environments whose transition continued, the
   next step's sampled ACT computes V(s') for the identical observation under
   identical weights (no update inside a rollout). Only truncated environments and
   the final rollout step need a separate value request. This roughly **halves ACT
   calls**. It must be done in a new development collector; the frozen
   `run_m08_live_architectures.py` must not be edited.
2. **Drop spatial for `structured-mlp-v1`.** Skip Python spatial validation and
   packing, C++ decode, and the H2D copy in `act()` and `update()`. UPDATE frames are
   ≈ 99% spatial bytes: 131,072 of 132,179 bytes per sample (code-derived from
   `m08_trainer_main.cpp:251-281`). Removing them also lifts the 64 MiB frame bound
   that currently limits `--rollout-length` to 32 or 64 (`train_live.py:53-54`):
   512 samples × 132,179 = 67,675,648 bytes > 67,108,864.
3. **Collapse D2H traffic into one copy.** For example,
   `torch::cat({logits, values.unsqueeze(1), logp, status_as_float}, 1).cpu()`, or a
   pinned host buffer with a single copy. That leaves one sync per ACT instead of 4
   (fused) or 7 (reference).
4. **Compute the 41-way distribution on the CPU from the logits that `act()`
   already copies** (`multimodal_trainer.cpp:122`). The recorded microbenchmark says
   CPU was the fastest option at B = 4, and it would remove the kernel launch,
   allocations and status sync altogether. It keeps behavior and learner
   implementations different (CPU vs GPU), exactly as the fused build does today,
   so it needs the same tolerance evidence.
5. **Step environments concurrently.** Send STEP, OBSERVE and LEGAL_ACTIONS to all 4
   workers before reading responses, or use one process per environment. Game time
   dominates the unattributed remainder; this also needs a development collector.

---

## 9. Ranked proposals (impact × risk)

"Impact" means the likely effect on end-to-end V1 CUDA training throughput, judged
from the recorded ceilings in §7.2. None is measured. Verification is described in
§10 and §11.

| Rank | ID | Change | Files | Likely end-to-end impact | Risk | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | K3 | Defer bootstrap values; value-only requests for truncations and rollout end | new `scripts/dev/collect_live.py` (development collector), optional VALUE request in `m08_trainer_main.cpp` | Medium: about half of all ACT round trips removed (Hypothesis until measured) | Medium: must prove bitwise-identical `next_value` | Largest ACT-side lever |
| 2 | K2 | Structured-only protocol for MLP (no spatial in ACT, UPDATE or validation) | development collector; `m08_trainer_main.cpp` (new message types); `multimodal_trainer.cpp` | Medium for MLP runs (the per-ACT and UPDATE byte volume falls about 99%) | Medium: protocol versioning; CNN paths unchanged | Also enables rollout 128 |
| 3 | K1 | In `act()` and `update()`, skip `spatial.to(device_)` when `kind == StructuredMlp` | `multimodal_trainer.cpp:112, 152` (pass an undefined tensor, or keep it on CPU; `forward` ignores it) | Low–Medium: 512 KB H2D per ACT and 4 MiB per minibatch removed | Low | Pure C++; no protocol change |
| 4 | K4 | Single D2H copy per ACT (concatenate outputs, pinned buffer) | `multimodal_trainer.cpp:113-131`; `fused_policy.cpp:30` | Low | Low | Removes 3 blocking copies |
| 5 | K12 | CPU distribution for small B (heuristic threshold, recorded in run metadata) | `multimodal_trainer.cpp:113-121` | Low | Low: a numerics note like the fused build's | Supported by recorded B = 4 CPU < fused |
| 6 | K5 | Value-only fast path for deterministic bootstrap ACTs (skip the distribution) | `multimodal_trainer.cpp` plus a flag | Low (subsumed by K3) | Low | |
| 7 | K6 | Pinned, reused staging buffers; `non_blocking` H2D | `multimodal_trainer.cpp` | Low | Low | Only after K1/K2 |
| 8 | K7 | Kernel: **warp-per-row** with `__shfl_xor_sync` (lane l handles elements l and l+32 when l < 9), 4–8 rows per block, 2 passes (max, then joint `(Z, Σ e·s)` giving `H = log Z − Σ e·s / Z`), no shared memory and no `__syncthreads` | `fused_policy_kernel.cu` | **Negligible end to end**; shorter kernel latency | Low–Medium: summation order changes; re-verify tolerances | A good CUDA learning exercise; not a throughput fix |
| 9 | K8 | Kernel: template flag to skip unused `probabilities`/`entropy` writes; `const __restrict__` pointers | `fused_policy_kernel.cu`, `fused_policy.cpp` | Negligible | Low | Keep the full-output variant for tests and benchmarks |
| 10 | K9 | Distinct status codes (1 input nonfinite, 2 all-illegal, 3 entropy nonfinite) and the failing row index in the error message | `fused_policy_kernel.cu:30,61`; `fused_policy.cpp:32-35` | None (diagnostics) | Low | |
| 11 | K10 | CUDA Graph capture of the whole `act()` at fixed B = 4 | `multimodal_trainer.cpp` | Low (bounded by the ≈ 11% inference share) | High: needs sync-free, static buffers; two graphs for B = 1 and B = 4 | Only if K1–K4 leave launch overhead dominant |
| 12 | K11 | Relax the `B ≤ 65,535` limit (`gridDim.x` allows far more) | `fused_policy.cpp:14` | None today (B ≤ 64) | Low | Only relevant if reused elsewhere |

**Not recommended:** a fused kernel with a custom backward for `update()`. V1 update
calls took 67.8 s of 1,216.8 s (about 5.6%, `PROGRESS_HISTORY:362-364`). Autograd
correctness risk is high and the ceiling is low. The V1 update has more headroom in
removing per-minibatch host syncs: `require_finite_gradients` twice,
`require_finite_multimodal_model`, five `.item()` calls, and `masked_categorical`'s
four `.item()` calls (`multimodal_trainer.cpp:160-184`).

### Where a custom kernel could matter: V2 (Hypothesis)

- V2 UPDATE is 33.55% of recorded wall time (`PROGRESS.md:1169`).
- Each V2 forward runs about 20 blocking `.item()` validations
  (`scalable_policy.cpp:17-41, 240-251, 294-297`).
- `live_v2_distribution` runs about 15 small ops on `[1, 12, 4096]` tensors plus two
  `masked_categorical` calls with 4 syncs each (`v2_live_input.cpp:214-232`).
- Every transition input (about 3 MB) is re-uploaded on each of 5 passes per update
  (`v2_live_train.cpp:151-176`).

**Before any new kernel**, a future agent should:

1. Upload each rollout's inputs to the device once per update.
2. Replace per-step `.item()` validations in the update path with device-side flag
   accumulation checked once per minibatch, mirroring V1's
   `require_finite_without_cuda_synchronization` (`multimodal_model.cpp:27-30`).
3. Batch the 8-step replay across sequences where semantics allow (the audit pass
   can be batched without changing optimization).
4. Profile again.

Only if the hierarchical distribution then dominates would a fused forward kernel
for it be worth it, and it would need a backward (or a `torch::autograd::Function`
wrapping reference ops for gradients), which is a much larger task.

---

## 10. Correctness checks a future agent should perform (not run here)

1. **Existing test on the target GPU:**
   `python scripts/dev/local.py build --build-dir <new> --cuda-root <cuda> --fused-policy`,
   then `ctest --test-dir <new> -R rl_fused_policy_test --output-on-failure`.
2. **New tests** in `fused_policy_test.cpp`:
   - a mixed batch (B = 8) where row 5 is all-illegal and the others are valid,
     expecting rejection;
   - a legal `+inf` and a legal `NaN`;
   - B = 65,535 accepted and B = 65,536 rejected;
   - a legal-logit spread of ±1e38 compared with the reference;
   - a non-contiguous `mask` rejected;
   - after K8, the logp-only variant equal to the full variant bit for bit on logp.
3. **Tolerances** (keep the preregistered ones from `CUDA_EXPERIMENT.md`):
   probabilities rtol 1e-5 and atol 1e-6; logp and entropy 1e-5; exact greedy
   agreement; exact zero illegal probability; exact −∞ illegal logp.
4. **Sanitizers on native Linux** (WSL is unsupported per the docs):
   `compute-sanitizer --tool memcheck|racecheck|synccheck|initcheck ./rl_fused_policy_test`.
   Record the outcome, including "not run".
5. **Live equivalence:**
   `compare_training_backends.py --reference <ref m08_trainer> --candidate <fused m08_trainer> --pairs 3`.
   Require byte-identical native traces, PPO metrics within rtol 1e-4 / atol 1e-5,
   and matching final exports within the kernel tolerance on replay.
6. **After K1–K5:** exact trace and model identity against the unchanged binary on the
   same seed (these changes must be bit-exact), plus
   `rl_checkpoint_roundtrip`/`rl_export_preserves_trainer` on CPU and CUDA.
7. **V1 behavior-replay audit** (02 §2.1) enabled in both builds, reporting the
   maximum |Δlogp| per update.

## 11. Profiling comparisons a future agent should perform (not run here)

1. **Kernel-only timing.** Use CUDA events around the launch in a development
   benchmark, separately from the wrapper's allocation, launch and status sync.
   Report both. The current `rl_policy_benchmark` measures only whole-wrapper wall
   time (`policy_benchmark.cpp:59-65`).
2. **Per-stage ACT timers** in `handle_act`: decode, H2D, forward, distribution,
   D2H, sample, encode (steady_clock, emitted behind a debug flag). Aggregate them
   per run so stages 1–9 in §7.2 get real shares.
3. **Nsight Systems** with a driver-supported version, preferably on native Linux.
   The recorded 2024.5/driver 13.3 combination produced no kernel tables. Add NVTX
   ranges (header-only `nvtx3` from the toolkit) around the stages above.
4. **End-to-end paired runs** with `compare_training_backends.py`: ≥ 3
   counterbalanced pairs on an idle host. Report the median and range of
   `collection_and_optimization_elapsed_ns`, `inference_elapsed_ns` and
   `trainer_update_elapsed_ns`. Never claim a speedup from kernel time or GPU
   utilization alone (AGENTS.md).
5. **Batch-size sweep** for K12: CPU vs fused vs reference at B ∈ {1, 4, 8, 16, 64}
   using `benchmark_policy.py`. Choose a threshold only from measured medians, and
   record it in run metadata.

## 12. Open questions

- Is the kernel meant to stay a CUDA learning artifact, or to become a default? The
  docs say optional. Its value is educational unless K1–K4 make inference a larger
  share.
- Which GPUs must it support besides the RTX 2070 (sm_75)? A single-architecture
  build with PTX covers newer GPUs by JIT, but that is not tested.
- Should the kernel eventually serve V2? The action shape (12 families × 4,096
  candidates, hierarchical) is different enough to need a new design.
