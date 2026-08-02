#!/usr/bin/env python3
"""M12 release-contract, evidence, and final-closure guards."""

from __future__ import annotations

import copy
import json
import pathlib
import unittest

import jsonschema

import validate_m12_release_contract


class V1M12ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract_path = cls.root / "config/v1/m12-release-contract.json"
        cls.schema_path = cls.root / "docs/project/schema/v1-m12-release-contract.schema.json"

    def test_contract_is_frozen_complete_and_self_consistent(self) -> None:
        contract = validate_m12_release_contract.validate(self.contract_path, self.schema_path)
        self.assertEqual(contract["identity"]["compatibility_sha256"], validate_m12_release_contract.EXPECTED_COMPATIBILITY)
        self.assertEqual(contract["campaigns"], validate_m12_release_contract.EXPECTED_CAMPAIGNS)
        self.assertEqual(len(contract["accepted_evidence"]), 14)
        self.assertEqual(len(contract["requirements"]), 18)

    def test_semantic_mutations_fail_schema_or_identity(self) -> None:
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        mutations = []
        value = copy.deepcopy(contract)
        value["status"] = "DRAFT"
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["supported_host"]["os_version"] = "rolling"
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["campaigns"].pop()
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["requirements"].pop()
        mutations.append(value)
        for mutation in mutations:
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(schema).validate(mutation)

    def test_release_runner_owns_every_campaign_and_quality_boundary(self) -> None:
        runner_path = self.root / "scripts/v1/run_m12_release_gate.py"
        if not runner_path.is_file():
            self.skipTest("M12 release runner is added after contract preregistration")
        runner = runner_path.read_text(encoding="utf-8")
        for campaign in validate_m12_release_contract.EXPECTED_CAMPAIGNS:
            self.assertIn(f'"{campaign}"', runner)
        for boundary in ("ShellCheck", "sanitizer", "malformed", "resource", "fault", "fresh", "origin/main"):
            self.assertIn(boundary, runner)

    def test_all_accepted_evidence_digests_are_nonzero_and_distinct(self) -> None:
        contract = validate_m12_release_contract.validate(self.contract_path, self.schema_path)
        digests = [item["sha256"] for item in contract["accepted_evidence"]]
        self.assertTrue(all(digest != "0" * 64 for digest in digests))
        self.assertEqual(len(digests), len(set(digests)))


if __name__ == "__main__":
    unittest.main()
