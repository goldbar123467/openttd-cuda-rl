#!/usr/bin/env python3
"""Mutation tests for the retained M22 final native runtime source."""

from __future__ import annotations

import copy
import contextlib
import hashlib
import io
import json
import os
import pathlib
import re
import subprocess
import tempfile
import unittest
from typing import Any
from unittest import mock

import jsonschema

from artifact_context import ARTIFACT_ROOT_ENV, ArtifactContext, ArtifactContextError
import prepare_m22_final_runtime as preparation
from tests.project.v2.test_v2_m15_native_source import _write_patch_preimage
import validate_m22_final_runtime_source as validator


def _git(repository: pathlib.Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repository), *arguments], text=True,
    ).strip()


def _patch_side(patch: pathlib.Path, side: str) -> dict[str, dict[int, str]]:
    """Return literal old/new hunk lines keyed by their target line numbers."""

    lines = patch.read_text(encoding="utf-8").splitlines(keepends=True)
    result: dict[str, dict[int, str]] = {}
    index = 0
    while index < len(lines):
        header = re.match(r"diff --git a/(\S+) b/(\S+)", lines[index])
        if header is None:
            index += 1
            continue
        relative = header.group(1)
        positions = result.setdefault(relative, {})
        index += 1
        while index < len(lines) and not lines[index].startswith("diff --git "):
            hunk = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", lines[index])
            if hunk is None:
                index += 1
                continue
            old_line, new_line = int(hunk.group(1)), int(hunk.group(2))
            index += 1
            while (index < len(lines) and not lines[index].startswith("@@ ") and
                   not lines[index].startswith("diff --git ")):
                line = lines[index]
                if line.startswith("\\ No newline"):
                    index += 1
                    continue
                marker, payload = line[:1], line[1:]
                if marker in {" ", "-"}:
                    if side == "old":
                        if old_line in positions and positions[old_line] != payload:
                            raise AssertionError(f"old-side patch overlap drifted: {relative}:{old_line}")
                        positions[old_line] = payload
                    old_line += 1
                if marker in {" ", "+"}:
                    if side == "new":
                        if new_line in positions and positions[new_line] != payload:
                            raise AssertionError(f"new-side patch overlap drifted: {relative}:{new_line}")
                        positions[new_line] = payload
                    new_line += 1
                index += 1
    return result


def _write_patch_chain_preimage(patches: tuple[pathlib.Path, ...], repository: pathlib.Path) -> None:
    if len(patches) == 1:
        _write_patch_preimage(patches[0], repository)
        return
    if len(patches) != 2:
        raise AssertionError("runtime fixture supports the frozen one- or two-patch series")
    intermediate: dict[str, dict[int, str]] = {}
    for source in (_patch_side(patches[0], "new"), _patch_side(patches[1], "old")):
        for relative, positions in source.items():
            destination = intermediate.setdefault(relative, {})
            for line_number, line in positions.items():
                if line_number in destination and destination[line_number] != line:
                    raise AssertionError(f"patch-chain overlap drifted: {relative}:{line_number}")
                destination[line_number] = line
    for relative, positions in intermediate.items():
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(
            positions.get(line_number, f"// fixture filler {line_number}\n")
            for line_number in range(1, max(positions) + 1)
        ), encoding="utf-8")
    subprocess.run(
        ["git", "apply", "--reverse", "--whitespace=error-all", str(patches[0])],
        cwd=repository, check=True,
    )


def _relative(recorded_root: str, recorded_path: str) -> pathlib.PurePosixPath:
    return pathlib.PurePosixPath(recorded_path).relative_to(pathlib.PurePosixPath(recorded_root))


