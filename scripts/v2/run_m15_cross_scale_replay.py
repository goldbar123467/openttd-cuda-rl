#!/usr/bin/env python3
"""Run exact twin-process/save-load replay at every M15 curriculum and generalization size."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import resource
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Any

import acquire_ai_package
import freeze_m15_episode_evidence
import qualify_ai_runtime
import qualify_m15_native_reset


CONTRACT = pathlib.Path("config/v2/m15-scalable-contract.json")
EPISODE_SOURCE = pathlib.Path("config/v2/m15-episode-source.json")
NATIVE_SOURCE = pathlib.Path("config/v2/m15-native-source.json")
PROGRAM = pathlib.Path("config/v2/m15-cross-scale-replay-program.json")
PROGRAM_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-episode-program.schema.json")
MANIFEST_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-reset-manifest.schema.json")
TRACE_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-episode-trace.schema.json")
CASES = [
    ("curriculum-64x64", 64, 64, 1110312784, "training", "curriculum"),
    ("curriculum-128x128", 128, 128, 786545128, "training", "curriculum"),
    ("curriculum-256x256", 256, 256, 1922409719, "training", "curriculum"),
    ("curriculum-512x512", 512, 512, 583478638, "training", "curriculum"),
    ("generalization-64x256", 64, 256, 865927513, "generalization", "generalization"),
    ("generalization-128x512", 128, 512, 1936289326, "generalization", "generalization"),
    ("generalization-256x1024", 256, 1024, 348404717, "generalization", "generalization"),
    ("generalization-512x128", 512, 128, 1893295922, "generalization", "generalization"),
    ("generalization-1024x1024", 1024, 1024, 1985050841, "generalization", "generalization"),
]
RUNS = ["run-a", "run-b"]
LIMITS = {"address_space_bytes": 3_221_225_472, "cpu_seconds": 300, "file_bytes": 128 * 1024 * 1024, "wall_seconds": 300}


class M15CrossScaleReplayError(ValueError):
    """Cross-scale replay failed or violated its frozen boundary."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15CrossScaleReplayError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def build_manifest(
    root: pathlib.Path,
    openttd: pathlib.Path,
    opengfx: pathlib.Path,
    width: int,
    height: int,
    seed: int,
    split: str,
    tier: str,
) -> dict[str, Any]:
    contract = load_json(root / CONTRACT)
    episode_source = load_json(root / EPISODE_SOURCE)
    native_source = load_json(root / NATIVE_SOURCE)
    executable = episode_source["build"]["executable"]
    require(openttd.is_file() and not openttd.is_symlink() and os.access(openttd, os.X_OK), "episode executable is unavailable")
    require(openttd.stat().st_size == executable["size"] and freeze_m15_episode_evidence.sha256_file(openttd) == executable["sha256"], "episode executable identity drifted")
    return {
        "schema_version": "openttd-rl-v2-m15-reset-manifest-1",
        "contract_sha256": freeze_m15_episode_evidence.sha256_file(root / CONTRACT),
        "engine_source_tree": native_source["base"]["engine_source_tree"], "executable_sha256": executable["sha256"],
        "map_width": width, "map_height": height, "map_seed": seed,
        "simulation_seed": qualify_m15_native_reset.stream_seed("simulation", seed),
        "candidate_tiebreak_seed": qualify_m15_native_reset.stream_seed("candidate-tiebreak", seed),
        "split": split, "climate": "temperate", "start_year": 1950,
        "settings_manifest_sha256": freeze_m15_episode_evidence.sha256_file(root / "config/v2/setting-inventory.json"),
        "content_manifest_sha256": freeze_m15_episode_evidence.sha256_file(opengfx), "generation_mode": "native-seeded",
        "town_target": max(2, min(128, width * height // 4096)), "industry_target": 256,
        "company_count": 1, "resource_tier": tier, "v1_adapter": False, "rejection_reason": None,
    }


def apply_limits() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (LIMITS["address_space_bytes"], LIMITS["address_space_bytes"]))
    resource.setrlimit(resource.RLIMIT_CPU, (LIMITS["cpu_seconds"], LIMITS["cpu_seconds"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS["file_bytes"], LIMITS["file_bytes"]))
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))


