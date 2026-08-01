#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Independent standard-library decoder for OpenTTD RL tape v1.

This module intentionally shares neither C parser code nor an FFI boundary.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

PREFIX = struct.Struct("<8sHHBBHIIQQQQQ")
RECORD = struct.Struct("<HHIQQQII")
TRAILER = struct.Struct("<8sQQ32sQ")
PROJECTION = struct.Struct("<HBBIQQ")
FIELD = struct.Struct("<IHHII")
FIELD_SCHEMA_SHA256 = "7622144440833e574435ea3633e8692504d8f69cdf27fe54c4b0c39c51684438"
_REGISTRY = json.loads(
    (Path(__file__).resolve().parents[1] / "schema/fields-v1.json").read_text()
)
_AUTHORITATIVE_FIELDS = tuple(
    field for field in _REGISTRY["fields"]
    if field["classification"] == "authoritative_full"
)


class TapeError(ValueError):
    def __init__(self, status: str, offset: int, message: str) -> None:
        super().__init__(f"{status} at {offset}: {message}")
        self.status = status
        self.offset = offset


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TapeError("canonical", 64, f"duplicate key {key!r}")
        result[key] = value
    return result


def canonical_json(value: Any) -> bytes:
    # Tape v1's schema admits integers but no floating values, so the
    # standard library's sorted compact form is the RFC 8785 representation
    # for every admitted header instance.
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _hex(value: Any, digits: int, name: str) -> None:
    if not isinstance(value, str) or len(value) != digits or any(
        byte not in "0123456789abcdef" for byte in value
    ):
        raise TapeError("schema", 64, f"invalid {name}")


def validate_header(value: Any) -> None:
    expected_top = {
        "backend_label",
        "diagnostic_features",
        "format",
        "identity",
        "initial",
        "limits",
        "projection_policy",
    }
    if not isinstance(value, dict) or set(value) != expected_top:
        raise TapeError("schema", 64, "header properties disagree with v1 schema")
    if not isinstance(value["backend_label"], str) or not value["backend_label"]:
        raise TapeError("schema", 64, "backend label required")
    diagnostics = value["diagnostic_features"]
    if not isinstance(diagnostics, list) or not all(
        isinstance(item, str) and item for item in diagnostics
    ) or len(diagnostics) != len(set(diagnostics)):
        raise TapeError("schema", 64, "diagnostic features invalid")
    if value["format"] != {"major": 1, "minor": 0}:
        raise TapeError("schema", 64, "format identity invalid")
    identity = value["identity"]
    digest_names = {
        "build_sha256",
        "command_input_sha256",
        "command_schema_sha256",
        "content_sha256",
        "executable_sha256",
        "field_schema_sha256",
        "fixture_sha256",
        "instrumentation_sha256",
        "settings_sha256",
    }
    if not isinstance(identity, dict) or set(identity) != digest_names | {
        "newgrfs", "source_commit"
    }:
        raise TapeError("schema", 64, "identity properties invalid")
    for name in digest_names:
        _hex(identity[name], 64, name)
    if identity["field_schema_sha256"] != FIELD_SCHEMA_SHA256:
        raise TapeError("schema", 64, "field schema digest differs from linked registry")
    _hex(identity["source_commit"], 40, "source_commit")
    if identity["newgrfs"] != []:
        raise TapeError("identity", 64, "NewGRF list must be empty")
    initial = value["initial"]
    initial_names = {
        "calendar_date", "calendar_fraction", "economy_date",
        "economy_fraction", "gameplay_rng_state", "interactive_rng_state",
        "native_tick", "public_step", "timers",
    }
    if not isinstance(initial, dict) or set(initial) != initial_names:
        raise TapeError("schema", 64, "initial properties invalid")
    for name in ("calendar_date", "calendar_fraction", "economy_date",
                 "economy_fraction"):
        if type(initial[name]) is not int or not 0 <= initial[name] <= 0xFFFFFFFF:
            raise TapeError("schema", 64, f"invalid {name}")
    for name in ("native_tick", "public_step"):
        if type(initial[name]) is not int or not 0 <= initial[name] <= 2**53 - 1:
            raise TapeError("schema", 64, f"invalid {name}")
    _hex(initial["gameplay_rng_state"], 16, "gameplay RNG")
    _hex(initial["interactive_rng_state"], 16, "interactive RNG")
    if not isinstance(initial["timers"], dict) or not initial["timers"]:
        raise TapeError("schema", 64, "timer state required")
    if value["limits"] != {
        "command_count": 1_000_000,
        "field_bytes": 67_108_864,
        "field_count": 10_000_000,
        "header_bytes": 1_048_576,
        "record_count": 50_000_000,
        "record_payload_bytes": 67_108_864,
        "tape_bytes": 1_099_511_627_776,
    }:
        raise TapeError("schema", 64, "declared limits differ from v1")
    if value["projection_policy"] != "complete":
        raise TapeError("schema", 64, "complete projection policy required")


