#!/usr/bin/env python3
"""Mutation tests for the detailed M15 hierarchical action contract."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_m15_action_contract


class M15ActionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validate_m15_action_contract.load_json(cls.root / validate_m15_action_contract.CONFIG)
        cls.schema = cls.root / validate_m15_action_contract.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "action-contract.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_action_contract.M15ActionContractError, "schema SHA-256"):
                validate_m15_action_contract.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_section_offset_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["binary"]["sections"][1]["offset"] += 1
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_action_contract.M15ActionContractError, "section layout"):
                validate_m15_action_contract.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_family_quota_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["families"][2]["quota"] -= 1
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_action_contract.M15ActionContractError, "family quotas"):
                validate_m15_action_contract.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_family_order_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["families"][7]["name"] = "STOP_VEHICLE"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_action_contract.M15ActionContractError, "family names"):
                validate_m15_action_contract.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_parameter_mapping_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["families"][5]["parameter_words"][0] = "depot_tile"
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_action_contract.M15ActionContractError, "parameter mapping"):
                validate_m15_action_contract.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)


if __name__ == "__main__":
    unittest.main()
