#!/usr/bin/env python3
"""Run and validate one source-integrated M15 native scalable reset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import resource
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

import jsonschema

import acquire_ai_package
import qualify_ai_runtime


CONTRACT = pathlib.Path("config/v2/m15-scalable-contract.json")
SOURCE = pathlib.Path("config/v2/m15-native-source.json")
MANIFEST_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-reset-manifest.schema.json")
PROJECTION_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-reset-projection.schema.json")
MANIFEST_NAME = "reset-manifest.json"
PROJECTION_NAME = "reset-projection.json"
TRANSCRIPT_NAME = "openttd-reset.log"
EVIDENCE_NAME = "reset-evidence.json"
MAXIMUM_TILES = 1_048_576
LIMITS = {
    "address_space_bytes": 7 * 1024 * 1024 * 1024,
    "cpu_seconds": 900,
    "file_bytes": 64 * 1024 * 1024,
    "wall_seconds": 900,
}


class M15NativeResetError(ValueError):
    """The native M15 reset request, process, or projection failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15NativeResetError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15NativeResetError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise M15NativeResetError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def stream_seed(name: str, map_seed: int) -> int:
    value = hashlib.sha256(f"openttd-rl-v2-m15-reset-stream-v1:{name}:{map_seed}".encode()).digest()
    return int.from_bytes(value[:4], "big") & 0x7FFFFFFF


def seed_split(contract: dict[str, Any], seed: int) -> str:
    matches = [name for name, item in contract["seeds"]["sets"].items() if seed in item["seeds"]]
    require(len(matches) == 1, "reset seed is not uniquely frozen in the M15 ledger")
    return matches[0]


def build_manifest(root: pathlib.Path, openttd: pathlib.Path, opengfx: pathlib.Path, width: int, height: int, seed: int) -> dict[str, Any]:
    contract = load_json(root / CONTRACT)
    require([width, height] in contract["map"]["native_rectangles"], "reset dimensions are not a frozen native rectangle")
    tile_count = width * height
    require(tile_count <= MAXIMUM_TILES, "reset tile count exceeds the preallocation budget")
    source = load_json(root / SOURCE)
    executable = source["build"]["executable"]
    require(openttd.is_file() and not openttd.is_symlink() and os.access(openttd, os.X_OK), "M15 OpenTTD executable is missing, a symlink, or not executable")
    require(openttd.stat().st_size == executable["size"] and sha256_file(openttd) == executable["sha256"], "M15 OpenTTD executable identity drifted from source evidence")
    require(opengfx.is_file() and not opengfx.is_symlink(), "OpenGFX content archive is missing or a symlink")
    split = seed_split(contract, seed)
    return {
        "schema_version": "openttd-rl-v2-m15-reset-manifest-1",
        "contract_sha256": sha256_file(root / CONTRACT),
        "engine_source_tree": source["base"]["engine_source_tree"],
        "executable_sha256": executable["sha256"],
        "map_width": width,
        "map_height": height,
        "map_seed": seed,
        "simulation_seed": stream_seed("simulation", seed),
        "candidate_tiebreak_seed": stream_seed("candidate-tiebreak", seed),
        "split": split,
        "climate": "temperate",
        "start_year": 1950,
        "settings_manifest_sha256": sha256_file(root / "config/v2/setting-inventory.json"),
        "content_manifest_sha256": sha256_file(opengfx),
        "generation_mode": "native-seeded",
        "town_target": max(2, min(128, tile_count // 4096)),
        "industry_target": 256,
        "company_count": 1,
        "resource_tier": "curriculum" if tile_count <= 262_144 else "generalization",
        "v1_adapter": False,
        "rejection_reason": None,
    }


def validate_schema(value: dict[str, Any], schema_path: pathlib.Path, label: str) -> None:
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(value)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15NativeResetError(f"{label} schema failed at {location}: {exc.message}") from exc


def canonical_write_new(path: pathlib.Path, value: dict[str, Any]) -> None:
    require(not path.exists() and not path.is_symlink(), f"refusing to overwrite {path}")
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def validate_projection(root: pathlib.Path, manifest: dict[str, Any], projection_path: pathlib.Path) -> dict[str, Any]:
    projection = load_json(projection_path)
    validate_schema(projection, root / PROJECTION_SCHEMA, "M15 reset projection")
    require(projection["contract_sha256"] == manifest["contract_sha256"], "projection contract identity drifted")
    expected_request = {
        "candidate_tiebreak_seed": manifest["candidate_tiebreak_seed"],
        "executable_sha256": manifest["executable_sha256"],
        "height": manifest["map_height"],
        "industry_target": manifest["industry_target"],
        "interactive_seed": manifest["simulation_seed"] ^ 0x524C5632,
        "map_seed": manifest["map_seed"],
        "resource_tier": manifest["resource_tier"],
        "simulation_seed": manifest["simulation_seed"],
        "split": manifest["split"],
        "town_target": manifest["town_target"],
        "width": manifest["map_width"],
    }
    require(projection["request"] == expected_request, "projection request echo drifted")
    state = projection["state"]
    map_value = state["map"]
    require(map_value["width"] == manifest["map_width"] and map_value["height"] == manifest["map_height"], "projection map dimensions drifted")
    require(map_value["tile_count"] == manifest["map_width"] * manifest["map_height"], "projection tile count drifted")
    require(sum(map_value[key] for key in ("clear_tiles", "house_tiles", "road_tiles", "water_tiles")) <= map_value["tile_count"], "projection tile-type counts exceed the map")
    towns = state["towns"]
    require(state["counts"]["towns"] == len(towns) and 2 <= len(towns) <= manifest["town_target"], "projection town count drifted")
    require([item["id"] for item in towns] == sorted({item["id"] for item in towns}), "projection town IDs are duplicated or unsorted")
    require(all(item["x"] < manifest["map_width"] and item["y"] < manifest["map_height"] for item in towns), "projection town coordinate is outside the map")
    return projection


def apply_limits() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (LIMITS["address_space_bytes"], LIMITS["address_space_bytes"]))
    resource.setrlimit(resource.RLIMIT_CPU, (LIMITS["cpu_seconds"], LIMITS["cpu_seconds"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS["file_bytes"], LIMITS["file_bytes"]))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))


