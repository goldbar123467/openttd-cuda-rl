#!/usr/bin/env python3
"""Mutation tests for the frozen M23 release and publication contract."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_m23_release_contract as validator


class M23ReleaseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract = validator.load(cls.root / validator.CONTRACT)

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "contract.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = self.write(pathlib.Path(raw), value)
            context = self.assertRaisesRegex(validator.M23ContractError, pattern) if pattern else self.assertRaises(
                validator.M23ContractError
            )
            with context:
                validator.validate(self.root, path)

    def test_repository_contract_passes(self) -> None:
        summary = validator.validate(self.root)
        self.assertEqual(
            (summary.checkpoints, summary.deployment_architectures, summary.equivalence_cases,
             summary.runtime_results, summary.playback_campaigns, summary.requirements),
            (2, 2, 48, 144, 8, 9),
        )

    def test_schema_is_closed_and_identity_bound(self) -> None:
        value = copy.deepcopy(self.contract)
        value["undeclared"] = True
        self.mutation_fails(value, "schema failed")
        value = copy.deepcopy(self.contract)
        value["schema_sha256"] = "0" * 64
        self.mutation_fails(value, "schema SHA-256")

    def test_duplicate_json_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "duplicate.json"
            path.write_text('{"status":"FROZEN","status":"PLANNED"}\n', encoding="utf-8")
            with self.assertRaisesRegex(validator.M23ContractError, "duplicate JSON key"):
                validator.load(path)

    def test_foundation_identity_or_omission_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["foundations"]["files"][3]["sha256"] = "0" * 64
        self.mutation_fails(value, "foundation inventory")
        value = copy.deepcopy(self.contract)
        value["foundations"]["files"].pop()
        self.mutation_fails(value, "foundation inventory")

    def test_v1_preservation_weakening_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["foundations"]["v1_boundary"] = "best effort"
        self.mutation_fails(value, "V1 preservation")

    def test_checkpoint_architecture_omission_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["checkpoint_packages"]["architectures"].pop()
        self.mutation_fails(value, "checkpoint architecture")

    def test_checkpoint_file_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["checkpoint_packages"]["architectures"][0]["files"][2]["sha256"] = "0" * 64
        self.mutation_fails(value, "checkpoint exact file identity")

    def test_checkpoint_id_or_copy_policy_mutation_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["checkpoint_packages"]["architectures"][1]["checkpoint_id"] = "0" * 64
        self.mutation_fails(value, "selection metadata")
        value = copy.deepcopy(self.contract)
        value["checkpoint_packages"]["copy_policy"] = "rewrite metadata"
        self.mutation_fails(value, "copy policy")

    def test_deployment_architecture_omission_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["deployment_packages"]["architectures"].pop()
        self.mutation_fails(value, "deployment architecture")

    def test_onnx_opset_or_input_shape_mutation_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["deployment_packages"]["graph"]["opset"] = 19
        self.mutation_fails(value, "ONNX graph")
        value = copy.deepcopy(self.contract)
        value["deployment_packages"]["graph"]["inputs"][2]["shape"][1] = 128
        self.mutation_fails(value, "graph signature")

    def test_recurrent_adapter_weakening_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["deployment_packages"]["adapter"]["reset"] = "ignored"
        self.mutation_fails(value, "adapter semantic")

    def test_training_dependency_in_deployment_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["deployment_packages"]["dependency_boundary"]["forbidden"].remove("LibTorch")
        self.mutation_fails(value, "inference-only dependency")

    def test_equivalence_case_count_or_class_mutation_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["equivalence"]["total_architecture_cases"] = 47
        self.mutation_fails(value, "case count")
        value = copy.deepcopy(self.contract)
        value["equivalence"]["case_classes"][2]["count_per_architecture"] = 7
        self.mutation_fails(value, "case classes")

    def test_equivalence_tolerance_weakening_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["equivalence"]["tolerances"]["next_hidden"]["absolute"] = 0.05
        self.mutation_fails(value, "tolerance")

    def test_equivalence_rejection_omission_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["equivalence"]["rejection_matrix"].remove("all-illegal-mask")
        self.mutation_fails(value, "rejection matrix")

    def test_program_executor_omission_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["normal_game"]["program_executors"].remove("ship-constructed")
        self.mutation_fails(value, "executor inventory")

    def test_learned_boundary_or_admin_shortcut_weakening_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["normal_game"]["controller_boundary"]["learned"] = "all control is learned"
        self.mutation_fails(value, "controller")
        value = copy.deepcopy(self.contract)
        value["normal_game"]["controller_boundary"]["admin_shortcuts"] = "allowed"
        self.mutation_fails(value, "no-admin")

    def test_visible_campaign_seed_or_opponent_mutation_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["normal_game"]["campaigns"][0]["seed"] += 1
        self.mutation_fails(value, "campaign seed")
        value = copy.deepcopy(self.contract)
        value["normal_game"]["campaigns"][5]["opponent"] = "NoOpAI"
        self.mutation_fails(value, "campaign content")

    def test_headless_or_partial_visible_acceptance_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["normal_game"]["campaign_acceptance"]["headless_or_dedicated"] = True
        self.mutation_fails(value, "visible normal-game")
        value = copy.deepcopy(self.contract)
        value["normal_game"]["campaign_acceptance"]["required_all_campaigns"] = False
        self.mutation_fails(value, "visible normal-game")

    def test_control_or_inspection_omission_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        del value["normal_game"]["controls"]["reload"]
        self.mutation_fails(value, "control inventory")
        value = copy.deepcopy(self.contract)
        value["normal_game"]["inspection"]["required_fields"].remove("last_error")
        self.mutation_fails(value, "inspection field")

    def test_safe_fallback_or_corruption_rejection_weakening_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["normal_game"]["failure_policy"]["safe_fallback"] = "random legal program"
        self.mutation_fails(value, "failure/fallback")
        value = copy.deepcopy(self.contract)
        value["normal_game"]["failure_policy"]["required_rejections"].remove("corrupt-model")
        self.mutation_fails(value, "failure/fallback")

    def test_operator_workflow_omission_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["operator_release"]["guide"]["one_linear_workflow"].remove("resume")
        self.mutation_fails(value, "guide workflow")

    def test_reproduction_root_or_byte_match_weakening_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["operator_release"]["reproduction"]["roots"] = 1
        self.mutation_fails(value, "two-root")
        value = copy.deepcopy(self.contract)
        value["operator_release"]["reproduction"]["required_matches"].remove("onnx-byte")
        self.mutation_fails(value, "reproduction boundary")

    def test_quality_or_zero_defect_weakening_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["operator_release"]["quality"]["nonclosed_defects"] = 1
        self.mutation_fails(value, "zero-defect")
        value = copy.deepcopy(self.contract)
        value["operator_release"]["quality"]["credential_scan"] = False
        self.mutation_fails(value, "quality")

    def test_publication_review_weakening_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["operator_release"]["publication"]["require_release_asset_round_trip"] = False
        self.mutation_fails(value, "publication boundary")
        value = copy.deepcopy(self.contract)
        value["operator_release"]["publication"]["v1_tag_and_asset_revalidation"] = False
        self.mutation_fails(value, "publication boundary")

    def test_requirement_inventory_or_definition_of_done_weakening_fails(self) -> None:
        value = copy.deepcopy(self.contract)
        value["requirements"].pop()
        self.mutation_fails(value)
        value = copy.deepcopy(self.contract)
        value["acceptance"]["definition_of_done"] = "most tests pass"
        self.mutation_fails(value, "definition-of-done")


if __name__ == "__main__":
    unittest.main()
