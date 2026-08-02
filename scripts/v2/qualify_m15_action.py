#!/usr/bin/env python3
"""Run and independently decode one source-integrated M15 candidate/action boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import shutil
import struct
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

import jsonschema

import acquire_ai_package
import qualify_ai_runtime
import qualify_m15_native_reset
import qualify_m15_observation
import validate_m15_action_contract


CONTRACT = pathlib.Path("config/v2/m15-scalable-contract.json")
ACTION_CONTRACT = pathlib.Path("config/v2/m15-action-contract.json")
ACTION_SOURCE = pathlib.Path("config/v2/m15-action-source.json")
NATIVE_SOURCE = pathlib.Path("config/v2/m15-native-source.json")
METADATA_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-candidate-metadata.schema.json")
REQUEST_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-action-request.schema.json")
RESULT_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-action-result.schema.json")
MANIFEST_NAME = "reset-manifest.json"
PROJECTION_NAME = "reset-projection.json"
OBSERVATION_METADATA_NAME = "observation-metadata.json"
CANDIDATE_METADATA_NAME = "candidate-metadata.json"
CANDIDATE_BINARY_NAME = "candidate-metadata.bin"
REQUEST_NAME = "action-request.json"
RESULT_NAME = "action-result.json"
TRANSCRIPT_NAME = "openttd-action.log"
EVIDENCE_NAME = "action-evidence.json"
CANDIDATE_BYTES = 790_528


class M15ActionError(ValueError):
    """The native M15 candidate/action boundary failed qualification."""


@dataclass(frozen=True)
class M15ActionSummary:
    width: int
    height: int
    selected: int
    total_legal: int
    binary_sha256: str
    snapshot_token: str


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15ActionError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15ActionError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15ActionError(f"cannot hash {path}: {exc}") from exc


def canonical_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    expected = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    require(path.read_text(encoding="utf-8") == expected, f"JSON is not canonical: {path}")


def validate_schema(value: dict[str, Any], schema_path: pathlib.Path, label: str) -> None:
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(value)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15ActionError(f"{label} schema failed at {location}: {exc.message}") from exc


def build_manifest(root: pathlib.Path, openttd: pathlib.Path, opengfx: pathlib.Path, width: int, height: int, seed: int) -> dict[str, Any]:
    contract = load_json(root / CONTRACT)
    source = load_json(root / ACTION_SOURCE)
    native_source = load_json(root / NATIVE_SOURCE)
    require([width, height] in contract["map"]["native_rectangles"], "dimensions are not a frozen native rectangle")
    require(width * height <= qualify_m15_native_reset.MAXIMUM_TILES, "tile count exceeds the M15 action budget")
    executable = source["build"]["executable"]
    require(openttd.is_file() and not openttd.is_symlink() and os.access(openttd, os.X_OK), "action executable is missing, a symlink, or not executable")
    require(openttd.stat().st_size == executable["size"] and sha256_file(openttd) == executable["sha256"], "action executable identity drifted")
    require(opengfx.is_file() and not opengfx.is_symlink(), "OpenGFX archive is missing or a symlink")
    return {
        "schema_version": "openttd-rl-v2-m15-reset-manifest-1",
        "contract_sha256": sha256_file(root / CONTRACT),
        "engine_source_tree": native_source["base"]["engine_source_tree"],
        "executable_sha256": executable["sha256"],
        "map_width": width,
        "map_height": height,
        "map_seed": seed,
        "simulation_seed": qualify_m15_native_reset.stream_seed("simulation", seed),
        "candidate_tiebreak_seed": qualify_m15_native_reset.stream_seed("candidate-tiebreak", seed),
        "split": qualify_m15_native_reset.seed_split(contract, seed),
        "climate": "temperate",
        "start_year": 1950,
        "settings_manifest_sha256": sha256_file(root / "config/v2/setting-inventory.json"),
        "content_manifest_sha256": sha256_file(opengfx),
        "generation_mode": "native-seeded",
        "town_target": max(2, min(128, width * height // 4096)),
        "industry_target": 256,
        "company_count": 1,
        "resource_tier": "curriculum" if width * height <= 262_144 else "generalization",
        "v1_adapter": False,
        "rejection_reason": None,
    }


def process_command(openttd: pathlib.Path, artifact_root: pathlib.Path, request: bool, sandbox: str) -> list[str]:
    command = [
        str(openttd), "-x", "-X", "-Q", "-I", "OpenGFX", "-v", "null", "-s", "null", "-m", "null",
        "-V", str(artifact_root / MANIFEST_NAME), "-U", str(artifact_root / PROJECTION_NAME),
        "-W", str(artifact_root / OBSERVATION_METADATA_NAME), "-J", str(artifact_root / CANDIDATE_METADATA_NAME),
    ]
    if request:
        command.extend(["-K", str(artifact_root / REQUEST_NAME), "-L", str(artifact_root / RESULT_NAME)])
    if sandbox == "test-none":
        return command
    require(sandbox == "bubblewrap", "unknown action sandbox")
    bwrap = shutil.which("bwrap")
    require(bwrap is not None, "bubblewrap is required for action qualification")
    return [
        bwrap, "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-net",
        "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
        "--bind", str(artifact_root), str(artifact_root), "--chdir", str(openttd.parent), "--", *command,
    ]


def stable_key(family: int, parameters: tuple[int, ...]) -> str:
    return hashlib.sha256(bytes([family]) + struct.pack("<16I", *parameters)).hexdigest()


def validate_candidates(root: pathlib.Path, artifact_root: pathlib.Path, manifest: dict[str, Any], observation: dict[str, Any], projection: dict[str, Any]) -> M15ActionSummary:
    path = artifact_root / CANDIDATE_METADATA_NAME
    metadata = load_json(path)
    canonical_json(path, metadata)
    validate_schema(metadata, root / METADATA_SCHEMA, "M15 candidate metadata")
    action_contract = load_json(root / ACTION_CONTRACT)
    require(metadata["contract_sha256"] == manifest["contract_sha256"], "candidate contract identity drifted")
    require(metadata["observation_sha256"] == observation["binary"]["sha256"], "candidate snapshot is not bound to the observation")
    binary_path = artifact_root / metadata["binary"]["file"]
    require(binary_path.is_file() and not binary_path.is_symlink() and binary_path.parent == artifact_root, "candidate binary is missing, a symlink, or escaped its artifact root")
    blob = binary_path.read_bytes()
    require(len(blob) == CANDIDATE_BYTES == metadata["binary"]["bytes"], "candidate byte count drifted")
    require(hashlib.sha256(blob).hexdigest() == metadata["binary"]["sha256"], "candidate SHA-256 drifted")
    require(metadata["sections"] == action_contract["binary"]["sections"], "candidate section layout drifted")
    features = struct.unpack_from("<131072f", blob, 0)
    require(all(math.isfinite(value) for value in features), "candidate features contain non-finite values")
    parameters_offset = action_contract["binary"]["sections"][1]["offset"]
    parameters = struct.unpack_from("<65536I", blob, parameters_offset)
    mask_offset = action_contract["binary"]["sections"][2]["offset"]
    mask = blob[mask_offset:mask_offset + 4096]
    require(set(mask) <= {0, 1}, "candidate mask is not canonical uint8")

    families = metadata["families"]
    expected_families = action_contract["families"]
    require([item["family_index"] for item in families] == list(range(12)), "candidate family indices drifted")
    require([item["name"] for item in families] == [item["name"] for item in expected_families], "candidate family names drifted")
    total_selected = 0
    for observed, expected in zip(families, expected_families, strict=True):
        for field in ("quota", "row_begin", "row_end"):
            require(observed[field] == expected[field], f"candidate family {field} drifted: {observed['name']}")
        require(observed["selected_legal"] == min(observed["total_legal"], observed["quota"]), f"candidate selected count drifted: {observed['name']}")
        require(observed["omitted_legal"] == observed["total_legal"] - observed["selected_legal"], f"candidate omission count drifted: {observed['name']}")
        expected_mask = b"\x01" * observed["selected_legal"] + b"\x00" * (observed["quota"] - observed["selected_legal"])
        require(mask[observed["row_begin"]:observed["row_end"]] == expected_mask, f"candidate family mask is not prefix-canonical: {observed['name']}")
        total_selected += observed["selected_legal"]
    towns = projection["state"]["counts"]["towns"]
    require(families[0]["total_legal"] == 1 and families[1]["total_legal"] == towns * (towns - 1), "pure semantic family count drifted")
    require(families[3]["total_legal"] == families[4]["total_legal"], "initial bus-stop/depot native domains unexpectedly diverged")
    require(families[5]["total_legal"] == families[6]["total_legal"] == families[7]["total_legal"] == families[8]["total_legal"] == families[9]["total_legal"] == families[10]["total_legal"] == 0, "initial vehicle lifecycle families are not empty")
    require(families[11]["total_legal"] in (1, 2), "initial loan domain count drifted")

    records = metadata["records"]
    require(len(records) == total_selected == sum(mask), "candidate records do not match selected mask rows")
    require([record["row"] for record in records] == [index for index, value in enumerate(mask) if value], "candidate records are not exact masked row order")
    prior: dict[int, tuple[int, str]] = {}
    record_rows = {record["row"] for record in records}
    for record in records:
        row, family = record["row"], record["family_index"]
        words = tuple(parameters[row * 16:(row + 1) * 16])
        require(tuple(record["parameters"]) == words and words[0] == family, f"candidate parameter words drifted at row {row}")
        require(record["stable_key"] == stable_key(family, words), f"candidate stable key drifted at row {row}")
        order = (record["priority"], record["stable_key"])
        if family in prior:
            previous = prior[family]
            require(previous[0] > order[0] or previous[0] == order[0] and previous[1] < order[1], f"candidate ordering drifted in family {family}")
        prior[family] = order
        row_features = features[row * 32:(row + 1) * 32]
        require(row_features[:12] == tuple(1.0 if index == family else 0.0 for index in range(12)), f"candidate family one-hot drifted at row {row}")
        require(abs(row_features[12] * 4294967295 - record["priority"]) <= 256, f"candidate priority feature drifted at row {row}")
        require(abs(row_features[13] - max(-1.0, min(1.0, record["cost"] / 1_000_000))) <= 1e-6, f"candidate cost feature drifted at row {row}")
        require(all(value == 0.0 for value in row_features[20:]), f"candidate reserved features are nonzero at row {row}")
    for row in range(4096):
        if row in record_rows:
            continue
        require(all(value == 0.0 for value in features[row * 32:(row + 1) * 32]), f"unused candidate feature row {row} is nonzero")
        require(all(value == 0 for value in parameters[row * 16:(row + 1) * 16]), f"unused candidate parameter row {row} is nonzero")

    snapshot = metadata["snapshot"]
    require(snapshot["map_seed"] == manifest["map_seed"] and snapshot["simulation_seed"] == manifest["simulation_seed"], "candidate snapshot seeds drifted")
    require(snapshot["tick"] == observation["snapshot"]["tick"], "candidate and observation ticks diverged")
    payload = f"{manifest['contract_sha256']}:session-{manifest['map_seed']}-{manifest['simulation_seed']}:episode-0:transition-0:tick-{snapshot['tick']}:{metadata['observation_sha256']}:{metadata['binary']['sha256']}"
    require(snapshot["snapshot_token"] == "m15a1:" + hashlib.sha256(payload.encode()).hexdigest(), "candidate snapshot token drifted")
    return M15ActionSummary(manifest["map_width"], manifest["map_height"], total_selected, sum(item["total_legal"] for item in families), metadata["binary"]["sha256"], snapshot["snapshot_token"])


def validate_result(root: pathlib.Path, artifact_root: pathlib.Path, request: dict[str, Any]) -> dict[str, Any]:
    path = artifact_root / RESULT_NAME
    result = load_json(path)
    canonical_json(path, result)
    validate_schema(result, root / RESULT_SCHEMA, "M15 action result")
    require(result["candidate_row"] == request["candidate_row"] and result["family_index"] == request["family_index"], "action result selection echo drifted")
    require(result["snapshot_token"] == request["snapshot_token"], "action result token echo drifted")
    if result["status"] in {"STALE_TOKEN", "OUT_OF_RANGE", "ILLEGAL_CANDIDATE", "FAMILY_MISMATCH"}:
        require(result["tick_before"] == result["tick_after"], "invalid action advanced a tick")
        require(result["state_sha256_before"] == result["state_sha256_after"], "invalid action mutated native state")
        require(result["native_commands"] == [] and result["rolled_back"] is False, "invalid action ran a native command")
    return result


def qualify(root: pathlib.Path, openttd: pathlib.Path, opengfx: pathlib.Path, artifact_root: pathlib.Path, width: int, height: int, seed: int, *, request: dict[str, Any] | None = None, sandbox: str = "bubblewrap") -> pathlib.Path:
    root, openttd, opengfx, artifact_root = root.resolve(), openttd.resolve(), opengfx.resolve(), artifact_root.resolve()
    require(artifact_root.is_absolute() and not artifact_root.exists() and not artifact_root.is_symlink(), "action artifact root must be a new absolute path")
    manifest = build_manifest(root, openttd, opengfx, width, height, seed)
    qualify_m15_native_reset.validate_schema(manifest, root / qualify_m15_native_reset.MANIFEST_SCHEMA, "M15 action reset manifest")
    artifact_root.mkdir(mode=0o700)
    qualify_m15_native_reset.canonical_write_new(artifact_root / MANIFEST_NAME, manifest)
    if request is not None:
        validate_schema(request, root / REQUEST_SCHEMA, "M15 action request")
        qualify_m15_native_reset.canonical_write_new(artifact_root / REQUEST_NAME, request)
    environment = acquire_ai_package.isolated_environment(artifact_root)
    rss: list[int] = []
    stop = threading.Event()
    started = time.monotonic()
    process = subprocess.Popen(
        process_command(openttd, artifact_root, request is not None, sandbox), cwd=openttd.parent, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
        preexec_fn=qualify_m15_native_reset.apply_limits, start_new_session=True,
    )
    monitor = threading.Thread(target=qualify_ai_runtime.monitor_rss, args=(process, stop, rss), daemon=True)
    monitor.start()
    try:
        output, _ = process.communicate(timeout=qualify_m15_native_reset.LIMITS["wall_seconds"])
    except subprocess.TimeoutExpired as exc:
        acquire_ai_package.terminate_process(acquire_ai_package.ConsoleSession(process))
        raise M15ActionError("action process exceeded its wall-time limit") from exc
    finally:
        stop.set()
        monitor.join(timeout=1)
    wall_seconds = time.monotonic() - started
    transcript = artifact_root / TRANSCRIPT_NAME
    transcript.write_text(output, encoding="utf-8")
    require(process.returncode == 0, f"action process returned {process.returncode}: {output[-2000:]}")
    require("Error: M15" not in output, "action process emitted a fail-closed diagnostic")
    projection = qualify_m15_native_reset.validate_projection(root, manifest, artifact_root / PROJECTION_NAME)
    observation_path = artifact_root / OBSERVATION_METADATA_NAME
    observation = load_json(observation_path)
    qualify_m15_observation.validate_observation(root, artifact_root, manifest, projection)
    summary = validate_candidates(root, artifact_root, manifest, observation, projection)
    result = validate_result(root, artifact_root, request) if request is not None else None
    maximum_rss = max(rss, default=0)
    evidence = {
        "schema_version": "openttd-rl-v2-m15-action-case-evidence-1", "outcome": "PASS", "width": width, "height": height, "seed": seed,
        "manifest_sha256": sha256_file(artifact_root / MANIFEST_NAME), "projection_sha256": sha256_file(artifact_root / PROJECTION_NAME),
        "observation_sha256": observation["binary"]["sha256"], "candidate_metadata_sha256": sha256_file(artifact_root / CANDIDATE_METADATA_NAME),
        "candidate_binary_sha256": summary.binary_sha256, "snapshot_token": summary.snapshot_token,
        "selected_candidates": summary.selected, "total_legal": summary.total_legal, "maximum_rss_kib": maximum_rss,
        "wall_seconds": round(wall_seconds, 6), "request_sha256": None if request is None else sha256_file(artifact_root / REQUEST_NAME),
        "result_sha256": None if result is None else sha256_file(artifact_root / RESULT_NAME), "status": None if result is None else result["status"],
        "oracle_checks": ["exact-binary-layout", "finite-features", "canonical-mask", "stable-key-recompute", "family-range-and-order", "native-full-domain-counts", "snapshot-recompute"] + ([] if result is None else ["typed-result", "invalid-no-mutation"]),
    }
    evidence_path = artifact_root / EVIDENCE_NAME
    qualify_m15_native_reset.canonical_write_new(evidence_path, evidence)
    return evidence_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--openttd", type=pathlib.Path, required=True)
    parser.add_argument("--opengfx", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--request", type=pathlib.Path)
    parser.add_argument("--sandbox", choices=("bubblewrap", "test-none"), default="bubblewrap")
    args = parser.parse_args()
    try:
        request = load_json(args.request) if args.request is not None else None
        evidence = qualify(args.root, args.openttd, args.opengfx, args.artifact_root, args.width, args.height, args.seed, request=request, sandbox=args.sandbox)
        print(f"V2_M15_ACTION=PASS evidence={evidence}")
        return 0
    except (M15ActionError, OSError) as exc:
        print(f"V2_M15_ACTION=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
