# G22 generalist-learning gate report

## Decision

`G22 PASS` on 2026-08-03.

The gate accepts the frozen semantic-v2 PPO curriculum, matched learned and
non-neural comparisons, recurrent/attention/graph state and exact recovery,
measured CPU/CUDA execution, development retention, and a separately
source-frozen 42-case independent evaluation. It preserves G14-G21 and V1. It
makes no arbitrary-content, universal-opponent-victory, ONNX-package, in-game
agent, clean-root reproduction, or V2-release claim.

## Gate evidence

| G22 clause | Result | Evidence |
|---|---|---|
| Finite multi-seed PPO | `PASS` | Six learned campaigns (two matched 1,457,520-parameter architectures by three seeds) completed 48 updates and 6,144 transitions each; all 288 updates were finite and all 36 development candidates were eligible |
| Hierarchical curriculum | `PASS` | Seventeen bounded programs across seven G15-G21 stages, with a per-update episode floor for every introduced program and development retention every four updates |
| Recurrent, attention, and graph state | `PASS` | Typed M15 graph tensors, domain-token attention, legal program masks, GRU hidden state, explicit resets, eight-step boundaries, and checkpoint state are implementation- and mutation-tested |
| Matched comparisons | `PASS` | Monolithic and specialist-router campaigns have identical parameter and transition budgets; public-heuristic, seeded-random, and wait-only baselines retain matched decisions and complete metrics; no architecture-superiority claim is made |
| CPU/CUDA semantics and cost | `PASS` | Batches 1, 8, and 32 pass every frozen forward/loss/gradient/update/checkpoint tolerance with identical greedy programs; inference and update benchmarks retain 30 samples after ten warmups plus GPU resource telemetry |
| Retention | `PASS` | All accepted candidates preserve previously passing programs; selected-checkpoint qualification passes all 16 active programs and revalidates the exact G15-G21 native evidence chain |
| Exact recovery | `PASS` | Both learned architectures reproduce uninterrupted 24-update execution through an independent update-16 checkpoint plus an eight-update fresh-process resume, including parameters, optimizer semantics, RNG streams, actions, values, rewards, metrics, hidden state, development results, and semantic checkpoint identity |
| Independent protocol | `PASS` | Follow-up-v2 used 42 disjoint unseen seeds, one manifest read, 42 fresh optimizer-free evaluator processes, 42 network-unshared native processes, no retry, replacement, reexecution, or post-result selection, and retained every case and failure category |
| Independent policy statistics | `PASS` | Learned mean return is `1.54319060396`; lower paired 95-percent confidence bounds are `0.390291622196` over seeded-random-legal and `1.42192802898` over wait-only |
| Every-mode native service | `PASS` | Exact required-program admission covers road, rail, water, air, and routing-labeled multimodal service; every required case has positive delivery and income |
| Coverage and regressions | `PASS` | All programs, climates, map sizes, opponents, broad probes, and native G15-G21 retention checks pass; all nine classified failure counts are zero |
| Earlier failed evidence | `PASS` | Final-v1 remains immutable `FAIL` after 42 attempts and follow-up-v1 remains immutable `FAIL` after 42 zero-failure attempts; follow-up-v2 replaces or relabels neither suite |
| Invalidating defects | `PASS` | The separately frozen required-program aggregate closes V2-DEF-0006; the ledger contains zero nonclosed defects or divergences |
| Earlier correctness floors | `PASS` | Aggregate V2 verification plus the unchanged complete 235-test V1 regression pass |

## Accepted machine evidence

- Learning contract:
  [`m22-learning-contract.json`](../../config/v2/m22-learning-contract.json),
  SHA-256
  `f3ae8f89dfb6edf19b910c55f55845279b77ddd7be5adbd1db244984f968b07b`.
- Native-qualified corpus:
  [`m22-native-corpus.json`](../../config/v2/m22-native-corpus.json), SHA-256
  `0af952bb840bca2a80a577e2a2446845f2db749d7efbaeb06af4b94418ff6725`.
- Matched training:
  [`m22-training-evidence.json`](../../config/v2/m22-training-evidence.json),
  SHA-256
  `1a0019a83816981ca355ae7c51f175fc482b2afecc45413d23d55a9ae2c177b1`.
