#!/usr/bin/env python3
"""Acquisition, mutation, and hostile-archive tests for the M14 AI lock."""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import acquire_ai_package


class AIPackageAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.fake_openttd = cls.root / "tests/project/v2/fixtures/fake_openttd_content_server.py"

    def acquire(self, parent: pathlib.Path, mode: str = "success") -> tuple[pathlib.Path, pathlib.Path]:
        artifact_root = parent / "artifact"
        with mock.patch.dict(os.environ, {"FAKE_CONTENT_MODE": mode}):
            lock = acquire_ai_package.acquire(
                self.root,
                self.fake_openttd,
                artifact_root,
                "KrakenAI2",
                startup_timeout=1.0,
                catalog_timeout=1.0,
                download_timeout=1.0,
            )
        return artifact_root, lock

    def test_dependency_complete_acquisition_and_revalidation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            artifact_root, lock = self.acquire(pathlib.Path(raw))
            manifest = acquire_ai_package.validate_lock(self.root, lock, openttd=self.fake_openttd)
            self.assertEqual(manifest["request"]["content_unique_id"], "4b524132")
            self.assertEqual([item["name"] for item in manifest["packages"]], ["FixtureLib", "KrakenAI2"])
            primary = next(item for item in manifest["packages"] if item["name"] == "KrakenAI2")
            self.assertEqual(primary["declared_info"]["author"], "Fixture Author")
            self.assertTrue((artifact_root / acquire_ai_package.TRANSCRIPT_NAME).is_file())

    def test_existing_artifact_root_is_rejected_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            artifact_root = pathlib.Path(raw) / "artifact"
            artifact_root.mkdir()
            marker = artifact_root / "keep"
            marker.write_text("user data\n", encoding="utf-8")
            with self.assertRaisesRegex(acquire_ai_package.AIPackageError, "new path"):
                acquire_ai_package.acquire(self.root, self.fake_openttd, artifact_root, "KrakenAI2")
            self.assertEqual(marker.read_text(encoding="utf-8"), "user data\n")

    def test_catalog_unique_id_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(acquire_ai_package.AIPackageError, "catalog unique ID differs"):
                self.acquire(pathlib.Path(raw), "wrong_uid")

    def test_path_traversal_member_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(acquire_ai_package.AIPackageError, "unsafe archive member"):
                self.acquire(pathlib.Path(raw), "unsafe")
            self.assertFalse((pathlib.Path(raw) / "artifact" / acquire_ai_package.LOCK_NAME).exists())

    def test_package_without_license_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(acquire_ai_package.AIPackageError, "no license/copying"):
                self.acquire(pathlib.Path(raw), "no_license")

    def test_catalog_and_declared_versions_are_recorded_separately(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, lock = self.acquire(pathlib.Path(raw), "declared_version_drift")
            manifest = acquire_ai_package.validate_lock(self.root, lock)
            primary = next(item for item in manifest["packages"] if item["name"] == "KrakenAI2")
            self.assertEqual(primary["version"], 3)
            self.assertEqual(primary["declared_info"]["version"], 2)

    def test_archive_label_sanitization_and_v_prefix_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, lock = self.acquire(pathlib.Path(raw), "archive_label_variant")
            manifest = acquire_ai_package.validate_lock(self.root, lock)
            primary = next(item for item in manifest["packages"] if item["name"] == "KrakenAI2")
            self.assertTrue(primary["archive_path"].endswith("4b524132-Kraken_AI2-v3.tar"))
            self.assertEqual(primary["version"], 3)

    def test_catalog_and_declared_names_are_recorded_separately(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, lock = self.acquire(pathlib.Path(raw), "declared_name_drift")
            manifest = acquire_ai_package.validate_lock(self.root, lock)
            primary = next(item for item in manifest["packages"] if item["name"] == "KrakenAI2")
            self.assertEqual(primary["name"], "KrakenAI2")
            self.assertEqual(primary["declared_info"]["name"], "Kraken AI Two")

    def test_startup_timeout_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            artifact_root = pathlib.Path(raw) / "artifact"
            with mock.patch.dict(os.environ, {"FAKE_CONTENT_MODE": "startup_stall"}):
                with self.assertRaisesRegex(acquire_ai_package.AIPackageError, "timed out"):
                    acquire_ai_package.acquire(
                        self.root,
                        self.fake_openttd,
                        artifact_root,
                        "KrakenAI2",
                        startup_timeout=0.1,
                        catalog_timeout=0.1,
                        download_timeout=0.1,
                    )

    def test_archive_byte_mutation_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            artifact_root, lock = self.acquire(pathlib.Path(raw))
            archive = next((artifact_root / "content_download").rglob("*KrakenAI2*.tar"))
            archive.write_bytes(archive.read_bytes() + b"tamper")
            with self.assertRaisesRegex(acquire_ai_package.AIPackageError, "metadata or bytes"):
                acquire_ai_package.validate_lock(self.root, lock)

    def test_manifest_digest_mutation_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            _, lock = self.acquire(pathlib.Path(raw))
            manifest = json.loads(lock.read_text(encoding="utf-8"))
            manifest["packages"][0]["archive_sha256"] = "0" * 64
            lock.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(acquire_ai_package.AIPackageError, "metadata or bytes"):
                acquire_ai_package.validate_lock(self.root, lock)

    def test_unknown_opponent_is_rejected_before_artifact_creation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            artifact_root = pathlib.Path(raw) / "artifact"
            with self.assertRaisesRegex(acquire_ai_package.AIPackageError, "research baseline"):
                acquire_ai_package.acquire(self.root, self.fake_openttd, artifact_root, "InventedAI")
            self.assertFalse(artifact_root.exists())

    def test_cli_records_catalog_listed_unselectable_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            artifact_root = pathlib.Path(raw) / "artifact"
            with mock.patch.dict(os.environ, {"FAKE_CONTENT_MODE": "unselectable"}):
                result = acquire_ai_package.main(
                    [
                        "--root",
                        str(self.root),
                        "acquire",
                        "--openttd",
                        str(self.fake_openttd),
                        "--artifact-root",
                        str(artifact_root),
                        "--opponent-name",
                        "KrakenAI2",
                        "--startup-timeout",
                        "1",
                        "--catalog-timeout",
                        "0.5",
                        "--download-timeout",
                        "1",
                    ]
                )
            self.assertEqual(result, 1)
            rejection = json.loads((artifact_root / acquire_ai_package.REJECTION_NAME).read_text(encoding="utf-8"))
            self.assertEqual(rejection["reason_code"], "catalog-listed-unselectable")
            self.assertEqual(rejection["request"]["name"], "KrakenAI2")
            self.assertEqual(
                rejection["console_transcript"]["sha256"],
                acquire_ai_package.sha256_file(artifact_root / acquire_ai_package.TRANSCRIPT_NAME),
            )


if __name__ == "__main__":
    unittest.main()
