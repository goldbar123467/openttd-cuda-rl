#!/usr/bin/env python3
"""Contract, identity, mutation, and source tests for the frozen M02 scenario."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import jsonschema

import validate_m02_scenario_contract


class V1M02ScenarioContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract_path = cls.root / "config/v1/m02-scenario-contract.json"
        cls.schema_path = (
            cls.root / "docs/project/schema/v1-m02-scenario-contract.schema.json"
        )
        cls.contract = validate_m02_scenario_contract.validate(
            cls.contract_path,
            cls.schema_path,
        )
        cls.schema = validate_m02_scenario_contract.load_strict_json(cls.schema_path)

    def test_frozen_contract_and_schema_identities_are_exact(self) -> None:
        self.assertEqual(
            self.contract["identity"]["schema_sha256"],
            "26ecec42c314866fcaa83d4ddb0ee38a2084af63fc90e648907cad75bee09543",
        )
        self.assertEqual(
            self.contract["identity"]["compatibility_sha256"],
            "45ec1b3beb4d6d50696bf1de75094e1817c6aa7ef8e0d38fc6696999764e5b0f",
        )
        self.assertEqual(
            validate_m02_scenario_contract.compatibility_sha256(self.contract),
            self.contract["identity"]["compatibility_sha256"],
        )

    def test_every_frozen_decision_family_rejects_mutation(self) -> None:
        mutations = (
            ("engine", "openttd_version", "15.4"),
            ("content", "networking", True),
            ("map", "width", 64),
            ("time", "start_year", 1951),
            ("economy", "inflation", True),
            ("company", "company_count", 2),
            ("towns", "count", 3),
            ("vehicle", "cargo", "mail"),
            ("settings", "difficulty.disasters", True),
            ("episode", "tick_horizon", 65535),
            ("corpus_policy", "procedural_generation", True),
            ("seed_policy", "retry_policy", "retry-until-valid"),
            ("reset_contract", "oracle_mode", "same-process"),
        )
        for section, key, value in mutations:
            with self.subTest(section=section, key=key):
                mutant = copy.deepcopy(self.contract)
                mutant[section][key] = value
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.Draft202012Validator(self.schema).validate(mutant)

    def test_scope_is_passenger_bus_only_and_zero_at_reset(self) -> None:
        scope = self.contract["transport_scope"]
        self.assertEqual(
            scope["agent_reachable"],
            ["bus", "bus-stop", "passenger-service", "road", "road-vehicle-depot"],
        )
        self.assertEqual(scope["starting_owned_infrastructure"], [])
        self.assertEqual(scope["starting_vehicles"], [])
        self.assertTrue(
            {"aircraft", "freight-cargo-service", "rail", "ship", "tram", "truck"}
            <= set(scope["forbidden"])
        )
        self.assertEqual(self.contract["settings"]["vehicle.max_aircraft"], 0)
        self.assertEqual(self.contract["settings"]["vehicle.max_ships"], 0)
        self.assertEqual(self.contract["settings"]["vehicle.max_trains"], 0)

    def test_template_splits_and_reset_projection_are_complete(self) -> None:
        corpus = self.contract["corpus_policy"]
        self.assertEqual(
            corpus["training_templates"]
            + corpus["development_templates"]
            + corpus["final_evaluation_templates"],
            corpus["template_count"],
        )
        required_projection = {
            "companies",
            "compatibility",
            "content",
            "depots",
            "economy",
            "map",
            "orders",
            "pools",
            "rng-streams",
            "roads",
            "scenario",
            "settings",
            "stations",
            "time",
            "towns",
            "vehicles",
        }
        self.assertEqual(
            set(self.contract["reset_contract"]["projection_fields"]),
            required_projection,
        )
        self.assertEqual(self.contract["reset_contract"]["oracle_mode"], "clean-process")

    def test_compatibility_identity_changes_for_semantic_mutation(self) -> None:
        mutant = copy.deepcopy(self.contract)
        mutant["company"]["initial_balance"] += 10000
        self.assertNotEqual(
            validate_m02_scenario_contract.compatibility_sha256(mutant),
            self.contract["identity"]["compatibility_sha256"],
        )

    def test_semantic_guards_reject_split_and_horizon_drift(self) -> None:
        split_mutant = copy.deepcopy(self.contract)
        split_mutant["corpus_policy"]["training_templates"] += 1
        with self.assertRaisesRegex(
            validate_m02_scenario_contract.M02ScenarioContractError,
            "template split count mismatch",
        ):
            validate_m02_scenario_contract.validate_semantics(split_mutant)

        horizon_mutant = copy.deepcopy(self.contract)
        horizon_mutant["episode"]["calendar_day_horizon_ceiling"] = 885
        with self.assertRaisesRegex(
            validate_m02_scenario_contract.M02ScenarioContractError,
            "calendar-day horizon ceiling",
        ):
            validate_m02_scenario_contract.validate_semantics(horizon_mutant)

    def test_strict_loader_rejects_duplicate_keys_and_bom(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            duplicate = pathlib.Path(raw) / "duplicate.json"
            duplicate.write_text('{"a":1,"a":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(
                validate_m02_scenario_contract.M02ScenarioContractError,
                "duplicate JSON key",
            ):
                validate_m02_scenario_contract.load_strict_json(duplicate)
            bom = pathlib.Path(raw) / "bom.json"
            bom.write_bytes(b"\xef\xbb\xbf{}\n")
            with self.assertRaisesRegex(
                validate_m02_scenario_contract.M02ScenarioContractError,
                "UTF-8 BOM",
            ):
                validate_m02_scenario_contract.load_strict_json(bom)

    def test_engine_source_supports_frozen_date_finance_tick_and_bus_values(self) -> None:
        source = self.root / "openttd-upstream/src"
        common_time = (source / "timer/timer_game_common.h").read_text(encoding="utf-8")
        tick_time = (source / "timer/timer_game_tick.h").read_text(encoding="utf-8")
        economy = (source / "economy_type.h").read_text(encoding="utf-8")
        engines = (source / "table/engines.h").read_text(encoding="utf-8")
        self.assertIn("DEF_START_YEAR{1950}", common_time)
        self.assertIn("DAY_TICKS = 74", tick_time)
        self.assertIn("INITIAL_LOAN = 100000", economy)
        self.assertIn("LOAN_INTERVAL = 10000", economy)
        self.assertIn("// 116 MPS Regal Bus", engines)
        self.assertIn("ROV(  0, 120,  91", engines)
        self.assertIn("112, 31,  42,  9), //  0 MPS Regal Bus", engines)


if __name__ == "__main__":
    unittest.main()