def _write_record_file(
    result_root: pathlib.Path,
    recorded_root: str,
    record: dict[str, Any],
    payload: bytes,
) -> pathlib.Path:
    path = result_root.joinpath(*_relative(recorded_root, record["path"]).parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    if "bytes" in record:
        record["bytes"] = len(payload)
    record["sha256"] = hashlib.sha256(payload).hexdigest()
    return path


def expected_runtime_closure(
    logical_set: str,
    build_name: str,
    smoke_ids: tuple[str, ...],
) -> tuple[tuple[str, str, str], ...]:
    archive_names = (
        "414e0201-Squid_Ate_FISH_FISH_2_Ships-2.0.3.tar",
        "415a1001-RattRoads-1.2.1.tar",
        "43415000-OpenGFX_Airports-0.5.0.tar",
        "454e1401-OpenGFX_Stations-1.0.tar",
        "4e445903-Age_of_Industry_Replacement_Set-1.3.2.tar",
        "4f472b31-OpenGFX_Trains-0.3.0.tar",
        "52415608-RAV8_Rangless_Av8-1.00.tar",
        "52580101-FIRS_and_CHIPS_style_objects-0.1.10.tar",
        "54574606-Timberwolf_s_Tracks-1.3.0.tar",
        "9787eafe-Road_Hog_Buses_Trucks_Trams-1.4.1.tar",
    )
    grf_names = (
        "fish.grf", "rattroads.grf", "airports.grf", "stations.grf", "industries.grf",
        "trains.grf", "aircraft.grf", "objects.grf", "tracks.grf", "roadhog.grf",
    )
    runtime_paths = (
        f"{build_name}/openttd",
        "build.log", "configure.log", "ctest.log", "ctest.xml", "ctest-inventory.json",
        f"{build_name}/baseset/opengfx-8.0.tar",
        "base.cfg", "content.cfg", "gamescript.cfg",
        "content_download/ai/484f4745-AAAHogEx-115.tar",
        "content_download/ai/4b524132-KrakenAI2-3.tar",
        "content_download/ai/4e6f7041-NoOpAI-4.tar",
        "content_download/ai/library/4752412a-Graph.AyStar-6.tar",
        "content_download/ai/library/5046524f-Pathfinder.Road-4.tar",
        "content_download/ai/library/51554248-Queue.BinaryHeap-1.tar",
        "content_download/ai/library/5350524c-SuperLib-40.tar",
        f"{build_name}/game/m21coverage/info.nut",
        f"{build_name}/game/m21coverage/main.nut",
        *(f"{build_name}/content_download/newgrf/{name}" for name in archive_names),
        *(f"{build_name}/newgrf/m21/{name}" for name in grf_names),
    )
    return (
        ("v2-m21-broad-a", "source", "directory"),
        ("v2-m21-broad-a", "source/.git", "directory"),
        (logical_set, "source", "directory"),
        (logical_set, "source/.git", "directory"),
        *((logical_set, path, "file") for path in runtime_paths),
        *((logical_set, f"smokes/{case_id}/{name}", "file")
          for case_id in smoke_ids for name in ("manifest.json", "report.json", "openttd.log")),
    )


def make_live_runtime_fixture(
    root: pathlib.Path,
    directory: pathlib.Path,
    source: dict[str, Any],
    *,
    patches: tuple[pathlib.Path, ...],
    logical_set: str,
) -> tuple[dict[str, Any], pathlib.Path, pathlib.Path, pathlib.Path]:
    """Create real relocated Git/runtime/smoke bytes while retaining frozen path strings."""

    value = copy.deepcopy(source)
    base_source = directory / "v2-m21-broad-a/source"
    base_source.mkdir(parents=True)
    resolved_patches = tuple((root / path).resolve() for path in patches)
    _write_patch_chain_preimage(resolved_patches, base_source)
    subprocess.run(["git", "init", "-q", str(base_source)], check=True)
    subprocess.run(["git", "-C", str(base_source), "add", "."], check=True)
    subprocess.run([
        "git", "-C", str(base_source), "-c", "user.name=runtime fixture",
        "-c", "user.email=runtime-fixture@example.invalid", "commit", "-q", "-m", "base",
    ], check=True)
    value["base"]["commit"] = _git(base_source, "rev-parse", "HEAD")
    value["base"]["tree"] = _git(base_source, "rev-parse", "HEAD^{tree}")

    result_root = directory / logical_set
    result_source = result_root / "source"
    result_root.mkdir(parents=True)
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(base_source), str(result_source)], check=True)
    for patch in resolved_patches:
        subprocess.run([
            "git", "-C", str(result_source), "apply", "--index", "--whitespace=error-all", str(patch),
        ], check=True)
    subprocess.run([
        "git", "-C", str(result_source), "-c", "user.name=runtime fixture",
        "-c", "user.email=runtime-fixture@example.invalid", "commit", "-q", "-m", "result",
    ], check=True)
    value["source"]["commit"] = _git(result_source, "rev-parse", "HEAD")
    value["source"]["tree"] = _git(result_source, "rev-parse", "HEAD^{tree}")

    recorded_root = value["retained_artifact"]
    executable = _write_record_file(
        result_root, recorded_root, value["executable"], b"relocated-openttd\n",
    )
    executable.chmod(0o700)
    for name, record in value["build"]["logs"].items():
        _write_record_file(result_root, recorded_root, record, f"{name} log\n".encode())
    inventory = json.dumps({"tests": [f"upstream-{index:03d}" for index in range(98)]}).encode() + b"\n"
    _write_record_file(result_root, recorded_root, value["build"]["test_inventory"], inventory)
    _write_record_file(result_root, recorded_root, value["runtime"]["open_gfx"], b"relocated OpenGFX\n")
    for name, record in value["runtime"]["configs"].items():
        _write_record_file(result_root, recorded_root, record, f"[{name}]\n".encode())
    for group in ("ai_archives", "ai_libraries", "gamescript_files", "newgrf_archives", "newgrf_files"):
        for ordinal, record in enumerate(value["runtime"][group]):
            _write_record_file(
                result_root, recorded_root, record, f"{group}-{ordinal}\n".encode(),
            )
    for smoke in value["smokes"]:
        smoke["executable_sha256"] = value["executable"]["sha256"]
        smoke["source_tree"] = value["source"]["tree"]
        case_root = result_root.joinpath(*_relative(recorded_root, smoke["artifact_root"]).parts)
        for path_key, hash_key, payload in (
            ("manifest_path", "manifest_sha256", b'{"fixture":"manifest"}\n'),
            ("report_path", "report_sha256", b'{"fixture":"report"}\n'),
            ("openttd_log_path", "openttd_log_sha256", b""),
        ):
            path = case_root / smoke[path_key]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            smoke[hash_key] = hashlib.sha256(payload).hexdigest()
    config_path = directory / f"{logical_set}.json"
    config_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return value, config_path, base_source, result_source


