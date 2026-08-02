#!/usr/bin/env python3
"""Run and independently decode one source-integrated M15 bounded observation."""

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
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

import jsonschema

import acquire_ai_package
import qualify_ai_runtime
import qualify_m15_native_reset


CONTRACT = pathlib.Path("config/v2/m15-scalable-contract.json")
NATIVE_SOURCE = pathlib.Path("config/v2/m15-native-source.json")
OBSERVATION_SOURCE = pathlib.Path("config/v2/m15-observation-source.json")
METADATA_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-observation-metadata.schema.json")
MANIFEST_NAME = "reset-manifest.json"
PROJECTION_NAME = "reset-projection.json"
METADATA_NAME = "observation-metadata.json"
BINARY_NAME = "observation-metadata.bin"
TRANSCRIPT_NAME = "openttd-observation.log"
EVIDENCE_NAME = "observation-evidence.json"
OBSERVATION_BYTES = 2_182_927
SECTION_LAYOUT = [
    ("structured", 0, 2_048, "float32-le", [512]),
    ("spatial.global", 2_048, 524_288, "float32-le", [32, 64, 64]),
    ("spatial.regional", 526_336, 524_288, "float32-le", [32, 64, 64]),
    ("spatial.local", 1_050_624, 131_072, "float32-le", [32, 32, 32]),
    ("entities.companies.values", 1_181_696, 1_920, "float32-le", [15, 32]),
    ("entities.companies.mask", 1_183_616, 15, "uint8", [15]),
    ("entities.towns.values", 1_183_631, 12_288, "float32-le", [128, 24]),
    ("entities.towns.mask", 1_195_919, 128, "uint8", [128]),
    ("entities.industries.values", 1_196_047, 24_576, "float32-le", [256, 24]),
    ("entities.industries.mask", 1_220_623, 256, "uint8", [256]),
    ("entities.stations.values", 1_220_879, 65_536, "float32-le", [512, 32]),
    ("entities.stations.mask", 1_286_415, 512, "uint8", [512]),
    ("entities.vehicles.values", 1_286_927, 163_840, "float32-le", [1024, 40]),
    ("entities.vehicles.mask", 1_450_767, 1_024, "uint8", [1024]),
    ("graph.nodes.values", 1_451_791, 196_608, "float32-le", [2048, 24]),
    ("graph.nodes.mask", 1_648_399, 2_048, "uint8", [2048]),
    ("graph.edges.values", 1_650_447, 524_288, "float32-le", [8192, 16]),
    ("graph.edges.mask", 2_174_735, 8_192, "uint8", [8192]),
]
CAPACITIES = {"companies": 15, "towns": 128, "industries": 256, "stations": 512, "vehicles": 1024}
FEATURES = {"companies": 32, "towns": 24, "industries": 24, "stations": 32, "vehicles": 40}


class M15ObservationError(ValueError):
    """The native bounded observation or its independent decoding failed."""


@dataclass(frozen=True)
class M15ObservationSummary:
    width: int
    height: int
    towns: int
    industries: int
    binary_sha256: str
    maximum_rss_kib: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15ObservationError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15ObservationError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise M15ObservationError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def canonical_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    expected = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    require(path.read_text(encoding="utf-8") == expected, f"JSON is not canonical: {path}")


def build_manifest(root: pathlib.Path, openttd: pathlib.Path, opengfx: pathlib.Path, width: int, height: int, seed: int) -> dict[str, Any]:
    contract = load_json(root / CONTRACT)
    source = load_json(root / OBSERVATION_SOURCE)
    native_source = load_json(root / NATIVE_SOURCE)
    require([width, height] in contract["map"]["native_rectangles"], "dimensions are not a frozen native rectangle")
    require(width * height <= qualify_m15_native_reset.MAXIMUM_TILES, "tile count exceeds the M15 observation budget")
    executable = source["build"]["executable"]
    require(openttd.is_file() and not openttd.is_symlink() and os.access(openttd, os.X_OK), "observation executable is missing, a symlink, or not executable")
    require(openttd.stat().st_size == executable["size"] and sha256_file(openttd) == executable["sha256"], "observation executable identity drifted")
    require(opengfx.is_file() and not opengfx.is_symlink(), "OpenGFX archive is missing or a symlink")
    split = qualify_m15_native_reset.seed_split(contract, seed)
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
        "split": split,
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


