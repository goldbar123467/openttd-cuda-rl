# PORT-004 fuzz targets

`fuzz_entry.c` is compiled ten times with a fixed `FUZZ_MODE` to keep all byte
entry points under one audited resource policy. Modes `0..4` exercise prefix,
header, record, projection, and full-tape parsing through the complete strict
validator; mode 5 exercises bounded command-input framing; modes 6 and 7
exercise field-schema/manifest-shaped canonical JSON; and modes 8 and 9 split
arbitrary input into independently validated comparator/minimizer pairs.

The campaign script uses Clang 16 libFuzzer with ASan and UBSan. It records exact
execution counts rather than substituting a wall-clock duration. The tracked
seed corpus is hexadecimal so Git review cannot normalize arbitrary binary
bytes; the runner materializes it under its generated build root.
