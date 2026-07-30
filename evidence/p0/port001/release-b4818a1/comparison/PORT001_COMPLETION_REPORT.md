# PORT-001 completion report

- Status: **PASS**
- Source commit: `b4818a12a1d37492fc43f8e8a9b87091ca5d60e8` (verified pushed to `port/p0-oracle-contract`)
- OpenTTD submodule: `29f808ef0022064e6d9a83c8476d1e0f4686af86` (clean)
- Clean reference roots: 2
- Upstream tests: 99/99 passed in each root, with no skip or timeout
- Headless smoke: exact 128-tick null-backend command passed in each root
- Required reconstruction equalities: 7/7
- Executable claim: behaviorally reproduced under the frozen profile
- Binary analysis: Raw executables differ. Build IDs and debug data reflect distinct generated roots; after stripping debug data and the GNU build-id note and replacing equal-length run-root strings, the remaining bytes are identical.

The raw executable digests, stage manifests, inventories, JUnit files, logs, readelf output,
and canonical comparison evidence remain below the external artifact root. This report does
not claim byte reproducibility unless the comparison record classifies the raw bytes as equal.
