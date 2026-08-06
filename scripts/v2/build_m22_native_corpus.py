#!/usr/bin/env python3
"""Build the M22 learning corpus only from accepted native G15-G21 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import sys
from typing import Any

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    add_artifact_root_argument,
    resolve_artifact_root,
)
import validate_m15_competence_evidence
import validate_m16_cargo_evidence
import validate_m17_rail_evidence
import validate_m18_ship_evidence
import validate_m19_air_evidence
import validate_m20_competition_evidence
import validate_m21_broad_evidence


SCHEMA = pathlib.Path("docs/project/schema/v2-m22-native-corpus.schema.json")
PROGRAMS = [
    "wait", "road-passenger", "road-cargo", "rail-passenger", "rail-freight", "ship-natural",
    "ship-constructed", "air-service", "air-helicopter", "multimodal-transfer", "mode-router",
    "competition-head-to-head", "calendar-inspect", "authority-economy", "event-recovery",
    "gamescript-response", "content-discovery",
]
SOURCES = {
    "G15": pathlib.Path("config/v2/m15-competence-evidence.json"),
    "G16": pathlib.Path("config/v2/m16-cargo-evidence.json"),
    "G17": pathlib.Path("config/v2/m17-rail-evidence.json"),
    "G18": pathlib.Path("config/v2/m18-ship-evidence.json"),
    "G19": pathlib.Path("config/v2/m19-air-evidence.json"),
    "G20": pathlib.Path("config/v2/m20-competition-evidence.json"),
    "G21": pathlib.Path("config/v2/m21-broad-evidence.json"),
}
PROGRAM_CASES = {
    "road-passenger": ("G15", "curriculum-64x64", "held-out-512x128", "road", "temperate", "PASS", "not-applicable", "standard"),
    "road-cargo": ("G16", "single-temperate-coal-s0", "single-toyland-sugr-s1", "road", "temperate", "COAL", "not-applicable", "freight"),
    "rail-passenger": ("G17", "passenger-s0", "passenger-s1", "rail", "temperate", "PASS", "not-applicable", "passenger"),
    "rail-freight": ("G17", "freight-s0", "freight-s1", "rail", "temperate", "COAL", "not-applicable", "freight"),
    "ship-natural": ("G18", "natural-s0", "natural-s1", "water", "temperate", "PASS", "not-applicable", "natural"),
    "ship-constructed": ("G18", "constructed-s0", "constructed-s1", "water", "temperate", "COAL", "not-applicable", "constructed"),
    "air-service": ("G19", "service-s0", "service-s1", "air", "temperate", "PASS", "not-applicable", "airplane"),
    "air-helicopter": ("G19", "helicopter-s0", "helicopter-s1", "air", "temperate", "GOOD", "not-applicable", "helicopter"),
    "multimodal-transfer": ("G19", "multimodal-s0", "multimodal-s1", "multimodal", "temperate", "GOOD", "not-applicable", "transfer"),
    "mode-router": ("G19", "router-s0", "router-s1", "multimodal", "temperate", "PASS", "not-applicable", "router"),
    "competition-head-to-head": ("G20", "round-robin-aaahogex-s0-a", "round-robin-krakenai2-s1-b", "company", "temperate", "PASS", "AAAHogEx", "head-to-head"),
    "calendar-inspect": ("G21", "calendar-temperate-s0", "calendar-toyland-s1", "broad", "temperate", "not-applicable", "not-applicable", "calendar"),
    "authority-economy": ("G21", "authority-economy-s0", "authority-economy-s1", "broad", "temperate", "not-applicable", "not-applicable", "authority-economy"),
    "event-recovery": ("G21", "events-s0", "events-s1", "broad", "temperate", "not-applicable", "not-applicable", "events"),
    "gamescript-response": ("G21", "gamescript-s0", "gamescript-s1", "broad", "temperate", "not-applicable", "not-applicable", "gamescript"),
    "content-discovery": ("G21", "content-s0", "content-s1", "broad", "temperate", "not-applicable", "not-applicable", "content"),
}
MODE_INDEX = {name: index for index, name in enumerate(("road", "rail", "water", "air", "multimodal", "company", "broad"))}
CLIMATE_INDEX = {name: index for index, name in enumerate(("temperate", "arctic", "tropic", "toyland"))}


class M22CorpusError(ValueError):
    """The accepted evidence cannot form the frozen M22 corpus."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22CorpusError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def derived_seed(domain: str, ordinal: int) -> int:
    return int.from_bytes(hashlib.sha256(f"{domain}:{ordinal}".encode("ascii")).digest()[:4], "big") & 0x7FFFFFFF


