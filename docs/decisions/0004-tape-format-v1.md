# ADR 0004: Freeze the OpenTTD RL tape format v1 and instrumentation boundaries

- Status: accepted
- Decision date: 2026-07-30
- Format version: `1.0`
- Source basis: OpenTTD `29f808ef0022064e6d9a83c8476d1e0f4686af86`
- Production implementation: ISO C17 under `parity/`
- Integrity provider: OpenSSL 3 EVP SHA-256
- Field registry: generated PORT-005 APIs `otrl_field_registry_at`,
  `otrl_field_authoritative_count`, and `otrl_field_lookup`

## Context and authority

P0 needs one byte contract that an instrumented pinned OpenTTD can emit, an
independent implementation can decode, and later scalar and CUDA backends can
match field by field. The file must retain exact experiment identity, preserve
native command and tick boundaries, reject corruption without partial state,
and permit a first divergence to be reduced to a valid causal prefix.

The binary tables in the execution contract section 17 are normative. This ADR
fixes the few compatibility choices left open there and incorporates the
instrumentation-boundary rules required by section 15.6. Meaning never changes
within major version 1. A compatible additive optional feature increments the
minor version and requires migration vectors; a required feature or changed
meaning increments the major version.

## Primitive representation

Every integer is an explicitly sized unsigned or two's-complement signed value
encoded little-endian. The codec uses byte loads/stores; it never serializes a C
structure or performs an unaligned typed load. Booleans are `u8` constrained to
zero or one. Enum-like values have a fixed integer width in this document or
the field registry. Pointer, `size_t`, `long`, native enum width, host padding,
float, object representation, address and RTTI data are forbidden.

Records and field entries are padded with zero bytes to the next eight-byte
boundary. Padding contributes to the covered digest. Checked addition,
multiplication and alignment precede every offset or allocation calculation.

Hand-reviewed primitive vectors include:

| Value | Exact bytes |
|---|---|
| `u16 0x1234` | `34 12` |
| `u32 0x12345678` | `78 56 34 12` |
| `u64 0x0123456789abcdef` | `ef cd ab 89 67 45 23 01` |
| `i64 INT64_MIN` | `00 00 00 00 00 00 00 80` |
| SHA-256 of empty input | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| SHA-256 of `abc` | `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad` |

## Exact framing

The 64-byte prefix is exactly the table in section 17.3.1. Its magic is
`4f54524c54415000` (`OTRLTAP\0`), major/minor are `1/0`, byte-order and hash
codes are both `1`, and prefix bytes is `64`. Its declared record byte count
includes record padding and excludes the trailer. The reserved `u64` is zero.

Prefix flags are:

| Bit | Name | Rule |
|---:|---|---|
| 0 | `PARTIAL` | Producer journal only; strict tape validation rejects it and finalization clears it. |
| 1 | `OPTIONAL_DIAGNOSTICS` | The header declares optional diagnostic features and record types 7–10 may occur. |
| 2–15 | optional, unassigned | A v1.0 reader ignores an unknown low optional bit only when all framing remains valid. |
| 16–31 | required-feature space | Any unknown set bit rejects with a version error. |

The canonical header immediately follows with no terminator. Every record has
the exact 40-byte header from section 17.3.3: type `u16`, record version `u16`,
flags `u32`, sequence/step/tick `u64`, payload bytes `u32`, reserved-zero `u32`,
payload, then zero alignment. Required bit zero of record flags is set for all
authoritative classes. Unknown required types reject. An unknown optional type
must have flags zero and can be skipped for comparison while its bytes remain
covered by integrity validation. No other record flag is defined in v1.

The final 64 bytes use magic `4f54524c454e4400` (`OTRLEND\0`), repeat record
count, store covered bytes equal to prefix + header + record region, store the
OpenSSL-EVP SHA-256 of exactly those covered bytes, and end in eight zero bytes.
No byte follows the trailer.

The reviewed small golden has header length 1416, projection payload length 48,
four records, and total length 1784. Its full-file SHA-256 is
`7234523a089593ff7c20a132164e984c8c583e17b32d5b5079b22231a0b6b936`.
Its prefix is:

```text
4f54524c54415000010000000101400088050000000000000400000000000000
f000000000000000000000000000000000000000000000000000000000000000
```

Its trailer is:

```text
4f54524c454e44000400000000000000b806000000000000
b40e93e8e13c890b0a3132e6b431ca1de2cc19ca9b3d62fdc0eb4ee71d6015e6
0000000000000000
```

The test generator is independent of the production writer and freezes the
complete byte count and digest in addition to these readable fragments.

## Canonical header and experiment identity

The header is UTF-8 RFC 8785 canonical JSON in the I-JSON integer subset: no
BOM, whitespace, duplicate keys, floats, negative values, integers above
`2^53-1`, invalid UTF-8, non-shortest escapes or noncanonical key order. Maximum
nesting is 64. The schema is
`parity/schema/tape-header.schema.json`; unknown properties reject.

