# Tape-v1 golden vectors

`minimal-valid.tape` is the complete 64,528-byte hand-reviewed v1 vector used by
the C17 validator/writer tests and the independent Python decoder. Its SHA-256
is `300e9e37659a88714ca19efeccf3d2870c27845abf81c2de6f5a91bbc04dd72f`.
`minimal-valid.hex` is the same byte sequence as one lowercase hexadecimal line;
tests require exact bidirectional equality rather than trusting either file.

The vector contains a canonical header, `REPLAY_START`, one complete projection
containing all 645 `authoritative_full` fields in frozen registry order,
checkpoint ID 1, `TERMINAL`, and a valid covered-byte SHA-256 trailer. The
fixture values are the registry's structural samples (with gameplay RNG field
1030 set to 42); this is a codec vector, not authoritative OpenTTD run evidence.

Malformed regression files remain small and focused. They belong in
`malformed/` only after a fuzzer or regression reveals a case not expressible as
an in-memory mutation of this vector.
