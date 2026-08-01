#!/usr/bin/env python3
"""Hostile-input tests for the independent command-input v1 codec."""

from __future__ import annotations

import hashlib
import copy
import struct
import sys
import unittest
from pathlib import Path

import jsonschema


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts" / "dev"))

from command_input_v1 import (  # noqa: E402
    ACTION_HEADER,
    ACTION_HEADER_BYTES,
    MAX_ACTION_COUNT,
    PREFIX,
    PREFIX_BYTES,
    TRAILER,
    TRAILER_BYTES,
    UINT64_MAX,
    Action,
    ActionRule,
    CommandInputError,
    _checked_total,
    build_command_input,
    canonical_json_bytes,
    load_json_bytes,
    parse_command_input,
    registry_header_identity,
    rules_from_registry,
    validate_command_registry,
)


ZERO = "0" * 64
RULES = {1: ActionRule(1, 1, 24, 3, 0)}


def header() -> dict[str, object]:
    return {
        "action_payload_schema_sha256": {"build_road_long": ZERO},
        "command_set_schema_sha256": ZERO,
        "command_set_sha256": ZERO,
        "company_context_policy": "action-header-u32-exact-or-0xffffffff-null",
        "content_sha256": ZERO,
        "fixture_id": "test-fixture",
        "fixture_sha256": ZERO,
        "initial_boundary": {"native_tick": 7, "public_step": 3, "sha256": ZERO},
        "schema_version": "openttd-p0-command-header-v1",
        "settings_sha256": ZERO,
        "source_commit": "29f808ef0022064e6d9a83c8476d1e0f4686af86",
    }


def action(sequence: int = 0, public_step: int = 3, native_tick: int = 7) -> Action:
    return Action(1, 1, 0, sequence, public_step, native_tick, 24, 0, b"abc")


def prefix_values(data: bytes | bytearray) -> list[object]:
    return list(PREFIX.unpack_from(data))


def replace_prefix(data: bytes, index: int, value: object) -> bytes:
    result = bytearray(data)
    values = prefix_values(result)
    values[index] = value
    result[:PREFIX_BYTES] = PREFIX.pack(*values)
    return bytes(result)


def repair_checksum(data: bytes) -> bytes:
    result = bytearray(data)
    values = prefix_values(result)
    covered = PREFIX_BYTES + int(values[6]) + int(values[9])
    if covered + TRAILER_BYTES <= len(result):
        result[covered + 24 : covered + 56] = hashlib.sha256(result[:covered]).digest()
    return bytes(result)


def mutate_u64(data: bytes, offset: int, value: int) -> bytes:
    result = bytearray(data)
    struct.pack_into("<Q", result, offset, value)
    return repair_checksum(bytes(result))


