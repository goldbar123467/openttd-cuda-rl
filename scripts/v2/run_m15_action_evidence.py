#!/usr/bin/env python3
"""Run the representative M15 candidate/action qualification matrix."""

from __future__ import annotations

import argparse
import json
import pathlib

import qualify_m15_action
import qualify_m15_native_reset


SEED = 1_110_312_784
MAP_CASES = [
    ("reset-0064x0064", 64, 64),
    ("repeat-0064x0064", 64, 64),
    ("reset-0064x0256", 64, 256),
    ("reset-0512x0128", 512, 128),
    ("reset-1024x1024", 1024, 1024),
]
POSITIVE_CASES = [
    ("positive-wait", 0, 0, "NO_OP", False),
    ("positive-select-town-pair", 1, 1, "SUCCESS", False),
    ("positive-build-road", 2, 257, "SUCCESS", True),
    ("positive-build-bus-stop", 3, 1281, "SUCCESS", True),
    ("positive-build-road-depot", 4, 2049, "SUCCESS", True),
    ("positive-manage-loan", 11, 3841, "SUCCESS", True),
]
NEGATIVE_CASES = [
    ("negative-stale-token", 2, 257, "STALE_TOKEN", "m15a1:" + "0" * 64),
    ("negative-out-of-range", 2, 4096, "OUT_OF_RANGE", None),
    ("negative-illegal-candidate", 1, 3, "ILLEGAL_CANDIDATE", None),
    ("negative-family-mismatch", 3, 257, "FAMILY_MISMATCH", None),
]


class M15ActionMatrixError(ValueError):
    """The representative action matrix is inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15ActionMatrixError(message)


def request(contract_sha256: str, token: str, family: int, row: int) -> dict[str, object]:
    return {
        "action_schema_id": "v2-m15-hierarchical-action-v1", "candidate_row": row,
        "contract_sha256": contract_sha256, "family_index": family,
        "schema_version": "openttd-rl-v2-m15-action-request-1", "snapshot_token": token,
    }


def run(root: pathlib.Path, openttd: pathlib.Path, opengfx: pathlib.Path, artifact_root: pathlib.Path, sandbox: str) -> pathlib.Path:
    root, openttd, opengfx, artifact_root = root.resolve(), openttd.resolve(), opengfx.resolve(), artifact_root.resolve()
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "action evidence root must be a new path")
    artifact_root.mkdir(mode=0o700)
    for directory, width, height in MAP_CASES:
        qualify_m15_action.qualify(root, openttd, opengfx, artifact_root / directory, width, height, SEED, sandbox=sandbox)
    primary = qualify_m15_action.load_json(artifact_root / MAP_CASES[0][0] / qualify_m15_action.CANDIDATE_METADATA_NAME)
    repeat = qualify_m15_action.load_json(artifact_root / MAP_CASES[1][0] / qualify_m15_action.CANDIDATE_METADATA_NAME)
    for field in ("binary", "observation_sha256", "families", "records", "sections", "snapshot"):
        require(primary[field] == repeat[field], f"deterministic repeat candidate {field} drifted")
    contract_sha256, token = primary["contract_sha256"], primary["snapshot"]["snapshot_token"]

    for directory, family, row, expected_status, should_mutate in POSITIVE_CASES:
        value = request(contract_sha256, token, family, row)
        qualify_m15_action.qualify(root, openttd, opengfx, artifact_root / directory, 64, 64, SEED, request=value, sandbox=sandbox)
        result = qualify_m15_action.load_json(artifact_root / directory / qualify_m15_action.RESULT_NAME)
        require(result["status"] == expected_status, f"positive action status drifted: {directory}")
        require(result["tick_before"] == result["tick_after"], f"positive action advanced a simulation tick: {directory}")
        require((result["state_sha256_before"] != result["state_sha256_after"]) == should_mutate, f"positive action mutation semantics drifted: {directory}")
        require((len(result["native_commands"]) > 0) == should_mutate, f"positive native command mapping drifted: {directory}")
        require(all(command["status"] == "SUCCESS" for command in result["native_commands"]), f"positive native command rejected: {directory}")

    for directory, family, row, expected_status, token_override in NEGATIVE_CASES:
        value = request(contract_sha256, token_override or token, family, row)
        qualify_m15_action.qualify(root, openttd, opengfx, artifact_root / directory, 64, 64, SEED, request=value, sandbox=sandbox)
        result = qualify_m15_action.load_json(artifact_root / directory / qualify_m15_action.RESULT_NAME)
        require(result["status"] == expected_status, f"negative action status drifted: {directory}")
        require(result["tick_before"] == result["tick_after"] and result["state_sha256_before"] == result["state_sha256_after"], f"negative action was not zero-tick/zero-mutation: {directory}")

    summary = {
        "schema_version": "openttd-rl-v2-m15-action-matrix-run-1", "outcome": "PASS", "seed": SEED,
        "map_cases": [item[0] for item in MAP_CASES], "positive_cases": [item[0] for item in POSITIVE_CASES],
        "negative_cases": [item[0] for item in NEGATIVE_CASES], "snapshot_token": token,
    }
    output = artifact_root / "matrix-run.json"
    qualify_m15_native_reset.canonical_write_new(output, summary)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--openttd", type=pathlib.Path, required=True)
    parser.add_argument("--opengfx", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--sandbox", choices=("bubblewrap", "test-none"), default="bubblewrap")
    args = parser.parse_args()
    try:
        result = run(args.root, args.openttd, args.opengfx, args.artifact_root, args.sandbox)
        print(f"V2_M15_ACTION_MATRIX=PASS summary={result}")
        return 0
    except (M15ActionMatrixError, qualify_m15_action.M15ActionError, OSError) as exc:
        print(f"V2_M15_ACTION_MATRIX=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
