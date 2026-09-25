from argparse import Namespace
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/dev"), str(ROOT / "scripts/v1")]
from trainer_diagnostics import AuditedClient, backend_info
from m08_trainer_client import M08TrainerClientError
from compare_training_backends import exact_comparison


class TrainerDiagnosticsTests(unittest.TestCase):
    def test_native_identity_overrides_build_filename_and_config(self):
        client = Mock()
        client._request.return_value = struct.pack("<II", 1, 9) + b"reference"
        info = backend_info(client, {"configure": ["-DRL_DEV_FUSED_POLICY=ON"]}, "cpu")
        self.assertEqual(info, {"act_distribution": "reference", "provenance": "native-info-v1", "behavior_replay_query": True})
        client._request.assert_called_once_with(7, b"")
        client._request.return_value = struct.pack("<II", 1, 9) + b"fused-cuda"
        with self.assertRaises(ValueError):
            backend_info(client, {}, "cuda:0")  # Wrong declared byte count.
        client._request.return_value = struct.pack("<II", 1, 10) + b"fused-cuda!"
        with self.assertRaises(ValueError):
            backend_info(client, {}, "cuda:0")
        client._request.return_value = struct.pack("<II", 1, 10) + b"fused-cuda"
        self.assertEqual(backend_info(client, {}, "cuda:0")["act_distribution"], "fused-cuda")
        with self.assertRaises(ValueError):
            backend_info(client, {}, "cpu")

    def test_only_unknown_message_permits_explicit_build_fallback(self):
        client = Mock()
        client._request.side_effect = M08TrainerClientError("unknown M08 trainer request type")
        for flag, device, expected in (("ON", "cuda:0", "fused-cuda"), ("ON", "cpu", "reference"), ("OFF", "cuda:0", "reference")):
            info = backend_info(client, {"configure": [f"-DRL_DEV_FUSED_POLICY={flag}"]}, device)
            self.assertEqual(info["act_distribution"], expected)
            self.assertFalse(info["behavior_replay_query"])
        for flags in ([], ["-DRL_DEV_FUSED_POLICY=MAYBE"], ["-DRL_DEV_FUSED_POLICY=ON"] * 2):
            with self.assertRaises(ValueError):
                backend_info(client, {"configure": flags}, "cpu")
        client._request.side_effect = M08TrainerClientError("response was truncated")
        with self.assertRaises(M08TrainerClientError):
            backend_info(client, {"configure": ["-DRL_DEV_FUSED_POLICY=OFF"]}, "cpu")

    def test_query_preserves_frozen_update_result_and_records_error(self):
        client = Mock()
        result = Namespace(update=3)
        client.update.return_value = result
        client._request.return_value = struct.pack("<Idq", 1, 2e-7, 4)
        records = []
        adapter = AuditedClient(client, records)
        self.assertIs(adapter.update([None] * 4), result)
        self.assertEqual(records, [{"update": 3, "samples": 4, "max_abs_log_probability_error": 2e-7}])
        for payload in (b"", struct.pack("<Idq", 2, 0., 4), struct.pack("<Idq", 1, float("nan"), 4),
                        struct.pack("<Idq", 1, .001, 4), struct.pack("<Idq", 1, 0., 3)):
            client._request.return_value = payload
            with self.assertRaises(ValueError):
                adapter.update([None] * 4)
        self.assertEqual(len(records), 1)

    def test_cross_binary_exact_requires_explicit_choice(self):
        with tempfile.TemporaryDirectory() as temporary:
            a, b = Path(temporary) / "a", Path(temporary) / "b"
            a.write_bytes(b"old")
            b.write_bytes(b"new")
            args = Namespace(reference=a, candidate=b, candidate_spatial_validation="vectorized", require_exact=False)
            with self.assertRaises(ValueError):
                exact_comparison(args)
            args.require_exact = True
            self.assertTrue(exact_comparison(args))
            args.candidate_spatial_validation = "reference"
            self.assertTrue(exact_comparison(args))
            args.require_exact = False
            self.assertFalse(exact_comparison(args))


if __name__ == "__main__":
    unittest.main()