def process_command(openttd: pathlib.Path, artifact_root: pathlib.Path, manifest: pathlib.Path, projection: pathlib.Path, sandbox: str) -> list[str]:
    command = [
        str(openttd), "-x", "-X", "-Q", "-I", "OpenGFX", "-v", "null", "-s", "null", "-m", "null",
        "-V", str(manifest), "-U", str(projection),
    ]
    if sandbox == "test-none":
        return command
    require(sandbox == "bubblewrap", "unknown M15 reset sandbox")
    bwrap = shutil.which("bwrap")
    require(bwrap is not None, "bubblewrap is required for native reset qualification")
    return [
        bwrap, "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-net",
        "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
        "--bind", str(artifact_root), str(artifact_root), "--chdir", str(openttd.parent), "--", *command,
    ]


def qualify(root: pathlib.Path, openttd: pathlib.Path, opengfx: pathlib.Path, artifact_root: pathlib.Path, width: int, height: int, seed: int, *, sandbox: str = "bubblewrap") -> pathlib.Path:
    root = root.resolve()
    openttd = openttd.resolve()
    opengfx = opengfx.resolve()
    artifact_root = artifact_root.resolve()
    require(artifact_root.is_absolute() and not artifact_root.exists() and not artifact_root.is_symlink(), "reset artifact root must be a new absolute path")
    manifest = build_manifest(root, openttd, opengfx, width, height, seed)
    validate_schema(manifest, root / MANIFEST_SCHEMA, "M15 reset manifest")
    artifact_root.mkdir(mode=0o700)
    manifest_path = artifact_root / MANIFEST_NAME
    projection_path = artifact_root / PROJECTION_NAME
    canonical_write_new(manifest_path, manifest)
    environment = acquire_ai_package.isolated_environment(artifact_root)
    rss: list[int] = []
    stop = threading.Event()
    started = time.monotonic()
    process = subprocess.Popen(
        process_command(openttd, artifact_root, manifest_path, projection_path, sandbox),
        cwd=openttd.parent, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", preexec_fn=apply_limits, start_new_session=True,
    )
    monitor = threading.Thread(target=qualify_ai_runtime.monitor_rss, args=(process, stop, rss), daemon=True)
    monitor.start()
    try:
        output, _ = process.communicate(timeout=LIMITS["wall_seconds"])
    except subprocess.TimeoutExpired as exc:
        acquire_ai_package.terminate_process(acquire_ai_package.ConsoleSession(process))
        raise M15NativeResetError("native reset exceeded its wall-time limit") from exc
    finally:
        stop.set()
        monitor.join(timeout=1)
    wall_seconds = time.monotonic() - started
    transcript = artifact_root / TRANSCRIPT_NAME
    transcript.write_text(output, encoding="utf-8")
    require(process.returncode == 0, f"native reset process returned {process.returncode}")
    require("Error: M15 scalable reset:" not in output, "native reset emitted a fail-closed diagnostic")
    require(projection_path.is_file() and not projection_path.is_symlink(), "native reset produced no projection")
    projection = validate_projection(root, manifest, projection_path)
    maximum_rss = max(rss, default=0)
    require(maximum_rss * 1024 <= LIMITS["address_space_bytes"], "native reset exceeded its RSS limit")
    evidence = {
        "schema_version": "openttd-rl-v2-m15-reset-evidence-1",
        "outcome": "PASS",
        "manifest_sha256": sha256_file(manifest_path),
        "projection_sha256": sha256_file(projection_path),
        "transcript_sha256": sha256_file(transcript),
        "width": width,
        "height": height,
        "seed": seed,
        "towns": projection["state"]["counts"]["towns"],
        "industries": projection["state"]["counts"]["industries"],
        "maximum_rss_kib": maximum_rss,
        "wall_seconds": round(wall_seconds, 6),
        "limits": LIMITS,
    }
    evidence_path = artifact_root / EVIDENCE_NAME
    canonical_write_new(evidence_path, evidence)
    return evidence_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--openttd", type=pathlib.Path, required=True)
    parser.add_argument("--opengfx", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--sandbox", choices=("bubblewrap", "test-none"), default="bubblewrap")
    args = parser.parse_args(argv or sys.argv[1:])
    try:
        evidence = qualify(args.root, args.openttd, args.opengfx, args.artifact_root, args.width, args.height, args.seed, sandbox=args.sandbox)
        print(f"V2_M15_NATIVE_RESET=PASS dimensions={args.width}x{args.height} seed={args.seed} evidence={evidence} sha256={sha256_file(evidence)}")
        return 0
    except (M15NativeResetError, OSError, subprocess.SubprocessError) as exc:
        print(f"V2_M15_NATIVE_RESET=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
