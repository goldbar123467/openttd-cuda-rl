#!/usr/bin/env python3
"""Run deterministic twin-process M19 aircraft and multimodal qualification."""

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


CONTRACT = pathlib.Path("config/v2/m19-air-contract.json")
SOURCE = pathlib.Path("config/v2/m19-air-source.json")
PACKAGE_EVIDENCE = pathlib.Path("config/v2/opponent-package-evidence.json")
RUNTIME_EVIDENCE = pathlib.Path("config/v2/opponent-runtime-evidence.json")
TWINS = ("a", "b")
PROBES = ("catalog", "construction", "lifecycle", "occupancy", "failure", "service", "helicopter", "multimodal", "recovery", "router")


class M19MatrixError(ValueError):
    """The native M19 matrix violated its frozen contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M19MatrixError(message)


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
    return int.from_bytes(hashlib.sha256(f"m19:{case_id}".encode()).digest()[:4], "big")


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
            if probe == "multimodal":
                cargo = "GOOD"
            elif probe in ("lifecycle", "failure", "service", "helicopter", "recovery") and ordinal == 1:
                cargo = "GOOD"
            else:
                cargo = "PASS"
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
        "-a", str(run / "manifest.json"), "-z", str(run / "report.json"),
    ]
    if sandbox == "test-none":
        return direct
    require(sandbox == "bubblewrap" and shutil.which("bwrap") is not None, "bubblewrap is unavailable")
    return [
        "bwrap", "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-net",
        "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--bind", str(run), str(run),
        "--chdir", str(executable.parent), "--", *direct,
    ]


def validate_common(report: dict[str, Any], case: Case, executable_sha: str) -> None:
    require(report["schema_version"] == "openttd-rl-v2-m19-air-report-1" and report["status"] == "PASS", f"report failed: {case.case_id}")
    require(report["executable_sha256"] == executable_sha and report["request"]["probe"] == case.probe, f"identity drift: {case.case_id}")
    require(report["request"]["cargo_label"] == case.cargo and report["request"]["seed"] == case.seed, f"request drift: {case.case_id}")
    require(report["map"] == {"height": 64, "width": 64}, f"map drift: {case.case_id}")
    catalog = report["catalog"]
    require(len(catalog["airport_specs"]) == 10 and sum(item["enabled"] for item in catalog["airport_specs"]) == 9,
            f"airport inventory drift: {case.case_id}")
    require(len(catalog["aircraft_engines"]) == 41 and sum(item["kind"] == "helicopter" for item in catalog["aircraft_engines"]) == 3,
            f"aircraft inventory drift: {case.case_id}")
    require(catalog["movement_blocks"] == 64 and catalog["movement_headings"] == 22, f"airport movement catalog drift: {case.case_id}")


def validate_probe(report: dict[str, Any], case: Case) -> dict[str, int]:
    probe = report["probe"]
    zero = {"income": 0, "delivered": 0, "ticks": 0}
    if case.probe == "catalog":
        require(probe == {"status": "CATALOG_ONLY"}, f"catalog drift: {case.case_id}")
        return zero
    if case.probe == "construction":
        require(len(probe["buildable_types"]) == 9 and probe["disabled_oilrig_rejected"] and probe["footprint_mask"], "airport type/footprint coverage failed")
        require(probe["ownership_mask"] and probe["spread_mask"] and probe["terrain_mask"], "airport construction masks failed")
        return zero
    if case.probe == "lifecycle":
        require(probe["clone_and_sale"] and probe["save_load"]["restored"] and probe["save_load"]["bytes"] > 0, "aircraft lifecycle/save-load failed")
        require(probe["range_mask"] == {"bounded_rejected": True, "limit": 8, "unlimited_accepted": True}, "aircraft range mask drifted")
        require(probe["replacement"]["executed"] and probe["replacement"]["from_engine"] != probe["replacement"]["to_engine"], "aircraft autoreplace failed")
        require(probe["timetable"] == {"speed_limit_rejected": True, "travel": 256, "wait": 64}, "aircraft timetable semantics drifted")
        return zero
    if case.probe == "occupancy":
        require(probe["aircraft"] == 4 and probe["block_state_count"] > 2 and probe["nonzero_block_ticks"] > 0 and
                probe["peak_destination_contenders"] >= 2 and 14 in probe["headings"], "airport occupancy/congestion oracle failed")
        return zero
    if case.probe == "failure":
        require(probe["airport_close_open"] and probe["removal_blocked"] and probe["crash"]["crashed"] and
                probe["crash"]["seeded_fixture"], "aircraft failure projection failed")
        return zero
    if case.probe in ("service", "helicopter"):
        accounting = probe["accounting"]
        expected_kind = "airplane" if case.probe == "service" else "helicopter"
        require(probe["aircraft"]["kind"] == expected_kind and accounting["delivered"] > 0 and accounting["income"] > 0,
                f"{expected_kind} competence failed")
        require(probe["ticks"] < 196608 and len(accounting["payment_events"]) == 1 and not accounting["payment_events"][0]["transfer"],
                f"{expected_kind} accounting failed")
        return {"income": accounting["income"], "delivered": accounting["delivered"], "ticks": probe["ticks"]}
    if case.probe == "multimodal":
        conservation = probe["conservation"]
        require(probe["modes"] == ["road", "water", "air"] and len(set(conservation.values())) == 1,
                "road-water-air conservation failed")
        require(probe["transfer_payment_count"] == 2 and probe["final"]["payment_count"] == 1 and
                probe["final"]["company_income_delta"] > 0, "multimodal payment boundary failed")
        return {"income": probe["final"]["company_income_delta"], "delivered": conservation["delivered"],
                "ticks": sum(probe["ticks"].values())}
    if case.probe == "recovery":
        require(probe["reopened"] and probe["saw_flying_while_closed"] and probe["delivery"]["delivered"] > 0 and
                probe["delivery"]["income"] > 0 and probe["recovery_ticks"] < 196608, "closed-airport recovery failed")
        return {"income": probe["delivery"]["income"], "delivered": probe["delivery"]["delivered"], "ticks": probe["recovery_ticks"]}
    require(case.probe == "router" and probe["checkpoint_exact"] and probe["no_privileged_inputs"], "router checkpoint boundary failed")
    require(probe["route_costs"] == {"cargo_sink": 14, "passenger_sink": 6} and len(probe["edges"]) == 8,
            "mode-neutral router result drifted")
    return zero


def baseline_evidence(root: pathlib.Path) -> dict[str, Any]:
    packages = load(root / PACKAGE_EVIDENCE)
    runtimes = load(root / RUNTIME_EVIDENCE)
    package_by_name = {item["name"]: item for item in packages["results"]}
    runtime_by_name = {item["name"]: item for item in runtimes["results"]}
    generalist = runtime_by_name["AAAHogEx"]
    lufthansa_package = package_by_name["Lufthansa"]
    lufthansa_runtime = runtime_by_name["Lufthansa"]
    archive = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m14-ai-lufthansa-a/content_download/ai/4c554654-Lufthansa-2.tar")
    require(generalist["outcome"] == "QUALIFIED_ACTIVE" and generalist["admission"] == "TOURNAMENT", "AAAHogEx is not a qualified active generalist")
    require(lufthansa_package["outcome"] == "LOCKED" and lufthansa_runtime["outcome"] == "REJECTED" and
            lufthansa_runtime["admission"] == "EXCLUDED", "Lufthansa rejection boundary drifted")
    require(archive.is_file() and sha256_file(archive) == "ac313debff38dc9937439f90068930653fc7ce2c8d6e94ee11dc4c10cb3e3a3b",
            "Lufthansa archive identity drifted")
    return {
        "generalist": {"name": "AAAHogEx", "outcome": "QUALIFIED_ACTIVE", "air_vehicles": generalist["vehicles"]["air"],
            "runtime_evidence_sha256": generalist["evidence_sha256"], "scenario_limitation": "active generalist chose rail rather than air"},
        "lufthansa": {"name": "Lufthansa", "outcome": "REJECTED", "admission": "EXCLUDED",
            "archive_sha256": sha256_file(archive), "runtime_evidence_sha256": lufthansa_runtime["evidence_sha256"],
            "disposition": "retain-rejection-no-repair-no-relabel"},
        "native_air_oracle": True,
    }


def run_one(executable: pathlib.Path, artifact_root: pathlib.Path, case: Case, twin: str, executable_sha: str, sandbox: str) -> dict[str, Any]:
    run_root = artifact_root / case.case_id / f"twin-{twin}"
    run_root.mkdir(parents=True, mode=0o700)
    write_new(run_root / "manifest.json", {"cargo_label": case.cargo, "executable_sha256": executable_sha, "probe": case.probe,
        "run_id": f"{case.case_id}-{twin}", "schema_version": "openttd-rl-v2-m19-air-manifest-1", "seed": case.seed})
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
            executable.stat().st_size == source["executable"]["bytes"], "M19 executable identity drifted")
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
    evidence = {"schema_version": "openttd-rl-v2-m19-air-evidence-1", "artifact_root": str(artifact_root),
        "contract_sha256": sha256_file(root / CONTRACT), "source_sha256": sha256_file(root / SOURCE), "executable_sha256": executable_sha,
        "execution": {"network_calls": "none", "process_limits": True, "sandbox": "bubblewrap" if sandbox == "bubblewrap" else "rlimit-only"},
        "baselines": baseline_evidence(root), "aggregate": {"cases": len(all_cases), "native_runs": len(results),
            "twin_exact_cases": len(projected), "airport_specs": 10, "buildable_airport_types": 9, "aircraft_engine_entries": 41,
            "probes": 10, "construction_pass": True, "lifecycle_pass": True, "occupancy_pass": True, "failure_pass": True,
            "service_pass": True, "helicopter_pass": True, "multimodal_pass": True, "recovery_pass": True, "router_pass": True,
            "maximum_wall_seconds": round(maximum_wall, 6)}, "cases": projected, "status": "PASS"}
    write_new(evidence_path, evidence)
    print(f"V2_M19_AIR_MATRIX=PASS cases={len(all_cases)} native_runs={len(results)} twin_exact={len(projected)}")
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
    except (M19MatrixError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"V2_M19_AIR_MATRIX=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