- Selected-checkpoint qualification:
  [`m22-qualification-evidence.json`](../../config/v2/m22-qualification-evidence.json),
  SHA-256
  `192f784c54420f99e01384c4c453e2df651c2d87b479c0bee3dc46bf3b5a3798`.
- Exact recovery:
  [`m22-recovery-evidence-v2.json`](../../config/v2/m22-recovery-evidence-v2.json),
  SHA-256
  `d486d7704420ae5b2cf0b37b7add8a77ccd188434b9930f6d3e3c06e906df0d8`.
- Independent follow-up-v2 manifest:
  [`m22-followup-v2-manifest.json`](../../config/v2/m22-followup-v2-manifest.json),
  SHA-256
  `1ba5ff295520d30c88a4d2282804992eedab8cb8f8c1174058e978da63725f4e`.
- Independent follow-up-v2 evidence:
  [`m22-followup-v2-evaluation-evidence.json`](../../config/v2/m22-followup-v2-evaluation-evidence.json),
  SHA-256
  `21e53fa3c7f7f5a15fcd9f199f0a59920082f3e03b8292ed968da44e9dc319ec`;
  internal report SHA-256
  `032d66ec189840ed727ace92694704e55cb14e4c46963a1c6bc3a8950d613bac`.
- Selected checkpoint:
  `03894fd1238b69b6724d82eb441380312be4e8226efa602fa5e43972f7fa9f5f`.
- Follow-up-v2 source commit/tree:
  `07b8967fa3d287bd6f7e8ca6bb61f27a5a013a69` /
  `b4626cc2529dcff46455fcc2919433b2c42859ba`.
- Evaluator executable SHA-256:
  `bc87f4608643b4664068381fa5136d464c44bd05dad09a66fa088bfa995b92e6`.
- Native executable SHA-256:
  `607702be982848e5099cd72022b4379d5a5fe68c77b69797f0b2b5fb8eb014ef`.

## Independent result summary

The accepted follow-up-v2 suite contains 42 cases and covers the exact frozen
16-program distribution over road, rail, water, air, multimodal, competition,
and broad probes. The runner read the new manifest once only after source,
checkpoint, evaluator, runtime, CUDA, sandbox, both immutable earlier suites,
and fixed evaluator preflight checks passed. It then attempted every case in
manifest order. The retained protocol records 42 evaluator attempts/processes,
42 native dispatches/processes, zero retries, zero replacements, and no
post-result selection.

All learned actions match their required programs. All native cases pass. The
exact service inventory admits nine programs with fixed counts and maps them to
all five required modes independently of the public task label, while retaining
the two multimodal-transfer cases as `task=routing`. Every acceptance predicate
is true and all failure counts are zero. Offline validation recomputes the
complete report; live validation additionally rehashes the evaluator, native
runtime, and every per-case artifact.

## Failed-suite preservation and defect closure

The initial final-v1 suite remains immutable `FAIL`: it attempted all 42 cases
and exposed eight native harness/runtime failures. The corrected independent
follow-up-v1 also remains immutable `FAIL`: it attempted all 42 cases with zero
classified failures, but its frozen aggregate omitted routing-labeled
multimodal service cases. Neither result was relabeled, replaced, or rerun.

Follow-up-v2 was a distinct pre-access source boundary with another 42 unseen
seeds. Its acceptance contract selects service cases from an exact
required-program inventory instead of `task=service`. Source tests cover a
complete synthetic pass, positive routing-labeled multimodal admission, and
multimodal native-service failure classification. Retained evidence mutation
tests reject changes to scores, source identity, reports, native artifacts,
evaluator identity, earlier failed suites, retry counts, and replacement counts.
That independent passing evidence closes `V2-DEF-0006` without changing either
earlier suite.

## Verification result

The complete source, contract, corpus, training, qualification, recovery,
runtime, manifest, failed-suite, and follow-up-v2 validators pass. Follow-up-v2
has 44 source/manifest/evidence mutation tests, and the aggregate suite retains
all earlier V2 gates and the unchanged V1 traceability regression:

```text
./scripts/v2/verify.sh
```

## Next stage

M23 is next in dependency order: content-addressed checkpoint and ONNX release
packages, native/standalone/in-game equivalence, visible normal-game operation,
controls and fallback semantics, clean-root reproduction, complete model card,
benchmark/notices/manifests, zero-defect release closure, and publication.
