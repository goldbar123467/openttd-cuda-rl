#!/usr/bin/env python3
"""Validate the retained native M20 competition source, patch, runtime, and executable."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import tempfile
from typing import Any

import jsonschema

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    add_artifact_root_argument,
    resolve_artifact_root,
)
from source_context import SourceContextError, run_git


CONFIG = pathlib.Path("config/v2/m20-competition-source.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m20-competition-source.schema.json")
TOUCHED = ["src/CMakeLists.txt", "src/openttd.cpp", "src/rl_v2_competition.cpp", "src/rl_v2_competition.h"]
BASE_LOGICAL_SET = "v2-m19-air-a"
RESULT_LOGICAL_SET = "v2-m20-competition-a"
LIVE_CONSUMER = "m20-competition-source"


class M20SourceError(ValueError):
    """M20 native source evidence is inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M20SourceError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke_git(*arguments: str, repository: pathlib.Path | None = None):
    try:
        return run_git(*arguments, repository=repository)
    except SourceContextError as exc:
        raise M20SourceError(f"git {' '.join(arguments)} failed: {exc}") from exc


def git(repository: pathlib.Path, *arguments: str) -> str:
    result = invoke_git(*arguments, repository=repository)
    detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
    require(result.returncode == 0, f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout.decode("utf-8", errors="replace").strip()


def schema_validate(value: dict[str, Any], schema: dict[str, Any]) -> None:
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M20SourceError(f"source schema failed at {where}: {exc.message}") from exc


def _recorded_relative(recorded_root: str, recorded_path: str, *, label: str) -> str:
    root = pathlib.PurePosixPath(recorded_root)
    path = pathlib.PurePosixPath(recorded_path)
    require(isinstance(recorded_path, str) and recorded_path.startswith("/") and not recorded_path.startswith("//") and
            str(path) == recorded_path and all(part not in {"", ".", ".."} for part in path.parts[1:]),
            f"recorded {label} path is not an absolute normalized POSIX path")
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise M20SourceError(f"recorded {label} path escaped retained artifact") from exc
    require(str(relative) != ".", f"recorded {label} path must be below retained artifact")
    return str(relative)


def _recorded_result_set(config: dict[str, Any]) -> str:
    recorded = config["retained_artifact"]
    path = pathlib.PurePosixPath(recorded)
    require(isinstance(recorded, str) and recorded.startswith("/") and not recorded.startswith("//") and
            str(path) == recorded and all(part not in {"", ".", ".."} for part in path.parts[1:]),
            "recorded retained artifact is not an absolute normalized POSIX path")
    require(path.name == RESULT_LOGICAL_SET, "retained artifact logical set drifted")
    require(_recorded_relative(recorded, config["source"]["path"], label="source") == "source", "recorded source path drifted")
    require(_recorded_relative(recorded, config["executable"]["path"], label="executable") == "build-competition/openttd", "recorded executable path drifted")
    require(_recorded_relative(recorded, config["build"]["open_gfx"]["path"], label="OpenGFX") == "build-competition/baseset/opengfx-8.0.tar", "recorded OpenGFX path drifted")
    require(_recorded_relative(recorded, config["runtime"]["config"]["path"], label="runtime config") == "openttd.cfg", "recorded runtime config path drifted")
    return path.name


def _content_records(root: pathlib.Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    content = load(root / config["runtime"]["content_manifest"])
    return [content["base_graphics"], *content["ai_archives"], *content["libraries"]]


def _requirements(root: pathlib.Path, config: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    result_set = _recorded_result_set(config)
    recorded_root = config["retained_artifact"]
    requirements = [
        ArtifactRequirement(BASE_LOGICAL_SET, "source", "directory", LIVE_CONSUMER),
        ArtifactRequirement(BASE_LOGICAL_SET, "source/.git", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, "source", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, "source/.git", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, "build-competition/openttd", "file", LIVE_CONSUMER, config["executable"]["sha256"]),
        ArtifactRequirement(result_set, "build-competition/baseset/opengfx-8.0.tar", "file", LIVE_CONSUMER, config["build"]["open_gfx"]["sha256"]),
        ArtifactRequirement(result_set, "openttd.cfg", "file", LIVE_CONSUMER, config["runtime"]["config"]["sha256"]),
    ]
    for record in _content_records(root, config):
        requirement = ArtifactRequirement(
            result_set,
            _recorded_relative(recorded_root, record["path"], label="content"),
            "file",
            LIVE_CONSUMER,
            record["sha256"],
        )
        if requirement not in requirements:
            requirements.append(requirement)
    require(len(requirements) == len(set(requirements)), "source/runtime inventory contains duplicates")
    return tuple(requirements)


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    return _requirements(root, load(root / CONFIG))


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, schema_path: pathlib.Path | None = None,
             *, artifact_context: ArtifactContext | None = None) -> dict[str, Any]:
    context = artifact_context or ArtifactContext.offline()
    repository_config = config_path is None
    root = root.resolve()
    config = load(config_path or root / CONFIG)
    schema_validate(config, load(schema_path or root / SCHEMA))
    patch = root / config["patch"]["path"]
    require(patch.is_file() and not patch.is_symlink() and sha256(patch) == config["patch"]["sha256"], "patch identity drifted")
    text = patch.read_text(encoding="utf-8")
    touched = re.findall(r"^diff --git a/(\S+) b/\S+$", text, re.MULTILINE)
    require(touched == TOUCHED, f"patch scope drifted: {touched}")
    for token in (
        "RunRlV2CompetitionQualification", "DoStartupNewCompany", "AIConfig::GetConfig", "CMD_BUILD_AIRPORT",
        "CMD_BUILD_VEHICLE", "CMD_INSERT_ORDER", "CMD_COMPANY_CTRL", "CMD_CREATE_SUBSIDY", "CMD_BUY_COMPANY",
        "SaveOrLoad", "StateGameLoop", "PublicCompany", "company_value_difference", "save_load_public_exact",
        "policy_input_fields", "privileged_inputs", "competition_manifest_sha256", "content_manifest_sha256",
    ):
        require(token in text, f"patch lost required token: {token}")
    for forbidden in ("std::system(", "popen(", "fork(", "execve(", "mock_score", "fake_company"):
        require(forbidden not in text, f"patch contains forbidden implementation path: {forbidden}")
    content_files = _content_records(root, config)
    require(config["build"]["upstream_ctest"] == {"passed": 98, "total": 98}, "upstream CTest result drifted")
    requirements = _requirements(root, config)
    if context.is_live:
        requirements = required_live_inputs(root) if repository_config else requirements
        context.preflight(requirements)
        live_paths = {(item.logical_set, item.relative_path): context.resolve(item) for item in requirements}
        base_source = live_paths[(BASE_LOGICAL_SET, "source")]
        result_source = live_paths[(RESULT_LOGICAL_SET, "source")]
        executable = live_paths[(RESULT_LOGICAL_SET, "build-competition/openttd")]
        opengfx = live_paths[(RESULT_LOGICAL_SET, "build-competition/baseset/opengfx-8.0.tar")]
        runtime_config = live_paths[(RESULT_LOGICAL_SET, "openttd.cfg")]
        require(git(base_source, "status", "--porcelain") == "", "base source is dirty")
        require(git(base_source, "rev-parse", "HEAD") == config["base"]["commit"], "base commit drifted")
        require(git(base_source, "rev-parse", "HEAD^{tree}") == config["base"]["tree"], "base tree drifted")
        with tempfile.TemporaryDirectory(prefix="openttd-rl-v2-m20-source-") as raw:
            target = pathlib.Path(raw) / "source"
            cloned = invoke_git("clone", "-q", "--no-hardlinks", str(base_source), str(target))
            require(cloned.returncode == 0, f"cannot clone base source: {cloned.stderr.decode('utf-8', errors='replace').strip()}")
            checked = invoke_git("apply", "--check", "--whitespace=error-all", str(patch), repository=target)
            check_output = (checked.stdout + checked.stderr).decode("utf-8", errors="replace")
            require(checked.returncode == 0 and not re.search(r"\b(?:offset|fuzz|warning)\b", check_output, re.I), "patch does not apply exactly to the M19 base")
            applied = invoke_git("apply", "--index", "--whitespace=error-all", str(patch), repository=target)
            require(applied.returncode == 0, f"cannot apply patch: {applied.stderr.decode('utf-8', errors='replace').strip()}")
            require(git(target, "write-tree") == config["source"]["tree"], "composed source tree drifted")
        require(git(result_source, "status", "--porcelain") == "", "retained source is dirty")
        require(git(result_source, "rev-parse", "HEAD") == config["source"]["commit"], "retained source commit drifted")
        require(git(result_source, "rev-parse", "HEAD^{tree}") == config["source"]["tree"], "retained source tree drifted")
        require(executable.stat().st_size == config["executable"]["bytes"] and sha256(executable) == config["executable"]["sha256"],
                "executable identity drifted")
        require(runtime_config.is_file() and sha256(runtime_config) == config["runtime"]["config"]["sha256"], "runtime config drifted")
        require(sha256(opengfx) == config["build"]["open_gfx"]["sha256"], "OpenGFX identity drifted")
        for record in content_files:
            relative = _recorded_relative(config["retained_artifact"], record["path"], label="content")
            path = live_paths[(RESULT_LOGICAL_SET, relative)]
            require(sha256(path) == record["sha256"], f"content identity drifted: {path}")
    return {"files": len(touched), "content_files": len(content_files), "tree": config["source"]["tree"], "live": context.is_live}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    add_artifact_root_argument(parser)
    args = parser.parse_args(argv)
    try:
        artifact_root = resolve_artifact_root(args.artifact_root)
        context = ArtifactContext.offline() if artifact_root is None else ArtifactContext.live(artifact_root)
        summary = validate(args.root, args.config, args.schema, artifact_context=context)
        print(f"V2_M20_COMPETITION_SOURCE=PASS files={summary['files']} content_files={summary['content_files']} "
              f"tree={summary['tree']} live={str(summary['live']).lower()}")
        return 0
    except (M20SourceError, SourceContextError, ArtifactContextError, OSError, json.JSONDecodeError) as exc:
        print(f"V2_M20_COMPETITION_SOURCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
