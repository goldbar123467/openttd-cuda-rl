#!/usr/bin/env python3
"""Reproduction and mutation tests for the frozen M22 follow-up manifest."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import jsonschema

import build_m22_followup_manifest as builder
import validate_m22_followup_manifest as validator


class M22FollowupManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.manifest = validator.load(cls.root / builder.MANIFEST)
        cls.schema = validator.load(cls.root / builder.SCHEMA)

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "followup-manifest.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str = "canonical deterministic build") -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validator.M22FollowupManifestError, pattern):
                validator.validate(self.root, self.write(pathlib.Path(raw), value))

    def test_schema_is_closed_and_canonical(self) -> None:
        jsonschema.Draft202012Validator.check_schema(self.schema)
        self.assertFalse(self.schema["additionalProperties"])
        jsonschema.Draft202012Validator(self.schema).validate(self.manifest)
        value = copy.deepcopy(self.manifest)
        value["post_selected"] = False
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(value)

    def test_all_seeds_are_derived_unique_and_previously_unseen(self) -> None:
        _, excluded = builder.seed_source_records(self.root)
        seeds = [case["seed"] for case in self.manifest["cases"]]
        self.assertEqual(len(seeds), len(set(seeds)))
        self.assertTrue(set(seeds).isdisjoint(excluded))
        self.assertTrue(set(seeds).isdisjoint(builder.EXTERNAL_DIAGNOSTIC_SEEDS))

    def test_seed_mutation_fails(self) -> None:
        value = copy.deepcopy(self.manifest)
        value["cases"][0]["seed"] += 1
        self.mutation_fails(value)

    def test_case_order_mutation_fails(self) -> None:
        value = copy.deepcopy(self.manifest)
        value["cases"][0], value["cases"][1] = value["cases"][1], value["cases"][0]
        self.mutation_fails(value)

    def test_competition_size_mutation_fails(self) -> None:
        value = copy.deepcopy(self.manifest)
        case = next(case for case in value["cases"] if case["source_gate"] == "G20")
        case["map_width"] = case["map_height"] = 64
        self.mutation_fails(value)

    def test_final_v1_retry_claim_fails_schema(self) -> None:
        value = copy.deepcopy(self.manifest)
        value["access_policy"]["final_v1_cases"] = "retry-failures"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(value)

    def test_external_diagnostic_seed_mutation_fails_schema(self) -> None:
        value = copy.deepcopy(self.manifest)
        value["seed_exclusions"]["external_diagnostic_seeds"][0] += 1
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(value)

    def test_runtime_prerequisite_mutation_fails(self) -> None:
        value = copy.deepcopy(self.manifest)
        value["prerequisites"]["corrected_runtime_source_sha256"] = "0" * 64
        self.mutation_fails(value)

    def test_seed_source_inventory_is_exact_and_content_addressed(self) -> None:
        records, _ = builder.seed_source_records(self.root)
        self.assertEqual(records, self.manifest["seed_exclusions"]["repository_sources"])
        self.assertEqual([record["path"] for record in records], [path.as_posix() for path in builder.SEED_SOURCES])

    def test_immutable_final_and_corrected_runtime_boundaries_remain_separate(self) -> None:
        immutable = validator.load(self.root / builder.IMMUTABLE_FINAL)
        runtime = validator.load(self.root / builder.CORRECTED_RUNTIME)
        self.assertEqual(immutable["status"], "FAIL")
        self.assertEqual(runtime["status"], "PASS")
        self.assertFalse(runtime["boundaries"]["followup"]["manifest_opened"])


if __name__ == "__main__":
    unittest.main()
