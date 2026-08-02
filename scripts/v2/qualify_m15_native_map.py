#!/usr/bin/env python3
"""Generate/save/load one native OpenTTD map or retain a bounded preflight rejection."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import lzma
import math
import os
import pathlib
import resource
import subprocess
import sys
import threading
import time
from typing import Any

import jsonschema

import acquire_ai_package
import qualify_ai_runtime


SCHEMA_RELATIVE = pathlib.Path("docs/project/schema/v2-m15-map-qualification.schema.json")
CONTRACT_RELATIVE = pathlib.Path("config/v2/m15-scalable-contract.json")
EVIDENCE_NAME = "m15-map-qualification.json"
TRANSCRIPT_NAME = "openttd-map-console.log"
SAVE_RELATIVE = pathlib.Path("save/m15-map.sav")
MAXIMUM_GENERATED_TILES = 1_048_576
LIMITS = {
    "address_space_bytes": 2 * 1024 * 1024 * 1024,
    "cpu_seconds": 180,
    "file_bytes": 512 * 1024 * 1024,
    "wall_seconds": 180,
}
TILE_TYPE_NAMES = {
    0: "clear", 1: "railway", 2: "road", 3: "house", 4: "trees", 5: "station",
    6: "water", 7: "void", 8: "industry", 9: "tunnel_bridge", 10: "object",
}


class M15MapQualificationError(ValueError):
    """One native map did not meet the M15 generation or preflight contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15MapQualificationError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15MapQualificationError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise M15MapQualificationError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def parse_save(path: pathlib.Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise M15MapQualificationError(f"cannot read savegame {path}: {exc}") from exc
    require(len(raw) >= 16 and raw[:4] == b"OTTX", f"savegame is not an OTTX container: {path}")
    try:
        payload = lzma.decompress(raw[8:])
    except lzma.LZMAError as exc:
        raise M15MapQualificationError(f"savegame XZ payload is invalid: {path}: {exc}") from exc
    maps = payload.find(b"MAPS")
    require(maps >= 0 and payload[maps + 4:maps + 21] == b"\x03\x10\x06\x05dim_x\x06\x05dim_y\x00", "savegame MAPS dimensions header is invalid")
    require(maps + 31 <= len(payload), "savegame MAPS dimensions are truncated")
    width = int.from_bytes(payload[maps + 22:maps + 26], "big")
    height = int.from_bytes(payload[maps + 26:maps + 30], "big")
    tiles = width * height
    mapt = payload.find(b"MAPT", maps + 31)
    require(mapt >= 0 and mapt + 8 + tiles <= len(payload), "savegame MAPT chunk is missing or truncated")
    require(int.from_bytes(payload[mapt + 4:mapt + 8], "big") == tiles, "savegame MAPT size mismatch")
    counts: collections.Counter[str] = collections.Counter()
    for value in payload[mapt + 8:mapt + 8 + tiles]:
        tile_type = value >> 4
        require(tile_type in TILE_TYPE_NAMES, f"savegame contains unknown tile type {tile_type}")
        counts[TILE_TYPE_NAMES[tile_type]] += 1
    map_chunks: list[bytes] = [payload[maps:mapt]]
    position = mapt
    for tag in (b"MAPT", b"MAPH", b"MAPO", b"MAP2", b"M3LO", b"M3HI", b"MAP5", b"MAPE", b"MAP7", b"MAP8"):
        require(payload[position:position + 4] == tag and position + 8 <= len(payload), f"savegame map chunk order is invalid at {tag.decode()}")
        size = int.from_bytes(payload[position + 4:position + 8], "big")
        end = position + 8 + size
        require(end <= len(payload), f"savegame map chunk {tag.decode()} is truncated")
        map_chunks.append(payload[position:end])
        position = end
    return {
        "width": width,
        "height": height,
        "tiles": tiles,
        "tile_type_counts": dict(sorted(counts.items())),
        "map_sha256": hashlib.sha256(b"".join(map_chunks)).hexdigest(),
    }


def write_config(path: pathlib.Path, width: int, height: int, seed: int) -> None:
    path.write_text(
        "[game_creation]\n"
        f"map_x = {width.bit_length() - 1}\n"
        f"map_y = {height.bit_length() - 1}\n"
        "starting_year = 1950\n"
        f"generation_seed = {seed}\n"
        "landscape = temperate\n"
        "land_generator = 1\n"
        "tree_placer = 0\n\n"
        "[difficulty]\n"
        "max_no_competitors = 0\n"
        "number_towns = 0\n"
        "industry_density = 0\n"
        "terrain_type = 0\n"
        "quantity_sea_lakes = 0\n\n"
        "[network]\n"
        "server_advertise = false\n"
        "server_name = V2 M15 native map qualification\n",
        encoding="utf-8",
    )


def apply_limits() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (LIMITS["address_space_bytes"], LIMITS["address_space_bytes"]))
    resource.setrlimit(resource.RLIMIT_CPU, (LIMITS["cpu_seconds"], LIMITS["cpu_seconds"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS["file_bytes"], LIMITS["file_bytes"]))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))