@dataclasses.dataclass(frozen=True)
class FieldValue:
    field_id: int
    value_type: int
    flags: int
    elements: int
    value: bytes


@dataclasses.dataclass(frozen=True)
class RecordValue:
    record_type: int
    version: int
    flags: int
    sequence: int
    public_step: int
    native_tick: int
    payload: bytes
    offset: int
    fields: tuple[FieldValue, ...] = ()


@dataclasses.dataclass(frozen=True)
class TapeValue:
    header: dict[str, Any]
    records: tuple[RecordValue, ...]
    digest: bytes
    flags: int
    maximum_public_step: int
    maximum_native_tick: int


def _projection(payload: bytes, base: int) -> tuple[FieldValue, ...]:
    if len(payload) < PROJECTION.size:
        raise TapeError("truncated", base + len(payload), "projection header")
    version, _kind, reserved, count, _ordinal, _digest = PROJECTION.unpack_from(payload)
    if version != 1:
        raise TapeError("version", base, "projection version")
    if reserved:
        raise TapeError("reserved", base + 3, "projection reserved")
    if count != len(_AUTHORITATIVE_FIELDS):
        raise TapeError("schema", base + 4, "projection field count")
    offset = PROJECTION.size
    previous = 0
    fields: list[FieldValue] = []
    widths = {1: 1, 2: 2, 3: 4, 4: 8, 5: 1, 6: 2, 7: 4, 8: 8}
    for expected in _AUTHORITATIVE_FIELDS:
        if len(payload) - offset < FIELD.size:
            raise TapeError("truncated", base + offset, "field header")
        field_id, value_type, flags, elements, byte_count = FIELD.unpack_from(payload, offset)
        if field_id <= previous or field_id != expected["field_id"]:
            raise TapeError("schema", base + offset, "field order or completeness")
        if value_type != expected["tape_value_type_id"]:
            raise TapeError("schema", base + offset + 4, "registry value type")
        previous = field_id
        offset += FIELD.size
        end = offset + byte_count
        padded = (end + 7) & ~7
        if padded > len(payload):
            raise TapeError("truncated", base + len(payload), "field value")
        value = payload[offset:end]
        if any(payload[end:padded]):
            raise TapeError("canonical", base + end, "field padding")
        width = widths.get(value_type, flags if value_type == 10 else 0)
        if value_type != 10 and flags:
            raise TapeError("schema", base + offset, "field flags")
        if expected["width_bits"] is not None and width * 8 != expected["width_bits"]:
            raise TapeError("schema", base + offset, "registry width")
        if expected["shape"] in ("scalar", "fixed_array") and elements != expected["fixed_count"]:
            raise TapeError("schema", base + offset, "registry fixed count")
        if expected["shape"] in ("dynamic_array", "bitset") and elements > expected["maximum_capacity"]:
            raise TapeError("schema", base + offset, "registry capacity")
        if width and elements * width != byte_count:
            raise TapeError("schema", base + offset, "field width")
        if value_type in (9, 12) and elements != byte_count:
            raise TapeError("schema", base + offset, "byte field count")
        if value_type == 11:
            if (elements + 7) // 8 != byte_count:
                raise TapeError("schema", base + offset, "bitset width")
            if elements and elements % 8 and value[-1] & ~((1 << elements % 8) - 1):
                raise TapeError("canonical", base + end - 1, "bitset high bits")
        if value_type == 12:
            value.decode("utf-8")
        if value_type not in range(1, 13):
            raise TapeError("schema", base + offset, "unknown value type")
        fields.append(FieldValue(field_id, value_type, flags, elements, value))
        offset = padded
    if offset != len(payload):
        raise TapeError("structure", base + offset, "projection trailing bytes")
    by_id = {field.field_id: field for field in fields}
    for field, expected in zip(fields, _AUTHORITATIVE_FIELDS, strict=True):
        source_path = expected["count_source_field"]
        if source_path is not None:
            source_id = next(item["field_id"] for item in _AUTHORITATIVE_FIELDS
                             if item["path"] == source_path)
            source = by_id[source_id]
            declared = int.from_bytes(source.value, "little", signed=False)
            if field.elements != declared:
                raise TapeError("schema", base, "count-source relationship")
        target_path = expected["offset_target_count_field"]
        if target_path is not None:
            target_id = next(item["field_id"] for item in _AUTHORITATIVE_FIELDS
                             if item["path"] == target_path)
            target = int.from_bytes(by_id[target_id].value, "little", signed=False)
            offsets = [int.from_bytes(field.value[index:index + 4], "little")
                       for index in range(0, len(field.value), 4)]
            if not offsets or offsets[0] != 0 or any(
                right < left for left, right in zip(offsets, offsets[1:])
            ) or offsets[-1] != target:
                raise TapeError("schema", base, "offset relationship")
    return tuple(fields)


