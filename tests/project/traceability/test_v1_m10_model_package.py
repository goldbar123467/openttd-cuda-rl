#!/usr/bin/env python3
"""M10 frozen package, exporter, runtime, tolerance, and rejection guards."""

from __future__ import annotations

import copy
import json
import pathlib
import unittest

import jsonschema

import validate_m10_model_package_contract


class V1M10ModelPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract_path = cls.root / "config/v1/m10-model-package-contract.json"
        cls.schema_path = cls.root / "docs/project/schema/v1-m10-model-package-contract.schema.json"

    def test_contract_is_frozen_and_self_consistent(self) -> None:
        contract = validate_m10_model_package_contract.validate(self.contract_path, self.schema_path)
        self.assertEqual(contract["identity"]["compatibility_sha256"], validate_m10_model_package_contract.EXPECTED_COMPATIBILITY)
        self.assertEqual(len(contract["models"]), 3)
        self.assertEqual(contract["exporter"]["opset"], 18)
        self.assertEqual(contract["runtime"]["version"], "1.28.0")

    def test_training_and_deployment_formats_are_distinct(self) -> None:
        contract = validate_m10_model_package_contract.validate(self.contract_path, self.schema_path)
        checkpoint = contract["checkpoint_policy"]
        self.assertNotEqual(checkpoint["training_format"], checkpoint["deployment_format"])
        self.assertFalse(checkpoint["training_state_in_deployment"])
        self.assertTrue(checkpoint["source_read_only"])

    def test_contract_mutations_fail_closed(self) -> None:
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        mutations = []
        value = copy.deepcopy(contract)
        value["status"] = "DRAFT"
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["requirements"].pop()
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["runtime"]["training_dependency"] = True
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["models"].pop()
        mutations.append(value)
        for mutation in mutations:
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(schema).validate(mutation)

    def test_frozen_tolerances_and_distribution_budget_are_nontrivial(self) -> None:
        contract = validate_m10_model_package_contract.validate(self.contract_path, self.schema_path)
        self.assertLessEqual(contract["tolerances"]["policy_logits"]["absolute"], 2e-5)
        self.assertEqual(contract["tolerances"]["greedy_action"], "exact")
        self.assertGreaterEqual(contract["sampled_distribution"]["samples_per_case_per_runtime"], 100_000)
        self.assertGreaterEqual(len(contract["rejection_matrix"]), 30)


if __name__ == "__main__":
    unittest.main()