def process_command(openttd: pathlib.Path, artifact_root: pathlib.Path, manifest: pathlib.Path, projection: pathlib.Path, metadata: pathlib.Path, sandbox: str) -> list[str]:
    command = [
        str(openttd), "-x", "-X", "-Q", "-I", "OpenGFX", "-v", "null", "-s", "null", "-m", "null",
        "-V", str(manifest), "-U", str(projection), "-W", str(metadata),
    ]
    if sandbox == "test-none":
        return command
    require(sandbox == "bubblewrap", "unknown observation sandbox")
    bwrap = shutil.which("bwrap")
    require(bwrap is not None, "bubblewrap is required for observation qualification")
    return [
        bwrap, "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-net",
        "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
        "--bind", str(artifact_root), str(artifact_root), "--chdir", str(openttd.parent), "--", *command,
    ]


def floats(blob: bytes, offset: int, count: int) -> tuple[float, ...]:
    return struct.unpack_from(f"<{count}f", blob, offset)


def section_values(blob: bytes, sections: dict[str, tuple[int, int, str, list[int]]], name: str) -> tuple[float, ...]:
    offset, size, dtype, shape = sections[name]
    require(dtype == "float32-le", f"{name} is not float32")
    count = math.prod(shape)
    require(size == count * 4, f"{name} byte count is inconsistent")
    return floats(blob, offset, count)


def validate_mask(blob: bytes, sections: dict[str, tuple[int, int, str, list[int]]], name: str, selected: int) -> None:
    offset, size, dtype, shape = sections[name]
    require(dtype == "uint8" and shape == [size], f"{name} mask layout drifted")
    require(blob[offset:offset + size] == b"\x01" * selected + b"\x00" * (size - selected), f"{name} mask is not canonical prefix-valid")


def near_integer(value: float, scale: int, expected: int) -> bool:
    return abs(value * scale - expected) <= 0.02


