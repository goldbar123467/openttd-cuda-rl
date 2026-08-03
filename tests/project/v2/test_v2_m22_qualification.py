#!/usr/bin/env python3
"""Mutation tests for M22 selected-checkpoint qualification evidence."""

from __future__ import annotations

import copy
import pathlib
import unittest

import jsonschema

import run_m22_qualification as runner
import run_m22_recovery as recovery
import validate_m22_qualification_evidence as validator


class M22QualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.evidence_path = cls.root / "config/v2/m22-qualification-evidence.json"
        cls.report = recovery.load(cls.evidence_path) if cls.evidence_path.is_file() else None

    @staticmethod
    def rehash(value: dict[str, object]) -> None:
        value.pop("report_sha256", None)
        value["report_sha256"] = recovery.sha256_bytes(recovery.canonical_bytes(value))

    def mutation_fails(self, value: dict[str, object], pattern: str) -> None:
        self.rehash(value)
        with self.assertRaisesRegex(validator.M22QualificationValidationError, pattern):
            validator.validate_value(value, self.root)

    def test_schema_is_strict_and_freezes_the_selected_checkpoint(self) -> None:
        schema = recovery.load(self.root / runner.SCHEMA)
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["$defs"]["selection"]["properties"]["checkpoint_id"]["const"],
            "03894fd1238b69b6724d82eb441380312be4e8226efa602fa5e43972f7fa9f5f",
        )

    def test_qualification_source_and_sandbox_exclude_final_manifest(self) -> None:
        self.assertNotIn(runner.FINAL_MANIFEST.as_posix(), runner.SOURCE_PATHS)
        self.assertEqual(runner.ARTIFACT_NAMES, tuple(sorted(runner.ARTIFACT_NAMES)))

    def test_repository_qualification_evidence_passes(self) -> None:
        if self.report is None:
            self.skipTest("qualification evidence has not yet been generated from a clean source commit")
        validator.validate_value(self.report, self.root)

    def test_parity_tolerance_mutation_fails(self) -> None:
        if self.report is None:
            self.skipTest("qualification evidence has not yet been generated")
        value = copy.deepcopy(self.report)
        value["device_result"]["parity"][0]["forward_max_abs"] = 0.001
        self.mutation_fails(value, "parity tolerance")

    def test_benchmark_derivation_mutation_fails(self) -> None:
        if self.report is None:
            self.skipTest("qualification evidence has not yet been generated")
        value = copy.deepcopy(self.report)
        value["device_result"]["benchmarks"][0]["batches"][1]["speedup"] += 0.1
        self.mutation_fails(value, "speedup is not timing-derived")

    def test_native_source_mutation_fails(self) -> None:
        if self.report is None:
            self.skipTest("qualification evidence has not yet been generated")
        value = copy.deepcopy(self.report)
        value["native_retention"]["sources"][3]["sha256"] = "0" * 64
        self.mutation_fails(value, "native G15-G21 retention")

    def test_final_access_mutation_fails(self) -> None:
        if self.report is None:
            self.skipTest("qualification evidence has not yet been generated")
        value = copy.deepcopy(self.report)
        value["finalized_selection"]["final_manifest_accessed"] = True
        self.mutation_fails(value, "schema failed")


if __name__ == "__main__":
    unittest.main()
