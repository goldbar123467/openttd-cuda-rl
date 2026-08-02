# G12 gate report: Version 1 release and clean reproduction

## Result

`G12: PASS` on 2026-08-02. All 12 frozen release campaigns pass, all 217 V1
requirements pass, the 10 explicitly post-V1 rows remain deferred, and the
reviewed defect ledger contains zero nonclosed or release-blocking entries.
Version 1 is complete at the frozen 32 by 32 passenger-bus boundary.

## Frozen identities and retained evidence

| Artifact | Identity |
|---|---|
| M12 contract commit | `7716621ac0acbf91d1c3de5a92aa39ce948e2f96` |
| M12 compatibility | `e644f6e31163f9eb91008fe0bcb5d6830f3f3bb89104b229f3d974085b287879` |
| M12 contract schema | `0c30952fd82c821e7c4919b7fb07506ba78300a8ac35e50a072b2b41ee6a7ea5` |
| Release-manifest schema | `42274a2d75e42667502855c1728922fc24913a1968ba12bbd3446175912dcac7` |
| M11 composed result tree | `e1151f41b131a41c1d450f741c8922da1a119e18` |
| Preclosure manifest file | `4c8e25fa4f641d617c5b4425dcb160498844aa5368dcc8ff0ef7da0bae0689e8` |
| Preclosure manifest semantic identity | `07dfd74848af8eea2e0add2b69b6799179b9c239b3ae0daa8bb80142bf9d2ed5` |

The first complete retained campaign is
`/home/thecl/.codex/artifacts/openttd-rl/m12-release-preclosure-f`. It ran from
clean commit `c8939bbc2c983033f40ec602db91b2235265726d`, contains 10,783 files and
uses 6.7 GiB. Its canonical manifest records the 17 rows that were still open
before this gate report and traceability closure were committed.

The accepted post-closure reproduction is retained at
`/home/thecl/.codex/artifacts/openttd-rl/m12-release-final-a`. Its
`v1-release-manifest.json`, `artifact-index.json`, and `commands.json` are the
machine authority for the final source commit, file digest, semantic identity,
host, commands, and generated-artifact hashes. It runs without
`--allow-preclosure` and requires an empty `pending_v1` inventory.

## Clean builds and executable boundary

The preclosure campaign created a fresh outer clone and independent OpenTTD
object clone, composed the exact M11 result tree, and committed that tree before
configuration. Both OpenTTD variants built under strict warnings and each
passed all 98 native CTests after the exact OpenGFX 8.0 archive was staged.

| Build | SHA-256 | Tests |
|---|---|---|
| Headless RL environment | `29069d2b6c2df13a219cdec3847b95a1e75062ede09f7356440ad2e466de36db` | PASS |
| Playable neural controller | `b02212bcf122c7e508808b0dd818da93b1fff0bb37191cfa50fc9b7e452953cd` | PASS |
| C++/CUDA trainer | `59f678c8493b5ed5fd2135b1124503f5c67e9aea0d2f8498b19e3479907fef0d` | six CTests PASS |

The playable dynamic closure contains ONNX Runtime 1.28.0 CPU and OpenSSL but
no LibTorch, CUDA, Python, trainer, or optimizer. The training build contains
the PPO trainer, all three architecture paths, CUDA gate, independent evaluator,
ONNX export orchestrator, deployment evaluator, and native test suites.

## Reproduction campaigns

| Campaign | Accepted result |
|---|---|
| Clean dual build | Fresh headless, playable, and training builds PASS |
| Scenario/reset reproduction | Final templates 07 and 08 PASS from the fresh executable |
| CPU/CUDA training | MLP on CPU plus CNN and combined on CUDA complete live updates |
| Checkpoint recovery | Interrupted and uninterrupted actions, metrics, and semantic state are exact |
| Independent evaluation | Frozen G09 report remains PASS and optimizer-free |
| ONNX package equivalence | 12 final cases agree in standalone and in-game adapters |
| Visible playback | Both final scenarios deliver passengers and earn positive income |
| Long-run soak | 8,192 steps, 64 updates, and CUDA health evidence PASS |
| Quality matrix | Static, syntax, sanitizer, malformed, fault, and resource boundaries PASS |
| Clean operator documentation | Full project suite passes in the fresh clone |
| Traceability/defects | 217 V1 rows PASS and zero nonclosed defects after closure |
| Fresh-root repeat | Independent playbacks have exact action logs |

The fresh live training smoke accepts 128 transitions for each architecture and
finishes one update with finite metrics. The retained long run records
8,192 environment steps over 64 updates. The selected G09 combined policy keeps
its independent final-set mean of 150 passengers and 424 operating profit.

Both fresh visible scenarios execute 24 decisions: template 07 delivers 15
passengers and earns 90; template 08 delivers 12 and earns 72. Standalone and
in-game ONNX paths preserve all greedy actions, with maximum absolute errors of
`7.152557373046875e-7` for logits, `4.240424975043844e-8` for probabilities,
and `5.7220458984375e-6` for value.

## Provenance and quality closure

The canonical manifest records the outer/upstream commits; clean-state policy;
Ubuntu, compiler, CPU, GPU, CUDA, CMake, and Ninja versions; five exact runtime
dependency files; all 10 compatibility identities; complete scenario,
initialization/training, evaluation, golden, sampling, and shuffle seed families;
run counters; every accepted checkpoint/report/package identity; and every M12
generated artifact.

The quality matrix passes full traceability and document lint, ShellCheck for
all V1 shell scripts, `bash -n`, Python byte-compilation, Git whitespace checks,
strict native warnings, retained sanitizer and resource evidence, malformed
input suites, and M07/M08/M11 fault injection. The release runner refuses a
dirty or unsynchronized repository, wrong host/GPU profile, changed accepted
evidence, existing output root, unresolved dynamic dependency, noncanonical
manifest, pending V1 row, or nonclosed defect.

The complete supported-host workflow—clean source, build, train, resume,
evaluate, export, install, play, validate, and troubleshoot—is documented in
`docs/project/V1_RELEASE_REPRODUCTION.md`.

## Version 1 boundary

G12 closes the bus-only V1 product: controlled 32 by 32 maps, one learning
company, passengers, buses, roads/stops/depot, C++ PPO, MLP/CNN/combined models,
measured CUDA, independent economic evaluation, portable ONNX packages, and
normal-game visible neural control. It does not authorize mail, freight,
industries, trains, ships, aircraft, larger maps, multiplayer training, NewGRFs,
additional RL algorithms, screen vision, GUI imitation, or distributed
multi-machine training. Those remain post-V1 work under new contracts and gates.
