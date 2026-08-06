#!/usr/bin/env python3
"""Mutation tests for the native M20 competition source delta."""

from __future__ import annotations

import copy
import contextlib
import hashlib
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Any
from unittest import mock

from artifact_context import ArtifactContext, ArtifactContextError, resolve_artifact_root
from tests.project.v2.test_v2_m16_cargo_source import make_live_source_fixture as make_git_fixture
import validate_m20_competition_source as validator


def make_custom_record_fixture(
    repository_root: pathlib.Path,
    directory: pathlib.Path,
    config: dict[str, Any],
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    project_root = directory / "project"
    patch = project_root / config["patch"]["path"]
    patch.parent.mkdir(parents=True)
    shutil.copyfile(repository_root / config["patch"]["path"], patch)
    content_path = project_root / config["runtime"]["content_manifest"]
    content_path.parent.mkdir(parents=True)
    shutil.copyfile(repository_root / config["runtime"]["content_manifest"], content_path)
    config_path = directory / "source.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return project_root, config_path, content_path


def make_repository_record_fixture(
    repository_root: pathlib.Path,
    directory: pathlib.Path,
) -> tuple[pathlib.Path, pathlib.Path]:
    config = validator.load(repository_root / validator.CONFIG)
    project_root, _, content_path = make_custom_record_fixture(repository_root, directory, config)
    for relative in (
        validator.CONFIG,
        validator.SCHEMA,
        pathlib.Path("config/v2/m20-competition-contract.json"),
    ):
        target = project_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository_root / relative, target)
    return project_root, content_path