def command_for(openttd: pathlib.Path, artifact_root: pathlib.Path, config: pathlib.Path, sandbox: str) -> list[str]:
    if sandbox == "bubblewrap":
        return qualify_ai_runtime.command_for(openttd, artifact_root, config, sandbox)
    require(sandbox == "test-none", "unknown M15 map sandbox")
    return [
        str(openttd), "-D", f"127.0.0.1:{acquire_ai_package.reserve_port()}",
        "-v", "dedicated", "-s", "null", "-m", "null", "-x", "-X", "-c", str(config),
    ]


def base_manifest(root: pathlib.Path, openttd: pathlib.Path, width: int, height: int, seed: int) -> dict[str, Any]:
    source = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    return {
        "$schema": "../../docs/project/schema/v2-m15-map-qualification.schema.json",
        "schema_version": "openttd-rl-v2-m15-map-qualification-1",
        "schema_sha256": sha256_file(root / SCHEMA_RELATIVE),
        "engine_source": {key: source[key] for key in ("release", "commit", "tree")},
        "executable": {"sha256": sha256_file(openttd), "size": openttd.stat().st_size},
        "contract_sha256": sha256_file(root / CONTRACT_RELATIVE),
        "request": {
            "width": width,
            "height": height,
            "map_x_bits": width.bit_length() - 1,
            "map_y_bits": height.bit_length() - 1,
            "tile_count": width * height,
            "seed": seed,
        },
        "limits": {"maximum_generated_tiles": MAXIMUM_GENERATED_TILES, **LIMITS},
    }


def write_manifest(root: pathlib.Path, artifact_root: pathlib.Path, manifest: dict[str, Any]) -> pathlib.Path:
    path = artifact_root / EVIDENCE_NAME
    require(not path.exists(), f"map qualification evidence already exists: {path}")
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    validate_manifest(root, path)
    return path


