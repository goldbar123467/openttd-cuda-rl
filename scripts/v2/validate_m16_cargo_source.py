#!/usr/bin/env python3
"""Validate the retained native M16 cargo source delta, patch, content, and executable."""

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
)
from source_context import SourceContextError, run_git


CONFIG = pathlib.Path("config/v2/m16-cargo-source.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m16-cargo-source.schema.json")
TOUCHED = ["src/CMakeLists.txt", "src/economy.cpp", "src/economy_func.h", "src/openttd.cpp", "src/rl_v2_cargo.cpp", "src/rl_v2_cargo.h", "src/station_cmd.cpp", "src/station_func.h"]
BASE_LOGICAL_SET = "v2-m15-competence-a"
RESULT_LOGICAL_SET = "v2-m16-cargo-a"
LIVE_CONSUMER = "m16-cargo-source"


class M16SourceError(ValueError):
    """M16 native source evidence is inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M16SourceError(message)


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
        raise M16SourceError(f"git {' '.join(arguments)} failed: {exc}") from exc


def git(repository: pathlib.Path, *arguments: str) -> str:
    result = invoke_git(*arguments, repository=repository)
    detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
    require(result.returncode == 0, f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout.decode("utf-8", errors="replace").strip()


def _recorded_result_set(config: dict[str, Any]) -> str:
    recorded = config["retained_artifact"]
    path = pathlib.PurePosixPath(recorded)
    require(
        isinstance(recorded, str)
        and recorded.startswith("/")
        and not recorded.startswith("//")
        and str(path) == recorded
        and all(part not in {"", ".", ".."} for part in path.parts[1:]),
        "recorded retained artifact is not an absolute normalized POSIX path",
    )
    require(path.name == RESULT_LOGICAL_SET, "retained artifact logical set drifted")
    require(config["source"]["path"] == f"{recorded}/source", "recorded source path drifted")
    require(config["executable"]["path"] == f"{recorded}/build/openttd", "recorded executable path drifted")
    require(config["build"]["open_gfx"]["path"] == f"{recorded}/build/baseset/opengfx-8.0.tar", "recorded OpenGFX path drifted")
    return path.name


def _requirements(config: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    result_set = _recorded_result_set(config)
    return (
        ArtifactRequirement(BASE_LOGICAL_SET, "source", "directory", LIVE_CONSUMER),
        ArtifactRequirement(BASE_LOGICAL_SET, "source/.git", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, "source", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, "source/.git", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, "build/openttd", "file", LIVE_CONSUMER, config["executable"]["sha256"]),
        ArtifactRequirement(result_set, "build/baseset/opengfx-8.0.tar", "file", LIVE_CONSUMER, config["build"]["open_gfx"]["sha256"]),
    )


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    return _requirements(load(root / CONFIG))


def validate(
    root: pathlib.Path,
    config_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_context: ArtifactContext | None = None,
) -> dict[str, Any]:
    context = artifact_context or ArtifactContext.offline()
    repository_config = config_path is None
    root = root.resolve()
    config, schema = load(config_path or root / CONFIG), load(schema_path or root / SCHEMA)
    try:
        jsonschema.Draft202012Validator(schema).validate(config)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M16SourceError(f"source schema failed at {where}: {exc.message}") from exc
    patch = root / config["patch"]["path"]
    require(patch.is_file() and not patch.is_symlink() and sha256(patch) == config["patch"]["sha256"], "patch identity drifted")
    text = patch.read_text(encoding="utf-8")
    touched = re.findall(r"^diff --git a/(\S+) b/\S+$", text, re.MULTILINE)
    require(touched == TOUCHED, f"patch scope drifted: {touched}")
    for token in ("RunRlV2CargoQualification", "PayFinalDelivery", "PayTransfer", "ProcessIndustryInputCargo", "CMD_BUILD_ROAD_STOP", "CMD_BUILD_VEHICLE", "OrderUnloadType::Transfer", "RebuildSubsidisedSourceAndDestinationCache"):
        require(token in text, f"patch lost required token: {token}")
    requirements = _requirements(config)
    if context.is_live:
        requirements = required_live_inputs(root) if repository_config else requirements
        context.preflight(requirements)
        live_paths = {(item.logical_set, item.relative_path): context.resolve(item) for item in requirements}
        base_source = live_paths[(BASE_LOGICAL_SET, "source")]
        result_source = live_paths[(RESULT_LOGICAL_SET, "source")]
        executable = live_paths[(RESULT_LOGICAL_SET, "build/openttd")]
        opengfx = live_paths[(RESULT_LOGICAL_SET, "build/baseset/opengfx-8.0.tar")]
        require(git(base_source, "status", "--porcelain") == "", "base source is dirty")
        require(git(base_source, "rev-parse", "HEAD") == config["base"]["commit"], "base commit drifted")
        require(git(base_source, "rev-parse", "HEAD^{tree}") == config["base"]["tree"], "base tree drifted")
        with tempfile.TemporaryDirectory(prefix="openttd-rl-v2-m16-source-") as raw:
            target = pathlib.Path(raw) / "source"
            cloned = invoke_git("clone", "-q", "--no-hardlinks", str(base_source), str(target))
            require(cloned.returncode == 0, f"cannot clone base source: {cloned.stderr.decode('utf-8', errors='replace').strip()}")
            checked = invoke_git("apply", "--check", "--whitespace=error-all", str(patch), repository=target)
            check_output = (checked.stdout + checked.stderr).decode("utf-8", errors="replace")
            require(checked.returncode == 0 and not re.search(r"\b(?:offset|fuzz|warning)\b", check_output, re.I), "patch does not apply exactly to base")
            applied = invoke_git("apply", "--index", "--whitespace=error-all", str(patch), repository=target)
            require(applied.returncode == 0, f"cannot apply patch: {applied.stderr.decode('utf-8', errors='replace').strip()}")
            require(git(target, "write-tree") == config["source"]["tree"], "composed source tree drifted")
        require(git(result_source, "status", "--porcelain") == "", "retained source is dirty")
        require(git(result_source, "rev-parse", "HEAD") == config["source"]["commit"], "retained source commit drifted")
        require(git(result_source, "rev-parse", "HEAD^{tree}") == config["source"]["tree"], "retained source tree drifted")
        require(executable.stat().st_size == config["executable"]["bytes"] and sha256(executable) == config["executable"]["sha256"], "executable identity drifted")
        require(sha256(opengfx) == config["build"]["open_gfx"]["sha256"], "OpenGFX identity drifted")
    return {"files": len(touched), "tree": config["source"]["tree"], "live": context.is_live}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    add_artifact_root_argument(parser)
    args = parser.parse_args(argv)
    try:
        artifact_root = args.artifact_root
        context = ArtifactContext.offline() if artifact_root is None else ArtifactContext.live(artifact_root)
        summary = validate(args.root, args.config, args.schema, artifact_context=context)
        print(f"V2_M16_CARGO_SOURCE=PASS files={summary['files']} tree={summary['tree']} live={str(summary['live']).lower()}")
        return 0
    except (M16SourceError, SourceContextError, ArtifactContextError, OSError, json.JSONDecodeError) as exc:
        print(f"V2_M16_CARGO_SOURCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
