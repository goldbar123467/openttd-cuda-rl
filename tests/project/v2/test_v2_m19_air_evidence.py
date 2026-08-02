#!/usr/bin/env python3
"""Mutation tests for complete native M19 aircraft evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_m19_air_evidence as validator


class M19AirEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validator.load(cls.root / validator.CONFIG)
        cls.schema = cls.root / validator.SCHEMA
        cls.artifact = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m19-air-matrix-a")

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "evidence.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validator.M19EvidenceError, pattern) if pattern else self.assertRaises((validator.M19EvidenceError, ValueError))
            with context:
                validator.validate(self.root, self.write(pathlib.Path(raw), value), self.schema, artifact_root=self.artifact)

    def test_repository_evidence_passes(self) -> None:
        summary = validator.validate(self.root, artifact_root=self.artifact)
        self.assertEqual((summary["cases"], summary["runs"], summary["twin_exact"]), (20, 40, 20))

    def test_case_omission_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"].pop()
        self.mutation_fails(value)

    def test_case_seed_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][5]["seed"] ^= 1
        self.mutation_fails(value, "metadata")

    def test_vacuous_income_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config)
        target = next(item for item in value["cases"] if item["probe"] == "service")
        target["metrics"]["income"] = 0
        self.mutation_fails(value, "metrics")

    def test_report_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["twins"][0]["report_sha256"] = "0" * 64
        self.mutation_fails(value, "report SHA-256")

    def test_twin_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["twins"][1]["normalized_sha256"] = "0" * 64
        self.mutation_fails(value, "normalized report")

    def test_baseline_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["baselines"]["lufthansa"]["archive_sha256"] = "0" * 64
        self.mutation_fails(value, "baseline")

    def test_executable_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["executable_sha256"] = "0" * 64
        self.mutation_fails(value, "executable identity")


if __name__ == "__main__":
    unittest.main()
