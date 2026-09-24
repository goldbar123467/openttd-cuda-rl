"""Public-state road graph for the interactive scripted V2 baseline."""
import heapq


def plan_network(observation, *, minimum_length=8, site_checks=False):
    grid = observation["map"]
    width, height = grid["width"], grid["height"]
    clear, houses = set(grid["clear_tiles"]), set(grid["houses"])
    existing = dict(grid["roads"])
    candidates = {(c["family"], tuple(c["parameters"][1:4])): c for c in observation["candidates"]}
    # OpenTTD's NE, SE, SW, NW correspond to -x, +y, +x, -y.
    offsets, road_bits = (-1, width, 1, -width), (8, 4, 2, 1)
    radius = grid["bus_stop_catchment_radius"] if site_checks else 4
    flat = set(grid["flat_tiles"]) if site_checks else set()
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
        return {h for h in houses if abs(h % width - tile % width) <= radius and abs(h // width - tile // width) <= radius}
    def junction_allowed(tile, bits):
        return not site_checks or tile in flat or not (bits & 5 and bits & 10) or existing.get(tile, 0) & bits == bits
    stops = []
    for family, params in candidates:
        tile, direction, _ = params
        if family != "BUILD_BUS_STOP" or tile not in clear:
            continue
        if site_checks:
            candidate = candidates[(family, params)]
            if candidate["passenger_acceptance_eighths"] < 8 or candidate["passenger_production"] == 0:
                continue
        neighbor = adjacent(tile, direction)
        covered = coverage(tile)
        if covered and neighbor in available and available[neighbor] & road_bits[(direction + 2) % 4]:
            stops.append((tile, direction, neighbor, covered))
    stops.sort(key=lambda stop: (stop[0], stop[1]))
    best = None
    for start, start_dir, start_neighbor, start_houses in stops:
        # Costs prefer public roads; no hidden terrain tests or future fares.
        first_state = (start_neighbor, (start_dir + 2) % 4)
        distance, previous = {first_state: 0}, {}
        queue = [(0, first_state)]
        while queue:
            cost, state = heapq.heappop(queue)
            tile, incoming = state
            if cost != distance[state]:
                continue
            for direction in range(4):
                neighbor = adjacent(tile, direction)
                if neighbor == start or neighbor not in available or not available[tile] & road_bits[direction] or not available[neighbor] & road_bits[(direction + 2) % 4]:
                    continue
                if not junction_allowed(tile, road_bits[incoming] | road_bits[direction]):
                    continue
                extra = 1 + (0 if existing.get(neighbor, 0) & road_bits[(direction + 2) % 4] else 4)
                next_state = (neighbor, (direction + 2) % 4)
                if cost + extra < distance.get(next_state, float("inf")):
                    distance[next_state] = cost + extra
                    previous[next_state] = state
                    heapq.heappush(queue, (cost + extra, next_state))
        for end, end_dir, end_neighbor, end_houses in stops:
            separation = abs(start % width - end % width) + abs(start // width - end // width)
            if end <= start or separation < minimum_length - 1:
                continue
            # Distinct catchments avoid overvaluing houses served by both stops.
            unique = (len(start_houses - end_houses), len(end_houses - start_houses))
            if min(unique) == 0:
                continue
            score = min(unique) * separation
            if best is not None and score < -best[0][0]:
                continue
            endings = [(distance[(end_neighbor, incoming)], (end_neighbor, incoming)) for incoming in range(4)
                       if (end_neighbor, incoming) in distance and junction_allowed(end_neighbor, road_bits[incoming] | road_bits[(end_dir + 2) % 4])]
            if not endings:
                continue
            _, state = min(endings)
            interior = [state[0]]
            while state != first_state:
                state = previous[state]
                interior.append(state[0])
            interior.reverse()
            line = [start, *interior, end]
            if len(set(line)) != len(line) or len(line) > 40:
                continue
            needed = {}
            for index, tile in enumerate(interior, 1):
                for other in (line[index - 1], line[index + 1]):
                    direction = offsets.index(other - tile)
                    needed[tile] = needed.get(tile, 0) | road_bits[direction]
            depot_options = []
            for tile in interior:
                for direction in range(4):
                    depot = adjacent(tile, direction)
                    if depot in line or depot not in clear:
                        continue
                    depot_direction = (direction + 2) % 4
                    depot_key = ("BUILD_ROAD_DEPOT", (depot, depot_direction, 0))
                    if depot_key not in candidates or not available[tile] & road_bits[direction]:
                        continue
                    with_junction = dict(needed)
                    with_junction[tile] |= road_bits[direction]
                    if not junction_allowed(tile, with_junction[tile]):
                        continue
                    actions = []
                    for road, bits in with_junction.items():
                        for axis in (5, 10):
                            if bits & axis & ~existing.get(road, 0):
                                actions.append(("BUILD_ROAD_PATH", (road, axis, 1)))
                    actions += [("BUILD_BUS_STOP", (start, start_dir, 0)), ("BUILD_BUS_STOP", (end, end_dir, 0)), depot_key]
                    if any(action not in candidates for action in actions):
                        continue
                    construction_cost = sum(candidates[action]["cost"] for action in actions)
                    depot_options.append((construction_cost, depot, depot_direction, actions))
            if not depot_options:
                continue
            construction_cost, depot, depot_direction, actions = min(depot_options)
            rank = (-score, construction_cost, len(line), start, end, start_dir, end_dir)
            if best is None or rank < best[0]:
                best = rank, {"planner": "public-road-graph", "line": line, "depot": depot,
                              "depot_direction": depot_direction, "house_coverage": [len(start_houses), len(end_houses)],
                              "exclusive_house_coverage": list(unique), "manhattan_separation": separation,
                              "native_site_checks": site_checks, "catchment_radius": radius,
                              "house_score": score, "estimated_construction_cost": construction_cost,
                              "actions": [[family, list(params)] for family, params in actions]}
    if best is None:
        raise RuntimeError("No connected public-road route exists among the exposed legal candidates")
    return best[1]
