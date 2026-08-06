#!/usr/bin/env python3
"""Mutation and relocated-live tests for complete native M17 rail evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from artifact_context import ArtifactContext, ArtifactContextError, resolve_artifact_root
from tests.project.v2.test_v2_m16_cargo_evidence import make_live_evidence_fixture
import validate_m17_rail_evidence as validator


class M17RailEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validator.load(cls.root / validator.CONFIG)
        cls.contract = validator.load(cls.root / validator.matrix.CONTRACT)
        cls.schema = cls.root / validator.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "evidence.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raised = self.assertRaisesRegex(validator.M17EvidenceError, pattern) if pattern else self.assertRaises((validator.M17EvidenceError, ValueError))
            with raised:
                validator.validate(self.root, self.write(pathlib.Path(raw), value), self.schema, artifact_context=ArtifactContext.offline())

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def test_repository_evidence_passes_offline_without_retained_artifacts(self) -> None:
        with mock.patch.object(validator.matrix, "validate_common", side_effect=AssertionError("unexpected live read")):
            summary = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertFalse(summary["live"])

    def test_retained_live_evidence_passes(self) -> None:
        self.assertTrue(validator.validate(self.root, artifact_context=ArtifactContext.live(self.live_base()))["live"])

    def test_required_live_inputs_are_the_exact_report_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        self.assertEqual(len(requirements), 28)
        self.assertEqual(len(set(requirements)), 28)
        self.assertEqual(
            [(item.relative_path, item.expected_sha256) for item in requirements],
            [(twin["report_path"], twin["report_sha256"]) for record in self.config["cases"] for twin in record["twins"]],
        )
        self.assertEqual({item.logical_set for item in requirements}, {"v2-m17-rail-matrix-a"})
        self.assertEqual({item.consumer for item in requirements}, {"m17-rail-evidence"})

    def test_relocated_live_reports_pass(self) -> None:
        retained = copy.deepcopy(self.config)
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _ = make_live_evidence_fixture(
                base,
                self.config,
                logical_set="v2-m17-rail-matrix-a",
                matrix=validator.matrix,
                contract=self.contract,
            )
            summary = validator.validate(self.root, config_path, self.schema, artifact_context=ArtifactContext.live(base))
        self.assertTrue(summary["live"])
        self.assertEqual(self.config, retained)

    def test_relocated_live_report_tamper_fails_before_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, artifact_set = make_live_evidence_fixture(
                base,
                self.config,
                logical_set="v2-m17-rail-matrix-a",
                matrix=validator.matrix,
                contract=self.contract,
            )
            report = artifact_set / self.config["cases"][0]["twins"][0]["report_path"]
            report.write_bytes(report.read_bytes() + b"tamper\n")
            with mock.patch.object(validator.matrix, "validate_common", side_effect=AssertionError("preflight did not run first")) as common:
                with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                    validator.validate(self.root, config_path, self.schema, artifact_context=ArtifactContext.live(base))
            common.assert_not_called()

    def test_case_omission_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"].pop()
        self.mutation_fails(value)

    def test_case_seed_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][5]["seed"] ^= 1
        self.mutation_fails(value, "metadata")

    def test_vacuous_income_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); next(item for item in value["cases"] if item["probe"] == "passenger")["metrics"]["income"] = 0
        self.mutation_fails(value, "metrics")

    def test_twin_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["twins"][1]["normalized_sha256"] = "0" * 64
        self.mutation_fails(value, "twin reports differ")

    def test_baseline_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["baselines"]["specialist_runtime_evidence_sha256"] = "0" * 64
        self.mutation_fails(value, "baseline")

    def test_executable_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["executable_sha256"] = "0" * 64
        self.mutation_fails(value, "executable identity")


if __name__ == "__main__":
    unittest.main()
