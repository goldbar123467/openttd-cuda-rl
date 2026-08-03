#!/usr/bin/env python3
"""Reproduce the frozen, unseen M22 independent follow-up-v2 manifest."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import sys
from typing import Any

import validate_m22_learning_contract as learning


MANIFEST = pathlib.Path("config/v2/m22-followup-v2-manifest.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m22-followup-v2-manifest.schema.json")
BASE_MANIFEST = pathlib.Path("config/v2/m22-evaluation-manifest.json")
LEARNING_CONTRACT = pathlib.Path("config/v2/m22-learning-contract.json")
QUALIFICATION = pathlib.Path("config/v2/m22-qualification-evidence.json")
CORRECTED_RUNTIME = pathlib.Path("config/v2/m22-followup-runtime-source.json")
IMMUTABLE_FINAL = pathlib.Path("config/v2/m22-final-evaluation-evidence.json")
IMMUTABLE_FOLLOWUP_V1 = pathlib.Path("config/v2/m22-followup-evaluation-evidence.json")
DOMAIN = "openttd-rl-v2-m22-independent-followup-v2"
ORDINAL_START = 3000
EXTERNAL_DIAGNOSTIC_SEEDS = (1900000001, 1900000011, 1900000013, 1900000017, 1900000021, 1900000023)
EXTERNAL_DIAGNOSTIC_SUMMARY_SHA256 = "3f662a56713347cdf646c93c8c10b28a137ecc2dffc446bc338ec0bc65f5b50d"
PREFLIGHT_SEEDS = (225501, 225503)
SEED_SOURCES = (
    pathlib.Path("config/v2/m22-learning-contract.json"),
    pathlib.Path("config/v2/m22-native-corpus.json"),
    pathlib.Path("config/v2/m22-training-evidence.json"),
    pathlib.Path("config/v2/m22-qualification-evidence.json"),
    pathlib.Path("config/v2/m22-recovery-evidence.json"),
    pathlib.Path("config/v2/m22-recovery-evidence-v2.json"),
    pathlib.Path("config/v2/m22-evaluation-manifest.json"),
    pathlib.Path("config/v2/m22-final-evaluation-evidence.json"),
    pathlib.Path("config/v2/m22-final-runtime-source.json"),
    pathlib.Path("config/v2/m22-followup-runtime-source.json"),
    pathlib.Path("config/v2/m22-final-attempt-a.json"),
    pathlib.Path("config/v2/m22-followup-manifest.json"),
    pathlib.Path("config/v2/m22-followup-evaluation-evidence.json"),
)
SERVICE_PROGRAM_COUNTS = {
    "air-helicopter": 2,
    "air-service": 2,
    "multimodal-transfer": 2,
    "rail-freight": 2,
    "rail-passenger": 2,
    "road-cargo": 8,
    "road-passenger": 4,
    "ship-constructed": 2,
    "ship-natural": 2,
}
SERVICE_PROGRAM_MODES = {
    "air-helicopter": "air",
    "air-service": "air",
    "multimodal-transfer": "multimodal",
    "rail-freight": "rail",
    "rail-passenger": "rail",
    "road-cargo": "road",
    "road-passenger": "road",
    "ship-constructed": "water",
    "ship-natural": "water",
}


class M22FollowupV2ManifestBuildError(ValueError):
    """The independent follow-up manifest cannot be reproduced safely."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22FollowupV2ManifestBuildError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"nonfinite JSON constant: {token}")))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise M22FollowupV2ManifestBuildError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def collect_seed_values(value: Any, key: str = "") -> set[int]:
    seeds: set[int] = set()
    if isinstance(value, dict):
        for child_key, child in value.items():
            if "seed" in child_key.lower() and isinstance(child, int) and not isinstance(child, bool):
                seeds.add(child)
            seeds.update(collect_seed_values(child, child_key))
    elif isinstance(value, list):
        if "seed" in key.lower():
            seeds.update(item for item in value if isinstance(item, int) and not isinstance(item, bool))
        for child in value:
            seeds.update(collect_seed_values(child, key))
    return seeds


def seed_source_records(root: pathlib.Path) -> tuple[list[dict[str, str]], set[int]]:
    records: list[dict[str, str]] = []
    seeds: set[int] = set(EXTERNAL_DIAGNOSTIC_SEEDS) | set(PREFLIGHT_SEEDS)
    for relative in SEED_SOURCES:
        path = root / relative
        value = load(path)
        records.append({"path": relative.as_posix(), "sha256": sha256(path)})
        seeds.update(collect_seed_values(value))
    return records, seeds


