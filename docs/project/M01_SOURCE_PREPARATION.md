# M01 OpenTTD 15.3 Source-Preparation Evidence

- Component result: `PASS`
- M01/G01 result: `PASS` (closed by `G01_GATE_REPORT.md`)
- Date: 2026-08-01
- Profile: `openttd-15.3-v1`
- Preparation identity:
  `17a41503ab80f3c01f4ed8e4e24b7a32b1cc0092644c2ae421096a4b4ddb15df`

## Proven source identity

| Field | Accepted value |
|---|---|
| Upstream | `https://github.com/OpenTTD/OpenTTD.git` |
| Release label | `15.3` |
| Commit | `14ec60f248547d4d062a1160f0fc26d742319888` |
| Base tree | `02d8cbbb0d8c030698d37ca76ab2773b6e23c397` |
| Declared C++ standard | C++20, checked in the prepared `CMakeLists.txt` |
| License basis | `GPL-2.0-only`, checked against prepared `COPYING.md` |
| Profile SHA-256 | `563339037626a8bb5a54e2f6a71e69500ccee44c11dfff2ce96bc4a96ef6c6cf` |
| Series SHA-256 | `f982ca6f630c74e240af16d6cb628660a41997cea6ff0c4940839d2ba80b21e2` |
| Patch count | 1 |
| Patch SHA-256 | `0d056466b1abf5df755790f691c99c1db32d3e5f8498fae273abf7d4e4f2ac33` |
| Prepared result tree | `c63a866377547631870efb48ac547948da19916a` |

The profile and both manifest formats are strict Draft 2020-12 JSON schemas. The
preparer has no network mode. It requires the exact commit to exist in the declared
local object repository, exports that commit rather than switching its worktree,
reconstructs and verifies the Git tree, applies only a digest-pinned ordered patch
series, and emits a path-independent preparation identity.

## Accepted portability patch

GCC/G++ 13.3.0 diagnosed OpenTTD 15.3's two-byte `LanguageMap::Mapping` vector
insertion as `-Wstringop-overflow` when OpenTTD's upstream `-fno-strict-overflow`
flag was active. Direct copies, aggregate emplacement, and alternate vector-growth
forms retained the same diagnostic. Because owned builds promote every warning to
an error, the failure was not suppressed.

`0001-gcc13-language-map-emplace.patch` gives `Mapping` an out-of-line constructor
and constructs the already-validated byte pair directly with `emplace_back`. It
does not change the container, value range, validation, or map semantics. The patch
applies exactly with no offset, fuzz, whitespace warning, or unlisted file.

## Repeated-preparation evidence

Each of the four accepted clean OpenTTD builds independently ran the source
preparer. All four emitted byte-identical `prepared-source.json` files with
SHA-256:

```text
319d3fa09424a31b2f33d194cf98191d367716b337af35fe02b6da2e2bd7a260
```

The accepted roots are the headless `k`/`l` and playable `f`/`g` roots recorded in
`M01_OPENTTD_BUILD_REPRODUCIBILITY.md`. Each manifest reports the same base commit,
base tree, one-patch series, result tree, and preparation identity. The historical
P0 object-repository checkout remained at
`29f808ef0022064e6d9a83c8476d1e0f4686af86` with an empty submodule status; no
accepted run checked out V1 in that worktree or registered another Git worktree.

## Fail-closed test evidence

Seven focused tests pass:

- exact base reconstruction and unchanged source repository;
- dirty object-repository rejection;
- series-digest drift rejection;
- unlisted patch rejection;
- base-tree drift rejection;
- exact listed patch application and changed result identity; and
- existing output rejection without overwrite.

The patch application path additionally rejects duplicate/traversing names,
missing files, whitespace errors, offset/fuzz/warning diagnostics, and any source
repository head/status mutation.

## Reproduction

Choose a new absolute artifact path:

```bash
./scripts/v1/prepare_source.sh \
  --artifact-root /absolute/new/artifact/path \
  --tools-python /usr/bin/python3.12
```

The command fails if the artifact root already exists. Generated source and
manifests do not enter Git.

## Boundary

This closes the source-reconstruction portion of `M01`. Its integration into both
reproducible OpenTTD variants is recorded separately in
`M01_OPENTTD_BUILD_REPRODUCIBILITY.md`. No bus, bridge, learning, production ONNX,
or playable-agent requirement becomes `PASS` from this source result. The later
complete gate audit is recorded in `G01_GATE_REPORT.md`.
