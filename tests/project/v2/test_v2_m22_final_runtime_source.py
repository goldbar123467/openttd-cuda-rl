#!/usr/bin/env python3
"""Mutation tests for the retained M22 final native runtime source."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import jsonschema

import prepare_m22_final_runtime as preparation
import validate_m22_final_runtime_source as validator


class M22FinalRuntimeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.source = validator.load(cls.root / validator.CONFIG)
        cls.artifact = pathlib.Path(cls.source["retained_artifact"])
        cls.base = pathlib.Path(validator.load(cls.root / preparation.M21_SOURCE)["source"]["path"])

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "runtime-source.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None, *, live: bool = False) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validator.M22RuntimeSourceError, pattern) if pattern else self.assertRaises(
                validator.M22RuntimeSourceError)
            with context:
                validator.validate(self.root, self.write(pathlib.Path(raw), value),
                                   artifact_root=self.artifact if live else None)

    def test_repository_runtime_source_passes(self) -> None:
        result = validator.validate(self.root)
        self.assertEqual((result["files"], result["smokes"], result["live"]), (9, 8, False))

    def test_live_runtime_source_and_all_artifacts_pass(self) -> None:
        if not self.artifact.is_dir():
            self.skipTest("retained M22 final runtime is unavailable")
        result = validator.validate(self.root, artifact_root=self.artifact, base_source=self.base)
        self.assertTrue(result["live"])

    def test_patch_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["patch"]["sha256"] = "0" * 64
        self.mutation_fails(value, "patch identity")

    def test_prerequisite_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["prerequisites"]["m20_source_record_sha256"] = "0" * 64
        self.mutation_fails(value, "prerequisite identity")

    def test_final_manifest_open_claim_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["final_boundary"]["manifest_opened"] = True
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)

    def test_public_smoke_seed_leak_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["smokes"][0]["case"]["seed"] = 1
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)

    def test_smoke_order_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["smokes"][0], value["smokes"][1] = value["smokes"][1], value["smokes"][0]
        self.mutation_fails(value, "inventory/order")

    def test_vacuous_service_metric_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["smokes"][0]["metrics"]["delivered"] = 0
        self.mutation_fails(value, "useful-service smoke is vacuous")

    def test_executable_identity_mutation_fails_live(self) -> None:
        value = copy.deepcopy(self.source)
        value["executable"]["sha256"] = "0" * 64
        for smoke in value["smokes"]:
            smoke["executable_sha256"] = "0" * 64
        self.mutation_fails(value, "executable identity", live=True)

    def test_smoke_report_digest_mutation_fails_live(self) -> None:
        value = copy.deepcopy(self.source)
        value["smokes"][0]["report_sha256"] = "0" * 64
        self.mutation_fails(value, "smoke artifact identity", live=True)

    def test_ctest_claim_mutation_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["build"]["upstream_ctest"]["passed"] = 97
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)


if __name__ == "__main__":
    unittest.main()
