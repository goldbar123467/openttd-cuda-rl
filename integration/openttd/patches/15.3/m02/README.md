# M02 OpenTTD feasibility delta

This directory is an ordered delta layered on the immutable M01 prepared-source
identity. `series` is parsed strictly by the M02 feasibility runner: patch names
must be unique basenames, every `.patch` in this directory must be listed, and
each patch must apply with `git apply --index` without offset or fuzz.

`0002` adds the default-off `OPTION_RL_ENVIRONMENT` map-size feasibility
profile. When that option is enabled, an optional
`scripts/rl_environment_editor_start.scr` hook runs only after an empty editor
world is fully initialized; the feasibility runner uses it to capture a genuine
empty 32 by 32 save without GUI automation. The same patch gives the
integer-valued `ScriptDate::Date` enum its existing 32-bit ABI explicitly; this
is the narrow source correction required for full-program UBSan because valid
day counts are not limited to the enum's `DATE_INVALID` sentinel. It does not
add the RL bridge, scenario, trainer, or neural agent.
