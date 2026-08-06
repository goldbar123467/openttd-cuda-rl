#!/usr/bin/env python3
"""Validate the frozen scenario-specific ShipAI qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from typing import Any

import jsonschema

import acquire_ai_package
from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    LiveInputManifest,
    RoleRequirement,
    add_artifact_root_argument,
)
import qualify_ai_runtime


CONFIG = pathlib.Path("config/v2/m18-shipai-evidence.json")
SCHEMA = pathlib.Path("docs/project/schema/v2-m18-shipai-evidence.schema.json")
PACKAGE_INDEX = pathlib.Path("config/v2/opponent-package-evidence.json")
RUNTIME_INDEX = pathlib.Path("config/v2/opponent-runtime-evidence.json")
SHIP_EVIDENCE = pathlib.Path("config/v2/m18-ship-evidence.json")
LIVE_CONSUMER = "m18-shipai-evidence"
PACKAGE_LOGICAL_SET = "v2-m14-ai-shipai-a"
SCENARIO_LOGICAL_SET = "v2-m18-shipai-scenario-c"
RUNTIME_LOGICAL_SET = "v2-m18-shipai-runtime-b"
SCENARIO_SHA256 = "ab70906c5d4ff06bffca38186ea53d3672f2d60634b1dbc5b74b31b6ff2d3484"
SCENARIO_BYTES = 11_292


class M18ShipAIError(ValueError):
    """The M18 ShipAI evidence is inconsistent."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M18ShipAIError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _recorded_file_requirement(
    record: dict[str, Any],
    *,
    logical_set: str,
    relative_path: str,
) -> ArtifactRequirement:
    recorded = record["path"]
    path = pathlib.PurePosixPath(recorded)
    require(
        isinstance(recorded, str)
        and recorded.startswith("/")
        and not recorded.startswith("//")
        and str(path) == recorded
        and all(part not in {"", ".", ".."} for part in path.parts[1:]),
        f"ShipAI {logical_set} recorded path is not an absolute normalized POSIX path",
    )
    require(
        path.parent.name == logical_set and path.name == relative_path,
        f"ShipAI {logical_set} recorded path drifted",
    )
    return ArtifactRequirement(
        logical_set,
        relative_path,
        "file",
        LIVE_CONSUMER,
        record["sha256"],
    )


def _requirements(
    evidence: dict[str, Any],
    package_record: dict[str, Any],
) -> tuple[ArtifactRequirement, ...]:
    require(package_record["artifact_dir"] == PACKAGE_LOGICAL_SET, "M14 ShipAI package logical set drifted")
    require(package_record["evidence_file"] == acquire_ai_package.LOCK_NAME, "M14 ShipAI package lock path drifted")
    return (
        ArtifactRequirement(
            PACKAGE_LOGICAL_SET,
            acquire_ai_package.LOCK_NAME,
            "file",
            LIVE_CONSUMER,
            package_record["evidence_sha256"],
        ),
        _recorded_file_requirement(
            evidence["scenario"],
            logical_set=SCENARIO_LOGICAL_SET,
            relative_path="report.json.sav",
        ),
        _recorded_file_requirement(
            evidence["qualification_manifest"],
            logical_set=RUNTIME_LOGICAL_SET,
            relative_path=qualify_ai_runtime.MANIFEST_NAME,
        ),
    )


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    evidence = load(root / CONFIG)
    package_index = load(root / PACKAGE_INDEX)
    package_records = [item for item in package_index["results"] if item["name"] == "ShipAI"]
    require(len(package_records) == 1, "M14 ShipAI package index cardinality drifted")
    return _requirements(evidence, package_records[0])


def _role_requirements(package_index: dict[str, Any]) -> tuple[RoleRequirement, ...]:
    return (
        RoleRequirement(
            "m14-openttd-executable",
            ".",
            "file",
            LIVE_CONSUMER,
            package_index["executable"]["sha256"],
        ),
    )


