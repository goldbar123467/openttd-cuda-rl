#!/usr/bin/env python3
"""Mutation tests for the retained passing M22 follow-up-v2 evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import jsonschema

import artifact_context
from artifact_context import ArtifactContext, ArtifactContextError
import run_m22_followup_v2_evaluation as runner
import validate_m22_followup_v2_evaluation as validator
from tests.project.v2.test_v2_m22_final_evaluation_source import make_relocated_evaluation_fixture


class M22FollowupV2EvaluationEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.report = validator.load(cls.root / validator.CONFIG)
        cls.artifact = pathlib.Path(cls.report["artifact_root"])
        cls.schema = validator.load(cls.root / runner.EVIDENCE_SCHEMA)

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "evidence.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def resign(value: dict[str, object]) -> None:
        unsigned = copy.deepcopy(value)
        unsigned.pop("report_sha256", None)
        value["report_sha256"] = runner.sha256_bytes(runner.canonical_bytes(unsigned))

    def mutation_fails(self, value: dict[str, object], pattern: str, *, live: bool = False,
                       evaluator: bool = False) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw).resolve()
            if not live and not evaluator:
                with self.assertRaisesRegex(validator.M22FollowupV2EvidenceError, pattern):
                    validator.validate(
                        self.root, self.write(directory, value),
                        artifact_context=ArtifactContext.offline(),
                    )
                return
            project, evidence, live_inputs = make_relocated_evaluation_fixture(
                self.root, directory, self.report, runner_module=runner,
                validator_module=validator, logical_set=validator.RESULT_LOGICAL_SET,
            )
            staged = validator.load(evidence)
            if live:
                staged["runs"][0]["native"]["record"]["report_sha256"] = "0" * 64
            if evaluator:
                staged["identity"]["evaluator_executable_sha256"] = "0" * 64
            self.resign(staged)
            evidence.write_text(json.dumps(staged) + "\n", encoding="utf-8")
            with mock.patch.object(artifact_context.LiveInputManifest, "load", return_value=live_inputs):
                with self.assertRaisesRegex((validator.M22FollowupV2EvidenceError, ArtifactContextError), pattern):
                    validator.validate(
                        project, evidence, artifact_context=ArtifactContext.live(directory),
                        bwrap_path=pathlib.Path("/usr/bin/bwrap"),
                    )

    def test_live_evidence_and_every_retained_artifact_validate(self) -> None:
        if not self.artifact.is_dir() or not (self.artifact.parent / "v2-live-inputs.json").is_file():
            self.skipTest("retained follow-up-v2 artifacts are unavailable")
        result = validator.validate(
            self.root, artifact_context=ArtifactContext.live(self.artifact.parent),
            bwrap_path=pathlib.Path("/usr/bin/bwrap"),
        )
        self.assertEqual(result, {"cases": 42, "failures": 0, "live": True, "status": "PASS"})

    def test_every_frozen_acceptance_predicate_is_true(self) -> None:
        acceptance = self.report["acceptance"]
        self.assertTrue(all(acceptance.values()))
        self.assertTrue(acceptance["service_case_contract_exact"])
        self.assertTrue(acceptance["service_every_mode"])
        self.assertTrue(all(not run["failures"] for run in self.report["runs"]))
        self.assertTrue(all(run["scores"]["learned_correct"] for run in self.report["runs"]))
        self.assertTrue(all(run["native"]["status"] == "PASS" for run in self.report["runs"]))

    def test_multimodal_routing_cases_have_positive_native_service(self) -> None:
        cases = [run for run in self.report["runs"] if run["required_program"] == "multimodal-transfer"]
        self.assertEqual(len(cases), 2)
        for run in cases:
            self.assertEqual((run["public_case"]["task"], run["public_case"]["transport_mode"]),
                             ("routing", "multimodal"))
            self.assertGreater(run["native"]["record"]["metrics"]["delivered"], 0)
            self.assertGreater(run["native"]["record"]["metrics"]["income"], 0)

    def test_protocol_is_exactly_one_read_without_retry_or_replacement(self) -> None:
        protocol = self.report["protocol"]
        self.assertEqual((protocol["cases_attempted"], protocol["evaluator_processes"],
                          protocol["native_processes"], protocol["manifest_reads"]), (42, 42, 42, 1))
        self.assertEqual((protocol["retries"], protocol["replacements"]), (0, 0))
        self.assertFalse(protocol["post_result_selection"])
        self.assertEqual(self.report["source"]["repository_commit"],
                         "07b8967fa3d287bd6f7e8ca6bb61f27a5a013a69")
        self.assertTrue(self.report["source"]["main_synchronized"])

    def test_report_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.report)
        value["report_sha256"] = "0" * 64
        self.mutation_fails(value, "report digest drifted")

    def test_case_score_mutation_fails_after_valid_resigning(self) -> None:
        value = copy.deepcopy(self.report)
        value["runs"][0]["scores"]["learned_return"] = 0.0
        self.resign(value)
        self.mutation_fails(value, "case score drifted")

    def test_source_identity_mutation_fails_after_valid_resigning(self) -> None:
        value = copy.deepcopy(self.report)
        value["source"]["files"][0]["sha256"] = "0" * 64
        self.resign(value)
        self.mutation_fails(value, "source identity drifted")

    def test_native_artifact_digest_mutation_fails_live(self) -> None:
        value = copy.deepcopy(self.report)
        value["runs"][0]["native"]["record"]["report_sha256"] = "0" * 64
        self.resign(value)
        self.mutation_fails(value, "SHA-256 mismatch", live=True)

    def test_evaluator_executable_mutation_fails_live(self) -> None:
        value = copy.deepcopy(self.report)
        value["identity"]["evaluator_executable_sha256"] = "0" * 64
        self.resign(value)
        self.mutation_fails(value, "SHA-256 mismatch", evaluator=True)

    def test_final_v1_replacement_claim_fails_schema(self) -> None:
        value = copy.deepcopy(self.report)
        value["immutable_final_v1"]["followup_replaces_final_v1"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(value)

    def test_followup_v1_replacement_claim_fails_schema(self) -> None:
        value = copy.deepcopy(self.report)
        value["immutable_followup_v1"]["followup_v2_replaces_followup_v1"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(value)

    def test_retry_claim_fails_schema(self) -> None:
        value = copy.deepcopy(self.report)
        value["protocol"]["retries"] = 1
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(value)

    def test_offline_validation_does_not_resolve_evaluator(self) -> None:
        with mock.patch.object(
            artifact_context.LiveInputManifest,
            "load",
            side_effect=AssertionError("unexpected evaluator resolution"),
        ):
            result = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertEqual(result, {"cases": 42, "failures": 0, "live": False, "status": "PASS"})

    def test_offline_validation_does_not_resolve_bwrap(self) -> None:
        with mock.patch.object(
            artifact_context,
            "preflight_tools",
            side_effect=AssertionError("unexpected bwrap resolution"),
        ):
            result = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertEqual(result, {"cases": 42, "failures": 0, "live": False, "status": "PASS"})

    def test_relocated_live_root_preserves_frozen_passing_status(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            common_root = pathlib.Path(raw).resolve()
            project, evidence, live_inputs = make_relocated_evaluation_fixture(
                self.root, common_root, self.report, runner_module=runner,
                validator_module=validator, logical_set=validator.RESULT_LOGICAL_SET,
            )
            with mock.patch.object(
                artifact_context.LiveInputManifest, "load", return_value=live_inputs,
            ):
                result = validator.validate(
                    project, evidence,
                    artifact_context=ArtifactContext.live(common_root),
                    bwrap_path=pathlib.Path("/usr/bin/bwrap"),
                )
        self.assertEqual(result, {"cases": 42, "failures": 0, "live": True, "status": "PASS"})

    def test_required_live_input_closure_is_exact_unique_and_path_safe(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        self.assertEqual(len(requirements), 359 + 85)
        self.assertEqual(len(set(requirements)), len(requirements))
        self.assertEqual(
            {item.logical_set for item in requirements},
            {"v2-m21-broad-a", "v2-m22-followup-runtime-a", "v2-m22-followup-v2-evaluation-a"},
        )
        self.assertTrue(all(not pathlib.PurePosixPath(item.relative_path).is_absolute()
                            and ".." not in pathlib.PurePosixPath(item.relative_path).parts
                            for item in requirements))

    def test_all_42_native_results_receive_post_preflight_gate_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw).resolve()
            project, evidence, _ = make_relocated_evaluation_fixture(
                self.root, directory, self.report, runner_module=runner,
                validator_module=validator, logical_set=validator.RESULT_LOGICAL_SET,
                require_evaluator=False,
            )
            report = validator.load(evidence)
            context = ArtifactContext.live(directory)
            result_requirements = validator._result_requirements(report)
            context.preflight((*result_requirements, *runner.runtime_validator.required_live_inputs(project)))
            files = {item.relative_path: context.resolve(item) for item in result_requirements}
            runtime_source = validator.load(project / runner.RUNTIME_SOURCE)
            runtime = runner.runtime_paths(runtime_source, context)
            for run in report["runs"]:
                runner.final_evidence_validator.validate_preflighted_native(
                    project, run, run["artifact_path"], files, report["identity"], runtime_source, runtime,
                )
            self.assertEqual(
                {run["public_case"]["source_gate"] for run in report["runs"]},
                {f"G{gate}" for gate in range(15, 22)},
            )

    def test_post_preflight_native_semantics_reject_malformed_json_drift_and_invalid_save(self) -> None:
        mutations = (("G16", "report.json", b"{"), ("G21", "report.json", None),
                     ("G20", "report.json.sav", b"not-an-openttd-save"))
        for gate, relative, replacement in mutations:
            with self.subTest(gate=gate, relative=relative), tempfile.TemporaryDirectory() as raw:
                directory = pathlib.Path(raw).resolve()
                project, evidence, _ = make_relocated_evaluation_fixture(
                    self.root, directory, self.report, runner_module=runner,
                    validator_module=validator, logical_set=validator.RESULT_LOGICAL_SET,
                    require_evaluator=False,
                )
                report = validator.load(evidence)
                run = next(item for item in report["runs"] if item["public_case"]["source_gate"] == gate and
                           relative in {entry["path"] for entry in item["native"]["artifact_inventory"]})
                path = directory / validator.RESULT_LOGICAL_SET / run["artifact_path"] / "native" / relative
                payload = replacement
                if payload is None:
                    value = json.loads(path.read_bytes())
                    value["map"]["width"] += 1
                    payload = runner.canonical_bytes(value)
                path.write_bytes(payload)
                digest = hashlib.sha256(payload).hexdigest()
                record = next(item for item in run["native"]["artifact_inventory"] if item["path"] == relative)
                record.update({"bytes": len(payload), "sha256": digest})
                if relative == "report.json":
                    run["native"]["record"]["report_sha256"] = digest
                case_record = directory / validator.RESULT_LOGICAL_SET / run["artifact_path"] / "case-record.json"
                case_record.write_bytes(runner.canonical_bytes(run))
                context = ArtifactContext.live(directory)
                result_requirements = validator._result_requirements(report)
                context.preflight((*result_requirements, *runner.runtime_validator.required_live_inputs(project)))
                files = {item.relative_path: context.resolve(item) for item in result_requirements}
                runtime_source = validator.load(project / runner.RUNTIME_SOURCE)
                with self.assertRaisesRegex(
                    runner.final_evidence_validator.M22FinalEvidenceError, "(semantic|malformed|savegame)",
                ):
                    runner.final_evidence_validator.validate_preflighted_native(
                        project, run, run["artifact_path"], files, report["identity"], runtime_source,
                        runner.runtime_paths(runtime_source, context),
                    )


if __name__ == "__main__":
    unittest.main()
