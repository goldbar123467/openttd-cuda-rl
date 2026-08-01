# G03 synchronized headless bridge gate report

- Gate: `G03`
- Result: `PASS`
- Date: 2026-08-01
- OpenTTD: 15.3 source commit
  `14ec60f248547d4d062a1160f0fc26d742319888`
- M03 result tree: `39ed7069eca2c48c512a9bdd989c049aca3c5329`
- Composed source identity:
  `d5d14398d545c951b04325d91d444e6194553e537d4b1f16615cba44351f2ef1`

## What this pass means

G03 supplies a source-integrated, versioned, synchronized control surface for
actual OpenTTD. One environment runs in each regular non-dedicated worker
process, controlled through inherited anonymous pipes. All calls occur at safe
game-loop boundaries, query calls are non-perturbing, normal typed engine commands
remain the only fixture mutation path, and coordinator-owned timeout/crash
handling retains process artifacts.

This pass does not claim an M04 policy observation, M05 policy action/mask
contract, M06 reward or training trajectory, PPO, CUDA learning, evaluator,
production ONNX package, or in-game neural controller. The M03 snapshot and two
fixture actions exist only to prove synchronization and native integration.

## Frozen identities

| Input | SHA-256 or identity |
| --- | --- |
| Bridge compatibility | `4701a21ae106f6fa120db1b89c3929d16c29afafb8e0198126173137ed2af2d6` |
| Bridge contract schema | `199c57a1b55b776f725aaa5d23ad298ef85a2b0bb13837674503ae98f7245dea` |
| Ordered M03 patch | `6677d5a32abc5250394133e162236f1b2c5a9acfe19ea867a8b0512b10343c50` |
| M03 series | `bb0f27f2bd530d89433dbf6b32fdbd4e63fed4e08224f8b190298f5185d7959e` |
| M03 result tree | `39ed7069eca2c48c512a9bdd989c049aca3c5329` |
| M03 composed source | `d5d14398d545c951b04325d91d444e6194553e537d4b1f16615cba44351f2ef1` |
| Oracle report schema | `5f4e69c6414b15c92c43b5d9798edcc316ab5f01c7b6242460cf5b1666be5423` |
| Current Ubuntu executable | `1a14655590e46cee0e7415174d62714092c8691d6bad2e4c89bf87b5065c9794` |
| OpenGFX 8.0 archive | `9389bcb0807058c80bd95121e978f05d9ef86b4b1bc3ac2da8da8bb02456043c` |

The patch applies exactly after the accepted M02 tree without fuzz or offset.
It is default-off behind `OPTION_RL_ENVIRONMENT`; invoking the M02 `-Z/-Y/-T/-R`
path without `-B` continues to produce every accepted M02 projection and
trajectory digest.

## Repeated native evidence

The two accepted roots are:

```text
/home/thecl/.codex/artifacts/openttd-rl/m03-bridge-oracle-20260801-a
/home/thecl/.codex/artifacts/openttd-rl/m03-bridge-oracle-20260801-b
```

`diff -qr` produces no output. Their common `manifest.json` SHA-256 is
`0a0664be8345ef79f6d01a7de404ad0f7427071849661a5e6dabd3025a960877`,
and their common `commands.json` SHA-256 is
`9fe51ff69535e422db6286c1f5e3e83205fb41a953cdddb66f0129607a3ca4bf`.
Both manifests pass the strict M03 oracle report schema.

| Template | Delivery transition | Trace SHA-256 |
| --- | ---: | --- |
| `m02-template-01` | 22 | `8834c3a3e0636eb5716a2952b2096abaa287c66b8f4dcc4afbad41782154cc46` |
| `m02-template-02` | 22 | `9b18979791049a5912fb108cd672e53019ef1f84c59e2f61854193504e38d2d9` |
| `m02-template-03` | 23 | `4f8ffd0ab32ee18364ab5b9276e3a4c0557277be5a27dd897b2fad40f391cd3d` |
| `m02-template-04` | 22 | `8f4883f06fa4f5c8246469a6f6c70511812ccbab91947ee8c6b7238e37791130` |
| `m02-template-05` | 26 | `524ec3296cd0f18bfdfb1738de0c2644e0c70dddbe78de331564a2d6e14e3342` |
| `m02-template-06` | 24 | `d9a7aaaa41f3e95563fa78cd51751dd78dc081fccc0de6f8c68d97768c9eaf90` |
| `m02-template-07` | 24 | `79f386299b42010dbbcc557a6b7ff05f6f27f5dfd6a39b1a8e58c793e6626f94` |
| `m02-template-08` | 24 | `83eeed44bb569ffa8687dd2a21686faa99f950da2aa123d9deddaf69a29f4b42` |

Every template runs twice in independent workers and resets a second time in the
same worker. Snapshot/legal-action tokens match; pause/resume and query calls do
not change engine or RNG state; stale handle/boundary and invalid lifecycle calls
fail closed. A separate interleaved two-worker test proves process isolation.

The scheduler accepts and records intervals 1, 64, and 128, advances exactly
1, 64, and 128 ticks, and rejects 0, 129, and 4,294,967,297 without mutation;
the same narrowing adversary is rejected as an action ID. The reference soak
performs 512 actions and 65,536 ticks, reports the declared simultaneous-horizon
priority, and rejects a post-horizon step without changing the final snapshot.
Bad checksums enter `FAILED`; a killed worker is classified as a crash; response
timeouts use a monotonic deadline, kill only the owned worker, classify the
failure, and retain stdout/stderr.

## Quality gates

The regular non-dedicated M03 build passes all 96 upstream unit cases and both
native regression tests: 98 of 98 CTest entries. The focused repository suite
passes 17 M03 contract, framing, patch-identity, source-application, schema, and
helper tests. The complete repository gate passes all 142 tests, 227 requirement
rows, 20 test-suite mappings, 32 passing requirements, 29 active documents, and
zero nonclosed defects. All 34 tracked or untracked repository shell scripts pass
ShellCheck 0.9.0 and `bash -n`.

## Next boundary

Stop at G03. M04 may next freeze the structured and spatial policy observation
plus shared preprocessing contract on the accepted M03 boundary. M05 actions,
M06 rewards, PPO, CUDA training, evaluation, ONNX, and neural playback remain
downstream.