def validate_observation(root: pathlib.Path, artifact_root: pathlib.Path, manifest: dict[str, Any], projection: dict[str, Any]) -> M15ObservationSummary:
    metadata_path = artifact_root / METADATA_NAME
    metadata = load_json(metadata_path)
    canonical_json(metadata_path, metadata)
    schema = load_json(root / METADATA_SCHEMA)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(metadata)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15ObservationError(f"metadata schema failed at {location}: {exc.message}") from exc
    require(metadata["contract_sha256"] == manifest["contract_sha256"], "metadata contract identity drifted")
    require(metadata["binary"]["file"] == BINARY_NAME, "metadata binary filename drifted")
    binary_path = artifact_root / metadata["binary"]["file"]
    require(binary_path.is_file() and not binary_path.is_symlink() and binary_path.parent == artifact_root, "observation binary is missing, a symlink, or escaped its artifact root")
    blob = binary_path.read_bytes()
    require(len(blob) == OBSERVATION_BYTES == metadata["binary"]["bytes"], "observation byte count drifted")
    require(hashlib.sha256(blob).hexdigest() == metadata["binary"]["sha256"], "observation SHA-256 drifted")

    expected_sections = [
        {"name": name, "offset": offset, "bytes": size, "dtype": dtype, "shape": shape}
        for name, offset, size, dtype, shape in SECTION_LAYOUT
    ]
    require(metadata["sections"] == expected_sections, "observation section layout drifted")
    require(SECTION_LAYOUT[-1][1] + SECTION_LAYOUT[-1][2] == len(blob), "section layout does not consume the exact binary")
    sections = {name: (offset, size, dtype, shape) for name, offset, size, dtype, shape in SECTION_LAYOUT}
    for name, _, _, dtype, _ in SECTION_LAYOUT:
        if dtype == "float32-le":
            require(all(math.isfinite(value) for value in section_values(blob, sections, name)), f"{name} contains NaN or infinity")

    snapshot = metadata["snapshot"]
    require(snapshot["width"] == manifest["map_width"] and snapshot["height"] == manifest["map_height"], "snapshot dimensions drifted")
    require(snapshot["tile_count"] == manifest["map_width"] * manifest["map_height"], "snapshot tile count drifted")
    require(snapshot["map_seed"] == manifest["map_seed"] and snapshot["simulation_seed"] == manifest["simulation_seed"] and snapshot["candidate_tiebreak_seed"] == manifest["candidate_tiebreak_seed"], "snapshot seed streams drifted")
    require(metadata["spatial"]["regional_origin"] == [snapshot["anchor_x"] - 32, snapshot["anchor_y"] - 32], "regional origin drifted")
    require(metadata["spatial"]["local_origin"] == [snapshot["anchor_x"] - 16, snapshot["anchor_y"] - 16], "local origin drifted")

    structured = section_values(blob, sections, "structured")
    require(near_integer(structured[0], 4096, manifest["map_width"]), "structured width drifted")
    require(near_integer(structured[1], 4096, manifest["map_height"]), "structured height drifted")
    require(near_integer(structured[2], 1_048_576, snapshot["tile_count"]), "structured tile count drifted")
    counts = projection["state"]["counts"]
    structured_scales = [(3, "towns", 64_000), (4, "industries", 64_000), (5, "stations", 64_000), (6, "vehicles", 0xFF000), (7, "companies", 15)]
    for index, key, scale in structured_scales:
        require(near_integer(structured[index], scale, counts[key]), f"structured {key} count drifted")
    require(structured[12] == 1.0 and all(value == 0.0 for value in structured[16:]), "structured snapshot marker or reserved features drifted")

    for name, capacity in CAPACITIES.items():
        item = metadata["entities"][name]
        require(item["capacity"] == capacity and item["total"] == counts[name], f"{name} metadata count drifted")
        require(item["selected"] == min(counts[name], capacity) and item["omitted"] == max(0, counts[name] - capacity), f"{name} selection count drifted")
        require(item["truncated"] == (counts[name] > capacity), f"{name} truncation flag drifted")
        validate_mask(blob, sections, f"entities.{name}.mask", item["selected"])

    global_values = section_values(blob, sections, "spatial.global")
    require(all(value == 1.0 for value in global_values[:4096]), "global in-map channel is not fully valid")
    require(all(value == 0.0 for value in global_values[16 * 4096:]), "global reserved channels are non-zero")
    for cell in range(4096):
        require(abs(sum(global_values[channel * 4096 + cell] for channel in range(1, 12)) - 1.0) <= 1e-6, "global tile-type channels are not one-hot/mean-complete")
    bin_tiles = (manifest["map_width"] // 64) * (manifest["map_height"] // 64)
    projection_map = projection["state"]["map"]
    for channel, key in ((1, "clear_tiles"), (3, "road_tiles"), (4, "house_tiles"), (7, "water_tiles")):
        observed = round(sum(global_values[channel * 4096:(channel + 1) * 4096]) * bin_tiles)
        require(observed == projection_map[key], f"global {key} disagrees with the independent reset projection")

    if manifest["map_width"] == 64 and manifest["map_height"] == 64:
        for view, side in (("regional", 64), ("local", 32)):
            values = section_values(blob, sections, f"spatial.{view}")
            origin_x, origin_y = metadata["spatial"][f"{view}_origin"]
            for y in range(side):
                for x in range(side):
                    absolute_x, absolute_y = origin_x + x, origin_y + y
                    target = y * side + x
                    if 0 <= absolute_x < 64 and 0 <= absolute_y < 64:
                        global_cell = absolute_y * 64 + absolute_x
                        require(all(values[channel * side * side + target] == global_values[channel * 4096 + global_cell] for channel in range(32)), f"{view} cross-view tile mismatch at {absolute_x},{absolute_y}")
                    else:
                        require(all(values[channel * side * side + target] == 0.0 for channel in range(32)), f"{view} out-of-map tile is not explicitly zero")

    towns = sorted(projection["state"]["towns"], key=lambda item: (-item["population"], item["id"]))[:128]
    town_rows = section_values(blob, sections, "entities.towns.values")
    town_id_scale = 63999
    width_scale = max(1, manifest["map_width"] - 1)
    height_scale = max(1, manifest["map_height"] - 1)
    for row_index, town in enumerate(towns):
        row = town_rows[row_index * FEATURES["towns"]:(row_index + 1) * FEATURES["towns"]]
        require(near_integer(row[0], town_id_scale, town["id"]), "town entity ID/order drifted")
        require(near_integer(row[1], width_scale, town["x"]) and near_integer(row[2], height_scale, town["y"]), "town entity coordinates drifted")
        require(near_integer(row[3], 100_000, town["population"]), "town entity population drifted")
    company_rows = section_values(blob, sections, "entities.companies.values")
    company = projection["state"]["company"]
    require(near_integer(company_rows[0], 14, company["id"]) and company_rows[1] == 1.0, "own-company row ordering drifted")
    require(abs(company_rows[2] * 1_000_000_000 - company["money"]) <= 8 and abs(company_rows[3] * 1_000_000_000 - company["loan"]) <= 8, "company money/loan features drifted")

    expected_nodes = sum(metadata["entities"][name]["selected"] for name in ("towns", "industries", "stations", "vehicles"))
    require(metadata["graph"]["nodes"]["selected"] == expected_nodes, "graph node count does not cover selected entity rows")
    validate_mask(blob, sections, "graph.nodes.mask", expected_nodes)
    edge_count = metadata["graph"]["edges"]["selected"]
    require(edge_count == metadata["entities"]["industries"]["selected"] * 2, "graph does not contain both directed nearest-town edges per industry")
    validate_mask(blob, sections, "graph.edges.mask", edge_count)
    edges = section_values(blob, sections, "graph.edges.values")
    decoded_edges: list[tuple[int, int, int]] = []
    for row_index in range(edge_count):
        row = edges[row_index * 16:(row_index + 1) * 16]
        source = round(row[0] * 2047)
        destination = round(row[1] * 2047)
        kind = round(row[2])
        require(source < expected_nodes and destination < expected_nodes and kind in (0, 1) and 0.0 <= row[3] <= 1.0, "graph edge feature is invalid")
        decoded_edges.append((source, destination, kind))
    require(decoded_edges == sorted(decoded_edges), "graph edges are not source/destination/kind ordered")
    require({(destination, source, 1 - kind) for source, destination, kind in decoded_edges} == set(decoded_edges), "graph directed edge pairs are incomplete")
    return M15ObservationSummary(manifest["map_width"], manifest["map_height"], counts["towns"], counts["industries"], metadata["binary"]["sha256"], 0)


def qualify(root: pathlib.Path, openttd: pathlib.Path, opengfx: pathlib.Path, artifact_root: pathlib.Path, width: int, height: int, seed: int, *, sandbox: str = "bubblewrap") -> pathlib.Path:
    root, openttd, opengfx, artifact_root = root.resolve(), openttd.resolve(), opengfx.resolve(), artifact_root.resolve()
    require(artifact_root.is_absolute() and not artifact_root.exists() and not artifact_root.is_symlink(), "observation artifact root must be a new absolute path")
    manifest = build_manifest(root, openttd, opengfx, width, height, seed)
    qualify_m15_native_reset.validate_schema(manifest, root / qualify_m15_native_reset.MANIFEST_SCHEMA, "M15 observation reset manifest")
    artifact_root.mkdir(mode=0o700)
    manifest_path, projection_path = artifact_root / MANIFEST_NAME, artifact_root / PROJECTION_NAME
    metadata_path = artifact_root / METADATA_NAME
    qualify_m15_native_reset.canonical_write_new(manifest_path, manifest)
    environment = acquire_ai_package.isolated_environment(artifact_root)
    rss: list[int] = []
    stop = threading.Event()
    started = time.monotonic()
    process = subprocess.Popen(
        process_command(openttd, artifact_root, manifest_path, projection_path, metadata_path, sandbox),
        cwd=openttd.parent, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", preexec_fn=qualify_m15_native_reset.apply_limits, start_new_session=True,
    )
    monitor = threading.Thread(target=qualify_ai_runtime.monitor_rss, args=(process, stop, rss), daemon=True)
    monitor.start()
    try:
        output, _ = process.communicate(timeout=qualify_m15_native_reset.LIMITS["wall_seconds"])
    except subprocess.TimeoutExpired as exc:
        acquire_ai_package.terminate_process(acquire_ai_package.ConsoleSession(process))
        raise M15ObservationError("observation process exceeded its wall-time limit") from exc
    finally:
        stop.set()
        monitor.join(timeout=1)
    wall_seconds = time.monotonic() - started
    transcript = artifact_root / TRANSCRIPT_NAME
    transcript.write_text(output, encoding="utf-8")
    require(process.returncode == 0, f"observation process returned {process.returncode}: {output[-2000:]}")
    require("Error: M15" not in output, "observation process emitted a fail-closed diagnostic")
    projection = qualify_m15_native_reset.validate_projection(root, manifest, projection_path)
    summary = validate_observation(root, artifact_root, manifest, projection)
    maximum_rss = max(rss, default=0)
    evidence = {
        "schema_version": "openttd-rl-v2-m15-observation-evidence-1",
        "outcome": "PASS",
        "width": width, "height": height, "seed": seed,
        "manifest_sha256": sha256_file(manifest_path), "projection_sha256": sha256_file(projection_path),
        "metadata_sha256": sha256_file(metadata_path), "binary_sha256": summary.binary_sha256,
        "transcript_sha256": sha256_file(transcript), "observation_bytes": OBSERVATION_BYTES,
        "towns": summary.towns, "industries": summary.industries,
        "maximum_rss_kib": maximum_rss, "wall_seconds": round(wall_seconds, 6),
        "oracle_checks": ["exact-layout", "finite-floats", "canonical-masks", "structured-projection", "global-type-projection", "64x64-cross-view", "entity-projection", "graph-pairs"],
    }
    evidence_path = artifact_root / EVIDENCE_NAME
    qualify_m15_native_reset.canonical_write_new(evidence_path, evidence)
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
        print(f"V2_M15_OBSERVATION=PASS dimensions={args.width}x{args.height} seed={args.seed} evidence={evidence} sha256={sha256_file(evidence)}")
        return 0
    except (M15ObservationError, qualify_m15_native_reset.M15NativeResetError, OSError, subprocess.SubprocessError) as exc:
        print(f"V2_M15_OBSERVATION=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