class M22FinalRuntimeSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.source = validator.load(cls.root / validator.CONFIG)

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "runtime-source.json"
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validator.M22RuntimeSourceError, pattern) if pattern else self.assertRaises(
                validator.M22RuntimeSourceError)
            with context:
                validator.validate(self.root, self.write(pathlib.Path(raw), value),
                                   artifact_context=ArtifactContext.offline())

    def test_repository_runtime_source_passes(self) -> None:
        result = validator.validate(self.root)
        self.assertEqual((result["files"], result["smokes"], result["live"]), (9, 8, False))

    def test_live_runtime_source_and_all_artifacts_pass(self) -> None:
        artifact_root = os.environ.get(ARTIFACT_ROOT_ENV)
        if artifact_root is None:
            self.skipTest("live artifact validation is outside offline mode")
        result = validator.validate(self.root, artifact_context=ArtifactContext.live(artifact_root))
        self.assertTrue(result["live"])

    def test_relocated_root_does_not_rewrite_retained_artifact(self) -> None:
        retained = (self.root / validator.CONFIG).read_bytes()
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            validator.validate(
                self.root, config_path, artifact_context=ArtifactContext.live(base),
            )
        self.assertEqual((self.root / validator.CONFIG).read_bytes(), retained)

    def test_offline_validation_never_opens_recorded_runtime_paths(self) -> None:
        recorded_root = self.source["retained_artifact"]
        original_open = pathlib.Path.open
        original_is_file = pathlib.Path.is_file
        original_is_dir = pathlib.Path.is_dir
        original_stat = pathlib.Path.stat

        def reject_open(path: pathlib.Path, *args: object, **kwargs: object):
            if str(path).startswith(recorded_root):
                raise AssertionError(f"recorded path opened offline: {path}")
            return original_open(path, *args, **kwargs)

        def reject_is_file(path: pathlib.Path) -> bool:
            if str(path).startswith(recorded_root):
                raise AssertionError(f"recorded path probed offline: {path}")
            return original_is_file(path)

        def reject_is_dir(path: pathlib.Path) -> bool:
            if str(path).startswith(recorded_root):
                raise AssertionError(f"recorded path probed offline: {path}")
            return original_is_dir(path)

        def reject_stat(path: pathlib.Path, *args: object, **kwargs: object):
            if str(path).startswith(recorded_root):
                raise AssertionError(f"recorded path stated offline: {path}")
            return original_stat(path, *args, **kwargs)

        real_git = validator.git

        def reject_recorded_git(repository: pathlib.Path, *arguments: str) -> str:
            if str(repository).startswith(recorded_root):
                raise AssertionError(f"recorded Git path opened offline: {repository}")
            return real_git(repository, *arguments)

        with mock.patch.object(pathlib.Path, "open", reject_open), \
             mock.patch.object(pathlib.Path, "is_file", reject_is_file), \
             mock.patch.object(pathlib.Path, "is_dir", reject_is_dir), \
             mock.patch.object(pathlib.Path, "stat", reject_stat), \
             mock.patch.object(validator, "git", side_effect=reject_recorded_git):
            summary = validator.validate(self.root, artifact_context=ArtifactContext.offline())
        self.assertFalse(summary["live"])

    def test_relocated_live_runtime_and_smokes_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            summary = validator.validate(
                self.root, config_path, artifact_context=ArtifactContext.live(base),
            )
        self.assertTrue(summary["live"])

    def test_relocated_m21_base_is_used_for_patch_check(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, result_source = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            summary = validator.validate(
                self.root, config_path, artifact_context=ArtifactContext.live(base),
            )
            observed_tree = _git(result_source, "rev-parse", "HEAD^{tree}")
        self.assertEqual(summary["source_tree"], observed_tree)

    def test_required_live_inputs_are_the_exact_runtime_closure(self) -> None:
        requirements = validator.required_live_inputs(self.root)
        keys = tuple((item.logical_set, item.relative_path, item.kind) for item in requirements)
        expected = expected_runtime_closure(
            "v2-m22-final-runtime-c",
            "build-final",
            (
                "source-g15-toyland-road", "source-g16-toyland-cargo", "source-g17-arctic-rail",
                "source-g18-tropic-water", "source-g19-toyland-air", "source-g20-tropic-aaahogex",
                "source-g21-arctic-content", "source-g21-tropic-gamescript",
            ),
        )
        self.assertEqual(keys, expected)
        self.assertEqual(len(keys), len(set(keys)))

    def test_missing_live_input_fails_before_git_or_semantic_reader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            (base / "v2-m22-final-runtime-c/base.cfg").unlink()
            with mock.patch.object(validator, "git", side_effect=AssertionError("Git ran before preflight")), \
                 mock.patch.object(validator, "_validate_live_source", side_effect=AssertionError("source reader ran before preflight")), \
                 mock.patch.object(validator, "_validate_live_files", side_effect=AssertionError("file reader ran before preflight")):
                with self.assertRaisesRegex(ArtifactContextError, "missing"):
                    validator.validate(
                        self.root, config_path, artifact_context=ArtifactContext.live(base),
                    )

    def test_recorded_runtime_path_traversal_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["executable"]["path"] = value["retained_artifact"] + "/../escape"
        self.mutation_fails(value, "normalized POSIX")

    def test_runtime_file_alias_fails_offline(self) -> None:
        value = copy.deepcopy(self.source)
        value["build"]["logs"]["build"] = copy.deepcopy(value["build"]["logs"]["configure"])
        self.mutation_fails(value, "duplicate")

    def test_hardlinked_live_inputs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            result = base / "v2-m22-final-runtime-c"
            first = result / "smokes/source-g15-toyland-road/openttd.log"
            second = result / "smokes/source-g16-toyland-cargo/openttd.log"
            second.unlink()
            os.link(first, second)
            with self.assertRaisesRegex(validator.M22RuntimeSourceError, "hard link"):
                validator.validate(
                    self.root, config_path, artifact_context=ArtifactContext.live(base),
                )

    def test_symlinked_live_input_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            result = base / "v2-m22-final-runtime-c"
            config = result / "base.cfg"
            target = result / "untracked-target.cfg"
            target.write_bytes(config.read_bytes())
            config.unlink()
            config.symlink_to(target)
            with self.assertRaisesRegex(ArtifactContextError, "symlink"):
                validator.validate(
                    self.root, config_path, artifact_context=ArtifactContext.live(base),
                )

    def test_historical_repository_commit_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["repository"]["commit"] = "0" * 40
        self.mutation_fails(value, "git cat-file")

    def test_historical_repository_tree_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["repository"]["tree"] = "0" * 40
        self.mutation_fails(value, "historical repository identity")

    def test_patch_digest_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["patch"]["sha256"] = "0" * 64
        self.mutation_fails(value, "patch identity")

    def test_prerequisite_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["prerequisites"]["m20_source_record_sha256"] = "0" * 64
        self.mutation_fails(value, "prerequisite identity")

    def test_final_manifest_open_claim_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["final_boundary"]["manifest_opened"] = True
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)

    def test_public_smoke_seed_leak_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["smokes"][0]["case"]["seed"] = 1
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)

    def test_smoke_order_mutation_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["smokes"][0], value["smokes"][1] = value["smokes"][1], value["smokes"][0]
        self.mutation_fails(value, "inventory/order")

    def test_vacuous_service_metric_fails(self) -> None:
        value = copy.deepcopy(self.source)
        value["smokes"][0]["metrics"]["delivered"] = 0
        self.mutation_fails(value, "useful-service smoke is vacuous")

    def test_executable_identity_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            value["executable"]["sha256"] = "0" * 64
            for smoke in value["smokes"]:
                smoke["executable_sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(
                    self.root, config_path, artifact_context=ArtifactContext.live(base),
                )

    def test_smoke_report_digest_mutation_fails_live(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            value, config_path, _, _ = make_live_runtime_fixture(
                self.root, base, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            value["smokes"][0]["report_sha256"] = "0" * 64
            config_path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactContextError, "SHA-256 mismatch"):
                validator.validate(
                    self.root, config_path, artifact_context=ArtifactContext.live(base),
                )

    def test_removed_base_source_option_exits_two(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                validator.main(["--root", str(self.root), "--base" + "-source", str(self.root)])
        self.assertEqual(raised.exception.code, 2)

    def test_cli_artifact_root_wins_over_environment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            parent = pathlib.Path(raw).resolve()
            configured = parent / "configured"
            configured.mkdir()
            _, config_path, _, _ = make_live_runtime_fixture(
                self.root, configured, self.source,
                patches=(preparation.PATCH,), logical_set="v2-m22-final-runtime-c",
            )
            with mock.patch.dict(os.environ, {ARTIFACT_ROOT_ENV: str(parent / "wrong")}, clear=False):
                with contextlib.redirect_stdout(io.StringIO()):
                    status = validator.main([
                        "--root", str(self.root), "--config", str(config_path),
                        "--artifact-root", str(configured),
                    ])
        self.assertEqual(status, 0)

    def test_relative_cli_artifact_root_fails_without_environment_fallback(self) -> None:
        with mock.patch.dict(os.environ, {ARTIFACT_ROOT_ENV: str(self.root)}, clear=False):
            with contextlib.redirect_stdout(io.StringIO()):
                status = validator.main(["--root", str(self.root), "--artifact-root", "relative/artifacts"])
        self.assertEqual(status, 1)

    def test_ctest_claim_mutation_fails_schema(self) -> None:
        value = copy.deepcopy(self.source)
        value["build"]["upstream_ctest"]["passed"] = 97
        schema = validator.load(self.root / validator.SCHEMA)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(value)


if __name__ == "__main__":
    unittest.main()