def build(root: pathlib.Path) -> dict[str, Any]:
    root = root.resolve()
    base = load(root / BASE_MANIFEST)
    records, excluded = seed_source_records(root)
    cases = copy.deepcopy(base["cases"])
    derived = [learning.derived_seed(DOMAIN, ORDINAL_START + index) for index in range(len(cases))]
    require(len(cases) == len(derived) == 42 and len(set(derived)) == 42,
            "follow-up-v2 seed inventory is not exactly 42 unique values")
    require(not excluded.intersection(derived), "follow-up-v2 seed overlaps a prior M22 or diagnostic seed")
    for index, case in enumerate(cases):
        case["case_id"] = f"followup-v2-{case['case_id']}"
        case["seed"] = derived[index]
        if case["source_gate"] == "G20":
            case["map_width"] = 128
            case["map_height"] = 128
    return {
        "$schema": "../../docs/project/schema/v2-m22-followup-v2-manifest.schema.json",
        "acceptance": copy.deepcopy(base["acceptance"]),
        "aggregate_contract": {
            "admission": "required-program-membership-independent-of-task-label",
            "multimodal_transfer_task": "routing",
            "positive_metrics": ["delivered", "income"],
            "required_service_modes": ["road", "rail", "water", "air", "multimodal"],
            "service_program_counts": SERVICE_PROGRAM_COUNTS,
            "service_program_modes": SERVICE_PROGRAM_MODES,
        },
        "access_policy": {
            "case_execution": "one-fresh-evaluator-and-one-network-unshared-native-dispatch-per-case",
            "development_selection": "forbidden",
            "final_v1_evidence": "immutable-fail-preserved",
            "final_v1_cases": "never-retried-replaced-or-relabeled",
            "followup_v1_evidence": "immutable-zero-failure-aggregate-fail-preserved",
            "followup_v1_cases": "never-retried-replaced-or-relabeled",
            "followup_v2_runner": "fresh-process-read-only-once-after-source-freeze",
            "policy_input": "case-public-state-only-never-seed-or-required-program",
            "post_result_selection": False,
            "replacement": 0,
            "retry": 0,
            "training": "forbidden",
        },
        "cases": cases,
        "manifest_id": "m22-independent-followup-v2",
        "prerequisites": {
            "corrected_runtime_source_sha256": sha256(root / CORRECTED_RUNTIME),
            "immutable_final_v1_evidence_sha256": sha256(root / IMMUTABLE_FINAL),
            "immutable_followup_v1_evidence_sha256": sha256(root / IMMUTABLE_FOLLOWUP_V1),
            "learning_contract_sha256": sha256(root / LEARNING_CONTRACT),
            "qualification_evidence_sha256": sha256(root / QUALIFICATION),
        },
        "purpose": "independent-post-aggregate-diagnosis-confirmation-not-retry-or-replacement",
        "schema_sha256": sha256(root / SCHEMA),
        "schema_version": "openttd-rl-v2-m22-followup-v2-manifest-1",
        "seed_derivation": {
            "algorithm": "sha256-first-31-bits-big-endian",
            "domain": DOMAIN,
            "ordinal_start": ORDINAL_START,
        },
        "seed_exclusions": {
            "external_diagnostic_seeds": list(EXTERNAL_DIAGNOSTIC_SEEDS),
            "external_diagnostic_summary_sha256": EXTERNAL_DIAGNOSTIC_SUMMARY_SHA256,
            "preflight_seeds": list(PREFLIGHT_SEEDS),
            "repository_sources": records,
        },
        "snapshot_date": "2026-08-03",
        "split": "final",
        "status": "FROZEN_BEFORE_FIRST_RUN",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--print", action="store_true", dest="print_manifest")
    args = parser.parse_args()
    try:
        value = build(args.root)
        if args.print_manifest:
            sys.stdout.buffer.write(canonical_bytes(value))
            return 0
        path = args.root.resolve() / MANIFEST
        require(path.is_file() and not path.is_symlink(), f"frozen follow-up-v2 manifest is absent: {path}")
        require(path.read_bytes() == canonical_bytes(value), "frozen follow-up-v2 manifest is not reproducible")
    except (M22FollowupV2ManifestBuildError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_FOLLOWUP_V2_MANIFEST_BUILD=FAIL {exc}", file=sys.stderr)
        return 1
    print("V2_M22_FOLLOWUP_V2_MANIFEST_BUILD=PASS cases=42 unseen=true competition=128x128")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
