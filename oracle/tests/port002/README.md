# PORT-002A fixture-contract tests

`port002_contract_tests.py` runs the 20 mandatory `P002-FIX-*`, 10 mandatory
`P002-SET-*`, and the two pre-PORT003 identity cases `P002-LOD-003` and
`P002-LOD-004` as deterministic positive/mutation tests. The schedule is
shuffled by a reported seed; the 32-ID inventory is checked exactly after every
run.

The tests prove the pre-PORT003 contract machinery: strict JSON/schema shape,
64×64 bounds, empty NewGRF/AI state, exact company/industry/cargo/engine data,
catchment and route geometry, forbidden branches, ten-command ordering,
funding arithmetic, personal-data rejection, canonical settings export,
behavior identity, and override/environment behavior.

They use a clearly synthetic byte file only to exercise final-manifest size and
SHA validation. That file is created under the disposable test work root and is
never an OpenTTD fixture or gate artifact. Passing the synthetic positive cases
is not evidence that the committed `fixture.sav` loads; the separate
`P002-LOD-003` case uses the committed bytes only to prove digest preflight.

Run the wrapper with the hash-locked tools environment:

```sh
scripts/ci/p002_fixture_contract_tests.sh \
  --tools-python /workspace/openttd-p0-tools-venv/bin/python \
  --schedule-seed 2002
```

The save-bit mutation case proves digest rejection before replay, and the wrong
content case proves profile identity rejection. The remaining mandatory
load/reachability cases (`P002-LOD-001`, `002`, `005`–`014`) remain blocked on
native loading/replay and PORT003 instrumentation. The contract validator
cannot prove two-load timer/RNG equality, command execute costs, returned
native IDs, movement/cargo milestones, exact payment, or undeclared filesystem
reads. None of those twelve cases is reported as `SKIP` or `PASS`; they remain
open gate requirements.
