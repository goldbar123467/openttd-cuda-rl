#!/usr/bin/env python3
"""Run the complete deterministic M21 broad-feature qualification matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import resource
import subprocess
import time
from typing import Any

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    resolve_artifact_root,
)


CONTRACT = pathlib.Path("config/v2/m21-broad-contract.json")
COVERAGE = pathlib.Path("config/v2/m21-broad-coverage.json")
SOURCE = pathlib.Path("config/v2/m21-broad-source.json")
BASELINE = pathlib.Path("config/v2/research-baseline.json")
CONTENT_LOCK = pathlib.Path("config/v2/m21-content-lock.json")
CONTENT_REQUEST = pathlib.Path("config/v2/m21-content-request.json")
GAMESCRIPT_INFO = pathlib.Path("config/v2/m21-gamescript/info.nut")
GAMESCRIPT_MAIN = pathlib.Path("config/v2/m21-gamescript/main.nut")
REPLICATES = ("a", "b")
RUNTIME_LOGICAL_SET = "v2-m21-broad-a"
RUNTIME_CONSUMER = "m21-broad-runtime"
EXECUTABLE_RELATIVE = "build-broad/openttd"
OPEN_GFX_RELATIVE = "build-broad/baseset/opengfx-8.0.tar"
CONFIG_RELATIVES = {
    "base": "base.cfg",
    "content": "content.cfg",
    "gamescript": "gamescript.cfg",
}
CONTENT_ROOT_RELATIVE = "build-broad/newgrf/m21"
CONTENT_NAMES = (
    "fish.grf", "rattroads.grf", "airports.grf", "stations.grf", "industries.grf",
    "trains.grf", "aircraft.grf", "objects.grf", "tracks.grf", "roadhog.grf",
)
GAMESCRIPT_ROOT_RELATIVE = "build-broad/game/m21coverage"


class M21MatrixError(ValueError):
    """The native M21 matrix violated its frozen contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M21MatrixError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_new(path: pathlib.Path, value: Any) -> None:
    require(not path.exists() and not path.is_symlink(), f"output already exists: {path}")
    path.write_bytes(canonical_bytes(value))


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def apply_limits() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (2_147_483_648, 2_147_483_648))
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))


def normalized(report: dict[str, Any]) -> bytes:
    value = json.loads(json.dumps(report))
    value.pop("run_id")
    value["request"].pop("run_id")
    return canonical_bytes(value)


def identities(root: pathlib.Path, contract: dict[str, Any]) -> dict[str, str]:
    values = {
        "content_lock_sha256": sha256(root / CONTENT_LOCK),
        "content_request_sha256": sha256(root / CONTENT_REQUEST),
        "gamescript_info_sha256": sha256(root / GAMESCRIPT_INFO),
        "gamescript_main_sha256": sha256(root / GAMESCRIPT_MAIN),
        "m20_evidence_sha256": sha256(root / "config/v2/m20-competition-evidence.json"),
    }
    require(values == contract["identities"], "M21 prerequisite identity closure drifted")
    require(sha256(root / BASELINE) == contract["coverage"]["research_baseline_sha256"], "research baseline drifted")
    return values


