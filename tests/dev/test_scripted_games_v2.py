"""Route enumeration, the scripted route player and database game selection."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from game_database_v2 import GRIDS, SCHEMA, game_id
from route_atlas_v2 import enumerate_routes, nearest_town
from route_player_v2 import ConstructionBlocked, RoutePlayer, check_strategy, strategy_id
from scripted_imitation_v2 import labelled, scripted_reference, select_games

WIDTH, HEIGHT = 24, 8


def tile(x, y):
    return y * WIDTH + x


def candidate(family, *parameters, cost=100, **extra):
    index = ("WAIT", "SELECT_TOWN_PAIR", "BUILD_ROAD_PATH", "BUILD_BUS_STOP", "BUILD_ROAD_DEPOT", "BUY_BUS",
             "SET_ROUTE", "START_VEHICLE", "STOP_VEHICLE", "SEND_TO_DEPOT", "SELL_VEHICLE", "MANAGE_LOAN").index(family)
    params = [index, *parameters] + [0] * (15 - len(parameters))
    return {"key": f"{family}:{parameters}", "family": family, "family_index": index, "parameters": params,
            "cost": cost, **extra}


def two_town_map():
    """Two towns at either end of a flat buildable corridor on row 4."""
    corridor = [tile(x, 4) for x in range(1, 23)]
    houses = [tile(2, 6), tile(3, 6), tile(21, 6), tile(22, 6)]
    stops = [tile(2, 5), tile(21, 5)]
    candidates = [candidate("WAIT", cost=0)]
    candidates += [candidate("BUILD_ROAD_PATH", road, axis, 1) for road in corridor for axis in (5, 10)]
    candidates += [candidate("BUILD_BUS_STOP", stop, 3, 0, passenger_acceptance_eighths=8, passenger_production=4)
                   for stop in stops]
    candidates.append(candidate("BUILD_ROAD_DEPOT", tile(10, 5), 3, 0))
    candidates += [candidate("SELECT_TOWN_PAIR", 0, 1, 0), candidate("SELECT_TOWN_PAIR", 1, 0, 0)]
    candidates += [candidate("MANAGE_LOAN", 1, 10000, 0, cost=0), candidate("MANAGE_LOAN", 2, 10000, 0, cost=0)]
    occupied = set(houses)
    return {"token": "t0", "tick": 0, "economy": {"balance": 100000, "loan": 100000},
            "map": {"width": WIDTH, "height": HEIGHT, "roads": [], "houses": houses,
                    "clear_tiles": [t for t in range(WIDTH * HEIGHT) if t not in occupied],
                    "flat_tiles": list(range(WIDTH * HEIGHT)), "bus_stop_catchment_radius": 3},
            "towns": [{"id": 0, "tile": tile(3, 4), "x": 3, "y": 4, "population": 900},
                      {"id": 1, "tile": tile(20, 4), "x": 20, "y": 4, "population": 700}],
            "stations": [], "depots": [], "vehicles": [], "candidates": candidates}


STRATEGY = {"buses": 1, "max_buses": 2, "queue_threshold": 60, "load": "both", "repay_reserve": 20000}


class RouteAtlasTests(unittest.TestCase):
    def test_inter_town_route_uses_only_exposed_primitives_in_build_order(self):
        observation = two_town_map()
        routes, report = enumerate_routes(observation)
        self.assertEqual(len(routes), 1)
        route = routes[0]
        self.assertEqual((route["kind"], route["town_pair"]), ("inter-town", [0, 1]))
        self.assertEqual(route["line"][0], tile(2, 5))
        self.assertEqual(route["line"][-1], tile(21, 5))
        self.assertEqual(route["path_tiles"], 22)
        exposed = {(c["family"], tuple(c["parameters"][1:4])) for c in observation["candidates"]}
        self.assertTrue(all((family, tuple(params)) in exposed for family, params in route["actions"]))
        self.assertEqual([family for family, _ in route["actions"][:3]], ["BUILD_ROAD_DEPOT", "BUILD_BUS_STOP", "BUILD_BUS_STOP"])
        self.assertEqual(report["towns_without_exposed_stops"], [])
        self.assertEqual(enumerate_routes(two_town_map())[0][0]["route_id"], route["route_id"])

    def test_unexposed_road_leaves_no_route(self):
        observation = two_town_map()
        gap = tile(12, 4)
        observation["candidates"] = [c for c in observation["candidates"]
                                     if not (c["family"] == "BUILD_ROAD_PATH" and c["parameters"][1] == gap)]
        routes, report = enumerate_routes(observation)
        self.assertEqual(routes, [])
        self.assertEqual(report["connectable_pairs"], 0)

    def test_stops_without_full_acceptance_are_not_sites(self):
        observation = two_town_map()
        for row in observation["candidates"]:
            if row["family"] == "BUILD_BUS_STOP":
                row["passenger_acceptance_eighths"] = 7
        self.assertEqual(enumerate_routes(observation)[1]["stop_sites"], 0)

    def test_nearest_town_breaks_ties_by_identity(self):
        towns = [{"id": 1, "x": 0, "y": 0}, {"id": 0, "x": 2, "y": 0}]
        self.assertEqual(nearest_town(1, 10, towns), 0)


class RoutePlayerTests(unittest.TestCase):
    def setUp(self):
        self.observation = two_town_map()
        self.route = enumerate_routes(self.observation)[0][0]

    def operating(self, **bus):
        state = two_town_map()
        state["stations"] = [{"id": 7, "tile": tile(2, 5), "waiting_passengers": 0},
                             {"id": 8, "tile": tile(21, 5), "waiting_passengers": 0}]
        state["depots"] = [{"id": 0, "tile": tile(10, 5)}]
        state["candidates"].append(candidate("BUY_BUS", tile(10, 5), 0, 0, cost=4000))
        if bus:
            vehicle = {"id": 3, "stopped": True, "orders": [], **bus}
            state["vehicles"] = [vehicle]
            for index in range(3):
                for station in (7, 8):
                    state["candidates"].append(candidate("SET_ROUTE", 3, 1 | index << 8 | 0x61 << 16, station))
                for mode in (0, 3):
                    state["candidates"].append(candidate("SET_ROUTE", 3, 2 | index << 8 | 3 << 16, mode))
            state["candidates"].append(candidate("START_VEHICLE", 3, 0, 0))
        return state

    def test_builds_depot_then_stops_then_roads(self):
        player = RoutePlayer(self.route, STRATEGY)
        chosen = []
        for _ in range(len(self.route["actions"])):
            selected, phase = player.choose(self.observation)
            self.assertEqual(phase, "build")
            chosen.append(selected["family"])
        self.assertEqual(chosen[:3], ["BUILD_ROAD_DEPOT", "BUILD_BUS_STOP", "BUILD_BUS_STOP"])
        self.assertEqual(set(chosen[3:]), {"BUILD_ROAD_PATH"})
        self.assertFalse(player.remaining)

    def test_construction_blocks_after_limit(self):
        player = RoutePlayer(self.route, STRATEGY, blocked_limit=2)
        empty = {**self.observation, "candidates": [candidate("WAIT", cost=0)]}
        self.assertEqual(player.choose(empty)[1], "blocked-wait")
        self.assertEqual(player.choose(empty)[1], "blocked-wait")
        with self.assertRaises(ConstructionBlocked):
            player.choose(empty)

    def test_roads_a_town_already_built_are_dropped_from_the_plan(self):
        player = RoutePlayer(self.route, STRATEGY, blocked_limit=0)
        roads = {}
        for family, params in self.route["actions"]:
            if family == "BUILD_ROAD_PATH":
                roads[params[0]] = roads.get(params[0], 0) | params[1]
        state = two_town_map()
        state["map"]["roads"] = [[road, bits] for road, bits in roads.items()]
        state["candidates"] = [c for c in state["candidates"] if c["family"] != "BUILD_ROAD_PATH"]
        phases = [player.choose(state)[1] for _ in range(3)]
        self.assertEqual(phases, ["build"] * 3)
        self.assertEqual(player.remaining, [])

    def test_buys_orders_loads_starts_then_repays(self):
        player = RoutePlayer(self.route, STRATEGY)
        player.remaining = []
        self.assertEqual(player.choose(self.operating())[1], "buy-bus")
        selected, phase = player.choose(self.operating())
        self.assertEqual(phase, "buy-bus")
        selected, phase = player.choose(self.operating(orders=[]))
        self.assertEqual((phase, selected["parameters"][1:4]), ("orders", [3, 1 | 0x61 << 16, 7]))
        first = {"index": 0, "destination": 7, "load_mode": 0}
        selected, phase = player.choose(self.operating(orders=[first]))
        self.assertEqual((phase, selected["parameters"][3]), ("orders", 8))
        second = {"index": 1, "destination": 8, "load_mode": 0}
        selected, phase = player.choose(self.operating(orders=[first, second]))
        self.assertEqual((phase, selected["parameters"][1:4]), ("loading", [3, 2 | 3 << 16, 3]))
        loaded = [{**first, "load_mode": 3}, {**second, "load_mode": 3}]
        self.assertEqual(player.choose(self.operating(orders=loaded))[1], "start")
        running = self.operating(orders=loaded, stopped=False)
        selected, phase = player.choose(running)
        self.assertEqual((phase, selected["parameters"][1:3]), ("repay", [2, 10000]))
        running["economy"] = {"balance": 25000, "loan": 100000}
        self.assertEqual(player.choose(running)[1], "wait")

    def test_state_only_observations_are_used_only_when_the_player_must_wait(self):
        player = RoutePlayer(self.route, STRATEGY)
        player.remaining = []
        loaded = [{"index": 0, "destination": 7, "load_mode": 3}, {"index": 1, "destination": 8, "load_mode": 3}]
        full = self.operating(orders=loaded, stopped=False)
        full["economy"] = {"balance": 25000, "loan": 100000}
        self.assertEqual(player.choose(full)[1], "wait")
        state = {**full, "candidates": [], "state_only": True}
        self.assertFalse(player.may_act(state))
        self.assertEqual(player.choose(state)[0]["family"], "WAIT")
        for change in ({"economy": {"balance": 40000, "loan": 100000}}, {"vehicles": []},
                       {"stations": [{**full["stations"][0], "waiting_passengers": 60}, full["stations"][1]]}):
            changed = {**state, **change}
            self.assertTrue(player.may_act(changed))
            self.assertNotEqual(player.choose({**full, **change})[1], "wait")
            with self.assertRaises(ValueError):
                player.choose(changed)

    def test_adds_a_bus_when_passengers_queue(self):
        player = RoutePlayer(self.route, STRATEGY)
        player.remaining = []
        loaded = [{"index": 0, "destination": 7, "load_mode": 3}, {"index": 1, "destination": 8, "load_mode": 3}]
        state = self.operating(orders=loaded, stopped=False)
        state["stations"][1]["waiting_passengers"] = 60
        self.assertEqual(player.choose(state)[1], "buy-bus")
        self.assertEqual(player.target_buses, 2)

    def test_focus_route_selects_its_town_pair_first(self):
        player = RoutePlayer({**self.route, "focus": [0, 1]}, STRATEGY)
        selected, phase = player.choose({**self.observation, "candidate_focus": {"towns": None}})
        self.assertEqual((phase, selected["parameters"][1:3]), ("select-towns", [0, 1]))
        self.assertEqual(player.choose({**self.observation, "candidate_focus": {"towns": [0, 1]}})[1], "build")


class StrategyAndDatabaseTests(unittest.TestCase):
    def test_grids_are_valid_and_distinct(self):
        for name, grid in GRIDS.items():
            identities = [strategy_id(check_strategy(dict(strategy))) for strategy in grid]
            self.assertEqual(len(identities), len(set(identities)), name)

    def test_invalid_strategies_fail_closed(self):
        for change in ({"buses": 0}, {"max_buses": 9}, {"buses": 3, "max_buses": 2}, {"load": "all"}, {"repay_reserve": -1}):
            with self.assertRaises(ValueError):
                check_strategy({**STRATEGY, **change})
        with self.assertRaises(ValueError):
            strategy_id({**STRATEGY, "extra": 1})

    def test_game_identity_binds_engine_map_route_strategy_and_budget(self):
        world = {"seed": 1, "split": "training", "width": 64, "height": 64}
        base = game_id("e", world, "r", STRATEGY, 512)
        self.assertEqual(base, game_id("e", dict(world), "r", dict(STRATEGY), 512))
        for changed in (game_id("f", world, "r", STRATEGY, 512), game_id("e", {**world, "seed": 2}, "r", STRATEGY, 512),
                        game_id("e", world, "q", STRATEGY, 512), game_id("e", world, "r", {**STRATEGY, "buses": 2}, 512),
                        game_id("e", world, "r", STRATEGY, 256)):
            self.assertNotEqual(base, changed)

    def test_selection_takes_best_sustained_games_per_map(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory)
            connection = sqlite3.connect(database / "games.sqlite")
            connection.executescript(SCHEMA)
            rows = [("a", "m1", 5, 1, 0), ("b", "m1", 9, 1, 0), ("c", "m1", 20, 0, 0), ("d", "m2", -3, 1, 0), ("e", "m2", 50, 1, 1)]
            for game, map_id, net_cash, sustained, bankrupt in rows:
                connection.execute("INSERT INTO games (game_id, map_id, status, net_cash, operating_profit, passengers, "
                                   "sustained_service, bankrupt, directory) VALUES (?,?,?,?,?,?,?,?,?)",
                                   (game, map_id, "completed", net_cash, 0, 0, sustained, bankrupt, f"/{game}"))
            connection.commit()
            connection.close()
            self.assertEqual([g["game_id"] for g in select_games(database, 1)], ["b", "d"])
            self.assertEqual([g["game_id"] for g in select_games(database, 2)], ["b", "a", "d"])

    def test_scripted_reference_requires_a_matching_development_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory)
            (database / "database.json").write_text(json.dumps({"split": "development", "engine_sha256": "e"}))
            connection = sqlite3.connect(database / "games.sqlite")
            connection.executescript(SCHEMA)
            for game, profit in (("a", -5), ("b", 30), ("c", 10)):
                connection.execute("INSERT INTO games (game_id, map_id, status, operating_profit, passengers, sustained_service) "
                                   "VALUES (?,?,?,?,?,?)", (game, "m", "completed", profit, 1, int(profit > 0)))
            connection.commit()
            connection.close()
            self.assertEqual(scripted_reference(database, "e", ["m", "absent"]),
                             {"m": {"games": 3, "best_operating_profit": 30, "best_passengers": 1,
                                    "median_operating_profit": 10, "sustained_service_games": 2}})
            with self.assertRaises(ValueError):
                scripted_reference(database, "other", ["m"])

    def test_wait_labels_follow_the_stride(self):
        self.assertTrue(labelled({"family": "BUY_BUS", "decision": 3}, 32))
        self.assertTrue(labelled({"family": "WAIT", "decision": 64}, 32))
        self.assertFalse(labelled({"family": "WAIT", "decision": 65}, 32))


if __name__ == "__main__":
    unittest.main()
