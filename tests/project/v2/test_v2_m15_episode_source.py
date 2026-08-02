#!/usr/bin/env python3
"""Mutation tests for M15 stateful episode source evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

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

    def test_repository_source_delta_passes(self) -> None:
        summary = validate_m15_episode_source.validate(self.root)
        self.assertEqual(summary.files, 5)

    def test_live_source_and_build_pass(self) -> None:
        base = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m15-action-a/source")
        artifact = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m15-episode-a")
        if not base.is_dir() or not artifact.is_dir():
            self.skipTest("retained episode source/build is unavailable")
        summary = validate_m15_episode_source.validate(self.root, base_source=base, artifact_root=artifact)
        self.assertTrue(summary.live_source and summary.live_build)

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_episode_source.M15EpisodeSourceError, "schema SHA-256"):
                validate_m15_episode_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_patch_digest_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["patch"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_episode_source.M15EpisodeSourceError, "patch SHA-256"):
                validate_m15_episode_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_result_tree_drift_fails_live(self) -> None:
        value = copy.deepcopy(self.config)
        value["result"]["tree"] = "0" * 40
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(validate_m15_episode_source.M15EpisodeSourceError):
                validate_m15_episode_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_executable_identity_drift_fails_live(self) -> None:
        artifact = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m15-episode-a")
        if not artifact.is_dir():
            self.skipTest("retained episode build is unavailable")
        value = copy.deepcopy(self.config)
        value["build"]["executable"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(validate_m15_episode_source.M15EpisodeSourceError):
                validate_m15_episode_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema, artifact_root=artifact)


if __name__ == "__main__":
    unittest.main()