def validate_sources(
    root: pathlib.Path,
    *,
    artifact_context: ArtifactContext | None = None,
) -> None:
    context = artifact_context or ArtifactContext.offline()
    del context
    offline = ArtifactContext.offline()
    validate_m15_competence_evidence.validate(root, artifact_context=offline)
    validate_m16_cargo_evidence.validate(root, artifact_context=offline)
    validate_m17_rail_evidence.validate(root, artifact_context=offline)
    validate_m18_ship_evidence.validate(root, artifact_context=offline)
    validate_m19_air_evidence.validate(root, artifact_context=offline)
    validate_m20_competition_evidence.validate(root, artifact_context=offline)
    validate_m21_broad_evidence.validate(root, artifact_context=offline)


def find_case(evidence: dict[str, Any], case_id: str) -> dict[str, Any]:
    cases = [item for item in evidence["cases"] if item["case_id"] == case_id]
    require(len(cases) == 1, f"native evidence case is missing or duplicated: {case_id}")
    return cases[0]


def native_metrics(gate: str, case: dict[str, Any]) -> dict[str, Any]:
    if gate == "G15":
        delivered, income = case["delivered_passengers"], case["income"]
        success = case["useful_service"] and case["twin_process_exact"] and case["save_load_exact"]
        seed = case["seed"]
        probe = "m15-competence"
        identities = [case["trace_sha256"], case["observation_sha256"], case["candidate_sha256"]]
    elif gate in {"G16", "G17", "G18", "G19"}:
        delivered, income = case["metrics"]["delivered"], case["metrics"]["income"]
        success = case["twin_exact"]
        seed, probe = case["seed"], case["probe"]
        identities = [item["normalized_sha256"] for item in case["twins"]]
        if probe in {"single-leg", "passenger", "freight", "natural", "constructed", "service", "helicopter", "multimodal"}:
            success = success and delivered > 0 and income > 0
    elif gate == "G20":
        metrics = case["replicate_metrics"][0]
        delivered = metrics["rl"]["delivered_cargo_units"]
        income = metrics["rl"]["company_value"]
        success = case["projection_replay_exact"] and metrics["rl"]["alive"] and metrics["fault_contained"] and metrics["save_load_public_exact"]
        seed, probe = case["simulation_seed"], case["probe"]
        identities = [item["normalized_sha256"] for item in case["replicates"]]
    else:
        delivered = income = 0
        success = case["twin_exact"]
        seed, probe = case["seed"], case["probe"]
        identities = [item["normalized_sha256"] for item in case["replicates"]]
    require(success, f"native source case is not an accepted success: {case['case_id']}")
    reward = 1.0 + min(math.log1p(delivered) / 10.0, 1.0) + min(math.log1p(max(0, income)) / 20.0, 1.0)
    return {"delivered": delivered, "income_or_company_value": income, "probe": probe, "seed": seed,
            "success": success, "report_identities": identities, "reward": float(f"{reward:.9f}")}


