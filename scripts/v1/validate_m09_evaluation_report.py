#!/usr/bin/env python3
"""Validate M09 raw evidence, statistics, provenance, and gate claims."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import pathlib
import sys
from typing import Any

import jsonschema

import validate_m07_ppo_contract
from run_m09_evaluation import ARCHITECTURES, NUMERIC_METRICS, canonical_bytes, sha256_file


class M09ReportError(ValueError):
    """M09 final report or its raw evidence is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M09ReportError(message)


def validate(report_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    report = validate_m07_ppo_contract.load_strict_json(report_path)
    schema = validate_m07_ppo_contract.load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(report)
    identity = copy.deepcopy(report)
    observed = identity.pop("report_sha256")
    require(observed == hashlib.sha256(canonical_bytes(identity)).hexdigest(), "final report semantic identity drifted")
    raw_path = report_path.parent / report["raw_episodes"]["path"]
    require(raw_path.is_file() and sha256_file(raw_path) == report["raw_episodes"]["sha256"], "raw episode artifact identity drifted")
    episodes = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines()]
    require(len(episodes) == report["episode_count"] and len({item["episode_id"] for item in episodes}) == len(episodes), "raw episode count/identity drifted")
    require(sum(item["suite"] == "primary" for item in episodes) == 18, "primary matched matrix must contain 18 episodes")
    require(sum(item["suite"] == "baseline" for item in episodes) == 6, "baseline matrix must contain six episodes")
    require(sum(item["suite"] == "stochastic" for item in episodes) == 4, "stochastic matrix must contain four episodes")
    require(sum(item["suite"] == "robustness" for item in episodes) == 8, "robustness matrix must contain eight episodes")
    for item in episodes:
        require(item["template_id"] in ("m02-template-07", "m02-template-08"), "non-final template entered final report")
        require(item["metrics"]["station_rating"] is None, "unavailable station rating was fabricated")
        require(all(not isinstance(value, float) or math.isfinite(value) for value in item["metrics"].values() if value is not None), "raw metrics contain nonfinite value")
    require(set(report["architecture_statistics"]) == set(ARCHITECTURES), "architecture report coverage drifted")
    for architecture in ARCHITECTURES:
        require(set(report["architecture_statistics"][architecture]) == set(NUMERIC_METRICS), "architecture metric coverage drifted")
        for statistic in report["architecture_statistics"][architecture].values():
            require(len(statistic["seed_means"]) == 3, "statistics are not based on three matched training seeds")
    require(set(report["baseline_summaries"]) == {"seeded-random-legal-v1", "wait-only-trivial-v1", "m05-scripted-bus-v1"}, "baseline coverage drifted")
    require(
        {(item["architecture"], item["run_seed"]) for item in report["training_reward_by_run"]}
        == {(architecture, seed) for architecture in ARCHITECTURES for seed in (2026090101, 2026090102, 2026090103)},
        "training reward matched-run coverage drifted",
    )
    require(all(item["quality_metric"] is False for item in report["training_reward_by_run"]), "training reward was promoted to a quality metric")
    require(report["selection"]["final_results_used"] is False, "final results influenced selection")
    require(report["claims"]["baseline_superiority"] and report["claims"]["reliable_profitability"], "G09 claims do not pass")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=pathlib.Path)
    parser.add_argument("schema", type=pathlib.Path)
    args = parser.parse_args()
    try:
        report = validate(args.report, args.schema)
    except (M09ReportError, OSError, ValueError, jsonschema.ValidationError) as exc:
        print(f"M09_EVALUATION_REPORT=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        f"M09_EVALUATION_REPORT=PASS episodes={report['episode_count']} "
        f"profit={report['selected_primary_summary']['operating_profit']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
