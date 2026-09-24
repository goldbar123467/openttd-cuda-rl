"""Mail planning must preserve submitted identities and count real cash costs."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from cargo_live import SCHEMA, mail_planner_view, summarize_mail
from coordinated_cargo import protect_existing_infrastructure, facility_stations


class CargoTests(unittest.TestCase):
    def test_existing_service_sites_are_not_available_to_road_construction(self):
        observation = {"stations": [{"tile": 9, "bus_stop_tiles": [11], "truck_stop_tiles": [15]}], "depots": [{"tile": 13}],
            "map": {"roads": [[11, 5], [12, 10], [13, 2]], "clear_tiles": [14]},
            "candidates": [{"family": "BUILD_ROAD_PATH", "parameters": [2, tile, 5, 1], "key": str(tile)} for tile in [11, 12, 13, 14, 15]]}
        original = copy.deepcopy(observation)
        protected = protect_existing_infrastructure(observation)
        self.assertEqual(observation, original)
        self.assertEqual(protected["map"]["roads"], [[12, 10]])
        self.assertEqual([c["key"] for c in protected["candidates"]], ["12", "14"])

    def test_joined_stop_resolves_to_station_id_instead_of_anchor_tile(self):
        observation = {"capabilities": {"station_facility_tiles": True},
            "stations": [{"id": 7, "tile": 2220, "bus_stop_tiles": [2220], "truck_stop_tiles": [2284, 2285]}]}
        self.assertEqual([(s["tile"], s["id"]) for s in facility_stations(observation, "truck_stop_tiles")], [(2284, 7), (2285, 7)])
        self.assertEqual(observation["stations"][0]["tile"], 2220)
        with self.assertRaisesRegex(ValueError, "facility tile"):
            facility_stations({**observation, "capabilities": {}}, "truck_stop_tiles")

    def test_local_plan_projection_keeps_keys_and_does_not_modify_public_data(self):
        observation = {"schema_version": SCHEMA, "action_schema_id": "v2-development-passenger-mail-action-1",
            "map": {"bus_stop_catchment_radius": 4, "truck_stop_catchment_radius": 3},
            "vehicles": [{"id": 1, "cargo_label": "PASS"}, {"id": 2, "cargo_label": "MAIL"}],
            "candidates": [
                {"key": "bus", "family": "BUILD_BUS_STOP", "parameters": [3, 10, 1, 0]},
                {"key": "mail", "family": "BUILD_TRUCK_STOP", "parameters": [12, 20, 2, 1],
                 "mail_acceptance_eighths": 8, "mail_production": 4, "cost": 23},
                {"key": "truck", "family": "BUY_MAIL_TRUCK", "parameters": [13, 30, 126, 3]}]}
        before = copy.deepcopy(observation)
        view = mail_planner_view(observation)
        self.assertEqual(observation, before)
        self.assertEqual([c["key"] for c in view["candidates"]], ["mail", "truck"])
        self.assertEqual(view["candidates"][0]["parameters"], [12, 20, 2, 0])
        self.assertEqual(view["candidates"][0]["passenger_acceptance_eighths"], 8)
        self.assertEqual(view["map"]["bus_stop_catchment_radius"], 3)
        self.assertEqual(view["vehicles"], [{"id": 2, "cargo_label": "MAIL"}])
        with self.assertRaisesRegex(ValueError, "explicit cargo"):
            mail_planner_view({**observation, "schema_version": "openttd-rl-development-v2-live-1"})

    def test_mail_capital_and_loan_principal_are_separate_from_income(self):
        initial = {"tick": 0, "economy": {"balance": 100000, "loan": 100000,
            "operating_profit": 0, "delivered_mail": 0, "delivered_passengers": 0}}
        after = {"balance": 89300, "loan": 90000, "operating_profit": 300,
                 "delivered_mail": 20, "delivered_passengers": 0}
        action = {"family": "BUY_MAIL_TRUCK", "status": "SUCCESS", "native_commands": [
            {"cost": 900, "phase": "EXECUTE", "status": "SUCCESS"},
            {"cost": 9999, "phase": "TEST", "status": "SUCCESS"}]}
        rows = [{"before": initial["economy"], "after": after, "action": action}]
        summary = summarize_mail(rows, initial, {"tick": 128, "terminal": False, "economy": after})
        self.assertEqual(summary["mail"], 20)
        self.assertEqual(summary["passengers"], 0)
        self.assertEqual(summary["net_capital_spend"], 900)
        self.assertEqual(summary["operating_profit"], 300)
        self.assertEqual(summary["cash_result_excluding_financing"], -700)
        self.assertEqual(summary["cash_result_before_capital"], 200)
        self.assertFalse(summary["sustained_mail_service"])


if __name__ == "__main__":
    unittest.main()