class CommandInputV1Tests(unittest.TestCase):
    def test_struct_sizes_are_frozen(self) -> None:
        self.assertEqual(PREFIX.size, 64)
        self.assertEqual(ACTION_HEADER.size, 48)
        self.assertEqual(TRAILER.size, 64)

    def test_minimal_valid_no_action_stream(self) -> None:
        data = build_command_input(header(), (), RULES)
        parsed = parse_command_input(data, RULES)
        self.assertEqual(parsed.actions, ())
        self.assertEqual(parsed.size_bytes, len(data))
        self.assertEqual(parsed.sha256, hashlib.sha256(data).hexdigest())

    def test_action_round_trip_and_zero_padding(self) -> None:
        data = build_command_input(header(), (action(),), RULES)
        parsed = parse_command_input(data, RULES)
        self.assertEqual(parsed.actions, (action(),))
        header_bytes = int(prefix_values(data)[6])
        payload_start = PREFIX_BYTES + header_bytes + ACTION_HEADER_BYTES
        self.assertEqual(data[payload_start : payload_start + 8], b"abc" + bytes(5))

    def test_bad_magic_rejected(self) -> None:
        data = replace_prefix(build_command_input(header(), (), RULES), 0, b"BADMAGIC")
        with self.assertRaisesRegex(CommandInputError, "prefix magic"):
            parse_command_input(data, RULES)

    def test_unsupported_major_and_minor_rejected(self) -> None:
        original = build_command_input(header(), (), RULES)
        for index, value in ((1, 2), (2, 1)):
            with self.subTest(index=index):
                with self.assertRaisesRegex(CommandInputError, "format version"):
                    parse_command_input(replace_prefix(original, index, value), RULES)

    def test_identity_mismatch_rejected(self) -> None:
        data = build_command_input(header(), (), RULES)
        with self.assertRaisesRegex(CommandInputError, "identity mismatch: fixture_sha256"):
            parse_command_input(data, RULES, {"fixture_sha256": "1" * 64})

    def test_noncanonical_header_rejected(self) -> None:
        value = header()
        header_raw = canonical_json_bytes(value) + b" "
        prefix = PREFIX.pack(b"OTRLCMD\x00", 1, 0, 1, 1, 64, len(header_raw), 0, 0, 0, 3, 7, 0)
        covered = prefix + header_raw
        data = covered + TRAILER.pack(b"OTRLCME\x00", 0, len(covered), hashlib.sha256(covered).digest(), 0)
        with self.assertRaisesRegex(CommandInputError, "not canonical"):
            parse_command_input(data, RULES)

    def test_truncated_prefix_header_action_and_trailer_rejected(self) -> None:
        empty = build_command_input(header(), (), RULES)
        populated = build_command_input(header(), (action(),), RULES)
        header_end = PREFIX_BYTES + int(prefix_values(empty)[6])
        action_start = PREFIX_BYTES + int(prefix_values(populated)[6])
        samples = (
            empty[:63],
            empty[: header_end - 1],
            populated[: action_start + ACTION_HEADER_BYTES - 1],
            empty[:-1],
        )
        for sample in samples:
            with self.subTest(size=len(sample)):
                with self.assertRaises(CommandInputError):
                    parse_command_input(sample, RULES)

    def test_oversized_action_count_rejected_before_allocation(self) -> None:
        data = replace_prefix(build_command_input(header(), (), RULES), 8, MAX_ACTION_COUNT + 1)
        with self.assertRaisesRegex(CommandInputError, "action count"):
            parse_command_input(data, RULES)

    def test_length_addition_overflow_rejected(self) -> None:
        with self.assertRaisesRegex(CommandInputError, "overflows u64"):
            _checked_total(UINT64_MAX, 1)
        data = replace_prefix(build_command_input(header(), (), RULES), 9, UINT64_MAX)
        with self.assertRaisesRegex(CommandInputError, "action region exceeds"):
            parse_command_input(data, RULES)

    def test_duplicate_or_skipped_sequence_rejected(self) -> None:
        data = build_command_input(header(), (action(), action(1)), RULES)
        header_bytes = int(prefix_values(data)[6])
        second_header = PREFIX_BYTES + header_bytes + ACTION_HEADER_BYTES + 8
        for value in (0, 2):
            with self.subTest(sequence=value):
                mutated = mutate_u64(data, second_header + 8, value)
                with self.assertRaisesRegex(CommandInputError, "sequence"):
                    parse_command_input(mutated, RULES)

    def test_decreasing_schedules_rejected(self) -> None:
        data = build_command_input(header(), (action(public_step=4, native_tick=8), action(1, 5, 9)), RULES)
        header_bytes = int(prefix_values(data)[6])
        second_header = PREFIX_BYTES + header_bytes + ACTION_HEADER_BYTES + 8
        for offset, value, message in ((16, 3, "public step"), (24, 7, "native tick")):
            with self.subTest(message=message):
                mutated = mutate_u64(data, second_header + offset, value)
                with self.assertRaisesRegex(CommandInputError, message):
                    parse_command_input(mutated, RULES)

    def test_unknown_action_type_rejected(self) -> None:
        data = build_command_input(header(), (action(),), RULES)
        header_bytes = int(prefix_values(data)[6])
        result = bytearray(data)
        struct.pack_into("<H", result, PREFIX_BYTES + header_bytes, 999)
        with self.assertRaisesRegex(CommandInputError, "unknown required action"):
            parse_command_input(repair_checksum(bytes(result)), RULES)

    def test_nonzero_reserved_fields_rejected(self) -> None:
        empty = build_command_input(header(), (), RULES)
        populated = build_command_input(header(), (action(),), RULES)
        header_bytes = int(prefix_values(populated)[6])
        cases: list[tuple[bytes, str]] = []
        cases.append((repair_checksum(replace_prefix(empty, 12, 1)), "prefix reserved"))
        action_reserved = bytearray(populated)
        struct.pack_into("<I", action_reserved, PREFIX_BYTES + header_bytes + 44, 1)
        cases.append((repair_checksum(bytes(action_reserved)), "action reserved"))
        trailer_reserved = bytearray(empty)
        struct.pack_into("<Q", trailer_reserved, len(empty) - 8, 1)
        cases.append((bytes(trailer_reserved), "trailer reserved"))
        for sample, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(CommandInputError, message):
                    parse_command_input(sample, RULES)

    def test_bad_checksum_rejected(self) -> None:
        data = bytearray(build_command_input(header(), (), RULES))
        data[-32] ^= 1
        with self.assertRaisesRegex(CommandInputError, "checksum"):
            parse_command_input(bytes(data), RULES)

    def test_trailing_bytes_rejected(self) -> None:
        data = build_command_input(header(), (), RULES) + b"x"
        with self.assertRaisesRegex(CommandInputError, "trailing bytes"):
            parse_command_input(data, RULES)

    def test_nonzero_action_padding_rejected(self) -> None:
        data = bytearray(build_command_input(header(), (action(),), RULES))
        header_bytes = int(prefix_values(data)[6])
        padding_offset = PREFIX_BYTES + header_bytes + ACTION_HEADER_BYTES + 3
        data[padding_offset] = 1
        with self.assertRaisesRegex(CommandInputError, "alignment padding"):
            parse_command_input(repair_checksum(bytes(data)), RULES)

    def test_native_command_payload_and_flag_contracts_rejected(self) -> None:
        data = build_command_input(header(), (action(),), RULES)
        header_bytes = int(prefix_values(data)[6])
        action_offset = PREFIX_BYTES + header_bytes
        mutations = ((action_offset + 4, "<I", 1, "flags"), (action_offset + 32, "<I", 27, "native command ID"), (action_offset + 40, "<I", 4, "payload"))
        for offset, encoding, value, message in mutations:
            with self.subTest(message=message):
                result = bytearray(data)
                struct.pack_into(encoding, result, offset, value)
                with self.assertRaisesRegex(CommandInputError, message):
                    parse_command_input(repair_checksum(bytes(result)), RULES)

    def test_validation_does_not_mutate_input(self) -> None:
        source = bytearray(build_command_input(header(), (action(),), RULES))
        before = bytes(source)
        parse_command_input(source, RULES)
        self.assertEqual(bytes(source), before)


