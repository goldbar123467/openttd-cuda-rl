#!/usr/bin/env python3
"""Build and retain the final-manifest-blind M22 native runtime.

The runner starts from the accepted M21 source, applies the cumulative M22
patch exactly, builds and tests OpenTTD, stages the byte-pinned M20/M21 runtime
closure, and executes only the fixed synthetic source-smoke inventory.  It does
not know the final evaluation manifest path and cannot execute final cases.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import xml.etree.ElementTree as ET
from typing import Any

import jsonschema

from artifact_context import (
    ArtifactContext, ArtifactContextError, ToolRequirement, preflight_tools,
    resolve_artifact_root,
)
import m22_final_native as native
import validate_m20_competition_source as m20_source
import validate_m21_broad_source as m21_source


PATCH = pathlib.Path("integration/openttd/patches/15.3/m22/final/0001-Add-M22-final-world-overrides.patch")
SCHEMA = pathlib.Path("docs/project/schema/v2-m22-final-runtime-source.schema.json")
LEARNING_CONTRACT = pathlib.Path("config/v2/m22-learning-contract.json")
M20_SOURCE = pathlib.Path("config/v2/m20-competition-source.json")
M20_CONTENT = pathlib.Path("config/v2/m20-content-manifest.json")
M21_SOURCE = pathlib.Path("config/v2/m21-broad-source.json")
M21_CONTENT_LOCK = pathlib.Path("config/v2/m21-content-lock.json")
TOUCHED = (
    "src/rl_v2_action.cpp", "src/rl_v2_air.cpp", "src/rl_v2_broad.cpp", "src/rl_v2_cargo.cpp",
    "src/rl_v2_competition.cpp", "src/rl_v2_environment.cpp", "src/rl_v2_final_world.h",
    "src/rl_v2_rail.cpp", "src/rl_v2_ship.cpp",
)
CMAKE_ARGUMENTS = (
    "-DCMAKE_BUILD_TYPE=RelWithDebInfo", "-DOPTION_RL_ENVIRONMENT=ON",
    "-DOPTION_RL_NEURAL_AGENT=OFF", "-DOPTION_USE_ASSERTS=ON",
)
SOURCE_COMMIT_MESSAGE = "Add final-manifest-blind M22 runtime overrides"
SOURCE_COMMIT_ENV = {
    "GIT_AUTHOR_NAME": "OpenTTD RL Evidence", "GIT_AUTHOR_EMAIL": "evidence@openttd-rl.invalid",
    "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z", "GIT_COMMITTER_NAME": "OpenTTD RL Evidence",
    "GIT_COMMITTER_EMAIL": "evidence@openttd-rl.invalid", "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
}

SMOKE_CASES: tuple[dict[str, Any], ...] = (
    {"case_id": "source-g15-toyland-road", "task": "service", "transport_mode": "road", "climate": "toyland",
     "map_width": 128, "map_height": 64, "cargo": "PASS", "opponent": "not-applicable", "seed": 221501,
     "required_program": "passenger-service", "native_probe": "passenger-service", "source_gate": "G15"},
    {"case_id": "source-g16-toyland-cargo", "task": "service", "transport_mode": "road", "climate": "toyland",
     "map_width": 128, "map_height": 128, "cargo": "TOYS", "opponent": "not-applicable", "seed": 221601,
     "required_program": "cargo-service", "native_probe": "single-leg", "source_gate": "G16"},
    {"case_id": "source-g17-arctic-rail", "task": "service", "transport_mode": "rail", "climate": "arctic",
     "map_width": 128, "map_height": 64, "cargo": "PASS", "opponent": "not-applicable", "seed": 221701,
     "required_program": "rail-passenger", "native_probe": "passenger", "source_gate": "G17"},
    {"case_id": "source-g18-tropic-water", "task": "service", "transport_mode": "water", "climate": "tropic",
     "map_width": 512, "map_height": 128, "cargo": "PASS", "opponent": "not-applicable", "seed": 221801,
     "required_program": "ship-natural", "native_probe": "natural", "source_gate": "G18"},
    {"case_id": "source-g19-toyland-air", "task": "service", "transport_mode": "air", "climate": "toyland",
     "map_width": 128, "map_height": 128, "cargo": "PASS", "opponent": "not-applicable", "seed": 221901,
     "required_program": "air-service", "native_probe": "service", "source_gate": "G19"},
    {"case_id": "source-g20-tropic-aaahogex", "task": "competition", "transport_mode": "company", "climate": "tropic",
     "map_width": 128, "map_height": 128, "cargo": "PASS", "opponent": "AAAHogEx", "seed": 222001,
     "required_program": "competition-head-to-head", "native_probe": "head-to-head", "source_gate": "G20"},
    {"case_id": "source-g21-arctic-content", "task": "retention", "transport_mode": "broad", "climate": "arctic",
     "map_width": 128, "map_height": 64, "cargo": "not-applicable", "opponent": "not-applicable", "seed": 222101,
     "required_program": "content-discovery", "native_probe": "content", "source_gate": "G21"},
    {"case_id": "source-g21-tropic-gamescript", "task": "retention", "transport_mode": "broad", "climate": "tropic",
     "map_width": 512, "map_height": 128, "cargo": "not-applicable", "opponent": "not-applicable", "seed": 222102,
     "required_program": "gamescript-response", "native_probe": "gamescript", "source_gate": "G21"},
)


class M22RuntimePreparationError(ValueError):
    """The retained runtime could not be prepared without weakening M22."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22RuntimePreparationError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_new(path: pathlib.Path, value: Any) -> None:
    require(not path.exists() and not path.is_symlink(), f"output already exists: {path}")
    path.write_bytes(canonical_bytes(value))


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: pathlib.Path) -> dict[str, Any]:
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), f"retained file is unavailable: {path}")
    return {"bytes": path.stat().st_size, "path": str(path), "sha256": sha256(path)}