def command(openttd: pathlib.Path, root: pathlib.Path, run: pathlib.Path, sandbox: str) -> list[str]:
    direct = [str(openttd), "-x", "-X", "-Q", "-I", "OpenGFX", "-v", "null", "-s", "null", "-m", "null",
              "-V", str(run / "reset-manifest.json"), "-U", str(run / "reset-projection.json"),
              "-E", str(root / PROGRAM), "-F", str(run / "episode-trace.json"), "-H", str(run / "artifacts")]
    if sandbox == "test-none": return direct
    require(sandbox == "bubblewrap" and shutil.which("bwrap") is not None, "bubblewrap is required for replay qualification")
    return ["bwrap", "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-net",
            "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--bind", str(run), str(run),
            "--chdir", str(openttd.parent), "--", *direct]


def validate_capture(artifact: pathlib.Path, step: dict[str, Any]) -> None:
    label = step["label"]
    observation = artifact / f"{label}-observation.json"
    candidates = artifact / f"{label}-candidates.json"
    require(freeze_m15_episode_evidence.sha256_file(artifact / f"{label}.sav") == step["save_sha256"], f"replay capture save drifted: {label}")
    observation_meta, candidate_meta = load_json(observation), load_json(candidates)
    require(freeze_m15_episode_evidence.sha256_file(observation.with_suffix(".bin")) == step["observation_sha256"] == observation_meta["binary"]["sha256"], f"replay observation drifted: {label}")
    require(freeze_m15_episode_evidence.sha256_file(candidates.with_suffix(".bin")) == step["candidate_sha256"] == candidate_meta["binary"]["sha256"], f"replay candidates drifted: {label}")


def project_run(root: pathlib.Path, run: pathlib.Path) -> dict[str, Any]:
    trace = load_json(run / "episode-trace.json")
    freeze_m15_episode_evidence.schema_validate(trace, load_json(root / TRACE_SCHEMA), "M15 cross-scale trace")
    program = load_json(root / PROGRAM)
    require(trace["program_sha256"] == freeze_m15_episode_evidence.sha256_file(root / PROGRAM), "cross-scale program identity drifted")
    require(trace["program_id"] == program["program_id"] and len(trace["steps"]) == 8, "cross-scale trace program shape drifted")
    require(trace["transitions"] == 4, "cross-scale transition count drifted")
    require(trace["invariants"] == {"all_action_families_executed": False, "save_load_replay_exact": True}, "cross-scale trace invariant drifted")
    require(trace["equivalence_groups"] == [{"captures": 2, "group": "save-load-suffix", "status": "EXACT"}], "cross-scale equivalence group drifted")
    captures = [step for step in trace["steps"] if step["operation"] == "CAPTURE"]
    require(len(captures) == 2, "cross-scale capture count drifted")
    for capture in captures: validate_capture(run / "artifacts", capture)
    exact_fields = ["state_sha256_after", "save_sha256", "observation_sha256", "candidate_sha256", "candidate_semantic_sha256"]
    require(all(captures[0][field] == captures[1][field] for field in exact_fields), "cross-scale save/load continuation differs")
    actions = [step for step in trace["steps"] if step["operation"] == "ACTION"]
    require([step["family"] for step in actions] == ["MANAGE_LOAN", "WAIT", "MANAGE_LOAN", "WAIT"], "cross-scale action suffix drifted")
    require([step["tick_after"] - step["tick_before"] for step in actions] == [0, 16, 0, 16], "cross-scale tick suffix drifted")
    save_step = trace["steps"][0]
    require(freeze_m15_episode_evidence.sha256_file(run / "artifacts/reset-ready.sav") == save_step["save_sha256"], "cross-scale reset checkpoint drifted")
    rss, wall = freeze_m15_episode_evidence.resource_values(run / "resource.txt")
    return {
        "projection_sha256": freeze_m15_episode_evidence.sha256_file(run / "reset-projection.json"),
        "trace_sha256": freeze_m15_episode_evidence.sha256_file(run / "episode-trace.json"),
        "checkpoint_sha256": save_step["save_sha256"], "checkpoint_bytes": save_step["bytes"],
        "state_sha256": captures[0]["state_sha256_after"], "save_sha256": captures[0]["save_sha256"],
        "observation_sha256": captures[0]["observation_sha256"], "candidate_sha256": captures[0]["candidate_sha256"],
        "candidate_semantic_sha256": captures[0]["candidate_semantic_sha256"],
        "maximum_rss_kib": rss, "wall_seconds": wall,
    }


