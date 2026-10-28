#!/usr/bin/env python3
"""Collect a database of scripted bus games: every exposed route on every map, under each strategy.

`collect` enumerates routes once per map (`route_atlas_v2`), then plays one full
game per map x route x strategy with `route_player_v2`, in parallel game
workers. Results go to a SQLite index (`games.sqlite`) and one directory per
game holding its compressed decision log, native transitions and summary.
Collection resumes: games already recorded are skipped, so the same command can
be rerun or extended with more seeds, sizes or strategies.

Maps come only from the contract's training or development seed ledgers, and a
database holds one split. Keep them apart: train on a training database, select
on a development one; final seeds are never used.

`report` prints per-strategy and per-map summaries from the index.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import itertools
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

from local import ROOT, baseset_identity, positive, source_identity, write_json
from route_player_v2 import PLAYER, discover_routes, play, strategy_id

SCHEMA = """
CREATE TABLE IF NOT EXISTS collections (id INTEGER PRIMARY KEY, started REAL, record TEXT);
CREATE TABLE IF NOT EXISTS maps (map_id TEXT PRIMARY KEY, split TEXT, seed INTEGER, width INTEGER, height INTEGER,
    initial_token TEXT, towns TEXT, atlas TEXT, status TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS routes (map_id TEXT, route_id TEXT, rank INTEGER, focus TEXT, kind TEXT, town_a INTEGER, town_b INTEGER,
    separation INTEGER, path_tiles INTEGER, new_road_actions INTEGER, construction_cost INTEGER, house_score INTEGER,
    route TEXT, PRIMARY KEY (map_id, route_id));
CREATE TABLE IF NOT EXISTS games (game_id TEXT PRIMARY KEY, map_id TEXT, route_id TEXT, strategy_id TEXT, strategy TEXT,
    status TEXT, decisions INTEGER, passengers INTEGER, operating_profit INTEGER, cash_result INTEGER,
    final_balance INTEGER, final_loan INTEGER, net_cash INTEGER, buses INTEGER, bankrupt INTEGER,
    sustained_service INTEGER, first_delivery INTEGER, non_wait_actions INTEGER, wall_seconds REAL,
    directory TEXT, error TEXT, collection_id INTEGER);
CREATE INDEX IF NOT EXISTS games_by_map ON games (map_id, status);
"""

# Named strategy grids. Each strategy is one way to operate any route: initial
# buses, adding buses (up to max_buses) when a stop queues queue_threshold
# passengers, loading at the two stops, and repaying debt above a cash reserve.
GRIDS = {
    "smoke": [{"buses": 1, "max_buses": 3, "queue_threshold": 60, "load": "both", "repay_reserve": 20000}],
    "standard": [{"buses": buses, "max_buses": 4, "queue_threshold": 60, "load": load, "repay_reserve": reserve}
                 for buses, load, reserve in itertools.product((1, 2), ("both", "none"), (20000, None))],
    "full": [{"buses": buses, "max_buses": 4 if scale else buses, "queue_threshold": 60, "load": load, "repay_reserve": reserve}
             for buses, scale, load, reserve in itertools.product((1, 2), (False, True), ("both", "first", "none"), (20000, 50000, None))],
}


def connect(database):
    connection = sqlite3.connect(database / "games.sqlite", timeout=60)
    connection.executescript(SCHEMA)
    return connection


def contract_seeds(split):
    contract = json.loads((ROOT / "config/v2/m15-scalable-contract.json").read_text())
    return contract["seeds"]["sets"][split]["seeds"]


def map_id(world):
    return f"{world['split']}-{world['seed']}-{world['width']}x{world['height']}"


def game_id(engine_sha256, world, route_id, strategy, decisions):
    identity = {"engine": engine_sha256, "map": map_id(world), "route": route_id,
                "strategy": strategy_id(strategy), "decisions": decisions, "player": PLAYER}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]


def run_game(engine, directory, world, route, strategy, decisions, focus):
    return play(engine, directory, world, route, strategy, decisions=decisions, focus=focus)


def collect(args):
    database = args.database.resolve()
    database.mkdir(parents=True, exist_ok=True)
    engine = args.openttd.resolve(strict=True)
    engine_sha256 = hashlib.sha256(engine.read_bytes()).hexdigest()
    identity_path = database / "database.json"
    identity = {"schema_version": "openttd-rl-scripted-game-database-1", "split": args.split, "engine_sha256": engine_sha256,
                "baseset": baseset_identity(engine.parent / "baseset/opengfx-8.0.tar"), "player": PLAYER,
                "decisions": args.decisions, "observation_mode": "orders-v1",
                "candidate_focus": "town-pair-v1" if args.town_pair_focus else None}
    if identity_path.exists():
        recorded = json.loads(identity_path.read_text())
        if recorded != identity:
            raise ValueError("Database was collected with another split, engine, base graphics, player or budget; use a new directory")
    else:
        write_json(identity_path, identity)
    strategies = json.loads(args.strategies.read_text()) if args.strategies else GRIDS[args.grid]
    for strategy in strategies:
        strategy_id(strategy)
    seeds = args.seeds or contract_seeds(args.split)
    if args.max_maps:
        seeds = seeds[:args.max_maps]
    worlds = [{"seed": seed, "split": args.split, "width": size, "height": size} for size in args.sizes for seed in seeds]
    parameters = {"minimum_length": args.minimum_length, "maximum_tiles": args.maximum_tiles,
                  "stops_per_town": args.stops_per_town, "routes_per_pair": args.routes_per_pair}
    connection = connect(database)
    record = {"source": source_identity(), "argv": sys.argv, "engine": str(engine), "strategies": strategies,
              "worlds": len(worlds), "atlas_parameters": parameters, "workers": args.workers}
    collection = connection.execute("INSERT INTO collections (started, record) VALUES (?, ?)",
                                    (time.time(), json.dumps(record))).lastrowid
    connection.commit()
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        pending = {}
        for world in worlds:
            row = connection.execute("SELECT atlas FROM maps WHERE map_id = ? AND status = 'ok'", (map_id(world),)).fetchone()
            if row and json.loads(row[0])["parameters"] == parameters:
                continue
            directory = database / "maps" / map_id(world) / f"atlas-{collection:04d}"
            pending[pool.submit(discover_routes, engine, directory, world, parameters, focus=args.town_pair_focus)] = world
        for future in as_completed(pending):
            world = pending[future]
            try:
                value = future.result()
            except Exception as error:
                connection.execute("INSERT OR REPLACE INTO maps (map_id, split, seed, width, height, status, error) VALUES (?,?,?,?,?,?,?)",
                                   (map_id(world), world["split"], world["seed"], world["width"], world["height"], "failed", repr(error)))
                print(json.dumps({"map": map_id(world), "atlas": "failed", "error": repr(error)}), flush=True)
            else:
                connection.execute("DELETE FROM routes WHERE map_id = ?", (map_id(world),))
                connection.execute("INSERT OR REPLACE INTO maps VALUES (?,?,?,?,?,?,?,?,?,?)",
                                   (map_id(world), world["split"], world["seed"], world["width"], world["height"], value["token"],
                                    json.dumps(value["towns"]), json.dumps(value["report"]), "ok", None))
                for rank, route in enumerate(value["routes"]):
                    connection.execute("INSERT INTO routes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                       (map_id(world), route["route_id"], rank, json.dumps(route["focus"]), route["kind"], *route["town_pair"],
                                        route["manhattan_separation"], route["path_tiles"], route["new_road_actions"],
                                        route["estimated_construction_cost"], route["house_score"], json.dumps(route)))
                print(json.dumps({"map": map_id(world), "routes": len(value["routes"]), "towns": len(value["towns"]),
                                  "kinds": sorted({(route["kind"], json.dumps(route["focus"])) for route in value["routes"]})}), flush=True)
            connection.commit()
        jobs = []
        for world in worlds:
            routes = connection.execute("SELECT route FROM routes WHERE map_id = ? ORDER BY rank", (map_id(world),)).fetchall()
            for (text,), strategy in itertools.product(routes, strategies):
                route = {**json.loads(text), "atlas_parameters": parameters}
                identity = game_id(engine_sha256, world, route["route_id"], strategy, args.decisions)
                done = connection.execute("SELECT status FROM games WHERE game_id = ?", (identity,)).fetchone()
                if done and (done[0] == "completed" or not args.retry_failed):
                    continue
                attempt = 1 + connection.execute("SELECT COUNT(*) FROM games WHERE game_id = ?", (identity,)).fetchone()[0]
                directory = database / "games" / map_id(world) / identity / f"attempt-{attempt:02d}"
                if directory.exists():
                    directory = directory.with_name(f"{directory.name}-{collection:04d}")
                jobs.append((identity, world, route, strategy, directory))
        if args.limit:
            jobs = jobs[:args.limit]
        print(json.dumps({"collection": collection, "maps": len(worlds), "strategies": len(strategies), "games": len(jobs)}), flush=True)
        futures = {pool.submit(run_game, engine, directory, world, route, strategy, args.decisions, args.town_pair_focus):
                   (identity, world, route, strategy, directory)
                   for identity, world, route, strategy, directory in jobs}
        finished = 0
        for future in as_completed(futures):
            identity, world, route, strategy, directory = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = {"status": "failed", "error": repr(error)}
            summary = result.get("summary") or {}
            final = (result.get("final_state") or {}).get("economy") or {}
            non_wait = summary.get("decisions", 0) - summary.get("action_counts", {}).get("WAIT", 0) if summary else None
            connection.execute("INSERT OR REPLACE INTO games VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (identity, map_id(world), route["route_id"], strategy_id(strategy), json.dumps(strategy),
                                result["status"], summary.get("decisions"), summary.get("passengers"),
                                summary.get("operating_profit"), summary.get("cash_result_excluding_financing"),
                                final.get("balance"), final.get("loan"),
                                final["balance"] - final["loan"] if final else None, summary.get("buses"),
                                int(summary["bankruptcy"]) if summary else None,
                                int(summary["service_in_all_final_three_windows"]) if summary else None,
                                summary.get("first_delivery_action"), non_wait, result.get("wall_seconds"),
                                str(directory), result.get("error"), collection))
            connection.commit()
            finished += 1
            print(json.dumps({"done": finished, "of": len(jobs), "game": identity, "map": map_id(world), "status": result["status"],
                              "passengers": summary.get("passengers"), "operating_profit": summary.get("operating_profit"),
                              "net_cash": final["balance"] - final["loan"] if final else None,
                              "seconds": result.get("wall_seconds"), "error": result.get("error")}), flush=True)
    record["elapsed_seconds"] = round(time.monotonic() - started, 1)
    connection.execute("UPDATE collections SET record = ? WHERE id = ?", (json.dumps(record), collection))
    connection.commit()
    connection.close()


def report(args):
    connection = connect(args.database.resolve())
    query = connection.execute
    print(json.dumps({"maps": query("SELECT status, COUNT(*) FROM maps GROUP BY status").fetchall(),
                      "routes": query("SELECT kind, COUNT(*) FROM routes GROUP BY kind").fetchall(),
                      "games": query("SELECT status, COUNT(*) FROM games GROUP BY status").fetchall()}))
    print("strategy                                                          games  deliver  sustained  mean_profit  mean_net_cash  sec/game")
    for strategy, games, delivered, sustained, profit, net, seconds in query(
            "SELECT strategy, COUNT(*), SUM(passengers > 0), SUM(sustained_service), AVG(operating_profit), AVG(net_cash), AVG(wall_seconds) "
            "FROM games WHERE status = 'completed' GROUP BY strategy_id ORDER BY AVG(net_cash) DESC"):
        print(f"{strategy:65s} {games:5d}  {delivered:7d}  {sustained:9d}  {profit:11.0f}  {net:13.0f}  {seconds:8.1f}")
    print("best game per map (by final cash minus loan):")
    for row in query("SELECT map_id, game_id, route_id, strategy, passengers, operating_profit, MAX(net_cash) FROM games "
                     "WHERE status = 'completed' GROUP BY map_id ORDER BY map_id"):
        print(json.dumps(dict(zip(("map", "game", "route", "strategy", "passengers", "operating_profit", "net_cash"), row))))
    connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    collector = commands.add_parser("collect")
    collector.add_argument("--openttd", type=Path, required=True)
    collector.add_argument("--database", type=Path, required=True)
    collector.add_argument("--split", choices=("training", "development"), default="training")
    collector.add_argument("--seeds", type=int, nargs="*", help="subset of the split's ledger seeds (default: all)")
    collector.add_argument("--max-maps", type=positive, help="use the first N ledger seeds")
    collector.add_argument("--sizes", type=int, nargs="+", choices=(64, 128), default=[64])
    collector.add_argument("--grid", choices=sorted(GRIDS), default="standard")
    collector.add_argument("--strategies", type=Path, help="JSON list of strategies instead of a named grid")
    collector.add_argument("--decisions", type=positive, default=512)
    collector.add_argument("--workers", type=positive, default=os.cpu_count() or 1)
    collector.add_argument("--limit", type=positive, help="play at most N new games this run")
    collector.add_argument("--retry-failed", action="store_true", help="replay failed and blocked games")
    collector.add_argument("--minimum-length", type=positive, default=8)
    collector.add_argument("--maximum-tiles", type=positive, default=64)
    collector.add_argument("--stops-per-town", type=positive, default=3)
    collector.add_argument("--routes-per-pair", type=positive, default=2)
    collector.add_argument("--town-pair-focus", action="store_true",
                           help="engine from prepare_route_focus.py: also play routes exposed after SELECT_TOWN_PAIR")
    reporter = commands.add_parser("report")
    reporter.add_argument("--database", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "collect":
        seeds = set(contract_seeds(arguments.split))
        if arguments.seeds and not set(arguments.seeds) <= seeds:
            parser.error("--seeds must come from the selected split's ledger")
        collect(arguments)
    else:
        report(arguments)
