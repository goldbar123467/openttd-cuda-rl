# M04 versioned policy-observation delta

This ordered delta applies after the accepted M03 result tree
`39ed7069eca2c48c512a9bdd989c049aca3c5329`. It adds one authoritative
native `RlObservation` encoder and extends the inherited-pipe bridge with
message type `8` (`OBSERVE`) without changing M03 message types `1` through
`7`.

The encoder returns a fixed 256-element float32 structured vector and a
32-channel by 32 by 32 float32 spatial tensor. It is callable only from an M03
`AT_BOUNDARY` or `PAUSED` state. Extraction executes no command, no game loop,
no pathfinder, and no RNG operation. An oracle-only raw source projection can
be requested for semantic comparisons; it is never a policy input.

The frozen machine contract is
`config/v1/m04-observation-contract.json` with compatibility identity
`7f8a46af1fe2a2c23e755c71b3bc2d04c9a0d057c573e901e5c9ed9178ca13eb`.

| Identity | Value |
| --- | --- |
| Accepted M03 composed identity | `d5d14398d545c951b04325d91d444e6194553e537d4b1f16615cba44351f2ef1` |
| M04 patch SHA-256 | `fd63122a88dc86ddd8caacb6be3ddce0445ab889701b779e60d264aa736ebea4` |
| M04 series SHA-256 | `b676ddaaf9cfe3fa1610a25941fac136c91e5c50445f604d0bc2637ada809670` |
| M04 result tree | `fe815570b5c816c6b324a9bf63d965157ea425c6` |
| M04 composed source identity | `820cf3ee0fb36734c318cb260e6cc4567a2a9acc55c831d5b36d1875341b291e` |

The patch applies with no fuzz, offset, warning, or whitespace error. The
default-off source profile remains unchanged because these files are compiled
only with `OPTION_RL_ENVIRONMENT=ON`.
