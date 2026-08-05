#!/usr/bin/env python3
"""Mutation tests for frozen M15 bounded-observation evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from artifact_context import ArtifactContext, resolve_artifact_root
import freeze_m15_observation_evidence
import qualify_m15_observation


class M15ObservationEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = freeze_m15_observation_evidence.load_json(cls.root / freeze_m15_observation_evidence.CONFIG)
        cls.schema = cls.root / freeze_m15_observation_evidence.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "observation-evidence.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def test_repository_evidence_passes(self) -> None:
        summary = freeze_m15_observation_evidence.validate(
            self.root,
            artifact_context=ArtifactContext.offline(),
        )
        self.assertEqual((summary.cases, summary.passed), (4, 4))

    def test_live_artifacts_pass(self) -> None:
        artifact_base = resolve_artifact_root(None)
        if artifact_base is None:
            self.skipTest("live artifact validation is outside offline mode")
        self.assertTrue(freeze_m15_observation_evidence.validate(
            self.root,
            artifact_context=ArtifactContext.live(artifact_base),
        ).live)

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_observation_evidence.M15ObservationEvidenceError, "schema SHA-256"):
                freeze_m15_observation_evidence.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=ArtifactContext.offline(),
                )

    def test_binary_digest_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["cases"][0]["binary_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_observation_evidence.M15ObservationEvidenceError, "deterministic lock"):
                freeze_m15_observation_evidence.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=ArtifactContext.offline(),
                )

    def test_case_order_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["cases"][0], value["cases"][1] = value["cases"][1], value["cases"][0]
        value["summary"] = freeze_m15_observation_evidence.summarize(value["cases"])
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_observation_evidence.M15ObservationEvidenceError, "dimensions/order"):
                freeze_m15_observation_evidence.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=ArtifactContext.offline(),
                )

    def test_live_binary_corruption_fails(self) -> None:
        artifact_base = resolve_artifact_root(None)
        if artifact_base is None:
            self.skipTest("live artifact validation is outside offline mode")
        source_root = artifact_base / self.config["artifact_root"]
        with tempfile.TemporaryDirectory() as raw:
            temporary_base = pathlib.Path(raw)
            target_root = temporary_base / self.config["artifact_root"]
            import shutil
            shutil.copytree(source_root, target_root)
            binary = target_root / "reset-0064x0064" / "observation-metadata.bin"
            data = bytearray(binary.read_bytes())
            data[2048] ^= 1
            binary.write_bytes(data)
            with self.assertRaisesRegex(qualify_m15_observation.M15ObservationError, "SHA-256"):
                freeze_m15_observation_evidence.case_from_artifact(self.root, target_root, "reset-0064x0064")

    def test_newly_frozen_evidence_validates_from_generated_set_parent(self) -> None:
        cases = {item["artifact_dir"]: item for item in self.config["cases"]}
        observed: dict[str, object] = {}

        def validate_generated(
            root: pathlib.Path,
            config_path: pathlib.Path,
            schema_path: pathlib.Path | None = None,
            *,
            artifact_context: ArtifactContext | None = None,
        ) -> None:
            self.assertEqual(root, self.root)
            self.assertIsNone(schema_path)
            self.assertIsNotNone(artifact_context)
            assert artifact_context is not None
            self.assertTrue(artifact_context.is_live)
            observed["artifact_root"] = artifact_context.artifact_root
            observed["bytes"] = config_path.read_bytes()

        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            artifact_root = (
                base / freeze_m15_observation_evidence.LOGICAL_ARTIFACT_SET
            )
            artifact_root.mkdir()
            output = base / "observation-evidence.json"
            with (
                mock.patch.object(
                    freeze_m15_observation_evidence,
                    "case_from_artifact",
                    side_effect=lambda root, artifact, directory: copy.deepcopy(
                        cases.get(directory, self.config["cases"][0])
                    ),
                ),
                mock.patch.object(
                    freeze_m15_observation_evidence,
                    "validate",
                    side_effect=validate_generated,
                ),
            ):
                frozen = freeze_m15_observation_evidence.freeze(
                    self.root,
                    artifact_root,
                    output,
                )
            self.assertEqual(frozen.read_bytes(), observed["bytes"])
            self.assertEqual(observed["artifact_root"], base)

    def test_required_live_inputs_are_the_exact_observation_closure(self) -> None:
        directories = (
            "reset-0064x0064",
            "reset-0064x0256",
            "reset-0512x0128",
            "reset-1024x1024",
            "repeat-0064x0064",
        )
        files = (
            "observation-evidence.json",
            "reset-manifest.json",
            "reset-projection.json",
            "observation-metadata.json",
            "observation-metadata.bin",
            "openttd-observation.log",
        )
        expected_paths = tuple(
            f"{directory}/{filename}"
            for directory in directories
            for filename in files
        )

        requirements = freeze_m15_observation_evidence.required_live_inputs(self.root)

        self.assertEqual(
            tuple(requirement.relative_path for requirement in requirements),
            expected_paths,
        )
        self.assertEqual(
            {requirement.logical_set for requirement in requirements},
            {"v2-m15-observation-evidence-c"},
        )
        self.assertEqual({requirement.kind for requirement in requirements}, {"file"})
        self.assertEqual(
            {requirement.consumer for requirement in requirements},
            {"m15-observation-evidence"},
        )
        by_path = {requirement.relative_path: requirement for requirement in requirements}
        self.assertEqual(
            by_path["reset-0064x0064/observation-metadata.bin"].expected_sha256,
            self.config["cases"][0]["binary_sha256"],
        )
        self.assertEqual(
            by_path["repeat-0064x0064/reset-manifest.json"].expected_sha256,
            self.config["determinism"]["manifest_sha256"],
        )

    def test_validation_only_cli_owns_offline_validation(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts/v2/validate_m15_observation_evidence.py"),
                "--root",
                str(self.root),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("V2_M15_OBSERVATION_EVIDENCE=PASS", completed.stdout)
        self.assertIn("live=false", completed.stdout)

    def test_creation_artifact_root_is_not_a_validation_base(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(self.root / "scripts/v2/freeze_m15_observation_evidence.py"),
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
                    str(self.root / "scripts/v2/freeze_m15_observation_evidence.py"),
                    "--root",
                    str(self.root),
                    "--artifact-root",
                    raw,
                    "--output",
                    str(pathlib.Path(raw) / "evidence.json"),
                    "--config",
                    str(self.root / freeze_m15_observation_evidence.CONFIG),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
