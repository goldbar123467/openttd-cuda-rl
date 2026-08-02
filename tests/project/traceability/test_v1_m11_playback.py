#!/usr/bin/env python3
"""M11 frozen playback, controller, inspection, control, and dependency guards."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import jsonschema

import validate_m11_playback_contract


class V1M11PlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract_path = cls.root / "config/v1/m11-playback-contract.json"
        cls.schema_path = cls.root / "docs/project/schema/v1-m11-playback-contract.schema.json"
        cls.config_schema_path = cls.root / "docs/project/schema/v1-m11-playback-config.schema.json"

    def test_contract_is_frozen_and_self_consistent(self) -> None:
        contract = validate_m11_playback_contract.validate(self.contract_path, self.schema_path)
        self.assertEqual(contract["identity"]["compatibility_sha256"], validate_m11_playback_contract.EXPECTED_COMPATIBILITY)
        self.assertEqual(contract["accepted_package"]["package_id"], validate_m11_playback_contract.ACCEPTED_PACKAGE_ID)
        self.assertEqual(len(contract["requirements"]), 14)

    def test_contract_mutations_fail_closed(self) -> None:
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        mutations = []
        value = copy.deepcopy(contract)
        value["status"] = "DRAFT"
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["accepted_package"]["package_id"] = "0" * 64
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["controller"]["interval"]["minimum_ticks"] = 1
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["requirements"].pop()
        mutations.append(value)
        for mutation in mutations:
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(schema).validate(mutation)

    def test_playback_configuration_modes_intervals_and_paths_are_strict(self) -> None:
        contract = validate_m11_playback_contract.validate(self.contract_path, self.schema_path)
        base = {
            "schema_version": "openttd-rl-v1-m11-playback-config-1",
            "contract_sha256": validate_m11_playback_contract.EXPECTED_COMPATIBILITY,
            "package_path": "/tmp/" + validate_m11_playback_contract.ACCEPTED_PACKAGE_ID,
            "scenario_instance": "/tmp/scenario.json",
            "inference": {"mode": "greedy", "sampling_seed": 2026110101, "interval_ticks": 128},
            "logging": {"actions": True, "path": "/tmp/actions.jsonl", "maximum_records": 64},
            "inspection": {"window": True, "debug_overlay": True, "report_path": "/tmp/inspection.json"},
            "controls": {"start_agent_paused": False, "native_pause_button": True, "agent_step_button": True},
            "acceptance": {"maximum_actions": 12, "exit_when_complete": True},
        }
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "config.json"
            for mode in ("greedy", "seeded-stochastic"):
                for interval in range(128, 1025, 128):
                    value = copy.deepcopy(base)
                    value["inference"]["mode"] = mode
                    value["inference"]["interval_ticks"] = interval
                    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
                    validate_m11_playback_contract.validate_playback_config(path, self.config_schema_path, contract)
            for interval in (0, 127, 129, 1152):
                value = copy.deepcopy(base)
                value["inference"]["interval_ticks"] = interval
                path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
                with self.assertRaises(jsonschema.ValidationError):
                    validate_m11_playback_contract.validate_playback_config(path, self.config_schema_path, contract)

    def test_controller_source_and_gate_boundaries_are_present(self) -> None:
        patch = self.root / "integration/openttd/patches/15.3/m11/0009-normal-game-neural-agent.patch"
        if not patch.is_file():
            self.skipTest("M11 implementation delta is added after contract preregistration")
        source = patch.read_text(encoding="utf-8")
        for symbol in ("EncodeRlObservation", "BuildRlActionMask", "ExecuteRlAction", "InGamePolicyAdapter"):
            self.assertIn(symbol, source)
        for field in ("current_action", "confidence", "value", "legal_action_count", "reward_relevant_state", "route_target", "model_name", "model_version"):
            self.assertIn(field, source)
        self.assertIn("-A <playback-config>", source)
        gate = (self.root / "scripts/v1/run_m11_playback_gate.py").read_text(encoding="utf-8")
        self.assertIn("LibTorch", gate)
        self.assertIn("golden.jsonl", gate)
        self.assertIn("missing-package", gate)


if __name__ == "__main__":
    unittest.main()
