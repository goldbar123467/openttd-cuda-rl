#!/usr/bin/env python3
"""Mutation tests for the frozen M15 scalable environment contract."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_m15_scalable_contract


class M15ScalableContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract_path = cls.root / "config/v2/m15-scalable-contract.json"
        cls.schema_path = cls.root / "docs/project/schema/v2-m15-scalable-contract.schema.json"
        cls.contract = validate_m15_scalable_contract.load_json(cls.contract_path)

    def validate_mutation(self, value: object) -> validate_m15_scalable_contract.M15ScalableContractSummary:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "m15.json"
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            return validate_m15_scalable_contract.validate(self.root, path, self.schema_path)

    def test_repository_contract_passes(self) -> None:
        summary = validate_m15_scalable_contract.validate(self.root)
        self.assertEqual(summary.rectangles, 49)
        self.assertEqual(summary.seeds, 48)
        self.assertEqual(summary.spatial_levels, 3)
        self.assertEqual(summary.entity_tables, 5)
        self.assertEqual(summary.action_families, 12)
        self.assertEqual(summary.observation_bytes, 2182927)
        self.assertEqual(summary.candidate_capacity, 4096)

    def test_schema_hash_drift_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["schema_sha256"] = "0" * 64
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "schema SHA-256"):
            self.validate_mutation(contract)

    def test_g14_identity_drift_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["identity"]["g14_gate_report_sha256"] = "0" * 64
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "g14_gate_report"):
            self.validate_mutation(contract)

    def test_v1_compatibility_digest_drift_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["identity"]["v1_contracts"]["observation"] = "0" * 64
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "V1 observation"):
            self.validate_mutation(contract)

    def test_missing_native_rectangle_fails_schema(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["map"]["native_rectangles"].pop()
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "schema failed"):
            self.validate_mutation(contract)

    def test_reordered_native_rectangles_fail(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["map"]["native_rectangles"][0], contract["map"]["native_rectangles"][1] = contract["map"]["native_rectangles"][1], contract["map"]["native_rectangles"][0]
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "rectangle inventory"):
            self.validate_mutation(contract)

    def test_curriculum_drift_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["map"]["curriculum"][0] = [64, 128]
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "curriculum"):
            self.validate_mutation(contract)

    def test_seed_derivation_mutation_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["seeds"]["sets"]["development"]["seeds"][0] += 1
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "deterministic derivation"):
            self.validate_mutation(contract)

    def test_underpowered_final_seed_set_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["seeds"]["sets"]["final"]["seeds"] = contract["seeds"]["sets"]["final"]["seeds"][:8]
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "underpowered"):
            self.validate_mutation(contract)

    def test_missing_scenario_manifest_identity_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["scenario"]["manifest_fields"].remove("settings_manifest_sha256")
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "manifest identity"):
            self.validate_mutation(contract)

    def test_town_capacity_drift_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["scenario"]["counts"]["towns"]["maximum"] = 127
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "town/industry bounds"):
            self.validate_mutation(contract)

    def test_spatial_pyramid_reordering_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["observation"]["spatial"][0], contract["observation"]["spatial"][1] = contract["observation"]["spatial"][1], contract["observation"]["spatial"][0]
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "spatial pyramid order"):
            self.validate_mutation(contract)

    def test_entity_inventory_reordering_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["observation"]["entities"][0], contract["observation"]["entities"][1] = contract["observation"]["entities"][1], contract["observation"]["entities"][0]
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "entity table inventory"):
            self.validate_mutation(contract)

    def test_entity_capacity_drift_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        next(item for item in contract["observation"]["entities"] if item["name"] == "vehicles")["capacity"] = 512
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "vehicle observation capacity"):
            self.validate_mutation(contract)

    def test_observation_byte_budget_drift_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["resources"]["observation_bytes"] += 4
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "observation byte budget"):
            self.validate_mutation(contract)

    def test_action_family_omission_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["action"]["families"].remove("MANAGE_LOAN")
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "action family inventory"):
            self.validate_mutation(contract)

    def test_candidate_byte_budget_drift_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["resources"]["candidate_bytes"] += 1
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "candidate byte budget"):
            self.validate_mutation(contract)

    def test_protocol_payload_underflow_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["resources"]["protocol_payload_bytes"] = 1048576
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "cannot hold"):
            self.validate_mutation(contract)

    def test_nonmonotonic_resource_budget_fails(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["resources"]["map_tier_limits"][2]["max_rss_kib"] = 100000
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "RSS budgets"):
            self.validate_mutation(contract)

    def test_v1_adapter_weakening_fails_schema(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["reset"]["v1_adapter"] = "approximately-compatible"
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "schema failed"):
            self.validate_mutation(contract)

    def test_legality_weakening_fails_schema(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["action"]["legality"] = "planner-heuristic-is-authoritative"
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "schema failed"):
            self.validate_mutation(contract)

    def test_final_seed_leakage_policy_fails_schema(self) -> None:
        contract = copy.deepcopy(self.contract)
        contract["seeds"]["final_policy"] = "available-to-training"
        with self.assertRaisesRegex(validate_m15_scalable_contract.M15ScalableContractError, "schema failed"):
            self.validate_mutation(contract)


if __name__ == "__main__":
    unittest.main()
