# G11 gate report: normal-game neural playback

## Result

`G11: PASS` on 2026-08-02. All 14 M11-owned requirements pass. The accepted
combined policy loads into a normal playable OpenTTD build, controls both final
bus scenarios to paid passenger service, exposes native inspection and controls,
replays deterministically, and fails closed without training dependencies or a
fallback policy.

## Frozen identities and provenance

| Artifact | Identity |
|---|---|
| Playback contract commit | `4bc208080040503b2ef79d7eb17e2d3506ac2906` |
| Accepted implementation commit | `5b74c380da2889edaacb006e3df7bc784ddb3f7e` |
| M11 compatibility | `3f331f7852b0174714de30b8ab6015178d7e01d4691832f8af2085d32bb01e42` |
| Accepted M10 package | `0334e6a9da8d5b87d48ecdcd859dc3a5be6b1f7913511bf3336f8d3cf1feeeb9` |
| Accepted model | `10df689ccc6d1cb7f2e98f05f0474f72577cd9328a4589e3b1c7167bcbf08b5b` |
| Playable executable | `38bdd3c192f146c59171f7d22b0dbcc471ccfbac3e63e4be32f5a3f89612e088` |
| Accepted report file | `3e01e4c3316e76fa861f11905be2955015a6f67e66a8d767078c338f1ff9f879` |
| Accepted report semantic identity | `0dc549efb22d5c7d2a5a0408a1c64eecbf69389f921497e4d243aca8889dbc3e` |

The retained artifact is
`/home/thecl/.codex/artifacts/openttd-rl/m11-playback-acceptance-c`. It contains
the staged playable runtime, 17 successful controller campaigns, six rejection
runs, canonical action/inspection evidence, the visible screenshot, dependency
closure, and the gate report: 157 files totaling 429,624,600 bytes.

## Actual-engine visible play

Both held-back final scenario layouts ran 24 decisions at a 128-tick interval.
The greedy controller selected towns, built both stops, road connector, and
depot, bought buses, assigned the route, started buses, and then operated the
service in normal game time.

| Scenario | Actions | Delivered passengers | Operating income | Action-log SHA-256 | Inspection SHA-256 |
|---|---:|---:|---:|---|---|
| `m02-template-07` | 24 | 15 | 90 | `a9255f8b74982a5bed8ba8360b529df244263fb74f0a6bfb04180257738cf080` | `6477ded87db71f293ddd7868f30341f4c37fb993f5548405abb93464d474c146` |
| `m02-template-08` | 24 | 12 | 72 | `4b65035bc3bc880fc088edf60e0f7d4eaa10f2bc5857fadd3745c1179e02a6d1` | `67b07f3794c952ca65359e5dac3e8ae083ff2fd15b2c8166fb0b9ed7429f0c2a` |

The template-07 SDL viewport is a real 800 by 600 PNG showing the constructed
route, vehicles, native game UI, and controller inspection window. Its SHA-256
is `87e32e37d779ebea2f210f97eb1c20462e84bd50ef228a27ee3445f67dfc3a2e`.
Every inspection report's `latest` object equals the last action-log record.

## Modes, timing, and equivalence

Two independent greedy template-07 processes produced identical 24-record
action trajectories despite different irrelevant sampling seeds. Two stochastic
runs with seed `2026110201` were also exact record-for-record; seed `2026110202`
produced a different action sequence.

All supported intervals fired exactly at tick zero and the configured next tick:
`128`, `256`, `384`, `512`, `640`, `768`, `896`, and `1024`. Schema tests reject
values outside the range or not divisible by 128.

The frozen 12-case M10 `golden.jsonl` corpus passed through both the standalone
deployment runtime and the exact in-game adapter source. Greedy actions and masks
were exact. Maximum absolute errors were `7.152557373046875e-7` for logits,
`4.240424975043844e-8` for probabilities, and `5.7220458984375e-6` for value,
all inside ADR 0014's frozen tolerances.

## Inspection, controls, and failure behavior

The screenshot and canonical records cover all eight required inspection fields:
current action, confidence, value, legal-action count, reward-relevant state,
route target, model name, and model version. The native window exposes policy
pause/resume, exactly-one policy action while policy-paused and game-running, and
OpenTTD's native game pause. Engine-tick stepping while natively paused remains
explicitly unsupported because commands are pause-gated.

The gate exercises all frozen failures: missing configuration, invalid
configuration, missing package, incompatible package, corrupt model, and injected
runtime output failure. Startup errors stop before control. The runtime fault
leaves exactly one prior action, disables the controller, publishes `FAILED`,
and executes no fallback action.

## Production boundary and verification

The playable build links ONNX Runtime 1.28.0 CPU and OpenSSL Crypto. Dynamic
closure checks find no LibTorch, `libc10`, Python runtime, CUDA, optimizer, or
trainer dependency in the playable binary or deployment evaluator. Python is
used only by contract tests and the acceptance orchestrator.

The focused M11 suite passes five tests, including exact reconstruction of the
accepted OpenTTD source and the M11 result tree. G11 ran from a clean committed
repository and preserves its commit and every significant executable, package,
report, log, inspection, screenshot, runtime-asset, and library identity.

G11 proves usable normal-game inference and visible policy play. Release
reproduction, clean-machine setup, longer soak, installation automation, and the
final V1 gate remain M12/G12.