Top-level members are exactly `backend_label`, `diagnostic_features`, `format`,
`identity`, `initial`, `limits`, and `projection_policy`. `identity` contains
the exact source commit plus build, executable, fixture, settings, content,
command-input, command-schema, field-schema and instrumentation-series
SHA-256 values and an empty NewGRF list. All hashes are lowercase fixed-width
hex. Initial date/timers, both RNG states and boundaries are explicit. The
limits object repeats the fixed public v1 limits. Projection policy is
`complete`.

Backend label and optional diagnostics are nonauthoritative comparison labels.
The comparator checks each named identity component separately and reports the
first identity key that differs. It does not compare arbitrary raw JSON spans
or accidentally include a diagnostic path. Absolute paths and secret-shaped
environment names are forbidden from identity.

## Limits

V1 fixes: 1 MiB header; 64 MiB record payload; 50 million records; 1 TiB tape;
10 million projection fields; 64 MiB one field; 1 MiB diagnostic string;
nesting depth 64; and one million commands. A context may configure lower local
resource limits, but cannot raise a format limit. `validate_file` opens a private
read-only mapping and validates it with bounded scalar state: SHA-256 is updated
in 1 MiB windows and consumed pages are advised away, record payloads are parsed
in place one at a time, and no record or payload array proportional to tape size
is retained. The completed tape owns the mapping and exposes records only through
a forward cursor. Comparator cursors retain one record view per input; the
minimizer streams retained records directly to a same-directory temporary file
while incrementally hashing it. It never constructs a prefix-sized memory
buffer. `validate_bytes` remains the explicit caller-memory convenience API and
copies its decoded result through the context allocator; its configured byte and
record limits therefore bound that caller-selected mode. Length consistency is
checked before any record allocation or traversal.

## Record registry and payload schemas

IDs 1–11 are permanently assigned as in section 17.5. `REPLAY_START`, command
records when scheduled, `AUTHORITATIVE_PROJECTION`, declared
`NAMED_CHECKPOINT`s and `TERMINAL` are required. RNG, route and cargo records
are optional. `TRACE_WARNING` is invalid in a normal flags-zero tape and is
allowed only with `OPTIONAL_DIAGNOSTICS`; such a tape is diagnostic evidence,
not a release golden.

Payloads not already fully specified by section 17.6 are:

- `REPLAY_START`: `u16 payload_version=1`, `u8 boundary_kind`, `u8 zero`,
  `u64 boundary_ordinal` (12 bytes).
- `COMMAND_INTENT`: `u16 version=1`, `u16 zero`, `u32 native_command`, `u32
  company`, `u32 command_flags`, `u32 native_payload_bytes`, `u32 zero`, then
  the exact normalized native payload (24 + N bytes).
- `COMMAND_TEST_RESULT` and `COMMAND_EXEC_RESULT`: `u16 version=1`, `u8
  success`, `u8 zero`, `u32 native_command`, `i64 cost`, `u32 expense_type`,
  `u32 error_string_id`, `u32 extra_error_string_id`, `u32 result_data_bytes`,
  then normalized result tuple data (32 + N bytes).
- `NAMED_CHECKPOINT`: `u16 version=1`, nonzero stable `u16 checkpoint_id`,
  `u32 zero` (8 bytes).
- `TERMINAL`: `u16 version=1`, `u16 terminal_reason`, `u32 zero` (8 bytes).

The record header already owns sequence, public step and native tick, so payloads
do not duplicate them. Command phases are intent, test, execute, projection for
an accepted command. A rejected test (`success=0`) is intent, test, projection
with no execute. A successful test without execute and an execute after a
rejected test both reject.

## Projection encoding and schema governance

Projection payloads use the exact 24-byte header and 16-byte field headers in
section 17.6. Version is one, reserved is zero, field count is nonzero,
boundary kind and ordinal are explicit, and the optional digest prefix is zero
when unused. Fields are strictly increasing, nonzero stable IDs.

The generated PORT-005 C registry is part of production validation. Each field
must resolve and agree on value type, width, scalar/fixed count or dynamic
maximum capacity, bitset shape and diagnostic classification. Stable-ID width
is the only permitted field flag and is exactly 1, 2, 4 or 8; all other values
use flags zero. Bitset unused high bits and all entry padding are zero.
Diagnostic UTF-8 strings require a diagnostic registry entry. Authoritative
strings are forbidden.

At every boundary declared complete, the producer emits every
`authoritative_full` field exactly once, including empty dynamic arrays and pool
allocation state. Map values are in `TileIndex` order. Raw structures, caches
classified derived, stateful/lazy getters and unordered iteration are forbidden.

## Instrumentation isolation and boundaries

Instrumentation exists only as an ordered patch series applied to a disposable
worktree. `OPTION_P0_ORACLE_TRACE=OFF` excludes adapter sources and their
OpenSSL dependency. An ON binary remains runtime-disabled unless command input,
canonical header and exclusive partial output are all supplied. Partial option
sets fail before fixture load.

Preflight reads and validates both complete input files before exposing a
command to gameplay. Command artifact `file_sha256` covers the entire command
file and becomes header identity; its separate covered checksum excludes only
the command trailer. No permissive fallback exists.

