# M17 native rail qualification patch

Apply `0001-Add-native-V2-rail-qualification.patch` to the accepted M16 cargo
source commit `ceb913106af64d6a1a9c50afb15bf4437297363b` without offsets or
fuzz.

The delta adds the `-C <manifest> -P <report>` native qualification path. It
uses real OpenTTD rail construction and removal, every track orientation,
junctions, crossings, stations, depots, waypoints, conversion, all six signal
types and two visual variants, reservations, train construction and consists,
refits, orders, timetables, service intervals, clone/sale, autoreplace, vehicle
movement, loading, final delivery, and company accounting.

The path is opt-in. Direct cargo packets and destination acceptance are bounded
qualification-fixture setup. The service probes still traverse real rail routes
and use the native station cargo list, vehicle ticks, delivery, and payment
paths; they do not claim that the empty fixture map generated cargo normally.

The accepted source, patch, executable, and OpenGFX identities are frozen in
[`m17-rail-source.json`](../../../../../../config/v2/m17-rail-source.json).
