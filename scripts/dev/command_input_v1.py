#!/usr/bin/env python3
"""Strict independent codec for the PORT-003 command-input v1 framing."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


PREFIX_MAGIC = b"OTRLCMD\x00"
TRAILER_MAGIC = b"OTRLCME\x00"
FORMAT_MAJOR = 1
FORMAT_MINOR = 0
BYTE_ORDER_CODE = 1
HASH_CODE_SHA256 = 1
PREFIX_BYTES = 64
ACTION_HEADER_BYTES = 48
TRAILER_BYTES = 64
MAX_HEADER_BYTES = 1 << 20
MAX_ACTION_COUNT = 1_000_000
MAX_ACTION_REGION_BYTES = 1 << 30
MAX_PAYLOAD_BYTES = 1 << 20
UINT64_MAX = (1 << 64) - 1

PREFIX = struct.Struct("<8sHHBBHIIQQQQQ")
ACTION_HEADER = struct.Struct("<HHIQQQIIII")
TRAILER = struct.Struct("<8sQQ32sQ")

HEADER_KEYS = {
    "action_payload_schema_sha256",
    "command_set_schema_sha256",
    "command_set_sha256",
    "company_context_policy",
    "content_sha256",
    "fixture_id",
    "fixture_sha256",
    "initial_boundary",
    "schema_version",
    "settings_sha256",
    "source_commit",
}
INITIAL_BOUNDARY_KEYS = {"native_tick", "public_step", "sha256"}
SHA256_KEYS = {
    "command_set_schema_sha256",
    "command_set_sha256",
    "content_sha256",
    "fixture_sha256",
    "settings_sha256",
}
SOURCE_COMMIT = "29f808ef0022064e6d9a83c8476d1e0f4686af86"
COMPANY_CONTEXT_POLICY = "action-header-u32-exact-or-0xffffffff-null"


class CommandInputError(ValueError):
    """Raised when command-input bytes violate the frozen format."""


@dataclass(frozen=True)
class ActionRule:
    action_type: int
    action_version: int
    native_command_id: int
    payload_bytes: int
    allowed_flags: int = 0


@dataclass(frozen=True)
class Action:
    action_type: int
    action_version: int
    flags: int
    sequence: int
    scheduled_public_step: int
    scheduled_native_tick: int
    native_command_id: int
    company_context: int
    payload: bytes


@dataclass(frozen=True)
class CommandInput:
    header: dict[str, Any]
    actions: tuple[Action, ...]
    sha256: str
    size_bytes: int


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CommandInputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_float(value: str) -> None:
    raise CommandInputError(f"floating-point JSON value is forbidden: {value}")


def canonical_json_bytes(value: Any) -> bytes:
    """Encode the ASCII-keyed, integer-only canonical JSON subset used by P0."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CommandInputError(f"header cannot be canonically encoded: {exc}") from exc


def load_json_bytes(data: bytes) -> Any:
    if data.startswith(b"\xef\xbb\xbf"):
        raise CommandInputError("JSON byte-order mark is forbidden")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CommandInputError(f"JSON is not strict UTF-8: {exc}") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except json.JSONDecodeError as exc:
        raise CommandInputError(f"invalid JSON: {exc}") from exc


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def validate_header(header: Any) -> dict[str, Any]:
    if not isinstance(header, dict) or set(header) != HEADER_KEYS:
        raise CommandInputError("canonical header has missing or unknown members")
    if header["schema_version"] != "openttd-p0-command-header-v1":
        raise CommandInputError("unsupported canonical header schema_version")
    if header["source_commit"] != SOURCE_COMMIT:
        raise CommandInputError("canonical header source commit differs from the pin")
    if header["company_context_policy"] != COMPANY_CONTEXT_POLICY:
        raise CommandInputError("unsupported company context policy")
    if not isinstance(header["fixture_id"], str) or not header["fixture_id"]:
        raise CommandInputError("fixture_id must be a nonempty string")
    for key in SHA256_KEYS:
        if not _is_sha256(header[key]):
            raise CommandInputError(f"{key} must be lowercase SHA-256 hexadecimal")
    boundary = header["initial_boundary"]
    if not isinstance(boundary, dict) or set(boundary) != INITIAL_BOUNDARY_KEYS:
        raise CommandInputError("initial_boundary has missing or unknown members")
    for key in ("native_tick", "public_step"):
        if not isinstance(boundary[key], int) or isinstance(boundary[key], bool) or not 0 <= boundary[key] <= UINT64_MAX:
            raise CommandInputError(f"initial_boundary.{key} must be a u64")
    if not _is_sha256(boundary["sha256"]):
        raise CommandInputError("initial_boundary.sha256 must be lowercase SHA-256 hexadecimal")
    payload_digests = header["action_payload_schema_sha256"]
    if not isinstance(payload_digests, dict) or not payload_digests:
        raise CommandInputError("action_payload_schema_sha256 must be a nonempty object")
    for name, digest in payload_digests.items():
        if not isinstance(name, str) or not name or not all(character.islower() or character.isdigit() or character == "_" for character in name):
            raise CommandInputError("action payload schema names must be lowercase identifiers")
        if not _is_sha256(digest):
            raise CommandInputError(f"payload schema digest for {name} is invalid")
    return header