def run_one(root: pathlib.Path, openttd: pathlib.Path, directory: pathlib.Path, manifest: dict[str, Any], sandbox: str) -> dict[str, Any]:
    directory.mkdir(mode=0o700)
    (directory / "artifacts").mkdir(mode=0o700)
    qualify_m15_native_reset.canonical_write_new(directory / "reset-manifest.json", manifest)
    environment = acquire_ai_package.isolated_environment(directory)
    rss: list[int] = []
    stop = threading.Event()
    started = time.monotonic()
    process = subprocess.Popen(command(openttd, root, directory, sandbox), cwd=openttd.parent, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                               preexec_fn=apply_limits, start_new_session=True)
    monitor = threading.Thread(target=qualify_ai_runtime.monitor_rss, args=(process, stop, rss), daemon=True)
    monitor.start()
    try:
        output, _ = process.communicate(timeout=LIMITS["wall_seconds"])
    except subprocess.TimeoutExpired as exc:
        os.killpg(process.pid, signal.SIGKILL); process.wait()
        raise M15CrossScaleReplayError(f"cross-scale process timed out: {directory}") from exc
    finally:
        stop.set(); monitor.join(timeout=1)
    wall = time.monotonic() - started
    (directory / "openttd.log").write_text(output, encoding="utf-8")
    (directory / "resource.txt").write_text(
        f"Elapsed (wall clock) time (h:mm:ss or m:ss): 0:{wall:.6f}\nMaximum resident set size (kbytes): {max(rss, default=0)}\n",
        encoding="utf-8")
    require(process.returncode == 0, f"cross-scale process failed ({process.returncode}): {directory}: {output.strip()}")
    return project_run(root, directory)


def run(root: pathlib.Path, openttd: pathlib.Path, opengfx: pathlib.Path, artifact_root: pathlib.Path, sandbox: str) -> pathlib.Path:
    root, openttd, opengfx, artifact_root = root.resolve(), openttd.resolve(), opengfx.resolve(), artifact_root.resolve()
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "cross-scale artifact root must be a new path")
    freeze_m15_episode_evidence.schema_validate(load_json(root / PROGRAM), load_json(root / PROGRAM_SCHEMA), "M15 cross-scale program")
    artifact_root.mkdir(mode=0o700)
    results: list[dict[str, Any]] = []
    for case_id, width, height, seed, split, tier in CASES:
        manifest = build_manifest(root, openttd, opengfx, width, height, seed, split, tier)
        qualify_m15_native_reset.validate_schema(manifest, root / MANIFEST_SCHEMA, f"M15 replay manifest {case_id}")
        case_root = artifact_root / case_id
        case_root.mkdir(mode=0o700)
        runs = [run_one(root, openttd, case_root / name, manifest, sandbox) for name in RUNS]
        exact = ["projection_sha256", "trace_sha256", "checkpoint_sha256", "state_sha256", "save_sha256", "observation_sha256", "candidate_sha256", "candidate_semantic_sha256"]
        require(all(runs[0][field] == runs[1][field] for field in exact), f"twin-process replay differs: {case_id}")
        results.append({"case_id": case_id, "width": width, "height": height, "seed": seed, "split": split, "tier": tier, "runs": runs, "twin_process_exact": True, "save_load_exact": True})
        print(f"V2_M15_REPLAY_CASE=PASS case={case_id} rss_kib={max(item['maximum_rss_kib'] for item in runs)} wall_seconds={max(item['wall_seconds'] for item in runs):.3f}", flush=True)
    output = artifact_root / "matrix-run.json"
    qualify_m15_native_reset.canonical_write_new(output, {
        "schema_version": "openttd-rl-v2-m15-cross-scale-replay-run-1", "outcome": "PASS",
        "contract_sha256": freeze_m15_episode_evidence.sha256_file(root / CONTRACT),
        "program_sha256": freeze_m15_episode_evidence.sha256_file(root / PROGRAM), "cases": results,
    })
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
        output = run(args.root, args.openttd, args.opengfx, args.artifact_root, args.sandbox)
        print(f"V2_M15_CROSS_SCALE_REPLAY=PASS summary={output}")
        return 0
    except (M15CrossScaleReplayError, freeze_m15_episode_evidence.M15EpisodeEvidenceError, qualify_m15_native_reset.M15NativeResetError, OSError, json.JSONDecodeError) as exc:
        print(f"V2_M15_CROSS_SCALE_REPLAY=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
