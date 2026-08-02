#!/usr/bin/env python3
"""Run deterministic twin-process M17 rail qualification."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import pathlib
import resource
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any


CONTRACT = pathlib.Path("config/v2/m17-rail-contract.json")
SOURCE = pathlib.Path("config/v2/m17-rail-source.json")
RUNTIME = pathlib.Path("config/v2/opponent-runtime-evidence.json")
TWINS = ("a", "b")
PROBES = (
    ("catalog", "PASS"),
    ("construction", "PASS"),
    ("signals", "PASS"),
    ("lifecycle", "PASS"),
    ("passenger", "PASS"),
    ("freight", "COAL"),
    ("stress", "PASS"),
)


class M17MatrixError(ValueError):
    """The native M17 matrix violated its frozen contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M17MatrixError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_new(path: pathlib.Path, value: Any) -> None:
    require(not path.exists() and not path.is_symlink(), f"output already exists: {path}")
    path.write_bytes(canonical_bytes(value))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_for(case_id: str, ordinal: int) -> int:
    return int.from_bytes(hashlib.sha256(f"m17:{case_id}:{ordinal}".encode()).digest()[:4], "big")


@dataclass(frozen=True)
class Case:
    case_id: str
    cargo: str
    probe: str
    seed: int


def cases(_contract: dict[str, Any]) -> list[Case]:
    result: list[Case] = []
    for probe, cargo in PROBES:
        for ordinal in range(2):
            case_id = f"{probe}-s{ordinal}"
            result.append(Case(case_id, cargo, probe, seed_for(case_id, ordinal)))
    return result


def apply_limits() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (1_073_741_824, 1_073_741_824))
    resource.setrlimit(resource.RLIMIT_CPU, (90, 90))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))


def normalized(report: dict[str, Any]) -> bytes:
    value = json.loads(json.dumps(report))
    value.pop("run_id")
    value["request"].pop("run_id")
    return canonical_bytes(value)


def command(executable: pathlib.Path, run: pathlib.Path, sandbox: str) -> list[str]:
    direct = [
        str(executable), "-x", "-X", "-Q", "-I", "OpenGFX", "-m", "null", "-s", "null", "-v", "null",
        "-C", str(run / "manifest.json"), "-P", str(run / "report.json"),
    ]
    if sandbox == "test-none":
        return direct
    require(sandbox == "bubblewrap" and shutil.which("bwrap") is not None, "bubblewrap is unavailable")
    return [
        "bwrap", "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-net",
        "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--bind", str(run), str(run),
        "--chdir", str(executable.parent), "--", *direct,
    ]


def command_statuses(probe: dict[str, Any], name: str) -> list[str]:
    return [item["status"] for item in probe.get("commands", []) if item["command"] == name]


def validate_common(report: dict[str, Any], case: Case, contract: dict[str, Any], executable_sha: str) -> None:
    require(report["schema_version"] == "openttd-rl-v2-m17-rail-report-1" and report["status"] == "PASS", f"report failed: {case.case_id}")
    require(report["executable_sha256"] == executable_sha and report["request"]["probe"] == case.probe, f"identity drift: {case.case_id}")
    require(report["request"]["cargo_label"] == case.cargo and report["request"]["seed"] == case.seed, f"request drift: {case.case_id}")
    require(report["map"] == {"height": 64, "width": 64}, f"map drift: {case.case_id}")
    catalog = report["catalog"]
    counts = contract["counts"]
    require(len(catalog["railtypes"]) == counts["rail_types"] == 4, f"rail-type inventory drift: {case.case_id}")
    require(len(catalog["engines"]) == counts["train_engine_entries"] == 116, f"engine inventory drift: {case.case_id}")
    require(catalog["track_orientations"] == contract["semantics"]["track_orientations"], f"orientation inventory drift: {case.case_id}")
    require(catalog["signal_types"] == contract["semantics"]["signal_types"], f"signal inventory drift: {case.case_id}")


