#!/usr/bin/env python3
"""M06 foundation contract, reward math, termination, and integrity tests."""

from __future__ import annotations

import copy
import hashlib
import pathlib
import tempfile
import unittest

import jsonschema

import m06_reward_reference
import validate_m06_reward_contract


class V1M06RewardContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract_path = cls.root / "config/v1/m06-reward-trajectory-contract.json"
        cls.schema_path = cls.root / "docs/project/schema/v1-m06-reward-trajectory-contract.schema.json"
        cls.contract = validate_m06_reward_contract.validate(cls.contract_path, cls.schema_path)
        cls.schema = validate_m06_reward_contract.load_strict_json(cls.schema_path)

    def test_frozen_foundation_schema_and_compatibility_identities_are_exact(self) -> None:
        self.assertEqual(
            self.contract["identity"]["compatibility_sha256"],
            "9d8f9c2fc6074d899fa3b0047c55e3fb15cc5c17cddeaceaa1fd5389e53c8c9e",
        )
        self.assertEqual(
            hashlib.sha256(self.contract_path.read_bytes()).hexdigest(),
            "28712c2b7fcf009e3ceda0ebbc2f18d382f28f780adb52186a08ab871998a2e7",
        )
        self.assertEqual(
            hashlib.sha256(self.schema_path.read_bytes()).hexdigest(),
            "fa6a776fb45649589058f1ea726a6f82b5c3afbb4144edac337383fe6152c2ad",
        )

    def test_all_reward_candidates_are_dispositioned_and_included_components_are_bijective(self) -> None:
        candidates = self.contract["candidate_dispositions"]
        self.assertEqual([item["candidate_id"] for item in candidates[:8]], [f"POS-{number:03d}" for number in range(1, 9)])
        self.assertEqual([item["candidate_id"] for item in candidates[8:]], [f"NEG-{number:03d}" for number in range(1, 11)])
        included = [item["component_id"] for item in candidates if item["disposition"] == "INCLUDED"]
        self.assertEqual(sorted(included), [f"RC-{number:03d}" for number in range(1, 9)])
        self.assertEqual({item["disposition"] for item in candidates}, {"INCLUDED", "DIAGNOSTIC_ONLY", "REJECTED"})

    def test_hand_calculated_reward_vector_and_left_fold_scalar_are_exact(self) -> None:
        raw = {
            "delivered_passengers_delta": 32,
            "operating_profit_delta": 4096,
            "capital_spend": 16384,
            "noop": 1,
            "native_rejected": 1,
            "idle_bus_ticks": 128,
            "vehicle_loss_count": 1,
            "bankruptcy": 0,
        }
        result = m06_reward_reference.compute_reward(raw, self.contract)
        self.assertEqual(result.raw, (32, 4096, 16384, 1, 1, 128, 1, 0))
        self.assertEqual(result.clamped, result.raw)
        self.assertEqual(result.weighted, (2.0, 1.0, -1.0, -0.015625, -0.25, -0.001953125, -2.0, 0.0))
        self.assertEqual(result.scalar, -0.267578125)

    def test_each_component_clamps_before_weighting(self) -> None:
        raw = {
            "delivered_passengers_delta": 999,
            "operating_profit_delta": 999999,
            "capital_spend": 999999,
            "noop": 1,
            "native_rejected": 1,
            "idle_bus_ticks": 9999,
            "vehicle_loss_count": 99,
            "bankruptcy": 1,
        }
        result = m06_reward_reference.compute_reward(raw, self.contract)
        self.assertEqual(result.clamped, (128, 16384, 65536, 1, 1, 1024, 8, 1))
        self.assertEqual(result.weighted, (8.0, 4.0, -4.0, -0.015625, -0.25, -0.015625, -16.0, -8.0))
        self.assertEqual(result.scalar, -16.28125)

    def test_raw_derivation_uses_lifetime_deltas_and_exact_action_results(self) -> None:
        pre = self._state(delivered=100, income=1000, expenses=-200, buses=2, stopped=1)
        post = self._state(delivered=132, income=1500, expenses=-300, buses=1, stopped=1)
        raw = m06_reward_reference.derive_raw(
            pre,
            post,
            {
                "advanced_ticks": 128,
                "native_commands": [{"cost": 100}, {"cost": 0}, {"cost": -50}],
                "status": "SUCCESS",
            },
        )
        self.assertEqual(
            raw,
            {
                "delivered_passengers_delta": 32,
                "operating_profit_delta": 400,
                "capital_spend": 100,
                "noop": 0,
                "native_rejected": 0,
                "idle_bus_ticks": 128,
                "vehicle_loss_count": 1,
                "bankruptcy": 0,
            },
        )
        bankrupt = dict(post)
        bankrupt["company_present"] = False
        self.assertEqual(
            m06_reward_reference.derive_raw(pre, bankrupt, {"advanced_ticks": 128, "native_commands": [], "status": "NATIVE_REJECTED"})["bankruptcy"],
            1,
        )

    def test_raw_derivation_and_component_inputs_fail_closed(self) -> None:
        pre = self._state(delivered=10, income=20, expenses=-5, buses=0, stopped=0)
        regressions = [
            self._state(delivered=9, income=20, expenses=-5, buses=0, stopped=0),
            self._state(delivered=10, income=19, expenses=-5, buses=0, stopped=0),
            self._state(delivered=10, income=20, expenses=-4, buses=0, stopped=0),
        ]
        for post in regressions:
            with self.subTest(post=post):
                with self.assertRaises(m06_reward_reference.M06RewardReferenceError):
                    m06_reward_reference.derive_raw(pre, post, {"advanced_ticks": 128, "native_commands": [], "status": "NO_OP"})
        invalid = {item["raw_field"]: 0 for item in self.contract["reward"]["components"]}
        invalid["noop"] = True
        with self.assertRaisesRegex(m06_reward_reference.M06RewardReferenceError, "never bool"):
            m06_reward_reference.compute_reward(invalid, self.contract)

    def test_all_termination_truncation_incomplete_and_failure_classes_are_typed(self) -> None:
        classify = lambda **values: m06_reward_reference.classify_termination(self.contract, **values)
        self.assertEqual(classify().reason, "NONE")
        bankruptcy = classify(bankruptcy=True, user_cancelled=True, action_horizon=True)
        self.assertEqual((bankruptcy.reason, bankruptcy.terminal, bankruptcy.bootstrap, bankruptcy.trainable), ("BANKRUPTCY", True, False, True))
        self.assertEqual(classify(action_horizon=True).reason, "ACTION_HORIZON")
        self.assertEqual(classify(tick_horizon=True).reason, "TICK_HORIZON")
        combined = classify(action_horizon=True, tick_horizon=True)
        self.assertEqual((combined.reason, combined.truncated, combined.bootstrap), ("ACTION_AND_TICK_HORIZON", True, True))
        cancelled = classify(user_cancelled=True)
        self.assertEqual((cancelled.reason, cancelled.truncated, cancelled.trainable), ("USER_CANCELLED", True, False))
        failure_names = [item["name"] for item in self.contract["termination"]["reasons"] if item["kind"] == "FAILURE"]
        for name in failure_names:
            with self.subTest(name=name):
                failure = classify(failure_reason=name, bankruptcy=True)
                self.assertEqual((failure.reason, failure.kind, failure.trainable, failure.bootstrap), (name, "FAILURE", False, False))
        with self.assertRaisesRegex(m06_reward_reference.M06RewardReferenceError, "disabled"):
            classify(solved=True)
        enabled = copy.deepcopy(self.contract)
        enabled["termination"]["solved_threshold"] = 100
        self.assertEqual(m06_reward_reference.classify_termination(enabled, solved=True).reason, "SOLVED")

    def test_integrity_float_bits_and_shuffle_seed_are_stable(self) -> None:
        self.assertEqual(m06_reward_reference.float64_bits(0.5), "000000000000e03f")
        self.assertEqual(m06_reward_reference.float64_bits(-0.015625), "00000000000090bf")
        record = {"schema_version": "openttd-rl-v1-m06-trajectory-1", "transition_ordinal": 3, "reward": 0.5}
        self.assertEqual(m06_reward_reference.record_sha256(record), "4106969df7881a6c19bd788a48c131c3d02482c078f1a4f0cdab541c08bb932c")
        record["integrity_sha256"] = "0" * 64
        self.assertEqual(m06_reward_reference.record_sha256(record), "4106969df7881a6c19bd788a48c131c3d02482c078f1a4f0cdab541c08bb932c")
        with self.assertRaisesRegex(m06_reward_reference.M06RewardReferenceError, "not finite"):
            m06_reward_reference.record_sha256({"reward": float("nan")})
        self.assertEqual(m06_reward_reference.rollout_shuffle_seed(run_seed=123, rollout_id=7, update_index=9), 15911524011253639047)

    def test_schema_and_semantic_guards_reject_drift(self) -> None:
        shape = copy.deepcopy(self.contract)
        shape["trajectory"]["observation_blob"]["byte_length"] = 132095
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(shape)
        coefficient = copy.deepcopy(self.contract)
        coefficient["reward"]["components"][0]["coefficient_denominator"] = 8
        with self.assertRaisesRegex(validate_m06_reward_contract.M06RewardContractError, "component"):
            validate_m06_reward_contract.validate_semantics(coefficient)
        duplicate = copy.deepcopy(self.contract)
        duplicate["candidate_dispositions"][1]["candidate_id"] = "POS-001"
        with self.assertRaisesRegex(validate_m06_reward_contract.M06RewardContractError, "candidate"):
            validate_m06_reward_contract.validate_semantics(duplicate)

    def test_strict_loader_rejects_duplicate_keys_and_bom(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            duplicate = pathlib.Path(raw) / "duplicate.json"
            duplicate.write_text('{"a":1,"a":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(validate_m06_reward_contract.M06RewardContractError, "duplicate"):
                validate_m06_reward_contract.load_strict_json(duplicate)
            bom = pathlib.Path(raw) / "bom.json"
            bom.write_bytes(b"\xef\xbb\xbf{}\n")
            with self.assertRaisesRegex(validate_m06_reward_contract.M06RewardContractError, "BOM"):
                validate_m06_reward_contract.load_strict_json(bom)

    @staticmethod
    def _state(*, delivered: int, income: int, expenses: int, buses: int, stopped: int) -> dict[str, object]:
        return {
            "company_present": True,
            "delivered_passengers_total": delivered,
            "operating_income_total": income,
            "operating_expenses_total": expenses,
            "primary_bus_count": buses,
            "stopped_primary_bus_count": stopped,
        }


if __name__ == "__main__":
    unittest.main()
