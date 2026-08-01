#!/usr/bin/env python3
"""Contract, identity, mutation, and source tests for the frozen M03 bridge."""

from __future__ import annotations

import copy
import pathlib
import tempfile
import unittest

import jsonschema

import validate_m03_bridge_contract


class V1M03BridgeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract_path = cls.root / "config/v1/m03-bridge-contract.json"
        cls.schema_path = (
            cls.root / "docs/project/schema/v1-m03-bridge-contract.schema.json"
        )
        cls.contract = validate_m03_bridge_contract.validate(
            cls.contract_path,
            cls.schema_path,
        )
        cls.schema = validate_m03_bridge_contract.load_strict_json(cls.schema_path)

    def test_frozen_contract_and_schema_identities_are_exact(self) -> None:
        self.assertEqual(
            self.contract["identity"]["schema_sha256"],
            "199c57a1b55b776f725aaa5d23ad298ef85a2b0bb13837674503ae98f7245dea",
        )
        self.assertEqual(
            self.contract["identity"]["compatibility_sha256"],
            "4701a21ae106f6fa120db1b89c3929d16c29afafb8e0198126173137ed2af2d6",
        )
        self.assertEqual(
            validate_m03_bridge_contract.compatibility_sha256(self.contract),
            self.contract["identity"]["compatibility_sha256"],
        )

    def test_every_contract_family_rejects_mutation(self) -> None:
        mutations = (
            ("transport", "network_listener", True),
            ("framing", "maximum_payload_bytes", 1048577),
            ("handle", "zero_is_invalid", False),
            ("lifecycle", "initial_state", "AT_BOUNDARY"),
            ("request_ordering", "request_id_first", 0),
            ("boundary", "observation_callbacks_may_advance_ticks", True),
            ("scheduler", "v1_reference_action_interval_ticks", 64),
            ("m03_test_actions", "policy_action_registry", True),
            ("snapshot", "is_m04_policy_observation", True),
            ("result_semantics", "engine_command_execution_at_most_once", False),
            ("failure_artifacts", "engine_semantics_use_wall_clock", True),
            ("isolation", "in_process_vectorization", True),
            ("nonperturbation", "observation_only", "may-advance-ticks"),
        )
        for section, key, value in mutations:
            with self.subTest(section=section, key=key):
                mutant = copy.deepcopy(self.contract)
                mutant[section][key] = value
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.Draft202012Validator(self.schema).validate(mutant)

    def test_scheduler_closes_m02_action_and_tick_horizons_exactly(self) -> None:
        scheduler = self.contract["scheduler"]
        self.assertEqual(scheduler["v1_reference_action_interval_ticks"], 128)
        self.assertEqual(
            scheduler["action_horizon"]
            * scheduler["v1_reference_action_interval_ticks"],
            scheduler["tick_horizon"],
        )
        self.assertEqual(
            scheduler["simultaneous_horizon_priority"],
            ["action-horizon", "tick-horizon"],
        )

    def test_bridge_actions_are_explicitly_not_m05_policy_actions(self) -> None:
        actions = self.contract["m03_test_actions"]
        self.assertFalse(actions["policy_action_registry"])
        self.assertEqual(
            [(item["id"], item["name"]) for item in actions["actions"]],
            [(0, "WAIT"), (1, "M02_SCRIPTED_BUS_SETUP")],
        )
        self.assertIn("not-policy-actions", actions["namespace"])

    def test_transport_is_local_framed_and_one_environment_per_process(self) -> None:
        transport = self.contract["transport"]
        self.assertEqual(transport["control_channel"], "inherited-anonymous-byte-streams")
        self.assertFalse(transport["network_listener"])
        self.assertEqual(transport["environments_per_worker_process"], 1)
        self.assertEqual(self.contract["framing"]["header_bytes"], 56)
        self.assertEqual(self.contract["framing"]["magic_ascii"], "ORL1")

    def test_snapshot_and_queries_are_nonperturbing_by_contract(self) -> None:
        boundary = self.contract["boundary"]
        self.assertFalse(boundary["observation_callbacks_may_advance_ticks"])
        self.assertFalse(boundary["observation_callbacks_may_consume_rng"])
        self.assertFalse(boundary["observation_callbacks_may_execute_commands"])
        self.assertFalse(self.contract["snapshot"]["is_m04_policy_observation"])

    def test_semantic_guards_reject_cross_field_drift(self) -> None:
        horizon_mutant = copy.deepcopy(self.contract)
        horizon_mutant["scheduler"]["tick_horizon"] -= 1
        with self.assertRaisesRegex(
            validate_m03_bridge_contract.M03BridgeContractError,
            "action horizon times reference interval",
        ):
            validate_m03_bridge_contract.validate_semantics(horizon_mutant)

        message_mutant = copy.deepcopy(self.contract)
        message_mutant["operations"]["close"]["message_type"] = 6
        with self.assertRaisesRegex(
            validate_m03_bridge_contract.M03BridgeContractError,
            "unique range 1..7",
        ):
            validate_m03_bridge_contract.validate_semantics(message_mutant)

    def test_strict_loader_rejects_duplicate_keys_and_bom(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            duplicate = pathlib.Path(raw) / "duplicate.json"
            duplicate.write_text('{"a":1,"a":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(
                validate_m03_bridge_contract.M03BridgeContractError,
                "duplicate JSON key",
            ):
                validate_m03_bridge_contract.load_strict_json(duplicate)
            bom = pathlib.Path(raw) / "bom.json"
            bom.write_bytes(b"\xef\xbb\xbf{}\n")
            with self.assertRaisesRegex(
                validate_m03_bridge_contract.M03BridgeContractError,
                "UTF-8 BOM",
            ):
                validate_m03_bridge_contract.load_strict_json(bom)

    def test_pinned_source_has_safe_tick_boundary_and_normal_command_path(self) -> None:
        source = self.root / "openttd-upstream/src"
        openttd = (source / "openttd.cpp").read_text(encoding="utf-8")
        command = (source / "command_func.h").read_text(encoding="utf-8")
        self.assertIn("void StateGameLoop()", openttd)
        self.assertIn("to be called from the StateGameLoop", command)


if __name__ == "__main__":
    unittest.main()
