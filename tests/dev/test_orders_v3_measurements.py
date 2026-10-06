import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from audit_orders_v3 import public_context
from benchmark_orders_v3 import first_route_from_journal, grouped


class V3MeasurementsTests(unittest.TestCase):
    def test_duplicate_neighbor_and_each_assigned_bus_counted_once(self):
        state = {"vehicles": [{"id": 2, "stopped": True, "orders": [{"destination": 0}, {"destination": 1}, {"destination": 0}]},
                              {"id": 4, "stopped": False, "orders": [{"destination": 0}]}],
                 "stations": [{"id": 0, "waiting_passengers": 425}, {"id": 1, "waiting_passengers": 0}]}
        adjacent = public_context(state, [6, 2, 1 | (0x61 << 16), 0])
        nonadjacent = public_context(state, [6, 2, 1 | (0x61 << 16), 1])
        self.assertEqual(adjacent[:4], [1, 1, .75, 1])
        self.assertEqual(nonadjacent[:4], [1, 0, .75, 1])
        self.assertAlmostEqual(adjacent[4], .15847394430497144)
        self.assertGreater(adjacent[5], nonadjacent[5])

    def test_first_departure_uses_first_purchased_bus_and_never_starting_is_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "journal.jsonl"
            bus = {"id": 2, "stopped": True, "orders": [{"destination": 0, "load_mode": 3}, {"destination": 1, "load_mode": 3}]}
            state = lambda buses: json.dumps({"kind": "response", "response": {"observation": {"vehicles": buses}}})
            path.write_text(state([]) + "\n" + state([bus]) + "\n")
            self.assertEqual(first_route_from_journal(path), {"vehicle_id": 2, "started": False, "valid": False})
            bus["stopped"] = False
            with path.open("a") as stream:
                stream.write(state([bus]) + "\n")
            self.assertTrue(first_route_from_journal(path)["valid"])
            bus["orders"][1]["destination"] = 0
            path.write_text(state([bus]) + "\n")
            self.assertFalse(first_route_from_journal(path)["valid"])

    def test_interface_termination_stays_in_summary_denominator(self):
        item = {"case": {"mode": "greedy"}, "outcome": "terminated-interface", "first_route": {"started": False, "valid": False},
                "summary": {"decisions": 100, "operating_profit": -5, "passengers": 0}}
        result = grouped([item])["greedy"]
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["interface_terminations"], 1)
        self.assertEqual(result["mean_operating_profit"], -5)


if __name__ == "__main__":
    unittest.main()
