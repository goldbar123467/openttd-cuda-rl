# PORT-003 instrumentation patch series

This directory holds the reviewable patch series applied only to disposable
worktrees of pinned OpenTTD commit
`29f808ef0022064e6d9a83c8476d1e0f4686af86`. The submodule itself remains
unchanged.

`patches/series` is the application order. PORT-003 is currently in progress:
the first two patches establish the opt-in trace sink, strict partial tape and
identity-header journal, and their upstream unit tests. The command,
projection, diagnostic, and non-perturbation patches remain mandatory before
the PORT-003 gate can pass.

The complete planned sequence is:

1. trace sink and primitive codec;
2. build, run, fixture, and schema identity;
3. native command-input and command-boundary records;
4. global, time, RNG, settings, and map projection;
5. pool and entity projection;
6. optional route and cargo diagnostics;
7. non-perturbation self-check hooks.

Use `oracle/runner/create_instrumented_worktree.sh` followed by
`oracle/runner/apply_instrumentation.sh`. Generated worktrees and builds belong
under a dedicated artifact root outside this repository.

`scripts/ci/p003_instrumentation_tests.sh --artifact-root ABSOLUTE_PATH
--tools-python ABSOLUTE_EXECUTABLE --foundation-only` verifies the current
apply/reject/reverse and command-input framing foundation. Invoking the test
runner without `--foundation-only` remains fail-closed until the complete
seven-patch collector and its runtime campaigns exist.
