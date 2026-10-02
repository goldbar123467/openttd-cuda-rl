"""Independent byte-level validation of the opt-in public bus-order projection."""
import math
import struct

SCHEMA = "v2-m15-public-development-orders-v1"
ACTION_SEMANTICS = "orders-v1"
VEHICLE_OFFSET = 1286927
VEHICLE_MASK = VEHICLE_OFFSET + 1024 * 40 * 4


def description():
    return {"mode": "orders-v1", "maximum_orders": 4, "structured_marker_index": 511,
            "structured_marker_value": 1, "vehicle_columns": {
                "13": "stopped", "14": "cargo_count/65535", "15": "cargo_capacity/65535",
                "16": "order_count/4", "17": "current_real_order_index/255",
                "18": "current_implicit_order_index/255", "19": "current_order_type/255",
                "20:36": "four-[raw_type-plus-256-times-raw_flags,destination,wait_time,travel_time]-blocks-divided-by-65535",
                "36": "current_order_destination/65535", "37": "log1p-current_order_time/log1p-UINT32_MAX",
                "38": "orders_shared", "39": "reserved-zero"},
            "unsupported_state": "fail-closed-on-shared-more-than-four-or-noncanonical-station-orders"}


def expected_vehicle(vehicle):
    orders = vehicle["orders"]
    if vehicle["orders_shared"] or len(orders) > 4 or vehicle["order_count"] != len(orders):
        raise ValueError("Order observation exceeds its complete sequence bound")
    values = [float(vehicle["stopped"]), vehicle["cargo_count"] / 65535,
              vehicle["cargo_capacity"] / 65535, len(orders) / 4,
              vehicle["current_real_order_index"] / 255, vehicle["current_implicit_order_index"] / 255,
              vehicle["current_order_type"] / 255]
    for index in range(4):
        if index >= len(orders):
            values.extend((0, 0, 0, 0))
            continue
        order = orders[index]
        raw = order["serialized"]
        if (order["index"] != index or len(raw) != 11 or raw[0] not in (0x21, 0x61) or
                raw[4] != 254 or raw[9:] != [255, 255] or
                order["type"] != 1 or order["raw_type"] != raw[0] or order["raw_flags"] != raw[1] or
                order["destination"] != raw[2] + 256 * raw[3] or
                order["wait_time"] != raw[5] + 256 * raw[6] or order["travel_time"] != raw[7] + 256 * raw[8] or
                order["load_mode"] != ((raw[1] >> 4) & 7) or order["unload_mode"] != (raw[1] & 7) or
                order["non_stop"] != ((raw[0] >> 6) & 3)):
            raise ValueError("Public order state differs from complete serialized station order")
        values.extend(((order["raw_type"] + 256 * order["raw_flags"]) / 65535, order["destination"] / 65535,
                       order["wait_time"] / 65535, order["travel_time"] / 65535))
    values.extend((vehicle["current_order_destination"] / 65535,
                   math.log1p(vehicle["current_order_time"]) / math.log1p(2**32 - 1),
                   float(vehicle["orders_shared"]), 0))
    return values


def validate_orders(observation, metadata, data):
    if (len(data) != 2182927 or metadata.get("observation_schema_id") != SCHEMA or
            metadata.get("action_semantics") != ACTION_SEMANTICS or metadata.get("order_observation") != description()):
        raise ValueError("Order observation schema, action semantics or projection metadata differs")
    if struct.unpack_from("<f", data, 511 * 4)[0] != 1.0:
        raise ValueError("Order observation marker missing")
    public = {vehicle["id"]: vehicle for vehicle in observation["vehicles"]}
    if len(public) != len(observation["vehicles"]):
        raise ValueError("Public vehicle identities repeat")
    checked = set()
    for row in range(1024):
        if data[VEHICLE_MASK + row] == 0:
            continue
        features = struct.unpack_from("<40f", data, VEHICLE_OFFSET + row * 40 * 4)
        if features[2] != 1 or features[3] != 1:
            continue
        # Pinned VehicleID pool end is 0xFF000; column zero is Unit(id,end-1).
        identity = round(features[0] * (0xFF000 - 1))
        if identity not in public or identity in checked:
            raise ValueError("Order tensor vehicle targeting differs from public identities")
        expected = expected_vehicle(public[identity])
        if any(not math.isclose(actual, value, rel_tol=2e-7, abs_tol=1e-8)
               for actual, value in zip(features[13:40], expected, strict=True)):
            raise ValueError("Order tensor differs from public vehicle sequence/loading/progress state")
        checked.add(identity)
    if checked != public.keys():
        raise ValueError("Order tensor omitted a public vehicle")
