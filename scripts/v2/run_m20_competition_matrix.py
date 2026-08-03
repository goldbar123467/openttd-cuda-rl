#!/usr/bin/env python3
"""Run the complete deterministic M20 shared-company competition qualification matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import random
import resource
import subprocess
import time
from dataclasses import dataclass
from typing import Any


CONTRACT = pathlib.Path("config/v2/m20-competition-contract.json")
SOURCE = pathlib.Path("config/v2/m20-competition-source.json")
COMPETITION_MANIFEST = pathlib.Path("config/v2/m14-competition-manifest.json")
MAP_MANIFEST = pathlib.Path("config/v2/m20-map-manifest.json")
SETTINGS_MANIFEST = pathlib.Path("config/v2/m20-settings-manifest.json")
CONTENT_MANIFEST = pathlib.Path("config/v2/m20-content-manifest.json")
POLICY_CONTRACT = pathlib.Path("config/v2/m15-policy-contract.json")
REPLICATES = ("a", "b")


class M20MatrixError(ValueError):
    """The native M20 matrix violated its frozen competition contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M20MatrixError(message)


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


@dataclass(frozen=True)
class Opponent:
    name: str
    version: int
    slot: int
    delay: int
    package_sha256: str
    runtime_sha256: str

    def manifest(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "package_evidence_sha256": self.package_sha256,
            "runtime_evidence_sha256": self.runtime_sha256,
            "slot": self.slot,
            "start_delay_days": self.delay,
            "version": self.version,
        }


@dataclass(frozen=True)
class Case:
    case_id: str
    probe: str
    seed_ordinal: int
    map_seed: int
    simulation_seed: int
    rl_slot: int
    rl_delay: int
    opponents: tuple[Opponent, ...]
    leg: str | None = None


def slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def opponent_from(record: dict[str, Any], slot: int, delay: int) -> Opponent:
    return Opponent(record["name"], record["declared_runtime_version"], slot, delay,
                    record["package_evidence_sha256"], record["runtime_evidence_sha256"])


def cases(contract: dict[str, Any]) -> list[Case]:
    roster = contract["roster"]
    seeds = contract["development_qualification"]["seed_pairs"]
    legs = contract["fairness"]["legs"]
    result: list[Case] = []
    for opponent in roster:
        for seed in seeds:
            for leg in legs:
                case_id = f"round-robin-{slug(opponent['name'])}-s{seed['ordinal']}-{leg['leg'].lower()}"
                result.append(Case(case_id, "head_to_head", seed["ordinal"], seed["map_seed"], seed["simulation_seed"],
                                   leg["rl_slot"], leg["rl_start_delay_days"],
                                   (opponent_from(opponent, leg["opponent_slot"], leg["opponent_start_delay_days"]),), leg["leg"]))
    for seed in seeds:
        result.append(Case(f"solo-s{seed['ordinal']}", "solo", seed["ordinal"], seed["map_seed"], seed["simulation_seed"],
                           0, 0, ()))
    for seed in seeds:
        field = tuple(opponent_from(record, index + 1, 0) for index, record in enumerate(roster))
        result.append(Case(f"mixed-field-s{seed['ordinal']}", "mixed_field", seed["ordinal"], seed["map_seed"],
                           seed["simulation_seed"], 0, 0, field))
    result.append(Case("fault-aaahogex-s0", "fault", seeds[0]["ordinal"], seeds[0]["map_seed"], seeds[0]["simulation_seed"],
                       0, 0, (opponent_from(roster[0], 1, 0),)))
    result.append(Case("fault-krakenai2-s1", "fault", seeds[1]["ordinal"], seeds[1]["map_seed"], seeds[1]["simulation_seed"],
                       0, 0, (opponent_from(roster[1], 1, 0),)))
    result.append(Case("interaction-aaahogex-s0", "interaction", seeds[0]["ordinal"], seeds[0]["map_seed"], seeds[0]["simulation_seed"],
                       0, 0, (opponent_from(roster[0], 1, 0),)))
    result.append(Case("interaction-krakenai2-s1", "interaction", seeds[1]["ordinal"], seeds[1]["map_seed"], seeds[1]["simulation_seed"],
                       0, 0, (opponent_from(roster[1], 1, 0),)))
    counts = contract["development_qualification"]["case_counts"]
    actual = {probe: sum(case.probe == probe for case in result) for probe in ("solo", "head_to_head", "mixed_field", "fault", "interaction")}
    require(actual == {key: counts[key] for key in actual} and len(result) == counts["total"], f"case inventory drifted: {actual}")
    return result


