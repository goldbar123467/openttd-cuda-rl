#!/usr/bin/env python3
"""Mutation tests for frozen M15 hierarchical-action evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from artifact_context import ArtifactContext, resolve_artifact_root
import freeze_m15_action_evidence
import qualify_m15_action


class M15ActionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = freeze_m15_action_evidence.load_json(cls.root / freeze_m15_action_evidence.CONFIG)
        cls.schema = cls.root / freeze_m15_action_evidence.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "action-evidence.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def test_repository_evidence_passes(self) -> None:
        summary = freeze_m15_action_evidence.validate(
            self.root,
            artifact_context=ArtifactContext.offline(),
        )
        self.assertEqual((summary.map_cases, summary.action_cases, summary.passed), (4, 10, 14))
        self.assertGreaterEqual(summary.maximum_rss_kib, 1)

    def test_live_artifacts_pass(self) -> None:
        artifact_base = resolve_artifact_root(None)
        if artifact_base is None:
            self.skipTest("live artifact validation is outside offline mode")
        self.assertTrue(freeze_m15_action_evidence.validate(
            self.root,
            artifact_context=ArtifactContext.live(artifact_base),
        ).live)

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_action_evidence.M15ActionEvidenceError, "schema SHA-256"):
                freeze_m15_action_evidence.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=ArtifactContext.offline(),
                )

    def test_deterministic_binary_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["map_cases"][0]["candidate_binary_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_action_evidence.M15ActionEvidenceError, "deterministic lock"):
                freeze_m15_action_evidence.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=ArtifactContext.offline(),
                )

    def test_negative_mutation_claim_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["action_cases"][-1]["mutated"] = True
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_action_evidence.M15ActionEvidenceError, "negative action invariant"):
                freeze_m15_action_evidence.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=ArtifactContext.offline(),
                )

    def test_live_candidate_binary_corruption_fails(self) -> None:
        artifact_base = resolve_artifact_root(None)
        if artifact_base is None:
            self.skipTest("live artifact validation is outside offline mode")
        source_root = artifact_base / self.config["artifact_root"]
        with tempfile.TemporaryDirectory() as raw:
            target_root = pathlib.Path(raw) / self.config["artifact_root"]
            source_case = source_root / "reset-0064x0064"
            target_case = target_root / "reset-0064x0064"
            shutil.copytree(source_case, target_case)
            binary = target_case / qualify_m15_action.CANDIDATE_BINARY_NAME
            data = bytearray(binary.read_bytes())
            data[0] ^= 1
            binary.write_bytes(data)
            with self.assertRaisesRegex(qualify_m15_action.M15ActionError, "SHA-256"):
                freeze_m15_action_evidence.map_case_from_artifact(self.root, target_root, "reset-0064x0064")

    def test_relocated_live_artifacts_do_not_rewrite_recorded_base(self) -> None:
        recorded_base = self.config["artifact_base_hint"]
        map_cases = {
            item["artifact_dir"]: item for item in self.config["map_cases"]
        }
        action_cases = {
            item["artifact_dir"]: item for item in self.config["action_cases"]
        }

        def map_projection(
            root: pathlib.Path,
            artifact_root: pathlib.Path,
            directory: str,
        ) -> dict[str, object]:
            self.assertEqual(root, self.root)
            self.assertEqual(artifact_root, relocated_set)
            return copy.deepcopy(map_cases.get(directory, self.config["map_cases"][0]))

        def action_projection(
            root: pathlib.Path,
            artifact_root: pathlib.Path,
            directory: str,
        ) -> dict[str, object]:
            self.assertEqual(root, self.root)
            self.assertEqual(artifact_root, relocated_set)
            return copy.deepcopy(action_cases[directory])

        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            relocated_set = base / self.config["artifact_root"]
            relocated_set.mkdir()
            with (
                mock.patch.object(
                    freeze_m15_action_evidence,
                    "map_case_from_artifact",
                    side_effect=map_projection,
                ),
                mock.patch.object(
                    freeze_m15_action_evidence,
                    "action_case_from_artifact",
                    side_effect=action_projection,
                ),
            ):
                summary = freeze_m15_action_evidence.validate(
                    self.root,
                    artifact_context=ArtifactContext.live(base),
                )

        self.assertTrue(summary.live)
        self.assertEqual(self.config["artifact_base_hint"], recorded_base)
        reloaded = freeze_m15_action_evidence.load_json(
            self.root / freeze_m15_action_evidence.CONFIG
        )
        self.assertEqual(reloaded["artifact_base_hint"], recorded_base)

    def test_newly_frozen_evidence_validates_from_generated_set_parent(self) -> None:
        map_cases = {
            item["artifact_dir"]: item for item in self.config["map_cases"]
        }
        action_cases = {
            item["artifact_dir"]: item for item in self.config["action_cases"]
        }
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
            artifact_root = base / freeze_m15_action_evidence.LOGICAL_ARTIFACT_SET
            artifact_root.mkdir()
            output = base / "action-evidence.json"
            with (
                mock.patch.object(
                    freeze_m15_action_evidence,
                    "map_case_from_artifact",
                    side_effect=lambda root, artifact, directory: copy.deepcopy(
                        map_cases.get(directory, self.config["map_cases"][0])
                    ),
                ),
                mock.patch.object(
                    freeze_m15_action_evidence,
                    "action_case_from_artifact",
                    side_effect=lambda root, artifact, directory: copy.deepcopy(
                        action_cases[directory]
                    ),
                ),
                mock.patch.object(
                    freeze_m15_action_evidence,
                    "validate",
                    side_effect=validate_generated,
                ),
            ):
                frozen = freeze_m15_action_evidence.freeze(
                    self.root,
                    artifact_root,
                    output,
                )
            self.assertEqual(frozen.read_bytes(), observed["bytes"])
            self.assertEqual(observed["artifact_root"], base)

    def test_required_live_inputs_are_the_exact_action_closure(self) -> None:
        map_directories = (
            "reset-0064x0064",
            "reset-0064x0256",
            "reset-0512x0128",
            "reset-1024x1024",
            "repeat-0064x0064",
        )
        map_files = (
            "action-evidence.json",
            "reset-manifest.json",
            "reset-projection.json",
            "observation-metadata.json",
            "observation-metadata.bin",
            "candidate-metadata.json",
            "candidate-metadata.bin",
            "openttd-action.log",
        )
        action_directories = (
            "positive-wait",
            "positive-select-town-pair",
            "positive-build-road",
            "positive-build-bus-stop",
            "positive-build-road-depot",
            "positive-manage-loan",
            "negative-stale-token",
            "negative-out-of-range",
            "negative-illegal-candidate",
            "negative-family-mismatch",
        )
        action_files = (
            "action-request.json",
            "action-result.json",
            "action-evidence.json",
        )
        expected_paths = tuple(
            f"{directory}/{filename}"
            for directory in map_directories
            for filename in map_files
        ) + tuple(
            f"{directory}/{filename}"
            for directory in action_directories
            for filename in action_files
        )

        requirements = freeze_m15_action_evidence.required_live_inputs(self.root)

        self.assertEqual(
            tuple(requirement.relative_path for requirement in requirements),
            expected_paths,
        )
        self.assertEqual(
            {requirement.logical_set for requirement in requirements},
            {"v2-m15-action-evidence-a"},
        )
        self.assertEqual({requirement.kind for requirement in requirements}, {"file"})
        self.assertEqual(
            {requirement.consumer for requirement in requirements},
            {"m15-action-evidence"},
        )
        by_path = {requirement.relative_path: requirement for requirement in requirements}
        self.assertEqual(
            by_path["reset-0064x0064/candidate-metadata.bin"].expected_sha256,
            self.config["map_cases"][0]["candidate_binary_sha256"],
        )
        self.assertEqual(
            by_path["positive-wait/action-request.json"].expected_sha256,
            self.config["action_cases"][0]["request_sha256"],
        )

    def test_validation_only_cli_owns_offline_validation(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts/v2/validate_m15_action_evidence.py"),
                "--root",
                str(self.root),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("V2_M15_ACTION_EVIDENCE=PASS", completed.stdout)
        self.assertIn("live=false", completed.stdout)

    def test_creation_artifact_root_is_not_a_validation_base(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(self.root / "scripts/v2/freeze_m15_action_evidence.py"),
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
                    str(self.root / "scripts/v2/freeze_m15_action_evidence.py"),
                    "--root",
                    str(self.root),
                    "--artifact-root",
                    raw,
                    "--output",
                    str(pathlib.Path(raw) / "evidence.json"),
                    "--config",
                    str(self.root / freeze_m15_action_evidence.CONFIG),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
