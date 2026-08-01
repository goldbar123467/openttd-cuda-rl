# ADR 0012: Make V1 evidence content-addressed and experiments preregistered

- Status: Accepted
- Date: 2026-07-31
- Applies to: tests, benchmarks, training, evaluation, model selection, and releases

## Context

V1 can fail while appearing successful: a reward exploit can look like learning,
an asynchronous boundary can corrupt trajectories, a GPU path can be faster but
wrong, a selected seed can exaggerate policy quality, and an ONNX file can exist
without preserving native behavior. The project therefore needs one policy for
what constitutes evidence and how a defect invalidates it.

Legacy P0 developed useful traceability and immutable-failure practices, but its
freight fixtures and phase-local results cannot prove bus V1 claims.

## Decision

### Artifact classes and storage

1. Every accepted run has a stable run ID and immutable manifest. The manifest
   records repository and OpenTTD/patch identities, dirty state, tool/dependency
   manifests, host/hardware, configuration digest, complete seed ledger, schema
   and compatibility IDs, command line, start/end time, exit/result state, parent
   artifacts, and file digests.
2. Raw logs, trajectories, checkpoints, profiles, crash bundles, and large reports
   live in a generated content-addressed artifact store outside tracked source.
   Compact reviewed evidence indexes under `evidence/v1/` refer to digests and
   approved durable locations; paths alone are never artifact identity.
3. Inputs are immutable. Derived artifacts name every parent digest. Re-running a
   logical name with different bytes creates a new identity rather than overwriting
   history.
4. Failure evidence is retained before minimization. A minimized reproducer links
   to, but does not replace, the original failure manifest.
5. Mandatory persistence is transactional: write to a temporary file, flush and
   close, verify length/digest/schema, then atomically publish. Disk-full, short
   write, permission, rename, or digest failure cannot be reported as success.
6. Evidence excludes secrets, full environments, authentication state, unrelated
   personal files, and unrestricted absolute paths. Redaction is explicit and may
   not remove a value needed to reproduce a claim.

### Claim and experiment protocol

7. Before a performance, parity, or model-quality campaign starts, its manifest
   freezes:

   - hypothesis and requirement IDs;
   - exact implementation/input identities;
   - independent variable and matched controls;
   - warmup, measurement, repetition, and seed counts;
   - metrics, units, aggregation, confidence/statistical method;
   - correctness tolerances and practical-success threshold;
   - exclusion, retry, early-stop, and failure rules; and
   - selection rule and evaluation split.

8. Correctness is decided before performance. A faster result that fails parity,
   drops work, changes tick semantics, or omits checks is a defect, not an
   optimization.
9. Performance claims report distributions and resource use, not only the best
   sample. CPU/GPU comparisons use equivalent work, validated outputs, declared
   synchronization, warmup, and transfer accounting. Break-even batch size and
   negative results are retained.
10. Development, model-selection, and final-evaluation scenario/seed sets are
    disjoint and named. Final sets are frozen before candidate comparison and may
    not be rerun selectively to choose a model.
11. Reward, economic outcome, robustness, and failure rates are reported
    separately. Positive reward alone never proves a useful bus company.
12. Existing AI comparisons include AI/version/source/configuration/seed/support
    limitations and disclose interface/timing differences. They cannot be merged
    into a misleading common score when conditions differ.

### Evidence authority and invalidation

13. A requirement becomes `PASS` only when its named test is `PASS`, evidence is
    fresh for the accepted code/contract identities, and all referenced artifacts
    validate. A file name, successful command exit, screenshot, or legacy P0 result
    alone is insufficient.
14. Dirty-worktree exploratory runs are permitted and must be labeled. Release
    evidence requires an exact recoverable source snapshot; unrecorded changes
    invalidate it.
15. A defect records severity, affected requirement/gate/artifact IDs, discovery
    evidence, disposition, and closing evidence. A defect capable of changing
    transitions, training data, selection, export, or evaluation reopens every
    downstream claim until regenerated or explicitly proven unaffected.
16. V1 traceability rejects P0-only evidence and rejects downstream aggregate
    completion when any dependency is non-passing or a blocking defect is open.
17. External trackers and dashboards are optional sinks. The local structured log
    and immutable manifest remain authoritative and sufficient for offline review.

## Release evidence set

An accepted V1 release index contains at least:

- source/build/dependency/content manifests and clean reconstruction evidence;
- environment, observation, action, reward, trajectory, metric, and model schemas;
- complete test/quality matrix and defect ledger;
- CPU/CUDA parity and measured-benefit report;
- preregistered multi-seed model and baseline evaluation;
- checkpoint recovery and soak/fault evidence;
- ONNX package and three-runtime equivalence report;
- clean-user train/export/install/play acceptance record; and
- exact requirement-to-test-to-evidence closure.

## Rejected alternatives

### Store only aggregate metrics

Rejected because aggregates cannot diagnose scenario imbalance, seed selection,
worker failure, or the first invalid transition.

### Let each executable invent its own logging format

Rejected because the monitor, evaluator, trainer, and release audit would no
longer share metric meaning or provenance.

### Treat a fixed seed as reproducibility proof

Rejected because builds, content, dependency algorithms, worker ordering, and
device kernels also affect results.

### Discard failed or slower experiments

Rejected because doing so hides defect frequency and biases architectural choices.

## Verification

The traceability/defect validators, artifact-schema mutation tests, interrupted
write/fault tests, metric-source comparisons, experiment-manifest lints, and `G12`
closure audit enforce this policy. Accepting the ADR creates no result by itself;
all current V1 requirement rows remain non-passing until their implementation
evidence exists.
