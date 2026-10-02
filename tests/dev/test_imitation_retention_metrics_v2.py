"""Ties must remain visible through import and training-retention reports."""
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from audit_imitation_retention_v2 import summary
from imitation_prediction_metrics_v2 import prediction_metrics, prediction_summary
import verify_imitation_v2


def prediction(target_probability, *, selected=None, family=7):
    probabilities = [0.0] * 4096
    probabilities[1], probabilities[2] = target_probability, 1 - target_probability
    chosen = selected if selected is not None else (1 if target_probability >= 0.5 else 2)
    native = {"row": chosen, "probabilities": probabilities, "value": 2.0, "entropy": 1.0}
    label = {"action_row": 1, "action_family": family, "legal_rows": [1, 2]}
    return native, label


def metrics(target_probability, **kwargs):
    return prediction_metrics(*prediction(target_probability, **kwargs))


class ImitationRetentionMetricTests(unittest.TestCase):
    def test_first_row_tie_stays_legacy_correct_but_not_unique(self):
        item = metrics(0.5)
        result = prediction_summary([item])
        self.assertTrue(item["exact_row"])
        self.assertTrue(item["target_tied"])
        self.assertFalse(item["unique_exact"])
        self.assertEqual(item["target_margin"], 0)
        self.assertEqual(result["exact_rows"], 1)
        self.assertEqual(result["accuracy"], 1)
        self.assertEqual(result["unique_exact_rows"], 0)
        self.assertEqual(result["unique_exact_accuracy"], 0)
        self.assertEqual(result["tied_target_count"], 1)
        self.assertFalse(result["all_unique_exact"])

    def test_near_tie_and_second_row_tie_do_not_count_as_unique(self):
        for item in (metrics(0.50000025), metrics(0.5, selected=2)):
            with self.subTest(item=item):
                self.assertTrue(item["target_tied"])
                self.assertFalse(item["unique_exact"])
        self.assertTrue(metrics(0.500001)["unique_exact"])

    def test_retention_counts_unique_forgetting_even_when_exact_row_stays(self):
        rows = [
            {"target_family": 7, "imitation": metrics(0.5), "ppo": metrics(0.8)},
            {"target_family": 11, "imitation": metrics(0.9), "ppo": metrics(0.5)},
            {"target_family": 11, "imitation": metrics(0.9), "ppo": metrics(0.3)},
        ]
        result = summary(rows)
        self.assertEqual(result["all"]["imitation"]["exact_rows"], 3)
        self.assertEqual(result["all"]["imitation"]["unique_exact_rows"], 2)
        self.assertEqual(result["all"]["ppo"]["exact_rows"], 2)
        self.assertEqual(result["all"]["ppo"]["unique_exact_rows"], 1)
        self.assertEqual(result["all"]["forgotten_exact_rows"], 1)
        self.assertEqual(result["all"]["forgotten_unique_choices"], 2)
        self.assertEqual(result["all"]["gained_unique_choices"], 1)
        self.assertEqual(result["11"]["forgotten_unique_choices"], 2)
        self.assertEqual(result["7"]["forgotten_unique_choices"], 0)
        self.assertAlmostEqual(result["all"]["ppo"]["minimum_target_margin"], -0.4)

    def test_a_low_probability_tie_is_not_a_tie_for_the_best_action(self):
        native, label = prediction(0.0)
        label["legal_rows"].append(3)
        item = prediction_metrics(native, label)
        self.assertEqual(item["target_near_tie_rows"], [3])
        self.assertFalse(item["target_tied"])
        self.assertFalse(item["unique_exact"])
        self.assertIsNone(prediction_summary([item])["mean_negative_log_likelihood"])

    def test_invalid_native_probability_distribution_fails_closed(self):
        native, label = prediction(0.9)
        native["probabilities"][3] = 0.1
        with self.assertRaisesRegex(ValueError, "legal distribution"):
            prediction_metrics(native, label)

    def test_human_import_parity_can_pass_while_unique_reproduction_is_false(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidates.bin"
            data = bytearray(790528)
            struct.pack_into("<2I", data, 4096 * 128 + 64, 7, 1)
            struct.pack_into("<2I", data, 4096 * 128 + 128, 7, 2)
            data[-4096 + 1] = data[-4096 + 2] = 1
            candidate.write_bytes(data)
            native, label = prediction(0.5)
            label.update(sample_id="tied-start", archived_tensors={
                "observation": {"path": str(root / "observation.bin")}, "candidate": {"path": str(candidate)}})
            labels = root / "labels.json"
            labels.write_text(json.dumps({"records": [label]}))
            run = {"dataset": {"labels": {"path": str(labels)}}}
            ancestry = {"weights": str(root / "weights.pt")}

            class Client:
                def __init__(self, *args, **kwargs):
                    pass

                def request(self, command):
                    if command == "RESET":
                        return {}
                    if command.startswith("PROBE\t"):
                        return {"proposal_probability": 0.5, "value": 2.0, "entropy": 1.0}
                    return native

                def close(self):
                    pass

                def abort(self):
                    pass

            args = SimpleNamespace(output=root / "report", build_dir=root, imitation_run=root,
                                   financial_features="signed-log-actions-v1", device="cpu")
            with patch.object(verify_imitation_v2, "checked_imitation_run", return_value=(run, ancestry)), \
                    patch.object(verify_imitation_v2, "source_identity", return_value={}), \
                    patch.object(verify_imitation_v2, "host", return_value={}), \
                    patch.object(verify_imitation_v2, "PolicyClient", Client), \
                    patch.object(verify_imitation_v2, "import_imitation", return_value={"status": "IMPORTED_WEIGHTS"}):
                verify_imitation_v2.human_import(args)
            report = json.loads((args.output / "report.json").read_text())
            self.assertEqual(report["status"], "passed")
            self.assertIn("import parity", report["claim"])
            self.assertEqual(report["summary"]["exact_rows"], 1)
            self.assertEqual(report["summary"]["unique_exact_rows"], 0)
            self.assertEqual(report["by_family"]["7"]["tied_target_count"], 1)
            self.assertTrue(report["checks"][0]["target_tied"])
            self.assertFalse(report["checks"][0]["unique_exact"])


if __name__ == "__main__":
    unittest.main()
