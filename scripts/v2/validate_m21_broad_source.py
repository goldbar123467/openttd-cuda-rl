#!/usr/bin/env python3
"""Validate the M21 contract, coverage, content closure, native source, and runtime identities."""

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
import run_m21_broad_matrix as matrix
from source_context import SourceContextError, run_git


CONFIG = pathlib.Path("config/v2/m21-broad-source.json")
SOURCE_SCHEMA = pathlib.Path("docs/project/schema/v2-m21-broad-source.schema.json")
CONTRACT_SCHEMA = pathlib.Path("docs/project/schema/v2-m21-broad-contract.schema.json")
COVERAGE_SCHEMA = pathlib.Path("docs/project/schema/v2-m21-broad-coverage.schema.json")
TOUCHED = ["src/CMakeLists.txt", "src/openttd.cpp", "src/rl_v2_broad.cpp", "src/rl_v2_broad.h"]
BASE_LOGICAL_SET = "v2-m20-competition-a"
RESULT_LOGICAL_SET = "v2-m21-broad-a"
LIVE_CONSUMER = "m21-broad-source"


class M21SourceError(ValueError):
    """M21 source or contract evidence is inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M21SourceError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schema_validate(value: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M21SourceError(f"{label} schema failed at {where}: {exc.message}") from exc


def invoke_git(*arguments: str, repository: pathlib.Path | None = None):
    try:
        return run_git(*arguments, repository=repository)
    except SourceContextError as exc:
        raise M21SourceError(f"git {' '.join(arguments)} failed: {exc}") from exc


def git(repository: pathlib.Path, *arguments: str) -> str:
    result = invoke_git(*arguments, repository=repository)
    detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
    require(result.returncode == 0, f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout.decode("utf-8", errors="replace").strip()


def _recorded_result_set(source: dict[str, Any]) -> str:
    recorded = source["retained_artifact"]
    path = pathlib.PurePosixPath(recorded)
    require(isinstance(recorded, str) and recorded.startswith("/") and not recorded.startswith("//") and
            str(path) == recorded and all(part not in {"", ".", ".."} for part in path.parts[1:]),
            "recorded retained artifact is not an absolute normalized POSIX path")
    require(path.name == RESULT_LOGICAL_SET, "retained artifact logical set drifted")
    require(source["source"]["path"] == f"{recorded}/source", "recorded source path drifted")
    return path.name


def _requirements(root: pathlib.Path, source: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    result_set = _recorded_result_set(source)
    requirements = (
        ArtifactRequirement(BASE_LOGICAL_SET, "source", "directory", LIVE_CONSUMER),
        ArtifactRequirement(BASE_LOGICAL_SET, "source/.git", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, "source", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, "source/.git", "directory", LIVE_CONSUMER),
        *matrix.required_runtime_inputs(root, source),
    )
    physical_keys = [(item.logical_set, item.relative_path, item.kind) for item in requirements]
    require(len(physical_keys) == len(set(physical_keys)), "source/runtime inventory contains duplicate physical inputs")
    require(len(requirements) == 21, "source/runtime inventory must contain exactly 21 physical inputs")
    return requirements


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    return _requirements(root, load(root / CONFIG))


def validate_content(root: pathlib.Path, contract: dict[str, Any]) -> None:
    request, lock = load(root / matrix.CONTENT_REQUEST), load(root / matrix.CONTENT_LOCK)
    require(lock["status"] == "LOCKED" and lock["acquisition"]["selected_closure"] == 10 and len(lock["packages"]) == 10,
            "content acquisition closure drifted")
    requested = {item["unique_id"]: item for item in request["packages"]}
    locked = {item["unique_id"]: item for item in lock["packages"]}
    require(set(requested) == set(locked), "requested and locked content IDs differ")
    capabilities = sorted({capability for item in request["packages"] for capability in item["capabilities"]})
    require(capabilities == contract["capabilities"], "declared content capability closure drifted")
    runtime = [(item["unique_id"], item["catalog"]["catalog_md5"]) for item in lock["packages"]]
    require(runtime == [(item["id"], item["md5"]) for item in contract["newgrfs"]], "runtime NewGRF identity closure drifted")
    for identifier, item in locked.items():
        wanted = requested[identifier]
        require(item["requested"] and item["version"] == wanted["version"] and item["license"] == wanted["license"] and
                item["capabilities"] == wanted["capabilities"], f"locked metadata drifted: {identifier}")
        require(item["archive"]["bytes"] > 0 and len(item["archive"]["sha256"]) == 64 and item["grf_files"] and
                item["license_files"] and all(record["bytes"] > 0 and len(record["sha256"]) == 64
                                              for record in item["grf_files"] + item["license_files"]),
                f"content bytes/license evidence is vacuous: {identifier}")


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, *,
             artifact_context: ArtifactContext | None = None) -> dict[str, Any]:
    context = artifact_context or ArtifactContext.offline()
    repository_config = config_path is None
    root = root.resolve()
    source = load(config_path or root / CONFIG)
    contract, coverage = load(root / matrix.CONTRACT), load(root / matrix.COVERAGE)
    schema_validate(source, load(root / SOURCE_SCHEMA), "source")
    schema_validate(contract, load(root / CONTRACT_SCHEMA), "contract")
    schema_validate(coverage, load(root / COVERAGE_SCHEMA), "coverage")
    matrix.identities(root, contract)
    summary = matrix.validate_coverage(root, contract, coverage)
    validate_content(root, contract)
    patch = root / source["patch"]["path"]
    require(patch.is_file() and not patch.is_symlink() and sha256(patch) == source["patch"]["sha256"], "source patch identity drifted")
    text = patch.read_text(encoding="utf-8")
    touched = re.findall(r"^diff --git a/(\S+) b/\S+$", text, re.MULTILINE)
    require(touched == TOUCHED, f"source patch scope drifted: {touched}")
    for token in (
        "RunRlV2BroadQualification", "expected_capabilities", "known_capabilities", "ActiveContent", "ResetGRFConfig",
        "RunCalendar", "StartupEngines", "RunAuthorityEconomy", "CMD_TOWN_RATING", "CMD_DO_TOWN_ACTION",
        "CMD_CREATE_SUBSIDY", "AddInflation", "EconomyIsInRecession", "RunEvents", "CheckVehicleBreakdown",
        "DisasterVehicle", "RunGameScript", "CMD_CREATE_GOAL", "CMD_GOAL_QUESTION", "CMD_CREATE_STORY_PAGE",
        "CMD_CREATE_LEAGUE_TABLE", "CMD_GOAL_QUESTION_ANSWER", "CMD_STORY_PAGE_BUTTON", "RunContent", "SaveOrLoad",
    ):
        require(token in text, f"source patch lost required token: {token}")
    for forbidden in ("std::system(", "popen(", "fork(", "execve(", "mock_result", "fake_content"):
        require(forbidden not in text, f"source patch contains forbidden path: {forbidden}")
    require(source["build"]["upstream_ctest"] == {"passed": 98, "total": 98}, "upstream CTest claim drifted")
    requirements = _requirements(root, source)
    if context.is_live:
        requirements = required_live_inputs(root) if repository_config else requirements
        context.preflight(requirements)
        live_paths = {(item.logical_set, item.relative_path): context.resolve(item) for item in requirements}
        base_source = live_paths[(BASE_LOGICAL_SET, "source")]
        result_source = live_paths[(RESULT_LOGICAL_SET, "source")]
        require(git(base_source, "status", "--porcelain") == "", "base source is dirty")
        require(git(base_source, "rev-parse", "HEAD") == source["base"]["commit"] and
                git(base_source, "rev-parse", "HEAD^{tree}") == source["base"]["tree"], "base source identity drifted")
        with tempfile.TemporaryDirectory(prefix="openttd-rl-v2-m21-source-") as raw:
            target = pathlib.Path(raw) / "source"
            cloned = invoke_git("clone", "-q", "--no-hardlinks", str(base_source), str(target))
            require(cloned.returncode == 0, f"cannot clone base source: {cloned.stderr.decode('utf-8', errors='replace').strip()}")
            checked = invoke_git("apply", "--check", "--whitespace=error-all", str(patch), repository=target)
            check_output = (checked.stdout + checked.stderr).decode("utf-8", errors="replace")
            require(checked.returncode == 0 and not re.search(r"\b(?:offset|fuzz|warning)\b", check_output, re.I), "M21 patch does not apply exactly to the base")
            applied = invoke_git("apply", "--index", "--whitespace=error-all", str(patch), repository=target)
            require(applied.returncode == 0, f"cannot apply patch: {applied.stderr.decode('utf-8', errors='replace').strip()}")
            require(git(target, "write-tree") == source["source"]["tree"], "composed source identity/tree drifted")
        require(git(result_source, "status", "--porcelain") == "", "retained source is dirty")
        require(git(result_source, "rev-parse", "HEAD") == source["source"]["commit"] and
                git(result_source, "rev-parse", "HEAD^{tree}") == source["source"]["tree"], "retained source identity drifted")
        matrix.validate_runtime(root, source, context)
    return {"commands": summary["commands"], "features": summary["features"], "files": len(touched),
            "live": context.is_live, "tree": source["source"]["tree"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    add_artifact_root_argument(parser)
    args = parser.parse_args(argv)
    try:
        artifact_root = resolve_artifact_root(args.artifact_root)
        context = ArtifactContext.offline() if artifact_root is None else ArtifactContext.live(artifact_root)
        result = validate(args.root, args.config, artifact_context=context)
        print(f"V2_M21_BROAD_SOURCE=PASS files={result['files']} tree={result['tree']} features={result['features']} "
              f"commands={result['commands']} live={str(result['live']).lower()}")
        return 0
    except (M21SourceError, matrix.M21MatrixError, SourceContextError, ArtifactContextError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M21_BROAD_SOURCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
