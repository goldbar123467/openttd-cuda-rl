#!/usr/bin/env python3
"""Build and validate the isolated M02 32 by 32 map feasibility delta."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import lzma
import os
import pathlib
import re
import shutil
import sys
from typing import Any

import jsonschema

import prepare_openttd_source
import run_openttd_build


class M02FeasibilityError(ValueError):
    """An M02 input, build, test, runtime, or reproducibility guard failed."""


SOURCE_COMMIT = "14ec60f248547d4d062a1160f0fc26d742319888"
SOURCE_TREE = "02d8cbbb0d8c030698d37ca76ab2773b6e23c397"
SOURCE_DATE_EPOCH = run_openttd_build.SOURCE_DATE_EPOCH
OTTDREV = run_openttd_build.OTTDREV
CMAKE_REPRODUCIBILITY_OPTIONS = ("-DCMAKE_SKIP_RPATH=ON",)
TILE_TYPE_NAMES = {
    0: "clear",
    1: "railway",
    2: "road",
    3: "house",
    4: "trees",
    5: "station",
    6: "water",
    7: "void",
    8: "industry",
    9: "tunnel_bridge",
    10: "object",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_strict_json(path: pathlib.Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise M02FeasibilityError(f"{path}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                M02FeasibilityError(f"{path}: invalid JSON constant {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M02FeasibilityError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise M02FeasibilityError(f"{path}: top level must be an object")
    return value


def validate_schema(instance: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(instance)
    except jsonschema.exceptions.SchemaError as exc:
        raise M02FeasibilityError(f"{label} schema is invalid: {exc.message}") from exc
    except jsonschema.exceptions.ValidationError as exc:
        raise M02FeasibilityError(f"{label} schema validation failed: {exc.message}") from exc


def load_plan(
    plan_path: pathlib.Path,
    schema_path: pathlib.Path,
) -> tuple[dict[str, Any], str]:
    plan = load_strict_json(plan_path)
    schema = load_strict_json(schema_path)
    validate_schema(plan, schema, "M02 feasibility plan")
    schema_sha256 = run_openttd_build.sha256_file(schema_path)
    if plan["schema_sha256"] != schema_sha256:
        raise M02FeasibilityError(
            "M02 plan schema digest mismatch: "
            f"expected={plan['schema_sha256']} actual={schema_sha256}"
        )
    return plan, run_openttd_build.sha256_file(plan_path)


def resolve_repository_path(root: pathlib.Path, relative: str, label: str) -> pathlib.Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise M02FeasibilityError(f"{label} escapes repository root: {relative}")
    return path


def validate_delta_series(
    root: pathlib.Path,
    source_plan: dict[str, Any],
) -> tuple[pathlib.Path, list[pathlib.Path], list[dict[str, Any]]]:
    directory = resolve_repository_path(root, source_plan["delta_directory"], "delta directory")
    series = resolve_repository_path(root, source_plan["delta_series_path"], "delta series")
    if not directory.is_dir() or not series.is_file() or series.parent != directory:
        raise M02FeasibilityError("M02 delta directory/series layout is invalid")
    if run_openttd_build.sha256_file(series) != source_plan["delta_series_sha256"]:
        raise M02FeasibilityError("M02 delta series digest mismatch")
    names: list[str] = []
    for line_number, raw in enumerate(series.read_text(encoding="utf-8").splitlines(), 1):
        name = raw.strip()
        if not name or name.startswith("#"):
            continue
        if name != pathlib.PurePosixPath(name).name or not name.endswith(".patch"):
            raise M02FeasibilityError(
                f"{series}:{line_number}: delta must be a .patch basename"
            )
        if name in names:
            raise M02FeasibilityError(f"{series}:{line_number}: duplicate delta {name}")
        names.append(name)
    patches = [directory / name for name in names]
    for path in patches:
        if path.is_symlink() or not path.is_file():
            raise M02FeasibilityError(f"M02 delta is not a regular file: {path}")
    present = {path.name for path in directory.glob("*.patch") if path.is_file()}
    if present != set(names):
        raise M02FeasibilityError(
            "M02 delta listed/present mismatch: "
            f"unlisted={sorted(present - set(names))} missing={sorted(set(names) - present)}"
        )
    records = [
        {
            "order": index + 2,
            "path": path.relative_to(root).as_posix(),
            "sha256": run_openttd_build.sha256_file(path),
        }
        for index, path in enumerate(patches)
    ]
    if records != source_plan["patches"]:
        raise M02FeasibilityError(
            f"M02 delta inventory differs from plan: expected={source_plan['patches']} actual={records}"
        )
    return series, patches, records


def composed_source_identity(
    base_preparation_identity_sha256: str,
    delta_series_sha256: str,
    patches: list[dict[str, Any]],
    result_tree: str,
) -> str:
    value = {
        "base_preparation_identity_sha256": base_preparation_identity_sha256,
        "delta_series_sha256": delta_series_sha256,
        "patches": patches,
        "result_tree": result_tree,
    }
    return sha256_bytes(canonical_bytes(value))


def validate_plan_files(root: pathlib.Path, plan: dict[str, Any]) -> None:
    source_plan = plan["source"]
    base_profile = resolve_repository_path(root, source_plan["base_profile_path"], "base profile")
    if run_openttd_build.sha256_file(base_profile) != source_plan["base_profile_sha256"]:
        raise M02FeasibilityError("accepted M01 source profile digest drifted")
    lock = resolve_repository_path(root, plan["build_inputs"]["lock_path"], "build lock")
    if run_openttd_build.sha256_file(lock) != plan["build_inputs"]["lock_sha256"]:
        raise M02FeasibilityError("locked offline build inputs digest drifted")
    lock_value = run_openttd_build.load_lock(lock)
    if len(lock_value["artifacts"]) != plan["build_inputs"]["artifact_count"]:
        raise M02FeasibilityError("locked offline build-input count drifted")
    validate_delta_series(root, source_plan)


def parse_save(path: pathlib.Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise M02FeasibilityError(f"cannot read savegame {path}: {exc}") from exc
    if len(raw) < 16 or raw[:4] != b"OTTX":
        raise M02FeasibilityError(f"savegame is not an OTTX container: {path}")
    try:
        payload = lzma.decompress(raw[8:])
    except lzma.LZMAError as exc:
        raise M02FeasibilityError(f"savegame XZ payload is invalid: {path}: {exc}") from exc
    maps = payload.find(b"MAPS")
    if maps < 0 or payload[maps + 4 : maps + 21] != b"\x03\x10\x06\x05dim_x\x06\x05dim_y\x00":
        raise M02FeasibilityError(f"savegame MAPS dimensions header is invalid: {path}")
    if maps + 31 > len(payload):
        raise M02FeasibilityError(f"savegame MAPS dimensions are truncated: {path}")
    width = int.from_bytes(payload[maps + 22 : maps + 26], "big")
    height = int.from_bytes(payload[maps + 26 : maps + 30], "big")
    tiles = width * height
    mapt = payload.find(b"MAPT", maps + 31)
    if mapt < 0 or mapt + 8 + tiles > len(payload):
        raise M02FeasibilityError(f"savegame MAPT chunk is missing or truncated: {path}")
    chunk_size = int.from_bytes(payload[mapt + 4 : mapt + 8], "big")
    if chunk_size != tiles:
        raise M02FeasibilityError(
            f"savegame MAPT size mismatch: expected={tiles} actual={chunk_size}"
        )
    counts: collections.Counter[str] = collections.Counter()
    for value in payload[mapt + 8 : mapt + 8 + tiles]:
        tile_type = value >> 4
        name = TILE_TYPE_NAMES.get(tile_type)
        if name is None:
            raise M02FeasibilityError(f"savegame contains unknown tile type {tile_type}")
        counts[name] += 1
    map_chunks = [payload[maps:mapt]]
    position = mapt
    for tag in (b"MAPT", b"MAPH", b"MAPO", b"MAP2", b"M3LO", b"M3HI", b"MAP5", b"MAPE", b"MAP7", b"MAP8"):
        if payload[position : position + 4] != tag or position + 8 > len(payload):
            raise M02FeasibilityError(
                f"savegame map chunk order is invalid at {tag.decode()}: {path}"
            )
        size = int.from_bytes(payload[position + 4 : position + 8], "big")
        end = position + 8 + size
        if end > len(payload):
            raise M02FeasibilityError(f"savegame map chunk {tag.decode()} is truncated: {path}")
        map_chunks.append(payload[position:end])
        position = end
    map_bytes = b"".join(map_chunks)
    summary = {
        "width": width,
        "height": height,
        "tiles": tiles,
        "tile_type_counts": dict(sorted(counts.items())),
        "save_sha256": sha256_bytes(raw),
        "payload_sha256": sha256_bytes(payload),
        "map_sha256": sha256_bytes(map_bytes),
    }
    return summary, map_bytes


def discover_runtime_save_paths(artifact_root: pathlib.Path) -> list[pathlib.Path]:
    """Return only saves created by this runner's explicit runtime roots."""
    candidates = [
        artifact_root / "reference-runtime-generated64/save",
        *sorted((artifact_root / "profiles").glob("*/runtime-*/save")),
    ]
    saves: list[pathlib.Path] = []
    for directory in candidates:
        if not directory.exists():
            continue
        if directory.is_symlink() or not directory.is_dir():
            raise M02FeasibilityError(
                f"runtime save evidence directory is not a regular directory: {directory}"
            )
        for save_path in sorted(directory.glob("*.sav")):
            if save_path.is_symlink() or not save_path.is_file():
                raise M02FeasibilityError(
                    f"runtime save evidence is not a regular file: {save_path}"
                )
            saves.append(save_path)
    return sorted(saves)