def validate_coverage(root: pathlib.Path, contract: dict[str, Any], coverage: dict[str, Any]) -> dict[str, int]:
    baseline = load(root / BASELINE)
    feature_expected = [item["id"] for item in baseline["feature_domains"]]
    require([item["feature_id"] for item in coverage["feature_domains"]] == feature_expected, "feature coverage order/content drifted")
    expected_commands: list[tuple[str, str, int]] = []
    occurrences: dict[str, int] = {}
    for disposition in baseline["command_dispositions"]:
        for command in disposition["commands"]:
            occurrences[command] = occurrences.get(command, 0) + 1
            expected_commands.append((disposition["id"], command, occurrences[command]))
    actual_commands = [(item["disposition"], item["command"], item["occurrence"]) for item in coverage["command_dispositions"]]
    require(actual_commands == expected_commands, "command coverage order/content/occurrence drifted")
    require(len(feature_expected) == contract["coverage"]["feature_domains"] == 18, "feature count drifted")
    require(len(expected_commands) == contract["coverage"]["command_dispositions"] == 145, "command count drifted")
    valid_proofs = {
        "accepted-foundation-for-future-stage", "accepted-prior-gate-regression", "m21-native-and-contract",
        "native-policy-command", "bounded-higher-level-policy-transaction", "native-company-script-response",
        "native-safe-presentation-command", "deliberate-presentation-only-proof", "native-admin-fixture-only",
        "admin-denied-from-policy",
    }
    for item in coverage["feature_domains"] + coverage["command_dispositions"]:
        require(item["proof_kind"] in valid_proofs, f"unknown proof kind: {item['proof_kind']}")
        require(item["evidence"] and any((root / path).is_file() for path in item["evidence"]),
                f"coverage row has no present evidence: {item}")
    for item in coverage["command_dispositions"]:
        if item["proof_kind"] == "deliberate-presentation-only-proof":
            require(item["disposition"] == "policy-optional", "presentation-only proof escaped optional disposition")
        if item["proof_kind"] == "admin-denied-from-policy":
            require(item["disposition"] == "benchmark-admin", "admin denial escaped admin disposition")
    return {"commands": len(expected_commands), "features": len(feature_expected)}


def _recorded_runtime_relative(source: dict[str, Any], recorded_path: str, *, label: str) -> str:
    recorded_root = source["retained_artifact"]
    root = pathlib.PurePosixPath(recorded_root)
    path = pathlib.PurePosixPath(recorded_path)
    require(isinstance(recorded_path, str) and recorded_path.startswith("/") and not recorded_path.startswith("//") and
            str(path) == recorded_path and all(part not in {"", ".", ".."} for part in path.parts[1:]),
            f"recorded M21 {label} path is not an absolute normalized POSIX path")
    require(root.name == RUNTIME_LOGICAL_SET, "M21 retained artifact logical set drifted")
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise M21MatrixError(f"recorded M21 {label} path escaped retained artifact") from exc
    require(str(relative) != ".", f"recorded M21 {label} path must be below retained artifact")
    return str(relative)


