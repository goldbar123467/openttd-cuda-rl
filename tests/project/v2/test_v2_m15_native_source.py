#!/usr/bin/env python3
"""Mutation tests for the M15 source delta and build evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_m15_native_source


class M15NativeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validate_m15_native_source.load_json(cls.root / validate_m15_native_source.CONFIG)
        cls.schema = cls.root / validate_m15_native_source.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "native-source.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def test_repository_source_delta_passes(self) -> None:
        summary = validate_m15_native_source.validate(self.root)
        self.assertEqual(summary.patches, 1)
        self.assertEqual(summary.files, 4)
        self.assertEqual(summary.result_tree, "70394b69df9a6c2104cb711c439da53b2abde367")

    def test_live_source_and_build_pass(self) -> None:
        base = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/m12-release-final-a/composed-source/openttd")
        artifact = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m15-native-a")
        if not base.is_dir() or not artifact.is_dir():
            self.skipTest("retained M15 live source/build artifacts are unavailable")
        summary = validate_m15_native_source.validate(self.root, base_source=base, artifact_root=artifact)
        self.assertTrue(summary.live_source and summary.live_build)

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_source.M15NativeSourceError, "schema SHA-256"):
                validate_m15_native_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_patch_digest_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["patch_series"]["patches"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_source.M15NativeSourceError, "patch SHA-256"):
                validate_m15_native_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_result_tree_drift_fails_live(self) -> None:
        base = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/m12-release-final-a/composed-source/openttd")
        if not base.is_dir():
            self.skipTest("retained V1 source artifact is unavailable")
        value = copy.deepcopy(self.config)
        value["result"]["tree"] = "0" * 40
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_source.M15NativeSourceError, "result tree"):
                validate_m15_native_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema, base_source=base)

    def test_executable_identity_drift_fails_live(self) -> None:
        artifact = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m15-native-a")
        if not artifact.is_dir():
            self.skipTest("retained M15 build artifact is unavailable")
        value = copy.deepcopy(self.config)
        value["build"]["executable"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_source.M15NativeSourceError, "executable SHA-256"):
                validate_m15_native_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema, artifact_root=artifact)


if __name__ == "__main__":
    unittest.main()
