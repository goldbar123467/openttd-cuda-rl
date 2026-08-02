#!/usr/bin/env python3
"""Runtime start/save/load, rejection, and mutation tests for M14 external AIs."""

from __future__ import annotations

import os
import pathlib
import tempfile
import unittest
from unittest import mock

import acquire_ai_package
import qualify_ai_runtime


class AIRuntimeQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.fake_openttd = cls.root / "tests/project/v2/fixtures/fake_openttd_content_server.py"

    def acquire_lock(self, parent: pathlib.Path) -> pathlib.Path:
        with mock.patch.dict(os.environ, {"FAKE_CONTENT_MODE": "success"}):
            return acquire_ai_package.acquire(
                self.root,
                self.fake_openttd,
                parent / "package",
                "KrakenAI2",
                startup_timeout=1.0,
                catalog_timeout=1.0,
                download_timeout=1.0,
            )

    def qualify(self, parent: pathlib.Path, mode: str = "success") -> tuple[pathlib.Path, pathlib.Path]:
        lock = self.acquire_lock(parent)
        artifact_root = parent / "runtime"
        with mock.patch.dict(os.environ, {"FAKE_CONTENT_MODE": mode}):
            manifest = qualify_ai_runtime.qualify(
                self.root,
                self.fake_openttd,
                lock,
                artifact_root,
                seed=123,
                minimum_days=3,
                timeout=3.0,
                sandbox="test-none",
            )
        return artifact_root, manifest

    def test_active_ai_survives_start_days_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            artifact_root, manifest_path = self.qualify(pathlib.Path(raw))
            manifest = qualify_ai_runtime.validate_manifest(self.root, manifest_path, openttd=self.fake_openttd)
            self.assertEqual(manifest["outcome"], "QUALIFIED_ACTIVE")
            self.assertTrue(all(manifest["checks"].values()))
            self.assertEqual(manifest["observations"]["company_after_load"]["road_vehicles"], 1)
            self.assertTrue((artifact_root / "save/v2-qualification.sav").is_file())

    def test_healthy_inactive_ai_is_distinguished_from_active(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, manifest_path = self.qualify(pathlib.Path(raw), "runtime_inactive")
            manifest = qualify_ai_runtime.validate_manifest(self.root, manifest_path)
            self.assertEqual(manifest["outcome"], "QUALIFIED_HEALTHY_INACTIVE")
            self.assertTrue(all(manifest["checks"].values()))

    def test_script_crash_is_retained_as_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, manifest_path = self.qualify(pathlib.Path(raw), "runtime_crash")
            manifest = qualify_ai_runtime.validate_manifest(self.root, manifest_path)
            self.assertEqual(manifest["outcome"], "REJECTED")
            self.assertFalse(manifest["checks"]["no_script_crash"])
            self.assertTrue(any("fixture crash" in detail for detail in manifest["error_details"]))

    def test_existing_artifact_root_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = pathlib.Path(raw)
            lock = self.acquire_lock(parent)
            artifact_root = parent / "runtime"
            artifact_root.mkdir()
            marker = artifact_root / "keep"
            marker.write_text("user data\n", encoding="utf-8")
            with self.assertRaisesRegex(qualify_ai_runtime.AIRuntimeError, "new absolute path"):
                qualify_ai_runtime.qualify(
                    self.root,
                    self.fake_openttd,
                    lock,
                    artifact_root,
                    seed=1,
                    minimum_days=1,
                    timeout=1,
                    sandbox="test-none",
                )
            self.assertEqual(marker.read_text(encoding="utf-8"), "user data\n")

    def test_savegame_byte_mutation_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            artifact_root, manifest_path = self.qualify(pathlib.Path(raw))
            save = artifact_root / "save/v2-qualification.sav"
            save.write_bytes(save.read_bytes() + b"tamper")
            with self.assertRaisesRegex(qualify_ai_runtime.AIRuntimeError, "savegame size mismatch"):
                qualify_ai_runtime.validate_manifest(self.root, manifest_path)

    def test_transcript_byte_mutation_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            artifact_root, manifest_path = self.qualify(pathlib.Path(raw))
            transcript = artifact_root / qualify_ai_runtime.TRANSCRIPT_NAME
            transcript.write_text(transcript.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")
            with self.assertRaisesRegex(qualify_ai_runtime.AIRuntimeError, "transcript SHA-256 mismatch"):
                qualify_ai_runtime.validate_manifest(self.root, manifest_path)

    def test_copied_package_byte_mutation_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            artifact_root, manifest_path = self.qualify(pathlib.Path(raw))
            archive = next((artifact_root / "content_download").rglob("*.tar"))
            archive.chmod(0o644)
            archive.write_bytes(archive.read_bytes() + b"tamper")
            with self.assertRaisesRegex(qualify_ai_runtime.AIRuntimeError, "package closure failed"):
                qualify_ai_runtime.validate_manifest(self.root, manifest_path)


if __name__ == "__main__":
    unittest.main()
