#!/usr/bin/env python3
"""Mutation tests for the frozen M22 learning and final-evaluation contracts."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_m22_learning_contract as validator


class M22LearningContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract = validator.load(cls.root / validator.CONTRACT)
        cls.evaluation = validator.load(cls.root / validator.EVALUATION)

    @staticmethod
    def write(directory: pathlib.Path, name: str, value: object) -> pathlib.Path:
        path = directory / name
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def contract_mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = self.write(pathlib.Path(raw), "contract.json", value)
            context = self.assertRaisesRegex(validator.M22ContractError, pattern) if pattern else self.assertRaises(validator.M22ContractError)
            with context:
                validator.validate(self.root, path, self.root / validator.EVALUATION)

    def evaluation_mutation_fails(self, value: object, pattern: str | None = None) -> None:
        mutated_contract = copy.deepcopy(self.contract)
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            evaluation_path = self.write(directory, "evaluation.json", value)
            mutated_contract["identities"]["final_evaluation_manifest_sha256"] = validator.sha256(evaluation_path)
            mutated_contract["independent_evaluation"]["manifest_sha256"] = validator.sha256(evaluation_path)
            contract_path = self.write(directory, "contract.json", mutated_contract)
            context = self.assertRaisesRegex(validator.M22ContractError, pattern) if pattern else self.assertRaises(validator.M22ContractError)
            with context:
                validator.validate(self.root, contract_path, evaluation_path)

    def test_repository_contract_passes(self) -> None:
        summary = validator.validate(self.root)
        self.assertEqual((summary.programs, summary.stages, summary.architectures, summary.trainer_seeds, summary.final_cases),
                         (17, 7, 3, 3, 42))

    def test_contract_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.contract); value["schema_sha256"] = "0" * 64
        self.contract_mutation_fails(value, "schema SHA-256")

    def test_identity_drift_fails(self) -> None:
        value = copy.deepcopy(self.contract); value["identities"]["m21_broad_contract_sha256"] = "0" * 64
        self.contract_mutation_fails(value, "m21_broad_contract")

    def test_program_reorder_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["policy_interface"]["programs"][1], value["policy_interface"]["programs"][2] = value["policy_interface"]["programs"][2], value["policy_interface"]["programs"][1]
        self.contract_mutation_fails(value, "program indices")

    def test_architecture_omission_fails(self) -> None:
        value = copy.deepcopy(self.contract); value["architectures"].pop()
        self.contract_mutation_fails(value)

    def test_transition_budget_drift_fails(self) -> None:
        value = copy.deepcopy(self.contract); value["ppo"]["transitions_per_seed"] -= 1
        self.contract_mutation_fails(value, "campaign transition")

    def test_curriculum_program_omission_fails(self) -> None:
        value = copy.deepcopy(self.contract); value["curriculum"]["stages"][-1]["programs"].pop()
        self.contract_mutation_fails(value, "every non-WAIT")

    def test_final_seed_mutation_fails(self) -> None:
        value = copy.deepcopy(self.evaluation); value["cases"][0]["seed"] += 1
        self.evaluation_mutation_fails(value, "final seed derivation")

    def test_final_case_omission_fails(self) -> None:
        value = copy.deepcopy(self.evaluation); value["cases"].pop(); value["acceptance"]["case_count"] -= 1
        self.evaluation_mutation_fails(value)

    def test_final_required_program_gate_mismatch_fails(self) -> None:
        value = copy.deepcopy(self.evaluation); value["cases"][12]["source_gate"] = "G18"
        self.evaluation_mutation_fails(value, "program/gate mismatch")

    def test_final_access_weakening_fails(self) -> None:
        value = copy.deepcopy(self.evaluation); value["access_policy"]["training"] = "allowed"
        self.evaluation_mutation_fails(value)


if __name__ == "__main__":
    unittest.main()
