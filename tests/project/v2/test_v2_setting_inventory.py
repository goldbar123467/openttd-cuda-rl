#!/usr/bin/env python3
"""Mutation tests for the pinned-source setting inventory."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_setting_inventory


class SettingInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.inventory_path = cls.root / "config/v2/setting-inventory.json"
        cls.schema_path = cls.root / "docs/project/schema/v2-setting-inventory.schema.json"
        cls.object_repository = cls.root / "openttd-upstream"
        cls.inventory = validate_setting_inventory.load_json(cls.inventory_path)

    def validate_mutation(self, value: object, *, live: bool = False) -> validate_setting_inventory.SettingInventorySummary:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "setting-inventory.json"
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            return validate_setting_inventory.validate(
                self.root,
                path,
                self.schema_path,
                object_repository=self.object_repository if live else None,
            )

    def test_repository_inventory_passes_static_and_live(self) -> None:
        static = validate_setting_inventory.validate(self.root)
        live = validate_setting_inventory.validate(self.root, object_repository=self.object_repository)
        self.assertEqual(static.source_files, 20)
        self.assertEqual(static.definitions, 435)
        self.assertEqual(static.unique_keys, 424)
        self.assertEqual(static.duplicates, 11)
        self.assertFalse(static.live_source)
        self.assertTrue(live.live_source)

    def test_schema_hash_drift_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["schema_sha256"] = "0" * 64
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "schema SHA-256"):
            self.validate_mutation(inventory)

    def test_engine_source_drift_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["engine_source"]["commit"] = "0" * 40
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "engine source"):
            self.validate_mutation(inventory)

    def test_missing_source_file_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["source_files"].pop()
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "source-file policy"):
            self.validate_mutation(inventory)

    def test_source_policy_drift_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["source_files"][0]["disposition"] = "SCENARIO_PIN"
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "disposition policy"):
            self.validate_mutation(inventory)

    def test_omitted_definition_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["definitions"].pop(100)
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "IDs"):
            self.validate_mutation(inventory)

    def test_duplicate_definition_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["definitions"][1]["source_ordinal"] = inventory["definitions"][0]["source_ordinal"]
        with self.assertRaises(validate_setting_inventory.SettingInventoryValidationError):
            self.validate_mutation(inventory)

    def test_scope_drift_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["definitions"][0]["scope"] = "CLIENT"
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "scope drifted"):
            self.validate_mutation(inventory)

    def test_definition_policy_drift_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["definitions"][0]["disposition"] = "SCENARIO_PIN"
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "disposition drifted"):
            self.validate_mutation(inventory)

    def test_summary_count_drift_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["counts"]["definitions"] += 1
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "summary counts"):
            self.validate_mutation(inventory)

    def test_secret_reclassification_fails(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        row = next(item for item in inventory["definitions"] if item["disposition"] == "SECRET_FORBIDDEN")
        row["disposition"] = "HARNESS_PIN"
        row["rationale_code"] = "competition-runtime"
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "disposition drifted"):
            self.validate_mutation(inventory)

    def test_source_expression_mutation_fails_live_extraction(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["definitions"][0]["default_expression"] = "false"
        with self.assertRaisesRegex(validate_setting_inventory.SettingInventoryValidationError, "live pinned-source extraction"):
            self.validate_mutation(inventory, live=True)


if __name__ == "__main__":
    unittest.main()
