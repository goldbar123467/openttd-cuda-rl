#!/usr/bin/env python3
"""Mutation tests for the fail-closed V1 dependency cache validator."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import tempfile
import unittest

import validate_dependency_cache


class V1DependencyCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project_root = pathlib.Path(__file__).resolve().parents[3]
        cls.schema = cls.project_root / "docs/project/schema/v1-dependency-lock.schema.json"
        cls.schema_sha256 = hashlib.sha256(cls.schema.read_bytes()).hexdigest()

    def make_fixture(
        self,
        root: pathlib.Path,
    ) -> tuple[pathlib.Path, pathlib.Path, dict[str, object]]:
        cache = root / "cache"
        cache.mkdir()
        artifacts: list[dict[str, object]] = []
        extractions: list[dict[str, object]] = []
        for index, suffix in enumerate(("zip", "tgz", "whl"), 1):
            relative = f"artifact-{index}.{suffix}"
            payload = f"artifact {index}\n".encode()
            (cache / relative).write_bytes(payload)
            extraction_root = cache / f"extracted-{index}"
            extraction_root.mkdir()
            (extraction_root / "MARKER").write_text("present\n", encoding="utf-8")
            artifacts.append(
                {
                    "id": f"fixture-{index}",
                    "component": f"Fixture {index}",
                    "version": "1.0",
                    "kind": suffix if suffix != "whl" else "wheel",
                    "relative_cache_path": relative,
                    "url": f"https://example.invalid/{relative}",
                    "size_bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "license_expression": "MIT",
                    "license_evidence": "fixture metadata",
                    "publication_disposition": "not-published; reacquire from pinned upstream URL",
                }
            )
            extractions.append(
                {
                    "artifact_id": f"fixture-{index}",
                    "relative_root": f"extracted-{index}",
                    "required_markers": ["MARKER"],
                }
            )
        lock: dict[str, object] = {
            "schema_version": "openttd-rl-v1-dependency-lock-1",
            "schema_sha256": self.schema_sha256,
            "profile_id": "ubuntu-24.04-wsl2-x86_64-cuda13",
            "host": {
                "architecture": "x86_64",
                "python": "3.12",
                "cxx": "GCC 13.3.0",
                "cmake": "3.28.3",
                "ninja": "1.11.1",
                "cuda": "13.0.88",
                "gpu_cc": "12.0",
            },
            "policy": {
                "offline_after_acquisition": True,
                "reject_unlisted_archives": True,
                "publish_external_binaries": False,
            },
            "artifacts": artifacts,
            "extractions": extractions,
        }
        lock_path = root / "dependency-lock.json"
        lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
        return cache, lock_path, lock

    def validate(self, cache: pathlib.Path, lock_path: pathlib.Path) -> dict[str, object]:
        return validate_dependency_cache.validate(
            lock_path=lock_path,
            schema_path=self.schema,
            cache_root=cache,
        )

    @staticmethod
    def rewrite(lock_path: pathlib.Path, lock: dict[str, object]) -> None:
        lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

    def test_exact_inventory_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cache, lock_path, _ = self.make_fixture(pathlib.Path(raw))
            result = self.validate(cache, lock_path)
            self.assertEqual(result["result"], "PASS")
            self.assertEqual(result["artifact_count"], 3)

    def test_duplicate_json_key_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cache, lock_path, _ = self.make_fixture(pathlib.Path(raw))
            lock_path.write_text('{"schema_version":"a","schema_version":"b"}\n')
            with self.assertRaisesRegex(
                validate_dependency_cache.DependencyCacheError,
                "duplicate JSON key",
            ):
                self.validate(cache, lock_path)

    def test_schema_digest_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cache, lock_path, lock = self.make_fixture(pathlib.Path(raw))
            lock["schema_sha256"] = "0" * 64
            self.rewrite(lock_path, lock)
            with self.assertRaisesRegex(
                validate_dependency_cache.DependencyCacheError,
                "schema digest mismatch",
            ):
                self.validate(cache, lock_path)

    def test_artifact_digest_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cache, lock_path, lock = self.make_fixture(pathlib.Path(raw))
            lock["artifacts"][0]["sha256"] = "0" * 64
            self.rewrite(lock_path, lock)
            with self.assertRaisesRegex(
                validate_dependency_cache.DependencyCacheError,
                "artifact digest mismatch",
            ):
                self.validate(cache, lock_path)

    def test_artifact_size_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cache, lock_path, lock = self.make_fixture(pathlib.Path(raw))
            lock["artifacts"][0]["size_bytes"] += 1
            self.rewrite(lock_path, lock)
            with self.assertRaisesRegex(
                validate_dependency_cache.DependencyCacheError,
                "artifact size mismatch",
            ):
                self.validate(cache, lock_path)

    def test_missing_artifact_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cache, lock_path, _ = self.make_fixture(pathlib.Path(raw))
            (cache / "artifact-1.zip").unlink()
            with self.assertRaisesRegex(
                validate_dependency_cache.DependencyCacheError,
                "cache archive inventory mismatch",
            ):
                self.validate(cache, lock_path)

    def test_unlisted_artifact_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cache, lock_path, _ = self.make_fixture(pathlib.Path(raw))
            (cache / "stray.whl").write_bytes(b"unlisted")
            with self.assertRaisesRegex(
                validate_dependency_cache.DependencyCacheError,
                "cache archive inventory mismatch",
            ):
                self.validate(cache, lock_path)

    def test_missing_extraction_marker_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cache, lock_path, _ = self.make_fixture(pathlib.Path(raw))
            (cache / "extracted-1/MARKER").unlink()
            with self.assertRaisesRegex(
                validate_dependency_cache.DependencyCacheError,
                "missing extraction marker",
            ):
                self.validate(cache, lock_path)

    def test_duplicate_artifact_id_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            cache, lock_path, lock = self.make_fixture(pathlib.Path(raw))
            mutated = copy.deepcopy(lock)
            mutated["artifacts"][1]["id"] = mutated["artifacts"][0]["id"]
            self.rewrite(lock_path, mutated)
            with self.assertRaisesRegex(
                validate_dependency_cache.DependencyCacheError,
                "artifact ids are not unique",
            ):
                self.validate(cache, lock_path)


if __name__ == "__main__":
    unittest.main()
