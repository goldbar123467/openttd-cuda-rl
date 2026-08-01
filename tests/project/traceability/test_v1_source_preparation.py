#!/usr/bin/env python3
"""Mutation tests for fail-closed V1 OpenTTD source preparation."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest

import prepare_openttd_source


class V1SourcePreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project_root = pathlib.Path(__file__).resolve().parents[3]
        cls.profile_schema = (
            cls.project_root / "docs/project/schema/v1-source-profile.schema.json"
        )
        cls.manifest_schema = (
            cls.project_root
            / "docs/project/schema/v1-prepared-source-manifest.schema.json"
        )
        cls.profile_schema_sha256 = hashlib.sha256(cls.profile_schema.read_bytes()).hexdigest()

    @staticmethod
    def git(repository: pathlib.Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return result.stdout.strip()

    def make_fixture(self, root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, dict[str, object]]:
        source = root / "source-repository"
        source.mkdir()
        self.git(source, "init", "-q")
        self.git(source, "config", "user.name", "V1 Source Test")
        self.git(source, "config", "user.email", "v1-source-test@example.invalid")
        self.git(source, "remote", "add", "origin", "https://github.com/OpenTTD/OpenTTD.git")
        (source / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.20)\nset(CMAKE_CXX_STANDARD 20)\n",
            encoding="utf-8",
        )
        (source / "COPYING.md").write_text(
            "GNU General Public License\nVersion 2\n",
            encoding="utf-8",
        )
        (source / "README.md").write_text("base\n", encoding="utf-8")
        self.git(source, "add", "-A")
        self.git(source, "commit", "-q", "-m", "fixture")
        commit = self.git(source, "rev-parse", "HEAD")
        tree = self.git(source, "rev-parse", "HEAD^{tree}")

        patch_directory = root / "patches"
        patch_directory.mkdir()
        series = patch_directory / "series"
        series.write_text("# empty fixture series\n", encoding="utf-8")
        profile = {
            "schema_version": "openttd-rl-v1-source-profile-1",
            "schema_sha256": self.profile_schema_sha256,
            "profile_id": "test-source-profile",
            "upstream": {
                "url": "https://github.com/OpenTTD/OpenTTD.git",
                "release": "15.3",
                "commit": commit,
                "tree": tree,
                "cxx_standard": 20,
                "license": "GPL-2.0-only",
            },
            "object_repository": "source-repository",
            "patch_series": {
                "directory": "patches",
                "series_file": "patches/series",
                "series_sha256": hashlib.sha256(series.read_bytes()).hexdigest(),
            },
            "guards": {
                "require_clean_object_repository_worktree": True,
                "reject_unlisted_patches": True,
                "reject_patch_offset_or_fuzz": True,
                "require_unchanged_object_repository": True,
            },
        }
        profile_path = root / "profile.json"
        profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
        return source, profile_path, profile

    def run_prepare(
        self,
        root: pathlib.Path,
        source: pathlib.Path,
        profile_path: pathlib.Path,
    ) -> dict[str, object]:
        return prepare_openttd_source.prepare(
            root=root,
            profile_path=profile_path,
            profile_schema_path=self.profile_schema,
            manifest_schema_path=self.manifest_schema,
            object_repository_override=source,
            output=root / "prepared",
            manifest_path=root / "artifacts/prepared-source.json",
        )

    def test_exact_base_preparation_passes_without_mutating_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            source, profile_path, profile = self.make_fixture(root)
            before_head = self.git(source, "rev-parse", "HEAD")
            manifest = self.run_prepare(root, source, profile_path)
            self.assertEqual(manifest["source"]["commit"], profile["upstream"]["commit"])
            self.assertEqual(manifest["result"]["tree"], profile["upstream"]["tree"])
            self.assertEqual(manifest["result"]["patch_count"], 0)
            self.assertEqual(manifest["result"]["worktree_status"], [])
            self.assertEqual(self.git(source, "rev-parse", "HEAD"), before_head)
            self.assertEqual(self.git(source, "status", "--porcelain=v1"), "")

    def test_dirty_object_repository_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            source, profile_path, _ = self.make_fixture(root)
            (source / "untracked.txt").write_text("dirty\n", encoding="utf-8")
            with self.assertRaisesRegex(
                prepare_openttd_source.SourcePreparationError,
                "worktree is dirty",
            ):
                self.run_prepare(root, source, profile_path)

    def test_series_digest_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            source, profile_path, _ = self.make_fixture(root)
            (root / "patches/series").write_text("# changed\n", encoding="utf-8")
            with self.assertRaisesRegex(
                prepare_openttd_source.SourcePreparationError,
                "series digest mismatch",
            ):
                self.run_prepare(root, source, profile_path)

    def test_unlisted_patch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            source, profile_path, _ = self.make_fixture(root)
            (root / "patches/stray.patch").write_text("not listed\n", encoding="utf-8")
            with self.assertRaisesRegex(
                prepare_openttd_source.SourcePreparationError,
                "listed/present patch mismatch",
            ):
                self.run_prepare(root, source, profile_path)

    def test_base_tree_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            source, profile_path, profile = self.make_fixture(root)
            mutated = copy.deepcopy(profile)
            mutated["upstream"]["tree"] = "0" * 40
            profile_path.write_text(json.dumps(mutated, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(
                prepare_openttd_source.SourcePreparationError,
                "base tree mismatch",
            ):
                self.run_prepare(root, source, profile_path)

    def test_exact_patch_changes_result_identity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            source, profile_path, profile = self.make_fixture(root)
            (source / "README.md").write_text("patched\n", encoding="utf-8")
            patch_text = self.git(source, "diff", "--binary", "--", "README.md") + "\n"
            (source / "README.md").write_text("base\n", encoding="utf-8")
            self.assertEqual(self.git(source, "status", "--porcelain=v1"), "")
            patch = root / "patches/0001-readme.patch"
            patch.write_text(patch_text, encoding="utf-8")
            series = root / "patches/series"
            series.write_text("0001-readme.patch\n", encoding="utf-8")
            profile["patch_series"]["series_sha256"] = hashlib.sha256(
                series.read_bytes()
            ).hexdigest()
            profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")

            manifest = self.run_prepare(root, source, profile_path)
            self.assertEqual(manifest["result"]["patch_count"], 1)
            self.assertEqual(manifest["result"]["worktree_status"], ["M\tREADME.md"])
            self.assertNotEqual(manifest["result"]["tree"], profile["upstream"]["tree"])
            self.assertEqual((root / "prepared/README.md").read_text(encoding="utf-8"), "patched\n")

    def test_existing_output_fails_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            source, profile_path, _ = self.make_fixture(root)
            (root / "prepared").mkdir()
            with self.assertRaisesRegex(
                prepare_openttd_source.SourcePreparationError,
                "output path already exists",
            ):
                self.run_prepare(root, source, profile_path)


if __name__ == "__main__":
    unittest.main()
