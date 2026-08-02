#!/usr/bin/env python3
"""Run deterministic twin-process M16 cargo, industry, transfer, and subsidy qualification."""

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


CONTRACT = pathlib.Path("config/v2/m16-cargo-contract.json")
SOURCE = pathlib.Path("config/v2/m16-cargo-source.json")
TWINS = ("a", "b")


class M16MatrixError(ValueError):
    """The native M16 matrix violated its frozen contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M16MatrixError(message)


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
    return int.from_bytes(hashlib.sha256(f"m16:{case_id}:{ordinal}".encode()).digest()[:4], "big")


@dataclass(frozen=True)
class Case:
    case_id: str
    climate: str
    cargo: str
    probe: str
    seed: int


def cases(contract: dict[str, Any]) -> list[Case]:
    result: list[Case] = []
    for climate in contract["semantics"]["climate_order"]:
        case_id = f"catalog-{climate}"
        result.append(Case(case_id, climate, "PASS", "catalog", seed_for(case_id, 0)))
        for cargo in contract["climates"][climate]:
            for ordinal in range(2):
                case_id = f"single-{climate}-{cargo.lower()}-s{ordinal}"
                result.append(Case(case_id, climate, cargo, "single-leg", seed_for(case_id, ordinal)))
    for probe, cargo in (("coordination", "MAIL"), ("transfer", "COAL"), ("subsidy", "COAL")):
        for ordinal in range(2):
            case_id = f"{probe}-temperate-s{ordinal}"
            result.append(Case(case_id, "temperate", cargo, probe, seed_for(case_id, ordinal)))
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
        "-N", str(run / "manifest.json"), "-O", str(run / "report.json"),
    ]
    if sandbox == "test-none":
        return direct
    require(sandbox == "bubblewrap" and shutil.which("bwrap") is not None, "bubblewrap is unavailable")
    return [
        "bwrap", "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-net",
        "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--bind", str(run), str(run),
        "--chdir", str(executable.parent), "--", *direct,
    ]


def validate_common(report: dict[str, Any], case: Case, contract: dict[str, Any], executable_sha: str) -> None:
    require(report["schema_version"] == "openttd-rl-v2-m16-cargo-report-1" and report["status"] == "PASS", f"report failed: {case.case_id}")
    require(report["climate"] == case.climate and report["executable_sha256"] == executable_sha, f"identity drift: {case.case_id}")
    labels = [item["label"] for item in report["cargo_catalog"]]
    require(labels == contract["climates"][case.climate], f"climate cargo catalog drift: {case.case_id}: {labels}")
    graph = report["industry_graph"]
    require(graph["industries"] and isinstance(graph["production_transitions"], list), f"industry graph is empty: {case.case_id}")
    lifecycle = report["lifecycle_and_economy"]
    require(lifecycle["industry_closure"]["exact_pool_roundtrip"] is True, f"closure lifecycle failed: {case.case_id}")
    require(all(lifecycle["economy"].values()) and all(lifecycle["cargo_distribution"].values()), f"economy/distribution transition failed: {case.case_id}")


def validate_probe(report: dict[str, Any], case: Case) -> dict[str, Any]:
    probe = report["probe"]
    if case.probe == "catalog":
        require(probe == {"status": "CATALOG_ONLY"}, f"catalog probe drift: {case.case_id}")
        return {"income": 0, "delivered": 0, "ticks": 0}
    if case.probe in ("single-leg", "subsidy"):
        accounting = probe["accounting"]
        events = accounting["payment_events"]
        require(accounting["delivered_delta"] > 0 and accounting["company_income_delta"] > 0, f"unprofitable delivery: {case.case_id}")
        require(len(events) == 1 and events[0]["transfer"] is False and events[0]["cargo"] == case.cargo, f"final payment drift: {case.case_id}")
        require(accounting["company_income_delta"] == events[0]["final_income"], f"accounting parity failed: {case.case_id}")
        multiplier = 2 if case.probe == "subsidy" else 1
        require(events[0]["final_income"] == events[0]["base_income"] * multiplier, f"payment multiplier drift: {case.case_id}")
        require(probe["vehicle"]["cargo"] == case.cargo and probe["vehicle"]["refit_capacity"] > 0, f"vehicle/refit drift: {case.case_id}")
        return {"income": accounting["company_income_delta"], "delivered": accounting["delivered_delta"], "ticks": probe["ticks"]}
    if case.probe == "coordination":
        accounting = probe["accounting"]
        events = accounting["payment_events"]
        require(probe["shared_stations"] is True and accounting["delivered_passengers"] > 0 and accounting["delivered_mail"] > 0, "coordination service failed")
        require({item["cargo"] for item in events} == {"PASS", "MAIL"} and accounting["company_income_delta"] == sum(item["final_income"] for item in events), "coordination accounting failed")
        return {"income": accounting["company_income_delta"], "delivered": accounting["delivered_passengers"] + accounting["delivered_mail"], "ticks": probe["ticks"]}
    require(case.probe == "transfer", f"unknown projected probe: {case.probe}")
    events = probe["payment_events"]
    require(probe["single_final_payment"] is True and probe["first_leg"]["company_income_delta"] == 0 and probe["first_leg"]["transfer_waiting"] > 0, "transfer intermediate accounting failed")
    require(len(events) == 2 and sum(not item["transfer"] for item in events) == 1 and sum(item["transfer"] for item in events) == 1, "transfer event cardinality failed")
    final = next(item for item in events if not item["transfer"])
    require(probe["final"]["company_income_delta"] == final["final_income"] > 0, "transfer final accounting failed")
    return {"income": final["final_income"], "delivered": probe["final"]["delivered_delta"], "ticks": probe["first_leg"]["ticks"] + probe["final"]["ticks"]}


def run_one(executable: pathlib.Path, artifact_root: pathlib.Path, case: Case, twin: str, executable_sha: str, sandbox: str) -> dict[str, Any]:
    run = artifact_root / case.case_id / f"twin-{twin}"
    run.mkdir(parents=True, mode=0o700)
    run_id = f"{case.case_id}-{twin}"
    manifest = {
        "amount": 8, "cargo_label": case.cargo, "climate": case.climate, "executable_sha256": executable_sha,
        "probe": case.probe, "run_id": run_id, "schema_version": "openttd-rl-v2-m16-cargo-manifest-1", "seed": case.seed,
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
        "case": case, "twin": twin, "report": report, "report_sha256": sha256_file(run / "report.json"),
        "normalized_sha256": sha256_bytes(normalized(report)), "wall_seconds": wall,
        "report_path": str((run / "report.json").relative_to(artifact_root)),
    }


def run(root: pathlib.Path, artifact_root: pathlib.Path, evidence_path: pathlib.Path, sandbox: str, workers: int) -> dict[str, Any]:
    root, artifact_root, evidence_path = root.resolve(), artifact_root.resolve(), evidence_path.resolve()
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "artifact root must be a new path")
    require(not evidence_path.exists() and not evidence_path.is_symlink(), "evidence output must be a new path")
    contract, source = load(root / CONTRACT), load(root / SOURCE)
    executable = pathlib.Path(source["executable"]["path"])
    require(executable.is_file() and os.access(executable, os.X_OK), "M16 executable is unavailable")
    executable_sha = sha256_file(executable)
    require(executable_sha == source["executable"]["sha256"] and executable.stat().st_size == source["executable"]["bytes"], "M16 executable identity drifted")
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
    unique_cargos: set[str] = set()
    climate_occurrences: set[tuple[str, str]] = set()
    production_edges: set[tuple[str, int, str, str]] = set()
    actual_cargo_classes: set[str] = set()
    maximum_wall = 0.0
    for case in all_cases:
        twins = sorted(by_case[case.case_id], key=lambda item: item["twin"])
        require(len(twins) == 2 and twins[0]["normalized_sha256"] == twins[1]["normalized_sha256"], f"twin replay differs: {case.case_id}")
        for twin in twins:
            validate_common(twin["report"], case, contract, executable_sha)
            maximum_wall = max(maximum_wall, twin["wall_seconds"])
        metrics = validate_probe(twins[0]["report"], case)
        for cargo in twins[0]["report"]["cargo_catalog"]:
            unique_cargos.add(cargo["label"])
            climate_occurrences.add((case.climate, cargo["label"]))
            actual_cargo_classes.update(cargo["classes"])
        for edge in twins[0]["report"]["industry_graph"]["production_transitions"]:
            production_edges.add((case.climate, edge["industry_id"], edge["accepted"], edge["produced"]))
        projected.append({
            "case_id": case.case_id, "cargo": case.cargo, "climate": case.climate, "probe": case.probe, "seed": case.seed,
            "metrics": metrics, "twin_exact": True,
            "twins": [{"name": item["twin"], "normalized_sha256": item["normalized_sha256"], "report_path": item["report_path"],
                        "report_sha256": item["report_sha256"], "wall_seconds": round(item["wall_seconds"], 6)} for item in twins],
        })
    single_cases = [item for item in all_cases if item.probe == "single-leg"]
    require(len(single_cases) == 92 and len(unique_cargos) == 31 and len(climate_occurrences) == 46, "cargo matrix completeness drifted")
    evidence = {
        "schema_version": "openttd-rl-v2-m16-cargo-evidence-1",
        "artifact_root": str(artifact_root),
        "contract_sha256": sha256_file(root / CONTRACT),
        "source_sha256": sha256_file(root / SOURCE),
        "executable_sha256": executable_sha,
        "execution": {"network_calls": "none", "process_limits": True, "sandbox": "bubblewrap" if sandbox == "bubblewrap" else "rlimit-only"},
        "aggregate": {
            "actual_cargo_classes": sorted(actual_cargo_classes), "actual_cargo_class_count": len(actual_cargo_classes),
            "cases": len(all_cases), "climate_occurrences": len(climate_occurrences), "native_runs": len(results),
            "production_edges": len(production_edges), "single_leg_cases": len(single_cases), "twin_exact_cases": len(projected),
            "unique_cargo_labels": len(unique_cargos), "maximum_wall_seconds": round(maximum_wall, 6),
            "coordination_pass": True, "subsidy_pass": True, "transfer_no_duplicate_payment": True,
        },
        "cases": projected,
        "status": "PASS",
    }
    write_new(evidence_path, evidence)
    print(f"V2_M16_CARGO_MATRIX=PASS cases={len(all_cases)} native_runs={len(results)} cargos={len(unique_cargos)} occurrences={len(climate_occurrences)} edges={len(production_edges)}")
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
    except (M16MatrixError, OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M16_CARGO_MATRIX=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
