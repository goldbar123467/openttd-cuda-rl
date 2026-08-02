#!/usr/bin/env python3
"""Mutation tests for the M14 opponent runtime qualification matrix."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

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
            with self.assertRaises(validate_opponent_runtime_evidence.OpponentRuntimeEvidenceError):
                validate_opponent_runtime_evidence.validate(self.root, artifact_base=pathlib.Path(raw))


if __name__ == "__main__":
    unittest.main()
