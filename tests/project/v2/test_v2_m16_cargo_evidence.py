#!/usr/bin/env python3
"""Mutation and relocated-live tests for complete native M16 cargo evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import tempfile
import unittest
from typing import Any
from unittest import mock

from artifact_context import ArtifactContext, ArtifactContextError, resolve_artifact_root
import validate_m16_cargo_evidence as validator


def make_live_evidence_fixture(
    directory: pathlib.Path,
    evidence: dict[str, Any],
    *,
    logical_set: str,
    cargo_contract: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], pathlib.Path, pathlib.Path]:
    value = copy.deepcopy(evidence)
    artifact_set = directory / logical_set
    artifact_set.mkdir(parents=True)
    actual_classes = value["aggregate"].get("actual_cargo_classes", [])
    for record in value["cases"]:
        normalized = f"normalized:{record['case_id']}\n".encode("utf-8")
        normalized_sha = hashlib.sha256(normalized).hexdigest()
        for twin in record["twins"]:
            path = artifact_set / twin["report_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            report: dict[str, Any] = {
                "case_id": record["case_id"],
                "normalized_fixture": normalized.decode("utf-8"),
                "twin": twin["name"],
            }
            if cargo_contract is not None:
                report["cargo_catalog"] = [
                    {
                        "label": label,
                        "classes": actual_classes if index == 0 else [],
                    }
                    for index, label in enumerate(cargo_contract["climates"][record["climate"]])
                ]
                report["industry_graph"] = {
                    "production_transitions": [
                        {"industry_id": index, "accepted": f"A{index}", "produced": f"P{index}"}
                        for index in range(6)
                    ],
                }
            path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
            twin["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            twin["normalized_sha256"] = normalized_sha
    config_path = directory / "evidence.json"
    config_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return value, config_path, artifact_set


class M16CargoEvidenceTests(unittest.TestCase):
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
            raised = self.assertRaisesRegex(validator.M16EvidenceError, pattern) if pattern else self.assertRaises((validator.M16EvidenceError, ValueError))
            with raised:
                validator.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=ArtifactContext.offline(),
                )

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def test_repository_evidence_passes(self) -> None:
        summary = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertEqual((summary["cases"], summary["runs"], summary["edges"]), (102, 204, 24))

    def test_repository_evidence_passes_offline_without_retained_artifacts(self) -> None:
        with mock.patch.object(validator.matrix, "validate_common", side_effect=AssertionError("unexpected live read")):
            summary = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertFalse(summary["live"])

    def test_retained_live_evidence_passes(self) -> None:
        summary = validator.validate(
            self.root,
            artifact_context=ArtifactContext.live(self.live_base()),
        )
        self.assertTrue(summary["live"])

    def test_required_live_inputs_are_the_exact_report_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        expected = [
            (twin["report_path"], twin["report_sha256"])
            for record in self.config["cases"]
            for twin in record["twins"]
        ]
        self.assertEqual(len(requirements), 204)
        self.assertEqual(len(set(requirements)), 204)
        self.assertEqual(
            [(item.relative_path, item.expected_sha256) for item in requirements],
            expected,
        )
        self.assertEqual({item.logical_set for item in requirements}, {"v2-m16-cargo-matrix-a"})
        self.assertEqual({item.kind for item in requirements}, {"file"})
        self.assertEqual({item.consumer for item in requirements}, {"m16-cargo-evidence"})

    def test_relocated_live_reports_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _ = make_live_evidence_fixture(
                base,
                self.config,
                logical_set="v2-m16-cargo-matrix-a",
                cargo_contract=self.contract,
            )

            def validate_common(report: dict[str, Any], case: Any, *_args: Any) -> None:
                self.assertEqual(report["case_id"], case.case_id)

            metrics = {record["case_id"]: record["metrics"] for record in value["cases"]}
            with mock.patch.object(validator.matrix, "validate_common", side_effect=validate_common) as common, mock.patch.object(
                validator.matrix,
                "normalized",
                side_effect=lambda report: report["normalized_fixture"].encode("utf-8"),
            ), mock.patch.object(
                validator.matrix,
                "validate_probe",
                side_effect=lambda _report, case: metrics[case.case_id],
            ) as probe:
                summary = validator.validate(
                    self.root,
                    config_path,
                    self.schema,
                    artifact_context=ArtifactContext.live(base),
                )
        self.assertTrue(summary["live"])
        self.assertEqual(common.call_count, 204)
        self.assertEqual(probe.call_count, 102)

    def test_relocated_live_report_digest_mutation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, artifact_set = make_live_evidence_fixture(
                base,
                self.config,
                logical_set="v2-m16-cargo-matrix-a",
                cargo_contract=self.contract,
            )
            report = artifact_set / self.config["cases"][0]["twins"][0]["report_path"]
            report.write_bytes(report.read_bytes() + b"tamper\n")
            with mock.patch.object(
                validator.matrix,
                "validate_common",
                side_effect=AssertionError("preflight did not run first"),
            ) as common:
                with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                    validator.validate(
                        self.root,
                        config_path,
                        self.schema,
                        artifact_context=ArtifactContext.live(base),
                    )
            common.assert_not_called()

    def test_case_omission_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"].pop()
        self.mutation_fails(value)

    def test_occurrence_count_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["aggregate"]["climate_occurrences"] = 44
        self.mutation_fails(value)

    def test_case_seed_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][10]["seed"] ^= 1
        self.mutation_fails(value, "metadata")

    def test_vacuous_income_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config)
        target = next(item for item in value["cases"] if item["probe"] == "single-leg")
        target["metrics"]["income"] = 0
        self.mutation_fails(value, "metrics")

    def test_twin_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["twins"][1]["normalized_sha256"] = "0" * 64
        self.mutation_fails(value, "twin reports differ")

    def test_executable_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["executable_sha256"] = "0" * 64
        self.mutation_fails(value, "executable identity")


if __name__ == "__main__":
    unittest.main()
