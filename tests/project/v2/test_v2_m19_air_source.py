#!/usr/bin/env python3
"""Mutation tests for the native M19 aircraft source delta."""

from __future__ import annotations

import copy
import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from artifact_context import ARTIFACT_ROOT_ENV, ArtifactContext, ArtifactContextError, resolve_artifact_root
from tests.project.v2.test_v2_m16_cargo_source import make_live_source_fixture
import validate_m19_air_source as validator


class M19AirSourceTests(unittest.TestCase):
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

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validator.M19SourceError, pattern) if pattern else self.assertRaises(validator.M19SourceError)
            with context:
                validator.validate(self.root, self.write(pathlib.Path(raw), value), self.schema,
                                   artifact_context=ArtifactContext.offline())

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def test_repository_source_passes(self) -> None:
        with mock.patch.object(validator, "git", side_effect=AssertionError("unexpected live access")) as reader:
            summary = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertEqual(summary["files"], 4)
        self.assertFalse(summary["live"])
        reader.assert_not_called()

    def test_live_source_build_and_base_pass(self) -> None:
        self.assertTrue(validator.validate(
            self.root,
            artifact_context=ArtifactContext.live(self.live_base()),
        )["live"])

    def test_required_live_inputs_are_the_exact_source_and_build_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        self.assertEqual(
            tuple((item.logical_set, item.relative_path, item.kind) for item in requirements),
            (
                ("v2-m18-ship-a", "source", "directory"),
                ("v2-m18-ship-a", "source/.git", "directory"),
                ("v2-m19-air-a", "source", "directory"),
                ("v2-m19-air-a", "source/.git", "directory"),
                ("v2-m19-air-a", "build/openttd", "file"),
                ("v2-m19-air-a", "build/baseset/opengfx-8.0.tar", "file"),
            ),
        )
        self.assertEqual({item.consumer for item in requirements}, {"m19-air-source"})

    def test_relocated_live_source_and_build_pass(self) -> None:
        recorded = copy.deepcopy(self.config)
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_source_fixture(
                self.root, base, self.config,
                base_set="v2-m18-ship-a", result_set="v2-m19-air-a",
            )
            summary = validator.validate(self.root, config_path, self.schema,
                                         artifact_context=ArtifactContext.live(base))
        self.assertTrue(summary["live"])
        self.assertEqual(value["retained_artifact"], recorded["retained_artifact"])
        self.assertEqual(value["source"]["path"], recorded["source"]["path"])
        self.assertEqual(self.config, recorded)

    def test_live_preflight_fails_before_git(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with mock.patch.object(validator, "git", side_effect=AssertionError("unexpected live read")) as reader:
                with self.assertRaisesRegex(ArtifactContextError, "missing"):
                    validator.validate(self.root, artifact_context=ArtifactContext.live(pathlib.Path(raw).resolve()))
            reader.assert_not_called()

    def test_relocated_source_ignores_hostile_git_environment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, base_source, _ = make_live_source_fixture(
                self.root, base, self.config,
                base_set="v2-m18-ship-a", result_set="v2-m19-air-a",
            )
            with mock.patch.dict(os.environ, {"GIT_DIR": str(base_source / ".git"), "GIT_WORK_TREE": str(base_source)}):
                summary = validator.validate(self.root, config_path, self.schema,
                                             artifact_context=ArtifactContext.live(base))
        self.assertTrue(summary["live"])

    def test_patch_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["patch"]["sha256"] = "0" * 64
        self.mutation_fails(value, "patch identity")

    def test_source_tree_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_source_fixture(
                self.root, base, self.config,
                base_set="v2-m18-ship-a", result_set="v2-m19-air-a",
            )
            value["source"]["tree"] = "0" * 40
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M19SourceError, "tree"):
                validator.validate(self.root, config_path, self.schema,
                                   artifact_context=ArtifactContext.live(base))

    def test_executable_digest_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_source_fixture(
                self.root, base, self.config,
                base_set="v2-m18-ship-a", result_set="v2-m19-air-a",
            )
            value["executable"]["sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(self.root, config_path, self.schema,
                                   artifact_context=ArtifactContext.live(base))

    def test_upstream_ctest_mutation_fails_offline(self) -> None:
        value = copy.deepcopy(self.config)
        value["build"]["upstream_ctest"]["passed"] = 97
        self.mutation_fails(value, "upstream_ctest")

    def test_removed_base_source_option_exits_two(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                validator.main(["--root", str(self.root), "--base" + "-source", str(self.root)])
        self.assertEqual(raised.exception.code, 2)

    def test_cli_artifact_root_wins_over_environment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = pathlib.Path(raw).resolve()
            configured = parent / "configured"
            configured.mkdir()
            _, config_path, _, _ = make_live_source_fixture(
                self.root, configured, self.config,
                base_set="v2-m18-ship-a", result_set="v2-m19-air-a",
            )
            with mock.patch.dict(os.environ, {ARTIFACT_ROOT_ENV: str(parent / "wrong")}, clear=False):
                with contextlib.redirect_stdout(io.StringIO()):
                    status = validator.main([
                        "--root", str(self.root),
                        "--config", str(config_path),
                        "--schema", str(self.schema),
                        "--artifact-root", str(configured),
                    ])
        self.assertEqual(status, 0)

    def test_relative_cli_artifact_root_fails_without_environment_fallback(self) -> None:
        with mock.patch.dict(os.environ, {ARTIFACT_ROOT_ENV: str(self.root)}, clear=False):
            with contextlib.redirect_stdout(io.StringIO()):
                status = validator.main(["--root", str(self.root), "--artifact-root", "relative/artifacts"])
        self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
