#!/usr/bin/env python3
"""Offline and relocated-live tests for the native M16 cargo source delta."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from typing import Any
from unittest import mock

from artifact_context import ArtifactContext, ArtifactContextError, resolve_artifact_root
from tests.project.v2.test_v2_m15_native_source import _write_patch_preimage
import validate_m16_cargo_source as validator


def _git(repository: pathlib.Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repository), *arguments],
        text=True,
    ).strip()


def make_live_source_fixture(
    root: pathlib.Path,
    directory: pathlib.Path,
    config: dict[str, Any],
    *,
    base_set: str,
    result_set: str,
) -> tuple[dict[str, Any], pathlib.Path, pathlib.Path, pathlib.Path]:
    """Create real relocated base/result Git repositories and build files."""

    value = copy.deepcopy(config)
    patch = root / value["patch"]["path"]
    base_source = directory / base_set / "source"
    base_source.mkdir(parents=True)
    _write_patch_preimage(patch, base_source)
    subprocess.run(["git", "init", "-q", str(base_source)], check=True)
    for key, setting in (("user.name", "source fixture"), ("user.email", "source-fixture@example.invalid")):
        subprocess.run(["git", "-C", str(base_source), "config", key, setting], check=True)
    subprocess.run(["git", "-C", str(base_source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(base_source), "commit", "-q", "-m", "base"], check=True)
    value["base"]["commit"] = _git(base_source, "rev-parse", "HEAD")
    value["base"]["tree"] = _git(base_source, "rev-parse", "HEAD^{tree}")

    result_source = directory / result_set / "source"
    result_source.parent.mkdir(parents=True)
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(base_source), str(result_source)], check=True)
    for key, setting in (("user.name", "source fixture"), ("user.email", "source-fixture@example.invalid")):
        subprocess.run(["git", "-C", str(result_source), "config", key, setting], check=True)
    subprocess.run(
        ["git", "-C", str(result_source), "apply", "--index", "--whitespace=error-all", str(patch)],
        check=True,
    )
    subprocess.run(["git", "-C", str(result_source), "commit", "-q", "-m", "result"], check=True)
    value["source"]["commit"] = _git(result_source, "rev-parse", "HEAD")
    value["source"]["tree"] = _git(result_source, "rev-parse", "HEAD^{tree}")

    executable = directory / result_set / "build/openttd"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"relocated-openttd-fixture\n")
    value["executable"]["bytes"] = executable.stat().st_size
    value["executable"]["sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    opengfx = directory / result_set / "build/baseset/opengfx-8.0.tar"
    opengfx.parent.mkdir(parents=True)
    opengfx.write_bytes(b"relocated-opengfx-fixture\n")
    value["build"]["open_gfx"]["sha256"] = hashlib.sha256(opengfx.read_bytes()).hexdigest()

    config_path = directory / "source.json"
    config_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return value, config_path, base_source, result_source


class M16CargoSourceTests(unittest.TestCase):
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

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            raised = self.assertRaisesRegex(validator.M16SourceError, pattern) if pattern else self.assertRaises(validator.M16SourceError)
            with raised:
                validator.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=ArtifactContext.offline(),
                )

    def test_repository_source_passes_offline(self) -> None:
        with mock.patch.object(validator, "git", side_effect=AssertionError("unexpected live access")) as reader:
            summary = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertEqual(summary["files"], 8)
        self.assertFalse(summary["live"])
        reader.assert_not_called()

    def test_retained_live_source_build_and_base_pass(self) -> None:
        summary = validator.validate(
            self.root,
            artifact_context=ArtifactContext.live(self.live_base()),
        )
        self.assertTrue(summary["live"])

    def test_required_live_inputs_are_the_exact_source_and_build_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        self.assertEqual(
            tuple((item.logical_set, item.relative_path, item.kind) for item in requirements),
            (
                ("v2-m15-competence-a", "source", "directory"),
                ("v2-m15-competence-a", "source/.git", "directory"),
                ("v2-m16-cargo-a", "source", "directory"),
                ("v2-m16-cargo-a", "source/.git", "directory"),
                ("v2-m16-cargo-a", "build/openttd", "file"),
                ("v2-m16-cargo-a", "build/baseset/opengfx-8.0.tar", "file"),
            ),
        )
        self.assertEqual({item.consumer for item in requirements}, {"m16-cargo-source"})
        self.assertEqual(requirements[-2].expected_sha256, self.config["executable"]["sha256"])
        self.assertEqual(requirements[-1].expected_sha256, self.config["build"]["open_gfx"]["sha256"])

    def test_relocated_live_source_and_build_pass(self) -> None:
        recorded = (
            self.config["retained_artifact"],
            self.config["source"]["path"],
            self.config["executable"]["path"],
            self.config["build"]["open_gfx"]["path"],
        )
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_source_fixture(
                self.root, base, self.config,
                base_set="v2-m15-competence-a", result_set="v2-m16-cargo-a",
            )
            summary = validator.validate(
                self.root,
                config_path,
                self.schema,
                artifact_context=ArtifactContext.live(base),
            )
        self.assertTrue(summary["live"])
        self.assertEqual(
            (value["retained_artifact"], value["source"]["path"], value["executable"]["path"], value["build"]["open_gfx"]["path"]),
            recorded,
        )

    def test_live_preflight_fails_before_git(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with mock.patch.object(validator, "git", side_effect=AssertionError("unexpected live read")) as reader:
                with self.assertRaisesRegex(ArtifactContextError, "missing"):
                    validator.validate(
                        self.root,
                        artifact_context=ArtifactContext.live(pathlib.Path(raw).resolve()),
                    )
            reader.assert_not_called()

    def test_relocated_live_source_ignores_hostile_git_environment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, base_source, _ = make_live_source_fixture(
                self.root, base, self.config,
                base_set="v2-m15-competence-a", result_set="v2-m16-cargo-a",
            )
            hostile = {"GIT_DIR": str(base_source / ".git"), "GIT_WORK_TREE": str(base_source)}
            with mock.patch.dict(os.environ, hostile):
                summary = validator.validate(
                    self.root,
                    config_path,
                    self.schema,
                    artifact_context=ArtifactContext.live(base),
                )
        self.assertTrue(summary["live"])

    def test_patch_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["patch"]["sha256"] = "0" * 64
        self.mutation_fails(value, "patch identity")

    def test_source_tree_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_source_fixture(
                self.root, base, self.config,
                base_set="v2-m15-competence-a", result_set="v2-m16-cargo-a",
            )
            value["source"]["tree"] = "0" * 40
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M16SourceError, "tree"):
                validator.validate(self.root, config_path, self.schema, artifact_context=ArtifactContext.live(base))

    def test_executable_digest_mutation_fails_live_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_source_fixture(
                self.root, base, self.config,
                base_set="v2-m15-competence-a", result_set="v2-m16-cargo-a",
            )
            value["executable"]["sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(self.root, config_path, self.schema, artifact_context=ArtifactContext.live(base))

    def test_executable_size_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_source_fixture(
                self.root, base, self.config,
                base_set="v2-m15-competence-a", result_set="v2-m16-cargo-a",
            )
            value["executable"]["bytes"] += 1
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M16SourceError, "executable identity"):
                validator.validate(self.root, config_path, self.schema, artifact_context=ArtifactContext.live(base))


if __name__ == "__main__":
    unittest.main()
