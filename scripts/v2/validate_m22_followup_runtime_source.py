#!/usr/bin/env python3
"""Validate the corrected, manifest-blind retained M22 follow-up runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import tempfile
from typing import Any

import jsonschema

import prepare_m22_followup_runtime as preparation


CONFIG = pathlib.Path("config/v2/m22-followup-runtime-source.json")
SCHEMA = preparation.SCHEMA


class M22FollowupRuntimeSourceError(ValueError):
    """The corrected M22 runtime source or retained closure is inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22FollowupRuntimeSourceError(message)


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
    require(completed.returncode == 0,
            f"git {' '.join(arguments)} failed: {(completed.stderr or completed.stdout).strip()}")
    return completed.stdout.strip()


def validate_file(record: dict[str, Any], artifact_root: pathlib.Path, label: str) -> pathlib.Path:
    path = pathlib.Path(record["path"])
    require(path.is_absolute() and path.is_relative_to(artifact_root), f"{label} escaped the retained artifact")
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == record["bytes"] and
            sha256(path) == record["sha256"], f"{label} identity drifted")
    return path


def validate_patch_series(root: pathlib.Path, source: dict[str, Any], base_source: pathlib.Path | None) -> None:
    records = source["patches"]
    require(len(records) == len(preparation.PATCHES) == 2, "corrected patch count drifted")
    resolved: list[pathlib.Path] = []
    for index, (relative, touched, record) in enumerate(
            zip(preparation.PATCHES, preparation.PATCH_TOUCHED, records, strict=True)):
        path = root / relative
        require(record == {"path": str(relative), "sha256": sha256(path), "touched_files": list(touched)},
                f"corrected patch record drifted at index {index}")
        text = path.read_text(encoding="utf-8")
        actual = re.findall(r"^diff --git a/(\S+) b/\S+$", text, re.MULTILINE)
        require(actual == list(touched), f"corrected patch scope drifted at index {index}: {actual}")
        for forbidden in ("std::system(", "popen(", "fork(", "execve(", "mock_result", "fake_service"):
            require(forbidden not in text, f"corrected patch contains forbidden path: {forbidden}")
        resolved.append(path.resolve())
    final_text = resolved[0].read_text(encoding="utf-8")
    for token in ("OPENTTD_RL_M22_FINAL_TOKEN", "GetRlV2FinalWorld", "m22-independent-final-v1"):
        require(token in final_text, f"final-world patch lost required token: {token}")
    correction_text = resolved[1].read_text(encoding="utf-8")
    for token in ("RoadStopType::Bus", "AutoRestoreBackup competitor_company", "Vehicle::CanAllocateItem()"):
        require(token in correction_text, f"follow-up correction lost required token: {token}")
    require("EnsureSharedWorldFloor" not in correction_text and "CMD_FOUND_TOWN" not in correction_text,
            "follow-up patch contains the rejected sparse-world mutation")
    if base_source is not None:
        base_source = base_source.resolve()
        require(git(base_source, "status", "--porcelain") == "", "accepted M21 base source is dirty")
        with tempfile.TemporaryDirectory() as raw:
            reproduced = preparation.prepare_source(
                base_source, pathlib.Path(raw) / "source", tuple(resolved), source["base"]["commit"])
        require((reproduced["commit"], reproduced["tree"]) ==
                (source["source"]["commit"], source["source"]["tree"]),
                "corrected source commit/tree is not reproducible from accepted M21")


