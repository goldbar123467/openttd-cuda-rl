#!/usr/bin/env python3
"""Mutation tests for M22 selected-checkpoint qualification evidence."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
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
import run_m22_qualification as runner
import run_m22_recovery as recovery
import validate_m22_qualification_evidence as validator


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
    *,
    before_id: str | None = None,
) -> tuple[str, list[dict[str, object]]]:
    nonce = 0
    while True:
        suffix = f" {nonce}" if before_id is not None else ""
        payloads = {
            "model.pt": f"fixture model {architecture} {seed} {update}{suffix}\n".encode(),
            "optimizer.pt": f"fixture optimizer {architecture} {seed} {update}{suffix}\n".encode(),
            "runtime.pt": f"fixture runtime {architecture} {seed} {update}{suffix}\n".encode(),
            "selection.json": f'{{"architecture":"{architecture}","seed":{seed},"update":{update},"nonce":{nonce}}}\n'.encode(),
            "trainer-state.bin": f"fixture trainer state {architecture} {seed} {update}{suffix}\n".encode(),
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
        if before_id is None or checkpoint_id < before_id:
            break
        nonce += 1
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


def committed_fixture_bytes(project: pathlib.Path, commit: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=project,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout


def refresh_file_record(checkpoint: dict[str, object], path: pathlib.Path) -> None:
    record = next(item for item in checkpoint["files"] if item["name"] == path.name)
    record["bytes"] = path.stat().st_size
    record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


def bind_qualification_source(project: pathlib.Path, value: dict[str, object]) -> None:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    source_files = [
        {
            "path": relative,
            "sha256": hashlib.sha256(
                committed_fixture_bytes(project, commit, relative)
            ).hexdigest(),
        }
        for relative in runner.SOURCE_PATHS
    ]
    value["source"].update({
        "clean": True,
        "files": source_files,
        "repository_commit": commit,
        "tree_sha256": recovery.sha256_bytes(recovery.canonical_bytes(source_files)),
    })
    for key, relative in (
        ("learning_contract_sha256", runner.CONTRACT.as_posix()),
        ("native_corpus_sha256", runner.CORPUS.as_posix()),
        ("qualification_schema_sha256", runner.SCHEMA.as_posix()),
        ("training_evidence_sha256", runner.TRAINING.as_posix()),
    ):
        value["identity"][key] = hashlib.sha256(
            committed_fixture_bytes(project, commit, relative)
        ).hexdigest()


class M22QualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.evidence_path = cls.root / "config/v2/m22-qualification-evidence.json"
        cls.report = recovery.load(cls.evidence_path) if cls.evidence_path.is_file() else None

    @staticmethod
    def rehash(value: dict[str, object]) -> None:
        value.pop("report_sha256", None)
        value["report_sha256"] = recovery.sha256_bytes(recovery.canonical_bytes(value))

    def mutation_fails(self, value: dict[str, object], pattern: str) -> None:
        self.rehash(value)
        with self.assertRaisesRegex(validator.M22QualificationValidationError, pattern):
            validator.validate_value(value, self.root)

    def make_live_fixture(
        self,
        directory: pathlib.Path,
        *,
        commit_training: bool = True,
    ) -> tuple[pathlib.Path, dict[str, object], LiveInputManifest]:
        project = directory / "project"
        subprocess.run(
            ["git", "clone", "-q", "--no-hardlinks", str(self.root), str(project)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        training_report = recovery.load(project / runner.TRAINING)
        selected = training_report["provisional_development_selection"]
        selected_run = next(
            item for item in training_report["runs"]
            if item["architecture"] == selected["architecture"] and item["seed"] == selected["seed"]
        )
        selected_checkpoint = recovery.checkpoint(selected_run["process"], selected["update"])

        live_root = directory / "live"
        live_root.mkdir()
        training_artifacts = live_root / "training"
        checkpoint_root = training_artifacts / selected["checkpoint_path"]
        checkpoint_id, checkpoint_files = write_checkpoint_fixture(
            checkpoint_root.parent,
            selected["architecture"],
            selected["seed"],
            selected["update"],
            training_report["identity"]["learning_contract_sha256"],
            training_report["identity"]["native_corpus_sha256"],
            before_id=selected["checkpoint_id"],
        )
        selected_checkpoint["id"] = checkpoint_id
        selected_checkpoint["path"] = (
            pathlib.PurePosixPath(selected_checkpoint["path"]).parent / checkpoint_id
        ).as_posix()
        selected_checkpoint["files"] = checkpoint_files
        selected_candidate = next(
            item for item in selected_run["candidates"]
            if item["update"] == selected["update"]
        )
        selected_candidate["checkpoint_id"] = checkpoint_id
        selected_candidate["checkpoint_path"] = selected_checkpoint["path"]
        selected_run["provisional_selection"]["checkpoint_id"] = checkpoint_id
        selected_run["provisional_selection"]["checkpoint_path"] = selected_checkpoint["path"]
        selected["checkpoint_id"] = checkpoint_id
        selected["checkpoint_path"] = selected_checkpoint["path"]
        self.rehash(training_report)
        (project / runner.TRAINING).write_bytes(recovery.canonical_bytes(training_report) + b"\n")

        value = copy.deepcopy(self.report)
        value["identity"]["checkpoint"] = copy.deepcopy(selected_checkpoint)
        value["finalized_selection"]["checkpoint_id"] = checkpoint_id
        value["finalized_selection"]["checkpoint_path"] = selected_checkpoint["path"]
        value["device_result"]["checkpoint"]["id"] = checkpoint_id
        schema = recovery.load(project / runner.SCHEMA)
        schema["$defs"]["checkpoint"]["properties"]["id"]["const"] = checkpoint_id
        schema["$defs"]["selection"]["properties"]["checkpoint_id"]["const"] = checkpoint_id
        schema["$defs"]["device_result"]["properties"]["checkpoint"]["const"]["id"] = checkpoint_id
        (project / runner.SCHEMA).write_bytes(recovery.canonical_bytes(schema) + b"\n")
        subprocess.run(["git", "config", "user.name", "Task 5A fixture"], cwd=project, check=True)
        subprocess.run(["git", "config", "user.email", "task5a@example.invalid"], cwd=project, check=True)
        paths_to_commit = [runner.SCHEMA.as_posix()]
        if commit_training:
            paths_to_commit.append(runner.TRAINING.as_posix())
        subprocess.run(["git", "add", *paths_to_commit], cwd=project, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "Commit qualification fixture authority"],
            cwd=project,
            check=True,
        )
        bind_qualification_source(project, value)
        qualification_artifacts = live_root / "qualification"
        qualification_artifacts.mkdir()
        artifact_payloads = {
            "device-result.json": recovery.canonical_bytes(value["device_result"]) + b"\n",
            "gpu-monitor-summary.json": recovery.canonical_bytes(value["telemetry"]) + b"\n",
            "gpu-telemetry.jsonl": b'{"gpu_available":true,"fixture":"byte-real"}\n',
            "stderr.txt": b"",
            "stdout.txt": b"byte-real qualification stdout\n",
        }
        artifacts = []
        for name in runner.ARTIFACT_NAMES:
            path = qualification_artifacts / name
            path.write_bytes(artifact_payloads[name])
            artifacts.append({
                "bytes": path.stat().st_size,
                "path": name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
        value["artifacts"] = artifacts
        value["process"]["stderr_sha256"] = artifacts[3]["sha256"]
        value["process"]["stdout_sha256"] = artifacts[4]["sha256"]

        executable = live_root / "qualification-executable"
        executable.write_bytes(b"byte-real qualification executable\n")
        corpus = live_root / "corpus.bin"
        corpus.write_bytes(validator.training.encoder.encode(project))
        value["identity"]["qualification_executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
        value["identity"]["corpus_binary_sha256"] = hashlib.sha256(corpus.read_bytes()).hexdigest()
        self.rehash(value)
        live_inputs = LiveInputManifest(
            ValidationMode.LIVE,
            live_root,
            MappingProxyType({
                "qualification-artifacts": qualification_artifacts,
                "training-artifacts": training_artifacts,
                "qualification-executable": executable,
                "v2-corpus-binary": corpus,
            }),
        )
        return project, value, live_inputs

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
            ["git", "commit", "-q", "-m", "Commit qualification schema fixture"],
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
        value = copy.deepcopy(self.report)
        bind_qualification_source(project, value)
        self.rehash(value)
        report_path = directory / "qualification-report.json"
        report_path.write_bytes(recovery.canonical_bytes(value) + b"\n")
        return project, report_path, value

    def test_schema_is_strict_and_freezes_the_selected_checkpoint(self) -> None:
        schema = recovery.load(self.root / runner.SCHEMA)
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["$defs"]["selection"]["properties"]["checkpoint_id"]["const"],
            "03894fd1238b69b6724d82eb441380312be4e8226efa602fa5e43972f7fa9f5f",
        )

    def test_qualification_source_and_sandbox_exclude_final_manifest(self) -> None:
        self.assertNotIn(runner.FINAL_MANIFEST.as_posix(), runner.SOURCE_PATHS)
        self.assertEqual(runner.ARTIFACT_NAMES, tuple(sorted(runner.ARTIFACT_NAMES)))

    def test_repository_qualification_evidence_passes(self) -> None:
        if self.report is None:
            self.skipTest("qualification evidence has not yet been generated from a clean source commit")
        validator.validate_value(self.report, self.root)

    def test_historical_git_reads_ignore_hostile_environment(self) -> None:
        self.assertIsNotNone(self.report)
        with mock.patch.dict(
            os.environ,
            {"GIT_DIR": "/missing-hostile-git-dir", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.bare", "GIT_CONFIG_VALUE_0": "true"},
            clear=False,
        ):
            validator.validate_value(self.report, self.root)

    def test_historical_source_commit_path_order_digest_and_inventory_mutations_fail(self) -> None:
        self.assertIsNotNone(self.report)
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

    def test_historical_schema_failures_stay_in_qualification_domain(self) -> None:
        variants = {
            "malformed-json": b"{\n",
            "invalid-utf8": b"\xff\n",
            "invalid-json-schema": b'{"type":7}\n',
        }
        script = self.root / "scripts/v2/validate_m22_qualification_evidence.py"
        for label, schema_bytes in variants.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                directory = pathlib.Path(raw).resolve()
                project, report_path, value = self.make_historical_schema_fixture(
                    directory,
                    schema_bytes,
                )
                with self.assertRaisesRegex(
                    validator.M22QualificationValidationError,
                    "committed qualification schema is (?:malformed|invalid)",
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
                self.assertIn("V2_M22_QUALIFICATION_EVIDENCE=FAIL", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)

    def test_native_corpus_revalidation_is_explicitly_offline(self) -> None:
        self.assertIsNotNone(self.report)
        contexts: list[ArtifactContext | None] = []
        real_validate = validator.native_validator.validate

        def observe(root: pathlib.Path, *args: object, artifact_context: ArtifactContext | None = None, **kwargs: object) -> object:
            contexts.append(artifact_context)
            return real_validate(root, *args, artifact_context=artifact_context, **kwargs)

        with tempfile.TemporaryDirectory() as raw:
            project, value, live_inputs = self.make_live_fixture(pathlib.Path(raw).resolve())
            with mock.patch.object(validator.native_validator, "validate", side_effect=observe):
                validator.validate_value(
                    value,
                    project,
                    artifact_context=ArtifactContext.live(live_inputs.artifact_root),
                    live_inputs=live_inputs,
                )
        self.assertGreaterEqual(len(contexts), 1)
        self.assertTrue(any(context is not None for context in contexts))
        self.assertTrue(all(not context.is_live for context in contexts if context is not None))

    def test_nested_training_validation_cannot_traverse_live_artifacts(self) -> None:
        self.assertIsNotNone(self.report)
        contexts: list[ArtifactContext | None] = []
        real_validate = validator.training_validator.validate_value

        def observe(report: object, root: pathlib.Path, *args: object,
                    artifact_context: ArtifactContext | None = None, **kwargs: object) -> object:
            contexts.append(artifact_context)
            return real_validate(
                report,
                root,
                *args,
                artifact_context=artifact_context,
                **kwargs,
            )

        with tempfile.TemporaryDirectory() as raw:
            project, value, live_inputs = self.make_live_fixture(pathlib.Path(raw).resolve())
            with mock.patch.object(validator.training_validator, "validate_value", side_effect=observe):
                validator.validate_value(
                    value,
                    project,
                    artifact_context=ArtifactContext.live(live_inputs.artifact_root),
                    live_inputs=live_inputs,
                )
        self.assertEqual(len(contexts), 1)
        self.assertIsNotNone(contexts[0])
        self.assertFalse(contexts[0].is_live)

    def test_offline_validation_never_reads_qualification_artifacts(self) -> None:
        self.assertIsNotNone(self.report)
        with (
            mock.patch.object(
                recovery,
                "inspect_checkpoint",
                side_effect=AssertionError("offline qualification traversed a checkpoint"),
            ),
            mock.patch.object(
                validator,
                "validate_artifacts",
                side_effect=AssertionError("offline qualification traversed retained artifacts"),
                create=True,
            ),
        ):
            validator.validate_value(
                self.report,
                self.root,
                artifact_context=ArtifactContext.offline(),
                live_inputs=LiveInputManifest.offline(),
            )

    def test_required_live_inputs_are_the_exact_qualification_closure(self) -> None:
        self.assertIsNotNone(self.report)
        requirements = validator.required_live_inputs(self.root)
        selected = self.report["finalized_selection"]
        checkpoint = self.report["identity"]["checkpoint"]
        expected = [
            ("qualification-artifacts", item["path"], item["sha256"])
            for item in self.report["artifacts"]
        ]
        expected.extend(
            (
                "training-artifacts",
                f"{selected['checkpoint_path']}/{item['name']}",
                item["sha256"],
            )
            for item in checkpoint["files"]
        )
        expected.extend((
            (
                "qualification-executable",
                ".",
                self.report["identity"]["qualification_executable_sha256"],
            ),
            ("v2-corpus-binary", ".", self.report["identity"]["corpus_binary_sha256"]),
        ))
        self.assertEqual(len(requirements), 14)
        self.assertEqual(
            [(item.role, item.relative_path, item.expected_sha256) for item in requirements],
            expected,
        )

    def test_live_qualification_preflights_complete_closure_before_helpers(self) -> None:
        self.assertIsNotNone(self.report)
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            bindings = {}
            for role in (
                "qualification-artifacts",
                "training-artifacts",
            ):
                path = live_root / role
                path.mkdir()
                bindings[role] = path
            for role in ("qualification-executable", "v2-corpus-binary"):
                path = live_root / role
                path.write_bytes(b"wrong live input bytes\n")
                bindings[role] = path
            live_inputs = LiveInputManifest(
                ValidationMode.LIVE,
                live_root,
                MappingProxyType(bindings),
            )
            with (
                self.assertRaises(ArtifactContextError),
                mock.patch.object(
                    validator.training_validator,
                    "validate_value",
                    wraps=validator.training_validator.validate_value,
                ) as training_helper,
                mock.patch.object(
                    validator.native_validator,
                    "validate",
                    wraps=validator.native_validator.validate,
                ) as native_helper,
            ):
                validator.validate_value(
                    self.report,
                    self.root,
                    artifact_context=ArtifactContext.live(live_root),
                    live_inputs=live_inputs,
                )
            training_helper.assert_not_called()
            native_helper.assert_not_called()

    def test_live_qualification_requires_one_exact_context_root(self) -> None:
        self.assertIsNotNone(self.report)
        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as other_raw:
            context_root = pathlib.Path(raw).resolve()
            manifest_root = pathlib.Path(other_raw).resolve()
            live_inputs = LiveInputManifest(
                ValidationMode.LIVE,
                manifest_root,
                MappingProxyType({}),
            )
            with self.assertRaisesRegex(
                validator.M22QualificationValidationError,
                "one exact artifact root",
            ):
                validator.validate_value(
                    self.report,
                    self.root,
                    artifact_context=ArtifactContext.live(context_root),
                    live_inputs=live_inputs,
                )

    def test_relocated_live_qualification_uses_selected_checkpoint_only(self) -> None:
        self.assertIsNotNone(self.report)
        retained = copy.deepcopy(self.report)
        with tempfile.TemporaryDirectory() as raw:
            project, value, live_inputs = self.make_live_fixture(pathlib.Path(raw).resolve())
            validator.validate_value(
                value,
                project,
                artifact_context=ArtifactContext.live(live_inputs.artifact_root),
                live_inputs=live_inputs,
            )
        self.assertEqual(self.report, retained)

    def test_live_qualification_checkpoint_commit_marker_requires_exact_bytes(self) -> None:
        self.assertIsNotNone(self.report)
        with tempfile.TemporaryDirectory() as raw:
            fixture_root = pathlib.Path(raw).resolve()
            project, value, live_inputs = self.make_live_fixture(fixture_root)
            checkpoint = value["identity"]["checkpoint"]
            marker = fixture_root / "live" / "training" / checkpoint["path"] / "COMMITTED"
            marker.write_bytes(checkpoint["id"].encode("ascii") + b"\r\n")
            refresh_file_record(checkpoint, marker)

            training_report = recovery.load(project / runner.TRAINING)
            selected = training_report["provisional_development_selection"]
            selected_run = next(
                item for item in training_report["runs"]
                if item["architecture"] == selected["architecture"] and
                item["seed"] == selected["seed"]
            )
            selected_checkpoint = recovery.checkpoint(
                selected_run["process"], selected["update"],
            )
            refresh_file_record(selected_checkpoint, marker)
            self.rehash(training_report)
            (project / runner.TRAINING).write_bytes(
                recovery.canonical_bytes(training_report) + b"\n",
            )
            subprocess.run(["git", "add", runner.TRAINING.as_posix()], cwd=project, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "Commit exact marker evidence"],
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
            bind_qualification_source(project, value)
            self.rehash(value)
            with self.assertRaisesRegex(
                validator.M22QualificationValidationError,
                "checkpoint commit marker",
            ):
                validator.validate_value(
                    value,
                    project,
                    artifact_context=ArtifactContext.live(live_inputs.artifact_root),
                    live_inputs=live_inputs,
                )

    def test_offline_qualification_rejects_uncommitted_training_replacement(self) -> None:
        self.assertIsNotNone(self.report)
        retained = copy.deepcopy(self.report)
        with tempfile.TemporaryDirectory() as raw:
            project, value, _ = self.make_live_fixture(
                pathlib.Path(raw).resolve(),
                commit_training=False,
            )
            with self.assertRaisesRegex(
                validator.M22QualificationValidationError,
                "training evidence|checkpoint inventory",
            ):
                validator.validate_value(value, project)
        self.assertEqual(self.report, retained)

    def test_live_qualification_rejects_uncommitted_training_replacement(self) -> None:
        self.assertIsNotNone(self.report)
        retained = copy.deepcopy(self.report)
        with tempfile.TemporaryDirectory() as raw:
            project, value, live_inputs = self.make_live_fixture(
                pathlib.Path(raw).resolve(),
                commit_training=False,
            )
            with self.assertRaisesRegex(
                validator.M22QualificationValidationError,
                "training evidence|checkpoint inventory",
            ):
                validator.validate_value(
                    value,
                    project,
                    artifact_context=ArtifactContext.live(live_inputs.artifact_root),
                    live_inputs=live_inputs,
                )
        self.assertEqual(self.report, retained)

    def test_live_qualification_closes_only_selected_and_qualification_directories(self) -> None:
        self.assertIsNotNone(self.report)
        for label in ("qualification", "selected-checkpoint"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                fixture_root = pathlib.Path(raw).resolve()
                project, value, live_inputs = self.make_live_fixture(fixture_root)
                if label == "qualification":
                    directory = fixture_root / "live" / "qualification"
                else:
                    directory = fixture_root / "live" / "training" / value["finalized_selection"]["checkpoint_path"]
                (directory / "unexpected.bin").write_bytes(b"unexpected retained entry\n")
                with (
                    self.assertRaisesRegex(validator.M22QualificationValidationError, "exact inventory"),
                    mock.patch.object(
                        validator.training_validator,
                        "validate_value",
                        wraps=validator.training_validator.validate_value,
                    ) as training_helper,
                    mock.patch.object(
                        validator.native_validator,
                        "validate",
                        wraps=validator.native_validator.validate,
                    ) as native_helper,
                ):
                    validator.validate_value(
                        value,
                        project,
                        artifact_context=ArtifactContext.live(live_inputs.artifact_root),
                        live_inputs=live_inputs,
                    )
                training_helper.assert_not_called()
                native_helper.assert_not_called()

    def test_live_qualification_allows_unrelated_training_checkpoints(self) -> None:
        self.assertIsNotNone(self.report)
        with tempfile.TemporaryDirectory() as raw:
            project, value, live_inputs = self.make_live_fixture(pathlib.Path(raw).resolve())
            unrelated = live_inputs.artifact_root / "training" / "unrelated" / "checkpoints" / ("f" * 64)
            unrelated.mkdir(parents=True)
            (unrelated / "not-selected.bin").write_bytes(b"outside selected checkpoint closure\n")
            validator.validate_value(
                value,
                project,
                artifact_context=ArtifactContext.live(live_inputs.artifact_root),
                live_inputs=live_inputs,
            )

    def test_live_qualification_rejects_cross_role_hardlink_before_helpers(self) -> None:
        self.assertIsNotNone(self.report)
        with tempfile.TemporaryDirectory() as raw:
            project, value, live_inputs = self.make_live_fixture(pathlib.Path(raw).resolve())
            checkpoint = live_inputs.artifact_root / "training" / value["finalized_selection"]["checkpoint_path"]
            source = checkpoint / "model.pt"
            target = live_inputs.artifact_root / "qualification" / "stdout.txt"
            target.unlink()
            os.link(source, target)
            stdout_record = next(item for item in value["artifacts"] if item["path"] == "stdout.txt")
            stdout_record["bytes"] = target.stat().st_size
            stdout_record["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
            value["process"]["stdout_sha256"] = stdout_record["sha256"]
            self.rehash(value)
            with (
                self.assertRaisesRegex(validator.M22QualificationValidationError, "physical file alias"),
                mock.patch.object(
                    validator.training_validator,
                    "validate_value",
                    wraps=validator.training_validator.validate_value,
                ) as training_helper,
                mock.patch.object(
                    validator.native_validator,
                    "validate",
                    wraps=validator.native_validator.validate,
                ) as native_helper,
            ):
                validator.validate_value(
                    value,
                    project,
                    artifact_context=ArtifactContext.live(live_inputs.artifact_root),
                    live_inputs=live_inputs,
                )
            training_helper.assert_not_called()
            native_helper.assert_not_called()

    def test_live_qualification_missing_or_symlink_entry_fails_in_preflight(self) -> None:
        self.assertIsNotNone(self.report)
        for mutation in ("missing", "symlink"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as raw:
                project, value, live_inputs = self.make_live_fixture(pathlib.Path(raw).resolve())
                target = live_inputs.artifact_root / "qualification" / "stdout.txt"
                if mutation == "missing":
                    target.unlink()
                else:
                    real = target.with_name("stdout-real.txt")
                    target.rename(real)
                    target.symlink_to(real)
                with (
                    self.assertRaises(ArtifactContextError),
                    mock.patch.object(
                        validator.recovery_validator,
                        "_validate_live_structure",
                    ) as structure_guard,
                    mock.patch.object(validator.training_validator, "validate_value") as training_helper,
                    mock.patch.object(validator.native_validator, "validate") as native_helper,
                ):
                    validator.validate_value(
                        value,
                        project,
                        artifact_context=ArtifactContext.live(live_inputs.artifact_root),
                        live_inputs=live_inputs,
                    )
                structure_guard.assert_not_called()
                training_helper.assert_not_called()
                native_helper.assert_not_called()

    def test_public_validate_has_no_raw_path_bypass_and_loads_live_manifest(self) -> None:
        parameters = inspect.signature(validator.validate).parameters
        self.assertEqual(list(parameters), ["report_path", "root", "artifact_context"])
        self.assertEqual(parameters["artifact_context"].kind, inspect.Parameter.KEYWORD_ONLY)
        report_path = self.root / validator.REPORT
        with self.assertRaises(TypeError):
            validator.validate(report_path, self.root, self.root)
        with self.assertRaises(TypeError):
            validator.validate(report_path, self.root, training_artifact_root=self.root)
        with mock.patch.object(
            validator,
            "validate_artifacts",
            side_effect=AssertionError("contextless public validation read retained paths"),
        ):
            self.assertEqual(validator.validate(report_path, self.root), {"live": False})

        with tempfile.TemporaryDirectory() as raw:
            project, value, live_inputs = self.make_live_fixture(pathlib.Path(raw).resolve())
            relocated_report = live_inputs.artifact_root / "qualification.json"
            relocated_report.write_bytes(recovery.canonical_bytes(value) + b"\n")
            with mock.patch.object(validator.LiveInputManifest, "load", return_value=live_inputs):
                self.assertEqual(
                    validator.validate(
                        relocated_report,
                        project,
                        artifact_context=ArtifactContext.live(live_inputs.artifact_root),
                    ),
                    {"live": True},
                )

    def test_qualification_cli_is_offline_by_default_and_removes_raw_path_bypasses(self) -> None:
        script = self.root / "scripts/v2/validate_m22_qualification_evidence.py"
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
                "--training-artifact-root", "/tmp/training", "--executable", "/tmp/executable",
                "--corpus", "/tmp/corpus",
            ],
            cwd=self.root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(removed.returncode, 2)
        self.assertIn("unrecognized arguments", removed.stderr)

    def test_parity_tolerance_mutation_fails(self) -> None:
        if self.report is None:
            self.skipTest("qualification evidence has not yet been generated")
        value = copy.deepcopy(self.report)
        value["device_result"]["parity"][0]["forward_max_abs"] = 0.001
        self.mutation_fails(value, "parity tolerance")

    def test_benchmark_derivation_mutation_fails(self) -> None:
        if self.report is None:
            self.skipTest("qualification evidence has not yet been generated")
        value = copy.deepcopy(self.report)
        value["device_result"]["benchmarks"][0]["batches"][1]["speedup"] += 0.1
        self.mutation_fails(value, "speedup is not timing-derived")

    def test_native_source_mutation_fails(self) -> None:
        if self.report is None:
            self.skipTest("qualification evidence has not yet been generated")
        value = copy.deepcopy(self.report)
        value["native_retention"]["sources"][3]["sha256"] = "0" * 64
        self.mutation_fails(value, "native G15-G21 retention")

    def test_final_access_mutation_fails(self) -> None:
        if self.report is None:
            self.skipTest("qualification evidence has not yet been generated")
        value = copy.deepcopy(self.report)
        value["finalized_selection"]["final_manifest_accessed"] = True
        self.mutation_fails(value, "schema failed")

    def test_qualification_artifact_path_inventory_mutation_fails_offline(self) -> None:
        self.assertIsNotNone(self.report)
        value = copy.deepcopy(self.report)
        value["artifacts"][0]["path"] = "renamed-device-result.json"
        self.mutation_fails(value, "artifact path inventory")


if __name__ == "__main__":
    unittest.main()
