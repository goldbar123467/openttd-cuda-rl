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
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest import mock

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

    def aggregate_record_mutations(self) -> tuple[fixtures.MutationCase, ...]:
        def mutate_statistics(report: dict[str, Any]) -> None:
            report["statistics"]["policies"][0]["statistics"]["mean"] += 1.0

        def mutate_acceptance(report: dict[str, Any]) -> None:
            report["acceptance"]["all_42_once"] = not report["acceptance"]["all_42_once"]

        def mutate_failure_counts(report: dict[str, Any]) -> None:
            category = next(iter(report["failure_counts"]))
            report["failure_counts"][category] += 1

        def mutate_status(report: dict[str, Any]) -> None:
            report["status"] = "PASS" if report["status"] == "FAIL" else "FAIL"

        return (
            fixtures.MutationCase("statistics", mutate_statistics, "statistics drifted"),
            fixtures.MutationCase(
                "acceptance", mutate_acceptance, "acceptance recomputation drifted",
            ),
            fixtures.MutationCase(
                "failure-counts", mutate_failure_counts, "failure counts drifted",
            ),
            fixtures.MutationCase("status", mutate_status, "status drifted"),
        )

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

    def test_malformed_schema_uses_requested_error_type_at_common_and_public_boundaries(self) -> None:
        mechanics = self.require_common()

        def assert_requested_error(call: Callable[[], None], pattern: str) -> None:
            try:
                call()
            except final_validator.M22FinalEvidenceError as exc:
                self.assertRegex(str(exc), pattern)
            except Exception as exc:  # pragma: no cover - the assertion reports the leaked type
                self.fail(f"schema boundary leaked {type(exc).__name__}: {exc}")
            else:
                self.fail("malformed schema was accepted")

        invalid_schema = {"type": 3}
        assert_requested_error(
            lambda: mechanics.validate_schema(
                {}, invalid_schema, "common fixture",
                error_type=final_validator.M22FinalEvidenceError,
            ),
            "common fixture schema is invalid",
        )
        assert_requested_error(
            lambda: final_validator.schema_validate({}, invalid_schema, "public fixture"),
            "public fixture schema is invalid",
        )

        report = final_validator.load(self.root / final_validator.CONFIG)
        manifest_bytes = (self.root / final_runner.learning.EVALUATION).read_bytes()
        manifest = json.loads(manifest_bytes)
        original_load = final_validator.load

        def load_with_invalid_schema(path: pathlib.Path) -> dict[str, Any]:
            if path == self.root / final_runner.EVIDENCE_SCHEMA:
                return invalid_schema
            return original_load(path)

        with mock.patch.object(final_validator, "load", side_effect=load_with_invalid_schema):
            assert_requested_error(
                lambda: final_validator.validate_value(
                    report, self.root, manifest_value=manifest,
                    manifest_bytes=manifest_bytes,
                ),
                "M22 final evaluation evidence schema is invalid",
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

    def test_followup_v1_source_policy_ignores_incidental_runner_attributes(self) -> None:
        setattr(followup_runner, "source_is_synchronized_main", lambda *_: True)
        try:
            try:
                followup_validator.validate_source(
                    self.report(self.suites[1])["source"], self.root,
                )
            except Exception as exc:  # pragma: no cover - the assertion reports the leaked policy
                self.fail(f"incidental runner attribute changed source policy: {exc}")
        finally:
            delattr(followup_runner, "source_is_synchronized_main")

    def test_followup_v2_local_synchronization_policy_survives_runner_attribute_removal(self) -> None:
        value = copy.deepcopy(self.report(self.suites[2])["source"])
        value["main_synchronized"] = False
        synchronization_helper = followup_v2_runner.source_is_synchronized_main
        delattr(followup_v2_runner, "source_is_synchronized_main")
        try:
            with self.assertRaisesRegex(
                followup_v2_validator.M22FollowupV2EvidenceError,
                "M22 follow-up-v2 source repository identity drifted",
            ):
                followup_v2_validator.validate_source(value, self.root)
        finally:
            setattr(
                followup_v2_runner,
                "source_is_synchronized_main",
                synchronization_helper,
            )

    def test_common_commit_tree_failure_is_neutral_across_suite_labels(self) -> None:
        mechanics = self.require_common()
        internal_error = getattr(mechanics, "_CommitTreeError", None)
        self.assertIsNotNone(internal_error, "common commit-tree failure must be structured")
        source = self.report(self.suites[0])["source"]
        commit = source["repository_commit"]
        blobs = {
            record["path"]: mechanics.historical_blob(
                self.root, commit, record["path"], final_validator.require,
            )
            for record in source["files"]
        }

        def fake_git(*arguments: str, repository: pathlib.Path) -> SimpleNamespace:
            self.assertEqual(repository, self.root)
            if arguments[1] == "-e":
                return SimpleNamespace(returncode=0, stdout=b"")
            return SimpleNamespace(returncode=0, stdout=b"author no-tree fixture\n")

        failures: list[Exception] = []
        with mock.patch.object(
            mechanics, "historical_blob",
            side_effect=lambda _root, _commit, path, _require: blobs[path],
        ), mock.patch.object(mechanics, "run_git", side_effect=fake_git):
            for label in ("M22 final", "unrelated suite label"):
                with self.subTest(label=label):
                    try:
                        mechanics.validate_source_identity(
                            source, self.root, mechanics=final_runner,
                            suite_label=label, require=final_validator.require,
                        )
                    except Exception as exc:
                        failures.append(exc)
                    else:
                        self.fail("tree-less commit was accepted")
        self.assertEqual(len(failures), 2)
        self.assertTrue(all(isinstance(exc, internal_error) for exc in failures))
        self.assertEqual(
            [getattr(exc, "reason", None) for exc in failures],
            ["no-tree", "no-tree"],
        )

    def test_suite_wrappers_translate_tree_less_commit_without_common_policy(self) -> None:
        mechanics = self.require_common()
        expectations = {
            "final-v1": (
                final_validator.M22FinalEvidenceError,
                "M22 final source commit has no tree",
            ),
            "follow-up-v1": (
                followup_validator.M22FollowupEvidenceError,
                "M22 follow-up source repository identity drifted",
            ),
            "follow-up-v2": (
                followup_v2_validator.M22FollowupV2EvidenceError,
                "M22 follow-up-v2 source repository identity drifted",
            ),
        }
        for spec in self.suites:
            with self.subTest(suite=spec.label):
                source = self.report(spec)["source"]
                commit = source["repository_commit"]
                blobs = {
                    record["path"]: mechanics.historical_blob(
                        self.root, commit, record["path"], spec.validator.require,
                    )
                    for record in source["files"]
                }

                def fake_git(*arguments: str, repository: pathlib.Path) -> SimpleNamespace:
                    self.assertEqual(repository, self.root)
                    if arguments[1] == "-e":
                        return SimpleNamespace(returncode=0, stdout=b"")
                    return SimpleNamespace(returncode=0, stdout=b"author no-tree fixture\n")

                error_type, pattern = expectations[spec.label]
                with mock.patch.object(
                    mechanics, "historical_blob",
                    side_effect=lambda _root, _commit, path, _require: blobs[path],
                ), mock.patch.object(mechanics, "run_git", side_effect=fake_git):
                    with self.assertRaisesRegex(error_type, pattern):
                        spec.validator.validate_source(source, self.root)

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
        value = copy.deepcopy(self.report(self.suites[2])["source"])
        value["main_synchronized"] = False
        with self.assertRaisesRegex(followup_v2_validator.M22FollowupV2EvidenceError,
                                    "source repository identity drifted"):
            followup_v2_validator.validate_source(value, self.root)

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

    def test_aggregate_record_mutation_inventory_covers_every_derived_record(self) -> None:
        self.assertEqual(
            {mutation.label for mutation in self.aggregate_record_mutations()},
            {"statistics", "acceptance", "failure-counts", "status"},
        )

    def test_aggregate_derived_record_mutations_fail_for_every_suite(self) -> None:
        mechanics = self.require_common()
        support = self.require_fixtures()
        error_types = {
            "final-v1": final_validator.M22FinalEvidenceError,
            "follow-up-v1": followup_validator.M22FollowupEvidenceError,
            "follow-up-v2": followup_v2_validator.M22FollowupV2EvidenceError,
        }
        for spec in self.suites:
            with self.subTest(suite=spec.label):
                def reject(value: dict[str, Any], pattern: str, live: bool) -> None:
                    self.assertFalse(live)
                    with self.assertRaisesRegex(error_types[spec.label], pattern):
                        mechanics.validate_aggregate_records(
                            value, self.cases(spec), mechanics=spec.mechanics,
                            suite_label=spec.message_prefix, live=False,
                            require=spec.validator.require,
                        )

                support.run_named_mutations(
                    self, self.report(spec), self.aggregate_record_mutations(), reject,
                )

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