def canonical_save_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in summary.items()
        if key not in {"save_sha256", "payload_sha256"}
    }


def validate_empty_save(summary: dict[str, Any], expected_size: int, label: str) -> None:
    if summary["width"] != expected_size or summary["height"] != expected_size:
        raise M02FeasibilityError(
            f"{label} dimensions mismatch: expected={expected_size}x{expected_size} "
            f"actual={summary['width']}x{summary['height']}"
        )
    present = set(summary["tile_type_counts"])
    if present != {"clear", "void"}:
        raise M02FeasibilityError(
            f"{label} is not a true empty editor map; tile types={sorted(present)}"
        )


def parse_unit_summary(output: str) -> tuple[int, int]:
    match = re.search(
        r"All tests passed \(([0-9]+) assertions in ([0-9]+) test cases\)",
        output,
    )
    if match is None:
        raise M02FeasibilityError("cannot parse complete OpenTTD unit-test summary")
    return int(match.group(2)), int(match.group(1))


def check_forbidden_diagnostics(output: str, pattern: str, label: str) -> None:
    match = re.search(pattern, output, re.IGNORECASE)
    if match is not None:
        raise M02FeasibilityError(
            f"{label} emitted forbidden diagnostic {match.group(0)!r}"
        )


class FeasibilityCommandRunner(run_openttd_build.CommandRunner):
    """Command logger with the shared fail-closed M01 execution semantics."""


