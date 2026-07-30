#!/usr/bin/env python3
"""Strict semantic validator for the PORT-005 registry and projections."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError as exc:  # pragma: no cover - gate reports missing dependency
    raise SystemExit(f"jsonschema is required: {exc}")


PIN = "29f808ef0022064e6d9a83c8476d1e0f4686af86"
ALLOWED_WIDTHS = {8, 16, 32, 64}
NUMERIC_TYPES = {"u8", "u16", "u32", "u64", "i8", "i16", "i32", "i64", "stable_id"}
PLACEHOLDER = re.compile(r"(?:\bTBD\b|\bTODO\b|\bFIXME\b|\bunknown\b|\blater\b|placeholder)", re.IGNORECASE)


class RegistryError(ValueError):
    pass


def source_code_lines(lines: list[str]) -> list[str]:
    """Remove C/C++ comments while preserving one output entry per line."""
    result: list[str] = []
    in_block_comment = False
    for line in lines:
        code = line
        output = ""
        while code:
            if in_block_comment:
                if "*/" not in code:
                    code = ""
                    break
                code = code.split("*/", 1)[1]
                in_block_comment = False
                continue
            block = code.find("/*")
            single = code.find("//")
            if single >= 0 and (block < 0 or single < block):
                output += code[:single]
                code = ""
            elif block >= 0:
                output += code[:block]
                code = code[block + 2:]
                in_block_comment = True
            else:
                output += code
                code = ""
        result.append(output)
    return result


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegistryError(f"duplicate object key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except UnicodeDecodeError as exc:
        raise RegistryError(f"not strict UTF-8: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RegistryError(f"invalid JSON: {path}: {exc}") from exc


def reject_floats(value: Any, where: str = "$") -> None:
    if isinstance(value, float):
        raise RegistryError(f"floating point forbidden at {where}")
    if isinstance(value, dict):
        for key, item in value.items():
            reject_floats(item, f"{where}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_floats(item, f"{where}[{index}]")


def canonical_bytes(value: Any) -> bytes:
    reject_floats(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sample_bytes(field: dict[str, Any]) -> bytes:
    try:
        encoded = bytes.fromhex(field["sample_encoded_hex"])
    except ValueError as exc:
        raise RegistryError(f"field {field['field_id']} sample is not lowercase even-length hexadecimal") from exc
    if encoded.hex() != field["sample_encoded_hex"]:
        raise RegistryError(f"field {field['field_id']} sample is not lowercase canonical hexadecimal")
    return encoded


def validate_registry(registry_path: Path, schema_path: Path, source_root: Path) -> dict[str, Any]:
    registry = load_json(registry_path)
    schema = load_json(schema_path)
    reject_floats(registry)
    try:
        jsonschema.Draft202012Validator(schema).validate(registry)
    except jsonschema.ValidationError as exc:
        raise RegistryError(f"JSON Schema failure at {'/'.join(str(p) for p in exc.absolute_path)}: {exc.message}") from exc

    expected_schema_digest = hashlib.sha256(canonical_bytes(schema)).hexdigest()
    if registry["schema_sha256"] != expected_schema_digest:
        raise RegistryError("schema_sha256 does not match canonical committed schema")

    ids: set[int] = set()
    paths: set[str] = set()
    prior = 0
    fields_by_path: dict[str, dict[str, Any]] = {}
    for field in registry["fields"]:
        field_id = field["field_id"]
        path = field["path"]
        if field_id in ids:
            raise RegistryError(f"duplicate field ID {field_id}")
        if path in paths:
            raise RegistryError(f"duplicate field path {path}")
        if field_id <= prior:
            raise RegistryError(f"field IDs are not strictly increasing at {field_id}")
        prior = field_id
        ids.add(field_id)
        paths.add(path)
        fields_by_path[path] = field

        for key, value in field.items():
            if isinstance(value, str) and PLACEHOLDER.search(value):
                raise RegistryError(f"placeholder token in field {field_id}.{key}")
        if field["source_commit"] != PIN:
            raise RegistryError(f"field {field_id} source commit differs from pin")
        source = source_root / field["source_file"]
        if not source.is_file():
            raise RegistryError(f"field {field_id} source file absent: {field['source_file']}")
        lines = source.read_text(encoding="utf-8").splitlines()
        code_lines = source_code_lines(lines)
        line = field["source_line_diagnostic"]
        if line > len(lines):
            raise RegistryError(f"field {field_id} source line outside file")
        symbol = field["source_symbol"]
        matches = [number for number, candidate in enumerate(code_lines, 1) if symbol in candidate]
        if not matches:
            raise RegistryError(f"field {field_id} source declaration/definition locator absent outside comments: {symbol}")
        if symbol not in code_lines[line - 1]:
            raise RegistryError(f"field {field_id} source-line diagnostic points to a comment or different symbol")
        if line != matches[0]:
            raise RegistryError(f"field {field_id} source-line diagnostic is not the reviewed first exact code locator")

        typ = field["value_type"]
        width = field["width_bits"]
        signedness = field["signedness"]
        encoded = sample_bytes(field)
        sample_values = field["sample_logical_value"] if isinstance(field["sample_logical_value"], list) else [field["sample_logical_value"]]
        if typ in NUMERIC_TYPES:
            if width not in ALLOWED_WIDTHS:
                raise RegistryError(f"field {field_id} numeric width is not supported")
            if signedness not in {"signed", "unsigned"}:
                raise RegistryError(f"field {field_id} numeric signedness missing")
            if len(encoded) != (width // 8) * len(sample_values):
                raise RegistryError(f"field {field_id} sample byte length differs from declared width")
            signed = signedness == "signed"
            rebuilt = b"".join(int(value).to_bytes(width // 8, "little", signed=signed) for value in sample_values)
            if rebuilt != encoded:
                raise RegistryError(f"field {field_id} sample byte order/value mismatch")
        elif width is not None or signedness is not None:
            raise RegistryError(f"field {field_id} nonnumeric width/signedness must be null")

        shape = field["shape"]
        if shape in {"dynamic_array", "bitset"}:
            count_source = field["count_source_field"]
            if not count_source:
                raise RegistryError(f"field {field_id} variable shape missing count source")
        if shape == "fixed_array" and field["fixed_count"] is None:
            raise RegistryError(f"field {field_id} fixed array missing count")
        if field["maximum_capacity"] < (field["fixed_count"] or 0):
            raise RegistryError(f"field {field_id} capacity smaller than fixed count")
        if field["classification"] == "derived_rebuild" or field["cache_classification"] == "derived_rebuild":
            if field["deterministic_rebuild_procedure"] in {"not_applicable", "not claimed"}:
                raise RegistryError(f"field {field_id} derived cache has no rebuild procedure")
            if field["cache_evidence_sha256"] is None:
                raise RegistryError(f"field {field_id} derived cache has no 10000-tick evidence digest")
        if field["classification"] == "out_of_scope_unreachable" and "unreach" not in field["fixture_reachability_status"]:
            raise RegistryError(f"field {field_id} out-of-scope classification lacks proof tag")
        if field["classification"] == "diagnostic" and field["consumed_by_simulation"]:
            raise RegistryError(f"field {field_id} diagnostic field is marked as consumed by simulation")

    for field in registry["fields"]:
        count_source = field["count_source_field"]
        if field["shape"] in {"dynamic_array", "bitset"}:
            if count_source not in fields_by_path:
                raise RegistryError(f"field {field['field_id']} count source is not a registered field: {count_source}")
            if fields_by_path[count_source]["shape"] != "scalar":
                raise RegistryError(f"field {field['field_id']} count source is not scalar: {count_source}")
            if count_source == field["path"]:
                raise RegistryError(f"field {field['field_id']} count source is self-referential")
        target = field["offset_target_count_field"]
        is_offsets = field["path"].endswith("_offsets") or field["path"].endswith(".offsets")
        if is_offsets != (target is not None):
            raise RegistryError(f"field {field['field_id']} offset target metadata mismatch")
        if target is not None:
            if target not in fields_by_path or fields_by_path[target]["shape"] != "scalar":
                raise RegistryError(f"field {field['field_id']} offset target is not a scalar field: {target}")
            if field["value_type"] != "u32" or field["shape"] != "dynamic_array":
                raise RegistryError(f"field {field['field_id']} offsets must be a dynamic U32 array")

    # Count dependencies must remain acyclic even if a future schema adds more
    # structural layers.
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(path: str) -> None:
        if path in visiting:
            raise RegistryError(f"count-source cycle at {path}")
        if path in visited:
            return
        visiting.add(path)
        source = fields_by_path[path]["count_source_field"]
        if source is not None:
            visit(source)
        visiting.remove(path)
        visited.add(path)
    for path in fields_by_path:
        visit(path)
    return registry


def validate_projection(projection_path: Path, registry: dict[str, Any]) -> None:
    projection = load_json(projection_path)
    if not isinstance(projection, dict) or set(projection) != {"boundary_ordinal", "field_schema_sha256", "fields"}:
        raise RegistryError("projection must contain exactly boundary_ordinal, field_schema_sha256, and fields")
    canonical_registry = canonical_bytes(registry)
    digest = hashlib.sha256(canonical_registry).hexdigest()
    if projection["field_schema_sha256"] != digest:
        raise RegistryError("projection field-schema identity mismatch")
    if not isinstance(projection["boundary_ordinal"], int) or projection["boundary_ordinal"] < 0:
        raise RegistryError("projection boundary ordinal is invalid")
    expected = {field["field_id"]: field for field in registry["fields"] if field["classification"] == "authoritative_full"}
    records = projection["fields"]
    if not isinstance(records, list):
        raise RegistryError("projection fields is not an array")
    prior = 0
    seen: dict[int, dict[str, Any]] = {}
    decoded_scalars: dict[str, int] = {}
    decoded_offsets: dict[str, list[int]] = {}
    path_by_id = {field["field_id"]: field["path"] for field in registry["fields"]}
    for record in records:
        if not isinstance(record, dict) or set(record) != {"field_id", "value_type", "element_count", "encoded_hex"}:
            raise RegistryError("projection record shape is invalid")
        field_id = record["field_id"]
        if not isinstance(field_id, int) or field_id <= prior:
            raise RegistryError("projection field IDs are not strictly increasing/nonzero")
        prior = field_id
        if field_id not in expected:
            raise RegistryError(f"projection contains unknown or non-full field {field_id}")
        meta = expected[field_id]
        if record["value_type"] != meta["tape_value_type_id"]:
            raise RegistryError(f"projection field {field_id} value type mismatch")
        if not isinstance(record["element_count"], int) or not 0 <= record["element_count"] <= meta["maximum_capacity"]:
            raise RegistryError(f"projection field {field_id} element count outside capacity")
        try:
            raw = bytes.fromhex(record["encoded_hex"])
        except (TypeError, ValueError) as exc:
            raise RegistryError(f"projection field {field_id} invalid hex") from exc
        if raw.hex() != record["encoded_hex"]:
            raise RegistryError(f"projection field {field_id} noncanonical hex")
        width = meta["width_bits"]
        if width is not None and len(raw) != record["element_count"] * (width // 8):
            raise RegistryError(f"projection field {field_id} byte count disagrees with width/count")
        if meta["shape"] == "bitset":
            required_bytes = (record["element_count"] + 7) // 8
            if len(raw) != required_bytes:
                raise RegistryError(f"projection bitset field {field_id} byte count mismatch")
            if raw and record["element_count"] % 8 and raw[-1] >> (record["element_count"] % 8):
                raise RegistryError(f"projection bitset field {field_id} has nonzero high padding bits")
        if meta["shape"] == "scalar" and record["element_count"] != 1:
            raise RegistryError(f"projection scalar field {field_id} does not have one element")
        if meta["shape"] == "fixed_array" and record["element_count"] != meta["fixed_count"]:
            raise RegistryError(f"projection fixed field {field_id} count mismatch")
        if meta["shape"] == "scalar" and width is not None:
            decoded_scalars[path_by_id[field_id]] = int.from_bytes(raw, "little", signed=meta["signedness"] == "signed")
        if meta["offset_target_count_field"] is not None:
            decoded_offsets[path_by_id[field_id]] = [int.from_bytes(raw[pos:pos + 4], "little") for pos in range(0, len(raw), 4)]
        seen[field_id] = record
    missing = sorted(set(expected) - set(seen))
    if missing:
        raise RegistryError(f"projection omits authoritative_full field {missing[0]}")
    for field_id, record in seen.items():
        meta = expected[field_id]
        if meta["shape"] in {"dynamic_array", "bitset"}:
            count_path = meta["count_source_field"]
            if count_path in decoded_scalars and record["element_count"] != decoded_scalars[count_path]:
                raise RegistryError(f"projection field {field_id} count differs from {count_path}")
    for path, offsets in decoded_offsets.items():
        meta = next(field for field in expected.values() if field["path"] == path)
        if not offsets or offsets[0] != 0:
            raise RegistryError(f"projection offset field {path} must begin at zero")
        if any(left > right for left, right in zip(offsets, offsets[1:])):
            raise RegistryError(f"projection offset field {path} is not nondecreasing")
        target = meta["offset_target_count_field"]
        if target in decoded_scalars and offsets[-1] != decoded_scalars[target]:
            raise RegistryError(f"projection offset field {path} final value differs from {target}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("registry", type=Path)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--projection", type=Path)
    args = parser.parse_args()
    try:
        registry = validate_registry(args.registry, args.schema, args.source_root)
        if args.projection is not None:
            validate_projection(args.projection, registry)
    except RegistryError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: {len(registry['fields'])} fields; sha256={hashlib.sha256(canonical_bytes(registry)).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
