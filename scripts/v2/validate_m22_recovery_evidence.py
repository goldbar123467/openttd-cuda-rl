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
import sys
from typing import Any

import jsonschema

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    LiveInputManifest,
    RoleRequirement,
    add_artifact_root_argument,
)
import run_m22_recovery as recovery
from source_context import SourceContextError, run_git


RECOVERY_V1 = pathlib.Path("config/v2/m22-recovery-evidence.json")
RECOVERY_V2 = pathlib.Path("config/v2/m22-recovery-evidence-v2.json")
LIVE_CONSUMER = "m22-recovery-evidence"
V1_CONTRACT_SHA256 = "0d47417080e1675ba3040a0eef210fd4cc8c7523b832edfa3d282da7134f6b40"
V2_CONTRACT_SHA256 = "f3ae8f89dfb6edf19b910c55f55845279b77ddd7be5adbd1db244984f968b07b"
CHECKPOINT_SCHEMA = "v2-m22-generalist-checkpoint-v1"
CHECKPOINT_BOUNDARY = "after-completed-ppo-update-and-retention-check-before-next-rollout"
CHECKPOINT_MANIFEST_FIELDS = (
    "schema", "contract", "corpus", "architecture", "run_seed", "checkpoint_id",
    "model_sha256", "optimizer_sha256", "runtime_sha256", "trainer_state_sha256",
    "selection_sha256", "boundary",
)
CHECKPOINT_PAYLOADS = (
    ("model_sha256", "model.pt"),
    ("optimizer_sha256", "optimizer.pt"),
    ("runtime_sha256", "runtime.pt"),
    ("trainer_state_sha256", "trainer-state.bin"),
    ("selection_sha256", "selection.json"),
)