def public_state(program: str, mode: str, climate: str, cargo: str, opponent: str, variant: str, case: dict[str, Any]) -> dict[str, Any]:
    width, height = (case.get("width", 64), case.get("height", 64))
    capabilities = [0] * 16
    capabilities[PROGRAMS.index(program) - 1] = 1
    return {
        "mode": mode, "mode_index": MODE_INDEX[mode], "climate": climate, "climate_index": CLIMATE_INDEX[climate],
        "map_width": width, "map_height": height, "cargo": cargo, "opponent": opponent, "variant": variant,
        "capabilities": capabilities,
        "policy_visibility": "public-native-state-and-declared-task-only-no-seed-or-label",
    }


def build(
    root: pathlib.Path,
    *,
    artifact_context: ArtifactContext | None = None,
) -> dict[str, Any]:
    context = artifact_context or ArtifactContext.offline()
    root = root.resolve()
    validate_sources(root, artifact_context=context)
    evidence = {gate: load(root / path) for gate, path in SOURCES.items()}
    entries: list[dict[str, Any]] = []
    for split, domain, ordinal_start in (("training", "openttd-rl-v2-m22-training-v1", 0),
                                          ("development", "openttd-rl-v2-m22-development-v1", 100)):
        for position, program in enumerate(PROGRAMS[1:]):
            gate, training_case, development_case, mode, climate, cargo, opponent, variant = PROGRAM_CASES[program]
            source_case = find_case(evidence[gate], training_case if split == "training" else development_case)
            metrics = native_metrics(gate, source_case)
            sampler_ordinal = ordinal_start + (position if split == "training" else position // 2)
            entries.append({
                "entry_id": f"{split}-{program}", "split": split, "sampler_seed": derived_seed(domain, sampler_ordinal),
                "program": program,
                "public_state": public_state(program, mode, climate, cargo, opponent, variant, source_case),
                "legal_programs": ["wait", program],
                "rewards": {"wait": 0.0, program: metrics.pop("reward")},
                "native": {"source_gate": gate, "evidence_path": SOURCES[gate].as_posix(),
                           "evidence_sha256": sha256(root / SOURCES[gate]), "case_id": source_case["case_id"], **metrics},
            })
    require(len(entries) == 32 and len({item["entry_id"] for item in entries}) == 32, "corpus entry closure drifted")
    for split in ("training", "development"):
        require([item["program"] for item in entries if item["split"] == split] == PROGRAMS[1:],
                f"{split} program coverage drifted")
    return {
        "$schema": "../../docs/project/schema/v2-m22-native-corpus.schema.json",
        "schema_version": "openttd-rl-v2-m22-native-corpus-1",
        "schema_sha256": sha256(root / SCHEMA),
        "snapshot_date": "2026-08-02",
        "corpus_id": "m22-native-qualified-program-corpus-v1",
        "status": "FROZEN",
        "sources": [{"gate": gate, "path": path.as_posix(), "sha256": sha256(root / path)} for gate, path in SOURCES.items()],
        "programs": [{"index": index, "id": program} for index, program in enumerate(PROGRAMS)],
        "reward": {
            "formula": "native_success + min(log1p(delivered)/10,1) + min(log1p(max(0,income_or_company_value))/20,1)",
            "wait": 0.0,
            "illegal": "masked-never-sampled",
            "provenance": "accepted native report fields only",
        },
        "entries": entries,
        "summary": {"entries": 32, "training": 16, "development": 16, "programs": 17, "native_gates": 7,
                    "final_entries": 0, "all_native_success": True},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=pathlib.Path, required=True)
    add_artifact_root_argument(parser)
    args = parser.parse_args()
    try:
        artifact_root = resolve_artifact_root(args.artifact_root)
        context = ArtifactContext.offline() if artifact_root is None else ArtifactContext.live(artifact_root)
        output = args.output.resolve()
        require(not output.exists() and not output.is_symlink(), f"output already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        value = build(args.root, artifact_context=context)
        output.write_bytes(canonical(value))
        print(f"V2_M22_NATIVE_CORPUS=PASS entries={len(value['entries'])} programs={len(value['programs'])} "
              f"sha256={sha256(output)} output={output}")
        return 0
    except (M22CorpusError, ArtifactContextError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_NATIVE_CORPUS=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
