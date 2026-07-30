# ADR 0001: Project Basis and Publication Boundary

- Status: Accepted
- Date: 2026-07-30
- Decision owners: repository owner and P0 implementation agent
- Applies to: `PORT-001` through `PORT-005`

## Context

This repository is a user-controlled research project that derives behavioral
evidence and instrumentation from a pinned OpenTTD source revision. The P0 phase
must establish a reproducible external oracle before any scalar gameplay port,
reinforcement-learning wrapper, batched backend, CUDA backend, or viewer exists.

The authoritative OpenTTD source is the `openttd-upstream` submodule at commit
`29f808ef0022064e6d9a83c8476d1e0f4686af86`. The outer repository began P0 from
commit `58895696c8a75eda2fac2ae553654ba4398f5cda` and development occurs only on
`port/p0-oracle-contract`.

The GitHub repository was inspected on 2026-07-30 with read-only metadata calls:

- repository: `goldbar123467/openttd-cuda-rl`;
- default branch: `main`;
- visibility: public;
- authenticated permission: administrator;
- transport: SSH to the user-controlled repository.

No visibility setting was changed. Any future visibility change requires explicit
human authorization and is outside this decision.

## Authority hierarchy

Conflicts are resolved in this order:

1. the pinned OpenTTD source and tests at the exact submodule commit;
2. repeatable observations from binaries built from that commit under the frozen
   reference profile;
3. `NEXT_STAGES_IMPLEMENTATION_HANDOFF.md`;
4. `OpenTTD_CUDA_RL_REVERSE_ENGINEERING_REPORT.md`;
5. `research-notes/09-verification-audit.md`;
6. subsystem research notes;
7. official specifications and primary technical sources;
8. peer-reviewed testing literature;
9. explicitly labeled, experimentally tested hypotheses.

Current OpenTTD `master`, memory-based explanations, generated summaries, and
convenience assumptions are not behavioral authority.

## Decision

1. Keep the user repository public unless its owner explicitly directs otherwise.
2. Treat source-derived instrumentation and subsequent translation work in this
   public repository as `GPL-2.0-only` derivative work.
3. Preserve upstream copyright and license notices, publish the applicable license
   text, and track provenance for OpenTTD, OpenGFX, dependencies, fixtures, and
   generated evidence.
4. Describe this as an independent research project. Do not use branding or prose
   that implies ownership, approval, or endorsement by the OpenTTD project.
5. Never submit AI-generated code, issues, comments, reviews, or pull requests to
   upstream OpenTTD. All generated work remains in the user's repository.
6. Never modify the pinned submodule in place. Instrumentation is an ordered patch
   series stored outside the submodule and applied only to a disposable worktree or
   disposable copy.
7. Never force-push, rewrite user history, delete unrelated refs, or merge to
   `main` without explicit human direction.
8. Push each valuable, verified atomic milestone because `/workspace` is not backed
   by a persistent volume.
9. Scan staged content for credentials before every push. Credential-bearing files,
   process environments, shell history, SSH keys, GitHub authentication files, and
   unredacted tokens are forbidden evidence materials.

## GPL boundary

The pinned upstream source is licensed under GPL version 2. This project uses the
SPDX identifier `GPL-2.0-only` and will keep the corresponding license text under
`LICENSES/GPL-2.0-only.txt`. OpenGFX is a separately acquired content dependency;
its exact release bytes and installed-file provenance are recorded rather than
vendored automatically.

This decision records project treatment, not legal advice. A material distribution
or relicensing change requires a new reviewed decision and human approval.

## Consequences

- Exact-commit source links and local paths must appear in the P0 source register.
- Every source-derived claim must map to code, a test, and retained raw evidence.
- The outer branch may contain instrumentation patches but the submodule gitlink
  must remain pinned and clean.
- Public pushes are deliberate publication events and must be preceded by diff,
  secret, submodule, and focused-test checks.
- Later implementation stages remain forbidden until the P0 oracle contract passes.

## Rejected alternatives

- Working directly on `main`: rejected because it bypasses the contract's branch
  isolation and review boundary.
- Tracking current upstream `master`: rejected because floating behavior cannot be
  reproduced or used as parity authority.
- Editing the submodule directly: rejected because it obscures the source baseline
  and makes clean-oracle reconstruction unreliable.
- Treating the project as an official OpenTTD contribution: rejected by ownership,
  publication, and upstream AI-contribution constraints.

## Verification

Gate 0 verifies this decision through credential-safe repository metadata,
submodule identity and cleanliness, explicit scope documents, the requirements
matrix, and pushed-branch evidence. Final P0 verification additionally checks the
license files, source register, patch-series identity, clean submodule, remote
branch, and zero later-phase code.