def git(repository: pathlib.Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    require(completed.returncode == 0, f"git {' '.join(arguments)} failed: {(completed.stderr or completed.stdout).strip()}")
    return completed.stdout.strip()


def checked(command: list[str], cwd: pathlib.Path, *, timeout: int, log: pathlib.Path | None = None,
            environment: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command, cwd=cwd, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
    )
    if log is not None:
        require(not log.exists() and not log.is_symlink(), f"log already exists: {log}")
        log.write_text(completed.stdout, encoding="utf-8")
    diagnostic = completed.stdout.strip()
    if len(diagnostic) > 8000:
        diagnostic = f"[output truncated to final 8000 characters]\n{diagnostic[-8000:]}"
    require(completed.returncode == 0, f"command failed ({completed.returncode}) {' '.join(command)}: {diagnostic}")
    return completed.stdout.strip()


def copy_exact(source: pathlib.Path, destination: pathlib.Path, expected_sha256: str) -> dict[str, Any]:
    require(source.is_file() and not source.is_symlink() and sha256(source) == expected_sha256,
            f"source asset identity drifted: {source}")
    require(not destination.exists() and not destination.is_symlink(), f"staged asset already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    require(sha256(destination) == expected_sha256, f"staged asset copy drifted: {destination}")
    return file_record(destination)


def prepare_source(base_source: pathlib.Path, source_path: pathlib.Path, patch: pathlib.Path,
                   base_commit: str) -> dict[str, str]:
    checked(["git", "clone", "--no-hardlinks", "--no-checkout", str(base_source), str(source_path)],
            source_path.parent, timeout=300)
    git(source_path, "checkout", "--detach", base_commit)
    require(git(source_path, "status", "--porcelain") == "", "fresh M21 clone is dirty")
    checked(["git", "apply", "--check", "--whitespace=error-all", str(patch)], source_path, timeout=60)
    checked(["git", "apply", "--index", "--whitespace=error-all", str(patch)], source_path, timeout=60)
    require(tuple(git(source_path, "diff", "--cached", "--name-only").splitlines()) == TOUCHED,
            "staged M22 patch scope drifted")
    environment = dict(os.environ)
    environment.update(SOURCE_COMMIT_ENV)
    checked(["git", "-c", "commit.gpgSign=false", "commit", "--no-gpg-sign", "-m", SOURCE_COMMIT_MESSAGE],
            source_path, timeout=60, environment=environment)
    require(git(source_path, "status", "--porcelain") == "", "retained M22 source is dirty after commit")
    return {"commit": git(source_path, "rev-parse", "HEAD"), "path": str(source_path),
            "tree": git(source_path, "rev-parse", "HEAD^{tree}")}


def configure_and_build(source_path: pathlib.Path, build_path: pathlib.Path, artifact_root: pathlib.Path,
                        jobs: int, open_gfx_source: pathlib.Path, open_gfx_sha256: str) -> tuple[dict[str, Any], dict[str, Any]]:
    require(shutil.which("cmake") is not None and shutil.which("ninja") is not None,
            "CMake and Ninja are required for M22 runtime preparation")
    configure_log, build_log = artifact_root / "configure.log", artifact_root / "build.log"
    checked(["cmake", "-S", str(source_path), "-B", str(build_path), "-G", "Ninja", *CMAKE_ARGUMENTS],
            artifact_root, timeout=900, log=configure_log)
    checked(["cmake", "--build", str(build_path), "-j", str(jobs)], artifact_root, timeout=7200, log=build_log)
    open_gfx = copy_exact(open_gfx_source, build_path / "baseset" / open_gfx_source.name, open_gfx_sha256)
    inventory_raw = checked(["ctest", "--test-dir", str(build_path), "--show-only=json-v1"],
                            artifact_root, timeout=120)
    inventory = json.loads(inventory_raw)
    names = [item["name"] for item in inventory["tests"]]
    require(len(names) == 98 and len(set(names)) == 98, "upstream CTest inventory drifted")
    inventory_path = artifact_root / "ctest-inventory.json"
    write_new(inventory_path, {"tests": names})
    junit = artifact_root / "ctest.xml"
    ctest_log = artifact_root / "ctest.log"
    checked(["ctest", "--test-dir", str(build_path), "--output-on-failure", "--no-tests=error",
             "--output-junit", str(junit)], artifact_root, timeout=900, log=ctest_log)
    xml = ET.parse(junit).getroot()
    suites = [xml] if xml.tag == "testsuite" else list(xml.findall("testsuite"))
    totals = {key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    require(totals == {"tests": 98, "failures": 0, "errors": 0, "skipped": 0},
            f"upstream CTest results drifted: {totals}")
    executable = build_path / "openttd"
    require(executable.is_file() and os.access(executable, os.X_OK), "built OpenTTD executable is unavailable")
    return {
        "cmake_arguments": list(CMAKE_ARGUMENTS), "generator": "Ninja", "jobs": jobs,
        "logs": {"build": file_record(build_log), "configure": file_record(configure_log),
                 "ctest": file_record(ctest_log), "junit": file_record(junit)},
        "test_inventory": file_record(inventory_path), "upstream_ctest": {"passed": 98, "total": 98},
    }, open_gfx


def stage_runtime(root: pathlib.Path, artifact_root: pathlib.Path, build_path: pathlib.Path,
                  artifact_context: ArtifactContext,
                  open_gfx: dict[str, Any]) -> dict[str, Any]:
    m20_content = load(root / M20_CONTENT)
    m21_config, content_lock = load(root / M21_SOURCE), load(root / M21_CONTENT_LOCK)
    require(artifact_context.is_live, "M22 runtime staging requires one live artifact context")
    m20_set = artifact_context.artifact_set("v2-m20-competition-a")
    m21_set = artifact_context.artifact_set("v2-m21-broad-a")
    configs: dict[str, dict[str, Any]] = {}
    for name, record in m21_config["runtime"]["configs"].items():
        configs[name] = copy_exact(m21_set / f"{name}.cfg", artifact_root / f"{name}.cfg", record["sha256"])
    ai_archives = []
    for record in m20_content["ai_archives"]:
        source = m20_set / "content_download" / "ai" / pathlib.PurePosixPath(record["path"]).name
        copied = copy_exact(source, artifact_root / "content_download" / "ai" / source.name, record["sha256"])
        ai_archives.append({"name": record["name"], **copied})
    ai_libraries = []
    for record in m20_content["libraries"]:
        source = m20_set / "content_download" / "ai" / "library" / pathlib.PurePosixPath(record["path"]).name
        ai_libraries.append(copy_exact(source, artifact_root / "content_download" / "ai" / "library" / source.name,
                                       record["sha256"]))
    newgrf_archives = []
    for package in content_lock["packages"]:
        relative = pathlib.Path(package["archive"]["path"])
        source = m21_set / "build-broad" / relative
        newgrf_archives.append(copy_exact(source, build_path / relative, package["archive"]["sha256"]))
    newgrf_files = []
    source_content_root = m21_set / "build-broad" / "newgrf" / "m21"
    for record in m21_config["runtime"]["content_files"]:
        newgrf_files.append(copy_exact(source_content_root / record["name"], build_path / "newgrf" / "m21" / record["name"],
                                       record["sha256"]))
    gamescript_files = []
    source_gamescript = m21_set / "build-broad" / "game" / "m21coverage"
    for name in ("info.nut", "main.nut"):
        source = source_gamescript / name
        gamescript_files.append(copy_exact(source, build_path / "game" / "m21coverage" / name, sha256(source)))
    return {
        "ai_archives": ai_archives, "ai_libraries": ai_libraries, "configs": configs,
        "gamescript_files": gamescript_files, "network_calls_during_preparation": "none",
        "newgrf_archives": newgrf_archives, "newgrf_files": newgrf_files, "open_gfx": open_gfx,
    }


def preflight_bwrap(bwrap_path: pathlib.Path | None) -> pathlib.Path:
    require(bwrap_path is not None, "an explicit Bubblewrap path is required")
    bwrap = pathlib.Path(bwrap_path)
    preflight_tools((ToolRequirement("bwrap", bwrap),))
    return bwrap


def run_smokes(
    root: pathlib.Path, artifact_root: pathlib.Path, runtime: native.RuntimePaths, *,
    bwrap_path: pathlib.Path,
) -> list[dict[str, Any]]:
    records = []
    smoke_root = artifact_root / "smokes"
    smoke_root.mkdir(mode=0o700)
    for ordinal, case in enumerate(SMOKE_CASES, 1):
        case_root = smoke_root / case["case_id"]
        record = native.run_native_case(
            root, runtime, case_root, dict(case), bwrap_path=bwrap_path,
        )
        records.append({"artifact_root": str(case_root), "private_seed": case["seed"], **record})
        print(f"M22 runtime smoke {ordinal:02d}/{len(SMOKE_CASES)} PASS {case['case_id']}", flush=True)
    return records


def run(root: pathlib.Path, artifact_root: pathlib.Path, evidence_path: pathlib.Path, *, jobs: int,
        bwrap_path: pathlib.Path, artifact_context: ArtifactContext | None = None) -> dict[str, Any]:
    root, artifact_root, evidence_path = root.resolve(), artifact_root.resolve(), evidence_path.resolve()
    context = artifact_context
    require(context is not None and context.is_live, "M22 runtime preparation requires one live artifact context")
    require(jobs >= 1, "build jobs must be positive")
    bwrap = preflight_bwrap(bwrap_path)
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "retained artifact root must be new")
    require(not evidence_path.exists() and not evidence_path.is_symlink(), "runtime evidence output must be new")
    require(git(root, "status", "--porcelain") == "", "repository must be clean before runtime preparation")
    repository = {"commit": git(root, "rev-parse", "HEAD"), "tree": git(root, "rev-parse", "HEAD^{tree}")}
    m21_config = load(root / M21_SOURCE)
    m20_source.validate(root, artifact_context=context)
    m21_source.validate(root, artifact_context=context)
    base_source = context.artifact_set("v2-m21-broad-a") / "source"
    patch = (root / PATCH).resolve()
    require(patch.is_file() and not patch.is_symlink(), "M22 cumulative patch is unavailable")
    artifact_root.mkdir(mode=0o700)
    source_path, build_path = artifact_root / "source", artifact_root / "build-final"
    print("M22 runtime source preparation", flush=True)
    source = prepare_source(base_source, source_path, patch, m21_config["source"]["commit"])
    print("M22 runtime configure/build/CTest", flush=True)
    open_gfx_source = context.artifact_set("v2-m21-broad-a") / "build-broad" / "baseset" / \
        pathlib.PurePosixPath(m21_config["build"]["open_gfx"]["path"]).name
    build, open_gfx = configure_and_build(source_path, build_path, artifact_root, jobs, open_gfx_source,
                                          m21_config["build"]["open_gfx"]["sha256"])
    print("M22 runtime asset staging", flush=True)
    runtime_assets = stage_runtime(root, artifact_root, build_path, context, open_gfx)
    executable = file_record(build_path / "openttd")
    runtime = native.RuntimePaths(
        executable=pathlib.Path(executable["path"]), opengfx=pathlib.Path(runtime_assets["open_gfx"]["path"]),
        base_config=pathlib.Path(runtime_assets["configs"]["base"]["path"]),
        content_config=pathlib.Path(runtime_assets["configs"]["content"]["path"]),
        gamescript_config=pathlib.Path(runtime_assets["configs"]["gamescript"]["path"]), source_tree=source["tree"],
    )
    print("M22 runtime representative native smokes", flush=True)
    smokes = run_smokes(root, artifact_root, runtime, bwrap_path=bwrap)
    contract = load(root / LEARNING_CONTRACT)
    evidence = {
        "base": {"commit": m21_config["source"]["commit"], "source_record_sha256": sha256(root / M21_SOURCE),
                 "tree": m21_config["source"]["tree"]},
        "build": build, "executable": executable,
        "final_boundary": {"expected_manifest_sha256": contract["identities"]["final_evaluation_manifest_sha256"],
                           "manifest_executions": 0, "manifest_opened": False},
        "patch": {"path": str(PATCH), "sha256": sha256(patch), "touched_files": list(TOUCHED)},
        "prerequisites": {"m20_source_record_sha256": sha256(root / M20_SOURCE),
                          "m21_source_record_sha256": sha256(root / M21_SOURCE)},
        "repository": repository, "retained_artifact": str(artifact_root), "runtime": runtime_assets,
        "schema_version": "openttd-rl-v2-m22-final-runtime-source-1", "smokes": smokes,
        "source": source, "status": "PASS",
    }
    try:
        jsonschema.Draft202012Validator(load(root / SCHEMA)).validate(evidence)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M22RuntimePreparationError(f"generated runtime evidence schema failed at {where}: {exc.message}") from exc
    write_new(evidence_path, evidence)
    print(f"V2_M22_FINAL_RUNTIME_PREP=PASS source={source['tree']} smokes={len(smokes)} ctests=98", flush=True)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--evidence", type=pathlib.Path, required=True)
    parser.add_argument("--jobs", type=int, default=max(1, min(8, os.cpu_count() or 1)))
    parser.add_argument("--bwrap", type=pathlib.Path, required=True,
                        help="absolute Bubblewrap executable path for native smoke isolation")
    parser.add_argument("--input-artifact-root", type=pathlib.Path,
                        help="absolute common root containing the accepted M20 and M21 logical artifact sets")
    args = parser.parse_args()
    try:
        input_root = resolve_artifact_root(args.input_artifact_root)
        context = None if input_root is None else ArtifactContext.live(input_root)
        run(
            args.root, args.artifact_root, args.evidence, jobs=args.jobs,
            bwrap_path=args.bwrap, artifact_context=context,
        )
        return 0
    except (M22RuntimePreparationError, native.M22FinalNativeError, m20_source.M20SourceError,
            m21_source.M21SourceError, ArtifactContextError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError,
            subprocess.SubprocessError) as exc:
        print(f"V2_M22_FINAL_RUNTIME_PREP=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
