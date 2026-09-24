import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from repair_v2 import connection


class RepairTests(unittest.TestCase):
    def observation(self):
        # Two stops at 6 and 10, originally connected along row one.
        return {"map": {"width": 6, "height": 4, "roads": [[6, 2], [7, 10], [8, 10], [9, 10], [10, 8]],
                        "flat_tiles": list(range(24))}, "candidates": []}

    def test_existing_connection_needs_no_spending(self):
        result = connection(self.observation(), 6, 10)
        self.assertEqual(result["line"], [6, 7, 8, 9, 10])
        self.assertEqual(result["actions"], [])

    def test_opponent_depot_breaks_through_road_and_detour_uses_candidates(self):
        observation = self.observation()
        observation["map"]["roads"][2][1] = 8
        self.assertIsNone(connection(observation, 6, 10))
        allowed = [(7, 5), (13, 5), (13, 10), (14, 10), (15, 10), (15, 5), (9, 5)]
        observation["candidates"] = [{"family": "BUILD_ROAD_PATH", "parameters": [1, tile, axis, 1], "cost": 100}
                                     for tile, axis in allowed]
        result = connection(observation, 6, 10, allow_construction=True)
        self.assertIsNotNone(result)
        self.assertNotIn(8, result["line"])
        self.assertEqual(result["estimated_construction_cost"], 700)
        self.assertEqual({tuple(action[1][:2]) for action in result["actions"]}, set(allowed))
        observation["map"]["flat_tiles"].remove(13)
        self.assertIsNone(connection(observation, 6, 10, allow_construction=True))

    def test_map_edges_do_not_wrap(self):
        observation = self.observation()
        observation["map"]["roads"] = [[5, 2], [6, 8]]
        self.assertIsNone(connection(observation, 5, 6))


if __name__ == "__main__":
    unittest.main()
