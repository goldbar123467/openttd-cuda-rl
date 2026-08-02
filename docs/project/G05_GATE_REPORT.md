# G05 explicit bus action and legality gate report

- Gate: `G05`
- Result: `PASS`
- Date: 2026-08-01
- Action compatibility:
  `215c7d3ebeea97f1629debee4a2d10301838ccfd3085e4828685591677b58536`
- M05 result tree: `ad0575b92f7975ef085e5f35bfe182a504d6cb51`
- M05 composed source identity:
  `9bb57367151fbf4eedcd802d179c946685a911bec9b99d7573501e0f52a3b2bd`

## Decision

G05 passes. The accepted source contains a fixed 41-action semantic catalog,
boundary-bound legal masks, normal OpenTTD test/execute command paths, explicit
route transactions, six typed outcomes, shared safe policy sampling, an
independent legality oracle, structured command logs, and a useful actual-engine
bus-service trajectory on every frozen scenario.

## Exit criteria

| G05 criterion | Result | Evidence |
|---|---|---|
| Every action and boundary parameter round-trips | PASS | exhaustive 41-index codec tests plus strict type negatives |
| Fixed/random masks match an independent oracle | PASS | 614 actual-engine states across eight templates |
| Sampling never returns a masked index | PASS | shared four-consumer softmax/greedy/sample and all-zero tests |
| Cost, tick, owner, and mutation match OpenTTD | PASS | per-action balance, subcommand, snapshot, owner, and 128-tick assertions |
| Transaction semantics survive injected failure | PASS | first-order rejection rolls back; unsupported hook fails fatally at transition zero |
| Scripted policy creates useful service | PASS | all templates build road/stops/depot, buy, order, run, deliver, and earn income |
| Compatibility mismatch fails closed | PASS | wrong identity and stale boundary reject with zero mutation |
| Legal mask generation is non-perturbing | PASS | source audit and repeat-at-boundary identity checks |

## Repeated evidence

The retained roots are:

```text
/home/thecl/.codex/artifacts/openttd-rl/m05-action-oracle-20260801-a
/home/thecl/.codex/artifacts/openttd-rl/m05-action-oracle-20260801-b
```

`diff -qr` produces no output. Both `manifest.json` files have SHA-256
`30700cfb8a556ddd7c23eec7463bac7a7f2bf365b9a94742fdeddd982cb2d7b8`.
The executable SHA-256 is
`ed23eeaea1f9deba1333c7ae3be1a8d16f30c203e706ce61b5a5138241f79094`.

The campaigns cover all nine action families, 614 differential-mask states,
eight deterministic 32-step legal-policy traces, ordinary/native rejection,
rollback, stale input, illegal input, identity mismatch, and fatal integration
failure. Scripted template incomes are 145, 112, 151, 157, 172, 144, 138, and
186; every value is positive and backed by passenger delivery.

## Quality closure

The M05 patch applies exactly after the accepted M04 result tree and produces the
frozen M05 tree with no fuzz, offset, warning, or whitespace error. The native
assert-enabled build compiles and all 98 upstream CTest entries pass. Contract,
codec, mask, sampling, oracle, patch-composition, source-audit, report-schema,
golden, and actual-engine campaign checks pass. The complete repository gate
passes all 169 tests, 227 requirement rows, 21 test-suite mappings, 81 passing
requirements, 10 deferred post-V1 requirements, and zero nonclosed defects. All
33 repository-owned shell scripts pass ShellCheck 0.9.0 and `bash -n`.

## Downstream boundary

G05 does not pass M06 rewards/termination/trajectory, PPO, CUDA, matched model
evaluation, ONNX export, or in-game neural playback. Downstream consumers must
use the exact action compatibility identity and preserve the accepted outcome
and mask semantics.
