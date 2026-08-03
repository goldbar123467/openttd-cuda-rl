#!/usr/bin/env python3
"""Validate the M21 contract, coverage, content closure, native source, and runtime identities."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
from typing import Any

import jsonschema

import run_m21_broad_matrix as matrix


CONFIG = pathlib.Path("config/v2/m21-broad-source.json")
SOURCE_SCHEMA = pathlib.Path("docs/project/schema/v2-m21-broad-source.schema.json")
CONTRACT_SCHEMA = pathlib.Path("docs/project/schema/v2-m21-broad-contract.schema.json")
COVERAGE_SCHEMA = pathlib.Path("docs/project/schema/v2-m21-broad-coverage.schema.json")
TOUCHED = ["src/CMakeLists.txt", "src/openttd.cpp", "src/rl_v2_broad.cpp", "src/rl_v2_broad.h"]


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


def git(repository: pathlib.Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repository), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    require(result.returncode == 0, f"git {' '.join(args)} failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


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


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, *, artifact_root: pathlib.Path | None = None,
             base_source: pathlib.Path | None = None) -> dict[str, Any]:
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
    if base_source is not None:
        base_source = base_source.resolve()
        require(git(base_source, "status", "--porcelain") == "", "base source is dirty")
        require(git(base_source, "rev-parse", "HEAD") == source["base"]["commit"] and
                git(base_source, "rev-parse", "HEAD^{tree}") == source["base"]["tree"], "base source identity drifted")
        checked = subprocess.run(["git", "-C", str(base_source), "apply", "--check", "--whitespace=error-all", str(patch)],
                                 text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        require(checked.returncode == 0 and not re.search(r"\b(?:offset|fuzz|warning)\b", checked.stdout + checked.stderr, re.I),
                "M21 patch does not apply exactly to the base")
    live = artifact_root is not None
    if live:
        artifact_root = artifact_root.resolve()
        require(str(artifact_root) == source["retained_artifact"], "retained artifact root drifted")
        repository = pathlib.Path(source["source"]["path"])
        require(repository == artifact_root / "source" and git(repository, "status", "--porcelain") == "", "retained source is missing or dirty")
        require(git(repository, "rev-parse", "HEAD") == source["source"]["commit"] and
                git(repository, "rev-parse", "HEAD^{tree}") == source["source"]["tree"], "retained source identity drifted")
        matrix.validate_runtime(root, source)
    require(source["build"]["upstream_ctest"] == {"passed": 98, "total": 98}, "upstream CTest claim drifted")
    return {"commands": summary["commands"], "features": summary["features"], "files": len(touched),
            "live": live, "tree": source["source"]["tree"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path)
    parser.add_argument("--base-source", type=pathlib.Path)
    args = parser.parse_args()
    try:
        result = validate(args.root, artifact_root=args.artifact_root, base_source=args.base_source)
        print(f"V2_M21_BROAD_SOURCE=PASS files={result['files']} tree={result['tree']} features={result['features']} "
              f"commands={result['commands']} live={str(result['live']).lower()}")
        return 0
    except (M21SourceError, matrix.M21MatrixError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M21_BROAD_SOURCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
