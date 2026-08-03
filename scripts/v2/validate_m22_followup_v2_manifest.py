#!/usr/bin/env python3
"""Independently validate the frozen, pre-access M22 follow-up-v2 protocol."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import sys
from collections import Counter
from typing import Any

import jsonschema

import build_m22_followup_v2_manifest as builder
import run_m22_final_evaluation as final
import validate_m22_followup_evaluation as followup_v1_validator
import validate_m22_learning_contract as learning


class M22FollowupV2ManifestError(ValueError):
    """The M22 follow-up-v2 protocol is incomplete, non-independent, or drifted."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22FollowupV2ManifestError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"nonfinite JSON constant: {token}")))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise M22FollowupV2ManifestError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def schema_validate(value: dict[str, Any], schema: dict[str, Any]) -> None:
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M22FollowupV2ManifestError(f"follow-up-v2 manifest schema failed at {where}: {exc.message}") from exc


def comparable_case(case: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(case)
    value.pop("case_id")
    value.pop("seed")
    if value["source_gate"] == "G20":
        value["map_width"] = 128
        value["map_height"] = 128
    return value


def validate_value(root: pathlib.Path, manifest: dict[str, Any], manifest_bytes: bytes) -> dict[str, Any]:
    root = root.resolve()
    schema_validate(manifest, load(root / builder.SCHEMA))
    expected = builder.build(root)
    require(manifest == expected and manifest_bytes == builder.canonical_bytes(expected),
            "follow-up-v2 manifest is not the canonical deterministic build")

    immutable = load(root / builder.IMMUTABLE_FINAL)
    immutable_followup_v1 = load(root / builder.IMMUTABLE_FOLLOWUP_V1)
    runtime = load(root / builder.CORRECTED_RUNTIME)
    qualification = load(root / builder.QUALIFICATION)
    base = load(root / builder.BASE_MANIFEST)
    require(immutable["status"] == "FAIL" and len(immutable["runs"]) == 42 and
            immutable["protocol"]["cases_attempted"] == 42,
            "immutable final-v1 failure boundary drifted")
    require(followup_v1_validator.validate(root) ==
            {"cases": 42, "failures": 0, "live": False, "status": "FAIL"} and
            immutable_followup_v1["acceptance"]["overall"] is False and
            immutable_followup_v1["acceptance"]["service_every_mode"] is False and
            all(value for key, value in immutable_followup_v1["acceptance"].items()
                if key not in {"overall", "service_every_mode"}),
            "immutable follow-up-v1 zero-failure aggregate boundary drifted")
    require(runtime["status"] == "PASS" and runtime["boundaries"]["immutable_final_v1"]["status"] == "FAIL" and
            runtime["boundaries"]["followup"] == {
                "evaluator_processes": 0, "manifest_opened": False, "native_dispatches": 0,
                "protocol_state": "not-yet-frozen",
            }, "corrected runtime historical pre-follow-up boundary drifted")
    selected = qualification["finalized_selection"]
    require(selected["finalized"] and not selected["final_manifest_accessed"] and
            selected["checkpoint_id"] == immutable["identity"]["checkpoint_id"] and
            selected["checkpoint_id"] == immutable_followup_v1["identity"]["checkpoint_id"],
            "selected checkpoint changed across final-v1, follow-up-v1, and follow-up-v2 freeze")

    cases, base_cases = manifest["cases"], base["cases"]
    require(len(cases) == len(base_cases) == 42 and len({case["case_id"] for case in cases}) == 42,
            "follow-up-v2 case identity closure drifted")
    require({case["case_id"] for case in cases}.isdisjoint(case["case_id"] for case in base_cases) and
            all(case["case_id"] == f"followup-v2-{old['case_id']}"
                for case, old in zip(cases, base_cases, strict=True)),
            "follow-up-v2 case IDs do not preserve distinct deterministic lineage")
    require([comparable_case(case) for case in cases] == [comparable_case(case) for case in base_cases],
            "follow-up-v2 changed more than case identity, seed, or corrected G20 dimensions")

    seeds = [case["seed"] for case in cases]
    derived = [learning.derived_seed(builder.DOMAIN, builder.ORDINAL_START + index) for index in range(42)]
    _, excluded = builder.seed_source_records(root)
    require(seeds == derived and len(set(seeds)) == 42 and not set(seeds).intersection(excluded),
            "follow-up-v2 seed derivation, uniqueness, or unseen boundary drifted")
    prior_followup_seeds = {case["private_seed"] for case in immutable_followup_v1["runs"]}
    require(set(seeds).isdisjoint(prior_followup_seeds),
            "follow-up-v2 seed overlaps immutable follow-up-v1 evidence")
    require(Counter(case["required_program"] for case in cases) ==
            Counter(case["required_program"] for case in base_cases),
            "follow-up-v2 program distribution drifted from the original independent suite")
    contract = load(root / builder.LEARNING_CONTRACT)
    program_gate = {item["id"]: item["source_gate"] for item in contract["policy_interface"]["programs"]}
    for case in cases:
        require(case["required_program"] in final.PROGRAM_INDEX and
                program_gate[case["required_program"]] == case["source_gate"] and
                final.public_program(case) == case["required_program"],
                f"follow-up-v2 public capability/program gate drifted: {case['case_id']}")

    service = [case for case in cases if case["required_program"] in builder.SERVICE_PROGRAM_COUNTS]
    require(Counter(case["required_program"] for case in service) == Counter(builder.SERVICE_PROGRAM_COUNTS) and
            all(case["transport_mode"] == builder.SERVICE_PROGRAM_MODES[case["required_program"]]
                for case in service) and
            all(case["task"] == "routing" for case in service
                if case["required_program"] == "multimodal-transfer") and
            {case["transport_mode"] for case in service} == final.SERVICE_MODES,
            "follow-up-v2 aggregate service-program admission contract drifted")

    competition = [case for case in cases if case["source_gate"] == "G20"]
    require(len(competition) == 6 and all((case["map_width"], case["map_height"]) == (128, 128)
                                          for case in competition) and
            Counter(case["opponent"] for case in competition) ==
            Counter({"AAAHogEx": 2, "KrakenAI2": 2, "NoOpAI": 2}),
            "follow-up-v2 competition contract is not two 128x128 cases per qualified opponent")
    require({case["transport_mode"] for case in cases} == learning.MODES and
            {case["climate"] for case in cases} == learning.CLIMATES and
            {(case["map_width"], case["map_height"]) for case in cases} == final.EXPECTED_SIZES and
            {case["opponent"] for case in cases if case["opponent"] != "not-applicable"} == learning.OPPONENTS,
            "follow-up-v2 mode, climate, size, or opponent coverage drifted")
    return {
        "cases": len(cases), "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "programs": len(set(case["required_program"] for case in cases)), "unseen_seeds": len(seeds),
    }


def validate(root: pathlib.Path, config_path: pathlib.Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = config_path or root / builder.MANIFEST
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes, parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"nonfinite JSON constant: {token}")))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise M22FollowupV2ManifestError(f"cannot load JSON {manifest_path}: {exc}") from exc
    require(isinstance(manifest, dict), f"JSON root is not an object: {manifest_path}")
    return validate_value(root, manifest, manifest_bytes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    args = parser.parse_args()
    try:
        result = validate(args.root, args.config)
    except (M22FollowupV2ManifestError, builder.M22FollowupV2ManifestBuildError, OSError, KeyError, TypeError,
            ValueError) as exc:
        print(f"V2_M22_FOLLOWUP_V2_MANIFEST=FAIL {exc}", file=sys.stderr)
        return 1
    print(f"V2_M22_FOLLOWUP_V2_MANIFEST=PASS cases={result['cases']} programs={result['programs']} "
          f"unseen_seeds={result['unseen_seeds']} sha256={result['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
