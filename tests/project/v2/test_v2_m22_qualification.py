#!/usr/bin/env python3
"""Mutation tests for M22 selected-checkpoint qualification evidence."""

from __future__ import annotations

import copy
import hashlib
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
        checkpoint_root.mkdir(parents=True)
        checkpoint_files = []
        for name in recovery.INVENTORY:
            path = checkpoint_root / name
            data = (
                (selected["checkpoint_id"] + "\n").encode("ascii")
                if name == "COMMITTED"
                else f"byte-real selected checkpoint {name}\n".encode()
            )
            path.write_bytes(data)
            checkpoint_files.append({
                "bytes": path.stat().st_size,
                "name": name,
                "sha256": hashlib.sha256(data).hexdigest(),
            })
        selected_checkpoint["files"] = checkpoint_files
        self.rehash(training_report)
        (project / runner.TRAINING).write_bytes(recovery.canonical_bytes(training_report) + b"\n")

        value = copy.deepcopy(self.report)
        value["identity"]["checkpoint"] = copy.deepcopy(selected_checkpoint)
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
                mock.patch.object(validator.training_validator, "validate_value") as training_helper,
                mock.patch.object(validator.native_validator, "validate") as native_helper,
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