def required_runtime_inputs(root: pathlib.Path, source: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    recorded_root = source["retained_artifact"]
    recorded = pathlib.PurePosixPath(recorded_root)
    require(isinstance(recorded_root, str) and recorded_root.startswith("/") and not recorded_root.startswith("//") and
            str(recorded) == recorded_root and all(part not in {"", ".", ".."} for part in recorded.parts[1:]) and
            recorded.name == RUNTIME_LOGICAL_SET, "M21 retained artifact logical set drifted")
    require(tuple(source["runtime"]["configs"]) == tuple(CONFIG_RELATIVES), "M21 runtime config inventory drifted")
    require(_recorded_runtime_relative(source, source["executable"]["path"], label="executable") == EXECUTABLE_RELATIVE,
            "M21 executable path drifted")
    require(_recorded_runtime_relative(source, source["build"]["open_gfx"]["path"], label="OpenGFX") == OPEN_GFX_RELATIVE,
            "M21 OpenGFX path drifted")
    config_paths = tuple(
        _recorded_runtime_relative(source, source["runtime"]["configs"][name]["path"], label=f"{name} config")
        for name in CONFIG_RELATIVES
    )
    require(len(config_paths) == len(set(config_paths)), "M21 runtime config inventory contains duplicates")
    requirements = [
        ArtifactRequirement(RUNTIME_LOGICAL_SET, EXECUTABLE_RELATIVE,
                            "file", RUNTIME_CONSUMER, source["executable"]["sha256"]),
        ArtifactRequirement(RUNTIME_LOGICAL_SET, OPEN_GFX_RELATIVE,
                            "file", RUNTIME_CONSUMER, source["build"]["open_gfx"]["sha256"]),
    ]
    for (name, relative), recorded_relative in zip(CONFIG_RELATIVES.items(), config_paths, strict=True):
        record = source["runtime"]["configs"][name]
        require(recorded_relative == relative, f"M21 {name} config path drifted")
        requirements.append(ArtifactRequirement(
            RUNTIME_LOGICAL_SET,
            relative,
            "file",
            RUNTIME_CONSUMER,
            record["sha256"],
        ))
    content_root = _recorded_runtime_relative(source, source["runtime"]["content_root"], label="content root")
    require(content_root == CONTENT_ROOT_RELATIVE, "M21 content root path drifted")
    content_names = tuple(record["name"] for record in source["runtime"]["content_files"])
    require(len(content_names) == len(set(content_names)), "duplicate physical runtime input")
    require(content_names == CONTENT_NAMES, "M21 content inventory drifted")
    for record, name in zip(source["runtime"]["content_files"], CONTENT_NAMES, strict=True):
        requirements.append(ArtifactRequirement(
            RUNTIME_LOGICAL_SET,
            f"{CONTENT_ROOT_RELATIVE}/{name}",
            "file",
            RUNTIME_CONSUMER,
            record["sha256"],
        ))
    gamescript_root = _recorded_runtime_relative(source, source["runtime"]["gamescript_root"], label="Game Script root")
    require(gamescript_root == GAMESCRIPT_ROOT_RELATIVE, "M21 Game Script root path drifted")
    requirements.extend((
        ArtifactRequirement(RUNTIME_LOGICAL_SET, f"{GAMESCRIPT_ROOT_RELATIVE}/info.nut", "file", RUNTIME_CONSUMER, sha256(root / GAMESCRIPT_INFO)),
        ArtifactRequirement(RUNTIME_LOGICAL_SET, f"{GAMESCRIPT_ROOT_RELATIVE}/main.nut", "file", RUNTIME_CONSUMER, sha256(root / GAMESCRIPT_MAIN)),
    ))
    physical_keys = [(item.logical_set, item.relative_path, item.kind) for item in requirements]
    require(len(physical_keys) == len(set(physical_keys)), "duplicate physical runtime input")
    require(len(requirements) == 17, "M21 runtime input inventory must contain exactly 17 physical inputs")
    return tuple(requirements)


def expected_runtime_paths(runtime_root: pathlib.Path) -> dict[str, pathlib.Path]:
    return {
        "executable": runtime_root / EXECUTABLE_RELATIVE,
        "open_gfx": runtime_root / OPEN_GFX_RELATIVE,
        **{f"config:{name}": runtime_root / relative for name, relative in CONFIG_RELATIVES.items()},
        **{f"content:{name}": runtime_root / CONTENT_ROOT_RELATIVE / name for name in CONTENT_NAMES},
        "gamescript:info.nut": runtime_root / GAMESCRIPT_ROOT_RELATIVE / "info.nut",
        "gamescript:main.nut": runtime_root / GAMESCRIPT_ROOT_RELATIVE / "main.nut",
    }


def validate_execution_layout(runtime_root: pathlib.Path, named_paths: dict[str, pathlib.Path]) -> None:
    expected = expected_runtime_paths(runtime_root)
    require(set(named_paths) == set(expected), "M21 runtime named-path inventory drifted")
    for name, expected_path in expected.items():
        require(named_paths[name] == expected_path, f"M21 runtime discovery path drifted: {name}")


def validate_runtime(root: pathlib.Path, source: dict[str, Any], artifact_context: ArtifactContext) -> tuple[pathlib.Path, dict[str, pathlib.Path]]:
    requirements = required_runtime_inputs(root, source)
    artifact_context.preflight(requirements)
    paths = {item.relative_path: artifact_context.resolve(item) for item in requirements}
    runtime_root = artifact_context.artifact_set(RUNTIME_LOGICAL_SET)
    executable_relative = _recorded_runtime_relative(source, source["executable"]["path"], label="executable")
    executable = paths[executable_relative]
    require(executable.is_file() and os.access(executable, os.X_OK), "M21 executable is unavailable")
    require(executable.stat().st_size == source["executable"]["bytes"] and sha256(executable) == source["executable"]["sha256"],
            "M21 executable identity drifted")
    named_paths: dict[str, pathlib.Path] = {"executable": executable}
    open_gfx_relative = _recorded_runtime_relative(source, source["build"]["open_gfx"]["path"], label="OpenGFX")
    open_gfx = paths[open_gfx_relative]
    require(open_gfx.stat().st_size == source["build"]["open_gfx"]["bytes"] and sha256(open_gfx) == source["build"]["open_gfx"]["sha256"],
            "M21 OpenGFX identity drifted")
    named_paths["open_gfx"] = open_gfx
    for name, record in source["runtime"]["configs"].items():
        path = paths[_recorded_runtime_relative(source, record["path"], label=f"{name} config")]
        require(path.is_file() and sha256(path) == record["sha256"], f"M21 {name} config identity drifted")
        named_paths[f"config:{name}"] = path
    content_root = _recorded_runtime_relative(source, source["runtime"]["content_root"], label="content root")
    for record in source["runtime"]["content_files"]:
        path = paths[f"{content_root}/{record['name']}"]
        require(path.is_file() and path.stat().st_size == record["bytes"] and sha256(path) == record["sha256"],
                f"staged NewGRF identity drifted: {record['name']}")
        named_paths[f"content:{record['name']}"] = path
    gamescript_root = _recorded_runtime_relative(source, source["runtime"]["gamescript_root"], label="Game Script root")
    info = paths[f"{gamescript_root}/info.nut"]
    main = paths[f"{gamescript_root}/main.nut"]
    require(sha256(info) == sha256(root / GAMESCRIPT_INFO) and sha256(main) == sha256(root / GAMESCRIPT_MAIN),
            "staged Game Script identity drifted")
    named_paths["gamescript:info.nut"] = info
    named_paths["gamescript:main.nut"] = main
    validate_execution_layout(runtime_root, named_paths)
    return runtime_root, named_paths


def manifest(case: dict[str, Any], replicate: str, contract: dict[str, Any], source: dict[str, Any],
             contract_sha256: str, content_lock_sha256: str) -> dict[str, Any]:
    content = case["probe"] == "content"
    return {
        "content_lock_sha256": content_lock_sha256,
        "contract_sha256": contract_sha256,
        "engine_source_tree": source["source"]["tree"],
        "executable_sha256": source["executable"]["sha256"],
        "expected_capabilities": list(contract["capabilities"]) if content else [],
        "expected_newgrfs": [dict(item) for item in contract["newgrfs"]] if content else [],
        "landscape": case["landscape"],
        "probe": case["probe"],
        "require_gamescript": case["probe"] == "gamescript",
        "run_id": f"{case['case_id']}-{replicate}",
        "schema_version": "openttd-rl-v2-m21-broad-run-1",
        "seed": case["seed"],
    }


def validate_report(report: dict[str, Any], case: dict[str, Any], replicate: str, contract: dict[str, Any],
                    source: dict[str, Any], contract_sha256: str, content_lock_sha256: str) -> None:
    run_id = f"{case['case_id']}-{replicate}"
    require(report["schema_version"] == "openttd-rl-v2-m21-broad-report-1" and report["status"] == "PASS", f"failed report: {run_id}")
    require(report["run_id"] == run_id and report["request"] == {"landscape": case["landscape"], "probe": case["probe"],
            "run_id": run_id, "seed": case["seed"]}, f"request projection drifted: {run_id}")
    require(report["engine_source_tree"] == source["source"]["tree"] and
            report["executable_sha256"] == source["executable"]["sha256"], f"source projection drifted: {run_id}")
    require(report["identity"] == {"content_lock_sha256": content_lock_sha256, "contract_sha256": contract_sha256},
            f"contract/content projection drifted: {run_id}")
    result = report["result"]
    probe = case["probe"]
    if probe == "calendar":
        require(result["save_load_exact"] and result["span_years"] == 200 and result["cargo_count"] > 0,
                f"calendar state is vacuous: {run_id}")
        snapshots = result["snapshots"]
        require([item["year"] for item in snapshots] == [1900, 1930, 1950, 1980, 2000, 2050, 2100],
                f"calendar boundaries drifted: {run_id}")
        series = [(item["airport_available"], tuple((key, value["available"], value["expired"])
                  for key, value in sorted(item["engines"].items()))) for item in snapshots]
        require(len(set(series)) > 1, f"calendar availability/expiry series is constant: {run_id}")
    elif probe == "authority_economy":
        economy = result["economy"]
        statuses = {item["command"]: item["status"] for item in result["commands"]}
        require(result["save_load_exact"] and result["exclusive_rights_expired"] and result["subsidy"]["awarded_months"] == 12,
                f"authority lifecycle failed: {run_id}")
        require(statuses["CMD_TOWN_RATING"] == "SUCCESS" and statuses["CMD_TOWN_RATING_INVALID"] == "REJECTED" and
                statuses["CMD_DO_TOWN_ACTION_COMPETITOR"] == "REJECTED", f"authority positive/negative paths drifted: {run_id}")
        require(economy["inflation_after"] > economy["inflation_before"] and economy["price_after"] >= economy["price_before"] and
                economy["payment_after"] >= economy["payment_before"] and economy["recession_fluct"] <= 0 < economy["recovered_fluct"],
                f"economy transition failed: {run_id}")
    elif probe == "events":
        require(result["save_load_exact"] and result["breakdown"]["disabled_no_event"] and result["breakdown"]["observed"] and
                0 < result["breakdown"]["recovery_ticks"] <= 32 and result["disaster"]["disabled_no_event"] and
                result["disaster"]["terminated"] and 0 < result["disaster"]["lifecycle_ticks"] <= 8,
                f"event/recovery semantics failed: {run_id}")
    elif probe == "gamescript":
        require(result["fixture_name"] == "M21CoverageFixture" and result["save_load_exact"] and
                result["responses"] == {"goal_question": True, "story_button": True} and len(result["commands"]) == 13 and
                all(item["status"] == "SUCCESS" for item in result["commands"]) and all(value == 1 for value in result["observed"].values()),
                f"Game Script semantics failed: {run_id}")
    else:
        require(probe == "content" and result["package_count"] == 10 and result["capability_schema_closed"] and
                not result["arbitrary_newgrf_universality"] and result["capabilities"] == contract["capabilities"],
                f"content contract failed: {run_id}")
        require(len(report["active_content"]) == 10 and
                [(item["id"], item["md5"]) for item in report["active_content"]] == [(item["id"], item["md5"]) for item in contract["newgrfs"]],
                f"runtime NewGRF identities drifted: {run_id}")
        require(all(value > 0 for value in result["assets"].values()), f"content capability projection is vacuous: {run_id}")


def run_command(runtime_root: pathlib.Path, runtime_paths: dict[str, pathlib.Path], config_name: str,
                request: pathlib.Path, report: pathlib.Path) -> subprocess.CompletedProcess[str]:
    validate_execution_layout(runtime_root, runtime_paths)
    require(config_name in CONFIG_RELATIVES, f"unknown M21 runtime config: {config_name}")
    executable = runtime_paths["executable"]
    config = runtime_paths[f"config:{config_name}"]
    command = [str(executable), "-x", "-X", "-I", "OpenGFX", "-m", "null", "-s", "null", "-v", "null",
               "-c", str(config), "-j", str(request), "-k", str(report)]
    return subprocess.run(command, cwd=runtime_root / "build-broad", text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=120, preexec_fn=apply_limits, start_new_session=True)


def run_negative(runtime_root: pathlib.Path, runtime_paths: dict[str, pathlib.Path], artifact_root: pathlib.Path,
                 contract: dict[str, Any], source: dict[str, Any], contract_hash: str, content_hash: str) -> list[dict[str, Any]]:
    base_case = {"case_id": "negative", "landscape": "temperate", "probe": "content", "seed": 21999}
    records = []
    for negative in contract["negative_cases"]:
        request = manifest(base_case, "negative", contract, source, contract_hash, content_hash)
        config_name = "content"
        if negative["mutation"] == "unknown-capability":
            request["expected_capabilities"][-1] = "unknown_vehicle"
            request["expected_newgrfs"] = []
            config_name = "base"
        elif negative["mutation"] == "unknown-content-id":
            request["expected_newgrfs"] = [{"id": "ffffffff", "md5": contract["newgrfs"][0]["md5"]}]
        else:
            request["schema_version"] = "openttd-rl-v2-m21-broad-run-999"
            request["expected_newgrfs"] = []
            request["expected_capabilities"] = []
            config_name = "base"
        request["run_id"] = negative["case_id"]
        root = artifact_root / negative["case_id"]
        root.mkdir(mode=0o700)
        request_path, report_path = root / "manifest.json", root / "report.json"
        write_new(request_path, request)
        completed = run_command(runtime_root, runtime_paths, config_name, request_path, report_path)
        (root / "openttd.log").write_text(completed.stdout, encoding="utf-8")
        require(completed.returncode != 0 and negative["diagnostic"] in completed.stdout and
                not report_path.exists() and not report_path.is_symlink(),
                f"negative case did not fail closed before report/world: {negative['case_id']}")
        records.append({"case_id": negative["case_id"], "diagnostic": negative["diagnostic"], "exit_code": completed.returncode,
                        "log_path": str((root / "openttd.log").relative_to(artifact_root)), "report_absent": True})
    return records


def run_one(runtime_root: pathlib.Path, runtime_paths: dict[str, pathlib.Path], config_name: str,
            artifact_root: pathlib.Path, case: dict[str, Any], replicate: str,
            contract: dict[str, Any], source: dict[str, Any], contract_hash: str, content_hash: str) -> dict[str, Any]:
    root = artifact_root / case["case_id"] / f"replicate-{replicate}"
    root.mkdir(parents=True, mode=0o700)
    request_path, report_path = root / "manifest.json", root / "report.json"
    write_new(request_path, manifest(case, replicate, contract, source, contract_hash, content_hash))
    started = time.monotonic()
    completed = run_command(runtime_root, runtime_paths, config_name, request_path, report_path)
    wall = round(time.monotonic() - started, 6)
    (root / "openttd.log").write_text(completed.stdout, encoding="utf-8")
    require(completed.returncode == 0, f"native run failed {case['case_id']}-{replicate}: {completed.stdout.strip()}")
    report = load(report_path)
    validate_report(report, case, replicate, contract, source, contract_hash, content_hash)
    save = pathlib.Path(str(report_path) + ".sav")
    save_record = None
    if case["probe"] == "content":
        require(not save.exists() and not save.is_symlink(),
                f"content case unexpectedly retained a save: {case['case_id']}-{replicate}")
    else:
        require(save.is_file() and not save.is_symlink(),
                f"save file absent or unsafe: {case['case_id']}-{replicate}")
        save_record = {"bytes": save.stat().st_size, "sha256": sha256(save)}
    return {"normalized_sha256": hashlib.sha256(normalized(report)).hexdigest(),
            "report_path": str(report_path.relative_to(artifact_root)), "report_sha256": sha256(report_path),
            "save": save_record, "wall_seconds": wall}


def run(root: pathlib.Path, artifact_root: pathlib.Path, evidence_path: pathlib.Path, *,
        artifact_context: ArtifactContext) -> dict[str, Any]:
    root, artifact_root, evidence_path = root.resolve(), artifact_root.resolve(), evidence_path.resolve()
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "artifact root must be new")
    require(not evidence_path.exists() and not evidence_path.is_symlink(), "evidence output must be new")
    contract, coverage, source = load(root / CONTRACT), load(root / COVERAGE), load(root / SOURCE)
    identity = identities(root, contract)
    coverage_summary = validate_coverage(root, contract, coverage)
    runtime_root, runtime_paths = validate_runtime(root, source, artifact_context)
    validate_execution_layout(runtime_root, runtime_paths)
    contract_hash, content_hash = sha256(root / CONTRACT), identity["content_lock_sha256"]
    artifact_root.mkdir(mode=0o700)
    negatives = run_negative(runtime_root, runtime_paths, artifact_root, contract, source, contract_hash, content_hash)
    cases = []
    maximum_wall = 0.0
    for ordinal, case in enumerate(contract["cases"], 1):
        config_name = "gamescript" if case["probe"] == "gamescript" else "content" if case["probe"] == "content" else "base"
        replicates = [run_one(runtime_root, runtime_paths, config_name, artifact_root, case, name,
                              contract, source, contract_hash, content_hash)
                      for name in REPLICATES]
        require(replicates[0]["normalized_sha256"] == replicates[1]["normalized_sha256"], f"exact twin drifted: {case['case_id']}")
        if replicates[0]["save"] is not None:
            require(replicates[0]["save"] == replicates[1]["save"], f"save twin drifted: {case['case_id']}")
        maximum_wall = max(maximum_wall, *(item["wall_seconds"] for item in replicates))
        cases.append({**case, "replicates": [{"name": name, **record} for name, record in zip(REPLICATES, replicates, strict=True)],
                      "twin_exact": True})
        print(f"M21 case {ordinal:02d}/{len(contract['cases'])} PASS {case['case_id']}", flush=True)
    evidence = {
        "aggregate": {"cases": len(cases), "command_dispositions": coverage_summary["commands"],
                      "exact_twins": len(cases), "feature_domains": coverage_summary["features"],
                      "maximum_wall_seconds": round(maximum_wall, 6), "native_runs": len(cases) * 2,
                      "negative_cases": len(negatives)},
        "artifact_root": str(artifact_root), "cases": cases, "contract_sha256": contract_hash,
        "coverage_sha256": sha256(root / COVERAGE), "execution": {"fresh_process_per_run": True, "network_calls": "none",
            "process_limits": True, "sandbox": "rlimit-only"}, "executable_sha256": source["executable"]["sha256"],
        "identities": identity, "negative_cases": negatives, "schema_version": "openttd-rl-v2-m21-broad-evidence-1",
        "source_sha256": sha256(root / SOURCE), "status": "PASS",
    }
    write_new(evidence_path, evidence)
    print(f"V2_M21_BROAD_MATRIX=PASS cases={len(cases)} native_runs={len(cases) * 2} twins={len(cases)} negatives={len(negatives)}")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--runtime-artifact-root", type=pathlib.Path)
    parser.add_argument("--evidence", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        runtime_root = resolve_artifact_root(args.runtime_artifact_root)
        if runtime_root is None:
            parser.error("M21 runtime artifact root is required via --runtime-artifact-root or OPENTTD_RL_ARTIFACT_ROOT")
        run(args.root, args.artifact_root, args.evidence, artifact_context=ArtifactContext.live(runtime_root))
        return 0
    except (M21MatrixError, ArtifactContextError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"V2_M21_BROAD_MATRIX=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