def validate_probe(report: dict[str, Any], case: Case) -> dict[str, int]:
    probe = report["probe"]
    if case.probe == "catalog":
        require(probe == {"status": "CATALOG_ONLY"}, f"catalog probe drift: {case.case_id}")
        return {"income": 0, "delivered": 0, "ticks": 0}
    if case.probe == "construction":
        require(probe["crossing"] and probe["junction"] and probe["foreign_owner_rejected"] and probe["waypoint_roundtrip"], "construction topology/lifecycle failed")
        require([item["name"] for item in probe["orientations"]] == ["x", "y", "upper", "lower", "left", "right"] and all(item["removed"] for item in probe["orientations"]), "track orientation roundtrip failed")
        station = probe["station"]
        require(station["footprint"] == {"height": 1, "tile": 2056, "width": 2} and station["platform_length"] == 2 and station["catchment_radius"] == 4 and station["removed_roundtrip"], "station projection/removal failed")
        require(probe["observations"] == {"junction_track_bits": 37, "level_crossing": True, "rail_crossing_track_bits": 3, "slope": 8}, "construction observation projection failed")
        require(command_statuses(probe, "CMD_BUILD_RAIL_INVALID_TYPE") == ["REJECTED"] and command_statuses(probe, "CMD_REMOVE_RAIL_FOREIGN_OWNER") == ["REJECTED"], "invalid/ownership failure semantics drifted")
        require(command_statuses(probe, "CMD_REMOVE_FROM_RAIL_STATION") == ["SUCCESS"], "station removal command missing")
        return {"income": 0, "delivered": 0, "ticks": 0}
    if case.probe == "signals":
        variants = {(item["type"], item["variant"], item["name"]) for item in probe["signals"]}
        expected = {(index, variant, name) for index, name in enumerate(("block", "entry", "exit", "combo", "path", "path-one-way")) for variant in (0, 1)}
        require(variants == expected and len(probe["signals"]) == 12, "signal type/variant coverage drifted")
        require({item["present_bits"] for item in probe["signals"]} == {4, 8, 12}, "signal direction coverage drifted")
        require(command_statuses(probe, "CMD_REMOVE_SIGNAL") == ["SUCCESS"] * 12, "signal removal roundtrips failed")
        require(probe["reservation"] == {"duplicate_rejected": True, "released": True, "reserved": True}, "reservation transitions failed")
        return {"income": 0, "delivered": 0, "ticks": 0}
    if case.probe == "lifecycle":
        require(probe["clone_and_sale"] and probe["consist_capacity"] > 0 and probe["orders"] == 2 and probe["service_interval"] == 120, "train lifecycle failed")
        require(probe["timetable"] == {"speed": 96, "travel": 256, "wait": 64}, "timetable transition failed")
        require(probe["order_flags"] == {"invalid_rejected": True, "load": True, "non_stop": True, "stop_location": True, "unload": True}, "station order flag coverage failed")
        require(probe["save_load"]["restored"] is True and probe["save_load"]["bytes"] > 0, "native rail save/load restoration failed")
        require(all(probe["safety_fixture"].values()), "lost/collision positive-negative fixture failed")
        require(probe["replacement"]["configured"] and probe["replacement"]["executed"] and probe["replacement"]["from_engine"] != probe["replacement"]["to_engine"], "autoreplace transition failed")
        for name in ("CMD_CLONE_VEHICLE", "CMD_SET_AUTOREPLACE", "CMD_AUTOREPLACE_VEHICLE", "CMD_CLEAR_AUTOREPLACE", "CMD_SELL_VEHICLE"):
            require("SUCCESS" in command_statuses(probe, name), f"lifecycle command missing: {name}")
        return {"income": 0, "delivered": 0, "ticks": 0}
    if case.probe in ("passenger", "freight"):
        accounting, safety = probe["accounting"], probe["safety"]
        require(accounting["delivered"] > 0 and accounting["income"] > 0 and probe["ticks"] < 131072, f"unprofitable rail service: {case.case_id}")
        require(safety["crashed"] is False and safety["stuck"] is False and safety["maximum_wait"] < 4096, f"unsafe rail service: {case.case_id}")
        require(case.cargo == ("PASS" if case.probe == "passenger" else "COAL"), f"service cargo drift: {case.case_id}")
        return {"income": accounting["income"], "delivered": accounting["delivered"], "ticks": probe["ticks"]}
    require(case.probe == "stress", f"unknown probe: {case.probe}")
    require(probe["trains"] == 2 and probe["signals"] == 2 and probe["shared_station"] is False and
            probe["shared_destination"] is True and probe["shared_physical_network"] is True and
            probe["junction_connectors"] == 1 and probe["terminal_stations"] == 3, "stress topology drifted")
    require(probe["delivered"] > 0 and probe["income"] > 0 and 32768 <= probe["ticks"] < 131072 and probe["maximum_wait"] < 4096, "stress service/deadlock bound failed")
    require(probe["unresolved_deadlock"] is False and probe["unexplained_collision"] is False, "stress safety failed")
    return {"income": probe["income"], "delivered": probe["delivered"], "ticks": probe["ticks"]}


