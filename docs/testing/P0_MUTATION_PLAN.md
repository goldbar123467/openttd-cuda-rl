# P0 Mutation and Fault-Detection Plan

## Goal and interpretation

Mutation testing asks whether the P0 tests detect realistic defects in the
oracle contract. It does not measure code quality by raw mutant count. A mutant
is useful only when it represents a behavior the contract requires and has one
unambiguous expected detection point.

The release campaign mutates disposable copies or compile-time test variants.
It never edits the pinned submodule, fixture, command input, registry, or golden
tape in place. Mutation outputs are nonauthoritative and remain below the
declared artifact root.

A mutant is `KILLED` only when its named test observes the expected failure
family and earliest boundary. Compiler failure, timeout, crash, or unrelated
test failure does not count unless that is the intended policy being tested. A
surviving mandatory mutant fails P0.

## Required mutation record

Each campaign entry records:

- stable mutant ID and versioned operator;
- requirement and production file/function governed;
- immutable input digest and disposable mutated-output digest;
- exact mutation location and old/new logical value;
- expected test ID, failure family, and earliest byte/boundary;
- exact argv and allowlisted environment;
- observed result and evidence paths;
- disposition: `KILLED`, `SURVIVED`, or `EQUIVALENT_REVIEWED`;
- reviewer rationale for an equivalent mutant.

Equivalent-mutant review requires pinned-source proof that no accepted input can
observe the change. It cannot be justified by “tests still pass.” Target
equivalent-mutant waivers at release is zero.

## Operator families

### Checked arithmetic and framing

| Family | Representative mutation | Required detection |
|---|---|---|
| `MUT-ARITH-ADD` | remove or invert checked addition overflow | overflow/extent negative test rejects before allocation/read |
| `MUT-ARITH-MUL` | remove or invert checked multiplication overflow | field/record size test rejects before allocation |
| `MUT-LIMIT-EQ` | change `>` to `>=` or the reverse at a size limit | exact-limit and limit-plus-one cases distinguish behavior |
| `MUT-PAD-ZERO` | accept nonzero alignment padding | prefix/record padding negative vector rejects at exact offset |
| `MUT-RESERVED` | ignore one reserved flag/word | reserved-field test rejects the targeted region |
| `MUT-TRAILING` | accept bytes after terminal/trailer | strict trailing-byte test rejects |

Boundary tests include zero, one, maximum, maximum plus one, and arithmetic
wraparound operands for every externally supplied length/count.

### Endian and primitive encoding

| Family | Representative mutation | Required detection |
|---|---|---|
| `MUT-ENDIAN-16` | decode a 16-bit word as big endian | hand-reviewed golden vector differs at first primitive |
| `MUT-ENDIAN-32` | byte-swap a 32-bit value | Python/C differential and logical dump fail |
| `MUT-ENDIAN-64` | truncate or byte-swap a 64-bit value | large counter/money vector fails |
| `MUT-SIGN` | decode signed money/date as unsigned | negative-value golden vector and comparator report fail |
| `MUT-WIDTH` | serialize host `size_t` or enum width | ABI/portable vector rejects byte length/type |
| `MUT-BIT-ORDER` | reverse bit order within an occupancy byte/word | fragmented-pool identity/next-allocation test fails |

### Canonical JSON and identity

| Family | Representative mutation | Required detection |
|---|---|---|
| `MUT-JSON-DUP` | accept duplicate object key | independent loader rejects |
| `MUT-JSON-ORDER` | accept noncanonical key/member order | canonical-header test rejects |
| `MUT-JSON-TYPE` | coerce string/bool/null to integer or label | typed schema/semantic test rejects |
| `MUT-JSON-EXTRA` | ignore an unknown property | closed-object schema test rejects |
| `MUT-HASH-REGION` | hash only covered command bytes instead of full file | full-file command identity test fails |
| `MUT-IDENTITY-SKIP` | omit one source/build/fixture/schema digest comparison | targeted identity-mismatch test reaches pre-gameplay failure |
| `MUT-HASH-COMPARE` | compare a digest prefix rather than all 32 bytes | late-byte digest mutation rejects |

