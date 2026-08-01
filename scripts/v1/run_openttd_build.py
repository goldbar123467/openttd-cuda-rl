#!/usr/bin/env python3
"""Run one clean, offline, reproducible OpenTTD 15.3 build profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from typing import Any

import prepare_openttd_source


class OpenTTDBuildError(ValueError):
    """A build input, command, test, smoke, or reproducibility guard failed."""


SOURCE_COMMIT = "14ec60f248547d4d062a1160f0fc26d742319888"
SOURCE_TREE = "02d8cbbb0d8c030698d37ca76ab2773b6e23c397"
PREPARED_TREE = "c63a866377547631870efb48ac547948da19916a"
SOURCE_DATE_EPOCH = "1775315764"
OTTDREV = f"15.3-v1\t20260404\t2\t{SOURCE_COMMIT}\t0\t0\n"
OPENGFX_GAME_FILES = (
    "ogfx1_base.grf",
    "ogfxc_arctic.grf",
    "ogfxe_extra.grf",
    "ogfxh_tropical.grf",
    "ogfxi_logos.grf",
    "ogfxt_toyland.grf",
    "opengfx.obg",
)
OPENGFX_DOCUMENT_LINKS = {
    "changelog.txt.gz": "../../../../doc/openttd-opengfx/changelog.gz",
    "license.txt": "../../../../common-licenses/GPL-2",
    "readme.txt.gz": "../../../../doc/openttd-opengfx/README.md.gz",
}


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def resolve_executable(value: str, label: str) -> pathlib.Path:
    if pathlib.Path(value).is_absolute():
        result = pathlib.Path(value).resolve()
    else:
        discovered = shutil.which(value)
        if discovered is None:
            raise OpenTTDBuildError(f"missing required executable: {label} ({value})")
        result = pathlib.Path(discovered).resolve()
    if not result.is_file() or not os.access(result, os.X_OK):
        raise OpenTTDBuildError(f"invalid required executable: {label} ({result})")
    return result


def exact_version(label: str, actual: str, expected: str) -> str:
    if actual != expected:
        raise OpenTTDBuildError(
            f"{label} version mismatch: expected={expected} actual={actual}"
        )
    return actual


def load_lock(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OpenTTDBuildError(f"cannot load build-input lock: {exc}") from exc
    if set(value) != {"schema_version", "profile_id", "policy", "artifacts"}:
        raise OpenTTDBuildError("build-input lock has unexpected or missing top-level fields")
    if value["schema_version"] != "openttd-rl-v1-openttd-build-input-lock-1":
        raise OpenTTDBuildError("unexpected build-input lock schema version")
    if value["policy"] != {"builds_are_offline": True, "reject_unlisted_debs": True}:
        raise OpenTTDBuildError("build-input lock policy is not fail-closed/offline")
    if not isinstance(value["artifacts"], list) or not value["artifacts"]:
        raise OpenTTDBuildError("build-input lock has no artifacts")
    required = {"package", "version", "architecture", "filename", "size_bytes", "sha256"}
    filenames: set[str] = set()
    packages: set[str] = set()
    for artifact in value["artifacts"]:
        if not isinstance(artifact, dict) or set(artifact) != required:
            raise OpenTTDBuildError("build-input artifact has unexpected or missing fields")
        filename = artifact["filename"]
        if pathlib.PurePosixPath(filename).name != filename or not filename.endswith(".deb"):
            raise OpenTTDBuildError(f"invalid build-input filename: {filename!r}")
        if filename in filenames or artifact["package"] in packages:
            raise OpenTTDBuildError("build-input filenames and packages must be unique")
        if not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]):
            raise OpenTTDBuildError(f"invalid build-input digest: {filename}")
        filenames.add(filename)
        packages.add(artifact["package"])
    return value


def clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "CFLAGS",
        "CPPFLAGS",
        "CXXFLAGS",
        "CMAKE_PREFIX_PATH",
        "CPATH",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "LIBRARY_PATH",
        "PKG_CONFIG_PATH",
        "PKG_CONFIG_SYSROOT_DIR",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH,
            "TZ": "UTC",
        }
    )
    return environment


class CommandRunner:
    def __init__(self, logs: pathlib.Path, environment: dict[str, str]) -> None:
        self.logs = logs
        self.environment = environment
        self.commands: list[dict[str, Any]] = []
        self.timings: dict[str, float] = {}
        self.logs.mkdir(parents=True, exist_ok=False)

    def run(
        self,
        label: str,
        command: list[str],
        *,
        cwd: pathlib.Path | None = None,
        environment: dict[str, str] | None = None,
        reject_warnings: bool = False,
        accepted_codes: tuple[int, ...] = (0,),
    ) -> subprocess.CompletedProcess[str]:
        start = time.monotonic()
        result = subprocess.run(
            command,
            cwd=cwd,
            env=self.environment if environment is None else environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.timings[label] = round(time.monotonic() - start, 3)
        output = result.stdout
        if result.stderr:
            output += ("\n" if output and not output.endswith("\n") else "") + result.stderr
        log_path = self.logs / f"{label}.log"
        log_path.write_text(output, encoding="utf-8")
        self.commands.append(
            {
                "label": label,
                "argv": command,
                "cwd": None if cwd is None else str(cwd),
                "exit_code": result.returncode,
            }
        )
        if result.returncode not in accepted_codes:
            detail = "\n".join(output.strip().splitlines()[-30:])
            raise OpenTTDBuildError(
                f"{label} failed with exit code {result.returncode}; "
                f"see logs/{log_path.name}: {detail}"
            )
        if reject_warnings and re.search(r"(?:CMake Warning|\bwarning:)", output):
            warnings = "\n".join(
                line for line in output.splitlines() if re.search(r"(?:CMake Warning|\bwarning:)", line)
            )
            raise OpenTTDBuildError(
                f"{label} emitted a warning; see logs/{log_path.name}: {warnings}"
            )
        return result


def validate_cache(
    lock: dict[str, Any], cache_root: pathlib.Path, dpkg_deb: pathlib.Path, runner: CommandRunner
) -> list[dict[str, Any]]:
    expected = {artifact["filename"] for artifact in lock["artifacts"]}
    actual = {path.name for path in cache_root.glob("*.deb") if path.is_file()}
    if actual != expected:
        raise OpenTTDBuildError(
            f"build-input cache inventory mismatch: unlisted={sorted(actual - expected)} "
            f"missing={sorted(expected - actual)}"
        )
    records: list[dict[str, Any]] = []
    for index, artifact in enumerate(lock["artifacts"], 1):
        path = cache_root / artifact["filename"]
        if path.is_symlink() or not path.is_file():
            raise OpenTTDBuildError(f"build input is not a regular non-symlink file: {path.name}")
        if path.stat().st_size != artifact["size_bytes"]:
            raise OpenTTDBuildError(f"build-input size mismatch: {path.name}")
        if sha256_file(path) != artifact["sha256"]:
            raise OpenTTDBuildError(f"build-input digest mismatch: {path.name}")
        metadata = runner.run(
            f"deb-metadata-{index:02d}",
            [str(dpkg_deb), "-f", str(path), "Package", "Version", "Architecture"],
        ).stdout
        parsed = dict(
            line.split(": ", 1) for line in metadata.splitlines() if ": " in line
        )
        expected_metadata = {
            "Package": artifact["package"],
            "Version": artifact["version"],
            "Architecture": artifact["architecture"],
        }
        if parsed != expected_metadata:
            raise OpenTTDBuildError(
                f"build-input package metadata mismatch for {path.name}: "
                f"expected={expected_metadata} actual={parsed}"
            )
        records.append(dict(artifact))
    return records


def parse_ctest_inventory(output: str) -> list[str]:
    try:
        data = json.loads(output)
        names = sorted(test["name"] for test in data["tests"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise OpenTTDBuildError(f"invalid CTest inventory: {exc}") from exc
    if not names or len(names) != len(set(names)):
        raise OpenTTDBuildError("CTest inventory is empty or contains duplicate names")
    return names


def parse_junit(path: pathlib.Path, expected: list[str]) -> list[dict[str, str]]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise OpenTTDBuildError(f"cannot parse CTest JUnit output: {exc}") from exc
    results: list[dict[str, str]] = []
    for testcase in root.iter("testcase"):
        name = testcase.attrib.get("name")
        if not name:
            raise OpenTTDBuildError("CTest JUnit testcase lacks name")
        result = "PASS"
        if testcase.find("failure") is not None or testcase.find("error") is not None:
            result = "FAIL"
        elif testcase.find("skipped") is not None:
            result = "SKIP"
        results.append({"name": name, "result": result})
    results.sort(key=lambda item: item["name"])
    if [item["name"] for item in results] != expected:
        raise OpenTTDBuildError("CTest JUnit inventory differs from pre-run inventory")
    nonpassing = [item for item in results if item["result"] != "PASS"]
    if nonpassing:
        raise OpenTTDBuildError(f"CTest JUnit contains nonpassing tests: {nonpassing[:10]}")
    return results


def parse_ldd(output: str) -> list[str]:
    dependencies: set[str] = set()
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "not found" in line:
            raise OpenTTDBuildError(f"unresolved runtime dependency: {line}")
        if "=>" in line:
            dependencies.add(line.split("=>", 1)[0].strip())
        else:
            first = line.split(" ", 1)[0]
            if first.startswith("/"):
                dependencies.add(pathlib.Path(first).name)
            elif first.startswith("linux-vdso"):
                dependencies.add(first)
    if not dependencies:
        raise OpenTTDBuildError("ldd reported no runtime dependencies")
    return sorted(dependencies)


def inventory_tree(root: pathlib.Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            records.append({"path": relative, "type": "symlink", "target": os.readlink(path)})
        elif path.is_file():
            records.append(
                {
                    "path": relative,
                    "type": "file",
                    "mode": stat.S_IMODE(path.stat().st_mode),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    if not records:
        raise OpenTTDBuildError(f"installed tree is empty: {root}")
    return records


def write_json(path: pathlib.Path, value: Any) -> None:
    if path.exists():
        raise OpenTTDBuildError(f"refusing to overwrite output: {path}")
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def replace_roots(value: Any, roots: dict[str, pathlib.Path]) -> Any:
    if isinstance(value, str):
        result = value
        for token, path in roots.items():
            result = result.replace(str(path), token)
        return result
    if isinstance(value, list):
        return [replace_roots(item, roots) for item in value]
    if isinstance(value, dict):
        return {key: replace_roots(item, roots) for key, item in value.items()}
    return value


def build(options: argparse.Namespace) -> dict[str, Any]:
    root = options.root.resolve()
    artifact_root = options.artifact_root.resolve()
    cache_root = options.cache_root.resolve()
    lock_path = options.lock.resolve()
    if not artifact_root.is_dir() or any(artifact_root.iterdir()):
        raise OpenTTDBuildError("artifact root must be an existing empty directory")
    if not cache_root.is_dir():
        raise OpenTTDBuildError(f"build-input cache does not exist: {cache_root}")

    tools = {
        name: resolve_executable(getattr(options, name), name)
        for name in (
            "cmake",
            "ctest",
            "dpkg_deb",
            "gcc",
            "gxx",
            "ldd",
            "ninja",
            "python",
            "timeout",
        )
    }
    runner = CommandRunner(artifact_root / "logs", clean_environment())
    gcc_version = runner.run("gcc-version", [str(tools["gcc"]), "-dumpfullversion"]).stdout.strip()
    gxx_version = runner.run("gxx-version", [str(tools["gxx"]), "-dumpfullversion"]).stdout.strip()
    cmake_version_output = runner.run(
        "cmake-version", [str(tools["cmake"]), "--version"]
    ).stdout
    ctest_version_output = runner.run(
        "ctest-version", [str(tools["ctest"]), "--version"]
    ).stdout
    ninja_version = runner.run(
        "ninja-version", [str(tools["ninja"]), "--version"]
    ).stdout.strip()
    cmake_match = re.search(r"^cmake version ([0-9.]+)$", cmake_version_output, re.MULTILINE)
    ctest_match = re.search(r"^ctest version ([0-9.]+)$", ctest_version_output, re.MULTILINE)
    if cmake_match is None or ctest_match is None:
        raise OpenTTDBuildError("cannot parse CMake or CTest version")
    cmake_version = exact_version("CMake", cmake_match.group(1), "3.28.3")
    ctest_version = exact_version("CTest", ctest_match.group(1), "3.28.3")
    exact_version("GCC", gcc_version, "13.3.0")
    exact_version("G++", gxx_version, "13.3.0")
    exact_version("Ninja", ninja_version, "1.11.1")
    lock = load_lock(lock_path)
    package_records = validate_cache(lock, cache_root, tools["dpkg_deb"], runner)

    source = artifact_root / "source"
    prepared_manifest_path = artifact_root / "prepared-source.json"
    prepared = prepare_openttd_source.prepare(
        root=root,
        profile_path=root / "config/v1/openttd-source-profile.json",
        profile_schema_path=root / "docs/project/schema/v1-source-profile.schema.json",
        manifest_schema_path=root / "docs/project/schema/v1-prepared-source-manifest.schema.json",
        object_repository_override=root / "openttd-upstream",
        output=source,
        manifest_path=prepared_manifest_path,
    )
    if (
        prepared["source"]["commit"] != SOURCE_COMMIT
        or prepared["source"]["tree"] != SOURCE_TREE
        or prepared["result"]["tree"] != PREPARED_TREE
    ):
        raise OpenTTDBuildError("prepared source identity differs from the accepted OpenTTD basis")
    source_git = source / ".git"
    source_git_evidence = artifact_root / "source-preparation-git-metadata"
    shutil.move(source_git, source_git_evidence)
    (source / ".ottdrev").write_text(OTTDREV, encoding="utf-8")

    sysroot = artifact_root / "sysroot"
    sysroot.mkdir()
    for index, artifact in enumerate(lock["artifacts"], 1):
        runner.run(
            f"deb-extract-{index:02d}",
            [str(tools["dpkg_deb"]), "-x", str(cache_root / artifact["filename"]), str(sysroot)],
        )
    packaged_baseset = sysroot / "usr/share/games/openttd/baseset/opengfx"
    if not (packaged_baseset / "opengfx.obg").is_file():
        raise OpenTTDBuildError("locked OpenGFX extraction lacks baseset/opengfx.obg")
    actual_baseset_entries = {path.name for path in packaged_baseset.iterdir()}
    expected_baseset_entries = set(OPENGFX_GAME_FILES) | set(OPENGFX_DOCUMENT_LINKS)
    if actual_baseset_entries != expected_baseset_entries:
        raise OpenTTDBuildError(
            "locked OpenGFX baseset inventory mismatch: "
            f"unlisted={sorted(actual_baseset_entries - expected_baseset_entries)} "
            f"missing={sorted(expected_baseset_entries - actual_baseset_entries)}"
        )
    for name in OPENGFX_GAME_FILES:
        path = packaged_baseset / name
        if path.is_symlink() or not path.is_file():
            raise OpenTTDBuildError(f"locked OpenGFX game file is invalid: {name}")
    for name, target in OPENGFX_DOCUMENT_LINKS.items():
        path = packaged_baseset / name
        if not path.is_symlink() or os.readlink(path) != target:
            raise OpenTTDBuildError(f"locked OpenGFX documentation link is invalid: {name}")
    content_root = artifact_root / "runtime-content"
    baseset_root = content_root / "baseset"
    baseset_root.mkdir(parents=True)
    for name in OPENGFX_GAME_FILES:
        shutil.copy2(packaged_baseset / name, baseset_root / name)

    build_root = artifact_root / "build"
    stage_root = artifact_root / "stage"
    stage_root.mkdir()
    canonical_prefix = f"/opt/openttd-rl-v1-{options.variant}"
    source_flags = (
        f"-O2 -g0 -Werror -ffile-prefix-map={source}=/usr/src/openttd-15.3 "
        f"-ffile-prefix-map={build_root}=/usr/src/openttd-build"
    )
    cmake_command = [
        str(tools["cmake"]),
        "-S",
        str(source),
        "-B",
        str(build_root),
        "-G",
        "Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_INSTALL_PREFIX={canonical_prefix}",
        f"-DCMAKE_C_COMPILER={tools['gcc']}",
        f"-DCMAKE_CXX_COMPILER={tools['gxx']}",
        f"-DCMAKE_MAKE_PROGRAM={tools['ninja']}",
        f"-DCMAKE_CXX_FLAGS_RELEASE={source_flags}",
        "-DCMAKE_EXE_LINKER_FLAGS=-Wl,--build-id=none,"
        f"-rpath-link,{sysroot / 'usr/lib/x86_64-linux-gnu'},"
        f"-rpath-link,{sysroot / 'usr/lib/x86_64-linux-gnu/pulseaudio'}",
        f"-DCMAKE_PREFIX_PATH={sysroot / 'usr'}",
        f"-DCMAKE_INCLUDE_PATH={sysroot / 'usr/include'};"
        f"{sysroot / 'usr/include/x86_64-linux-gnu'};"
        f"{sysroot / 'usr/include/harfbuzz'}",
        f"-DCMAKE_LIBRARY_PATH={sysroot / 'usr/lib/x86_64-linux-gnu'}",
        "-DBUILD_TESTING=ON",
        f"-DOPTION_DEDICATED={'ON' if options.variant == 'headless' else 'OFF'}",
        "-DOPTION_INSTALL_FHS=ON",
        "-DOPTION_PACKAGE_DEPENDENCIES=OFF",
        "-DOPTION_USE_ASSERTS=ON",
        "-DOPTION_FORCE_COLORED_OUTPUT=OFF",
        "-DOPTION_USE_NSIS=OFF",
        "-DOPTION_TOOLS_ONLY=OFF",
        "-DOPTION_DOCS_ONLY=OFF",
        "-DOPTION_ALLOW_INVALID_SIGNATURE=OFF",
        "-DOPTION_SURVEY_KEY=",
        "-DPERSONAL_DIR=.openttd-v1",
        "-DSHARED_DIR=(not set)",
        f"-DGLOBAL_DIR={canonical_prefix}/share/games/openttd",
    ]
    build_environment = runner.environment.copy()
    build_environment.update(
        {
            "PKG_CONFIG_PATH": ":".join(
                [
                    str(sysroot / "usr/lib/x86_64-linux-gnu/pkgconfig"),
                    str(sysroot / "usr/share/pkgconfig"),
                ]
            ),
            "PKG_CONFIG_SYSROOT_DIR": str(sysroot),
        }
    )
    runtime_library_path = ":".join(
        [
            str(sysroot / "usr/lib/x86_64-linux-gnu"),
            str(sysroot / "usr/lib/x86_64-linux-gnu/pulseaudio"),
            str(sysroot / "lib/x86_64-linux-gnu"),
        ]
    )
    configure_result = runner.run(
        "cmake-configure",
        cmake_command,
        environment=build_environment,
        reject_warnings=True,
    )
    required_features = [
        "PNG found -- -DWITH_PNG",
        "ZLIB found -- -DWITH_ZLIB",
        "LIBLZMA found -- -DWITH_LIBLZMA",
        "CURL found -- -DWITH_CURL",
    ]
    if options.variant == "playable":
        required_features.extend(
            [
                "SDL2 found -- -DWITH_SDL2",
                "FREETYPE found -- -DWITH_FREETYPE",
                "Fontconfig found -- -DWITH_FONTCONFIG",
                "Harfbuzz found -- -DWITH_HARFBUZZ",
                "ICU_i18n found -- -DWITH_ICU_I18N",
                "ICU_uc found -- -DWITH_ICU_UC",
            ]
        )
    missing_features = [
        feature for feature in required_features if feature not in configure_result.stdout
    ]
    if missing_features:
        raise OpenTTDBuildError(
            f"CMake did not enable required {options.variant} components: {missing_features}"
        )
    runner.run(
        "cmake-build",
        [str(tools["cmake"]), "--build", str(build_root), "--parallel", str(options.jobs)],
        environment=build_environment,
        reject_warnings=True,
    )

    # Upstream's regression tests run the just-built executable from the build
    # directory, so provide the locked base graphics there as test input.
    shutil.copytree(baseset_root, build_root / "baseset", dirs_exist_ok=True)

    test_environment = build_environment.copy()
    if options.variant == "playable":
        test_environment["LD_LIBRARY_PATH"] = runtime_library_path
    inventory_result = runner.run(
        "ctest-inventory",
        [str(tools["ctest"]), "--test-dir", str(build_root), "--show-only=json-v1"],
        environment=test_environment,
    )
    test_names = parse_ctest_inventory(inventory_result.stdout)
    write_json(artifact_root / "test-inventory.json", test_names)
    junit = artifact_root / "ctest-results.junit.xml"
    runner.run(
        "ctest",
        [
            str(tools["ctest"]),
            "--test-dir",
            str(build_root),
            "--output-on-failure",
            "--no-tests=error",
            "--timeout",
            "300",
            "--output-junit",
            str(junit),
        ],
        environment=test_environment,
    )
    test_results = parse_junit(junit, test_names)
    write_json(artifact_root / "test-results.json", test_results)

    install_environment = build_environment.copy()
    install_environment["DESTDIR"] = str(stage_root)
    runner.run(
        "cmake-install",
        [str(tools["cmake"]), "--install", str(build_root)],
        environment=install_environment,
        reject_warnings=True,
    )
    install_root = stage_root / canonical_prefix.removeprefix("/")
    executable = install_root / "games/openttd"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise OpenTTDBuildError("installed OpenTTD executable is missing or not executable")
    runtime_data_root = install_root / "share/games/openttd"
    if not (runtime_data_root / "lang/english.lng").is_file():
        raise OpenTTDBuildError("staged OpenTTD runtime data lacks the English language pack")
    if not (runtime_data_root / "baseset/opengfx.obg").is_file():
        raise OpenTTDBuildError("staged OpenTTD runtime data lacks the locked OpenGFX set")

    runtime_environment = runner.environment.copy()
    runtime_environment.update(
        {
            "LD_LIBRARY_PATH": runtime_library_path,
            "SDL_AUDIODRIVER": "dummy",
            "SDL_VIDEODRIVER": "dummy",
            "XDG_CONFIG_HOME": str(artifact_root / "user/config"),
            "XDG_DATA_HOME": str(artifact_root / "user/data"),
        }
    )
    version_output = runner.run(
        "openttd-version", [str(executable), "-h"], environment=runtime_environment
    ).stdout
    if "OpenTTD 15.3-v1" not in version_output:
        raise OpenTTDBuildError("installed executable did not report OpenTTD 15.3-v1")
    ldd_output = runner.run(
        "openttd-ldd", [str(tools["ldd"]), str(executable)], environment=runtime_environment
    ).stdout
    runtime_dependencies = parse_ldd(ldd_output)

    common_smoke = [
        str(executable),
        "-g",
        "-v",
        "null:ticks=128",
        "-s",
        "null",
        "-m",
        "null",
        "-b",
        "null",
        "-I",
        "OpenGFX",
        "-Q",
        "-x",
    ]
    smoke = runner.run(
        "headless-smoke",
        common_smoke,
        cwd=runtime_data_root,
        environment=runtime_environment,
    )
    if re.search(r"\b(?:ERROR|FATAL):", smoke.stdout + smoke.stderr, re.IGNORECASE):
        raise OpenTTDBuildError("headless smoke output contains an error diagnostic")

    smoke_profiles = [{"name": "null-video-128-ticks", "result": "PASS"}]
    if options.variant == "playable":
        # OpenTTD executes this hook only after the new game has reached
        # OnStartGame.  It therefore proves that the SDL main loop initialized
        # while still giving the smoke test a normal, deterministic exit path.
        game_start_script = (
            artifact_root / "user/data/openttd-v1/scripts/game_start.scr"
        )
        game_start_script.parent.mkdir(parents=True, exist_ok=True)
        game_start_script.write_text("exit\n", encoding="utf-8")
        playable_command = [
            str(tools["timeout"]),
            "--signal=KILL",
            "20s",
            str(executable),
            "-g",
            "-v",
            "sdl",
            "-s",
            "null",
            "-m",
            "null",
            "-b",
            "32bpp-anim",
            "-I",
            "OpenGFX",
            "-Q",
            "-x",
            "-d",
            "driver=1",
        ]
        playable = runner.run(
            "playable-sdl-smoke",
            playable_command,
            cwd=runtime_data_root,
            environment=runtime_environment,
        )
        if re.search(r"\b(?:ERROR|FATAL):", playable.stdout + playable.stderr, re.IGNORECASE):
            raise OpenTTDBuildError("playable SDL smoke output contains an error diagnostic")
        required_driver_diagnostics = [
            "Successfully loaded blitter '32bpp-anim'",
            "SDL2: using driver 'dummy'",
            "Successfully loaded video driver 'sdl'",
        ]
        missing_diagnostics = [
            diagnostic
            for diagnostic in required_driver_diagnostics
            if diagnostic not in playable.stderr
        ]
        if missing_diagnostics:
            raise OpenTTDBuildError(
                "playable SDL smoke omitted required driver diagnostics: "
                f"{missing_diagnostics}"
            )
        smoke_profiles.append({"name": "sdl-dummy-main-game-start-stop", "result": "PASS"})

    install_inventory = inventory_tree(install_root)
    manifest_base: dict[str, Any] = {
        "schema_version": "openttd-rl-v1-openttd-build-manifest-1",
        "profile_id": lock["profile_id"],
        "variant": options.variant,
        "inputs": {
            "build_input_lock_sha256": sha256_file(lock_path),
            "source_profile_sha256": prepared["profile_sha256"],
            "source_commit": SOURCE_COMMIT,
            "source_tree": SOURCE_TREE,
            "prepared_tree": PREPARED_TREE,
            "prepared_source_identity": prepared["preparation_identity_sha256"],
            "ottdrev_sha256": hashlib.sha256(OTTDREV.encode()).hexdigest(),
            "source_date_epoch": int(SOURCE_DATE_EPOCH),
            "packages": package_records,
        },
        "host": {
            "architecture": platform.machine(),
            "os": "ubuntu-24.04",
        },
        "tools": {
            "cmake": cmake_version,
            "ctest": ctest_version,
            "gcc": gcc_version,
            "gxx": gxx_version,
            "ninja": ninja_version,
        },
        "configuration": {
            "build_type": "Release",
            "cxx_standard": 20,
            "assertions": True,
            "dedicated": options.variant == "headless",
            "install_fhs": True,
            "package_dependencies": False,
            "warnings_as_errors": True,
            "gnu_build_id": False,
            "sysroot_rpath_link": True,
            "canonical_install_prefix": canonical_prefix,
        },
        "tests": {
            "count": len(test_names),
            "inventory_sha256": hashlib.sha256(canonical_bytes(test_names)).hexdigest(),
            "results_sha256": hashlib.sha256(canonical_bytes(test_results)).hexdigest(),
            "result": "PASS",
        },
        "runtime": {
            "version": "15.3-v1",
            "dependencies": runtime_dependencies,
            "smoke_profiles": smoke_profiles,
            "opengfx_version": "7.1-1",
        },
        "install_artifacts": install_inventory,
        "result": "PASS",
    }
    manifest = dict(manifest_base)
    manifest["build_identity_sha256"] = hashlib.sha256(canonical_bytes(manifest_base)).hexdigest()
    write_json(artifact_root / "build-manifest.json", manifest)
    roots = {
        "<ARTIFACT_ROOT>": artifact_root,
        "<SOURCE_ROOT>": source,
        "<BUILD_ROOT>": build_root,
        "<SYSROOT>": sysroot,
        "<STAGE_ROOT>": stage_root,
        "<CACHE_ROOT>": cache_root,
        "<REPOSITORY_ROOT>": root,
    }
    write_json(artifact_root / "commands.json", replace_roots(runner.commands, roots))
    write_json(
        artifact_root / "timing.json",
        {
            "schema_version": "openttd-rl-v1-openttd-build-timing-1",
            "variant": options.variant,
            "seconds": runner.timings,
            "total_seconds": round(sum(runner.timings.values()), 3),
        },
    )
    shutil.rmtree(build_root)
    if build_root.exists():
        raise OpenTTDBuildError("clean build directory removal failed")
    return manifest


def parse_args(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--variant", required=True, choices=("headless", "playable"))
    parser.add_argument("--artifact-root", required=True, type=pathlib.Path)
    parser.add_argument("--cache-root", required=True, type=pathlib.Path)
    parser.add_argument("--lock", required=True, type=pathlib.Path)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--ctest", default="ctest")
    parser.add_argument("--dpkg-deb", dest="dpkg_deb", default="dpkg-deb")
    parser.add_argument("--gcc", default="gcc")
    parser.add_argument("--gxx", default="g++")
    parser.add_argument("--ldd", default="ldd")
    parser.add_argument("--ninja", default="ninja")
    parser.add_argument("--python", default="python3")
    parser.add_argument("--timeout", default="timeout")
    options = parser.parse_args(arguments)
    if options.jobs < 1:
        parser.error("--jobs must be positive")
    return options


def main(arguments: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        manifest = build(options)
    except (
        OpenTTDBuildError,
        prepare_openttd_source.SourcePreparationError,
        OSError,
        UnicodeError,
    ) as exc:
        print(f"V1_OPENTTD_BUILD=FAIL variant={options.variant} {exc}", file=sys.stderr)
        return 1
    print(
        f"V1_OPENTTD_BUILD=PASS variant={options.variant} "
        f"tests={manifest['tests']['count']} identity={manifest['build_identity_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
