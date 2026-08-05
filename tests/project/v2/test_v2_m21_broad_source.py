#!/usr/bin/env python3
"""Mutation tests for the M21 contract, coverage, content lock, and native source."""

from __future__ import annotations

import copy
import contextlib
import hashlib
import io
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from typing import Any
from unittest import mock

import jsonschema

from artifact_context import ArtifactContext, ArtifactContextError, resolve_artifact_root
import run_m21_broad_matrix as matrix
from tests.project.v2.test_v2_m15_native_source import _write_patch_preimage
import validate_m21_broad_source as validator


def _git(repository: pathlib.Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repository), *arguments],
        text=True,
    ).strip()


def make_live_source_fixture(
    root: pathlib.Path,
    directory: pathlib.Path,
    config: dict[str, Any],
) -> tuple[dict[str, Any], pathlib.Path]:
    value = copy.deepcopy(config)
    patch = root / value["patch"]["path"]
    base_source = directory / "v2-m20-competition-a/source"
    base_source.mkdir(parents=True)
    _write_patch_preimage(patch, base_source)
    subprocess.run(["git", "init", "-q", str(base_source)], check=True)
    for key, setting in (("user.name", "source fixture"), ("user.email", "source-fixture@example.invalid")):
        subprocess.run(["git", "-C", str(base_source), "config", key, setting], check=True)
    subprocess.run(["git", "-C", str(base_source), "add", "."], check=True)
    subprocess.run(["git", "-C", str(base_source), "commit", "-q", "-m", "base"], check=True)
    value["base"]["commit"] = _git(base_source, "rev-parse", "HEAD")
    value["base"]["tree"] = _git(base_source, "rev-parse", "HEAD^{tree}")

    result_root = directory / "v2-m21-broad-a"
    result_source = result_root / "source"
    result_root.mkdir(parents=True)
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

    executable = result_root / "build-broad/openttd"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"relocated-m21-openttd\n")
    executable.chmod(0o700)
    value["executable"]["bytes"] = executable.stat().st_size
    value["executable"]["sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    opengfx = result_root / "build-broad/baseset/opengfx-8.0.tar"
    opengfx.parent.mkdir(parents=True)
    opengfx.write_bytes(b"relocated-m21-opengfx\n")
    value["build"]["open_gfx"]["bytes"] = opengfx.stat().st_size
    value["build"]["open_gfx"]["sha256"] = hashlib.sha256(opengfx.read_bytes()).hexdigest()
    for name, record in value["runtime"]["configs"].items():
        path = result_root / f"{name}.cfg"
        path.write_text(f"[{name}]\n", encoding="utf-8")
        record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    content_root = result_root / "build-broad/newgrf/m21"
    content_root.mkdir(parents=True)
    for record in value["runtime"]["content_files"]:
        path = content_root / record["name"]
        path.write_bytes(f"relocated-{record['name']}\n".encode())
        record["bytes"] = path.stat().st_size
        record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    gamescript_root = result_root / "build-broad/game/m21coverage"
    gamescript_root.mkdir(parents=True)
    (gamescript_root / "info.nut").write_bytes((root / matrix.GAMESCRIPT_INFO).read_bytes())
    (gamescript_root / "main.nut").write_bytes((root / matrix.GAMESCRIPT_MAIN).read_bytes())

    config_path = directory / "source.json"
    config_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return value, config_path


class M21BroadSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.source = validator.load(cls.root / validator.CONFIG)
        cls.contract = validator.load(cls.root / matrix.CONTRACT)
        cls.coverage = validator.load(cls.root / matrix.COVERAGE)

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "source.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            errors = (validator.M21SourceError, matrix.M21MatrixError)
            context = self.assertRaisesRegex(errors, pattern) if pattern else self.assertRaises(errors)
            with context:
                validator.validate(self.root, self.write(pathlib.Path(raw), value),
                                   artifact_context=ArtifactContext.offline())

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def test_repository_contract_coverage_content_and_source_pass(self) -> None:
        with mock.patch.object(validator, "git", side_effect=AssertionError("unexpected live access")) as reader:
            result = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertEqual((result["files"], result["features"], result["commands"]), (4, 18, 145))
        self.assertFalse(result["live"])
        reader.assert_not_called()

    def test_live_source_and_runtime_pass(self) -> None:
        self.assertTrue(validator.validate(
            self.root,
            artifact_context=ArtifactContext.live(self.live_base()),
        )["live"])

    def test_required_live_inputs_are_the_exact_source_and_runtime_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        expected = (
            ("v2-m20-competition-a", "source", "directory"),
            ("v2-m20-competition-a", "source/.git", "directory"),
            ("v2-m21-broad-a", "source", "directory"),
            ("v2-m21-broad-a", "source/.git", "directory"),
            ("v2-m21-broad-a", "build-broad/openttd", "file"),
            ("v2-m21-broad-a", "build-broad/baseset/opengfx-8.0.tar", "file"),
            ("v2-m21-broad-a", "base.cfg", "file"),
            ("v2-m21-broad-a", "content.cfg", "file"),
            ("v2-m21-broad-a", "gamescript.cfg", "file"),
            ("v2-m21-broad-a", "build-broad/newgrf/m21/fish.grf", "file"),
            ("v2-m21-broad-a", "build-broad/newgrf/m21/rattroads.grf", "file"),
            ("v2-m21-broad-a", "build-broad/newgrf/m21/airports.grf", "file"),
            ("v2-m21-broad-a", "build-broad/newgrf/m21/stations.grf", "file"),
            ("v2-m21-broad-a", "build-broad/newgrf/m21/industries.grf", "file"),
            ("v2-m21-broad-a", "build-broad/newgrf/m21/trains.grf", "file"),
            ("v2-m21-broad-a", "build-broad/newgrf/m21/aircraft.grf", "file"),
            ("v2-m21-broad-a", "build-broad/newgrf/m21/objects.grf", "file"),
            ("v2-m21-broad-a", "build-broad/newgrf/m21/tracks.grf", "file"),
            ("v2-m21-broad-a", "build-broad/newgrf/m21/roadhog.grf", "file"),
            ("v2-m21-broad-a", "build-broad/game/m21coverage/info.nut", "file"),
            ("v2-m21-broad-a", "build-broad/game/m21coverage/main.nut", "file"),
        )
        self.assertEqual(tuple((item.logical_set, item.relative_path, item.kind) for item in requirements), expected)
        self.assertEqual({item.consumer for item in requirements[:4]}, {"m21-broad-source"})
        self.assertEqual({item.consumer for item in requirements[4:]}, {"m21-broad-runtime"})

    def test_relocated_runtime_paths_are_used_instead_of_recorded_paths(self) -> None:
        recorded = copy.deepcopy(self.source)
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path = make_live_source_fixture(self.root, base, self.source)
            summary = validator.validate(
                self.root,
                config_path,
                artifact_context=ArtifactContext.live(base),
            )
        self.assertTrue(summary["live"])
        self.assertEqual(
            (
                value["retained_artifact"],
                value["source"]["path"],
                value["executable"]["path"],
                value["runtime"]["content_root"],
                value["runtime"]["gamescript_root"],
            ),
            (
                recorded["retained_artifact"],
                recorded["source"]["path"],
                recorded["executable"]["path"],
                recorded["runtime"]["content_root"],
                recorded["runtime"]["gamescript_root"],
            ),
        )
        self.assertEqual(self.source, recorded)

    def test_validate_runtime_returns_relocated_root_and_named_paths(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, _ = make_live_source_fixture(self.root, base, self.source)
            runtime_root, paths = matrix.validate_runtime(self.root, value, ArtifactContext.live(base))
        self.assertEqual(runtime_root, base / "v2-m21-broad-a")
        self.assertEqual(set(paths), {
            "executable", "open_gfx", "config:base", "config:content", "config:gamescript",
            *(f"content:{record['name']}" for record in self.source["runtime"]["content_files"]),
            "gamescript:info.nut", "gamescript:main.nut",
        })
        self.assertTrue(all(path.is_relative_to(runtime_root) for path in paths.values()))

    def test_extra_runtime_config_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["runtime"]["configs"]["extra"] = {
            "path": f"{value['retained_artifact']}/extra.cfg",
            "sha256": "0" * 64,
        }
        self.mutation_fails(value, "config inventory")

    def test_runtime_discovery_path_mutations_fail_offline(self) -> None:
        mutations = (
            ("executable", ("executable", "path"),
             f"{self.source['retained_artifact']}/build-broad/not-discovered/openttd", "executable path"),
            ("base-config", ("runtime", "configs", "base", "path"),
             f"{self.source['retained_artifact']}/not-discovered/base.cfg", "base config path"),
            ("content-root", ("runtime", "content_root"),
             f"{self.source['retained_artifact']}/build-broad/not-discovered/m21", "content root path"),
            ("gamescript-root", ("runtime", "gamescript_root"),
             f"{self.source['retained_artifact']}/build-broad/not-discovered/m21coverage", "Game Script root path"),
            ("content-name", ("runtime", "content_files", 0, "name"), "renamed.grf", "content inventory"),
        )
        for label, keys, replacement, pattern in mutations:
            with self.subTest(label=label):
                value = copy.deepcopy(self.source)
                target: Any = value
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = replacement
                self.mutation_fails(value, pattern)

    def test_conflicting_content_physical_alias_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["runtime"]["content_files"][1]["name"] = value["runtime"]["content_files"][0]["name"]
        value["runtime"]["content_files"][1]["sha256"] = "0" * 64
        self.mutation_fails(value, "duplicate physical runtime input")

    def test_relocated_declared_opengfx_outside_discovery_layout_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path = make_live_source_fixture(self.root, base, self.source)
            expected = base / "v2-m21-broad-a/build-broad/baseset/opengfx-8.0.tar"
            alternate = base / "v2-m21-broad-a/build-broad/not-discovered/opengfx-8.0.tar"
            alternate.parent.mkdir(parents=True)
            alternate.write_bytes(expected.read_bytes())
            value["build"]["open_gfx"]["path"] = (
                f"{self.source['retained_artifact']}/build-broad/not-discovered/opengfx-8.0.tar"
            )
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(matrix.M21MatrixError, "OpenGFX path"):
                validator.validate(self.root, config_path,
                                   artifact_context=ArtifactContext.live(base))

    def test_run_command_uses_complete_relocated_discovery_layout(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, _ = make_live_source_fixture(self.root, base, self.source)
            executable = base / "v2-m21-broad-a/build-broad/openttd"
            executable.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, pathlib, sys\n"
                "target = pathlib.Path(sys.argv[sys.argv.index('-k') + 1])\n"
                "target.write_text(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}))\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            value["executable"]["bytes"] = executable.stat().st_size
            value["executable"]["sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
            runtime_root, paths = matrix.validate_runtime(self.root, value, ArtifactContext.live(base))
            request = base / "request.json"
            report = base / "report.json"
            request.write_text("{}\n", encoding="utf-8")
            try:
                completed = matrix.run_command(runtime_root, paths, "content", request, report)
            except TypeError as exc:
                self.fail(f"runner does not consume the complete relocated runtime map: {exc}")
            self.assertEqual(completed.returncode, 0)
            observed = json.loads(report.read_text(encoding="utf-8"))
            discovery_root = runtime_root / "build-broad"
            self.assertEqual(pathlib.Path(observed["cwd"]), discovery_root)
            config_index = observed["argv"].index("-c")
            self.assertEqual(pathlib.Path(observed["argv"][config_index + 1]), runtime_root / "content.cfg")
            self.assertEqual(paths["open_gfx"], discovery_root / "baseset/opengfx-8.0.tar")
            self.assertEqual(
                {paths[f"content:{name}"] for name in (
                    "fish.grf", "rattroads.grf", "airports.grf", "stations.grf", "industries.grf",
                    "trains.grf", "aircraft.grf", "objects.grf", "tracks.grf", "roadhog.grf",
                )},
                {discovery_root / "newgrf/m21" / name for name in (
                    "fish.grf", "rattroads.grf", "airports.grf", "stations.grf", "industries.grf",
                    "trains.grf", "aircraft.grf", "objects.grf", "tracks.grf", "roadhog.grf",
                )},
            )
            self.assertEqual(paths["gamescript:info.nut"], discovery_root / "game/m21coverage/info.nut")
            self.assertEqual(paths["gamescript:main.nut"], discovery_root / "game/m21coverage/main.nut")

    def test_live_preflight_fails_before_git_or_runtime_helper(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with mock.patch.object(validator, "git", side_effect=AssertionError("unexpected live read")) as reader, \
                    mock.patch.object(matrix, "validate_runtime", side_effect=AssertionError("unexpected runtime read")) as runtime:
                with self.assertRaisesRegex(ArtifactContextError, "missing"):
                    validator.validate(self.root, artifact_context=ArtifactContext.live(pathlib.Path(raw).resolve()))
            reader.assert_not_called()
            runtime.assert_not_called()

    def test_symlinked_runtime_input_fails_before_git(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path = make_live_source_fixture(self.root, base, self.source)
            target = base / "v2-m21-broad-a/base.cfg"
            payload = base / "payload.cfg"
            payload.write_bytes(target.read_bytes())
            target.unlink()
            target.symlink_to(payload)
            with mock.patch.object(validator, "git", side_effect=AssertionError("unexpected live read")) as reader:
                with self.assertRaisesRegex(ArtifactContextError, "symlink traversal"):
                    validator.validate(self.root, config_path,
                                       artifact_context=ArtifactContext.live(base))
            reader.assert_not_called()

    def test_relocated_source_ignores_hostile_git_environment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path = make_live_source_fixture(self.root, base, self.source)
            hostile = base / "v2-m20-competition-a/source"
            with mock.patch.dict(os.environ, {"GIT_DIR": str(hostile / ".git"), "GIT_WORK_TREE": str(hostile)}):
                summary = validator.validate(self.root, config_path,
                                             artifact_context=ArtifactContext.live(base))
        self.assertTrue(summary["live"])

    def test_patch_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source); value["patch"]["sha256"] = "0" * 64
        self.mutation_fails(value, "patch identity")

    def test_source_tree_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path = make_live_source_fixture(self.root, base, self.source)
            value["source"]["tree"] = "0" * 40
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.M21SourceError, "source identity"):
                validator.validate(self.root, config_path,
                                   artifact_context=ArtifactContext.live(base))

    def test_executable_digest_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path = make_live_source_fixture(self.root, base, self.source)
            value["executable"]["sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(self.root, config_path,
                                   artifact_context=ArtifactContext.live(base))

    def test_upstream_ctest_mutation_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["build"]["upstream_ctest"]["passed"] = 97
        self.mutation_fails(value, "upstream_ctest")

    def test_runtime_config_alias_is_rejected_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["runtime"]["configs"]["content"] = copy.deepcopy(value["runtime"]["configs"]["base"])
        self.mutation_fails(value, "duplicates")

    def test_removed_base_source_option_exits_two(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                validator.main(["--root", str(self.root), "--base" + "-source", str(self.root)])
        self.assertEqual(raised.exception.code, 2)

    def test_contract_case_omission_fails_schema(self) -> None:
        value = copy.deepcopy(self.contract); value["cases"].pop()
        schema = validator.load(self.root / validator.CONTRACT_SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)

    def test_feature_coverage_omission_fails(self) -> None:
        value = copy.deepcopy(self.coverage); value["feature_domains"].pop()
        with self.assertRaises(matrix.M21MatrixError):
            matrix.validate_coverage(self.root, self.contract, value)

    def test_command_disposition_mutation_fails(self) -> None:
        value = copy.deepcopy(self.coverage); value["command_dispositions"][0]["disposition"] = "benchmark-admin"
        with self.assertRaisesRegex(matrix.M21MatrixError, "command coverage"):
            matrix.validate_coverage(self.root, self.contract, value)

    def test_presentation_proof_cannot_escape_optional_disposition(self) -> None:
        value = copy.deepcopy(self.coverage)
        row = next(item for item in value["command_dispositions"] if item["disposition"] == "policy-required")
        row["proof_kind"] = "deliberate-presentation-only-proof"
        with self.assertRaisesRegex(matrix.M21MatrixError, "presentation-only"):
            matrix.validate_coverage(self.root, self.contract, value)


if __name__ == "__main__":
    unittest.main()
