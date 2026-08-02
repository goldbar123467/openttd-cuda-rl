#!/usr/bin/env python3
"""Validate V2 atomic requirements, tests, local evidence, and defect accounting."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

import jsonschema


class V2TraceabilityError(ValueError):
    """V2 requirements/test/defect traceability violates a fail-closed invariant."""


@dataclass(frozen=True)
class V2TraceabilitySummary:
    requirements: int
    passed: int
    in_progress: int
    planned: int
    tests: int
    tests_passed: int
    nonclosed_defects: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise V2TraceabilityError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise V2TraceabilityError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise V2TraceabilityError(f"cannot hash {path}: {exc}") from exc


def schema_validate(instance: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(instance)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise V2TraceabilityError(f"{label} schema failed at {location}: {exc.message}") from exc


def require_unique(values: Iterable[str], label: str) -> None:
    values = list(values)
    duplicates = sorted({value for value in values if values.count(value) > 1})
    require(not duplicates, f"duplicate {label}: {duplicates}")


def require_local_paths(root: pathlib.Path, paths: Iterable[str], owner: str) -> None:
    for raw_path in paths:
        path = root / raw_path
        require(path.exists(), f"{owner} references missing local path: {raw_path}")


def validate(
    root: pathlib.Path,
    requirements_path: pathlib.Path | None = None,
    requirements_schema_path: pathlib.Path | None = None,
    defects_path: pathlib.Path | None = None,
    defects_schema_path: pathlib.Path | None = None,
) -> V2TraceabilitySummary:
    root = root.resolve()
    requirements_path = requirements_path or root / "docs/project/requirements-v2.json"
    requirements_schema_path = requirements_schema_path or root / "docs/project/schema/requirements-v2.schema.json"
    defects_path = defects_path or root / "docs/project/defects-v2.json"
    defects_schema_path = defects_schema_path or root / "docs/project/schema/defect-ledger-v2.schema.json"

    registry = load_json(requirements_path)
    registry_schema = load_json(requirements_schema_path)
    schema_validate(registry, registry_schema, "requirements")
    require(registry["schema_sha256"] == sha256_file(requirements_schema_path), "requirements schema SHA-256 mismatch")
    source_ids = [source["id"] for source in registry["source_authorities"]]
    require_unique(source_ids, "source authority ID")
    for source in registry["source_authorities"]:
        require_local_paths(root, [source["path"]], f"source authority {source['id']}")

    requirements = registry["requirements"]
    requirement_ids = [requirement["id"] for requirement in requirements]
    require_unique(requirement_ids, "V2 requirement ID")
    requirement_by_id = {requirement["id"]: requirement for requirement in requirements}
    requirement_index = {identifier: index for index, identifier in enumerate(requirement_ids)}
    gate_order = registry["gate_order"]
    gate_index = {gate: index for index, gate in enumerate(gate_order)}
    gate_counts = Counter(requirement["gate"] for requirement in requirements)
    require(set(gate_counts) == set(gate_order), "requirements do not cover every V2 gate")
    require(all(count >= 8 for count in gate_counts.values()), f"a V2 gate has fewer than eight atomic requirements: {dict(gate_counts)}")

    for requirement in requirements:
        identifier = requirement["id"]
        require(requirement["milestone"][1:] == requirement["gate"][1:], f"{identifier} milestone/gate mismatch")
        unknown_sources = sorted(set(requirement["source_refs"]) - set(source_ids))
        require(not unknown_sources, f"{identifier} references unknown sources: {unknown_sources}")
        unknown_dependencies = sorted(set(requirement["depends_on"]) - set(requirement_ids))
        require(not unknown_dependencies, f"{identifier} references unknown dependencies: {unknown_dependencies}")
        require(identifier not in requirement["depends_on"], f"{identifier} depends on itself")
        for dependency in requirement["depends_on"]:
            require(requirement_index[dependency] < requirement_index[identifier], f"{identifier} has a forward dependency on {dependency}")
            require(gate_index[requirement_by_id[dependency]["gate"]] <= gate_index[requirement["gate"]], f"{identifier} depends on a later gate {dependency}")
        require_local_paths(root, requirement["implementation"], f"requirement {identifier} implementation")
        require_local_paths(root, requirement["evidence"], f"requirement {identifier} evidence")
        if requirement["status"] == "PASS":
            incomplete = [dependency for dependency in requirement["depends_on"] if requirement_by_id[dependency]["status"] != "PASS"]
            require(not incomplete, f"passed requirement {identifier} has non-passed dependencies: {incomplete}")

    tests = registry["tests"]
    test_ids = [test["id"] for test in tests]
    require_unique(test_ids, "V2 test ID")
    test_by_id = {test["id"]: test for test in tests}
    require(set(test["gate"] for test in tests) == set(gate_order), "tests do not cover every V2 gate")
    linked_requirements: list[str] = []
    for test in tests:
        identifier = test["id"]
        unknown = sorted(set(test["requirement_ids"]) - set(requirement_ids))
        require(not unknown, f"{identifier} references unknown requirements: {unknown}")
        linked_requirements.extend(test["requirement_ids"])
        if test["runner"] is not None:
            require_local_paths(root, [test["runner"]], f"test {identifier} runner")
        require_local_paths(root, test["evidence"], f"test {identifier} evidence")
        for requirement_id in test["requirement_ids"]:
            requirement = requirement_by_id[requirement_id]
            require(requirement["gate"] == test["gate"], f"{identifier} gate differs from {requirement_id}")
            require(identifier in requirement["test_ids"], f"test-to-requirement link is not bidirectional: {identifier} -> {requirement_id}")
        if test["status"] == "PASS":
            nonpassed = [identifier for identifier in test["requirement_ids"] if requirement_by_id[identifier]["status"] != "PASS"]
            require(not nonpassed, f"passed test {identifier} covers non-passed requirements: {nonpassed}")
    require(set(linked_requirements) == set(requirement_ids), "one or more V2 requirements have no test owner")
    for requirement in requirements:
        identifier = requirement["id"]
        unknown_tests = sorted(set(requirement["test_ids"]) - set(test_ids))
        require(not unknown_tests, f"{identifier} references unknown tests: {unknown_tests}")
        for test_id in requirement["test_ids"]:
            require(identifier in test_by_id[test_id]["requirement_ids"], f"requirement-to-test link is not bidirectional: {identifier} -> {test_id}")
        if requirement["status"] == "PASS":
            require(any(test_by_id[test_id]["status"] == "PASS" for test_id in requirement["test_ids"]), f"passed requirement {identifier} has no passed test")
    v1_regression = test_by_id.get("V2-TEST-V1-REGRESSION")
    require(v1_regression is not None and v1_regression["status"] == "PASS", "V1 regression test is not retained as PASS")

    defects = load_json(defects_path)
    defects_schema = load_json(defects_schema_path)
    schema_validate(defects, defects_schema, "defect ledger")
    require(defects["schema_sha256"] == sha256_file(defects_schema_path), "defect schema SHA-256 mismatch")
    entries = defects["entries"]
    require_unique([entry["id"] for entry in entries], "V2 defect ID")
    active_statuses = {"OPEN", "DIAGNOSED", "FIXED_PENDING_VERIFICATION"}
    active = [entry for entry in entries if entry["status"] in active_statuses]
    expected_counts = {
        "defects": sum(entry["kind"] == "DEFECT" for entry in active),
        "divergences": sum(entry["kind"] == "DIVERGENCE" for entry in active),
        "release_blocking": sum(entry["blocks_release"] for entry in active),
        "total_nonclosed": len(active),
    }
    require(defects["open_counts"] == expected_counts, f"defect open counts drifted: {defects['open_counts']} != {expected_counts}")
    for entry in entries:
        identifier = entry["id"]
        unknown = sorted(set(entry["affected_requirement_ids"]) - set(requirement_ids))
        require(not unknown, f"{identifier} references unknown requirements: {unknown}")
        expected_gates = {requirement_by_id[item]["gate"] for item in entry["affected_requirement_ids"]}
        require(expected_gates.issubset(set(entry["affected_gates"])), f"{identifier} omits an affected requirement gate")
        require_local_paths(root, entry["reproducer"], f"defect {identifier} reproducer")
        require_local_paths(root, entry["evidence"], f"defect {identifier} evidence")
        require_local_paths(root, entry["closure_evidence"], f"defect {identifier} closure evidence")
        if entry["regression_test"] is not None:
            require_local_paths(root, [entry["regression_test"]], f"defect {identifier} regression test")

    statuses = Counter(requirement["status"] for requirement in requirements)
    return V2TraceabilitySummary(
        requirements=len(requirements),
        passed=statuses["PASS"],
        in_progress=statuses["IN_PROGRESS"],
        planned=statuses["PLANNED"],
        tests=len(tests),
        tests_passed=sum(test["status"] == "PASS" for test in tests),
        nonclosed_defects=len(active),
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--requirements", type=pathlib.Path)
    parser.add_argument("--requirements-schema", type=pathlib.Path)
    parser.add_argument("--defects", type=pathlib.Path)
    parser.add_argument("--defects-schema", type=pathlib.Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        summary = validate(
            args.root,
            args.requirements,
            args.requirements_schema,
            args.defects,
            args.defects_schema,
        )
        print(
            f"V2_TRACEABILITY=PASS requirements={summary.requirements} passed={summary.passed} "
            f"in_progress={summary.in_progress} planned={summary.planned} tests={summary.tests} "
            f"tests_passed={summary.tests_passed} nonclosed_defects={summary.nonclosed_defects}"
        )
        return 0
    except (V2TraceabilityError, OSError) as exc:
        print(f"V2_TRACEABILITY=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
