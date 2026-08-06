#!/usr/bin/env python3
"""Common mechanical validation and fresh-fixture tests for M22 evaluation."""

from __future__ import annotations

import copy
import dataclasses
import json
import pathlib
import tempfile
import unittest
from collections.abc import Callable
from types import ModuleType
from typing import Any

import run_m22_final_evaluation as final_runner
import run_m22_followup_evaluation as followup_runner
import run_m22_followup_v2_evaluation as followup_v2_runner
import validate_m22_final_evaluation as final_validator
import validate_m22_followup_evaluation as followup_validator
import validate_m22_followup_v2_evaluation as followup_v2_validator
import m22_evaluation_validation as common
from tests.project.v2 import m22_fixture_support as fixtures


@dataclasses.dataclass(frozen=True)
class SuiteSpec:
    label: str
    message_prefix: str
    mechanics: ModuleType
    validator: ModuleType
    manifest_path: pathlib.Path
    expected: dict[str, object]
    native_processes: int


def _change_path(value: dict[str, Any]) -> None:
    value["files"][0]["path"] = "scripts/v2/not-the-frozen-source.py"


def _reverse_source_order(value: dict[str, Any]) -> None:
    value["files"][0], value["files"][1] = value["files"][1], value["files"][0]


def _change_source_sha(value: dict[str, Any]) -> None:
    value["files"][0]["sha256"] = "0" * 64


def _change_inventory_sha(value: dict[str, Any]) -> None:
    value["tree_sha256"] = "0" * 64


def _change_commit(value: dict[str, Any]) -> None:
    value["repository_commit"] = "not-a-commit"


def _change_tree(value: dict[str, Any]) -> None:
    value["repository_tree"] = "0" * 40


