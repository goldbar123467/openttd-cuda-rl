#!/usr/bin/env python3
"""Manifest-generic native execution for one M22 public final case.

This module never opens the M22 final manifest.  Callers provide one already
validated case.  The selected policy receives only the public projection; this
native layer owns the hidden run seed and executes the preregistered G15-G21
capability exactly once in a fresh, network-unshared OpenTTD process.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import resource
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Any

import qualify_m15_native_reset as m15_reset
import run_m16_cargo_matrix as m16
import run_m17_rail_matrix as m17
import run_m18_ship_matrix as m18
import run_m19_air_matrix as m19
import run_m20_competition_matrix as m20
import run_m21_broad_matrix as m21


FINAL_TOKEN = "m22-independent-final-v1"
M15_ENGINE_TREE = "02d8cbbb0d8c030698d37ca76ab2773b6e23c397"
TIMEOUT_SECONDS = 300
PUBLIC_FIELDS = (
    "case_id", "task", "transport_mode", "climate", "map_width", "map_height",
    "cargo", "opponent", "native_probe", "source_gate",
)
G15_ARTIFACT_PATHS = (
    "artifacts/capture-service-branch-a-candidates.bin",
    "artifacts/capture-service-branch-a-candidates.json",
    "artifacts/capture-service-branch-a-observation.bin",
    "artifacts/capture-service-branch-a-observation.json",
    "artifacts/capture-service-branch-a.sav",
    "artifacts/capture-service-branch-b-candidates.bin",
    "artifacts/capture-service-branch-b-candidates.json",
    "artifacts/capture-service-branch-b-observation.bin",
    "artifacts/capture-service-branch-b-observation.json",
    "artifacts/capture-service-branch-b.sav",
    "artifacts/service-ready.sav", "manifest.json", "openttd.log", "report.json", "reset.json",
)


def expected_artifact_paths(case: dict[str, Any], status: str) -> tuple[str, ...]:
    """Return the closed native file inventory for one frozen gate dispatch."""
    gate, probe = case["source_gate"], case["native_probe"]
    if status == "FAIL":
        if gate == "G21" and probe in {"authority-economy", "events"}:
            return ("manifest.json", "openttd.log")
        return ("manifest.json", "openttd.log", "report.json")
    if gate == "G15":
        return G15_ARTIFACT_PATHS
    if gate == "G20" or (gate == "G21" and probe in {
        "calendar", "authority-economy", "events", "gamescript",
    }):
        return ("manifest.json", "openttd.log", "report.json", "report.json.sav")
    return ("manifest.json", "openttd.log", "report.json")


def expected_failure_marker(case: dict[str, Any]) -> str:
    if case["source_gate"] == "G19" and case["native_probe"] == "multimodal":
        return "multimodal probe requires freight cargo"
    if case["source_gate"] == "G20":
        return "shared map lacks generated towns or industries"
    if case["source_gate"] == "G21" and case["native_probe"] in {"authority-economy", "events"}:
        return "Game save failed"
    return "M22 native process failed"


class M22FinalNativeError(ValueError):
    """A final native request, launch, or report violated the frozen boundary."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22FinalNativeError(message)


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


def derived_seed(label: str, seed: int) -> int:
    require(1 <= seed <= 2_147_483_647, "M22 native seed is outside the frozen 31-bit domain")
    value = int.from_bytes(hashlib.sha256(f"m22-final:{label}:{seed}".encode()).digest()[:4], "big") & 0x7FFF_FFFF
    return value or 1


def resource_tier(width: int, height: int) -> str:
    """Project an accepted M15 resource tier from the final-world tile count."""
    return "curriculum" if width * height <= 262_144 else "generalization"


@dataclass(frozen=True)
class RuntimePaths:
    executable: pathlib.Path
    opengfx: pathlib.Path
    base_config: pathlib.Path
    content_config: pathlib.Path
    gamescript_config: pathlib.Path
    source_tree: str


