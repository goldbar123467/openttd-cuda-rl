#!/usr/bin/env python3
"""Contract, codec, mask, sampling, and independent-oracle tests for M05."""

from __future__ import annotations

import copy
import hashlib
import math
import pathlib
import tempfile
import unittest

import jsonschema

import m05_action_adapter
import validate_m05_action_contract


class V1M05ActionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract_path = cls.root / "config/v1/m05-action-contract.json"
        cls.schema_path = cls.root / "docs/project/schema/v1-m05-action-contract.schema.json"
        cls.contract = validate_m05_action_contract.validate(cls.contract_path, cls.schema_path)
        cls.schema = validate_m05_action_contract.load_strict_json(cls.schema_path)

    def test_frozen_contract_schema_and_compatibility_identities_are_exact(self) -> None:
        self.assertEqual(
            self.contract["identity"]["compatibility_sha256"],
            "215c7d3ebeea97f1629debee4a2d10301838ccfd3085e4828685591677b58536",
        )
        self.assertEqual(
            hashlib.sha256(self.contract_path.read_bytes()).hexdigest(),
            "33d42081e05abc6e2bb62623a460e3153111e3b253ca90e4b48d39ef9e843d47",
        )
        self.assertEqual(
            hashlib.sha256(self.schema_path.read_bytes()).hexdigest(),
            "8548f92fdad6ca1e44af1749212d01609739a7f23889e4d9bc7b057662d74803",
        )

    def test_every_action_index_round_trips_with_boundary_parameters(self) -> None:
        for index in range(m05_action_adapter.ACTION_COUNT):
            with self.subTest(index=index):
                decoded = m05_action_adapter.decode_action(index)
                self.assertEqual(
                    m05_action_adapter.encode_action(decoded.family, **dict(decoded.parameters)),
                    index,
                )
        for invalid in (-1, 41, True, 2.5):
            with self.subTest(invalid=invalid):
                with self.assertRaises(m05_action_adapter.M05ActionAdapterError):
                    m05_action_adapter.decode_action(invalid)  # type: ignore[arg-type]
        invalid_encodings = (
            ("SELECT_TOWNS", {"origin_town_slot": False, "destination_town_slot": 1}),
            ("BUILD_BUS_STOP", {"site_town_slot": True, "orientation": 0}),
            ("BUY_BUS", {"depot_site": False, "engine_id": 116}),
            ("SET_RUNNING", {"vehicle_slot": 0, "desired_running": 1}),
        )
        for family, parameters in invalid_encodings:
            with self.subTest(family=family, parameters=parameters):
                with self.assertRaises(m05_action_adapter.M05ActionAdapterError):
                    m05_action_adapter.encode_action(family, **parameters)

    def test_schema_and_semantic_validator_reject_family_and_horizon_drift(self) -> None:
        shape = copy.deepcopy(self.contract)
        shape["mask"]["shape"] = [40]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(shape)
        family = copy.deepcopy(self.contract)
        family["families"][4]["index_start"] = 11
        with self.assertRaisesRegex(validate_m05_action_contract.M05ActionContractError, "ranges"):
            validate_m05_action_contract.validate_semantics(family)
        horizon = copy.deepcopy(self.contract)
        horizon["boundary"]["episode_tick_budget"] = 65535
        with self.assertRaisesRegex(validate_m05_action_contract.M05ActionContractError, "horizons"):
            validate_m05_action_contract.validate_semantics(horizon)

    def test_illegal_logits_receive_exactly_zero_probability_for_every_consumer(self) -> None:
        legal = [0] * 41
        legal[0] = 1
        legal[3] = 1
        mask = self._mask(legal)
        logits = [1000.0] * 41
        logits[0] = -1000.0
        logits[3] = -999.0
        outputs = [
            m05_action_adapter.masked_distribution(logits, mask, consumer=consumer)
            for consumer in m05_action_adapter.CONSUMERS
        ]
        self.assertEqual(len({result.probabilities for result in outputs}), 1)
        self.assertEqual(outputs[0].legal_count, 2)
        self.assertTrue(all(outputs[0].probabilities[index] == 0.0 for index in range(41) if index not in (0, 3)))
        self.assertAlmostEqual(math.fsum(outputs[0].probabilities), 1.0)

    def test_all_masked_and_single_legal_sampling_are_safe(self) -> None:
        empty = m05_action_adapter.masked_distribution([0.0] * 41, self._mask([0] * 41), consumer="trainer")
        self.assertTrue(empty.all_masked_fallback)
        self.assertEqual(m05_action_adapter.greedy_action(empty), 0)
        for uniform in (0.0, 0.5, math.nextafter(1.0, 0.0)):
            self.assertEqual(m05_action_adapter.sample_action(empty, uniform), 0)
        one = [0] * 41
        one[40] = 1
        distribution = m05_action_adapter.masked_distribution([-100.0] * 41, self._mask(one), consumer="evaluator")
        self.assertEqual(m05_action_adapter.greedy_action(distribution), 40)
        self.assertEqual(m05_action_adapter.sample_action(distribution, 0.999), 40)

    def test_mask_rejects_identity_shape_count_nonbinary_and_nonfinite_logits(self) -> None:
        base = self._mask([1] + [0] * 40)
        mutations = []
        wrong_identity = copy.deepcopy(base)
        wrong_identity["compatibility_sha256"] = "0" * 64
        mutations.append(wrong_identity)
        wrong_shape = copy.deepcopy(base)
        wrong_shape["legal"].pop()
        mutations.append(wrong_shape)
        wrong_count = copy.deepcopy(base)
        wrong_count["legal_count"] = 2
        mutations.append(wrong_count)
        nonbinary = copy.deepcopy(base)
        nonbinary["legal"][0] = True
        mutations.append(nonbinary)
        for mutant in mutations:
            with self.subTest(mutant=mutant):
                with self.assertRaises(m05_action_adapter.M05ActionAdapterError):
                    m05_action_adapter.validate_mask(mutant)
        with self.assertRaisesRegex(m05_action_adapter.M05ActionAdapterError, "finite"):
            m05_action_adapter.masked_distribution([float("nan")] + [0.0] * 40, base, consumer="trainer")

    def test_independent_oracle_covers_construction_route_and_vehicle_lifecycle(self) -> None:
        reset = self._source()
        mask = m05_action_adapter.independent_oracle_mask(reset)
        self.assertEqual({index for index, value in enumerate(mask) if value}, {0, 1, 2, 3, 5, 8})
        built = self._source()
        built["selection"] = {"origin_town_slot": 0, "destination_town_slot": 1}
        built["connector"]["built"] = True
        built["depot"]["present"] = True
        built["stops"][0]["station_id"] = 0
        built["stops"][1]["station_id"] = 1
        built["vehicles"][0].update(present=True, running=False, orders=[])
        mask = m05_action_adapter.independent_oracle_mask(built)
        self.assertEqual(mask[16], 1)
        self.assertEqual(mask[17], 1)
        built["vehicles"][0]["orders"] = [0, 1]
        mask = m05_action_adapter.independent_oracle_mask(built)
        self.assertEqual(mask[17], 0)
        self.assertEqual(mask[25], 1)
        built["vehicles"][0]["running"] = True
        mask = m05_action_adapter.independent_oracle_mask(built)
        self.assertEqual(mask[25], 0)
        self.assertEqual(mask[33], 1)

    def test_strict_loader_rejects_duplicate_keys_and_bom(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            duplicate = pathlib.Path(raw) / "duplicate.json"
            duplicate.write_text('{"a":1,"a":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(validate_m05_action_contract.M05ActionContractError, "duplicate"):
                validate_m05_action_contract.load_strict_json(duplicate)
            bom = pathlib.Path(raw) / "bom.json"
            bom.write_bytes(b"\xef\xbb\xbf{}\n")
            with self.assertRaisesRegex(validate_m05_action_contract.M05ActionContractError, "BOM"):
                validate_m05_action_contract.load_strict_json(bom)

    @staticmethod
    def _mask(legal: list[int]) -> dict[str, object]:
        return {
            "schema_version": "openttd-rl-v1-m05-action-mask-1",
            "compatibility_sha256": m05_action_adapter.ACTION_COMPATIBILITY_SHA256,
            "action_count": 41,
            "dtype": "uint8",
            "legal": legal,
            "legal_count": sum(legal),
        }

    @staticmethod
    def _source() -> dict[str, object]:
        return {
            "company": {"balance": 100000, "id": 0},
            "connector": {"axis": 0, "built": False, "start_tile": 1, "end_tile": 2},
            "depot": {"actual_direction": -1, "expected_direction": 1, "present": False, "tile": 2},
            "selection": {"origin_town_slot": -1, "destination_town_slot": -1},
            "stops": [
                {"actual_direction": -1, "expected_direction": 1, "station_id": -1, "tile": 10, "town_slot": 0},
                {"actual_direction": -1, "expected_direction": 0, "station_id": -1, "tile": 20, "town_slot": 1},
            ],
            "town_slots_present": [True, True],
            "vehicles": [
                {"orders": [], "present": False, "running": False, "slot": slot, "tile": -1}
                for slot in range(8)
            ],
        }


if __name__ == "__main__":
    unittest.main()
