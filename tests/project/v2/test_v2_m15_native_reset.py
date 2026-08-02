#!/usr/bin/env python3
"""Mutation and live tests for the source-integrated M15 scalable reset."""

from __future__ import annotations

import copy
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

import qualify_m15_native_reset
import validate_m15_native_reset_evidence


class M15NativeResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.matrix_path = cls.root / validate_m15_native_reset_evidence.EVIDENCE
        cls.matrix = validate_m15_native_reset_evidence.load_json(cls.matrix_path)
        cls.schema = cls.root / validate_m15_native_reset_evidence.SCHEMA
        cls.artifact_base = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m15-native-a")
        cls.executable = cls.artifact_base / "build/openttd"
        cls.opengfx = cls.artifact_base / "build/baseset/opengfx-8.0.tar"

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "matrix.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def validate_mutation(self, directory: pathlib.Path, value: object) -> validate_m15_native_reset_evidence.M15NativeResetEvidenceSummary:
        return validate_m15_native_reset_evidence.validate(self.root, self.write(directory, value), self.schema)

    def test_repository_matrix_passes(self) -> None:
        summary = validate_m15_native_reset_evidence.validate(self.root)
        self.assertEqual(summary.runs, 6)
        self.assertEqual(summary.rectangles, 5)

    def test_live_matrix_passes(self) -> None:
        if not self.artifact_base.is_dir():
            self.skipTest("retained M15 native reset artifacts are unavailable")
        summary = validate_m15_native_reset_evidence.validate(self.root, artifact_base=self.artifact_base)
        self.assertTrue(summary.live)

    def test_same_manifest_repeat_is_byte_identical(self) -> None:
        first, second = self.matrix["results"][:2]
        self.assertEqual(first["projection_sha256"], second["projection_sha256"])

    def test_reordered_run_fails(self) -> None:
        value = copy.deepcopy(self.matrix)
        value["results"][0], value["results"][1] = value["results"][1], value["results"][0]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_reset_evidence.M15NativeResetEvidenceError, "order/coverage"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_repeat_projection_drift_fails(self) -> None:
        value = copy.deepcopy(self.matrix)
        value["results"][1]["projection_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_reset_evidence.M15NativeResetEvidenceError, "projections differ"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_town_target_drift_fails(self) -> None:
        value = copy.deepcopy(self.matrix)
        value["results"][2]["towns"] = 3
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_reset_evidence.M15NativeResetEvidenceError, "town target"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_summary_drift_fails(self) -> None:
        value = copy.deepcopy(self.matrix)
        value["summary"]["maximum_rss_kib"] += 1
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_reset_evidence.M15NativeResetEvidenceError, "summary"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_source_identity_drift_fails(self) -> None:
        value = copy.deepcopy(self.matrix)
        value["native_source_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_reset_evidence.M15NativeResetEvidenceError, "source evidence"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_manifest_builder_rejects_unknown_rectangle(self) -> None:
        if not self.executable.is_file() or not self.opengfx.is_file():
            self.skipTest("retained M15 build artifacts are unavailable")
        with self.assertRaisesRegex(qualify_m15_native_reset.M15NativeResetError, "frozen native rectangle"):
            qualify_m15_native_reset.build_manifest(self.root, self.executable, self.opengfx, 32, 32, 1110312784)

    def test_preflight_rejects_before_artifact_creation(self) -> None:
        if not self.executable.is_file() or not self.opengfx.is_file():
            self.skipTest("retained M15 build artifacts are unavailable")
        with tempfile.TemporaryDirectory() as raw:
            target = pathlib.Path(raw) / "must-not-exist"
            with self.assertRaisesRegex(qualify_m15_native_reset.M15NativeResetError, "preallocation budget"):
                qualify_m15_native_reset.qualify(self.root, self.executable, self.opengfx, target, 2048, 1024, 1110312784, sandbox="test-none")
            self.assertFalse(target.exists())

    def test_native_binary_rejects_over_budget_before_projection(self) -> None:
        if not self.executable.is_file() or not self.opengfx.is_file():
            self.skipTest("retained M15 build artifacts are unavailable")
        manifest = qualify_m15_native_reset.build_manifest(self.root, self.executable, self.opengfx, 1024, 1024, 1110312784)
        manifest["map_width"] = 2048
        manifest["map_height"] = 1024
        manifest["town_target"] = 128
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            manifest_path = directory / "manifest.json"
            projection_path = directory / "projection.json"
            manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            environment = dict(os.environ)
            environment["HOME"] = raw
            result = subprocess.run(
                [str(self.executable), "-x", "-X", "-Q", "-I", "OpenGFX", "-v", "null", "-s", "null", "-m", "null", "-V", str(manifest_path), "-U", str(projection_path)],
                cwd=self.executable.parent, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30,
            )
            self.assertIn("tile count exceeds the M15 preflight generation budget", result.stdout)
            self.assertFalse(projection_path.exists())

    def test_projection_request_mutation_fails(self) -> None:
        projection_path = self.artifact_base / "qualified-64-a/reset-projection.json"
        manifest_path = self.artifact_base / "qualified-64-a/reset-manifest.json"
        if not projection_path.is_file() or not manifest_path.is_file():
            self.skipTest("retained M15 reset artifacts are unavailable")
        projection = validate_m15_native_reset_evidence.load_json(projection_path)
        manifest = validate_m15_native_reset_evidence.load_json(manifest_path)
        projection["request"]["simulation_seed"] += 1
        with tempfile.TemporaryDirectory() as raw:
            mutated = pathlib.Path(raw) / "projection.json"
            mutated.write_text(json.dumps(projection) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(qualify_m15_native_reset.M15NativeResetError, "request echo"):
                qualify_m15_native_reset.validate_projection(self.root, manifest, mutated)


if __name__ == "__main__":
    unittest.main()
