#!/usr/bin/env python3
"""Validate all-architecture live OpenTTD M08 training/evaluation evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import math
import pathlib
import sys
from typing import Any

import jsonschema

import validate_m07_ppo_contract
from validate_m08_architecture_contract import canonical_bytes


class M08LiveError(ValueError):
    """The live M08 evidence does not close the architecture/environment gate."""


ARCHITECTURES = ["structured-mlp-v1", "spatial-cnn-v1", "combined-cnn-mlp-v1"]
DEVICES = ["cpu", "cuda:0", "cuda:0"]
METRICS = [
    "policy_loss", "value_loss", "entropy", "approximate_kl", "clip_fraction",
    "gradient_norm", "explained_variance", "learning_rate", "mean_rollout_reward",
    "minimum_rollout_reward", "maximum_rollout_reward",
]


def validate(manifest_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    manifest = validate_m07_ppo_contract.load_strict_json(manifest_path)
    schema = validate_m07_ppo_contract.load_strict_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(manifest)
    identity_payload = copy.deepcopy(manifest)
    observed_identity = identity_payload.pop("manifest_sha256")
    if hashlib.sha256(canonical_bytes(identity_payload)).hexdigest() != observed_identity:
        raise M08LiveError("live manifest semantic identity drifted")
    if [item["architecture"] for item in manifest["architectures"]] != ARCHITECTURES:
        raise M08LiveError("live architecture order or coverage drifted")
    if [item["device"] for item in manifest["architectures"]] != DEVICES:
        raise M08LiveError("live production device disposition drifted")
    expected_samples = (
        manifest["configuration"]["updates"]
        * manifest["configuration"]["rollout_length"]
        * manifest["configuration"]["environment_count"]
    )
    reward_vectors: list[list[tuple[float, float, float]]] = []
    for item in manifest["architectures"]:
        training = item["training"]
        if training["accepted_samples"] != expected_samples or len(training["updates"]) != manifest["configuration"]["updates"]:
            raise M08LiveError("live trainer sample/update accounting drifted")
        if [update["samples"] for update in training["updates"]] != [
            128 * index for index in range(1, manifest["configuration"]["updates"] + 1)
        ]:
            raise M08LiveError("live cumulative sample counters drifted")
        for update in training["updates"]:
            if not all(isinstance(update[field], (int, float)) and math.isfinite(update[field]) for field in METRICS):
                raise M08LiveError("live trainer emitted a nonfinite metric")
        reward_vectors.append([
            (update["mean_rollout_reward"], update["minimum_rollout_reward"], update["maximum_rollout_reward"])
            for update in training["updates"]
        ])
        evaluation = item["evaluation"]
        if not all(math.isfinite(evaluation[field]) for field in ("return", "income", "delivered_passengers")):
            raise M08LiveError("live evaluation emitted a nonfinite result")
    if reward_vectors[0] != reward_vectors[1] or reward_vectors[0] != reward_vectors[2]:
        raise M08LiveError("matched seeded environment reward trace changed across architecture/device paths")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=pathlib.Path)
    parser.add_argument("schema", type=pathlib.Path)
    args = parser.parse_args()
    try:
        manifest = validate(args.manifest, args.schema)
    except (M08LiveError, OSError, ValueError, jsonschema.ValidationError) as exc:
        print(f"M08_LIVE_ARCHITECTURES_REPORT=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M08_LIVE_ARCHITECTURES_REPORT=PASS architectures=3 "
        f"samples_each={manifest['architectures'][0]['training']['accepted_samples']} "
        f"openttd_sha256={manifest['compatibility']['openttd_executable_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
