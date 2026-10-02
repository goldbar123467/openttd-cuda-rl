"""Finance projection audits reject ineffective limits and inconsistent debt."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from verify_v2_finance import SCHEMA, expected_features, legacy_view, validate_finance
from finance_observation_v2 import field_descriptions, MAXIMUM_LOAN_ENCODING


class FinanceObservationTests(unittest.TestCase):
    def fixture(self):
        finance = {"maximum_loan": 300000, "borrowing_headroom": 190000, "interest_rate_percent": 2,
                   "quarter_income": 1000, "quarter_expenses": -250, "quarter_operating_profit": 750,
                   "year_interest_paid": 166}
        observation = {"economy": {"loan": 110000, "balance": 109750, "finance": finance}}
        metadata = {"observation_schema_id": SCHEMA, "finance_observation": {"values": dict(finance),
                    "mode": "finance-v1", "structured": field_descriptions(),
                    "company_maximum_loan": MAXIMUM_LOAN_ENCODING, "quarter_expenses_sign": "native-negative-expense"}}
        data = bytearray(2182927)
        struct.pack_into("<7f", data, 16 * 4, *expected_features(finance))
        struct.pack_into("<f", data, 1181696 + 16, .0003)
        return observation, metadata, data

    def test_corrected_effective_limit_and_signed_expenses_are_valid(self):
        observation, metadata, data = self.fixture()
        validate_finance(observation, metadata, data)
        values = struct.unpack_from("<7f", data, 16 * 4)
        self.assertGreater(values[0], values[1])
        self.assertAlmostEqual(values[2], .02)
        self.assertLess(values[4], 0)

    def test_legacy_maximum_loan_sentinel_cannot_pass_as_effective_limit(self):
        observation, metadata, data = self.fixture()
        struct.pack_into("<f", data, 1181696 + 16, 1.0)
        with self.assertRaisesRegex(ValueError, "effective maximum loan"):
            validate_finance(observation, metadata, data)

    def test_headroom_must_use_actual_outstanding_principal(self):
        observation, metadata, data = self.fixture()
        observation["economy"]["loan"] = 100000
        with self.assertRaisesRegex(ValueError, "headroom"):
            validate_finance(observation, metadata, data)

    def test_corrupt_interest_feature_is_rejected(self):
        observation, metadata, data = self.fixture()
        struct.pack_into("<f", data, 18 * 4, 2.0)
        with self.assertRaisesRegex(ValueError, "projection"):
            validate_finance(observation, metadata, data)

    def test_changed_field_encoding_and_nonfinite_raw_values_are_rejected(self):
        observation, metadata, data = self.fixture()
        metadata["finance_observation"]["structured"][2]["encoding"] = "unscaled-percent"
        with self.assertRaisesRegex(ValueError, "encodings"):
            validate_finance(observation, metadata, data)
        observation, metadata, data = self.fixture()
        observation["economy"]["finance"]["interest_rate_percent"] = float("nan")
        with self.assertRaisesRegex(ValueError, "native integer"):
            validate_finance(observation, metadata, data)

    def test_legacy_comparison_retains_principal_profit_and_actions(self):
        row = {"before": {"loan": 100000, "finance": {"maximum_loan": 300000}},
               "after": {"loan": 110000, "operating_profit": -10},
               "action": {"family": "MANAGE_LOAN", "parameters": [11, 1, 10000]}}
        result = legacy_view([row])[0]
        self.assertEqual(result["before"], {"loan": 100000})
        self.assertEqual(result["after"], row["after"])
        self.assertEqual(result["action"], row["action"])


if __name__ == "__main__":
    unittest.main()
