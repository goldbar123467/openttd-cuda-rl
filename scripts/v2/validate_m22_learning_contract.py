#!/usr/bin/env python3
"""Validate the frozen M22 learner, curriculum, checkpoint, and final-evaluation contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema


CONTRACT = pathlib.Path("config/v2/m22-learning-contract.json")
CONTRACT_SCHEMA = pathlib.Path("docs/project/schema/v2-m22-learning-contract.schema.json")
EVALUATION = pathlib.Path("config/v2/m22-evaluation-manifest.json")
EVALUATION_SCHEMA = pathlib.Path("docs/project/schema/v2-m22-evaluation-manifest.schema.json")

IDENTITY_PATHS = {
    "v1_ppo_contract_sha256": "config/v1/m07-ppo-contract.json",
    "v1_architecture_contract_sha256": "config/v1/m08-architecture-cuda-contract.json",
    "v1_evaluation_contract_sha256": "config/v1/m09-evaluation-contract.json",
    "m15_scalable_contract_sha256": "config/v2/m15-scalable-contract.json",
    "m15_observation_contract_sha256": "config/v2/m15-observation-contract.json",
    "m15_action_contract_sha256": "config/v2/m15-action-contract.json",
    "m15_policy_contract_sha256": "config/v2/m15-policy-contract.json",
    "m16_cargo_contract_sha256": "config/v2/m16-cargo-contract.json",
    "m17_rail_contract_sha256": "config/v2/m17-rail-contract.json",
    "m18_ship_contract_sha256": "config/v2/m18-ship-contract.json",
    "m19_air_contract_sha256": "config/v2/m19-air-contract.json",
    "m20_competition_contract_sha256": "config/v2/m20-competition-contract.json",
    "m20_content_manifest_sha256": "config/v2/m20-content-manifest.json",
    "m21_broad_contract_sha256": "config/v2/m21-broad-contract.json",
    "m21_content_lock_sha256": "config/v2/m21-content-lock.json",
    "g21_gate_report_sha256": "docs/project/G21_GATE_REPORT.md",
    "m22_native_corpus_sha256": "config/v2/m22-native-corpus.json",
    "final_evaluation_manifest_sha256": EVALUATION.as_posix(),
}

PROGRAMS = [
    "wait", "road-passenger", "road-cargo", "rail-passenger", "rail-freight", "ship-natural",
    "ship-constructed", "air-service", "air-helicopter", "multimodal-transfer", "mode-router",
    "competition-head-to-head", "calendar-inspect", "authority-economy", "event-recovery",
    "gamescript-response", "content-discovery",
]
ARCHITECTURES = ["monolithic-generalist-v1", "specialist-router-v1", "public-heuristic-v1"]
MODES = {"road", "rail", "water", "air", "multimodal", "company", "broad"}
CLIMATES = {"temperate", "arctic", "tropic", "toyland"}
SIZES = {(64, 64), (128, 128), (512, 128), (1024, 1024)}
OPPONENTS = {"AAAHogEx", "KrakenAI2", "NoOpAI"}


class M22ContractError(ValueError):
    """The M22 contract or final manifest is inconsistent."""


@dataclass(frozen=True)
class M22ContractSummary:
    programs: int
    stages: int
    architectures: int
    trainer_seeds: int
    final_cases: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22ContractError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M22ContractError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def schema_validate(value: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as exc:
        location = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M22ContractError(f"{label} schema failed at {location}: {exc.message}") from exc


def derived_seed(domain: str, ordinal: int) -> int:
    digest = hashlib.sha256(f"{domain}:{ordinal}".encode("ascii")).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def validate(
    root: pathlib.Path,
    contract_path: pathlib.Path | None = None,
    evaluation_path: pathlib.Path | None = None,
) -> M22ContractSummary:
    root = root.resolve()
    contract_path = contract_path or root / CONTRACT
    evaluation_path = evaluation_path or root / EVALUATION
    contract, evaluation = load(contract_path), load(evaluation_path)
    contract_schema, evaluation_schema = load(root / CONTRACT_SCHEMA), load(root / EVALUATION_SCHEMA)
    schema_validate(contract, contract_schema, "M22 learning contract")
    schema_validate(evaluation, evaluation_schema, "M22 final evaluation manifest")
    require(contract["schema_sha256"] == sha256(root / CONTRACT_SCHEMA), "learning contract schema SHA-256 mismatch")
    require(evaluation["schema_sha256"] == sha256(root / EVALUATION_SCHEMA), "evaluation manifest schema SHA-256 mismatch")

    identities = contract["identities"]
    require(set(identities) == set(IDENTITY_PATHS), "learning contract identity inventory drifted")
    for key, relative in IDENTITY_PATHS.items():
        target = evaluation_path if key == "final_evaluation_manifest_sha256" else root / relative
        require(identities[key] == sha256(target), f"learning contract identity drifted: {key}")
    require(contract["independent_evaluation"]["manifest_sha256"] == sha256(evaluation_path),
            "independent evaluation manifest identity drifted")

    programs = contract["policy_interface"]["programs"]
    require([item["index"] for item in programs] == list(range(len(PROGRAMS))), "program indices drifted")
    require([item["id"] for item in programs] == PROGRAMS, "program inventory or order drifted")
    require(len({item["native_transaction"] for item in programs}) == len(programs), "program transaction mapping is not unique")
    program_gate = {item["id"]: item["source_gate"] for item in programs}
    extensions = contract["policy_interface"]["extensions"]
    require([item["name"] for item in extensions] == [
        "domain_tokens", "domain_token_kind", "domain_token_mask", "program_features", "program_mask",
    ], "policy extension inventory drifted")
    require(extensions[0]["shape"] == ["batch", 256, 64] and extensions[3]["shape"] == ["batch", 17, 64],
            "policy extension shapes drifted")
    require(contract["policy_interface"]["memory"] == {
        "kind": "GRUCell", "hidden_size": 256, "sequence_length": 8,
        "reset": "episode-boundary-explicit-bool-mask",
        "truncated_bptt": "exact-eight-boundaries-no-hidden-gradient-across-reset",
    }, "recurrent sequence boundary drifted")

    architectures = contract["architectures"]
    require([item["id"] for item in architectures] == ARCHITECTURES, "architecture inventory or order drifted")
    require([item["kind"] for item in architectures] == ["learned", "learned", "non-neural"],
            "architecture kind disposition drifted")
    require(architectures[1]["specialists"] == 7 and architectures[2]["trainable"] == "none",
            "specialist or non-neural baseline drifted")
    require([item["parameter_count"] for item in architectures] == [1457520, 1457520, 0],
            "architecture parameter count drifted")

    ppo = contract["ppo"]
    require(ppo["rollout_steps"] * ppo["parallel_environments"] == ppo["transitions_per_update"],
            "PPO rollout transition count drifted")
    require(ppo["transitions_per_update"] * ppo["updates"] == ppo["transitions_per_seed"],
            "PPO campaign transition count drifted")
    require(ppo["minibatch_size"] > 0 and ppo["transitions_per_update"] % ppo["minibatch_size"] == 0,
            "PPO minibatches are incomplete")
    require(0 < ppo["policy_clip"] < 1 and 0 < ppo["value_clip"] < 1 and ppo["maximum_gradient_norm"] > 0,
            "PPO numerical bounds drifted")

    seed_config = contract["seeds"]
    trainer = seed_config["trainer_seeds"]
    require(trainer == [derived_seed(seed_config["trainer_domain"], index) for index in range(3)], "trainer seed derivation drifted")
    require(len(trainer) == len(set(trainer)), "trainer seeds are not unique")
    environment_seeds: set[int] = set()
    for split, count in (("training", 16), ("development", 8)):
        item = seed_config["environment_domains"][split]
        expected = [derived_seed(item["domain"], item["ordinal_start"] + index) for index in range(count)]
        require(item["seeds"] == expected, f"{split} environment seed derivation drifted")
        require(not environment_seeds.intersection(expected), "training/development seed overlap")
        environment_seeds.update(expected)

    stages = contract["curriculum"]["stages"]
    require([item["index"] for item in stages] == list(range(7)), "curriculum stage order drifted")
    require(sum(item["weight"] for item in stages) == 100, "curriculum weights do not sum to 100")
    stage_programs = [program for item in stages for program in item["programs"]]
    require(stage_programs == PROGRAMS[1:], "curriculum does not cover every non-WAIT program exactly once")
    require(contract["curriculum"]["retention_interval_updates"] == 4, "retention interval drifted")

    environment = contract["environment_boundary"]
    require(environment["native_corpus"] == "config/v2/m22-native-corpus.json" and
            environment["native_corpus_entries"] == 32 and
            environment["native_corpus_builder"] == "scripts/v2/build_m22_native_corpus.py",
            "native corpus boundary drifted")

    checkpoint = contract["checkpoint"]
    require(checkpoint["schema_id"] == "v2-m22-generalist-checkpoint-v1" and checkpoint["inventory"] == [
        "COMMITTED", "m22.manifest", "model.pt", "optimizer.pt", "runtime.pt", "selection.json", "trainer-state.bin",
    ], "checkpoint schema or exact inventory drifted")
    require(checkpoint["boundary"] == "after-completed-ppo-update-and-retention-check-before-next-rollout" and
            checkpoint["cross_device"] == "canonical-CPU-payload-loadable-to-validated-runtime-device",
            "checkpoint boundary or cross-device contract drifted")
    require(checkpoint["recovery_fork_update"] + checkpoint["recovery_continue_updates"] <= ppo["updates"],
            "checkpoint recovery continuation exceeds the campaign")
    for state in ("optimizer-semantic-tensors", "all-rng-streams", "case-order", "hidden-state", "checkpoint-semantic-identity"):
        require(state in checkpoint["equivalence"], f"checkpoint recovery equivalence omitted {state}")
    device = contract["device"]
    require(device["production"] == "cuda:0" and device["oracle"] == "cpu" and not device["mixed_precision"] and not device["tf32"],
            "device semantic boundary drifted")
    require(all(value > 0 for value in device["tolerances"].values()), "device tolerance is not positive")

    cases = evaluation["cases"]
    require(len(cases) == 42 and evaluation["acceptance"]["case_count"] == 42, "final case count drifted")
    require(len({item["case_id"] for item in cases}) == 42, "final case IDs are not unique")
    require(len({item["seed"] for item in cases}) == 42, "final seeds are not unique")
    final_domain = evaluation["seed_derivation"]["domain"]
    final_start = evaluation["seed_derivation"]["ordinal_start"]
    require([item["seed"] for item in cases] == [derived_seed(final_domain, final_start + index) for index in range(42)],
            "final seed derivation or case order drifted")
    require(not environment_seeds.intersection(item["seed"] for item in cases), "final seed overlaps training/development")
    require({item["transport_mode"] for item in cases} == MODES, "final transport-mode coverage drifted")
    require({item["climate"] for item in cases} == CLIMATES, "final climate coverage drifted")
    require({(item["map_width"], item["map_height"]) for item in cases} == SIZES, "final map-size coverage drifted")
    require({item["opponent"] for item in cases if item["opponent"] != "not-applicable"} == OPPONENTS,
            "final opponent coverage drifted")
    for item in cases:
        require(item["required_program"] in PROGRAMS[1:], f"unknown required program in final case: {item['case_id']}")
        require(program_gate[item["required_program"]] == item["source_gate"], f"program/gate mismatch: {item['case_id']}")
    require(evaluation["access_policy"] == {
        "training": "forbidden",
        "development_selection": "forbidden",
        "final_runner": "fresh-process-read-only-once-after-selection",
        "policy_input": "case-public-state-only-never-seed-or-required-program",
    }, "final access policy drifted")
    require(contract["selection"]["final_manifest_read"] == "forbidden" and
            contract["independent_evaluation"]["checkpoint"] == "development-selected-before-manifest-access",
            "final-blind selection boundary drifted")
    require(contract["acceptance"]["required_transitions_per_seed"] == ppo["transitions_per_seed"] and
            contract["acceptance"]["final"].startswith("all 42"), "G22 acceptance count drifted")
    return M22ContractSummary(len(programs), len(stages), len(architectures), len(trainer), len(cases))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--contract", type=pathlib.Path)
    parser.add_argument("--evaluation", type=pathlib.Path)
    args = parser.parse_args()
    try:
        result = validate(args.root, args.contract, args.evaluation)
        print(f"V2_M22_LEARNING_CONTRACT=PASS programs={result.programs} stages={result.stages} "
              f"architectures={result.architectures} trainer_seeds={result.trainer_seeds} final_cases={result.final_cases}")
        return 0
    except (M22ContractError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_LEARNING_CONTRACT=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
