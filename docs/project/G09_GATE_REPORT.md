# G09 gate report: independent evaluation and policy quality

## Result

`G09: PASS` on 2026-08-02. All 26 M09-owned requirements pass, and
`DONE-003` passes because the development-selected learned policy clears both
baseline superiority and reliable profitability on the frozen final set.

## Frozen identities and provenance

| Artifact | Identity |
|---|---|
| Preregistration commit | `412f40af7dbbab83323ad4ae73cda0744ebf887b` |
| Training/evaluator foundation commit | `b0b171e910956e4f0e140b17650b9e33ae7193ca` |
| Accepted evaluation-runner commit | `6919a121e66e3928136dc7659e761c9040f62c67` |
| Evaluation compatibility | `c64c9876c1f6cf46dcc2642bd4628ed45f4659d1866a047d4e51def60dab9a5e` |
| M09 OpenTTD executable | `8e61a1325090240cf084ad0a9d82376bf11082564bb0eb17ac4a1c8033158a0c` |
| Optimizer-free evaluator executable | `e619d8f64f67debce625dde032656b38278c59c5703f157cece8591509feef0b` |
| Training manifest file | `4913865a6c33d35214327337d6eec60aa77ca5663d8f0314ae25fc920ca78b5b` |
| Training manifest semantic identity | `64e6efc78f50756b0b53bda2835c251f1f7627528ddec4a2b371246b954ad89e` |
| Final report file | `0eafc1924456ef9a752d4b6c149b29677dd2d427f2d06f6257bad5de46f09731` |
| Final report semantic identity | `1de3ca8d7a2900e491cd1ac2c1230726ed77e936803f77a4cfac38ac8ba1e568` |
| Raw 36-episode JSONL | `96353ace7c2dccaa7154f2cf1d383e51abf9e7b586847a56b984db3a7089dee7` |
| Selected evaluation package | `074b3c3838d9c4b53235d8f9ccc060047f7ce29929511fda6086f072c53b62e3` |

The accepted training evidence is under
`/home/thecl/.codex/artifacts/openttd-rl/m09-training-acceptance-a`. The final
report and raw episodes are under
`/home/thecl/.codex/artifacts/openttd-rl/m09-final-acceptance-a`.

## Exit criteria

| G09 criterion | Result | Evidence |
|---|---|---|
| Evaluator cannot update policy or normalization state | PASS | evaluator has no optimizer linkage; all nine package-file snapshots and native in-memory state digests remain unchanged |
| Baseline provenance and limitations are complete | PASS | frozen random, WAIT-only, and existing M05 scripted workflow registry plus raw two-layout results |
| Matched budgets reject unfair comparisons | PASS | three architectures by three run seeds, exactly 2,048 accepted samples per run, checked before comparison |
| A learned policy beats random and trivial | PASS | selected policy mean is 150 passengers and 424 operating profit versus random 68.5/-78.5 and WAIT 0/-333 |
| Reliable profitability and stability | PASS | both unseen primary episodes survive with positive balance, deliveries, and operating profit |
| MLP/CNN/combined comparison is complete | PASS | 18 primary episodes; seed means, dispersion, ranges, and two-sided 95% Student-t intervals reported |
| Training reward is not substituted for policy quality | PASS | all nine training rewards are reported with `quality_metric=false`; success uses native economic outcomes |

## Independent selection and primary result

The nine-run training process never opened a final template. It selected models
only from templates 05 and 06, recorded
`final_evaluation_accessed=false`, and then exited. Combined CNN/MLP seed
`2026090101` was the only development candidate with positive operating profit
and passenger deliveries on both development layouts. The separate final
process recomputed that selection before opening templates 07 and 08 and
recorded `final_results_used=false`.

| Unseen template | Operating profit | Passengers | Final balance | Survival | Invalid actions |
|---|---:|---:|---:|---|---:|
| `m02-template-07` | 394 | 145 | 60,794 | PASS | 0 |
| `m02-template-08` | 454 | 155 | 61,076 | PASS | 0 |
| Mean | 424 | 150 | 60,935 | PASS | 0 |

The selected policy also exceeds the documented existing M05 scripted workflow,
whose two-layout mean is 177 operating profit and 93 passengers. This comparison
is reported as context; the preregistered G09 superiority threshold names random
and trivial baselines.

## Matched architecture and seed stability

Each cell below is the mean over the two final layouts for one independently
initialized training seed.

| Architecture | Profit seed means | Profit mean / sample SD | Passenger seed means | Passenger mean / sample SD |
|---|---|---:|---|---:|
| Structured MLP | -333, -333, 43 | -207.67 / 217.08 | 0, 0, 124.5 | 41.5 / 71.88 |
| Spatial CNN | -333, -333, -333 | -333 / 0 | 0, 0, 0 | 0 / 0 |
| Combined CNN/MLP | 424, -333, -333 | -80.67 / 437.05 | 150, 0, 0 | 50 / 86.60 |

The 95% Student-t confidence intervals are wide for the MLP and combined
models. The report therefore makes no architecture-superiority claim and does
not present the selected seed as representative of the whole architecture.

## Stochastic and robustness results

Four explicitly seeded stochastic episodes all survive and operate profitably.
Their mean is 566.25 operating profit and 215.75 passengers. The eight greedy
robustness episodes cover both final layouts, starting balances 75,000 and
125,000, and horizons 64 and 256. Every case survives, delivers passengers, and
has positive operating profit; the mean is 528.5 profit and 175.25 passengers.
The report contains no robustness failure cases.

The final evidence contains all 15 registered metric dispositions. Station
rating remains explicitly unavailable because the frozen observation does not
expose it; no value is fabricated. Coverage and profitable-vehicle count remain
documented proxies, and company operating profit remains the V1 route-profit
proxy because V1 allows one route.

## Repository verification

- The native M09 suite covers all architectures, deterministic and stochastic
  inference, package corruption rejection, and read-only model/file state.
- Nine focused Python tests cover preregistration, exact patch composition,
  optimizer-free linkage, final-blind training, development-only selection, and
  training-seed confidence statistics.
- The accepted final report schema and semantic validator pass over 36 unique
  raw episodes: 18 primary, 6 baseline, 4 stochastic, and 8 robustness.
- The full repository suite passes 215 tests; Python compilation, JSON schema
  checks, ShellCheck, bash syntax, and Git whitespace checks pass.

G09 does not claim ONNX equivalence, portable three-runtime packaging, in-game
neural control, or long-duration recovery. Those remain M10 through M12.
