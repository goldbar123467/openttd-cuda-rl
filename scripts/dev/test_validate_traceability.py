#!/usr/bin/env python3
"""Negative semantic tests for the fail-closed traceability linter."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import jsonschema

import validate_traceability


class TraceabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[2]
        cls.registry_path = cls.root / "evidence/p0/P0_REQUIREMENTS_TRACEABILITY.json"
        cls.schema_path = cls.root / "oracle/manifests/schema/requirements-traceability.schema.json"
        cls.ledger_path = cls.root / "evidence/p0/P0_DEFECT_DIVERGENCE_LEDGER.json"
        cls.markdown_path = cls.root / "docs/testing/P0_REQUIREMENTS_TRACEABILITY.md"
        cls.registry = validate_traceability.load_json(cls.registry_path)

    def write_registry(self, directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "traceability.json"
        path.write_text(json.dumps(value, separators=(",", ":")) + "\n", encoding="utf-8")
        return path

    def validate_mutation(
        self,
        directory: pathlib.Path,
        registry: object,
        *,
        gate_result: pathlib.Path | None = None,
    ) -> tuple[int, int, int]:
        return validate_traceability.validate(
            self.root,
            self.write_registry(directory, registry),
            self.schema_path,
            self.ledger_path,
            self.markdown_path,
            gate_result,
        )

    def test_baseline_registry_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(self.validate_mutation(pathlib.Path(raw), self.registry), (56, 25, 0))

    def test_required_requirement_without_test_fails(self) -> None:
        value = copy.deepcopy(self.registry)
        value["requirements"][0]["test_ids"] = []
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(jsonschema.ValidationError):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_required_test_without_requirement_fails(self) -> None:
        value = copy.deepcopy(self.registry)
        value["tests"][0]["requirement_ids"] = []
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(jsonschema.ValidationError):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_passing_requirement_with_missing_artifact_fails(self) -> None:
        value = copy.deepcopy(self.registry)
        requirement = value["requirements"][0]
        requirement["status"] = "PASS"
        requirement["evidence"] = ["evidence/p0/does-not-exist.json"]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_traceability.TraceabilityError, "missing artifact"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_unowned_implementation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with mock.patch.object(
                validate_traceability,
                "tracked_implementation_paths",
                return_value=["intentionally-unowned.c"],
            ):
                with self.assertRaisesRegex(validate_traceability.TraceabilityError, "no owning requirement"):
                    self.validate_mutation(pathlib.Path(raw), self.registry)

    def test_open_defect_mapped_to_pass_fails(self) -> None:
        value = copy.deepcopy(self.registry)
        requirement = next(item for item in value["requirements"] if item["id"] == "TAPE-READER-001")
        requirement["status"] = "PASS"
        requirement["implementation"] = ["parity/src/tape_reader.c"]
        requirement["evidence"] = ["evidence/p0/P0_DEFECT_DIVERGENCE_LEDGER.json"]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_traceability.TraceabilityError, "open defect"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_mandatory_skip_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            gate = directory / "gate.json"
            gate.write_text('{"gates":[{"id":"PORT-003","status":"SKIP"}]}\n', encoding="utf-8")
            with self.assertRaisesRegex(validate_traceability.TraceabilityError, "mandatory gate uses SKIP"):
                self.validate_mutation(directory, self.registry, gate_result=gate)


if __name__ == "__main__":
    unittest.main()