### Reader, writer, and atomic output

| Family | Representative mutation | Required detection |
|---|---|---|
| `MUT-IO-EINTR` | fail to retry an interruptible read/write | deterministic injected EINTR completes or fails by contract |
| `MUT-IO-SHORT` | treat a short read/write as complete | short-I/O fault retains partial output and returns nonzero |
| `MUT-IO-FSYNC` | omit file or parent-directory `fsync` | wrapped syscall trace/order test fails |
| `MUT-IO-RENAME` | publish before trailer/digest verification | rename-failure test finds no authoritative output |
| `MUT-IO-OVERWRITE` | replace unequal existing output | exclusive/unequal-output test preserves original bytes |
| `MUT-IO-PERM` | ignore output-open/permission failure | CLI returns nonzero without partial stdout success claim |
| `MUT-IO-WHOLEFILE` | replace streaming path with full-file allocation | sparse-large-input RSS gate fails |

### Tape records and projections

| Family | Representative mutation | Required detection |
|---|---|---|
| `MUT-SEQ` | allow duplicate/decreasing sequence | record monotonicity test rejects earliest record |
| `MUT-BOUNDARY` | allow decreasing step/tick/ordinal | boundary test rejects earliest record |
| `MUT-REQUIRED` | skip unknown required record | unknown-required test rejects; optional record test still accepts |
| `MUT-TERMINAL` | accept missing/duplicate/nonfinal terminal | terminal tests reject |
| `MUT-COUNTERS` | fail to verify trailer counters/maxima | counter mutation rejects |
| `MUT-FIELD-ORDER` | sort incorrectly or allow duplicate field ID | projection test rejects exact entry |
| `MUT-FIELD-OMIT` | do not require one authoritative field family | omission test rejects copied projection |
| `MUT-FIELD-COUNT` | ignore schema element count | count/offset mutation rejects |
| `MUT-FIELD-TYPE` | ignore value-type mismatch | wrong-type mutation rejects |
| `MUT-MAP-COUNT` | accept 4,095 map elements | fixed 4,096-plane test rejects |

### Comparator and minimizer

| Family | Representative mutation | Required detection |
|---|---|---|
| `MUT-CMP-LATE` | report a later mismatch instead of earliest | multi-fault vector expects first boundary/field |
| `MUT-CMP-DIAG` | compare optional diagnostics as authority | diagnostics off/on authoritative-equality test fails |
| `MUT-CMP-IGNORE` | ignore a required field/type/count/value | targeted injected divergence must report it |
| `MUT-CMP-CTX` | drop last command or prior checkpoint | report-schema/completeness test rejects |
| `MUT-CMP-IDENT` | compare mismatched identities as state | identity mismatch must stop before state comparison |
| `MUT-MIN-SIG` | preserve only field ID, not full signature | two-divergence minimization test selects wrong prefix and fails |
| `MUT-MIN-PHYSICAL` | confuse logical diagnostic-filtered and physical index | optional-record prefix test fails validation/signature |
| `MUT-MIN-TRUNC` | emit raw truncation without final trailer | independent validator rejects minimized output |
| `MUT-MIN-COPY` | copy entire theoretical tape into memory | sparse-large-input RSS gate fails |

### Command instrumentation

| Family | Representative mutation | Required detection |
|---|---|---|
| `MUT-CMD-DIRECT` | bypass native command dispatcher | native test/execute phase records are absent and gate fails |
| `MUT-CMD-TEST` | omit test result | command phase-count test fails at action |
| `MUT-CMD-EXEC` | omit execute result for accepted command | phase closure fails |
| `MUT-CMD-REJECT` | abort rather than record native rejection | rejected-prefix campaign fails structural/result contract |
| `MUT-CMD-COMPANY` | execute under wrong company context | ownership/cost/result negative test diverges |
| `MUT-CMD-RESULT` | hard-code returned vehicle/station ID | perturbed legal prefix and typed-result test fail |
| `MUT-CMD-INACTIVE` | serialize result while no trace is active | zero inactive-capture counter test fails |
| `MUT-CMD-SCHEDULE` | run action one tick early/late | intent/native boundary schedule test fails |

