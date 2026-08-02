#!/usr/bin/env python3
"""Mutation tests for the M15 scalable policy contract."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_m15_policy_contract


class M15PolicyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validate_m15_policy_contract.load_json(cls.root / validate_m15_policy_contract.CONFIG)
        cls.schema = cls.root / validate_m15_policy_contract.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "policy-contract.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validate_m15_policy_contract.M15PolicyContractError, pattern) if pattern else self.assertRaises(validate_m15_policy_contract.M15PolicyContractError)
            with context:
                validate_m15_policy_contract.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_repository_contract_passes(self) -> None:
        summary = validate_m15_policy_contract.validate(self.root)
        self.assertEqual((summary.inputs, summary.outputs, summary.devices), (25, 4, 2))
        self.assertEqual(summary.parameters, 1239406)

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config); value["schema_sha256"] = "0" * 64
        self.mutation_fails(value, "schema SHA-256")

    def test_encoder_omission_fails(self) -> None:
        value = copy.deepcopy(self.config); value["architecture"]["encoders"].pop()
        self.mutation_fails(value)

    def test_input_shape_drift_fails(self) -> None:
        value = copy.deepcopy(self.config); value["inputs"][12]["shape"] = ["batch", 1023, 40]
        self.mutation_fails(value, "vehicles")

    def test_onnx_order_drift_fails(self) -> None:
        value = copy.deepcopy(self.config); value["onnx"]["inputs"][0], value["onnx"]["inputs"][1] = value["onnx"]["inputs"][1], value["onnx"]["inputs"][0]
        self.mutation_fails(value, "ONNX input order")

    def test_checkpoint_state_omission_fails(self) -> None:
        value = copy.deepcopy(self.config); value["checkpoint"]["state"].remove("rng_state")
        self.mutation_fails(value)

    def test_recurrent_width_drift_fails(self) -> None:
        value = copy.deepcopy(self.config); value["architecture"]["memory"]["hidden_size"] = 128
        self.mutation_fails(value)


if __name__ == "__main__":
    unittest.main()
