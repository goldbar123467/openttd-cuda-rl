#!/usr/bin/env python3
"""Mutation tests for the corrected retained M22 follow-up runtime source."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import jsonschema

import prepare_m22_followup_runtime as preparation
import validate_m22_followup_runtime_source as validator


class M22FollowupRuntimeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.source = validator.load(cls.root / validator.CONFIG)
        cls.artifact = pathlib.Path(cls.source["retained_artifact"])
        m21 = validator.load(cls.root / preparation.foundation.M21_SOURCE)
        cls.base = pathlib.Path(m21["source"]["path"])

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "runtime-source.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def smoke(value: dict[str, object], case_id: str) -> dict[str, object]:
        return next(item for item in value["smokes"] if item["case"]["case_id"] == case_id)

    def mutation_fails(self, value: object, pattern: str | None = None, *, live: bool = False) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(
                validator.M22FollowupRuntimeSourceError, pattern
            ) if pattern else self.assertRaises(validator.M22FollowupRuntimeSourceError)
            with context:
                validator.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    artifact_root=self.artifact if live else None,
                )

    def test_repository_runtime_source_passes(self) -> None:
        result = validator.validate(self.root)
        self.assertEqual((result["files"], result["smokes"], result["live"]), (9, 14, False))

    def test_live_runtime_source_and_all_artifacts_pass(self) -> None:
        if not self.artifact.is_dir() or not self.base.is_dir():
            self.skipTest("retained corrected M22 runtime or accepted M21 source is unavailable")
        result = validator.validate(self.root, artifact_root=self.artifact, base_source=self.base)
        self.assertTrue(result["live"])

    def test_patch_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["patches"][1]["sha256"] = "0" * 64
        self.mutation_fails(value, "patch record drifted")

    def test_patch_order_mutation_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["patches"].reverse()
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)

    def test_immutable_final_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["boundaries"]["immutable_final_v1"]["evidence_sha256"] = "0" * 64
        self.mutation_fails(value, "immutable final/follow-up boundary")

    def test_followup_manifest_open_claim_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["boundaries"]["followup"]["manifest_opened"] = True
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)

    def test_smoke_order_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["smokes"][0], value["smokes"][1] = value["smokes"][1], value["smokes"][0]
        self.mutation_fails(value, "inventory/order")

    def test_vacuous_corrected_passenger_metric_fails(self) -> None:
        value = copy.deepcopy(self.source)
        smoke = self.smoke(value, "followup-source-g19-passenger-multimodal")
        smoke["metrics"]["delivered"] = 0
        self.mutation_fails(value, "useful-service smoke is vacuous")

    def test_competition_size_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        smoke = self.smoke(value, "followup-source-g20-krakenai2-128")
        smoke["case"]["map_width"] = 64
        self.mutation_fails(value, "public/private projection drifted")

    def test_competition_metric_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        smoke = self.smoke(value, "followup-source-g20-noopai-128")
        smoke["metrics"]["delivered"] = 24
        self.mutation_fails(value, "competition smoke is vacuous")

    def test_authority_save_exact_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        smoke = self.smoke(value, "followup-source-g21-authority-economy")
        smoke["metrics"]["save_load_exact"] = False
        self.mutation_fails(value, "authority smoke drifted")

    def test_executable_identity_mutation_fails_live(self) -> None:
        value = copy.deepcopy(self.source)
        value["executable"]["sha256"] = "0" * 64
        for smoke in value["smokes"]:
            smoke["executable_sha256"] = "0" * 64
        self.mutation_fails(value, "executable identity drifted", live=True)

    def test_smoke_report_digest_mutation_fails_live(self) -> None:
        value = copy.deepcopy(self.source)
        value["smokes"][0]["report_sha256"] = "0" * 64
        self.mutation_fails(value, "smoke artifact identity drifted", live=True)

    def test_ctest_claim_mutation_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["build"]["upstream_ctest"]["passed"] = 97
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)


if __name__ == "__main__":
    unittest.main()
