# M16 native cargo qualification patch

Apply `0001-Add-native-V2-cargo-and-industry-qualification.patch` to the
accepted M15 competence source commit
`abc1912e290d8f49221fb3f68e30f3bcb3190ec9` without offsets or fuzz.

The delta adds the `-N <manifest> -O <report>` native qualification path. It
uses real OpenTTD road stops, depots, road vehicles, refits, orders, movement,
loading, transfer, final delivery, cargo payment, subsidy, and industry-input
production behavior. Deterministic source packets and acceptance for otherwise
unavailable sinks are qualification-fixture setup; they are not claimed as
normal scenario generation.

The path is opt-in. Cargo-payment telemetry and station-acceptance overrides
remain disabled during ordinary OpenTTD play. The shared
`ProcessIndustryInputCargo` helper preserves the normal production path while
allowing the qualification runner to exercise that exact transition.

The accepted source, patch, executable, and OpenGFX identities are frozen in
[`m16-cargo-source.json`](../../../../../../config/v2/m16-cargo-source.json).
