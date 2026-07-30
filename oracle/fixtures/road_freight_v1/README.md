# `road_freight_v1` fixture contract

This directory contains the PORT002A-frozen contract and deterministic save
bytes from two independent pinned-worktree runs of the disposable native
builder. PORT002A is frozen; PORT002B and the overall PORT002 gate remain open.

Committed artifacts:

- `settings.normalized.json` is canonical JSON for the exact first-fixture
  setting inventory. Its document SHA-256 is
  `900e841dfa042109a151261cf5cbbd0b1a1d28750c18120877df6eac017f626b`;
  its behavior-only identity is
  `2eb84e267e88936b19f9cfa5369396a3ef2b4b8f1f0912df3bc5422b6f211c5d`.
- `fixture.manifest.json` is the strict PORT002A manifest. It binds the source,
  builder executable, map planes, objects, coordinates, content, normalized
  settings, save bytes, and ten-command plan while retaining explicit PORT002B
  blockers.
- `fixture.sav` is exactly 10008 bytes with SHA-256
  `74c9be53902598061e1e82835c394a37b77bfc71c818de1df8456cdfc2804d20`.
  Two final settings-aligned native builder runs produced byte-identical output.
- The creation executable is 405127064 bytes with SHA-256
  `a0f3536b011fcb1af21341c4893c5efefb1b12db1fc0bfb5678edfbfdbc2c3e7`.
- The canonical 4096×12-byte map-plane stream is 49152 bytes with SHA-256
  `5a933bc43d59c05b0d8fda519aec0aafa71b16d50a03aea83aefade7a57c9dd6`;
  both runs matched.

Absent by design at this revision:

- measured command costs and funding proof;
- loaded timers and RNG words;
- native pickup, delivery, acceptance, and payment boundaries.
- isolated-home undeclared-read evidence.

Validate the PORT002A artifact in authoritative mode:

```sh
/workspace/openttd-p0-tools-venv/bin/python \
  oracle/tests/port002/port002_contract.py \
  --schema oracle/manifests/schema/fixture.schema.json \
  --manifest oracle/fixtures/road_freight_v1/fixture.manifest.json
```

PORT002B remains open until PORT003 proves two independent loads, exact native
command costs, native milestone replay equality, and isolated-home behavior.
Only then may the pending boundary/funding/milestone records become verified,
the blockers become an empty array, and the status advance to `PORT002B_PASS`.

No personal strings, user paths, downloaded NewGRFs, AI/GameScript content, or
post-freeze scenario/editor mutation are permitted.
