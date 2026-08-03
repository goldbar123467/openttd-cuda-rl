#!/usr/bin/env python3
"""Mutation tests for the M21 contract, coverage, content lock, and native source."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import jsonschema

import run_m21_broad_matrix as matrix
import validate_m21_broad_source as validator


class M21BroadSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.source = validator.load(cls.root / validator.CONFIG)
        cls.contract = validator.load(cls.root / matrix.CONTRACT)
        cls.coverage = validator.load(cls.root / matrix.COVERAGE)
        cls.artifact = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m21-broad-a")

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "source.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None, *, live: bool = False) -> None:
        with tempfile.TemporaryDirectory() as raw:
            errors = (validator.M21SourceError, matrix.M21MatrixError)
            context = self.assertRaisesRegex(errors, pattern) if pattern else self.assertRaises(errors)
            with context:
                validator.validate(self.root, self.write(pathlib.Path(raw), value), artifact_root=self.artifact if live else None)

    def test_repository_contract_coverage_content_and_source_pass(self) -> None:
        result = validator.validate(self.root)
        self.assertEqual((result["files"], result["features"], result["commands"]), (4, 18, 145))

    def test_live_source_and_runtime_pass(self) -> None:
        if not self.artifact.is_dir():
            self.skipTest("retained M21 source is unavailable")
        self.assertTrue(validator.validate(self.root, artifact_root=self.artifact)["live"])

    def test_patch_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source); value["patch"]["sha256"] = "0" * 64
        self.mutation_fails(value, "patch identity")

    def test_source_tree_mutation_fails_live(self) -> None:
        value = copy.deepcopy(self.source); value["source"]["tree"] = "0" * 40
        self.mutation_fails(value, "source identity", live=True)

    def test_executable_digest_mutation_fails_live(self) -> None:
        value = copy.deepcopy(self.source); value["executable"]["sha256"] = "0" * 64
        self.mutation_fails(value, "executable identity", live=True)

    def test_contract_case_omission_fails_schema(self) -> None:
        value = copy.deepcopy(self.contract); value["cases"].pop()
        schema = validator.load(self.root / validator.CONTRACT_SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)

    def test_feature_coverage_omission_fails(self) -> None:
        value = copy.deepcopy(self.coverage); value["feature_domains"].pop()
        with self.assertRaises(matrix.M21MatrixError):
            matrix.validate_coverage(self.root, self.contract, value)

    def test_command_disposition_mutation_fails(self) -> None:
        value = copy.deepcopy(self.coverage); value["command_dispositions"][0]["disposition"] = "benchmark-admin"
        with self.assertRaisesRegex(matrix.M21MatrixError, "command coverage"):
            matrix.validate_coverage(self.root, self.contract, value)

    def test_presentation_proof_cannot_escape_optional_disposition(self) -> None:
        value = copy.deepcopy(self.coverage)
        row = next(item for item in value["command_dispositions"] if item["disposition"] == "policy-required")
        row["proof_kind"] = "deliberate-presentation-only-proof"
        with self.assertRaisesRegex(matrix.M21MatrixError, "presentation-only"):
            matrix.validate_coverage(self.root, self.contract, value)


if __name__ == "__main__":
    unittest.main()
