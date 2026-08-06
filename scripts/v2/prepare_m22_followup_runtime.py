#!/usr/bin/env python3
"""Build and retain the manifest-blind corrected M22 follow-up runtime.

The preparer starts from the accepted M21 source, applies the immutable M22
final-world patch followed by the diagnosed two-file correction, builds and
tests OpenTTD, stages the byte-pinned M20/M21 runtime closure, and runs only a
fixed synthetic smoke inventory. It never opens final-v1 or follow-up manifests
and cannot execute an acceptance case.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
from typing import Any

import jsonschema

import m22_final_native as native
import prepare_m22_final_runtime as foundation


FINAL_PATCH = foundation.PATCH
CORRECTION_PATCH = pathlib.Path(
    "integration/openttd/patches/15.3/m22/followup/0001-Correct-M22-native-harness-boundaries.patch"
)
PATCHES = (FINAL_PATCH, CORRECTION_PATCH)
PATCH_TOUCHED = (
    foundation.TOUCHED,
    ("src/rl_v2_air.cpp", "src/rl_v2_broad.cpp"),
)
SCHEMA = pathlib.Path("docs/project/schema/v2-m22-followup-runtime-source.schema.json")
IMMUTABLE_FINAL_EVIDENCE = pathlib.Path("config/v2/m22-final-evaluation-evidence.json")
SOURCE_COMMIT_MESSAGE = "Add corrected manifest-blind M22 follow-up runtime"

SMOKE_CASES: tuple[dict[str, Any], ...] = (*foundation.SMOKE_CASES,
    {"case_id": "followup-source-g19-passenger-multimodal", "task": "service",
     "transport_mode": "multimodal", "climate": "temperate", "map_width": 64, "map_height": 64,
     "cargo": "PASS", "opponent": "not-applicable", "seed": 223901,
     "required_program": "multimodal-transfer", "native_probe": "multimodal", "source_gate": "G19"},
    {"case_id": "followup-source-g20-aaahogex-128", "task": "competition", "transport_mode": "company",
     "climate": "temperate", "map_width": 128, "map_height": 128, "cargo": "PASS",
     "opponent": "AAAHogEx", "seed": 224001, "required_program": "competition-head-to-head",
     "native_probe": "head-to-head", "source_gate": "G20"},
    {"case_id": "followup-source-g20-krakenai2-128", "task": "competition", "transport_mode": "company",
     "climate": "temperate", "map_width": 128, "map_height": 128, "cargo": "PASS",
     "opponent": "KrakenAI2", "seed": 224002, "required_program": "competition-head-to-head",
     "native_probe": "head-to-head", "source_gate": "G20"},
    {"case_id": "followup-source-g20-noopai-128", "task": "competition", "transport_mode": "company",
     "climate": "temperate", "map_width": 128, "map_height": 128, "cargo": "PASS", "opponent": "NoOpAI",
     "seed": 224003, "required_program": "competition-head-to-head", "native_probe": "head-to-head",
     "source_gate": "G20"},
    {"case_id": "followup-source-g21-authority-economy", "task": "retention", "transport_mode": "broad",
     "climate": "temperate", "map_width": 64, "map_height": 64, "cargo": "not-applicable",
     "opponent": "not-applicable", "seed": 224101, "required_program": "authority-economy",
     "native_probe": "authority-economy", "source_gate": "G21"},
    {"case_id": "followup-source-g21-events", "task": "retention", "transport_mode": "broad",
     "climate": "temperate", "map_width": 64, "map_height": 64, "cargo": "not-applicable",
     "opponent": "not-applicable", "seed": 224102, "required_program": "event-recovery",
     "native_probe": "events", "source_gate": "G21"},
)


def prepare_source(base_source: pathlib.Path, source_path: pathlib.Path,
                   patches: tuple[pathlib.Path, ...], base_commit: str) -> dict[str, str]:
    foundation.require(len(patches) == len(PATCH_TOUCHED), "follow-up patch inventory drifted")
    foundation.checked(["git", "clone", "--no-hardlinks", "--no-checkout", str(base_source), str(source_path)],
                       source_path.parent, timeout=300)
    foundation.git(source_path, "checkout", "--detach", base_commit)
    foundation.require(foundation.git(source_path, "status", "--porcelain") == "", "fresh M21 clone is dirty")
    cumulative: set[str] = set()
    for patch, touched in zip(patches, PATCH_TOUCHED, strict=True):
        foundation.checked(["git", "apply", "--check", "--whitespace=error-all", str(patch)],
                           source_path, timeout=60)
        foundation.checked(["git", "apply", "--index", "--whitespace=error-all", str(patch)],
                           source_path, timeout=60)
        cumulative.update(touched)
        actual = set(foundation.git(source_path, "diff", "--cached", "--name-only").splitlines())
        foundation.require(actual == cumulative, f"staged corrected M22 patch scope drifted: {sorted(actual)}")
    environment = dict(os.environ)
    environment.update(foundation.SOURCE_COMMIT_ENV)
    foundation.checked(["git", "-c", "commit.gpgSign=false", "commit", "--no-gpg-sign", "-m",
                        SOURCE_COMMIT_MESSAGE], source_path, timeout=60, environment=environment)
    foundation.require(foundation.git(source_path, "status", "--porcelain") == "",
                       "retained corrected M22 source is dirty after commit")
    return {"commit": foundation.git(source_path, "rev-parse", "HEAD"), "path": str(source_path),
            "tree": foundation.git(source_path, "rev-parse", "HEAD^{tree}")}


def run_smokes(root: pathlib.Path, artifact_root: pathlib.Path,
               runtime: native.RuntimePaths, *, bwrap_path: pathlib.Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    smoke_root = artifact_root / "smokes"
    smoke_root.mkdir(mode=0o700)
    for ordinal, case in enumerate(SMOKE_CASES, 1):
        case_root = smoke_root / case["case_id"]
        record = native.run_native_case(
            root, runtime, case_root, dict(case), bwrap_path=bwrap_path,
        )
        records.append({"artifact_root": str(case_root), "private_seed": case["seed"], **record})
        print(f"M22 corrected runtime smoke {ordinal:02d}/{len(SMOKE_CASES)} PASS {case['case_id']}", flush=True)
    return records


def run(root: pathlib.Path, artifact_root: pathlib.Path, evidence_path: pathlib.Path, *, jobs: int,
        bwrap_path: pathlib.Path,
        artifact_context: foundation.ArtifactContext | None = None) -> dict[str, Any]:
    root, artifact_root, evidence_path = root.resolve(), artifact_root.resolve(), evidence_path.resolve()
    context = artifact_context
    foundation.require(context is not None and context.is_live,
                       "corrected M22 runtime preparation requires one live artifact context")
    foundation.require(jobs >= 1, "build jobs must be positive")
    bwrap = foundation.preflight_bwrap(bwrap_path)
    foundation.require(not artifact_root.exists() and not artifact_root.is_symlink(),
                       "corrected retained artifact root must be new")
    foundation.require(not evidence_path.exists() and not evidence_path.is_symlink(),
                       "corrected runtime evidence output must be new")
    foundation.require(foundation.git(root, "status", "--porcelain") == "",
                       "repository must be clean before corrected runtime preparation")
    repository = {"commit": foundation.git(root, "rev-parse", "HEAD"),
                  "tree": foundation.git(root, "rev-parse", "HEAD^{tree}")}

    m21_config = foundation.load(root / foundation.M21_SOURCE)
    foundation.m20_source.validate(root, artifact_context=context)
    foundation.m21_source.validate(root, artifact_context=context)
    base_source = context.artifact_set("v2-m21-broad-a") / "source"

    patches = tuple((root / path).resolve() for path in PATCHES)
    foundation.require(all(path.is_file() and not path.is_symlink() for path in patches),
                       "corrected M22 patch series is unavailable")
    immutable = foundation.load(root / IMMUTABLE_FINAL_EVIDENCE)
    foundation.require(immutable.get("status") == "FAIL" and immutable.get("manifest", {}).get("id") == native.FINAL_TOKEN,
                       "immutable failed final-v1 evidence identity drifted")

    artifact_root.mkdir(mode=0o700)
    source_path, build_path = artifact_root / "source", artifact_root / "build-followup"
    print("M22 corrected runtime source preparation", flush=True)
    source = prepare_source(base_source, source_path, patches, m21_config["source"]["commit"])
    print("M22 corrected runtime configure/build/CTest", flush=True)
    open_gfx_source = context.artifact_set("v2-m21-broad-a") / "build-broad" / "baseset" / \
        pathlib.PurePosixPath(m21_config["build"]["open_gfx"]["path"]).name
    build, open_gfx = foundation.configure_and_build(
        source_path, build_path, artifact_root, jobs, open_gfx_source,
        m21_config["build"]["open_gfx"]["sha256"],
    )
    print("M22 corrected runtime asset staging", flush=True)
    runtime_assets = foundation.stage_runtime(root, artifact_root, build_path, context, open_gfx)
    executable = foundation.file_record(build_path / "openttd")
    runtime = native.RuntimePaths(
        executable=pathlib.Path(executable["path"]), opengfx=pathlib.Path(runtime_assets["open_gfx"]["path"]),
        base_config=pathlib.Path(runtime_assets["configs"]["base"]["path"]),
        content_config=pathlib.Path(runtime_assets["configs"]["content"]["path"]),
        gamescript_config=pathlib.Path(runtime_assets["configs"]["gamescript"]["path"]),
        source_tree=source["tree"],
    )
    print("M22 corrected runtime fixed synthetic smokes", flush=True)
    smokes = run_smokes(root, artifact_root, runtime, bwrap_path=bwrap)
    patch_records = [
        {"path": str(relative), "sha256": foundation.sha256(path), "touched_files": list(touched)}
        for relative, path, touched in zip(PATCHES, patches, PATCH_TOUCHED, strict=True)
    ]
    evidence = {
        "base": {"commit": m21_config["source"]["commit"],
                 "source_record_sha256": foundation.sha256(root / foundation.M21_SOURCE),
                 "tree": m21_config["source"]["tree"]},
        "boundaries": {
            "followup": {"evaluator_processes": 0, "manifest_opened": False, "native_dispatches": 0,
                         "protocol_state": "not-yet-frozen"},
            "immutable_final_v1": {"evidence_path": str(IMMUTABLE_FINAL_EVIDENCE),
                                   "evidence_sha256": foundation.sha256(root / IMMUTABLE_FINAL_EVIDENCE),
                                   "evaluator_processes": 0, "manifest_opened": False, "native_dispatches": 0,
                                   "status": "FAIL"},
        },
        "build": build,
        "executable": executable,
        "patches": patch_records,
        "prerequisites": {
            "final_runtime_source_record_sha256": foundation.sha256(root / "config/v2/m22-final-runtime-source.json"),
            "m20_source_record_sha256": foundation.sha256(root / foundation.M20_SOURCE),
            "m21_source_record_sha256": foundation.sha256(root / foundation.M21_SOURCE),
        },
        "repository": repository,
        "retained_artifact": str(artifact_root),
        "runtime": runtime_assets,
        "schema_version": "openttd-rl-v2-m22-followup-runtime-source-1",
        "smokes": smokes,
        "source": source,
        "status": "PASS",
    }
    try:
        jsonschema.Draft202012Validator(foundation.load(root / SCHEMA)).validate(evidence)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise foundation.M22RuntimePreparationError(
            f"generated corrected runtime evidence schema failed at {where}: {exc.message}"
        ) from exc
    foundation.write_new(evidence_path, evidence)
    print(f"V2_M22_FOLLOWUP_RUNTIME_PREP=PASS source={source['tree']} smokes={len(smokes)} ctests=98", flush=True)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--evidence", type=pathlib.Path, required=True)
    parser.add_argument("--jobs", type=int, default=max(1, min(8, os.cpu_count() or 1)))
    parser.add_argument("--bwrap", type=pathlib.Path, required=True,
                        help="absolute Bubblewrap executable path for native smoke isolation")
    parser.add_argument("--input-artifact-root", type=pathlib.Path,
                        help="absolute common root containing the accepted M20 and M21 logical artifact sets")
    args = parser.parse_args()
    try:
        input_root = foundation.resolve_artifact_root(args.input_artifact_root)
        context = None if input_root is None else foundation.ArtifactContext.live(input_root)
        run(
            args.root, args.artifact_root, args.evidence, jobs=args.jobs,
            bwrap_path=args.bwrap, artifact_context=context,
        )
        return 0
    except (foundation.M22RuntimePreparationError, native.M22FinalNativeError,
            foundation.m20_source.M20SourceError, foundation.m21_source.M21SourceError,
            foundation.ArtifactContextError,
            OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"V2_M22_FOLLOWUP_RUNTIME_PREP=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
