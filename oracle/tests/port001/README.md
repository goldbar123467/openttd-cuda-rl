# PORT-001 mandatory contract tests

`scripts/ci/p001_contract_tests.sh` runs all 61 test IDs from contract section
12. The suite is deliberately offline and creates all mutant inputs below an
explicit disposable work root. It exercises the committed runners using:

- detached and named local Git worktrees for repository policy;
- strict Draft 2020-12 schema validation plus duplicate/BOM/UTF-8 checks;
- the production semantic validator, raw schema-digest binding, and the frozen
  RFC 8785 profile lock for all six baseline/schema pairs;
- locally generated ZIP archives whose frozen digest is injected only into a
  disposable copy of the production acquisition runner;
- tiny real CMake and CTest projects for configuration, inventory, JUnit,
  failure, skip, and timeout behavior;
- deterministic fake OpenTTD executables for exact smoke command enforcement.

The test material injection changes only frozen identity constants in a copied
runner. The production repository and pinned submodule are never modified.
There are no network calls and no skip outcome: missing tools or source material
fail the suite clearly.

Run from any directory:

```sh
./scripts/ci/p001_contract_tests.sh \
  --tools-python /absolute/path/to/hash-locked-p0-venv/bin/python
```

Use `--keep-work` to retain failure artifacts. The harness prints one TAP line
per mandatory ID and exits nonzero after the first failure. The release CTest
registration uses a frozen randomized schedule seed; the top-level gate repeats
that CTest with `--repeat until-fail` to expose order dependence and flakiness.
