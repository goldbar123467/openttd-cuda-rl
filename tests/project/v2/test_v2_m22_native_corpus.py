#!/usr/bin/env python3
"""Mutation tests for the frozen M22 native-qualified corpus."""

from __future__ import annotations

import copy
import pathlib
import tempfile
import unittest

import validate_m22_native_corpus as validator


class M22NativeCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.corpus = validator.load(cls.root / validator.CORPUS)
        cls.contract = validator.load(cls.root / validator.CONTRACT)

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            corpus_path = directory / "corpus.json"
            corpus_path.write_bytes(validator.canonical(value))
            contract = copy.deepcopy(self.contract)
            contract["identities"]["m22_native_corpus_sha256"] = validator.sha256(corpus_path)
            contract_path = directory / "contract.json"
            contract_path.write_bytes(validator.canonical(contract))
            context = (self.assertRaisesRegex(validator.M22CorpusValidationError, pattern)
                       if pattern else self.assertRaises(validator.M22CorpusValidationError))
            with context:
                validator.validate(self.root, corpus_path, contract_path)

    def test_repository_corpus_passes(self) -> None:
        summary = validator.validate(self.root)
        self.assertEqual((summary.entries, summary.training, summary.development, summary.programs, summary.native_gates),
                         (32, 16, 16, 17, 7))

    def test_schema_hash_mutation_fails(self) -> None:
        value = copy.deepcopy(self.corpus)
        value["schema_sha256"] = "0" * 64
        self.mutation_fails(value, "schema SHA-256")

    def test_source_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.corpus)
        value["sources"][0]["sha256"] = "0" * 64
        self.mutation_fails(value, "exactly rebuild")

    def test_native_reward_mutation_fails(self) -> None:
        value = copy.deepcopy(self.corpus)
        value["entries"][0]["rewards"]["road-passenger"] += 0.25
        self.mutation_fails(value, "exactly rebuild")

    def test_public_state_label_leak_mutation_fails(self) -> None:
        value = copy.deepcopy(self.corpus)
        value["entries"][0]["public_state"]["required_program"] = "road-passenger"
        self.mutation_fails(value, "exactly rebuild")

    def test_final_split_mutation_fails(self) -> None:
        value = copy.deepcopy(self.corpus)
        value["entries"][0]["split"] = "final"
        self.mutation_fails(value)


if __name__ == "__main__":
    unittest.main()
