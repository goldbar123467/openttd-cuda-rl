#!/usr/bin/env python3
"""Fresh fixture factories and isolated named mutations for M22 evaluation tests."""

from __future__ import annotations

import copy
import dataclasses
import unittest
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol


class FixtureMechanics(Protocol):
    FAILURES: Sequence[str]
    PROGRAM_INDEX: Mapping[str, int]
    PREFLIGHT_CASE: dict[str, Any]
    SOURCE_PATHS: Sequence[str]

    @staticmethod
    def public_case(case: dict[str, Any]) -> dict[str, Any]: ...

    @staticmethod
    def public_program(case: dict[str, Any]) -> str: ...

    @staticmethod
    def case_scores(
        case: dict[str, Any], evaluator: dict[str, Any], native: dict[str, Any],
    ) -> dict[str, Any]: ...

    @staticmethod
    def failure_categories(
        case: dict[str, Any], evaluator: dict[str, Any], native: dict[str, Any],
        scores: dict[str, Any],
    ) -> list[str]: ...

    @staticmethod
    def protocol_record(runs: list[dict[str, Any]], case_ids: list[str]) -> dict[str, Any]: ...

    @staticmethod
    def aggregate_statistics(runs: list[dict[str, Any]]) -> dict[str, Any]: ...

    @staticmethod
    def acceptance(
        runs: list[dict[str, Any]], statistics: dict[str, Any], protocol: dict[str, Any],
    ) -> dict[str, Any]: ...

    @staticmethod
    def canonical_bytes(value: object) -> bytes: ...

    @staticmethod
    def sha256_bytes(value: bytes) -> str: ...


@dataclasses.dataclass(frozen=True)
class MutationCase:
    label: str
    mutate: Callable[[dict[str, Any]], None]
    error_pattern: str
    live: bool = False


def make_case(case_id: str, *, private_seed: int) -> dict[str, Any]:
    """Return one fresh representative evaluation case."""

    return {
        "case_id": case_id,
        "task": "service",
        "transport_mode": "road",
        "climate": "temperate",
        "map_width": 64,
        "map_height": 64,
        "cargo": "PASS",
        "opponent": "not-applicable",
        "seed": private_seed,
        "required_program": "road-passenger",
        "native_probe": "passenger-service",
        "source_gate": "G15",
    }


def make_run(
    mechanics: FixtureMechanics,
    case: dict[str, Any],
    ordinal: int,
) -> dict[str, Any]:
    """Return one fresh complete fake run derived from a private case."""

    private_case = copy.deepcopy(case)
    public = copy.deepcopy(mechanics.public_case(private_case))
    required_program = private_case["required_program"]
    evaluator = {
        "action": required_program,
        "action_index": mechanics.PROGRAM_INDEX[required_program],
        "failure_category": None,
        "failure_detail": None,
        "legal_active_program": mechanics.public_program(private_case),
        "process": {
            "attempt": 1,
            "exit_code": 0,
            "fresh_process": True,
            "launched": True,
            "network_unshared": True,
            "stderr_path": "evaluator.stderr",
            "stderr_sha256": "1" * 64,
            "stdout_path": "evaluator.stdout",
            "stdout_sha256": "2" * 64,
            "timed_out": False,
            "wall_seconds": 0.1,
        },
        "report_path": "evaluator-report.json",
        "report_sha256": "3" * 64,
        "status": "PASS",
    }
    metrics: dict[str, Any] = {"delivered": 8, "income": 45, "ticks": 100}
    if private_case["opponent"] != "not-applicable":
        metrics["opponent"] = private_case["opponent"]
    native_record = {
        "case": copy.deepcopy(public),
        "executable_sha256": "4" * 64,
        "fresh_processes": 1,
        "manifest_path": "manifest.json",
        "manifest_sha256": "5" * 64,
        "metrics": metrics,
        "native_probe": private_case["native_probe"],
        "network_unshared": True,
        "openttd_log_path": "openttd.log",
        "openttd_log_sha256": "6" * 64,
        "report_path": "report.json",
        "report_sha256": "7" * 64,
        "source_tree": "8" * 40,
        "status": "PASS",
        "wall_seconds": 0.2,
    }
    native_result = {
        "artifact_inventory": [],
        "attempt": 1,
        "failure_category": None,
        "failure_detail": None,
        "record": native_record,
        "status": "PASS",
    }
    scores = mechanics.case_scores(private_case, evaluator, native_result)
    failures = mechanics.failure_categories(private_case, evaluator, native_result, scores)
    return {
        "artifact_path": f"cases/{ordinal:02d}-{private_case['case_id']}",
        "evaluator": evaluator,
        "failures": failures,
        "native": native_result,
        "ordinal": ordinal,
        "private_seed": private_case["seed"],
        "public_case": public,
        "required_program": required_program,
        "scores": scores,
    }


def make_report(
    mechanics: FixtureMechanics,
    spec: Mapping[str, Any],
) -> dict[str, Any]:
    """Return one fresh 42-run report around a suite-local report template."""

    copied = copy.deepcopy(dict(spec))
    case_prefix = copied["case_id_prefix"]
    private_seed = copied["private_seed"]
    report = copied["report"]
    source_file_sha256 = copied.get("source_file_sha256", "7" * 64)
    cases = [
        make_case(f"{case_prefix}-{ordinal:02d}", private_seed=private_seed)
        for ordinal in range(42)
    ]
    runs = [make_run(mechanics, case, ordinal) for ordinal, case in enumerate(cases)]
    protocol = mechanics.protocol_record(runs, [case["case_id"] for case in cases])
    statistics = mechanics.aggregate_statistics(runs)
    acceptance = mechanics.acceptance(runs, statistics, protocol)
    report["acceptance"] = acceptance
    report["failure_counts"] = {
        category: sum(category in run["failures"] for run in runs)
        for category in mechanics.FAILURES
    }
    report["preflight"] = {
        "evaluator": copy.deepcopy(runs[0]["evaluator"]),
        "public_case": copy.deepcopy(mechanics.public_case(mechanics.PREFLIGHT_CASE)),
    }
    report["protocol"] = protocol
    report["runs"] = runs
    report["source"]["files"] = [
        {"path": path, "sha256": source_file_sha256}
        for path in mechanics.SOURCE_PATHS
    ]
    report["statistics"] = statistics
    report["status"] = "PASS" if acceptance["overall"] else "FAIL"
    report["report_sha256"] = mechanics.sha256_bytes(mechanics.canonical_bytes(report))
    return report


def run_named_mutations(
    test: unittest.TestCase,
    base: dict[str, Any],
    cases: Sequence[MutationCase],
    reject: Callable[[dict[str, Any], str, bool], None],
) -> None:
    """Run every named mutation on an isolated copy and preserve the base."""

    original = copy.deepcopy(base)
    for mutation in cases:
        with test.subTest(label=mutation.label):
            value = copy.deepcopy(base)
            mutation.mutate(value)
            reject(value, mutation.error_pattern, mutation.live)
            test.assertEqual(base, original)
    test.assertEqual(base, original)
