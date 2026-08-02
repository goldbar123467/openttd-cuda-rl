#!/usr/bin/env python3
"""Mutation tests for the native M18 ship source delta."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_m18_ship_source as validator


class M18ShipSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validator.load(cls.root / validator.CONFIG)
        cls.schema = cls.root / validator.SCHEMA
        cls.artifact = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m18-ship-a")
        cls.base = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m17-rail-a/source")

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "source.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None, *, live: bool = False) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validator.M18SourceError, pattern) if pattern else self.assertRaises(validator.M18SourceError)
            with context:
                validator.validate(self.root, self.write(pathlib.Path(raw), value), self.schema,
                                   artifact_root=self.artifact if live else None)

    def test_repository_source_passes(self) -> None:
        self.assertEqual(validator.validate(self.root)["files"], 4)

    def test_live_source_build_and_base_pass(self) -> None:
        if not self.artifact.is_dir() or not self.base.is_dir():
            self.skipTest("retained native sources are unavailable")
        self.assertTrue(validator.validate(self.root, artifact_root=self.artifact, base_source=self.base)["live"])

    def test_patch_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["patch"]["sha256"] = "0" * 64
        self.mutation_fails(value, "patch identity")

    def test_source_tree_mutation_fails_live(self) -> None:
        value = copy.deepcopy(self.config); value["source"]["tree"] = "0" * 40
        self.mutation_fails(value, "tree", live=True)

    def test_executable_digest_mutation_fails_live(self) -> None:
        value = copy.deepcopy(self.config); value["executable"]["sha256"] = "0" * 64
        self.mutation_fails(value, "executable identity", live=True)

    def test_executable_size_mutation_fails_live(self) -> None:
        value = copy.deepcopy(self.config); value["executable"]["bytes"] += 1
        self.mutation_fails(value, "executable identity", live=True)


if __name__ == "__main__":
    unittest.main()
