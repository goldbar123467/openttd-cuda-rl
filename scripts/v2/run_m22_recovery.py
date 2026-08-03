#!/usr/bin/env python3
"""Run the frozen M22 update-16 fresh-process exact-recovery campaign."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import pathlib
import re
import resource
import shutil
import subprocess
import sys
import time
from typing import Any

import encode_m22_native_corpus


CONTRACT = pathlib.Path("config/v2/m22-learning-contract.json")
CORPUS = pathlib.Path("config/v2/m22-native-corpus.json")
FINAL_MANIFEST = pathlib.Path("config/v2/m22-evaluation-manifest.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m22-recovery-evidence.schema.json")
ARCHITECTURES = ("monolithic-generalist-v1", "specialist-router-v1")
INVENTORY = ("COMMITTED", "m22.manifest", "model.pt", "optimizer.pt", "runtime.pt", "selection.json", "trainer-state.bin")
TRACE_FIELDS = (
    "actions_sha256", "case_order_sha256", "hidden_state_sha256",
    "log_probabilities_sha256", "rewards_sha256", "values_sha256",
)
EQUIVALENCE_FIELDS = (
    "parameters", "optimizer-semantic-tensors", "all-rng-streams", "curriculum", "case-order",
    "actions", "log-probabilities", "values", "rewards", "metrics", "hidden-state",
    "development-evaluation", "checkpoint-semantic-identity",
)
SOURCE_PATHS = (
    "config/v2/m22-learning-contract.json",
    "config/v2/m22-native-corpus.json",
    "scripts/v2/encode_m22_native_corpus.py",
    "scripts/v2/run_m22_recovery.py",
    "scripts/v2/validate_m22_recovery_evidence.py",
    "training/v2/include/openttd_rl/v2/generalist_policy.h",
    "training/v2/include/openttd_rl/v2/m22_campaign.h",
    "training/v2/include/openttd_rl/v2/m22_checkpoint.h",
    "training/v2/include/openttd_rl/v2/m22_corpus.h",
    "training/v2/include/openttd_rl/v2/m22_trainer.h",
    "training/v2/m22/CMakeLists.txt",
    "training/v2/src/generalist_policy.cpp",
    "training/v2/src/m22_campaign.cpp",
    "training/v2/src/m22_campaign_main.cpp",
    "training/v2/src/m22_checkpoint.cpp",
    "training/v2/src/m22_corpus.cpp",
    "training/v2/src/m22_ppo.cpp",
    "training/v2/src/m22_trainer.cpp",
    "training/v2/src/scalable_policy.cpp",
)
CHECKPOINT_RE = re.compile(r"^M22_CHECKPOINT update=([0-9]+) id=([0-9a-f]{64}) path=(/.+)$")
TERMINAL_RE = re.compile(
    r"^M22_CAMPAIGN=PASS architecture=([^ ]+) seed=([0-9]+) updates=([0-9]+) transitions=([0-9]+)$"
)


class M22RecoveryError(RuntimeError):
    """The production recovery campaign was not exactly reproducible."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22RecoveryError(message)


def reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON number: {value}")


