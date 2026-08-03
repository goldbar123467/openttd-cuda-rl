#!/usr/bin/env python3
"""Tests for the bounded M22 native-trainer corpus representation."""

from __future__ import annotations

import hashlib
import pathlib
import unittest

import encode_m22_native_corpus as encoder


class M22NativeCorpusBinaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.data = encoder.encode(cls.root)

    def mutation_fails(self, data: bytes, pattern: str | None = None) -> None:
        context = (self.assertRaisesRegex(encoder.M22CorpusEncodingError, pattern)
                   if pattern else self.assertRaises(encoder.M22CorpusEncodingError))
        with context:
            encoder.decode(data)

    def test_repository_corpus_round_trips_exactly(self) -> None:
        decoded = encoder.decode(self.data)
        self.assertEqual(decoded.learning_contract_sha256, encoder.sha256(self.root / encoder.CONTRACT))
        self.assertEqual(decoded.corpus_sha256, encoder.sha256(self.root / encoder.CORPUS))
        self.assertEqual(len(decoded.entries), 32)
        self.assertEqual([item.program for item in decoded.entries[:16]], list(range(1, 17)))
        self.assertEqual(self.data, encoder.encode(self.root))
        self.assertEqual(len(hashlib.sha256(self.data).hexdigest()), 64)

    def test_magic_mutation_fails(self) -> None:
        value = bytearray(self.data); value[0] ^= 1
        self.mutation_fails(bytes(value), "magic")

    def test_truncation_fails(self) -> None:
        self.mutation_fails(self.data[:-1], "truncated")

    def test_trailing_bytes_fail(self) -> None:
        self.mutation_fails(self.data + b"x", "trailing")

    def test_split_mutation_fails(self) -> None:
        value = bytearray(self.data); value[144] = 2
        self.mutation_fails(bytes(value), "entry header")

    def test_program_mask_mutation_fails(self) -> None:
        decoded = encoder.decode(self.data)
        first = decoded.entries[0]
        header = 8 + 4 + 64 + 64 + 4 + 10 + len(first.entry_id) + encoder.FEATURES * 4
        value = bytearray(self.data); value[header] = 0
        self.mutation_fails(bytes(value), "program mask")


if __name__ == "__main__":
    unittest.main()
