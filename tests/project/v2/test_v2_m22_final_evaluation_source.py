#!/usr/bin/env python3
"""Offline and mutation tests for M22's frozen final one-shot runner."""

from __future__ import annotations

import copy
import hashlib
import json
import lzma
import os
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
    project: pathlib.Path,
    runtime_source: dict[str, object],
    manifest: dict[str, object],
    evaluator_source: pathlib.Path | None,
) -> tuple[dict[str, object], LiveInputManifest | None]:
    """Stage byte-real producer outputs, stubbing only the external OpenTTD process."""

    from tests.project.v2.test_v2_m22_final_runtime_source import _smoke_report

    value = copy.deepcopy(report)
    evaluator_executable: pathlib.Path | None = None
    if evaluator_source is not None:
        evaluator_executable = common_root / "typed-inputs/final-v1-evaluator"
        evaluator_executable.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(evaluator_source, evaluator_executable)
        evaluator_executable.chmod(0o700)
        if hashlib.sha256(evaluator_executable.read_bytes()).hexdigest() != runner.EVALUATOR_SHA256:
            raise AssertionError("configured evaluator is not the frozen final-v1 role")
    result_root = common_root / logical_set
    context = ArtifactContext.live(common_root)
    runtime = runner_module.runtime_paths(runtime_source, context)
    cases = {case["case_id"]: case for case in manifest["cases"]}

    def save_fixture(case: dict[str, object]) -> bytes:
        width, height = int(case["map_width"]), int(case["map_height"])
        maps = bytes.fromhex("4d4150530310060564696d5f78060564696d5f790009")
        maps += width.to_bytes(4, "big") + height.to_bytes(4, "big") + b"\x00"
        chunks = []
        for tag, payload in (
            (b"MAPT", bytes(width * height)), (b"MAPH", b""), (b"MAPO", b""), (b"MAP2", b""),
            (b"M3LO", b""), (b"M3HI", b""), (b"MAP5", b""), (b"MAPE", b""),
            (b"MAP7", b""), (b"MAP8", b""),
        ):
            chunks.append(tag + len(payload).to_bytes(4, "big") + payload)
        return b"OTTX\x00\x00\x00\x00" + lzma.compress(maps + b"".join(chunks))

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
        case = cases[run["public_case"]["case_id"]]
        report_value = _smoke_report(project, runtime_source, case, run["native"]["record"]["metrics"])

        def launch(_command: list[str], _runtime: native.RuntimePaths,
                   run_root: pathlib.Path, launched_case: dict[str, object]) -> tuple[float, str]:
            native.write_new(run_root / "report.json", report_value)
            if launched_case["source_gate"] == "G15":
                native.write_new(run_root / "reset.json", {"request": {
                    "width": launched_case["map_width"], "height": launched_case["map_height"],
                    "climate": launched_case["climate"], "split": "final",
                }})
            (run_root / "openttd.log").write_text("", encoding="utf-8")
            for relative in native.expected_artifact_paths(launched_case, "PASS"):
                path = run_root / relative
                if path.exists():
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                if relative.endswith(".sav"):
                    path.write_bytes(save_fixture(launched_case))
                elif relative.endswith(".json"):
                    path.write_bytes(runner_module.canonical_bytes({
                        "case_id": launched_case["case_id"], "kind": relative,
                    }))
                else:
                    path.write_bytes(b"M22B\x00" + hashlib.sha256(relative.encode("ascii")).digest())
            return 0.0, ""

        with mock.patch.object(native, "launch", side_effect=launch):
            native_record = native.run_native_case(project, runtime, native_root, case)
        run["native"] = {
            "artifact_inventory": runner_module.artifact_inventory(native_root), "attempt": 1,
            "failure_category": None, "failure_detail": None, "record": native_record, "status": "PASS",
        }
        run["scores"] = runner_module.case_scores(case, run["evaluator"], run["native"])
        run["failures"] = runner_module.failure_categories(case, run["evaluator"], run["native"], run["scores"])
        (case_root / "case-record.json").write_bytes(runner_module.canonical_bytes(run))

    value["protocol"] = runner_module.protocol_record(value["runs"], [case["case_id"] for case in manifest["cases"]])
    value["statistics"] = runner_module.aggregate_statistics(value["runs"])
    value["acceptance"] = runner_module.acceptance(value["runs"], value["statistics"], value["protocol"])
    value["failure_counts"] = {
        category: sum(category in run["failures"] for run in value["runs"])
        for category in runner_module.FAILURES
    }
    value["status"] = "PASS" if value["acceptance"]["overall"] else "FAIL"

    unsigned = copy.deepcopy(value)
    unsigned.pop("report_sha256", None)
    value["report_sha256"] = runner_module.sha256_bytes(runner_module.canonical_bytes(unsigned))
    live_inputs = None if evaluator_executable is None else LiveInputManifest(
        ValidationMode.LIVE, common_root,
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
    require_evaluator: bool = True,
) -> tuple[pathlib.Path, pathlib.Path, LiveInputManifest | None]:
    """Build the complete runtime and evaluation closures under one relocated root."""

    configured = os.environ.get("OPENTTD_RL_M22_EVALUATOR")
    if require_evaluator and not configured:
        raise unittest.SkipTest(
            "frozen final-v1 evaluator live artifact is unavailable; set OPENTTD_RL_M22_EVALUATOR",
        )
    evaluator_source = pathlib.Path(configured) if configured else None
    if evaluator_source is not None and (not evaluator_source.is_absolute() or not evaluator_source.is_file() or
            evaluator_source.is_symlink() or
            hashlib.sha256(evaluator_source.read_bytes()).hexdigest() != runner.EVALUATOR_SHA256):
        raise unittest.SkipTest("configured frozen final-v1 evaluator live artifact is unavailable or drifted")

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
        project=project, runtime_source=runtime_value, manifest=manifest_value,
        evaluator_source=evaluator_source,
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

    def test_native_launch_executes_only_the_explicit_bwrap_under_hostile_path(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw).resolve()
            exact_marker, ambient_marker = directory / "exact.marker", directory / "ambient.marker"
            exact = directory / "exact-bwrap"
            exact.write_text(
                "#!/bin/sh\nprintf exact > \"$TASK5C_EXACT_MARKER\"\n"
                "while [ \"$1\" != -- ]; do shift; done\nshift\nexec \"$@\"\n",
                encoding="utf-8",
            )
            exact.chmod(0o700)
            hostile = directory / "hostile"
            hostile.mkdir()
            ambient = hostile / "bwrap"
            ambient.write_text(
                "#!/bin/sh\nprintf ambient > \"$TASK5C_AMBIENT_MARKER\"\nexit 97\n",
                encoding="utf-8",
            )
            ambient.chmod(0o700)
            run_root = directory / "native"
            run_root.mkdir()
            runtime = native.RuntimePaths(
                executable=pathlib.Path("/bin/sh"), opengfx=directory / "opengfx",
                base_config=directory / "base.cfg", content_config=directory / "content.cfg",
                gamescript_config=directory / "gamescript.cfg", source_tree="1" * 40,
            )
            case = self.case()
            environment = {
                **os.environ, "PATH": str(hostile), "TASK5C_EXACT_MARKER": str(exact_marker),
                "TASK5C_AMBIENT_MARKER": str(ambient_marker),
            }
            with mock.patch.dict(os.environ, environment, clear=True):
                _, output = native.launch(
                    ["/bin/sh", "-c", "printf native-output"], runtime, run_root, case,
                    bwrap_path=exact,
                )
            self.assertEqual(output, "native-output")
            self.assertEqual(exact_marker.read_text(encoding="utf-8"), "exact")
            self.assertFalse(ambient_marker.exists())

    def test_native_launch_rejects_the_supplied_bwrap_symlink_before_starting_a_process(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw).resolve()
            bwrap_link = directory / "bwrap"
            bwrap_link.symlink_to("/usr/bin/bwrap")
            run_root = directory / "native"
            run_root.mkdir()
            runtime = native.RuntimePaths(
                executable=pathlib.Path("/bin/sh"), opengfx=directory / "opengfx",
                base_config=directory / "base.cfg", content_config=directory / "content.cfg",
                gamescript_config=directory / "gamescript.cfg", source_tree="1" * 40,
            )
            with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("process started")):
                with self.assertRaisesRegex(native.M22FinalNativeError, "bubblewrap path"):
                    native.launch(
                        ["/bin/true"], runtime, run_root, self.case(), bwrap_path=bwrap_link,
                    )

    def test_supplied_manifest_bytes_are_not_reopened_by_final_validator(self) -> None:
        report = validator.load(self.root / validator.CONFIG)
        manifest_path = self.root / runner.learning.EVALUATION
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        original_open = pathlib.Path.open

        def poisoned_open(path: pathlib.Path, *args: object, **kwargs: object):
            if path == manifest_path:
                raise AssertionError("final manifest was reopened")
            return original_open(path, *args, **kwargs)

        with mock.patch.object(pathlib.Path, "open", poisoned_open):
            result = validator.validate_value(
                report, self.root, manifest_value=manifest, manifest_bytes=manifest_bytes,
            )
        self.assertEqual(result, {"cases": 42, "failures": 10, "live": False, "status": "FAIL"})

    def test_supplied_manifest_bytes_must_match_supplied_value_and_frozen_digest(self) -> None:
        report = validator.load(self.root / validator.CONFIG)
        manifest_bytes = (self.root / runner.learning.EVALUATION).read_bytes()
        manifest = json.loads(manifest_bytes)
        with self.assertRaisesRegex(validator.M22FinalEvidenceError, "manifest"):
            validator.validate_value(
                report, self.root, manifest_value=manifest, manifest_bytes=manifest_bytes + b" ",
            )

    def test_public_offline_validation_rejects_malformed_result_descriptors_without_artifact_reads(self) -> None:
        original = validator.load(self.root / validator.CONFIG)
        manifest_bytes = (self.root / runner.learning.EVALUATION).read_bytes()
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
                    with self.assertRaisesRegex(validator.M22FinalEvidenceError, "(native|artifact|closure)"):
                        validator.validate_value(
                            report, self.root, artifact_context=ArtifactContext.offline(),
                            manifest_value=manifest, manifest_bytes=manifest_bytes,
                        )

    def test_evaluator_and_prior_attempt_identities_are_frozen(self) -> None:
        report = validator.load(self.root / validator.CONFIG)
        report["identity"]["evaluator_executable_sha256"] = "0" * 64
        self.assertEqual(
            validator.expected_identity(self.root, report)["evaluator_executable_sha256"],
            runner.EVALUATOR_SHA256,
        )
        contract = runner.load(self.root / runner.CONTRACT)
        prior = runner.load(self.root / runner.PRIOR_ATTEMPT)
        for field, replacement in (
            ("evaluator_executable_sha256", "0" * 64), ("checkpoint_id", "1" * 64),
        ):
            with self.subTest(field=field):
                mutated = copy.deepcopy(prior)
                mutated["identity"][field] = replacement
                original_load = runner.load

                def injected_load(path: pathlib.Path) -> dict[str, object]:
                    return mutated if path == self.root / runner.PRIOR_ATTEMPT else original_load(path)

                with mock.patch.object(runner, "load", side_effect=injected_load):
                    with self.assertRaisesRegex(runner.M22FinalEvaluationError, "identity"):
                        runner.validate_prior_attempt_record(self.root, contract)

    def test_substitute_evaluator_cannot_bind_the_frozen_public_role(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw).resolve()
            substitute = directory / "substitute-evaluator"
            substitute.write_bytes(b"not the frozen evaluator\n")
            substitute.chmod(0o700)
            with self.assertRaisesRegex(artifact_context.ArtifactContextError, "SHA-256 mismatch"):
                LiveInputManifest.bind(
                    ArtifactContext.live(directory), {"final-v1-evaluator": substitute},
                )

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

    def test_failed_native_records_retain_the_exact_gate_failure_semantics(self) -> None:
        report = validator.load(self.root / validator.CONFIG)
        manifest = runner.load(self.root / runner.learning.EVALUATION)
        evaluator_schema = validator.load(self.root / runner.EVALUATOR_SCHEMA)
        run = next(item for item in report["runs"] if item["native"]["status"] == "FAIL")
        case = next(item for item in manifest["cases"] if item["case_id"] == run["public_case"]["case_id"])
        mutated = copy.deepcopy(run)
        mutated["native"]["failure_detail"] = "unrelated process failure"
        with self.assertRaisesRegex(validator.M22FinalEvidenceError, "failure semantics"):
            validator.validate_run(
                mutated, case, run["ordinal"], report["identity"], None, evaluator_schema,
            )

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
