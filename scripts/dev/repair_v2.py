"""Find a current road connection or a legal detour between existing own stops."""
import heapq


def connection(observation, start, end, *, allow_construction=False):
    grid = observation["map"]
    width, height = grid["width"], grid["height"]
    roads, flat = dict(grid["roads"]), set(grid["flat_tiles"])
    offsets, bits = (-1, width, 1, -width), (8, 4, 2, 1)
    candidates = {(c["parameters"][1], c["parameters"][2]): c
                  for c in observation.get("candidates", [])
                  if allow_construction and c["family"] == "BUILD_ROAD_PATH" and c["parameters"][3] == 1}
    available = dict(roads)
    for (tile, axis), candidate in candidates.items():
        if axis not in (5, 10) or candidate["cost"] < 0:
            raise ValueError("Unexpected primitive road candidate")
        if tile not in (start, end):
            available[tile] = available.get(tile, 0) | axis
    if start == end or start not in roads or end not in roads:
        return None

    def actions_for(tile, needed):
        current = roads.get(tile, 0)
        if current & needed == needed:
            return []
        if tile in (start, end) or (tile not in flat and needed & 5 and needed & 10):
            return None
        actions = []
        for axis in (5, 10):
            if needed & axis & ~current:
                candidate = candidates.get((tile, axis))
                if candidate is None:
                    return None
                actions.append(candidate)
        return actions

    initial = (start, 4)
    distances, previous = {initial: (0, 0)}, {}
    queue = [(0, 0, initial)]
    final = None
    while queue:
        cost, steps, state = heapq.heappop(queue)
        if distances[state] != (cost, steps):
            continue
        tile, incoming = state
        if tile == end:
            final = state
            break
        for direction, offset in enumerate(offsets):
            neighbor = tile + offset
            opposite = (direction + 2) % 4
            if (not 0 <= neighbor < width * height or
                    abs(neighbor % width - tile % width) + abs(neighbor // width - tile // width) != 1 or
                    not available.get(tile, 0) & bits[direction] or
                    not available.get(neighbor, 0) & bits[opposite]):
                continue
            needed = bits[direction] | (bits[incoming] if incoming < 4 else 0)
            actions = actions_for(tile, needed)
            if actions is None:
                continue
            next_state = (neighbor, opposite)
            distance = (cost + sum(c["cost"] for c in actions), steps + 1)
            if distance < distances.get(next_state, (float("inf"), float("inf"))):
                distances[next_state] = distance
                previous[next_state] = state
                heapq.heappush(queue, (*distance, next_state))
    if final is None:
        return None
    states = [final]
    while states[-1] != initial:
        states.append(previous[states[-1]])
    states.reverse()
    line = [state[0] for state in states]
    if len(set(line)) != len(line):
        # Never publish a looping construction plan around a slope constraint.
        return None
    actions = []
    for index, tile in enumerate(line[:-1]):
        direction = offsets.index(line[index + 1] - tile)
        incoming = states[index][1]
        needed = bits[direction] | (bits[incoming] if incoming < 4 else 0)
        actions.extend(actions_for(tile, needed))
    return {"line": line, "estimated_construction_cost": sum(c["cost"] for c in actions),
            "actions": [[c["family"], c["parameters"][1:4]] for c in actions]}
