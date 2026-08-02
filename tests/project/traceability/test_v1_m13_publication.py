#!/usr/bin/env python3
"""M13 public-release contract and distribution-boundary guards."""

from __future__ import annotations

import copy
import json
import pathlib
import unittest

import jsonschema

import validate_m13_publication_contract


class V1M13PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract_path = cls.root / "config/v1/m13-publication-contract.json"
        cls.schema_path = cls.root / "docs/project/schema/v1-m13-publication-contract.schema.json"

    def test_contract_is_frozen_and_self_consistent(self) -> None:
        contract = validate_m13_publication_contract.validate(
            self.contract_path, self.schema_path
        )
        self.assertEqual(
            contract["identity"]["compatibility_sha256"],
            validate_m13_publication_contract.EXPECTED_COMPATIBILITY,
        )
        self.assertEqual(contract["gates"], validate_m13_publication_contract.EXPECTED_GATES)

    def test_semantic_mutations_fail_schema_or_identity(self) -> None:
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        mutations = []
        value = copy.deepcopy(contract)
        value["status"] = "DRAFT"
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["archive"]["excluded_components"].pop()
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["model_package"]["files"]["model.onnx"] = "0" * 64
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["repository_surface"]["required_paths"].pop()
        mutations.append(value)
        for mutation in mutations:
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(schema).validate(mutation)

    def test_distribution_is_model_evidence_only(self) -> None:
        contract = validate_m13_publication_contract.validate(
            self.contract_path, self.schema_path
        )
        excluded = set(contract["archive"]["excluded_components"])
        self.assertTrue(
            {"openttd-binaries", "opengfx", "onnxruntime", "libtorch", "cuda-runtime"}
            <= excluded
        )
        self.assertEqual(contract["model_package"]["license"], "GPL-2.0-only")
        self.assertEqual(len(contract["archive"]["required_payload_files"]), 8)

    def test_publication_builder_owns_every_gate(self) -> None:
        runner_path = self.root / "scripts/v1/build_v1_publication.py"
        if not runner_path.is_file():
            self.skipTest("M13 publication builder is added after contract preregistration")
        runner = runner_path.read_text(encoding="utf-8")
        for boundary in (
            "origin/main",
            "gitleaks",
            "symlink",
            "safe archive",
            "byte-identical",
            "forbidden_text",
        ):
            self.assertIn(boundary, runner)


if __name__ == "__main__":
    unittest.main()
