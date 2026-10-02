import copy
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from orders_observation_v2 import SCHEMA, VEHICLE_OFFSET, VEHICLE_MASK, description, expected_vehicle, validate_orders


class OrderObservationTests(unittest.TestCase):
    def fixture(self):
        vehicle = {"id": 1, "stopped": True, "cargo_count": 0, "cargo_capacity": 31, "order_count": 1,
            "current_real_order_index": 0, "current_implicit_order_index": 0, "current_order_type": 0,
            "current_order_destination": 65535, "current_order_time": 0, "orders_shared": False,
            "orders": [{"index": 0, "type": 1, "raw_type": 97, "raw_flags": 48, "destination": 2,
                        "load_mode": 3, "unload_mode": 0, "non_stop": 1, "wait_time": 112, "travel_time": 42,
                        "serialized": [97, 48, 2, 0, 254, 112, 0, 42, 0, 255, 255]}]}
        observation = {"vehicles": [vehicle]}
        metadata = {"observation_schema_id": SCHEMA, "action_semantics": "orders-v1", "order_observation": description()}
        data = bytearray(2182927)
        struct.pack_into("<f", data, 511 * 4, 1)
        values = [1 / (0xFF000 - 1), 0, 1, 1] + [0] * 9 + expected_vehicle(vehicle)
        struct.pack_into("<40f", data, VEHICLE_OFFSET, *values)
        data[VEHICLE_MASK] = 1
        return observation, metadata, data

    def test_exact_sequence_and_flags_validate(self):
        validate_orders(*self.fixture())

    def test_different_supported_load_flags_or_target_cannot_pass(self):
        for field, value in (("raw_flags", 32), ("destination", 1), ("load_mode", 2)):
            observation, metadata, data = self.fixture()
            observation["vehicles"][0]["orders"][0][field] = value
            with self.assertRaises(ValueError):
                validate_orders(observation, metadata, data)
        observation, metadata, data = self.fixture()
        observation["vehicles"][0]["id"] = 2
        with self.assertRaisesRegex(ValueError, "targeting"):
            validate_orders(observation, metadata, data)

    def test_tensor_state_changes_and_old_schema_reject(self):
        for column in (13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 36, 37, 38, 39):
            observation, metadata, data = self.fixture()
            struct.pack_into("<f", data, VEHICLE_OFFSET + column * 4, 0.4321)
            with self.assertRaisesRegex(ValueError, "differs from public"):
                validate_orders(observation, metadata, data)
        observation, metadata, data = self.fixture()
        metadata["observation_schema_id"] = "v2-m15-public-development-finance-v1"
        with self.assertRaisesRegex(ValueError, "schema"):
            validate_orders(observation, metadata, data)

    def test_unobserved_tail_and_truncation_reject(self):
        observation, _, _ = self.fixture()
        vehicle = observation["vehicles"][0]
        vehicle["orders"] *= 5
        vehicle["order_count"] = 5
        with self.assertRaisesRegex(ValueError, "bound"):
            expected_vehicle(vehicle)
        observation, _, _ = self.fixture()
        vehicle = copy.deepcopy(observation["vehicles"][0])
        vehicle["orders"][0]["serialized"][9] = 1
        with self.assertRaisesRegex(ValueError, "serialized"):
            expected_vehicle(vehicle)


if __name__ == "__main__":
    unittest.main()
