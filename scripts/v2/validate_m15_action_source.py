#!/usr/bin/env python3
"""Validate the exact M15 hierarchical-action source delta and retained build."""

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


CONFIG = pathlib.Path("config/v2/m15-action-source.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m15-action-source.schema.json")
BASE_LOGICAL_SET = "v2-m15-observation-a"
RESULT_LOGICAL_SET = "v2-m15-action-a"
LIVE_CONSUMER = "m15-action-source"
EXPECTED_FILES = [
    "src/CMakeLists.txt", "src/openttd.cpp", "src/rl_v2_action.cpp", "src/rl_v2_action.h",
    "src/rl_v2_environment.cpp", "src/rl_v2_environment.h", "src/rl_v2_observation.cpp", "src/rl_v2_observation.h",
]
FORBIDDEN_V1_FILES = {
    "src/rl_action.cpp", "src/rl_action.h", "src/rl_bridge.cpp", "src/rl_bridge.h",
    "src/rl_environment.cpp", "src/rl_environment.h", "src/rl_neural_agent.cpp", "src/rl_neural_agent.h",
    "src/rl_observation.cpp", "src/rl_observation.h", "src/rl_reward.cpp", "src/rl_reward.h",
}


class M15ActionSourceError(ValueError):
    """The M15 hierarchical-action source or build evidence is inconsistent."""


@dataclass(frozen=True)
class M15ActionSourceSummary:
    files: int
    result_tree: str
    live_source: bool
    live_build: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15ActionSourceError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15ActionSourceError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15ActionSourceError(f"cannot hash {path}: {exc}") from exc


def git(repository: pathlib.Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(repository), *arguments], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
        "M15 action recorded build root is not an absolute normalized POSIX path",
    )
    require(path.name == RESULT_LOGICAL_SET, "M15 action logical artifact set drifted")
    return path.name


def _requirements(config: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    result_set = _recorded_result_set(config)
    executable = config["build"]["executable"]
    return (
        ArtifactRequirement(BASE_LOGICAL_SET, "source", "directory", LIVE_CONSUMER),
        ArtifactRequirement(BASE_LOGICAL_SET, "source/.git", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, "source", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, "source/.git", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, executable["path"], "file", LIVE_CONSUMER, executable["sha256"]),
    )


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    return _requirements(load_json(root / CONFIG))


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, schema_path: pathlib.Path | None = None, *, artifact_context: ArtifactContext | None = None) -> M15ActionSourceSummary:
    context = artifact_context or ArtifactContext.offline()
    repository_config = config_path is None
    root = root.resolve()
    config_path, schema_path = config_path or root / CONFIG, schema_path or root / SCHEMA
    config, schema = load_json(config_path), load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(config)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15ActionSourceError(f"M15 action source schema failed at {location}: {exc.message}") from exc
    require(config["schema_sha256"] == sha256_file(schema_path), "M15 action source schema SHA-256 mismatch")
    require(config["base"]["observation_source_evidence_sha256"] == sha256_file(root / "config/v2/m15-observation-source.json"), "M15 observation source evidence identity drifted")
    patch = root / config["patch"]["path"]
    require(patch.is_file() and not patch.is_symlink(), "M15 action patch is missing or a symlink")
    require(sha256_file(patch) == config["patch"]["sha256"], "M15 action patch SHA-256 mismatch")
    patch_text = patch.read_text(encoding="utf-8")
    touched = re.findall(r"^diff --git a/(\S+) b/\S+$", patch_text, re.MULTILINE)
    require(touched == EXPECTED_FILES, f"M15 action patch file scope drifted: {touched}")
    require(not (set(touched) & FORBIDDEN_V1_FILES), "M15 action patch modifies a frozen V1 RL source file")
    for token in ("CANDIDATE_CAPACITY = 4096", "CANDIDATE_BYTES = 790528", "FAMILY_QUOTAS", "EnumerateCandidates", "NativeStateSha256", "STALE_TOKEN", "-J"):
        require(token in patch_text, f"M15 action patch lost required token: {token}")

    _recorded_result_set(config)
    if context.is_live:
        requirements = required_live_inputs(root) if repository_config else _requirements(config)
        context.preflight(requirements)
        live_paths = {
            (requirement.logical_set, requirement.relative_path): context.resolve(requirement)
            for requirement in requirements
        }
        base_source = live_paths[(BASE_LOGICAL_SET, "source")]
        result_source = live_paths[(RESULT_LOGICAL_SET, "source")]
        executable = live_paths[(RESULT_LOGICAL_SET, config["build"]["executable"]["path"])]
        require(git(base_source, "status", "--porcelain") == "", "M15 action base source is dirty")
        require(git(base_source, "rev-parse", "HEAD") == config["base"]["commit"], "M15 action base commit drifted")
        require(git(base_source, "rev-parse", "HEAD^{tree}") == config["base"]["tree"], "M15 action base tree drifted")
        with tempfile.TemporaryDirectory(prefix="openttd-rl-v2-m15-action-source-") as raw:
            target = pathlib.Path(raw) / "source"
            cloned = subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(base_source), str(target)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            require(cloned.returncode == 0, f"cannot clone action base source: {cloned.stderr.strip()}")
            checked = subprocess.run(["git", "-C", str(target), "apply", "--check", "--whitespace=error-all", str(patch)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            require(checked.returncode == 0 and not re.search(r"\b(?:offset|fuzz|warning)\b", checked.stdout + checked.stderr, re.I), "M15 action patch does not apply exactly")
            applied = subprocess.run(["git", "-C", str(target), "apply", "--index", "--whitespace=error-all", str(patch)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            require(applied.returncode == 0, f"cannot apply M15 action patch: {applied.stderr.strip()}")
            require(git(target, "write-tree") == config["result"]["tree"], "M15 action result tree drifted")
        require(git(result_source, "status", "--porcelain") == "", "M15 action retained source is dirty")
        require(git(result_source, "rev-parse", "HEAD") == config["result"]["commit"], "M15 action retained commit drifted")
        require(git(result_source, "rev-parse", "HEAD^{tree}") == config["result"]["tree"], "M15 action retained tree drifted")
        require(executable.is_file() and not executable.is_symlink(), "M15 action executable is missing or a symlink")
        require(executable.stat().st_size == config["build"]["executable"]["size"], "M15 action executable size drifted")
        require(sha256_file(executable) == config["build"]["executable"]["sha256"], "M15 action executable SHA-256 drifted")
    return M15ActionSourceSummary(len(touched), config["result"]["tree"], context.is_live, context.is_live)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    add_artifact_root_argument(parser)
    args = parser.parse_args(argv)
    try:
        context = ArtifactContext.offline() if args.artifact_root is None else ArtifactContext.live(args.artifact_root)
        summary = validate(args.root, args.config, args.schema, artifact_context=context)
        print(f"V2_M15_ACTION_SOURCE=PASS files={summary.files} result_tree={summary.result_tree} live_source={str(summary.live_source).lower()} live_build={str(summary.live_build).lower()}")
        return 0
    except (M15ActionSourceError, ArtifactContextError, OSError) as exc:
        print(f"V2_M15_ACTION_SOURCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