def qualify(
    root: pathlib.Path,
    openttd: pathlib.Path,
    artifact_root: pathlib.Path,
    width: int,
    height: int,
    seed: int,
    *,
    sandbox: str = "bubblewrap",
) -> pathlib.Path:
    root = root.resolve()
    openttd = openttd.resolve()
    artifact_root = artifact_root.resolve()
    require(artifact_root.is_absolute() and not artifact_root.exists() and not artifact_root.is_symlink(), "artifact root must be a new absolute path")
    require(openttd.is_file() and not openttd.is_symlink(), "OpenTTD executable is missing or a symlink")
    contract = load_json(root / CONTRACT_RELATIVE)
    require([width, height] in contract["map"]["native_rectangles"], "requested dimensions are not a frozen native rectangle")
    require(seed in {value for item in contract["seeds"]["sets"].values() for value in item["seeds"]}, "map seed is not in the frozen M15 seed ledger")
    artifact_root.mkdir(mode=0o700)
    manifest = base_manifest(root, openttd, width, height, seed)
    if width * height > MAXIMUM_GENERATED_TILES:
        manifest.update({
            "outcome": "PREFLIGHT_REJECTED",
            "reason_code": "tile-count-exceeds-useful-play-preflight-budget",
            "checks": {"native_rectangle": True, "preflight_passed": False, "map_generated": False, "save_created": False, "dimensions_confirmed": False, "load_succeeded": False, "resource_limits_respected": True},
            "observations": {"start_date": None, "post_load_date": None, "save": None, "map": None, "transcript_sha256": None},
            "resources": {"wall_seconds": 0, "max_rss_kib": 0, "returncode": None},
        })
        return write_manifest(root, artifact_root, manifest)

    config = artifact_root / "openttd.cfg"
    write_config(config, width, height, seed)
    environment = acquire_ai_package.isolated_environment(artifact_root)
    session: acquire_ai_package.ConsoleSession | None = None
    rss: list[int] = []
    rss_stop = threading.Event()
    rss_thread: threading.Thread | None = None
    start_date: str | None = None
    post_load_date: str | None = None
    save_info: dict[str, Any] | None = None
    map_info: dict[str, Any] | None = None
    started = time.monotonic()
    returncode: int | None = None
    error: BaseException | None = None
    try:
        process = subprocess.Popen(
            command_for(openttd, artifact_root, config, sandbox),
            cwd=openttd.parent,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            preexec_fn=apply_limits,
            start_new_session=True,
        )
        session = acquire_ai_package.ConsoleSession(process)
        rss_thread = threading.Thread(target=qualify_ai_runtime.monitor_rss, args=(process, rss_stop, rss), daemon=True)
        rss_thread.start()
        session.wait_for(
            lambda line: "Map generated, starting game" in line,
            start=0,
            timeout=LIMITS["wall_seconds"],
            label=f"{width}x{height} map generation",
        )
        start_date = qualify_ai_runtime.query_date(session, timeout=10).isoformat()
        save_start = session.send("save m15-map")
        session.wait_for(lambda line: line.startswith("Map successfully saved to "), start=save_start, timeout=30, label="M15 map save")
        save_path = artifact_root / SAVE_RELATIVE
        qualify_ai_runtime.wait_nonempty_stable_file(save_path, 15)
        map_info = parse_save(save_path)
        require(map_info["width"] == width and map_info["height"] == height, f"saved map dimensions are {map_info['width']}x{map_info['height']}, expected {width}x{height}")
        save_info = {"path": SAVE_RELATIVE.as_posix(), "size": save_path.stat().st_size, "sha256": sha256_file(save_path)}
        load_start = session.send("load m15-map.sav")
        session.wait_for(lambda line: "Listening on 127.0.0.1:" in line, start=load_start, timeout=30, label="M15 map reload")
        post_load_date = qualify_ai_runtime.query_date(session, timeout=15).isoformat()
    except (M15MapQualificationError, acquire_ai_package.AIPackageError, qualify_ai_runtime.AIRuntimeError, OSError, subprocess.SubprocessError) as exc:
        error = exc
    finally:
        acquire_ai_package.terminate_process(session)
        if session is not None:
            returncode = session.process.returncode
            (artifact_root / TRANSCRIPT_NAME).write_text(session.transcript(), encoding="utf-8")
            acquire_ai_package.close_process_streams(session)
        rss_stop.set()
        if rss_thread is not None:
            rss_thread.join(timeout=1)
    if error is not None:
        raise M15MapQualificationError(f"{width}x{height} native qualification failed: {error}") from error
    transcript_path = artifact_root / TRANSCRIPT_NAME
    maximum_rss = max(rss, default=0)
    wall_seconds = time.monotonic() - started
    require(returncode == 0, f"OpenTTD returned {returncode}")
    require(maximum_rss * 1024 <= LIMITS["address_space_bytes"], "OpenTTD RSS exceeded address-space limit")
    require(wall_seconds <= LIMITS["wall_seconds"], "OpenTTD map qualification exceeded wall limit")
    assert start_date is not None and post_load_date is not None and save_info is not None and map_info is not None
    manifest.update({
        "outcome": "GENERATED",
        "reason_code": None,
        "checks": {"native_rectangle": True, "preflight_passed": True, "map_generated": True, "save_created": True, "dimensions_confirmed": True, "load_succeeded": True, "resource_limits_respected": True},
        "observations": {"start_date": start_date, "post_load_date": post_load_date, "save": save_info, "map": map_info, "transcript_sha256": sha256_file(transcript_path)},
        "resources": {"wall_seconds": round(wall_seconds, 6), "max_rss_kib": maximum_rss, "returncode": returncode},
    })
    return write_manifest(root, artifact_root, manifest)


