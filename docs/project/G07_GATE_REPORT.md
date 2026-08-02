# G07 gate report: trusted CPU PPO and structured MLP

## Result

`G07: PASS` on 2026-08-01. All 39 M07-owned requirements are `PASS`. M08 spatial
and measured-CUDA work is unblocked; final independent model quality remains
withheld.

## Frozen identities

| Artifact | Identity |
|---|---|
| Accepted source commit | `6f65df606cc8c1b52165b8562bdadacf8f1339d2` |
| PPO compatibility | `8649da85cee2914d423a7ae8f1bcff0fa6a1c7d749bd04232976fbad6df518c0` |
| PPO contract file | `cb4311100d12238bc668645321a866e5044e0abb1753ba6145fe27abcb3964ac` |
| Trainer executable | `c45a6589a47f175f041bf151339e38aad79ede207aaf3d4fc107e5d810f4f31f` |
| OpenTTD executable | `765c108213bfbb23df2712956acb9bbf6bbb5b0a1d446b0ec154a94fbf41876c` |
| Live manifest content | `c45d3b62521f22986cab284ffd66d0e73e7025313bcf8301ecdc15ffa792c648` |
| Live manifest semantic identity | `dd24f73653b3bd54566064340b556c2fe5f6bbac978fc809c7974de4947904e8` |
| Recovery report content | `ae933f91d367ab0c398b5965492d0a140395642952c3ce6b3a8aa1025f972fbf` |
| Recovery report semantic identity | `bfa70780e3c502c3adbc563d6d3798293c6dfedca482c7684ac3bf0db3e53eee` |
| Selected checkpoint | `7c4b210f43c06032488c72b613401734a0bf7e6eafcce4d0167d0dc1d3c92360` |

## Exit criteria

| G07 criterion | Result | Evidence |
|---|---|---|
| PPO math matches an independent reference | PASS | 14 scalar Python/native vectors at `1e-12`, plus analytic gradients and first Adam step |
| Numerical injection stops with diagnostics | PASS | injected NaN terminated the service and wrote diagnostic `b99b0796…` without model/optimizer payloads |
| Checkpoint round trip is exact | PASS | model, Adam semantic state, counters, RNG, config, and development metadata round trip |
| Interrupted and uninterrupted runs match | PASS | identical action continuation, rollout values, metrics, parameters, and checkpoint `1654d29c…` |
| Monitor equals logged sources | PASS | 41-field source registry, schema validation, wide/compact rendering tests, unavailable-GPU negative |
| Structured MLP improves over random | PASS | selected return `21.589691` vs `10.952728`; passengers `119.5` vs `94.5`; service `2/2` |
| Extended CPU run has no desynchronization | PASS | 64 updates, 8,192 transitions, 16 complete episodes, four isolated workers, no unresolved fault |

## Learning and selection evidence

The accepted run root is:

```text
/home/thecl/.codex/artifacts/openttd-rl/m07-cpu-ppo-acceptance-c
```

It trains only on templates 01–04 and evaluates only on development templates
05–06. No template 07/08 worker was launched. The seeded-random development
baseline produced mean return `10.952728271484375`, `94.5` delivered passengers,
and service on both templates.

| Candidate update | Eligible | Mean return | Mean passengers | Service |
|---:|:---:|---:|---:|---:|
| 16 | yes | `21.589691162109375` | `119.5` | `2/2` |
| 32 | no | `-2.287445068359375` | `0.0` | `0/2` |
| 48 | yes | `20.598846435546875` | `101.0` | `2/2` |
| 64 | yes | `20.763031005859375` | `95.0` | `2/2` |

The fail-closed rejection at update 32 proves that training health is not
mistaken for model quality. Deterministic selection retained update 16, and a
fresh process reproduced both episode results exactly. A separate calibration
run at
`/home/thecl/.codex/artifacts/openttd-rl/m07-cpu-ppo-development-b` produced the
same update-16 checkpoint identity and evaluation, demonstrating seeded
reproducibility across complete campaigns.

The 64-update soak completed 8,192 transitions and sixteen 512-step episodes in
`964578201797` ns. Every final training company had eight routes, eight buses,
positive passenger delivery, and positive income. Final update metrics were all
finite; mean rollout reward was `0.27805519104003906` and explained variance was
`0.9066571693365122`.

## Recovery and fault evidence

The accepted recovery root is:

```text
/home/thecl/.codex/artifacts/openttd-rl/m07-recovery-foundation-b
```

After update one, the campaign forked into uninterrupted and fresh-process
resumed paths. Their next stochastic action sequence, transition values, update
metrics, model parameters, optimizer semantic state, counters, and checkpoint
identity were exact. Repeated greedy evaluation did not mutate state. An
all-illegal mask was rejected while leaving the service usable.

A separate injected-NaN service wrote
`numerical-failure/diagnostic-b99b0796e677b45f0de17eb4af95c35d23e058c74f49ab619eb62cb074ea4ff6/diagnostic.json`,
terminated, and published no `model.pt`, `optimizer.pt`, or checkpoint header.

## Reference, metrics, and repository verification

- Clean pinned LibTorch build: 13 build steps and 4/4 CTest targets pass under
  `-Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Werror`.
- Native tests cover GAE, normalization, masking, clipped loss, seeded streams,
  minibatches, optimizer mutation, gradient clipping, exact recovery, corruption,
  metrics, terminal rendering, and nonfinite diagnostics.
- The deterministic two-action bandit improves from `0.5` to `1.0` greedy
  accuracy after 100 updates and 12,800 samples.
- Full repository suite with evidence closure: 199 tests pass; 227 requirement
  rows, 22 test mappings, and zero nonclosed defects validate.
- ShellCheck 0.9.0, `bash -n`, Python compile, schema validation, and Git whitespace
  checks pass.

An earlier 64-update development artifact (`m07-cpu-ppo-acceptance-a`) is retained
as rejected diagnostic evidence: it improperly mixed scenario partitions and its
final policy failed readiness. It is not G07 evidence. The corrected contract
hard-forbids final-evaluation exposure and selects only from the development
suite.

G07 does not pass the M08 CNN/combined/CUDA work, M09 independent evaluator, M10
export/package equivalence, M11 normal-game playback, or M12 release reproduction.
