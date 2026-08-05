#!/usr/bin/env python3
"""Validate the exact M15 passenger-service source delta and retained build."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
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
from source_context import SourceContextError, run_git


CONFIG = pathlib.Path("config/v2/m15-competence-source.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m15-competence-source.schema.json")
BASE_LOGICAL_SET = "v2-m15-episode-a"
RESULT_LOGICAL_SET = "v2-m15-competence-a"
LIVE_CONSUMER = "m15-competence-source"
EXPECTED_FILES = ["src/rl_v2_action.cpp"]
FORBIDDEN_V1_FILES = {
    "src/rl_action.cpp", "src/rl_action.h", "src/rl_bridge.cpp", "src/rl_bridge.h",
    "src/rl_environment.cpp", "src/rl_environment.h", "src/rl_neural_agent.cpp",
    "src/rl_neural_agent.h", "src/rl_observation.cpp", "src/rl_observation.h",
    "src/rl_reward.cpp", "src/rl_reward.h",
}


class M15CompetenceSourceError(ValueError):
    """The M15 passenger-service source or build evidence is inconsistent."""


@dataclass(frozen=True)
class M15CompetenceSourceSummary:
    files: int
    result_tree: str
    live_source: bool
    live_build: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15CompetenceSourceError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15CompetenceSourceError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15CompetenceSourceError(f"cannot hash {path}: {exc}") from exc


def invoke_git(*arguments: str, repository: pathlib.Path | None = None):
    try:
        return run_git(*arguments, repository=repository)
    except SourceContextError as exc:
        raise M15CompetenceSourceError(
            f"git {' '.join(arguments)} failed: {exc}"
        ) from exc


def git(repository: pathlib.Path, *arguments: str) -> str:
    result = invoke_git(*arguments, repository=repository)
    detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
    require(result.returncode == 0, f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout.decode("utf-8", errors="replace").strip()


def _recorded_result_set(config: dict[str, Any]) -> str:
    recorded = config["build"]["artifact_root"]
    path = pathlib.PurePosixPath(recorded)
    require(
        isinstance(recorded, str)
        and recorded.startswith("/")
        and not recorded.startswith("//")
        and str(path) == recorded
        and all(part not in {"", ".", ".."} for part in path.parts[1:]),
        "M15 competence recorded build root is not an absolute normalized POSIX path",
    )
    require(path.name == RESULT_LOGICAL_SET, "M15 competence logical artifact set drifted")
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


def validate(
    root: pathlib.Path,
    config_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_context: ArtifactContext | None = None,
) -> M15CompetenceSourceSummary:
    context = artifact_context or ArtifactContext.offline()
    repository_config = config_path is None
    root = root.resolve()
    config_path, schema_path = config_path or root / CONFIG, schema_path or root / SCHEMA
    config, schema = load_json(config_path), load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(config)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15CompetenceSourceError(f"M15 competence source schema failed at {location}: {exc.message}") from exc
    require(config["schema_sha256"] == sha256_file(schema_path), "M15 competence source schema SHA-256 mismatch")
    require(config["base"]["episode_source_evidence_sha256"] == sha256_file(root / "config/v2/m15-episode-source.json"), "M15 episode source evidence identity drifted")
    patch = root / config["patch"]["path"]
    require(patch.is_file() and not patch.is_symlink(), "M15 competence patch is missing or a symlink")
    require(sha256_file(patch) == config["patch"]["sha256"], "M15 competence patch SHA-256 mismatch")
    patch_text = patch.read_text(encoding="utf-8")
    touched = re.findall(r"^diff --git a/(\S+) b/\S+$", patch_text, re.MULTILINE)
    require(touched == EXPECTED_FILES, f"M15 competence patch file scope drifted: {touched}")
    require(not (set(touched) & FORBIDDEN_V1_FILES), "M15 competence patch modifies a frozen V1 RL source file")
    for token in ("RunPassengerService", "FindServiceSite", "StateGameLoop", "CMD_BUILD_VEHICLE", "delivered_passengers", 'operation == \"SERVICE\"'):
        require(token in patch_text, f"M15 competence patch lost required token: {token}")

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
        require(git(base_source, "status", "--porcelain") == "", "M15 competence base source is dirty")
        require(git(base_source, "rev-parse", "HEAD") == config["base"]["commit"], "M15 competence base commit drifted")
        require(git(base_source, "rev-parse", "HEAD^{tree}") == config["base"]["tree"], "M15 competence base tree drifted")
        with tempfile.TemporaryDirectory(prefix="openttd-rl-v2-m15-competence-source-") as raw:
            target = pathlib.Path(raw) / "source"
            cloned = invoke_git("clone", "-q", "--no-hardlinks", str(base_source), str(target))
            clone_detail = cloned.stderr.decode("utf-8", errors="replace").strip()
            require(cloned.returncode == 0, f"cannot clone competence base source: {clone_detail}")
            checked = invoke_git("apply", "--check", "--whitespace=error-all", str(patch), repository=target)
            check_output = (checked.stdout + checked.stderr).decode("utf-8", errors="replace")
            require(checked.returncode == 0 and not re.search(r"\b(?:offset|fuzz|warning)\b", check_output, re.I), "M15 competence patch does not apply exactly")
            applied = invoke_git("apply", "--index", "--whitespace=error-all", str(patch), repository=target)
            apply_detail = applied.stderr.decode("utf-8", errors="replace").strip()
            require(applied.returncode == 0, f"cannot apply M15 competence patch: {apply_detail}")
            require(git(target, "write-tree") == config["result"]["tree"], "M15 competence result tree drifted")
        require(git(result_source, "status", "--porcelain") == "", "M15 competence retained source is dirty")
        require(git(result_source, "rev-parse", "HEAD") == config["result"]["commit"], "M15 competence retained commit drifted")
        require(git(result_source, "rev-parse", "HEAD^{tree}") == config["result"]["tree"], "M15 competence retained tree drifted")
        require(executable.is_file() and not executable.is_symlink(), "M15 competence executable is missing or a symlink")
        require(executable.stat().st_size == config["build"]["executable"]["size"], "M15 competence executable size drifted")
        require(sha256_file(executable) == config["build"]["executable"]["sha256"], "M15 competence executable SHA-256 drifted")
    return M15CompetenceSourceSummary(len(touched), config["result"]["tree"], context.is_live, context.is_live)


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
        print(f"V2_M15_COMPETENCE_SOURCE=PASS files={summary.files} result_tree={summary.result_tree} live_source={str(summary.live_source).lower()} live_build={str(summary.live_build).lower()}")
        return 0
    except (M15CompetenceSourceError, ArtifactContextError, OSError) as exc:
        print(f"V2_M15_COMPETENCE_SOURCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
