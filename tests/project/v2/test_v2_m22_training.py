#!/usr/bin/env python3
"""Foundation tests for the complete M22 training campaign tooling."""

from __future__ import annotations

import copy
import hashlib
import pathlib
import unittest

import jsonschema

import run_m22_training as runner
import run_m22_recovery as recovery
import validate_m22_training_evidence as validator


class M22TrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.report = recovery.load(cls.root / "config/v2/m22-training-evidence.json")

    @staticmethod
    def rehash(value: dict[str, object]) -> None:
        value.pop("report_sha256", None)
        value["report_sha256"] = hashlib.sha256(recovery.canonical_bytes(value)).hexdigest()

    def mutation_fails(self, value: dict[str, object], pattern: str) -> None:
        self.rehash(value)
        with self.assertRaisesRegex(validator.M22TrainingValidationError, pattern):
            validator.validate_value(value, self.root)

    def test_training_schema_is_strict_and_valid(self) -> None:
        schema = recovery.load(self.root / runner.SCHEMA)
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["configuration"]["properties"]["seeds"]["const"], list(runner.SEEDS))

    def test_random_baseline_is_deterministic_and_seeded(self) -> None:
        first = [runner.random_correct(runner.SEEDS[0], 7, index) for index in range(128)]
        second = [runner.random_correct(runner.SEEDS[0], 7, index) for index in range(128)]
        other = [runner.random_correct(runner.SEEDS[1], 7, index) for index in range(128)]
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertGreater(sum(first), 0)
        self.assertLess(sum(first), len(first))

    def test_matched_baselines_use_exact_transition_budget(self) -> None:
        counts = [0] + [384] * 16
        rewards = {program: 1.0 + program / 100 for program in range(1, 17)}
        result = runner.matched_baselines(runner.SEEDS[0], counts, rewards)
        self.assertEqual([item["baseline"] for item in result], list(runner.BASELINES))
        self.assertTrue(all(item["matched_transitions"] == 6144 for item in result))
        self.assertEqual(result[0]["correct_program_fraction"], 1.0)
        self.assertEqual(result[-1]["mean_return"], 0.0)
        self.assertGreater(result[0]["mean_return"], result[1]["mean_return"])

    def test_selection_uses_complete_frozen_ordering(self) -> None:
        base = {"eligible": True, "service_count": 16, "mean_development_return": 2.0,
                "mean_company_value": 100.0, "transitions": 4096, "checkpoint_id": "b" * 64}
        lower_id = dict(base, checkpoint_id="a" * 64)
        later = dict(base, transitions=5120, checkpoint_id="0" * 64)
        self.assertEqual(runner.select([base, lower_id, later]), lower_id)

    def test_training_source_and_sandbox_exclude_final_manifest(self) -> None:
        self.assertNotIn(recovery.FINAL_MANIFEST.as_posix(), runner.SOURCE_PATHS)
        self.assertEqual(runner.ARCHITECTURES, recovery.ARCHITECTURES)
        self.assertEqual(len(runner.ARCHITECTURES) * len(runner.SEEDS), 6)

    def test_repository_training_evidence_passes(self) -> None:
        validator.validate_value(self.report, self.root)

    def test_update_trace_mutation_fails(self) -> None:
        value = copy.deepcopy(self.report)
        value["runs"][0]["process"]["updates"][0]["trace"]["actions_sha256"] = "0" * 64
        self.mutation_fails(value, "update digest")

    def test_process_identity_reuse_fails(self) -> None:
        value = copy.deepcopy(self.report)
        value["runs"][1]["process"]["pid"] = value["runs"][0]["process"]["pid"]
        self.mutation_fails(value, "six fresh processes")

    def test_candidate_metric_mutation_fails(self) -> None:
        value = copy.deepcopy(self.report)
        value["runs"][2]["candidates"][3]["mean_development_return"] += 0.01
        self.mutation_fails(value, "candidate metrics")

    def test_overall_selection_mutation_fails(self) -> None:
        value = copy.deepcopy(self.report)
        value["provisional_development_selection"]["checkpoint_id"] = "0" * 64
        self.mutation_fails(value, "overall development selection")


if __name__ == "__main__":
    unittest.main()
