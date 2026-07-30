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
the remaining eight LinkGraph fields, `roadveh_queue`, and the eight reached
YAPF road limits/penalties.

The canonical normalized-settings document SHA-256 after this correction is
`d0822a7643be7ae9189194d5dbafa61418a939b7a49064b528244e9c8046d9a2`.
The behavior-only identity is
`c3ef97e6421b4dbdd06e7f44c33feeb33dd7be7ae74699a43558ff142232a91c`.
