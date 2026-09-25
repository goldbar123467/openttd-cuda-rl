import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from studies.protocol_v2 import load_protocol
from studies.training_result_v2 import early_stop_update


class TrainingStopTests(unittest.TestCase):
    def setUp(self):
        self.protocol = load_protocol()

    def probe(self, update, weak=6, probability=.099):
        return {"update": update, "maps": [{"map_seed": seed, "proposal_probability": probability if i < weak else .5}
                                           for i, seed in enumerate(self.protocol["training_maps"])]}

    def test_first_consecutive_pair_and_strict_probability_boundary(self):
        self.assertIsNone(early_stop_update([self.probe(32)], self.protocol))
        self.assertEqual(early_stop_update([self.probe(32), self.probe(40)], self.protocol), 40)
        self.assertIsNone(early_stop_update([self.probe(32, probability=.1), self.probe(40)], self.protocol))
        rows = [self.probe(32), self.probe(40, weak=5), self.probe(48), self.probe(56), self.probe(64)]
        self.assertEqual(early_stop_update(rows, self.protocol), 56)

    def test_missing_duplicate_wrong_map_invalid_probability_rejected(self):
        good = self.probe(32)
        wrong_map = copy.deepcopy(good)
        wrong_map["maps"][0]["map_seed"] = self.protocol["held_out"]["maps"][0]
        duplicate = copy.deepcopy(good)
        duplicate["maps"][0] = duplicate["maps"][1]
        for rows in ([self.probe(24)], [self.probe(40)], [good, good], [good, self.probe(48)],
                     [wrong_map], [duplicate], [self.probe(32, probability=float("nan"))],
                     [self.probe(32, probability=True)], [self.probe(32, probability=-.01)]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                early_stop_update(rows, self.protocol)


if __name__ == "__main__":
    unittest.main()
