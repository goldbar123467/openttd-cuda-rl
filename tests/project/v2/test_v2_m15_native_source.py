#!/usr/bin/env python3
"""Mutation tests for the M15 source delta and build evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import re
import subprocess
import tempfile
import unittest
from typing import Any
from unittest import mock

from artifact_context import ArtifactContext, ArtifactContextError, resolve_artifact_root
import validate_m15_action_source
import validate_m15_competence_source
import validate_m15_episode_source
import validate_m15_native_source
import validate_m15_observation_source


def _git(repository: pathlib.Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repository), *arguments],
        text=True,
    ).strip()


def _write_patch_preimage(patch: pathlib.Path, repository: pathlib.Path) -> None:
    """Create a minimal real Git worktree to which the patch applies exactly."""

    lines = patch.read_text(encoding="utf-8").splitlines(keepends=True)
    index = 0
    while index < len(lines):
        header = re.match(r"diff --git a/(\S+) b/(\S+)", lines[index])
        if header is None:
            index += 1
            continue
        relative = header.group(1)
        index += 1
        section: list[str] = []
        while index < len(lines) and not lines[index].startswith("diff --git "):
            section.append(lines[index])
            index += 1
        if any(line.startswith("new file mode ") for line in section):
            continue
        content: list[str] = []
        section_index = 0
        while section_index < len(section):
            hunk = re.match(
                r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@",
                section[section_index],
            )
            if hunk is None:
                section_index += 1
                continue
            position = int(hunk.group(1)) - 1
            while len(content) < position:
                content.append(f"// fixture filler {len(content) + 1}\n")
            section_index += 1
            while section_index < len(section) and not section[section_index].startswith("@@ "):
                line = section[section_index]
                if line.startswith((" ", "-")):
                    old_line = line[1:]
                    if len(content) == position:
                        content.append(old_line)
                    else:
                        if content[position] != old_line:
                            raise AssertionError(f"overlapping patch context drifted for {relative}")
                    position += 1
                section_index += 1
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(content), encoding="utf-8")


def make_live_source_fixture(
    root: pathlib.Path,
    directory: pathlib.Path,
    config: dict[str, Any],
    schema_path: pathlib.Path,
    *,
    patch_relative: str,
    base_set: str,
    base_relative: str,
    result_set: str,
    config_filename: str,
) -> tuple[dict[str, Any], pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path]:
    """Build real relocated base/result Git repositories plus a retained executable."""

    value = copy.deepcopy(config)
    patch = root / patch_relative
    base_source = directory / base_set / base_relative
    base_source.mkdir(parents=True)
    _write_patch_preimage(patch, base_source)
    subprocess.run(["git", "init", "-q", str(base_source)], check=True)
    for key, setting in (("user.name", "M15 fixture"), ("user.email", "m15-fixture@example.invalid")):
        subprocess.run(["git", "-C", str(base_source), "config", key, setting], check=True)
    subprocess.run(["git", "-C", str(base_source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(base_source), "commit", "-q", "-m", "base"], check=True)
    value["base"]["commit"] = _git(base_source, "rev-parse", "HEAD")
    value["base"]["tree"] = _git(base_source, "rev-parse", "HEAD^{tree}")

    result_source = directory / result_set / "source"
    result_source.parent.mkdir(parents=True)
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(base_source), str(result_source)], check=True)
    for key, setting in (("user.name", "M15 fixture"), ("user.email", "m15-fixture@example.invalid")):
        subprocess.run(["git", "-C", str(result_source), "config", key, setting], check=True)
    subprocess.run(
        ["git", "-C", str(result_source), "apply", "--index", "--whitespace=error-all", str(patch)],
        check=True,
    )
    subprocess.run(["git", "-C", str(result_source), "commit", "-q", "-m", "result"], check=True)
    value["result"]["tree"] = _git(result_source, "rev-parse", "HEAD^{tree}")
    if "commit" in value["result"]:
        value["result"]["commit"] = _git(result_source, "rev-parse", "HEAD")

    executable = directory / result_set / value["build"]["executable"]["path"]
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"x" * 1_000_000)
    value["build"]["executable"]["size"] = executable.stat().st_size
    value["build"]["executable"]["sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    for section in ("base", "result"):
        properties = schema["properties"][section]["properties"]
        for field in ("commit", "tree"):
            if field in value[section] and "const" in properties[field]:
                properties[field]["const"] = value[section][field]
    fixture_schema = directory / f"{config_filename}.schema.json"
    fixture_schema.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    value["schema_sha256"] = hashlib.sha256(fixture_schema.read_bytes()).hexdigest()
    fixture_config = directory / config_filename
    fixture_config.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return value, fixture_config, fixture_schema, base_source, result_source


def _source_validator_cases(root: pathlib.Path) -> tuple[tuple[Any, ...], ...]:
    native = validate_m15_native_source.load_json(root / validate_m15_native_source.CONFIG)
    observation = validate_m15_observation_source.load_json(
        root / validate_m15_observation_source.CONFIG
    )
    action = validate_m15_action_source.load_json(root / validate_m15_action_source.CONFIG)
    episode = validate_m15_episode_source.load_json(root / validate_m15_episode_source.CONFIG)
    competence = validate_m15_competence_source.load_json(
        root / validate_m15_competence_source.CONFIG
    )
    return (
        (
            "native",
            validate_m15_native_source,
            native,
            root / validate_m15_native_source.SCHEMA,
            str(
                pathlib.Path(native["patch_series"]["directory"])
                / native["patch_series"]["patches"][0]["name"]
            ),
            "m12-release-final-a",
            "composed-source/openttd",
            "v2-m15-native-a",
        ),
        (
            "observation",
            validate_m15_observation_source,
            observation,
            root / validate_m15_observation_source.SCHEMA,
            observation["patch"]["path"],
            "v2-m15-native-a",
            "source",
            "v2-m15-observation-a",
        ),
        (
            "action",
            validate_m15_action_source,
            action,
            root / validate_m15_action_source.SCHEMA,
            action["patch"]["path"],
            "v2-m15-observation-a",
            "source",
            "v2-m15-action-a",
        ),
        (
            "episode",
            validate_m15_episode_source,
            episode,
            root / validate_m15_episode_source.SCHEMA,
            episode["patch"]["path"],
            "v2-m15-action-a",
            "source",
            "v2-m15-episode-a",
        ),
        (
            "competence",
            validate_m15_competence_source,
            competence,
            root / validate_m15_competence_source.SCHEMA,
            competence["patch"]["path"],
            "v2-m15-episode-a",
            "source",
            "v2-m15-competence-a",
        ),
    )


def _hostile_git_environment(
    directory: pathlib.Path,
    base_source: pathlib.Path,
) -> dict[str, str]:
    redirect = directory / "hostile-repository"
    subprocess.run(
        ["git", "clone", "-q", "--no-hardlinks", str(base_source), str(redirect)],
        check=True,
    )
    return {
        "GIT_DIR": str(redirect / ".git"),
        "GIT_WORK_TREE": str(redirect),
    }


def _install_replacement_refs(
    base_source: pathlib.Path,
    result_source: pathlib.Path,
) -> None:
    base_commit = _git(base_source, "rev-parse", "HEAD")
    result_commit = _git(result_source, "rev-parse", "HEAD")
    subprocess.run(
        ["git", "-C", str(base_source), "fetch", "-q", str(result_source), result_commit],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(base_source), "replace", base_commit, result_commit],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(result_source), "replace", result_commit, base_commit],
        check=True,
    )


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

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def test_repository_source_delta_passes(self) -> None:
        summary = validate_m15_native_source.validate(
            self.root,
            artifact_context=ArtifactContext.offline(),
        )
        self.assertEqual(summary.patches, 1)
        self.assertEqual(summary.files, 4)
        self.assertEqual(summary.result_tree, "70394b69df9a6c2104cb711c439da53b2abde367")

    def test_live_source_and_build_pass(self) -> None:
        summary = validate_m15_native_source.validate(
            self.root,
            artifact_context=ArtifactContext.live(self.live_base()),
        )
        self.assertTrue(summary.live_source and summary.live_build)

    def test_offline_validation_does_not_open_recorded_base_source(self) -> None:
        with mock.patch.object(
            validate_m15_native_source,
            "git",
            side_effect=AssertionError("unexpected live access"),
        ) as reader:
            summary = validate_m15_native_source.validate(
                self.root,
                artifact_context=ArtifactContext.offline(),
            )
        self.assertFalse(summary.live_source)
        self.assertFalse(summary.live_build)
        reader.assert_not_called()

    def test_relocated_live_source_and_build_use_one_context(self) -> None:
        recorded_root = self.config["build"]["artifact_root"]
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, schema_path, base_source, result_source = make_live_source_fixture(
                self.root,
                base,
                self.config,
                self.schema,
                patch_relative=self.config["patch_series"]["directory"] + "/" + self.config["patch_series"]["patches"][0]["name"],
                base_set="m12-release-final-a",
                base_relative="composed-source/openttd",
                result_set="v2-m15-native-a",
                config_filename="native-source.json",
            )
            real_git = validate_m15_native_source.git
            with mock.patch.object(validate_m15_native_source, "git", wraps=real_git) as reader:
                summary = validate_m15_native_source.validate(
                    self.root,
                    config_path,
                    schema_path,
                    artifact_context=ArtifactContext.live(base),
                )
        self.assertTrue(summary.live_source and summary.live_build)
        self.assertEqual(value["build"]["artifact_root"], recorded_root)
        read_repositories = {call.args[0] for call in reader.call_args_list}
        self.assertIn(base_source, read_repositories)
        self.assertIn(result_source, read_repositories)

    def test_every_source_validator_ignores_hostile_git_environment_during_clone_apply(self) -> None:
        for (
            name, validator, config, schema, patch_relative,
            base_set, base_relative, result_set,
        ) in _source_validator_cases(self.root):
            with self.subTest(validator=name), tempfile.TemporaryDirectory() as raw:
                base = pathlib.Path(raw).resolve()
                _, config_path, schema_path, base_source, _ = make_live_source_fixture(
                    self.root,
                    base,
                    config,
                    schema,
                    patch_relative=patch_relative,
                    base_set=base_set,
                    base_relative=base_relative,
                    result_set=result_set,
                    config_filename=f"{name}-source.json",
                )
                hostile = _hostile_git_environment(base, base_source)
                with mock.patch.dict(os.environ, hostile):
                    summary = validator.validate(
                        self.root,
                        config_path,
                        schema_path,
                        artifact_context=ArtifactContext.live(base),
                    )
                self.assertTrue(summary.live_source and summary.live_build)

    def test_every_source_validator_ignores_replacement_refs_for_source_identity(self) -> None:
        for (
            name, validator, config, schema, patch_relative,
            base_set, base_relative, result_set,
        ) in _source_validator_cases(self.root):
            with self.subTest(validator=name), tempfile.TemporaryDirectory() as raw:
                base = pathlib.Path(raw).resolve()
                _, config_path, schema_path, base_source, result_source = make_live_source_fixture(
                    self.root,
                    base,
                    config,
                    schema,
                    patch_relative=patch_relative,
                    base_set=base_set,
                    base_relative=base_relative,
                    result_set=result_set,
                    config_filename=f"{name}-source.json",
                )
                _install_replacement_refs(base_source, result_source)
                summary = validator.validate(
                    self.root,
                    config_path,
                    schema_path,
                    artifact_context=ArtifactContext.live(base),
                )
                self.assertTrue(summary.live_source and summary.live_build)

    def test_live_preflight_fails_before_source_read(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with mock.patch.object(
                validate_m15_native_source,
                "git",
                side_effect=AssertionError("unexpected live read"),
            ) as reader:
                with self.assertRaisesRegex(ArtifactContextError, "missing"):
                    validate_m15_native_source.validate(
                        self.root,
                        artifact_context=ArtifactContext.live(pathlib.Path(raw).resolve()),
                    )
            reader.assert_not_called()

    def test_required_live_inputs_are_the_exact_native_source_closure(self) -> None:
        requirements = validate_m15_native_source.required_live_inputs(self.root)
        self.assertEqual(
            tuple((item.logical_set, item.relative_path, item.kind) for item in requirements),
            (
                ("m12-release-final-a", "composed-source/openttd", "directory"),
                ("m12-release-final-a", "composed-source/openttd/.git", "directory"),
                ("v2-m15-native-a", "source", "directory"),
                ("v2-m15-native-a", "source/.git", "directory"),
                ("v2-m15-native-a", "build/openttd", "file"),
            ),
        )
        self.assertEqual({item.consumer for item in requirements}, {"m15-native-source"})
        self.assertEqual(
            requirements[-1].expected_sha256,
            self.config["build"]["executable"]["sha256"],
        )

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_source.M15NativeSourceError, "schema SHA-256"):
                validate_m15_native_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema, artifact_context=ArtifactContext.offline())

    def test_patch_digest_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["patch_series"]["patches"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_source.M15NativeSourceError, "patch SHA-256"):
                validate_m15_native_source.validate(self.root, self.write(pathlib.Path(raw), value), self.schema, artifact_context=ArtifactContext.offline())

    def test_result_tree_drift_fails_live(self) -> None:
        base = self.live_base()
        value = copy.deepcopy(self.config)
        value["result"]["tree"] = "0" * 40
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_source.M15NativeSourceError, "result tree"):
                validate_m15_native_source.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=ArtifactContext.live(base),
                )

    def test_executable_identity_drift_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, schema_path, _, _ = make_live_source_fixture(
                self.root,
                base,
                self.config,
                self.schema,
                patch_relative=self.config["patch_series"]["directory"] + "/" + self.config["patch_series"]["patches"][0]["name"],
                base_set="m12-release-final-a",
                base_relative="composed-source/openttd",
                result_set="v2-m15-native-a",
                config_filename="native-source.json",
            )
            value["build"]["executable"]["sha256"] = "0" * 64
            config_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validate_m15_native_source.validate(
                    self.root,
                    config_path,
                    schema_path,
                    artifact_context=ArtifactContext.live(base),
                )


if __name__ == "__main__":
    unittest.main()
