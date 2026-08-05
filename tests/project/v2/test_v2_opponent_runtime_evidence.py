#!/usr/bin/env python3
"""Mutation tests for the M14 opponent runtime qualification matrix."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import shutil
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
import validate_opponent_runtime_evidence


class OpponentRuntimeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.evidence_path = cls.root / "config/v2/opponent-runtime-evidence.json"
        cls.schema_path = cls.root / "docs/project/schema/v2-opponent-runtime-evidence.schema.json"
        cls.evidence = validate_opponent_runtime_evidence.load_json(cls.evidence_path)

    @staticmethod
    def write_json(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "opponent-runtime-evidence.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def validate_mutation(self, directory: pathlib.Path, value: object) -> validate_opponent_runtime_evidence.RuntimeEvidenceSummary:
        return validate_opponent_runtime_evidence.validate(
            self.root,
            self.write_json(directory, value),
            self.schema_path,
        )

    @staticmethod
    def result(evidence: dict[str, object], name: str) -> dict[str, object]:
        return next(item for item in evidence["results"] if item["name"] == name)  # type: ignore[index]

    def test_repository_runtime_matrix_passes(self) -> None:
        summary = validate_opponent_runtime_evidence.validate(self.root)
        self.assertEqual(summary.opponents, 10)
        self.assertEqual(summary.package_rejected, 2)
        self.assertEqual(summary.runtime_rejected, 2)
        self.assertEqual(summary.tournament, 2)
        self.assertEqual(summary.control, 1)
        self.assertEqual(summary.scenario_required, 3)

    def test_repository_evidence_passes_offline_without_retained_artifacts(self) -> None:
        with mock.patch.object(
            validate_opponent_runtime_evidence.qualify_ai_runtime,
            "validate_manifest",
            side_effect=AssertionError("unexpected live read"),
        ), mock.patch.object(
            validate_opponent_runtime_evidence.validate_opponent_package_evidence,
            "validate",
            side_effect=AssertionError("unexpected live read"),
        ):
            summary = validate_opponent_runtime_evidence.validate(
                self.root,
                artifact_context=ArtifactContext.offline(),
            )
        self.assertFalse(summary.live_artifacts)

    def test_required_live_inputs_are_the_exact_package_and_runtime_sets(self) -> None:
        requirements = validate_opponent_runtime_evidence.required_live_inputs(self.root)
        package = validate_opponent_runtime_evidence.validate_opponent_package_evidence.load_json(
            self.root / "config/v2/opponent-package-evidence.json"
        )
        expected = [
            (
                result["artifact_dir"],
                result["evidence_file"],
                result["evidence_sha256"],
            )
            for result in package["results"]
        ] + [
            (
                result["artifact_dir"],
                result["evidence_file"],
                result["evidence_sha256"],
            )
            for result in self.evidence["results"]
            if result["phase"] != "PACKAGE"
        ]
        self.assertEqual(len(requirements), 18)
        self.assertEqual(
            [
                (
                    requirement.logical_set,
                    requirement.relative_path,
                    requirement.expected_sha256,
                )
                for requirement in requirements
            ],
            expected,
        )

    def test_required_live_role_is_the_frozen_m14_executable(self) -> None:
        self.assertEqual(
            validate_opponent_runtime_evidence.required_live_roles(self.root),
            (
                RoleRequirement(
                    "m14-openttd-executable",
                    ".",
                    "file",
                    "m14-opponent-runtime-evidence",
                    self.evidence["executable"]["sha256"],
                ),
            ),
        )

    def test_runtime_derived_inputs_preflight_before_nested_helper_readers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            project = directory / "project"
            artifact_root = directory / "artifacts"
            for relative in (
                "config/v1",
                "config/v2",
                "docs/project/schema",
            ):
                (project / relative).mkdir(parents=True, exist_ok=True)
            for relative in (
                "config/v1/openttd-source-profile.json",
                "config/v2/research-baseline.json",
                "docs/project/schema/v2-opponent-package-evidence.schema.json",
                "docs/project/schema/v2-opponent-runtime-evidence.schema.json",
            ):
                shutil.copyfile(self.root / relative, project / relative)
            artifact_root.mkdir()
            executable = artifact_root / "m14-openttd"
            with executable.open("wb") as stream:
                stream.truncate(self.evidence["executable"]["size"])

            package = validate_opponent_runtime_evidence.validate_opponent_package_evidence.load_json(
                self.root / "config/v2/opponent-package-evidence.json"
            )
            for result in package["results"]:
                artifact_set = artifact_root / result["artifact_dir"]
                artifact_set.mkdir(exist_ok=True)
                retained = (
                    {
                        "packages": [{
                            "archive_path": "package-helper-must-not-run.tar",
                            "archive_sha256": "0" * 64,
                        }],
                    }
                    if result["outcome"] == "LOCKED"
                    else {
                        "console_transcript": {
                            "path": "package-helper-must-not-run.log",
                            "size": 1,
                            "sha256": "0" * 64,
                        },
                    }
                )
                evidence_file = artifact_set / result["evidence_file"]
                evidence_file.write_text(json.dumps(retained) + "\n", encoding="utf-8")
                result["evidence_sha256"] = hashlib.sha256(
                    evidence_file.read_bytes()
                ).hexdigest()
            package_path = project / "config/v2/opponent-package-evidence.json"
            package_path.write_text(
                json.dumps(package, indent=2) + "\n",
                encoding="utf-8",
            )

            runtime = copy.deepcopy(self.evidence)
            runtime["package_evidence_sha256"] = hashlib.sha256(
                package_path.read_bytes()
            ).hexdigest()
            package_by_name = {item["name"]: item for item in package["results"]}
            for result in runtime["results"]:
                if result["phase"] == "PACKAGE":
                    result["evidence_sha256"] = package_by_name[result["name"]][
                        "evidence_sha256"
                    ]
                    continue
                artifact_set = artifact_root / result["artifact_dir"]
                artifact_set.mkdir()
                retained = {
                    "package_lock": {"sha256": "0" * 64},
                    "resources": {"console_transcript_sha256": "0" * 64},
                    "observations": {"save": None},
                }
                evidence_file = artifact_set / result["evidence_file"]
                evidence_file.write_text(json.dumps(retained) + "\n", encoding="utf-8")
                result["evidence_sha256"] = hashlib.sha256(
                    evidence_file.read_bytes()
                ).hexdigest()
            runtime_path = project / "config/v2/opponent-runtime-evidence.json"
            runtime_path.write_text(
                json.dumps(runtime, indent=2) + "\n",
                encoding="utf-8",
            )
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
                with self.assertRaisesRegex(
                    validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError,
                    "ai-package-lock.json",
                ):
                    validate_opponent_runtime_evidence.validate(
                        project,
                        runtime_path,
                        project / "docs/project/schema/v2-opponent-runtime-evidence.schema.json",
                        artifact_context=context,
                        live_inputs=live_inputs,
                    )

    def test_schema_hash_drift_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "schema SHA-256"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_package_index_digest_drift_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["package_evidence_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "runtime/package evidence"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_missing_opponent_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"].pop()
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_unsorted_results_fail(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"][0], evidence["results"][1] = evidence["results"][1], evidence["results"][0]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "not bytewise sorted"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_content_identity_drift_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"][0]["content_unique_id"] = "00000000"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "content ID drifted"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_active_admission_requires_vehicle_activity(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        self.result(evidence, "KrakenAI2")["vehicles"] = {"train": 0, "road": 0, "air": 0, "ship": 0}
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "lacks 30-day vehicle activity"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_inactive_ai_cannot_enter_tournament(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        self.result(evidence, "ShipAI")["admission"] = "TOURNAMENT"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "inactive admission policy"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_package_rejection_cannot_replace_locked_runtime(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        kraken = self.result(evidence, "KrakenAI2")
        kraken.clear()
        kraken.update(
            {
                "name": "KrakenAI2",
                "content_unique_id": "4b524132",
                "phase": "PACKAGE",
                "outcome": "PACKAGE_REJECTED",
                "admission": "EXCLUDED",
                "artifact_dir": "invented-package-rejection",
                "evidence_file": "ai-package-rejection.json",
                "evidence_sha256": "0" * 64,
                "reason_code": "catalog-listed-unselectable",
            }
        )
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "rejects a locked package"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_duplicate_artifact_directory_fails(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence["results"][1]["artifact_dir"] = evidence["results"][0]["artifact_dir"]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError, "duplicate artifact directories"):
                self.validate_mutation(pathlib.Path(raw), evidence)

    def test_live_validation_requires_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = ArtifactContext.live(pathlib.Path(raw))
            with self.assertRaisesRegex(
                validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError,
                "live-input manifest",
            ):
                validate_opponent_runtime_evidence.validate(
                    self.root,
                    artifact_context=context,
                    live_inputs=LiveInputManifest.offline(),
                )

    def test_retained_live_evidence_when_configured(self) -> None:
        configured = resolve_artifact_root(None)
        if not configured:
            self.skipTest("live artifact validation is outside offline mode")
        context = ArtifactContext.live(configured)
        summary = validate_opponent_runtime_evidence.validate(
            self.root,
            artifact_context=context,
            live_inputs=LiveInputManifest.load(configured),
        )
        self.assertTrue(summary.live_artifacts)


if __name__ == "__main__":
    unittest.main()
