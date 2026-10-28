"""Enumerate every buildable two-stop bus route in a public live V2 observation.

`route_v2.plan_network` returns the single highest-scoring route. Scripted data
collection instead needs all of them: each stop pair that the exposed legal
candidates can connect by road, with the town each stop serves. The geometry
rules (road bits, junctions on flat tiles only, native catchment and acceptance
checks) match `plan_network` with site checks; `route_v2.py` stays unchanged
because checkpoints bind its source.
"""
import hashlib
import heapq
import json

# OpenTTD's NE, SE, SW, NW are -x, +y, +x, -y; ROAD_X is 10 and ROAD_Y is 5.
ROAD_BITS = (8, 4, 2, 1)


def stable_id(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def nearest_town(tile, width, towns):
    """Public geometry only: the closest town centre by Manhattan distance."""
    x, y = tile % width, tile // width
    if not towns:
        return None
    return min(towns, key=lambda town: (abs(town["x"] - x) + abs(town["y"] - y), town["id"]))["id"]


def enumerate_routes(observation, *, minimum_length=8, maximum_tiles=64, stops_per_town=3, routes_per_pair=1):
    """Return (routes, report). Routes are ordered by town pair, then rank."""
    grid = observation["map"]
    width, height = grid["width"], grid["height"]
    clear, houses, flat = set(grid["clear_tiles"]), set(grid["houses"]), set(grid["flat_tiles"])
    existing = {tile: bits for tile, bits in grid["roads"]}
    radius = grid["bus_stop_catchment_radius"]
    towns = sorted(observation["towns"], key=lambda town: town["id"])
    candidates = {(c["family"], tuple(c["parameters"][1:4])): c for c in observation["candidates"]}
    offsets = (-1, width, 1, -width)
    available = dict(existing)
    for family, params in candidates:
        if family == "BUILD_ROAD_PATH" and params[0] not in houses:
            available[params[0]] = available.get(params[0], 0) | params[1]

    def adjacent(tile, direction):
        result = tile + offsets[direction]
        if not 0 <= result < width * height or abs(result % width - tile % width) + abs(result // width - tile // width) != 1:
            return None
        return result

    def coverage(tile):
        return frozenset(h for h in houses if abs(h % width - tile % width) <= radius and abs(h // width - tile // width) <= radius)

    def junction_allowed(tile, bits):
        return tile in flat or not (bits & 5 and bits & 10) or existing.get(tile, 0) & bits == bits

    # Native site checks: full present passenger acceptance and some supply.
    stops = []
    for (family, params), candidate in candidates.items():
        tile, direction, _ = params
        if (family != "BUILD_BUS_STOP" or tile not in clear or candidate["passenger_acceptance_eighths"] < 8 or
                candidate["passenger_production"] == 0):
            continue
        neighbor = adjacent(tile, direction)
        covered = coverage(tile)
        if covered and neighbor in available and available[neighbor] & ROAD_BITS[(direction + 2) % 4]:
            stops.append({"tile": tile, "direction": direction, "neighbor": neighbor, "houses": covered,
                          "town": nearest_town(tile, width, towns), "cost": candidate["cost"],
                          "passenger_production": candidate["passenger_production"]})
    # Keep a few well-covered, mutually separated sites per town so that every
    # town pair is represented without exploring hundreds of adjacent copies.
    selected = []
    for town in towns:
        local = sorted((s for s in stops if s["town"] == town["id"]),
                       key=lambda s: (-len(s["houses"]), s["tile"], s["direction"]))
        chosen = []
        for stop in local:
            if len(chosen) == stops_per_town:
                break
            if all(abs(stop["tile"] % width - c["tile"] % width) + abs(stop["tile"] // width - c["tile"] // width) >= 3
                   for c in chosen):
                chosen.append(stop)
        selected.extend(chosen)
    selected.sort(key=lambda s: (s["tile"], s["direction"]))

    options = {}
    for start in selected:
        first_state = (start["neighbor"], (start["direction"] + 2) % 4)
        distance, previous = {first_state: 0}, {}
        queue = [(0, first_state)]
        while queue:
            cost, state = heapq.heappop(queue)
            tile, incoming = state
            if cost != distance[state]:
                continue
            for direction in range(4):
                neighbor = adjacent(tile, direction)
                if (neighbor == start["tile"] or neighbor not in available or not available[tile] & ROAD_BITS[direction] or
                        not available[neighbor] & ROAD_BITS[(direction + 2) % 4]):
                    continue
                if not junction_allowed(tile, ROAD_BITS[incoming] | ROAD_BITS[direction]):
                    continue
                # Prefer public roads: new road costs money and one decision per axis.
                extra = 1 + (0 if existing.get(neighbor, 0) & ROAD_BITS[(direction + 2) % 4] else 4)
                next_state = (neighbor, (direction + 2) % 4)
                if cost + extra < distance.get(next_state, float("inf")):
                    distance[next_state] = cost + extra
                    previous[next_state] = state
                    heapq.heappush(queue, (cost + extra, next_state))
        for end in selected:
            if end["tile"] <= start["tile"]:
                continue
            separation = abs(start["tile"] % width - end["tile"] % width) + abs(start["tile"] // width - end["tile"] // width)
            unique = (len(start["houses"] - end["houses"]), len(end["houses"] - start["houses"]))
            if separation < minimum_length - 1 or min(unique) == 0:
                continue
            endings = [(distance[(end["neighbor"], incoming)], (end["neighbor"], incoming)) for incoming in range(4)
                       if (end["neighbor"], incoming) in distance and
                       junction_allowed(end["neighbor"], ROAD_BITS[incoming] | ROAD_BITS[(end["direction"] + 2) % 4])]
            if not endings:
                continue
            _, state = min(endings)
            interior = [state[0]]
            while state != first_state:
                state = previous[state]
                interior.append(state[0])
            interior.reverse()
            line = [start["tile"], *interior, end["tile"]]
            if len(set(line)) != len(line) or len(line) > maximum_tiles:
                continue
            needed = {}
            for index, tile in enumerate(interior, 1):
                for other in (line[index - 1], line[index + 1]):
                    needed[tile] = needed.get(tile, 0) | ROAD_BITS[offsets.index(other - tile)]
            depots = []
            for tile in interior:
                for direction in range(4):
                    depot = adjacent(tile, direction)
                    key = ("BUILD_ROAD_DEPOT", (depot, (direction + 2) % 4, 0))
                    if depot in line or depot not in clear or key not in candidates or not available[tile] & ROAD_BITS[direction]:
                        continue
                    bits = dict(needed)
                    bits[tile] |= ROAD_BITS[direction]
                    if not junction_allowed(tile, bits[tile]):
                        continue
                    roads = [("BUILD_ROAD_PATH", (road, axis, 1)) for road, value in bits.items()
                             for axis in (5, 10) if value & axis & ~existing.get(road, 0)]
                    actions = [key, ("BUILD_BUS_STOP", (start["tile"], start["direction"], 0)),
                               ("BUILD_BUS_STOP", (end["tile"], end["direction"], 0)), *roads]
                    if any(action not in candidates for action in actions):
                        continue
                    depots.append((sum(candidates[action]["cost"] for action in actions), len(roads), depot, actions))
            if not depots:
                continue
            construction_cost, new_roads, depot, actions = min(depots)
            pair = tuple(sorted((start["town"], end["town"])))
            route = {"town_pair": list(pair), "kind": "intra-town" if pair[0] == pair[1] else "inter-town",
                     "line": line, "depot": depot, "depot_direction": actions[0][1][1],
                     "stops": [{key: stop[key] for key in ("tile", "direction", "town", "passenger_production")} |
                               {"house_coverage": len(stop["houses"])} for stop in (start, end)],
                     "exclusive_house_coverage": list(unique), "manhattan_separation": separation,
                     "path_tiles": len(line), "new_road_actions": new_roads,
                     "house_score": min(unique) * separation, "estimated_construction_cost": construction_cost,
                     "actions": [[family, list(params)] for family, params in actions]}
            route["route_id"] = stable_id({"line": line, "actions": route["actions"]})
            options.setdefault(pair, []).append(route)
    routes = []
    for pair in sorted(options, key=lambda pair: tuple(-1 if value is None else value for value in pair)):
        ranked = sorted(options[pair], key=lambda r: (-r["house_score"], r["estimated_construction_cost"], r["path_tiles"], r["route_id"]))
        routes.extend(ranked[:routes_per_pair])
    served = {stop["town"] for stop in selected}
    report = {"schema_version": "openttd-rl-route-atlas-v2-1",
              "parameters": {"minimum_length": minimum_length, "maximum_tiles": maximum_tiles,
                             "stops_per_town": stops_per_town, "routes_per_pair": routes_per_pair},
              "towns": [{**town, "exposed_stop_sites": sum(stop["town"] == town["id"] for stop in stops)} for town in towns],
              "towns_without_exposed_stops": [town["id"] for town in towns if town["id"] not in served],
              "stop_sites": len(stops), "selected_stop_sites": len(selected),
              "connectable_pairs": sum(len(value) for value in options.values()), "town_pairs": len(options),
              "routes": len(routes)}
    return routes, report