def apply_limits() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (2_147_483_648, 2_147_483_648))
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024 * 1024, 128 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))


def normalized(report: dict[str, Any]) -> bytes:
    value = json.loads(json.dumps(report))
    value.pop("run_id")
    value["request"].pop("run_id")
    value["result"].pop("save_bytes")
    return canonical_bytes(value)


def expected_identities(root: pathlib.Path, contract: dict[str, Any]) -> dict[str, str]:
    identities = {
        "competition_manifest_sha256": sha256_file(root / COMPETITION_MANIFEST),
        "content_manifest_sha256": sha256_file(root / CONTENT_MANIFEST),
        "m20_contract_sha256": sha256_file(root / CONTRACT),
        "map_manifest_sha256": sha256_file(root / MAP_MANIFEST),
        "policy_package_sha256": sha256_file(root / POLICY_CONTRACT),
        "settings_manifest_sha256": sha256_file(root / SETTINGS_MANIFEST),
    }
    frozen = contract["identities"]
    require(identities["competition_manifest_sha256"] == frozen["competition_manifest_sha256"], "M14 competition identity drifted")
    require(identities["content_manifest_sha256"] == frozen["content_manifest_sha256"], "content identity drifted")
    require(identities["map_manifest_sha256"] == frozen["map_manifest_sha256"], "map identity drifted")
    require(identities["settings_manifest_sha256"] == frozen["settings_manifest_sha256"], "settings identity drifted")
    require(identities["policy_package_sha256"] == frozen["policy_contract_sha256"], "policy contract identity drifted")
    return identities


def manifest(case: Case, replicate: str, identities: dict[str, str], source: dict[str, Any], calendar_days: int) -> dict[str, Any]:
    return {
        "calendar_days": calendar_days,
        "competition_manifest_sha256": identities["competition_manifest_sha256"],
        "content_manifest_sha256": identities["content_manifest_sha256"],
        "engine_source_tree": source["source"]["tree"],
        "executable_sha256": source["executable"]["sha256"],
        "m20_contract_sha256": identities["m20_contract_sha256"],
        "map_manifest_sha256": identities["map_manifest_sha256"],
        "map_seed": case.map_seed,
        "opponents": [opponent.manifest() for opponent in case.opponents],
        "policy_package_sha256": identities["policy_package_sha256"],
        "probe": case.probe,
        "rl_slot": case.rl_slot,
        "rl_start_delay_days": case.rl_delay,
        "run_id": f"{case.case_id}-{replicate}",
        "schema_version": "openttd-rl-v2-m20-competition-run-1",
        "settings_manifest_sha256": identities["settings_manifest_sha256"],
        "simulation_seed": case.simulation_seed,
        "split": "development",
    }


