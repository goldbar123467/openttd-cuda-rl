#!/usr/bin/env python3
"""Mutation tests for M15 lifecycle and replay evidence."""

from __future__ import annotations

import copy
import dataclasses
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    resolve_artifact_root,
)
import freeze_m15_episode_evidence


class M15EpisodeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = freeze_m15_episode_evidence.load_json(cls.root / freeze_m15_episode_evidence.CONFIG)
        cls.schema = cls.root / freeze_m15_episode_evidence.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "episode-evidence.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def materialize_synthetic_closure(
        base: pathlib.Path,
        requirements: tuple[ArtifactRequirement, ...],
    ) -> tuple[ArtifactRequirement, ...]:
        for requirement in requirements:
            path = base / requirement.logical_set / requirement.relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic episode fixture\n")
        return tuple(
            dataclasses.replace(requirement, expected_sha256=None)
            for requirement in requirements
        )

    def test_live_artifacts_pass(self) -> None:
        artifact_base = resolve_artifact_root(None)
        if artifact_base is None:
            self.skipTest("live artifact validation is outside offline mode")
        self.assertTrue(freeze_m15_episode_evidence.validate(
            self.root,
            artifact_context=ArtifactContext.live(artifact_base),
        ).live)

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_episode_evidence.M15EpisodeEvidenceError, "schema SHA-256"):
                freeze_m15_episode_evidence.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=ArtifactContext.offline(),
                )

    def test_rollback_claim_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["runs"][0]["rollback"]["state_exact"] = False
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(freeze_m15_episode_evidence.M15EpisodeEvidenceError):
                freeze_m15_episode_evidence.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=ArtifactContext.offline(),
                )

    def test_deterministic_trace_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["runs"][1]["trace_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_episode_evidence.M15EpisodeEvidenceError, "deterministic trace"):
                freeze_m15_episode_evidence.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=ArtifactContext.offline(),
                )

    def test_live_capture_binary_corruption_fails(self) -> None:
        artifact_base = resolve_artifact_root(None)
        if artifact_base is None:
            self.skipTest("live artifact validation is outside offline mode")
        source = artifact_base / self.config["artifact_root"]
        with tempfile.TemporaryDirectory() as raw:
            target = pathlib.Path(raw) / "evidence"
            shutil.copytree(source / "run-a", target / "run-a")
            binary = target / "run-a/artifacts/capture-branch-a-candidates.bin"
            data = bytearray(binary.read_bytes())
            data[0] ^= 1
            binary.write_bytes(data)
            with self.assertRaisesRegex(freeze_m15_episode_evidence.M15EpisodeEvidenceError, "capture candidates"):
                freeze_m15_episode_evidence.project_run(self.root, target, "run-a")

    def test_newly_frozen_evidence_validates_from_generated_set_parent(self) -> None:
        runs = {item["artifact_dir"]: item for item in self.config["runs"]}
        committed_path = self.root / freeze_m15_episode_evidence.CONFIG
        committed_bytes = committed_path.read_bytes()

        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            artifact_root = base / freeze_m15_episode_evidence.LOGICAL_ARTIFACT_SET
            synthetic_requirements = self.materialize_synthetic_closure(
                base,
                freeze_m15_episode_evidence.required_live_inputs(self.root),
            )
            output = base / "episode-evidence.json"
            with (
                mock.patch.object(
                    freeze_m15_episode_evidence,
                    "required_live_inputs",
                    return_value=synthetic_requirements,
                ),
                mock.patch.object(
                    freeze_m15_episode_evidence,
                    "project_run",
                    side_effect=lambda root, artifact, directory: copy.deepcopy(
                        runs[directory]
                    ),
                ) as run_reader,
            ):
                frozen = freeze_m15_episode_evidence.freeze(
                    self.root,
                    artifact_root,
                    output,
                )
            self.assertEqual(frozen.read_bytes(), committed_bytes)
            self.assertEqual(committed_path.read_bytes(), committed_bytes)
            self.assertEqual(
                freeze_m15_episode_evidence.load_json(frozen)["artifact_base_hint"],
                self.config["artifact_base_hint"],
            )
            self.assertEqual(
                [call.args for call in run_reader.call_args_list],
                [
                    (self.root, artifact_root, directory)
                    for directory in (
                        *freeze_m15_episode_evidence.RUN_DIRS,
                        *freeze_m15_episode_evidence.RUN_DIRS,
                    )
                ],
            )

    def test_live_preflight_rejects_missing_episode_inputs_before_read(self) -> None:
        runs = {item["artifact_dir"]: item for item in self.config["runs"]}
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            (base / self.config["artifact_root"]).mkdir()
            with mock.patch.object(
                freeze_m15_episode_evidence,
                "project_run",
                side_effect=lambda root, artifact, directory: copy.deepcopy(
                    runs[directory]
                ),
            ) as run_reader:
                with self.assertRaisesRegex(ArtifactContextError, "missing file"):
                    freeze_m15_episode_evidence.validate(
                        self.root,
                        artifact_context=ArtifactContext.live(base),
                    )
            run_reader.assert_not_called()

    def test_live_preflight_rejects_nested_episode_symlink_before_read(self) -> None:
        runs = {item["artifact_dir"]: item for item in self.config["runs"]}
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            set_root = base / self.config["artifact_root"]
            path = set_root / "run-a/resource.txt"
            path.parent.mkdir(parents=True)
            target = base / "outside-resource.txt"
            target.write_text("outside\n", encoding="utf-8")
            path.symlink_to(target)
            with mock.patch.object(
                freeze_m15_episode_evidence,
                "project_run",
                side_effect=lambda root, artifact, directory: copy.deepcopy(
                    runs[directory]
                ),
            ) as run_reader:
                with self.assertRaisesRegex(ArtifactContextError, "symlink traversal"):
                    freeze_m15_episode_evidence.validate(
                        self.root,
                        artifact_context=ArtifactContext.live(base),
                    )
            run_reader.assert_not_called()

    def test_live_preflight_rejects_episode_digest_before_read(self) -> None:
        runs = {item["artifact_dir"]: item for item in self.config["runs"]}
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            trace = (
                base
                / self.config["artifact_root"]
                / "run-a/episode-trace.json"
            )
            trace.parent.mkdir(parents=True)
            trace.write_bytes(b"wrong trace digest\n")
            with mock.patch.object(
                freeze_m15_episode_evidence,
                "project_run",
                side_effect=lambda root, artifact, directory: copy.deepcopy(
                    runs[directory]
                ),
            ) as run_reader:
                with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                    freeze_m15_episode_evidence.validate(
                        self.root,
                        artifact_context=ArtifactContext.live(base),
                    )
            run_reader.assert_not_called()

    def test_required_live_inputs_are_the_exact_episode_closure(self) -> None:
        fixed_files = (
            "episode-trace.json",
            "reset-projection.json",
            "resource.txt",
            "artifacts/route-ready.sav",
        )
        capture_files = tuple(
            f"artifacts/capture-branch-{branch}{suffix}"
            for branch in ("a", "b")
            for suffix in (
                ".sav",
                "-observation.json",
                "-observation.bin",
                "-candidates.json",
                "-candidates.bin",
            )
        )
        expected_paths = tuple(
            f"{run}/{filename}"
            for run in ("run-a", "run-b")
            for filename in fixed_files + capture_files
        )

        requirements = freeze_m15_episode_evidence.required_live_inputs(self.root)

        self.assertEqual(
            tuple(requirement.relative_path for requirement in requirements),
            expected_paths,
        )
        self.assertEqual(
            {requirement.logical_set for requirement in requirements},
            {"v2-m15-episode-evidence-a"},
        )
        self.assertEqual({requirement.kind for requirement in requirements}, {"file"})
        self.assertEqual(
            {requirement.consumer for requirement in requirements},
            {"m15-episode-evidence"},
        )
        by_path = {requirement.relative_path: requirement for requirement in requirements}
        self.assertEqual(
            by_path["run-a/episode-trace.json"].expected_sha256,
            self.config["runs"][0]["trace_sha256"],
        )
        self.assertEqual(
            by_path["run-b/artifacts/capture-branch-b-candidates.bin"].expected_sha256,
            self.config["runs"][1]["replay"]["candidate_sha256"],
        )

    def test_validation_only_cli_owns_offline_validation(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts/v2/validate_m15_episode_evidence.py"),
                "--root",
                str(self.root),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("V2_M15_EPISODE_EVIDENCE=PASS", completed.stdout)
        self.assertIn("live=false", completed.stdout)

    def test_creation_artifact_root_is_not_a_validation_base(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(self.root / "scripts/v2/freeze_m15_episode_evidence.py"),
                    "--root",
                    str(self.root),
                    "--artifact-root",
                    raw,
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("creation requires --output", completed.stderr)

    def test_generator_rejects_mixed_creation_and_validation_options(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(self.root / "scripts/v2/freeze_m15_episode_evidence.py"),
                    "--root",
                    str(self.root),
                    "--artifact-root",
                    raw,
                    "--output",
                    str(pathlib.Path(raw) / "evidence.json"),
                    "--config",
                    str(self.root / freeze_m15_episode_evidence.CONFIG),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