def validate_smokes(source: dict[str, Any], artifact_root: pathlib.Path | None) -> None:
    smokes = source["smokes"]
    require([item["case"]["case_id"] for item in smokes] ==
            [case["case_id"] for case in preparation.SMOKE_CASES],
            "corrected runtime smoke inventory/order drifted")
    require(len(smokes) == 14 and [case["source_gate"] for case in preparation.SMOKE_CASES[:8]] ==
            ["G15", "G16", "G17", "G18", "G19", "G20", "G21", "G21"],
            "corrected runtime foundational gate coverage drifted")
    for expected, record in zip(preparation.SMOKE_CASES, smokes, strict=True):
        require(record["case"] == {key: expected[key] for key in preparation.native.PUBLIC_FIELDS} and
                record["private_seed"] == expected["seed"],
                f"corrected smoke public/private projection drifted: {expected['case_id']}")
        require("seed" not in record["case"] and "required_program" not in record["case"] and
                record["fresh_processes"] == 1 and record["network_unshared"] and record["status"] == "PASS",
                f"corrected smoke process boundary drifted: {expected['case_id']}")
        require(record["executable_sha256"] == source["executable"]["sha256"] and
                record["source_tree"] == source["source"]["tree"],
                f"corrected smoke identity drifted: {expected['case_id']}")
        metrics = record["metrics"]
        probe = preparation.native.canonical_probe(expected)
        if expected["source_gate"] in {"G15", "G16", "G17", "G18", "G19"}:
            require(metrics.get("delivered", 0) > 0 and metrics.get("income", 0) > 0,
                    f"corrected useful-service smoke is vacuous: {expected['case_id']}")
        elif expected["source_gate"] == "G20":
            require(expected["map_width"] == expected["map_height"] == 128 and metrics.get("delivered", 0) >= 25 and
                    metrics.get("opponent") == expected["opponent"],
                    f"corrected competition smoke is vacuous: {expected['case_id']}")
        elif probe == "content":
            require(metrics == {"capabilities": 14, "packages": 10}, "corrected content smoke drifted")
        elif probe == "gamescript":
            require(metrics.get("commands") == 13 and metrics.get("responses") == 2 and
                    metrics.get("save_load_exact"), "corrected Game Script smoke drifted")
        elif probe == "authority_economy":
            require(metrics == {"commands": 6, "save_load_exact": True}, "corrected authority smoke drifted")
        else:
            require(probe == "events" and 0 < metrics.get("recovery_ticks", 0) <= 32 and
                    metrics.get("save_load_exact"), "corrected event smoke drifted")
        if artifact_root is not None:
            case_root = pathlib.Path(record["artifact_root"])
            require(case_root == artifact_root / "smokes" / expected["case_id"],
                    "corrected smoke artifact path drifted")
            for path_key, hash_key in (("manifest_path", "manifest_sha256"), ("report_path", "report_sha256"),
                                       ("openttd_log_path", "openttd_log_sha256")):
                path = case_root / record[path_key]
                require(path.is_file() and not path.is_symlink() and sha256(path) == record[hash_key],
                        f"corrected smoke artifact identity drifted: {expected['case_id']}/{path_key}")


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None, *,
             artifact_root: pathlib.Path | None = None, base_source: pathlib.Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    source = load(config_path or root / CONFIG)
    try:
        jsonschema.Draft202012Validator(load(root / SCHEMA)).validate(source)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M22FollowupRuntimeSourceError(
            f"corrected runtime source schema failed at {where}: {exc.message}"
        ) from exc
    require(source["prerequisites"] == {
        "final_runtime_source_record_sha256": sha256(root / "config/v2/m22-final-runtime-source.json"),
        "m20_source_record_sha256": sha256(root / preparation.foundation.M20_SOURCE),
        "m21_source_record_sha256": sha256(root / preparation.foundation.M21_SOURCE),
    }, "corrected runtime prerequisite identity drifted")
    m21 = load(root / preparation.foundation.M21_SOURCE)
    require(source["base"] == {
        "commit": m21["source"]["commit"],
        "source_record_sha256": sha256(root / preparation.foundation.M21_SOURCE),
        "tree": m21["source"]["tree"],
    }, "corrected runtime base identity drifted")
    immutable_path = root / preparation.IMMUTABLE_FINAL_EVIDENCE
    immutable = load(immutable_path)
    require(immutable["status"] == "FAIL" and source["boundaries"] == {
        "followup": {"evaluator_processes": 0, "manifest_opened": False, "native_dispatches": 0,
                     "protocol_state": "not-yet-frozen"},
        "immutable_final_v1": {"evidence_path": str(preparation.IMMUTABLE_FINAL_EVIDENCE),
                               "evidence_sha256": sha256(immutable_path), "evaluator_processes": 0,
                               "manifest_opened": False, "native_dispatches": 0, "status": "FAIL"},
    }, "immutable final/follow-up boundary drifted")
    repository_commit = source["repository"]["commit"]
    require(git(root, "cat-file", "-t", repository_commit) == "commit" and
            git(root, "show", "-s", "--format=%T", repository_commit) == source["repository"]["tree"],
            "corrected runtime preparation repository identity drifted")
    validate_patch_series(root, source, base_source)
    require(source["build"]["cmake_arguments"] == list(preparation.foundation.CMAKE_ARGUMENTS) and
            source["build"]["upstream_ctest"] == {"passed": 98, "total": 98},
            "corrected runtime build contract drifted")
    live_root = artifact_root.resolve() if artifact_root is not None else None
    validate_smokes(source, live_root)
    if live_root is not None:
        require(str(live_root) == source["retained_artifact"], "corrected retained artifact root drifted")
        source_path = pathlib.Path(source["source"]["path"])
        require(source_path == live_root / "source" and git(source_path, "status", "--porcelain") == "",
                "corrected retained source is missing or dirty")
        require(git(source_path, "rev-parse", "HEAD") == source["source"]["commit"] and
                git(source_path, "rev-parse", "HEAD^{tree}") == source["source"]["tree"],
                "corrected retained source identity drifted")
        validate_file(source["executable"], live_root, "corrected M22 executable")
        for name, record in source["build"]["logs"].items():
            validate_file(record, live_root, f"corrected M22 {name} log")
        inventory_path = validate_file(source["build"]["test_inventory"], live_root,
                                       "corrected M22 CTest inventory")
        inventory = load(inventory_path)
        require(len(inventory["tests"]) == len(set(inventory["tests"])) == 98,
                "corrected live CTest inventory drifted")
        runtime = source["runtime"]
        validate_file(runtime["open_gfx"], live_root, "corrected M22 OpenGFX")
        for name, record in runtime["configs"].items():
            validate_file(record, live_root, f"corrected M22 {name} config")
        for group in ("ai_archives", "ai_libraries", "gamescript_files", "newgrf_archives", "newgrf_files"):
            for ordinal, record in enumerate(runtime[group]):
                validate_file(record, live_root, f"corrected M22 {group}[{ordinal}]")
    return {"files": len({path for touched in preparation.PATCH_TOUCHED for path in touched}),
            "live": live_root is not None, "smokes": len(source["smokes"]),
            "source_tree": source["source"]["tree"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path)
    parser.add_argument("--base-source", type=pathlib.Path)
    args = parser.parse_args()
    try:
        result = validate(args.root, artifact_root=args.artifact_root, base_source=args.base_source)
        print(f"V2_M22_FOLLOWUP_RUNTIME_SOURCE=PASS files={result['files']} smokes={result['smokes']} "
              f"tree={result['source_tree']} live={str(result['live']).lower()}")
        return 0
    except (M22FollowupRuntimeSourceError, preparation.foundation.M22RuntimePreparationError,
            OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_FOLLOWUP_RUNTIME_SOURCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
