#!/usr/bin/env python3
"""Run the repeatable M15 all-family lifecycle and save/load replay matrix."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import resource
import shutil
import signal
import subprocess
import threading
import time
from typing import Any

import acquire_ai_package
import freeze_m15_episode_evidence
import qualify_ai_runtime
import qualify_m15_native_reset


SEED = 1_110_312_784
CONTRACT = pathlib.Path("config/v2/m15-scalable-contract.json")
EPISODE_SOURCE = pathlib.Path("config/v2/m15-episode-source.json")
NATIVE_SOURCE = pathlib.Path("config/v2/m15-native-source.json")
PROGRAM = pathlib.Path("config/v2/m15-episode-program.json")
MANIFEST_SCHEMA = pathlib.Path("docs/project/schema/v2-m15-reset-manifest.schema.json")
RUN_DIRS = ["run-a", "run-b"]
LIMITS = {"address_space_bytes": 2_147_483_648, "cpu_seconds": 60, "file_bytes": 64 * 1024 * 1024, "wall_seconds": 60}


class M15EpisodeRunError(ValueError):
    """The M15 episode evidence runner failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15EpisodeRunError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def build_manifest(root: pathlib.Path, openttd: pathlib.Path, opengfx: pathlib.Path) -> dict[str, Any]:
    contract = load_json(root / CONTRACT)
    episode_source = load_json(root / EPISODE_SOURCE)
    native_source = load_json(root / NATIVE_SOURCE)
    executable = episode_source["build"]["executable"]
    require(openttd.is_file() and not openttd.is_symlink() and os.access(openttd, os.X_OK), "episode executable is unavailable")
    require(openttd.stat().st_size == executable["size"] and freeze_m15_episode_evidence.sha256_file(openttd) == executable["sha256"], "episode executable identity drifted")
    require(opengfx.is_file() and not opengfx.is_symlink(), "OpenGFX archive is unavailable")
    return {
        "schema_version": "openttd-rl-v2-m15-reset-manifest-1", "contract_sha256": freeze_m15_episode_evidence.sha256_file(root / CONTRACT),
        "engine_source_tree": native_source["base"]["engine_source_tree"], "executable_sha256": executable["sha256"],
        "map_width": 64, "map_height": 64, "map_seed": SEED,
        "simulation_seed": qualify_m15_native_reset.stream_seed("simulation", SEED),
        "candidate_tiebreak_seed": qualify_m15_native_reset.stream_seed("candidate-tiebreak", SEED),
        "split": qualify_m15_native_reset.seed_split(contract, SEED), "climate": "temperate", "start_year": 1950,
        "settings_manifest_sha256": freeze_m15_episode_evidence.sha256_file(root / "config/v2/setting-inventory.json"),
        "content_manifest_sha256": freeze_m15_episode_evidence.sha256_file(opengfx), "generation_mode": "native-seeded",
        "town_target": 2, "industry_target": 256, "company_count": 1, "resource_tier": "curriculum", "v1_adapter": False, "rejection_reason": None,
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
    if sandbox == "test-none":
        return direct
    require(sandbox == "bubblewrap", "unknown episode sandbox")
    bwrap = shutil.which("bwrap")
    require(bwrap is not None, "bubblewrap is required for episode qualification")
    return [bwrap, "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-net",
            "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--bind", str(run), str(run),
            "--chdir", str(openttd.parent), "--", *direct]


def run_one(root: pathlib.Path, openttd: pathlib.Path, artifact_root: pathlib.Path, directory: str, manifest: dict[str, Any], sandbox: str) -> None:
    run = artifact_root / directory
    run.mkdir(mode=0o700)
    (run / "artifacts").mkdir(mode=0o700)
    qualify_m15_native_reset.canonical_write_new(run / "reset-manifest.json", manifest)
    environment = acquire_ai_package.isolated_environment(run)
    rss: list[int] = []
    stop = threading.Event()
    started = time.monotonic()
    process = subprocess.Popen(command(openttd, root, run, sandbox), cwd=openttd.parent, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                               preexec_fn=apply_limits, start_new_session=True)
    monitor = threading.Thread(target=qualify_ai_runtime.monitor_rss, args=(process, stop, rss), daemon=True)
    monitor.start()
    try:
        output, _ = process.communicate(timeout=LIMITS["wall_seconds"])
    except subprocess.TimeoutExpired as exc:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        raise M15EpisodeRunError(f"episode run timed out: {directory}") from exc
    finally:
        stop.set()
        monitor.join(timeout=1)
    wall = time.monotonic() - started
    (run / "openttd.log").write_text(output, encoding="utf-8")
    (run / "resource.txt").write_text(
        f"Elapsed (wall clock) time (h:mm:ss or m:ss): 0:{wall:.6f}\nMaximum resident set size (kbytes): {max(rss, default=0)}\n",
        encoding="utf-8",
    )
    require(process.returncode == 0, f"episode process failed ({process.returncode}): {directory}: {output.strip()}")
    freeze_m15_episode_evidence.project_run(root, artifact_root, directory)


def run(root: pathlib.Path, openttd: pathlib.Path, opengfx: pathlib.Path, artifact_root: pathlib.Path, sandbox: str) -> pathlib.Path:
    root, openttd, opengfx, artifact_root = root.resolve(), openttd.resolve(), opengfx.resolve(), artifact_root.resolve()
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "episode evidence root must be a new path")
    manifest = build_manifest(root, openttd, opengfx)
    qualify_m15_native_reset.validate_schema(manifest, root / MANIFEST_SCHEMA, "M15 episode reset manifest")
    artifact_root.mkdir(mode=0o700)
    for directory in RUN_DIRS:
        run_one(root, openttd, artifact_root, directory, manifest, sandbox)
    trace_hashes = [freeze_m15_episode_evidence.sha256_file(artifact_root / directory / "episode-trace.json") for directory in RUN_DIRS]
    require(trace_hashes[0] == trace_hashes[1], "episode repeat trace differs")
    summary = {"schema_version": "openttd-rl-v2-m15-episode-matrix-run-1", "outcome": "PASS", "runs": RUN_DIRS,
               "program_sha256": freeze_m15_episode_evidence.sha256_file(root / PROGRAM), "trace_sha256": trace_hashes[0]}
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
        output = run(args.root, args.openttd, args.opengfx, args.artifact_root, args.sandbox)
        print(f"V2_M15_EPISODE_MATRIX=PASS summary={output}")
        return 0
    except (M15EpisodeRunError, freeze_m15_episode_evidence.M15EpisodeEvidenceError, qualify_m15_native_reset.M15NativeResetError, OSError, json.JSONDecodeError) as exc:
        print(f"V2_M15_EPISODE_MATRIX=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
