#!/usr/bin/env python3
"""Local C++ PPO development: discover the host, build, test, and smoke train.

No release evidence is changed. Run with the Python environment supplying Torch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOME = Path.home() / ".local/share/openttd-rl"


def positive(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return result


def source_identity() -> dict:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()
    # Include untracked implementation files as well as tracked modifications.
    files = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    ).split(b"\0")
    digest = hashlib.sha256()
    for name in sorted(set(files) - {b""}):
        path = ROOT / os.fsdecode(name)
        if path.is_file():
            digest.update(name + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return {"commit": git("rev-parse", "HEAD"), "status": git("status", "--porcelain"),
            "working_files_sha256": digest.hexdigest()}


def host() -> dict:
    import torch
    cuda = torch.cuda.is_available()
    return {"python": sys.version, "python_executable": sys.executable,
            "platform": platform.platform(), "torch": torch.__version__,
            "torch_cuda": torch.version.cuda, "cuda_available": cuda,
            "gpu": torch.cuda.get_device_name(0) if cuda else None,
            "compute_capability": list(torch.cuda.get_device_capability(0)) if cuda else None,
            "torch_architectures": torch.cuda.get_arch_list() if cuda else [],
            "cmake_prefix": torch.utils.cmake_prefix_path}


def write_json(path: Path, value: dict) -> None:
    # Publish complete metadata or keep the previous version across interruption.
    # Temporary files share the destination filesystem, making replace atomic.
    data = json.dumps(value, indent=2, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="." + path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if sys.platform == "linux":
            descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def capture_source(destination: Path) -> dict:
    """Retain reconstructable development code in addition to its identity hash."""
    destination.mkdir(parents=True, exist_ok=False)
    patch = subprocess.check_output(["git", "diff", "--binary", "HEAD", "--", "."], cwd=ROOT)
    (destination / "working-tree.patch").write_bytes(patch)
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT).split(b"\0")
    selected = sorted(os.fsdecode(name) for name in untracked if name and (
        os.fsdecode(name).startswith(("scripts/dev/", "training/dev/", "tests/dev/", "integration/dev/")) or
        os.fsdecode(name) in {"AGENTS.md", "docs/DEVELOPMENT.md", "docs/PROGRESS.md",
                             "docs/PROGRESS_HISTORY_2026-09-23.md", "docs/CUDA_EXPERIMENT.md"}))
    with tarfile.open(destination / "development-files.tar.gz", "w:gz") as archive:
        for name in selected:
            archive.add(ROOT / name, arcname=name, recursive=False)
    record = {"base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "patch_sha256": hashlib.sha256(patch).hexdigest(), "untracked_files": selected,
              "archive_sha256": hashlib.sha256((destination / "development-files.tar.gz").read_bytes()).hexdigest(),
              "reconstruction": "In an isolated checkout of base_commit, apply working-tree.patch and extract development-files.tar.gz."}
    write_json(destination / "source.json", record)
    return record


def build(args: argparse.Namespace) -> None:
    if sys.platform != "linux":
        raise ValueError("Use Linux or WSL2 for the POSIX trainer service.")
    info = host()
    for tool in ("cmake", "ninja", "c++", "ctest"):
        if not shutil.which(tool):
            raise ValueError(f"Missing build tool: {tool}")
    build_dir = args.build_dir.resolve()
    cache = build_dir / "CMakeCache.txt"
    expected_torch_dir = str(Path(info["cmake_prefix"]) / "Torch")
    if cache.exists():
        for line in cache.read_text().splitlines():
            if line.startswith("Torch_DIR:PATH=") and line.split("=", 1)[1] != expected_torch_dir:
                raise ValueError("This build uses another Torch environment. Choose a new --build-dir.")
    command = ["cmake", "-S", str(ROOT / "training/dev"), "-B", str(build_dir),
               "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
               f"-DRL_DEV_CUDA_TESTS={'ON' if info['cuda_available'] else 'OFF'}",
               f"-DRL_DEV_FUSED_POLICY={'ON' if getattr(args, 'fused_policy', False) else 'OFF'}",
               f"-DRL_DEV_V2_POLICY={'ON' if getattr(args, 'v2_policy', False) else 'OFF'}",
               f"-DCMAKE_PREFIX_PATH={info['cmake_prefix']}",
               f"-DPython3_EXECUTABLE={sys.executable}"]
    if info["torch_cuda"]:
        capability = info["compute_capability"]
        arch = args.cuda_arch or (".".join(map(str, capability)) if capability else None)
        if arch is None:
            raise ValueError("CUDA Torch without a visible GPU needs --cuda-arch (for example 7.5).")
        command += [f"-DTORCH_CUDA_ARCH_LIST={arch}"]
        if getattr(args, "fused_policy", False):
            if not info["cuda_available"] or not re.fullmatch(r"[0-9]+\.[0-9]+", arch):
                raise ValueError("The experimental fused policy requires a visible GPU and one numeric CUDA architecture")
            command += [f"-DCMAKE_CUDA_ARCHITECTURES={arch.replace('.', '')}"]
        else:
            command += ["-UCMAKE_CUDA_ARCHITECTURES"]
        if args.cuda_root:
            command += [f"-DCUDAToolkit_ROOT={args.cuda_root.resolve()}",
                        f"-DCUDA_TOOLKIT_ROOT_DIR={args.cuda_root.resolve()}",
                        f"-DCMAKE_CUDA_COMPILER={args.cuda_root.resolve() / 'bin/nvcc'}"]
    subprocess.run(command, check=True)
    subprocess.run(["cmake", "--build", str(build_dir), "--parallel", str(args.jobs)], check=True)
    identity = source_identity()
    source_archive = build_dir / "source-archives" / identity["working_files_sha256"]
    if not source_archive.exists():
        capture_source(source_archive)
    write_json(build_dir / "development-build.json",
               {"kind": "development-build", "host": info, "source": identity,
                "source_archive": str(source_archive), "configure": command})
    print(f"Built native PPO: {build_dir}", flush=True)


def smoke(args: argparse.Namespace) -> None:
    info = host()
    if args.device == "cuda:0" and not info["cuda_available"]:
        raise ValueError("CUDA was requested but is unavailable; no CPU fallback was used.")
    build_dir, output = args.build_dir.resolve(), args.output.resolve()
    executable = build_dir / "m08_architecture_smoke"
    if not executable.is_file():
        raise ValueError(f"Build the trainer first: {executable}")
    build_record = build_dir / "development-build.json"
    if not build_record.is_file():
        raise ValueError("Build provenance is missing; run the build command first.")
    output.mkdir(parents=True, exist_ok=False)
    record = {"kind": "synthetic-ppo-smoke", "claim": "PPO learns a fixture; not OpenTTD gameplay",
              "device": args.device, "host": info, "source": source_identity(),
              "build": json.loads(build_record.read_text()),
              "binary_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(), "status": "running"}
    write_json(output / "run.json", record)
    try:
        with (output / "stdout.log").open("w") as log:
            subprocess.run([str(executable), "--device", args.device, "--report", str(output / "learning.json")],
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=args.timeout)
        record["status"] = "passed"
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(output / "run.json", record)
    print((output / "stdout.log").read_text(), end="")
    print(f"Synthetic learning artifacts: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    builder = commands.add_parser("build")
    builder.add_argument("--build-dir", type=Path, default=DEFAULT_HOME / "build/ppo")
    builder.add_argument("--jobs", type=positive, default=2)
    builder.add_argument("--cuda-root", type=Path)
    builder.add_argument("--cuda-arch")
    builder.add_argument("--fused-policy", action="store_true",
                         help="Build the experimental inference-only CUDA distribution kernel; use a separate build directory")
    builder.add_argument("--v2-policy", action="store_true",
                         help="Build the existing scalable V2 policy using the local runtime; use a separate build directory")
    tester = commands.add_parser("test")
    tester.add_argument("--build-dir", type=Path, default=DEFAULT_HOME / "build/ppo")
    runner = commands.add_parser("smoke")
    runner.add_argument("--build-dir", type=Path, default=DEFAULT_HOME / "build/ppo")
    runner.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    runner.add_argument("--output", type=Path, required=True)
    runner.add_argument("--timeout", type=positive, default=300)
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            print(json.dumps(host(), indent=2))
        elif args.command == "build":
            build(args)
        elif args.command == "test":
            subprocess.run(["ctest", "--test-dir", str(args.build_dir.resolve()), "--output-on-failure"], check=True)
        else:
            smoke(args)
    except (ValueError, OSError, ImportError, subprocess.SubprocessError) as exc:
        print(f"Local development failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
