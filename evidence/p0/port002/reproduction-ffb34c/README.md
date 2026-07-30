# PORT002 smoke-setting closure reproduction

This compact record binds the rerun performed after the source-owner review
identified reached `_settings_game.vehicle.smoke_amount`. The deterministic
builder now sets the native value to `2` explicitly. Two independent creation
processes, started in different UTC seconds, still produced byte-identical
outputs equal to the committed fixture:

- fixture: 10,008 bytes, SHA-256
  `74c9be53902598061e1e82835c394a37b77bfc71c818de1df8456cdfc2804d20`;
- map planes: 49,152 bytes, SHA-256
  `5a933bc43d59c05b0d8fda519aec0aafa71b16d50a03aea83aefade7a57c9dd6`;
- builder patch: SHA-256
  `ffb34c53680adb1cf1649b84ea1ca4c66449c210ade143ece61e6547ac87cd9e`;
- normalized settings: SHA-256
  `6def2c6df29992747165e3b2c090561893d0fe4d3a80c5833f871b3ed7e584f2`.

The raw build tree, commands, logs, two saves, and two map streams are retained
outside Git at
`/workspace/openttd-p0-artifacts/port002-smoke-setting-ffb34c`. The repository
does not depend on that absolute path for identity; `artifact-index.json`
records the content digests needed to audit the retained run.
