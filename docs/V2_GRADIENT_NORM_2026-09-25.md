# V2 gradient norm accumulation

The portable study uses the versioned `--gradient-norm fp64-v1` mode. The native
default remains `historical` for exact reproductions. [Protocol 2](../config/dev/v2-recovery-study-protocol-2.json)
records this common numerical amendment before any new recovery study or held-out
access. Protocol 1 and its failed qualification records remain unchanged.

## Evidence

On the RTX 2070 / Torch 2.9.1+cu128 installation, historical A0 exceeded the fixed
absolute CPU/CUDA limit of 1e-4. Its second update reported gradient norms
3.07306422 (CPU) and 3.07318368 (CUDA), a difference of .00011946. All 128 native
transitions matched. The unchanged pre-recovery trainer reproduced the same
per-device actions, updates and final weights.

An isolated diagnostic build saved parameters and pre-clipping gradients at all
64 optimizer minibatches across two updates. Tracing preserved actions, updates
and final weights exactly on each device. Recomputing norms from those fixed
snapshots separated reduction error from differences in the gradients themselves:

| Original CPU gradients | CPU float32 norm mean | Float64 norm mean | CUDA float32 reduction of the same gradients |
| --- | ---: | ---: | ---: |
| Update 1 | 8.2086381875 | 8.2086594579 | 8.2086594030 |
| Update 2 | 3.0730642201 | 3.0730698071 | 3.0730698705 |

LibTorch's C++ helper reduces each parameter's norm in its gradient dtype. Here
CPU float32 reduction underestimates the norm and changes clipping coefficients.
Small gradient/parameter differences grow during later Adam steps. This is
floating-point accumulation error, not a changed mask or a new PPO loss defect.
PyTorch documents cross-device limits in its [numerical accuracy notes](https://docs.pytorch.org/docs/2.9/notes/numerical_accuracy.html).

The isolated counterfactual changed only norm accumulation. Both previously
failing workloads passed the **unchanged** bound:

| Two-update workload | Historical maximum update error | FP64 accumulation maximum update error |
| --- | ---: | ---: |
| A0, guide v2, entropy .01 | .00011946 | .00001930 |
| Retained guide v3, entropy .001 | .00012935 | .00003568 |

These are bounded engineering checks on training maps, not learning results or
proof that all devices will pass. Every target runs its own qualification.

## Semantics and compatibility

The alternative computes each dense gradient's L2 norm and their combined norm
in float64 on the requested device, then applies
`min(1, max_gradient_norm / (norm + 1e-6))` to the original gradients. It retains
the .5 limit and LibTorch's clipping epsilon. Parameters, gradients, forward/backward
operations and Adam state remain float32. Losses, optimizer settings, sequence
batching, seeds, maps, budgets, early stop and acceptance criteria are unchanged.
Nonfinite norms fail before any gradient changes. CPU fallback is forbidden.

This changes numerical outputs; it is not claimed to be bitwise equivalent to
historical clipping. The historical option retains the original LibTorch call.
Native/Python checkpoints, effective native configuration, training/model and ONNX
provenance, study registration and qualification bind the selected mode and reject
mismatches. Protocol 2 cannot reuse historical-mode training runs.

Native tests use an independent scalar long-double oracle for unclipped/zero
gradients, large reductions, extreme finite values, missing gradients and nonfinite
failures. Integrated qualification also checks exact historical raw/A0 reference
behavior, both numerical workloads, probe neutrality, checkpoint mismatch refusal
and reset-resume equality. See [current results](REFACTOR_2026-09-25_STATUS.md).

## Artifacts and reproduction

Roots below are under `/home/imsa/.local/share/openttd-rl/runs/`:

- `refactor-a0-reference-01/verification.json`: exact pre-recovery/recovery A0 behavior.
- `refactor-numeric-trace-01/verification.json`: tracing neutrality, source capsule and binary identities.
- `refactor-numeric-trace-01/analysis/audit.json`: per-minibatch differences and snapshot hashes.
- `refactor-numeric-trace-01/analysis/norm-reductions.json`: reductions over identical saved gradients.
- `refactor-fp64-clipping-experiment-01/verification.json`: counterfactual comparisons and source/binary hashes.
- `refactor-gradient-qualification-01/`: integrated qualification logs and reports.

Run `verify_v2_default.py --gradient-norm fp64-v1` with the current trainer,
the pre-recovery trainer from `e5f6943`, and the native engine to repeat reference
and CPU/CUDA checks. `verify_v2_recovery.py` and `verify_v2_resume.py` accept the
same option. The portable bootstrap supplies it from protocol 2 and refuses
registration unless the complete bundle passes.
