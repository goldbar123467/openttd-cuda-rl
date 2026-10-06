from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from order_projection_v3 import project_bytes, VEHICLE_OFFSET, STATION_OFFSET
from v2_onnx_package import financial_features_mode, metadata_for


class OrderProjectionTests(unittest.TestCase):
    def fixture(self):
        obs, actions = bytearray(2182927), bytearray(790528)
        struct.pack_into("<f", obs, 511 * 4, 1)
        struct.pack_into("<f", obs, VEHICLE_OFFSET, 9 / 1044479)
        struct.pack_into("<f", obs, VEHICLE_OFFSET + 2 * 4, 1)
        struct.pack_into("<2f", obs, VEHICLE_OFFSET + 4 * 4, .25, .75)
        obs[VEHICLE_OFFSET + 1024 * 160] = 1
        for row, family in enumerate((6, 7)):
            struct.pack_into("<f", actions, row * 128 + family * 4, 1)
            struct.pack_into("<2f", actions, row * 128 + 56, .25, .75)
            struct.pack_into("<4I", actions, 524288 + row * 64, family, 9, 1 | 0x61 << 16, 0)
            actions[-4096 + row] = 1
        return obs, actions

    def test_projection_preserves_all_other_bytes_and_is_idempotent(self):
        obs, actions = self.fixture()
        projected_obs, projected_actions = project_bytes(obs, actions, public_state={"stations": []})
        self.assertEqual(struct.unpack_from("<f", projected_obs, 511 * 4), (2,))
        self.assertEqual(struct.unpack_from("<6f", projected_actions, 56), (0,) * 6)
        expected_obs, expected_actions = bytearray(obs), bytearray(actions)
        struct.pack_into("<f", expected_obs, 511 * 4, 2)
        struct.pack_into("<2f", expected_actions, 56, 0, 0)
        self.assertEqual(projected_obs, expected_obs)
        self.assertEqual(projected_actions, expected_actions)
        self.assertEqual(project_bytes(projected_obs, projected_actions), (projected_obs, projected_actions))

    def test_unknown_slot_meaning_is_rejected(self):
        for column in range(16, 20):
            obs, actions = self.fixture()
            struct.pack_into("<f", actions, column * 4, .1)
            with self.assertRaisesRegex(ValueError, "occupied"):
                project_bytes(obs, actions)
        obs, actions = self.fixture()
        struct.pack_into("<f", actions, 14 * 4, .1)
        with self.assertRaisesRegex(ValueError, "coordinates"):
            project_bytes(obs, actions)
        obs, actions = self.fixture()
        struct.pack_into("<f", obs, 511 * 4, 2)
        with self.assertRaisesRegex(ValueError, "occupied"):
            project_bytes(obs, actions)

    def test_v3_cannot_be_exported_as_onnx(self):
        self.assertEqual(financial_features_mode("signed-log-orders-v3"), "signed-log-orders-v3")
        with self.assertRaisesRegex(ValueError, "native candidate parameters"):
            metadata_for("signed-log-orders-v3")

    def test_exact_public_passenger_count_replaces_total_cargo_only_in_v3(self):
        obs, actions = self.fixture()
        obs[STATION_OFFSET + 512 * 128] = 1
        struct.pack_into("<f", obs, STATION_OFFSET + 3 * 4, 1)
        struct.pack_into("<f", obs, STATION_OFFSET + 5 * 4, 500 / 65535)
        source = bytes(obs)
        projected, _ = project_bytes(obs, actions, public_state={"stations": [{"id": 0, "waiting_passengers": 425}]})
        self.assertEqual(struct.unpack_from("<f", projected, STATION_OFFSET + 5 * 4),
                         struct.unpack("<f", struct.pack("<f", 425 / 65535)))
        self.assertEqual(bytes(obs), source)
        with self.assertRaisesRegex(ValueError, "requires.*public passenger"):
            project_bytes(obs, actions)
        with self.assertRaisesRegex(ValueError, "station differs"):
            project_bytes(obs, actions, public_state={"stations": [{"id": 1, "waiting_passengers": 425}]})


if __name__ == "__main__":
    unittest.main()
