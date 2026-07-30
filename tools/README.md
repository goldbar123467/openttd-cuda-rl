# P0 Tool Environment

`requirements-p0.txt` is generated from `requirements-p0.in` with hashes and must
be installed with hash enforcement into an environment outside the repository.
The supported local profile uses Python 3.12.

```bash
uv pip compile --generate-hashes --python-version 3.12 \
  --output-file tools/requirements-p0.txt tools/requirements-p0.in
uv venv /workspace/openttd-p0-tools-venv --python /usr/bin/python3.12
uv pip install --python /workspace/openttd-p0-tools-venv/bin/python \
  --require-hashes --requirements tools/requirements-p0.txt
```

The environment validates Draft 2020-12 schemas and provides an independent RFC
8785 reference. It is not permitted to parse, write, compare, minimize, or finalize
production tape files. Those correctness-critical implementations remain ISO C17.

Validate a frozen PORT-001 manifest against both its schema and the canonical
profile lock with:

```bash
/workspace/openttd-p0-tools-venv/bin/python tools/validate_manifest.py \
  --schema oracle/manifests/schema/source.schema.json \
  --profile-lock oracle/manifests/baseline/P0_PROFILE_LOCK.json \
  oracle/manifests/baseline/openttd-source.json
```

After committing and pushing a clean `port/p0-oracle-contract` branch, the full
PORT-001 closure command is:

```bash
./oracle/runner/port001_gate.sh \
  --profile local-release \
  --artifact-root /workspace/openttd-p0-artifacts/port001-release \
  --tools-python /workspace/openttd-p0-tools-venv/bin/python
```

That command runs the adversarial harness repeatedly, constructs two fresh
references, compares all seven mandatory identities, inspects any binary byte
difference, and emits canonical evidence and a schema-valid gate result. It
fails if the worktree is dirty or the local commit is not exactly pushed.

Regenerate the lock only through a reviewed dependency-change commit, re-run the
schema/canonicalization differential tests, and update dependency provenance.
