#!/usr/bin/env python3
"""Mutation tests for complete retained M21 broad-feature evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_m21_broad_evidence as validator


class M21BroadEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validator.load(cls.root / validator.CONFIG)
        cls.artifact = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m21-broad-f")

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "evidence.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validator.M21EvidenceError, pattern) if pattern else self.assertRaises(validator.M21EvidenceError)
            with context:
                validator.validate(self.root, self.write(pathlib.Path(raw), value), artifact_root=self.artifact)

    def test_repository_evidence_passes(self) -> None:
        result = validator.validate(self.root, artifact_root=self.artifact)
        self.assertEqual((result["cases"], result["runs"], result["twins"], result["features"], result["commands"]),
                         (16, 32, 16, 18, 145))

    def test_case_omission_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"].pop()
        self.mutation_fails(value)

    def test_case_metadata_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["landscape"] = "toyland"
        self.mutation_fails(value, "metadata")

    def test_report_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["replicates"][0]["report_sha256"] = "0" * 64
        self.mutation_fails(value, "report hash")

    def test_normalized_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["replicates"][1]["normalized_sha256"] = "0" * 64
        self.mutation_fails(value, "normalized report")

    def test_save_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["replicates"][0]["save"]["sha256"] = "0" * 64
        self.mutation_fails(value, "save identity")

    def test_negative_diagnostic_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["negative_cases"][0]["diagnostic"] = "wrong diagnostic"
        self.mutation_fails(value, "negative rejection")

    def test_contract_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["contract_sha256"] = "0" * 64
        self.mutation_fails(value, "contract identity")

    def test_coverage_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["coverage_sha256"] = "0" * 64
        self.mutation_fails(value, "coverage identity")


if __name__ == "__main__":
    unittest.main()