class CommandRegistryV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = load_json_bytes((REPOSITORY_ROOT / "parity/schema/command-set.schema.json").read_bytes())
        cls.registry = load_json_bytes((REPOSITORY_ROOT / "parity/schema/commands-v1.json").read_bytes())

    def test_committed_registry_matches_source_and_payload_digests(self) -> None:
        jsonschema.Draft202012Validator(self.schema).validate(self.registry)
        validated = validate_command_registry(self.registry, self.schema, REPOSITORY_ROOT / "openttd-upstream")
        self.assertEqual([entry["action_type"] for entry in validated["actions"]], [1, 2, 3, 4, 5, 6])
        self.assertEqual([entry["native_command_id"] for entry in validated["actions"]], [24, 27, 22, 34, 46, 121])

    def test_registry_identity_binds_a_no_action_stream(self) -> None:
        identity = registry_header_identity(self.registry, self.schema)
        value = header()
        value.update(identity)
        rules = rules_from_registry(self.registry)
        data = build_command_input(value, (), rules)
        parsed = parse_command_input(data, rules, identity)
        self.assertEqual(parsed.header["command_set_sha256"], identity["command_set_sha256"])

    def test_payload_schema_digest_mutation_rejected(self) -> None:
        mutated = copy.deepcopy(self.registry)
        mutated["actions"][0]["operands"][0]["domain"] = "0..4094"
        with self.assertRaisesRegex(CommandInputError, "payload schema digest mismatch"):
            validate_command_registry(mutated, self.schema)


if __name__ == "__main__":
    unittest.main()
