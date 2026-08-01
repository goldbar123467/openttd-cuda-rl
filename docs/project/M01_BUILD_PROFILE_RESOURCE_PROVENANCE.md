# M01 Build Profiles, Runtime Resources, and Dependency Provenance

- Milestone: `M01`
- Component result: `PASS`
- Gate result: `G01 PASS`
- Date: 2026-08-01

## Outcome

The three evidence families that remained after the accepted toolchain and clean
OpenTTD builds now pass:

1. a strict seven-profile build matrix freezes feature/dependency boundaries;
2. two preregistered runtime-resource campaigns retain raw samples and report
   medians plus complete ranges; and
3. two offline provenance runs produce byte-identical manifests covering every
   locked artifact/package and every file-backed runtime dependency.

No accepted release pair was rebuilt or modified. No OpenTTD feature, scenario,
environment bridge, trainer, production model, or in-game neural controller was
added in this work.

## Build-profile matrix

The machine contract is `config/v1/build-profile-matrix.json`, validated by
`scripts/v1/build_profiles.sh` against the Draft 2020-12 schema. Its SHA-256 is
`abefa9a9bf64645da5f5df3e12b171f71a7d7449aa4d6571c5bf28016051718d`;
its canonical identity is
`677619eff8daa697340e0de28abdad4a9472e83578da2b9591376f8c8ea05450`.

The exact profiles are:

| Profile | State at G01 | First complete execution |
|---|---|---|
| C++ debug/assertions CPU | defined, target pending | `G03` worker/native tests |
| C++ optimized CPU | OpenTTD baseline validated | repeat for `G03` worker |
| ASan + leak checks | defined, target pending | `G02` owned 32 by 32 patch |
| fail-fast UBSan | defined, target pending | `G02` owned 32 by 32 patch |
| CUDA debug/check | defined, target pending | `G08` first CUDA workload |
| CUDA optimized | ABI/toolchain baseline validated | `G08` parity/benefit/soak |
| playable inference-only | defined, target pending | `G10` accepted ONNX package |

“Defined, target pending” is not an executed-profile pass. Each such row has an
explicit activation gate and resolution task, so later milestones cannot treat
configuration alone as evidence.

The matrix freezes independent `OPTION_RL_BRIDGE`,
`OPTION_RL_IN_GAME_INFERENCE`, `OPTION_RL_TELEMETRY`, and
`OPTION_USE_ASSERTS` controls. Training/inference/telemetry default off;
assertions default on. Every production profile forbids a Python runtime.

The accepted dedicated headless binary remains immutable release-build evidence
and is explicitly `worker_eligible=false`. The future environment worker is one
regular, non-dedicated OpenTTD process per environment with a controlled null
video loop; its first activation is `G03`.

## Runtime-resource experiment

The preregistration file is `config/v1/resource-measurement-plan.json`, SHA-256
`2daa2d70d8ab8f178f6f9cc393dc07a9d3f858b0b1b46bb2cd9f96be6b2026b5`.
Each workload used one excluded warm-up and five retained samples. The throughput
workload executed 8,192 ticks. The playable idle workload paused after game start,
remained alive for a declared three-second window, and was then bounded with the
same explicit `SIGKILL` termination class used by the accepted playable smoke.

Accepted runs:

| Run | Report SHA-256 | Report identity |
|---|---|---|
| `m01-runtime-resources-20260801-c` | `aeb55fdae78cd79a8648e5a5ceb381b916cbf9b3e9c613abb51665dc1294478f` | `06937c1d88b9bac47e6b4587d43360e114ae33e2fb2fbe02393238003922b1bd` |
| `m01-runtime-resources-20260801-d` | `0c176672f92e4d2d3172ebe845c10e164fa8b83f326302fbfccab787d5ae8b7b` | `b0c9dc866be9420b2948e1c8a2c6ef263d7dd2bae5e3256221cb197cb8f2cc1c` |

The reports differ because elapsed time and resource use are observations, not
deterministic build products. Their plan, commands, binary identities, workload
inventory, correctness rules, warm-up count, and sample count are identical.

Median/range observations:

| Metric | Run `c` | Run `d` |
|---|---:|---:|
| Headless startup/shutdown seconds | 0.101237 (0.101192–0.101239) | 0.101161 (0.096254–0.101324) |
| Headless ticks/second | 57,786 (53,883–57,835) | 59,902 (55,701–62,221) |
| Headless max RSS KiB | 30,892 (30,680–31,084) | 30,984 (30,648–31,128) |
| Playable startup/shutdown seconds | 0.177167 (0.172083–0.182207) | 0.197586 (0.187499–0.207692) |
| Playable paused-idle CPU utilization percent | 5.202 (4.850–5.549) | 5.182 (5.125–5.359) |
| Playable paused-idle max RSS KiB | 66,040 (62,324–75,396) | 67,716 (66,404–68,616) |

These are hardware/host baselines, not performance thresholds or later worker
throughput claims.

## License and provenance

`scripts/v1/dependency_provenance.sh` validates local bytes and installed package
metadata without network access. It records source URL, exact version, SHA-256,
license declaration/evidence, and distribution status for:

- 25 locked toolchain/export artifacts;
- 34 locked OpenTTD build-overlay packages;
- OpenGFX as an explicit GPL-2.0 record;
- OpenTTD 15.3 source; and
- 90 file-backed libraries from the accepted headless/playable `ldd` closures,
  comprising 26 locked-overlay and 64 host-runtime dependencies.

The Linux virtual DSO is not file-backed and therefore is not falsely assigned a
package hash/license. Every real runtime path must resolve to exactly one locked
archive or installed host package; ambiguity and missing license evidence fail.

Both accepted provenance roots, `m01-dependency-provenance-20260801-a` and `-b`,
produced byte-identical JSON and text. Manifest SHA-256 is
`d3a567d2cbee1c0e9975ad36424480402b05a3a6f0849f5296056e862cdb1b05`;
canonical identity is
`fe9b7a915c0b33d637e45d875dcdc6bb13c918a15826302e020cb516f28a1adc`.

## Reproduction commands

Validate the tracked profile contract:

```bash
./scripts/v1/build_profiles.sh
```

Run a new resource campaign against either byte-identical accepted pair:

```bash
./scripts/v1/measure_runtime_resources.sh \
  --artifact-root /absolute/new/empty/root \
  --headless-root /absolute/accepted/headless/root \
  --playable-root /absolute/accepted/playable/root
```

Generate provenance offline:

```bash
./scripts/v1/dependency_provenance.sh \
  --artifact-root /absolute/new/empty/root \
  --dependency-cache /absolute/locked/toolchain/cache \
  --build-cache /absolute/locked/deb/cache \
  --headless-root /absolute/accepted/headless/root \
  --playable-root /absolute/accepted/playable/root
```

The runners refuse output overwrite, reject incomplete inventories and drift, and
emit machine-readable JSON plus stable human-readable summaries.

## Failure history retained

Resource roots `a` and `b` are diagnostic failure evidence. Run `a` exposed an
accidental extra CLI argument. Run `b` showed that the SDL process did not honor
the initially preregistered `SIGTERM` idle boundary. The accepted plan therefore
uses explicit bounded `SIGKILL`; neither failure was hidden or relabeled.