Each action is posted once through native `Command<...>::Post` under explicit
company context. Hooks copy the already-produced test and execute results; they
do not call the command procedure twice, draw RNG, request a path, mutate a
pool, or evaluate a lazy cache. Initial projection follows replay start.
Same-tick commands execute in public-step order before tick advancement. Every
completed tick has a post-tick projection. Checkpoints are source-reviewed state
detectors, not elapsed-time guesses. V1 assigns exactly: 1 `route_completion`,
2 `first_production`, 3 `first_station_capture`, 4 `first_loading`, 5
`first_unloading`, 6 `first_accepted_delivery`, 7 `first_payment`, and 8
`continuation_end`. No other checkpoint ID is valid in a P0 tape.

## Partial producer and transactional finalizer

The C++ adapter owns only an exact `PARTIAL` journal: prefix, canonical header,
complete contiguous records, zero padding and no trailer. Advisory counters may
be zero or updated in place. It fsyncs the journal and parent directory.

The C17 tool is the sole final authority:

```text
tape finalize INPUT.partial OUTPUT.tape
```

It rejects bad prefix identity/flags/reserved fields, a raw sequence mismatch,
truncation, padding, malformed payload or lifecycle before output. It then
recomputes counts and maxima, clears partial, writes the trailer, validates the
new bytes through the independent production parse path, fsyncs and promotes by
no-overwrite atomic link. Failure never exposes a final file; an existing
destination remains unchanged.

## Parser API and transaction semantics

Public structs begin with `uint32_t size` and `uint32_t version`; reserved fields
must be zero. Parser objects are opaque and context-owned. `validate_bytes`
copies header and record payloads; `validate_file` owns an immutable private file
mapping until tape destruction. Neither mode borrows mutable caller storage. On
any failure, partial allocations/mappings are released and the caller-owned
output pointer/result is unchanged. Error location carries byte
offset, sequence, step, tick, field ID and a bounded message. No global mutable
parser or process-global error buffer exists, so independent contexts are safe
to use concurrently.

Stable library status values are exactly `OTRL_OK=0` through
`OTRL_E_INTERNAL=19` in `openttd_rl_parity/status.h`. CLI mapping is 0 success/equal, 1 valid
divergence, 2 identity mismatch, 3 malformed/corrupt, 4 I/O/local resource, 5
internal invariant and 64 usage. Printing an error never changes failure to
zero.

## Comparison and minimization

Both tapes validate independently before comparison. Format and every named
identity component precede semantic comparison. Optional diagnostic records
are skipped only after their bytes and declaration validate. The comparator
tracks separate physical indices for oracle and target; encoded sequence is not
used as a target vector index after ignored diagnostics.

At the first mismatch it stops and returns tape digests, full identity context,
backend labels, environment zero, step/tick, boundary kind/ordinal, both record
indices/type, field ID/path/type/width/signedness/element, exact decimal and
fixed-byte hex values, prior command phases/checkpoint, source anchor, cache
class and reproducible CLI arguments. Untrusted text is JSON escaped. Later
differences never overwrite the root cause.

The minimizer writes a minimized **target** tape and always compares the
unchanged oracle with that result. It retains every record through the earliest
closed boundary that contains the divergence, adds the original terminal when
needed, rewrites counts/maxima/sequence/trailer, validates, and verifies the
complete divergence signature including values. Command intent/test/execute
records remain causal predecessors of their projection. Closed-boundary search
uses binary search when the predicate is proven monotone and a separately
tested linear fallback when a synthetic predicate violates monotonicity. Output
uses the same no-overwrite transaction as finalization.

## Human inspection and security model

`inspect`, `dump` and comparator text are nonauthoritative. Filters are bounded;
unknown IDs and reversed tick ranges are explicit errors. Integers are printed
without locale formatting and binary values use fixed byte hex. Control bytes
are escaped. No implicit display truncation exists.

The threat model is an arbitrary untrusted byte string up to configured local
limits. Validation authenticates integrity, not authorship. SHA-256 detects
corruption but provides no signature. The implementation prevents integer
overflow, input-derived unbounded allocation, recursive-depth abuse, partial
result publication, output overwrite and path content in identity. It does not
open network connections or load Python/CUDA at runtime.

## Verification and consequences

The C library and CLI compile under GCC 13 and Clang 16 with warnings as errors;
C and C++ ABI callers are compiled. A standard-library-only Python decoder
independently checks all framing. Tests cover exact vectors, every-byte
truncation, malformed header/record/projection/trailer cases, identity and first
field faults, accepted and rejected command grammar, diagnostics, minimization,
transactional output and stable exits. Separate ASan/UBSan, coverage, libFuzzer
and deterministic mutation campaigns are release gates.

Plain, patched-OFF, patched-ON/runtime-disabled and patched-ON/enabled OpenTTD
runs use isolated roots. Plain/OFF/disabled authoritative outcomes must match;
enabled adds only a valid tape. Two serial and twenty repeated enabled tapes
must be byte-identical, parallel runs must not interfere, and upstream's exact
99-test inventory passes in all compiled profiles. A schema, source boundary or
payload change therefore requires an explicit version/registry decision rather
than a compatibility guess.
