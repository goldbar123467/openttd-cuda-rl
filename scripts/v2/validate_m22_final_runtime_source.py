#!/usr/bin/env python3
"""Validate M22's cumulative patch and retained final-manifest-blind runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import tempfile
import xml.etree.ElementTree as ET
from typing import Any

import jsonschema

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    add_artifact_root_argument,
    resolve_artifact_root,
)
import prepare_m22_final_runtime as preparation
from source_context import SourceContextError, run_git


CONFIG = pathlib.Path("config/v2/m22-final-runtime-source.json")
SCHEMA = preparation.SCHEMA
BASE_LOGICAL_SET = "v2-m21-broad-a"
RESULT_LOGICAL_SET = "v2-m22-final-runtime-c"
LIVE_CONSUMER = "m22-final-runtime-source"
EXPECTED_LIVE_INPUTS = 67


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


def invoke_git(*arguments: str, repository: pathlib.Path | None = None):
    try:
        return run_git(*arguments, repository=repository)
    except SourceContextError as exc:
        raise M22RuntimeSourceError(f"git {' '.join(arguments)} failed: {exc}") from exc


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
        raise M22RuntimeSourceError(f"runtime source schema failed at {where}: {exc.message}") from exc


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
        raise M22RuntimeSourceError(f"recorded {label} path escaped retained artifact") from exc
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
    require(recorded.name == RESULT_LOGICAL_SET, "retained artifact logical set drifted")
    require(
        _recorded_relative(source["retained_artifact"], source["source"]["path"], label="source") == "source",
        "recorded retained source path drifted",
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


def _canonical_runtime(root: pathlib.Path, source: dict[str, Any], *, build_name: str) -> None:
    """Bind the M22 layout to the committed M20/M21 staging authorities."""

    recorded_root = source["retained_artifact"]
    m20_content = load(root / preparation.M20_CONTENT)
    m21_source = load(root / preparation.M21_SOURCE)
    m21_lock = load(root / preparation.M21_CONTENT_LOCK)
    m21_contract = load(root / preparation.native.m21.CONTRACT)

    require(source["base"] == {
        "commit": m21_source["source"]["commit"],
        "source_record_sha256": sha256(root / preparation.M21_SOURCE),
        "tree": m21_source["source"]["tree"],
    }, "M22 runtime base identity drifted")
    require(tuple(source["build"]["logs"]) == ("build", "configure", "ctest", "junit"),
            "M22 canonical runtime build-log order drifted")
    expected_logs = {"build": "build.log", "configure": "configure.log", "ctest": "ctest.log", "junit": "ctest.xml"}
    require(all(_recorded_relative(recorded_root, source["build"]["logs"][name]["path"], label=f"{name} log") == relative
                for name, relative in expected_logs.items()), "M22 canonical runtime build-log layout drifted")
    require(_recorded_relative(recorded_root, source["build"]["test_inventory"]["path"], label="CTest inventory") ==
            "ctest-inventory.json", "M22 canonical runtime CTest inventory path drifted")
    require(_recorded_relative(recorded_root, source["executable"]["path"], label="executable") ==
            f"{build_name}/openttd", "M22 canonical runtime executable path drifted")

    open_gfx = m21_source["build"]["open_gfx"]
    actual_open_gfx = source["runtime"]["open_gfx"]
    require(_recorded_relative(recorded_root, actual_open_gfx["path"], label="OpenGFX") ==
            f"{build_name}/baseset/{pathlib.PurePosixPath(open_gfx['path']).name}" and
            actual_open_gfx["bytes"] == open_gfx["bytes"] and actual_open_gfx["sha256"] == open_gfx["sha256"],
            "M22 canonical runtime OpenGFX identity drifted")

    require(tuple(source["runtime"]["configs"]) == ("base", "content", "gamescript"),
            "M22 canonical runtime config order drifted")
    for name, authority in m21_source["runtime"]["configs"].items():
        actual = source["runtime"]["configs"][name]
        require(_recorded_relative(recorded_root, actual["path"], label=f"{name} config") == f"{name}.cfg" and
                actual["sha256"] == authority["sha256"], f"M22 canonical runtime {name} config drifted")

    expected_ai = []
    for authority in m20_content["ai_archives"]:
        expected_ai.append((authority["name"], f"content_download/ai/{pathlib.PurePosixPath(authority['path']).name}",
                            authority["sha256"]))
    actual_ai = [(record["name"], _recorded_relative(recorded_root, record["path"], label="AI archive"),
                  record["sha256"]) for record in source["runtime"]["ai_archives"]]
    require(actual_ai == expected_ai, "M22 canonical runtime AI archive inventory drifted")

    expected_libraries = [(f"content_download/ai/library/{pathlib.PurePosixPath(item['path']).name}", item["sha256"])
                          for item in m20_content["libraries"]]
    actual_libraries = [(_recorded_relative(recorded_root, item["path"], label="AI library"), item["sha256"])
                        for item in source["runtime"]["ai_libraries"]]
    require(actual_libraries == expected_libraries, "M22 canonical runtime AI library inventory drifted")

    expected_archives = [(f"{build_name}/{item['archive']['path']}", item["archive"]["bytes"], item["archive"]["sha256"])
                         for item in m21_lock["packages"]]
    actual_archives = [(_recorded_relative(recorded_root, item["path"], label="NewGRF archive"), item["bytes"], item["sha256"])
                       for item in source["runtime"]["newgrf_archives"]]
    require(actual_archives == expected_archives, "M22 canonical runtime NewGRF archive inventory drifted")

    expected_grfs = [(f"{build_name}/newgrf/m21/{item['name']}", item["bytes"], item["sha256"])
                     for item in m21_source["runtime"]["content_files"]]
    actual_grfs = [(_recorded_relative(recorded_root, item["path"], label="staged NewGRF"), item["bytes"], item["sha256"])
                   for item in source["runtime"]["newgrf_files"]]
    require(actual_grfs == expected_grfs, "M22 canonical runtime staged NewGRF inventory drifted")

    expected_scripts = (
        (f"{build_name}/game/m21coverage/info.nut", m21_contract["identities"]["gamescript_info_sha256"]),
        (f"{build_name}/game/m21coverage/main.nut", m21_contract["identities"]["gamescript_main_sha256"]),
    )
    actual_scripts = tuple((_recorded_relative(recorded_root, item["path"], label="GameScript"), item["sha256"])
                           for item in source["runtime"]["gamescript_files"])
    require(actual_scripts == expected_scripts, "M22 canonical runtime GameScript inventory drifted")
    require(source["runtime"]["network_calls_during_preparation"] == "none",
            "M22 canonical runtime network boundary drifted")


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
        require(case_relative == f"smokes/{case_id}", f"M22 smoke artifact path drifted: {case_id}")
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
    require(len(physical) == len(set(physical)), "M22 runtime live-input closure contains duplicate physical inputs")
    require(len(requirements) == EXPECTED_LIVE_INPUTS,
            f"M22 runtime live-input closure must contain exactly {EXPECTED_LIVE_INPUTS} inputs")
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
        require(identity.st_nlink == 1, f"M22 live input is a hard link: {path}")
        key = (identity.st_dev, identity.st_ino)
        require(key not in inodes, f"M22 live inputs alias one file: {inodes.get(key)} and {path}")
        inodes[key] = path
    return resolved


def validate_patch(root: pathlib.Path, record: dict[str, Any]) -> pathlib.Path:
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
    return patch.resolve()


def validate_smokes(source: dict[str, Any]) -> None:
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


def _validate_historical_repository(root: pathlib.Path, source: dict[str, Any]) -> None:
    repository_commit = source["repository"]["commit"]
    require(git(root, "cat-file", "-e", f"{repository_commit}^{{commit}}") == "" and
            git(root, "rev-parse", f"{repository_commit}^{{tree}}") == source["repository"]["tree"],
            "M22 preparation historical repository identity drifted")


def _live_json(path: pathlib.Path, *, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
        require(isinstance(value, dict), f"M22 live {label} JSON root is not an object")
        require(raw == preparation.canonical_bytes(value), f"M22 live {label} is not canonical JSON")
        return value
    except M22RuntimeSourceError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise M22RuntimeSourceError(f"M22 live {label} is malformed: {exc}") from exc


def _expected_smoke_manifest(
    root: pathlib.Path,
    source: dict[str, Any],
    runtime: preparation.native.RuntimePaths,
    case: dict[str, Any],
) -> dict[str, Any]:
    native = preparation.native
    executable_sha = source["executable"]["sha256"]
    probe = native.canonical_probe(case)
    gate = case["source_gate"]
    if gate == "G15":
        return native.m15_request(root, runtime, case, executable_sha)
    if gate == "G16":
        return {"amount": 8, "climate": case["climate"],
                **native.simple_request(case, executable_sha, probe, "openttd-rl-v2-m16-cargo-manifest-1")}
    if gate == "G17":
        return native.simple_request(case, executable_sha, probe, "openttd-rl-v2-m17-rail-manifest-1")
    if gate == "G18":
        return native.simple_request(case, executable_sha, probe, "openttd-rl-v2-m18-ship-manifest-1")
    if gate == "G19":
        return native.simple_request(case, executable_sha, probe, "openttd-rl-v2-m19-air-manifest-1")
    identity_source = {"source": {"tree": source["source"]["tree"]},
                       "executable": {"sha256": executable_sha}}
    if gate == "G20":
        contract = native.m20.load(root / native.m20.CONTRACT)
        identities = native.m20.expected_identities(root, contract)
        roster = next((item for item in contract["roster"] if item["name"] == case["opponent"]), None)
        require(roster is not None and probe == "head_to_head", "M22 live G20 smoke opponent/probe drifted")
        opponent = native.m20.opponent_from(roster, 1, 0)
        native_case = native.m20.Case(
            case["case_id"], probe, 1000, case["seed"], native.derived_seed("competition-simulation", case["seed"]),
            0, 0, (opponent,), "FINAL",
        )
        request = native.m20.manifest(native_case, "final", identities, identity_source,
                                      contract["development_qualification"]["calendar_days"])
        request.update({"run_id": case["case_id"], "split": "final"})
        return request
    require(gate == "G21", f"M22 live smoke gate is unsupported: {gate}")
    contract = native.m21.load(root / native.m21.CONTRACT)
    native_case = {"case_id": case["case_id"], "landscape": case["climate"], "probe": probe, "seed": case["seed"]}
    request = native.m21.manifest(native_case, "final", contract, identity_source,
                                  sha256(root / native.m21.CONTRACT), sha256(root / native.m21.CONTENT_LOCK))
    request["run_id"] = case["case_id"]
    return request


def _report_metrics(root: pathlib.Path, source: dict[str, Any], case: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    native = preparation.native
    executable_sha = source["executable"]["sha256"]
    probe = native.canonical_probe(case)
    gate = case["source_gate"]
    if gate == "G15":
        steps = report.get("steps")
        require(isinstance(steps, list), f"M22 live G15 smoke report steps drifted: {case['case_id']}")
        service = next((step.get("service") for step in steps if isinstance(step, dict) and step.get("operation") == "SERVICE"), None)
        require(isinstance(service, dict) and service["company"]["delivered_passengers"] > 0 and
                service["company"]["income"] > 0 and service["vehicle"]["running"],
                f"M22 live G15 smoke service drifted: {case['case_id']}")
        return {"delivered": service["company"]["delivered_passengers"], "income": service["company"]["income"],
                "ticks": service["ticks"]["executed"], "vehicle_capacity": service["vehicle"]["capacity"]}
    if gate == "G16":
        native_case = native.m16.Case(case["case_id"], case["climate"], case["cargo"], probe, case["seed"])
        native.m16.validate_common(report, native_case, native.m16.load(root / native.m16.CONTRACT), executable_sha)
        native.validate_map(report, case)
        return native.m16.validate_probe(report, native_case)
    if gate == "G17":
        native_case = native.m17.Case(case["case_id"], case["cargo"], probe, case["seed"])
        require(report.get("status") == "PASS" and report.get("executable_sha256") == executable_sha,
                f"M22 live G17 smoke identity/status drifted: {case['case_id']}")
        native.validate_map(report, case)
        return native.m17.validate_probe(report, native_case)
    if gate == "G18":
        native_case = native.m18.Case(case["case_id"], case["cargo"], probe, case["seed"])
        require(report.get("status") == "PASS" and report.get("executable_sha256") == executable_sha,
                f"M22 live G18 smoke identity/status drifted: {case['case_id']}")
        native.validate_map(report, case)
        return native.m18.validate_probe(report, native_case)
    if gate == "G19":
        native_case = native.m19.Case(case["case_id"], case["cargo"], probe, case["seed"])
        require(report.get("status") == "PASS" and report.get("executable_sha256") == executable_sha,
                f"M22 live G19 smoke identity/status drifted: {case['case_id']}")
        native.validate_map(report, case)
        return native.m19.validate_probe(report, native_case)
    if gate == "G20":
        contract = native.m20.load(root / native.m20.CONTRACT)
        identities = native.m20.expected_identities(root, contract)
        require(report.get("status") == "PASS" and report["request"]["split"] == "final" and
                report["identity"] == identities, f"M22 live G20 smoke identity/status drifted: {case['case_id']}")
        result = report["result"]
        public_map, rl = result["policy_input"]["public_map"], result["score"]["rl"]
        require(public_map["width"] == case["map_width"] and public_map["height"] == case["map_height"] and
                result["save_load_public_exact"] and result["privileged_inputs"] == [] and rl["alive"] and
                rl["aircraft"] >= 1 and rl["delivered_cargo_units"] >= 25 and
                len(result["score"]["opponents"]) == 1 and
                result["score"]["opponents"][0]["name"] == case["opponent"],
                f"M22 live G20 smoke result drifted: {case['case_id']}")
        return {"delivered": rl["delivered_cargo_units"], "income": rl["operating_profit"],
                "ticks": contract["development_qualification"]["calendar_days"],
                "company_value": rl["company_value"], "opponent": case["opponent"]}
    require(gate == "G21", f"M22 live smoke gate is unsupported: {gate}")
    native.validate_map(report, case)
    require(report.get("status") == "PASS" and report["request"]["probe"] == probe and
            report["request"]["landscape"] == case["climate"],
            f"M22 live G21 smoke request/status drifted: {case['case_id']}")
    result = report["result"]
    if probe == "calendar":
        require(result["save_load_exact"] and result["span_years"] == 200, "M22 live G21 calendar smoke drifted")
        return {"boundaries": len(result["snapshots"]), "save_load_exact": True}
    if probe == "authority_economy":
        require(result["save_load_exact"] and result["exclusive_rights_expired"], "M22 live G21 authority smoke drifted")
        return {"commands": len(result["commands"]), "save_load_exact": True}
    if probe == "events":
        require(result["save_load_exact"] and result["breakdown"]["observed"] and result["disaster"]["terminated"],
                "M22 live G21 events smoke drifted")
        return {"recovery_ticks": result["breakdown"]["recovery_ticks"], "save_load_exact": True}
    if probe == "gamescript":
        require(result["fixture_name"] == "M21CoverageFixture" and result["save_load_exact"] and
                all(result["responses"].values()), "M22 live G21 GameScript smoke drifted")
        return {"commands": len(result["commands"]), "responses": len(result["responses"]), "save_load_exact": True}
    require(probe == "content" and result["package_count"] == 10 and result["capability_schema_closed"] and
            len(report["active_content"]) == 10 and all(value > 0 for value in result["assets"].values()),
            "M22 live G21 content smoke drifted")
    return {"packages": 10, "capabilities": len(result["capabilities"])}


def _validate_live_files(
    root: pathlib.Path,
    source: dict[str, Any],
    paths: dict[tuple[str, str], pathlib.Path],
    *,
    result_set: str = RESULT_LOGICAL_SET,
    smoke_cases: tuple[dict[str, Any], ...] = preparation.SMOKE_CASES,
) -> None:
    try:
        recorded_root = source["retained_artifact"]
        for label, record in _runtime_file_records(source):
            relative = _recorded_relative(recorded_root, record["path"], label=label)
            path = paths[(result_set, relative)]
            require(path.stat().st_size == record["bytes"], f"M22 {label} byte size drifted")

        executable_relative = _recorded_relative(recorded_root, source["executable"]["path"], label="executable")
        executable = paths[(result_set, executable_relative)]
        require(not executable.is_symlink() and executable.is_file() and executable.stat().st_mode & 0o111 != 0 and
                os.access(executable, os.X_OK), "M22 live executable mode drifted")

        inventory_record = source["build"]["test_inventory"]
        inventory_relative = _recorded_relative(recorded_root, inventory_record["path"], label="CTest inventory")
        inventory = _live_json(paths[(result_set, inventory_relative)], label="CTest inventory")
        require(set(inventory) == {"tests"} and isinstance(inventory["tests"], list) and
                len(inventory["tests"]) == 98 and all(isinstance(name, str) and name for name in inventory["tests"]) and
                len(set(inventory["tests"])) == 98, "M22 live CTest inventory must contain exactly 98 unique names")

        junit_record = source["build"]["logs"]["junit"]
        junit_relative = _recorded_relative(recorded_root, junit_record["path"], label="JUnit")
        try:
            xml = ET.parse(paths[(result_set, junit_relative)]).getroot()
        except (ET.ParseError, OSError, ValueError) as exc:
            raise M22RuntimeSourceError(f"M22 live JUnit XML is malformed: {exc}") from exc
        require(xml.tag in {"testsuite", "testsuites"}, "M22 live JUnit root drifted")
        suites = [xml] if xml.tag == "testsuite" else list(xml.findall("testsuite"))
        require(bool(suites), "M22 live JUnit contains no test suites")
        totals = {key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
                  for key in ("tests", "failures", "errors", "skipped")}
        testcases = [case for suite in suites for case in suite.findall("testcase")]
        testcase_names = [case.attrib.get("name") for case in testcases]
        require(totals == {"tests": 98, "failures": 0, "errors": 0, "skipped": 0} and
                testcase_names == inventory["tests"] and
                all(case.find("failure") is None and case.find("error") is None and case.find("skipped") is None
                    for case in testcases),
                f"M22 live JUnit results drifted: {totals}")

        ctest_record = source["build"]["logs"]["ctest"]
        ctest_relative = _recorded_relative(recorded_root, ctest_record["path"], label="CTest log")
        ctest_text = paths[(result_set, ctest_relative)].read_text(encoding="utf-8")
        require(re.search(r"100% tests passed, 0 tests failed out of 98", ctest_text) is not None,
                "M22 live CTest log totals drifted")
        for name in ("build", "configure"):
            record = source["build"]["logs"][name]
            relative = _recorded_relative(recorded_root, record["path"], label=f"{name} log")
            text = paths[(result_set, relative)].read_text(encoding="utf-8")
            require("\x00" not in text, f"M22 live {name} log is not textual")

        runtime = preparation.native.RuntimePaths(
            executable=executable,
            opengfx=paths[(result_set, _recorded_relative(recorded_root, source["runtime"]["open_gfx"]["path"], label="OpenGFX"))],
            base_config=paths[(result_set, _recorded_relative(recorded_root, source["runtime"]["configs"]["base"]["path"], label="base config"))],
            content_config=paths[(result_set, _recorded_relative(recorded_root, source["runtime"]["configs"]["content"]["path"], label="content config"))],
            gamescript_config=paths[(result_set, _recorded_relative(recorded_root, source["runtime"]["configs"]["gamescript"]["path"], label="gamescript config"))],
            source_tree=source["source"]["tree"],
        )
        for expected, record in zip(smoke_cases, source["smokes"], strict=True):
            case_id = expected["case_id"]
            case_relative = f"smokes/{case_id}"
            require((record["manifest_path"], record["report_path"], record["openttd_log_path"]) ==
                    ("manifest.json", "report.json", "openttd.log"),
                    f"M22 live smoke {case_id} canonical file layout drifted")
            manifest = _live_json(paths[(result_set, f"{case_relative}/manifest.json")],
                                  label=f"smoke {case_id} manifest")
            require(manifest == _expected_smoke_manifest(root, source, runtime, expected),
                    f"M22 live smoke {case_id} manifest semantics drifted")
            report = _live_json(paths[(result_set, f"{case_relative}/report.json")],
                                label=f"smoke {case_id} report")
            require(_report_metrics(root, source, expected, report) == record["metrics"],
                    f"M22 live smoke {case_id} report/metrics drifted")
            log = paths[(result_set, f"{case_relative}/openttd.log")].read_text(encoding="utf-8")
            require("\x00" not in log and "Traceback (most recent call last)" not in log and
                    "M22 native process failed" not in log, f"M22 live smoke {case_id} log semantics drifted")
    except M22RuntimeSourceError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ET.ParseError, KeyError, TypeError, ValueError) as exc:
        raise M22RuntimeSourceError(f"M22 live runtime semantic validation failed: {exc}") from exc


def _validate_live_source(
    source: dict[str, Any],
    patch: pathlib.Path,
    paths: dict[tuple[str, str], pathlib.Path],
) -> None:
    base_source = paths[(BASE_LOGICAL_SET, "source")]
    result_source = paths[(RESULT_LOGICAL_SET, "source")]
    require(git(base_source, "status", "--porcelain") == "", "M22 base source is dirty")
    require(git(base_source, "rev-parse", "HEAD") == source["base"]["commit"] and
            git(base_source, "rev-parse", "HEAD^{tree}") == source["base"]["tree"],
            "M22 base source identity drifted")
    with tempfile.TemporaryDirectory(prefix="openttd-rl-v2-m22-final-source-") as raw:
        target = pathlib.Path(raw) / "source"
        cloned = invoke_git("clone", "-q", "--no-hardlinks", str(base_source), str(target))
        require(cloned.returncode == 0, "cannot clone the accepted M21 source")
        checked = invoke_git("apply", "--check", "--whitespace=error-all", str(patch), repository=target)
        detail = (checked.stdout + checked.stderr).decode("utf-8", errors="replace")
        require(checked.returncode == 0 and not re.search(r"\b(?:offset|fuzz|warning)\b", detail, re.I),
                "M22 final patch does not apply exactly to the accepted M21 source")
        applied = invoke_git("apply", "--index", "--whitespace=error-all", str(patch), repository=target)
        require(applied.returncode == 0, "cannot apply the M22 final patch")
        require(git(target, "write-tree") == source["source"]["tree"], "M22 composed source tree drifted")
    require(git(result_source, "status", "--porcelain") == "", "M22 retained source is dirty")
    require(git(result_source, "rev-parse", "HEAD") == source["source"]["commit"] and
            git(result_source, "rev-parse", "HEAD^{tree}") == source["source"]["tree"],
            "M22 retained source identity drifted")


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
        "m20_source_record_sha256": sha256(root / preparation.M20_SOURCE),
        "m21_source_record_sha256": sha256(root / preparation.M21_SOURCE),
    } and source["base"]["source_record_sha256"] == sha256(root / preparation.M21_SOURCE),
            "M22 runtime prerequisite identity drifted")
    _canonical_runtime(root, source, build_name="build-final")
    contract = load(root / preparation.LEARNING_CONTRACT)
    require(source["final_boundary"] == {
        "expected_manifest_sha256": contract["identities"]["final_evaluation_manifest_sha256"],
        "manifest_executions": 0, "manifest_opened": False,
    }, "M22 final-manifest boundary drifted")
    patch = validate_patch(root, source["patch"])
    require(source["build"]["cmake_arguments"] == list(preparation.CMAKE_ARGUMENTS) and
            source["build"]["upstream_ctest"] == {"passed": 98, "total": 98}, "M22 build contract drifted")
    validate_smokes(source)
    requirements = _requirements(source)
    paths: dict[tuple[str, str], pathlib.Path] = {}
    if context.is_live:
        paths = _preflight_live(context, requirements)
    _validate_historical_repository(root, source)
    if context.is_live:
        _validate_live_source(source, patch, paths)
        _validate_live_files(root, source, paths)
    return {"files": len(source["patch"]["touched_files"]), "live": context.is_live,
            "smokes": len(source["smokes"]), "source_tree": source["source"]["tree"]}


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
        print(f"V2_M22_FINAL_RUNTIME_SOURCE=PASS files={result['files']} smokes={result['smokes']} "
              f"tree={result['source_tree']} live={str(result['live']).lower()}")
        return 0
    except (M22RuntimeSourceError, preparation.M22RuntimePreparationError, SourceContextError,
            ArtifactContextError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_FINAL_RUNTIME_SOURCE=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
