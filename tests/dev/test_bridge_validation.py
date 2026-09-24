"""Differential checks against the frozen protocol, including malformed frames."""
import json
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/v1"))
import bridge_validation as fast
import m03_bridge_protocol as reference


class BridgeValidationTests(unittest.TestCase):
    def test_reference_mode_restores_reference_functions(self):
        crc, check = reference.crc32c, reference._response_is_compact_sorted
        try:
            fast.configure("fast")
            self.assertIs(reference.crc32c, fast.crc32c)
            fast.configure("reference")
            self.assertIs(reference.crc32c, crc)
            self.assertIs(reference._response_is_compact_sorted, check)
        finally:
            fast.configure("reference")

    def test_crc_standard_vector_and_reference_byte_patterns(self):
        self.assertEqual(fast.crc32c(b"123456789"), 0xE3069283)
        rng = random.Random(1023)
        cases = [b"", bytes(range(256)), b"\0" * 32768, b"\xff" * 32768]
        cases += [rng.randbytes(length) for length in range(0, 1024, 13)]
        for data in cases:
            self.assertEqual(fast.crc32c(data), reference.crc32c(data))
            self.assertEqual(fast.crc32c(bytearray(data)), reference.crc32c(data))

    def test_normalization_matches_reference_for_strings_numbers_and_layout(self):
        rng = random.Random(1023)
        cases = [{"a": [0, -0., 1e-12, 3e20], "z": '123 " -7.3e4 \\ 42\n'},
                 {"spatial": {"data": [0.] * 32768, "shape": [32, 32, 32]}},
                 {"unicode": "日本語", "control": "\u0000\t\n"}]
        for _ in range(100):
            cases.append({"numbers": [rng.uniform(-100, 100) for _ in range(5)],
                          "strings": [''.join(rng.choices('abc012-+eE.\\"\n', k=30)) for _ in range(3)]})
        for value in cases:
            valid = reference.canonical_bytes(value)
            variants = [valid, json.dumps(value, indent=2).encode(),
                        valid.replace(b'"data":', b'"data" :'), valid + b" ",
                        valid.replace(b"0.0", b"0e0"), valid.replace(b"[32,32,32]", b"[3.2e1,32.0,32]")]
            for payload in variants:
                self.assertEqual(fast.response_is_compact_sorted(value, payload),
                                 reference._response_is_compact_sorted(value, payload))

    def test_string_and_key_changes_are_not_normalized_away(self):
        value = {"a1": "value123", "b": 5.0}
        valid = reference.canonical_bytes(value)
        self.assertTrue(fast.response_is_compact_sorted(value, valid.replace(b"5.0", b"5e0")))
        for changed in (valid.replace(b"a1", b"a2"), valid.replace(b"123", b"124"),
                        b'{"b":5,"a1":"value123"}'):
            self.assertFalse(fast.response_is_compact_sorted(value, changed))


if __name__ == "__main__":
    unittest.main()