class M22RecoveryValidationError(ValueError):
    """The M22 exact-recovery evidence is malformed or insufficient."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M22RecoveryValidationError(message)


def _safe_relative_posix(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not value.startswith("/")
        and "\\" not in value
        and "\x00" not in value
        and all(part not in {"", ".", ".."} for part in value.split("/"))
    )


def _checkpoint_id(fields: dict[str, str]) -> str:
    identity = "\n".join((
        fields["schema"], fields["contract"], fields["corpus"], fields["architecture"],
        fields["run_seed"], fields["model_sha256"], fields["optimizer_sha256"],
        fields["runtime_sha256"], fields["trainer_state_sha256"],
        fields["selection_sha256"], fields["boundary"],
    )) + "\n"
    return recovery.sha256_bytes(identity.encode("ascii"))


def _parse_checkpoint_manifest(
    path: pathlib.Path,
    require_value: Any,
) -> dict[str, str]:
    try:
        data = path.read_bytes()
        text = data.decode("ascii")
    except (OSError, UnicodeError) as exc:
        require_value(False, f"M22 checkpoint manifest is unreadable: {exc}")
        raise AssertionError("unreachable")
    require_value(len(data) <= 8192 and text.endswith("\n") and "\r" not in text,
                  "M22 checkpoint manifest framing drifted")
    lines = text.splitlines()
    require_value(len(lines) == len(CHECKPOINT_MANIFEST_FIELDS),
                  "M22 checkpoint manifest field count drifted")
    pairs = []
    for line in lines:
        require_value("=" in line and not line.startswith("="),
                      "M22 checkpoint manifest is malformed")
        pairs.append(line.split("=", 1))
    require_value(tuple(pair[0] for pair in pairs) == CHECKPOINT_MANIFEST_FIELDS,
                  "M22 checkpoint manifest field order drifted")
    fields = {name: value for name, value in pairs}
    require_value(
        fields["schema"] == CHECKPOINT_SCHEMA and fields["boundary"] == CHECKPOINT_BOUNDARY,
        "M22 checkpoint manifest compatibility drifted",
    )
    for name in ("checkpoint_id", *(field for field, _ in CHECKPOINT_PAYLOADS)):
        require_value(re.fullmatch(r"[0-9a-f]{64}", fields[name]) is not None,
                      f"M22 checkpoint manifest digest is malformed: {name}")
    return fields


def _validate_checkpoint_artifact(
    path: pathlib.Path,
    checkpoint: dict[str, Any],
    architecture: str,
    seed: int,
    contract_sha256: str,
    corpus_sha256: str,
    require_value: Any,
) -> None:
    fields = _parse_checkpoint_manifest(path / "m22.manifest", require_value)
    require_value(
        fields["contract"] == contract_sha256 and fields["corpus"] == corpus_sha256 and
        fields["architecture"] == architecture and fields["run_seed"] == str(seed),
        "M22 checkpoint manifest contract/corpus/run identity drifted",
    )
    checkpoint_id = checkpoint["id"]
    require_value(
        path.name == checkpoint_id == fields["checkpoint_id"] == _checkpoint_id(fields),
        "M22 checkpoint identity is not content addressed",
    )
    try:
        committed = (path / "COMMITTED").read_bytes()
    except OSError as exc:
        require_value(False, f"M22 checkpoint commit marker is unreadable: {exc}")
        raise AssertionError("unreachable")
    require_value(
        committed == checkpoint_id.encode("ascii") + b"\n",
        "M22 checkpoint commit marker drifted",
    )
    records = {item["name"]: item for item in checkpoint["files"]}
    for field, name in CHECKPOINT_PAYLOADS:
        payload = path / name
        try:
            observed = recovery.sha256(payload)
            observed_bytes = payload.stat().st_size
        except OSError as exc:
            require_value(False, f"M22 checkpoint payload is unreadable: {name}: {exc}")
            raise AssertionError("unreachable")
        require_value(
            fields[field] == observed == records[name]["sha256"] and
            observed_bytes == records[name]["bytes"],
            f"M22 checkpoint payload identity drifted: {name}",
        )


def _validate_live_structure(
    live_inputs: LiveInputManifest,
    requirements: tuple[RoleRequirement, ...],
    exact_directories: list[tuple[pathlib.Path, tuple[str, ...], str]],
    require_value: Any,
) -> None:
    for directory, expected, label in exact_directories:
        try:
            entries = list(directory.iterdir())
        except OSError as exc:
            require_value(False, f"{label} is unreadable: {exc}")
            raise AssertionError("unreachable")
        require_value(directory.is_dir() and not directory.is_symlink(),
                      f"{label} is not a real directory")
        require_value(tuple(sorted(item.name for item in entries)) == expected,
                      f"{label} exact inventory drifted")
        require_value(all(item.is_file() and not item.is_symlink() for item in entries),
                      f"{label} contains a non-regular entry")

    identities: dict[tuple[int, int], pathlib.Path] = {}
    for requirement in requirements:
        if requirement.kind != "file":
            continue
        path = live_inputs.resolve(requirement)
        try:
            status = path.stat()
        except OSError as exc:
            require_value(False, f"M22 live input is unreadable after preflight: {path}: {exc}")
            raise AssertionError("unreachable")
        identity = (status.st_dev, status.st_ino)
        previous = identities.get(identity)
        require_value(previous is None, f"M22 physical file alias: {path} aliases {previous}")
        identities[identity] = path


def load(path: pathlib.Path) -> dict[str, Any]:
    return recovery.load(path)


def _requirements(
    report: dict[str, Any],
    *,
    artifact_role: str,
    executable_role: str,
    corpus_role: str,
) -> tuple[RoleRequirement, ...]:
    requirements: list[RoleRequirement] = []
    for run in report["runs"]:
        for process in (run["uninterrupted"], run["prefix"], run["resumed"]):
            requirements.append(RoleRequirement(
                artifact_role,
                process["log_path"],
                "file",
                LIVE_CONSUMER,
                process["stdout_sha256"],
            ))
            for checkpoint in process["checkpoints"]:
                for item in checkpoint["files"]:
                    requirements.append(RoleRequirement(
                        artifact_role,
                        f"{checkpoint['path']}/{item['name']}",
                        "file",
                        LIVE_CONSUMER,
                        item["sha256"],
                    ))
    identity = report["identity"]
    requirements.extend((
        RoleRequirement(
            executable_role, ".", "file", LIVE_CONSUMER,
            identity["campaign_executable_sha256"],
        ),
        RoleRequirement(
            corpus_role, ".", "file", LIVE_CONSUMER,
            identity["corpus_binary_sha256"],
        ),
    ))
    require(len(requirements) == len(set(requirements)),
            "M22 recovery live-input closure contains duplicates")
    return tuple(requirements)


def _live_roles(report: dict[str, Any]) -> tuple[str, str, str]:
    contract_sha256 = report["identity"]["learning_contract_sha256"]
    if contract_sha256 == V1_CONTRACT_SHA256:
        return "recovery-v1-artifacts", "recovery-v1-executable", "recovery-v1-corpus"
    require(contract_sha256 == V2_CONTRACT_SHA256,
            "M22 recovery learning contract does not identify a frozen recovery version")
    return "recovery-v2-artifacts", "v2-campaign-executable", "v2-corpus-binary"


def _requirements_for_report(report: dict[str, Any]) -> tuple[RoleRequirement, ...]:
    artifact_role, executable_role, corpus_role = _live_roles(report)
    return _requirements(
        report,
        artifact_role=artifact_role,
        executable_role=executable_role,
        corpus_role=corpus_role,
    )


def required_live_inputs(
    root: pathlib.Path,
    report_path: pathlib.Path | None = None,
) -> tuple[RoleRequirement, ...]:
    root = root.resolve()
    selected = (report_path or root / RECOVERY_V2).resolve()
    report = load(selected)
    require(selected in {(root / RECOVERY_V1).resolve(), (root / RECOVERY_V2).resolve()},
            "M22 recovery report path does not identify a frozen recovery version")
    return _requirements_for_report(report)


def self_hash(value: dict[str, Any]) -> str:
    payload = copy.deepcopy(value)
    expected = payload.pop("report_sha256")
    require(isinstance(expected, str), "M22 recovery report self-hash is absent")
    observed = recovery.sha256_bytes(recovery.canonical_bytes(payload))
    require(expected == observed, "M22 recovery report self-hash mismatch")
    return observed


def _validate_record_paths(report: dict[str, Any]) -> None:
    log_paths: set[str] = set()
    checkpoint_paths: set[str] = set()
    checkpoint_identities: dict[str, tuple[str, int]] = {}
    for run in report["runs"]:
        architecture = run["architecture"]
        for process_name in ("uninterrupted", "prefix", "resumed"):
            process = run[process_name]
            expected_log = f"{architecture}/{process_name}/campaign.log"
            log_path = process["log_path"]
            require(
                _safe_relative_posix(log_path) and log_path == expected_log and log_path not in log_paths,
                "M22 recovery log path is unsafe, duplicated, or not bound to its process",
            )
            log_paths.add(log_path)
            for checkpoint in process["checkpoints"]:
                checkpoint_id = checkpoint["id"]
                expected_path = f"{architecture}/{process_name}/checkpoints/{checkpoint_id}"
                require(
                    isinstance(checkpoint_id, str) and re.fullmatch(r"[0-9a-f]{64}", checkpoint_id) is not None and
                    _safe_relative_posix(checkpoint["path"]) and checkpoint["path"] == expected_path and
                    [item["name"] for item in checkpoint["files"]] == list(recovery.INVENTORY),
                    "M22 recovery checkpoint inventory/path drifted",
                )
                require(
                    checkpoint["path"] not in checkpoint_paths,
                    "M22 recovery checkpoint path is reused across logical checkpoints",
                )
                checkpoint_paths.add(checkpoint["path"])
                logical_checkpoint = (architecture, checkpoint["update"])
                previous = checkpoint_identities.get(checkpoint_id)
                require(
                    previous is None or previous == logical_checkpoint,
                    "M22 recovery checkpoint identity is reused across logical checkpoints",
                )
                checkpoint_identities[checkpoint_id] = logical_checkpoint


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
        checkpoint_path = item["path"]
        require(isinstance(checkpoint_path, str) and checkpoint_path and
                not checkpoint_path.startswith("/") and "\\" not in checkpoint_path and
                "\x00" not in checkpoint_path and
                all(part not in {"", ".", ".."} for part in checkpoint_path.split("/")) and
                checkpoint_path.endswith("/" + item["id"]) and
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
    try:
        completed = run_git("show", f"{commit}:{relative}", repository=root)
    except SourceContextError as exc:
        raise M22RecoveryValidationError(
            f"M22 historical source is unavailable: {relative}: {exc}"
        ) from exc
    require(completed.returncode == 0,
            f"M22 historical source is unavailable: {relative}")
    return completed.stdout


def committed_source_files(root: pathlib.Path, commit: str) -> list[dict[str, str]]:
    result = []
    for relative in recovery.SOURCE_PATHS:
        result.append({"path": relative, "sha256": hashlib.sha256(committed_bytes(root, commit, relative)).hexdigest()})
    return result


def validate_value(report: dict[str, Any], root: pathlib.Path, artifact_root: pathlib.Path | None = None,
                   executable: pathlib.Path | None = None, corpus: pathlib.Path | None = None, *,
                   artifact_context: ArtifactContext | None = None,
                   live_inputs: LiveInputManifest | None = None) -> None:
    context = artifact_context or ArtifactContext.offline()
    if artifact_context is not None and not context.is_live:
        artifact_root = executable = corpus = None
    root = root.resolve()
    source = report.get("source")
    require(isinstance(source, dict), "M22 recovery source identity is absent")
    commit = source.get("repository_commit")
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
            "M22 recovery repository commit is malformed")
    try:
        contained = run_git("cat-file", "-e", commit + "^{commit}", repository=root)
    except SourceContextError as exc:
        raise M22RecoveryValidationError(f"M22 recovery source commit is unavailable: {exc}") from exc
    require(contained.returncode == 0, "M22 recovery source commit is not retained")
    try:
        schema = json.loads(committed_bytes(root, commit, recovery.SCHEMA.as_posix()))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise M22RecoveryValidationError(f"M22 committed recovery schema is malformed: {exc}") from exc
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as exc:
        raise M22RecoveryValidationError(f"M22 committed recovery schema is invalid: {exc}") from exc
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
    _validate_record_paths(report)
    if context.is_live:
        require(live_inputs is not None and live_inputs.is_live,
                "live-input manifest is required for live M22 recovery validation")
        assert live_inputs is not None
        require(live_inputs.artifact_root == context.artifact_root,
                "live-input manifest and artifact context must share one exact artifact root")
        requirements = _requirements_for_report(report)
        live_inputs.preflight(requirements)
        artifact_role, _, _ = _live_roles(report)
        artifact_root = live_inputs.resolve(RoleRequirement(
            artifact_role, ".", "directory", LIVE_CONSUMER,
        ))
        executable = live_inputs.resolve(requirements[-2])
        corpus = live_inputs.resolve(requirements[-1])
        exact_directories = [
            (artifact_root / checkpoint["path"], recovery.INVENTORY, "M22 recovery checkpoint")
            for run in report["runs"]
            for process in (run["uninterrupted"], run["prefix"], run["resumed"])
            for checkpoint in process["checkpoints"]
        ]
        _validate_live_structure(live_inputs, requirements, exact_directories, require)
        for run in report["runs"]:
            for process in (run["uninterrupted"], run["prefix"], run["resumed"]):
                for checkpoint in process["checkpoints"]:
                    _validate_checkpoint_artifact(
                        artifact_root / checkpoint["path"], checkpoint,
                        run["architecture"], report["configuration"]["run_seed"],
                        identity["learning_contract_sha256"], identity["native_corpus_sha256"], require,
                    )
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
    if context.is_live and artifact_root is not None:
        validate_artifacts(report, artifact_root)
    elif artifact_context is None and artifact_root is not None:
        validate_artifacts(report, artifact_root)


def _validate(
    report_path: pathlib.Path,
    root: pathlib.Path,
    *,
    artifact_context: ArtifactContext | None = None,
    live_inputs: LiveInputManifest | None = None,
) -> dict[str, bool]:
    context = artifact_context or ArtifactContext.offline()
    report_path = report_path.resolve()
    report = load(report_path)
    require(report_path.read_bytes() == recovery.canonical_bytes(report) + b"\n", "M22 recovery evidence is not canonical JSON")
    if live_inputs is None:
        live_inputs = (
            LiveInputManifest.load(context.artifact_root)
            if context.is_live and context.artifact_root is not None
            else LiveInputManifest.offline()
        )
    validate_value(
        report, root,
        artifact_context=context,
        live_inputs=live_inputs,
    )
    return {"live": context.is_live}


def validate(
    report_path: pathlib.Path,
    root: pathlib.Path,
    *,
    artifact_context: ArtifactContext | None = None,
) -> dict[str, bool]:
    return _validate(report_path, root, artifact_context=artifact_context)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--report", type=pathlib.Path, required=True)
    add_artifact_root_argument(parser)
    parser.add_argument("--executable", type=pathlib.Path)
    parser.add_argument("--corpus", type=pathlib.Path)
    args = parser.parse_args(argv)
    if args.artifact_root is None and (args.executable is not None or args.corpus is not None):
        parser.error("unrecognized arguments: --executable/--corpus require --artifact-root")
    try:
        if args.artifact_root is None:
            context = ArtifactContext.offline()
            live_inputs = LiveInputManifest.offline()
        else:
            report = load(args.report)
            artifact_role, executable_role, corpus_role = _live_roles(report)
            context = ArtifactContext.live(pathlib.Path("/"))
            live_inputs = LiveInputManifest.bind(context, {
                artifact_role: args.artifact_root,
                executable_role: args.executable,
                corpus_role: args.corpus,
            })
        summary = _validate(
            args.report, args.root,
            artifact_context=context,
            live_inputs=live_inputs,
        )
        report = load(args.report)
    except (M22RecoveryValidationError, recovery.M22RecoveryError, ArtifactContextError,
            SourceContextError, OSError,
            jsonschema.ValidationError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M22_RECOVERY_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1
    print(f"V2_M22_RECOVERY_EVIDENCE=PASS architectures={report['summary']['architectures']} "
          f"fresh_processes={report['summary']['fresh_processes']} live={str(summary['live']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
