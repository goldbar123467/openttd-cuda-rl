#!/usr/bin/env python3
"""Independent P0 JSON/schema validator; never a production tape authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import jsonschema
import rfc8785


EXIT_VALID = 0
EXIT_INVALID = 3
EXIT_IO = 4
EXIT_USAGE = 64
SECRET_ENV_RE = re.compile(r"(?:TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE|CREDENTIAL|API_KEY|AUTH)", re.IGNORECASE)
PORT001_MANDATORY_CHECK_IDS = {
    "BASELINE-SCHEMAS",
    "BINARY-ANALYSIS",
    "BRANCH-PUSH",
    "CLEAN-RUN-A",
    "CLEAN-RUN-B",
    "CONFIGURATION-IDENTITY",
    "HEADLESS-SMOKE-BEHAVIOR",
    "MANDATORY-TESTS",
    "OPENGFX-IDENTITY",
    "RUNTIME-VERSION-OUTPUT",
    "SOURCE-IDENTITY",
    "TEST-INVENTORY",
    "TEST-RESULTS",
}


class DuplicateKeyError(ValueError):
    """Raised when a JSON object repeats a member name."""


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant: {value}")


def load_strict_json(path: Path) -> Any:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 byte-order mark is forbidden")
    text = raw.decode("utf-8", errors="strict")
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicates,
        parse_constant=_reject_constant,
    )


def semantic_validate(schema_path: Path, instance: Any) -> None:
    if not isinstance(instance, dict):
        return
    declared_schema_digest = instance.get("schema_sha256")
    if declared_schema_digest is not None:
        actual_schema_digest = hashlib.sha256(schema_path.read_bytes()).hexdigest()
        if declared_schema_digest != actual_schema_digest:
            raise ValueError(
                f"schema_sha256 mismatch: expected actual schema digest {actual_schema_digest}, got {declared_schema_digest}",
            )

    environment_names: list[str] = []
    allowlist = instance.get("environment_allowlist")
    if isinstance(allowlist, list):
        environment_names.extend(name for name in allowlist if isinstance(name, str))
    environment = instance.get("environment")
    if isinstance(environment, list):
        environment_names.extend(
            entry["name"] for entry in environment
            if isinstance(entry, dict) and isinstance(entry.get("name"), str)
        )
    forbidden_names = sorted({name for name in environment_names if SECRET_ENV_RE.search(name)})
    if forbidden_names:
        raise ValueError(f"secret-named environment entries are forbidden: {forbidden_names}")

    def reject_workspace_paths(value: Any, *, diagnostics: bool = False) -> None:
        if isinstance(value, str) and not diagnostics and (value == "/workspace" or value.startswith("/workspace/")):
            raise ValueError(f"absolute workspace path is forbidden in authoritative manifest data: {value}")
        if isinstance(value, dict):
            for key, child in value.items():
                reject_workspace_paths(child, diagnostics=diagnostics or key == "diagnostics")
        elif isinstance(value, list):
            for child in value:
                reject_workspace_paths(child, diagnostics=diagnostics)

    reject_workspace_paths(instance)

    for collection_name, key_name in (
        ("tools", "name"),
        ("packages", "binary_package"),
        ("environment", "name"),
    ):
        collection = instance.get(collection_name)
        if isinstance(collection, list):
            keys = [entry.get(key_name) for entry in collection if isinstance(entry, dict)]
            if len(keys) != len(set(keys)):
                raise ValueError(f"duplicate {key_name} in {collection_name}")

    configuration = instance.get("configuration")
    if isinstance(configuration, dict) and isinstance(configuration.get("options"), list):
        option_names = [entry.get("name") for entry in configuration["options"] if isinstance(entry, dict)]
        if len(option_names) != len(set(option_names)):
            raise ValueError("duplicate configuration option name")

    if instance.get("profile") == "tests-relwithdebinfo":
        names = instance.get("test_names")
        serial = instance.get("serial_tests")
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            raise ValueError("test inventory names are malformed")
        if names != sorted(names) or len(names) != len(set(names)):
            raise ValueError("test inventory names must be unique and sorted")
        if not isinstance(serial, list) or not set(serial).issubset(names):
            raise ValueError("serial test inventory is not a subset of test names")
        stream = "".join(name + "\n" for name in names).encode("utf-8")
        if instance.get("inventory_sha256") != hashlib.sha256(stream).hexdigest():
            raise ValueError("test inventory digest does not match the exact name stream")
        if instance.get("inventory_stream_size_bytes") != len(stream):
            raise ValueError("test inventory stream size does not match the exact name stream")

    if schema_path.name == "gate-result.schema.json" and instance.get("status") == "PASS":
        checks = instance.get("checks")
        if not isinstance(checks, list) or not all(isinstance(check, dict) for check in checks):
            raise ValueError("PASS gate checks are malformed")
        if any(check.get("status") != "PASS" for check in checks):
            raise ValueError("PASS gate contains a non-PASS check")
        check_ids = [check.get("id") for check in checks]
        if not all(isinstance(check_id, str) for check_id in check_ids) or len(check_ids) != len(set(check_ids)):
            raise ValueError("PASS gate check IDs must be unique strings")
        open_counts = instance.get("open_counts")
        if not isinstance(open_counts, dict) or set(open_counts.values()) != {0}:
            raise ValueError("PASS gate contains a nonzero or malformed open count")
        branch_push = instance.get("branch_push")
        if (
            not isinstance(branch_push, dict)
            or branch_push.get("required") is not True
            or branch_push.get("verified") is not True
            or branch_push.get("local_commit") != branch_push.get("remote_commit")
        ):
            raise ValueError("PASS gate branch push is unverified or local/remote commits differ")
        if instance.get("gate_id") == "PORT-001" and set(check_ids) != PORT001_MANDATORY_CHECK_IDS:
            missing = sorted(PORT001_MANDATORY_CHECK_IDS - set(check_ids))
            unexpected = sorted(set(check_ids) - PORT001_MANDATORY_CHECK_IDS)
            raise ValueError(f"PORT-001 PASS gate check set is not exact: missing={missing}, unexpected={unexpected}")

    if schema_path.name == "defect-divergence-ledger.schema.json":
        entries = instance.get("entries")
        open_counts = instance.get("open_counts")
        if not isinstance(entries, list) or not isinstance(open_counts, dict):
            raise ValueError("defect/divergence ledger collections are malformed")
        entry_ids = [entry.get("id") for entry in entries if isinstance(entry, dict)]
        if len(entry_ids) != len(entries) or len(entry_ids) != len(set(entry_ids)):
            raise ValueError("defect/divergence ledger IDs must be unique strings")
        nonclosed = {"OPEN", "DIAGNOSED", "FIXED_PENDING_GATE"}
        defects = sum(
            entry.get("kind") == "DEFECT" and entry.get("status") in nonclosed
            for entry in entries
        )
        divergences = sum(
            entry.get("kind") == "DIVERGENCE" and entry.get("status") in nonclosed
            for entry in entries
        )
        expected_counts = {
            "defects": defects,
            "divergences": divergences,
            "total_nonclosed": defects + divergences,
        }
        if open_counts != expected_counts:
            raise ValueError(
                f"defect/divergence open counts disagree with entries: expected {expected_counts}, got {open_counts}",
            )


def validate(schema_path: Path, instance_path: Path, profile_lock_path: Path | None = None) -> tuple[Any, bytes]:
    schema = load_strict_json(schema_path)
    instance = load_strict_json(instance_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = "/" + "/".join(str(part) for part in first.absolute_path)
        raise ValueError(f"schema validation failed at {location}: {first.message}")
    semantic_validate(schema_path, instance)
    canonical = rfc8785.dumps(instance)
    if profile_lock_path is not None:
        lock = load_strict_json(profile_lock_path)
        if not isinstance(lock, dict) or not isinstance(lock.get("manifests"), dict):
            raise ValueError("profile lock is malformed")
        expected_digest = lock["manifests"].get(instance_path.name)
        if not isinstance(expected_digest, str):
            raise ValueError(f"profile lock omits {instance_path.name}")
        actual_digest = hashlib.sha256(canonical).hexdigest()
        if actual_digest != expected_digest:
            raise ValueError(
                f"frozen profile digest mismatch for {instance_path.name}: expected {expected_digest}, got {actual_digest}",
            )
    return instance, canonical


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Strict independent validator for P0 JSON artifacts",
    )
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--profile-lock", type=Path)
    digest_group = parser.add_mutually_exclusive_group()
    digest_group.add_argument("--canonical-sha256", action="store_true")
    digest_group.add_argument("--identity-sha256", action="store_true")
    parser.add_argument("instance", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        return EXIT_VALID if exc.code == 0 else EXIT_USAGE

    try:
        instance, canonical = validate(args.schema, args.instance, args.profile_lock)
    except (OSError, UnicodeError) as exc:
        print(f"I/O or encoding failure: {exc}", file=sys.stderr)
        return EXIT_IO
    except (DuplicateKeyError, ValueError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        print(f"invalid JSON artifact: {exc}", file=sys.stderr)
        return EXIT_INVALID
    except rfc8785.CanonicalizationError as exc:
        print(f"canonicalization failure: {exc}", file=sys.stderr)
        return EXIT_INVALID

    if args.identity_sha256:
        if not isinstance(instance, dict) or "identity" not in instance:
            print("identity digest requested but top-level identity is absent", file=sys.stderr)
            return EXIT_INVALID
        print(hashlib.sha256(rfc8785.dumps(instance["identity"])).hexdigest())
    elif args.canonical_sha256:
        print(hashlib.sha256(canonical).hexdigest())
    else:
        print("VALID")
    return EXIT_VALID


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