def validate_runtime(runtime: RuntimePaths) -> str:
    require(runtime.executable.is_absolute() and runtime.executable.is_file() and not runtime.executable.is_symlink() and
            os.access(runtime.executable, os.X_OK), "M22 final OpenTTD executable is unavailable")
    require(runtime.opengfx.is_file() and not runtime.opengfx.is_symlink(), "M22 final OpenGFX archive is unavailable")
    for name, path in (("base", runtime.base_config), ("content", runtime.content_config),
                       ("gamescript", runtime.gamescript_config)):
        require(path.is_absolute() and path.is_file() and not path.is_symlink(), f"M22 final {name} config is unavailable")
    require(len(runtime.source_tree) == 40 and set(runtime.source_tree) <= set("0123456789abcdef"),
            "M22 final source tree is malformed")
    return sha256(runtime.executable)


def public_case(case: dict[str, Any]) -> dict[str, Any]:
    require(all(field in case for field in (*PUBLIC_FIELDS, "seed")), "M22 native case is incomplete")
    return {field: case[field] for field in PUBLIC_FIELDS}


def canonical_probe(case: dict[str, Any]) -> str:
    probe = case["native_probe"]
    gate = case["source_gate"]
    aliases = {
        "G15": {"passenger-service": "passenger-service", "passenger": "passenger-service",
                "m15-competence": "passenger-service"},
        "G16": {"single-leg": "single-leg", "cargo-service": "single-leg", "industry-chain": "single-leg"},
        "G17": {"passenger": "passenger", "rail-passenger": "passenger", "freight": "freight", "rail-freight": "freight"},
        "G18": {"natural": "natural", "ship-natural": "natural", "constructed": "constructed", "ship-constructed": "constructed"},
        "G19": {"service": "service", "air-service": "service", "airplane": "service", "helicopter": "helicopter",
                "air-helicopter": "helicopter", "multimodal": "multimodal", "multimodal-transfer": "multimodal",
                "transfer": "multimodal", "router": "router", "mode-router": "router", "routing": "router"},
        "G20": {"head-to-head": "head_to_head", "head_to_head": "head_to_head"},
        "G21": {"calendar": "calendar", "calendar-inspect": "calendar", "authority-economy": "authority_economy",
                "authority_economy": "authority_economy", "events": "events", "event-recovery": "events",
                "gamescript": "gamescript", "gamescript-response": "gamescript", "content": "content",
                "content-discovery": "content"},
    }
    require(gate in aliases and probe in aliases[gate], f"unsupported M22 native gate/probe pair: {gate}/{probe}")
    return aliases[gate][probe]


def apply_limits() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (3_221_225_472, 3_221_225_472))
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))


def isolated_environment(run_root: pathlib.Path, case: dict[str, Any]) -> dict[str, str]:
    environment = dict(os.environ)
    for variable, relative in {
        "HOME": "isolation/home", "XDG_CONFIG_HOME": "isolation/xdg/config",
        "XDG_CACHE_HOME": "isolation/xdg/cache", "XDG_DATA_HOME": "isolation/xdg/data",
    }.items():
        path = run_root / relative
        path.mkdir(parents=True, exist_ok=False)
        environment[variable] = str(path)
    environment.update({
        "OPENTTD_RL_M22_FINAL_TOKEN": FINAL_TOKEN,
        "OPENTTD_RL_M22_FINAL_WIDTH": str(case["map_width"]),
        "OPENTTD_RL_M22_FINAL_HEIGHT": str(case["map_height"]),
        "OPENTTD_RL_M22_FINAL_CLIMATE": case["climate"],
    })
    return environment


