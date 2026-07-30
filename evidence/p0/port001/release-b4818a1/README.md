# PORT-001 compact release evidence

This directory is the Git-safe, compact copy of the authoritative PORT-001
artifact root produced at outer commit
`b4818a12a1d37492fc43f8e8a9b87091ca5d60e8`. The machine-readable gate reports
`PASS`, both clean roots ran 99/99 upstream tests and the exact 128-tick smoke,
and every file named by `comparison/port001-raw-artifact-index.json` is retained
here with its original bytes.

Generated build/install products are deliberately not tracked. This is required
by the repository policy that build products must not enter Git. Exactly two
evidence-statement artifact paths are therefore external to this compact copy:

| Artifact role | Size | SHA-256 |
|---|---:|---|
| `run-a/install/games/openttd` | 404,942,392 | `ae73552b5829d7f569aec301ac4f30a9b4cc81ba1ab1208f9372da3b853b738f` |
| `run-b/install/games/openttd` | 404,943,600 | `378c4aa5c82c7d961000317bb36eac5e9c4c28495b3ccdafe4b84704bcaae842` |

The two binary-inspection working copies are also omitted build products. They
are each 19,572,800 bytes. Their SHA-256 digests are
`bb160fcc90041bf8e83407626cbf863b02d124682b534ef77a48d8053ebac49c`
and `ba6e4233841799b3376d59e6bda24fe6aaddff5e32af480afdb74e9f531884a6`.
Their measurements, build IDs, readelf outputs, normalization counts, and
normalized digest are retained in `comparison/port001-reference-comparison.json`.

The full generated root on the authoring instance was:

```text
/workspace/openttd-p0-artifacts/port001-release-b4818a1
```

It is reproducible from a clean checkout of the recorded commit with:

```sh
./oracle/runner/port001_gate.sh \
  --profile local-release \
  --artifact-root /workspace/openttd-p0-artifacts/port001-release-b4818a1 \
  --tools-python /workspace/openttd-p0-tools-venv/bin/python \
  --parallel 16
```

The command requires an absent or empty artifact root. The committed commands,
logs, stage results, manifests, exact inventories, JUnit files, schemas, profile,
readelf output, comparison, raw index, evidence statement, and gate result are
otherwise complete. The raw index intentionally excludes the live comparator
stdout/stderr and gate wrapper log/result because those files are finalized only
after the immutable pre-decision index is emitted; that exclusion is explicit in
the index and covered by a regression test.
