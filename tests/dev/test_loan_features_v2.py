"""Loan preprocessing is native-only until ONNX includes exact action parameters."""
from importlib.util import find_spec
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from v2_onnx_package import financial_features_mode, metadata_for


class LoanFeaturesTests(unittest.TestCase):
    def test_native_mode_is_explicit_and_onnx_metadata_rejects_it(self):
        for mode in ("signed-log-loan-v1", "signed-log-actions-v1", "signed-log-orders-v1", "signed-log-orders-v2"):
            self.assertEqual(financial_features_mode(mode), mode)
            with self.assertRaisesRegex(ValueError, "native candidate parameters"):
                metadata_for(mode)
        self.assertEqual(metadata_for("raw")["openttd_rl.financial_features"], "raw")
        self.assertEqual(metadata_for("signed-log-v1")["openttd_rl.financial_features"], "signed-log-v1")

    @unittest.skipUnless(find_spec("torch") is not None, "direct export test requires the local Torch environment")
    def test_direct_export_adapter_and_loader_reject_before_weights_read(self):
        from v2_export_policy import ExportPolicy, load_export_policy
        for mode in ("signed-log-loan-v1", "signed-log-actions-v1", "signed-log-orders-v1", "signed-log-orders-v2"):
            with self.assertRaisesRegex(ValueError, "native candidate parameters"):
                ExportPolicy(mode)
            with self.assertRaisesRegex(ValueError, "native candidate parameters"):
                load_export_policy("nonexistent-policy.pt", mode)


if __name__ == "__main__":
    unittest.main()
