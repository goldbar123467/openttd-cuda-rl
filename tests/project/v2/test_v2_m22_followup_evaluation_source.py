#!/usr/bin/env python3
"""Offline and mutation tests for M22's frozen follow-up one-shot runner."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import jsonschema

import run_m22_followup_evaluation as runner
import validate_m22_followup_evaluation as validator


class M22FollowupEvaluationSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.schema = validator.load(cls.root / runner.EVIDENCE_SCHEMA)

    @staticmethod
    def case(case_id: str = "followup-case-00") -> dict[str, object]:
        return {
            "case_id": case_id, "task": "service", "transport_mode": "road", "climate": "temperate",
            "map_width": 64, "map_height": 64, "cargo": "PASS", "opponent": "not-applicable",
            "seed": 698564641, "required_program": "road-passenger", "native_probe": "passenger-service",
            "source_gate": "G15",
        }

    @classmethod
    def fake_run(cls, ordinal: int) -> dict[str, object]:
        case = cls.case(f"followup-case-{ordinal:02d}")
        public = runner.public_case(case)
        evaluator = {
            "action": "road-passenger", "action_index": 1, "failure_category": None, "failure_detail": None,
            "legal_active_program": "road-passenger",
            "process": {
                "attempt": 1, "exit_code": 0, "fresh_process": True, "launched": True,
                "network_unshared": True, "stderr_path": "evaluator.stderr", "stderr_sha256": "1" * 64,
                "stdout_path": "evaluator.stdout", "stdout_sha256": "2" * 64, "timed_out": False,
                "wall_seconds": 0.1,
            },
            "report_path": "evaluator-report.json", "report_sha256": "3" * 64, "status": "PASS",
        }
        native_record = {
            "case": public, "executable_sha256": "4" * 64, "fresh_processes": 1,
            "manifest_path": "manifest.json", "manifest_sha256": "5" * 64,
            "metrics": {"delivered": 8, "income": 45, "ticks": 100}, "native_probe": "passenger-service",
            "network_unshared": True, "openttd_log_path": "openttd.log", "openttd_log_sha256": "6" * 64,
            "report_path": "report.json", "report_sha256": "7" * 64, "source_tree": "8" * 40,
            "status": "PASS", "wall_seconds": 0.2,
        }
        native_result = {
            "artifact_inventory": [], "attempt": 1, "failure_category": None, "failure_detail": None,
            "record": native_record, "status": "PASS",
        }
        scores = runner.case_scores(case, evaluator, native_result)
        return {
            "artifact_path": f"cases/{ordinal:02d}-followup-case-{ordinal:02d}", "evaluator": evaluator,
            "failures": [], "native": native_result, "ordinal": ordinal, "private_seed": 698564641,
            "public_case": public, "required_program": "road-passenger", "scores": scores,
        }

    @classmethod
    def fake_report(cls) -> dict[str, object]:
        runs = [cls.fake_run(index) for index in range(42)]
        protocol = runner.protocol_record(runs, [run["public_case"]["case_id"] for run in runs])
        statistics = runner.aggregate_statistics(runs)
        acceptance = runner.acceptance(runs, statistics, protocol)
        report: dict[str, object] = {
            "acceptance": acceptance, "artifact_root": "/retained/m22-followup", "failure_counts": {
                category: 0 for category in runner.FAILURES
            },
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
            "manifest": {"case_count": 42, "id": "m22-independent-followup-v1",
                         "path": "config/v2/m22-followup-manifest.json", "sha256": "6" * 64},
            "preflight": {"evaluator": copy.deepcopy(runs[0]["evaluator"]),
                          "public_case": runner.public_case(runner.PREFLIGHT_CASE)},
            "protocol": protocol, "runs": runs,
            "schema_version": "openttd-rl-v2-m22-followup-evaluation-evidence-1",
            "source": {
                "clean": True, "files": [{"path": path, "sha256": "7" * 64} for path in runner.SOURCE_PATHS],
                "repository_commit": "8" * 40, "repository_tree": "9" * 40, "tree_sha256": "a" * 64,
            },
            "statistics": statistics, "status": "PASS" if acceptance["overall"] else "FAIL",
        }
        report["report_sha256"] = runner.sha256_bytes(runner.canonical_bytes(report))
        return report

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