def required_live_roles(root: pathlib.Path) -> tuple[RoleRequirement, ...]:
    root = root.resolve()
    return _role_requirements(load(root / PACKAGE_INDEX))


def _adjacent_relative_path(evidence_file: str, relative: str) -> str:
    return (pathlib.PurePosixPath(evidence_file).parent / relative).as_posix()


def _retained_packages(lock: dict[str, Any], label: str) -> list[dict[str, Any]]:
    packages = lock.get("packages")
    require(isinstance(packages, list) and bool(packages), f"{label} packages must be a nonempty list")
    for index, package in enumerate(packages):
        require(isinstance(package, dict), f"{label} packages[{index}] must be an object")
        require(isinstance(package.get("archive_path"), str) and bool(package["archive_path"]), f"{label} packages[{index}].archive_path must be nonempty")
        digest = package.get("archive_sha256")
        require(isinstance(digest, str) and len(digest) == 64, f"{label} packages[{index}].archive_sha256 must be a SHA-256 digest")
    return packages


def _package_archive_requirements(
    logical_set: str,
    evidence_file: str,
    lock: dict[str, Any],
    label: str,
) -> tuple[ArtifactRequirement, ...]:
    return tuple(
        ArtifactRequirement(
            logical_set,
            _adjacent_relative_path(evidence_file, package["archive_path"]),
            "file",
            LIVE_CONSUMER,
            package["archive_sha256"],
        )
        for package in _retained_packages(lock, label)
    )


