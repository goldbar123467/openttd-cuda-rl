# M11 normal-game neural-agent OpenTTD delta

This patch applies after the accepted M09 composed source tree. It adds the
inference-only normal-game C++ controller selected by `-A <playback-config>`,
links the shared M10 ONNX Runtime adapter, and reuses the exact M04 encoder,
M05 mask/action adapter, and M06 reward-state projection.

The playable build exposes a native inspection window, policy/game pause
controls, a policy-only single-action step, bounded canonical action logs, and
an atomically published inspection report. Startup compatibility failures stop
before control. Runtime failures disable the controller, retain the playable
game, publish a failed report, and never substitute another policy.

The build option is off by default. `OPTION_RL_NEURAL_AGENT=ON` requires the
M02–M09 environment delta, a GUI build, the OpenTTD-RL source root, ONNX Runtime
1.28.0 CPU, and OpenSSL Crypto. It does not link LibTorch, Python, CUDA, an
optimizer, or the trainer.
