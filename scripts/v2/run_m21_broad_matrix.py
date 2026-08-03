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


CONTRACT = pathlib.Path("config/v2/m21-broad-contract.json")
COVERAGE = pathlib.Path("config/v2/m21-broad-coverage.json")
SOURCE = pathlib.Path("config/v2/m21-broad-source.json")
BASELINE = pathlib.Path("config/v2/research-baseline.json")
CONTENT_LOCK = pathlib.Path("config/v2/m21-content-lock.json")
CONTENT_REQUEST = pathlib.Path("config/v2/m21-content-request.json")
GAMESCRIPT_INFO = pathlib.Path("config/v2/m21-gamescript/info.nut")
GAMESCRIPT_MAIN = pathlib.Path("config/v2/m21-gamescript/main.nut")
REPLICATES = ("a", "b")


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


def validate_runtime(root: pathlib.Path, source: dict[str, Any]) -> tuple[pathlib.Path, dict[str, pathlib.Path]]:
    executable = pathlib.Path(source["executable"]["path"])
    require(executable.is_file() and os.access(executable, os.X_OK), "M21 executable is unavailable")
    require(executable.stat().st_size == source["executable"]["bytes"] and sha256(executable) == source["executable"]["sha256"],
            "M21 executable identity drifted")
    configs: dict[str, pathlib.Path] = {}
    for name, record in source["runtime"]["configs"].items():
        path = pathlib.Path(record["path"])
        require(path.is_file() and sha256(path) == record["sha256"], f"M21 {name} config identity drifted")
        configs[name] = path
    content_root = pathlib.Path(source["runtime"]["content_root"])
    for record in source["runtime"]["content_files"]:
        path = content_root / record["name"]
        require(path.is_file() and path.stat().st_size == record["bytes"] and sha256(path) == record["sha256"],
                f"staged NewGRF identity drifted: {record['name']}")
    gamescript_root = pathlib.Path(source["runtime"]["gamescript_root"])
    require(sha256(gamescript_root / "info.nut") == sha256(root / GAMESCRIPT_INFO) and
            sha256(gamescript_root / "main.nut") == sha256(root / GAMESCRIPT_MAIN), "staged Game Script identity drifted")
    return executable, configs


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


def run_command(executable: pathlib.Path, config: pathlib.Path, request: pathlib.Path, report: pathlib.Path) -> subprocess.CompletedProcess[str]:
    command = [str(executable), "-x", "-X", "-I", "OpenGFX", "-m", "null", "-s", "null", "-v", "null",
               "-c", str(config), "-j", str(request), "-k", str(report)]
    return subprocess.run(command, cwd=executable.parent, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=120, preexec_fn=apply_limits, start_new_session=True)


def run_negative(executable: pathlib.Path, configs: dict[str, pathlib.Path], artifact_root: pathlib.Path,
                 contract: dict[str, Any], source: dict[str, Any], contract_hash: str, content_hash: str) -> list[dict[str, Any]]:
    base_case = {"case_id": "negative", "landscape": "temperate", "probe": "content", "seed": 21999}
    records = []
    for negative in contract["negative_cases"]:
        request = manifest(base_case, "negative", contract, source, contract_hash, content_hash)
        config = configs["content"]
        if negative["mutation"] == "unknown-capability":
            request["expected_capabilities"][-1] = "unknown_vehicle"
            request["expected_newgrfs"] = []
            config = configs["base"]
        elif negative["mutation"] == "unknown-content-id":
            request["expected_newgrfs"] = [{"id": "ffffffff", "md5": contract["newgrfs"][0]["md5"]}]
        else:
            request["schema_version"] = "openttd-rl-v2-m21-broad-run-999"
            request["expected_newgrfs"] = []
            request["expected_capabilities"] = []
            config = configs["base"]
        request["run_id"] = negative["case_id"]
        root = artifact_root / negative["case_id"]
        root.mkdir(mode=0o700)
        request_path, report_path = root / "manifest.json", root / "report.json"
        write_new(request_path, request)
        completed = run_command(executable, config, request_path, report_path)
        (root / "openttd.log").write_text(completed.stdout, encoding="utf-8")
        require(completed.returncode != 0 and negative["diagnostic"] in completed.stdout and not report_path.exists(),
                f"negative case did not fail closed before report/world: {negative['case_id']}")
        records.append({"case_id": negative["case_id"], "diagnostic": negative["diagnostic"], "exit_code": completed.returncode,
                        "log_path": str((root / "openttd.log").relative_to(artifact_root)), "report_absent": True})
    return records


def run_one(executable: pathlib.Path, config: pathlib.Path, artifact_root: pathlib.Path, case: dict[str, Any], replicate: str,
            contract: dict[str, Any], source: dict[str, Any], contract_hash: str, content_hash: str) -> dict[str, Any]:
    root = artifact_root / case["case_id"] / f"replicate-{replicate}"
    root.mkdir(parents=True, mode=0o700)
    request_path, report_path = root / "manifest.json", root / "report.json"
    write_new(request_path, manifest(case, replicate, contract, source, contract_hash, content_hash))
    started = time.monotonic()
    completed = run_command(executable, config, request_path, report_path)
    wall = round(time.monotonic() - started, 6)
    (root / "openttd.log").write_text(completed.stdout, encoding="utf-8")
    require(completed.returncode == 0, f"native run failed {case['case_id']}-{replicate}: {completed.stdout.strip()}")
    report = load(report_path)
    validate_report(report, case, replicate, contract, source, contract_hash, content_hash)
    save = pathlib.Path(str(report_path) + ".sav")
    save_record = None
    if case["probe"] != "content":
        require(save.is_file(), f"save file absent: {case['case_id']}-{replicate}")
        save_record = {"bytes": save.stat().st_size, "sha256": sha256(save)}
    return {"normalized_sha256": hashlib.sha256(normalized(report)).hexdigest(),
            "report_path": str(report_path.relative_to(artifact_root)), "report_sha256": sha256(report_path),
            "save": save_record, "wall_seconds": wall}


def run(root: pathlib.Path, artifact_root: pathlib.Path, evidence_path: pathlib.Path) -> dict[str, Any]:
    root, artifact_root, evidence_path = root.resolve(), artifact_root.resolve(), evidence_path.resolve()
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "artifact root must be new")
    require(not evidence_path.exists() and not evidence_path.is_symlink(), "evidence output must be new")
    contract, coverage, source = load(root / CONTRACT), load(root / COVERAGE), load(root / SOURCE)
    identity = identities(root, contract)
    coverage_summary = validate_coverage(root, contract, coverage)
    executable, configs = validate_runtime(root, source)
    contract_hash, content_hash = sha256(root / CONTRACT), identity["content_lock_sha256"]
    artifact_root.mkdir(mode=0o700)
    negatives = run_negative(executable, configs, artifact_root, contract, source, contract_hash, content_hash)
    cases = []
    maximum_wall = 0.0
    for ordinal, case in enumerate(contract["cases"], 1):
        config = configs["gamescript"] if case["probe"] == "gamescript" else configs["content"] if case["probe"] == "content" else configs["base"]
        replicates = [run_one(executable, config, artifact_root, case, name, contract, source, contract_hash, content_hash)
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
    parser.add_argument("--evidence", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        run(args.root, args.artifact_root, args.evidence)
        return 0
    except (M21MatrixError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"V2_M21_BROAD_MATRIX=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