### Projection and continuation state

| Family | Representative mutation | Required detection |
|---|---|---|
| `MUT-PROJ-GETTER` | invoke a cache-filling getter while projecting | trace off/on non-perturbation or cache-byte test fails |
| `MUT-PROJ-POOL` | recompute compressed occupancy and drop native bitmap word shape | fragmentation/next-ID continuation test fails |
| `MUT-PROJ-OWNER` | flatten nested values without owner offsets | empty-owner partition test fails |
| `MUT-PROJ-PACKET` | sort cargo packets instead of native list order | packet-order/conservation continuation test fails |
| `MUT-PROJ-TIMER` | omit or increment a timer/cursor incorrectly | earliest post-tick timer test fails |
| `MUT-PROJ-RNG` | swap/omit one RNG word | initial/tick projection and repeat determinism fail |
| `MUT-PROJ-CACHE` | classify a reached cache diagnostic | registry policy and continuation mutation fail |
| `MUT-PROJ-HORIZON` | stop before/after exact final boundary | record/max/checkpoint count test fails |
| `MUT-PROJ-MILESTONE` | conflate unload, delivery, or payment | named checkpoint predicates fail against ledger/cargo state |

### Economic and cargo invariants

| Family | Representative mutation | Required detection |
|---|---|---|
| `MUT-MONEY-UNIT` | change one cost/income unit | categorized ledger invariant fails at earliest boundary |
| `MUT-MONEY-DUP` | debit purchase or credit delivery twice | one-occurrence invariant fails |
| `MUT-CARGO-LOSS` | remove one cargo unit | conservation invariant fails |
| `MUT-CARGO-DUP` | reference one packet in two containers | ownership uniqueness fails |
| `MUT-CARGO-ORDER` | swap packet chain elements | exact packet-order comparison fails |
| `MUT-CARGO-PROV` | alter source station/tile/date | provenance comparison fails |
| `MUT-CARGO-SPLIT` | make split totals differ by one | split/merge invariant fails |
| `MUT-PAYMENT-INPUT` | use wrong distance/date/amount | delivery/payment checkpoint and ledger fail |

## Campaign execution

1. Verify immutable baseline digests and a clean pinned submodule.
2. Build/run the unmutated profile and require every owning test to pass.
3. Materialize one mutant in an isolated directory or select one explicit
   standalone fault ID.
4. Record the exact mutation and resulting digest.
5. Run only the owning focused test first; retain its raw result.
6. Require the expected failure family and earliest location.
7. Run the surrounding suite to detect unintended common-mode effects.
8. Remove the disposable mutant directory without touching retained evidence.
9. Reverify baseline digests and submodule cleanliness.
10. Emit the canonical campaign summary and verify every mandatory operator has
    a disposition.

Independent data mutations are preferred for parsers, schemas, comparators, and
invariants because they are deterministic and inexpensive. Compile-time source
mutants are reserved for control-flow, I/O, inactive-trace, and streaming-memory
properties that data faults cannot exercise.

## Release gate

The mutation gate reports `PASS` only when:

- the unmutated baseline passes;
- every mandatory mutant is generated and exercised exactly as declared;
- every non-equivalent mandatory mutant is killed by its owning test with the
  expected failure family;
- there are no unexplained compiler failures, crashes, timeouts, or survivors;
- no threshold, assertion, timeout, sanitizer, or corpus size was weakened;
- raw per-mutant evidence and the canonical summary both verify by SHA-256;
- source, fixture, command input, and pinned submodule still match their
  pre-campaign identities.

Any survivor remains a release failure and enters the defect ledger with its
reproduction command. It is not converted to an equivalent mutant merely to
make the score green.
