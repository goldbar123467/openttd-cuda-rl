#!/usr/bin/env python3
"""Mutation tests for M15 stateful episode source evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from artifact_context import ArtifactContext, ArtifactContextError, resolve_artifact_root
from tests.project.v2.test_v2_m15_native_source import make_live_source_fixture
import validate_m15_episode_source


class M15EpisodeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validate_m15_episode_source.load_json(cls.root / validate_m15_episode_source.CONFIG)
        cls.schema = cls.root / validate_m15_episode_source.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "episode-source.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def test_repository_source_delta_passes(self) -> None:
        summary = validate_m15_episode_source.validate(
            self.root,
            artifact_context=ArtifactContext.offline(),
        )
        self.assertEqual(summary.files, 5)

    def test_live_source_and_build_pass(self) -> None:
        summary = validate_m15_episode_source.validate(
            self.root,
            artifact_context=ArtifactContext.live(self.live_base()),
        )
        self.assertTrue(summary.live_source and summary.live_build)

    def test_offline_validation_does_not_open_recorded_base_source(self) -> None:
        with mock.patch.object(
            validate_m15_episode_source,
            "git",
            side_effect=AssertionError("unexpected live access"),
        ) as reader:
            summary = validate_m15_episode_source.validate(
                self.root,
                artifact_context=ArtifactContext.offline(),
            )
        self.assertFalse(summary.live_source or summary.live_build)
        reader.assert_not_called()

    def test_relocated_live_source_and_build_use_one_context(self) -> None:
        recorded_root = self.config["build"]["artifact_root"]
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, schema_path, base_source, result_source = make_live_source_fixture(
                self.root,
                base,
                self.config,
                self.schema,
                patch_relative=self.config["patch"]["path"],
                base_set="v2-m15-action-a",
                base_relative="source",
                result_set="v2-m15-episode-a",
                config_filename="episode-source.json",
            )
            real_git = validate_m15_episode_source.git
            with mock.patch.object(validate_m15_episode_source, "git", wraps=real_git) as reader:
                summary = validate_m15_episode_source.validate(
                    self.root,
                    config_path,
                    schema_path,
                    artifact_context=ArtifactContext.live(base),
                )
        self.assertTrue(summary.live_source and summary.live_build)
        self.assertEqual(value["build"]["artifact_root"], recorded_root)
        read_repositories = {call.args[0] for call in reader.call_args_list}
        self.assertIn(base_source, read_repositories)
        self.assertIn(result_source, read_repositories)

    def test_live_preflight_fails_before_source_read(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with mock.patch.object(
                validate_m15_episode_source,
                "git",
                side_effect=AssertionError("unexpected live read"),
            ) as reader:
                with self.assertRaisesRegex(ArtifactContextError, "missing"):
                    validate_m15_episode_source.validate(
                        self.root,
                        artifact_context=ArtifactContext.live(pathlib.Path(raw).resolve()),
                    )
            reader.assert_not_called()

    def test_required_live_inputs_are_the_exact_episode_source_closure(self) -> None:
        requirements = validate_m15_episode_source.required_live_inputs(self.root)
        self.assertEqual(
            tuple((item.logical_set, item.relative_path, item.kind) for item in requirements),
            (
                ("v2-m15-action-a", "source", "directory"),
                ("v2-m15-action-a", "source/.git", "directory"),
                ("v2-m15-episode-a", "source", "directory"),
                ("v2-m15-episode-a", "source/.git", "directory"),
                ("v2-m15-episode-a", "build/openttd", "file"),
            ),
        )
        self.assertEqual({item.consumer for item in requirements}, {"m15-episode-source"})
        self.assertEqual(requirements[-1].expected_sha256, self.config["build"]["executable"]["sha256"])

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_episode_source.M15EpisodeSourceError, "schema SHA-256"):
                validate_m15_episode_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema, artifact_context=ArtifactContext.offline())

    def test_patch_digest_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["patch"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_episode_source.M15EpisodeSourceError, "patch SHA-256"):
                validate_m15_episode_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema, artifact_context=ArtifactContext.offline())

    def test_result_tree_drift_fails_live(self) -> None:
        value = copy.deepcopy(self.config)
        value["result"]["tree"] = "0" * 40
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(validate_m15_episode_source.M15EpisodeSourceError):
                validate_m15_episode_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema, artifact_context=ArtifactContext.offline())

    def test_executable_identity_drift_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, schema_path, _, _ = make_live_source_fixture(
                self.root,
                base,
                self.config,
                self.schema,
                patch_relative=self.config["patch"]["path"],
                base_set="v2-m15-action-a",
                base_relative="source",
                result_set="v2-m15-episode-a",
                config_filename="episode-source.json",
            )
            value["build"]["executable"]["sha256"] = "0" * 64
            config_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validate_m15_episode_source.validate(self.root, config_path, schema_path, artifact_context=ArtifactContext.live(base))


if __name__ == "__main__":
    unittest.main()
