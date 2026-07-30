#!/usr/bin/env python3
"""Validate the P0 requirement graph beyond what JSON Schema can express."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import pathlib
import subprocess
import sys
from typing import Any

import jsonschema


class TraceabilityError(ValueError):
    """A fail-closed traceability contract violation."""


def load_json(path: pathlib.Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, child in pairs:
            if key in value:
                raise TraceabilityError(f"{path}: duplicate key {key!r}")
            value[key] = child
        return value

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=lambda token: (_ for _ in ()).throw(
            TraceabilityError(f"{path}: invalid JSON constant {token}")
        ),
    )


def unique_index(values: list[dict[str, Any]], name: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for value in values:
        identifier = value["id"]
        if identifier in result:
            raise TraceabilityError(f"duplicate {name} ID: {identifier}")
        result[identifier] = value
    return result


def tracked_implementation_paths(root: pathlib.Path) -> list[str]:
    output = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z", "--",
         "CMakeLists.txt", "CMakePresets.json", "cmake/**", "oracle/runner/**",
         "parity/include/**", "parity/python_reference/**", "parity/src/**",
         "parity/tools/**", "scripts/ci/**", "scripts/dev/**", "tools/*.py"],
    )
    return sorted(item.decode("utf-8") for item in output.split(b"\0") if item)


def validate(
    root: pathlib.Path,
    registry_path: pathlib.Path,
    schema_path: pathlib.Path,
    ledger_path: pathlib.Path,
    markdown_path: pathlib.Path,
    gate_result_path: pathlib.Path | None = None,
) -> tuple[int, int, int]:
    registry = load_json(registry_path)
    schema = load_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(registry)

    actual_schema_digest = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    if registry["schema_sha256"] != actual_schema_digest:
        raise TraceabilityError(
            "traceability schema digest mismatch: "
            f"expected {actual_schema_digest}, got {registry['schema_sha256']}"
        )

    requirements = unique_index(registry["requirements"], "requirement")
    tests = unique_index(registry["tests"], "test")
    markdown = markdown_path.read_text(encoding="utf-8")

    for requirement_id, requirement in requirements.items():
        if not requirement["test_ids"]:
            raise TraceabilityError(f"required requirement lacks a test: {requirement_id}")
        if not requirement["evidence"]:
            raise TraceabilityError(f"required requirement lacks evidence: {requirement_id}")
        if requirement_id not in markdown:
            raise TraceabilityError(f"human traceability view omits {requirement_id}")
        for test_id in requirement["test_ids"]:
            if test_id not in tests:
                raise TraceabilityError(f"{requirement_id} names undeclared test {test_id}")
            if requirement_id not in tests[test_id]["requirement_ids"]:
                raise TraceabilityError(f"test {test_id} lacks reverse mapping to {requirement_id}")
        if requirement["status"] == "PASS":
            for relative in requirement["implementation"] + requirement["evidence"]:
                if not (root / relative).is_file():
                    raise TraceabilityError(
                        f"passing requirement {requirement_id} points to missing artifact: {relative}"
                    )

    for test_id, test in tests.items():
        if not test["requirement_ids"]:
            raise TraceabilityError(f"required test lacks a requirement: {test_id}")
        if not (root / test["runner"]).is_file():
            raise TraceabilityError(f"test {test_id} runner is missing: {test['runner']}")
        for requirement_id in test["requirement_ids"]:
            if requirement_id not in requirements:
                raise TraceabilityError(f"test {test_id} names unknown requirement {requirement_id}")
            if test_id not in requirements[requirement_id]["test_ids"]:
                raise TraceabilityError(f"requirement {requirement_id} lacks reverse mapping to {test_id}")

    ownership = registry["implementation_ownership"]
    for rule in ownership:
        for requirement_id in rule["requirement_ids"]:
            if requirement_id not in requirements:
                raise TraceabilityError(
                    f"implementation rule {rule['glob']} names unknown requirement {requirement_id}"
                )
    for relative in tracked_implementation_paths(root):
        owners = {
            requirement_id
            for rule in ownership
            if fnmatch.fnmatchcase(relative, rule["glob"])
            for requirement_id in rule["requirement_ids"]
        }
        if not owners:
            raise TraceabilityError(f"implementation file has no owning requirement: {relative}")

    ledger = load_json(ledger_path)
    ledger_entries = {entry["id"]: entry for entry in ledger["entries"]}
    defect_mappings = {mapping["defect_id"]: mapping for mapping in registry["defect_mappings"]}
    if set(defect_mappings) != set(ledger_entries):
        missing = sorted(set(ledger_entries) - set(defect_mappings))
        stale = sorted(set(defect_mappings) - set(ledger_entries))
        raise TraceabilityError(f"defect mapping mismatch: missing={missing}, stale={stale}")
    open_statuses = {"OPEN", "DIAGNOSED", "FIXED_PENDING_GATE"}
    for defect_id, entry in ledger_entries.items():
        mapping = defect_mappings[defect_id]
        if entry["status"] in open_statuses:
            for requirement_id in mapping["requirement_ids"]:
                if requirements[requirement_id]["status"] == "PASS" and not mapping.get("passing_exception"):
                    raise TraceabilityError(
                        f"open defect {defect_id} maps to passing requirement {requirement_id}"
                    )

    gate_result_path = gate_result_path or root / "evidence/p0/P0_GATE_RESULT.json"
    if gate_result_path.exists():
        gate_result = load_json(gate_result_path)
        for gate in gate_result.get("gates", []):
            if gate.get("status") == "SKIP":
                raise TraceabilityError(f"mandatory gate uses SKIP: {gate.get('id', '<missing>')}")

    pass_count = sum(item["status"] == "PASS" for item in requirements.values())
    return len(requirements), len(tests), pass_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--registry", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    parser.add_argument("--ledger", type=pathlib.Path)
    parser.add_argument("--markdown", type=pathlib.Path)
    parser.add_argument("--gate-result", type=pathlib.Path)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    registry = args.registry or root / "evidence/p0/P0_REQUIREMENTS_TRACEABILITY.json"
    schema = args.schema or root / "oracle/manifests/schema/requirements-traceability.schema.json"
    ledger = args.ledger or root / "evidence/p0/P0_DEFECT_DIVERGENCE_LEDGER.json"
    markdown = args.markdown or root / "docs/testing/P0_REQUIREMENTS_TRACEABILITY.md"
    try:
        requirement_count, test_count, pass_count = validate(
            root, registry, schema, ledger, markdown, args.gate_result
        )
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError,
            jsonschema.SchemaError, jsonschema.ValidationError, TraceabilityError) as exc:
        print(f"traceability validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"TRACEABILITY=PASS requirements={requirement_count} tests={test_count} "
        f"requirements_passed={pass_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
