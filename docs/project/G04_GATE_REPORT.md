# G04 versioned observation and preprocessing gate report

- Gate: `G04`
- Result: `PASS`
- Date: 2026-08-01
- Observation compatibility:
  `7f8a46af1fe2a2c23e755c71b3bc2d04c9a0d057c573e901e5c9ed9178ca13eb`
- M04 result tree: `fe815570b5c816c6b324a9bf63d965157ea425c6`
- M04 composed source identity:
  `820cf3ee0fb36734c318cb260e6cc4567a2a9acc55c831d5b36d1875341b291e`

## Decision

G04 passes. The accepted OpenTTD source now contains one fixed-shape native
observation encoder, an M03-boundary `OBSERVE` operation, an exhaustive machine
schema, explicit candidate dispositions, frozen normalization, actual-engine
goldens, cross-consumer byte equivalence, and matched-control non-perturbation
evidence.

## Exit criteria

| G04 criterion | Result | Evidence |
| --- | --- | --- |
| Every included scalar and tile has an actual-engine semantic comparison | PASS | 264,192 independent comparisons over eight templates |
| Every excluded source candidate has a reviewed rationale | PASS | 27-row candidate registry covering OBS-002 through OBS-013 |
| Repeated encoding is byte-identical at one snapshot | PASS | reset and built-route response bytes repeat in every worker |
| Orientation channels pass targeted fixtures | PASS | every road/stop/depot NE/SE/SW/NW plane is positive across the corpus |
| Ownership channels pass targeted fixtures | PASS | town roads remain distinct from company connector/stops/depot |
| Catchment channel passes targeted fixtures | PASS | engine `Station::catchment_tiles` source comparison on both stops |
| Blocked/buildable channels pass targeted fixtures | PASS | all 1,024 tiles per template compared to type/slope source |
| Route and vehicle channels pass targeted fixtures | PASS | two order endpoints and the live bus tile in every built setup |
| Encoder calls do not mutate or advance the engine | PASS | observed/control snapshots, tick/RNG/pool guards, and source audit |
| Schema/digest incompatibility is rejected | PASS | native bridge and all common adapters reject before tensor use |
| Trainer/evaluator/ONNX/in-game preprocessing is shared | PASS | one C++ entrypoint and identical canonical bytes for all consumer labels |

## Repeated evidence

The retained roots are:

```text
/home/thecl/.codex/artifacts/openttd-rl/m04-observation-oracle-20260801-a
/home/thecl/.codex/artifacts/openttd-rl/m04-observation-oracle-20260801-b
```

`diff -qr` produces no output. Both roots have:

| Artifact | SHA-256 |
| --- | --- |
| `manifest.json` | `a80aa42cbbb3b38e473e48023f04cda4aad5a1a84e8b059619c3d92155ff3485` |
| `goldens.json` | `1dce190b8e7216b03c5e45cc6ee0af050bf69aa773aecc051250a4288ccf3ec6` |

The executable SHA-256 is
`f38965086fefafa8e4a9f0b5f5eb2145c1ffb13dc5815e4cf5fa6a512551cf49`.
The report schema fixes 33,024 comparisons per template, 264,192 total, exact
consumer identities, non-perturbation, digest rejection, payload bounds, and
positive aggregate coverage for all 32 channels.

## Frozen golden tensor identities

| Template | Post-setup tensor SHA-256 |
| --- | --- |
| `m02-template-01` | `c6116afb16382d1c2ef1e35ecab0b6c43afe060a9a040087f44f897c56d47489` |
| `m02-template-02` | `3b9db2d3321ba54530c68a44a8eecee1216a937e4aaf2481f6fbd1b700ddbb89` |
| `m02-template-03` | `0faa82b72d3b99f1f27f1be1ab55269843dc1d388d7d9fe970cdf2c754588cd3` |
| `m02-template-04` | `943d186714993b50dfa3d7f07e6c92ff0eff723f5157caf8ecc1919d55099b1c` |
| `m02-template-05` | `9c7e2f7de3979ead08a128e0d1f1f2ace2abe2fcc46ec82a8a6a1acb12193149` |
| `m02-template-06` | `9cc1944c8eff39a30e7e9b3899f9d4ec8e9c1a9f8710833d643d6973488c3c59` |
| `m02-template-07` | `d95b89c8dcfaa716a42ba1f87d28f59f23bc32d6f22df796ffe092a2fd11f423` |
| `m02-template-08` | `2d8a20174180a55686a349e454c5454c2dbfa9f8e3ceed0ca0fb6da0808589c4` |

## Quality closure

The M04 native build compiles cleanly and the ordered patch applies exactly
after the accepted M03 result tree with no fuzz, offset, warning, or whitespace
error. Focused contract, adapter, golden, source, patch-composition, and report
schema tests pass. The native build passes 98 of 98 CTest entries. The complete
repository gate passes all 155 tests, 227 requirement rows, 21 test-suite
mappings, 51 passing requirements, 10 deferred post-V1 requirements, and zero
nonclosed defects. All 33 repository-owned shell scripts pass ShellCheck 0.9.0
and `bash -n`.

## Downstream boundary

G04 does not pass M05 actions/masks, M06 reward/trajectory, PPO, CUDA, matched
model evaluation, ONNX export, or neural in-game playback. Those gates must use
this exact compatibility identity or reject the input.
