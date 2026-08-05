#!/usr/bin/env python3
"""Validate the exact M15 native OpenTTD source delta and retained build evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any

import jsonschema

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    add_artifact_root_argument,
)


CONFIG = pathlib.Path("config/v2/m15-native-source.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m15-native-source.schema.json")
BASE_LOGICAL_SET = "m12-release-final-a"
BASE_SOURCE_RELATIVE = "composed-source/openttd"
RESULT_LOGICAL_SET = "v2-m15-native-a"
LIVE_CONSUMER = "m15-native-source"
EXPECTED_FILES = [
    "src/CMakeLists.txt",
    "src/openttd.cpp",
    "src/rl_v2_environment.cpp",
    "src/rl_v2_environment.h",
]
FORBIDDEN_V1_FILES = {
    "src/rl_action.cpp", "src/rl_action.h", "src/rl_bridge.cpp", "src/rl_bridge.h",
    "src/rl_environment.cpp", "src/rl_environment.h", "src/rl_neural_agent.cpp",
    "src/rl_neural_agent.h", "src/rl_observation.cpp", "src/rl_observation.h",
    "src/rl_reward.cpp", "src/rl_reward.h",
}


class M15NativeSourceError(ValueError):
    """The M15 source delta or build evidence is inconsistent."""


@dataclass(frozen=True)
class M15NativeSourceSummary:
    patches: int
    files: int
    result_tree: str
    live_source: bool
    live_build: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15NativeSourceError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15NativeSourceError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15NativeSourceError(f"cannot hash {path}: {exc}") from exc


def git(repository: pathlib.Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    require(result.returncode == 0, f"git {' '.join(arguments)} failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def _recorded_result_set(config: dict[str, Any]) -> str:
    recorded = config["build"]["artifact_root"]
    path = pathlib.PurePosixPath(recorded)
    require(
        isinstance(recorded, str)
        and recorded.startswith("/")
        and not recorded.startswith("//")
        and str(path) == recorded
        and all(part not in {"", ".", ".."} for part in path.parts[1:]),
        "M15 native recorded build root is not an absolute normalized POSIX path",
    )
    require(path.name == RESULT_LOGICAL_SET, "M15 native logical artifact set drifted")
    return path.name


def _requirements(config: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    result_set = _recorded_result_set(config)
    executable = config["build"]["executable"]
    return (
        ArtifactRequirement(BASE_LOGICAL_SET, BASE_SOURCE_RELATIVE, "directory", LIVE_CONSUMER),
        ArtifactRequirement(BASE_LOGICAL_SET, f"{BASE_SOURCE_RELATIVE}/.git", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, "source", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, "source/.git", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, executable["path"], "file", LIVE_CONSUMER, executable["sha256"]),
    )


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    return _requirements(load_json(root / CONFIG))


def validate(
    root: pathlib.Path,
    config_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_context: ArtifactContext | None = None,
) -> M15NativeSourceSummary:
    context = artifact_context or ArtifactContext.offline()
    repository_config = config_path is None
    root = root.resolve()
    config_path = config_path or root / CONFIG
    schema_path = schema_path or root / SCHEMA
    config = load_json(config_path)
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(config)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15NativeSourceError(f"M15 native source schema failed at {location}: {exc.message}") from exc
    require(config["schema_sha256"] == sha256_file(schema_path), "M15 native source schema SHA-256 mismatch")

    series = root / config["patch_series"]["series"]
    require(series.is_file() and not series.is_symlink(), "M15 patch series is missing or a symlink")
    require(sha256_file(series) == config["patch_series"]["series_sha256"], "M15 patch series SHA-256 mismatch")
    names = [line.strip() for line in series.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    locked_names = [item["name"] for item in config["patch_series"]["patches"]]
    require(names == locked_names, "M15 patch series order/inventory drifted")
    patch_directory = root / config["patch_series"]["directory"]
    present = sorted(path.name for path in patch_directory.glob("*.patch") if path.is_file())
    require(present == names, "M15 listed/present patch inventory drifted")

    touched: list[str] = []
    for lock in config["patch_series"]["patches"]:
        patch = patch_directory / lock["name"]
        require(sha256_file(patch) == lock["sha256"], f"M15 patch SHA-256 mismatch: {patch.name}")
        text = patch.read_text(encoding="utf-8")
        touched.extend(re.findall(r"^diff --git a/(\S+) b/\S+$", text, re.MULTILINE))
        require("M15 scalable reset" in text and "RunRlV2ScalableReset" in text, "M15 patch lost the scalable reset entrypoint")
        require("b7a4ba1fc20507b77e2ef2ac01347665526cdbd4fc3e036587df5bdb3666d271" in text, "M15 patch lost the frozen contract identity")
        require("MAXIMUM_GENERATED_TILES = 1U << 20" in text, "M15 patch lost native preflight")
    require(touched == EXPECTED_FILES, f"M15 patch file scope drifted: {touched}")
    require(not (set(touched) & FORBIDDEN_V1_FILES), "M15 patch modifies a frozen V1 RL source file")

    _recorded_result_set(config)
    if context.is_live:
        requirements = required_live_inputs(root) if repository_config else _requirements(config)
        context.preflight(requirements)
        live_paths = {
            (requirement.logical_set, requirement.relative_path): context.resolve(requirement)
            for requirement in requirements
        }
        base_source = live_paths[(BASE_LOGICAL_SET, BASE_SOURCE_RELATIVE)]
        result_source = live_paths[(RESULT_LOGICAL_SET, "source")]
        executable = live_paths[(RESULT_LOGICAL_SET, config["build"]["executable"]["path"])]
        require(git(base_source, "status", "--porcelain") == "", "M15 base source is dirty")
        require(git(base_source, "rev-parse", "HEAD") == config["base"]["commit"], "M15 base source commit drifted")
        require(git(base_source, "rev-parse", "HEAD^{tree}") == config["base"]["tree"], "M15 base source tree drifted")
        with tempfile.TemporaryDirectory(prefix="openttd-rl-v2-m15-source-") as raw:
            target = pathlib.Path(raw) / "source"
            result = subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(base_source), str(target)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            require(result.returncode == 0, f"cannot clone M15 base source: {result.stderr.strip()}")
            for name in names:
                patch = patch_directory / name
                check = subprocess.run(["git", "-C", str(target), "apply", "--check", "--whitespace=error-all", str(patch)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                require(check.returncode == 0 and not re.search(r"\b(?:offset|fuzz|warning)\b", check.stdout + check.stderr, re.I), f"M15 patch does not apply exactly: {name}")
                applied = subprocess.run(["git", "-C", str(target), "apply", "--index", "--whitespace=error-all", str(patch)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                require(applied.returncode == 0, f"cannot apply M15 patch: {name}: {applied.stderr.strip()}")
            require(git(target, "write-tree") == config["result"]["tree"], "M15 composed result tree drifted")
        require(git(result_source, "status", "--porcelain") == "", "M15 retained source is dirty")
        require(git(result_source, "rev-parse", "HEAD^{tree}") == config["result"]["tree"], "M15 retained result tree drifted")
        require(executable.is_file() and not executable.is_symlink(), "M15 native executable is missing or a symlink")
        require(executable.stat().st_size == config["build"]["executable"]["size"], "M15 native executable size drifted")
        require(sha256_file(executable) == config["build"]["executable"]["sha256"], "M15 native executable SHA-256 drifted")

    return M15NativeSourceSummary(len(names), len(touched), config["result"]["tree"], context.is_live, context.is_live)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    add_artifact_root_argument(parser)
    args = parser.parse_args(argv)
    try:
        context = (
            ArtifactContext.offline()
            if args.artifact_root is None
            else ArtifactContext.live(args.artifact_root)
        )
        summary = validate(args.root, args.config, args.schema, artifact_context=context)
        print(f"V2_M15_NATIVE_SOURCE=PASS patches={summary.patches} files={summary.files} result_tree={summary.result_tree} live_source={str(summary.live_source).lower()} live_build={str(summary.live_build).lower()}")
        return 0
    except (M15NativeSourceError, ArtifactContextError, OSError) as exc:
        print(f"V2_M15_NATIVE_SOURCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
