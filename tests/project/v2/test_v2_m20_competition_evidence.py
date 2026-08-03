#!/usr/bin/env python3
"""Mutation tests for complete native M20 competition evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_m20_competition_evidence as validator


class M20CompetitionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validator.load(cls.root / validator.CONFIG)
        cls.schema = cls.root / validator.SCHEMA
        cls.artifact = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m20-competition-matrix-f")

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "evidence.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validator.M20EvidenceError, pattern) if pattern else self.assertRaises((validator.M20EvidenceError, ValueError))
            with context:
                validator.validate(self.root, self.write(pathlib.Path(raw), value), self.schema, artifact_root=self.artifact)

    def test_repository_evidence_passes(self) -> None:
        summary = validator.validate(self.root, artifact_root=self.artifact)
        self.assertEqual((summary["cases"], summary["runs"], summary["replay_exact"]), (32, 64, 32))

    def test_case_omission_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"].pop()
        self.mutation_fails(value)

    def test_fairness_leg_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["leg"] = "D"
        self.mutation_fails(value, "metadata")

    def test_report_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["replicates"][0]["report_sha256"] = "0" * 64
        self.mutation_fails(value, "report SHA-256")

    def test_replay_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["replicates"][1]["normalized_sha256"] = "0" * 64
        self.mutation_fails(value, "normalized report")

    def test_metric_projection_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["replicate_metrics"][0]["rl"]["delivered_cargo_units"] = 0
        self.mutation_fails(value, "metric projection")

    def test_scoring_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["scoring"]["overall_mean_company_value_difference"] += 1
        self.mutation_fails(value, "scoring")

    def test_executable_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["executable_sha256"] = "0" * 64
        self.mutation_fails(value, "executable identity")


if __name__ == "__main__":
    unittest.main()