def launch(
    command: list[str], runtime: RuntimePaths, run_root: pathlib.Path, case: dict[str, Any], *,
    bwrap_path: pathlib.Path | None = None,
) -> tuple[float, str]:
    require(bwrap_path is not None, "an explicit bubblewrap path is required for M22 final native execution")
    require(bwrap_path.is_absolute() and bwrap_path.is_file() and not bwrap_path.is_symlink() and
            os.access(bwrap_path, os.X_OK), "the explicit bubblewrap path is not a regular executable")
    wrapped = [
        str(bwrap_path), "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-ipc",
        "--unshare-uts", "--unshare-net", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
        "--tmpfs", "/tmp", "--bind", str(run_root), str(run_root), "--chdir", str(runtime.executable.parent), "--",
        *command,
    ]
    started = time.monotonic()
    process = subprocess.Popen(
        wrapped, cwd=runtime.executable.parent, env=isolated_environment(run_root, case), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, preexec_fn=apply_limits, start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        raise M22FinalNativeError(f"M22 native process timed out: {case['case_id']}") from exc
    wall = time.monotonic() - started
    (run_root / "openttd.log").write_text(output, encoding="utf-8")
    require(process.returncode == 0, f"M22 native process failed ({process.returncode}) {case['case_id']}: {output.strip()}")
    return wall, output


def launch_case(
    command: list[str], runtime: RuntimePaths, run_root: pathlib.Path, case: dict[str, Any],
    bwrap_path: pathlib.Path | None,
) -> tuple[float, str]:
    # Task-level producer tests replace launch with a four-argument process
    # stub.  Production callers always provide the preflighted executable.
    if bwrap_path is None:
        return launch(command, runtime, run_root, case)
    return launch(command, runtime, run_root, case, bwrap_path=bwrap_path)


def base_command(runtime: RuntimePaths) -> list[str]:
    return [str(runtime.executable), "-x", "-X", "-Q", "-I", "OpenGFX", "-m", "null", "-s", "null", "-v", "null"]


def m15_request(root: pathlib.Path, runtime: RuntimePaths, case: dict[str, Any], executable_sha: str) -> dict[str, Any]:
    seed = case["seed"]
    return {
        "schema_version": "openttd-rl-v2-m15-reset-manifest-1",
        "contract_sha256": sha256(root / "config/v2/m15-scalable-contract.json"),
        "engine_source_tree": M15_ENGINE_TREE,
        "executable_sha256": executable_sha,
        "map_width": case["map_width"], "map_height": case["map_height"], "map_seed": seed,
        "simulation_seed": m15_reset.stream_seed("simulation", seed),
        "candidate_tiebreak_seed": m15_reset.stream_seed("candidate-tiebreak", seed),
        "split": "final", "climate": case["climate"], "start_year": 1950,
        "settings_manifest_sha256": sha256(root / "config/v2/setting-inventory.json"),
        "content_manifest_sha256": sha256(runtime.opengfx), "generation_mode": "native-seeded",
        "town_target": max(2, min(128, case["map_width"] * case["map_height"] // 4096)),
        "industry_target": 256, "company_count": 1,
        "resource_tier": resource_tier(case["map_width"], case["map_height"]),
        "v1_adapter": False, "rejection_reason": None,
    }


def validate_map(report: dict[str, Any], case: dict[str, Any]) -> None:
    require(report["map"] == {"width": case["map_width"], "height": case["map_height"]},
            f"M22 native map projection drifted: {case['case_id']}")


def run_g15(root: pathlib.Path, runtime: RuntimePaths, run_root: pathlib.Path,
            case: dict[str, Any], executable_sha: str,
            bwrap_path: pathlib.Path | None = None) -> tuple[pathlib.Path, dict[str, Any]]:
    manifest = m15_request(root, runtime, case, executable_sha)
    write_new(run_root / "manifest.json", manifest)
    artifacts = run_root / "artifacts"
    artifacts.mkdir(mode=0o700)
    command = [*base_command(runtime), "-V", str(run_root / "manifest.json"), "-U", str(run_root / "reset.json"),
               "-E", str(root / "config/v2/m15-competence-program.json"), "-F", str(run_root / "report.json"),
               "-H", str(artifacts)]
    launch_case(command, runtime, run_root, case, bwrap_path)
    projection, report = load(run_root / "reset.json"), load(run_root / "report.json")
    require(projection["request"]["width"] == case["map_width"] and projection["request"]["height"] == case["map_height"] and
            projection["request"]["climate"] == case["climate"] and projection["request"]["split"] == "final",
            "M22 G15 reset projection drifted")
    service = next((step["service"] for step in report["steps"] if step["operation"] == "SERVICE"), None)
    require(service is not None and service["company"]["delivered_passengers"] > 0 and service["company"]["income"] > 0 and
            service["vehicle"]["running"], "M22 G15 useful passenger service failed")
    return run_root / "report.json", {
        "delivered": service["company"]["delivered_passengers"], "income": service["company"]["income"],
        "ticks": service["ticks"]["executed"], "vehicle_capacity": service["vehicle"]["capacity"],
    }


def simple_request(case: dict[str, Any], executable_sha: str, probe: str, schema: str) -> dict[str, Any]:
    return {"cargo_label": case["cargo"], "executable_sha256": executable_sha, "probe": probe,
            "run_id": case["case_id"], "schema_version": schema, "seed": case["seed"]}


def run_g16(root: pathlib.Path, runtime: RuntimePaths, run_root: pathlib.Path,
            case: dict[str, Any], executable_sha: str, probe: str,
            bwrap_path: pathlib.Path | None = None) -> tuple[pathlib.Path, dict[str, Any]]:
    request = {"amount": 8, "climate": case["climate"],
               **simple_request(case, executable_sha, probe, "openttd-rl-v2-m16-cargo-manifest-1")}
    write_new(run_root / "manifest.json", request)
    launch_case([*base_command(runtime), "-N", str(run_root / "manifest.json"), "-O", str(run_root / "report.json")],
                runtime, run_root, case, bwrap_path)
    report = load(run_root / "report.json")
    native_case = m16.Case(case["case_id"], case["climate"], case["cargo"], probe, case["seed"])
    m16.validate_common(report, native_case, m16.load(root / m16.CONTRACT), executable_sha)
    validate_map(report, case)
    return run_root / "report.json", m16.validate_probe(report, native_case)


def run_g17(root: pathlib.Path, runtime: RuntimePaths, run_root: pathlib.Path,
            case: dict[str, Any], executable_sha: str, probe: str,
            bwrap_path: pathlib.Path | None = None) -> tuple[pathlib.Path, dict[str, Any]]:
    write_new(run_root / "manifest.json", simple_request(case, executable_sha, probe, "openttd-rl-v2-m17-rail-manifest-1"))
    launch_case([*base_command(runtime), "-C", str(run_root / "manifest.json"), "-P", str(run_root / "report.json")],
                runtime, run_root, case, bwrap_path)
    report = load(run_root / "report.json")
    native_case = m17.Case(case["case_id"], case["cargo"], probe, case["seed"])
    require(report["status"] == "PASS" and report["executable_sha256"] == executable_sha, "M22 G17 identity/status drifted")
    validate_map(report, case)
    return run_root / "report.json", m17.validate_probe(report, native_case)


def run_g18(root: pathlib.Path, runtime: RuntimePaths, run_root: pathlib.Path,
            case: dict[str, Any], executable_sha: str, probe: str,
            bwrap_path: pathlib.Path | None = None) -> tuple[pathlib.Path, dict[str, Any]]:
    write_new(run_root / "manifest.json", simple_request(case, executable_sha, probe, "openttd-rl-v2-m18-ship-manifest-1"))
    launch_case([*base_command(runtime), "-u", str(run_root / "manifest.json"), "-w", str(run_root / "report.json")],
                runtime, run_root, case, bwrap_path)
    report = load(run_root / "report.json")
    native_case = m18.Case(case["case_id"], case["cargo"], probe, case["seed"])
    require(report["status"] == "PASS" and report["executable_sha256"] == executable_sha, "M22 G18 identity/status drifted")
    validate_map(report, case)
    return run_root / "report.json", m18.validate_probe(report, native_case)


def run_g19(root: pathlib.Path, runtime: RuntimePaths, run_root: pathlib.Path,
            case: dict[str, Any], executable_sha: str, probe: str,
            bwrap_path: pathlib.Path | None = None) -> tuple[pathlib.Path, dict[str, Any]]:
    write_new(run_root / "manifest.json", simple_request(case, executable_sha, probe, "openttd-rl-v2-m19-air-manifest-1"))
    launch_case([*base_command(runtime), "-a", str(run_root / "manifest.json"), "-z", str(run_root / "report.json")],
                runtime, run_root, case, bwrap_path)
    report = load(run_root / "report.json")
    native_case = m19.Case(case["case_id"], case["cargo"], probe, case["seed"])
    require(report["status"] == "PASS" and report["executable_sha256"] == executable_sha, "M22 G19 identity/status drifted")
    validate_map(report, case)
    return run_root / "report.json", m19.validate_probe(report, native_case)


def run_g20(root: pathlib.Path, runtime: RuntimePaths, run_root: pathlib.Path,
            case: dict[str, Any], executable_sha: str, probe: str,
            bwrap_path: pathlib.Path | None = None) -> tuple[pathlib.Path, dict[str, Any]]:
    contract = m20.load(root / m20.CONTRACT)
    identities = m20.expected_identities(root, contract)
    roster = next((item for item in contract["roster"] if item["name"] == case["opponent"]), None)
    require(roster is not None and probe == "head_to_head", "M22 G20 opponent/probe is not in the frozen roster")
    opponent = m20.opponent_from(roster, 1, 0)
    native_case = m20.Case(case["case_id"], probe, 1000, case["seed"], derived_seed("competition-simulation", case["seed"]),
                           0, 0, (opponent,), "FINAL")
    source = {"source": {"tree": runtime.source_tree}, "executable": {"sha256": executable_sha}}
    request = m20.manifest(native_case, "final", identities, source, contract["development_qualification"]["calendar_days"])
    request["run_id"] = case["case_id"]
    request["split"] = "final"
    write_new(run_root / "manifest.json", request)
    command = [str(runtime.executable), "-x", "-X", "-c", str(runtime.base_config), "-I", "OpenGFX", "-m", "null",
               "-s", "null", "-v", "null", "-i", str(run_root / "manifest.json"), "-y", str(run_root / "report.json")]
    launch_case(command, runtime, run_root, case, bwrap_path)
    report = load(run_root / "report.json")
    require(report["status"] == "PASS" and report["request"]["split"] == "final" and report["identity"] == identities,
            "M22 G20 status/split/identity drifted")
    result = report["result"]
    public_map = result["policy_input"]["public_map"]
    require(public_map["width"] == case["map_width"] and public_map["height"] == case["map_height"] and
            result["save_load_public_exact"] and result["privileged_inputs"] == [], "M22 G20 public-state boundary drifted")
    rl = result["score"]["rl"]
    require(rl["alive"] and rl["aircraft"] >= 1 and rl["delivered_cargo_units"] >= 25 and
            len(result["score"]["opponents"]) == 1 and result["score"]["opponents"][0]["name"] == case["opponent"],
            "M22 G20 competence/opponent projection failed")
    return run_root / "report.json", {"delivered": rl["delivered_cargo_units"], "income": rl["operating_profit"],
                                      "ticks": contract["development_qualification"]["calendar_days"],
                                      "company_value": rl["company_value"], "opponent": case["opponent"]}


def run_g21(root: pathlib.Path, runtime: RuntimePaths, run_root: pathlib.Path,
            case: dict[str, Any], executable_sha: str, probe: str,
            bwrap_path: pathlib.Path | None = None) -> tuple[pathlib.Path, dict[str, Any]]:
    contract = m21.load(root / m21.CONTRACT)
    native_case = {"case_id": case["case_id"], "landscape": case["climate"], "probe": probe, "seed": case["seed"]}
    source = {"source": {"tree": runtime.source_tree}, "executable": {"sha256": executable_sha}}
    contract_sha, content_sha = sha256(root / m21.CONTRACT), sha256(root / m21.CONTENT_LOCK)
    request = m21.manifest(native_case, "final", contract, source, contract_sha, content_sha)
    request["run_id"] = case["case_id"]
    write_new(run_root / "manifest.json", request)
    config = runtime.gamescript_config if probe == "gamescript" else runtime.content_config if probe == "content" else runtime.base_config
    command = [str(runtime.executable), "-x", "-X", "-I", "OpenGFX", "-m", "null", "-s", "null", "-v", "null",
               "-c", str(config), "-j", str(run_root / "manifest.json"), "-k", str(run_root / "report.json")]
    launch_case(command, runtime, run_root, case, bwrap_path)
    report = load(run_root / "report.json")
    validate_map(report, case)
    require(report["status"] == "PASS" and report["request"]["probe"] == probe and
            report["request"]["landscape"] == case["climate"], "M22 G21 request/status drifted")
    result = report["result"]
    if probe == "calendar":
        require(result["save_load_exact"] and result["span_years"] == 200, "M22 G21 calendar failed")
        metrics = {"boundaries": len(result["snapshots"]), "save_load_exact": True}
    elif probe == "authority_economy":
        require(result["save_load_exact"] and result["exclusive_rights_expired"], "M22 G21 authority/economy failed")
        metrics = {"commands": len(result["commands"]), "save_load_exact": True}
    elif probe == "events":
        require(result["save_load_exact"] and result["breakdown"]["observed"] and result["disaster"]["terminated"],
                "M22 G21 event recovery failed")
        metrics = {"recovery_ticks": result["breakdown"]["recovery_ticks"], "save_load_exact": True}
    elif probe == "gamescript":
        require(result["fixture_name"] == "M21CoverageFixture" and result["save_load_exact"] and
                all(result["responses"].values()), "M22 G21 Game Script failed")
        metrics = {"commands": len(result["commands"]), "responses": len(result["responses"]), "save_load_exact": True}
    else:
        require(probe == "content" and result["package_count"] == 10 and result["capability_schema_closed"] and
                len(report["active_content"]) == 10 and all(value > 0 for value in result["assets"].values()),
                "M22 G21 content discovery failed")
        metrics = {"packages": 10, "capabilities": len(result["capabilities"])}
    return run_root / "report.json", metrics


def run_native_case(root: pathlib.Path, runtime: RuntimePaths, artifact_root: pathlib.Path,
                    case: dict[str, Any], *, bwrap_path: pathlib.Path | None = None) -> dict[str, Any]:
    root, artifact_root = root.resolve(), artifact_root.resolve()
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "M22 native artifact root must be new")
    require(case["case_id"] and case["source_gate"] in {f"G{gate}" for gate in range(15, 22)}, "M22 native case identity drifted")
    require(case["map_width"] in (64, 128, 512, 1024) and case["map_height"] in (64, 128, 1024) and
            case["map_width"] * case["map_height"] <= 1_048_576, "M22 native map domain drifted")
    executable_sha = validate_runtime(runtime)
    probe = canonical_probe(case)
    artifact_root.mkdir(mode=0o700)
    gate = case["source_gate"]
    started = time.monotonic()
    if gate == "G15":
        report_path, metrics = run_g15(root, runtime, artifact_root, case, executable_sha, bwrap_path)
    elif gate == "G16":
        report_path, metrics = run_g16(root, runtime, artifact_root, case, executable_sha, probe, bwrap_path)
    elif gate == "G17":
        report_path, metrics = run_g17(root, runtime, artifact_root, case, executable_sha, probe, bwrap_path)
    elif gate == "G18":
        report_path, metrics = run_g18(root, runtime, artifact_root, case, executable_sha, probe, bwrap_path)
    elif gate == "G19":
        report_path, metrics = run_g19(root, runtime, artifact_root, case, executable_sha, probe, bwrap_path)
    elif gate == "G20":
        report_path, metrics = run_g20(root, runtime, artifact_root, case, executable_sha, probe, bwrap_path)
    else:
        report_path, metrics = run_g21(root, runtime, artifact_root, case, executable_sha, probe, bwrap_path)
    elapsed = round(time.monotonic() - started, 6)
    log_path = artifact_root / "openttd.log"
    return {
        "case": public_case(case), "executable_sha256": executable_sha, "fresh_processes": 1,
        "manifest_path": "manifest.json", "manifest_sha256": sha256(artifact_root / "manifest.json"),
        "metrics": metrics, "native_probe": probe, "network_unshared": True,
        "openttd_log_path": "openttd.log", "openttd_log_sha256": sha256(log_path),
        "report_path": str(report_path.relative_to(artifact_root)), "report_sha256": sha256(report_path),
        "source_tree": runtime.source_tree, "status": "PASS", "wall_seconds": elapsed,
    }