def runtime_environment(
    base: dict[str, str],
    sysroot: pathlib.Path,
    user_root: pathlib.Path,
    sanitizer: str,
) -> dict[str, str]:
    environment = base.copy()
    environment.update(
        {
            "LD_LIBRARY_PATH": ":".join(
                [
                    str(sysroot / "usr/lib/x86_64-linux-gnu"),
                    str(sysroot / "usr/lib/x86_64-linux-gnu/pulseaudio"),
                    str(sysroot / "lib/x86_64-linux-gnu"),
                ]
            ),
            "SDL_AUDIODRIVER": "dummy",
            "SDL_VIDEODRIVER": "dummy",
            "XDG_CONFIG_HOME": str(user_root / "xdg-config"),
            "XDG_DATA_HOME": str(user_root / "xdg-data"),
        }
    )
    if sanitizer == "address":
        environment["ASAN_OPTIONS"] = (
            "abort_on_error=1:detect_leaks=1:halt_on_error=1:symbolize=0"
        )
    elif sanitizer == "undefined":
        environment["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=0"
    return environment


def write_editor_config(path: pathlib.Path, map_bits: int) -> None:
    path.mkdir(parents=True, exist_ok=False)
    (path / "openttd.cfg").write_text(
        "[game_creation]\n"
        f"map_x = {map_bits}\n"
        f"map_y = {map_bits}\n"
        "landscape = temperate\n"
        "terrain_type = 0\n"
        "amount_of_rivers = 0\n"
        "\n"
        "[network]\n"
        "server_game_type = local\n",
        encoding="utf-8",
    )


def common_runtime_args(executable: pathlib.Path) -> list[str]:
    return [
        str(executable),
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


def provision_runtime_content(runtime_root: pathlib.Path, runtime_cwd: pathlib.Path) -> None:
    language_source = runtime_cwd / "lang" / "english.lng"
    if not language_source.is_file():
        raise M02FeasibilityError(
            f"runtime content lacks English language pack: {language_source}"
        )
    language_target = runtime_root / "lang"
    language_target.mkdir()
    shutil.copy2(language_source, language_target / "english.lng")
    baseset_source = runtime_cwd / "baseset"
    baseset_target = runtime_root / "baseset"
    baseset_target.mkdir()
    required = (*run_openttd_build.OPENGFX_GAME_FILES, "no_sound.obs", "no_music.obm")
    for name in required:
        source = baseset_source / name
        if not source.is_file() or source.is_symlink():
            raise M02FeasibilityError(f"runtime content file is missing or invalid: {source}")
        shutil.copy2(source, baseset_target / name)


def create_empty_editor_save(
    runner: FeasibilityCommandRunner,
    *,
    label: str,
    executable: pathlib.Path,
    runtime_root: pathlib.Path,
    runtime_cwd: pathlib.Path,
    environment: dict[str, str],
    map_bits: int,
    seed: int,
    timeout_seconds: int,
    timeout_executable: pathlib.Path,
    forbidden_pattern: str,
) -> tuple[dict[str, Any], bytes]:
    write_editor_config(runtime_root, map_bits)
    provision_runtime_content(runtime_root, runtime_cwd)
    config = runtime_root / "openttd.cfg"
    save_name = label
    save_path = runtime_root / "save" / f"{save_name}.sav"
    script = runtime_root / "scripts" / "rl_environment_editor_start.scr"
    script.parent.mkdir()
    script.write_text(f"save {save_name}\n", encoding="utf-8")
    command = [
        str(timeout_executable),
        "--signal=KILL",
        f"{timeout_seconds}s",
    ] + common_runtime_args(executable) + [
        "-e",
        "-G",
        str(seed),
        "-c",
        str(config),
        "-v",
        "null:ticks=1",
    ]
    result = runner.run(
        label,
        command,
        cwd=runtime_cwd,
        environment=environment,
    )
    check_forbidden_diagnostics(result.stdout + result.stderr, forbidden_pattern, label)
    if not save_path.is_file():
        raise M02FeasibilityError(
            f"{label} did not execute the RL editor-ready save hook"
        )
    return parse_save(save_path)


def create_generated_game_save(
    runner: FeasibilityCommandRunner,
    *,
    label: str,
    executable: pathlib.Path,
    runtime_root: pathlib.Path,
    runtime_cwd: pathlib.Path,
    environment: dict[str, str],
    map_bits: int,
    seed: int,
    timeout_seconds: int,
    timeout_executable: pathlib.Path,
    forbidden_pattern: str,
) -> tuple[dict[str, Any], bytes]:
    write_editor_config(runtime_root, map_bits)
    provision_runtime_content(runtime_root, runtime_cwd)
    config = runtime_root / "openttd.cfg"
    save_name = label
    save_path = runtime_root / "save" / f"{save_name}.sav"
    script = runtime_root / "scripts" / "game_start.scr"
    script.parent.mkdir()
    script.write_text(f"save {save_name}\nexit\n", encoding="utf-8")
    command = [
        str(timeout_executable),
        "--signal=KILL",
        f"{timeout_seconds}s",
    ] + common_runtime_args(executable) + [
        "-D",
        "-G",
        str(seed),
        "-c",
        str(config),
    ]
    result = runner.run(
        label,
        command,
        cwd=runtime_cwd,
        environment=environment,
    )
    check_forbidden_diagnostics(result.stdout + result.stderr, forbidden_pattern, label)
    if not save_path.is_file():
        raise M02FeasibilityError(f"{label} did not execute the game-start save hook")
    return parse_save(save_path)


def locate_reference_executable(
    reference_root: pathlib.Path,
    reference_plan: dict[str, Any],
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, dict[str, Any]]:
    manifest_path = reference_root / "build-manifest.json"
    manifest = load_strict_json(manifest_path)
    if manifest.get("variant") != "playable":
        raise M02FeasibilityError("M01 reference is not a playable build")
    if manifest.get("build_identity_sha256") != reference_plan["build_identity_sha256"]:
        raise M02FeasibilityError("M01 reference build identity mismatch")
    prefix = manifest.get("configuration", {}).get("canonical_install_prefix")
    if not isinstance(prefix, str) or not prefix.startswith("/opt/"):
        raise M02FeasibilityError("M01 reference install prefix is invalid")
    install_root = reference_root / "stage" / prefix.removeprefix("/")
    executable = install_root / "games/openttd"
    runtime_cwd = install_root / "share/games/openttd"
    sysroot = reference_root / "sysroot"
    if not executable.is_file() or not runtime_cwd.is_dir() or not sysroot.is_dir():
        raise M02FeasibilityError("M01 reference runtime tree is incomplete")
    if run_openttd_build.sha256_file(executable) != reference_plan["executable_sha256"]:
        raise M02FeasibilityError("M01 reference executable digest mismatch")
    return executable, runtime_cwd, sysroot, manifest


def sanitizer_flags(sanitizer: str) -> tuple[str, str]:
    if sanitizer == "none":
        return "", ""
    if sanitizer == "address":
        return "-fsanitize=address -fno-omit-frame-pointer", "-fsanitize=address"
    if sanitizer == "undefined":
        return (
            "-fsanitize=undefined -fno-sanitize-recover=all -fno-omit-frame-pointer",
            "-fsanitize=undefined -fno-sanitize-recover=all",
        )
    raise M02FeasibilityError(f"unknown sanitizer: {sanitizer}")


def build_profile(
    *,
    root: pathlib.Path,
    artifact_root: pathlib.Path,
    workspace_root: pathlib.Path,
    source: pathlib.Path,
    sysroot: pathlib.Path,
    profile: dict[str, Any],
    plan: dict[str, Any],
    tools: dict[str, pathlib.Path],
    runner: FeasibilityCommandRunner,
    jobs: int,
) -> tuple[dict[str, Any], bytes]:
    profile_id = profile["id"]
    profile_root = artifact_root / "profiles" / profile_id
    build_root = workspace_root / "profiles" / profile_id / "build"
    products = artifact_root / "products" / profile_id
    products.mkdir(parents=True, exist_ok=False)
    compile_sanitizer, link_sanitizer = sanitizer_flags(profile["sanitizer"])
    debug_flag = "-g0" if profile["sanitizer"] == "none" else "-g1"
    prefix_maps: list[str] = []
    for original, replacement in (
        (source, "/usr/src/openttd-15.3-m02"),
        (build_root, "/usr/src/openttd-build-m02"),
        (artifact_root, "/var/lib/openttd-rl/m02-artifacts"),
        (root, "/usr/src/openttd-rl"),
    ):
        for option in ("ffile-prefix-map", "fdebug-prefix-map", "fmacro-prefix-map"):
            prefix_maps.append(f"-{option}={original}={replacement}")
    compile_flags = " ".join(
        part
        for part in (
            profile["optimization"],
            debug_flag,
            "-Werror -fno-record-gcc-switches",
            " ".join(prefix_maps),
            compile_sanitizer,
        )
        if part
    )
    link_flags = " ".join(
        part
        for part in (
            "-Wl,--build-id=none,"
            f"-rpath-link,{sysroot / 'usr/lib/x86_64-linux-gnu'},"
            f"-rpath-link,{sysroot / 'usr/lib/x86_64-linux-gnu/pulseaudio'}",
            link_sanitizer,
        )
        if part
    )
    configure = [
        str(tools["cmake"]),
        "-S",
        str(source),
        "-B",
        str(build_root),
        "-G",
        "Ninja",
        f"-DCMAKE_BUILD_TYPE={profile['build_type']}",
        *CMAKE_REPRODUCIBILITY_OPTIONS,
        f"-DCMAKE_C_COMPILER={tools['gcc']}",
        f"-DCMAKE_CXX_COMPILER={tools['gxx']}",
        f"-DCMAKE_MAKE_PROGRAM={tools['ninja']}",
        f"-DCMAKE_C_FLAGS_RELEASE={compile_flags}",
        f"-DCMAKE_CXX_FLAGS_RELEASE={compile_flags}",
        f"-DCMAKE_EXE_LINKER_FLAGS={link_flags}",
        f"-DCMAKE_PREFIX_PATH={sysroot / 'usr'}",
        f"-DCMAKE_INCLUDE_PATH={sysroot / 'usr/include'};"
        f"{sysroot / 'usr/include/x86_64-linux-gnu'};"
        f"{sysroot / 'usr/include/harfbuzz'}",
        f"-DCMAKE_LIBRARY_PATH={sysroot / 'usr/lib/x86_64-linux-gnu'}",
        "-DBUILD_TESTING=ON",
        "-DOPTION_DEDICATED=OFF",
        f"-DOPTION_RL_ENVIRONMENT={'ON' if profile['rl_environment'] else 'OFF'}",
        "-DOPTION_INSTALL_FHS=ON",
        "-DOPTION_PACKAGE_DEPENDENCIES=OFF",
        "-DOPTION_USE_ASSERTS=ON",
        "-DOPTION_FORCE_COLORED_OUTPUT=OFF",
        "-DOPTION_USE_NSIS=OFF",
        "-DOPTION_TOOLS_ONLY=OFF",
        "-DOPTION_DOCS_ONLY=OFF",
        "-DOPTION_ALLOW_INVALID_SIGNATURE=OFF",
        "-DOPTION_SURVEY_KEY=",
        "-DPERSONAL_DIR=.openttd-m02",
        "-DSHARED_DIR=(not set)",
        "-DGLOBAL_DIR=/opt/openttd-rl-v1-m02/share/games/openttd",
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
    configure_result = runner.run(
        f"{profile_id}-cmake-configure",
        configure,
        environment=build_environment,
        reject_warnings=True,
    )
    components = plan["validation"]["required_cmake_components"]
    missing = [component for component in components if component not in configure_result.stdout]
    if missing:
        raise M02FeasibilityError(
            f"{profile_id} CMake omitted required components: {missing}"
        )
    expected_option = f"Option RL Environment - {'ON' if profile['rl_environment'] else 'OFF'}"
    if expected_option not in configure_result.stdout:
        raise M02FeasibilityError(
            f"{profile_id} CMake did not report {expected_option}"
        )
    runner.run(
        f"{profile_id}-cmake-build",
        [str(tools["cmake"]), "--build", str(build_root), "--parallel", str(jobs)],
        environment=build_environment,
        reject_warnings=True,
    )
    packaged_baseset = sysroot / "usr/share/games/openttd/baseset/opengfx"
    for name in run_openttd_build.OPENGFX_GAME_FILES:
        source_file = packaged_baseset / name
        if not source_file.is_file() or source_file.is_symlink():
            raise M02FeasibilityError(
                f"locked OpenGFX gameplay file is missing or invalid: {source_file}"
            )
        shutil.copy2(source_file, build_root / "baseset" / name)
    executable = build_root / "openttd"
    test_executable = build_root / "openttd_test"
    if not executable.is_file() or not test_executable.is_file():
        raise M02FeasibilityError(f"{profile_id} build omitted OpenTTD binaries")
    shutil.copy2(executable, products / "openttd")
    shutil.copy2(test_executable, products / "openttd_test")
    runtime_env = runtime_environment(
        runner.environment,
        sysroot,
        profile_root / "user",
        profile["sanitizer"],
    )
    unit = runner.run(
        f"{profile_id}-unit-tests",
        [str(test_executable), "~[.]"],
        cwd=build_root,
        environment=runtime_env,
    )
    unit_output = unit.stdout + unit.stderr
    check_forbidden_diagnostics(
        unit_output,
        plan["validation"]["forbidden_diagnostics_regex"],
        f"{profile_id} unit tests",
    )
    test_cases, assertions = parse_unit_summary(unit_output)
    if (
        test_cases != plan["validation"]["unit_test_cases"]
        or assertions != plan["validation"]["unit_test_assertions"][profile_id]
    ):
        raise M02FeasibilityError(
            f"{profile_id} unit-test totals drifted: cases={test_cases} assertions={assertions}"
        )
    inventory = runner.run(
        f"{profile_id}-ctest-inventory",
        [str(tools["ctest"]), "--test-dir", str(build_root), "--show-only=json-v1"],
        environment=runtime_env,
    )
    regression_names = run_openttd_build.parse_ctest_inventory(inventory.stdout)
    if regression_names != plan["validation"]["regression_tests"]:
        raise M02FeasibilityError(
            f"{profile_id} regression inventory drifted: {regression_names}"
        )
    regression = runner.run(
        f"{profile_id}-ctest",
        [
            str(tools["ctest"]),
            "--test-dir",
            str(build_root),
            "--output-on-failure",
            "--no-tests=error",
            "--timeout",
            str(plan["validation"]["timeout_seconds"]),
        ],
        environment=runtime_env,
    )
    check_forbidden_diagnostics(
        regression.stdout + regression.stderr,
        plan["validation"]["forbidden_diagnostics_regex"],
        f"{profile_id} regressions",
    )
    map64, payload64 = create_generated_game_save(
        runner,
        label=f"{profile_id}-generated64",
        executable=executable,
        runtime_root=profile_root / "runtime-generated64",
        runtime_cwd=build_root,
        environment=runtime_env,
        map_bits=6,
        seed=plan["validation"]["seed"],
        timeout_seconds=plan["validation"]["timeout_seconds"],
        timeout_executable=tools["timeout"],
        forbidden_pattern=plan["validation"]["forbidden_diagnostics_regex"],
    )
    if map64["width"] != 64 or map64["height"] != 64:
        raise M02FeasibilityError(
            f"{profile_id} generated 64 dimensions drifted: "
            f"{map64['width']}x{map64['height']}"
        )

    empty32: dict[str, Any] | None = None
    generated32: dict[str, Any] | None = None
    if profile["rl_environment"]:
        repetitions: list[dict[str, Any]] = []
        repetition_payloads: list[bytes] = []
        for repetition in range(1, plan["validation"]["empty_save_repetitions"] + 1):
            summary, payload = create_empty_editor_save(
                runner,
                label=f"{profile_id}-empty32-{repetition}",
                executable=executable,
                runtime_root=profile_root / f"runtime-empty32-{repetition}",
                runtime_cwd=build_root,
                environment=runtime_env,
                map_bits=5,
                seed=plan["validation"]["seed"],
                timeout_seconds=plan["validation"]["timeout_seconds"],
                timeout_executable=tools["timeout"],
                forbidden_pattern=plan["validation"]["forbidden_diagnostics_regex"],
            )
            validate_empty_save(summary, 32, f"{profile_id} empty 32 repetition {repetition}")
            repetitions.append(summary)
            repetition_payloads.append(payload)
        if len({value["save_sha256"] for value in repetitions}) != 1:
            raise M02FeasibilityError(f"{profile_id} repeated empty 32 saves are not byte-identical")
        if len({sha256_bytes(payload) for payload in repetition_payloads}) != 1:
            raise M02FeasibilityError(f"{profile_id} repeated empty 32 payloads differ")
        first_save = (
            profile_root
            / "runtime-empty32-1"
            / "save"
            / f"{profile_id}-empty32-1.sav"
        )
        soak = runner.run(
            f"{profile_id}-empty32-reload-soak",
            common_runtime_args(executable)
            + [
                "-e",
                "-g",
                str(first_save),
                "-v",
                f"null:ticks={plan['validation']['soak_ticks']}",
            ],
            cwd=build_root,
            environment=runtime_env,
        )
        check_forbidden_diagnostics(
            soak.stdout + soak.stderr,
            plan["validation"]["forbidden_diagnostics_regex"],
            f"{profile_id} empty 32 reload soak",
        )
        generated_root = profile_root / "runtime-generated32"
        write_editor_config(generated_root, 5)
        generated = runner.run(
            f"{profile_id}-generated32",
            common_runtime_args(executable)
            + [
                "-g",
                "-G",
                str(plan["validation"]["seed"]),
                "-c",
                str(generated_root / "openttd.cfg"),
                "-v",
                f"null:ticks={plan['validation']['generated_32_ticks']}",
            ],
            cwd=build_root,
            environment=runtime_env,
        )
        check_forbidden_diagnostics(
            generated.stdout + generated.stderr,
            plan["validation"]["forbidden_diagnostics_regex"],
            f"{profile_id} generated 32",
        )
        empty32 = {
            "repetitions": [canonical_save_summary(value) for value in repetitions],
            "byte_identical": True,
            "reload": "PASS",
            "soak_ticks": plan["validation"]["soak_ticks"],
            "result": "PASS",
        }
        generated32 = {
            "ticks": plan["validation"]["generated_32_ticks"],
            "seed": plan["validation"]["seed"],
            "result": "PASS",
        }
        requested_32 = {
            "permitted": True,
            "actual_width": 32,
            "actual_height": 32,
            "result": "PASS",
        }
    else:
        restricted, _ = create_generated_game_save(
            runner,
            label=f"{profile_id}-requested32",
            executable=executable,
            runtime_root=profile_root / "runtime-requested32",
            runtime_cwd=build_root,
            environment=runtime_env,
            map_bits=5,
            seed=plan["validation"]["seed"],
            timeout_seconds=plan["validation"]["timeout_seconds"],
            timeout_executable=tools["timeout"],
            forbidden_pattern=plan["validation"]["forbidden_diagnostics_regex"],
        )
        if restricted["width"] != 64 or restricted["height"] != 64:
            raise M02FeasibilityError(
                f"{profile_id} did not reject the 32 request: "
                f"actual={restricted['width']}x{restricted['height']}"
            )
        requested_32 = {
            "permitted": False,
            "actual_width": 64,
            "actual_height": 64,
            "result": "PASS",
        }

    profile_report = {
        "id": profile_id,
        "rl_environment": profile["rl_environment"],
        "sanitizer": profile["sanitizer"],
        "binary_sha256": run_openttd_build.sha256_file(products / "openttd"),
        "test_binary_sha256": run_openttd_build.sha256_file(products / "openttd_test"),
        "cmake_components": components,
        "unit_tests": {
            "test_cases": test_cases,
            "assertions": assertions,
            "result": "PASS",
        },
        "regression_tests": {"names": regression_names, "result": "PASS"},
        "requested_32": requested_32,
        "empty_32": empty32,
        "generated_32": generated32,
        "generated_64": canonical_save_summary(map64),
        "result": "PASS",
    }
    shutil.rmtree(build_root)
    if build_root.exists():
        raise M02FeasibilityError(f"{profile_id} clean build directory removal failed")
    return profile_report, payload64


def exact_tool_versions(
    tools: dict[str, pathlib.Path],
    plan: dict[str, Any],
    runner: FeasibilityCommandRunner,
) -> dict[str, str]:
    values: dict[str, str] = {}
    values["gcc"] = runner.run("gcc-version", [str(tools["gcc"]), "-dumpfullversion"]).stdout.strip()
    values["gxx"] = runner.run("gxx-version", [str(tools["gxx"]), "-dumpfullversion"]).stdout.strip()
    values["ninja"] = runner.run("ninja-version", [str(tools["ninja"]), "--version"]).stdout.strip()
    for name in ("cmake", "ctest"):
        output = runner.run(f"{name}-version", [str(tools[name]), "--version"]).stdout
        match = re.search(rf"^{name} version ([0-9.]+)$", output, re.MULTILINE)
        if match is None:
            raise M02FeasibilityError(f"cannot parse {name} version")
        values[name] = match.group(1)
    for name, expected in plan["tools"].items():
        if values[name] != expected:
            raise M02FeasibilityError(
                f"{name} version mismatch: expected={expected} actual={values[name]}"
            )
    return values


def write_json(path: pathlib.Path, value: Any) -> None:
    if path.exists():
        raise M02FeasibilityError(f"refusing to overwrite output: {path}")
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_human_report(path: pathlib.Path, report: dict[str, Any]) -> None:
    if path.exists():
        raise M02FeasibilityError(f"refusing to overwrite output: {path}")
    lines = [
        "M02_MAP_FEASIBILITY=PASS",
        f"plan={report['plan']['id']} sha256={report['plan']['sha256']}",
        f"prepared_tree={report['source']['prepared_tree']}",
        f"source_identity={report['source']['composed_identity_sha256']}",
        f"offline_build_inputs={report['build_inputs']['artifact_count']}",
    ]
    for profile in report["profiles"]:
        requested = profile["requested_32"]
        lines.append(
            f"profile={profile['id']} flag={'ON' if profile['rl_environment'] else 'OFF'} "
            f"sanitizer={profile['sanitizer']} tests="
            f"{profile['unit_tests']['test_cases']}/{profile['unit_tests']['assertions']} "
            f"requested32={requested['actual_width']}x{requested['actual_height']} PASS"
        )
        if profile["empty_32"] is not None:
            lines.append(
                f"profile={profile['id']} empty32_repetitions="
                f"{len(profile['empty_32']['repetitions'])} "
                f"soak_ticks={profile['empty_32']['soak_ticks']} PASS"
            )
        lines.append(f"profile={profile['id']} generated64=PASS")
    lines.extend(
        [
            "normal64_reference=m01-playable-build-20260801-g map_chunks_byte_identical=PASS",
            "forbidden_scope=bridge,scenario,ppo,neural-agent ABSENT",
            f"report_identity={report['report_identity_sha256']}",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def canonical_workspace_root(artifact_root: pathlib.Path) -> pathlib.Path:
    return artifact_root.parent / ".m02-map-feasibility-work"


def run_feasibility_in_workspace(
    options: argparse.Namespace,
    workspace_root: pathlib.Path,
) -> dict[str, Any]:
    root = options.root.resolve()
    artifact_root = options.artifact_root.resolve()
    cache_root = options.cache_root.resolve()
    reference_root = options.reference_root.resolve()
    plan_path = options.plan.resolve()
    plan_schema_path = options.plan_schema.resolve()
    report_schema_path = options.report_schema.resolve()
    if not artifact_root.is_dir() or any(artifact_root.iterdir()):
        raise M02FeasibilityError("artifact root must be an existing empty directory")
    if not cache_root.is_dir():
        raise M02FeasibilityError(f"offline build-input cache does not exist: {cache_root}")
    if not reference_root.is_dir():
        raise M02FeasibilityError(f"M01 reference root does not exist: {reference_root}")
    plan, plan_sha256 = load_plan(plan_path, plan_schema_path)
    validate_plan_files(root, plan)
    report_schema = load_strict_json(report_schema_path)
    tools = {
        name: run_openttd_build.resolve_executable(getattr(options, name), name)
        for name in ("cmake", "ctest", "dpkg_deb", "gcc", "gxx", "ninja", "timeout")
    }
    runner = FeasibilityCommandRunner(
        artifact_root / "logs",
        run_openttd_build.clean_environment(),
    )
    tool_versions = exact_tool_versions(tools, plan, runner)
    lock_path = root / plan["build_inputs"]["lock_path"]
    lock = run_openttd_build.load_lock(lock_path)
    package_records = run_openttd_build.validate_cache(
        lock,
        cache_root,
        tools["dpkg_deb"],
        runner,
    )
    inventory_sha256 = sha256_bytes(canonical_bytes(package_records))

    source = workspace_root / "source"
    base_manifest_path = artifact_root / "base-prepared-source.json"
    base = prepare_openttd_source.prepare(
        root=root,
        profile_path=root / plan["source"]["base_profile_path"],
        profile_schema_path=root / "docs/project/schema/v1-source-profile.schema.json",
        manifest_schema_path=root / "docs/project/schema/v1-prepared-source-manifest.schema.json",
        object_repository_override=root / "openttd-upstream",
        output=source,
        manifest_path=base_manifest_path,
    )
    if (
        base["source"]["commit"] != SOURCE_COMMIT
        or base["source"]["tree"] != SOURCE_TREE
        or base["result"]["tree"] != plan["source"]["base_prepared_tree"]
        or base["preparation_identity_sha256"]
        != plan["source"]["base_preparation_identity_sha256"]
    ):
        raise M02FeasibilityError("accepted M01 prepared-source identity drifted")
    series, patches, patch_records = validate_delta_series(root, plan["source"])
    prepare_openttd_source.apply_patches(source, patches, SOURCE_TREE)
    prepared_tree = prepare_openttd_source.git(source, "write-tree")
    if prepared_tree != plan["source"]["result_tree"]:
        raise M02FeasibilityError(
            f"M02 prepared tree mismatch: expected={plan['source']['result_tree']} "
            f"actual={prepared_tree}"
        )
    composed_identity = composed_source_identity(
        base["preparation_identity_sha256"],
        run_openttd_build.sha256_file(series),
        patch_records,
        prepared_tree,
    )
    if composed_identity != plan["source"]["composed_identity_sha256"]:
        raise M02FeasibilityError("M02 composed source identity mismatch")
    composed_manifest = {
        "schema_version": "openttd-rl-v1-m02-composed-source-1",
        "source_commit": SOURCE_COMMIT,
        "source_tree": SOURCE_TREE,
        "base_prepared_tree": base["result"]["tree"],
        "base_preparation_identity_sha256": base["preparation_identity_sha256"],
        "delta_series_sha256": run_openttd_build.sha256_file(series),
        "patches": patch_records,
        "result_tree": prepared_tree,
        "composed_identity_sha256": composed_identity,
    }
    write_json(artifact_root / "composed-source.json", composed_manifest)
    shutil.move(source / ".git", artifact_root / "source-preparation-git-metadata")
    (source / ".ottdrev").write_text(OTTDREV, encoding="utf-8")

    sysroot = workspace_root / "sysroot"
    sysroot.mkdir()
    for index, artifact in enumerate(lock["artifacts"], 1):
        runner.run(
            f"deb-extract-{index:02d}",
            [
                str(tools["dpkg_deb"]),
                "-x",
                str(cache_root / artifact["filename"]),
                str(sysroot),
            ],
        )
    packaged_baseset = sysroot / "usr/share/games/openttd/baseset/opengfx"
    if not (packaged_baseset / "opengfx.obg").is_file():
        raise M02FeasibilityError("locked OpenGFX extraction is incomplete")

    reference_executable, reference_cwd, reference_sysroot, _ = locate_reference_executable(
        reference_root,
        plan["reference"],
    )
    reference_runtime = artifact_root / "reference-runtime-generated64"
    reference_env = runtime_environment(
        runner.environment,
        reference_sysroot,
        artifact_root / "reference-user",
        "none",
    )
    reference_save, reference_payload = create_generated_game_save(
        runner,
        label="m01-reference-generated64",
        executable=reference_executable,
        runtime_root=reference_runtime,
        runtime_cwd=reference_cwd,
        environment=reference_env,
        map_bits=6,
        seed=plan["validation"]["seed"],
        timeout_seconds=plan["validation"]["timeout_seconds"],
        timeout_executable=tools["timeout"],
        forbidden_pattern=plan["validation"]["forbidden_diagnostics_regex"],
    )
    if reference_save["width"] != 64 or reference_save["height"] != 64:
        raise M02FeasibilityError(
            "M01 reference generated map is not 64 by 64"
        )

    profile_reports: list[dict[str, Any]] = []
    profile_payloads: dict[str, bytes] = {}
    for profile in plan["profiles"]:
        profile_report, payload64 = build_profile(
            root=root,
            artifact_root=artifact_root,
            workspace_root=workspace_root,
            source=source,
            sysroot=sysroot,
            profile=profile,
            plan=plan,
            tools=tools,
            runner=runner,
            jobs=options.jobs,
        )
        profile_reports.append(profile_report)
        profile_payloads[profile["id"]] = payload64
    save_artifacts = []
    for save_path in discover_runtime_save_paths(artifact_root):
        summary, _ = parse_save(save_path)
        save_artifacts.append(
            {"path": save_path.relative_to(artifact_root).as_posix(), **summary}
        )
    if not save_artifacts:
        raise M02FeasibilityError("M02 feasibility run produced no savegame evidence")
    write_json(
        artifact_root / "save-artifacts.noncanonical.json",
        {
            "schema_version": "openttd-rl-v1-m02-save-artifact-records-1",
            "note": "Raw saves include OpenTTD's intentional unique session ID; map_sha256 is the deterministic behavior oracle.",
            "artifacts": save_artifacts,
        },
    )
    unequal = [profile_id for profile_id, payload in profile_payloads.items() if payload != reference_payload]
    if unequal:
        raise M02FeasibilityError(
            f"normal 64 by 64 save payload differs from M01 reference: {unequal}"
        )
    equivalence = {
        "reference_map_sha256": sha256_bytes(reference_payload),
        "profile_map_sha256": {
            profile_id: sha256_bytes(payload)
            for profile_id, payload in profile_payloads.items()
        },
        "map_chunks_byte_identical": True,
        "result": "PASS",
    }
    report_base = {
        "schema_version": "openttd-rl-v1-m02-map-feasibility-report-1",
        "plan": {"id": plan["plan_id"], "sha256": plan_sha256},
        "source": {
            "commit": SOURCE_COMMIT,
            "base_prepared_tree": base["result"]["tree"],
            "base_preparation_identity_sha256": base["preparation_identity_sha256"],
            "delta_series_sha256": run_openttd_build.sha256_file(series),
            "patches": patch_records,
            "prepared_tree": prepared_tree,
            "composed_identity_sha256": composed_identity,
        },
        "build_inputs": {
            "lock_sha256": run_openttd_build.sha256_file(lock_path),
            "artifact_count": len(package_records),
            "inventory_sha256": inventory_sha256,
            "offline_only": True,
        },
        "reference": {
            "artifact_id": plan["reference"]["artifact_id"],
            "build_identity_sha256": plan["reference"]["build_identity_sha256"],
            "executable_sha256": plan["reference"]["executable_sha256"],
            "generated_64": canonical_save_summary(reference_save),
        },
        "tools": tool_versions,
        "profiles": profile_reports,
        "equivalence_64": equivalence,
        "result": "PASS",
    }
    report = dict(report_base)
    report["report_identity_sha256"] = sha256_bytes(canonical_bytes(report_base))
    validate_schema(report, report_schema, "M02 feasibility report")
    write_json(artifact_root / "map-feasibility-report.json", report)
    write_human_report(artifact_root / "map-feasibility-report.txt", report)
    roots = {
        "<M01_REFERENCE_ROOT>": reference_root,
        "<ARTIFACT_ROOT>": artifact_root,
        "<SOURCE_ROOT>": source,
        "<SYSROOT>": sysroot,
        "<CACHE_ROOT>": cache_root,
        "<REPOSITORY_ROOT>": root,
        "<WORKSPACE_ROOT>": workspace_root,
    }
    write_json(
        artifact_root / "commands.json",
        run_openttd_build.replace_roots(runner.commands, roots),
    )
    write_json(
        artifact_root / "timing.json",
        {
            "schema_version": "openttd-rl-v1-m02-map-feasibility-timing-1",
            "seconds": runner.timings,
            "total_seconds": round(sum(runner.timings.values()), 3),
        },
    )
    shutil.move(source, artifact_root / "source")
    shutil.move(sysroot, artifact_root / "sysroot")
    shutil.rmtree(workspace_root)
    return report


def run_feasibility(options: argparse.Namespace) -> dict[str, Any]:
    artifact_root = options.artifact_root.resolve()
    if not artifact_root.is_dir() or any(artifact_root.iterdir()):
        raise M02FeasibilityError("artifact root must be an existing empty directory")
    workspace_root = canonical_workspace_root(artifact_root)
    if workspace_root.exists() or workspace_root.is_symlink():
        raise M02FeasibilityError(
            f"canonical M02 workspace already exists: {workspace_root}"
        )
    workspace_root.mkdir(mode=0o700)
    try:
        return run_feasibility_in_workspace(options, workspace_root)
    except Exception:
        if workspace_root.exists() or workspace_root.is_symlink():
            failed_workspace = artifact_root / "failed-canonical-workspace"
            if failed_workspace.exists() or failed_workspace.is_symlink():
                raise M02FeasibilityError(
                    f"cannot preserve failed canonical workspace: {failed_workspace}"
                )
            shutil.move(workspace_root, failed_workspace)
        raise


def parse_args(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--artifact-root", required=True, type=pathlib.Path)
    parser.add_argument("--cache-root", required=True, type=pathlib.Path)
    parser.add_argument("--reference-root", required=True, type=pathlib.Path)
    parser.add_argument("--plan", required=True, type=pathlib.Path)
    parser.add_argument("--plan-schema", required=True, type=pathlib.Path)
    parser.add_argument("--report-schema", required=True, type=pathlib.Path)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--ctest", default="ctest")
    parser.add_argument("--dpkg-deb", dest="dpkg_deb", default="dpkg-deb")
    parser.add_argument("--gcc", default="gcc")
    parser.add_argument("--gxx", default="g++")
    parser.add_argument("--ninja", default="ninja")
    parser.add_argument("--timeout", default="timeout")
    options = parser.parse_args(arguments)
    if options.jobs < 1:
        parser.error("--jobs must be positive")
    return options


def main(arguments: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        report = run_feasibility(options)
    except (
        M02FeasibilityError,
        prepare_openttd_source.SourcePreparationError,
        run_openttd_build.OpenTTDBuildError,
        OSError,
        UnicodeError,
    ) as exc:
        print(f"V1_M02_MAP_FEASIBILITY=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "V1_M02_MAP_FEASIBILITY=PASS "
        f"profiles={len(report['profiles'])} "
        f"identity={report['report_identity_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
