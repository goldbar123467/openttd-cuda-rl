#!/usr/bin/env python3
"""Foundation tests for the complete M22 training campaign tooling."""

from __future__ import annotations

import copy
import hashlib
import inspect
import os
import pathlib
import subprocess
import tempfile
import unittest
from types import MappingProxyType
from unittest import mock

import jsonschema

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    LiveInputManifest,
    ValidationMode,
)
import run_m22_training as runner
import run_m22_recovery as recovery
import validate_m22_training_evidence as validator


CHECKPOINT_SCHEMA = "v2-m22-generalist-checkpoint-v1"
CHECKPOINT_BOUNDARY = "after-completed-ppo-update-and-retention-check-before-next-rollout"


def fixture_checkpoint_id(fields: dict[str, str]) -> str:
    identity = "\n".join((
        fields["schema"], fields["contract"], fields["corpus"], fields["architecture"],
        fields["run_seed"], fields["model_sha256"], fields["optimizer_sha256"],
        fields["runtime_sha256"], fields["trainer_state_sha256"],
        fields["selection_sha256"], fields["boundary"],
    )) + "\n"
    return hashlib.sha256(identity.encode("ascii")).hexdigest()


def write_checkpoint_fixture(
    parent: pathlib.Path,
    architecture: str,
    seed: int,
    update: int,
    contract_sha256: str,
    corpus_sha256: str,
) -> tuple[str, list[dict[str, object]]]:
    payloads = {
        "model.pt": f"fixture model {architecture} {seed} {update}\n".encode(),
        "optimizer.pt": f"fixture optimizer {architecture} {seed} {update}\n".encode(),
        "runtime.pt": f"fixture runtime {architecture} {seed} {update}\n".encode(),
        "selection.json": f'{{"architecture":"{architecture}","seed":{seed},"update":{update}}}\n'.encode(),
        "trainer-state.bin": f"fixture trainer state {architecture} {seed} {update}\n".encode(),
    }
    digests = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    fields = {
        "schema": CHECKPOINT_SCHEMA,
        "contract": contract_sha256,
        "corpus": corpus_sha256,
        "architecture": architecture,
        "run_seed": str(seed),
        "checkpoint_id": "",
        "model_sha256": digests["model.pt"],
        "optimizer_sha256": digests["optimizer.pt"],
        "runtime_sha256": digests["runtime.pt"],
        "trainer_state_sha256": digests["trainer-state.bin"],
        "selection_sha256": digests["selection.json"],
        "boundary": CHECKPOINT_BOUNDARY,
    }
    checkpoint_id = fixture_checkpoint_id(fields)
    fields["checkpoint_id"] = checkpoint_id
    directory = parent / checkpoint_id
    directory.mkdir(parents=True)
    for name, data in payloads.items():
        (directory / name).write_bytes(data)
    (directory / "m22.manifest").write_text(
        "".join(f"{name}={value}\n" for name, value in fields.items()),
        encoding="ascii",
    )
    (directory / "COMMITTED").write_text(checkpoint_id + "\n", encoding="ascii")
    files = [
        {
            "bytes": (directory / name).stat().st_size,
            "name": name,
            "sha256": hashlib.sha256((directory / name).read_bytes()).hexdigest(),
        }
        for name in recovery.INVENTORY
    ]
    return checkpoint_id, files


def refresh_file_record(checkpoint: dict[str, object], path: pathlib.Path) -> None:
    record = next(item for item in checkpoint["files"] if item["name"] == path.name)
    record["bytes"] = path.stat().st_size
    record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


