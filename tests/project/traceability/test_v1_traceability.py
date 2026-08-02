#!/usr/bin/env python3
"""Negative semantic tests for the V1 project traceability contract."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import jsonschema

import validate_traceability


class V1TraceabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.registry_path = cls.root / "docs/project/requirements-v1.json"
        cls.requirement_schema_path = cls.root / "docs/project/schema/requirements-v1.schema.json"
        cls.ledger_path = cls.root / "docs/project/defects-v1.json"
        cls.defect_schema_path = cls.root / "docs/project/schema/defect-ledger-v1.schema.json"
        cls.markdown_path = cls.root / "docs/project/REQUIREMENTS.md"
        cls.registry = validate_traceability.load_json(cls.registry_path)
        cls.ledger = validate_traceability.load_json(cls.ledger_path)
        cls.markdown = cls.markdown_path.read_text(encoding="utf-8")

    @staticmethod
    def write_json(directory: pathlib.Path, name: str, value: object) -> pathlib.Path:
        path = directory / name
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def write_text(directory: pathlib.Path, name: str, value: str) -> pathlib.Path:
        path = directory / name
        path.write_text(value, encoding="utf-8")
        return path

    def validate_mutation(
        self,
        directory: pathlib.Path,
        *,
        registry: object | None = None,
        ledger: object | None = None,
        markdown: str | None = None,
    ) -> validate_traceability.ValidationSummary:
        return validate_traceability.validate(
            self.root,
            self.write_json(directory, "requirements.json", registry or self.registry),
            self.requirement_schema_path,
            self.write_json(directory, "defects.json", ledger or self.ledger),
            self.defect_schema_path,
            self.write_text(directory, "requirements.md", markdown or self.markdown),
        )

    @staticmethod
    def requirement(registry: dict[str, object], identifier: str) -> dict[str, object]:
        return next(
            item for item in registry["requirements"]  # type: ignore[index]
            if item["id"] == identifier
        )

    @staticmethod
    def find_test_entry(registry: dict[str, object], identifier: str) -> dict[str, object]:
        return next(
            item for item in registry["tests"]  # type: ignore[index]
            if item["id"] == identifier
        )

    def promote_requirement(
        self,
        registry: dict[str, object],
        identifier: str,
        *,
        evidence: str = "docs/project/REQUIREMENTS.md",
    ) -> None:
        requirement = self.requirement(registry, identifier)
        requirement["status"] = "PASS"
        requirement["implementation"] = ["GOAL.md"]
        requirement["evidence"] = [evidence]
        for test_id in requirement["test_ids"]:  # type: ignore[union-attr]
            test = self.find_test_entry(registry, test_id)
            test["status"] = "PASS"
            test["runner"] = "scripts/v1/traceability.sh"
            test["evidence"] = ["docs/project/REQUIREMENTS.md"]

    def test_baseline_registry_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            summary = self.validate_mutation(pathlib.Path(raw))
        self.assertEqual(summary.requirements, 227)
        self.assertEqual(summary.tests, 22)
        self.assertEqual(summary.requirements_passed, 95)
        self.assertEqual(summary.post_v1_deferred, 10)
        self.assertEqual(summary.nonclosed_defects, 0)

    def test_missing_machine_requirement_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["requirements"].pop()
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "requirement count mismatch",
            ):
                self.validate_mutation(pathlib.Path(raw), registry=registry)

    def test_duplicate_requirement_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["requirements"].append(copy.deepcopy(registry["requirements"][0]))
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "duplicate requirement ID",
            ):
                self.validate_mutation(pathlib.Path(raw), registry=registry)

    def test_human_requirement_omission_fails(self) -> None:
        line = next(line for line in self.markdown.splitlines() if line.startswith("| `SCOPE-001`"))
        markdown = self.markdown.replace(line + "\n", "", 1)
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "registry/Markdown requirement mismatch",
            ):
                self.validate_mutation(pathlib.Path(raw), markdown=markdown)

    def test_machine_human_statement_drift_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.requirement(registry, "SCOPE-001")["summary"] = "A narrower invented scope."
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "machine/human summary mismatch",
            ):
                self.validate_mutation(pathlib.Path(raw), registry=registry)

    def test_machine_human_status_drift_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.requirement(registry, "SCOPE-001")["status"] = "IN_PROGRESS"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "machine/human status mismatch",
            ):
                self.validate_mutation(pathlib.Path(raw), registry=registry)

    def test_requirement_without_test_fails_schema(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.requirement(registry, "SCOPE-001")["test_ids"] = []
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(jsonschema.ValidationError):
                self.validate_mutation(pathlib.Path(raw), registry=registry)

    def test_missing_reverse_test_mapping_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        test = self.find_test_entry(registry, "V1-TEST-M02-SCENARIO-RESET")
        test["requirement_ids"].remove("SCOPE-001")
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "lacks reverse mapping",
            ):
                self.validate_mutation(pathlib.Path(raw), registry=registry)

    def test_test_unknown_requirement_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.find_test_entry(registry, "V1-TEST-SCOPE")["requirement_ids"].append("SCOPE-999")
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "names unknown requirement SCOPE-999",
            ):
                self.validate_mutation(pathlib.Path(raw), registry=registry)

    def test_pass_without_implementation_or_evidence_fails_schema(self) -> None:
        registry = copy.deepcopy(self.registry)
        requirement = self.requirement(registry, "SCOPE-001")
        requirement["status"] = "PASS"
        requirement["implementation"] = []
        requirement["evidence"] = []
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(jsonschema.ValidationError):
                self.validate_mutation(pathlib.Path(raw), registry=registry)

    def test_legacy_evidence_cannot_be_laundered_as_fresh(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.promote_requirement(registry, "SCOPE-001", evidence="evidence/p0/README.md")
        markdown = self.markdown.replace(
            "| `SCOPE-001` | Every V1 scenario is exactly 32 by 32 tiles. | Scenario-schema test and reset-run manifest. | `NOT_STARTED` |",
            "| `SCOPE-001` | Every V1 scenario is exactly 32 by 32 tiles. | Scenario-schema test and reset-run manifest. | `PASS` |",
            1,
        )
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "places legacy artifact in fresh V1 evidence",
            ):
                self.validate_mutation(pathlib.Path(raw), registry=registry, markdown=markdown)

    def test_missing_pass_evidence_file_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.promote_requirement(registry, "SCOPE-001", evidence="evidence/v1/does-not-exist.json")
        markdown = self.markdown.replace(
            "| `SCOPE-001` | Every V1 scenario is exactly 32 by 32 tiles. | Scenario-schema test and reset-run manifest. | `NOT_STARTED` |",
            "| `SCOPE-001` | Every V1 scenario is exactly 32 by 32 tiles. | Scenario-schema test and reset-run manifest. | `PASS` |",
            1,
        )
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "points to missing file",
            ):
                self.validate_mutation(pathlib.Path(raw), registry=registry, markdown=markdown)

    def test_implemented_test_with_missing_runner_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        test = self.find_test_entry(registry, "V1-TEST-TRACEABILITY-CONTRACT")
        test["runner"] = "tests/project/traceability/does-not-exist.py"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "runner points to missing file",
            ):
                self.validate_mutation(pathlib.Path(raw), registry=registry)

    def test_nonclosed_defect_blocks_passing_requirement(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.promote_requirement(registry, "SCOPE-001")
        markdown = self.markdown.replace(
            "| `SCOPE-001` | Every V1 scenario is exactly 32 by 32 tiles. | Scenario-schema test and reset-run manifest. | `NOT_STARTED` |",
            "| `SCOPE-001` | Every V1 scenario is exactly 32 by 32 tiles. | Scenario-schema test and reset-run manifest. | `PASS` |",
            1,
        )
        ledger = copy.deepcopy(self.ledger)
        ledger["entries"] = [
            {
                "id": "V1-DEF-0001",
                "kind": "DEFECT",
                "title": "Injected traceability contradiction",
                "severity": "BLOCKER",
                "blocks_release": True,
                "status": "OPEN",
                "discovery_date": "2026-07-31",
                "discovered_by": "V1-TEST-TRACEABILITY-CONTRACT",
                "source_revision": "76574e7e65494b72ed3c07cbf973722865c3569f",
                "affected_requirement_ids": ["SCOPE-001"],
                "affected_gates": ["G02"],
                "first_observed": "Synthetic validator mutation.",
                "impact": "A passing scope requirement has an unresolved blocking defect.",
                "root_cause": None,
                "owner": "Traceability self-test",
                "reproducer": [],
                "evidence": [],
                "fix_revision": None,
                "regression_test": None,
                "closure_evidence": [],
            }
        ]
        ledger["open_counts"] = {
            "defects": 1,
            "divergences": 0,
            "release_blocking": 1,
            "total_nonclosed": 1,
        }
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "affects passing requirement SCOPE-001",
            ):
                self.validate_mutation(
                    pathlib.Path(raw), registry=registry, ledger=ledger, markdown=markdown
                )

    def test_defect_open_counts_are_recomputed(self) -> None:
        ledger = copy.deepcopy(self.ledger)
        ledger["open_counts"]["total_nonclosed"] = 1
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "defect open_counts mismatch",
            ):
                self.validate_mutation(pathlib.Path(raw), ledger=ledger)

    def test_passing_aggregate_with_nonpassing_dependencies_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.promote_requirement(registry, "DONE-003")
        markdown = self.markdown.replace(
            "| `DONE-003` | At least one policy passes both baseline superiority (`EVAL-012`) and reliable profitability (`EVAL-013`). | Final independent evaluation report. | `NOT_STARTED` |",
            "| `DONE-003` | At least one policy passes both baseline superiority (`EVAL-012`) and reliable profitability (`EVAL-013`). | Final independent evaluation report. | `PASS` |",
            1,
        )
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "has nonpassing dependencies",
            ):
                self.validate_mutation(pathlib.Path(raw), registry=registry, markdown=markdown)

    def test_done_001_cannot_omit_a_v1_requirement(self) -> None:
        registry = copy.deepcopy(self.registry)
        aggregate = next(
            item for item in registry["aggregate_dependencies"]
            if item["requirement_id"] == "DONE-001"
        )
        aggregate["dependency_ids"].remove("SCOPE-001")
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "DONE-001 does not depend on every",
            ):
                self.validate_mutation(pathlib.Path(raw), registry=registry)

    def test_post_v1_requirement_cannot_be_activated_early(self) -> None:
        registry = copy.deepcopy(self.registry)
        self.requirement(registry, "EXP-001")["status"] = "NOT_STARTED"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(jsonschema.ValidationError):
                self.validate_mutation(pathlib.Path(raw), registry=registry)

    def test_source_brief_digest_drift_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["source_briefs"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "source brief short sha256 mismatch",
            ):
                self.validate_mutation(pathlib.Path(raw), registry=registry)

    def test_schema_digest_drift_fails(self) -> None:
        registry = copy.deepcopy(self.registry)
        registry["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(
                validate_traceability.TraceabilityError,
                "requirement registry schema digest mismatch",
            ):
                self.validate_mutation(pathlib.Path(raw), registry=registry)


if __name__ == "__main__":
    unittest.main()