def validate_manifest(root: pathlib.Path, evidence_path: pathlib.Path, *, openttd: pathlib.Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    evidence_path = evidence_path.resolve()
    manifest = load_json(evidence_path)
    schema_path = root / SCHEMA_RELATIVE
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(manifest)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15MapQualificationError(f"M15 map evidence schema failed at {location}: {exc.message}") from exc
    require(manifest["schema_sha256"] == sha256_file(schema_path), "M15 map evidence schema SHA-256 mismatch")
    require(manifest["contract_sha256"] == sha256_file(root / CONTRACT_RELATIVE), "M15 map contract SHA-256 mismatch")
    source = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    require(manifest["engine_source"] == {key: source[key] for key in ("release", "commit", "tree")}, "M15 map engine source drifted")
    request = manifest["request"]
    require(request["width"] == 1 << request["map_x_bits"] and request["height"] == 1 << request["map_y_bits"], "M15 map bit/dimension encoding drifted")
    require(request["tile_count"] == request["width"] * request["height"], "M15 map tile count drifted")
    contract = load_json(root / CONTRACT_RELATIVE)
    require([request["width"], request["height"]] in contract["map"]["native_rectangles"], "M15 evidence dimensions are not a native rectangle")
    if openttd is not None:
        require(manifest["executable"] == {"sha256": sha256_file(openttd), "size": openttd.stat().st_size}, "M15 map executable identity drifted")
    if manifest["outcome"] == "PREFLIGHT_REJECTED":
        require(request["tile_count"] > MAXIMUM_GENERATED_TILES, "M15 preflight rejected a map inside the generated tier")
        return manifest
    require(request["tile_count"] <= MAXIMUM_GENERATED_TILES, "M15 generated map exceeds the preflight budget")
    save = manifest["observations"]["save"]
    save_path = evidence_path.parent / save["path"]
    require(save_path.is_file() and not save_path.is_symlink(), "M15 map save evidence is missing or a symlink")
    require(save_path.stat().st_size == save["size"] and sha256_file(save_path) == save["sha256"], "M15 map save identity drifted")
    parsed = parse_save(save_path)
    require(parsed == manifest["observations"]["map"], "M15 parsed map evidence drifted")
    require(parsed["width"] == request["width"] and parsed["height"] == request["height"], "M15 saved map dimensions drifted")
    transcript = evidence_path.parent / TRANSCRIPT_NAME
    require(transcript.is_file() and not transcript.is_symlink(), "M15 map transcript is missing or a symlink")
    require(sha256_file(transcript) == manifest["observations"]["transcript_sha256"], "M15 map transcript identity drifted")
    return manifest


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--openttd", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--sandbox", choices=("bubblewrap", "test-none"), default="bubblewrap")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        evidence = qualify(args.root, args.openttd, args.artifact_root, args.width, args.height, args.seed, sandbox=args.sandbox)
        manifest = load_json(evidence)
        print(f"V2_M15_MAP={manifest['outcome']} dimensions={args.width}x{args.height} evidence={evidence} sha256={sha256_file(evidence)}")
        return 0
    except (M15MapQualificationError, OSError) as exc:
        print(f"V2_M15_MAP=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
