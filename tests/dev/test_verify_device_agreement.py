"""Fail-closed V1 device replay without training or held-out access."""
import copy
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
import verify_device_agreement as verify


def fixture(sampled=False):
    prediction = dict(action=0 if sampled else 2, log_probability=math.log(.25 if sampled else .75), value=1.,
                      logits=[0.] * 41, probabilities=[.25, 0., .75] + [0.] * 38)
    row = dict(action=prediction["action"], legal=[1, 0, 1] + [0] * 38,
               structured_before=[0.] * 256, prediction=prediction)
    actual = dict(copy.deepcopy(prediction), action=2, log_probability=math.log(.75))
    return row, actual


class AgreementTests(unittest.TestCase):
    def test_sampled_action_is_not_treated_as_greedy(self):
        row, actual = fixture(True)
        result = verify.compare_row(row, actual, "sampled")
        self.assertTrue(result["passed"])
        self.assertIsNone(result["selected_logp_error"])

    def test_identical_greedy_passes(self):
        row, actual = fixture()
        self.assertTrue(verify.compare_row(row, actual, "greedy")["passed"])

    def test_argmax_flip_fails_even_within_probability_tolerance(self):
        row, actual = fixture()
        row["action"] = row["prediction"]["action"] = 0
        row["prediction"]["probabilities"] = [.5, 0, .5] + [0.] * 38
        actual["probabilities"] = [.5 - 1e-7, 0, .5 + 1e-7] + [0.] * 38
        result = verify.compare_row(row, actual, "greedy")
        self.assertFalse(result["passed"])
        self.assertFalse(result["argmax_equal"])
        self.assertEqual(result["probability_failures"], 0)

    def test_fixed_probability_tolerance_rejects_perturbation(self):
        row, actual = fixture()
        actual["probabilities"][0] += 1e-4
        actual["probabilities"][2] -= 1e-4
        self.assertEqual(verify.compare_row(row, actual, "greedy")["probability_failures"], 2)

    def test_selected_logp_checked(self):
        row, actual = fixture()
        actual["log_probability"] += 1e-3
        self.assertFalse(verify.compare_row(row, actual, "greedy")["passed"])

    def test_illegal_probability_must_be_exact_zero(self):
        row, actual = fixture()
        actual["probabilities"][1] = 1e-12
        with self.assertRaisesRegex(ValueError, "legality"):
            verify.compare_row(row, actual, "greedy")

    def test_nonfinite_and_unormalized_predictions_fail(self):
        for value in (float('nan'), float('inf'), -.1, 1.1):
            row, actual = fixture()
            actual["probabilities"][0] = value
            with self.assertRaises(ValueError):
                verify.compare_row(row, actual, "greedy")

    def test_trace_action_and_native_argmax_validated(self):
        row, actual = fixture()
        row["action"] = 0
        with self.assertRaisesRegex(ValueError, "Trace action"):
            verify.compare_row(row, actual, "greedy")
        row, actual = fixture()
        actual["action"] = 0
        with self.assertRaisesRegex(ValueError, "argmax"):
            verify.compare_row(row, actual, "greedy")

    def test_missing_spatial_only_permitted_for_mlp(self):
        row, _ = fixture()
        self.assertEqual(verify.inputs(row, 'structured-mlp-v1')[1], [0.] * 32768)
        for architecture in ('spatial-cnn-v1', 'combined-cnn-mlp-v1'):
            with self.assertRaisesRegex(ValueError, 'retained spatial_before'):
                verify.inputs(row, architecture)
            full = dict(row, spatial_before=[.25] * 32768)
            self.assertEqual(verify.inputs(full, architecture)[1][0], .25)

    def test_invalid_observations_and_mask_rejected(self):
        for key, value in (("structured_before", [0.] * 255), ("structured_before", [float('nan')] * 256),
                           ("legal", [0] * 41), ("legal", [1.] * 41), ("spatial_before", [0.] * 32)):
            row, _ = fixture()
            row[key] = value
            with self.assertRaises(ValueError):
                verify.inputs(row, 'structured-mlp-v1')

    def test_import_response_shape(self):
        client = Mock()
        client._request.return_value = struct.pack('<I', 2)
        with self.assertRaisesRegex(ValueError, 'import response'):
            verify.import_package(client, Path('/model'))

    def test_inspect_response_shape(self):
        client = Mock()
        client._request.return_value = struct.pack('<I', 0)
        with self.assertRaisesRegex(ValueError, 'INSPECT response'):
            verify.inspect(client, [[0.] * 256], [[0.] * 32768], [[1] * 41])

    def test_package_rehash_and_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / 'model.pt'
            model.write_bytes(b'weights')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'model_sha256': verify.sha256(model)}))
            package = root / verify.sha256(manifest)
            package.mkdir()
            model.rename(package / model.name)
            manifest.rename(package / manifest.name)
            self.assertEqual(verify.package_hashes(package)[0]['manifest.json'], package.name)
            (package / 'model.pt').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'content identity'):
                verify.package_hashes(package)


if __name__ == '__main__':
    unittest.main()
