# G01 Reproducible Build and Runtime Profile Gate Report

- Gate: `G01`
- Result: `PASS`
- Date: 2026-08-01
- Outer baseline commit: `76574e7e65494b72ed3c07cbf973722865c3569f`
- Worktree condition: intentionally dirty, content-addressed by the accepted M00
  preservation snapshot
- OpenTTD submodule: clean at
  `29f808ef0022064e6d9a83c8476d1e0f4686af86`

## What this pass means

The exact OpenTTD 15.3 source/patch basis, compilers, build tools, CUDA, LibTorch,
auxiliary exporter, ONNX Runtime, content, supported host, build profiles,
headless/playable variants, resource baseline, licenses, and dependency
provenance are frozen with reproducible evidence. Development may proceed to the
conditional 32 by 32 feasibility slice in `M02`.

This pass does not claim that a 32 by 32 map works. It does not claim that an RL
bridge, bus scenario, reset contract, PPO trainer, CUDA training workload,
production ONNX package, evaluator, or in-game neural agent exists.

## Gate evidence

| G01 condition | Evidence | Result |
|---|---|---|
| Exact source reconstruction | Pinned commit/tree, ordered patch, preparation schema/runner, repeated identity | `PASS` |
| Toolchain and ABI closure | Two byte-identical four-test CUDA/LibTorch/ONNX probe roots | `PASS` |
| Headless build | Two clean 96-test builds, 161 byte-identical installed artifacts | `PASS` |
| Playable build | Two clean two-test builds plus null and SDL main-loop smokes, 161 byte-identical installed artifacts | `PASS` |
| Build-profile contract | Seven strict profiles with explicit feature/dependency flags and activation tasks | `PASS` |
| Worker boundary | Dedicated binary retained only as evidence; future worker is regular/non-dedicated/null-video | `PASS` |
| Runtime baseline | Two four-workload campaigns, one warm-up plus five raw samples, median/range | `PASS` |
| License/provenance | 25 toolchain, 34 overlay, OpenGFX, OpenTTD source, 90 runtime dependencies | `PASS` |
| Offline behavior | Accepted build/probe/provenance operations use only locked/local inputs | `PASS` |
| Source/worktree integrity | Clean submodule plus verified recoverable outer dirty-worktree snapshot | `PASS` |
| Drift rejection | Profile, dependency, package, identity, inventory, license, schema, and overwrite mutation tests | `PASS` |

## Deterministic closure audit

`scripts/v1/g01_audit.sh` independently revalidates retained artifacts rather than
trusting their names. It checks installed file bytes and modes, cleaned build
directories, paired manifests/products, raw resource sample inventories,
protocol equality, byte-identical provenance, snapshot hashes, submodule state,
and `git diff --check`.

Accepted audit roots:

- `m01-g01-audit-20260801-a`
- `m01-g01-audit-20260801-b`

Both emitted byte-identical reports:

| Artifact | SHA-256 |
|---|---|
| `g01-audit.json` | `e5db84ff30ac2b09e6dd1516e672ad153773674070c7335464893e50d325cd78` |
| `g01-audit.txt` | `a25aa69caa7e9a70d5257db4d1fe3e2638834ca5c8bc3f4782a4d0ffc10d59fc` |

Audit identity:
`7312e80f167a282c3b2d297737f64352838605fb3a28a0b07f7334008e67a5b7`.

## Traceability correction

The initial machine registry assigned `STACK-001` and `STACK-005` to `G01`, but
their acceptance language covers the complete future trainer/export/inference
source graph. Passing those requirements before those components exist would be
vacuous. Their owning gate is now `G11`, when whole-program C++ ownership and the
auxiliary-only Python boundary can actually be audited. They remain
`NOT_STARTED`; no atomic V1 product requirement was falsely promoted merely to
close this infrastructure gate.

## Next gate

Begin `M02` with only the conditional `OPTION_RL_ENVIRONMENT`-style 32 by 32
engine feasibility patch. The normal flag-off minimum remains 64. Both modes must
build/test, and the 32 by 32 path must create, save, reload, and soak under
assertions and sanitizers before scenario design proceeds.
