# ADR 0008: Define the V1 license, publication, and upstream boundary

- Status: Accepted
- Date: 2026-07-31
- Applies to: V1 source, binaries, dependencies, evidence, and publication
- Extends: ADR 0001 without carrying forward its P0-only delivery mandate

## Context

Version 1 compiles an RL bridge and a native neural-company controller into
OpenTTD. That source integration creates a different distribution boundary from a
standalone trainer that merely starts an unmodified executable. The repository is
also expected to retain research evidence and model packages, some of which have
different authorship, size, privacy, and licensing properties from source code.

OpenTTD's source headers and license file identify the engine as GNU General Public
License version 2 software. This repository already retains the corresponding text
at `LICENSES/GPL-2.0-only.txt`. Third-party dependencies such as OpenGFX, LibTorch,
ONNX Runtime, and their transitive runtime libraries retain their own licenses and
notices.

This record defines project policy, not legal advice.

## Decision

1. Source patches, glue code, and binaries that form the source-integrated OpenTTD
   program are treated and distributed as `GPL-2.0-only`, with upstream copyright
   and notices preserved.
2. Every distributed source or binary bundle includes the applicable license text,
   exact OpenTTD base commit, ordered patch-series identity, build instructions,
   and a dependency/license manifest sufficient to reconstruct the corresponding
   source.
3. Standalone artifacts do not inherit a license by implication. Original trainer
   libraries, schemas, documentation, datasets, checkpoints, and model packages
   receive explicit license/provenance fields before public distribution. An
   artifact with an unknown or incompatible redistribution basis is retained
   privately or omitted from the release.
4. OpenGFX and every other game-content dependency are recorded by release,
   source URL, digest, license, and installation method. They are not silently
   vendored into source or model packages.
5. The work is described as an independent research project. Nothing may imply
   OpenTTD endorsement or official project status.
6. No AI-generated source, issue, comment, review, or pull request is submitted to
   upstream OpenTTD. Upstream interaction in this project is read-only unless the
   repository owner gives a new explicit instruction.
7. A public push, release, model upload, or change of repository visibility is a
   deliberate external publication action. Local implementation work does not
   authorize it. The P0 instruction to push every milestone is superseded for V1.
8. Before publication, the exact staged/release set is reviewed for credentials,
   personal paths, environment dumps, restricted data, generated binaries, license
   notices, provenance, and reproducibility. Secret-bearing material is never
   accepted evidence.
9. Large raw runs and checkpoints live in an ignored content-addressed artifact
   store. Only reviewed compact evidence, schemas, manifests, and deliberately
   selected release artifacts enter Git.

## Publication package boundary

The normal-game distribution is an OpenTTD-derived binary/source bundle plus the
CPU inference runtime and a model package. It excludes the PPO optimizer, training
runtime, CUDA toolkit, training-only LibTorch/CUDA libraries, raw trajectories, and
private experiment state.

The training distribution may add those dependencies, but its manifest must make
the added license and source-offer obligations visible rather than relying on the
playable package inventory.

## Rejected alternatives

### Treat the bridge as a license-independent plug-in

Rejected because V1 deliberately compiles source-derived integration into the
OpenTTD program. The project will use the conservative integrated-program boundary
instead of making a legal conclusion that a custom interface changes it.

### Commit every experiment and model to Git

Rejected because large or sensitive run products obscure review, make repository
history expensive, and can accidentally publish data that was never accepted.

### Automatically publish every passing gate

Rejected because a technical pass does not establish release scope, licensing,
privacy, or owner authorization.

## Verification

`G01` and `G12` must prove:

- exact license files and notices are included in each build/package inventory;
- every dependency and content item has source, version, digest, and license data;
- source reconstruction starts from the named OpenTTD commit and patch series;
- the playable package has no trainer or CUDA-training dependency;
- package mutation tests reject missing license/provenance fields; and
- publication review contains a credential/path scan and an explicit approved
  release file list.

Accepting this ADR establishes the boundary; it does not claim that a distributable
bundle already exists.
