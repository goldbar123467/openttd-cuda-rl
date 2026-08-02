# ADR 0014: Freeze CPU native-to-ONNX equivalence tolerances

- Status: Accepted
- Date: 2026-08-01
- Applies to: M10 native, ONNX Runtime standalone, and in-game-adapter inference

## Context

The immutable M09 actor-critic tensors are exported from LibTorch float32 modules
to ONNX opset 18 and executed by ONNX Runtime CPU 1.28.0. Equivalent graph
implementations can choose different legal floating-point reduction and fused
kernel orders. Requiring bit equality would reject equivalent packages, while an
unbounded approximate comparison could hide incorrect graphs or preprocessing.

Action masks, tensor names, shapes, dtypes, architecture identity, recurrent-state
disposition, and greedy actions are semantic values and admit no approximation.
Sampled actions cannot be compared one-for-one when two runtimes consume random
bits differently, so their distributions require a separate preregistered gate.

## Decision

All three V1 architectures use float32 inputs, parameters, logits, and values on
CPU. For every one of the 36 frozen golden cases, a scalar `observed` passes only
when it is finite and:

```text
abs(expected - observed) <= absolute + relative * abs(expected)
```

The frozen tolerances are:

| Output | Absolute | Relative | Rationale |
|---|---:|---:|---|
| policy logits | `2e-5` | `2e-5` | Bounds accumulated float32 GEMM/convolution ordering differences while remaining far below control-scale logits. |
| masked probabilities | `2e-6` | `2e-5` | Softmax is normalized and therefore receives a tighter absolute bound. |
| value | `2e-5` | `2e-5` | Same float32 network arithmetic as logits, with one scalar head. |

Legal masks are byte-exact. Illegal-action probabilities must be zero, greedy
actions must be exact, and all-illegal or nonfinite inputs fail before inference.
V1 has no recurrent state; introducing it requires a new package compatibility
version and an exact recurrent-state shape/disposition test.

For three cases per architecture, each runtime probability vector is independently
sampled 100,000 times. Every runtime pair must have total-variation distance at
most `0.015` and maximum per-action frequency difference at most `0.005`. These
bounds are deliberately wider than ordinary multinomial fluctuation at this
sample count but narrow enough to expose a materially changed categorical policy.
Bins with small expected counts are merged only for a reported chi-square
diagnostic; promotion gates on the preregistered TV and maximum-bin bounds.

The M10 gate includes negative self-tests that perturb otherwise accepted outputs
beyond each tolerance. A comparison implementation that accidentally accepts the
perturbation invalidates the gate.

## Consequences

Export promotion requires exact tensor transfer, exact repeated ONNX bytes, graph
signature inspection, and bounded output equivalence. Tolerances cannot excuse a
name, shape, dtype, mask, action, compatibility, or dependency mismatch.

Changing a threshold, runtime/provider, dtype, preprocessing rule, or device is a
contract change. It requires a new compatibility identity, fresh golden evidence,
and review of this decision; measurements may not tune a frozen threshold after
the final cases have been observed.

## Rejected alternatives

Bitwise output equality was rejected because valid CPU kernels may associate
float32 operations differently. A single coarse epsilon was rejected because
softmax probabilities have a different numerical scale from raw logits. Seeded
action equality alone was rejected because RNG implementations may map the same
seed differently even when their categorical distributions agree.

## Verification

`config/v1/m10-model-package-contract.json` is authoritative for the numeric
values and sample budget. `scripts/v1/run_m10_package_gate.py` compares every
golden output, checks exact semantic fields, runs the sampled-distribution gate,
and records maximum observed errors in the immutable M10 report.
