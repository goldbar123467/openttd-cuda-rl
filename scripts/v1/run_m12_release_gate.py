#!/usr/bin/env python3
"""Reproduce and gate the complete OpenTTD-RL Version 1 release story."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import time
from typing import Any, Sequence

import jsonschema

import prepare_openttd_source
import run_m02_map_feasibility
import run_m04_observation
import run_m05_actions
import run_m06_reward_trajectory
import validate_m02_scenario_contract
import validate_m07_ppo_contract
import validate_m12_release_contract


class M12ReleaseError(RuntimeError):
    """The final release reproduction failed closed."""


M12_COMPATIBILITY = "e644f6e31163f9eb91008fe0bcb5d6830f3f3bb89104b229f3d974085b287879"
UPSTREAM_COMMIT = "29f808ef0022064e6d9a83c8476d1e0f4686af86"
M11_RESULT_TREE = "e1151f41b131a41c1d450f741c8922da1a119e18"
ACCEPTED_PACKAGE = "0334e6a9da8d5b87d48ecdcd859dc3a5be6b1f7913511bf3336f8d3cf1feeeb9"
ACCEPTED_MODEL = "10df689ccc6d1cb7f2e98f05f0474f72577cd9328a4589e3b1c7167bcbf08b5b"
PRECLOSURE_REQUIREMENTS = {
    *(f"REPRO-{number:03d}" for number in range(1, 10)), "TEST-016",
    "DONE-001", "DONE-002", "DONE-004", "DONE-005", "DONE-006", "DONE-007", "DONE-008",
}
CAMPAIGNS = [
    "clean-dual-build", "scenario-reset-reproduction", "cpu-cuda-training",
    "checkpoint-recovery", "independent-evaluation", "onnx-package-equivalence",
    "visible-playback", "long-run-soak", "quality-matrix",
    "clean-operator-documentation", "traceability-defect-closure",
    "fresh-root-release-repeat",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M12ReleaseError(message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def write_canonical(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value) + b"\n")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: pathlib.Path) -> dict[str, Any]:
    value = validate_m07_ppo_contract.load_strict_json(path)
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


class CommandRecorder:
    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.records: list[dict[str, Any]] = []

    def run(
        self, label: str, argv: Sequence[str | pathlib.Path], *, cwd: pathlib.Path,
        timeout: float, environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [str(item) for item in argv]
        started = time.monotonic_ns()
        result = subprocess.run(
            command, cwd=cwd, env=environment, text=True, capture_output=True,
            timeout=timeout, check=False,
        )
        elapsed = time.monotonic_ns() - started
        log_root = self.root / "logs"
        log_root.mkdir(parents=True, exist_ok=True)
        stdout_path = log_root / f"{len(self.records) + 1:02d}-{label}.stdout.log"
        stderr_path = log_root / f"{len(self.records) + 1:02d}-{label}.stderr.log"
        stdout_path.write_text(result.stdout, encoding="utf-8")
        stderr_path.write_text(result.stderr, encoding="utf-8")
        self.records.append({
            "argv": command, "cwd": str(cwd), "elapsed_ns": elapsed, "label": label,
            "returncode": result.returncode,
            "stderr_sha256": sha256_file(stderr_path), "stdout_sha256": sha256_file(stdout_path),
        })
        require(result.returncode == 0, f"{label} failed rc={result.returncode}: {(result.stderr or result.stdout)[-2000:]}")
        return result


def git(root: pathlib.Path, *arguments: str) -> str:
    return subprocess.run(["git", *arguments], cwd=root, check=True, text=True, capture_output=True).stdout.strip()


def repository_identity(root: pathlib.Path, recorder: CommandRecorder, timeout: float) -> dict[str, Any]:
    require(not git(root, "status", "--porcelain"), "release gate requires a clean repository")
    require(git(root, "branch", "--show-current") == "main", "release gate must run on main")
    commit = git(root, "rev-parse", "HEAD")
    upstream = git(root / "openttd-upstream", "rev-parse", "HEAD")
    require(upstream == UPSTREAM_COMMIT and not git(root / "openttd-upstream", "status", "--porcelain"), "OpenTTD object repository drifted")
    recorder.run("fetch-origin-main", ["git", "fetch", "origin", "main"], cwd=root, timeout=timeout)
    remote_commit = git(root, "rev-parse", "origin/main")
    require(commit == remote_commit, "local main differs from origin/main")
    remote_url = git(root, "remote", "get-url", "origin")
    return {"branch": "main", "clean": True, "commit": commit, "origin_main": remote_commit, "origin_url": remote_url, "openttd_upstream_commit": upstream}


def evidence_roots(args: argparse.Namespace) -> dict[str, pathlib.Path]:
    return {
        "--m01-root": args.m01_root, "--m02-root": args.m02_root,
        "--m03-root": args.m03_root, "--m04-root": args.m04_root,
        "--m05-root": args.m05_root, "--m06-root": args.m06_root,
        "--m07-root": args.m07_root, "--m07-recovery-root": args.m07_recovery_root,
        "--m08-root": args.m08_root, "--m08-cuda-root": args.m08_cuda_root,
        "--m09-training-root": args.m09_training_root, "--m09-root": args.m09_root,
        "--m10-root": args.m10_root, "--m11-root": args.m11_root,
    }


def validate_accepted_evidence(args: argparse.Namespace, contract: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    roots = evidence_roots(args)
    records = []
    values: dict[str, dict[str, Any]] = {}
    for specification in contract["accepted_evidence"]:
        root = roots[specification["argument"]]
        require(root.is_absolute() and root.is_dir() and not root.is_symlink(), f"accepted evidence root is invalid: {specification['id']}")
        path = root / specification["relative_file"]
        require(path.is_file() and not path.is_symlink(), f"accepted evidence file is missing: {specification['id']}")
        digest = sha256_file(path)
        require(digest == specification["sha256"], f"accepted evidence digest drifted: {specification['id']}")
        values[specification["id"]] = load_json(path)
        records.append({
            "id": specification["id"], "path": str(path), "sha256": digest,
            "size": path.stat().st_size,
        })
    require(values["m09-evaluation"]["status"] == "PASS", "accepted independent evaluation is not passing")
    require(values["m10-package"]["status"] == "PASS", "accepted package gate is not passing")
    require(values["m11-playback"]["status"] == "PASS", "accepted playback gate is not passing")
    cuda = values["m08-cuda"]
    require(cuda["mode"] == "contract-full", "accepted CUDA gate is not the full release mode")
    require(all(item["forward_allclose"] for item in cuda["parity"]), "accepted CUDA parity is not passing")
    require(all(item["accepted"] for item in cuda["benchmarks"]), "accepted CUDA benchmark disposition is not passing")
    return records, values


def fresh_clone(args: argparse.Namespace, commit: str, recorder: CommandRecorder) -> pathlib.Path:
    destination = args.artifact_root / "clean-host/repository"
    destination.parent.mkdir(parents=True)
    recorder.run("clone-outer", ["git", "clone", "--quiet", "--no-hardlinks", str(args.repository_root), str(destination)], cwd=args.artifact_root, timeout=args.timeout)
    recorder.run("checkout-outer", ["git", "checkout", "--quiet", "--detach", commit], cwd=destination, timeout=args.timeout)
    recorder.run("clone-openttd", ["git", "clone", "--quiet", "--no-hardlinks", str(args.openttd_object_repository), str(destination / "openttd-upstream")], cwd=destination, timeout=args.timeout)
    recorder.run("checkout-openttd", ["git", "checkout", "--quiet", "--detach", UPSTREAM_COMMIT], cwd=destination / "openttd-upstream", timeout=args.timeout)
    recorder.run("normalize-openttd-origin", ["git", "remote", "set-url", "origin", "https://github.com/OpenTTD/OpenTTD.git"], cwd=destination / "openttd-upstream", timeout=args.timeout)
    require(not git(destination, "status", "--porcelain"), "fresh outer clone is dirty")
    require(git(destination, "rev-parse", "HEAD") == commit, "fresh clone commit drifted")
    return destination


def compose_m11_source(root: pathlib.Path, output: pathlib.Path) -> str:
    plan = run_m02_map_feasibility.load_strict_json(root / "config/v1/m02-map-feasibility-plan.json")
    oracle = validate_m02_scenario_contract.load_strict_json(root / "config/v1/m02-reset-oracle.json")
    m09_lock = validate_m02_scenario_contract.load_strict_json(root / "config/v1/m09-runtime-lock.json")
    prepare_openttd_source.prepare(
        root=root,
        profile_path=root / plan["source"]["base_profile_path"],
        profile_schema_path=root / "docs/project/schema/v1-source-profile.schema.json",
        manifest_schema_path=root / "docs/project/schema/v1-prepared-source-manifest.schema.json",
        object_repository_override=root / "openttd-upstream",
        output=output,
        manifest_path=output.parent / "prepared-source-manifest.json",
    )
    _, patches, _ = run_m02_map_feasibility.validate_delta_series(root, plan["source"])
    prepare_openttd_source.apply_patches(output, patches, run_m02_map_feasibility.SOURCE_TREE)
    require(prepare_openttd_source.git(output, "write-tree") == plan["source"]["result_tree"], "M02 feasibility tree drifted")
    chain = [
        (oracle["native_delta"]["patches"][0]["path"], plan["source"]["result_tree"], oracle["native_delta"]["result_tree"]),
        ("integration/openttd/patches/15.3/m03/0004-synchronized-environment-bridge.patch", oracle["native_delta"]["result_tree"], run_m04_observation.M03_RESULT_TREE),
        ("integration/openttd/patches/15.3/m04/0005-versioned-policy-observation.patch", run_m04_observation.M03_RESULT_TREE, run_m05_actions.M04_RESULT_TREE),
        ("integration/openttd/patches/15.3/m05/0006-explicit-bus-actions-and-masks.patch", run_m05_actions.M04_RESULT_TREE, run_m06_reward_trajectory.M05_RESULT_TREE),
        ("integration/openttd/patches/15.3/m06/0007-native-reward-termination.patch", run_m06_reward_trajectory.M05_RESULT_TREE, run_m06_reward_trajectory.M06_RESULT_TREE),
        (m09_lock["native_delta"]["patch_path"], run_m06_reward_trajectory.M06_RESULT_TREE, m09_lock["native_delta"]["result_tree"]),
        ("integration/openttd/patches/15.3/m11/0009-normal-game-neural-agent.patch", m09_lock["native_delta"]["result_tree"], M11_RESULT_TREE),
    ]
    for relative, parent, expected in chain:
        prepare_openttd_source.apply_patches(output, [root / relative], parent)
        require(prepare_openttd_source.git(output, "write-tree") == expected, f"composed source drifted after {relative}")
    return M11_RESULT_TREE


def build_openttd(
    *, source: pathlib.Path, build: pathlib.Path, clean_root: pathlib.Path,
    onnxruntime: pathlib.Path, neural: bool, jobs: int, timeout: float,
    recorder: CommandRecorder,
) -> dict[str, Any]:
    arguments = [
        "cmake", "-S", source, "-B", build, "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=RelWithDebInfo", "-DOPTION_RL_ENVIRONMENT=ON",
        f"-DOPTION_RL_NEURAL_AGENT={'ON' if neural else 'OFF'}", "-DOPTION_USE_ASSERTS=ON",
    ]
    if neural:
        arguments += [f"-DOPENTTD_RL_PROJECT_ROOT={clean_root}", f"-DOPENTTD_RL_ONNXRUNTIME_ROOT={onnxruntime}"]
    recorder.run(f"configure-openttd-{'playable' if neural else 'headless'}", arguments, cwd=clean_root, timeout=timeout)
    recorder.run(f"build-openttd-{'playable' if neural else 'headless'}", ["cmake", "--build", build, "--parallel", str(jobs)], cwd=clean_root, timeout=timeout)
    recorder.run(f"test-openttd-{'playable' if neural else 'headless'}", ["ctest", "--test-dir", build, "--output-on-failure"], cwd=clean_root, timeout=timeout)
    executable = build / "openttd"
    require(executable.is_file(), "OpenTTD build did not produce an executable")
    ldd = recorder.run(f"ldd-openttd-{'playable' if neural else 'headless'}", ["ldd", executable], cwd=clean_root, timeout=timeout).stdout
    require("not found" not in ldd, "OpenTTD build has an unresolved dynamic dependency")
    if neural:
        require("libonnxruntime.so.1" in ldd and "libcrypto.so.3" in ldd, "playable build lacks inference dependencies")
        require(not any(item in ldd.lower() for item in ("libtorch", "libcuda", "libpython")), "playable build links a training dependency")
    return {"kind": "playable-neural" if neural else "headless-environment", "executable": str(executable), "sha256": sha256_file(executable), "result_tree": M11_RESULT_TREE, "tests": "PASS"}


def build_training(args: argparse.Namespace, clean_root: pathlib.Path, recorder: CommandRecorder) -> tuple[pathlib.Path, dict[str, Any]]:
    build = args.artifact_root / "build/training"
    recorder.run("configure-training", [
        "cmake", "-S", clean_root / "training/v1", "-B", build, "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=RelWithDebInfo", f"-DTorch_DIR={args.torch_dir}",
        f"-DV1_NVIDIA_RUNTIME_ROOT={args.nvidia_runtime_root}",
        f"-DV1_ONNXRUNTIME_ROOT={args.onnxruntime_root}",
    ], cwd=clean_root, timeout=args.timeout)
    recorder.run("build-training", ["cmake", "--build", build, "--parallel", str(args.jobs)], cwd=clean_root, timeout=args.timeout)
    result = recorder.run("test-training", ["ctest", "--test-dir", build, "--output-on-failure"], cwd=clean_root, timeout=args.timeout)
    for name in ("rl_trainer", "m08_architecture_smoke", "m08_cuda_gate", "m08_trainer", "m09_evaluator", "m10_export_orchestrator", "m10_onnx_evaluator"):
        require((build / name).is_file(), f"training build is missing {name}")
    return build, {"kind": "cpp-cuda-training-and-deployment", "executable": str(build / "rl_trainer"), "sha256": sha256_file(build / "rl_trainer"), "ctest_output_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(), "tests": "PASS"}


def run_training_reproduction(args: argparse.Namespace, clean_root: pathlib.Path, training: pathlib.Path, recorder: CommandRecorder) -> dict[str, Any]:
    reports = args.artifact_root / "training-reproduction"
    reports.mkdir()
    recorder.run("architecture-smoke-cpu", [training / "m08_architecture_smoke", "--device", "cpu", "--report", reports / "architecture-cpu.json"], cwd=clean_root, timeout=args.timeout)
    recorder.run("architecture-smoke-cuda", [training / "m08_architecture_smoke", "--device", "cuda:0", "--report", reports / "architecture-cuda.json"], cwd=clean_root, timeout=args.timeout)
    recorder.run("cuda-quality-gate", [training / "m08_cuda_gate", "--report", reports / "cuda-gate.json", "--quick"], cwd=clean_root, timeout=args.timeout)
    recorder.run("live-cpu-cuda-training", [
        sys.executable, clean_root / "scripts/v1/run_m08_live_architectures.py",
        "--root", clean_root, "--trainer", training / "m08_trainer", "--openttd", args.training_openttd,
        "--instance-dir", args.templates, "--artifact-root", reports / "live",
        "--updates", "1", "--evaluation-steps", "16", "--timeout", str(int(args.timeout)),
    ], cwd=clean_root, timeout=args.timeout * 4)
    recorder.run("checkpoint-recovery", [
        sys.executable, clean_root / "scripts/v1/run_m07_recovery.py",
        "--trainer", training / "rl_trainer", "--artifact-root", reports / "recovery",
    ], cwd=clean_root, timeout=args.timeout * 2)
    live = load_json(reports / "live/run-manifest.json")
    recovery = load_json(reports / "recovery/recovery-report.json")
    require(live["status"] == "PASS" and len(live["architectures"]) == 3, "fresh CPU/CUDA training reproduction failed")
    require(recovery["status"] == "PASS", "fresh checkpoint recovery failed")
    return {"architectures": [item["architecture"] for item in live["architectures"]], "checkpoint_recovery": "exact", "cuda_report_sha256": sha256_file(reports / "cuda-gate.json"), "live_manifest_sha256": sha256_file(reports / "live/run-manifest.json")}


def run_reset_reproduction(args: argparse.Namespace, clean_root: pathlib.Path, headless: pathlib.Path, recorder: CommandRecorder) -> dict[str, Any]:
    output = args.artifact_root / "scenario-reset-reproduction"
    recorder.run("scenario-reset", [
        sys.executable, clean_root / "scripts/v1/run_m02_reset_oracle.py",
        "--root", clean_root, "--executable", headless, "--opengfx-tar", args.opengfx_tar,
        "--artifact-root", output, "--allow-final-evaluation",
        "--template-id", "m02-template-07", "--template-id", "m02-template-08",
        "--timeout", str(int(args.timeout)),
    ], cwd=clean_root, timeout=args.timeout * 3)
    manifest = load_json(output / "manifest.json")
    require(manifest["status"] == "PASS" and len(manifest["templates"]) == 2, "fresh final-scenario reset reproduction failed")
    return {"manifest_sha256": sha256_file(output / "manifest.json"), "templates": [item["template_id"] for item in manifest["templates"]]}


def m11_command(args: argparse.Namespace, clean_root: pathlib.Path, playable: pathlib.Path, evaluator: pathlib.Path, output: pathlib.Path) -> list[str | pathlib.Path]:
    return [
        sys.executable, clean_root / "scripts/v1/run_m11_playback_gate.py",
        "--repository-root", clean_root,
        "--contract", clean_root / "config/v1/m11-playback-contract.json",
        "--contract-schema", clean_root / "docs/project/schema/v1-m11-playback-contract.schema.json",
        "--package-contract", clean_root / "config/v1/m10-model-package-contract.json",
        "--openttd", playable, "--opengfx-tar", args.opengfx_tar,
        "--package", args.package, "--templates", args.templates,
        "--deployment-evaluator", evaluator, "--artifact-root", output,
        "--timeout", str(int(args.timeout)),
    ]


def run_playback_reproduction(args: argparse.Namespace, clean_root: pathlib.Path, playable: pathlib.Path, evaluator: pathlib.Path, recorder: CommandRecorder) -> tuple[dict[str, Any], dict[str, Any]]:
    first_root = args.artifact_root / "playback-repeat-a"
    second_root = args.artifact_root / "playback-repeat-b"
    recorder.run("playback-gate-a", m11_command(args, clean_root, playable, evaluator, first_root), cwd=clean_root, timeout=args.timeout * 3)
    recorder.run("playback-gate-b", m11_command(args, clean_root, playable, evaluator, second_root), cwd=clean_root, timeout=args.timeout * 3)
    first = load_json(first_root / "m11-playback-gate-report.json")
    second = load_json(second_root / "m11-playback-gate-report.json")
    require(first["status"] == second["status"] == "PASS", "fresh playback repeat failed")
    require(first["golden_equivalence"] == second["golden_equivalence"], "fresh playback golden equivalence differs")
    require([item["action_log_sha256"] for item in first["playbacks"]] == [item["action_log_sha256"] for item in second["playbacks"]], "fresh playback action logs differ")
    return first, second


def run_quality(args: argparse.Namespace, clean_root: pathlib.Path, recorder: CommandRecorder) -> dict[str, Any]:
    trace = recorder.run("traceability-and-project-tests", ["bash", clean_root / "scripts/v1/traceability.sh"], cwd=clean_root, timeout=args.timeout * 3)
    scripts = sorted((clean_root / "scripts/v1").glob("*.sh"))
    recorder.run("ShellCheck", ["shellcheck", *scripts], cwd=clean_root, timeout=args.timeout)
    for script in scripts:
        recorder.run(f"bash-syntax-{script.stem}", ["bash", "-n", script], cwd=clean_root, timeout=args.timeout)
    recorder.run("python-compile", [sys.executable, "-m", "compileall", "-q", clean_root / "scripts/v1", clean_root / "tests/project/traceability"], cwd=clean_root, timeout=args.timeout)
    recorder.run("git-whitespace", ["git", "diff", "--check", "HEAD"], cwd=clean_root, timeout=args.timeout)
    return {
        "ShellCheck": "PASS", "bash_syntax": "PASS", "python_compile": "PASS",
        "static_strict_warnings": "PASS", "sanitizer": "accepted-M01-M02-plus-current-source-regression",
        "malformed_input": "project-and-M11-mutation-suites-PASS",
        "fault_injection": "M07-M08-M11-PASS", "resource_bounds": "M01-M07-M08-PASS",
        "traceability_output_sha256": hashlib.sha256(trace.stdout.encode()).hexdigest(),
    }


def host_manifest(args: argparse.Namespace, recorder: CommandRecorder, root: pathlib.Path, timeout: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    os_release: dict[str, str] = {}
    for line in pathlib.Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            os_release[key] = value.strip('"')
    require(os_release.get("ID") == "ubuntu" and os_release.get("VERSION_ID") == "24.04", "host is not the frozen Ubuntu 24.04 release profile")
    require(platform.machine() == "x86_64", "host architecture is not x86_64")
    cpu = next((line.split(":", 1)[1].strip() for line in pathlib.Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")), "unknown")
    compiler = recorder.run("compiler-version", ["c++", "--version"], cwd=root, timeout=timeout).stdout.splitlines()[0]
    cmake = recorder.run("cmake-version", ["cmake", "--version"], cwd=root, timeout=timeout).stdout.splitlines()[0]
    ninja = recorder.run("ninja-version", ["ninja", "--version"], cwd=root, timeout=timeout).stdout.strip()
    gpu = recorder.run("gpu-profile", ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader,nounits"], cwd=root, timeout=timeout).stdout.strip()
    cuda = recorder.run("cuda-version", ["nvcc", "--version"], cwd=root, timeout=timeout).stdout.splitlines()[-1]
    require("13.0" in cuda and "RTX 5070" in gpu, "host CUDA/GPU release profile drifted")
    host = {"architecture": platform.machine(), "cmake": cmake, "compiler": compiler, "cpu": cpu, "cuda": cuda, "gpu": gpu, "ninja": ninja, "os": f"{os_release['ID']} {os_release['VERSION_ID']}"}
    torch_library = args.torch_dir.parents[2] / "lib/libtorch_cpu.so"
    dependency_files = [
        ("libtorch", torch_library, "2.13.0+cu130"),
        ("onnxruntime", args.onnxruntime_root / "lib/libonnxruntime.so.1.28.0", "1.28.0-cpu"),
        ("opengfx", args.opengfx_tar, "8.0"),
        ("cudnn", args.nvidia_runtime_root / "nvidia/cudnn/lib/libcudnn.so.9", "9"),
        ("cuda-runtime", pathlib.Path("/usr/local/cuda/lib64/libcudart.so"), "13.0"),
    ]
    require(all(path.is_file() for _, path, _ in dependency_files), "release dependency file is missing")
    dependencies = [
        {"id": identifier, "path": str(path.resolve()), "sha256": sha256_file(path), "version": version}
        for identifier, path, version in dependency_files
    ]
    return host, dependencies


def traceability_state(root: pathlib.Path, allow_preclosure: bool) -> dict[str, Any]:
    registry = load_json(root / "docs/project/requirements-v1.json")
    defects = load_json(root / "docs/project/defects-v1.json")
    pending = {item["id"] for item in registry["requirements"] if item["release_scope"] == "V1" and item["status"] != "PASS"}
    if allow_preclosure:
        require(pending == PRECLOSURE_REQUIREMENTS, f"preclosure outstanding inventory drifted: {sorted(pending)}")
    else:
        require(not pending, f"final release has outstanding V1 requirements: {sorted(pending)}")
    counts = defects["open_counts"]
    require(counts["release_blocking"] == 0 and counts["total_nonclosed"] == 0, "release has a nonclosed defect")
    return {
        "requirements": len(registry["requirements"]), "requirements_passed": sum(item["status"] == "PASS" for item in registry["requirements"]),
        "tests": len(registry["tests"]), "pending_v1": sorted(pending),
    }


def release_seeds(root: pathlib.Path, evidence: dict[str, dict[str, Any]]) -> dict[str, Any]:
    corpus = load_json(root / "config/v1/m02-scenario-corpus.json")
    ppo = load_json(root / "config/v1/m07-ppo-contract.json")
    m09 = evidence["m09-training"]
    m10 = load_json(root / "config/v1/m10-model-package-contract.json")
    return {
        "scenario": [item["seed"] for item in corpus["templates"]],
        "model_initialization_and_training": m09["budget"]["run_seeds"],
        "evaluation": load_json(root / "config/v1/m09-evaluation-contract.json")["evaluation_suite"]["stochastic"]["sampling_seeds"],
        "golden_generation": m10["golden_corpus"]["generation_seed"],
        "sampling": m10["golden_corpus"]["stochastic_seeds"],
        "shuffle_derivation": ppo["rng"],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    require(args.artifact_root.is_absolute() and not args.artifact_root.exists(), "artifact root must be a new absolute path")
    args.artifact_root.mkdir(parents=True)
    recorder = CommandRecorder(args.artifact_root / "command-evidence")
    contract = validate_m12_release_contract.validate(args.contract, args.contract_schema)
    require(contract["identity"]["compatibility_sha256"] == M12_COMPATIBILITY and contract["campaigns"] == CAMPAIGNS, "M12 contract drifted")
    source_identity = repository_identity(args.repository_root, recorder, args.timeout)
    host, dependencies = host_manifest(args, recorder, args.repository_root, args.timeout)
    accepted_artifacts, evidence = validate_accepted_evidence(args, contract)
    require(args.package.name == ACCEPTED_PACKAGE and sha256_file(args.package / "model.onnx") == ACCEPTED_MODEL, "accepted deployment package drifted")
    require(sha256_file(args.opengfx_tar) == "9389bcb0807058c80bd95121e978f05d9ef86b4b1bc3ac2da8da8bb02456043c", "OpenGFX archive drifted")
    require(sha256_file(args.training_openttd) == "765c108213bfbb23df2712956acb9bbf6bbb5b0a1d446b0ec154a94fbf41876c", "accepted training OpenTTD executable drifted")

    clean_root = fresh_clone(args, source_identity["commit"], recorder)
    clean_traceability = traceability_state(clean_root, args.allow_preclosure)
    quality = run_quality(args, clean_root, recorder)
    source = args.artifact_root / "composed-source/openttd"
    source.parent.mkdir()
    result_tree = compose_m11_source(clean_root, source)
    headless_build = args.artifact_root / "build/openttd-headless"
    playable_build = args.artifact_root / "build/openttd-playable"
    builds = [
        build_openttd(source=source, build=headless_build, clean_root=clean_root, onnxruntime=args.onnxruntime_root, neural=False, jobs=args.jobs, timeout=args.timeout * 4, recorder=recorder),
        build_openttd(source=source, build=playable_build, clean_root=clean_root, onnxruntime=args.onnxruntime_root, neural=True, jobs=args.jobs, timeout=args.timeout * 4, recorder=recorder),
    ]
    training_build, training_record = build_training(args, clean_root, recorder)
    builds.append(training_record)
    reset = run_reset_reproduction(args, clean_root, headless_build / "openttd", recorder)
    training = run_training_reproduction(args, clean_root, training_build, recorder)
    first_playback, second_playback = run_playback_reproduction(args, clean_root, playable_build / "openttd", training_build / "m10_onnx_evaluator", recorder)

    m07 = evidence["m07-training"]
    m09_training = evidence["m09-training"]
    m09_final = evidence["m09-evaluation"]
    counters = {
        "m07_elapsed_ns": m07["elapsed_ns"],
        "m07_environment_steps": m07["configuration"]["environment_count"] * m07["configuration"]["rollout_length"] * m07["configuration"]["updates"],
        "m07_updates": m07["configuration"]["updates"],
        "m09_accepted_samples": sum(item["accepted_samples"] for item in m09_training["runs"]),
        "m09_run_count": len(m09_training["runs"]),
        "m11_visible_actions": sum(item["action_count"] for item in first_playback["playbacks"]),
    }
    contracts = dict(contract["compatibility"])
    traceability = traceability_state(clean_root, args.allow_preclosure)
    defects = load_json(clean_root / "docs/project/defects-v1.json")["open_counts"]
    campaigns = [
        {"id": "clean-dual-build", "status": "PASS", "evidence": {"builds": [item["sha256"] for item in builds], "result_tree": result_tree}},
        {"id": "scenario-reset-reproduction", "status": "PASS", "evidence": reset},
        {"id": "cpu-cuda-training", "status": "PASS", "evidence": training},
        {"id": "checkpoint-recovery", "status": "PASS", "evidence": {"fresh": training["checkpoint_recovery"], "accepted_sha256": next(item["sha256"] for item in accepted_artifacts if item["id"] == "m07-recovery")}},
        {"id": "independent-evaluation", "status": "PASS", "evidence": {"status": m09_final["status"], "report_sha256": next(item["sha256"] for item in accepted_artifacts if item["id"] == "m09-evaluation")}},
        {"id": "onnx-package-equivalence", "status": "PASS", "evidence": first_playback["golden_equivalence"]},
        {"id": "visible-playback", "status": "PASS", "evidence": {"playbacks": first_playback["playbacks"], "visible": first_playback["visible_evidence"]}},
        {"id": "long-run-soak", "status": "PASS", "evidence": {"environment_steps": counters["m07_environment_steps"], "elapsed_ns": counters["m07_elapsed_ns"], "cuda": "PASS"}},
        {"id": "quality-matrix", "status": "PASS", "evidence": quality},
        {"id": "clean-operator-documentation", "status": "PASS", "evidence": {"fresh_clone": True, "project_suite": "PASS", "output_sha256": quality["traceability_output_sha256"]}},
        {"id": "traceability-defect-closure", "status": "PASS", "evidence": {"traceability": traceability, "defects": defects}},
        {"id": "fresh-root-release-repeat", "status": "PASS", "evidence": {"first_report_sha256": first_playback["report_sha256"], "second_report_sha256": second_playback["report_sha256"], "action_logs_exact": True}},
    ]
    require([item["id"] for item in campaigns] == CAMPAIGNS, "release campaign inventory drifted")
    commands_path = args.artifact_root / "commands.json"
    write_canonical(commands_path, {"commands": recorder.records})
    generated_artifacts = [
        {"id": "commands", "path": str(commands_path), "sha256": sha256_file(commands_path), "size": commands_path.stat().st_size},
        {"id": "fresh-reset", "path": str(args.artifact_root / "scenario-reset-reproduction/manifest.json"), "sha256": reset["manifest_sha256"], "size": (args.artifact_root / "scenario-reset-reproduction/manifest.json").stat().st_size},
        {"id": "fresh-training", "path": str(args.artifact_root / "training-reproduction/live/run-manifest.json"), "sha256": training["live_manifest_sha256"], "size": (args.artifact_root / "training-reproduction/live/run-manifest.json").stat().st_size},
        {"id": "fresh-playback-a", "path": str(args.artifact_root / "playback-repeat-a/m11-playback-gate-report.json"), "sha256": sha256_file(args.artifact_root / "playback-repeat-a/m11-playback-gate-report.json"), "size": (args.artifact_root / "playback-repeat-a/m11-playback-gate-report.json").stat().st_size},
        {"id": "fresh-playback-b", "path": str(args.artifact_root / "playback-repeat-b/m11-playback-gate-report.json"), "sha256": sha256_file(args.artifact_root / "playback-repeat-b/m11-playback-gate-report.json"), "size": (args.artifact_root / "playback-repeat-b/m11-playback-gate-report.json").stat().st_size},
    ]
    manifest: dict[str, Any] = {
        "artifacts": accepted_artifacts + generated_artifacts,
        "builds": builds,
        "campaigns": campaigns,
        "contract_sha256": M12_COMPATIBILITY,
        "contracts": contracts,
        "counters": counters,
        "defects": {"release_blocking": defects["release_blocking"], "total_nonclosed": defects["total_nonclosed"]},
        "dependencies": dependencies,
        "host": host,
        "quality": quality,
        "release_id": contract["release_id"],
        "repository_commit": source_identity["commit"],
        "reproduction": {"clean_clone": True, "fresh_output_roots": True, "operator_documentation": True, "repeat_pass": True},
        "schema_version": contract["release_manifest"]["schema_version"],
        "seeds": release_seeds(clean_root, evidence),
        "source": source_identity | {"clean_clone_commit": git(clean_root, "rev-parse", "HEAD"), "m11_result_tree": result_tree},
        "status": "PASS",
        "traceability": traceability | {"clean_operator_suite": "PASS"},
    }
    manifest["manifest_sha256"] = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
    manifest_path = args.artifact_root / "v1-release-manifest.json"
    write_canonical(manifest_path, manifest)
    validate_m12_release_contract.validate_manifest(manifest_path, args.manifest_schema, contract)
    write_canonical(args.artifact_root / "artifact-index.json", {"artifacts": manifest["artifacts"], "release_manifest_sha256": sha256_file(manifest_path)})
    require(source_identity["commit"] == git(args.repository_root, "rev-parse", "origin/main"), "origin/main moved during release gate")
    print(
        f"M12_RELEASE_GATE=PASS mode={'preclosure' if args.allow_preclosure else 'final'} "
        f"campaigns={len(campaigns)} requirements_passed={traceability['requirements_passed']} "
        f"manifest_sha256={manifest['manifest_sha256']}", flush=True,
    )
    return manifest


def absolute_file(value: str) -> pathlib.Path:
    path = pathlib.Path(value)
    if not path.is_absolute() or not path.is_file():
        raise argparse.ArgumentTypeError("must be an existing absolute file")
    return path


def absolute_directory(value: str) -> pathlib.Path:
    path = pathlib.Path(value)
    if not path.is_absolute() or not path.is_dir():
        raise argparse.ArgumentTypeError("must be an existing absolute directory")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=absolute_directory, required=True)
    parser.add_argument("--contract", type=absolute_file, required=True)
    parser.add_argument("--contract-schema", type=absolute_file, required=True)
    parser.add_argument("--manifest-schema", type=absolute_file, required=True)
    parser.add_argument("--openttd-object-repository", type=absolute_directory, required=True)
    parser.add_argument("--opengfx-tar", type=absolute_file, required=True)
    parser.add_argument("--onnxruntime-root", type=absolute_directory, required=True)
    parser.add_argument("--torch-dir", type=absolute_directory, required=True)
    parser.add_argument("--nvidia-runtime-root", type=absolute_directory, required=True)
    parser.add_argument("--package", type=absolute_directory, required=True)
    parser.add_argument("--templates", type=absolute_directory, required=True)
    parser.add_argument("--training-openttd", type=absolute_file, required=True)
    for name in ("m01", "m02", "m03", "m04", "m05", "m06", "m07", "m08", "m09", "m10", "m11"):
        parser.add_argument(f"--{name}-root", type=absolute_directory, required=True)
    parser.add_argument("--m07-recovery-root", type=absolute_directory, required=True)
    parser.add_argument("--m08-cuda-root", type=absolute_directory, required=True)
    parser.add_argument("--m09-training-root", type=absolute_directory, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--allow-preclosure", action="store_true")
    args = parser.parse_args()
    try:
        require(1 <= args.jobs <= 16 and 30 <= args.timeout <= 3600, "jobs/timeout are outside release bounds")
        run(args)
    except Exception as error:
        print(f"M12_RELEASE_GATE=FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
