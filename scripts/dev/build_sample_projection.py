#!/usr/bin/env python3
"""Build a structurally complete zero-owner PORT005 sample projection.

This is a format fixture, not runtime continuation evidence. It includes every
authoritative_full field exactly once in registry order and is suitable for
PORT004 golden tape construction and parser mutation tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from validate_field_schema import canonical_bytes, load_json


def build_sample_projection(registry: dict[str, Any], boundary_ordinal: int = 0) -> dict[str, Any]:
    scalar_values: dict[str, int] = {}
    for field in registry["fields"]:
        if field["classification"] != "authoritative_full" or field["shape"] != "scalar" or field["width_bits"] is None:
            continue
        sample = field["sample_logical_value"]
        scalar_values[field["path"]] = int(sample[0] if isinstance(sample, list) else sample)

    records: list[dict[str, Any]] = []
    for field in registry["fields"]:
        if field["classification"] != "authoritative_full":
            continue
        if field["shape"] == "scalar":
            count = 1
            raw = bytes.fromhex(field["sample_encoded_hex"])
        elif field["shape"] == "fixed_array":
            count = field["fixed_count"]
            raw = bytes.fromhex(field["sample_encoded_hex"]) * count
        elif field["shape"] == "dynamic_array":
            count = scalar_values[field["count_source_field"]]
            raw = bytes.fromhex(field["sample_encoded_hex"]) * count
        else:
            count = scalar_values[field["count_source_field"]]
            raw = bytes((count + 7) // 8)
        records.append({
            "field_id": field["field_id"],
            "value_type": field["tape_value_type_id"],
            "element_count": count,
            "encoded_hex": raw.hex(),
        })
    return {
        "boundary_ordinal": boundary_ordinal,
        "field_schema_sha256": hashlib.sha256(canonical_bytes(registry)).hexdigest(),
        "fields": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--boundary-ordinal", type=int, default=0)
    args = parser.parse_args()
    if args.boundary_ordinal < 0:
        parser.error("--boundary-ordinal must be nonnegative")
    projection = build_sample_projection(load_json(args.registry), args.boundary_ordinal)
    args.output.write_bytes(canonical_bytes(projection) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
