# P0 Evidence Policy

This directory contains small, reviewed, credential-safe evidence summaries and
machine-readable result/provenance documents that are useful in source control.
Large or raw generated evidence is written under a caller-supplied artifact root
outside tracked source directories.

Tracked summaries must link to raw-artifact relative paths and SHA-256 digests.
They must not contain secrets, host authentication material, full process
environments, private paths, or unbounded logs. Raw artifacts are retained for the
required validation interval and are included in the final digest inventory when
their size and license permit distribution.

No evidence document may turn a failed or skipped mandatory gate into `PASS`.
