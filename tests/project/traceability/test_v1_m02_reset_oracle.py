#!/usr/bin/env python3
"""Native M02 reset projection, mutation, patch, and oracle-runner tests."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import tempfile
import unittest

import generate_m02_scenario
import prepare_openttd_source
import run_m02_map_feasibility
import run_m02_reset_oracle
import validate_m02_reset_projection
import validate_m02_scenario_contract
import validate_m02_scripted_trajectory


class V1M02ResetOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract, cls.corpus, cls.ledger = generate_m02_scenario.load_and_validate(
            cls.root / "config/v1/m02-scenario-contract.json",
            cls.root / "docs/project/schema/v1-m02-scenario-contract.schema.json",
            cls.root / "config/v1/m02-scenario-corpus.json",
            cls.root / "docs/project/schema/v1-m02-scenario-corpus.schema.json",
            cls.root / "config/v1/m02-seed-ledger.json",
            cls.root / "docs/project/schema/v1-m02-seed-ledger.schema.json",
        )
        cls.instance = generate_m02_scenario.build_instance(
            cls.contract,
            cls.corpus,
            cls.ledger,
            cls.corpus["templates"][0],
            cls.root / "docs/project/schema/v1-m02-scenario-instance.schema.json",
        )
        cls.schema = validate_m02_scenario_contract.load_strict_json(
            cls.root / "docs/project/schema/v1-m02-reset-projection.schema.json"
        )
        cls.trajectory_schema = validate_m02_scenario_contract.load_strict_json(
            cls.root / "docs/project/schema/v1-m02-scripted-bus-trajectory.schema.json"
        )

    def valid_report(self) -> dict[str, object]:
        template = self.instance["template"]
        route = generate_m02_scenario.route_tiles(template["road_waypoints"])
        house_points = {(template["towns"][0]["x"], template["towns"][0]["y"]), (template["towns"][1]["x"], template["towns"][1]["y"])}
        route_points = set(route)
        tiles: list[dict[str, object]] = []
        counts = [0] * 11
        for index in range(1024):
            x, y = index % 32, index // 32
            if x in (0, 31) or y in (0, 31):
                tile_type = 7
            elif (x, y) in route_points:
                tile_type = 2
            elif (x, y) in house_points:
                tile_type = 3
            else:
                tile_type = 0
            counts[tile_type] += 1
            tiles.append({"index": index, "raw": [tile_type << 4, 1, 0, 0, 0, 0, 0, 0, 0, 0], "x": x, "y": y})
        roads = [
            {
                "bits": 1,
                "index": y * 32 + x,
                "owner": 15,
                "road_type": 0,
                "town_id": 0,
                "x": x,
                "y": y,
            }
            for x, y in route
        ]
        stops = [
            {**stop, "passenger_source_tiles_in_catchment": 1}
            for stop in template["bus_stops"]
        ]
        depot = copy.deepcopy(template["road_depot"])
        offsets = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
        dx, dy = offsets[depot["entrance"]]
        depot.update({"front_x": depot["x"] + dx, "front_y": depot["y"] + dy})
        projection = {
            "companies": [
                {
                    "id": 0,
                    "is_ai": False,
                    "loan": 100000,
                    "max_loan": 300000,
                    "money": 100000,
                    "owned_airport": 0,
                    "owned_rail": 0,
                    "owned_road": 0,
                    "owned_station": 0,
                    "owned_tram": 0,
                    "owned_water": 0,
                }
            ],
            "compatibility": {
                "contract_sha256": self.instance["contract_compatibility_sha256"],
                "corpus_sha256": self.instance["corpus_sha256"],
                "ledger_sha256": self.instance["seed_ledger_sha256"],
            },
            "content": {
                "ai_company_count": 0,
                "base_graphics_metadata_version": [9499],
                "base_graphics_name": "OpenGFX",
                "game_script": None,
                "multiplayer": False,
                "networking": False,
                "newgrf_count": 0,
            },
            "depots": [],
            "economy": {
                "inflation_payment": 65536,
                "inflation_prices": 65536,
                "interest_rate": 2,
                "maximum_loan": 300000,
            },
            "map": {"height": 32, "terrain_height": 1, "tile_type_counts": counts, "tiles": tiles, "width": 32},
            "orders": [],
            "pools": {
                "cargo_packets": 0,
                "companies": 1,
                "depots": 0,
                "groups": 0,
                "industries": 0,
                "objects": 0,
                "order_lists": 0,
                "signs": 0,
                "stations": 0,
                "subsidies": 0,
                "towns": 2,
                "vehicles": 0,
            },
            "rng-streams": {"interactive": [1, 1], "simulation": [2, 3]},
            "roads": roads,
            "scenario": {
                "planned_construction": {"bus_stops": stops, "road_depot": depot, "road_path_length": len(route) - 1},
                "scenario_sha256": self.instance["identity"]["scenario_sha256"],
                "seed": self.instance["seed"],
                "split": self.instance["split"],
                "template_id": self.instance["template_id"],
            },
            "settings": self.contract["settings"],
            "stations": [],
            "time": {
                "calendar_date": 712223,
                "calendar_date_fraction": 0,
                "calendar_month": 0,
                "calendar_year": 1950,
                "economy_date": 712223,
                "economy_date_fraction": 0,
                "economy_month": 0,
                "economy_year": 1950,
                "tick": 0,
                "ticks_per_day": 74,
            },
            "towns": [
                {
                    "growth_enabled": False,
                    "growth_rate": 65535,
                    "house_tiles": 1,
                    "id": town["town_id"],
                    "layout": 0,
                    "name": town["name"],
                    "passenger_source_tiles": 1,
                    "population": 250,
                    "x": town["x"],
                    "y": town["y"],
                }
                for town in template["towns"]
            ],
            "vehicles": [],
        }
        return {
            "projection": projection,
            "same_process_byte_identical": True,
            "same_process_repetitions": 2,
            "schema_version": "openttd-rl-v1-m02-reset-projection-1",
            "status": "PASS",
        }

    def valid_trajectory(self) -> dict[str, object]:
        labels = [
            "build-bus-stop-0",
            "build-bus-stop-1",
            "connect-road-depot",
            "build-road-depot",
            "build-mps-regal-bus",
            "insert-station-order-0",
            "insert-station-order-1",
            "start-bus",
        ]
        costs = [100, 100, 10, 100, 1000, 0, 0, 0]
        balance = 100000
        actions = []
        for label, cost in zip(labels, costs):
            balance -= cost
            actions.append({"action": label, "balance_after": balance, "cost": cost})
        stops = self.instance["template"]["bus_stops"]
        return {
            "schema_version": "openttd-rl-v1-m02-scripted-bus-trajectory-1",
            "status": "PASS",
            "trajectory": {
                "actions": actions,
                "company": {
                    "balance": balance + 5,
                    "delivered_passengers": 1,
                    "expenses": -5,
                    "id": 0,
                    "income": 10,
                },
                "facilities": {"depot_count": 1, "station_count": 2},
                "forbidden": {
                    "airports": 0,
                    "industries": 0,
                    "rail": 0,
                    "ships": 0,
                    "trams": 0,
                    "trucks": 0,
                },
                "orders": [
                    {"destination_station_id": 0, "type": "go-to-station"},
                    {"destination_station_id": 1, "type": "go-to-station"},
                ],
                "scenario": {
                    "scenario_sha256": self.instance["identity"]["scenario_sha256"],
                    "seed": self.instance["seed"],
                    "template_id": self.instance["template_id"],
                },
                "stations": [
                    {
                        "ever_accepted_passengers": index == 1,
                        "id": index,
                        "owner": 0,
                        "tile": stop["y"] * 32 + stop["x"],
                        "waiting_passengers": 0,
                    }
                    for index, stop in enumerate(stops)
                ],
                "ticks": {"executed": 1000, "final": 1000, "limit": 65536},
                "vehicle": {
                    "capacity": 31,
                    "cargo": "passengers",
                    "cargo_stored": 0,
                    "engine_id": 116,
                    "id": 0,
                    "profit_this_year": 10,
                    "running": True,
                    "type": "bus",
                },
            },
        }

    def test_valid_projection_passes_schema_and_complete_semantics(self) -> None:
        report = self.valid_report()
        validate_m02_reset_projection.validate_schema(report, self.schema)
        digest = validate_m02_reset_projection.validate_report_semantics(
            report, self.instance, self.contract
        )
        self.assertEqual(len(digest), 64)
        self.assertEqual(
            digest,
            hashlib.sha256(
                validate_m02_reset_projection.canonical_bytes(report["projection"])
            ).hexdigest(),
        )

    def test_forbidden_scope_mutations_fail_closed(self) -> None:
        mutations = {
            "networking": lambda value: value["projection"]["content"].update(networking=True),
            "company-owned-rail": lambda value: value["projection"]["companies"][0].update(owned_rail=1),
            "vehicle": lambda value: value["projection"]["vehicles"].append({"id": 0}),
            "station": lambda value: value["projection"]["stations"].append({"id": 0}),
            "depot": lambda value: value["projection"]["depots"].append({"id": 0}),
            "order": lambda value: value["projection"]["orders"].append({"id": 0}),
            "industry-pool": lambda value: value["projection"]["pools"].update(industries=1),
            "newgrf": lambda value: value["projection"]["content"].update(newgrf_count=1),
            "gamescript": lambda value: value["projection"]["content"].update(game_script="script"),
            "tram": lambda value: value["projection"]["companies"][0].update(owned_tram=1),
            "aircraft": lambda value: value["projection"]["companies"][0].update(owned_airport=1),
            "water": lambda value: value["projection"]["companies"][0].update(owned_water=1),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                report = copy.deepcopy(self.valid_report())
                mutate(report)
                with self.assertRaises(validate_m02_reset_projection.M02ResetProjectionError):
                    validate_m02_reset_projection.validate_report_semantics(
                        report, self.instance, self.contract
                    )

    def test_forbidden_map_types_are_rejected_even_when_counts_match(self) -> None:
        for tile_type in (1, 5, 6, 8, 9, 10):
            with self.subTest(tile_type=tile_type):
                report = self.valid_report()
                tile = report["projection"]["map"]["tiles"][33]
                previous = tile["raw"][0] >> 4
                tile["raw"][0] = tile_type << 4
                report["projection"]["map"]["tile_type_counts"][previous] -= 1
                report["projection"]["map"]["tile_type_counts"][tile_type] += 1
                with self.assertRaisesRegex(
                    validate_m02_reset_projection.M02ResetProjectionError,
                    "forbidden tile type",
                ):
                    validate_m02_reset_projection.validate_report_semantics(
                        report, self.instance, self.contract
                    )

    def test_scripted_trajectory_schema_and_semantics_pass(self) -> None:
        report = self.valid_trajectory()
        validate_m02_reset_projection.validate_schema(report, self.trajectory_schema)
        digest = validate_m02_scripted_trajectory.validate_semantics(
            report, self.instance
        )
        self.assertEqual(
            digest,
            hashlib.sha256(
                validate_m02_reset_projection.canonical_bytes(report) + b"\n"
            ).hexdigest(),
        )

    def test_scripted_trajectory_mutations_fail_closed(self) -> None:
        mutations = {
            "no-delivery": lambda value: value["trajectory"]["company"].update(delivered_passengers=0),
            "no-income": lambda value: value["trajectory"]["company"].update(income=0),
            "rail": lambda value: value["trajectory"]["forbidden"].update(rail=1),
            "tram": lambda value: value["trajectory"]["forbidden"].update(trams=1),
            "truck": lambda value: value["trajectory"]["forbidden"].update(trucks=1),
            "wrong-engine": lambda value: value["trajectory"]["vehicle"].update(engine_id=117),
            "mail": lambda value: value["trajectory"]["vehicle"].update(cargo="mail"),
            "stopped": lambda value: value["trajectory"]["vehicle"].update(running=False),
            "tick-overrun": lambda value: value["trajectory"]["ticks"].update(executed=65537, final=65537),
            "wrong-order": lambda value: value["trajectory"]["orders"][0].update(destination_station_id=1),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                report = copy.deepcopy(self.valid_trajectory())
                mutate(report)
                with self.assertRaises(
                    validate_m02_scripted_trajectory.M02ScriptedTrajectoryError
                ):
                    validate_m02_scripted_trajectory.validate_semantics(
                        report, self.instance
                    )

    def test_encoding_loader_rejects_duplicate_bom_and_pretty_json(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temporary = pathlib.Path(raw)
            duplicate = temporary / "duplicate.json"
            duplicate.write_bytes(b'{"a":1,"a":2}\n')
            with self.assertRaisesRegex(validate_m02_reset_projection.M02ResetProjectionError, "duplicate JSON key"):
                validate_m02_reset_projection.load_canonical_json(duplicate)
            bom = temporary / "bom.json"
            bom.write_bytes(b"\xef\xbb\xbf{}\n")
            with self.assertRaisesRegex(validate_m02_reset_projection.M02ResetProjectionError, "BOM"):
                validate_m02_reset_projection.load_canonical_json(bom)
            pretty = temporary / "pretty.json"
            pretty.write_text("{\n  \"a\": 1\n}\n", encoding="utf-8")
            with self.assertRaisesRegex(validate_m02_reset_projection.M02ResetProjectionError, "not canonical"):
                validate_m02_reset_projection.load_canonical_json(pretty)

    def test_oracle_config_pins_every_input_and_expected_projection(self) -> None:
        oracle = validate_m02_scenario_contract.load_strict_json(
            self.root / "config/v1/m02-reset-oracle.json"
        )
        expected = run_m02_reset_oracle.validate_oracle_config(self.root, oracle)
        self.assertEqual(list(expected), [f"m02-template-{number:02d}" for number in range(1, 9)])
        self.assertEqual(
            len({item["projection_sha256"] for item in expected.values()}), 8
        )

    def test_native_delta_applies_exactly_after_accepted_feasibility_tree(self) -> None:
        plan = validate_m02_scenario_contract.load_strict_json(
            self.root / "config/v1/m02-map-feasibility-plan.json"
        )
        oracle = validate_m02_scenario_contract.load_strict_json(
            self.root / "config/v1/m02-reset-oracle.json"
        )
        with tempfile.TemporaryDirectory() as raw:
            temporary = pathlib.Path(raw)
            source = temporary / "source"
            base = prepare_openttd_source.prepare(
                root=self.root,
                profile_path=self.root / plan["source"]["base_profile_path"],
                profile_schema_path=self.root / "docs/project/schema/v1-source-profile.schema.json",
                manifest_schema_path=self.root / "docs/project/schema/v1-prepared-source-manifest.schema.json",
                object_repository_override=self.root / "openttd-upstream",
                output=source,
                manifest_path=temporary / "base-manifest.json",
            )
            _, feasibility_patches, _ = run_m02_map_feasibility.validate_delta_series(
                self.root, plan["source"]
            )
            prepare_openttd_source.apply_patches(
                source, feasibility_patches, run_m02_map_feasibility.SOURCE_TREE
            )
            self.assertEqual(prepare_openttd_source.git(source, "write-tree"), plan["source"]["result_tree"])
            native_patch = self.root / oracle["native_delta"]["patches"][0]["path"]
            prepare_openttd_source.apply_patches(
                source, [native_patch], plan["source"]["result_tree"]
            )
            self.assertEqual(
                prepare_openttd_source.git(source, "write-tree"),
                oracle["native_delta"]["result_tree"],
            )
            self.assertEqual(base["preparation_identity_sha256"], plan["source"]["base_preparation_identity_sha256"])

    def test_native_patch_stays_before_rl_bridge_and_training_scope(self) -> None:
        oracle = validate_m02_scenario_contract.load_strict_json(
            self.root / "config/v1/m02-reset-oracle.json"
        )
        text = (self.root / oracle["native_delta"]["patches"][0]["path"]).read_text(
            encoding="utf-8"
        )
        self.assertIn("M02_SCENARIO_RESET=PASS", text)
        self.assertIn("OPTION_RL_ENVIRONMENT", text)
        for forbidden in ("PPO", "LibTorch", "ONNX Runtime", "rl_bridge", "policy inference"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
