#!/usr/bin/env python3
"""Mutation tests for the M14 opponent acquisition evidence index."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

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
            with self.assertRaisesRegex(validate_opponent_package_evidence.OpponentEvidenceError, "artifact directory is missing"):
                validate_opponent_package_evidence.validate(
                    self.root,
                    artifact_base=pathlib.Path(raw),
                )


if __name__ == "__main__":
    unittest.main()
