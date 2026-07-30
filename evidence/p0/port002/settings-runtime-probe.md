# PORT-002 runtime setting probe

The pinned plain release executable loaded the committed
`road_freight_v1/fixture.sav` in an isolated `HOME`, `XDG_CONFIG_HOME`,
`XDG_DATA_HOME`, and `XDG_CACHE_HOME`, with `/dev/null` as its configuration,
configuration writes disabled, NewGRF scanning disabled, and the frozen
OpenGFX/NoSound/NoMusic profile selected. The diagnostic dedicated console was
bound only to `127.0.0.1` and exited immediately after the read-only queries.
This was a setting probe, not an authoritative replay.

The 24 newly reviewed settings reported the committed values in
`settings.normalized.json`. The two values that differ from the raw table
defaults were:

```text
Current value for 'linkgraph.recalc_interval' is '16' (min: 4, max: 90, def: 8).
Current value for 'linkgraph.recalc_time' is '64' (min: 1, max: 9000, def: 32).
```

Pinned source explains the difference. `src/settings.cpp:1427-1429` converts
legacy/configuration LinkGraph day values into runtime seconds, and
`src/timer/timer_game_common.h:158` fixes `SECONDS_PER_DAY` to 2. Thus 8 becomes
16 and 32 becomes 64 before fixture creation. All other queried additions
equaled their declared values: the five construction settings, `give_money`,
the remaining seven LinkGraph fields, `roadveh_queue`, the eight reached YAPF
road limits/penalties, and the reached `vehicle.smoke_amount` default of `2`.

The canonical normalized-settings document SHA-256 after this correction is
`6def2c6df29992747165e3b2c090561893d0fe4d3a80c5833f871b3ed7e584f2`.
The behavior-only identity is
`fc5667d5b48a1ee760649150762ebae2f7dd43f0ed185b5671a1d632b8f7651c`.
