#!/usr/bin/env python3
"""Mutation tests for the M15 hierarchical-action source evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_m15_action_source


class M15ActionSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validate_m15_action_source.load_json(cls.root / validate_m15_action_source.CONFIG)
        cls.schema = cls.root / validate_m15_action_source.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "action-source.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def test_repository_source_delta_passes(self) -> None:
        summary = validate_m15_action_source.validate(self.root)
        self.assertEqual(summary.files, 8)
        self.assertEqual(summary.result_tree, "52e0c3452b84b8324b83ac0958b9b34995b74de8")

    def test_live_source_and_build_pass(self) -> None:
        base = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m15-observation-a/source")
        artifact = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m15-action-a")
        if not base.is_dir() or not artifact.is_dir():
            self.skipTest("retained M15 source/build artifacts are unavailable")
        summary = validate_m15_action_source.validate(self.root, base_source=base, artifact_root=artifact)
        self.assertTrue(summary.live_source and summary.live_build)

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_action_source.M15ActionSourceError, "schema SHA-256"):
                validate_m15_action_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_patch_digest_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["patch"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_action_source.M15ActionSourceError, "patch SHA-256"):
                validate_m15_action_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_result_tree_drift_fails_live(self) -> None:
        base = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m15-observation-a/source")
        if not base.is_dir():
            self.skipTest("retained M15 source artifact is unavailable")
        value = copy.deepcopy(self.config)
        value["result"]["tree"] = "0" * 40
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_action_source.M15ActionSourceError, "result[/ ]tree"):
                validate_m15_action_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema, base_source=base)

    def test_executable_identity_drift_fails_live(self) -> None:
        artifact = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m15-action-a")
        if not artifact.is_dir():
            self.skipTest("retained M15 build artifact is unavailable")
        value = copy.deepcopy(self.config)
        value["build"]["executable"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_action_source.M15ActionSourceError, "executable SHA-256"):
                validate_m15_action_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema, artifact_root=artifact)


if __name__ == "__main__":
    unittest.main()
