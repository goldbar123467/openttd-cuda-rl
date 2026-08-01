#!/usr/bin/env python3
"""Compare two independent M02 feasibility runs at their canonical boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from typing import Any

import jsonschema


class M02ComparisonError(ValueError):
    """A run is invalid or canonical outputs are not reproducible."""


CANONICAL_FILES = (
    "map-feasibility-report.json",
    "map-feasibility-report.txt",
    "composed-source.json",
    "commands.json",
)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M02ComparisonError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise M02ComparisonError(f"{path}: top level must be an object")
    return value


def validate_report(run: pathlib.Path, schema: dict[str, Any]) -> dict[str, Any]:
    report = load_object(run / "map-feasibility-report.json")
    try:
        jsonschema.Draft202012Validator(schema).validate(report)
    except jsonschema.exceptions.ValidationError as exc:
        raise M02ComparisonError(
            f"{run.name} report schema validation failed: {exc.message}"
        ) from exc
    if report["result"] != "PASS":
        raise M02ComparisonError(f"{run.name} report is not PASS")
    return report


def compare(
    first: pathlib.Path,
    second: pathlib.Path,
    schema_path: pathlib.Path,
) -> dict[str, Any]:
    first = first.resolve()
    second = second.resolve()
    if first == second:
        raise M02ComparisonError("independent run roots must differ")
    if not first.is_dir() or not second.is_dir():
        raise M02ComparisonError("both independent run roots must exist")
    schema = load_object(schema_path.resolve())
    first_report = validate_report(first, schema)
    second_report = validate_report(second, schema)
    digests: dict[str, str] = {}
    for relative in CANONICAL_FILES:
        first_path = first / relative
        second_path = second / relative
        if not first_path.is_file() or not second_path.is_file():
            raise M02ComparisonError(f"canonical output is missing: {relative}")
        first_bytes = first_path.read_bytes()
        second_bytes = second_path.read_bytes()
        if first_bytes != second_bytes:
            raise M02ComparisonError(f"canonical output differs: {relative}")
        digests[relative] = hashlib.sha256(first_bytes).hexdigest()
    if first_report["report_identity_sha256"] != second_report["report_identity_sha256"]:
        raise M02ComparisonError("report identities differ")
    for profile in first_report["profiles"]:
        profile_id = profile["id"]
        other = next(item for item in second_report["profiles"] if item["id"] == profile_id)
        for binary in ("binary_sha256", "test_binary_sha256"):
            if profile[binary] != other[binary]:
                raise M02ComparisonError(
                    f"{profile_id} {binary} differs between independent builds"
                )
    comparison_base = {
        "schema_version": "openttd-rl-v1-m02-map-feasibility-comparison-1",
        "canonical_file_sha256": digests,
        "report_identity_sha256": first_report["report_identity_sha256"],
        "independent_runs": 2,
        "raw_save_note": (
            "OpenTTD unique session IDs make raw normal-game containers noncanonical; "
            "all serialized map chunks are compared by the canonical report."
        ),
        "result": "PASS",
    }
    comparison = dict(comparison_base)
    comparison["comparison_identity_sha256"] = hashlib.sha256(
        json.dumps(comparison_base, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return comparison


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", required=True, type=pathlib.Path)
    parser.add_argument("--second", required=True, type=pathlib.Path)
    parser.add_argument("--schema", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    options = parser.parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        result = compare(options.first, options.second, options.schema)
        if options.output.exists():
            raise M02ComparisonError(f"refusing to overwrite output: {options.output}")
        options.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (M02ComparisonError, OSError, UnicodeError) as exc:
        print(f"V1_M02_MAP_FEASIBILITY_REPRODUCIBILITY=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "V1_M02_MAP_FEASIBILITY_REPRODUCIBILITY=PASS "
        f"identity={result['comparison_identity_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
