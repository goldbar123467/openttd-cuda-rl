#!/usr/bin/env python3
"""Mutation tests for the detailed M15 bounded-observation contract."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_m15_observation_contract


class M15ObservationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validate_m15_observation_contract.load_json(cls.root / validate_m15_observation_contract.CONFIG)
        cls.schema = cls.root / validate_m15_observation_contract.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "observation-contract.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_observation_contract.M15ObservationContractError, "schema SHA-256"):
                validate_m15_observation_contract.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_section_offset_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["serialization"]["sections"][4]["offset"] += 1
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_observation_contract.M15ObservationContractError, "section layout"):
                validate_m15_observation_contract.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_channel_order_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["spatial"]["channels"][1], value["spatial"]["channels"][2] = value["spatial"]["channels"][2], value["spatial"]["channels"][1]
        value["spatial"]["channels"][1]["index"] = 1
        value["spatial"]["channels"][2]["index"] = 2
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_observation_contract.M15ObservationContractError, "semantic channels"):
                validate_m15_observation_contract.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_entity_capacity_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["entities"][2]["capacity"] = 255
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_observation_contract.M15ObservationContractError, "capacities/features"):
                validate_m15_observation_contract.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_reserved_range_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["entities"][4]["reserved"]["start"] = 12
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_observation_contract.M15ObservationContractError, "reserved range"):
                validate_m15_observation_contract.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)


if __name__ == "__main__":
    unittest.main()
