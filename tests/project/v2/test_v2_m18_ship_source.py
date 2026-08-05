#!/usr/bin/env python3
"""Offline and relocated-live tests for the native M18 ship source delta."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from artifact_context import ArtifactContext, ArtifactContextError, resolve_artifact_root
from tests.project.v2.test_v2_m16_cargo_source import make_live_source_fixture
import validate_m18_ship_source as validator


class M18ShipSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validator.load(cls.root / validator.CONFIG)
        cls.schema = cls.root / validator.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "source.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raised = self.assertRaisesRegex(validator.M18SourceError, pattern) if pattern else self.assertRaises(validator.M18SourceError)
            with raised:
                validator.validate(self.root, self.write(pathlib.Path(raw), value), self.schema, artifact_context=ArtifactContext.offline())

    def test_repository_source_passes_offline(self) -> None:
        with mock.patch.object(validator, "git", side_effect=AssertionError("unexpected live access")) as reader:
            summary = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertEqual(summary["files"], 4)
        self.assertFalse(summary["live"])
        reader.assert_not_called()

    def test_retained_live_source_build_and_base_pass(self) -> None:
        summary = validator.validate(self.root, artifact_context=ArtifactContext.live(self.live_base()))
        self.assertTrue(summary["live"])

    def test_required_live_inputs_are_the_exact_source_and_build_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        self.assertEqual(
            tuple((item.logical_set, item.relative_path, item.kind) for item in requirements),
            (
                ("v2-m17-rail-a", "source", "directory"),
                ("v2-m17-rail-a", "source/.git", "directory"),
                ("v2-m18-ship-a", "source", "directory"),
                ("v2-m18-ship-a", "source/.git", "directory"),
                ("v2-m18-ship-a", "build/openttd", "file"),
                ("v2-m18-ship-a", "build/baseset/opengfx-8.0.tar", "file"),
            ),
        )
        self.assertEqual({item.consumer for item in requirements}, {"m18-ship-source"})
        self.assertEqual(requirements[-2].expected_sha256, self.config["executable"]["sha256"])
        self.assertEqual(requirements[-1].expected_sha256, self.config["build"]["open_gfx"]["sha256"])

    def test_relocated_live_source_and_build_pass(self) -> None:
        recorded = (self.config["retained_artifact"], self.config["source"]["path"], self.config["executable"]["path"], self.config["build"]["open_gfx"]["path"])
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_source_fixture(
                self.root, base, self.config,
                base_set="v2-m17-rail-a", result_set="v2-m18-ship-a",
            )
            summary = validator.validate(self.root, config_path, self.schema, artifact_context=ArtifactContext.live(base))
        self.assertTrue(summary["live"])
        self.assertEqual((value["retained_artifact"], value["source"]["path"], value["executable"]["path"], value["build"]["open_gfx"]["path"]), recorded)

    def test_live_preflight_fails_before_git(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with mock.patch.object(validator, "git", side_effect=AssertionError("unexpected live read")) as reader:
                with self.assertRaisesRegex(ArtifactContextError, "missing"):
                    validator.validate(self.root, artifact_context=ArtifactContext.live(pathlib.Path(raw).resolve()))
            reader.assert_not_called()

    def test_patch_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["patch"]["sha256"] = "0" * 64
        self.mutation_fails(value, "patch identity")

    def test_source_tree_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_source_fixture(self.root, base, self.config, base_set="v2-m17-rail-a", result_set="v2-m18-ship-a")
            value["source"]["tree"] = "0" * 40
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M18SourceError, "tree"):
                validator.validate(self.root, config_path, self.schema, artifact_context=ArtifactContext.live(base))

    def test_executable_digest_mutation_fails_live_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_source_fixture(self.root, base, self.config, base_set="v2-m17-rail-a", result_set="v2-m18-ship-a")
            value["executable"]["sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(self.root, config_path, self.schema, artifact_context=ArtifactContext.live(base))

    def test_executable_size_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_source_fixture(self.root, base, self.config, base_set="v2-m17-rail-a", result_set="v2-m18-ship-a")
            value["executable"]["bytes"] += 1
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M18SourceError, "executable identity"):
                validator.validate(self.root, config_path, self.schema, artifact_context=ArtifactContext.live(base))


if __name__ == "__main__":
    unittest.main()