def load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise M22RecoveryError(f"cannot load strict JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def apply_limits() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 << 30, 2 << 30))
    resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
    resource.setrlimit(resource.RLIMIT_NPROC, (512, 512))


def source_identity(root: pathlib.Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=root,
        check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    require(completed.stdout == "", "accepted M22 recovery requires a clean source worktree")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, "repository commit identity is malformed")
    files = []
    for relative in SOURCE_PATHS:
        path = root / relative
        require(path.is_file() and not path.is_symlink(), f"M22 recovery source is missing or symlinked: {relative}")
        files.append({"path": relative, "sha256": sha256(path)})
    return {
        "clean": True,
        "files": files,
        "repository_commit": commit,
        "tree_sha256": sha256_bytes(canonical_bytes(files)),
    }


def inspect_checkpoint(path: pathlib.Path, artifact_root: pathlib.Path, update: int, checkpoint_id: str) -> dict[str, Any]:
    require(path == path.resolve() and path.is_dir() and not path.is_symlink(), "checkpoint path is not an absolute real directory")
    require(path.name == checkpoint_id, "checkpoint directory is not content addressed")
    names = tuple(sorted(item.name for item in path.iterdir()))
    require(names == INVENTORY, "checkpoint exact inventory drifted")
    files = []
    for name in INVENTORY:
        item = path / name
        require(item.is_file() and not item.is_symlink(), f"checkpoint entry is not a regular file: {name}")
        files.append({"bytes": item.stat().st_size, "name": name, "sha256": sha256(item)})
    require((path / "COMMITTED").read_text(encoding="ascii") == checkpoint_id + "\n", "checkpoint commit marker drifted")
    return {
        "files": files,
        "id": checkpoint_id,
        "path": path.relative_to(artifact_root).as_posix(),
        "update": update,
    }


def parse_update(line: str) -> dict[str, Any]:
    try:
        value = json.loads(line, parse_constant=reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise M22RecoveryError(f"M22 update JSON is malformed: {exc}") from exc
    require(isinstance(value, dict), "M22 update JSON is not an object")
    trace = value.get("trace")
    require(isinstance(trace, dict) and tuple(sorted(trace)) == TRACE_FIELDS, "M22 recovery trace field inventory drifted")
    require(all(isinstance(trace[field], str) and re.fullmatch(r"[0-9a-f]{64}", trace[field]) for field in TRACE_FIELDS),
            "M22 recovery trace digest is malformed")
    require(all(math.isfinite(item) for item in value.values() if isinstance(item, float)), "M22 update contains a nonfinite metric")
    retention = value.get("retention")
    if isinstance(retention, dict):
        require(all(math.isfinite(item) for item in retention.values() if isinstance(item, float)),
                "M22 retention contains a nonfinite metric")
    return value


def parse_output(
    stdout: str,
    architecture: str,
    seed: int,
    start_update: int,
    update_count: int,
    checkpoint_root: pathlib.Path,
    artifact_root: pathlib.Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    terminal: dict[str, Any] | None = None
    for line in stdout.splitlines():
        require(line != "", "M22 campaign emitted an empty output line")
        if line.startswith("M22_UPDATE "):
            updates.append(parse_update(line.removeprefix("M22_UPDATE ")))
            continue
        matched = CHECKPOINT_RE.fullmatch(line)
        if matched:
            update, checkpoint_id, raw_path = int(matched.group(1)), matched.group(2), pathlib.Path(matched.group(3))
            expected = checkpoint_root / checkpoint_id
            require(raw_path == expected, "M22 campaign reported a checkpoint outside its assigned root")
            checkpoints.append(inspect_checkpoint(raw_path, artifact_root, update, checkpoint_id))
            continue
        matched = TERMINAL_RE.fullmatch(line)
        if matched:
            require(terminal is None, "M22 campaign emitted multiple terminal records")
            terminal = {
                "architecture": matched.group(1), "seed": int(matched.group(2)),
                "transitions": int(matched.group(4)), "updates": int(matched.group(3)),
            }
            continue
        raise M22RecoveryError(f"unexpected M22 campaign output: {line[:240]}")
    expected_updates = list(range(start_update + 1, start_update + update_count + 1))
    require([item.get("update") for item in updates] == expected_updates, "M22 update sequence is discontinuous")
    for item in updates:
        require(item.get("transitions") == item["update"] * 128, "M22 transition counter drifted")
        retention_expected = item["update"] % 4 == 0
        require(item.get("retention_ran") is retention_expected and ("retention" in item) is retention_expected,
                "M22 retention cadence drifted")
    expected_checkpoints = [value for value in expected_updates if value % 8 == 0]
    require([item["update"] for item in checkpoints] == expected_checkpoints, "M22 checkpoint cadence drifted")
    require(terminal == {"architecture": architecture, "seed": seed,
                         "transitions": expected_updates[-1] * 128, "updates": expected_updates[-1]},
            "M22 terminal campaign projection drifted")
    return updates, checkpoints, terminal


def sandbox_command(
    bwrap: pathlib.Path,
    root: pathlib.Path,
    artifact_root: pathlib.Path,
    executable: pathlib.Path,
    corpus: pathlib.Path,
    checkpoint_root: pathlib.Path,
    architecture: str,
    seed: int,
    update_count: int,
    resume: pathlib.Path | None,
) -> list[str]:
    child = [
        str(executable), "--corpus", str(corpus), "--device", "cuda:0",
        "--additional-updates", str(update_count), "--checkpoint-root", str(checkpoint_root),
    ]
    if resume is None:
        child += ["--architecture", architecture, "--seed", str(seed)]
    else:
        child += ["--resume", str(resume)]
    return [
        str(bwrap), "--die-with-parent", "--new-session", "--unshare-net",
        "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev", "--proc", "/proc",
        "--tmpfs", "/tmp", "--bind", str(artifact_root), str(artifact_root),
        "--ro-bind", str(executable), str(executable), "--ro-bind", str(corpus), str(corpus),
        "--ro-bind", "/dev/null", str(root / FINAL_MANIFEST), "--chdir", str(root),
        "--clearenv", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp",
        "--setenv", "TMPDIR", "/tmp", "--setenv", "LANG", "C.UTF-8", "--setenv", "TZ", "UTC",
        "--setenv", "CUDA_VISIBLE_DEVICES", "0", "--setenv", "CUDA_CACHE_DISABLE", "1",
        "--setenv", "CUBLAS_WORKSPACE_CONFIG", ":4096:8", "--setenv", "OMP_NUM_THREADS", "1",
        "--", *child,
    ]


def run_process(
    name: str,
    command: list[str],
    architecture: str,
    seed: int,
    start_update: int,
    update_count: int,
    checkpoint_root: pathlib.Path,
    artifact_root: pathlib.Path,
) -> dict[str, Any]:
    checkpoint_root.mkdir(parents=True, mode=0o700)
    started = time.monotonic()
    process = subprocess.Popen(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        start_new_session=True, preexec_fn=apply_limits,
    )
    try:
        stdout, _unused = process.communicate(timeout=1800)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, 9)
        stdout, _unused = process.communicate()
        raise M22RecoveryError(f"M22 {name} process exceeded the 1,800-second timeout: {stdout[-1000:]}")
    wall_seconds = round(time.monotonic() - started, 6)
    log_path = checkpoint_root.parent / "campaign.log"
    require(not log_path.exists(), "M22 recovery process log already exists")
    log_path.write_text(stdout, encoding="utf-8")
    require(process.returncode == 0, f"M22 {name} process failed ({process.returncode}): {stdout[-1000:]}")
    updates, checkpoints, terminal = parse_output(
        stdout, architecture, seed, start_update, update_count, checkpoint_root, artifact_root,
    )
    return {
        "checkpoints": checkpoints,
        "exit_code": process.returncode,
        "log_path": log_path.relative_to(artifact_root).as_posix(),
        "name": name,
        "pid": process.pid,
        "stdout_sha256": sha256(log_path),
        "terminal": terminal,
        "updates": updates,
        "updates_sha256": sha256_bytes(canonical_bytes(updates)),
        "wall_seconds": wall_seconds,
    }


def checkpoint(process: dict[str, Any], update: int) -> dict[str, Any]:
    matches = [item for item in process["checkpoints"] if item["update"] == update]
    require(len(matches) == 1, f"process does not contain exactly one checkpoint at update {update}")
    return matches[0]


def compare_run(architecture: str, uninterrupted: dict[str, Any], prefix: dict[str, Any], resumed: dict[str, Any]) -> dict[str, Any]:
    require(uninterrupted["updates"][:16] == prefix["updates"], f"{architecture} prefix updates differ")
    require(uninterrupted["updates"][16:] == resumed["updates"], f"{architecture} resumed updates differ")
    require(len({uninterrupted["pid"], prefix["pid"], resumed["pid"]}) == 3, f"{architecture} processes were not fresh")
    for update, left_process, right_process in (
        (8, uninterrupted, prefix), (16, uninterrupted, prefix), (24, uninterrupted, resumed),
    ):
        left, right = checkpoint(left_process, update), checkpoint(right_process, update)
        require(left["id"] == right["id"], f"{architecture} checkpoint identity differs at update {update}")
        require(left["files"] == right["files"], f"{architecture} checkpoint inventory differs at update {update}")
    for left, right in zip(uninterrupted["updates"][16:], resumed["updates"]):
        require(left["trace"] == right["trace"], f"{architecture} transition trace differs after recovery")
    return {
        "all_equivalence_fields_exact": True,
        "checkpoint_inventories_exact": True,
        "equivalence_fields": list(EQUIVALENCE_FIELDS),
        "final_checkpoint_id": checkpoint(uninterrupted, 24)["id"],
        "fork_checkpoint_id": checkpoint(uninterrupted, 16)["id"],
        "fresh_processes": True,
        "prefix_updates_exact": True,
        "resumed_updates_exact": True,
        "trace_fields": list(TRACE_FIELDS),
    }


def run(root: pathlib.Path, executable: pathlib.Path, corpus: pathlib.Path,
        artifact_root: pathlib.Path, evidence_path: pathlib.Path) -> dict[str, Any]:
    root, executable, corpus = root.resolve(), executable.resolve(), corpus.resolve()
    artifact_root, evidence_path = artifact_root.resolve(), evidence_path.resolve()
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "M22 recovery artifact root must be new")
    require(not evidence_path.exists() and not evidence_path.is_symlink(), "M22 recovery evidence path must be new")
    require(executable.is_file() and os.access(executable, os.X_OK), "M22 campaign executable is missing or not executable")
    require(corpus.is_file() and not corpus.is_symlink(), "M22 native corpus binary is missing or symlinked")
    bwrap_raw = shutil.which("bwrap")
    require(bwrap_raw is not None, "bubblewrap is required for final-partition and network isolation")
    bwrap = pathlib.Path(bwrap_raw).resolve()
    contract = load(root / CONTRACT)
    corpus_json = load(root / CORPUS)
    decoded = encode_m22_native_corpus.decode(corpus.read_bytes())
    require(decoded.learning_contract_sha256 == sha256(root / CONTRACT) and decoded.corpus_sha256 == sha256(root / CORPUS),
            "M22 native corpus binary identities drifted")
    configuration = {
        "architectures": list(ARCHITECTURES),
        "continue_updates": int(contract["checkpoint"]["recovery_continue_updates"]),
        "device": "cuda:0",
        "fork_update": int(contract["checkpoint"]["recovery_fork_update"]),
        "run_seed": int(contract["seeds"]["trainer_seeds"][0]),
        "total_updates": int(contract["checkpoint"]["recovery_fork_update"] + contract["checkpoint"]["recovery_continue_updates"]),
        "transitions_per_update": int(contract["ppo"]["transitions_per_update"]),
    }
    require(configuration == {
        "architectures": list(ARCHITECTURES), "continue_updates": 8, "device": "cuda:0",
        "fork_update": 16, "run_seed": 1910917137, "total_updates": 24, "transitions_per_update": 128,
    }, "M22 recovery configuration drifted from the frozen contract")
    source = source_identity(root)
    artifact_root.mkdir(parents=True, mode=0o700)
    runs = []
    for architecture in ARCHITECTURES:
        run_root = artifact_root / architecture
        uninterrupted_root = run_root / "uninterrupted" / "checkpoints"
        uninterrupted = run_process(
            "uninterrupted", sandbox_command(bwrap, root, artifact_root, executable, corpus, uninterrupted_root,
                                               architecture, configuration["run_seed"], 24, None),
            architecture, configuration["run_seed"], 0, 24, uninterrupted_root, artifact_root,
        )
        prefix_root = run_root / "prefix" / "checkpoints"
        prefix = run_process(
            "prefix", sandbox_command(bwrap, root, artifact_root, executable, corpus, prefix_root,
                                      architecture, configuration["run_seed"], 16, None),
            architecture, configuration["run_seed"], 0, 16, prefix_root, artifact_root,
        )
        resume_path = prefix_root / checkpoint(prefix, 16)["id"]
        resumed_root = run_root / "resumed" / "checkpoints"
        resumed = run_process(
            "resumed", sandbox_command(bwrap, root, artifact_root, executable, corpus, resumed_root,
                                       architecture, configuration["run_seed"], 8, resume_path),
            architecture, configuration["run_seed"], 16, 8, resumed_root, artifact_root,
        )
        runs.append({
            "architecture": architecture,
            "equivalence": compare_run(architecture, uninterrupted, prefix, resumed),
            "prefix": prefix,
            "resumed": resumed,
            "uninterrupted": uninterrupted,
        })
    report: dict[str, Any] = {
        "configuration": configuration,
        "identity": {
            "bubblewrap_sha256": sha256(bwrap),
            "campaign_executable_sha256": sha256(executable),
            "corpus_binary_sha256": sha256(corpus),
            "learning_contract_sha256": sha256(root / CONTRACT),
            "native_corpus_sha256": sha256(root / CORPUS),
            "recovery_schema_sha256": sha256(root / SCHEMA),
        },
        "isolation": {
            "artifact_root_only_writable": True,
            "bubblewrap": True,
            "final_manifest_accessed": False,
            "final_manifest_binding": "read-only-empty-file",
            "network_namespace": "unshared",
            "root_filesystem": "read-only",
        },
        "runs": runs,
        "schema_version": "openttd-rl-v2-m22-recovery-evidence-1",
        "source": source,
        "status": "PASS",
        "summary": {
            "architectures": len(runs),
            "exact_architectures": sum(item["equivalence"]["all_equivalence_fields_exact"] for item in runs),
            "fresh_processes": len(runs) * 3,
            "maximum_wall_seconds": max(process["wall_seconds"] for item in runs
                                         for process in (item["uninterrupted"], item["prefix"], item["resumed"])),
        },
    }
    report["report_sha256"] = sha256_bytes(canonical_bytes(report))
    import validate_m22_recovery_evidence
    validate_m22_recovery_evidence.validate_value(report, root, artifact_root, executable, corpus)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with evidence_path.open("xb") as output:
        output.write(canonical_bytes(report) + b"\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--executable", type=pathlib.Path, required=True)
    parser.add_argument("--corpus", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--evidence", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.root, args.executable, args.corpus, args.artifact_root, args.evidence)
    except (M22RecoveryError, OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_RECOVERY=FAIL {exc}", file=sys.stderr)
        return 1
    print(f"V2_M22_RECOVERY=PASS architectures={result['summary']['architectures']} "
          f"fresh_processes={result['summary']['fresh_processes']} report={result['report_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
