#!/usr/bin/env python3
"""Mutation tests for scenario-qualified M18 ShipAI evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import validate_m18_shipai_evidence as validator


class M18ShipAIEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validator.load(cls.root / validator.CONFIG)

    def validate_mutation(self, value: object) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "shipai.json"
            path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with mock.patch.object(validator, "CONFIG", path):
                validator.validate(self.root)

    def test_repository_evidence_passes(self) -> None:
        self.assertEqual(validator.validate(self.root)["ships"], 2)

    def test_scenario_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["scenario"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(validator.M18ShipAIError, "scenario identity"):
            self.validate_mutation(value)

    def test_m14_disposition_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["m14"]["evidence_sha256"] = "0" * 64
        with self.assertRaisesRegex(validator.M18ShipAIError, "runtime disposition"):
            self.validate_mutation(value)

    def test_package_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["package"]["archive_sha256"] = "0" * 64
        with self.assertRaisesRegex(validator.M18ShipAIError, "package projection"):
            self.validate_mutation(value)

    def test_ship_projection_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["observations"]["ships_after_load"] += 1
        with self.assertRaisesRegex(validator.M18ShipAIError, "observation projection"):
            self.validate_mutation(value)


if __name__ == "__main__":
    unittest.main()
