# M11 normal-game neural playback

## Accepted boundary

M11 adds an inference-only C++ controller to the normal playable OpenTTD 15.3
game loop. It loads the M09-selected, M10-accepted combined CNN/MLP ONNX package,
uses the shared native M04 observation encoder, M05 mask/action adapter, M06
reward-state projection, and M10 in-game inference adapter, then acts first at
tick zero and at a configured 128-tick multiple thereafter.

The controller is selected with `-A /absolute/path/playback.json`. It is not the
headless bridge and does not use screen scraping, simulated input, Python, or
menu navigation. The playable process owns reset, observation, masking,
inference, OpenTTD commands, inspection, and controls in C++.

## End-to-end workflow

1. Train the three frozen architectures with `run_m09_training.py` and the
   frozen M07/M08 contracts. G09 selects the combined policy independently on
   development results and evaluates it on the held-back final split.
2. Run `run_m10_package_gate.py` to export, validate, and content-address the
   selected policy. Install the complete immutable directory atomically as
   `openttd-rl/models/<package-id>`; do not copy individual payloads into an
   existing package.
3. Reconstruct the accepted M09 OpenTTD tree, apply
   `integration/openttd/patches/15.3/m11/series`, and configure with
   `OPTION_RL_ENVIRONMENT=ON`, `OPTION_RL_NEURAL_AGENT=ON`, an absolute
   `OPENTTD_RL_PROJECT_ROOT`, and the pinned ONNX Runtime 1.28.0 CPU root.
4. Create a canonical playback configuration from the example below. Select
   greedy or explicitly seeded stochastic inference, one safe interval, the
   scenario, package, inspection report, and optional action log.
5. Launch the playable build with OpenGFX and `-A`. The controller resets the
   configured final scenario, opens the inspection window when requested, and
   begins normal game control at tick zero. The user watches the bus company in
   the native viewport and can continue normal non-networked play.

The accepted G11 artifact executes this complete installed-package launch on
both frozen final templates and retains a real SDL-rendered 800 by 600 viewport
screenshot for template 07.

## Configuration

The file must validate against
`docs/project/schema/v1-m11-playback-config.schema.json`, contain absolute paths,
and be compact, key-sorted JSON followed by exactly one LF. This formatted
example is explanatory; serialize it canonically before launch.

```json
{
  "schema_version": "openttd-rl-v1-m11-playback-config-1",
  "contract_sha256": "3f331f7852b0174714de30b8ab6015178d7e01d4691832f8af2085d32bb01e42",
  "package_path": "/absolute/openttd-rl/models/0334e6a9da8d5b87d48ecdcd859dc3a5be6b1f7913511bf3336f8d3cf1feeeb9",
  "scenario_instance": "/absolute/instances/m02-template-07.json",
  "inference": {"mode": "greedy", "sampling_seed": 2026110101, "interval_ticks": 128},
  "logging": {"actions": true, "path": "/absolute/run/actions.jsonl", "maximum_records": 4096},
  "inspection": {"window": true, "debug_overlay": false, "report_path": "/absolute/run/inspection.json"},
  "controls": {"start_agent_paused": false, "native_pause_button": true, "agent_step_button": true},
  "acceptance": {"maximum_actions": 0, "exit_when_complete": false}
}
```

For ordinary play, keep `maximum_actions` at zero and `exit_when_complete` false.
The bounded-action automatic exit and screenshot path exist only for acceptance
orchestration. The action log is optional and bounded; the inspection report is
always atomically replaced with the latest controller state.

## Inspection and controls

The native window reports the current action, confidence, value, legal-action
count, balance/income/expenses/passengers/bus counts, route towns/stops/depot,
model name, version, and package identity. These values are derived from the
same immutable structured record written to the action log and report.

The window exposes three controls:

- Pause/resume agent stops policy decisions without pausing the game.
- Step one agent action performs exactly one decision while the agent is paused
  and the native game is running.
- Pause/resume game uses OpenTTD's native pause command.

V1 deliberately does not single-step an engine tick while the native game is
paused because OpenTTD game commands are pause-gated. That unsupported control
is explicit rather than simulated.

## Failure and dependency behavior

Missing, noncanonical, incompatible, or corrupt configuration/packages stop
before control with an actionable user error. A runtime inference/output failure
disables the controller, leaves the game available, writes a `FAILED` report,
and never substitutes a scripted, random, or previous action.

Normal inference dynamically closes over OpenTTD, ONNX Runtime CPU 1.28.0,
OpenSSL Crypto, and ordinary host libraries. LibTorch, Python, CUDA, the
optimizer, trainer, and training state are absent. G11 checks both the playable
binary and independent deployment evaluator with `ldd`.

## Verification

Run the focused contract/source suite with:

```text
./scripts/v1/run_m11_foundation_tests.sh
```

`scripts/v1/run_m11_playback_gate.py` performs the clean installed-package
acceptance campaign. The immutable inputs, retained result, exact hashes, and
observed outcomes are recorded in `docs/project/G11_GATE_REPORT.md`.
