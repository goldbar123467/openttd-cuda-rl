"""Independent order audit catches plausible semantic substitutions and false fit."""
import copy
from pathlib import Path
import sys
import struct
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from audit_bus_orders_v2 import (VEHICLE_OFFSET, categorical_inputs, decode_packet, order_inventory, public_order_tensor,
                                 route_status, semantic_transition, summarize)


def order(destination=1, flags=0, raw_type=0x61):
    raw = [raw_type, flags, destination & 255, destination >> 8, 254, 0, 0, 0, 0, 255, 255]
    return {"type": 1, "destination": destination, "serialized": raw}


def state(orders1=None, orders2=None):
    lists = {1: orders1 or []}
    if orders2 is not None:
        lists[2] = orders2
    return {"exact_orders": [{"vehicle_id": identity, "orders": orders} for identity, orders in lists.items()],
            "vehicles": [{"id": identity, "stopped": True, "cargo_count": 0, "cargo_capacity": 31,
                          "orders_shared": False} for identity in lists]}


def event(name, packet):
    return {"name": name, "payload": packet}


class BusOrderAuditTests(unittest.TestCase):
    def test_authoritative_packets_keep_vehicle_index_station_and_raw_nonstop(self):
        operation, parameters = decode_packet(event("CmdInsertOrder", "020000000161000200FE00000000FFFF"))
        self.assertEqual(operation, "INSERT_ORDER")
        self.assertEqual(parameters, [6, 2, 1 | 1 << 8 | 0x61 << 16, 2])
        operation, parameters = decode_packet(event("CmdCloneOrder", "010200000001000000"))
        self.assertEqual((operation, parameters), ("COPY_ORDERS", [6, 2, 3, 1]))

    def test_full_load_all_and_shared_copy_are_never_full_load_any_or_copy(self):
        for name, packet in (("CmdModifyOrder", "0100000000030200"),
                             ("CmdCloneOrder", "000200000001000000"),
                             ("CmdInsertOrder", "010000000061300100FE00000000FFFF")):
            with self.subTest(name=name), self.assertRaises(ValueError):
                decode_packet(event(name, packet))

    def test_load_changes_only_selected_order_loading_bits(self):
        before = state([order(1, flags=1), order(0)])
        after = copy.deepcopy(before)
        after["exact_orders"][0]["orders"][1]["serialized"][1] = 48
        command = event("CmdModifyOrder", "0100000001030300")
        self.assertEqual(semantic_transition(command, before, after)["operation"], "FULL_LOAD_ANY")
        for vehicle, index, byte, value in ((0, 0, 1, 0), (0, 1, 0, 0x21), (0, 1, 1, 32)):
            altered = copy.deepcopy(after)
            altered["exact_orders"][vehicle]["orders"][index]["serialized"][byte] = value
            with self.subTest(byte=byte, value=value), self.assertRaises(ValueError):
                semantic_transition(command, before, altered)

    def test_insertion_preserves_existing_order_and_inserts_at_exact_index(self):
        before = state([order(0, flags=48)])
        after = state([order(1), order(0, flags=48)])
        command = event("CmdInsertOrder", "010000000061000100FE00000000FFFF")
        semantic_transition(command, before, after)
        after["exact_orders"][0]["orders"].reverse()
        with self.assertRaises(ValueError):
            semantic_transition(command, before, after)

    def test_copy_requires_source_preserved_and_independent_destination(self):
        before = state([order(1, 48), order(0, 48)], [])
        after = state([order(1, 48), order(0, 48)], [order(1, 48), order(0, 48)])
        command = event("CmdCloneOrder", "010200000001000000")
        semantic_transition(command, before, after)
        after["vehicles"][1]["orders_shared"] = True
        with self.assertRaisesRegex(ValueError, "independent"):
            semantic_transition(command, before, after)
        after["vehicles"][1]["orders_shared"] = False
        after["exact_orders"][0]["orders"].pop()
        with self.assertRaises(ValueError):
            semantic_transition(command, before, after)

    def test_delete_cannot_substitute_declone_or_affect_source_bus(self):
        before = state([order(1, 48), order(0, 48)], [order(1, 48), order(0, 48)])
        after = state([order(1, 48), order(0, 48)], [order(1, 48)])
        semantic_transition(event("CmdDeleteOrder", "0200000001"), before, after)
        with self.assertRaisesRegex(ValueError, "declone"):
            semantic_transition(event("CmdDeleteOrder", "0200000002"), before, after)
        after["exact_orders"][0]["orders"].pop()
        with self.assertRaises(ValueError):
            semantic_transition(event("CmdDeleteOrder", "0200000001"), before, after)

    def test_start_reports_exact_routes_and_loading_before_motion(self):
        before = state([order(1, 48), order(0, 48)])
        after = copy.deepcopy(before)
        after["vehicles"][0]["stopped"] = False
        result = semantic_transition(event("CmdStartStopVehicle", "0100000000"), before, after)
        self.assertEqual(result["before_start"]["route"], [1, 0])
        self.assertTrue(result["before_start"]["both_endpoints_full_load_any"])
        after["vehicles"][0]["stopped"] = True
        with self.assertRaises(ValueError):
            semantic_transition(event("CmdStartStopVehicle", "0100000000"), before, after)

    def test_full_load_all_does_not_pass_full_load_any_before_start(self):
        snapshot = state([order(1, 32), order(0, 48)])
        self.assertFalse(route_status(snapshot, 1)["both_endpoints_full_load_any"])

    def test_serialized_flags_and_order_summary_cannot_disagree(self):
        snapshot = state([order(1)])
        snapshot["exact_orders"][0]["orders"][0]["destination"] = 2
        with self.assertRaises(ValueError):
            order_inventory(snapshot)

    def test_summary_does_not_call_input_alias_or_probability_tie_success(self):
        def row(operation, margin, alias=False):
            prediction = {"exact_row": True, "unique_greedy_target": margin > 1e-6,
                          "target_margin": margin, "target_near_tie_rows": [2] if margin <= 1e-6 else []}
            return {"operation": operation, "prediction": prediction, "permuted_prediction": prediction,
                    "input": {"target_alias_rows": [2] if alias else [], "alias_groups": [dict()] if alias else []},
                    "permutation_probability_max_error": 0}
        result = summarize([row("INSERT_ORDER", 0), row("FULL_LOAD_ANY", .1), row("COPY_ORDERS", .2, True)])
        self.assertEqual(result["overall"]["exact_rows"], 3)
        self.assertEqual(result["overall"]["unique_exact"], 1)
        self.assertEqual(result["overall"]["target_ties"], 1)
        self.assertEqual(result["by_operation"]["COPY_ORDERS"]["target_input_aliases"], 1)

    def test_actual_float32_order_flags_sequence_and_dynamic_timing_are_checked(self):
        snapshot = state([order(1, 48), order(0, 48)])
        snapshot["exact_orders"][0]["orders"][0]["serialized"][5:9] = [40, 1, 55, 6]
        snapshot["vehicles"][0].update(current_real_order_index=0, current_implicit_order_index=0,
                                         current_order_type=1, current_order_destination=1, current_order_time=0)
        data = bytearray(2182927)
        struct.pack_into("<f", data, 511 * 4, 1)
        data[VEHICLE_OFFSET + 1024 * 40 * 4] = 1
        values = [1, 0, 31 / 65535, .5, 0, 0, 1 / 255,
                  0x3061 / 65535, 1 / 65535, 296 / 65535, 1591 / 65535,
                  0x3061 / 65535, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                  1 / 65535, 0, 0, 0]
        struct.pack_into("<27f", data, VEHICLE_OFFSET + 13 * 4, *values)
        self.assertEqual(len(public_order_tensor(snapshot, data)), 1)
        for column, value in ((20, 0x2061 / 65535), (21, 0), (22, 0), (23, 0), (13, 0)):
            changed = bytearray(data)
            struct.pack_into("<f", changed, VEHICLE_OFFSET + column * 4, value)
            with self.subTest(column=column), self.assertRaises(ValueError):
                public_order_tensor(snapshot, changed)

    def test_actual_categorical_encoding_uses_public_operation_loading_and_index(self):
        rows = [
            {"family": 6, "parameters": [6, 1, 2 | 1 << 8 | 3 << 16, 3] + [0] * 12,
             "features": [0, 1, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0] + [0] * 20},
            {"family": 6, "parameters": [6, 2, 3, 1] + [0] * 12,
             "features": [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0] + [0] * 20},
        ]
        self.assertEqual(categorical_inputs({"rows": rows}), {"2": 1, "3": 1})
        rows[0]["features"][6], rows[0]["features"][7] = 0, 1
        with self.assertRaisesRegex(ValueError, "categorical input"):
            categorical_inputs({"rows": rows})


if __name__ == "__main__":
    unittest.main()