def decode_bytes(data: bytes) -> TapeValue:
    if len(data) < PREFIX.size:
        raise TapeError("truncated", len(data), "file prefix")
    (magic, major, minor, endian, hash_code, prefix_bytes, header_bytes, flags,
     record_count, record_bytes, max_step, max_tick, reserved) = PREFIX.unpack_from(data)
    if magic != b"OTRLTAP\0":
        raise TapeError("magic", 0, "file prefix")
    if (major, minor) != (1, 0):
        raise TapeError("version", 8, "tape version")
    if endian != 1:
        raise TapeError("endian", 12, "byte order")
    if hash_code != 1:
        raise TapeError("hash_algorithm", 13, "digest algorithm")
    if prefix_bytes != 64 or reserved:
        raise TapeError("reserved", 14 if prefix_bytes != 64 else 56, "prefix")
    if flags & 1 or flags & 0xFFFF0000:
        raise TapeError("structure", 20, "partial or unknown required flags")
    if not 0 < header_bytes <= 1_048_576:
        raise TapeError("limit", 16, "header bytes")
    if not 0 < record_count <= 50_000_000:
        raise TapeError("limit", 24, "record count")
    trailer_offset = 64 + header_bytes + record_bytes
    if trailer_offset + TRAILER.size != len(data):
        status = "truncated" if trailer_offset + TRAILER.size > len(data) else "structure"
        raise TapeError(status, len(data), "declared length")
    header_raw = data[64:64 + header_bytes]
    try:
        header = json.loads(header_raw, object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TapeError("canonical", 64, str(exc)) from exc
    if canonical_json(header) != header_raw:
        raise TapeError("canonical", 64, "header is not RFC8785 canonical subset")
    validate_header(header)
    trailer_magic, trailer_count, covered, digest, trailer_reserved = TRAILER.unpack_from(
        data, trailer_offset
    )
    if trailer_magic != b"OTRLEND\0":
        raise TapeError("magic", trailer_offset, "trailer")
    if trailer_count != record_count or covered != trailer_offset:
        raise TapeError("structure", trailer_offset + 8, "trailer counts")
    if trailer_reserved:
        raise TapeError("reserved", trailer_offset + 56, "trailer")
    if hashlib.sha256(data[:trailer_offset]).digest() != digest:
        raise TapeError("checksum", trailer_offset + 24, "covered digest")
    records: list[RecordValue] = []
    offset = 64 + header_bytes
    previous_step = previous_tick = 0
    for sequence in range(record_count):
        if trailer_offset - offset < RECORD.size:
            raise TapeError("truncated", offset, "record header")
        record_type, version, rflags, encoded_sequence, step, tick, payload_bytes, rr = (
            RECORD.unpack_from(data, offset)
        )
        if rr or rflags & ~1:
            raise TapeError("reserved", offset + (36 if rr else 4), "record")
        if encoded_sequence != sequence:
            raise TapeError("sequence", offset + 8, "record sequence")
        if version != 1:
            raise TapeError("version", offset + 2, "record version")
        if sequence and (step < previous_step or tick < previous_tick):
            raise TapeError("sequence", offset + 16, "boundary order")
        end = offset + RECORD.size + payload_bytes
        padded = (end + 7) & ~7
        if padded > trailer_offset:
            raise TapeError("truncated", trailer_offset, "record payload")
        if any(data[end:padded]):
            raise TapeError("canonical", end, "record padding")
        payload = data[offset + RECORD.size:end]
        fields = _projection(payload, offset + RECORD.size) if record_type == 5 else ()
        records.append(RecordValue(record_type, version, rflags, sequence, step, tick,
                                   payload, offset, fields))
        previous_step, previous_tick, offset = step, tick, padded
    if offset != trailer_offset or records[0].record_type != 1 or records[-1].record_type != 11:
        raise TapeError("structure", offset, "record region lifecycle")
    if not any(record.record_type == 5 for record in records):
        raise TapeError("structure", offset, "projection missing")
    if (max_step, max_tick) != (previous_step, previous_tick):
        raise TapeError("structure", 40, "prefix maxima")
    return TapeValue(header, tuple(records), digest, flags, max_step, max_tick)


def decode_file(path: str | Path) -> TapeValue:
    return decode_bytes(Path(path).read_bytes())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    decoded = decode_file(args.file)
    print(json.dumps({"digest": decoded.digest.hex(), "records": len(decoded.records)},
                     sort_keys=True, separators=(",", ":")))
