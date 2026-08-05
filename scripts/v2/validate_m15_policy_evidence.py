#!/usr/bin/env python3
"""Validate retained native CPU/CUDA scalable-policy and checkpoint evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    add_artifact_root_argument,
)

CONFIG = pathlib.Path("config/v2/m15-policy-evidence.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m15-policy-evidence.schema.json")
LOGICAL_ARTIFACT_SET = "v2-m15-policy-a"
LIVE_CONSUMER = "m15-policy-evidence"


class M15PolicyEvidenceError(ValueError):
    """The native policy evidence is inconsistent."""


@dataclass(frozen=True)
class M15PolicyEvidenceSummary:
    files: int
    devices: int
    parameters: int
    live_source: bool
    live_artifact: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M15PolicyEvidenceError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise M15PolicyEvidenceError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise M15PolicyEvidenceError(f"cannot hash {path}: {exc}") from exc


def git(repository: pathlib.Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(repository), *arguments], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    require(result.returncode == 0, f"git {' '.join(arguments)} failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def validate_checkpoint(path: pathlib.Path, expected_id: str, contract_sha: str) -> None:
    require(path.is_dir() and not path.is_symlink(), "policy checkpoint directory is missing or a symlink")
    expected_files = ["COMMITTED", "checkpoint.manifest", "model.pt", "optimizer.pt", "runtime.pt", "state.bin"]
    actual = sorted(item.name for item in path.iterdir())
    require(actual == expected_files, "policy checkpoint file inventory drifted")
    lines = (path / "checkpoint.manifest").read_text(encoding="utf-8").splitlines()
    require(len(lines) == 8, "policy checkpoint manifest field count drifted")
    fields = dict(line.split("=", 1) for line in lines)
    require(fields.get("schema") == "v2-m15-scalable-checkpoint-v1", "policy checkpoint schema drifted")
    require(fields.get("contract") == contract_sha, "policy checkpoint contract identity drifted")
    require(fields.get("checkpoint_id") == expected_id == path.name, "policy checkpoint ID drifted")
    require(fields.get("boundary") == "after-completed-ppo-update-before-next-rollout", "policy checkpoint boundary drifted")
    for filename, field in (("model.pt", "model_sha256"), ("optimizer.pt", "optimizer_sha256"), ("runtime.pt", "runtime_sha256"), ("state.bin", "state_sha256")):
        require(sha256_file(path / filename) == fields.get(field), f"policy checkpoint payload drifted: {filename}")
    require((path / "COMMITTED").read_text(encoding="ascii") == expected_id + "\n", "policy checkpoint commit marker drifted")
    require((path / "state.bin").read_bytes().startswith(b"OTRLV2S1"), "policy checkpoint state magic drifted")


def _recorded_artifact_set(config: dict[str, Any]) -> str:
    build_text = config["build"]["artifact_root"]
    source_text = config["source"]["artifact_root"]
    build_root = pathlib.PurePosixPath(build_text)
    source_root = pathlib.PurePosixPath(source_text)
    for value, path, label in (
        (build_text, build_root, "build"),
        (source_text, source_root, "source"),
    ):
        require(
            isinstance(value, str)
            and value.startswith("/")
            and not value.startswith("//")
            and str(path) == value
            and all(part not in {"", ".", ".."} for part in path.parts[1:]),
            f"policy recorded {label} root is not an absolute normalized POSIX path",
        )
    require(build_root.name == LOGICAL_ARTIFACT_SET, "policy logical artifact set drifted")
    require(source_root == build_root / "source", "policy source/build recorded roots diverged")
    return build_root.name


def _requirements(config: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    logical_set = _recorded_artifact_set(config)
    requirements: list[ArtifactRequirement] = [
        ArtifactRequirement(logical_set, ".", "directory", LIVE_CONSUMER),
        ArtifactRequirement(logical_set, "source", "directory", LIVE_CONSUMER),
        ArtifactRequirement(logical_set, "source/.git", "directory", LIVE_CONSUMER),
    ]
    requirements.extend(
        ArtifactRequirement(
            logical_set,
            f"source/{item['path']}",
            "file",
            LIVE_CONSUMER,
            item["sha256"],
        )
        for item in config["source"]["files"]
    )
    executable = config["build"]["executable"]
    requirements.append(ArtifactRequirement(
        logical_set,
        executable["path"],
        "file",
        LIVE_CONSUMER,
        executable["sha256"],
    ))
    for run in config["runs"]:
        directory = run["artifact_directory"]
        checkpoint = f"{directory}/checkpoints/{run['checkpoint_id']}"
        requirements.extend([
            ArtifactRequirement(
                logical_set,
                f"{directory}/policy-report.json",
                "file",
                LIVE_CONSUMER,
                run["report_sha256"],
            ),
            ArtifactRequirement(logical_set, checkpoint, "directory", LIVE_CONSUMER),
            *(
                ArtifactRequirement(
                    logical_set,
                    f"{checkpoint}/{filename}",
                    "file",
                    LIVE_CONSUMER,
                )
                for filename in (
                    "COMMITTED",
                    "checkpoint.manifest",
                    "model.pt",
                    "optimizer.pt",
                    "runtime.pt",
                    "state.bin",
                )
            ),
        ])
    return tuple(requirements)


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    return _requirements(load_json(root / CONFIG))


def validate(
    root: pathlib.Path,
    config_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_context: ArtifactContext | None = None,
) -> M15PolicyEvidenceSummary:
    context = artifact_context or ArtifactContext.offline()
    repository_config = config_path is None
    root = root.resolve()
    config_path, schema_path = config_path or root / CONFIG, schema_path or root / SCHEMA
    config, schema = load_json(config_path), load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(config)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise M15PolicyEvidenceError(f"M15 policy evidence schema failed at {location}: {exc.message}") from exc
    require(config["schema_sha256"] == sha256_file(schema_path), "M15 policy evidence schema SHA-256 mismatch")
    identities = config["identities"]
    require(identities["scalable_contract_sha256"] == sha256_file(root / "config/v2/m15-scalable-contract.json"), "scalable contract identity drifted")
    require(identities["policy_contract_sha256"] == sha256_file(root / "config/v2/m15-policy-contract.json"), "policy contract identity drifted")
    require(identities["dependency_lock_sha256"] == sha256_file(root / "config/v1/dependency-lock.json"), "dependency lock identity drifted")
    paths = [item["path"] for item in config["source"]["files"]]
    require(paths == sorted(paths) and len(paths) == len(set(paths)), "policy source inventory is not sorted and unique")
    for item in config["source"]["files"]:
        require(sha256_file(root / "training/v2" / item["path"]) == item["sha256"], f"repository policy source drifted: {item['path']}")
    require(
        [
            (item["device"], item["artifact_directory"])
            for item in config["runs"]
        ] == [("cpu", "cpu"), ("cuda:0", "cuda")],
        "policy device/artifact directory order drifted",
    )
    parameter_counts = {item["parameter_count"] for item in config["runs"]}
    require(len(parameter_counts) == 1, "policy parameter counts diverged across devices")
    require(config["summary"] == {
        "devices_passed": len(config["runs"]),
        "parameter_count": next(iter(parameter_counts)),
        "recurrent_reset_exact": all(item["reset_max_abs_error"] == 0 for item in config["runs"]),
        "checkpoint_recovery_exact": all(item["checkpoint_max_abs_error"] == 0 for item in config["runs"]),
        "onnx_design_frozen": True,
        "status": "PASS",
    }, "policy evidence summary drifted")
    logical_set = _recorded_artifact_set(config)

    if context.is_live:
        requirements = (
            required_live_inputs(root)
            if repository_config
            else _requirements(config)
        )
        context.preflight(requirements)
        live_paths = {item.relative_path: context.resolve(item) for item in requirements}
        source_artifact = live_paths["source"]
        require(git(source_artifact, "status", "--porcelain") == "", "policy source artifact is dirty")
        require(git(source_artifact, "rev-parse", "HEAD") == config["source"]["commit"], "policy source commit drifted")
        require(git(source_artifact, "rev-parse", "HEAD^{tree}") == config["source"]["tree"], "policy source tree drifted")
        require(git(source_artifact, "ls-files") .splitlines() == paths, "policy source git inventory drifted")
        for item in config["source"]["files"]:
            require(sha256_file(live_paths[f"source/{item['path']}"]) == item["sha256"], f"retained policy source drifted: {item['path']}")

        executable = live_paths[config["build"]["executable"]["path"]]
        require(executable.is_file() and not executable.is_symlink(), "policy gate executable is missing or a symlink")
        require(executable.stat().st_size == config["build"]["executable"]["size"], "policy gate executable size drifted")
        require(sha256_file(executable) == config["build"]["executable"]["sha256"], "policy gate executable SHA-256 drifted")
        for run in config["runs"]:
            directory_name = run["artifact_directory"]
            report_path = live_paths[f"{directory_name}/policy-report.json"]
            require(sha256_file(report_path) == run["report_sha256"], f"policy report drifted: {run['device']}")
            report = load_json(report_path)
            require(report["schema_version"] == "openttd-rl-v2-m15-policy-report-1", "policy report schema drifted")
            require(report["contract_sha256"] == identities["scalable_contract_sha256"], "policy report contract drifted")
            for field in ("device", "parameter_count", "forward_nanoseconds", "reset_max_abs_error", "checkpoint_max_abs_error", "checkpoint_id"):
                require(report[field] == run[field], f"policy report field drifted: {run['device']} {field}")
            require(report["outputs"] == ["family_logits", "candidate_logits", "value", "next_hidden"], "policy output inventory drifted")
            require(set(report["tests"].values()) == {"PASS"} and len(report["tests"]) == 4, "policy native test disposition drifted")
            checkpoint = f"{directory_name}/checkpoints/{run['checkpoint_id']}"
            validate_checkpoint(live_paths[checkpoint], run["checkpoint_id"], identities["scalable_contract_sha256"])
    return M15PolicyEvidenceSummary(len(paths), len(config["runs"]), config["summary"]["parameter_count"], context.is_live, context.is_live)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    add_artifact_root_argument(parser)
    args = parser.parse_args()
    try:
        context = (
            ArtifactContext.offline()
            if args.artifact_root is None
            else ArtifactContext.live(args.artifact_root)
        )
        summary = validate(
            args.root,
            args.config,
            args.schema,
            artifact_context=context,
        )
        print(f"V2_M15_POLICY_EVIDENCE=PASS files={summary.files} devices={summary.devices} parameters={summary.parameters} live_source={str(summary.live_source).lower()} live_artifact={str(summary.live_artifact).lower()}")
        return 0
    except (M15PolicyEvidenceError, ArtifactContextError, OSError, ValueError) as exc:
        print(f"V2_M15_POLICY_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
