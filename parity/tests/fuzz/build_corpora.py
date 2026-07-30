#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build isolated, reproducible seed sets for every PORT-004 parser target."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path


TARGETS = (
    "fuzz_tape_prefix", "fuzz_tape_header", "fuzz_tape_records",
    "fuzz_projection_payload", "fuzz_full_tape", "fuzz_command_input",
    "fuzz_field_schema_json", "fuzz_manifest_json", "fuzz_comparator_pair",
    "fuzz_minimizer_pair",
)


def canonical_json(path: Path) -> bytes:
    return json.dumps(json.loads(path.read_text()), sort_keys=True,
                      separators=(",", ":")).encode()


def write_seed(directory: Path, name: str, payload: bytes) -> None:
    digest = hashlib.sha256(payload).hexdigest()[:16]
    (directory / f"{name}-{digest}").write_bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    output = args.output.resolve()
    sys.path.insert(0, str(root / "parity/tests/golden"))
    from golden import header, projection, record, tape  # noqa: PLC0415

    directories = {target: output / target for target in TARGETS}
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=False)

    valid_tape = tape()
    divergent_tape = tape([
        record(1, 0, 0, 0), record(5, 1, 0, 0, projection(43)),
        record(6, 2, 0, 0), record(11, 3, 0, 0),
    ])
    for target in ("fuzz_tape_prefix", "fuzz_tape_records", "fuzz_full_tape"):
        write_seed(directories[target], "valid-tape", valid_tape)
        write_seed(directories[target], "invalid-truncated", valid_tape[:31])
    write_seed(directories["fuzz_tape_header"], "valid-header", header())
    write_seed(directories["fuzz_tape_header"], "invalid-header", b'{"a":1,"a":2}')
    write_seed(directories["fuzz_projection_payload"], "valid-projection", projection())
    write_seed(directories["fuzz_projection_payload"], "invalid-projection", b"\x01")
    write_seed(directories["fuzz_command_input"], "valid-command", struct.pack("<II", 22, 0))
    write_seed(directories["fuzz_command_input"], "invalid-command", struct.pack("<II", 22, 9))
    fields = canonical_json(root / "parity/schema/fields-v1.json")
    manifest = canonical_json(root / "oracle/fixtures/road_freight_v1/fixture.manifest.json")
    write_seed(directories["fuzz_field_schema_json"], "valid-fields", fields)
    write_seed(directories["fuzz_field_schema_json"], "invalid-key-order", b'{"b":0,"a":0}')
    write_seed(directories["fuzz_manifest_json"], "valid-manifest", manifest)
    write_seed(directories["fuzz_manifest_json"], "invalid-json", b"{")
    equal_pair = struct.pack("<I", len(valid_tape)) + valid_tape + valid_tape
    divergent_pair = struct.pack("<I", len(valid_tape)) + valid_tape + divergent_tape
    for target in ("fuzz_comparator_pair", "fuzz_minimizer_pair"):
        write_seed(directories[target], "valid-equal-pair", equal_pair)
        write_seed(directories[target], "valid-divergent-pair", divergent_pair)
        write_seed(directories[target], "invalid-pair", b"\xff\xff\xff\xff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