def run_one(executable: pathlib.Path, artifact_root: pathlib.Path, case: Case, twin: str, executable_sha: str, sandbox: str) -> dict[str, Any]:
    run = artifact_root / case.case_id / f"twin-{twin}"
    run.mkdir(parents=True, mode=0o700)
    run_id = f"{case.case_id}-{twin}"
    manifest = {
        "cargo_label": case.cargo,
        "executable_sha256": executable_sha,
        "probe": case.probe,
        "run_id": run_id,
        "schema_version": "openttd-rl-v2-m17-rail-manifest-1",
        "seed": case.seed,
    }
    write_new(run / "manifest.json", manifest)
    started = time.monotonic()
    result = subprocess.run(command(executable, run, sandbox), cwd=executable.parent, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=120, preexec_fn=apply_limits, start_new_session=True)
    wall = time.monotonic() - started
    (run / "openttd.log").write_text(result.stdout, encoding="utf-8")
    require(result.returncode == 0, f"native run failed ({result.returncode}) {run}: {result.stdout.strip()}")
    report = load(run / "report.json")
    return {
        "case": case,
        "twin": twin,
        "report": report,
        "report_sha256": sha256_file(run / "report.json"),
        "normalized_sha256": sha256_bytes(normalized(report)),
        "wall_seconds": wall,
        "report_path": str((run / "report.json").relative_to(artifact_root)),
    }


def baseline_evidence(root: pathlib.Path, contract: dict[str, Any]) -> dict[str, Any]:
    runtime = load(root / RUNTIME)
    specialist = next(item for item in runtime["results"] if item["name"] == "AAAHogEx")
    rejected = next(item for item in runtime["results"] if item["name"] == "ChooChoo")
    frozen = contract["baseline"]
    require(specialist["outcome"] == "QUALIFIED_ACTIVE" and specialist["admission"] == "TOURNAMENT" and specialist["vehicles"]["train"] >= 1, "AAAHogEx rail baseline is not qualified")
    require(specialist["evidence_sha256"] == frozen["specialist"]["evidence_sha256"], "AAAHogEx evidence identity drifted")
    require(rejected["outcome"] == "PACKAGE_REJECTED" and rejected["reason_code"] == frozen["rejected_preferred_specialist"]["reason_code"], "ChooChoo rejection drifted")
    return {
        "specialist_qualified": True,
        "specialist_name": "AAAHogEx",
        "specialist_runtime_evidence_sha256": specialist["evidence_sha256"],
        "choochoo_rejection_retained": True,
        "passenger_beats_zero_service": True,
        "freight_beats_zero_service": True,
    }


