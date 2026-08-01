# M03 synchronized environment-bridge delta

This ordered delta applies after the accepted M02 scenario/reset tree
`551a99fbd33bd1b0f8c9ec35561deb0e893b81fe`. It adds the optional,
source-integrated M03 control layer without changing the default-off build or
the accepted M02 batch entry point.

The bridge runs only when `OPTION_RL_ENVIRONMENT=ON` and `-B
<read-fd>:<write-fd>` is supplied with `-Z <scenario-instance>`. It accepts no
network listener: the descriptors must be distinct inherited anonymous pipes.
Each regular, non-dedicated OpenTTD worker owns exactly one environment and
executes commands and complete `StateGameLoop()` calls synchronously on its main
thread.

`0004` implements the frozen contract in
`config/v1/m03-bridge-contract.json`: checksummed versioned frames, typed
session/episode handles, strict request and transition ordering, lifecycle
guards, reset/snapshot/legal-actions/step/pause/resume/close, and exact 128-tick
reference steps with a validated 1-through-128 interval. `WAIT` and
`M02_SCRIPTED_BUS_SETUP` are M03 integration fixtures only;
they are not the downstream M05 policy action registry.

The patch reuses the accepted M02 reset and scripted bus command fixture. The
legacy `-Z/-Y/-T/-R` batch path remains available when `-B` is absent so its
byte-identical projection and trajectory outputs can serve as bridge-disabled
non-perturbation evidence.
