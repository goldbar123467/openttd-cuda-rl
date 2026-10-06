"""Explicit conversion of public orders-v1 tensors for the native v3 reader.

Native slots 14/15 hold redundant bus coordinates, contrary to the original
proposal. Only this authorized projection clears them; native C++ then requires
all six slots to be zero. Original tensors, actions and masks remain intact.
"""
import hashlib
import json
from pathlib import Path
import struct

MODE = "signed-log-orders-v3"
PROJECTION = "openttd-rl-public-orders-v3-projection-1"
OBSERVATION_BYTES, CANDIDATE_BYTES = 2182927, 790528
VEHICLE_OFFSET = 1286927
STATION_OFFSET = 1220879


def project_bytes(observation, candidates, *, public_state=None):
    if len(observation) != OBSERVATION_BYTES or len(candidates) != CANDIDATE_BYTES:
        raise ValueError("V3 projection tensor sizes differ")
    marker = struct.unpack_from("<f", observation, 511 * 4)[0]
    if marker not in (1.0, 2.0):
        raise ValueError("V3 projection requires a versioned public order observation")
    vehicles = {}
    for row in range(1024):
        if observation[VEHICLE_OFFSET + 1024 * 160 + row] != 1:
            continue
        values = struct.unpack_from("<40f", observation, VEHICLE_OFFSET + row * 160)
        if values[2] != 1:
            continue
        identity = round(values[0] * 1044479)
        if identity in vehicles:
            raise ValueError("V3 projection repeats a public vehicle identity")
        vehicles[identity] = values[4:6]
    projected = bytearray(candidates)
    for row, legal in enumerate(candidates[-4096:]):
        if legal not in (0, 1):
            raise ValueError("V3 projection requires a binary legal mask")
        if not legal:
            continue
        family, vehicle = struct.unpack_from("<2I", candidates, 524288 + row * 64)
        if family != 6:
            continue
        fields = struct.unpack_from("<6f", candidates, row * 128 + 56)
        if any(fields[2:]) or (marker == 2 and any(fields)):
            raise ValueError("V3 projection refuses occupied reserved order slots")
        if marker == 1 and (vehicle not in vehicles or fields[:2] != vehicles[vehicle]):
            raise ValueError("V3 projection native coordinates differ from the public target vehicle")
        struct.pack_into("<6f", projected, row * 128 + 56, *([0.0] * 6))
    obs = bytearray(observation)
    if marker == 1:
        if public_state is None:
            raise ValueError("V3 projection requires the matching public passenger counts")
        stops = {stop["id"]: stop["waiting_passengers"] for stop in public_state["stations"]}
        if len(stops) != len(public_state["stations"]) or any(type(count) is not int or count < 0 for count in stops.values()):
            raise ValueError("V3 public passenger counts/identities differ")
        encoded_stops = set()
        for row in range(512):
            if observation[STATION_OFFSET + 512 * 128 + row] != 1:
                continue
            values = struct.unpack_from("<32f", observation, STATION_OFFSET + row * 128)
            if values[3] != 1:
                continue
            identity = round(values[0] * 63999)
            if identity not in stops or identity in encoded_stops:
                raise ValueError("V3 public passenger station differs from tensor identity")
            encoded_stops.add(identity)
            # Original column 5 sums all cargo (including mail). Bind the
            # requested passenger-only metric from this same public snapshot.
            struct.pack_into("<f", obs, STATION_OFFSET + row * 128 + 5 * 4, min(stops[identity], 65535) / 65535)
        if encoded_stops != stops.keys():
            raise ValueError("V3 public passenger stations are truncated or missing")
    struct.pack_into("<f", obs, 511 * 4, 2.0)
    return bytes(obs), bytes(projected)


def project_pair(observation, candidates, output, *, public_state=None):
    observation, candidates, output = Path(observation), Path(candidates), Path(output)
    original = observation.read_bytes(), candidates.read_bytes()
    projected = project_bytes(*original, public_state=public_state)
    output.mkdir(parents=True, exist_ok=True)
    paths = output / "observation.bin", output / "candidates.bin"
    for path, data in zip(paths, projected):
        path.write_bytes(data)
    digest = lambda data: hashlib.sha256(data).hexdigest()
    return paths, {"schema_version": PROJECTION,
                   "source_paths": [str(observation.resolve()), str(candidates.resolve())],
                   "source_sha256": list(map(digest, original)),
                   "public_passenger_counts": ({str(stop["id"]): stop["waiting_passengers"] for stop in public_state["stations"]}
                                               if public_state is not None else None),
                   "public_state_sha256": (digest(json.dumps(public_state, sort_keys=True, separators=(",", ":")).encode())
                                           if public_state is not None else None),
                   "projected_sha256": list(map(digest, projected)),
                   "legal_mask_and_parameters_unchanged": True}
