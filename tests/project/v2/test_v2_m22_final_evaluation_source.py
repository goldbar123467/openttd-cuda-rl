#!/usr/bin/env python3
"""Offline and mutation tests for M22's frozen final one-shot runner."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from types import MappingProxyType
from unittest import mock

import jsonschema

import artifact_context
from artifact_context import ArtifactContext, LiveInputManifest, ValidationMode
import m22_final_native as native
import run_m22_final_evaluation as runner
import validate_m22_final_evaluation as validator


def _evaluation_report(
    run: dict[str, object], checkpoint_id: str, runner_module: object,
) -> dict[str, object]:
    active = run["evaluator"]["legal_active_program"]
    active_index = runner_module.PROGRAM_INDEX[active]
    mask = [index in (0, active_index) for index in range(len(runner_module.PROGRAMS))]
    return {
        "checkpoint": {"architecture": "monolithic-generalist-v1", "id": checkpoint_id, "run_seed": 1},
        "execution": {
            "device": "cuda:0", "greedy_masked": True, "optimizer_constructed": False,
            "optimizer_deserialized": False, "optimizer_path_opened": False, "recurrent_reset": True,
        },
        "policy": {
            "action": run["evaluator"]["action"], "action_index": run["evaluator"]["action_index"],
            "legal_active_index": active_index, "legal_active_program": active,
            "logits": [0.0] * len(runner_module.PROGRAMS), "next_hidden": [0.0] * 256, "value": 0.0,
        },
        "public_state": runner_module.evaluator_public_case(run["public_case"]),
        "schema_version": "openttd-rl-v2-m22-evaluator-report-1", "status": "PASS",
        "tensor_input": {"program_mask": mask, "public_features": [0.0] * 32},
    }


def _write_payload(path: pathlib.Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def stage_evaluation_artifacts(
    common_root: pathlib.Path,
    report: dict[str, object],
    *,
    logical_set: str,
    runner_module: object,
) -> tuple[dict[str, object], LiveInputManifest]:
    """Stage a byte-real complete evaluation tree and its typed evaluator role."""

    value = copy.deepcopy(report)
    evaluator_executable = common_root / "typed-inputs/final-v1-evaluator"
    evaluator_digest = _write_payload(
        evaluator_executable, b"#!/bin/sh\n# byte-real Task 5C evaluator fixture\nexit 0\n",
    )
    evaluator_executable.chmod(0o700)
    value["identity"]["evaluator_executable_sha256"] = evaluator_digest
    result_root = common_root / logical_set

    def stage_evaluator(run: dict[str, object], base: pathlib.Path, label: str) -> None:
        evaluator = run["evaluator"]
        process = evaluator["process"]
        evaluator_root = base / "evaluator"
        process["stdout_sha256"] = _write_payload(
            evaluator_root / process["stdout_path"], f"{label} evaluator stdout\n".encode(),
        )
        process["stderr_sha256"] = _write_payload(
            evaluator_root / process["stderr_path"], f"{label} evaluator stderr\n".encode(),
        )
        payload = runner_module.canonical_bytes(_evaluation_report(
            run, value["identity"]["checkpoint_id"], runner_module,
        ))
        evaluator["report_sha256"] = _write_payload(evaluator_root / evaluator["report_path"], payload)

    preflight = value["preflight"]
    stage_evaluator(preflight, result_root / "preflight", "preflight")
    (result_root / "preflight/preflight-record.json").write_bytes(runner_module.canonical_bytes(preflight))

    for run in value["runs"]:
        case_root = result_root / run["artifact_path"]
        stage_evaluator(run, case_root, run["public_case"]["case_id"])
        native_root = case_root / "native"
        for item in run["native"]["artifact_inventory"]:
            payload = f"{run['public_case']['case_id']} native {item['path']}\n".encode()
            item["bytes"] = len(payload)
            item["sha256"] = _write_payload(native_root / item["path"], payload)
        if run["native"]["status"] == "PASS":
            record = run["native"]["record"]
            record["executable_sha256"] = value["identity"]["native_executable_sha256"]
            record["source_tree"] = value["identity"]["native_source_tree"]
            by_path = {item["path"]: item for item in run["native"]["artifact_inventory"]}
            for path_key, digest_key in (
                ("manifest_path", "manifest_sha256"), ("report_path", "report_sha256"),
                ("openttd_log_path", "openttd_log_sha256"),
            ):
                record[digest_key] = by_path[record[path_key]]["sha256"]
        (case_root / "case-record.json").write_bytes(runner_module.canonical_bytes(run))

    unsigned = copy.deepcopy(value)
    unsigned.pop("report_sha256", None)
    value["report_sha256"] = runner_module.sha256_bytes(runner_module.canonical_bytes(unsigned))
    live_inputs = LiveInputManifest(
        ValidationMode.LIVE,
        common_root,
        MappingProxyType({"final-v1-evaluator": evaluator_executable}),
    )
    return value, live_inputs


def commit_evaluation_project(
    repository_root: pathlib.Path,
    project: pathlib.Path,
    runner_module: object,
    value: dict[str, object],
    *,
    preserve_existing: tuple[str, ...] = (),
) -> pathlib.Path:
    """Populate the runtime fixture repository with exact evaluation source blobs."""

    subprocess.run(
        ["git", "-C", str(project), "fetch", "-q", str(repository_root),
         "+refs/heads/*:refs/remotes/task5c/*"],
        check=True,
    )
    for relative in runner_module.SOURCE_PATHS:
        if relative in preserve_existing and (project / relative).is_file():
            continue
        source = repository_root / relative
        destination = project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    subprocess.run(["git", "-C", str(project), "add", "."], check=True)
    subprocess.run([
        "git", "-C", str(project), "-c", "user.name=Task 5C fixture",
        "-c", "user.email=task5c@example.invalid", "commit", "-q", "-m", "evaluation fixture",
    ], check=True)
    commit = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "HEAD"], check=True,
        text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "HEAD^{tree}"], check=True,
        text=True, stdout=subprocess.PIPE,
    ).stdout.strip()
    files = []
    for relative in runner_module.SOURCE_PATHS:
        blob = subprocess.run(
            ["git", "-C", str(project), "show", f"{commit}:{relative}"], check=True,
            stdout=subprocess.PIPE,
        ).stdout
        files.append({"path": relative, "sha256": hashlib.sha256(blob).hexdigest()})
    value["source"].update({
        "clean": True, "files": files, "repository_commit": commit,
        "repository_tree": tree, "tree_sha256": runner_module.sha256_bytes(runner_module.canonical_bytes(files)),
    })
    if "main_synchronized" in value["source"]:
        value["source"]["main_synchronized"] = True
    return project


def make_relocated_evaluation_fixture(
    repository_root: pathlib.Path,
    directory: pathlib.Path,
    report: dict[str, object],
    *,
    runner_module: object,
    validator_module: object,
    logical_set: str,
) -> tuple[pathlib.Path, pathlib.Path, LiveInputManifest]:
    """Build the complete runtime and evaluation closures under one relocated root."""

    import prepare_m22_followup_runtime as runtime_preparation
    import validate_m22_followup_runtime_source as runtime_validator
    from tests.project.v2.test_v2_m22_final_runtime_source import make_live_runtime_fixture

    runtime_source = runtime_validator.load(repository_root / runtime_validator.CONFIG)
    runtime_value, _, _, _ = make_live_runtime_fixture(
        repository_root,
        directory,
        runtime_source,
        patches=runtime_preparation.PATCHES,
        logical_set=runtime_validator.RESULT_LOGICAL_SET,
    )
    project = directory / "project"
    runtime_config = project / runtime_validator.CONFIG
    runtime_config.parent.mkdir(parents=True, exist_ok=True)
    runtime_config.write_text(json.dumps(runtime_value, indent=2) + "\n", encoding="utf-8")

    if runner_module.MANIFEST.name == "m22-followup-v2-manifest.json":
        import build_m22_followup_manifest as followup_manifest_builder
        import run_m22_followup_evaluation as followup_runner
        import validate_m22_followup_evaluation as followup_validator

        followup_manifest = followup_manifest_builder.build(project)
        followup_manifest_bytes = followup_manifest_builder.canonical_bytes(followup_manifest)
        (project / followup_manifest_builder.MANIFEST).write_bytes(followup_manifest_bytes)
        followup_report = followup_validator.load(repository_root / followup_validator.CONFIG)
        followup_report["manifest"] = {
            "case_count": 42,
            "id": followup_manifest["manifest_id"],
            "path": followup_runner.MANIFEST.as_posix(),
            "sha256": hashlib.sha256(followup_manifest_bytes).hexdigest(),
        }
        commit_evaluation_project(repository_root, project, followup_runner, followup_report)
        followup_report["identity"] = followup_validator.expected_identity(project, followup_report)
        followup_unsigned = copy.deepcopy(followup_report)
        followup_unsigned.pop("report_sha256", None)
        followup_report["report_sha256"] = followup_runner.sha256_bytes(
            followup_runner.canonical_bytes(followup_unsigned)
        )
        (project / followup_validator.CONFIG).write_text(
            json.dumps(followup_report, indent=2) + "\n", encoding="utf-8",
        )
    value = copy.deepcopy(report)
    manifest_value = runner_module.manifest_builder.build(project)
    manifest_bytes = runner_module.manifest_builder.canonical_bytes(manifest_value)
    (project / runner_module.MANIFEST).write_bytes(manifest_bytes)
    value["manifest"] = {
        "case_count": 42,
        "id": manifest_value["manifest_id"],
        "path": runner_module.MANIFEST.as_posix(),
        "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
    preserve = (("config/v2/m22-followup-evaluation-evidence.json",)
                if runner_module.MANIFEST.name == "m22-followup-v2-manifest.json" else ())
    commit_evaluation_project(
        repository_root, project, runner_module, value, preserve_existing=preserve,
    )
    if "immutable_followup_v1" in value:
        immutable_followup = runner_module.load(project / runner_module.IMMUTABLE_FOLLOWUP_V1)
        value["immutable_followup_v1"] = runner_module.immutable_followup_v1_record(
            project, immutable_followup,
        )
    value["identity"] = validator_module.expected_identity(project, value)
    value, live_inputs = stage_evaluation_artifacts(
        directory, value, logical_set=logical_set, runner_module=runner_module,
    )
    evidence = directory / "evaluation-evidence.json"
    evidence.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return project, evidence, live_inputs


class M22FinalEvaluationSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.schema = json.loads((cls.root / runner.EVIDENCE_SCHEMA).read_text(encoding="utf-8"))

    @staticmethod
    def case(case_id: str = "case-00") -> dict[str, object]:
        return {
            "case_id": case_id, "task": "service", "transport_mode": "road", "climate": "temperate",
            "map_width": 64, "map_height": 64, "cargo": "PASS", "opponent": "not-applicable",
            "seed": 101, "required_program": "road-passenger", "native_probe": "passenger-service",
            "source_gate": "G15",
        }

    @classmethod
    def fake_run(cls, ordinal: int) -> dict[str, object]:
        case = cls.case(f"case-{ordinal:02d}")
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
            "artifact_path": f"cases/{ordinal:02d}-case-{ordinal:02d}", "evaluator": evaluator, "failures": [],
            "native": native_result, "ordinal": ordinal, "private_seed": 101,
            "public_case": public, "required_program": "road-passenger", "scores": scores,
        }

    @classmethod
    def fake_report(cls) -> dict[str, object]:
        runs = [cls.fake_run(index) for index in range(42)]
        protocol = runner.protocol_record(runs, [run["public_case"]["case_id"] for run in runs])
        statistics = runner.aggregate_statistics(runs)
        acceptance = runner.acceptance(runs, statistics, protocol)
        report: dict[str, object] = {
            "acceptance": acceptance, "artifact_root": "/retained/m22-final", "failure_counts": {
                category: 0 for category in runner.FAILURES
            },
            "identity": {
                "aggregate_schema_sha256": "9" * 64, "bubblewrap_sha256": "a" * 64,
                "checkpoint_id": "b" * 64, "evaluation_manifest_schema_sha256": "c" * 64,
                "evaluator_executable_sha256": "d" * 64, "evaluator_report_schema_sha256": "e" * 64,
                "learning_contract_sha256": "f" * 64, "native_executable_sha256": "0" * 64,
                "native_source_tree": "1" * 40, "prior_attempt_sha256": "2" * 64,
                "qualification_evidence_sha256": "2" * 64,
                "runtime_source_sha256": "3" * 64,
            },
            "history": {"cases_attempted": 0, "failure_category": "final-manifest-adapter", "manifest_reads": 1,
                        "prior_attempt": "config/v2/m22-final-attempt-a.json",
                        "status": "REJECTED_BEFORE_CASE_EXECUTION"},
            "manifest": {"case_count": 42, "id": "m22-independent-final-v1",
                         "path": "config/v2/m22-evaluation-manifest.json", "sha256": "4" * 64},
            "preflight": {"evaluator": copy.deepcopy(runs[0]["evaluator"]),
                          "public_case": runner.public_case(runner.PREFLIGHT_CASE)},
            "protocol": protocol, "runs": runs,
            "schema_version": "openttd-rl-v2-m22-final-evaluation-evidence-1",
            "source": {
                "clean": True, "files": [{"path": path, "sha256": "5" * 64} for path in runner.SOURCE_PATHS],
                "repository_commit": "6" * 40, "repository_tree": "7" * 40, "tree_sha256": "8" * 64,
            },
            "statistics": statistics, "status": "PASS" if acceptance["overall"] else "FAIL",
        }
        report["report_sha256"] = runner.sha256_bytes(runner.canonical_bytes(report))
        return report

    def test_aggregate_schema_is_canonical_closed_and_accepts_complete_report(self) -> None:
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

    def test_public_capability_mapping_covers_all_sixteen_active_programs(self) -> None:
        rows = (
            ("G15", "m15-competence", "road-passenger"), ("G16", "industry-chain", "road-cargo"),
            ("G17", "passenger", "rail-passenger"), ("G17", "freight", "rail-freight"),
            ("G18", "natural", "ship-natural"), ("G18", "constructed", "ship-constructed"),
            ("G19", "service", "air-service"), ("G19", "helicopter", "air-helicopter"),
            ("G19", "multimodal", "multimodal-transfer"), ("G19", "router", "mode-router"),
            ("G20", "head-to-head", "competition-head-to-head"), ("G21", "calendar", "calendar-inspect"),
            ("G21", "authority-economy", "authority-economy"), ("G21", "events", "event-recovery"),
            ("G21", "gamescript", "gamescript-response"), ("G21", "content", "content-discovery"),
        )
        actual = []
        for index, (gate, probe, expected) in enumerate(rows):
            case = self.case(f"mapping-{index}")
            case.update({"source_gate": gate, "native_probe": probe})
            actual.append(runner.public_program(case))
            self.assertEqual(actual[-1], expected)
        self.assertEqual(actual, list(runner.PROGRAMS[1:]))

    def test_accessed_preregistered_manifest_has_complete_public_mapping(self) -> None:
        manifest = runner.load(self.root / runner.learning.EVALUATION)
        self.assertEqual(len(manifest["cases"]), 42)
        self.assertTrue(all(runner.public_program(case) == case["required_program"] for case in manifest["cases"]))
        self.assertEqual(len({(case["source_gate"], case["native_probe"])
                              for case in manifest["cases"]}), 17)

    def test_evaluator_command_has_no_seed_or_required_program_channel(self) -> None:
        case = self.case()
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            command = runner.evaluator_command(
                pathlib.Path("/usr/bin/bwrap"), self.root, pathlib.Path("/retained/m22-evaluator"),
                pathlib.Path("/retained/checkpoint"), directory, case, "cuda:0",
            )
        self.assertNotIn("--seed", command)
        self.assertNotIn("--required-program", command)
        self.assertNotIn(str(case["seed"]), command)
        self.assertNotIn(str(case["required_program"]), command)
        self.assertEqual(command.count("--policy-split"), 1)
        self.assertIn("--unshare-net", command)

    def test_baselines_are_public_only_deterministic_and_legal(self) -> None:
        first = self.case()
        second = copy.deepcopy(first)
        second["seed"] = 2_000_000_000
        second["required_program"] = "content-discovery"
        decisions = runner.baseline_decisions(first)
        self.assertEqual(decisions, runner.baseline_decisions(second))
        self.assertEqual([item["policy"] for item in decisions],
                         ["seeded-random-legal", "wait-only", "public-heuristic-v1"])
        self.assertTrue(all(item["action"] in {"wait", "road-passenger"} for item in decisions))

    def test_student_t_statistics_are_exact_and_complete(self) -> None:
        result = runner.summary_stats([2.5] * 42)
        self.assertEqual(result["n"], 42)
        self.assertEqual((result["mean"], result["median"], result["ci95_lower"], result["ci95_upper"]),
                         (2.5, 2.5, 2.5, 2.5))
        self.assertEqual(result["t_critical_95"], 2.01954097)

    def test_native_reward_matches_frozen_corpus_formula(self) -> None:
        native_result = self.fake_run(0)["native"]
        expected = 1.0 + min(__import__("math").log1p(8) / 10.0, 1.0) + min(__import__("math").log1p(45) / 20.0, 1.0)
        self.assertEqual(runner.native_reward(native_result), runner.rounded(expected))

    def test_wrong_learned_program_is_retained_as_failure_without_suppressing_native(self) -> None:
        case = self.case()
        run = self.fake_run(0)
        evaluator = copy.deepcopy(run["evaluator"])
        evaluator["action"], evaluator["action_index"] = "wait", 0
        scores = runner.case_scores(case, evaluator, run["native"])
        failures = runner.failure_categories(case, evaluator, run["native"], scores)
        self.assertEqual(scores["learned_return"], 0.0)
        self.assertEqual(run["native"]["status"], "PASS")
        self.assertIn("learned-program-mismatch", failures)

    def test_independent_validator_recomputes_case_scores_and_failures(self) -> None:
        case = self.case()
        run = self.fake_run(0)
        validator.validate_run(run, case, 0, {"checkpoint_id": "b" * 64}, None,
                               json.loads((self.root / runner.EVALUATOR_SCHEMA).read_text(encoding="utf-8")))
        mutated = copy.deepcopy(run)
        mutated["scores"]["learned_return"] = 0.0
        with self.assertRaisesRegex(validator.M22FinalEvidenceError, "case score"):
            validator.validate_run(mutated, case, 0, {"checkpoint_id": "b" * 64}, None,
                                   json.loads((self.root / runner.EVALUATOR_SCHEMA).read_text(encoding="utf-8")))

    def test_acceptance_fails_closed_on_missing_native_process(self) -> None:
        runs = [self.fake_run(index) for index in range(42)]
        protocol = runner.protocol_record(runs, [run["public_case"]["case_id"] for run in runs])
        statistics = runner.aggregate_statistics(runs)
        self.assertTrue(runner.acceptance(runs, statistics, protocol)["all_42_once"])
        protocol["native_processes"] -= 1
        self.assertFalse(runner.acceptance(runs, statistics, protocol)["all_42_once"])

    def test_runner_has_one_manifest_read_after_all_preflight_boundaries(self) -> None:
        source = (self.root / "scripts/v2/run_m22_final_evaluation.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("manifest_path.read_bytes()"), 1)
        read = source.index("manifest_bytes = manifest_path.read_bytes()")
        for token in ("source_identity(root)", "checkpoint_preflight(", "runtime_validator.validate(",
                      "native.validate_runtime(runtime)", "preflight_evaluator = run_evaluator("):
            self.assertLess(source.index(token, source.index("def run(")), read)
        loop = source.index('for ordinal, case in enumerate(manifest["cases"]):', read)
        self.assertGreater(source.index("run_evaluator(", loop), loop)
        self.assertGreater(source.index("run_native(", loop), loop)

    def test_runner_requires_one_typed_live_context_and_explicit_tool(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            with self.assertRaisesRegex(runner.M22FinalEvaluationError, "one live artifact context"):
                runner.run(
                    self.root, self.root / runner.learning.EVALUATION,
                    directory / "v2-m22-final-evaluation-b", directory / "evidence.json",
                    artifact_context=None, bwrap_path=pathlib.Path("/usr/bin/bwrap"),
                )

    def test_create_only_writer_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "record.json"
            runner.write_new(path, {"value": 1})
            with self.assertRaisesRegex(runner.M22FinalEvaluationError, "already exists"):
                runner.write_new(path, {"value": 2})

    def test_source_inventory_binds_runner_validator_schema_and_native_boundaries(self) -> None:
        self.assertEqual(len(runner.SOURCE_PATHS), 14)
        self.assertIn("config/v2/m22-final-attempt-a.json", runner.SOURCE_PATHS)
        self.assertIn("docs/project/schema/v2-m22-final-attempt.schema.json", runner.SOURCE_PATHS)
        self.assertIn("scripts/v2/run_m22_final_evaluation.py", runner.SOURCE_PATHS)
        self.assertIn("scripts/v2/validate_m22_final_evaluation.py", runner.SOURCE_PATHS)
        self.assertIn("scripts/v2/m22_final_native.py", runner.SOURCE_PATHS)
        self.assertIn("training/v2/src/m22_evaluator_main.cpp", runner.SOURCE_PATHS)
        self.assertIn("docs/project/schema/v2-m22-final-evaluation-evidence.schema.json", runner.SOURCE_PATHS)

    def test_required_live_input_closure_is_exact_unique_and_path_safe(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        self.assertEqual(len(requirements), 4 + 351 + 67)
        self.assertEqual(len(set(requirements)), len(requirements))
        self.assertEqual(
            {item.logical_set for item in requirements},
            {"v2-m21-broad-a", "v2-m22-final-runtime-c",
             "v2-m22-final-evaluation-a", "v2-m22-final-evaluation-b"},
        )
        self.assertTrue(all(not pathlib.PurePosixPath(item.relative_path).is_absolute()
                            and ".." not in pathlib.PurePosixPath(item.relative_path).parts
                            for item in requirements))

    def test_offline_validation_does_not_open_prior_attempt_artifacts(self) -> None:
        original_is_dir = pathlib.Path.is_dir
        prior_attempt = runner.load(self.root / runner.PRIOR_ATTEMPT)
        recorded_root = pathlib.Path(prior_attempt["artifacts"]["root"])

        def poisoned_is_dir(path: pathlib.Path) -> bool:
            if path == recorded_root or path.is_relative_to(recorded_root):
                raise AssertionError(f"unexpected prior-attempt live read: {path}")
            return original_is_dir(path)

        with mock.patch.object(pathlib.Path, "is_dir", poisoned_is_dir):
            result = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertEqual(result, {"cases": 42, "failures": 10, "live": False, "status": "FAIL"})

    def test_offline_validation_does_not_resolve_bwrap(self) -> None:
        with mock.patch.object(
            artifact_context,
            "preflight_tools",
            side_effect=AssertionError("unexpected bwrap resolution"),
        ):
            result = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertEqual(result, {"cases": 42, "failures": 10, "live": False, "status": "FAIL"})


if __name__ == "__main__":
    unittest.main()
