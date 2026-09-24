#!/usr/bin/env python3
"""Build and operate one bus through public live V2 observations and candidates."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time

from live_v2 import LiveV2
from local import capture_source, positive, source_identity, write_json
from route_v2 import plan_network


def candidate_index(observation):
    return {(c["family"], tuple(c["parameters"][1:4])): c for c in observation["candidates"]}


def plan_service(observation, *, minimum_length=8, reuse_roads=False):
    """Straight public-state baseline; no engine predicates beyond exposed candidates.

    Mirroring the old qualification's site scoring does not execute its SERVICE
    macro: each primitive below is selected again from the next live observation.
    """
    grid = observation["map"]
    width, height = grid["width"], grid["height"]
    clear = set(grid["clear_tiles"])
    existing_roads = dict(grid["roads"]) if reuse_roads else {}
    houses = [(tile % width, tile // width) for tile in grid["houses"]]
    candidates = candidate_index(observation)
    def near(tile):
        x, y = tile % width, tile // width
        return sum(abs(hx - x) <= 4 and abs(hy - y) <= 4 for hx, hy in houses)
    def key(family, tile, parameter, count=0):
        return family, (tile, parameter, count)
    best = None
    for vertical in (False, True):
        step, bits = (width, 5) if vertical else (1, 10)
        first_direction, last_direction = (1, 3) if vertical else (2, 0)
        for length in (length for length in (8, 10, 12) if length >= minimum_length):
            for start in sorted(clear):
                x, y = start % width, start // width
                if x < 1 or y < 1 or x + (1 if vertical else length) >= width or y + (length if vertical else 1) >= height:
                    continue
                line = [start + offset * step for offset in range(length)]
                if line[-1] not in clear or not all(tile in clear or tile in existing_roads for tile in line[1:-1]):
                    continue
                stops = [key("BUILD_BUS_STOP", line[0], first_direction),
                         key("BUILD_BUS_STOP", line[-1], last_direction)]
                roads = [key("BUILD_ROAD_PATH", tile, bits, 1) for tile in line[1:-1]
                         if existing_roads.get(tile, 0) & bits != bits]
                junction = line[length // 2]
                crossing_bits = 10 if vertical else 5
                crossings = [] if existing_roads.get(junction, 0) & crossing_bits == crossing_bits else [key("BUILD_ROAD_PATH", junction, crossing_bits, 1)]
                if any(action not in candidates for action in stops + roads + crossings):
                    continue
                coverage = [near(line[0]), near(line[-1])]
                if min(coverage) == 0:
                    continue
                for side in (-1, 1):
                    depot = junction + side * (1 if vertical else width)
                    direction = (2 if side < 0 else 0) if vertical else (1 if side < 0 else 3)
                    depot_action = key("BUILD_ROAD_DEPOT", depot, direction)
                    if depot not in clear or depot_action not in candidates:
                        continue
                    actions = roads + crossings + stops + [depot_action]
                    score = min(coverage) * 10000 + sum(coverage)
                    rank = (-score, start, length, vertical, side)
                    if best is None or rank < best[0]:
                        best = rank, {"line": line, "depot": depot, "depot_direction": direction,
                                      "house_coverage": coverage, "house_score": score,
                                      "estimated_construction_cost": sum(candidates[action]["cost"] for action in actions),
                                      "actions": [[family, list(params)] for family, params in actions]}
    if best is None:
        raise RuntimeError("No complete straight bus site exists among the exposed legal candidates")
    return best[1]


class ServicePolicy:
    def __init__(self, observation, *, repay=False, minimum_length=8, reuse_roads=False, planner="straight", site_checks=False):
        self.plan = plan_network(observation, minimum_length=minimum_length, site_checks=site_checks) if planner == "graph" else plan_service(observation, minimum_length=minimum_length, reuse_roads=reuse_roads)
        self.stage = 0
        self.repay = repay

    def choose(self, observation):
        candidates = candidate_index(observation)
        if self.stage < len(self.plan["actions"]):
            family, params = self.plan["actions"][self.stage]
            candidate = candidates.get((family, tuple(params)))
            if candidate is None:
                raise RuntimeError(f"Planned primitive is no longer exposed/legal at stage {self.stage}: {family} {params}")
            self.stage += 1
            return candidate
        buses = observation["vehicles"]
        if not buses:
            matches = [c for c in observation["candidates"] if c["family"] == "BUY_BUS" and c["parameters"][1] == self.plan["depot"]]
        else:
            if len(buses) != 1:
                raise RuntimeError("One-bus baseline unexpectedly has multiple vehicles")
            bus = buses[0]
            stations = {station["tile"]: station["id"] for station in observation["stations"]}
            desired = [stations[self.plan["line"][0]], stations[self.plan["line"][-1]]]
            if [order["destination"] for order in bus["orders"]] != desired:
                matches = [c for c in observation["candidates"] if c["family"] == "SET_ROUTE" and c["parameters"][1:4] == [bus["id"], *desired]]
            elif bus["stopped"]:
                matches = [c for c in observation["candidates"] if c["family"] == "START_VEHICLE" and c["parameters"][1] == bus["id"]]
            else:
                matches = [c for c in observation["candidates"] if c["family"] == "WAIT"]
                if self.repay and observation["economy"]["balance"] >= 20000 and observation["economy"]["loan"] >= 10000:
                    payments = [c for c in observation["candidates"] if c["family"] == "MANAGE_LOAN" and c["parameters"][1:3] == [2, 10000]]
                    if payments:
                        matches = payments
        if not matches:
            raise RuntimeError("Planned service continuation has no exposed legal candidate")
        return matches[0]


def summarize(transitions, initial, final):
    def net_capital(rows):
        return sum(c["cost"] for row in rows if row["action"]["family"] in
                   ("BUILD_ROAD_PATH", "BUILD_BUS_STOP", "BUILD_ROAD_DEPOT", "BUY_BUS", "SELL_VEHICLE")
                   for c in row["action"]["native_commands"] if c["phase"] == "EXECUTE" and c["status"] == "SUCCESS")
    windows = []
    for start in range(0, len(transitions), 128):
        rows = transitions[start:start + 128]
        before, after = rows[0]["before"], rows[-1]["after"]
        windows.append({"first_decision": start + 1, "decisions": len(rows),
                        "passengers": after["delivered_passengers"] - before["delivered_passengers"],
                        "operating_profit": after["operating_profit"] - before["operating_profit"],
                        "cash_result_before_capital": after["balance"] - before["balance"] -
                            (after["loan"] - before["loan"]) + net_capital(rows)})
    capital_families = {"BUILD_ROAD_PATH", "BUILD_BUS_STOP", "BUILD_ROAD_DEPOT", "BUY_BUS"}
    capital = sum(c["cost"] for row in transitions if row["action"]["family"] in capital_families
                  for c in row["action"]["native_commands"] if c["phase"] == "EXECUTE" and c["status"] == "SUCCESS")
    sales = -sum(c["cost"] for row in transitions if row["action"]["family"] == "SELL_VEHICLE"
                 for c in row["action"]["native_commands"] if c["phase"] == "EXECUTE" and c["status"] == "SUCCESS")
    end, beginning = final["economy"], initial["economy"]
    profit = end["operating_profit"] - beginning["operating_profit"]
    balance_change = end["balance"] - beginning["balance"]
    loan_change = end["loan"] - beginning["loan"]
    cash_result = balance_change - loan_change
    return {"accounting_schema": "development-v2-single-economics-3",
            "decisions": len(transitions), "simulation_ticks": final["tick"] - initial["tick"],
            "passengers": end["delivered_passengers"] - beginning["delivered_passengers"],
            "operating_profit": profit, "capital_spend": capital, "vehicle_sale_proceeds": sales,
            "net_capital_spend": capital - sales, "operating_profit_less_capital": profit - capital + sales,
            "balance_change": balance_change, "loan_change": loan_change,
            "cash_result_excluding_financing": cash_result,
            "cash_result_before_capital": cash_result + capital - sales,
            "other_cash_flow": cash_result - (profit - capital + sales),
            "invalid_actions": sum(row["action"]["status"] not in ("SUCCESS", "NO_OP") for row in transitions),
            "bankruptcy": final["terminal"], "buses": len(final["vehicles"]), "stations": len(final["stations"]),
            "first_delivery_action": next((row["decision"] for row in transitions if row["after"]["delivered_passengers"] > beginning["delivered_passengers"]), None),
            "action_counts": dict(Counter(row["action"]["family"] for row in transitions)), "windows": windows,
            "service_in_all_final_three_windows": len(windows) == 4 and all(w["decisions"] == 128 and w["passengers"] > 0 and w["operating_profit"] > 0 for w in windows[-3:]),
            "positive_cash_service_in_all_final_three_windows": len(windows) == 4 and all(w["decisions"] == 128 and w["passengers"] > 0 and w["cash_result_before_capital"] > 0 for w in windows[-3:])}


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    record = {"kind": "interactive-native-v2-service", "status": "running", "source": source_identity(),
              "policy": args.policy, "split": args.split, "seed": args.seed, "maximum_decisions": args.decisions,
              "minimum_route_length": args.minimum_route_length,
              "reuse_roads": args.reuse_roads,
              "planner": args.planner,
              "native_site_checks": args.native_site_checks,
              "hypothesis": "A public-state script can establish passenger service via sequential native legal candidates",
              "claim": "Scripted live interaction; no SERVICE macro, corpus rewards, neural learning or shared companies"}
    capture_source(root / "source")
    write_json(root / "run.json", record)
    client = None
    started = time.monotonic()
    try:
        client = LiveV2(args.openttd, root / "worker", seed=args.seed, split=args.split, decisions=args.decisions)
        initial = client.request("OBSERVE")["observation"]
        policy = ServicePolicy(initial, repay=args.policy == "one-bus-repay", minimum_length=args.minimum_route_length,
                               reuse_roads=args.reuse_roads, planner=args.planner, site_checks=args.native_site_checks) if args.policy != "wait" else None
        if policy:
            write_json(root / "plan.json", policy.plan)
        transitions = []
        for index in range(args.decisions):
            observation = initial if index == 0 else client.request("OBSERVE")["observation"]
            candidate = policy.choose(observation) if policy else next(c for c in observation["candidates"] if c["family"] == "WAIT")
            action = client.request("ACT", token=observation["token"], candidate=candidate["key"])
            if action["status"] != "OK" or action["action"]["status"] not in ("SUCCESS", "NO_OP"):
                raise RuntimeError(f"Exposed native action failed: {action}")
            transition = client.request("STEP")["transition"]
            if transition["tick_after"] - transition["tick_before"] != 128:
                raise RuntimeError("Native step budget differs")
            transitions.append(transition)
            if index < 20 or (index + 1) % 128 == 0:
                print(json.dumps({"decision": index + 1, "action": candidate["family"], "economy": transition["after"]}), flush=True)
            if transition["terminal"]:
                break
        final = client.request("OBSERVE")["observation"]
        if not (final["terminal"] or final["truncated"]):
            raise RuntimeError("Interactive episode did not reach its native boundary")
        client.close()
        client = None
        record.update(status="completed", summary=summarize(transitions, initial, final), final_observation=final)
        write_json(root / "summary.json", record["summary"])
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        if client is not None:
            client.abort()
        record["wall_seconds"] = time.monotonic() - started
        write_json(root / "run.json", record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openttd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--split", choices=("training", "development"), default="training")
    parser.add_argument("--decisions", type=positive, default=512)
    parser.add_argument("--policy", choices=("wait", "one-bus", "one-bus-repay"), default="one-bus")
    parser.add_argument("--minimum-route-length", type=int, choices=(8, 10, 12), default=8)
    parser.add_argument("--reuse-roads", action="store_true", help="Allow existing public roads inside a planned straight route")
    parser.add_argument("--planner", choices=("straight", "graph"), default="straight")
    parser.add_argument("--native-site-checks", action="store_true", help="Use native bus catchment/acceptance and avoid new intersections on slopes")
    run(parser.parse_args())
