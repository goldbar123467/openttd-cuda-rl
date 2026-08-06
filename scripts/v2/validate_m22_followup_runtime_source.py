#!/usr/bin/env python3
"""Validate the corrected, manifest-blind retained M22 follow-up runtime."""

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
import prepare_m22_followup_runtime as preparation
import validate_m22_final_runtime_source as foundation_validator
from source_context import SourceContextError, run_git


CONFIG = pathlib.Path("config/v2/m22-followup-runtime-source.json")
SCHEMA = preparation.SCHEMA
BASE_LOGICAL_SET = "v2-m21-broad-a"
RESULT_LOGICAL_SET = "v2-m22-followup-runtime-a"
LIVE_CONSUMER = "m22-followup-runtime-source"
EXPECTED_LIVE_INPUTS = 85


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


def invoke_git(*arguments: str, repository: pathlib.Path | None = None):
    try:
        return run_git(*arguments, repository=repository)
    except SourceContextError as exc:
        raise M22FollowupRuntimeSourceError(f"git {' '.join(arguments)} failed: {exc}") from exc


def git(repository: pathlib.Path, *arguments: str) -> str:
    completed = invoke_git(*arguments, repository=repository)
    detail = (completed.stderr or completed.stdout).decode("utf-8", errors="replace").strip()
    require(completed.returncode == 0, f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout.decode("utf-8", errors="replace").strip()


def schema_validate(source: dict[str, Any], schema: dict[str, Any]) -> None:
    try:
        jsonschema.Draft202012Validator(schema).validate(source)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M22FollowupRuntimeSourceError(
            f"corrected runtime source schema failed at {where}: {exc.message}"
        ) from exc


def _normalized_absolute(value: str, *, label: str) -> pathlib.PurePosixPath:
    path = pathlib.PurePosixPath(value) if isinstance(value, str) else pathlib.PurePosixPath("")
    require(
        isinstance(value, str)
        and value.startswith("/")
        and not value.startswith("//")
        and "\\" not in value
        and "\x00" not in value
        and str(path) == value
        and all(part not in {"", ".", ".."} for part in path.parts[1:]),
        f"recorded {label} path is not an absolute normalized POSIX path",
    )
    return path


def _recorded_relative(recorded_root: str, recorded_path: str, *, label: str) -> str:
    root = _normalized_absolute(recorded_root, label="retained artifact")
    path = _normalized_absolute(recorded_path, label=label)
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise M22FollowupRuntimeSourceError(f"recorded {label} path escaped retained artifact") from exc
    require(str(relative) != ".", f"recorded {label} path must be below retained artifact")
    return relative.as_posix()


def _safe_relative(value: str, *, label: str) -> str:
    path = pathlib.PurePosixPath(value) if isinstance(value, str) else pathlib.PurePosixPath("")
    require(
        isinstance(value, str)
        and bool(value)
        and not value.startswith("/")
        and "\\" not in value
        and "\x00" not in value
        and str(path) == value
        and all(part not in {"", ".", ".."} for part in path.parts),
        f"recorded {label} path is not a safe relative POSIX path",
    )
    return path.as_posix()


def _result_logical_set(source: dict[str, Any]) -> str:
    recorded = _normalized_absolute(source["retained_artifact"], label="retained artifact")
    require(recorded.name == RESULT_LOGICAL_SET, "corrected retained artifact logical set drifted")
    require(
        _recorded_relative(source["retained_artifact"], source["source"]["path"], label="source") == "source",
        "corrected recorded retained source path drifted",
    )
    return recorded.name


def _runtime_file_records(source: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    records: list[tuple[str, dict[str, Any]]] = [("executable", source["executable"])]
    records.extend((f"{name} log", record) for name, record in source["build"]["logs"].items())
    records.append(("CTest inventory", source["build"]["test_inventory"]))
    records.append(("OpenGFX", source["runtime"]["open_gfx"]))
    records.extend((f"{name} config", record) for name, record in source["runtime"]["configs"].items())
    for group in ("ai_archives", "ai_libraries", "gamescript_files", "newgrf_archives", "newgrf_files"):
        records.extend((f"{group}[{ordinal}]", record) for ordinal, record in enumerate(source["runtime"][group]))
    return records


def _requirements(source: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    result_set = _result_logical_set(source)
    recorded_root = source["retained_artifact"]
    requirements: list[ArtifactRequirement] = [
        ArtifactRequirement(BASE_LOGICAL_SET, "source", "directory", LIVE_CONSUMER),
        ArtifactRequirement(BASE_LOGICAL_SET, "source/.git", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, "source", "directory", LIVE_CONSUMER),
        ArtifactRequirement(result_set, "source/.git", "directory", LIVE_CONSUMER),
    ]
    for label, record in _runtime_file_records(source):
        requirements.append(ArtifactRequirement(
            result_set,
            _recorded_relative(recorded_root, record["path"], label=label),
            "file",
            LIVE_CONSUMER,
            record["sha256"],
        ))
    for smoke in source["smokes"]:
        case_id = smoke["case"]["case_id"]
        case_relative = _recorded_relative(recorded_root, smoke["artifact_root"], label=f"smoke {case_id}")
        require(case_relative == f"smokes/{case_id}", f"corrected smoke artifact path drifted: {case_id}")
        for path_key, hash_key in (
            ("manifest_path", "manifest_sha256"),
            ("report_path", "report_sha256"),
            ("openttd_log_path", "openttd_log_sha256"),
        ):
            relative = _safe_relative(smoke[path_key], label=f"smoke {case_id}/{path_key}")
            requirements.append(ArtifactRequirement(
                result_set, f"{case_relative}/{relative}", "file", LIVE_CONSUMER, smoke[hash_key],
            ))
    physical = [(item.logical_set, item.relative_path, item.kind) for item in requirements]
    require(len(physical) == len(set(physical)),
            "corrected runtime live-input closure contains duplicate physical inputs")
    require(len(requirements) == EXPECTED_LIVE_INPUTS,
            f"corrected runtime live-input closure must contain exactly {EXPECTED_LIVE_INPUTS} inputs")
    return tuple(requirements)


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    return _requirements(load(root / CONFIG))


def _preflight_live(
    context: ArtifactContext,
    requirements: tuple[ArtifactRequirement, ...],
) -> dict[tuple[str, str], pathlib.Path]:
    context.preflight(requirements)
    resolved = {(item.logical_set, item.relative_path): context.resolve(item) for item in requirements}
    inodes: dict[tuple[int, int], pathlib.Path] = {}
    for requirement in requirements:
        if requirement.kind != "file":
            continue
        path = resolved[(requirement.logical_set, requirement.relative_path)]
        identity = path.stat()
        require(identity.st_nlink == 1, f"corrected M22 live input is a hard link: {path}")
        key = (identity.st_dev, identity.st_ino)
        require(key not in inodes, f"corrected M22 live inputs alias one file: {inodes.get(key)} and {path}")
        inodes[key] = path
    return resolved


def validate_patch_series(root: pathlib.Path, source: dict[str, Any]) -> tuple[pathlib.Path, ...]:
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
    return tuple(resolved)


def validate_smokes(source: dict[str, Any]) -> None:
    smokes = source["smokes"]
    require([item["case"]["case_id"] for item in smokes] == [case["case_id"] for case in preparation.SMOKE_CASES],
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


def _validate_historical_repository(root: pathlib.Path, source: dict[str, Any]) -> None:
    repository_commit = source["repository"]["commit"]
    require(git(root, "cat-file", "-e", f"{repository_commit}^{{commit}}") == "" and
            git(root, "rev-parse", f"{repository_commit}^{{tree}}") == source["repository"]["tree"],
            "corrected runtime preparation historical repository identity drifted")


def _validate_live_files(
    root: pathlib.Path,
    source: dict[str, Any],
    paths: dict[tuple[str, str], pathlib.Path],
) -> None:
    try:
        foundation_validator._validate_live_files(
            root, source, paths, result_set=RESULT_LOGICAL_SET, smoke_cases=preparation.SMOKE_CASES,
        )
    except foundation_validator.M22RuntimeSourceError as exc:
        raise M22FollowupRuntimeSourceError(str(exc).replace("M22 ", "corrected M22 ", 1)) from exc


def _validate_live_source(
    source: dict[str, Any],
    patches: tuple[pathlib.Path, ...],
    paths: dict[tuple[str, str], pathlib.Path],
) -> None:
    base_source = paths[(BASE_LOGICAL_SET, "source")]
    result_source = paths[(RESULT_LOGICAL_SET, "source")]
    require(git(base_source, "status", "--porcelain") == "", "accepted M21 base source is dirty")
    require(git(base_source, "rev-parse", "HEAD") == source["base"]["commit"] and
            git(base_source, "rev-parse", "HEAD^{tree}") == source["base"]["tree"],
            "accepted M21 base source identity drifted")
    with tempfile.TemporaryDirectory(prefix="openttd-rl-v2-m22-followup-source-") as raw:
        target = pathlib.Path(raw) / "source"
        cloned = invoke_git("clone", "-q", "--no-hardlinks", str(base_source), str(target))
        require(cloned.returncode == 0, "cannot clone the accepted M21 source")
        for patch in patches:
            checked = invoke_git("apply", "--check", "--whitespace=error-all", str(patch), repository=target)
            detail = (checked.stdout + checked.stderr).decode("utf-8", errors="replace")
            require(checked.returncode == 0 and not re.search(r"\b(?:offset|fuzz|warning)\b", detail, re.I),
                    "corrected patch series does not apply exactly to the accepted M21 source")
            applied = invoke_git("apply", "--index", "--whitespace=error-all", str(patch), repository=target)
            require(applied.returncode == 0, "cannot apply the corrected M22 patch series")
        require(git(target, "write-tree") == source["source"]["tree"],
                "corrected composed source tree drifted")
    require(git(result_source, "status", "--porcelain") == "", "corrected retained source is dirty")
    require(git(result_source, "rev-parse", "HEAD") == source["source"]["commit"] and
            git(result_source, "rev-parse", "HEAD^{tree}") == source["source"]["tree"],
            "corrected retained source identity drifted")


def validate(
    root: pathlib.Path,
    config_path: pathlib.Path | None = None,
    *,
    artifact_context: ArtifactContext | None = None,
) -> dict[str, Any]:
    context = artifact_context or ArtifactContext.offline()
    root = root.resolve()
    source = load(config_path or root / CONFIG)
    schema_validate(source, load(root / SCHEMA))
    require(source["prerequisites"] == {
        "final_runtime_source_record_sha256": sha256(root / "config/v2/m22-final-runtime-source.json"),
        "m20_source_record_sha256": sha256(root / preparation.foundation.M20_SOURCE),
        "m21_source_record_sha256": sha256(root / preparation.foundation.M21_SOURCE),
    }, "corrected runtime prerequisite identity drifted")
    try:
        foundation_validator._canonical_runtime(root, source, build_name="build-followup")
    except foundation_validator.M22RuntimeSourceError as exc:
        raise M22FollowupRuntimeSourceError(str(exc).replace("M22 ", "corrected M22 ", 1)) from exc
    immutable_path = root / preparation.IMMUTABLE_FINAL_EVIDENCE
    immutable = load(immutable_path)
    require(immutable["status"] == "FAIL" and source["boundaries"] == {
        "followup": {"evaluator_processes": 0, "manifest_opened": False, "native_dispatches": 0,
                     "protocol_state": "not-yet-frozen"},
        "immutable_final_v1": {"evidence_path": str(preparation.IMMUTABLE_FINAL_EVIDENCE),
                               "evidence_sha256": sha256(immutable_path), "evaluator_processes": 0,
                               "manifest_opened": False, "native_dispatches": 0, "status": "FAIL"},
    }, "immutable final/follow-up boundary drifted")
    patches = validate_patch_series(root, source)
    require(source["build"]["cmake_arguments"] == list(preparation.foundation.CMAKE_ARGUMENTS) and
            source["build"]["upstream_ctest"] == {"passed": 98, "total": 98},
            "corrected runtime build contract drifted")
    validate_smokes(source)
    requirements = _requirements(source)
    paths: dict[tuple[str, str], pathlib.Path] = {}
    if context.is_live:
        paths = _preflight_live(context, requirements)
    _validate_historical_repository(root, source)
    if context.is_live:
        _validate_live_source(source, patches, paths)
        _validate_live_files(root, source, paths)
    return {"files": len({path for touched in preparation.PATCH_TOUCHED for path in touched}),
            "live": context.is_live, "smokes": len(source["smokes"]),
            "source_tree": source["source"]["tree"]}


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
        print(f"V2_M22_FOLLOWUP_RUNTIME_SOURCE=PASS files={result['files']} smokes={result['smokes']} "
              f"tree={result['source_tree']} live={str(result['live']).lower()}")
        return 0
    except (M22FollowupRuntimeSourceError, preparation.foundation.M22RuntimePreparationError,
            SourceContextError, ArtifactContextError, OSError, json.JSONDecodeError, KeyError,
            TypeError, ValueError) as exc:
        print(f"V2_M22_FOLLOWUP_RUNTIME_SOURCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
