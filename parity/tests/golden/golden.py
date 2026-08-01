# SPDX-License-Identifier: GPL-2.0-only
"""Hand-auditable independent tape-v1 vectors used only by tests."""

from __future__ import annotations

import hashlib
import json
import struct
import argparse
from pathlib import Path
from typing import Iterable


REGISTRY = json.loads(
    (Path(__file__).resolve().parents[2] / "schema/fields-v1.json").read_text()
)
FIELD_SCHEMA_SHA256 = "7622144440833e574435ea3633e8692504d8f69cdf27fe54c4b0c39c51684438"


def header(backend: str = "oracle", fixture: str = "6" * 64) -> bytes:
    value = {
        "backend_label": backend,
        "diagnostic_features": [],
        "format": {"major": 1, "minor": 0},
        "identity": {
            "build_sha256": "0" * 64,
            "command_input_sha256": "1" * 64,
            "command_schema_sha256": "2" * 64,
            "content_sha256": "3" * 64,
            "executable_sha256": "4" * 64,
            "field_schema_sha256": FIELD_SCHEMA_SHA256,
            "fixture_sha256": fixture,
            "instrumentation_sha256": "7" * 64,
            "newgrfs": [],
            "settings_sha256": "8" * 64,
            "source_commit": "9" * 40,
        },
        "initial": {
            "calendar_date": 712223,
            "calendar_fraction": 0,
            "economy_date": 712223,
            "economy_fraction": 0,
            "gameplay_rng_state": "5b9692207657b27e",
            "interactive_rng_state": "4952463149524631",
            "native_tick": 0,
            "public_step": 0,
            "timers": {"calendar_subtick": 0},
        },
        "limits": {
            "command_count": 1_000_000,
            "field_bytes": 67_108_864,
            "field_count": 10_000_000,
            "header_bytes": 1_048_576,
            "record_count": 50_000_000,
            "record_payload_bytes": 67_108_864,
            "tape_bytes": 1_099_511_627_776,
        },
        "projection_policy": "complete",
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def projection(value: int = 42, field_id: int = 1030,
               overrides: dict[int, int] | None = None) -> bytes:
    replacements = dict(overrides or {})
    replacements.setdefault(field_id, value)
    scalar_values: dict[str, int] = {}
    for field in REGISTRY["fields"]:
        if field["classification"] != "authoritative_full" or field["shape"] != "scalar":
            continue
        sample = field["sample_logical_value"]
        scalar_values[field["path"]] = int(sample[0] if isinstance(sample, list) else sample)
        if field["field_id"] in replacements:
            scalar_values[field["path"]] = replacements[field["field_id"]]
    entries: list[tuple[dict[str, object], int, bytes]] = []
    for field in REGISTRY["fields"]:
        if field["classification"] != "authoritative_full":
            continue
        if field["shape"] == "scalar":
            count = 1
            logical = scalar_values[field["path"]]
            width = int(field["width_bits"]) // 8
            raw = logical.to_bytes(width, "little", signed=field["signedness"] == "signed")
        elif field["shape"] == "fixed_array":
            count = int(field["fixed_count"])
            raw = bytes.fromhex(str(field["sample_encoded_hex"])) * count
        elif field["shape"] == "dynamic_array":
            count = scalar_values[str(field["count_source_field"])]
            raw = bytes.fromhex(str(field["sample_encoded_hex"])) * count
        else:
            count = scalar_values[str(field["count_source_field"])]
            raw = bytes((count + 7) // 8)
        entries.append((field, count, raw))
    payload = bytearray(struct.pack("<HBBIQQ", 1, 1, 0, len(entries), 0, 0))
    for field, count, raw in entries:
        flags = (int(field["width_bits"]) // 8
                 if field["value_type"] == "stable_id" else 0)
        payload.extend(struct.pack("<IHHII", int(field["field_id"]),
                                   int(field["tape_value_type_id"]), flags,
                                   count, len(raw)))
        payload.extend(raw)
        payload.extend(b"\0" * ((-len(payload)) & 7))
    return bytes(payload)


def record(record_type: int, sequence: int, step: int, tick: int,
           payload: bytes | None = None, flags: int = 1, version: int = 1) -> bytes:
    if payload is None:
        if record_type == 1:
            payload = struct.pack("<HBBQ", 1, 1, 0, 0)
        elif record_type == 6:
            payload = struct.pack("<HHI", 1, 1, 0)
        elif record_type == 11:
            payload = struct.pack("<HHI", 1, 0, 0)
        else:
            payload = b""
    value = bytearray(struct.pack(
        "<HHIQQQII", record_type, version, flags, sequence, step, tick,
        len(payload), 0
    ))
    value.extend(payload)
    value.extend(b"\0" * ((-len(value)) & 7))
    return bytes(value)


def tape(records: Iterable[bytes] | None = None, header_bytes: bytes | None = None,
         flags: int = 0, maximum_step: int = 0, maximum_tick: int = 0) -> bytes:
    header_bytes = header() if header_bytes is None else header_bytes
    records = list(records if records is not None else [
        record(1, 0, 0, 0),
        record(5, 1, 0, 0, projection()),
        record(6, 2, 0, 0),
        record(11, 3, 0, 0),
    ])
    region = b"".join(records)
    prefix = struct.pack(
        "<8sHHBBHIIQQQQQ", b"OTRLTAP\0", 1, 0, 1, 1, 64,
        len(header_bytes), flags, len(records), len(region), maximum_step,
        maximum_tick, 0,
    )
    covered = prefix + header_bytes + region
    return covered + struct.pack(
        "<8sQQ32sQ", b"OTRLEND\0", len(records), len(covered),
        hashlib.sha256(covered).digest(), 0
    )


def repair_digest(value: bytearray) -> None:
    value[-40:-8] = hashlib.sha256(value[:-64]).digest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hex-output", type=Path, required=True)
    args = parser.parse_args()
    encoded = tape()
    args.output.write_bytes(encoded)
    args.hex_output.write_text(encoded.hex() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