def validate_common(report: dict[str, Any], case: Case, replicate: str, identities: dict[str, str], source: dict[str, Any],
                    contract: dict[str, Any]) -> None:
    require(report["schema_version"] == "openttd-rl-v2-m20-competition-report-1" and report["status"] == "PASS",
            f"report failed: {case.case_id}-{replicate}")
    require(report["run_id"] == f"{case.case_id}-{replicate}" and report["engine_source_tree"] == source["source"]["tree"] and
            report["executable_sha256"] == source["executable"]["sha256"], f"source identity drifted: {case.case_id}-{replicate}")
    require(report["identity"] == identities, f"run identity drifted: {case.case_id}-{replicate}")
    request = report["request"]
    require(request == {
        "calendar_days": contract["development_qualification"]["calendar_days"],
        "map_seed": case.map_seed,
        "opponents": [opponent.manifest() for opponent in case.opponents],
        "probe": case.probe,
        "rl_slot": case.rl_slot,
        "rl_start_delay_days": case.rl_delay,
        "run_id": f"{case.case_id}-{replicate}",
        "simulation_seed": case.simulation_seed,
        "split": "development",
    }, f"request projection drifted: {case.case_id}-{replicate}")
    result = report["result"]
    require(result["save_load_public_exact"] is True and result["save_bytes"] > 0, f"save/load failed: {case.case_id}-{replicate}")
    require(result["privileged_inputs"] == [] and result["policy_input_fields"] == contract["public_observation"]["allowed_policy_fields"],
            f"policy visibility drifted: {case.case_id}-{replicate}")
    require(sorted(result["policy_input"].keys()) == ["public_companies", "public_events", "public_map", "schema_version", "self_company_id"],
            f"policy input shape drifted: {case.case_id}-{replicate}")
    rl = result["score"]["rl"]
    require(rl["alive"] and rl["aircraft"] >= 1 and rl["delivered_cargo_units"] >= 25 and rl["crashed_vehicles"] == 0,
            f"solo competence was not retained: {case.case_id}-{replicate}")
    require(len(result["score"]["opponents"]) == len(case.opponents), f"score roster drifted: {case.case_id}-{replicate}")


def validate_probe(report: dict[str, Any], case: Case) -> dict[str, Any]:
    result, events = report["result"], report["result"]["events"]
    kinds = [event["kind"] for event in events]
    require(kinds.count("rl_started") == 1 and kinds.count("rl_service_started") == 1, f"RL launch event drifted: {case.case_id}")
    require(kinds.count("opponent_started") == len(case.opponents), f"opponent launch event drifted: {case.case_id}")
    if case.probe == "solo":
        require(not case.opponents and not result["score"]["opponents"], f"solo roster drifted: {case.case_id}")
    elif case.probe == "head_to_head":
        require(len(case.opponents) == 1 and result["interaction"] is None, f"head-to-head projection drifted: {case.case_id}")
    elif case.probe == "mixed_field":
        require([item["name"] for item in result["score"]["opponents"]] == ["AAAHogEx", "KrakenAI2", "NoOpAI"],
                f"mixed-field roster drifted: {case.case_id}")
    elif case.probe == "fault":
        require(result["fault_contained"] and kinds.count("opponent_failure_contained") == 1 and
                result["score"]["opponents"][0]["public_state"]["alive"] is False, f"fault containment failed: {case.case_id}")
    else:
        require(case.probe == "interaction" and result["interaction"]["subsidy_awarded"] and
                result["interaction"]["target_removed"] and kinds.count("subsidy_awarded") == 1 and
                kinds.count("company_acquired") == 1 and kinds.count("ownership_collision_rejected") == 1 and
                result["interaction"]["collision_disposition"] == {"crashed_vehicles_scored": True,
                    "ownership_collision_rejected": True, "physical_plane_crashes_disabled": True},
                f"interaction projection failed: {case.case_id}")
    return {
        "company_value_differences": [item["company_value_difference"] for item in result["score"]["opponents"]],
        "fault_contained": result["fault_contained"],
        "opponent_states": [{"alive": item["public_state"]["alive"], "company_value": item["public_state"].get("company_value", 0),
                             "delivered_cargo_units": item["public_state"].get("delivered_cargo_units", 0), "name": item["name"],
                             "operating_profit": item["public_state"].get("operating_profit", 0)} for item in result["score"]["opponents"]],
        "rl": {"alive": result["score"]["rl"]["alive"], "company_value": result["score"]["rl"]["company_value"],
               "delivered_cargo_units": result["score"]["rl"]["delivered_cargo_units"],
               "operating_profit": result["score"]["rl"]["operating_profit"]},
        "save_load_public_exact": result["save_load_public_exact"],
    }