def _checked_total(*values: int) -> int:
    total = 0
    for value in values:
        if value < 0 or value > UINT64_MAX - total:
            raise CommandInputError("command-input length addition overflows u64")
        total += value
    return total


def _padded_payload_bytes(payload_bytes: int) -> int:
    if not 0 <= payload_bytes <= MAX_PAYLOAD_BYTES:
        raise CommandInputError("action payload exceeds the format limit")
    return _checked_total(payload_bytes, (-payload_bytes) & 7)


def validate_command_registry(
    registry: Any,
    schema: Any | None = None,
    source_root: Path | None = None,
) -> dict[str, Any]:
    required_keys = {
        "$schema", "schema_version", "schema_sha256", "registry_major",
        "registry_minor", "source_commit", "command_input_format",
        "action_type_zero_reserved", "published_ids_never_reused", "actions",
    }
    if not isinstance(registry, dict) or set(registry) != required_keys:
        raise CommandInputError("command registry has missing or unknown members")
    if registry["$schema"] != "command-set.schema.json":
        raise CommandInputError("command registry names an unsupported schema")
    if registry["schema_version"] != "openttd-p0-commands-v1" or registry["registry_major"] != 1:
        raise CommandInputError("unsupported command registry version")
    if registry["source_commit"] != SOURCE_COMMIT:
        raise CommandInputError("command registry source commit differs from the pin")
    if registry["command_input_format"] != "OTRLCMD-v1.0-little-endian":
        raise CommandInputError("command registry format identity mismatch")
    if registry["action_type_zero_reserved"] is not True or registry["published_ids_never_reused"] is not True:
        raise CommandInputError("command registry stable-ID policy is not enabled")
    if schema is not None:
        schema_digest = hashlib.sha256(canonical_json_bytes(schema)).hexdigest()
        if registry["schema_sha256"] != schema_digest:
            raise CommandInputError("command registry schema digest mismatch")
    if not isinstance(registry["actions"], list) or not registry["actions"]:
        raise CommandInputError("command registry must contain actions")

    prior_type = 0
    names: set[str] = set()
    native_ids: set[int] = set()
    for entry in registry["actions"]:
        if not isinstance(entry, dict):
            raise CommandInputError("command registry action must be an object")
        action_type = entry.get("action_type")
        if not isinstance(action_type, int) or isinstance(action_type, bool) or action_type <= prior_type:
            raise CommandInputError("command registry action types must be strictly increasing positive integers")
        prior_type = action_type
        name = entry.get("name")
        native_id = entry.get("native_command_id")
        if name in names or native_id in native_ids:
            raise CommandInputError("command registry action name or native command ID is duplicated")
        names.add(name)
        native_ids.add(native_id)
        if entry.get("action_version") != 1:
            raise CommandInputError(f"unsupported registry action version for type {action_type}")
        payload_bytes = entry.get("payload_bytes")
        if not isinstance(payload_bytes, int) or isinstance(payload_bytes, bool) or not 0 < payload_bytes <= MAX_PAYLOAD_BYTES:
            raise CommandInputError(f"invalid payload size for action type {action_type}")
        operands = entry.get("operands")
        if not isinstance(operands, list) or not operands:
            raise CommandInputError(f"action type {action_type} has no operands")
        expected_payload_digest = hashlib.sha256(canonical_json_bytes({
            "action_type": action_type,
            "action_version": entry["action_version"],
            "payload_bytes": payload_bytes,
            "operands": operands,
        })).hexdigest()
        if entry.get("payload_schema_sha256") != expected_payload_digest:
            raise CommandInputError(f"payload schema digest mismatch for action type {action_type}")
        cursor = 0
        operand_names: set[str] = set()
        for operand in operands:
            if not isinstance(operand, dict):
                raise CommandInputError(f"non-object operand for action type {action_type}")
            operand_name = operand.get("name")
            if operand_name in operand_names:
                raise CommandInputError(f"duplicate operand name for action type {action_type}")
            operand_names.add(operand_name)
            if operand.get("offset") != cursor:
                raise CommandInputError(f"operand gap or overlap for action type {action_type}")
            width = operand.get("width_bits")
            count = operand.get("count", 1)
            if width not in {8, 16, 32, 64} or not isinstance(count, int) or isinstance(count, bool) or count < 1:
                raise CommandInputError(f"invalid operand width/count for action type {action_type}")
            cursor = _checked_total(cursor, width // 8 * count)
        if cursor != payload_bytes:
            raise CommandInputError(f"operands do not cover payload for action type {action_type}")
        if source_root is not None:
            source_path = source_root / entry["source_file"]
            if not source_path.is_file():
                raise CommandInputError(f"command source file is missing: {entry['source_file']}")
            source_lines = source_path.read_text(encoding="utf-8").splitlines()
            line = entry["source_line"]
            if line > len(source_lines) or entry["source_symbol"] not in source_lines[line - 1]:
                raise CommandInputError(f"command source locator mismatch for action type {action_type}")
    return registry


def registry_header_identity(registry: Any, schema: Any) -> dict[str, Any]:
    validated = validate_command_registry(registry, schema)
    return {
        "action_payload_schema_sha256": {
            entry["name"]: entry["payload_schema_sha256"] for entry in validated["actions"]
        },
        "command_set_schema_sha256": validated["schema_sha256"],
        "command_set_sha256": hashlib.sha256(canonical_json_bytes(validated)).hexdigest(),
    }


def rules_from_registry(registry: Any) -> dict[int, ActionRule]:
    registry = validate_command_registry(registry)
    rules: dict[int, ActionRule] = {}
    for entry in registry["actions"]:
        if not isinstance(entry, dict):
            raise CommandInputError("command registry action must be an object")
        try:
            rule = ActionRule(
                action_type=entry["action_type"],
                action_version=entry["action_version"],
                native_command_id=entry["native_command_id"],
                payload_bytes=entry["payload_bytes"],
                allowed_flags=entry["allowed_flags_mask"],
            )
        except KeyError as exc:
            raise CommandInputError(f"command registry action is missing {exc.args[0]}") from exc
        if rule.action_type in rules:
            raise CommandInputError(f"duplicate command registry action type {rule.action_type}")
        rules[rule.action_type] = rule
    return rules


def _validate_action(action: Action, rule: ActionRule, prior: Action | None) -> None:
    if action.action_version != rule.action_version:
        raise CommandInputError(f"unsupported action version for type {action.action_type}")
    if action.native_command_id != rule.native_command_id:
        raise CommandInputError(f"native command ID mismatch for action type {action.action_type}")
    if action.flags & ~rule.allowed_flags:
        raise CommandInputError(f"unknown action flags for type {action.action_type}")
    if len(action.payload) != rule.payload_bytes:
        raise CommandInputError(f"payload length mismatch for action type {action.action_type}")
    if not 0 <= action.company_context <= 0xFFFFFFFF:
        raise CommandInputError("company context is outside u32")
    if prior is None:
        if action.sequence != 0:
            raise CommandInputError("first action sequence must be zero")
    else:
        if action.sequence != prior.sequence + 1:
            raise CommandInputError("action sequence must increase exactly by one")
        if action.scheduled_public_step < prior.scheduled_public_step:
            raise CommandInputError("scheduled public step decreases")
        if action.scheduled_native_tick < prior.scheduled_native_tick:
            raise CommandInputError("scheduled native tick decreases")


def parse_command_input(
    data: bytes,
    rules: Mapping[int, ActionRule],
    expected_header: Mapping[str, Any] | None = None,
) -> CommandInput:
    """Validate the complete stream transactionally and return immutable values."""
    if len(data) < PREFIX_BYTES:
        raise CommandInputError("truncated command-input prefix")
    (
        magic,
        major,
        minor,
        byte_order,
        hash_code,
        prefix_bytes,
        header_bytes,
        flags,
        action_count,
        action_region_bytes,
        maximum_public_step,
        maximum_native_tick,
        reserved,
    ) = PREFIX.unpack_from(data)
    if magic != PREFIX_MAGIC:
        raise CommandInputError("bad command-input prefix magic")
    if major != FORMAT_MAJOR or minor != FORMAT_MINOR:
        raise CommandInputError("unsupported command-input format version")
    if byte_order != BYTE_ORDER_CODE or hash_code != HASH_CODE_SHA256:
        raise CommandInputError("unsupported byte-order or hash code")
    if prefix_bytes != PREFIX_BYTES:
        raise CommandInputError("noncanonical prefix size")
    if header_bytes == 0 or header_bytes > MAX_HEADER_BYTES:
        raise CommandInputError("canonical header length is outside limits")
    if flags != 0:
        raise CommandInputError("unknown command-input prefix flags")
    if action_count > MAX_ACTION_COUNT:
        raise CommandInputError("action count exceeds the format limit")
    if action_region_bytes > MAX_ACTION_REGION_BYTES:
        raise CommandInputError("action region exceeds the format limit")
    if reserved != 0:
        raise CommandInputError("nonzero command-input prefix reserved field")

    covered_bytes = _checked_total(PREFIX_BYTES, header_bytes, action_region_bytes)
    total_bytes = _checked_total(covered_bytes, TRAILER_BYTES)
    if len(data) < total_bytes:
        raise CommandInputError("truncated command-input stream")
    if len(data) > total_bytes:
        raise CommandInputError("trailing bytes after command-input trailer")

    header_raw = data[PREFIX_BYTES : PREFIX_BYTES + header_bytes]
    header = validate_header(load_json_bytes(header_raw))
    if canonical_json_bytes(header) != header_raw:
        raise CommandInputError("command-input header is not canonical JSON")
    if expected_header is not None:
        for key, expected in expected_header.items():
            if key not in header or header[key] != expected:
                raise CommandInputError(f"command-input identity mismatch: {key}")

    trailer_magic, trailer_count, trailer_covered, digest, trailer_reserved = TRAILER.unpack_from(data, covered_bytes)
    if trailer_magic != TRAILER_MAGIC:
        raise CommandInputError("bad command-input trailer magic")
    if trailer_count != action_count or trailer_covered != covered_bytes:
        raise CommandInputError("command-input trailer count or covered length mismatch")
    if trailer_reserved != 0:
        raise CommandInputError("nonzero command-input trailer reserved field")
    actual_digest = hashlib.sha256(data[:covered_bytes]).digest()
    if digest != actual_digest:
        raise CommandInputError("command-input stream checksum mismatch")

    cursor = PREFIX_BYTES + header_bytes
    action_limit = cursor + action_region_bytes
    actions: list[Action] = []
    prior: Action | None = None
    while cursor < action_limit:
        if action_limit - cursor < ACTION_HEADER_BYTES:
            raise CommandInputError("truncated action header")
        fields = ACTION_HEADER.unpack_from(data, cursor)
        action_type, action_version, action_flags, sequence, public_step, native_tick, native_id, company, payload_bytes, action_reserved = fields
        if action_reserved != 0:
            raise CommandInputError("nonzero action reserved field")
        padded_payload_bytes = _padded_payload_bytes(payload_bytes)
        record_bytes = _checked_total(ACTION_HEADER_BYTES, padded_payload_bytes)
        if record_bytes > action_limit - cursor:
            raise CommandInputError("truncated action payload")
        payload_start = cursor + ACTION_HEADER_BYTES
        payload_end = payload_start + payload_bytes
        padded_end = cursor + record_bytes
        if any(data[payload_end:padded_end]):
            raise CommandInputError("nonzero action alignment padding")
        action = Action(
            action_type,
            action_version,
            action_flags,
            sequence,
            public_step,
            native_tick,
            native_id,
            company,
            data[payload_start:payload_end],
        )
        rule = rules.get(action_type)
        if rule is None:
            raise CommandInputError(f"unknown required action type {action_type}")
        _validate_action(action, rule, prior)
        actions.append(action)
        prior = action
        cursor = padded_end

    if cursor != action_limit or len(actions) != action_count:
        raise CommandInputError("action count or action-region length mismatch")
    actual_max_public = actions[-1].scheduled_public_step if actions else header["initial_boundary"]["public_step"]
    actual_max_tick = actions[-1].scheduled_native_tick if actions else header["initial_boundary"]["native_tick"]
    if maximum_public_step != actual_max_public or maximum_native_tick != actual_max_tick:
        raise CommandInputError("maximum scheduled boundary fields are not exact")
    return CommandInput(header, tuple(actions), hashlib.sha256(data).hexdigest(), len(data))


def build_command_input(header: Mapping[str, Any], actions: Sequence[Action], rules: Mapping[int, ActionRule]) -> bytes:
    header_value = validate_header(dict(header))
    header_raw = canonical_json_bytes(header_value)
    if not 0 < len(header_raw) <= MAX_HEADER_BYTES:
        raise CommandInputError("canonical header length is outside limits")
    if len(actions) > MAX_ACTION_COUNT:
        raise CommandInputError("action count exceeds the format limit")

    action_parts: list[bytes] = []
    prior: Action | None = None
    for action in actions:
        rule = rules.get(action.action_type)
        if rule is None:
            raise CommandInputError(f"unknown required action type {action.action_type}")
        _validate_action(action, rule, prior)
        padded = _padded_payload_bytes(len(action.payload))
        action_parts.append(ACTION_HEADER.pack(
            action.action_type,
            action.action_version,
            action.flags,
            action.sequence,
            action.scheduled_public_step,
            action.scheduled_native_tick,
            action.native_command_id,
            action.company_context,
            len(action.payload),
            0,
        ))
        action_parts.append(action.payload)
        action_parts.append(bytes(padded - len(action.payload)))
        prior = action
    action_region = b"".join(action_parts)
    if len(action_region) > MAX_ACTION_REGION_BYTES:
        raise CommandInputError("action region exceeds the format limit")
    maximum_public_step = actions[-1].scheduled_public_step if actions else header_value["initial_boundary"]["public_step"]
    maximum_native_tick = actions[-1].scheduled_native_tick if actions else header_value["initial_boundary"]["native_tick"]
    prefix = PREFIX.pack(
        PREFIX_MAGIC,
        FORMAT_MAJOR,
        FORMAT_MINOR,
        BYTE_ORDER_CODE,
        HASH_CODE_SHA256,
        PREFIX_BYTES,
        len(header_raw),
        0,
        len(actions),
        len(action_region),
        maximum_public_step,
        maximum_native_tick,
        0,
    )
    covered = prefix + header_raw + action_region
    trailer = TRAILER.pack(TRAILER_MAGIC, len(actions), len(covered), hashlib.sha256(covered).digest(), 0)
    result = covered + trailer
    parse_command_input(result, rules)
    return result


def _load_json_file(path: Path) -> Any:
    return load_json_bytes(path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    validate_parser = subparsers.add_parser("validate", help="validate a complete command-input stream")
    validate_parser.add_argument("file", type=Path)
    validate_parser.add_argument("--registry", type=Path, required=True)
    empty_parser = subparsers.add_parser("build-empty", help="build a canonical no-action stream")
    empty_parser.add_argument("--header", type=Path, required=True)
    empty_parser.add_argument("--registry", type=Path, required=True)
    empty_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        registry = _load_json_file(args.registry)
        schema = _load_json_file(args.registry.parent / registry.get("$schema", ""))
        validate_command_registry(registry, schema, Path(__file__).resolve().parents[2] / "openttd-upstream")
        rules = rules_from_registry(registry)
        expected_identity = registry_header_identity(registry, schema)
        if args.operation == "validate":
            parsed = parse_command_input(args.file.read_bytes(), rules, expected_identity)
            print(json.dumps({"actions": len(parsed.actions), "sha256": parsed.sha256, "size_bytes": parsed.size_bytes}, sort_keys=True, separators=(",", ":")))
        else:
            header = _load_json_file(args.header)
            for key, value in expected_identity.items():
                if header.get(key) != value:
                    raise CommandInputError(f"command-input identity mismatch: {key}")
            output = build_command_input(header, (), rules)
            args.output.write_bytes(output)
            print(hashlib.sha256(output).hexdigest())
    except (CommandInputError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