def run(root: pathlib.Path, artifact_root: pathlib.Path, evidence_path: pathlib.Path, sandbox: str, workers: int) -> dict[str, Any]:
    root, artifact_root, evidence_path = root.resolve(), artifact_root.resolve(), evidence_path.resolve()
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "artifact root must be a new path")
    require(not evidence_path.exists() and not evidence_path.is_symlink(), "evidence output must be a new path")
    contract, source = load(root / CONTRACT), load(root / SOURCE)
    executable = pathlib.Path(source["executable"]["path"])
    require(executable.is_file() and os.access(executable, os.X_OK), "M17 executable is unavailable")
    executable_sha = sha256_file(executable)
    require(executable_sha == source["executable"]["sha256"] and executable.stat().st_size == source["executable"]["bytes"], "M17 executable identity drifted")
    artifact_root.mkdir(mode=0o700)
    all_cases = cases(contract)
    jobs = [(case, twin) for case in all_cases for twin in TWINS]
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_one, executable, artifact_root, case, twin, executable_sha, sandbox) for case, twin in jobs]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    by_case: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        by_case.setdefault(item["case"].case_id, []).append(item)
    projected: list[dict[str, Any]] = []
    maximum_wall = 0.0
    probe_metrics: dict[str, list[dict[str, int]]] = {}
    for case in all_cases:
        twins = sorted(by_case[case.case_id], key=lambda item: item["twin"])
        require(len(twins) == 2 and twins[0]["normalized_sha256"] == twins[1]["normalized_sha256"], f"twin replay differs: {case.case_id}")
        for twin in twins:
            validate_common(twin["report"], case, contract, executable_sha)
            maximum_wall = max(maximum_wall, twin["wall_seconds"])
        metrics = validate_probe(twins[0]["report"], case)
        probe_metrics.setdefault(case.probe, []).append(metrics)
        projected.append({
            "case_id": case.case_id,
            "cargo": case.cargo,
            "probe": case.probe,
            "seed": case.seed,
            "metrics": metrics,
            "twin_exact": True,
            "twins": [{
                "name": item["twin"],
                "normalized_sha256": item["normalized_sha256"],
                "report_path": item["report_path"],
                "report_sha256": item["report_sha256"],
                "wall_seconds": round(item["wall_seconds"], 6),
            } for item in twins],
        })
    require(all(item["income"] > 0 and item["delivered"] > 0 for name in ("passenger", "freight") for item in probe_metrics[name]), "service did not beat zero-service baselines")
    evidence = {
        "schema_version": "openttd-rl-v2-m17-rail-evidence-1",
        "artifact_root": str(artifact_root),
        "contract_sha256": sha256_file(root / CONTRACT),
        "source_sha256": sha256_file(root / SOURCE),
        "executable_sha256": executable_sha,
        "execution": {"network_calls": "none", "process_limits": True, "sandbox": "bubblewrap" if sandbox == "bubblewrap" else "rlimit-only"},
        "baselines": baseline_evidence(root, contract),
        "aggregate": {
            "cases": len(all_cases),
            "native_runs": len(results),
            "twin_exact_cases": len(projected),
            "rail_types": 4,
            "train_engine_entries": 116,
            "track_orientations": 6,
            "signal_variants": 12,
            "construction_pass": True,
            "lifecycle_pass": True,
            "passenger_pass": True,
            "freight_pass": True,
            "stress_pass": True,
            "maximum_wall_seconds": round(maximum_wall, 6),
        },
        "cases": projected,
        "status": "PASS",
    }
    write_new(evidence_path, evidence)
    print(f"V2_M17_RAIL_MATRIX=PASS cases={len(all_cases)} native_runs={len(results)} twin_exact={len(projected)}")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--evidence", type=pathlib.Path, required=True)
    parser.add_argument("--sandbox", choices=("bubblewrap", "test-none"), default="bubblewrap")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    try:
        require(1 <= args.workers <= 8, "workers must be in 1..8")
        run(args.root, args.artifact_root, args.evidence, args.sandbox, args.workers)
        return 0
    except (M17MatrixError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"V2_M17_RAIL_MATRIX=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
