#!/usr/bin/env python3
"""Run and validate the complete 49-rectangle M15 native map matrix."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Any

import jsonschema

import qualify_m15_native_map


SCHEMA_RELATIVE = pathlib.Path("docs/project/schema/v2-m15-map-evidence.schema.json")
CONTRACT_RELATIVE = pathlib.Path("config/v2/m15-scalable-contract.json")
EVIDENCE_NAME = "m15-map-evidence.json"


class M15MapMatrixError(ValueError):
    """The complete M15 map matrix is missing, inconsistent, or failed."""


@dataclass(frozen=True)
class M15MapMatrixSummary:
    rectangles: int
    generated: int
    preflight_rejected: int
    save_bytes: int
    maximum_rss_kib: int
    live_artifacts: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15MapMatrixError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15MapMatrixError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15MapMatrixError(f"cannot hash {path}: {exc}") from exc


def run_one(
    root: pathlib.Path,
    openttd: pathlib.Path,
    artifact_root: pathlib.Path,
    width: int,
    height: int,
    seed: int,
    sandbox: str,
) -> tuple[tuple[int, int], str]:
    run_root = artifact_root / f"map-{width:04d}x{height:04d}"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(root / "scripts/v2")
    command = [
        sys.executable,
        str(root / "scripts/v2/qualify_m15_native_map.py"),
        "--root", str(root),
        "--openttd", str(openttd),
        "--artifact-root", str(run_root),
        "--width", str(width),
        "--height", str(height),
        "--seed", str(seed),
        "--sandbox", sandbox,
    ]
    result = subprocess.run(command, cwd=root, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    require(result.returncode == 0, f"{width}x{height} map qualifier failed:\n{result.stdout}")
    return (width, height), result.stdout.strip()


def result_projection(manifest: dict[str, Any], artifact_dir: str, evidence_sha256: str) -> dict[str, Any]:
    save = manifest["observations"]["save"]
    map_value = manifest["observations"]["map"]
    return {
        "width": manifest["request"]["width"],
        "height": manifest["request"]["height"],
        "tile_count": manifest["request"]["tile_count"],
        "outcome": manifest["outcome"],
        "reason_code": manifest["reason_code"],
        "artifact_dir": artifact_dir,
        "evidence_file": qualify_m15_native_map.EVIDENCE_NAME,
        "evidence_sha256": evidence_sha256,
        "map_sha256": None if map_value is None else map_value["map_sha256"],
        "save_sha256": None if save is None else save["sha256"],
        "save_size": None if save is None else save["size"],
        "max_rss_kib": manifest["resources"]["max_rss_kib"],
        "wall_seconds": manifest["resources"]["wall_seconds"],
    }


def run_matrix(
    root: pathlib.Path,
    openttd: pathlib.Path,
    artifact_root: pathlib.Path,
    seed: int,
    *,
    workers: int = 2,
    sandbox: str = "bubblewrap",
) -> pathlib.Path:
    root = root.resolve()
    openttd = openttd.resolve()
    artifact_root = artifact_root.resolve()
    require(artifact_root.is_absolute() and not artifact_root.exists() and not artifact_root.is_symlink(), "matrix artifact root must be a new absolute path")
    require(1 <= workers <= 4, "M15 map matrix workers must be in 1..4")
    contract = load_json(root / CONTRACT_RELATIVE)
    require(seed in {value for item in contract["seeds"]["sets"].values() for value in item["seeds"]}, "matrix seed is not frozen")
    rectangles = [tuple(item) for item in contract["map"]["native_rectangles"]]
    artifact_root.mkdir(mode=0o700)
    outputs: dict[tuple[int, int], str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(run_one, root, openttd, artifact_root, width, height, seed, sandbox): (width, height)
            for width, height in rectangles
        }
        for future in concurrent.futures.as_completed(futures):
            dimensions, output = future.result()
            outputs[dimensions] = output
            print(output, flush=True)
    require(set(outputs) == set(rectangles), "M15 map matrix did not run every rectangle")

    results: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    for width, height in rectangles:
        artifact_dir = f"map-{width:04d}x{height:04d}"
        evidence_path = artifact_root / artifact_dir / qualify_m15_native_map.EVIDENCE_NAME
        manifest = qualify_m15_native_map.validate_manifest(root, evidence_path, openttd=openttd)
        manifests.append(manifest)
        results.append(result_projection(manifest, artifact_dir, sha256_file(evidence_path)))
    counts = Counter(item["outcome"] for item in results)
    require(counts == {"GENERATED": 39, "PREFLIGHT_REJECTED": 10}, f"M15 map outcome counts drifted: {dict(counts)}")
    first = manifests[0]
    matrix = {
        "$schema": "../../docs/project/schema/v2-m15-map-evidence.schema.json",
        "schema_version": "openttd-rl-v2-m15-map-evidence-1",
        "schema_sha256": sha256_file(root / SCHEMA_RELATIVE),
        "snapshot_date": "2026-08-02",
        "engine_source": first["engine_source"],
        "executable": first["executable"],
        "contract_sha256": first["contract_sha256"],
        "artifact_base_hint": str(artifact_root.parent),
        "artifact_root": artifact_root.name,
        "seed": seed,
        "policy": {
            "all_49_rectangles": True,
            "generated_at_or_below_tile_budget": True,
            "preflight_rejected_above_tile_budget": True,
            "save_load_required_for_generated": True,
            "all_outcomes_retained": True,
        },
        "results": results,
        "counts": {
            "rectangles": len(results),
            "generated": counts["GENERATED"],
            "preflight_rejected": counts["PREFLIGHT_REJECTED"],
            "save_bytes": sum(item["save_size"] or 0 for item in results),
            "maximum_rss_kib": max(item["max_rss_kib"] for item in results),
            "summed_wall_seconds": round(sum(item["wall_seconds"] for item in results), 6),
        },
    }
    matrix_path = artifact_root / EVIDENCE_NAME
    matrix_path.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
    validate(root, matrix_path, artifact_base=artifact_root.parent, openttd=openttd)
    return matrix_path


def validate(
    root: pathlib.Path,
    evidence_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_base: pathlib.Path | None = None,
    openttd: pathlib.Path | None = None,
) -> M15MapMatrixSummary:
    root = root.resolve()
    evidence_path = evidence_path or root / "config/v2/m15-map-evidence.json"
    schema_path = schema_path or root / SCHEMA_RELATIVE
    evidence = load_json(evidence_path)
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(evidence)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15MapMatrixError(f"M15 map matrix schema failed at {location}: {exc.message}") from exc
    require(evidence["schema_sha256"] == sha256_file(schema_path), "M15 map matrix schema SHA-256 mismatch")
    require(evidence["contract_sha256"] == sha256_file(root / CONTRACT_RELATIVE), "M15 map matrix contract SHA-256 mismatch")
    source = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    require(evidence["engine_source"] == {key: source[key] for key in ("release", "commit", "tree")}, "M15 map matrix engine source drifted")
    contract = load_json(root / CONTRACT_RELATIVE)
    frozen_seeds = {value for item in contract["seeds"]["sets"].values() for value in item["seeds"]}
    require(evidence["seed"] in frozen_seeds, "M15 map matrix seed is not frozen")
    runtime_executable = load_json(root / "config/v2/opponent-runtime-evidence.json")["executable"]
    require(evidence["executable"] == runtime_executable, "M15 map matrix executable drifted from G14 runtime evidence")
    expected_rectangles = [tuple(item) for item in contract["map"]["native_rectangles"]]
    results = evidence["results"]
    require([(item["width"], item["height"]) for item in results] == expected_rectangles, "M15 map matrix rectangle order/coverage drifted")
    require(len({item["artifact_dir"] for item in results}) == len(results), "M15 map matrix artifact directories are duplicated")
    for item in results:
        require(item["tile_count"] == item["width"] * item["height"], f"M15 {item['width']}x{item['height']} tile count drifted")
        if item["tile_count"] <= qualify_m15_native_map.MAXIMUM_GENERATED_TILES:
            require(item["outcome"] == "GENERATED" and item["reason_code"] is None, f"M15 {item['width']}x{item['height']} was not generated inside budget")
            require(item["map_sha256"] is not None and item["save_sha256"] is not None and item["save_size"] is not None and item["max_rss_kib"] > 0, f"M15 {item['width']}x{item['height']} generated evidence is incomplete")
        else:
            require(item["outcome"] == "PREFLIGHT_REJECTED" and item["reason_code"] == "tile-count-exceeds-useful-play-preflight-budget", f"M15 {item['width']}x{item['height']} preflight disposition drifted")
            require(item["map_sha256"] is None and item["save_sha256"] is None and item["save_size"] is None and item["max_rss_kib"] == 0, f"M15 {item['width']}x{item['height']} rejection contains generated artifacts")
    counts = Counter(item["outcome"] for item in results)
    expected_counts = {
        "rectangles": len(results),
        "generated": counts["GENERATED"],
        "preflight_rejected": counts["PREFLIGHT_REJECTED"],
        "save_bytes": sum(item["save_size"] or 0 for item in results),
        "maximum_rss_kib": max(item["max_rss_kib"] for item in results),
        "summed_wall_seconds": round(sum(item["wall_seconds"] for item in results), 6),
    }
    require(evidence["counts"] == expected_counts, "M15 map matrix summary counts drifted")
    require(counts == {"GENERATED": 39, "PREFLIGHT_REJECTED": 10}, f"M15 map matrix outcome inventory drifted: {dict(counts)}")

    if artifact_base is not None:
        artifact_root = artifact_base.resolve() / evidence["artifact_root"]
        require(artifact_root.is_dir() and not artifact_root.is_symlink(), "M15 live map artifact root is missing or a symlink")
        if openttd is not None:
            openttd = openttd.resolve()
            require(evidence["executable"] == {"sha256": sha256_file(openttd), "size": openttd.stat().st_size}, "M15 map matrix executable drifted")
        for item in results:
            evidence_file = artifact_root / item["artifact_dir"] / item["evidence_file"]
            require(evidence_file.is_file() and not evidence_file.is_symlink(), f"M15 live evidence is missing or a symlink: {evidence_file}")
            require(sha256_file(evidence_file) == item["evidence_sha256"], f"M15 {item['width']}x{item['height']} evidence digest drifted")
            manifest = qualify_m15_native_map.validate_manifest(root, evidence_file, openttd=openttd)
            require(result_projection(manifest, item["artifact_dir"], item["evidence_sha256"]) == item, f"M15 {item['width']}x{item['height']} result projection drifted")

    return M15MapMatrixSummary(
        rectangles=len(results),
        generated=counts["GENERATED"],
        preflight_rejected=counts["PREFLIGHT_REJECTED"],
        save_bytes=expected_counts["save_bytes"],
        maximum_rss_kib=expected_counts["maximum_rss_kib"],
        live_artifacts=artifact_base is not None,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--openttd", type=pathlib.Path)
    parser.add_argument("--artifact-root", type=pathlib.Path)
    parser.add_argument("--evidence", type=pathlib.Path)
    parser.add_argument("--artifact-base", type=pathlib.Path)
    parser.add_argument("--seed", type=int, default=1110312784)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--sandbox", choices=("bubblewrap", "test-none"), default="bubblewrap")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.artifact_root is not None:
            require(args.openttd is not None and args.evidence is None and args.artifact_base is None, "matrix run requires --openttd and forbids validation-only options")
            path = run_matrix(args.root, args.openttd, args.artifact_root, args.seed, workers=args.workers, sandbox=args.sandbox)
            print(f"V2_M15_MAP_MATRIX=GENERATED evidence={path} sha256={sha256_file(path)}")
            return 0
        summary = validate(args.root, args.evidence, artifact_base=args.artifact_base, openttd=args.openttd)
        print(
            f"V2_M15_MAP_MATRIX=PASS rectangles={summary.rectangles} generated={summary.generated} "
            f"preflight_rejected={summary.preflight_rejected} save_bytes={summary.save_bytes} "
            f"max_rss_kib={summary.maximum_rss_kib} live={str(summary.live_artifacts).lower()}"
        )
        return 0
    except (M15MapMatrixError, qualify_m15_native_map.M15MapQualificationError, OSError) as exc:
        print(f"V2_M15_MAP_MATRIX=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