def _qualification_inputs(manifest: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    package_lock = manifest.get("package_lock")
    resources = manifest.get("resources")
    observations = manifest.get("observations")
    require(isinstance(package_lock, dict), "ShipAI qualification package_lock must be an object")
    require(isinstance(resources, dict), "ShipAI qualification resources must be an object")
    require(isinstance(observations, dict), "ShipAI qualification observations must be an object")
    save = observations.get("save")
    require(isinstance(save, dict), "ShipAI qualification observations.save must be an object")
    package_lock_sha256 = package_lock.get("sha256")
    transcript_sha256 = resources.get("console_transcript_sha256")
    save_path = save.get("path")
    save_sha256 = save.get("sha256")
    require(
        isinstance(package_lock_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", package_lock_sha256) is not None,
        "ShipAI qualification package_lock.sha256 must be 64 lowercase hexadecimal characters",
    )
    require(
        isinstance(transcript_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", transcript_sha256) is not None,
        "ShipAI qualification resources.console_transcript_sha256 must be 64 lowercase hexadecimal characters",
    )
    require(
        isinstance(save_path, str)
        and bool(save_path)
        and "\\" not in save_path
        and "\x00" not in save_path
        and not save_path.startswith("/")
        and all(part not in {"", ".", ".."} for part in save_path.split("/")),
        "ShipAI qualification observations.save.path must be a safe nonempty relative POSIX path",
    )
    require(
        isinstance(save_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", save_sha256) is not None,
        "ShipAI qualification observations.save.sha256 must be 64 lowercase hexadecimal characters",
    )
    return (
        ArtifactRequirement(
            RUNTIME_LOGICAL_SET,
            qualify_ai_runtime.COPIED_LOCK_NAME,
            "file",
            LIVE_CONSUMER,
            package_lock_sha256,
        ),
        ArtifactRequirement(
            RUNTIME_LOGICAL_SET,
            qualify_ai_runtime.TRANSCRIPT_NAME,
            "file",
            LIVE_CONSUMER,
            transcript_sha256,
        ),
        ArtifactRequirement(
            RUNTIME_LOGICAL_SET,
            save_path,
            "file",
            LIVE_CONSUMER,
            save_sha256,
        ),
    )


def validate(
    root: pathlib.Path,
    config_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_context: ArtifactContext | None = None,
    live_inputs: LiveInputManifest | None = None,
) -> dict[str, Any]:
    context = artifact_context or ArtifactContext.offline()
    repository_evidence = config_path is None
    root = root.resolve()
    evidence = load(config_path or root / CONFIG)
    try:
        jsonschema.Draft202012Validator(load(schema_path or root / SCHEMA)).validate(evidence)
    except jsonschema.ValidationError as exc:
        where = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise M18ShipAIError(f"ShipAI schema failed at {where}: {exc.message}") from exc
    package_index, runtime_index = load(root / PACKAGE_INDEX), load(root / RUNTIME_INDEX)
    package_records = [item for item in package_index["results"] if item["name"] == "ShipAI"]
    runtime_records = [item for item in runtime_index["results"] if item["name"] == "ShipAI"]
    require(len(package_records) == 1 and len(runtime_records) == 1, "M14 ShipAI index cardinality drifted")
    package_record, runtime_record = package_records[0], runtime_records[0]
    requirements = _requirements(evidence, package_record)
    require(runtime_record["outcome"] == evidence["m14"]["outcome"] and
            runtime_record["admission"] == evidence["m14"]["admission"] and
            runtime_record["evidence_sha256"] == evidence["m14"]["evidence_sha256"],
            "M14 ShipAI runtime disposition drifted")
    package = evidence["package"]
    require(
        package["name"] == package_record["name"]
        and package["content_unique_id"] == package_record["content_unique_id"]
        and package["version"] == package_record["version"],
        "M14 ShipAI package projection drifted",
    )
    projected_closure = hashlib.sha256(
        f"{package['content_unique_id']} {package_record['archive_bytes']} {package['archive_sha256']}\n".encode("ascii")
    ).hexdigest()
    require(
        package_record["package_count"] == 1
        and projected_closure == package_record["closure_sha256"],
        "M14 ShipAI package projection drifted",
    )
    if repository_evidence:
        require(
            evidence["scenario"]["bytes"] == SCENARIO_BYTES
            and evidence["scenario"]["sha256"] == SCENARIO_SHA256,
            "ShipAI scenario identity drifted",
        )
    ship_evidence = load(root / SHIP_EVIDENCE)
    require(
        evidence["qualification_manifest"]["sha256"]
        == ship_evidence["baselines"]["qualification_manifest_sha256"],
        "ShipAI qualification_manifest identity drifted",
    )
    observations = evidence["observations"]
    require(
        observations == {
            "minimum_days": 30,
            "ships_before_load": ship_evidence["baselines"]["ships_before_load"],
            "ships_after_load": ship_evidence["baselines"]["ships_after_load"],
            "save_load_restored": True,
        },
        "ShipAI observation projection drifted",
    )
    if not context.is_live:
        return {"ships": observations["ships_after_load"], "days": observations["minimum_days"], "live": False}

    require(live_inputs is not None and live_inputs.is_live, "live-input manifest is required for live ShipAI validation")
    assert live_inputs is not None
    require(live_inputs.artifact_root == context.artifact_root, "live-input manifest and artifact context must share one exact artifact root")
    if repository_evidence:
        requirements = required_live_inputs(root)
        roles = required_live_roles(root)
    else:
        roles = _role_requirements(package_index)
    context.preflight(requirements)
    live_inputs.preflight(roles)
    openttd = live_inputs.resolve(roles[0])
    require(openttd.stat().st_size == package_index["executable"]["size"], "M14 ShipAI executable size drifted")
    direct = {(item.logical_set, item.relative_path): context.resolve(item) for item in requirements}
    lock_path = direct[(PACKAGE_LOGICAL_SET, acquire_ai_package.LOCK_NAME)]
    scenario_path = direct[(SCENARIO_LOGICAL_SET, "report.json.sav")]
    manifest_path = direct[(RUNTIME_LOGICAL_SET, qualify_ai_runtime.MANIFEST_NAME)]
    lock = load(lock_path)
    retained_manifest = load(manifest_path)
    package_archives = _package_archive_requirements(
        PACKAGE_LOGICAL_SET,
        acquire_ai_package.LOCK_NAME,
        lock,
        "M14 ShipAI package lock",
    )
    qualification_inputs = _qualification_inputs(retained_manifest)
    context.preflight((*package_archives, *qualification_inputs))
    copied_lock_requirement = qualification_inputs[0]
    copied_lock = load(context.resolve(copied_lock_requirement))
    runtime_archives = _package_archive_requirements(
        RUNTIME_LOGICAL_SET,
        qualify_ai_runtime.COPIED_LOCK_NAME,
        copied_lock,
        "ShipAI qualification package lock",
    )
    context.preflight(runtime_archives)

    require(sha256(lock_path) == package_record["evidence_sha256"], "M14 ShipAI package lock identity drifted")
    require(len(lock["packages"]) == 1 and lock["request"] == {
        "catalog_url": "https://bananas.openttd.org/package/ai/53484950", "content_unique_id": "53484950",
        "name": "ShipAI", "version": 10}, "M14 ShipAI package request drifted")
    validated_lock = acquire_ai_package.validate_lock(root, lock_path, openttd=openttd)
    locked_package = validated_lock["packages"][0]
    require(evidence["package"] == {"name": locked_package["name"], "content_unique_id": locked_package["local_unique_id"],
            "version": locked_package["version"], "archive_sha256": locked_package["archive_sha256"]},
            "M14 ShipAI package projection drifted")
    require(scenario_path.stat().st_size == evidence["scenario"]["bytes"] and sha256(scenario_path) == evidence["scenario"]["sha256"], "ShipAI scenario identity drifted")
    require(manifest_path.stat().st_size == evidence["qualification_manifest"]["bytes"] and sha256(manifest_path) == evidence["qualification_manifest"]["sha256"], "ShipAI qualification_manifest identity drifted")
    manifest = qualify_ai_runtime.validate_manifest(root, manifest_path, openttd=openttd)
    require(manifest == retained_manifest, "ShipAI qualification helper projection drifted")
    require(manifest["outcome"] == "QUALIFIED_ACTIVE" and all(manifest["checks"].values()), "ShipAI runtime qualification is not active and healthy")
    before, after = manifest["observations"]["company_before_load"], manifest["observations"]["company_after_load"]
    require(before["ships"] >= 1 and after["ships"] == before["ships"] and sum(before[k] for k in ("trains", "road_vehicles", "aircraft")) == 0,
            "ShipAI did not retain an all-ship fleet across save/load")
    require(observations == {"minimum_days": manifest["scenario"]["minimum_elapsed_days"], "ships_before_load": before["ships"],
            "ships_after_load": after["ships"], "save_load_restored": True}, "ShipAI observation projection drifted")
    return {"ships": after["ships"], "days": observations["minimum_days"], "live": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    add_artifact_root_argument(parser)
    parser.add_argument("--openttd", type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        artifact_root = args.artifact_root
        if artifact_root is None:
            context = ArtifactContext.offline()
            live_inputs = LiveInputManifest.offline()
        else:
            context = ArtifactContext.live(artifact_root)
            live_inputs = (
                LiveInputManifest.load(artifact_root)
                if args.openttd is None
                else LiveInputManifest.bind(
                    context, {"m14-openttd-executable": args.openttd}
                )
            )
        summary = validate(args.root, args.config, args.schema, artifact_context=context, live_inputs=live_inputs)
        print(f"V2_M18_SHIPAI=PASS ships={summary['ships']} days={summary['days']} save_load=true live={str(summary['live']).lower()}")
        return 0
    except (M18ShipAIError, acquire_ai_package.AIPackageError, qualify_ai_runtime.AIRuntimeError, ArtifactContextError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"V2_M18_SHIPAI=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