def committed_fixture_bytes(project: pathlib.Path, commit: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=project,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


class M22TrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.report = recovery.load(cls.root / "config/v2/m22-training-evidence.json")

    @staticmethod
    def rehash(value: dict[str, object]) -> None:
        value.pop("report_sha256", None)
        value["report_sha256"] = hashlib.sha256(recovery.canonical_bytes(value)).hexdigest()

    def mutation_fails(self, value: dict[str, object], pattern: str) -> None:
        self.rehash(value)
        with self.assertRaisesRegex(validator.M22TrainingValidationError, pattern):
            validator.validate_value(value, self.root)

    def make_live_fixture(self, live_root: pathlib.Path) -> tuple[dict[str, object], LiveInputManifest]:
        value = copy.deepcopy(self.report)
        artifact_root = live_root / "training"
        artifact_root.mkdir()
        for run in value["runs"]:
            process = run["process"]
            log = artifact_root / process["log_path"]
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_bytes(f"byte-real {process['log_path']}\n".encode())
            process["stdout_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
            for checkpoint in process["checkpoints"]:
                old_path = pathlib.PurePosixPath(checkpoint["path"])
                checkpoint_id, files = write_checkpoint_fixture(
                    artifact_root.joinpath(*old_path.parent.parts),
                    run["architecture"],
                    run["seed"],
                    checkpoint["update"],
                    value["identity"]["learning_contract_sha256"],
                    value["identity"]["native_corpus_sha256"],
                )
                checkpoint["id"] = checkpoint_id
                checkpoint["path"] = (old_path.parent / checkpoint_id).as_posix()
                checkpoint["files"] = files
            checkpoints = {item["update"]: item for item in process["checkpoints"]}
            for candidate in run["candidates"]:
                checkpoint = checkpoints[candidate["update"]]
                candidate["checkpoint_id"] = checkpoint["id"]
                candidate["checkpoint_path"] = checkpoint["path"]
            run["provisional_selection"] = runner.select(run["candidates"])
        all_candidates = [
            {"architecture": run["architecture"], "seed": run["seed"], **candidate}
            for run in value["runs"]
            for candidate in run["candidates"]
        ]
        selected = runner.select(all_candidates)
        value["provisional_development_selection"].update({
            "architecture": selected["architecture"],
            "seed": selected["seed"],
            "update": selected["update"],
            "checkpoint_id": selected["checkpoint_id"],
            "checkpoint_path": selected["checkpoint_path"],
        })
        executable = live_root / "campaign"
        executable.write_bytes(b"byte-real relocated campaign executable\n")
        corpus = live_root / "corpus.bin"
        corpus.write_bytes(validator.encoder.encode(self.root))
        value["identity"]["campaign_executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
        value["identity"]["corpus_binary_sha256"] = hashlib.sha256(corpus.read_bytes()).hexdigest()
        self.rehash(value)
        live_inputs = LiveInputManifest(
            ValidationMode.LIVE,
            live_root,
            MappingProxyType({
                "training-artifacts": artifact_root,
                "v2-campaign-executable": executable,
                "v2-corpus-binary": corpus,
            }),
        )
        return value, live_inputs

    def make_historical_schema_fixture(
        self,
        directory: pathlib.Path,
        schema_bytes: bytes,
    ) -> tuple[pathlib.Path, pathlib.Path, dict[str, object]]:
        project = directory / "project"
        subprocess.run(
            ["git", "clone", "-q", "--no-hardlinks", str(self.root), str(project)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(["git", "config", "user.name", "Task 5A fixture"], cwd=project, check=True)
        subprocess.run(["git", "config", "user.email", "task5a@example.invalid"], cwd=project, check=True)
        (project / runner.SCHEMA).write_bytes(schema_bytes)
        subprocess.run(["git", "add", runner.SCHEMA.as_posix()], cwd=project, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "Commit training schema fixture"],
            cwd=project,
            check=True,
        )
        self.assertEqual(
            subprocess.run(
                ["git", "status", "--porcelain"], cwd=project, check=True,
                text=True, stdout=subprocess.PIPE,
            ).stdout,
            "",
        )
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=project, check=True,
            text=True, stdout=subprocess.PIPE,
        ).stdout.strip()
        value = copy.deepcopy(self.report)
        source_files = [
            {
                "path": relative,
                "sha256": hashlib.sha256(
                    committed_fixture_bytes(project, commit, relative)
                ).hexdigest(),
            }
            for relative in runner.SOURCE_PATHS
        ]
        source_hashes = {item["path"]: item["sha256"] for item in source_files}
        value["source"].update({
            "clean": True,
            "files": source_files,
            "repository_commit": commit,
            "tree_sha256": recovery.sha256_bytes(recovery.canonical_bytes(source_files)),
        })
        value["identity"]["learning_contract_sha256"] = source_hashes[runner.CONTRACT.as_posix()]
        value["identity"]["native_corpus_sha256"] = source_hashes[runner.CORPUS.as_posix()]
        value["identity"]["recovery_evidence_sha256"] = source_hashes[runner.RECOVERY.as_posix()]
        value["identity"]["training_schema_sha256"] = hashlib.sha256(schema_bytes).hexdigest()
        self.rehash(value)
        report_path = directory / "training-report.json"
        report_path.write_bytes(recovery.canonical_bytes(value) + b"\n")
        return project, report_path, value

    def test_training_schema_is_strict_and_valid(self) -> None:
        schema = recovery.load(self.root / runner.SCHEMA)
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["configuration"]["properties"]["seeds"]["const"], list(runner.SEEDS))

    def test_random_baseline_is_deterministic_and_seeded(self) -> None:
        first = [runner.random_correct(runner.SEEDS[0], 7, index) for index in range(128)]
        second = [runner.random_correct(runner.SEEDS[0], 7, index) for index in range(128)]
        other = [runner.random_correct(runner.SEEDS[1], 7, index) for index in range(128)]
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertGreater(sum(first), 0)
        self.assertLess(sum(first), len(first))

    def test_matched_baselines_use_exact_transition_budget(self) -> None:
        counts = [0] + [384] * 16
        rewards = {program: 1.0 + program / 100 for program in range(1, 17)}
        result = runner.matched_baselines(runner.SEEDS[0], counts, rewards)
        self.assertEqual([item["baseline"] for item in result], list(runner.BASELINES))
        self.assertTrue(all(item["matched_transitions"] == 6144 for item in result))
        self.assertEqual(result[0]["correct_program_fraction"], 1.0)
        self.assertEqual(result[-1]["mean_return"], 0.0)
        self.assertGreater(result[0]["mean_return"], result[1]["mean_return"])

    def test_selection_uses_complete_frozen_ordering(self) -> None:
        base = {"eligible": True, "service_count": 16, "mean_development_return": 2.0,
                "mean_company_value": 100.0, "transitions": 4096, "checkpoint_id": "b" * 64}
        lower_id = dict(base, checkpoint_id="a" * 64)
        later = dict(base, transitions=5120, checkpoint_id="0" * 64)
        self.assertEqual(runner.select([base, lower_id, later]), lower_id)

    def test_training_source_and_sandbox_exclude_final_manifest(self) -> None:
        self.assertNotIn(recovery.FINAL_MANIFEST.as_posix(), runner.SOURCE_PATHS)
        self.assertEqual(runner.ARCHITECTURES, recovery.ARCHITECTURES)
        self.assertEqual(len(runner.ARCHITECTURES) * len(runner.SEEDS), 6)

    def test_repository_training_evidence_passes(self) -> None:
        validator.validate_value(self.report, self.root)

    def test_historical_git_reads_ignore_hostile_environment(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"GIT_DIR": "/missing-hostile-git-dir", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "true"},
            clear=False,
        ):
            validator.validate_value(self.report, self.root)

    def test_historical_source_commit_path_order_digest_and_inventory_mutations_fail(self) -> None:
        mutations = {
            "commit": lambda value: value["source"].__setitem__("repository_commit", "0" * 40),
            "path": lambda value: value["source"]["files"][0].__setitem__("path", "wrong/path"),
            "order": lambda value: value["source"]["files"].__setitem__(slice(0, 2), list(reversed(value["source"]["files"][:2]))),
            "digest": lambda value: value["source"]["files"][0].__setitem__("sha256", "0" * 64),
            "inventory": lambda value: value["source"].__setitem__("tree_sha256", "0" * 64),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                value = copy.deepcopy(self.report)
                mutate(value)
                self.mutation_fails(value, "source commit|source identity")

    def test_historical_schema_failures_stay_in_training_domain(self) -> None:
        variants = {
            "malformed-json": b"{\n",
            "invalid-utf8": b"\xff\n",
            "invalid-json-schema": b'{"type":7}\n',
        }
        script = self.root / "scripts/v2/validate_m22_training_evidence.py"
        for label, schema_bytes in variants.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                directory = pathlib.Path(raw).resolve()
                project, report_path, value = self.make_historical_schema_fixture(
                    directory,
                    schema_bytes,
                )
                with self.assertRaisesRegex(
                    validator.M22TrainingValidationError,
                    "committed training schema is (?:malformed|invalid)",
                ) as raised:
                    validator.validate_value(value, project)
                self.assertIsNotNone(raised.exception.__cause__)
                completed = subprocess.run(
                    [
                        "python3", str(script), "--root", str(project),
                        "--report", str(report_path),
                    ],
                    cwd=project,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(completed.returncode, 1)
                self.assertIn("V2_M22_TRAINING_EVIDENCE=FAIL", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)

    def test_offline_validation_never_reads_training_artifacts(self) -> None:
        with mock.patch.object(
            validator,
            "validate_artifacts",
            side_effect=AssertionError("offline training traversed retained artifacts"),
        ):
            validator.validate_value(
                self.report,
                self.root,
                artifact_context=ArtifactContext.offline(),
                live_inputs=LiveInputManifest.offline(),
            )

    def test_required_live_inputs_are_the_exact_training_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        expected_artifacts = []
        for run in self.report["runs"]:
            process = run["process"]
            expected_artifacts.append((process["log_path"], process["stdout_sha256"]))
            for checkpoint in process["checkpoints"]:
                expected_artifacts.extend(
                    (f"{checkpoint['path']}/{item['name']}", item["sha256"])
                    for item in checkpoint["files"]
                )
        self.assertEqual(len(requirements), 260)
        self.assertEqual(
            [(item.relative_path, item.expected_sha256) for item in requirements[:-2]],
            expected_artifacts,
        )
        self.assertEqual({item.role for item in requirements[:-2]}, {"training-artifacts"})
        self.assertEqual(
            [(item.role, item.relative_path, item.expected_sha256) for item in requirements[-2:]],
            [
                ("v2-campaign-executable", ".", self.report["identity"]["campaign_executable_sha256"]),
                ("v2-corpus-binary", ".", self.report["identity"]["corpus_binary_sha256"]),
            ],
        )

    def test_live_training_preflights_complete_closure_before_artifact_reader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            artifact_root = live_root / "training"
            artifact_root.mkdir()
            executable = live_root / "campaign"
            corpus = live_root / "corpus.bin"
            executable.write_bytes(b"wrong campaign bytes\n")
            corpus.write_bytes(b"wrong corpus bytes\n")
            live_inputs = LiveInputManifest(
                ValidationMode.LIVE,
                live_root,
                MappingProxyType({
                    "training-artifacts": artifact_root,
                    "v2-campaign-executable": executable,
                    "v2-corpus-binary": corpus,
                }),
            )
            with (
                self.assertRaises(ArtifactContextError),
                mock.patch.object(validator, "validate_artifacts") as artifact_reader,
            ):
                validator.validate_value(
                    self.report,
                    self.root,
                    artifact_context=ArtifactContext.live(live_root),
                    live_inputs=live_inputs,
                )
            artifact_reader.assert_not_called()

    def test_relocated_live_training_logs_checkpoints_and_binaries_pass(self) -> None:
        retained = copy.deepcopy(self.report)
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            value, live_inputs = self.make_live_fixture(live_root)
            validator.validate_value(
                value,
                self.root,
                artifact_context=ArtifactContext.live(live_root),
                live_inputs=live_inputs,
            )
        self.assertEqual(self.report, retained)

    def test_live_training_checkpoint_commit_marker_requires_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            value, live_inputs = self.make_live_fixture(live_root)
            checkpoint = value["runs"][0]["process"]["checkpoints"][0]
            marker = live_root / "training" / checkpoint["path"] / "COMMITTED"
            marker.write_bytes(checkpoint["id"].encode("ascii") + b"\r\n")
            refresh_file_record(checkpoint, marker)
            self.rehash(value)
            with self.assertRaisesRegex(
                validator.M22TrainingValidationError,
                "checkpoint commit marker",
            ):
                validator.validate_value(
                    value,
                    self.root,
                    artifact_context=ArtifactContext.live(live_root),
                    live_inputs=live_inputs,
                )

    def test_live_training_closes_checkpoint_directories_before_reader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            value, live_inputs = self.make_live_fixture(live_root)
            checkpoint = value["runs"][0]["process"]["checkpoints"][0]
            directory = live_root / "training" / checkpoint["path"]
            (directory / "unexpected.bin").write_bytes(b"extra checkpoint entry\n")
            with (
                self.assertRaisesRegex(validator.M22TrainingValidationError, "exact inventory"),
                mock.patch.object(validator, "validate_artifacts") as artifact_reader,
            ):
                validator.validate_value(
                    value,
                    self.root,
                    artifact_context=ArtifactContext.live(live_root),
                    live_inputs=live_inputs,
                )
            artifact_reader.assert_not_called()

    def test_live_training_rejects_cross_checkpoint_hardlink_before_reader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            value, live_inputs = self.make_live_fixture(live_root)
            checkpoints = value["runs"][0]["process"]["checkpoints"]
            source = live_root / "training" / checkpoints[0]["path"] / "model.pt"
            target = live_root / "training" / checkpoints[1]["path"] / "model.pt"
            target.unlink()
            os.link(source, target)
            refresh_file_record(checkpoints[1], target)
            candidate = next(item for item in value["runs"][0]["candidates"] if item["update"] == checkpoints[1]["update"])
            candidate["checkpoint_id"] = checkpoints[1]["id"]
            candidate["checkpoint_path"] = checkpoints[1]["path"]
            self.rehash(value)
            with (
                self.assertRaisesRegex(validator.M22TrainingValidationError, "physical file alias"),
                mock.patch.object(validator, "validate_artifacts") as artifact_reader,
            ):
                validator.validate_value(
                    value,
                    self.root,
                    artifact_context=ArtifactContext.live(live_root),
                    live_inputs=live_inputs,
                )
            artifact_reader.assert_not_called()

    def test_live_training_missing_or_symlink_entry_fails_in_preflight(self) -> None:
        for mutation in ("missing", "symlink"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as raw:
                live_root = pathlib.Path(raw).resolve()
                value, live_inputs = self.make_live_fixture(live_root)
                checkpoint = value["runs"][0]["process"]["checkpoints"][0]
                target = live_root / "training" / checkpoint["path"] / "model.pt"
                if mutation == "missing":
                    target.unlink()
                else:
                    real = target.with_name("model-real.pt")
                    target.rename(real)
                    target.symlink_to(real)
                with (
                    self.assertRaises(ArtifactContextError),
                    mock.patch.object(
                        validator.recovery_validator,
                        "_validate_live_structure",
                    ) as structure_guard,
                    mock.patch.object(validator, "validate_artifacts") as artifact_reader,
                ):
                    validator.validate_value(
                        value,
                        self.root,
                        artifact_context=ArtifactContext.live(live_root),
                        live_inputs=live_inputs,
                    )
                structure_guard.assert_not_called()
                artifact_reader.assert_not_called()

    def test_public_validate_has_no_raw_path_bypass_and_loads_live_manifest(self) -> None:
        parameters = inspect.signature(validator.validate).parameters
        self.assertEqual(list(parameters), ["report_path", "root", "artifact_context"])
        self.assertEqual(parameters["artifact_context"].kind, inspect.Parameter.KEYWORD_ONLY)
        report_path = self.root / validator.REPORT
        with self.assertRaises(TypeError):
            validator.validate(report_path, self.root, self.root)
        with self.assertRaises(TypeError):
            validator.validate(report_path, self.root, executable=self.root)
        with mock.patch.object(
            validator,
            "validate_artifacts",
            side_effect=AssertionError("contextless public validation read retained paths"),
        ):
            self.assertEqual(validator.validate(report_path, self.root), {"live": False})

        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            value, live_inputs = self.make_live_fixture(live_root)
            relocated_report = live_root / "training.json"
            relocated_report.write_bytes(recovery.canonical_bytes(value) + b"\n")
            with mock.patch.object(validator.LiveInputManifest, "load", return_value=live_inputs):
                self.assertEqual(
                    validator.validate(
                        relocated_report,
                        self.root,
                        artifact_context=ArtifactContext.live(live_root),
                    ),
                    {"live": True},
                )

    def test_relocated_live_training_symlink_fails_before_artifact_reader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            value, live_inputs = self.make_live_fixture(live_root)
            first = live_inputs.resolve(validator._requirements(value)[0])
            target = first.with_name("real-log")
            first.rename(target)
            first.symlink_to(target)
            with (
                self.assertRaises(ArtifactContextError),
                mock.patch.object(validator, "validate_artifacts") as artifact_reader,
            ):
                validator.validate_value(
                    value,
                    self.root,
                    artifact_context=ArtifactContext.live(live_root),
                    live_inputs=live_inputs,
                )
            artifact_reader.assert_not_called()

    def test_training_cli_is_offline_by_default_and_removes_raw_binary_bypasses(self) -> None:
        script = self.root / "scripts/v2/validate_m22_training_evidence.py"
        report = self.root / validator.REPORT
        completed = subprocess.run(
            ["python3", str(script), "--root", str(self.root), "--report", str(report)],
            cwd=self.root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("live=false", completed.stdout)
        removed = subprocess.run(
            [
                "python3", str(script), "--root", str(self.root), "--report", str(report),
                "--executable", "/tmp/executable", "--corpus", "/tmp/corpus",
            ],
            cwd=self.root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(removed.returncode, 2)
        self.assertIn("unrecognized arguments", removed.stderr)

    def test_update_trace_mutation_fails(self) -> None:
        value = copy.deepcopy(self.report)
        value["runs"][0]["process"]["updates"][0]["trace"]["actions_sha256"] = "0" * 64
        self.mutation_fails(value, "update digest")

    def test_checkpoint_path_and_inventory_mutations_fail_offline(self) -> None:
        for label, mutate in (
            (
                "path",
                lambda checkpoint: checkpoint.__setitem__("path", "../outside/" + checkpoint["id"]),
            ),
            (
                "inventory",
                lambda checkpoint: checkpoint["files"][0].__setitem__("name", "wrong-name"),
            ),
        ):
            with self.subTest(label=label):
                value = copy.deepcopy(self.report)
                mutate(value["runs"][0]["process"]["checkpoints"][0])
                self.mutation_fails(value, "checkpoint inventory/path")

    def test_checkpoint_path_and_id_cannot_be_reused_across_updates_offline(self) -> None:
        value = copy.deepcopy(self.report)
        run = value["runs"][0]
        source = recovery.checkpoint(run["process"], 8)
        target = recovery.checkpoint(run["process"], 16)
        target.update({
            "files": copy.deepcopy(source["files"]),
            "id": source["id"],
            "path": source["path"],
        })
        candidate = next(item for item in run["candidates"] if item["update"] == 16)
        candidate["checkpoint_id"] = target["id"]
        candidate["checkpoint_path"] = target["path"]
        run["provisional_selection"] = runner.select(run["candidates"])
        all_candidates = [
            {"architecture": item["architecture"], "seed": item["seed"], **candidate_item}
            for item in value["runs"]
            for candidate_item in item["candidates"]
        ]
        selected = runner.select(all_candidates)
        value["provisional_development_selection"].update({
            "architecture": selected["architecture"],
            "checkpoint_id": selected["checkpoint_id"],
            "checkpoint_path": selected["checkpoint_path"],
            "seed": selected["seed"],
            "update": selected["update"],
        })
        self.rehash(value)
        with (
            self.assertRaisesRegex(
                validator.M22TrainingValidationError,
                "checkpoint (?:path|identity) is reused",
            ),
            mock.patch.object(
                validator,
                "validate_artifacts",
                side_effect=AssertionError("offline duplicate check traversed artifacts"),
            ) as artifact_reader,
        ):
            validator.validate_value(
                value,
                self.root,
                artifact_context=ArtifactContext.offline(),
                live_inputs=LiveInputManifest.offline(),
            )
        artifact_reader.assert_not_called()

    def test_checkpoint_id_cannot_be_reused_across_distinct_runs_offline(self) -> None:
        value = copy.deepcopy(self.report)
        source_run = value["runs"][0]
        target_run = value["runs"][1]
        source = recovery.checkpoint(source_run["process"], 8)
        target = recovery.checkpoint(target_run["process"], 8)
        target.update({
            "files": copy.deepcopy(source["files"]),
            "id": source["id"],
            "path": (
                f"{target_run['architecture']}/seed-{target_run['seed']}"
                f"/training/checkpoints/{source['id']}"
            ),
        })
        candidate = next(item for item in target_run["candidates"] if item["update"] == 8)
        candidate["checkpoint_id"] = target["id"]
        candidate["checkpoint_path"] = target["path"]
        target_run["provisional_selection"] = runner.select(target_run["candidates"])
        all_candidates = [
            {"architecture": item["architecture"], "seed": item["seed"], **candidate_item}
            for item in value["runs"]
            for candidate_item in item["candidates"]
        ]
        selected = runner.select(all_candidates)
        value["provisional_development_selection"].update({
            "architecture": selected["architecture"],
            "checkpoint_id": selected["checkpoint_id"],
            "checkpoint_path": selected["checkpoint_path"],
            "seed": selected["seed"],
            "update": selected["update"],
        })
        self.rehash(value)
        with (
            self.assertRaisesRegex(
                validator.M22TrainingValidationError,
                "checkpoint identity is reused",
            ),
            mock.patch.object(
                validator,
                "validate_artifacts",
                side_effect=AssertionError("offline duplicate check traversed artifacts"),
            ) as artifact_reader,
        ):
            validator.validate_value(
                value,
                self.root,
                artifact_context=ArtifactContext.offline(),
                live_inputs=LiveInputManifest.offline(),
            )
        artifact_reader.assert_not_called()

    def test_training_log_paths_are_safe_unique_and_run_bound_offline(self) -> None:
        mutations = {
            "parent": "../escape.log",
            "absolute": "/tmp/campaign.log",
            "dot": "./campaign.log",
            "empty": "",
            "empty-component": "monolithic-generalist-v1//campaign.log",
            "backslash": "monolithic-generalist-v1\\campaign.log",
            "nul": "monolithic-generalist-v1/campaign\x00.log",
            "duplicate": self.report["runs"][0]["process"]["log_path"],
        }
        for label, path in mutations.items():
            with self.subTest(label=label):
                value = copy.deepcopy(self.report)
                target = value["runs"][1]["process"] if label == "duplicate" else value["runs"][0]["process"]
                target["log_path"] = path
                self.rehash(value)
                with self.assertRaisesRegex(validator.M22TrainingValidationError, "log path|log_path"):
                    validator.validate_value(value, self.root)

    def test_process_identity_reuse_fails(self) -> None:
        value = copy.deepcopy(self.report)
        value["runs"][1]["process"]["pid"] = value["runs"][0]["process"]["pid"]
        self.mutation_fails(value, "six fresh processes")

    def test_candidate_metric_mutation_fails(self) -> None:
        value = copy.deepcopy(self.report)
        value["runs"][2]["candidates"][3]["mean_development_return"] += 0.01
        self.mutation_fails(value, "candidate metrics")

    def test_overall_selection_mutation_fails(self) -> None:
        value = copy.deepcopy(self.report)
        value["provisional_development_selection"]["checkpoint_id"] = "0" * 64
        self.mutation_fails(value, "overall development selection")


if __name__ == "__main__":
    unittest.main()
