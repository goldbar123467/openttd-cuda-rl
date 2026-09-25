# 9/25 refractor: PPO, evaluation and CUDA review

This folder holds a static technical review of the OpenTTD live PPO project at
commit `0595a72`. No code or configuration was changed, and nothing was built, run,
trained, evaluated, profiled or tested.

## Reading order

1. [00-review-summary.md](00-review-summary.md): assessment, top concerns, ranked actions.
2. [08-ppo-training-recovery.md](08-ppo-training-recovery.md): the concrete plan to
   get V2 training back on track, with settings, code sketches and experiment
   protocol.
3. [05-custom-kernel-review.md](05-custom-kernel-review.md): the CUDA kernel and
   why its speedup vanishes end to end.
4. [03-evaluation-audit.md](03-evaluation-audit.md): how models are evaluated and
   where comparisons are weak.
5. [07-prioritized-plan.md](07-prioritized-plan.md): staged, implementable work
   items with verification steps.

Reference material:

- [01-project-map.md](01-project-map.md): components and data flow, with the
  kernel's position.
- [02-correctness-and-ppo-review.md](02-correctness-and-ppo-review.md): PPO
  detail-by-detail verification.
- [04-evaluation-bottlenecks.md](04-evaluation-bottlenecks.md): where evaluation
  time goes, and output-preserving speedups.
- [06-strategy-and-refactor-options.md](06-strategy-and-refactor-options.md):
  learning and code-organization options with evidence.
- [09-coverage-and-findings-register.md](09-coverage-and-findings-register.md):
  what was and was not reviewed, extra findings, and every finding with IDs.

## Labels used throughout

| Label | Meaning |
| --- | --- |
| Confirmed / Certain / C | Follows from the code at the cited lines |
| Recorded / Rec | A measurement the repository's own documents report (cited) |
| Supported | Consistent with recorded audits, but not isolated causally |
| Risk / R | A plausible problem, not demonstrated |
| Measure / M / Hypothesis | Needs profiling or an offline audit before acting |
| Derived | Arithmetic on recorded numbers or code constants |

## Glossary (PPO and CUDA terms as used here)

- **Behavior log-probability**: the log-probability of the action actually sampled
  during collection. PPO's ratio compares the updated policy against it.
- **Advantage (A)**: how much better an action turned out than the critic expected.
  Here it is computed with **GAE**, an exponentially weighted (γλ) sum of one-step
  TD errors.
- **γ (gamma)**: the discount per decision. .99 means rewards about 100 decisions
  away count ~37%.
- **λ (lambda)**: the GAE trace weight. It trades bias (small λ) against variance
  (λ = 1).
- **Bootstrap vs continuation**: at a time limit the target still includes
  `γ·V(next)` (bootstrap = 1), but the advantage trace stops (continuation = 0). At
  a true terminal both are 0.
- **Clipped surrogate**: PPO limits each update by clipping the probability ratio to
  [1−ε, 1+ε] (ε = .2 here).
- **Entropy bonus**: a loss term rewarding spread-out action probabilities, which
  keeps exploration alive.
- **Forced step**: a decision where the (guided) mask allows exactly one action. It
  carries no policy-gradient information.
- **Choice fraction**: the share of decisions that are not forced. It scales the
  *effective* strength of loss terms averaged over all steps (08 M1).
- **Potential-based shaping**: adding `γΦ(s') − Φ(s)` to rewards. It changes the
  learning signal's timing without changing which policies are optimal.
- **Stored-state recurrent PPO (BPTT 8)**: replaying 8-step sequences from the
  hidden state recorded during collection.
- **Block / warp / thread**: a CUDA kernel launches blocks of threads. A warp is 32
  threads executing together. Here each 41-action row gets one 64-thread block.
- **Shared memory / `__syncthreads()`**: fast per-block scratch memory, plus the
  barrier all threads of a block must reach before reading others' writes.
- **Occupancy**: how many warps an SM can keep resident. It is irrelevant when the
  grid has only a handful of blocks, as here.
- **Host–device sync**: the CPU waiting for the GPU, for example via `.item()` or
  `.cpu()`. Each one stalls both sides, and small workloads are dominated by these
  waits.
- **Pinned memory**: page-locked host memory that allows faster, asynchronous copies
  to and from the GPU.
- **CUDA stream**: an ordered queue of GPU work. LibTorch's "current stream" must be
  used by custom kernels (it is, here).
