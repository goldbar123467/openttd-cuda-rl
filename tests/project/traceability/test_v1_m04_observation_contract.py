#!/usr/bin/env python3
"""Contract, schema, candidate, normalization, and adapter tests for M04."""

from __future__ import annotations

import copy
import hashlib
import pathlib
import tempfile
import unittest

import jsonschema

import m04_preprocessing
import validate_m04_observation_contract


class V1M04ObservationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract_path = cls.root / "config/v1/m04-observation-contract.json"
        cls.schema_path = cls.root / "docs/project/schema/v1-m04-observation-contract.schema.json"
        cls.contract = validate_m04_observation_contract.validate(
            cls.contract_path,
            cls.schema_path,
        )
        cls.schema = validate_m04_observation_contract.load_strict_json(cls.schema_path)

    def test_frozen_contract_schema_and_golden_identities_are_exact(self) -> None:
        self.assertEqual(
            self.contract["identity"]["compatibility_sha256"],
            "7f8a46af1fe2a2c23e755c71b3bc2d04c9a0d057c573e901e5c9ed9178ca13eb",
        )
        self.assertEqual(
            hashlib.sha256(self.contract_path.read_bytes()).hexdigest(),
            "6139634cf1ae8a1b0d639596e400a12b6b6f56fe3e9a3a1ee5d92d731013877e",
        )
        self.assertEqual(
            hashlib.sha256(self.schema_path.read_bytes()).hexdigest(),
            "0cafc71df2c8af62f93e0e52df8493b07873ad0bc598fbd5207015dc5836ee92",
        )
        golden = self.root / "tests/fixtures/v1/m04-observation-goldens.json"
        self.assertEqual(
            hashlib.sha256(golden.read_bytes()).hexdigest(),
            "1dce190b8e7216b03c5e45cc6ee0af050bf69aa773aecc051250a4288ccf3ec6",
        )

    def test_every_field_and_channel_is_individually_frozen(self) -> None:
        fields = self.contract["tensors"]["structured"]["fields"]
        channels = self.contract["tensors"]["spatial"]["channels"]
        self.assertEqual([item["index"] for item in fields], list(range(256)))
        self.assertEqual([item["index"] for item in channels], list(range(32)))
        for item in fields + channels:
            for key in (
                "name",
                "semantic_source",
                "raw_type",
                "unit",
                "transform",
                "clip",
                "output_bounds",
                "missing",
                "update_boundary",
            ):
                self.assertIn(key, item)
        self.assertTrue(all(item["positive_fixture"] for item in channels))

    def test_candidate_registry_dispositions_every_m04_family(self) -> None:
        registry = self.contract["candidate_registry"]
        covered = {requirement for item in registry for requirement in item["requirements"]}
        self.assertTrue({f"OBS-{index:03d}" for index in range(2, 14)} <= covered)
        excluded = {item["candidate"]: item for item in registry if item["disposition"] != "INCLUDED"}
        self.assertIn("water", excluded)
        self.assertIn("route occupancy/path", excluded)
        self.assertIn("recent reward components", excluded)
        self.assertTrue(all(len(item["rationale"]) >= 30 for item in excluded.values()))

    def test_schema_rejects_contract_family_mutations(self) -> None:
        mutations = []
        shape = copy.deepcopy(self.contract)
        shape["tensors"]["spatial"]["shape"] = [32, 31, 32]
        mutations.append(shape)
        boundary = copy.deepcopy(self.contract)
        boundary["boundary"]["may_execute_commands"] = True
        mutations.append(boundary)
        fitted = copy.deepcopy(self.contract)
        fitted["normalization"]["evaluation_updates"] = True
        mutations.append(fitted)
        shared = copy.deepcopy(self.contract)
        shared["shared_preprocessing"]["duplicate_transform_implementations_allowed"] = True
        mutations.append(shared)
        for mutant in mutations:
            with self.subTest(mutant=mutant):
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.Draft202012Validator(self.schema).validate(mutant)

    def test_semantic_validator_rejects_reorder_duplicate_and_slot_drift(self) -> None:
        reorder = copy.deepcopy(self.contract)
        reorder["tensors"]["structured"]["fields"][0]["index"] = 1
        with self.assertRaisesRegex(validate_m04_observation_contract.M04ObservationContractError, "indices"):
            validate_m04_observation_contract.validate_semantics(reorder)
        duplicate = copy.deepcopy(self.contract)
        duplicate["tensors"]["spatial"]["channels"][1]["name"] = duplicate["tensors"]["spatial"]["channels"][0]["name"]
        with self.assertRaisesRegex(validate_m04_observation_contract.M04ObservationContractError, "unique"):
            validate_m04_observation_contract.validate_semantics(duplicate)
        slots = copy.deepcopy(self.contract)
        slots["slots"]["station"]["maximum"] = 15
        with self.assertRaisesRegex(validate_m04_observation_contract.M04ObservationContractError, "maxima"):
            validate_m04_observation_contract.validate_semantics(slots)

    def test_all_consumers_receive_identical_native_tensor_bytes(self) -> None:
        observation = {
            "compatibility_sha256": self.contract["identity"]["compatibility_sha256"],
            "schema_version": "openttd-rl-v1-m04-observation-1",
            "structured": {"data": [0.0] * 256, "dtype": "float32", "logical_order": "feature", "shape": [256]},
            "spatial": {"data": [0.0] * (32 * 32 * 32), "dtype": "float32", "logical_order": "channel-y-x", "shape": [32, 32, 32]},
        }
        outputs = [
            m04_preprocessing.load_policy_tensors(observation, consumer=consumer, contract=self.contract)
            for consumer in self.contract["shared_preprocessing"]["consumers"]
        ]
        self.assertEqual(len({item.combined for item in outputs}), 1)
        self.assertEqual(len(outputs[0].combined), (256 + 32 * 32 * 32) * 4)

    def test_adapter_rejects_wrong_identity_nonfinite_bounds_and_oracle_leak(self) -> None:
        base = {
            "compatibility_sha256": self.contract["identity"]["compatibility_sha256"],
            "schema_version": "openttd-rl-v1-m04-observation-1",
            "structured": {"data": [0.0] * 256, "dtype": "float32", "logical_order": "feature", "shape": [256]},
            "spatial": {"data": [0.0] * (32 * 32 * 32), "dtype": "float32", "logical_order": "channel-y-x", "shape": [32, 32, 32]},
        }
        wrong = copy.deepcopy(base)
        wrong["compatibility_sha256"] = "0" * 64
        with self.assertRaisesRegex(m04_preprocessing.M04PreprocessingError, "identity"):
            m04_preprocessing.load_policy_tensors(wrong, consumer="trainer", contract=self.contract)
        nonfinite = copy.deepcopy(base)
        nonfinite["structured"]["data"][0] = float("nan")
        with self.assertRaisesRegex(m04_preprocessing.M04PreprocessingError, "outside"):
            m04_preprocessing.load_policy_tensors(nonfinite, consumer="trainer", contract=self.contract)
        bounded = copy.deepcopy(base)
        bounded["spatial"]["data"][0] = 1.1
        with self.assertRaisesRegex(m04_preprocessing.M04PreprocessingError, "outside"):
            m04_preprocessing.load_policy_tensors(bounded, consumer="trainer", contract=self.contract)
        leak = copy.deepcopy(base)
        leak["source_projection"] = {}
        with self.assertRaisesRegex(m04_preprocessing.M04PreprocessingError, "cannot enter"):
            m04_preprocessing.load_policy_tensors(leak, consumer="in-game-controller", contract=self.contract)

    def test_strict_loader_rejects_duplicate_keys_and_bom(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            duplicate = pathlib.Path(raw) / "duplicate.json"
            duplicate.write_text('{"a":1,"a":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(validate_m04_observation_contract.M04ObservationContractError, "duplicate"):
                validate_m04_observation_contract.load_strict_json(duplicate)
            bom = pathlib.Path(raw) / "bom.json"
            bom.write_bytes(b"\xef\xbb\xbf{}\n")
            with self.assertRaisesRegex(validate_m04_observation_contract.M04ObservationContractError, "BOM"):
                validate_m04_observation_contract.load_strict_json(bom)


if __name__ == "__main__":
    unittest.main()
