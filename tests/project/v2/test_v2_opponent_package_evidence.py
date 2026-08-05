#!/usr/bin/env python3
"""Mutation tests for the M14 opponent acquisition evidence index."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from artifact_context import (
    ArtifactContext,
    LiveInputManifest,
    RoleRequirement,
    resolve_artifact_root,
)
import artifact_context
import validate_opponent_package_evidence


class OpponentPackageEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.evidence_path = cls.root / "config/v2/opponent-package-evidence.json"
        cls.schema_path = cls.root / "docs/project/schema/v2-opponent-package-evidence.schema.json"
        cls.evidence = validate_opponent_package_evidence.load_json(cls.evidence_path)

    @staticmethod
    def write_json(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "opponent-package-evidence.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def validate_mutation(self, directory: pathlib.Path, value: object) -> validate_opponent_package_evidence.OpponentEvidenceSummary:
        return validate_opponent_package_evidence.validate(
            self.root,
            self.write_json(directory, value),
            self.schema_path,
        )

    def test_repository_evidence_index_passes(self) -> None:
        summary = validate_opponent_package_evidence.validate(self.root)
        self.assertEqual(summary.opponents, 10)
        self.assertEqual(summary.locked, 8)
        self.assertEqual(summary.rejected, 2)
        self.assertEqual(summary.packages, 18)
        self.assertEqual(summary.archive_bytes, 4_341_760)
        self.assertEqual(summary.license_files, 18)

    def test_repository_evidence_passes_offline_without_retained_artifacts(self) -> None:
        with mock.patch.object(
            validate_opponent_package_evidence.acquire_ai_package,
            "validate_lock",
            side_effect=AssertionError("unexpected live read"),
        ), mock.patch.object(
            validate_opponent_package_evidence,
            "validate_rejection",
            side_effect=AssertionError("unexpected live read"),
        ):
            summary = validate_opponent_package_evidence.validate(
                self.root,
                artifact_context=ArtifactContext.offline(),
            )
        self.assertFalse(summary.live_artifacts)

    def test_required_live_inputs_are_the_exact_ten_package_sets(self) -> None:
        requirements = validate_opponent_package_evidence.required_live_inputs(self.root)
        self.assertEqual(len(requirements), 10)
        self.assertEqual(
            [
                (
                    requirement.logical_set,
                    requirement.relative_path,
                    requirement.expected_sha256,
                )
                for requirement in requirements
            ],
            [
                (
                    result["artifact_dir"],
                    result["evidence_file"],
                    result["evidence_sha256"],
                )
                for result in self.evidence["results"]
            ],
        )

    def test_required_live_role_is_the_frozen_m14_executable(self) -> None:
        self.assertEqual(
            validate_opponent_package_evidence.required_live_roles(self.root),
            (
                RoleRequirement(
                    "m14-openttd-executable",
                    ".",
                    "file",
                    "m14-opponent-package-evidence",
                    self.evidence["executable"]["sha256"],
                ),
            ),
        )

    def test_derived_artifacts_are_preflighted_before_helper_readers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            artifact_root = directory / "artifacts"
            artifact_root.mkdir()
            executable = artifact_root / "m14-openttd"
            with executable.open("wb") as stream:
                stream.truncate(self.evidence["executable"]["size"])

            evidence = copy.deepcopy(self.evidence)
            for result in evidence["results"]:
                artifact_set = artifact_root / result["artifact_dir"]
                artifact_set.mkdir()
                if result["outcome"] == "LOCKED":
                    retained = {
                        "packages": [{
                            "archive_path": "content_download/missing.tar",
                            "archive_sha256": "0" * 64,
                        }],
                    }
                else:
                    retained = {
                        "console_transcript": {
                            "path": "openttd-content-console.log",
                            "size": 1,
                            "sha256": "0" * 64,
                        },
                    }
                evidence_file = artifact_set / result["evidence_file"]
                evidence_file.write_text(
                    json.dumps(retained) + "\n",
                    encoding="utf-8",
                )
                result["evidence_sha256"] = hashlib.sha256(
                    evidence_file.read_bytes()
                ).hexdigest()
            evidence_path = self.write_json(directory, evidence)
            context = ArtifactContext.live(artifact_root)

            def fixture_digest(path: pathlib.Path) -> str:
                if path == executable:
                    return self.evidence["executable"]["sha256"]
                return hashlib.sha256(path.read_bytes()).hexdigest()

            with mock.patch.object(
                artifact_context,
                "_sha256_file",
                side_effect=fixture_digest,
            ):
                live_inputs = LiveInputManifest.bind(
                    context,
                    {"m14-openttd-executable": executable},
                )
                with mock.patch.object(
                    validate_opponent_package_evidence.acquire_ai_package,
                    "validate_lock",
                    side_effect=AssertionError("helper ran before derived preflight"),
                ) as lock_reader, mock.patch.object(
                    validate_opponent_package_evidence,
                    "validate_rejection",
                    side_effect=AssertionError("helper ran before derived preflight"),
                ) as rejection_reader:
                    with self.assertRaisesRegex(
                        validate_opponent_package_evidence.OpponentEvidenceError,
                        "content_download/missing.tar",
                    ):
                        validate_opponent_package_evidence.validate(
                            self.root,
                            evidence_path,
                            self.schema_path,
                            artifact_context=context,
                            live_inputs=live_inputs,
                        )
                lock_reader.assert_not_called()
                rejection_reader.assert_not_called()

    def test_live_input_manifest_must_share_the_exact_artifact_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            context_root = directory / "context"
            manifest_root = directory / "manifest"
            context_root.mkdir()
            manifest_root.mkdir()
            executable = manifest_root / "m14-openttd"
            executable.write_bytes(b"fixture")
            manifest_context = ArtifactContext.live(manifest_root)
            with mock.patch.object(
                artifact_context,
                "_sha256_file",
                return_value=self.evidence["executable"]["sha256"],
            ):
                live_inputs = LiveInputManifest.bind(
                    manifest_context,
                    {"m14-openttd-executable": executable},
                )
            with self.assertRaisesRegex(
                validate_opponent_package_evidence.OpponentEvidenceError,
                "share one exact artifact root",
            ):
                validate_opponent_package_evidence.validate(
                    self.root,
                    artifact_context=ArtifactContext.live(context_root),
                    live_inputs=live_inputs,
                )

    def test_schema_hash_drift_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_package_evidence.OpponentEvidenceError, "schema SHA-256"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_missing_opponent_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"].pop()
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(validate_opponent_package_evidence.OpponentEvidenceError):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_unsorted_results_fail(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"][0], evidence["results"][1] = evidence["results"][1], evidence["results"][0]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_package_evidence.OpponentEvidenceError, "not bytewise sorted"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_content_identity_drift_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"][0]["content_unique_id"] = "00000000"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_package_evidence.OpponentEvidenceError, "content ID drifted"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_version_drift_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"][0]["version"] += 1
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_package_evidence.OpponentEvidenceError, "version drifted"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_duplicate_artifact_directory_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"][1]["artifact_dir"] = evidence["results"][0]["artifact_dir"]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_package_evidence.OpponentEvidenceError, "duplicate artifact directories"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_live_validation_requires_evidence_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = ArtifactContext.live(pathlib.Path(raw))
            with self.assertRaisesRegex(
                validate_opponent_package_evidence.OpponentEvidenceError,
                "live-input manifest",
            ):
                validate_opponent_package_evidence.validate(
                    self.root,
                    artifact_context=context,
                    live_inputs=LiveInputManifest.offline(),
                )

    def test_retained_live_evidence_when_configured(self) -> None:
        configured = resolve_artifact_root(None)
        if not configured:
            self.skipTest("live artifact validation is outside offline mode")
        context = ArtifactContext.live(configured)
        summary = validate_opponent_package_evidence.validate(
            self.root,
            artifact_context=context,
            live_inputs=LiveInputManifest.load(configured),
        )
        self.assertTrue(summary.live_artifacts)


if __name__ == "__main__":
    unittest.main()
