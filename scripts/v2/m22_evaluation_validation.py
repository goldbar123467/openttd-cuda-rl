#!/usr/bin/env python3
"""Shared mechanical validation for the three retained M22 evaluations."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import re
from collections.abc import Callable, Sequence
from typing import Any, Literal, Protocol

import jsonschema

from source_context import SourceContextError, run_git


Require = Callable[[bool, str], None]


class _CommitTreeError(Exception):
    """A neutral commit-tree failure for suite-local diagnostic translation."""

    def __init__(self, reason: Literal["identity", "no-tree"]) -> None:
        self.reason = reason
        super().__init__(reason)


class EvaluationMechanics(Protocol):
    SOURCE_PATHS: Sequence[str]
    FAILURES: Sequence[str]

    @staticmethod
    def canonical_bytes(value: object) -> bytes: ...

    @staticmethod
    def sha256_bytes(value: bytes) -> str: ...

    @staticmethod
    def protocol_record(runs: list[dict[str, Any]], case_ids: list[str]) -> dict[str, Any]: ...

    @staticmethod
    def aggregate_statistics(runs: list[dict[str, Any]]) -> dict[str, Any]: ...

    @staticmethod
    def acceptance(
        runs: list[dict[str, Any]], statistics: dict[str, Any], protocol: dict[str, Any],
    ) -> dict[str, Any]: ...


def load_json_object(path: pathlib.Path, *, error_type: type[Exception]) -> dict[str, Any]:
    """Load one finite JSON object, raising the caller's public error type."""

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"nonfinite JSON constant: {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise error_type(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise error_type(f"JSON root is not an object: {path}")
    return value


def validate_schema(
    value: object,
    schema: dict[str, Any],
    label: str,
    *,
    error_type: type[Exception],
) -> None:
    """Validate with Draft 2020-12 while preserving the suite error contract."""

    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
    except (jsonschema.SchemaError, TypeError) as exc:
        raise error_type(f"{label} schema is invalid") from exc
    try:
        validator.validate(value)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise error_type(f"{label} schema failed at {where}: {exc.message}") from exc
    except TypeError as exc:
        raise error_type(f"{label} schema is invalid") from exc


def historical_blob(
    root: pathlib.Path,
    commit: str,
    path: str,
    require: Require,
) -> bytes:
    """Read a traversal-safe blob from one recorded Git commit."""

    require(
        isinstance(path, str)
        and bool(path)
        and not path.startswith("/")
        and "\\" not in path
        and "\x00" not in path
        and all(part not in {"", ".", ".."} for part in path.split("/")),
        "historical source path is not a safe relative POSIX path",
    )
    try:
        completed = run_git("show", f"{commit}:{path}", repository=root)
    except SourceContextError as exc:
        require(False, f"historical source is unavailable: {path}: {exc}")
        raise AssertionError("require() returned after rejecting unavailable historical source")
    require(completed.returncode == 0, f"historical source is unavailable: {path}")
    return completed.stdout


def _commit_tree(
    root: pathlib.Path,
    commit: str,
    suite_label: str,
    require: Require,
) -> str:
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
            f"{suite_label} source commit is malformed")
    try:
        exists = run_git("cat-file", "-e", f"{commit}^{{commit}}", repository=root)
        body = run_git("cat-file", "-p", commit, repository=root)
    except SourceContextError as exc:
        require(False, f"{suite_label} source repository identity is unavailable: {exc}")
        raise AssertionError("require() returned after rejecting unavailable source repository")
    first = body.stdout.splitlines()[0] if body.stdout else b""
    if exists.returncode != 0 or body.returncode != 0:
        raise _CommitTreeError("identity")
    if not first.startswith(b"tree "):
        raise _CommitTreeError("no-tree")
    return first.removeprefix(b"tree ").decode("ascii")


def validate_source_identity(
    value: dict[str, Any],
    root: pathlib.Path,
    mechanics: EvaluationMechanics,
    suite_label: str,
    require: Require,
) -> None:
    """Validate historical paths, blobs, inventory digest, commit, and tree."""

    require(
        isinstance(value, dict) and isinstance(value.get("files"), list),
        f"{suite_label} source identity is malformed",
    )
    files = value["files"]
    require(
        [item.get("path") for item in files if isinstance(item, dict)]
        == list(mechanics.SOURCE_PATHS),
        f"{suite_label} source inventory/order drifted",
    )
    commit = value.get("repository_commit")
    require(isinstance(commit, str), f"{suite_label} source commit is malformed")

    def suite_require(condition: bool, message: str) -> None:
        require(condition, f"{suite_label} {message}")

    for record in files:
        require(
            isinstance(record, dict)
            and set(record) == {"path", "sha256"}
            and isinstance(record["sha256"], str),
            f"{suite_label} source file record is malformed",
        )
        require(
            hashlib.sha256(
                historical_blob(root, commit, record["path"], suite_require)
            ).hexdigest()
            == record["sha256"],
            f"{suite_label} source identity drifted: {record['path']}",
        )
    require(
        value["tree_sha256"] == mechanics.sha256_bytes(mechanics.canonical_bytes(files)),
        f"{suite_label} source inventory digest drifted",
    )
    require(
        _commit_tree(root, commit, suite_label, require) == value.get("repository_tree"),
        f"{suite_label} source repository identity drifted",
    )


def validate_report_digest(
    report: dict[str, Any],
    mechanics: EvaluationMechanics,
    suite_label: str,
    require: Require,
) -> None:
    """Recompute the canonical digest over the complete unsigned report."""

    unsigned = copy.deepcopy(report)
    claimed = unsigned.pop("report_sha256")
    require(
        claimed == mechanics.sha256_bytes(mechanics.canonical_bytes(unsigned)),
        f"{suite_label} report digest drifted",
    )


def validate_aggregate_records(
    report: dict[str, Any],
    cases: Sequence[dict[str, Any]],
    mechanics: EvaluationMechanics,
    suite_label: str,
    live: bool,
    require: Require,
) -> dict[str, Any]:
    """Recompute mechanical aggregate records and return the public summary."""

    runs = report["runs"]
    require(len(runs) == len(cases) == 42, f"{suite_label} run inventory drifted")
    expected_protocol = mechanics.protocol_record(
        runs, [case["case_id"] for case in cases]
    )
    require(
        report["protocol"] == expected_protocol,
        f"{suite_label} protocol accounting drifted",
    )
    expected_statistics = mechanics.aggregate_statistics(runs)
    require(report["statistics"] == expected_statistics, f"{suite_label} statistics drifted")
    expected_acceptance = mechanics.acceptance(runs, expected_statistics, expected_protocol)
    require(
        report["acceptance"] == expected_acceptance,
        f"{suite_label} acceptance recomputation drifted",
    )
    failure_counts = {
        category: sum(category in run["failures"] for run in runs)
        for category in mechanics.FAILURES
    }
    require(
        report["failure_counts"] == failure_counts,
        f"{suite_label} failure counts drifted",
    )
    require(
        report["status"] == ("PASS" if expected_acceptance["overall"] else "FAIL"),
        f"{suite_label} status drifted",
    )
    return {
        "cases": len(cases),
        "failures": sum(failure_counts.values()),
        "live": live,
        "status": report["status"],
    }
