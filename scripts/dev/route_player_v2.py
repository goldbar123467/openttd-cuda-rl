#!/usr/bin/env python3
"""Play one complete scripted bus game on a chosen route through live V2 orders-v1.

The player builds a route from `route_atlas_v2`, buys buses, gives each the
route's two station orders, sets loading, starts service, then waits, adds
buses when passengers queue and manages the loan according to a strategy.
Every decision is an exposed native legal candidate followed by a 128-tick
STEP, so a game is the same kind of record a neural policy or MCP agent makes.
Waiting is an explicit scripted choice, recorded like any other action.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time

from evaluate_bus_orders_campaign_v2 import CompactJournal
from live_v2 import LiveV2, reset_manifest
from local import positive, write_json
from route_atlas_v2 import stable_id, enumerate_routes
from service_v2 import summarize

PLAYER = "scripted-route-player-v1"
GOTO_STATION = 0x61
LOAD_MODES = {"none": 0, "full-load-any": 3}
STRATEGY_KEYS = ("buses", "max_buses", "queue_threshold", "load", "repay_reserve")


def strategy_id(strategy):
    if set(strategy) != set(STRATEGY_KEYS):
        raise ValueError("Strategy fields differ")
    return hashlib.sha256(json.dumps(strategy, sort_keys=True).encode()).hexdigest()[:12]


def check_strategy(strategy):
    strategy_id(strategy)
    if (type(strategy["buses"]) is not int or type(strategy["max_buses"]) is not int or
            not 1 <= strategy["buses"] <= strategy["max_buses"] <= 8 or strategy["load"] not in ("none", "first", "both") or
            type(strategy["queue_threshold"]) is not int or strategy["queue_threshold"] < 1 or
            (strategy["repay_reserve"] is not None and (type(strategy["repay_reserve"]) is not int or strategy["repay_reserve"] < 0))):
        raise ValueError("Strategy values outside the supported range")
    return strategy


class ConstructionBlocked(RuntimeError):
    """A planned primitive stayed unexposed; recorded as a failed route, not retried."""


class RoutePlayer:
    def __init__(self, route, strategy, *, blocked_limit=16):
        self.route, self.strategy = route, check_strategy(strategy)
        self.focus = route.get("focus")
        priority = {"BUILD_ROAD_DEPOT": 0, "BUILD_BUS_STOP": 1, "BUILD_ROAD_PATH": 2}
        # Reserve the depot and stop sites before road work changes the bounded
        # candidate inventory, as the supplied-infrastructure benchmark does.
        self.remaining = sorted(route["actions"], key=lambda row: priority[row[0]])
        self.blocked, self.blocked_limit = 0, blocked_limit
        self.target_buses = strategy["buses"]

    def _wait(self, observation):
        return next(c for c in observation["candidates"] if c["family"] == "WAIT")

    def choose(self, observation):
        """Return (candidate, phase)."""
        inventory = {(c["family"], tuple(c["parameters"][1:4])): c for c in observation["candidates"]}
        economy = observation["economy"]
        if self.focus and (observation.get("candidate_focus") or {}).get("towns") != self.focus:
            return inventory[("SELECT_TOWN_PAIR", (*self.focus, 0))], "select-towns"
        if self.remaining:
            # Towns grow their own roads; a planned piece that now exists is
            # no longer a legal command but the route is connected there.
            roads = dict(observation["map"]["roads"])
            self.remaining = [(family, params) for family, params in self.remaining
                              if family != "BUILD_ROAD_PATH" or roads.get(params[0], 0) & params[1] != params[1]]
        if self.remaining:
            index = next((i for i, (family, params) in enumerate(self.remaining) if (family, tuple(params)) in inventory), None)
            if index is not None:
                family, params = self.remaining.pop(index)
                self.blocked = 0
                return inventory[(family, tuple(params))], "build"
            borrow = inventory.get(("MANAGE_LOAN", (1, 10000, 0)))
            if borrow and economy["balance"] < 20000:
                return borrow, "borrow-for-construction"
            self.blocked += 1
            if self.blocked > self.blocked_limit:
                raise ConstructionBlocked(f"{len(self.remaining)} planned primitives unexposed for {self.blocked_limit} decisions")
            return self._wait(observation), "blocked-wait"
        stations = {station["tile"]: station for station in observation["stations"]}
        ends = [stations.get(stop["tile"]) for stop in self.route["stops"]]
        if None in ends:
            raise ConstructionBlocked("Built stop tiles are not own stations")
        buses = sorted(observation["vehicles"], key=lambda bus: bus["id"])
        desired = [end["id"] for end in ends]
        loads = {"none": [0, 0], "first": [3, 0], "both": [3, 3]}[self.strategy["load"]]
        # Configure the newest incomplete bus first so a purchase is never stranded.
        for bus in buses:
            orders = bus["orders"]
            destinations = [order["destination"] for order in orders]
            if destinations != desired[:len(destinations)]:
                return inventory[("SET_ROUTE", (bus["id"], 4 | (len(orders) - 1) << 8, 0))], "fix-orders"
            if len(orders) < 2:
                index = len(orders)
                key = ("SET_ROUTE", (bus["id"], 1 | index << 8 | GOTO_STATION << 16, desired[index]))
                if key in inventory:
                    return inventory[key], "orders"
            for order, mode in zip(orders, loads):
                if order["load_mode"] != mode:
                    key = ("SET_ROUTE", (bus["id"], 2 | order["index"] << 8 | 3 << 16, mode))
                    if key in inventory:
                        return inventory[key], "loading"
            if bus["stopped"] and len(orders) == 2:
                key = ("START_VEHICLE", (bus["id"], 0, 0))
                if key in inventory:
                    return inventory[key], "start"
        buy = next((c for c in observation["candidates"] if c["family"] == "BUY_BUS" and c["parameters"][1] == self.route["depot"]), None)
        waiting = max(end["waiting_passengers"] for end in ends)
        if (len(buses) < self.target_buses or (len(buses) < self.strategy["max_buses"] and
                waiting >= self.strategy["queue_threshold"] and all(not bus["stopped"] for bus in buses))):
            if buy and economy["balance"] - buy["cost"] >= 5000:
                self.target_buses = max(self.target_buses, len(buses) + 1)
                return buy, "buy-bus"
            borrow = inventory.get(("MANAGE_LOAN", (1, 10000, 0)))
            if borrow and len(buses) < self.strategy["buses"]:
                return borrow, "borrow-for-bus"
        reserve = self.strategy["repay_reserve"]
        repay = inventory.get(("MANAGE_LOAN", (2, 10000, 0)))
        if reserve is not None and repay and economy["loan"] >= 10000 and economy["balance"] >= reserve + 10000:
            return repay, "repay"
        return self._wait(observation), "wait"


def world_factory(width, height):
    return lambda executable, baseset, seed, split: reset_manifest(executable, baseset, seed, split, width=width, height=height)


def open_game(engine, worker, world, decisions, focus=False):
    client = LiveV2(engine, worker, seed=world["seed"], split=world["split"], decisions=decisions,
                    observation_mode="orders-v1", _reset_factory=world_factory(world["width"], world["height"]),
                    candidate_focus="town-pair-v1" if focus else None)
    client.events = CompactJournal(client.events)
    return client


def discover_routes(engine, directory, world, parameters, *, focus=False):
    """All routes at reset, plus (with focus) those exposed after selecting each town pair.

    Selecting a pair costs one decision, so its routes are enumerated from the
    observation after that step, exactly where the player starts building.
    """
    def probe(name, pair):
        client = open_game(engine, directory / name, world, 2 if pair else 1, focus=focus)
        try:
            observation = client.request("OBSERVE")["observation"]
            if pair:
                select = next(c for c in observation["candidates"] if c["family"] == "SELECT_TOWN_PAIR" and c["parameters"][1:3] == list(pair))
                if client.request("ACT", token=observation["token"], candidate=select["key"])["status"] != "OK":
                    raise RuntimeError("Town-pair selection was rejected")
                client.request("STEP")
                observation = client.request("OBSERVE")["observation"]
            routes, report = enumerate_routes(observation, **parameters)
            client.close()
            client = None
        finally:
            if client is not None:
                client.abort()
        for route in routes:
            route["focus"] = list(pair) if pair else None
            route["route_id"] = stable_id({"focus": route["focus"], "route": route["route_id"]})
        return observation, routes, report
    initial, routes, report = probe("anchor", None)
    reports = {"anchor": report}
    pairs = sorted({tuple(sorted(c["parameters"][1:3])) for c in initial["candidates"] if c["family"] == "SELECT_TOWN_PAIR"}) if focus else []
    for pair in pairs:
        _, focused, reports[f"towns-{pair[0]}-{pair[1]}"] = probe(f"towns-{pair[0]}-{pair[1]}", pair)
        routes.extend(focused)
    return {"world": world, "token": initial["token"], "towns": initial["towns"], "routes": routes,
            "report": {"parameters": parameters, "candidate_focus": "town-pair-v1" if focus else None, "probes": reports}}


def play(engine, output, world, route, strategy, *, decisions=512, focus=False):
    """Play one game; write decisions.jsonl.gz and result.json. Returns the result."""
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema_version": "openttd-rl-scripted-route-game-1", "player": PLAYER, "status": "running",
              "world": world, "route_id": route["route_id"], "focus": route.get("focus"),
              "candidate_focus": "town-pair-v1" if focus else None, "strategy": strategy,
              "strategy_id": strategy_id(strategy), "decisions_budget": decisions, "step_ticks": 128}
    write_json(output / "result.json", result)
    client, started = None, time.monotonic()
    rows = []
    try:
        client = open_game(engine, output / "worker", world, decisions, focus=focus)
        initial = client.request("OBSERVE")["observation"]
        player = RoutePlayer(route, strategy)
        observation, transitions, verified = initial, [], False
        for _ in range(decisions):
            candidate, phase = player.choose(observation)
            if phase == "build" and not verified:
                # Determinism check: the plan must be rediscovered where building starts.
                atlas_routes, _ = enumerate_routes(observation, **route["atlas_parameters"])
                if not any(r["line"] == route["line"] and r["actions"] == route["actions"] for r in atlas_routes):
                    raise ValueError("Route is not reproduced where construction starts; map or engine differs")
                verified = True
            action = client.request("ACT", token=observation["token"], candidate=candidate["key"])
            if action["status"] != "OK" or action["action"]["status"] not in ("SUCCESS", "NO_OP"):
                raise RuntimeError(f"Exposed native action failed: {action}")
            transition = client.request("STEP")["transition"]
            if transition["tick_after"] - transition["tick_before"] != 128:
                raise RuntimeError("Native step budget differs")
            transitions.append(transition)
            rows.append({"decision": transition["decision"], "token": observation["token"], "tick": observation["tick"],
                         "family": candidate["family"], "key": candidate["key"], "parameters": candidate["parameters"][:4],
                         "cost": candidate["cost"], "legal_candidates": len(observation["candidates"]), "phase": phase,
                         "before": transition["before"], "after": transition["after"]})
            observation = client.request("OBSERVE")["observation"]
            if transition["terminal"] or transition["truncated"]:
                break
        final = observation
        client.close()
        client = None
        summary = summarize(transitions, initial, final)
        result.update(status="completed", summary=summary, final_token=final["token"],
                      final_state={key: final[key] for key in ("economy", "stations", "depots", "vehicles", "tick")})
    except ConstructionBlocked as error:
        result.update(status="blocked", error=str(error))
    except BaseException as error:
        result.update(status="failed", error=f"{type(error).__name__}: {error}")
        if not isinstance(error, Exception):
            raise
    finally:
        if client is not None:
            client.abort()
        with gzip.open(output / "decisions.jsonl.gz", "wt") as stream:
            for row in rows:
                stream.write(json.dumps(row, separators=(",", ":")) + "\n")
        result["decisions_recorded"] = len(rows)
        result["wall_seconds"] = round(time.monotonic() - started, 2)
        for name in ("requests.jsonl", "transitions.jsonl"):
            path = output / "worker" / name
            if path.exists():
                with path.open("rb") as source, gzip.open(path.with_suffix(".jsonl.gz"), "wb") as target:
                    target.write(source.read())
                path.unlink()
        write_json(output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openttd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--split", choices=("training", "development"), default="training")
    parser.add_argument("--size", type=int, choices=(64, 128), default=64)
    parser.add_argument("--route-index", type=int, default=0)
    parser.add_argument("--decisions", type=positive, default=512)
    parser.add_argument("--buses", type=positive, default=1)
    parser.add_argument("--max-buses", type=positive, default=3)
    parser.add_argument("--queue-threshold", type=positive, default=60)
    parser.add_argument("--load", choices=("none", "first", "both"), default="both")
    parser.add_argument("--repay-reserve", type=int, default=20000)
    parser.add_argument("--town-pair-focus", action="store_true", help="engine built by prepare_route_focus.py")
    args = parser.parse_args()
    world = {"seed": args.seed, "split": args.split, "width": args.size, "height": args.size}
    parameters = {"minimum_length": 8, "maximum_tiles": 64, "stops_per_town": 3, "routes_per_pair": 1}
    found = discover_routes(args.openttd.resolve(), args.output.resolve() / "atlas", world, parameters, focus=args.town_pair_focus)
    for index, route in enumerate(found["routes"]):
        print(index, route["focus"], route["town_pair"], route["kind"], route["path_tiles"], route["estimated_construction_cost"])
    route = {**found["routes"][args.route_index], "atlas_parameters": parameters}
    strategy = {"buses": args.buses, "max_buses": args.max_buses, "queue_threshold": args.queue_threshold,
                "load": args.load, "repay_reserve": args.repay_reserve}
    result = play(args.openttd.resolve(), args.output.resolve() / "game", world, route, strategy,
                  decisions=args.decisions, focus=args.town_pair_focus)
    print(json.dumps({key: result.get(key) for key in ("status", "error", "summary", "wall_seconds")}, indent=1)[:3000])
