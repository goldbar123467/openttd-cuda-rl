#!/usr/bin/env python3
"""Validate M22's cumulative patch and retained final-manifest-blind runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
from typing import Any

import jsonschema

import prepare_m22_final_runtime as preparation


CONFIG = pathlib.Path("config/v2/m22-final-runtime-source.json")
SCHEMA = preparation.SCHEMA


class M22RuntimeSourceError(ValueError):
    """The M22 final runtime source or retained closure is inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22RuntimeSourceError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(repository: pathlib.Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    require(completed.returncode == 0, f"git {' '.join(arguments)} failed: {(completed.stderr or completed.stdout).strip()}")
    return completed.stdout.strip()


def validate_file(record: dict[str, Any], artifact_root: pathlib.Path, label: str) -> pathlib.Path:
    path = pathlib.Path(record["path"])
    require(path.is_absolute() and path.is_relative_to(artifact_root), f"{label} escaped the retained artifact")
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == record["bytes"] and
            sha256(path) == record["sha256"], f"{label} identity drifted")
    return path


def validate_patch(root: pathlib.Path, record: dict[str, Any], base_source: pathlib.Path | None) -> None:
    patch = root / record["path"]
    require(patch.is_file() and not patch.is_symlink() and sha256(patch) == record["sha256"],
            "M22 final patch identity drifted")
    text = patch.read_text(encoding="utf-8")
    touched = re.findall(r"^diff --git a/(\S+) b/\S+$", text, re.MULTILINE)
    require(touched == list(preparation.TOUCHED) == record["touched_files"], f"M22 final patch scope drifted: {touched}")
    for token in (
        "OPENTTD_RL_M22_FINAL_TOKEN", "OPENTTD_RL_M22_FINAL_WIDTH", "OPENTTD_RL_M22_FINAL_HEIGHT",
        "OPENTTD_RL_M22_FINAL_CLIMATE", "m22-independent-final-v1", "GetRlV2FinalWorld",
        "GetAcceptanceAroundTiles", "GetDefaultCargoType()", "learning_company_vehicles",
        "M22 competition runs must use the final split",
    ):
        require(token in text, f"M22 final patch lost required token: {token}")
    for forbidden in ("std::system(", "popen(", "fork(", "execve(", "mock_result", "fake_service"):
        require(forbidden not in text, f"M22 final patch contains forbidden path: {forbidden}")
    if base_source is not None:
        base_source = base_source.resolve()
        require(git(base_source, "status", "--porcelain") == "", "M22 base source is dirty")
        completed = subprocess.run(
            ["git", "-C", str(base_source), "apply", "--check", "--whitespace=error-all", str(patch)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        require(completed.returncode == 0 and not re.search(r"\b(?:offset|fuzz|warning)\b",
                                                            completed.stdout + completed.stderr, re.I),
                "M22 final patch does not apply exactly to the accepted M21 source")


def validate_smokes(source: dict[str, Any], artifact_root: pathlib.Path | None) -> None:
    smokes = source["smokes"]
    require([item["case"]["case_id"] for item in smokes] == [case["case_id"] for case in preparation.SMOKE_CASES],
            "M22 runtime smoke inventory/order drifted")
    require([item["case"]["source_gate"] for item in smokes] == ["G15", "G16", "G17", "G18", "G19", "G20", "G21", "G21"],
            "M22 runtime smoke gate coverage drifted")
    for expected, record in zip(preparation.SMOKE_CASES, smokes, strict=True):
        require(record["case"] == {key: expected[key] for key in preparation.native.PUBLIC_FIELDS} and
                record["private_seed"] == expected["seed"], f"M22 runtime smoke public/private projection drifted: {expected['case_id']}")
        require("seed" not in record["case"] and "required_program" not in record["case"] and
                record["fresh_processes"] == 1 and record["network_unshared"] and record["status"] == "PASS",
                f"M22 runtime smoke boundary drifted: {expected['case_id']}")
        require(record["executable_sha256"] == source["executable"]["sha256"] and
                record["source_tree"] == source["source"]["tree"], f"M22 runtime smoke identity drifted: {expected['case_id']}")
        metrics = record["metrics"]
        if expected["source_gate"] in {"G15", "G16", "G17", "G18", "G19"}:
            require(metrics.get("delivered", 0) > 0 and metrics.get("income", 0) > 0,
                    f"M22 useful-service smoke is vacuous: {expected['case_id']}")
        elif expected["source_gate"] == "G20":
            require(metrics.get("delivered", 0) >= 25 and metrics.get("opponent") == "AAAHogEx",
                    "M22 competition smoke is vacuous")
        elif expected["native_probe"] == "content":
            require(metrics == {"capabilities": 14, "packages": 10}, "M22 content smoke drifted")
        else:
            require(metrics.get("commands") == 13 and metrics.get("responses") == 2 and metrics.get("save_load_exact"),
                    "M22 Game Script smoke drifted")
        if artifact_root is not None:
            case_root = pathlib.Path(record["artifact_root"])
            require(case_root == artifact_root / "smokes" / expected["case_id"], "M22 smoke artifact path drifted")
            for path_key, hash_key in (("manifest_path", "manifest_sha256"), ("report_path", "report_sha256"),
                                       ("openttd_log_path", "openttd_log_sha256")):
                path = case_root / record[path_key]
                require(path.is_file() and not path.is_symlink() and sha256(path) == record[hash_key],
                        f"M22 smoke artifact identity drifted: {expected['case_id']}/{path_key}")


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, *, artifact_root: pathlib.Path | None = None,
             base_source: pathlib.Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    source = load(config_path or root / CONFIG)
    try:
        jsonschema.Draft202012Validator(load(root / SCHEMA)).validate(source)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M22RuntimeSourceError(f"runtime source schema failed at {where}: {exc.message}") from exc
    require(source["prerequisites"] == {
        "m20_source_record_sha256": sha256(root / preparation.M20_SOURCE),
        "m21_source_record_sha256": sha256(root / preparation.M21_SOURCE),
    } and source["base"]["source_record_sha256"] == sha256(root / preparation.M21_SOURCE),
            "M22 runtime prerequisite identity drifted")
    m21 = load(root / preparation.M21_SOURCE)
    require(source["base"]["commit"] == m21["source"]["commit"] and source["base"]["tree"] == m21["source"]["tree"],
            "M22 runtime base identity drifted")
    contract = load(root / preparation.LEARNING_CONTRACT)
    require(source["final_boundary"] == {
        "expected_manifest_sha256": contract["identities"]["final_evaluation_manifest_sha256"],
        "manifest_executions": 0, "manifest_opened": False,
    }, "M22 final-manifest boundary drifted")
    repository_commit = source["repository"]["commit"]
    require(git(root, "cat-file", "-t", repository_commit) == "commit" and
            git(root, "show", "-s", "--format=%T", repository_commit) == source["repository"]["tree"],
            "M22 preparation repository identity drifted")
    validate_patch(root, source["patch"], base_source)
    require(source["build"]["cmake_arguments"] == list(preparation.CMAKE_ARGUMENTS) and
            source["build"]["upstream_ctest"] == {"passed": 98, "total": 98}, "M22 build contract drifted")
    validate_smokes(source, artifact_root.resolve() if artifact_root is not None else None)
    live = artifact_root is not None
    if live:
        artifact_root = artifact_root.resolve()
        require(str(artifact_root) == source["retained_artifact"], "M22 retained artifact root drifted")
        source_path = pathlib.Path(source["source"]["path"])
        require(source_path == artifact_root / "source" and git(source_path, "status", "--porcelain") == "",
                "M22 retained source is missing or dirty")
        require(git(source_path, "rev-parse", "HEAD") == source["source"]["commit"] and
                git(source_path, "rev-parse", "HEAD^{tree}") == source["source"]["tree"],
                "M22 retained source identity drifted")
        validate_file(source["executable"], artifact_root, "M22 executable")
        for name, record in source["build"]["logs"].items():
            validate_file(record, artifact_root, f"M22 {name} log")
        validate_file(source["build"]["test_inventory"], artifact_root, "M22 CTest inventory")
        inventory = load(pathlib.Path(source["build"]["test_inventory"]["path"]))
        require(len(inventory["tests"]) == len(set(inventory["tests"])) == 98, "M22 live CTest inventory drifted")
        runtime = source["runtime"]
        validate_file(runtime["open_gfx"], artifact_root, "M22 OpenGFX")
        for name, record in runtime["configs"].items():
            validate_file(record, artifact_root, f"M22 {name} config")
        for group in ("ai_archives", "ai_libraries", "gamescript_files", "newgrf_archives", "newgrf_files"):
            for ordinal, record in enumerate(runtime[group]):
                validate_file(record, artifact_root, f"M22 {group}[{ordinal}]")
    return {"files": len(source["patch"]["touched_files"]), "live": live, "smokes": len(source["smokes"]),
            "source_tree": source["source"]["tree"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path)
    parser.add_argument("--base-source", type=pathlib.Path)
    args = parser.parse_args()
    try:
        result = validate(args.root, artifact_root=args.artifact_root, base_source=args.base_source)
        print(f"V2_M22_FINAL_RUNTIME_SOURCE=PASS files={result['files']} smokes={result['smokes']} "
              f"tree={result['source_tree']} live={str(result['live']).lower()}")
        return 0
    except (M22RuntimeSourceError, preparation.M22RuntimePreparationError, OSError, json.JSONDecodeError,
            KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_FINAL_RUNTIME_SOURCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
