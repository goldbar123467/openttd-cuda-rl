#!/usr/bin/env python3
"""Validate the M14 package-to-runtime opponent qualification matrix."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Any

import jsonschema

import qualify_ai_runtime
import validate_opponent_package_evidence
from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    LiveInputManifest,
    RoleRequirement,
    add_artifact_root_argument,
)


EVIDENCE_RELATIVE = pathlib.Path("config/v2/opponent-runtime-evidence.json")
LIVE_CONSUMER = "m14-opponent-runtime-evidence"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class OpponentRuntimeEvidenceError(ValueError):
    """The M14 opponent runtime evidence matrix violates an invariant."""


@dataclass(frozen=True)
class RuntimeEvidenceSummary:
    opponents: int
    package_rejected: int
    runtime_rejected: int
    tournament: int
    control: int
    scenario_required: int
    live_artifacts: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OpponentRuntimeEvidenceError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OpponentRuntimeEvidenceError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise OpponentRuntimeEvidenceError(f"cannot hash {path}: {exc}") from exc


def vehicle_projection(company: dict[str, Any] | None) -> dict[str, int] | None:
    if company is None:
        return None
    return {
        "train": company["trains"],
        "road": company["road_vehicles"],
        "air": company["aircraft"],
        "ship": company["ships"],
    }


def elapsed_days(manifest: dict[str, Any]) -> int | None:
    start = manifest["observations"]["start_date"]
    end = manifest["observations"]["post_load_date"]
    if start is None or end is None:
        return None
    return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days


def _requirements(evidence: dict[str, Any]) -> tuple[ArtifactRequirement, ...]:
    return tuple(
        ArtifactRequirement(
            result["artifact_dir"],
            result["evidence_file"],
            "file",
            LIVE_CONSUMER,
            result["evidence_sha256"],
        )
        for result in evidence["results"]
        if result["phase"] != "PACKAGE"
    )


def _complete_requirements(
    evidence: dict[str, Any],
    package_index: dict[str, Any],
) -> tuple[ArtifactRequirement, ...]:
    requirements = list(_requirements(evidence))
    package_by_name = {item["name"]: item for item in package_index["results"]}
    for result in evidence["results"]:
        if result["phase"] == "PACKAGE":
            continue
        requirements.extend((
            ArtifactRequirement(
                result["artifact_dir"], qualify_ai_runtime.COPIED_LOCK_NAME,
                "file", LIVE_CONSUMER,
            ),
            ArtifactRequirement(
                result["artifact_dir"], qualify_ai_runtime.TRANSCRIPT_NAME,
                "file", LIVE_CONSUMER,
            ),
        ))
        if result["save_sha256"] is not None:
            requirements.append(ArtifactRequirement(
                result["artifact_dir"], f"{qualify_ai_runtime.SAVE_BASENAME}.sav",
                "file", LIVE_CONSUMER, result["save_sha256"],
            ))
        package_record = package_by_name[result["name"]]
        archives = validate_opponent_package_evidence.PACKAGE_ARCHIVES.get(result["name"])
        require(
            archives is not None and len(archives) == package_record["package_count"],
            f"{result['name']} committed runtime archive closure drifted",
        )
        requirements.extend(
            ArtifactRequirement(result["artifact_dir"], archive, "file", LIVE_CONSUMER)
            for archive in archives
        )
    return tuple(requirements)


def required_live_inputs(root: pathlib.Path) -> tuple[ArtifactRequirement, ...]:
    root = root.resolve()
    evidence = load_json(root / EVIDENCE_RELATIVE)
    return (
        *validate_opponent_package_evidence.required_live_inputs(root),
        *_complete_requirements(
            evidence,
            load_json(root / validate_opponent_package_evidence.EVIDENCE_RELATIVE),
        ),
    )


def _role_requirements(evidence: dict[str, Any]) -> tuple[RoleRequirement, ...]:
    return (
        RoleRequirement(
            "m14-openttd-executable",
            ".",
            "file",
            LIVE_CONSUMER,
            evidence["executable"]["sha256"],
        ),
    )


def required_live_roles(root: pathlib.Path) -> tuple[RoleRequirement, ...]:
    root = root.resolve()
    return _role_requirements(load_json(root / EVIDENCE_RELATIVE))


def _adjacent_relative_path(evidence_file: str, relative: str) -> str:
    return (pathlib.PurePosixPath(evidence_file).parent / relative).as_posix()


def _retained_manifest_inputs(
    manifest: dict[str, Any],
    name: str,
) -> tuple[str, str, dict[str, Any] | None]:
    prefix = f"{name} retained runtime evidence structure invalid"
    package_lock = manifest.get("package_lock")
    require(isinstance(package_lock, dict), f"{prefix}: package_lock must be an object")
    package_lock_sha256 = package_lock.get("sha256")
    require(
        isinstance(package_lock_sha256, str)
        and SHA256.fullmatch(package_lock_sha256) is not None,
        f"{prefix}: package_lock.sha256 must be a SHA-256 digest",
    )
    resources = manifest.get("resources")
    require(isinstance(resources, dict), f"{prefix}: resources must be an object")
    transcript_sha256 = resources.get("console_transcript_sha256")
    require(
        isinstance(transcript_sha256, str)
        and SHA256.fullmatch(transcript_sha256) is not None,
        f"{prefix}: resources.console_transcript_sha256 must be a SHA-256 digest",
    )
    observations = manifest.get("observations")
    require(isinstance(observations, dict), f"{prefix}: observations must be an object")
    save = observations.get("save")
    require(save is None or isinstance(save, dict), f"{prefix}: observations.save must be null or an object")
    if save is not None:
        require(
            isinstance(save.get("path"), str) and bool(save["path"]),
            f"{prefix}: observations.save.path must be a nonempty string",
        )
        require(
            isinstance(save.get("sha256"), str)
            and SHA256.fullmatch(save["sha256"]) is not None,
            f"{prefix}: observations.save.sha256 must be a SHA-256 digest",
        )
    return package_lock_sha256, transcript_sha256, save


def _retained_lock_packages(lock: dict[str, Any], name: str) -> list[dict[str, Any]]:
    prefix = f"{name} retained runtime package-lock structure invalid"
    packages = lock.get("packages")
    require(isinstance(packages, list) and bool(packages), f"{prefix}: packages must be a nonempty list")
    for index, package in enumerate(packages):
        require(isinstance(package, dict), f"{prefix}: packages[{index}] must be an object")
        require(
            isinstance(package.get("archive_path"), str) and bool(package["archive_path"]),
            f"{prefix}: packages[{index}].archive_path must be a nonempty string",
        )
        require(
            isinstance(package.get("archive_sha256"), str)
            and SHA256.fullmatch(package["archive_sha256"]) is not None,
            f"{prefix}: packages[{index}].archive_sha256 must be a SHA-256 digest",
        )
    return packages


def validate(
    root: pathlib.Path,
    evidence_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_context: ArtifactContext | None = None,
    live_inputs: LiveInputManifest | None = None,
) -> RuntimeEvidenceSummary:
    context = artifact_context or ArtifactContext.offline()
    repository_evidence = evidence_path is None
    root = root.resolve()
    evidence_path = evidence_path or root / EVIDENCE_RELATIVE
    schema_path = schema_path or root / "docs/project/schema/v2-opponent-runtime-evidence.schema.json"
    evidence = load_json(evidence_path)
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(evidence)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise OpponentRuntimeEvidenceError(f"runtime evidence schema failed at {location}: {exc.message}") from exc
    require(evidence["schema_sha256"] == sha256_file(schema_path), "runtime evidence schema SHA-256 mismatch")
    source = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    require(evidence["engine_source"] == {key: source[key] for key in ("release", "commit", "tree")}, "runtime evidence engine source drifted")
    package_path = root / "config/v2/opponent-package-evidence.json"
    require(evidence["package_evidence_sha256"] == sha256_file(package_path), "runtime/package evidence SHA-256 mismatch")
    package_evidence = load_json(package_path)
    package_results = {item["name"]: item for item in package_evidence["results"]}
    baseline = load_json(root / "config/v2/research-baseline.json")
    baseline_by_name = {item["name"]: item for item in baseline["opponents"]}

    results = evidence["results"]
    names = [item["name"] for item in results]
    require(names == sorted(names), "runtime evidence results are not bytewise sorted")
    require(len(names) == len(set(names)), "runtime evidence has duplicate opponents")
    require(set(names) == set(baseline_by_name), "runtime evidence does not cover the ten-AI audit pool exactly")
    require(len({item["artifact_dir"] for item in results}) == len(results), "runtime evidence has duplicate artifact directories")
    package_artifact_dirs = {item["artifact_dir"] for item in package_evidence["results"]}
    runtime_artifact_dirs = {
        item["artifact_dir"] for item in results if item["phase"] != "PACKAGE"
    }
    overlapping_artifact_dirs = sorted(package_artifact_dirs & runtime_artifact_dirs)
    require(
        not overlapping_artifact_dirs,
        f"runtime/package artifact directories overlap: {overlapping_artifact_dirs}",
    )

    for result in results:
        name = result["name"]
        require(result["content_unique_id"] == baseline_by_name[name]["content_id"], f"{name} runtime content ID drifted")
        package = package_results[name]
        if result["phase"] == "PACKAGE":
            require(package["outcome"] == "REJECTED", f"{name} runtime matrix rejects a locked package before runtime")
            require(result["evidence_sha256"] == package["evidence_sha256"], f"{name} package rejection digest drifted")
            require(result["artifact_dir"] == package["artifact_dir"], f"{name} package rejection artifact drifted")
        else:
            require(package["outcome"] == "LOCKED", f"{name} runtime result has no package lock")
            vehicles = result["vehicles"]
            vehicle_count = 0 if vehicles is None else sum(vehicles.values())
            if result["outcome"] == "QUALIFIED_ACTIVE":
                require(result["admission"] == "TOURNAMENT" and vehicle_count > 0 and result["elapsed_days"] >= 30, f"{name} active admission lacks 30-day vehicle activity")
                require(result["reason_code"] is None, f"{name} active admission has a rejection reason")
            elif result["outcome"] == "QUALIFIED_HEALTHY_INACTIVE":
                require(result["admission"] == "SCENARIO_REQUIRED" and vehicle_count == 0 and result["elapsed_days"] >= 30, f"{name} inactive admission policy mismatch")
                require(result["reason_code"] is None, f"{name} inactive result has a rejection reason")
            elif result["outcome"] == "QUALIFIED_CONTROL":
                require(name == "NoOpAI" and result["admission"] == "CONTROL" and vehicle_count == 0 and result["elapsed_days"] >= 2, "control admission is not an inactive NoOpAI run")
                require(result["reason_code"] is None, "control result has a rejection reason")
            else:
                require(result["admission"] == "EXCLUDED" and result["reason_code"] is not None, f"{name} runtime rejection is not excluded/reasoned")

    counts = Counter(result["outcome"] for result in results)
    admissions = Counter(result["admission"] for result in results)
    require(counts == {"PACKAGE_REJECTED": 2, "QUALIFIED_ACTIVE": 2, "QUALIFIED_HEALTHY_INACTIVE": 3, "REJECTED": 2, "QUALIFIED_CONTROL": 1}, f"runtime outcome inventory drifted: {dict(counts)}")
    require(admissions == {"EXCLUDED": 4, "TOURNAMENT": 2, "SCENARIO_REQUIRED": 3, "CONTROL": 1}, f"runtime admission inventory drifted: {dict(admissions)}")

    if context.is_live:
        require(
            live_inputs is not None and live_inputs.is_live,
            "live-input manifest is required for live opponent runtime validation",
        )
        assert live_inputs is not None
        require(
            live_inputs.artifact_root == context.artifact_root,
            "live-input manifest and artifact context must share one exact artifact root",
        )
        # The portable driver preflights ``required_live_inputs`` as the complete,
        # immutable repository closure.  The validator's own first stage remains
        # fixture-aware: it authenticates the two evidence indexes before their
        # retained records are used to derive and preflight nested paths below.
        requirements = (
            *validate_opponent_package_evidence._requirements(
                validate_opponent_package_evidence.load_json(
                    root / validate_opponent_package_evidence.EVIDENCE_RELATIVE
                )
            ),
            *_requirements(evidence),
        )
        roles = (
            required_live_roles(root)
            if repository_evidence
            else _role_requirements(evidence)
        )
        try:
            context.preflight(requirements)
            live_inputs.preflight(roles)
            openttd = live_inputs.resolve(roles[0])
            require(
                openttd.stat().st_size == evidence["executable"]["size"],
                "runtime evidence executable size mismatch",
            )
        except ArtifactContextError as exc:
            raise OpponentRuntimeEvidenceError(f"live artifact preflight failed: {exc}") from exc
        runtime_requirements = requirements[-len(_requirements(evidence)):]
        retained: list[tuple[dict[str, Any], pathlib.Path, dict[str, Any]]] = []
        manifest_inputs: list[ArtifactRequirement] = []
        for result, requirement in zip(
            (item for item in results if item["phase"] != "PACKAGE"),
            runtime_requirements,
            strict=True,
        ):
            evidence_file = context.resolve(requirement)
            manifest = load_json(evidence_file)
            retained.append((result, evidence_file, manifest))
            package_lock_sha256, transcript_sha256, save = _retained_manifest_inputs(
                manifest,
                result["name"],
            )
            manifest_inputs.extend([
                ArtifactRequirement(
                    result["artifact_dir"],
                    _adjacent_relative_path(
                        result["evidence_file"],
                        qualify_ai_runtime.COPIED_LOCK_NAME,
                    ),
                    "file",
                    LIVE_CONSUMER,
                    package_lock_sha256,
                ),
                ArtifactRequirement(
                    result["artifact_dir"],
                    _adjacent_relative_path(
                        result["evidence_file"],
                        qualify_ai_runtime.TRANSCRIPT_NAME,
                    ),
                    "file",
                    LIVE_CONSUMER,
                    transcript_sha256,
                ),
            ])
            if save is not None:
                manifest_inputs.append(ArtifactRequirement(
                    result["artifact_dir"],
                    _adjacent_relative_path(result["evidence_file"], save["path"]),
                    "file",
                    LIVE_CONSUMER,
                    save["sha256"],
                ))
        try:
            context.preflight(tuple(manifest_inputs))
            archive_inputs: list[ArtifactRequirement] = []
            for result, _evidence_file, manifest in retained:
                lock_relative = _adjacent_relative_path(
                    result["evidence_file"],
                    qualify_ai_runtime.COPIED_LOCK_NAME,
                )
                lock = load_json(context.resolve(ArtifactRequirement(
                    result["artifact_dir"],
                    lock_relative,
                    "file",
                    LIVE_CONSUMER,
                    _retained_manifest_inputs(manifest, result["name"])[0],
                )))
                for package in _retained_lock_packages(lock, result["name"]):
                    archive_inputs.append(ArtifactRequirement(
                        result["artifact_dir"],
                        _adjacent_relative_path(
                            result["evidence_file"],
                            package["archive_path"],
                        ),
                        "file",
                        LIVE_CONSUMER,
                        package["archive_sha256"],
                    ))
            context.preflight(tuple(archive_inputs))
        except ArtifactContextError as exc:
            raise OpponentRuntimeEvidenceError(f"live artifact preflight failed: {exc}") from exc

        try:
            validate_opponent_package_evidence.validate(
                root,
                evidence_path=package_path,
                artifact_context=context,
                live_inputs=live_inputs,
            )
        except validate_opponent_package_evidence.OpponentEvidenceError as exc:
            raise OpponentRuntimeEvidenceError(f"live package evidence failed: {exc}") from exc

        for result, evidence_file, _record in retained:
            try:
                manifest = qualify_ai_runtime.validate_manifest(
                    root,
                    evidence_file,
                    openttd=openttd,
                )
            except qualify_ai_runtime.AIRuntimeError as exc:
                raise OpponentRuntimeEvidenceError(f"{result['name']} runtime manifest failed: {exc}") from exc
            require(manifest["package_lock"]["catalog_name"] == result["name"], f"{result['name']} manifest name mismatch")
            require(manifest["package_lock"]["catalog_unique_id"] == result["content_unique_id"], f"{result['name']} manifest content ID mismatch")
            require(manifest["outcome"] == result["outcome"], f"{result['name']} manifest outcome mismatch")
            require(elapsed_days(manifest) == result["elapsed_days"], f"{result['name']} elapsed-day mismatch")
            require(vehicle_projection(manifest["observations"]["company_after_load"]) == result["vehicles"], f"{result['name']} vehicle projection mismatch")
            require(manifest["resources"]["max_rss_kib"] == result["max_rss_kib"], f"{result['name']} RSS evidence mismatch")
            save = manifest["observations"]["save"]
            require((None if save is None else save["sha256"]) == result["save_sha256"], f"{result['name']} save digest mismatch")
            transcript = (evidence_file.parent / qualify_ai_runtime.TRANSCRIPT_NAME).read_text(encoding="utf-8")
            if result["reason_code"] == "declared-identity-not-listed":
                require(not manifest["checks"]["declared_identity_listed"] and "Compile error" in transcript, f"{result['name']} identity rejection lacks compile-error evidence")
            elif result["reason_code"] == "script-crash-missing-library":
                require(not manifest["checks"]["no_script_crash"] and "couldn't find library" in transcript, f"{result['name']} missing-library rejection lacks crash evidence")

    return RuntimeEvidenceSummary(
        opponents=len(results),
        package_rejected=counts["PACKAGE_REJECTED"],
        runtime_rejected=counts["REJECTED"],
        tournament=admissions["TOURNAMENT"],
        control=admissions["CONTROL"],
        scenario_required=admissions["SCENARIO_REQUIRED"],
        live_artifacts=context.is_live,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--evidence", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    add_artifact_root_argument(parser)
    parser.add_argument("--openttd", type=pathlib.Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        configured_root = args.artifact_root
        if configured_root is None:
            context = ArtifactContext.offline()
            live_inputs = LiveInputManifest.offline()
        else:
            context = ArtifactContext.live(configured_root)
            live_inputs = (
                LiveInputManifest.load(configured_root)
                if args.openttd is None
                else LiveInputManifest.bind(
                    context, {"m14-openttd-executable": args.openttd}
                )
            )
        summary = validate(
            args.root,
            args.evidence,
            args.schema,
            artifact_context=context,
            live_inputs=live_inputs,
        )
        print(
            f"V2_OPPONENT_RUNTIME=PASS opponents={summary.opponents} package_rejected={summary.package_rejected} "
            f"runtime_rejected={summary.runtime_rejected} tournament={summary.tournament} control={summary.control} "
            f"scenario_required={summary.scenario_required} live={str(summary.live_artifacts).lower()}"
        )
        return 0
    except (OpponentRuntimeEvidenceError, ArtifactContextError, OSError) as exc:
        print(f"V2_OPPONENT_RUNTIME=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
