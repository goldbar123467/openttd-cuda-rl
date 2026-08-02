#!/usr/bin/env python3
"""Run deterministic twin-process M18 ship and waterway qualification."""

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


CONTRACT = pathlib.Path("config/v2/m18-ship-contract.json")
SOURCE = pathlib.Path("config/v2/m18-ship-source.json")
SHIPAI = pathlib.Path("config/v2/m18-shipai-evidence.json")
TWINS = ("a", "b")
PROBES = ("catalog", "construction", "connectivity", "lifecycle", "natural", "constructed", "transfer", "recovery")


class M18MatrixError(ValueError):
    """The native M18 matrix violated its frozen contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M18MatrixError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_new(path: pathlib.Path, value: Any) -> None:
    require(not path.exists() and not path.is_symlink(), f"output already exists: {path}")
    path.write_bytes(canonical_bytes(value))


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_for(case_id: str) -> int:
    return int.from_bytes(hashlib.sha256(f"m18:{case_id}".encode()).digest()[:4], "big")


@dataclass(frozen=True)
class Case:
    case_id: str
    cargo: str
    probe: str
    seed: int


def cases(_contract: dict[str, Any]) -> list[Case]:
    result: list[Case] = []
    for probe in PROBES:
        for ordinal in range(2):
            case_id = f"{probe}-s{ordinal}"
            cargo = "COAL" if probe == "transfer" or ordinal == 1 else "PASS"
            result.append(Case(case_id, cargo, probe, seed_for(case_id)))
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
        "-u", str(run / "manifest.json"), "-w", str(run / "report.json"),
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


def validate_common(report: dict[str, Any], case: Case, executable_sha: str) -> None:
    require(report["schema_version"] == "openttd-rl-v2-m18-ship-report-1" and report["status"] == "PASS", f"report failed: {case.case_id}")
    require(report["executable_sha256"] == executable_sha and report["request"]["probe"] == case.probe, f"identity drift: {case.case_id}")
    require(report["request"]["cargo_label"] == case.cargo and report["request"]["seed"] == case.seed, f"request drift: {case.case_id}")
    require(report["map"] == {"height": 64, "width": 64}, f"map drift: {case.case_id}")
    catalog = report["catalog"]
    require(len(catalog["engines"]) == 11, f"ship-engine inventory drift: {case.case_id}")
    require(catalog["water_classes"] == [{"id": 0, "name": "sea"}, {"id": 1, "name": "canal"}, {"id": 2, "name": "river"}],
            f"water-class inventory drift: {case.case_id}")
    require(catalog["water_region_edge_length"] == 16, f"water-region geometry drift: {case.case_id}")


def validate_probe(report: dict[str, Any], case: Case) -> dict[str, int]:
    probe = report["probe"]
    zero = {"income": 0, "delivered": 0, "ticks": 0}
    if case.probe == "catalog":
        require(probe == {"status": "CATALOG_ONLY"}, f"catalog drift: {case.case_id}")
        return zero
    if case.probe == "construction":
        require(probe["distant_dock_join"] and probe["invalid_class_rejected"] and all(probe["removal_roundtrip"].values()), "construction/removal oracle failed")
        require(probe["water_classes"] == ["canal", "river", "sea"], "construction water-class coverage drifted")
        for name in ("CMD_BUILD_LOCK", "CMD_BUILD_AQUEDUCT", "CMD_BUILD_DOCK", "CMD_BUILD_SHIP_DEPOT", "CMD_BUILD_BUOY"):
            require("SUCCESS" in command_statuses(probe, name), f"construction command missing: {name}")
        require(command_statuses(probe, "CMD_BUILD_CANAL_INVALID_CLASS") == ["REJECTED"] and
                command_statuses(probe, "CMD_REMOVE_FOREIGN_CANAL") == ["REJECTED"], "construction rejection semantics drifted")
        return zero
    if case.probe == "connectivity":
        require(probe["before_cut"] == {"engine": True, "independent": True} and
                probe["after_cut"] == {"engine": False, "independent": False} and probe["reconnected"], "connectivity parity failed")
        require(probe["start_patch"]["label"] > 0 and probe["start_region"] == {"x": 0, "y": 2}, "water-region projection drifted")
        return zero
    if case.probe == "lifecycle":
        require(probe["clone_and_sale"] and probe["service_interval"] == 120, "ship lifecycle failed")
        require(probe["order_flags"] == {"invalid_rejected": True, "load": True, "unload": True}, "ship order flags drifted")
        require(probe["timetable"] == {"speed": 48, "travel": 256, "wait": 64}, "ship timetable drifted")
        require(probe["save_load"]["restored"] and probe["save_load"]["bytes"] > 0 and
                probe["safety_fixture"] == {"crashed": False, "lost_cleared": True, "lost_positive": True},
                "ship save/load or safety fixture failed")
        require(probe["replacement"]["configured"] and probe["replacement"]["executed"] and
                probe["replacement"]["from_engine"] != probe["replacement"]["to_engine"], "ship autoreplace failed")
        return zero
    if case.probe in ("natural", "constructed"):
        accounting, route = probe["accounting"], probe["route"]
        require(accounting["delivered"] > 0 and accounting["income"] > 0 and probe["ticks"] < 131072, f"ship service failed: {case.case_id}")
        require(probe["ship"]["lost"] is False and len(accounting["payment_events"]) == 1 and not accounting["payment_events"][0]["transfer"], "ship service safety/accounting failed")
        if case.probe == "constructed":
            require(route == {"aqueduct_traversed": True, "constructed": True, "lock_traversed": True, "water_class": "canal"}, "constructed traversal drifted")
        else:
            require(not route["constructed"] and not route["lock_traversed"] and not route["aqueduct_traversed"] and
                    route["water_class"] == ("sea" if case.cargo == "PASS" else "river"), "natural route drifted")
        return {"income": accounting["income"], "delivered": accounting["delivered"], "ticks": probe["ticks"]}
    if case.probe == "transfer":
        require(probe["shared_road_dock_station"] and probe["first_leg"]["cash_delta"] == 0 and probe["first_leg"]["transferred"] > 0, "feeder transfer failed")
        require(probe["final"]["company_income_delta"] > 0 and probe["final"]["delivered"] > 0 and probe["final"]["payment_count"] == 1, "final transfer payment failed")
        require(sum(not event["transfer"] for event in probe["payment_events"]) == 1 and any(event["transfer"] for event in probe["payment_events"]), "transfer event conservation failed")
        return {"income": probe["final"]["company_income_delta"], "delivered": probe["final"]["delivered"], "ticks": probe["final"]["ticks"]}
    require(case.probe == "recovery" and probe["disconnected"] and probe["lost_detected"] and probe["safe_stopped"] and probe["reconnected"], "recovery state machine failed")
    require(probe["delivery"]["delivered"] > 0 and probe["delivery"]["income"] > 0 and probe["recovery_ticks"] < 131072, "recovery delivery failed")
    return {"income": probe["delivery"]["income"], "delivered": probe["delivery"]["delivered"], "ticks": probe["recovery_ticks"]}


def baseline_evidence(root: pathlib.Path) -> dict[str, Any]:
    index = load(root / SHIPAI)
    manifest_path = pathlib.Path(index["qualification_manifest"]["path"])
    require(manifest_path.is_file() and sha256_file(manifest_path) == index["qualification_manifest"]["sha256"], "ShipAI qualification manifest drifted")
    manifest = load(manifest_path)
    before, after = manifest["observations"]["company_before_load"], manifest["observations"]["company_after_load"]
    require(manifest["outcome"] == "QUALIFIED_ACTIVE" and before["ships"] >= 1 and after["ships"] == before["ships"], "ShipAI is not active and save/load stable")
    require(index["status"] == "PASS" and index["scenario"]["sha256"] == sha256_file(pathlib.Path(index["scenario"]["path"])), "ShipAI scenario evidence drifted")
    return {"specialist_name": "ShipAI", "specialist_qualified": True, "ships_before_load": before["ships"],
            "ships_after_load": after["ships"], "qualification_manifest_sha256": index["qualification_manifest"]["sha256"],
            "natural_beats_zero_service": True, "constructed_beats_zero_service": True}


def run_one(executable: pathlib.Path, artifact_root: pathlib.Path, case: Case, twin: str, executable_sha: str, sandbox: str) -> dict[str, Any]:
    run_root = artifact_root / case.case_id / f"twin-{twin}"
    run_root.mkdir(parents=True, mode=0o700)
    write_new(run_root / "manifest.json", {"cargo_label": case.cargo, "executable_sha256": executable_sha, "probe": case.probe,
        "run_id": f"{case.case_id}-{twin}", "schema_version": "openttd-rl-v2-m18-ship-manifest-1", "seed": case.seed})
    started = time.monotonic()
    result = subprocess.run(command(executable, run_root, sandbox), cwd=executable.parent, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=120, preexec_fn=apply_limits, start_new_session=True)
    wall = time.monotonic() - started
    (run_root / "openttd.log").write_text(result.stdout, encoding="utf-8")
    require(result.returncode == 0, f"native run failed ({result.returncode}) {run_root}: {result.stdout.strip()}")
    report = load(run_root / "report.json")
    return {"case": case, "twin": twin, "report": report, "report_sha256": sha256_file(run_root / "report.json"),
            "normalized_sha256": hashlib.sha256(normalized(report)).hexdigest(), "wall_seconds": wall,
            "report_path": str((run_root / "report.json").relative_to(artifact_root))}


def run(root: pathlib.Path, artifact_root: pathlib.Path, evidence_path: pathlib.Path, sandbox: str, workers: int) -> dict[str, Any]:
    root, artifact_root, evidence_path = root.resolve(), artifact_root.resolve(), evidence_path.resolve()
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "artifact root must be new")
    require(not evidence_path.exists() and not evidence_path.is_symlink(), "evidence output must be new")
    contract, source = load(root / CONTRACT), load(root / SOURCE)
    executable = pathlib.Path(source["executable"]["path"])
    executable_sha = sha256_file(executable)
    require(executable.is_file() and os.access(executable, os.X_OK) and executable_sha == source["executable"]["sha256"] and
            executable.stat().st_size == source["executable"]["bytes"], "M18 executable identity drifted")
    artifact_root.mkdir(mode=0o700)
    all_cases = cases(contract)
    jobs = [(case, twin) for case in all_cases for twin in TWINS]
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(run_one, executable, artifact_root, case, twin, executable_sha, sandbox) for case, twin in jobs]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    projected, maximum_wall = [], 0.0
    for case in all_cases:
        twins = sorted((item for item in results if item["case"] == case), key=lambda item: item["twin"])
        require(len(twins) == 2 and twins[0]["normalized_sha256"] == twins[1]["normalized_sha256"], f"twin replay differs: {case.case_id}")
        for twin in twins:
            validate_common(twin["report"], case, executable_sha)
            maximum_wall = max(maximum_wall, twin["wall_seconds"])
        metrics = validate_probe(twins[0]["report"], case)
        projected.append({"case_id": case.case_id, "cargo": case.cargo, "probe": case.probe, "seed": case.seed, "metrics": metrics,
            "twin_exact": True, "twins": [{"name": item["twin"], "normalized_sha256": item["normalized_sha256"],
                "report_path": item["report_path"], "report_sha256": item["report_sha256"],
                "wall_seconds": round(item["wall_seconds"], 6)} for item in twins]})
    evidence = {"schema_version": "openttd-rl-v2-m18-ship-evidence-1", "artifact_root": str(artifact_root),
        "contract_sha256": sha256_file(root / CONTRACT), "source_sha256": sha256_file(root / SOURCE), "executable_sha256": executable_sha,
        "execution": {"network_calls": "none", "process_limits": True, "sandbox": "bubblewrap" if sandbox == "bubblewrap" else "rlimit-only"},
        "baselines": baseline_evidence(root), "aggregate": {"cases": len(all_cases), "native_runs": len(results),
            "twin_exact_cases": len(projected), "ship_engine_entries": 11, "water_classes": 3, "probes": 8,
            "construction_pass": True, "connectivity_pass": True, "lifecycle_pass": True, "natural_pass": True,
            "constructed_pass": True, "transfer_pass": True, "recovery_pass": True, "maximum_wall_seconds": round(maximum_wall, 6)},
        "cases": projected, "status": "PASS"}
    write_new(evidence_path, evidence)
    print(f"V2_M18_SHIP_MATRIX=PASS cases={len(all_cases)} native_runs={len(results)} twin_exact={len(projected)}")
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
    except (M18MatrixError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"V2_M18_SHIP_MATRIX=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
