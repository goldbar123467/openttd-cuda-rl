#!/usr/bin/env python3
"""Run and validate all 49 M15 rectangles through the source-integrated reset path."""

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

from artifact_context import ArtifactContext, ArtifactContextError, ArtifactRequirement
import qualify_m15_native_reset


SCHEMA = pathlib.Path("docs/project/schema/v2-m15-native-reset-matrix.schema.json")
EVIDENCE = pathlib.Path("config/v2/m15-native-reset-matrix.json")
EVIDENCE_NAME = "m15-native-reset-matrix.json"
REPEAT_DIR = "repeat-0064x0064"
LIVE_CONSUMER = "m15-native-reset-matrix"


class M15NativeResetMatrixError(ValueError):
    """The complete source-integrated reset matrix is missing or inconsistent."""


@dataclass(frozen=True)
class M15NativeResetMatrixSummary:
    rectangles: int
    generated: int
    preflight_rejected: int
    maximum_rss_kib: int
    live: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15NativeResetMatrixError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15NativeResetMatrixError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15NativeResetMatrixError(f"cannot hash {path}: {exc}") from exc


def artifact_dir(width: int, height: int) -> str:
    return f"reset-{width:04d}x{height:04d}"


def run_one(root: pathlib.Path, openttd: pathlib.Path, opengfx: pathlib.Path, matrix_root: pathlib.Path, width: int, height: int, seed: int, sandbox: str, directory: str | None = None) -> str:
    target = matrix_root / (directory or artifact_dir(width, height))
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(root / "scripts/v2")
    command = [
        sys.executable, str(root / "scripts/v2/qualify_m15_native_reset.py"), "--root", str(root),
        "--openttd", str(openttd), "--opengfx", str(opengfx), "--artifact-root", str(target),
        "--width", str(width), "--height", str(height), "--seed", str(seed), "--sandbox", sandbox,
    ]
    result = subprocess.run(command, cwd=root, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    require(result.returncode == 0, f"M15 native reset {width}x{height} failed:\n{result.stdout}")
    return result.stdout.strip()


def generated_result(matrix_root: pathlib.Path, width: int, height: int, directory: str | None = None) -> dict[str, Any]:
    name = directory or artifact_dir(width, height)
    artifact = matrix_root / name
    evidence_path = artifact / qualify_m15_native_reset.EVIDENCE_NAME
    evidence = load_json(evidence_path)
    return {
        "width": width,
        "height": height,
        "tile_count": width * height,
        "outcome": "GENERATED",
        "reason_code": None,
        "artifact_dir": name,
        "manifest_sha256": evidence["manifest_sha256"],
        "projection_sha256": evidence["projection_sha256"],
        "evidence_sha256": sha256_file(evidence_path),
        "transcript_sha256": evidence["transcript_sha256"],
        "towns": evidence["towns"],
        "industries": evidence["industries"],
        "maximum_rss_kib": evidence["maximum_rss_kib"],
        "wall_seconds": evidence["wall_seconds"],
    }


def preflight_result(width: int, height: int) -> dict[str, Any]:
    return {
        "width": width, "height": height, "tile_count": width * height,
        "outcome": "PREFLIGHT_REJECTED", "reason_code": "tile-count-exceeds-useful-play-preflight-budget",
        "artifact_dir": None, "manifest_sha256": None, "projection_sha256": None, "evidence_sha256": None,
        "transcript_sha256": None, "towns": None, "industries": None, "maximum_rss_kib": 0, "wall_seconds": 0,
    }


def summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(item["outcome"] for item in results)
    generated = [item for item in results if item["outcome"] == "GENERATED"]
    return {
        "rectangles": len(results), "generated": counts["GENERATED"], "preflight_rejected": counts["PREFLIGHT_REJECTED"],
        "maximum_rss_kib": max(item["maximum_rss_kib"] for item in generated),
        "summed_wall_seconds": round(sum(item["wall_seconds"] for item in generated), 6),
        "maximum_towns": max(item["towns"] for item in generated),
        "maximum_industries": max(item["industries"] for item in generated),
    }


def _recorded_artifact_set(evidence: dict[str, Any]) -> str:
    recorded_base = evidence["artifact_base_hint"]
    base = pathlib.PurePosixPath(recorded_base)
    require(
        isinstance(recorded_base, str)
        and recorded_base.startswith("/")
        and not recorded_base.startswith("//")
        and str(base) == recorded_base
        and all(part not in {"", ".", ".."} for part in base.parts[1:]),
        "M15 native reset matrix recorded artifact base is not an absolute normalized POSIX path",
    )
    logical_set = evidence["artifact_root"]
    require(
        isinstance(logical_set, str)
        and logical_set not in {"", ".", ".."}
        and "/" not in logical_set
        and "\\" not in logical_set,
        "M15 native reset matrix logical artifact set is invalid",
    )
    return logical_set


def _requirements(evidence: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    logical_set = _recorded_artifact_set(evidence)
    requirements: list[ArtifactRequirement] = []
    for item in evidence["results"]:
        if item["outcome"] != "GENERATED":
            continue
        for filename, digest in (
            (qualify_m15_native_reset.EVIDENCE_NAME, item["evidence_sha256"]),
            (qualify_m15_native_reset.MANIFEST_NAME, item["manifest_sha256"]),
            (qualify_m15_native_reset.PROJECTION_NAME, item["projection_sha256"]),
            (qualify_m15_native_reset.TRANSCRIPT_NAME, item["transcript_sha256"]),
        ):
            requirements.append(ArtifactRequirement(
                logical_set,
                f"{item['artifact_dir']}/{filename}",
                "file",
                LIVE_CONSUMER,
                digest,
            ))
    repeat = evidence["determinism"]
    for filename, field in (
        (qualify_m15_native_reset.EVIDENCE_NAME, "evidence_sha256"),
        (qualify_m15_native_reset.MANIFEST_NAME, "manifest_sha256"),
        (qualify_m15_native_reset.PROJECTION_NAME, "projection_sha256"),
        (qualify_m15_native_reset.TRANSCRIPT_NAME, "transcript_sha256"),
    ):
        requirements.append(ArtifactRequirement(
            logical_set,
            f"{repeat['artifact_dir']}/{filename}",
            "file",
            LIVE_CONSUMER,
            repeat[field],
        ))
    return tuple(requirements)


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    return _requirements(load_json(root / EVIDENCE))


def run_matrix(root: pathlib.Path, openttd: pathlib.Path, opengfx: pathlib.Path, matrix_root: pathlib.Path, seed: int, *, workers: int = 2, sandbox: str = "bubblewrap") -> pathlib.Path:
    root = root.resolve()
    openttd = openttd.resolve()
    opengfx = opengfx.resolve()
    matrix_root = matrix_root.resolve()
    require(matrix_root.is_absolute() and not matrix_root.exists() and not matrix_root.is_symlink(), "matrix artifact root must be a new absolute path")
    require(1 <= workers <= 4, "matrix workers must be in 1..4")
    contract = load_json(root / qualify_m15_native_reset.CONTRACT)
    require(seed in {value for item in contract["seeds"]["sets"].values() for value in item["seeds"]}, "matrix seed is not frozen")
    rectangles = [tuple(item) for item in contract["map"]["native_rectangles"]]
    generated_rectangles = [(width, height) for width, height in rectangles if width * height <= qualify_m15_native_reset.MAXIMUM_TILES]
    matrix_root.mkdir(mode=0o700)
    outputs: dict[tuple[int, int], str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_one, root, openttd, opengfx, matrix_root, width, height, seed, sandbox): (width, height) for width, height in generated_rectangles}
        for future in concurrent.futures.as_completed(futures):
            dimensions = futures[future]
            outputs[dimensions] = future.result()
            print(outputs[dimensions], flush=True)
    require(set(outputs) == set(generated_rectangles), "matrix did not run every in-budget rectangle")
    print(run_one(root, openttd, opengfx, matrix_root, 64, 64, seed, sandbox, REPEAT_DIR), flush=True)

    results = [generated_result(matrix_root, width, height) if width * height <= qualify_m15_native_reset.MAXIMUM_TILES else preflight_result(width, height) for width, height in rectangles]
    repeat = generated_result(matrix_root, 64, 64, REPEAT_DIR)
    require(repeat["manifest_sha256"] == results[0]["manifest_sha256"], "repeat manifest differs from primary 64x64 manifest")
    require(repeat["projection_sha256"] == results[0]["projection_sha256"], "repeat projection differs from primary 64x64 projection")
    source = load_json(root / qualify_m15_native_reset.SOURCE)
    value = {
        "$schema": "../../docs/project/schema/v2-m15-native-reset-matrix.schema.json",
        "schema_version": "openttd-rl-v2-m15-native-reset-matrix-1",
        "schema_sha256": sha256_file(root / SCHEMA), "snapshot_date": "2026-08-02",
        "contract_sha256": sha256_file(root / qualify_m15_native_reset.CONTRACT),
        "native_source_sha256": sha256_file(root / qualify_m15_native_reset.SOURCE),
        "executable": {key: source["build"]["executable"][key] for key in ("sha256", "size")},
        "artifact_base_hint": str(matrix_root.parent), "artifact_root": matrix_root.name, "seed": seed,
        "policy": {"all_49_rectangles": True, "source_integrated_generated_at_or_below_budget": True, "source_and_harness_preflight_above_budget": True, "same_manifest_same_projection": True, "g15_pass_claim": False},
        "results": results,
        "determinism": {key: repeat[key] for key in ("width", "height", "artifact_dir", "manifest_sha256", "projection_sha256", "evidence_sha256", "transcript_sha256")} | {"byte_identical": True},
        "summary": summary(results),
    }
    path = matrix_root / EVIDENCE_NAME
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    validate(root, path, artifact_context=ArtifactContext.live(matrix_root.parent))
    return path


def validate(
    root: pathlib.Path,
    evidence_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_context: ArtifactContext | None = None,
) -> M15NativeResetMatrixSummary:
    context = artifact_context or ArtifactContext.offline()
    repository_evidence = evidence_path is None
    root = root.resolve()
    evidence_path = evidence_path or root / EVIDENCE
    schema_path = schema_path or root / SCHEMA
    evidence = load_json(evidence_path)
    schema_value = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema_value, format_checker=jsonschema.FormatChecker()).validate(evidence)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15NativeResetMatrixError(f"M15 native reset matrix schema failed at {location}: {exc.message}") from exc
    require(evidence["schema_sha256"] == sha256_file(schema_path), "M15 native reset matrix schema SHA-256 mismatch")
    require(evidence["contract_sha256"] == sha256_file(root / qualify_m15_native_reset.CONTRACT), "M15 native reset matrix contract SHA-256 mismatch")
    require(evidence["native_source_sha256"] == sha256_file(root / qualify_m15_native_reset.SOURCE), "M15 native reset matrix source SHA-256 mismatch")
    source = load_json(root / qualify_m15_native_reset.SOURCE)
    require(evidence["executable"] == {key: source["build"]["executable"][key] for key in ("sha256", "size")}, "M15 native reset matrix executable drifted")
    contract = load_json(root / qualify_m15_native_reset.CONTRACT)
    rectangles = [tuple(item) for item in contract["map"]["native_rectangles"]]
    results = evidence["results"]
    require([(item["width"], item["height"]) for item in results] == rectangles, "M15 native reset matrix rectangle order/coverage drifted")
    generated_directories = [item["artifact_dir"] for item in results if item["outcome"] == "GENERATED"]
    require(len(generated_directories) == len(set(generated_directories)), "M15 native reset matrix artifact directories are duplicated")
    for item in results:
        require(item["tile_count"] == item["width"] * item["height"], f"M15 native reset {item['width']}x{item['height']} tile count drifted")
        if item["tile_count"] <= qualify_m15_native_reset.MAXIMUM_TILES:
            require(item["outcome"] == "GENERATED" and item["reason_code"] is None and item["artifact_dir"] == artifact_dir(item["width"], item["height"]), f"M15 native reset {item['width']}x{item['height']} generated outcome drifted")
            require(item["towns"] == max(2, min(128, item["tile_count"] // 4096)), f"M15 native reset {item['width']}x{item['height']} town target drifted")
            require(all(item[key] is not None for key in ("manifest_sha256", "projection_sha256", "evidence_sha256", "transcript_sha256", "industries")), f"M15 native reset {item['width']}x{item['height']} evidence is incomplete")
        else:
            require(item == preflight_result(item["width"], item["height"]), f"M15 native reset {item['width']}x{item['height']} preflight outcome drifted")
    require(evidence["summary"] == summary(results), "M15 native reset matrix summary drifted")
    require(evidence["summary"]["generated"] == 39 and evidence["summary"]["preflight_rejected"] == 10, "M15 native reset outcome counts drifted")
    first = results[0]
    determinism = evidence["determinism"]
    require(determinism["manifest_sha256"] == first["manifest_sha256"] and determinism["projection_sha256"] == first["projection_sha256"], "M15 native reset deterministic repeat drifted")
    logical_set = _recorded_artifact_set(evidence)

    if context.is_live:
        requirements = (
            required_live_inputs(root)
            if repository_evidence
            else _requirements(evidence)
        )
        context.preflight(requirements)
        matrix_root = context.artifact_set(logical_set)
        require(matrix_root.is_dir() and not matrix_root.is_symlink(), "M15 native reset matrix artifact root is missing or a symlink")
        for item in results:
            if item["outcome"] != "GENERATED":
                continue
            live = generated_result(matrix_root, item["width"], item["height"])
            require(live == item, f"M15 native reset live artifact drifted: {item['artifact_dir']}")
            manifest = load_json(matrix_root / item["artifact_dir"] / qualify_m15_native_reset.MANIFEST_NAME)
            require(manifest["map_seed"] == evidence["seed"] and manifest["map_width"] == item["width"] and manifest["map_height"] == item["height"], f"M15 native reset live manifest request drifted: {item['artifact_dir']}")
            qualify_m15_native_reset.validate_projection(root, manifest, matrix_root / item["artifact_dir"] / qualify_m15_native_reset.PROJECTION_NAME)
        repeat = generated_result(matrix_root, 64, 64, REPEAT_DIR)
        require({key: repeat[key] for key in ("width", "height", "artifact_dir", "manifest_sha256", "projection_sha256", "evidence_sha256", "transcript_sha256")} | {"byte_identical": True} == determinism, "M15 native reset live deterministic artifact drifted")

    return M15NativeResetMatrixSummary(len(results), evidence["summary"]["generated"], evidence["summary"]["preflight_rejected"], evidence["summary"]["maximum_rss_kib"], context.is_live)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--openttd", type=pathlib.Path)
    parser.add_argument("--opengfx", type=pathlib.Path)
    parser.add_argument("--artifact-root", type=pathlib.Path)
    parser.add_argument("--evidence", type=pathlib.Path)
    parser.add_argument("--seed", type=int, default=1110312784)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--sandbox", choices=("bubblewrap", "test-none"), default="bubblewrap")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    creation_options = (args.openttd, args.opengfx, args.artifact_root)
    if any(value is not None for value in creation_options) and args.evidence is not None:
        parser.error("creation options cannot be mixed with validation options")
    try:
        if args.artifact_root is not None:
            require(args.openttd is not None and args.opengfx is not None, "creation requires --openttd and --opengfx")
            path = run_matrix(args.root, args.openttd, args.opengfx, args.artifact_root, args.seed, workers=args.workers, sandbox=args.sandbox)
            print(f"V2_M15_NATIVE_RESET_MATRIX=GENERATED evidence={path} sha256={sha256_file(path)}")
            return 0
        require(args.openttd is None and args.opengfx is None, "creation requires --artifact-root")
        summary_value = validate(
            args.root,
            args.evidence,
            artifact_context=ArtifactContext.offline(),
        )
        print(f"V2_M15_NATIVE_RESET_MATRIX=PASS rectangles={summary_value.rectangles} generated={summary_value.generated} preflight_rejected={summary_value.preflight_rejected} max_rss_kib={summary_value.maximum_rss_kib} live={str(summary_value.live).lower()}")
        return 0
    except (
        M15NativeResetMatrixError,
        qualify_m15_native_reset.M15NativeResetError,
        ArtifactContextError,
        OSError,
    ) as exc:
        print(f"V2_M15_NATIVE_RESET_MATRIX=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
