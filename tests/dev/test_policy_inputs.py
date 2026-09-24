"""Vectorized checks retain the frozen validator's decoded-JSON semantics."""
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
import train_live
from policy_inputs import spatial_validation, vectorized_spatial


class PolicyInputTests(unittest.TestCase):
    def observation(self):
        rng = random.Random(319)
        return {"spatial": {"shape": [32, 32, 32], "logical_order": "channel-y-x",
                            "data": [rng.random() for _ in range(32768)]}}

    def test_json_scalars_match_reference_without_replacing_values(self):
        observation = self.observation()
        values = observation["spatial"]["data"]
        for value in (0, 1, False, True, 0., 1., 1e-320, .5, -1e-320, 1.0000000000000002,
                      2, -1, 10**90, float("nan"), float("inf"), float("-inf"),
                      "0.5", None, {}, [0.]):
            values[16384] = value
            accepted = []
            for validator in (train_live.m08.spatial, vectorized_spatial):
                try:
                    result = validator(observation)
                    self.assertIs(result, values)
                    accepted.append(True)
                except (ValueError, RuntimeError):
                    accepted.append(False)
            with self.subTest(value=value):
                self.assertEqual(accepted[0], accepted[1])

    def test_shape_order_length_and_scope(self):
        for field, value in (("shape", [32, 32, 31]), ("logical_order", "y-x-channel"), ("data", [0.] * 32767)):
            observation = self.observation()
            observation["spatial"][field] = value
            for validator in (train_live.m08.spatial, vectorized_spatial):
                with self.assertRaises((ValueError, RuntimeError)):
                    validator(observation)
        original = train_live.m08.spatial
        collector = SimpleNamespace(spatial=original)
        with self.assertRaisesRegex(RuntimeError, "deliberate"):
            with spatial_validation(collector, "vectorized"):
                self.assertIs(collector.spatial, vectorized_spatial)
                raise RuntimeError("deliberate")
        self.assertIs(collector.spatial, original)


if __name__ == "__main__":
    unittest.main()