def run_one(executable: pathlib.Path, runtime_config: pathlib.Path, artifact_root: pathlib.Path, case: Case, replicate: str,
            identities: dict[str, str], source: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    run_root = artifact_root / case.case_id / f"replicate-{replicate}"
    run_root.mkdir(parents=True, mode=0o700)
    request = manifest(case, replicate, identities, source, contract["development_qualification"]["calendar_days"])
    write_new(run_root / "manifest.json", request)
    command = [str(executable), "-x", "-X", "-c", str(runtime_config), "-I", "OpenGFX", "-m", "null", "-s", "null", "-v", "null",
               "-i", str(run_root / "manifest.json"), "-y", str(run_root / "report.json")]
    started = time.monotonic()
    completed = subprocess.run(command, cwd=executable.parent, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=120, preexec_fn=apply_limits, start_new_session=True)
    wall = time.monotonic() - started
    (run_root / "openttd.log").write_text(completed.stdout, encoding="utf-8")
    require(completed.returncode == 0, f"native run failed ({completed.returncode}) {case.case_id}-{replicate}: {completed.stdout.strip()}")
    report = load(run_root / "report.json")
    validate_common(report, case, replicate, identities, source, contract)
    return {"report": report, "report_path": str((run_root / "report.json").relative_to(artifact_root)),
            "report_sha256": sha256_file(run_root / "report.json"),
            "normalized_sha256": hashlib.sha256(normalized(report)).hexdigest(), "wall_seconds": round(wall, 6)}


def percentile_interval(values: list[float], confidence: float, resamples: int, rng: random.Random) -> list[float]:
    require(values, "cannot bootstrap an empty sample")
    samples = [sum(rng.choice(values) for _ in values) / len(values) for _ in range(resamples)]
    samples.sort()
    alpha = (1.0 - confidence) / 2.0
    low = samples[math.floor(alpha * (len(samples) - 1))]
    high = samples[math.ceil((1.0 - alpha) * (len(samples) - 1))]
    return [round(low, 6), round(high, 6)]


def scoring(cases_: list[Case], projected: list[dict[str, Any]], contract: dict[str, Any]) -> dict[str, Any]:
    by_case = {record["case_id"]: record for record in projected}
    block_values: dict[str, list[dict[str, Any]]] = {record["name"]: [] for record in contract["roster"]}
    for opponent in contract["roster"]:
        for seed in contract["development_qualification"]["seed_pairs"]:
            values = []
            for leg in contract["fairness"]["legs"]:
                case_id = f"round-robin-{slug(opponent['name'])}-s{seed['ordinal']}-{leg['leg'].lower()}"
                replicate_values = [item["company_value_differences"][0] for item in by_case[case_id]["replicate_metrics"]]
                values.append({"leg": leg["leg"], "mean": round(sum(replicate_values) / len(replicate_values), 6),
                               "replicate_values": replicate_values})
            block_values[opponent["name"]].append({"four_leg_mean": round(sum(item["mean"] for item in values) / len(values), 6),
                                                    "legs": values, "seed_ordinal": seed["ordinal"]})
    settings = contract["scoring"]
    rng = random.Random(settings["bootstrap_seed"])
    summaries = []
    for opponent in contract["roster"]:
        blocks = [item["four_leg_mean"] for item in block_values[opponent["name"]]]
        summaries.append({"admission": opponent["admission"], "blocks": block_values[opponent["name"]],
                          "confidence_interval": percentile_interval(blocks, settings["confidence"], settings["bootstrap_resamples"], rng),
                          "mean_company_value_difference": round(sum(blocks) / len(blocks), 6), "opponent": opponent["name"]})
    stratified_samples = []
    for _ in range(settings["bootstrap_resamples"]):
        strata = []
        for opponent in contract["roster"]:
            values = [item["four_leg_mean"] for item in block_values[opponent["name"]]]
            strata.append(sum(rng.choice(values) for _ in values) / len(values))
        stratified_samples.append(sum(strata) / len(strata))
    stratified_samples.sort()
    alpha = (1.0 - settings["confidence"]) / 2.0
    overall = [item["four_leg_mean"] for blocks in block_values.values() for item in blocks]
    return {
        "all_scheduled_runs_included": True,
        "bootstrap_resamples": settings["bootstrap_resamples"],
        "bootstrap_seed": settings["bootstrap_seed"],
        "confidence": settings["confidence"],
        "opponents": summaries,
        "overall_confidence_interval": [round(stratified_samples[math.floor(alpha * (len(stratified_samples) - 1))], 6),
                                        round(stratified_samples[math.ceil((1.0 - alpha) * (len(stratified_samples) - 1))], 6)],
        "overall_mean_company_value_difference": round(sum(overall) / len(overall), 6),
        "sample_unit": settings["sample_unit"],
        "universal_victory_required": False,
    }


def run(root: pathlib.Path, artifact_root: pathlib.Path, evidence_path: pathlib.Path) -> dict[str, Any]:
    root, artifact_root, evidence_path = root.resolve(), artifact_root.resolve(), evidence_path.resolve()
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "artifact root must be new")
    require(not evidence_path.exists() and not evidence_path.is_symlink(), "evidence output must be new")
    contract, source = load(root / CONTRACT), load(root / SOURCE)
    identities = expected_identities(root, contract)
    executable = pathlib.Path(source["executable"]["path"])
    runtime_config = pathlib.Path(source["runtime"]["config"]["path"])
    require(executable.is_file() and os.access(executable, os.X_OK) and sha256_file(executable) == source["executable"]["sha256"] and
            executable.stat().st_size == source["executable"]["bytes"], "M20 executable identity drifted")
    require(runtime_config.is_file() and sha256_file(runtime_config) == source["runtime"]["config"]["sha256"], "runtime config identity drifted")
    artifact_root.mkdir(mode=0o700)
    all_cases = cases(contract)
    projected = []
    maximum_wall = 0.0
    for ordinal, case in enumerate(all_cases, 1):
        replicates = [run_one(executable, runtime_config, artifact_root, case, replicate, identities, source, contract)
                      for replicate in REPLICATES]
        replicate_metrics = [validate_probe(item["report"], case) for item in replicates]
        maximum_wall = max(maximum_wall, *(item["wall_seconds"] for item in replicates))
        projected.append({"case_id": case.case_id, "leg": case.leg, "map_seed": case.map_seed,
                          "projection_replay_exact": True, "replicate_metrics": replicate_metrics,
                          "probe": case.probe, "seed_ordinal": case.seed_ordinal, "simulation_seed": case.simulation_seed,
                          "replicates": [{key: item[key] for key in ("name", "normalized_sha256", "report_path", "report_sha256", "wall_seconds")}
                                         for item in ({**replicates[0], "name": "a"}, {**replicates[1], "name": "b"})]})
        print(f"M20 case {ordinal:02d}/{len(all_cases)} PASS {case.case_id}", flush=True)
    score = scoring(all_cases, projected, contract)
    evidence = {
        "aggregate": {"all_scheduled_runs_included": True, "cases": len(all_cases), "fault_cases": 2,
                      "head_to_head_cases": 24, "interaction_cases": 2, "maximum_wall_seconds": round(maximum_wall, 6),
                      "mixed_field_cases": 2, "native_runs": len(all_cases) * 2, "opponents": 3, "seed_blocks": 6,
                      "projection_replay_exact_cases": len(all_cases), "replicates": len(all_cases) * 2, "solo_cases": 2},
        "artifact_root": str(artifact_root),
        "cases": projected,
        "contract_sha256": sha256_file(root / CONTRACT),
        "execution": {"external_ai_decision_stream": "stochastic-replicate", "fresh_process_per_run": True, "network_calls": "none",
                      "process_limits": True, "sandbox": "rlimit-only", "shared_native_map": True},
        "executable_sha256": source["executable"]["sha256"],
        "identities": identities,
        "runner_modes": ["solo", "head_to_head", "round_robin", "mixed_field", "fault", "interaction"],
        "schema_version": "openttd-rl-v2-m20-competition-evidence-1",
        "scoring": score,
        "source_sha256": sha256_file(root / SOURCE),
        "status": "PASS",
    }
    write_new(evidence_path, evidence)
    print(f"V2_M20_COMPETITION_MATRIX=PASS cases={len(all_cases)} native_runs={len(all_cases) * 2} projection_exact={len(all_cases)}")
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
    except (M20MatrixError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"V2_M20_COMPETITION_MATRIX=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
