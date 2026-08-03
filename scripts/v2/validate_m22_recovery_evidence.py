#!/usr/bin/env python3
"""Validate M22 production fresh-process exact-recovery evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import pathlib
import re
import subprocess
import sys
from typing import Any

import jsonschema

import run_m22_recovery as recovery


class M22RecoveryValidationError(ValueError):
    """The M22 exact-recovery evidence is malformed or insufficient."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22RecoveryValidationError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    return recovery.load(path)


def self_hash(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    expected = payload.pop("report_sha256")
    require(isinstance(expected, str), "M22 recovery report self-hash is absent")
    observed = recovery.sha256_bytes(recovery.canonical_bytes(payload))
    require(expected == observed, "M22 recovery report self-hash mismatch")
    return observed


def validate_process(process: dict[str, Any], start: int, count: int, architecture: str, seed: int) -> None:
    expected_updates = list(range(start + 1, start + count + 1))
    require([item["update"] for item in process["updates"]] == expected_updates,
            "M22 recovery process update sequence drifted")
    require(process["updates_sha256"] == recovery.sha256_bytes(recovery.canonical_bytes(process["updates"])),
            "M22 recovery process update digest mismatch")
    require(process["terminal"] == {"architecture": architecture, "seed": seed,
                                    "transitions": expected_updates[-1] * 128, "updates": expected_updates[-1]},
            "M22 recovery process terminal projection drifted")
    require([item["update"] for item in process["checkpoints"]] == [item for item in expected_updates if item % 8 == 0],
            "M22 recovery process checkpoint cadence drifted")
    require(process["exit_code"] == 0 and process["pid"] > 1 and process["wall_seconds"] > 0,
            "M22 recovery process did not complete successfully")
    for item in process["updates"]:
        require(item["transitions"] == item["update"] * 128, "M22 recovery transition counter drifted")
        require(all(math.isfinite(value) for value in item.values() if isinstance(value, float)),
                "M22 recovery update contains a nonfinite metric")
        require(tuple(sorted(item["trace"])) == recovery.TRACE_FIELDS and
                all(re.fullmatch(r"[0-9a-f]{64}", item["trace"][field]) for field in recovery.TRACE_FIELDS),
                "M22 recovery update trace inventory drifted")
        expected_retention = item["update"] % 4 == 0
        require(item["retention_ran"] is expected_retention and ("retention" in item) is expected_retention,
                "M22 recovery retention cadence drifted")
    for item in process["checkpoints"]:
        require(item["path"].endswith("/" + item["id"]) and
                [entry["name"] for entry in item["files"]] == list(recovery.INVENTORY),
                "M22 recovery checkpoint inventory/path drifted")


def validate_artifacts(report: dict[str, Any], artifact_root: pathlib.Path) -> None:
    artifact_root = artifact_root.resolve()
    require(artifact_root.is_dir() and not artifact_root.is_symlink(), "M22 recovery artifact root is unavailable")
    for run in report["runs"]:
        for process in (run["uninterrupted"], run["prefix"], run["resumed"]):
            log = artifact_root / process["log_path"]
            require(log.is_file() and recovery.sha256(log) == process["stdout_sha256"],
                    "M22 recovery process log identity mismatch")
            for checkpoint in process["checkpoints"]:
                path = artifact_root / checkpoint["path"]
                require(path.is_dir() and path.name == checkpoint["id"], "M22 recovery checkpoint artifact is absent")
                observed = [{"bytes": (path / name).stat().st_size, "name": name,
                             "sha256": recovery.sha256(path / name)} for name in recovery.INVENTORY]
                require(observed == checkpoint["files"], "M22 recovery checkpoint artifact identity mismatch")


def committed_bytes(root: pathlib.Path, commit: str, relative: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{relative}"], cwd=root, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout


def committed_source_files(root: pathlib.Path, commit: str) -> list[dict[str, str]]:
    result = []
    for relative in recovery.SOURCE_PATHS:
        result.append({"path": relative, "sha256": hashlib.sha256(committed_bytes(root, commit, relative)).hexdigest()})
    return result


def validate_value(report: dict[str, Any], root: pathlib.Path, artifact_root: pathlib.Path | None = None,
                   executable: pathlib.Path | None = None, corpus: pathlib.Path | None = None) -> None:
    root = root.resolve()
    source = report.get("source")
    require(isinstance(source, dict), "M22 recovery source identity is absent")
    commit = source.get("repository_commit")
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
            "M22 recovery repository commit is malformed")
    contained = subprocess.run(["git", "cat-file", "-e", commit + "^{commit}"], cwd=root,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    require(contained.returncode == 0, "M22 recovery source commit is not retained")
    try:
        schema = json.loads(committed_bytes(root, commit, recovery.SCHEMA.as_posix()))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise M22RecoveryValidationError(f"M22 committed recovery schema is malformed: {exc}") from exc
    jsonschema.Draft202012Validator.check_schema(schema)
    try:
        jsonschema.Draft202012Validator(schema).validate(report)
    except jsonschema.ValidationError as exc:
        location = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M22RecoveryValidationError(f"M22 recovery schema failed at {location}: {exc.message}") from exc
    self_hash(report)
    expected_files = committed_source_files(root, commit)
    require(source["clean"] and source["files"] == expected_files and
            source["tree_sha256"] == recovery.sha256_bytes(recovery.canonical_bytes(expected_files)),
            "M22 recovery source tree identity drifted")
    source_hashes = {item["path"]: item["sha256"] for item in expected_files}
    identity = report["identity"]
    require(identity["learning_contract_sha256"] == source_hashes[recovery.CONTRACT.as_posix()],
            "M22 recovery learning contract identity drifted")
    require(identity["native_corpus_sha256"] == source_hashes[recovery.CORPUS.as_posix()],
            "M22 recovery native corpus identity drifted")
    require(identity["recovery_schema_sha256"] == hashlib.sha256(
                committed_bytes(root, commit, recovery.SCHEMA.as_posix())).hexdigest(),
            "M22 recovery schema identity drifted")
    if executable is not None:
        require(identity["campaign_executable_sha256"] == recovery.sha256(executable.resolve()),
                "M22 recovery campaign executable identity drifted")
        require(identity["corpus_binary_sha256"] == recovery.sha256(corpus.resolve()),
                "M22 recovery corpus binary identity drifted")
        require(executable.resolve().is_file(), "M22 recovery executable is unavailable")
    require(report["configuration"] == {
        "architectures": list(recovery.ARCHITECTURES), "continue_updates": 8, "device": "cuda:0",
        "fork_update": 16, "run_seed": 1910917137, "total_updates": 24, "transitions_per_update": 128,
    }, "M22 recovery configuration drifted")
    require(report["isolation"] == {
        "artifact_root_only_writable": True, "bubblewrap": True, "final_manifest_accessed": False,
        "final_manifest_binding": "read-only-empty-file", "network_namespace": "unshared",
        "root_filesystem": "read-only",
    }, "M22 recovery isolation claim drifted")
    require([item["architecture"] for item in report["runs"]] == list(recovery.ARCHITECTURES),
            "M22 recovery architecture inventory drifted")
    for run in report["runs"]:
        architecture = run["architecture"]
        validate_process(run["uninterrupted"], 0, 24, architecture, 1910917137)
        validate_process(run["prefix"], 0, 16, architecture, 1910917137)
        validate_process(run["resumed"], 16, 8, architecture, 1910917137)
        require(len({run[name]["pid"] for name in ("uninterrupted", "prefix", "resumed")}) == 3,
                "M22 recovery process identity was reused")
        require(run["uninterrupted"]["updates"][:16] == run["prefix"]["updates"] and
                run["uninterrupted"]["updates"][16:] == run["resumed"]["updates"],
                "M22 interrupted and uninterrupted updates differ")
        equivalence = run["equivalence"]
        require(equivalence["equivalence_fields"] == list(recovery.EQUIVALENCE_FIELDS) and
                equivalence["trace_fields"] == list(recovery.TRACE_FIELDS) and
                all(equivalence[field] is True for field in (
                    "all_equivalence_fields_exact", "checkpoint_inventories_exact", "fresh_processes",
                    "prefix_updates_exact", "resumed_updates_exact",
                )), "M22 recovery equivalence projection drifted")
        for update, left_name, right_name in ((8, "uninterrupted", "prefix"),
                                               (16, "uninterrupted", "prefix"),
                                               (24, "uninterrupted", "resumed")):
            left = recovery.checkpoint(run[left_name], update)
            right = recovery.checkpoint(run[right_name], update)
            require(left["id"] == right["id"] and left["files"] == right["files"],
                    "M22 recovery checkpoint equivalence drifted")
        require(equivalence["fork_checkpoint_id"] == recovery.checkpoint(run["uninterrupted"], 16)["id"] and
                equivalence["final_checkpoint_id"] == recovery.checkpoint(run["uninterrupted"], 24)["id"],
                "M22 recovery checkpoint summary identity drifted")
    summary = report["summary"]
    walls = [process["wall_seconds"] for run in report["runs"]
             for process in (run["uninterrupted"], run["prefix"], run["resumed"])]
    require(summary == {"architectures": 2, "exact_architectures": 2, "fresh_processes": 6,
                        "maximum_wall_seconds": max(walls)}, "M22 recovery summary drifted")
    if artifact_root is not None:
        validate_artifacts(report, artifact_root)


def validate(report_path: pathlib.Path, root: pathlib.Path, artifact_root: pathlib.Path | None = None,
             executable: pathlib.Path | None = None, corpus: pathlib.Path | None = None) -> None:
    report_path = report_path.resolve()
    report = load(report_path)
    require(report_path.read_bytes() == recovery.canonical_bytes(report) + b"\n", "M22 recovery evidence is not canonical JSON")
    validate_value(report, root, artifact_root, executable, corpus)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path)
    parser.add_argument("--executable", type=pathlib.Path)
    parser.add_argument("--corpus", type=pathlib.Path)
    args = parser.parse_args()
    try:
        if (args.executable is None) != (args.corpus is None):
            raise M22RecoveryValidationError("--executable and --corpus must be provided together")
        validate(args.report, args.root, args.artifact_root, args.executable, args.corpus)
        report = load(args.report)
    except (M22RecoveryValidationError, recovery.M22RecoveryError, OSError, jsonschema.ValidationError,
            subprocess.SubprocessError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_RECOVERY_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1
    print(f"V2_M22_RECOVERY_EVIDENCE=PASS architectures={report['summary']['architectures']} "
          f"fresh_processes={report['summary']['fresh_processes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
