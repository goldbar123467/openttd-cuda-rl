#!/usr/bin/env python3
"""Executable, offline tests for every mandatory PORT-001 contract ID."""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import json
import os
import pathlib
import random
import re
import shutil
import stat
import subprocess
import sys
import textwrap
import uuid
import zipfile
from collections.abc import Callable, Iterator

import jsonschema


EXPECTED_SUBMODULE = "29f808ef0022064e6d9a83c8476d1e0f4686af86"
EXPECTED_VERSION = "OpenTTD 20260729--g29f808ef00"
SECRET_ENV_RE = re.compile(r"(?:TOKEN|SECRET|PASSWORD|PASSWD|PRIVATE|CREDENTIAL|API_KEY|AUTH)", re.I)


class TestFailure(AssertionError):
    pass


class CommandFailure(TestFailure):
    pass


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write(path: pathlib.Path, data: str | bytes, executable: bool = False) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def strict_json_bytes(data: bytes) -> object:
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 byte-order mark is forbidden")
    text = data.decode("utf-8")

    def reject_duplicate(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate object key: {key}")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=reject_duplicate)


def strict_json(path: pathlib.Path) -> object:
    return strict_json_bytes(path.read_bytes())


def canonical_bytes(value: object) -> bytes:
    def reject_floats(item: object) -> None:
        if isinstance(item, float):
            raise ValueError("floats are outside the P0 canonical subset")
        if isinstance(item, dict):
            for child in item.values():
                reject_floats(child)
        elif isinstance(item, list):
            for child in item:
                reject_floats(child)

    reject_floats(value)
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


class Harness:
    def __init__(self, repository: pathlib.Path, work: pathlib.Path, tools_python: pathlib.Path) -> None:
        self.repository = repository.resolve()
        self.work = work.resolve()
        self.runner = self.repository / "oracle/runner"
        self.manifests = self.repository / "oracle/manifests"
        self.validator = self.repository / "tools/validate_manifest.py"
        # Preserve the venv launcher path: resolving its symlink would bypass
        # pyvenv.cfg and silently execute the host interpreter instead.
        self.tools_python = tools_python.absolute()
        self.case_index = 0
        self.passed: list[str] = []
        self._baseline_source = strict_json(self.manifests / "baseline/openttd-source.json")
        self._source_schema = strict_json(self.manifests / "schema/source.schema.json")
        self._test_inventory = strict_json(self.manifests / "baseline/tests-relwithdebinfo.json")
        assert isinstance(self._baseline_source, dict)
        assert isinstance(self._source_schema, dict)
        assert isinstance(self._test_inventory, dict)
        names = self._test_inventory.get("test_names")
        if not isinstance(names, list) or len(names) != 99 or not all(isinstance(item, str) for item in names):
            raise TestFailure("committed test inventory must contain exactly 99 string names")
        self.test_names: list[str] = names
        serial = self._test_inventory.get("serial_tests")
        if not isinstance(serial, list) or not all(isinstance(item, str) for item in serial):
            raise TestFailure("committed test inventory must contain serial_tests string names")
        self.serial_tests: list[str] = serial
        self.clean_status_before = self.git("status", "--porcelain=v1", "--untracked-files=all").stdout
        probe = self.run(
            [self.tools_python, "-c", "import jsonschema, rfc8785"],
            timeout=30,
        )
        self.assert_success(probe, "P0 tools Python dependency probe")

    def git(self, *args: str, cwd: pathlib.Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.run(["git", *args], cwd=cwd or self.repository, check=check)

    def run(
        self,
        argv: list[str | pathlib.Path],
        *,
        cwd: pathlib.Path | None = None,
        env: dict[str, str] | None = None,
        check: bool = False,
        timeout: int = 180,
    ) -> subprocess.CompletedProcess[str]:
        command = [str(item) for item in argv]
        command_env = os.environ.copy()
        command_env.update(
            {
                "LC_ALL": "C.UTF-8",
                "LANG": "C.UTF-8",
                "TZ": "UTC",
                "PYTHONHASHSEED": "0",
                "http_proxy": "http://127.0.0.1:9",
                "https_proxy": "http://127.0.0.1:9",
                "HTTP_PROXY": "http://127.0.0.1:9",
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "ALL_PROXY": "http://127.0.0.1:9",
                "NO_PROXY": "",
            }
        )
        if env:
            command_env.update(env)
        result = subprocess.run(
            command,
            cwd=str(cwd or self.repository),
            env=command_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        if check and result.returncode != 0:
            raise CommandFailure(
                f"command failed ({result.returncode}): {command!r}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def fresh(self, label: str) -> pathlib.Path:
        self.case_index += 1
        path = self.work / f"{self.case_index:03d}-{label}"
        if path.exists():
            raise TestFailure(f"test path unexpectedly exists: {path}")
        path.mkdir(parents=True)
        return path

    def assert_success(self, result: subprocess.CompletedProcess[str], context: str) -> None:
        if result.returncode != 0:
            raise TestFailure(f"{context}: expected success, got {result.returncode}\n{result.stdout}\n{result.stderr}")

    def assert_failure(self, result: subprocess.CompletedProcess[str], *needles: str) -> None:
        if result.returncode == 0:
            raise TestFailure("expected command failure, got success")
        combined = result.stdout + result.stderr
        for needle in needles:
            if needle not in combined:
                raise TestFailure(f"failure output omitted {needle!r}:\n{combined}")

    def assert_unchanged(self) -> None:
        after = self.git("status", "--porcelain=v1", "--untracked-files=all").stdout
        if after != self.clean_status_before:
            raise TestFailure(f"test suite changed the repository worktree\nbefore:\n{self.clean_status_before}\nafter:\n{after}")

    def case(self, test_id: str, description: str, function: Callable[[], None]) -> None:
        try:
            function()
        except Exception as exc:
            print(f"not ok {len(self.passed) + 1} - {test_id} {description}", flush=True)
            print(f"# {type(exc).__name__}: {exc}", flush=True)
            raise
        self.passed.append(test_id)
        print(f"ok {len(self.passed)} - {test_id} {description}", flush=True)

    def schema_validate(self, value: object, schema: dict[str, object] | None = None) -> None:
        jsonschema.Draft202012Validator(schema or self._source_schema, format_checker=jsonschema.FormatChecker()).validate(value)

    def schema_invalid(self, value: object, schema: dict[str, object] | None = None) -> None:
        try:
            self.schema_validate(value, schema)
        except jsonschema.ValidationError:
            return
        raise TestFailure("mutant unexpectedly passed Draft 2020-12 validation")

    def validator_run(
        self,
        label: str,
        schema: pathlib.Path,
        *,
        value: object | None = None,
        raw: bytes | None = None,
        profile_lock: pathlib.Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        root = self.fresh(label)
        instance = root / "instance.json"
        if (value is None) == (raw is None):
            raise TestFailure("validator fixture requires exactly one of value or raw")
        if raw is not None:
            write(instance, raw)
        else:
            write(instance, json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
        command: list[str | pathlib.Path] = [
            self.tools_python,
            self.validator,
            "--schema",
            schema,
        ]
        if profile_lock is not None:
            command.extend(["--profile-lock", profile_lock])
        command.append(instance)
        return self.run(command, timeout=30)

    def production_valid(self, label: str, value: object, schema: pathlib.Path | None = None) -> None:
        result = self.validator_run(label, schema or self.manifests / "schema/source.schema.json", value=value)
        self.assert_success(result, "production manifest validation")

    def production_invalid(
        self,
        label: str,
        *,
        value: object | None = None,
        raw: bytes | None = None,
        schema: pathlib.Path | None = None,
        needle: str = "invalid JSON artifact",
    ) -> None:
        result = self.validator_run(
            label,
            schema or self.manifests / "schema/source.schema.json",
            value=value,
            raw=raw,
        )
        self.assert_failure(result, needle)

    def validate_frozen_profile_pairs(self) -> None:
        pairs = {
            "build-relwithdebinfo.json": "build.schema.json",
            "dependencies-ubuntu-24.04.json": "dependency.schema.json",
            "opengfx-8.0.json": "opengfx.schema.json",
            "openttd-source.json": "source.schema.json",
            "tests-relwithdebinfo.json": "test-inventory.schema.json",
            "toolchain-linux-x86_64.json": "toolchain.schema.json",
        }
        lock = self.manifests / "baseline/P0_PROFILE_LOCK.json"
        for manifest_name, schema_name in pairs.items():
            manifest = self.manifests / "baseline" / manifest_name
            schema = self.manifests / "schema" / schema_name
            positive = self.run(
                [self.tools_python, self.validator, "--schema", schema, "--profile-lock", lock, manifest],
                timeout=30,
            )
            self.assert_success(positive, f"frozen baseline/schema pair {manifest_name}")

            mutant = strict_json(manifest)
            if not isinstance(mutant, dict):
                raise TestFailure(f"baseline manifest is not an object: {manifest_name}")
            mutant.pop("schema_version", None)
            negative = self.validator_run(f"pair-negative-{manifest.stem}", schema, value=mutant)
            self.assert_failure(negative, "schema validation failed")
        print("# six frozen baseline/schema pairs: positive and negative validation PASS", flush=True)

    def strict_manifest_validate(self, value: dict[str, object]) -> None:
        self.schema_validate(value)
        allowlist = value.get("environment_allowlist")
        if not isinstance(allowlist, list):
            raise ValueError("environment_allowlist must be an array")
        forbidden = [name for name in allowlist if isinstance(name, str) and SECRET_ENV_RE.search(name)]
        if forbidden:
            raise ValueError(f"secret-named environment entries are forbidden: {forbidden}")

    def invoke_common(self, common: pathlib.Path, body: str, *arguments: pathlib.Path | str) -> subprocess.CompletedProcess[str]:
        command = f'source "$1"; shift; {body}'
        return self.run(["bash", "-c", command, "p001-common", common, *arguments])

    def sandbox_runner(self, label: str, archive_digest: str, content_digest: str) -> pathlib.Path:
        root = self.fresh(label) / "sandbox-repository"
        destination = root / "oracle/runner"
        shutil.copytree(self.runner, destination)
        shutil.copytree(self.manifests, root / "oracle/manifests")
        common = destination / "common.sh"
        text = common.read_text(encoding="utf-8")
        replacements = {
            "P0_OPENGFX_ARCHIVE_SHA256": archive_digest,
            "P0_OPENGFX_INSTALLED_SHA256": content_digest,
        }
        for name, value in replacements.items():
            pattern = rf"(readonly {name}=)'[0-9a-f]{{64}}'"
            text, count = re.subn(pattern, rf"\1'{value}'", text)
            if count != 1:
                raise TestFailure(f"could not inject exactly one {name} constant")
        common.write_text(text, encoding="utf-8")
        return root

    def make_zip(self, root: pathlib.Path, member: str, payload: bytes) -> pathlib.Path:
        archive = root / "fixture.zip"
        root.mkdir(parents=True, exist_ok=True)
        info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        with zipfile.ZipFile(archive, "w") as handle:
            handle.writestr(info, payload)
        return archive

    def run_fetch(
        self,
        label: str,
        archive: pathlib.Path,
        expected_archive_digest: str,
        content: bytes,
        *,
        destination_seed: bytes | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], pathlib.Path, pathlib.Path]:
        sandbox = self.sandbox_runner(label, expected_archive_digest, hashlib.sha256(content).hexdigest())
        artifact = sandbox.parent / "artifacts"
        input_archive = artifact / "inputs/archive.zip"
        input_archive.parent.mkdir(parents=True)
        shutil.copyfile(archive, input_archive)
        destination = artifact / "content"
        destination.mkdir(parents=True)
        if destination_seed is not None:
            write(destination / "opengfx-8.0.tar", destination_seed)
        result = self.run(
            [
                sandbox / "oracle/runner/fetch_opengfx.sh",
                "--destination",
                destination,
                "--artifact-root",
                artifact,
                "--input-archive",
                input_archive,
            ],
            env={"P0_TEST_MODE": "1"},
        )
        return result, artifact, destination

    @contextlib.contextmanager
    def outer_worktree(
        self,
        label: str,
        *,
        branch: str = "detached",
        with_submodule: bool = True,
        submodule_commit: str = EXPECTED_SUBMODULE,
    ) -> Iterator[pathlib.Path]:
        parent = self.fresh(label)
        outer = parent / "outer"
        branch_name: str | None = None
        if branch == "detached":
            self.git("worktree", "add", "--detach", str(outer), "HEAD", check=True)
        elif branch == "main":
            self.git("worktree", "add", str(outer), "main", check=True)
        elif branch == "named":
            branch_name = f"p001-test-{uuid.uuid4().hex}"
            self.git("worktree", "add", "-b", branch_name, str(outer), "HEAD", check=True)
        else:
            raise ValueError(branch)
        subpath = outer / "openttd-upstream"
        sub_added = False
        try:
            # A pre-PORT001 lineage worktree did not contain these files, while
            # a clean checkout of the committed milestone does. Overlay the
            # live test inputs in both cases so the same mutation fixtures run
            # before and after the harness itself becomes tracked.
            shutil.copytree(self.runner, outer / "oracle/runner", dirs_exist_ok=True)
            shutil.copytree(self.manifests, outer / "oracle/manifests", dirs_exist_ok=True)
            (outer / "tools").mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.repository / "tools/verify_host_profile.py", outer / "tools/verify_host_profile.py")
            if with_submodule:
                if subpath.exists():
                    subpath.rmdir()
                self.git(
                    "worktree",
                    "add",
                    "--detach",
                    str(subpath),
                    submodule_commit,
                    cwd=self.repository / "openttd-upstream",
                    check=True,
                )
                sub_added = True
            yield outer
        finally:
            if sub_added:
                self.git("worktree", "remove", "--force", str(subpath), cwd=self.repository / "openttd-upstream", check=False)
            self.git("worktree", "remove", "--force", str(outer), check=False)
            self.git("worktree", "prune", check=False)
            if branch_name:
                self.git("branch", "-D", branch_name, check=False)

    def preflight(self, root: pathlib.Path, mode: str = "read-only") -> tuple[subprocess.CompletedProcess[str], pathlib.Path]:
        artifact = root.parent / f"{root.name}-p001-artifacts"
        content = artifact / "content"
        result = self.run(
            [
                root / "oracle/runner/preflight.sh",
                "--mode",
                mode,
                "--artifact-root",
                artifact,
                "--content-root",
                content,
            ],
            timeout=120,
        )
        return result, artifact

    def make_cmake_source(self, artifact: pathlib.Path, *, missing_dependency: bool = False, unresolved: bool = False) -> pathlib.Path:
        source = artifact / "test-fixtures/source"
        source.mkdir(parents=True)
        if unresolved:
            cmake = """
                cmake_minimum_required(VERSION 3.28)
                project(P0Fixture LANGUAGES C CXX)
                set(PERSONAL_DIR ".openttd" CACHE STRING "")
                set(SHARED_DIR "(not set)" CACHE STRING "")
                set(GLOBAL_DIR "${CMAKE_INSTALL_PREFIX}/share/games/openttd" CACHE STRING "")
                set(HOST_BINARY_DIR "" CACHE PATH "")
                option(OPTION_DEDICATED "" OFF)
                option(OPTION_INSTALL_FHS "" ON)
                option(OPTION_USE_ASSERTS "" ON)
                option(OPTION_PACKAGE_DEPENDENCIES "" OFF)
                option(OPTION_FORCE_COLORED_OUTPUT "" OFF)
                option(OPTION_USE_NSIS "" OFF)
                option(OPTION_TOOLS_ONLY "" OFF)
                option(OPTION_DOCS_ONLY "" OFF)
                option(OPTION_ALLOW_INVALID_SIGNATURE "" OFF)
                option(OPTION_LINE_IN_DOXYGEN_WARNINGS "" ON)
                option(OPTION_SURVEY_KEY "" OFF)
                option(OPTION_DOXYGEN_WARN_FILE "" OFF)
                option(OPTION_DOXYGEN_GS_WARN_FILE "" OFF)
                option(OPTION_DOXYGEN_AI_WARN_FILE "" OFF)
                foreach(package CURL Fluidsynth Fontconfig Freetype Harfbuzz ICU LZO LibLZMA Ogg OpenGL Opus OpusFile PNG ZLIB)
                    set(FIND_PACKAGE_MESSAGE_DETAILS_${package} "[p0-fixture][v1()]" CACHE INTERNAL "")
                endforeach()
                foreach(feature WITH_PNG WITH_ZLIB WITH_LIBLZMA WITH_LZO WITH_CURL WITH_FLUIDSYNTH WITH_SDL2 WITH_FREETYPE WITH_FONTCONFIG WITH_HARFBUZZ WITH_ICU_I18N WITH_ICU_UC WITH_OPUSFILE WITH_OPENGL WITH_SSE)
                    message(STATUS "${feature} found -- -D${feature}")
                endforeach()
                set(SDL2_DIR "/p0/test-fixture/sdl2" CACHE PATH "")
                add_library(p0_contract_missing SHARED missing.cpp)
                add_executable(openttd main.cpp)
                target_link_libraries(openttd PRIVATE p0_contract_missing)
                set_target_properties(openttd PROPERTIES INSTALL_RPATH "$ORIGIN")
                install(TARGETS openttd RUNTIME DESTINATION games)
                install(FILES "${CMAKE_BINARY_DIR}/baseset/opengfx-8.0.tar" DESTINATION share/games/openttd/baseset)
            """
            write(source / "missing.cpp", 'extern "C" int p0_missing() { return 0; }\n')
            write(source / "main.cpp", 'extern "C" int p0_missing(); int main() { return p0_missing(); }\n')
        else:
            required = "find_package(P0DefinitelyMissing 99 REQUIRED)" if missing_dependency else ""
            cmake = f"""
                cmake_minimum_required(VERSION 3.28)
                project(P0Fixture LANGUAGES C CXX)
                set(PERSONAL_DIR ".openttd" CACHE STRING "")
                set(SHARED_DIR "(not set)" CACHE STRING "")
                set(GLOBAL_DIR "${{CMAKE_INSTALL_PREFIX}}/share/games/openttd" CACHE STRING "")
                set(HOST_BINARY_DIR "" CACHE PATH "")
                option(OPTION_DEDICATED "" OFF)
                option(OPTION_INSTALL_FHS "" ON)
                option(OPTION_USE_ASSERTS "" ON)
                option(OPTION_PACKAGE_DEPENDENCIES "" OFF)
                option(OPTION_FORCE_COLORED_OUTPUT "" OFF)
                option(OPTION_USE_NSIS "" OFF)
                option(OPTION_TOOLS_ONLY "" OFF)
                option(OPTION_DOCS_ONLY "" OFF)
                option(OPTION_ALLOW_INVALID_SIGNATURE "" OFF)
                option(OPTION_LINE_IN_DOXYGEN_WARNINGS "" ON)
                option(OPTION_SURVEY_KEY "" OFF)
                option(OPTION_DOXYGEN_WARN_FILE "" OFF)
                option(OPTION_DOXYGEN_GS_WARN_FILE "" OFF)
                option(OPTION_DOXYGEN_AI_WARN_FILE "" OFF)
                {required}
                foreach(package CURL Fluidsynth Fontconfig Freetype Harfbuzz ICU LZO LibLZMA Ogg OpenGL Opus OpusFile PNG ZLIB)
                    set(FIND_PACKAGE_MESSAGE_DETAILS_${{package}} "[p0-fixture][v1()]" CACHE INTERNAL "")
                endforeach()
                foreach(feature WITH_PNG WITH_ZLIB WITH_LIBLZMA WITH_LZO WITH_CURL WITH_FLUIDSYNTH WITH_SDL2 WITH_FREETYPE WITH_FONTCONFIG WITH_HARFBUZZ WITH_ICU_I18N WITH_ICU_UC WITH_OPUSFILE WITH_OPENGL WITH_SSE)
                    message(STATUS "${{feature}} found -- -D${{feature}}")
                endforeach()
                set(SDL2_DIR "/p0/test-fixture/sdl2" CACHE PATH "")
                add_custom_target(p0_fixture ALL COMMAND "${{CMAKE_COMMAND}}" -E true)
            """
        write(source / "CMakeLists.txt", textwrap.dedent(cmake).lstrip())
        self.run(["git", "init", "-q", "--initial-branch=fixture", source], check=True)
        self.run(["git", "config", "user.name", "P0 Test"], cwd=source, check=True)
        self.run(["git", "config", "user.email", "p0-test@example.invalid"], cwd=source, check=True)
        self.run(["git", "add", "."], cwd=source, check=True)
        self.run(["git", "commit", "-q", "-m", "fixture"], cwd=source, check=True)
        return source

    def configure_fixture(self, label: str, *, missing_dependency: bool = False, unresolved: bool = False, sandbox: pathlib.Path | None = None) -> tuple[subprocess.CompletedProcess[str], pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path]:
        root = sandbox or self.fresh(label)
        artifact = (sandbox.parent / "artifacts") if sandbox else (root / "artifacts")
        source = self.make_cmake_source(artifact, missing_dependency=missing_dependency, unresolved=unresolved)
        build = artifact / "build"
        install = artifact / "install"
        runner = (sandbox / "oracle/runner") if sandbox else self.runner
        result = self.run(
            [
                runner / "configure_reference.sh",
                "--source-root",
                source,
                "--build-root",
                build,
                "--install-root",
                install,
                "--artifact-root",
                artifact,
                "--test-source-override",
            ],
            env={"P0_TEST_MODE": "1"},
            timeout=180,
        )
        return result, artifact, source, build, install

    def fake_build_tree(self, label: str, mutations: dict[str, str]) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path]:
        root = self.fresh(label)
        artifact = root / "artifacts"
        build = artifact / "build"
        install = artifact / "install"
        build.mkdir(parents=True)
        install.mkdir(parents=True)
        values = {
            "CMAKE_BUILD_TYPE": "CMAKE_BUILD_TYPE:STRING=RelWithDebInfo",
            "CMAKE_GENERATOR": "CMAKE_GENERATOR:INTERNAL=Ninja",
            "OPTION_DEDICATED": "OPTION_DEDICATED:BOOL=OFF",
            "OPTION_INSTALL_FHS": "OPTION_INSTALL_FHS:BOOL=ON",
            "OPTION_USE_ASSERTS": "OPTION_USE_ASSERTS:BOOL=ON",
            "CMAKE_INSTALL_PREFIX": f"CMAKE_INSTALL_PREFIX:PATH={install}",
        }
        values.update(mutations)
        write(build / "CMakeCache.txt", "\n".join(values.values()) + "\n")
        manifest = artifact / "configure.json"
        write(
            manifest,
            json.dumps(
                {
                    "authoritative": {"source_commit": EXPECTED_SUBMODULE},
                    "diagnostics": {"build_root": str(build), "install_root": str(install)},
                    "return_code": 0,
                    "status": "PASS",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
        )
        return artifact, build, install, manifest

    def run_build(self, runner: pathlib.Path, artifact: pathlib.Path, build: pathlib.Path, install: pathlib.Path, manifest: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return self.run(
            [
                runner / "build_reference.sh",
                "--build-root",
                build,
                "--install-root",
                install,
                "--artifact-root",
                artifact,
                "--configuration-manifest",
                manifest,
                "--parallel",
                "1",
                "--test-configuration-override",
            ],
            env={"P0_TEST_MODE": "1"},
            timeout=180,
        )

    def make_ctest_build(
        self,
        root: pathlib.Path,
        names: list[str],
        *,
        failure: str | None = None,
        skipped: str | None = None,
        timed_out: str | None = None,
    ) -> pathlib.Path:
        build = root / "build"
        build.mkdir(parents=True)
        lines = ["# synthetic, deterministic CTest inventory"]
        for name in names:
            escaped = name.replace("]=]", "] = ]")
            if name == failure:
                command = '"/bin/false"'
            elif name == skipped:
                command = '"/p0/nonexistent-test-executable"'
            elif name == timed_out:
                command = '"/bin/sh" "-c" "while :; do :; done"'
            else:
                command = '"/bin/true"'
            lines.append(f"add_test([=[{escaped}]=] {command})")
            lines.append(f'set_tests_properties([=[{escaped}]=] PROPERTIES WORKING_DIRECTORY "{build}")')
            if name in self.serial_tests:
                lines.append(f"set_tests_properties([=[{escaped}]=] PROPERTIES RUN_SERIAL TRUE)")
        write(build / "CTestTestfile.cmake", "\n".join(lines) + "\n")
        return build

    def run_ctest_runner(
        self,
        label: str,
        names: list[str],
        *,
        baseline_names: list[str] | None = None,
        failure: str | None = None,
        skipped: str | None = None,
        timed_out: str | None = None,
        malformed_baseline: bool = False,
        poison_results_dir: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], pathlib.Path, pathlib.Path]:
        root = self.fresh(label)
        artifact = root / "artifacts"
        (artifact / "manifests").mkdir(parents=True)
        build = self.make_ctest_build(artifact, names, failure=failure, skipped=skipped, timed_out=timed_out)
        baseline = root / "baseline.json"
        if malformed_baseline:
            write(baseline, '{"test_names": [}\n')
        else:
            selected_names = baseline_names if baseline_names is not None else self.test_names
            write(
                baseline,
                json.dumps({"serial_tests": [name for name in self.serial_tests if name in selected_names], "test_names": selected_names}) + "\n",
            )
        if poison_results_dir:
            write(artifact / "test-results", "not a directory\n")
        command: list[str | pathlib.Path] = [
            self.runner / "test_reference.sh",
            "--build-root",
            build,
            "--artifact-root",
            artifact,
            "--baseline-inventory",
            baseline,
        ]
        environment = None
        if timed_out is not None:
            command.extend(["--test-timeout", "1"])
            environment = {"P0_TEST_MODE": "1"}
        result = self.run(command, env=environment, timeout=180)
        return result, artifact, build

    def fake_openttd(self, path: pathlib.Path, *, version: str = EXPECTED_VERSION, include_null_video: bool = True, smoke_rc: int = 0) -> None:
        video = "null: Null Video Driver" if include_null_video else "sdl: Graphical Video Driver"
        body = f"""#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "${{1-}}" == -h ]]; then
    cat <<'EOF'
{version}
OpenGFX: OpenGFX base graphics set for OpenTTD. [OpenGFX 8.0]

List of music drivers:
null: Null Music Driver

List of sound drivers:
null: Null Sound Driver

List of video drivers:
{video}

List of blitters:
null: Null Blitter

EOF
    exit 0
fi
printf '%s\\n' "$*"
exit {smoke_rc}
"""
        write(path, body, executable=True)

    def smoke_fixture(
        self,
        label: str,
        *,
        version: str = EXPECTED_VERSION,
        include_null_video: bool = True,
        smoke_rc: int = 0,
        content_present: bool = True,
        manifest_digest: str | None = None,
        omit_digest: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], pathlib.Path]:
        content = b"P0 deterministic OpenGFX stand-in\n"
        sandbox = self.sandbox_runner(label, "0" * 64, hashlib.sha256(content).hexdigest())
        artifact = sandbox.parent / "artifacts"
        (artifact / "manifests").mkdir(parents=True)
        install = artifact / "install"
        executable = install / "games/openttd"
        self.fake_openttd(executable, version=version, include_null_video=include_null_video, smoke_rc=smoke_rc)
        if content_present:
            write(install / "share/games/openttd/baseset/opengfx-8.0.tar", content)
        executable_digest = sha256(executable)
        executable_value: dict[str, object] = {}
        if not omit_digest:
            executable_value["sha256"] = manifest_digest or executable_digest
        manifest = artifact / "build.json"
        write(
            manifest,
            json.dumps(
                {
                    "authoritative": {"executable": executable_value, "source_commit": EXPECTED_SUBMODULE},
                    "diagnostics": {"install_root": str(install)},
                    "return_code": 0,
                    "status": "PASS",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
        )
        result = self.run(
            [
                sandbox / "oracle/runner/smoke_reference.sh",
                "--install-root",
                install,
                "--artifact-root",
                artifact,
                "--build-manifest",
                manifest,
            ],
            timeout=140,
        )
        return result, artifact

    # Repository tests -------------------------------------------------
    def rep001(self) -> None:
        root = self.fresh("rep001")
        result = self.run(
            [self.runner / "preflight.sh", "--mode", "read-only", "--artifact-root", root / "artifacts", "--content-root", root / "artifacts/content"],
            timeout=120,
        )
        self.assert_success(result, "current repository preflight")
        detail = strict_json(root / "artifacts/results/preflight-details.json")
        if not isinstance(detail, dict) or detail.get("status") != "PASS":
            raise TestFailure("preflight detail did not report PASS")

    def rep002(self) -> None:
        root = self.fresh("rep002")
        wrong_repository = root / "wrong-submodule"
        self.run(["git", "init", "-q", "--initial-branch=fixture", wrong_repository], check=True)
        self.run(["git", "config", "user.name", "P0 Test"], cwd=wrong_repository, check=True)
        self.run(["git", "config", "user.email", "p0-test@example.invalid"], cwd=wrong_repository, check=True)
        write(wrong_repository / "sentinel", "wrong commit\n")
        self.run(["git", "add", "sentinel"], cwd=wrong_repository, check=True)
        self.run(["git", "commit", "-q", "-m", "wrong pin"], cwd=wrong_repository, check=True)
        wrong = self.run(["git", "rev-parse", "HEAD"], cwd=wrong_repository, check=True).stdout.strip()
        result = self.invoke_common(self.runner / "common.sh", 'p0_require_commit "$1" "$2"', wrong_repository, EXPECTED_SUBMODULE)
        self.assert_failure(result, "commit mismatch", EXPECTED_SUBMODULE, wrong)

    def rep003(self) -> None:
        with self.outer_worktree("rep003") as outer:
            changed = outer / "openttd-upstream/P001_DIRTY_SENTINEL"
            write(changed, "secret-content-must-not-be-logged\n")
            result = self.invoke_common(outer / "oracle/runner/common.sh", 'p0_require_clean_submodule "$1"', outer / "openttd-upstream")
            self.assert_failure(result, "dirty submodule", "P001_DIRTY_SENTINEL")
            if "secret-content-must-not-be-logged" in result.stderr:
                raise TestFailure("dirty-submodule failure leaked file contents")

    def rep004(self) -> None:
        with self.outer_worktree("rep004", with_submodule=False) as outer:
            result, _ = self.preflight(outer)
            self.assert_failure(result, "git submodule update --init --recursive")

    def rep005(self) -> None:
        with self.outer_worktree("rep005") as outer:
            modules = outer / ".gitmodules"
            modules.write_text(modules.read_text(encoding="utf-8").replace("https://github.com/OpenTTD/OpenTTD.git", "https://example.invalid/changed.git"), encoding="utf-8")
            result, _ = self.preflight(outer)
            self.assert_failure(result, "modified submodule URL", "https://example.invalid/changed.git")

    def rep006(self) -> None:
        with self.outer_worktree("rep006", branch="main") as outer:
            result, _ = self.preflight(outer, "edit")
            self.assert_failure(result, "edit mode is forbidden on main")

    def rep007(self) -> None:
        with self.outer_worktree("rep007", branch="detached") as outer:
            result, _ = self.preflight(outer, "read-only")
            self.assert_success(result, "detached read-only preflight")

    def rep008(self) -> None:
        with self.outer_worktree("rep008", branch="named") as outer:
            dummy_access_key = "AKIA" + "IOSFODNN7EXAMPLE"
            dummy_secret_key = "wJalr" + "XUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
            staged = outer / "docs/p001-dummy-leak.txt"
            write(staged, f"aws_access_key_id={dummy_access_key}\naws_secret_access_key={dummy_secret_key}\n")
            self.run(["git", "add", "docs/p001-dummy-leak.txt"], cwd=outer, check=True)
            result, artifact = self.preflight(outer, "edit")
            self.assert_failure(result, "scanning staged content with redacted gitleaks output")
            combined = result.stdout + result.stderr
            for log in (artifact / "logs").glob("preflight.gitleaks.*.log"):
                combined += log.read_text(encoding="utf-8", errors="replace")
            if dummy_access_key in combined or dummy_secret_key in combined:
                raise TestFailure("preflight output did not redact staged dummy secret")

    def rep009(self) -> None:
        with self.outer_worktree("rep009", branch="named") as outer:
            write(outer / "build/CMakeCache.txt", "sentinel\n")
            self.run(["git", "add", "--force", "build/CMakeCache.txt"], cwd=outer, check=True)
            result, _ = self.preflight(outer, "edit")
            self.assert_failure(result, "generated build artifact is staged", "build/CMakeCache.txt")

    def rep010(self) -> None:
        mutant = copy.deepcopy(self._baseline_source)
        assert isinstance(mutant, dict)
        mutant["expected_outputs"][0]["name"] = "/workspace/private/output"  # type: ignore[index]
        self.production_invalid("rep010-validator", value=mutant, needle="absolute workspace path is forbidden")

    # Manifest tests ---------------------------------------------------
    def man001(self) -> None:
        value = copy.deepcopy(self._baseline_source)
        assert isinstance(value, dict)
        value.pop("diagnostics", None)
        self.production_valid("man001-validator", value)

    def source_mutant(self, mutation: Callable[[dict[str, object]], None]) -> dict[str, object]:
        value = copy.deepcopy(self._baseline_source)
        assert isinstance(value, dict)
        mutation(value)
        return value

    def man006(self) -> None:
        self.production_invalid(
            "man006-validator",
            raw=b'{"schema_version":1,"schema_version":1}',
            needle="duplicate JSON object key",
        )

    def man007(self) -> None:
        self.production_invalid(
            "man007-validator",
            raw=b'{"x":"\xff"}',
            needle="I/O or encoding failure",
        )

    def man008(self) -> None:
        self.production_invalid(
            "man008-validator",
            raw=b"\xef\xbb\xbf{}",
            needle="byte-order mark is forbidden",
        )

    def canonical_with_common(self, label: str, value_bytes: bytes) -> bytes:
        root = self.fresh(label)
        source = write(root / "input.json", value_bytes)
        output = root / "output.json"
        result = self.invoke_common(self.runner / "common.sh", 'p0_json_canonicalize "$1" "$2"', source, output)
        self.assert_success(result, "production canonicalizer")
        return output.read_bytes()

    def man011(self) -> None:
        one = self.canonical_with_common("man011-a", b'{"b":2,"a":1}\n')
        two = self.canonical_with_common("man011-b", b'{"a":1,"b":2}\n')
        if one != two:
            raise TestFailure("property order changed canonical bytes")

    def man012(self) -> None:
        one = self.canonical_with_common("man012-a", b'{ "a" : [1, 2] }\n')
        two = self.canonical_with_common("man012-b", b'{"a":[1,2]}')
        if one != two:
            raise TestFailure("insignificant whitespace changed canonical bytes")

    def man013(self) -> None:
        first = canonical_bytes(self._baseline_source)
        mutant = copy.deepcopy(self._baseline_source)
        assert isinstance(mutant, dict)
        mutant["status"] = "FAIL"
        mutant["status_reason"] = "deliberate mutation"
        if hashlib.sha256(first).digest() == hashlib.sha256(canonical_bytes(mutant)).digest():
            raise TestFailure("authoritative mutation did not change digest")
        version_result = self.invoke_common(
            self.runner / "common.sh",
            'p0_require_minimum_version "mutated-toolchain" "1.0.0" "999.0.0"',
        )
        self.assert_failure(version_result, "mutated-toolchain 1.0.0 is below required minimum 999.0.0")

    def man014(self) -> None:
        def identity(value: dict[str, object]) -> bytes:
            projected = {key: item for key, item in value.items() if key != "diagnostics"}
            return hashlib.sha256(canonical_bytes(projected)).digest()

        original = copy.deepcopy(self._baseline_source)
        mutant = copy.deepcopy(self._baseline_source)
        assert isinstance(original, dict) and isinstance(mutant, dict)
        mutant["diagnostics"] = {"note": "/different/generated/path"}
        if identity(original) != identity(mutant):
            raise TestFailure("diagnostic path changed experiment identity")
        if canonical_bytes(original) == canonical_bytes(mutant):
            raise TestFailure("full evidence bytes did not record diagnostic path change")

    def man015(self) -> None:
        mutant = self.source_mutant(lambda value: value.__setitem__("environment_allowlist", ["LC_ALL", "GITHUB_TOKEN"]))
        self.production_invalid("man015-validator", value=mutant, needle="secret-named environment entries are forbidden")

    def man010(self) -> None:
        root = self.fresh("man010")
        source = write(root / "floating-count.json", b'{"expected_count":99.0}\n')
        result = self.invoke_common(self.runner / "common.sh", 'p0_json_canonicalize "$1" "$2"', source, root / "canonical.json")
        self.assert_failure(result, "floating-point values are outside the P0 canonical JSON subset")

    # OpenGFX tests ----------------------------------------------------
    def gfx001(self) -> None:
        root = self.fresh("gfx001-input")
        payload = b"approved payload\n"
        archive = self.make_zip(root, "opengfx-8.0.tar", payload)
        result, _, destination = self.run_fetch("gfx001", archive, sha256(archive), payload)
        self.assert_success(result, "approved local archive")
        if (destination / "opengfx-8.0.tar").read_bytes() != payload:
            raise TestFailure("verified payload was not promoted")

    def gfx002(self) -> None:
        root = self.fresh("gfx002-input")
        payload = b"approved payload\n"
        archive = self.make_zip(root, "opengfx-8.0.tar", payload)
        expected = sha256(archive)
        data = bytearray(archive.read_bytes())
        data[len(data) // 2] ^= 1
        archive.write_bytes(data)
        result, _, destination = self.run_fetch("gfx002", archive, expected, payload)
        self.assert_failure(result, "SHA-256 mismatch")
        if (destination / "opengfx-8.0.tar").exists():
            raise TestFailure("mutated archive payload was promoted")

    def gfx003(self) -> None:
        root = self.fresh("gfx003-input")
        payload = b"approved payload\n"
        archive = self.make_zip(root, "opengfx-8.0.tar", payload)
        renamed = archive.with_name("unexpected-name.bin")
        archive.rename(renamed)
        result, _, destination = self.run_fetch("gfx003", renamed, sha256(renamed), payload)
        self.assert_success(result, "digest-authorized renamed archive")
        if not (destination / "opengfx-8.0.tar").is_file():
            raise TestFailure("renamed archive was not installed through explicit destination")

    def gfx004(self) -> None:
        root = self.fresh("gfx004-input")
        expected_archive = self.make_zip(root / "expected", "opengfx-8.0.tar", b"expected\n")
        wrong_archive = self.make_zip(root / "wrong", "opengfx-8.0.tar", b"wrong\n")
        result, _, _ = self.run_fetch("gfx004", wrong_archive, sha256(expected_archive), b"expected\n")
        self.assert_failure(result, "SHA-256 mismatch")

    def gfx_malicious(self, label: str, member: str) -> None:
        root = self.fresh(f"{label}-input")
        payload = b"payload\n"
        archive = self.make_zip(root, member, payload)
        result, _, destination = self.run_fetch(label, archive, sha256(archive), payload)
        self.assert_failure(result, "escapes extraction root")
        if (destination / "opengfx-8.0.tar").exists():
            raise TestFailure("unsafe archive was promoted")

    def gfx007(self) -> None:
        root = self.fresh("gfx007-input")
        payload = b"approved\n"
        archive = self.make_zip(root, "opengfx-8.0.tar", payload)
        result, _, destination = self.run_fetch("gfx007", archive, sha256(archive), payload, destination_seed=b"different\n")
        self.assert_failure(result, "differs and will not be overwritten")
        if (destination / "opengfx-8.0.tar").read_bytes() != b"different\n":
            raise TestFailure("differing destination was overwritten")

    def gfx008(self) -> None:
        root = self.fresh("gfx008-input")
        payload = b"payload\n"
        archive = self.make_zip(root, "opengfx-8.0.tar", payload)
        archive.write_bytes(archive.read_bytes()[:20])
        result, artifact, destination = self.run_fetch("gfx008", archive, sha256(archive), payload)
        self.assert_failure(result)
        if (destination / "opengfx-8.0.tar").exists():
            raise TestFailure("interrupted archive was promoted")
        if any(path.name == "opengfx-8.0.tar" for path in artifact.rglob("*")):
            raise TestFailure("interrupted input produced a final installed payload")

    def gfx009(self) -> None:
        root = self.fresh("gfx009-input")
        payload = b"verified offline payload\n"
        installed = write(root / "content/opengfx-8.0.tar", payload)
        sandbox = self.sandbox_runner("gfx009", "0" * 64, hashlib.sha256(payload).hexdigest())
        result = self.invoke_common(sandbox / "oracle/runner/common.sh", 'p0_require_sha256 "$1" "$2" "offline installed content"', installed, hashlib.sha256(payload).hexdigest())
        self.assert_success(result, "offline installed-content verification")

    def gfx010(self) -> None:
        root = self.fresh("gfx010-input")
        installed = write(root / "opengfx-8.0.tar", b"drift\n")
        expected = hashlib.sha256(b"approved\n").hexdigest()
        result = self.invoke_common(self.runner / "common.sh", 'p0_require_sha256 "$1" "$2" "installed OpenGFX content"', installed, expected)
        self.assert_failure(result, "installed OpenGFX content SHA-256 mismatch")

    # Build tests ------------------------------------------------------
    def bld001(self) -> None:
        result, artifact, _, build, _ = self.configure_fixture("bld001")
        self.assert_success(result, "fresh reference-profile configure")
        cache = (build / "CMakeCache.txt").read_text(encoding="utf-8")
        for line in ("CMAKE_BUILD_TYPE:STRING=RelWithDebInfo", "CMAKE_GENERATOR:INTERNAL=Ninja", "OPTION_USE_ASSERTS:BOOL=ON"):
            if line not in cache:
                raise TestFailure(f"fresh cache omitted {line}")
        if strict_json(artifact / "results/configure-reference.json").get("status") != "PASS":  # type: ignore[union-attr]
            raise TestFailure("configure result did not report PASS")

    def bld002(self) -> None:
        root = self.fresh("bld002")
        artifact = root / "artifacts"
        source = self.make_cmake_source(artifact)
        build = artifact / "build"
        install = artifact / "install"
        write(build / "CMakeCache.txt", "P001_INCOMPATIBLE_SENTINEL:BOOL=ON\n")
        result = self.run(
            [self.runner / "configure_reference.sh", "--source-root", source, "--build-root", build, "--install-root", install, "--artifact-root", artifact, "--test-source-override"],
            env={"P0_TEST_MODE": "1"},
            timeout=180,
        )
        self.assert_success(result, "incompatible cache isolation")
        if "P001_INCOMPATIBLE_SENTINEL" in (build / "CMakeCache.txt").read_text(encoding="utf-8"):
            raise TestFailure("incompatible cache was reused")

    def cache_failure(self, label: str, mutation: dict[str, str], expected: str) -> None:
        artifact, build, install, manifest = self.fake_build_tree(label, mutation)
        result = self.run_build(self.runner, artifact, build, install, manifest)
        self.assert_failure(result, expected)

    def bld007(self) -> None:
        result, artifact, _, _, _ = self.configure_fixture("bld007", missing_dependency=True)
        self.assert_failure(result)
        if "P0DefinitelyMissing" not in result.stderr and "P0DefinitelyMissing" not in result.stdout:
            logs = "".join(path.read_text(encoding="utf-8", errors="replace") for path in artifact.rglob("configure-reference.stderr.log"))
            if "P0DefinitelyMissing" not in logs:
                raise TestFailure("configuration failure did not identify missing dependency")

    def bld008(self) -> None:
        payload = b"fixture content\n"
        sandbox = self.sandbox_runner("bld008-sandbox", "0" * 64, hashlib.sha256(payload).hexdigest())
        artifact = sandbox.parent / "artifacts"
        build = artifact / "build"
        install = artifact / "install"
        build.mkdir(parents=True)
        install.mkdir(parents=True)
        lines = [
            "CMAKE_BUILD_TYPE:STRING=RelWithDebInfo",
            "CMAKE_GENERATOR:INTERNAL=Ninja",
            "OPTION_DEDICATED:BOOL=OFF",
            "OPTION_INSTALL_FHS:BOOL=ON",
            "OPTION_USE_ASSERTS:BOOL=ON",
            f"CMAKE_INSTALL_PREFIX:PATH={install}",
        ]
        write(build / "CMakeCache.txt", "\n".join(lines) + "\n")
        write(build / "baseset/opengfx-8.0.tar", payload)
        stale = write(build / "openttd", "#!/bin/sh\nexit 0\n", executable=True)
        os.utime(stale, (1, 1))
        manifest = write(
            artifact / "configure.json",
            json.dumps({"authoritative": {"source_commit": EXPECTED_SUBMODULE}, "diagnostics": {"build_root": str(build), "install_root": str(install)}, "return_code": 0, "status": "PASS"}) + "\n",
        )
        result = self.run_build(sandbox / "oracle/runner", artifact, build, install, manifest)
        self.assert_failure(result, "stale OpenTTD executable")

    def bld009(self) -> None:
        payload = b"fixture content\n"
        sandbox = self.sandbox_runner("bld009-sandbox", "0" * 64, hashlib.sha256(payload).hexdigest())
        result, artifact, _, build, install = self.configure_fixture("ignored", unresolved=True, sandbox=sandbox)
        self.assert_success(result, "unresolved-library fixture configure")
        write(build / "baseset/opengfx-8.0.tar", payload)
        manifest = artifact / "manifests/configure-reference.json"
        value = strict_json(manifest)
        assert isinstance(value, dict)
        value["authoritative"]["source_commit"] = EXPECTED_SUBMODULE  # type: ignore[index]
        write(manifest, json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        build_result = self.run_build(sandbox / "oracle/runner", artifact, build, install, manifest)
        self.assert_failure(build_result, "unresolved shared library")
        ldd_log = artifact / "logs/build-reference.ldd.log"
        if not ldd_log.is_file() or "not found" not in ldd_log.read_text(encoding="utf-8", errors="replace"):
            raise TestFailure("unresolved-library failure omitted ldd evidence")

    def bld010(self) -> None:
        result, _ = self.smoke_fixture("bld010", omit_digest=True)
        self.assert_failure(result, "executable digest is malformed or omitted")

    # Test inventory tests --------------------------------------------
    def tst001(self) -> None:
        result, artifact, _ = self.run_ctest_runner("tst001", self.test_names)
        self.assert_success(result, "exact 99-test inventory and run")
        details = strict_json(artifact / "manifests/test-reference.json")
        if details["authoritative"]["counts"] != {"failed": 0, "passed": 99, "skipped": 0, "total": 99}:  # type: ignore[index]
            raise TestFailure("test result counts differ from 99/99")

    def tst006(self) -> None:
        result, artifact, _ = self.run_ctest_runner("tst006", self.test_names, failure=self.test_names[0])
        self.assert_failure(result)
        for path in (artifact / "test-results/ctest-results.junit.xml", artifact / "logs/test-reference.stdout.log", artifact / "results/test-reference.json"):
            if not path.is_file():
                raise TestFailure(f"failing test omitted retained evidence: {path}")
        result_value = strict_json(artifact / "results/test-reference.json")
        if not isinstance(result_value, dict) or result_value.get("status") != "FAIL" or result_value.get("return_code") == 0:
            raise TestFailure("one-test failure did not produce a nonzero FAIL gate result")

    def tst007(self) -> None:
        result, artifact, _ = self.run_ctest_runner("tst007", self.test_names, skipped=self.test_names[0])
        self.assert_failure(result)
        junit = artifact / "test-results/ctest-results.junit.xml"
        if not junit.is_file() or "<skipped" not in junit.read_text(encoding="utf-8", errors="replace"):
            raise TestFailure("unexpected skip did not appear in JUnit evidence")

    def tst008(self) -> None:
        result, artifact, _ = self.run_ctest_runner("tst008", self.test_names, timed_out=self.test_names[0])
        self.assert_failure(result)
        junit = artifact / "test-results/ctest-results.junit.xml"
        if not junit.is_file() or "timeout" not in junit.read_text(encoding="utf-8", errors="replace").lower():
            raise TestFailure("timeout did not appear in retained JUnit evidence")

    def tst009(self) -> None:
        result, _, _ = self.run_ctest_runner("tst009", self.test_names, poison_results_dir=True)
        self.assert_failure(result)

    def tst010(self) -> None:
        result, _, _ = self.run_ctest_runner("tst010", self.test_names, malformed_baseline=True)
        self.assert_failure(result, "invalid JSON")

    # Smoke tests ------------------------------------------------------
    def smk001(self) -> None:
        result, artifact = self.smoke_fixture("smk001")
        self.assert_success(result, "exact null-backend 128-tick smoke")
        command = strict_json(artifact / "commands/smoke-reference-openttd.json")
        if not isinstance(command, list) or command[1:] != ["-g", "-v", "null:ticks=128", "-s", "null", "-m", "null", "-b", "null", "-I", "OpenGFX", "-Q", "-x"]:
            raise TestFailure(f"smoke command drifted: {command!r}")

    def smk004(self) -> None:
        result, artifact = self.smoke_fixture("smk004", smoke_rc=42)
        self.assert_failure(result)
        if not (artifact / "logs/smoke-reference.stdout.log").is_file() or not (artifact / "logs/smoke-reference.stderr.log").is_file():
            raise TestFailure("nonzero smoke omitted retained stdout/stderr")
        gate_result = strict_json(artifact / "results/smoke-reference.json")
        if not isinstance(gate_result, dict) or gate_result.get("status") != "FAIL" or gate_result.get("return_code") != 42:
            raise TestFailure("nonzero smoke did not emit the exact failing gate return code")

    def run_all(self, schedule_seed: int | None = None) -> None:
        print("TAP version 13", flush=True)
        print("1..61", flush=True)
        self.validate_frozen_profile_pairs()
        repository_cases = [
            ("P001-REP-001", "correct outer repository and submodule", self.rep001),
            ("P001-REP-002", "wrong submodule commit fails with identities", self.rep002),
            ("P001-REP-003", "dirty submodule lists paths only", self.rep003),
            ("P001-REP-004", "missing submodule gives recovery command", self.rep004),
            ("P001-REP-005", "modified submodule URL fails", self.rep005),
            ("P001-REP-006", "edit mode on main fails", self.rep006),
            ("P001-REP-007", "detached read-only mode succeeds", self.rep007),
            ("P001-REP-008", "credential-like staged path fails", self.rep008),
            ("P001-REP-009", "staged build tree fails", self.rep009),
            ("P001-REP-010", "absolute canonical path fails schema", self.rep010),
        ]
        manifest_cases: list[tuple[str, str, Callable[[], None]]] = [
            ("P001-MAN-001", "minimal valid source manifest", self.man001),
            ("P001-MAN-002", "missing commit is invalid", lambda: self.production_invalid("man002-validator", value=self.source_mutant(lambda v: v["identity"]["submodule"].pop("commit")), needle="schema validation failed")),  # type: ignore[index]
            ("P001-MAN-003", "short digest is invalid", lambda: self.production_invalid("man003-validator", value=self.source_mutant(lambda v: v.__setitem__("schema_sha256", "0" * 63)), needle="schema validation failed")),
            ("P001-MAN-004", "uppercase digest is invalid", lambda: self.production_invalid("man004-validator", value=self.source_mutant(lambda v: v.__setitem__("schema_sha256", "A" * 64)), needle="schema validation failed")),
            ("P001-MAN-005", "unknown property is invalid", lambda: self.production_invalid("man005-validator", value=self.source_mutant(lambda v: v.__setitem__("unknown_required", True)), needle="schema validation failed")),
            ("P001-MAN-006", "duplicate JSON key is invalid", self.man006),
            ("P001-MAN-007", "non-UTF-8 JSON is invalid", self.man007),
            ("P001-MAN-008", "UTF-8 BOM is invalid", self.man008),
            ("P001-MAN-009", "negative test count is invalid", lambda: self.production_invalid("man009-validator", value=self._inventory_mutant("expected_count", -1), schema=self.manifests / "schema/test-inventory.schema.json", needle="schema validation failed")),
            ("P001-MAN-010", "floating test count is invalid", self.man010),
            ("P001-MAN-011", "property order canonicalizes equally", self.man011),
            ("P001-MAN-012", "whitespace canonicalizes equally", self.man012),
            ("P001-MAN-013", "authoritative change changes digest", self.man013),
            ("P001-MAN-014", "diagnostic path leaves identity unchanged", self.man014),
            ("P001-MAN-015", "secret-named environment is rejected", self.man015),
        ]
        gfx_cases = [
            ("P001-GFX-001", "approved archive is accepted", self.gfx001),
            ("P001-GFX-002", "one-bit archive mutation is rejected", self.gfx002),
            ("P001-GFX-003", "renamed approved bytes use digest policy", self.gfx003),
            ("P001-GFX-004", "right name with wrong bytes is rejected", self.gfx004),
            ("P001-GFX-005", "parent traversal archive is rejected", lambda: self.gfx_malicious("gfx005", "../opengfx-8.0.tar")),
            ("P001-GFX-006", "absolute archive path is rejected", lambda: self.gfx_malicious("gfx006", "/opengfx-8.0.tar")),
            ("P001-GFX-007", "differing destination is preserved", self.gfx007),
            ("P001-GFX-008", "interrupted archive is never promoted", self.gfx008),
            ("P001-GFX-009", "verified install works offline", self.gfx009),
            ("P001-GFX-010", "installed drift fails", self.gfx010),
        ]
        build_cases = [
            ("P001-BLD-001", "fresh reference configure succeeds", self.bld001),
            ("P001-BLD-002", "incompatible cache is isolated", self.bld002),
            ("P001-BLD-003", "wrong build type fails", lambda: self.cache_failure("bld003", {"CMAKE_BUILD_TYPE": "CMAKE_BUILD_TYPE:STRING=Debug"}, "CMAKE_BUILD_TYPE")),
            ("P001-BLD-004", "disabled assertions fail", lambda: self.cache_failure("bld004", {"OPTION_USE_ASSERTS": "OPTION_USE_ASSERTS:BOOL=OFF"}, "assertions")),
            ("P001-BLD-005", "dedicated-only build fails", lambda: self.cache_failure("bld005", {"OPTION_DEDICATED": "OPTION_DEDICATED:BOOL=ON"}, "dedicated mode")),
            ("P001-BLD-006", "wrong generator fails", lambda: self.cache_failure("bld006", {"CMAKE_GENERATOR": "CMAKE_GENERATOR:INTERNAL=Unix Makefiles"}, "generator")),
            ("P001-BLD-007", "missing dependency fails clearly", self.bld007),
            ("P001-BLD-008", "stale executable is never accepted", self.bld008),
            ("P001-BLD-009", "unresolved shared library fails", self.bld009),
            ("P001-BLD-010", "omitted executable digest fails", self.bld010),
        ]
        test_cases = [
            ("P001-TST-001", "exact 99-test inventory passes", self.tst001),
            ("P001-TST-002", "98 tests fail", lambda: self.assert_failure(self.run_ctest_runner("tst002", self.test_names[:-1])[0], "expected exactly 99 tests, found 98")),
            ("P001-TST-003", "100 tests fail", lambda: self.assert_failure(self.run_ctest_runner("tst003", [*self.test_names, "P001 synthetic extra"])[0], "expected exactly 99 tests, found 100")),
            ("P001-TST-004", "renamed test fails", lambda: self.assert_failure(self.run_ctest_runner("tst004", ["P001 renamed", *self.test_names[1:]])[0], "inventory drift")),
            ("P001-TST-005", "zero tests fail through no-tests policy", self._zero_tests),
            ("P001-TST-006", "one upstream failure retains JUnit and log", self.tst006),
            ("P001-TST-007", "unexpected skip fails", self.tst007),
            ("P001-TST-008", "timeout fails", self.tst008),
            ("P001-TST-009", "unwritable JUnit path fails", self.tst009),
            ("P001-TST-010", "malformed inventory JSON fails", self.tst010),
        ]
        smoke_cases = [
            ("P001-SMK-001", "exact null-backend 128-tick command passes", self.smk001),
            ("P001-SMK-002", "missing OpenGFX fails by content name", lambda: self.assert_failure(self.smoke_fixture("smk002", content_present=False)[0], "opengfx-8.0.tar")),
            ("P001-SMK-003", "wrong executable digest fails before run", lambda: self.assert_failure(self.smoke_fixture("smk003", manifest_digest="f" * 64)[0], "smoke executable SHA-256 mismatch")),
            ("P001-SMK-004", "nonzero OpenTTD exit retains logs", self.smk004),
            ("P001-SMK-005", "unexpected graphical backend fails", lambda: self.assert_failure(self.smoke_fixture("smk005", include_null_video=False)[0], "null video capability is unavailable")),
            ("P001-SMK-006", "version drift fails", lambda: self.assert_failure(self.smoke_fixture("smk006", version="OpenTTD MUTATED")[0], "runtime version drift")),
        ]
        cases = repository_cases + manifest_cases + gfx_cases + build_cases + test_cases + smoke_cases
        if schedule_seed is not None:
            random.Random(schedule_seed).shuffle(cases)
            print(f"# randomized mandatory-case schedule seed: {schedule_seed}", flush=True)
        for item in cases:
            self.case(*item)

        self.assert_unchanged()
        if len(self.passed) != 61 or len(set(self.passed)) != 61:
            raise TestFailure(f"mandatory ID accounting error: {len(self.passed)} passes, {len(set(self.passed))} unique")

    def _inventory_mutant(self, key: str, value: object) -> dict[str, object]:
        mutant = copy.deepcopy(self._test_inventory)
        assert isinstance(mutant, dict)
        mutant[key] = value
        return mutant

    def _zero_tests(self) -> None:
        result, _, build = self.run_ctest_runner("tst005", [])
        self.assert_failure(result, "expected exactly 99 tests, found 0")
        direct = self.run(["ctest", "--test-dir", build, "--no-tests=error"])
        self.assert_failure(direct, "No tests were found")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True, type=pathlib.Path)
    parser.add_argument("--work-root", required=True, type=pathlib.Path)
    parser.add_argument("--tools-python", required=True, type=pathlib.Path)
    parser.add_argument("--schedule-seed", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    harness = Harness(args.repository_root, args.work_root, args.tools_python)
    try:
        harness.run_all(args.schedule_seed)
    except Exception:
        return 1
    print(f"# PORT-001 mandatory tests: PASS ({len(harness.passed)}/61)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
