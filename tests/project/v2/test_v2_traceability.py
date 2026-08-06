#!/usr/bin/env python3
"""Mutation tests for the V2 atomic requirements/test/defect registry."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_traceability


class V2TraceabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.requirements_path = cls.root / "docs/project/requirements-v2.json"
        cls.requirements_schema = cls.root / "docs/project/schema/requirements-v2.schema.json"
        cls.defects_path = cls.root / "docs/project/defects-v2.json"
        cls.defects_schema = cls.root / "docs/project/schema/defect-ledger-v2.schema.json"
        cls.registry = validate_traceability.load_json(cls.requirements_path)
        cls.defects = validate_traceability.load_json(cls.defects_path)

    @staticmethod
    def write_json(directory: pathlib.Path, name: str, value: object) -> pathlib.Path:
        path = directory / name
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def validate_mutation(
        self,
        directory: pathlib.Path,
        registry: object | None = None,
        defects: object | None = None,
    ) -> validate_traceability.V2TraceabilitySummary:
        return validate_traceability.validate(
            self.root,
            self.write_json(directory, "requirements-v2.json", registry or self.registry),
            self.requirements_schema,
            self.write_json(directory, "defects-v2.json", defects or self.defects),
            self.defects_schema,
        )

    @staticmethod
    def requirement(registry: dict[str, object], identifier: str) -> dict[str, object]:
        return next(item for item in registry["requirements"] if item["id"] == identifier)  # type: ignore[index]

    @staticmethod
    def lookup_test(registry: dict[str, object], identifier: str) -> dict[str, object]:
        return next(item for item in registry["tests"] if item["id"] == identifier)  # type: ignore[index]

    def test_requirements_schema_hash_drift_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_traceability.V2TraceabilityError, "requirements schema SHA-256"):
                self.validate_mutation(pathlib.Path(raw), registry)

    def test_duplicate_requirement_id_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["requirements"][1]["id"] = registry["requirements"][0]["id"]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_traceability.V2TraceabilityError, "duplicate V2 requirement ID"):
                self.validate_mutation(pathlib.Path(raw), registry)

    def test_milestone_gate_mismatch_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.requirement(registry, "V2-SCALE-001")["gate"] = "G16"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_traceability.V2TraceabilityError, "milestone/gate mismatch"):
                self.validate_mutation(pathlib.Path(raw), registry)

    def test_unknown_source_reference_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.requirement(registry, "V2-SCALE-001")["source_refs"] = ["invented-source"]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_traceability.V2TraceabilityError, "unknown sources"):
                self.validate_mutation(pathlib.Path(raw), registry)

    def test_forward_dependency_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.requirement(registry, "V2-AUTH-001")["depends_on"] = ["V2-AUTH-002"]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_traceability.V2TraceabilityError, "forward dependency"):
                self.validate_mutation(pathlib.Path(raw), registry)

    def test_pass_without_evidence_fails_schema(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.requirement(registry, "V2-AUTH-001")["evidence"] = []
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_traceability.V2TraceabilityError, "requirements schema failed"):
                self.validate_mutation(pathlib.Path(raw), registry)

    def test_missing_local_implementation_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.requirement(registry, "V2-AUTH-001")["implementation"] = ["missing/v2-file"]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_traceability.V2TraceabilityError, "missing local path"):
                self.validate_mutation(pathlib.Path(raw), registry)

    def test_unknown_test_reference_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.requirement(registry, "V2-SCALE-001")["test_ids"].append("V2-TEST-INVENTED")
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_traceability.V2TraceabilityError, "unknown tests"):
                self.validate_mutation(pathlib.Path(raw), registry)

    def test_nonbidirectional_test_link_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.requirement(registry, "V2-SCALE-001")["test_ids"] = ["V2-TEST-G16"]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_traceability.V2TraceabilityError, "not bidirectional"):
                self.validate_mutation(pathlib.Path(raw), registry)

    def test_passed_requirement_requires_passed_test(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.lookup_test(registry, "V2-TEST-M14-SOURCE")["status"] = "IMPLEMENTED"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_traceability.V2TraceabilityError, "has no passed test"):
                self.validate_mutation(pathlib.Path(raw), registry)

    def test_v1_regression_cannot_be_downgraded(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.lookup_test(registry, "V2-TEST-V1-REGRESSION")["status"] = "IMPLEMENTED"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(validate_traceability.V2TraceabilityError):
                self.validate_mutation(pathlib.Path(raw), registry)

    def test_defect_schema_hash_drift_fails(self) -> None:
        defects = copy.deepcopy(self.defects)
        defects["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_traceability.V2TraceabilityError, "defect schema SHA-256"):
                self.validate_mutation(pathlib.Path(raw), defects=defects)

    def test_defect_open_count_drift_fails(self) -> None:
        defects = copy.deepcopy(self.defects)
        defects["open_counts"]["total_nonclosed"] += 1
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_traceability.V2TraceabilityError, "defect open counts drifted"):
                self.validate_mutation(pathlib.Path(raw), defects=defects)


if __name__ == "__main__":
    unittest.main()