class M22EvaluationCommonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.suites = (
            SuiteSpec(
                "final-v1", "M22 final", final_runner, final_validator,
                final_runner.learning.EVALUATION,
                {"cases": 42, "failures": 10, "live": False, "status": "FAIL"},
                34,
            ),
            SuiteSpec(
                "follow-up-v1", "M22 follow-up", followup_runner, followup_validator,
                followup_runner.MANIFEST,
                {"cases": 42, "failures": 0, "live": False, "status": "FAIL"},
                42,
            ),
            SuiteSpec(
                "follow-up-v2", "M22 follow-up-v2", followup_v2_runner,
                followup_v2_validator, followup_v2_runner.MANIFEST,
                {"cases": 42, "failures": 0, "live": False, "status": "PASS"},
                42,
            ),
        )

    def require_common(self) -> ModuleType:
        return common

    def require_fixtures(self) -> ModuleType:
        return fixtures

    def report(self, spec: SuiteSpec) -> dict[str, Any]:
        return spec.validator.load(self.root / spec.validator.CONFIG)

    def cases(self, spec: SuiteSpec) -> list[dict[str, Any]]:
        return json.loads((self.root / spec.manifest_path).read_bytes())["cases"]

    def test_json_and_schema_helpers_preserve_requested_error_type(self) -> None:
        mechanics = self.require_common()
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "value.json"
            path.write_text('{"answer": 42}\n', encoding="utf-8")
            self.assertEqual(
                mechanics.load_json_object(path, error_type=final_validator.M22FinalEvidenceError),
                {"answer": 42},
            )
            path.write_text("[]\n", encoding="utf-8")
            with self.assertRaisesRegex(final_validator.M22FinalEvidenceError, "root is not an object"):
                mechanics.load_json_object(path, error_type=final_validator.M22FinalEvidenceError)
        with self.assertRaisesRegex(followup_validator.M22FollowupEvidenceError,
                                    "fixture schema failed at value"):
            mechanics.validate_schema(
                {"value": "wrong"},
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {"value": {"type": "integer"}},
                },
                "fixture", error_type=followup_validator.M22FollowupEvidenceError,
            )

    def test_frozen_source_identity_validates_for_every_suite(self) -> None:
        mechanics = self.require_common()
        for spec in self.suites:
            with self.subTest(suite=spec.label):
                mechanics.validate_source_identity(
                    self.report(spec)["source"], self.root,
                    mechanics=spec.mechanics, suite_label=spec.message_prefix,
                    require=spec.validator.require,
                )

    def test_source_path_order_hash_commit_and_tree_mutations_fail_for_every_suite(self) -> None:
        mechanics = self.require_common()
        support = self.require_fixtures()
        mutations = (
            support.MutationCase("path", _change_path, "source inventory/order drifted"),
            support.MutationCase("order", _reverse_source_order, "source inventory/order drifted"),
            support.MutationCase("sha256", _change_source_sha, "source identity drifted"),
            support.MutationCase("inventory-sha256", _change_inventory_sha,
                                 "source inventory digest drifted"),
            support.MutationCase("commit", _change_commit, "historical source is unavailable"),
            support.MutationCase("tree", _change_tree, "source repository identity drifted"),
        )
        for spec in self.suites:
            with self.subTest(suite=spec.label):
                error_type = {
                    "final-v1": final_validator.M22FinalEvidenceError,
                    "follow-up-v1": followup_validator.M22FollowupEvidenceError,
                    "follow-up-v2": followup_v2_validator.M22FollowupV2EvidenceError,
                }[spec.label]

                def reject(value: dict[str, Any], pattern: str, live: bool) -> None:
                    self.assertFalse(live)
                    with self.assertRaisesRegex(error_type, pattern):
                        mechanics.validate_source_identity(
                            value, self.root, mechanics=spec.mechanics,
                            suite_label=spec.message_prefix, require=spec.validator.require,
                        )

                support.run_named_mutations(self, self.report(spec)["source"], mutations, reject)

    def test_followup_v2_main_synchronization_mutation_fails(self) -> None:
        mechanics = self.require_common()
        value = copy.deepcopy(self.report(self.suites[2])["source"])
        value["main_synchronized"] = False
        with self.assertRaisesRegex(followup_v2_validator.M22FollowupV2EvidenceError,
                                    "source repository identity drifted"):
            mechanics.validate_source_identity(
                value, self.root, mechanics=followup_v2_runner,
                suite_label="M22 follow-up-v2", require=followup_v2_validator.require,
            )

    def test_report_digest_mutation_fails_for_every_suite(self) -> None:
        mechanics = self.require_common()
        for spec in self.suites:
            with self.subTest(suite=spec.label):
                report = self.report(spec)
                mechanics.validate_report_digest(
                    report, mechanics=spec.mechanics, suite_label=spec.message_prefix,
                    require=spec.validator.require,
                )
                report["report_sha256"] = "0" * 64
                error_type = {
                    "final-v1": final_validator.M22FinalEvidenceError,
                    "follow-up-v1": followup_validator.M22FollowupEvidenceError,
                    "follow-up-v2": followup_v2_validator.M22FollowupV2EvidenceError,
                }[spec.label]
                with self.assertRaisesRegex(error_type, "report digest drifted"):
                    mechanics.validate_report_digest(
                        report, mechanics=spec.mechanics, suite_label=spec.message_prefix,
                        require=spec.validator.require,
                    )

    def test_aggregate_records_preserve_outcomes_and_one_shot_protocol(self) -> None:
        mechanics = self.require_common()
        for spec in self.suites:
            with self.subTest(suite=spec.label):
                report = self.report(spec)
                protocol = report["protocol"]
                self.assertEqual(
                    (protocol["cases_attempted"], protocol["evaluator_processes"],
                     protocol["native_dispatches"], protocol["native_processes"],
                     protocol["manifest_reads"]),
                    (42, 42, 42, spec.native_processes, 1),
                )
                self.assertEqual((protocol["retries"], protocol["replacements"]), (0, 0))
                self.assertFalse(protocol["post_result_selection"])
                self.assertEqual(
                    mechanics.validate_aggregate_records(
                        report, self.cases(spec), mechanics=spec.mechanics,
                        suite_label=spec.message_prefix, live=False,
                        require=spec.validator.require,
                    ),
                    spec.expected,
                )

    def test_aggregate_protocol_mutations_fail_for_every_suite(self) -> None:
        mechanics = self.require_common()
        support = self.require_fixtures()

        def set_protocol(field: str, value: object) -> Callable[[dict[str, Any]], None]:
            def mutate(report: dict[str, Any]) -> None:
                report["protocol"][field] = value
            return mutate

        mutations = (
            support.MutationCase("manifest-reads", set_protocol("manifest_reads", 2),
                                 "protocol accounting drifted"),
            support.MutationCase("evaluator-processes", set_protocol("evaluator_processes", 41),
                                 "protocol accounting drifted"),
            support.MutationCase("native-processes", set_protocol("native_processes", 41),
                                 "protocol accounting drifted"),
            support.MutationCase("retry", set_protocol("retries", 1), "protocol accounting drifted"),
            support.MutationCase("replacement", set_protocol("replacements", 1),
                                 "protocol accounting drifted"),
            support.MutationCase("post-selection", set_protocol("post_result_selection", True),
                                 "protocol accounting drifted"),
        )
        for spec in self.suites:
            error_type = {
                "final-v1": final_validator.M22FinalEvidenceError,
                "follow-up-v1": followup_validator.M22FollowupEvidenceError,
                "follow-up-v2": followup_v2_validator.M22FollowupV2EvidenceError,
            }[spec.label]
            with self.subTest(suite=spec.label):
                def reject(value: dict[str, Any], pattern: str, live: bool) -> None:
                    self.assertFalse(live)
                    with self.assertRaisesRegex(error_type, pattern):
                        mechanics.validate_aggregate_records(
                            value, self.cases(spec), mechanics=spec.mechanics,
                            suite_label=spec.message_prefix, live=False,
                            require=spec.validator.require,
                        )

                support.run_named_mutations(self, self.report(spec), mutations, reject)

    def test_fixture_factories_return_fresh_42_run_reports(self) -> None:
        support = self.require_fixtures()
        case = support.make_case("fixture-case", private_seed=17)
        run_a = support.make_run(final_runner, case, 0)
        run_b = support.make_run(final_runner, case, 0)
        run_a["evaluator"]["process"]["attempt"] = 9
        self.assertEqual(run_b["evaluator"]["process"]["attempt"], 1)
        self.assertEqual(case["seed"], 17)

        spec = {
            "case_id_prefix": "fixture-case",
            "private_seed": 17,
            "source_file_sha256": "7" * 64,
            "report": {
                "artifact_root": "/retained/fixture",
                "identity": {},
                "manifest": {},
                "schema_version": "fixture-1",
                "source": {
                    "clean": True, "repository_commit": "8" * 40,
                    "repository_tree": "9" * 40, "tree_sha256": "a" * 64,
                },
            },
        }
        first = support.make_report(final_runner, spec)
        second = support.make_report(final_runner, spec)
        self.assertEqual(len(first["runs"]), 42)
        self.assertEqual(len({id(run) for run in first["runs"]}), 42)
        self.assertEqual(len({id(run["evaluator"]) for run in first["runs"]}), 42)
        self.assertEqual(len({id(run["native"]) for run in first["runs"]}), 42)
        first["runs"][0]["public_case"]["task"] = "mutated"
        self.assertEqual(first["runs"][1]["public_case"]["task"], "service")
        self.assertEqual(second["runs"][0]["public_case"]["task"], "service")
        self.assertEqual(spec["report"]["source"].get("files"), None)

    def test_named_mutations_are_isolated_and_leave_base_unchanged(self) -> None:
        support = self.require_fixtures()
        base = {"nested": {"values": ["base"]}}
        observed: list[tuple[list[str], str, bool]] = []

        def first(value: dict[str, Any]) -> None:
            value["nested"]["values"].append("first")

        def second(value: dict[str, Any]) -> None:
            self.assertEqual(value, base)
            value["nested"]["values"].append("second")

        def reject(value: dict[str, Any], pattern: str, live: bool) -> None:
            observed.append((copy.deepcopy(value["nested"]["values"]), pattern, live))

        support.run_named_mutations(
            self, base,
            (
                support.MutationCase("first", first, "first-error"),
                support.MutationCase("second", second, "second-error", live=True),
            ),
            reject,
        )
        self.assertEqual(base, {"nested": {"values": ["base"]}})
        self.assertEqual(
            observed,
            [(["base", "first"], "first-error", False),
             (["base", "second"], "second-error", True)],
        )


if __name__ == "__main__":
    unittest.main()
