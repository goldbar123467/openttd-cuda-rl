#!/usr/bin/env python3
"""Offline and mutation tests for M22's frozen follow-up one-shot runner."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import jsonschema

from artifact_context import ArtifactContext
import run_m22_followup_evaluation as runner
import validate_m22_followup_evaluation as validator
from tests.project.v2 import m22_fixture_support as fixture_support


class M22FollowupEvaluationSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.schema = validator.load(cls.root / runner.EVIDENCE_SCHEMA)

    @staticmethod
    def case(case_id: str = "followup-case-00") -> dict[str, object]:
        return fixture_support.make_case(case_id, private_seed=698564641)

    @classmethod
    def fake_run(cls, ordinal: int) -> dict[str, object]:
        return fixture_support.make_run(runner, cls.case(f"followup-case-{ordinal:02d}"), ordinal)

    @classmethod
    def fake_report(cls) -> dict[str, object]:
        return fixture_support.make_report(runner, {
            "case_id_prefix": "followup-case", "private_seed": 698564641,
            "source_file_sha256": "7" * 64,
            "report": {
                "artifact_root": "/retained/m22-followup",
                "identity": {
                    "aggregate_schema_sha256": "9" * 64, "bubblewrap_sha256": "a" * 64,
                    "checkpoint_id": "b" * 64, "evaluation_manifest_schema_sha256": "c" * 64,
                    "evaluator_executable_sha256": "d" * 64, "evaluator_report_schema_sha256": "e" * 64,
                    "immutable_final_v1_evidence_sha256": "f" * 64, "learning_contract_sha256": "0" * 64,
                    "native_executable_sha256": "1" * 64, "native_source_tree": "2" * 40,
                    "qualification_evidence_sha256": "3" * 64, "runtime_source_sha256": "4" * 64,
                },
                "immutable_final_v1": {
                    "cases_attempted": 42, "evidence_path": "config/v2/m22-final-evaluation-evidence.json",
                    "evidence_sha256": "5" * 64, "followup_replaces_final_v1": False,
                    "original_cases_reexecuted": 0, "status": "FAIL",
                },
                "manifest": {
                    "case_count": 42, "id": "m22-independent-followup-v1",
                    "path": "config/v2/m22-followup-manifest.json", "sha256": "6" * 64,
                },
                "schema_version": "openttd-rl-v2-m22-followup-evaluation-evidence-1",
                "source": {
                    "clean": True, "repository_commit": "8" * 40,
                    "repository_tree": "9" * 40, "tree_sha256": "a" * 64,
                },
            },
        })

    def test_public_offline_validation_rejects_malformed_result_descriptors_without_artifact_reads(self) -> None:
        original = validator.load(self.root / validator.CONFIG)
        manifest_bytes = (self.root / runner.MANIFEST).read_bytes()
        manifest = json.loads(manifest_bytes)

        def mutate(report: dict[str, object], kind: str) -> None:
            run = report["runs"][0]
            record = run["native"]["record"]
            inventory = run["native"]["artifact_inventory"]
            if kind == "root":
                report["artifact_root"] = "/wrong-logical-set"
            elif kind == "unsafe":
                inventory[0]["path"] = "../escape"
            elif kind == "alternate":
                record["report_path"] = "manifest.json"
                record["report_sha256"] = record["manifest_sha256"]
            elif kind == "unbound":
                record["report_sha256"] = "0" * 64
            else:
                inventory.append(copy.deepcopy(inventory[0]))

        for kind in ("root", "unsafe", "duplicate", "alternate", "unbound"):
            with self.subTest(kind=kind):
                report = copy.deepcopy(original)
                mutate(report, kind)
                unsigned = copy.deepcopy(report)
                unsigned.pop("report_sha256")
                report["report_sha256"] = runner.sha256_bytes(runner.canonical_bytes(unsigned))
                with mock.patch.object(ArtifactContext, "artifact_set",
                                       side_effect=AssertionError("offline artifact read")), \
                     mock.patch.object(ArtifactContext, "preflight",
                                       side_effect=AssertionError("offline artifact read")), \
                     mock.patch.object(ArtifactContext, "resolve",
                                       side_effect=AssertionError("offline artifact read")):
                    with self.assertRaisesRegex(validator.M22FollowupEvidenceError, "(native|artifact|closure)"):
                        validator.validate_value(
                            report, self.root, artifact_context=ArtifactContext.offline(),
                            manifest_value=manifest, manifest_bytes=manifest_bytes,
                        )

    def test_evaluator_identity_is_the_frozen_role_digest(self) -> None:
        report = validator.load(self.root / validator.CONFIG)
        report["identity"]["evaluator_executable_sha256"] = "0" * 64
        self.assertEqual(
            validator.expected_identity(self.root, report)["evaluator_executable_sha256"],
            runner.foundation.EVALUATOR_SHA256,
        )

    def test_aggregate_schema_is_closed_and_accepts_complete_report(self) -> None:
        jsonschema.Draft202012Validator.check_schema(self.schema)
        self.assertFalse(self.schema["additionalProperties"])
        jsonschema.Draft202012Validator(self.schema).validate(self.fake_report())

    def test_schema_rejects_missing_run_and_unknown_property(self) -> None:
        missing = self.fake_report()
        missing["runs"].pop()
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(missing)
        unknown = self.fake_report()
        unknown["runs"][0]["post_selected"] = False
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(unknown)

    def test_frozen_manifest_has_complete_mapping_and_corrected_competition(self) -> None:
        manifest = runner.manifest_validator.load(self.root / runner.MANIFEST)
        self.assertEqual(len(manifest["cases"]), 42)
        self.assertTrue(all(runner.public_program(case) == case["required_program"] for case in manifest["cases"]))
        competition = [case for case in manifest["cases"] if case["source_gate"] == "G20"]
        self.assertEqual(len(competition), 6)
        self.assertTrue(all((case["map_width"], case["map_height"]) == (128, 128) for case in competition))

    def test_evaluator_command_has_no_seed_or_required_program_channel(self) -> None:
        case = self.case()
        with tempfile.TemporaryDirectory() as raw:
            command = runner.evaluator_command(
                pathlib.Path("/usr/bin/bwrap"), self.root, pathlib.Path("/retained/m22-evaluator"),
                pathlib.Path("/retained/checkpoint"), pathlib.Path(raw), case, "cuda:0",
            )
        self.assertNotIn("--seed", command)
        self.assertNotIn("--required-program", command)
        self.assertNotIn(str(case["seed"]), command)
        self.assertNotIn(str(case["required_program"]), command)
        self.assertIn("--unshare-net", command)

    def test_baselines_are_public_only_deterministic_and_suite_distinct(self) -> None:
        first = self.case()
        second = copy.deepcopy(first)
        second["seed"] = 2_000_000_000
        second["required_program"] = "content-discovery"
        decisions = runner.baseline_decisions(first)
        self.assertEqual(decisions, runner.baseline_decisions(second))
        self.assertNotEqual(runner.random_legal_seed(first), runner.foundation.random_legal_seed(first))
        self.assertTrue(all(item["action"] in {"wait", "road-passenger"} for item in decisions))

    def test_statistics_retain_exact_42_case_student_t_boundary(self) -> None:
        result = runner.summary_stats([2.5] * 42)
        self.assertEqual((result["n"], result["mean"], result["ci95_lower"], result["ci95_upper"]),
                         (42, 2.5, 2.5, 2.5))
        self.assertEqual(result["t_critical_95"], 2.01954097)

    def test_wrong_learned_program_is_retained_without_suppressing_native(self) -> None:
        case = self.case()
        run = self.fake_run(0)
        evaluator = copy.deepcopy(run["evaluator"])
        evaluator["action"], evaluator["action_index"] = "wait", 0
        scores = runner.case_scores(case, evaluator, run["native"])
        failures = runner.failure_categories(case, evaluator, run["native"], scores)
        self.assertEqual(scores["learned_return"], 0.0)
        self.assertEqual(run["native"]["status"], "PASS")
        self.assertIn("learned-program-mismatch", failures)

    def test_independent_validator_recomputes_scores_and_failures(self) -> None:
        case = self.case()
        run = self.fake_run(0)
        evaluator_schema = validator.load(self.root / runner.EVALUATOR_SCHEMA)
        validator.validate_run(run, case, 0, {"checkpoint_id": "b" * 64}, None, evaluator_schema)
        mutated = copy.deepcopy(run)
        mutated["scores"]["learned_return"] = 0.0
        with self.assertRaisesRegex(validator.M22FollowupEvidenceError, "case score"):
            validator.validate_run(mutated, case, 0, {"checkpoint_id": "b" * 64}, None, evaluator_schema)

    def test_acceptance_fails_closed_on_missing_native_process(self) -> None:
        runs = [self.fake_run(index) for index in range(42)]
        protocol = runner.protocol_record(runs, [run["public_case"]["case_id"] for run in runs])
        statistics = runner.aggregate_statistics(runs)
        self.assertTrue(runner.acceptance(runs, statistics, protocol)["all_42_once"])
        protocol["native_processes"] -= 1
        self.assertFalse(runner.acceptance(runs, statistics, protocol)["all_42_once"])

    def test_runner_has_one_manifest_read_after_all_preflight_boundaries(self) -> None:
        source = (self.root / "scripts/v2/run_m22_followup_evaluation.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("manifest_path.read_bytes()"), 1)
        read = source.index("manifest_bytes = manifest_path.read_bytes()")
        start = source.index("def run(")
        for token in ("source_identity(root)", "checkpoint_preflight(", "runtime_validator.validate(",
                      "native.validate_runtime(runtime)", "immutable_final_record(",
                      "preflight_evaluator = run_evaluator("):
            self.assertLess(source.index(token, start), read)
        loop = source.index('for ordinal, case in enumerate(manifest["cases"]):', read)
        self.assertGreater(source.index("run_evaluator(", loop), loop)
        self.assertGreater(source.index("run_native(", loop), loop)

    def test_runner_requires_one_typed_live_context_and_explicit_tool(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            with self.assertRaisesRegex(runner.M22FollowupEvaluationError, "one live artifact context"):
                runner.run(
                    self.root, self.root / runner.MANIFEST,
                    directory / "v2-m22-followup-evaluation-a", directory / "evidence.json",
                    artifact_context=None, bwrap_path=pathlib.Path("/usr/bin/bwrap"),
                )

    def test_create_only_writer_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "record.json"
            runner.write_new(path, {"value": 1})
            with self.assertRaisesRegex(runner.foundation.M22FinalEvaluationError, "already exists"):
                runner.write_new(path, {"value": 2})

    def test_source_inventory_binds_all_followup_and_native_boundaries(self) -> None:
        self.assertEqual(len(runner.SOURCE_PATHS), 20)
        self.assertNotIn("config/v2/m22-followup-manifest.json", runner.SOURCE_PATHS)
        self.assertIn("config/v2/m22-final-evaluation-evidence.json", runner.SOURCE_PATHS)
        self.assertIn("scripts/v2/run_m22_followup_evaluation.py", runner.SOURCE_PATHS)
        self.assertIn("scripts/v2/validate_m22_followup_evaluation.py", runner.SOURCE_PATHS)
        self.assertIn("docs/project/schema/v2-m22-followup-evaluation-evidence.schema.json", runner.SOURCE_PATHS)
        self.assertIn("training/v2/src/m22_evaluator_main.cpp", runner.SOURCE_PATHS)

    def test_protocol_never_retries_or_replaces_final_v1(self) -> None:
        report = self.fake_report()
        self.assertEqual(report["protocol"]["retries"], 0)
        self.assertEqual(report["protocol"]["replacements"], 0)
        self.assertEqual(report["immutable_final_v1"]["original_cases_reexecuted"], 0)
        self.assertFalse(report["immutable_final_v1"]["followup_replaces_final_v1"])


if __name__ == "__main__":
    unittest.main()
