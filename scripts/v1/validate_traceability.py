#!/usr/bin/env python3
"""Validate V1 project traceability beyond JSON Schema expressiveness."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema


REQUIREMENT_ID = re.compile(
    r"^(SCOPE|LIFE|STACK|PPO|OBS|ACT|REW|AI|MODEL|RUN|MON|EVAL|REPRO|TEST|ARCH|DONE|EXP)-[0-9]{3}$"
)
EXPECTED_PREFIX_COUNTS = {
    "ACT": 20,
    "AI": 6,
    "ARCH": 5,
    "DONE": 8,
    "EVAL": 13,
    "EXP": 10,
    "LIFE": 17,
    "MODEL": 18,
    "MON": 9,
    "OBS": 18,
    "PPO": 22,
    "REPRO": 9,
    "REW": 8,
    "RUN": 10,
    "SCOPE": 27,
    "STACK": 11,
    "TEST": 16,
}
EXPECTED_SOURCE_BRIEFS = {
    "short": {
        "filename": "pasted-text-1.txt",
        "size_bytes": 2124,
        "line_count": 106,
        "sha256": "03d14e26b4e0b438e419d6f834ca99025c5a980eecee4c536c0cda5f7243b92a",
    },
    "full": {
        "filename": "pasted-text-2.txt",
        "size_bytes": 19339,
        "line_count": 759,
        "sha256": "a7da553035e44468f29184a69c014f16bd1439fcbdf77275d0762073da306492",
    },
}
NONCLOSED_DEFECT_STATUSES = {
    "OPEN",
    "DIAGNOSED",
    "FIXED_PENDING_VERIFICATION",
    "ACCEPTED_LIMITATION",
}


class TraceabilityError(ValueError):
    """A fail-closed project traceability contract violation."""


@dataclass(frozen=True)
class ValidationSummary:
    requirements: int
    tests: int
    requirements_passed: int
    post_v1_deferred: int
    nonclosed_defects: int


def load_json(path: pathlib.Path) -> Any:
    """Load strict JSON, rejecting duplicate keys and nonstandard constants."""

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise TraceabilityError(f"{path}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=lambda token: (_ for _ in ()).throw(
            TraceabilityError(f"{path}: invalid JSON constant {token}")
        ),
    )


def unique_index(values: list[dict[str, Any]], kind: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for value in values:
        identifier = value["id"]
        if identifier in result:
            raise TraceabilityError(f"duplicate {kind} ID: {identifier}")
        result[identifier] = value
    return result


def validate_schema(instance: Any, schema: Any) -> None:
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    ).validate(instance)


def check_schema_digest(instance: dict[str, Any], schema_path: pathlib.Path, label: str) -> None:
    actual = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    if instance["schema_sha256"] != actual:
        raise TraceabilityError(
            f"{label} schema digest mismatch: expected {actual}, got {instance['schema_sha256']}"
        )


def parse_human_requirements(markdown_path: pathlib.Path) -> dict[str, dict[str, str]]:
    """Independently parse the four-column atomic requirement rows."""

    rows: dict[str, dict[str, str]] = {}
    for line_number, line in enumerate(markdown_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("| `"):
            continue
        fields = line.split("|")
        if len(fields) != 6:
            continue
        raw_id, summary, acceptance, raw_status = (field.strip() for field in fields[1:5])
        if not (raw_id.startswith("`") and raw_id.endswith("`")):
            continue
        identifier = raw_id[1:-1]
        if not REQUIREMENT_ID.fullmatch(identifier):
            continue
        if not (raw_status.startswith("`") and raw_status.endswith("`")):
            raise TraceabilityError(
                f"{markdown_path}:{line_number}: requirement {identifier} status is not code-delimited"
            )
        if identifier in rows:
            raise TraceabilityError(
                f"{markdown_path}:{line_number}: duplicate human requirement {identifier}"
            )
        rows[identifier] = {
            "summary": summary,
            "acceptance": acceptance,
            "status": raw_status[1:-1],
        }
    if not rows:
        raise TraceabilityError(f"{markdown_path}: no atomic requirement rows found")
    return rows


def check_source_briefs(registry: dict[str, Any]) -> None:
    briefs = unique_index(registry["source_briefs"], "source brief")
    if set(briefs) != set(EXPECTED_SOURCE_BRIEFS):
        raise TraceabilityError(
            f"source brief set mismatch: expected={sorted(EXPECTED_SOURCE_BRIEFS)} got={sorted(briefs)}"
        )
    for identifier, expected in EXPECTED_SOURCE_BRIEFS.items():
        observed = briefs[identifier]
        for key, expected_value in expected.items():
            if observed[key] != expected_value:
                raise TraceabilityError(
                    f"source brief {identifier} {key} mismatch: expected={expected_value!r} got={observed[key]!r}"
                )


def check_requirement_inventory(
    requirements: dict[str, dict[str, Any]],
    human: dict[str, dict[str, str]],
) -> None:
    expected_total = sum(EXPECTED_PREFIX_COUNTS.values())
    if len(requirements) != expected_total:
        raise TraceabilityError(
            f"requirement count mismatch: expected={expected_total} got={len(requirements)}"
        )
    if set(requirements) != set(human):
        missing_machine = sorted(set(human) - set(requirements))
        missing_human = sorted(set(requirements) - set(human))
        raise TraceabilityError(
            "registry/Markdown requirement mismatch: "
            f"missing_machine={missing_machine}, missing_human={missing_human}"
        )

    observed_counts: dict[str, int] = {}
    for identifier, requirement in requirements.items():
        prefix = identifier.split("-", 1)[0]
        observed_counts[prefix] = observed_counts.get(prefix, 0) + 1
        human_row = human[identifier]
        for key in ("summary", "acceptance", "status"):
            if requirement[key] != human_row[key]:
                raise TraceabilityError(
                    f"{identifier} machine/human {key} mismatch: "
                    f"machine={requirement[key]!r} human={human_row[key]!r}"
                )
    if observed_counts != EXPECTED_PREFIX_COUNTS:
        raise TraceabilityError(
            f"requirement prefix counts mismatch: expected={EXPECTED_PREFIX_COUNTS} got={observed_counts}"
        )


def existing_file(root: pathlib.Path, relative: str, context: str) -> None:
    if not (root / relative).is_file():
        raise TraceabilityError(f"{context} points to missing file: {relative}")


def check_tests_and_evidence(
    root: pathlib.Path,
    registry: dict[str, Any],
    requirements: dict[str, dict[str, Any]],
    tests: dict[str, dict[str, Any]],
) -> None:
    legacy_prefix = registry["legacy_evidence_policy"]["legacy_prefix"]
    for identifier, requirement in requirements.items():
        for relative in requirement["implementation"]:
            existing_file(root, relative, f"requirement {identifier} implementation")
        for relative in requirement["evidence"]:
            if relative.startswith(legacy_prefix):
                raise TraceabilityError(
                    f"requirement {identifier} places legacy artifact in fresh V1 evidence: {relative}"
                )
            existing_file(root, relative, f"requirement {identifier} evidence")
        for relative in requirement["legacy_evidence"]:
            if not relative.startswith(legacy_prefix):
                raise TraceabilityError(
                    f"requirement {identifier} legacy evidence lacks {legacy_prefix!r} prefix: {relative}"
                )
            existing_file(root, relative, f"requirement {identifier} legacy evidence")

        for test_id in requirement["test_ids"]:
            if test_id not in tests:
                raise TraceabilityError(f"requirement {identifier} names unknown test {test_id}")
            if identifier not in tests[test_id]["requirement_ids"]:
                raise TraceabilityError(
                    f"test {test_id} lacks reverse mapping to requirement {identifier}"
                )
        if requirement["release_scope"] == "POST_V1":
            for test_id in requirement["test_ids"]:
                if tests[test_id]["status"] != "DEFERRED":
                    raise TraceabilityError(
                        f"post-V1 requirement {identifier} maps to nondeferred test {test_id}"
                    )
        elif any(tests[test_id]["status"] == "DEFERRED" for test_id in requirement["test_ids"]):
            raise TraceabilityError(f"V1 requirement {identifier} maps to a deferred test")

        if requirement["status"] == "PASS":
            if not requirement["evidence"]:
                raise TraceabilityError(f"passing requirement {identifier} lacks fresh V1 evidence")
            nonpassing_tests = [
                test_id for test_id in requirement["test_ids"] if tests[test_id]["status"] != "PASS"
            ]
            if nonpassing_tests:
                raise TraceabilityError(
                    f"passing requirement {identifier} has nonpassing tests: {nonpassing_tests}"
                )

    for test_id, test in tests.items():
        if test["runner"] is not None:
            existing_file(root, test["runner"], f"test {test_id} runner")
        for relative in test["evidence"]:
            if relative.startswith(legacy_prefix):
                raise TraceabilityError(
                    f"test {test_id} places legacy artifact in fresh V1 evidence: {relative}"
                )
            existing_file(root, relative, f"test {test_id} evidence")
        for requirement_id in test["requirement_ids"]:
            if requirement_id not in requirements:
                raise TraceabilityError(f"test {test_id} names unknown requirement {requirement_id}")
            if test_id not in requirements[requirement_id]["test_ids"]:
                raise TraceabilityError(
                    f"requirement {requirement_id} lacks reverse mapping to test {test_id}"
                )
        if test["status"] in {"IMPLEMENTED", "PASS"} and test["runner"] is None:
            raise TraceabilityError(f"{test['status'].lower()} test {test_id} lacks a runner")


def check_defects(
    root: pathlib.Path,
    ledger: dict[str, Any],
    requirements: dict[str, dict[str, Any]],
) -> tuple[int, int]:
    entries = unique_index(ledger["entries"], "defect")
    defects = 0
    divergences = 0
    release_blocking = 0
    nonclosed = 0
    known_gates = {f"G{number:02d}" for number in range(13)} | {"POST_V1"}
    for identifier, entry in entries.items():
        if entry["kind"] == "DEFECT":
            defects += 1
        else:
            divergences += 1
        if entry["status"] in NONCLOSED_DEFECT_STATUSES:
            nonclosed += 1
            if entry["blocks_release"]:
                release_blocking += 1
        for requirement_id in entry["affected_requirement_ids"]:
            if requirement_id not in requirements:
                raise TraceabilityError(
                    f"defect {identifier} names unknown requirement {requirement_id}"
                )
            if (
                entry["status"] in NONCLOSED_DEFECT_STATUSES
                and requirements[requirement_id]["status"] == "PASS"
            ):
                raise TraceabilityError(
                    f"nonclosed defect {identifier} affects passing requirement {requirement_id}"
                )
        unknown_gates = sorted(set(entry["affected_gates"]) - known_gates)
        if unknown_gates:
            raise TraceabilityError(f"defect {identifier} names unknown gates: {unknown_gates}")
        for field in ("reproducer", "evidence", "closure_evidence"):
            for relative in entry[field]:
                existing_file(root, relative, f"defect {identifier} {field}")
        if entry["regression_test"] is not None:
            existing_file(root, entry["regression_test"], f"defect {identifier} regression test")

    expected_counts = {
        "defects": defects,
        "divergences": divergences,
        "release_blocking": release_blocking,
        "total_nonclosed": nonclosed,
    }
    if ledger["open_counts"] != expected_counts:
        raise TraceabilityError(
            f"defect open_counts mismatch: expected={expected_counts} got={ledger['open_counts']}"
        )
    return nonclosed, release_blocking


def check_aggregates(
    registry: dict[str, Any],
    requirements: dict[str, dict[str, Any]],
    release_blocking_defects: int,
) -> None:
    aggregates = unique_index(
        [dict(item, id=item["requirement_id"]) for item in registry["aggregate_dependencies"]],
        "aggregate",
    )
    done_ids = {identifier for identifier in requirements if identifier.startswith("DONE-")}
    if set(aggregates) != done_ids:
        raise TraceabilityError(
            f"DONE aggregate set mismatch: missing={sorted(done_ids - set(aggregates))}, "
            f"stale={sorted(set(aggregates) - done_ids)}"
        )
    expected_done_001 = {
        identifier
        for identifier, requirement in requirements.items()
        if requirement["release_scope"] == "V1" and not identifier.startswith("DONE-")
    }
    if set(aggregates["DONE-001"]["dependency_ids"]) != expected_done_001:
        raise TraceabilityError("DONE-001 does not depend on every nonaggregate V1 requirement")

    for identifier, aggregate in aggregates.items():
        dependencies = aggregate["dependency_ids"]
        for dependency_id in dependencies:
            if dependency_id not in requirements:
                raise TraceabilityError(
                    f"aggregate {identifier} names unknown dependency {dependency_id}"
                )
            if dependency_id == identifier:
                raise TraceabilityError(f"aggregate {identifier} depends on itself")
        if requirements[identifier]["status"] == "PASS":
            nonpassing = [
                dependency_id
                for dependency_id in dependencies
                if requirements[dependency_id]["status"] != "PASS"
            ]
            if nonpassing:
                raise TraceabilityError(
                    f"passing aggregate {identifier} has nonpassing dependencies: {nonpassing}"
                )
            if aggregate["requires_zero_release_blocking_defects"] and release_blocking_defects:
                raise TraceabilityError(
                    f"passing aggregate {identifier} has {release_blocking_defects} release-blocking defects"
                )


def validate(
    root: pathlib.Path,
    registry_path: pathlib.Path,
    requirement_schema_path: pathlib.Path,
    ledger_path: pathlib.Path,
    defect_schema_path: pathlib.Path,
    markdown_path: pathlib.Path,
) -> ValidationSummary:
    root = root.resolve(strict=True)
    registry = load_json(registry_path)
    requirement_schema = load_json(requirement_schema_path)
    ledger = load_json(ledger_path)
    defect_schema = load_json(defect_schema_path)
    validate_schema(registry, requirement_schema)
    validate_schema(ledger, defect_schema)
    check_schema_digest(registry, requirement_schema_path, "requirement registry")
    check_schema_digest(ledger, defect_schema_path, "defect ledger")
    check_source_briefs(registry)

    requirements = unique_index(registry["requirements"], "requirement")
    tests = unique_index(registry["tests"], "test")
    human = parse_human_requirements(markdown_path)
    check_requirement_inventory(requirements, human)
    check_tests_and_evidence(root, registry, requirements, tests)
    nonclosed_defects, release_blocking_defects = check_defects(root, ledger, requirements)
    check_aggregates(registry, requirements, release_blocking_defects)
    return ValidationSummary(
        requirements=len(requirements),
        tests=len(tests),
        requirements_passed=sum(item["status"] == "PASS" for item in requirements.values()),
        post_v1_deferred=sum(
            item["status"] == "DEFERRED_POST_V1" for item in requirements.values()
        ),
        nonclosed_defects=nonclosed_defects,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--registry", type=pathlib.Path)
    parser.add_argument("--requirement-schema", type=pathlib.Path)
    parser.add_argument("--ledger", type=pathlib.Path)
    parser.add_argument("--defect-schema", type=pathlib.Path)
    parser.add_argument("--markdown", type=pathlib.Path)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    registry = args.registry or root / "docs/project/requirements-v1.json"
    requirement_schema = args.requirement_schema or root / "docs/project/schema/requirements-v1.schema.json"
    ledger = args.ledger or root / "docs/project/defects-v1.json"
    defect_schema = args.defect_schema or root / "docs/project/schema/defect-ledger-v1.schema.json"
    markdown = args.markdown or root / "docs/project/REQUIREMENTS.md"
    try:
        summary = validate(root, registry, requirement_schema, ledger, defect_schema, markdown)
    except (
        OSError,
        json.JSONDecodeError,
        jsonschema.SchemaError,
        jsonschema.ValidationError,
        TraceabilityError,
    ) as exc:
        print(f"V1 traceability validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        "V1_TRACEABILITY=PASS "
        f"requirements={summary.requirements} tests={summary.tests} "
        f"requirements_passed={summary.requirements_passed} "
        f"post_v1_deferred={summary.post_v1_deferred} "
        f"nonclosed_defects={summary.nonclosed_defects}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