def make_live_source_fixture(
    repository_root: pathlib.Path,
    directory: pathlib.Path,
    config: dict[str, Any],
) -> tuple[pathlib.Path, dict[str, Any], pathlib.Path]:
    project_root = directory / "project"
    patch = project_root / config["patch"]["path"]
    patch.parent.mkdir(parents=True)
    shutil.copyfile(repository_root / config["patch"]["path"], patch)
    content = validator.load(repository_root / config["runtime"]["content_manifest"])
    content_path = project_root / config["runtime"]["content_manifest"]
    content_path.parent.mkdir(parents=True)
    content_path.write_text(json.dumps(content) + "\n", encoding="utf-8")

    value, config_path, _, _ = make_git_fixture(
        project_root,
        directory,
        config,
        base_set="v2-m19-air-a",
        result_set="v2-m20-competition-a",
    )
    result_root = directory / "v2-m20-competition-a"
    source_executable = result_root / "build/openttd"
    executable = result_root / "build-competition/openttd"
    executable.parent.mkdir(parents=True)
    shutil.copyfile(source_executable, executable)
    source_opengfx = result_root / "build/baseset/opengfx-8.0.tar"
    opengfx = result_root / "build-competition/baseset/opengfx-8.0.tar"
    opengfx.parent.mkdir(parents=True)
    shutil.copyfile(source_opengfx, opengfx)
    value["executable"]["bytes"] = executable.stat().st_size
    value["executable"]["sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    value["build"]["open_gfx"]["sha256"] = hashlib.sha256(opengfx.read_bytes()).hexdigest()
    runtime_config = result_root / "openttd.cfg"
    runtime_config.write_text("[fixture]\n", encoding="utf-8")
    value["runtime"]["config"]["sha256"] = hashlib.sha256(runtime_config.read_bytes()).hexdigest()

    content_records = [content["base_graphics"], *content["ai_archives"], *content["libraries"]]
    for index, record in enumerate(content_records):
        relative = pathlib.PurePosixPath(record["path"]).relative_to(pathlib.PurePosixPath(value["retained_artifact"]))
        path = result_root.joinpath(*relative.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == pathlib.PurePosixPath("build-competition/baseset/opengfx-8.0.tar"):
            payload = opengfx.read_bytes()
        else:
            payload = f"relocated-content-{index}\n".encode()
            path.write_bytes(payload)
        record["sha256"] = hashlib.sha256(payload).hexdigest()
    content_path.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
    config_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return project_root, value, config_path


class M20CompetitionSourceTests(unittest.TestCase):
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

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validator.M20SourceError, pattern) if pattern else self.assertRaises(validator.M20SourceError)
            with context:
                validator.validate(self.root, self.write(pathlib.Path(raw), value), self.schema,
                                   artifact_context=ArtifactContext.offline())

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def test_live_source_build_content_and_base_pass(self) -> None:
        summary = validator.validate(self.root, artifact_context=ArtifactContext.live(self.live_base()))
        self.assertTrue(summary["live"])
        self.assertEqual(summary["content_files"], 8)

    def test_required_live_inputs_are_the_exact_source_runtime_and_content_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        self.assertEqual(
            tuple((item.logical_set, item.relative_path, item.kind) for item in requirements[:7]),
            (
                ("v2-m19-air-a", "source", "directory"),
                ("v2-m19-air-a", "source/.git", "directory"),
                ("v2-m20-competition-a", "source", "directory"),
                ("v2-m20-competition-a", "source/.git", "directory"),
                ("v2-m20-competition-a", "build-competition/openttd", "file"),
                ("v2-m20-competition-a", "build-competition/baseset/opengfx-8.0.tar", "file"),
                ("v2-m20-competition-a", "openttd.cfg", "file"),
            ),
        )
        content = validator.load(self.root / self.config["runtime"]["content_manifest"])
        expected_content = {
            pathlib.PurePosixPath(record["path"]).relative_to(pathlib.PurePosixPath(self.config["retained_artifact"])).as_posix()
            for record in [content["base_graphics"], *content["ai_archives"], *content["libraries"]]
        }
        self.assertEqual({item.relative_path for item in requirements[7:]}, expected_content - {"build-competition/baseset/opengfx-8.0.tar"})
        self.assertEqual(len(requirements), 14)
        self.assertEqual({item.consumer for item in requirements}, {"m20-competition-source"})

    def test_relocated_live_source_runtime_and_content_pass(self) -> None:
        recorded = copy.deepcopy(self.config)
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            project_root, value, config_path = make_live_source_fixture(self.root, base, self.config)
            summary = validator.validate(project_root, config_path, self.schema,
                                         artifact_context=ArtifactContext.live(base))
        self.assertTrue(summary["live"])
        self.assertEqual(value["retained_artifact"], recorded["retained_artifact"])
        self.assertEqual(value["source"]["path"], recorded["source"]["path"])
        self.assertEqual(self.config, recorded)

    def test_custom_content_manifest_ai_omission_fails_offline(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project_root, config_path, content_path = make_custom_record_fixture(
                self.root, pathlib.Path(raw), self.config,
            )
            content = validator.load(content_path)
            content["ai_archives"].pop()
            content_path.write_text(json.dumps(content) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M20SourceError, "content inventory"):
                validator.validate(project_root, config_path, self.schema,
                                   artifact_context=ArtifactContext.offline())

    def test_custom_base_graphics_split_from_core_opengfx_fails_offline(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project_root, config_path, content_path = make_custom_record_fixture(
                self.root, pathlib.Path(raw), self.config,
            )
            content = validator.load(content_path)
            content["base_graphics"]["path"] = (
                f"{self.config['retained_artifact']}/build-competition/baseset/alternate-opengfx-8.0.tar"
            )
            content_path.write_text(json.dumps(content) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M20SourceError, "base graphics.*OpenGFX"):
                validator.validate(project_root, config_path, self.schema,
                                   artifact_context=ArtifactContext.offline())

    def test_custom_conflicting_content_alias_fails_offline(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project_root, config_path, content_path = make_custom_record_fixture(
                self.root, pathlib.Path(raw), self.config,
            )
            content = validator.load(content_path)
            content["ai_archives"][0]["path"] = content["ai_archives"][1]["path"]
            content["ai_archives"][0]["sha256"] = "0" * 64
            content_path.write_text(json.dumps(content) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M20SourceError, "duplicate physical content"):
                validator.validate(project_root, config_path, self.schema,
                                   artifact_context=ArtifactContext.offline())

    def test_custom_nested_content_records_fail_closed_for_malformed_fields(self) -> None:
        targets = (
            ("base_graphics", lambda content: content["base_graphics"]),
            ("ai_archives[0]", lambda content: content["ai_archives"][0]),
            ("ai_archives[1]", lambda content: content["ai_archives"][1]),
            ("ai_archives[2]", lambda content: content["ai_archives"][2]),
            ("libraries[0]", lambda content: content["libraries"][0]),
            ("libraries[1]", lambda content: content["libraries"][1]),
            ("libraries[2]", lambda content: content["libraries"][2]),
            ("libraries[3]", lambda content: content["libraries"][3]),
        )
        mutations = (
            ("extra", lambda record: record.__setitem__("unexpected", "accepted")),
            ("missing", lambda record: record.pop("sha256")),
            ("wrong-type", lambda record: record.__setitem__("path", 7)),
        )
        for label, select in targets:
            for mutation, mutate in mutations:
                with self.subTest(record=label, mutation=mutation), tempfile.TemporaryDirectory() as raw:
                    project_root, config_path, content_path = make_custom_record_fixture(
                        self.root, pathlib.Path(raw), self.config,
                    )
                    content = validator.load(content_path)
                    mutate(select(content))
                    content_path.write_text(json.dumps(content) + "\n", encoding="utf-8")
                    try:
                        validator.validate(project_root, config_path, self.schema,
                                           artifact_context=ArtifactContext.offline())
                    except Exception as exc:  # The public boundary must convert malformed records to its domain error.
                        self.assertIsInstance(exc, validator.M20SourceError)
                        self.assertRegex(str(exc), rf"content {label.replace('[', r'\[').replace(']', r'\]')} record malformed")
                    else:
                        self.fail(f"malformed content {label} record was accepted: {mutation}")

    def test_malformed_custom_manifest_cli_exits_one_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project_root, config_path, content_path = make_custom_record_fixture(
                self.root, pathlib.Path(raw), self.config,
            )
            content = validator.load(content_path)
            del content["libraries"][0]["sha256"]
            content_path.write_text(json.dumps(content) + "\n", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(self.root / "scripts/v2/validate_m20_competition_source.py"),
                    "--root", str(project_root),
                    "--config", str(config_path),
                    "--schema", str(self.schema),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("V2_M20_COMPETITION_SOURCE=FAIL content libraries[0] record malformed", completed.stdout)
        self.assertNotIn("Traceback", completed.stderr)

    def test_repository_content_manifest_digest_mutation_fails_offline(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project_root, content_path = make_repository_record_fixture(self.root, pathlib.Path(raw))
            content = validator.load(content_path)
            content["ai_archives"][0]["sha256"] = "0" * 64
            content_path.write_text(json.dumps(content) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M20SourceError, "content manifest identity"):
                validator.validate(project_root, artifact_context=ArtifactContext.offline())

    def test_repository_contract_digest_mutation_fails_offline(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            project_root, _ = make_repository_record_fixture(self.root, pathlib.Path(raw))
            contract_path = project_root / "config/v2/m20-competition-contract.json"
            contract_path.write_bytes(contract_path.read_bytes() + b" \n")
            with self.assertRaisesRegex(validator.M20SourceError, "M20 contract identity"):
                validator.validate(project_root, artifact_context=ArtifactContext.offline())

    def test_relocated_live_base_graphics_split_fails_before_git(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            project_root, _, config_path = make_live_source_fixture(self.root, base, self.config)
            content_path = project_root / self.config["runtime"]["content_manifest"]
            content = validator.load(content_path)
            recorded = f"{self.config['retained_artifact']}/build-competition/baseset/alternate-opengfx-8.0.tar"
            content["base_graphics"]["path"] = recorded
            content_path.write_text(json.dumps(content) + "\n", encoding="utf-8")
            alternate = base / "v2-m20-competition-a/build-competition/baseset/alternate-opengfx-8.0.tar"
            shutil.copyfile(base / "v2-m20-competition-a/build-competition/baseset/opengfx-8.0.tar", alternate)
            with mock.patch.object(validator, "git", side_effect=AssertionError("unexpected Git read")) as reader:
                with self.assertRaisesRegex(validator.M20SourceError, "base graphics.*OpenGFX"):
                    validator.validate(project_root, config_path, self.schema,
                                       artifact_context=ArtifactContext.live(base))
            reader.assert_not_called()

    def test_live_preflight_fails_before_git(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with mock.patch.object(validator, "git", side_effect=AssertionError("unexpected live read")) as reader:
                with self.assertRaisesRegex(ArtifactContextError, "missing"):
                    validator.validate(self.root, artifact_context=ArtifactContext.live(pathlib.Path(raw).resolve()))
            reader.assert_not_called()

    def test_patch_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.config); value["patch"]["sha256"] = "0" * 64
        self.mutation_fails(value, "patch identity")

    def test_source_tree_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            project_root, value, config_path = make_live_source_fixture(self.root, base, self.config)
            value["source"]["tree"] = "0" * 40
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M20SourceError, "tree"):
                validator.validate(project_root, config_path, self.schema,
                                   artifact_context=ArtifactContext.live(base))

    def test_executable_digest_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            project_root, value, config_path = make_live_source_fixture(self.root, base, self.config)
            value["executable"]["sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(project_root, config_path, self.schema,
                                   artifact_context=ArtifactContext.live(base))

    def test_upstream_ctest_mutation_fails_offline(self) -> None:
        value = copy.deepcopy(self.config)
        value["build"]["upstream_ctest"]["passed"] = 97
        self.mutation_fails(value, "upstream_ctest")

    def test_removed_base_source_option_exits_two(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                validator.main(["--root", str(self.root), "--base" + "-source", str(self.root)])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
