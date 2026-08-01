#!/usr/bin/env python3
"""Validate the V1 build-profile matrix and accepted baseline declarations."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from typing import Any

import jsonschema


class BuildProfileError(ValueError):
    """The build-profile matrix is incomplete, contradictory, or misleading."""


EXPECTED_PROFILES = {
    "asan",
    "cpp-debug-assertions-cpu",
    "cpp-optimized-cpu",
    "cuda-debug",
    "cuda-optimized",
    "playable-inference-only",
    "ubsan",
}
EXPECTED_FLAGS = {
    "assertions": "OPTION_USE_ASSERTS",
    "in_game_inference": "OPTION_RL_IN_GAME_INFERENCE",
    "rl_bridge": "OPTION_RL_BRIDGE",
    "telemetry": "OPTION_RL_TELEMETRY",
}


def load_json(path: pathlib.Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise BuildProfileError(f"{path}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                BuildProfileError(f"{path}: invalid JSON constant {value}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BuildProfileError(f"cannot load {path}: {exc}") from exc


def unique(values: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for value in values:
        identifier = value["id"]
        if identifier in result:
            raise BuildProfileError(f"duplicate {label}: {identifier}")
        result[identifier] = value
    return result


def validate(matrix_path: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    matrix = load_json(matrix_path)
    schema = load_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    try:
        jsonschema.Draft202012Validator(schema).validate(matrix)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(item) for item in exc.absolute_path) or "<root>"
        raise BuildProfileError(f"schema validation failed at {location}: {exc.message}") from exc

    profiles = unique(matrix["profiles"], "profile ID")
    if set(profiles) != EXPECTED_PROFILES:
        raise BuildProfileError(
            f"profile inventory mismatch: expected={sorted(EXPECTED_PROFILES)} "
            f"actual={sorted(profiles)}"
        )
    flags = unique(matrix["feature_flags"], "feature flag")
    observed_flags = {identifier: value["cmake_option"] for identifier, value in flags.items()}
    if observed_flags != EXPECTED_FLAGS:
        raise BuildProfileError(
            f"feature-flag inventory mismatch: expected={EXPECTED_FLAGS} actual={observed_flags}"
        )
    if any(value["default"] for identifier, value in flags.items() if identifier != "assertions"):
        raise BuildProfileError("RL bridge, in-game inference, and telemetry must default off")
    if not flags["assertions"]["default"]:
        raise BuildProfileError("assertions must default on")

    for identifier, profile in profiles.items():
        features = profile["features"]
        instrumentation = profile["instrumentation"]
        dependencies = profile["dependencies"]
        if profile["execution_state"] == "DEFINED_PENDING_TARGET" and not profile["resolution_task"]:
            raise BuildProfileError(f"pending profile lacks explicit resolution task: {identifier}")
        if dependencies["python_runtime"]:
            raise BuildProfileError(f"production profile depends on Python at runtime: {identifier}")
        if identifier == "asan" and not instrumentation["address_sanitizer"]:
            raise BuildProfileError("ASan profile does not enable the address sanitizer")
        if identifier == "ubsan" and not instrumentation["undefined_sanitizer"]:
            raise BuildProfileError("UBSan profile does not enable the undefined-behavior sanitizer")
        if identifier == "cuda-debug" and not instrumentation["cuda_debug"]:
            raise BuildProfileError("CUDA debug profile does not enable CUDA debugging")
        if identifier.startswith("cuda-") and not (dependencies["cuda"] and dependencies["libtorch"]):
            raise BuildProfileError(f"CUDA profile lacks CUDA/LibTorch dependency: {identifier}")
        if identifier == "playable-inference-only":
            expected = {
                "cuda": False,
                "libtorch": False,
                "onnxruntime": True,
                "python_runtime": False,
            }
            if dependencies != expected or not features["in_game_inference"]:
                raise BuildProfileError("playable inference-only dependency boundary is invalid")

    baselines = unique(matrix["accepted_baselines"], "accepted baseline")
    run_ids: set[str] = set()
    for identifier, baseline in baselines.items():
        for run_id in baseline["accepted_runs"]:
            if run_id in run_ids:
                raise BuildProfileError(f"accepted run reused by multiple baselines: {run_id}")
            run_ids.add(run_id)
        if baseline["profile_id"] not in profiles:
            raise BuildProfileError(
                f"accepted baseline {identifier} names unknown profile {baseline['profile_id']}"
            )
        if baseline["worker_eligible"]:
            raise BuildProfileError(
                f"M01 accepted baseline is incorrectly worker eligible: {identifier}"
            )
    headless = baselines.get("dedicated-headless-release-evidence")
    if headless is None or "never an RL worker" not in headless["artifact_role"]:
        raise BuildProfileError("dedicated headless evidence lacks the worker prohibition")

    canonical = json.dumps(matrix, sort_keys=True, separators=(",", ":")).encode()
    return {
        "matrix_sha256": hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
        "matrix_identity_sha256": hashlib.sha256(canonical).hexdigest(),
        "profiles": len(profiles),
        "baselines": len(baselines),
        "pending_profiles": sum(
            profile["execution_state"] == "DEFINED_PENDING_TARGET"
            for profile in profiles.values()
        ),
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True, type=pathlib.Path)
    parser.add_argument("--schema", required=True, type=pathlib.Path)
    options = parser.parse_args(arguments)
    try:
        summary = validate(options.matrix, options.schema)
    except (BuildProfileError, OSError, UnicodeError) as exc:
        print(f"V1_BUILD_PROFILES=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "V1_BUILD_PROFILES=PASS "
        f"profiles={summary['profiles']} baselines={summary['baselines']} "
        f"pending={summary['pending_profiles']} identity={summary['matrix_identity_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
