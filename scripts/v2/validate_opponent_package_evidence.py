#!/usr/bin/env python3
"""Validate the M14 opponent acquisition evidence index and optional live artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema

import acquire_ai_package
from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    DeferredArtifactRequirement,
    LiveInputManifest,
    RoleRequirement,
    add_artifact_root_argument,
)


EVIDENCE_RELATIVE = pathlib.Path("config/v2/opponent-package-evidence.json")
LIVE_CONSUMER = "m14-opponent-package-evidence"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PACKAGE_ARCHIVES = {
    "AAAHogEx": ("content_download/ai/484f4745-AAAHogEx-115.tar",),
    "KrakenAI2": (
        "content_download/ai/4b524132-KrakenAI2-3.tar",
        "content_download/ai/library/4752412a-Graph.AyStar-6.tar",
        "content_download/ai/library/5046524f-Pathfinder.Road-4.tar",
        "content_download/ai/library/51554248-Queue.BinaryHeap-1.tar",
        "content_download/ai/library/5350524c-SuperLib-40.tar",
    ),
    "LuDiAI AfterFix": ("content_download/ai/4c444146-LuDiAI_AfterFix-27.tar",),
    "Lufthansa": ("content_download/ai/4c554654-Lufthansa-2.tar",),
    "NoOpAI": ("content_download/ai/4e6f7041-NoOpAI-4.tar",),
    "ShipAI": ("content_download/ai/53484950-ShipAI-10.tar",),
    "Trans AI": ("content_download/ai/46544149-Trans_AI-200626.tar",),
    "WmDOT": (
        "content_download/ai/7d7d6d57-WmDOT-16.tar",
        "content_download/ai/library/4752412a-Graph.AyStar-6.tar",
        "content_download/ai/library/4c4d6d57-MinchinWeb_s_MetaLibrary-11.tar",
        "content_download/ai/library/5046524f-Pathfinder.Road-4.tar",
        "content_download/ai/library/51554248-Queue.BinaryHeap-1.tar",
        "content_download/ai/library/51554648-Queue.FibonacciHeap-3.tar",
        "content_download/ai/library/5350524c-SuperLib-40.tar",
    ),
}


class OpponentEvidenceError(ValueError):
    """The opponent evidence index violates an M14 invariant."""


@dataclass(frozen=True)
class OpponentEvidenceSummary:
    opponents: int
    locked: int
    rejected: int
    packages: int
    archive_bytes: int
    license_files: int
    live_artifacts: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OpponentEvidenceError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OpponentEvidenceError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise OpponentEvidenceError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def closure_sha256(packages: list[dict[str, Any]]) -> str:
    value = "".join(
        f"{package['local_unique_id']} {package['archive_size']} {package['archive_sha256']}\n"
        for package in packages
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
    )


def _complete_requirements(
    evidence: dict[str, Any],
) -> tuple[ArtifactRequirement | DeferredArtifactRequirement, ...]:
    direct = _requirements(evidence)
    requirements: list[ArtifactRequirement | DeferredArtifactRequirement] = [*direct]
    for result, authority in zip(evidence["results"], direct, strict=True):
        if result["outcome"] == "REJECTED":
            requirements.append(DeferredArtifactRequirement(
                result["artifact_dir"],
                acquire_ai_package.TRANSCRIPT_NAME,
                "file",
                LIVE_CONSUMER,
                authority,
            ))
            continue
        archives = PACKAGE_ARCHIVES.get(result["name"])
        require(
            archives is not None and len(archives) == result["package_count"],
            f"{result['name']} committed package archive closure drifted",
        )
        requirements.extend(
            DeferredArtifactRequirement(
                result["artifact_dir"], archive, "file", LIVE_CONSUMER, authority,
            )
            for archive in archives
        )
    return tuple(requirements)


def required_live_inputs(
    root: pathlib.Path,
) -> tuple[ArtifactRequirement | DeferredArtifactRequirement, ...]:
    root = root.resolve()
    return _complete_requirements(load_json(root / EVIDENCE_RELATIVE))


def expanded_live_inputs(
    context: ArtifactContext,
    root: pathlib.Path,
) -> tuple[ArtifactRequirement, ...]:
    """Expand nested bytes only from digest-authenticated retained records."""

    root = root.resolve()
    evidence = load_json(root / EVIDENCE_RELATIVE)
    result_requirements = _requirements(evidence)
    expanded: list[ArtifactRequirement] = []
    for result, requirement in zip(
        evidence["results"], result_requirements, strict=True,
    ):
        record = load_json(context.resolve(requirement))
        if result["outcome"] == "LOCKED":
            packages = _retained_packages(record, result["name"])
            expected_paths = PACKAGE_ARCHIVES.get(result["name"])
            observed_paths = tuple(
                _adjacent_relative_path(
                    result["evidence_file"], package["archive_path"],
                )
                for package in packages
            )
            require(
                expected_paths is not None and observed_paths == expected_paths,
                f"{result['name']} retained package archive closure drifted",
            )
            expanded.extend(
                ArtifactRequirement(
                    result["artifact_dir"],
                    relative_path,
                    "file",
                    LIVE_CONSUMER,
                    package["archive_sha256"],
                )
                for relative_path, package in zip(
                    observed_paths, packages, strict=True,
                )
            )
        else:
            transcript = _retained_transcript(record, result["name"])
            require(
                transcript["sha256"] == result["transcript_sha256"],
                f"{result['name']} retained transcript digest drifted",
            )
            expanded.append(ArtifactRequirement(
                result["artifact_dir"],
                _adjacent_relative_path(
                    result["evidence_file"], transcript["path"],
                ),
                "file",
                LIVE_CONSUMER,
                transcript["sha256"],
            ))
    return tuple(expanded)


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


def _retained_packages(record: dict[str, Any], name: str) -> list[dict[str, Any]]:
    packages = record.get("packages")
    require(
        isinstance(packages, list) and bool(packages),
        f"{name} retained package evidence structure invalid: packages must be a nonempty list",
    )
    for index, package in enumerate(packages):
        require(
            isinstance(package, dict),
            f"{name} retained package evidence structure invalid: packages[{index}] must be an object",
        )
        require(
            isinstance(package.get("archive_path"), str) and bool(package["archive_path"]),
            f"{name} retained package evidence structure invalid: packages[{index}].archive_path must be a nonempty string",
        )
        require(
            isinstance(package.get("archive_sha256"), str)
            and SHA256.fullmatch(package["archive_sha256"]) is not None,
            f"{name} retained package evidence structure invalid: packages[{index}].archive_sha256 must be a SHA-256 digest",
        )
    return packages


def _retained_transcript(record: dict[str, Any], name: str) -> dict[str, Any]:
    transcript = record.get("console_transcript")
    require(
        isinstance(transcript, dict),
        f"{name} retained package evidence structure invalid: console_transcript must be an object",
    )
    require(
        isinstance(transcript.get("path"), str) and bool(transcript["path"]),
        f"{name} retained package evidence structure invalid: console_transcript.path must be a nonempty string",
    )
    require(
        isinstance(transcript.get("sha256"), str)
        and SHA256.fullmatch(transcript["sha256"]) is not None,
        f"{name} retained package evidence structure invalid: console_transcript.sha256 must be a SHA-256 digest",
    )
    return transcript


def validate_rejection(
    root: pathlib.Path,
    rejection_path: pathlib.Path,
    result: dict[str, Any],
    executable: dict[str, Any],
) -> None:
    rejection = load_json(rejection_path)
    schema_path = root / acquire_ai_package.REJECTION_SCHEMA_RELATIVE
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(rejection)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise OpponentEvidenceError(f"rejection schema failed at {location}: {exc.message}") from exc
    require(rejection["schema_sha256"] == sha256_file(schema_path), "rejection schema SHA-256 mismatch")
    require(rejection["request"]["name"] == result["name"], "rejection opponent name mismatch")
    require(rejection["request"]["content_unique_id"] == result["content_unique_id"], "rejection content ID mismatch")
    require(rejection["request"]["version"] == result["version"], "rejection version mismatch")
    require(rejection["reason_code"] == result["reason_code"], "rejection reason mismatch")
    require(rejection["executable"] == executable, "rejection executable identity mismatch")
    transcript = rejection_path.parent / rejection["console_transcript"]["path"]
    require(transcript.is_file(), f"rejection transcript is missing: {transcript}")
    require(transcript.stat().st_size == rejection["console_transcript"]["size"], "rejection transcript size mismatch")
    require(sha256_file(transcript) == rejection["console_transcript"]["sha256"], "rejection transcript SHA-256 mismatch")
    require(result["transcript_sha256"] == rejection["console_transcript"]["sha256"], "index transcript SHA-256 mismatch")


def validate(
    root: pathlib.Path,
    evidence_path: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
    *,
    artifact_context: ArtifactContext | None = None,
    live_inputs: LiveInputManifest | None = None,
) -> OpponentEvidenceSummary:
    context = artifact_context or ArtifactContext.offline()
    repository_evidence = evidence_path is None
    root = root.resolve()
    evidence_path = evidence_path or root / EVIDENCE_RELATIVE
    schema_path = schema_path or root / "docs/project/schema/v2-opponent-package-evidence.schema.json"
    evidence = load_json(evidence_path)
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(evidence)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise OpponentEvidenceError(f"evidence schema failed at {location}: {exc.message}") from exc
    require(evidence["schema_sha256"] == sha256_file(schema_path), "opponent evidence schema SHA-256 mismatch")

    source = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    expected_source = {key: source[key] for key in ("release", "commit", "tree")}
    require(evidence["engine_source"] == expected_source, "opponent evidence engine source drifted")
    baseline = load_json(root / "config/v2/research-baseline.json")
    opponents = {item["name"]: item for item in baseline["opponents"]}
    results = evidence["results"]
    names = [item["name"] for item in results]
    require(names == sorted(names), "opponent evidence results are not bytewise sorted")
    require(set(names) == set(opponents), "opponent evidence does not cover the research audit pool exactly")
    require(len(names) == len(set(names)), "opponent evidence has duplicate names")
    artifact_dirs = [item["artifact_dir"] for item in results]
    require(len(artifact_dirs) == len(set(artifact_dirs)), "opponent evidence has duplicate artifact directories")
    for result in results:
        opponent = opponents[result["name"]]
        require(result["content_unique_id"] == opponent["content_id"], f"{result['name']} content ID drifted")
        require(result["version"] == acquire_ai_package.canonical_version(opponent["version"]), f"{result['name']} version drifted")
    locked = [result for result in results if result["outcome"] == "LOCKED"]
    rejected = [result for result in results if result["outcome"] == "REJECTED"]
    require(len(locked) >= 6, "opponent acquisition locked fewer than six audit-pool AIs")
    require(rejected, "opponent evidence must retain truthful rejection coverage")

    if context.is_live:
        require(
            live_inputs is not None and live_inputs.is_live,
            "live-input manifest is required for live opponent package validation",
        )
        assert live_inputs is not None
        require(
            live_inputs.artifact_root == context.artifact_root,
            "live-input manifest and artifact context must share one exact artifact root",
        )
        result_requirements = _requirements(evidence)
        roles = (
            required_live_roles(root)
            if repository_evidence
            else _role_requirements(evidence)
        )
        try:
            context.preflight(result_requirements)
            live_inputs.preflight(roles)
            openttd = live_inputs.resolve(roles[0])
            require(
                openttd.stat().st_size == evidence["executable"]["size"],
                "evidence executable size mismatch",
            )
            retained: list[tuple[dict[str, Any], pathlib.Path, dict[str, Any]]] = []
            derived: list[ArtifactRequirement] = []
            for result, requirement in zip(
                results, result_requirements, strict=True,
            ):
                evidence_file = context.resolve(requirement)
                record = load_json(evidence_file)
                retained.append((result, evidence_file, record))
                if result["outcome"] == "LOCKED":
                    for package in _retained_packages(record, result["name"]):
                        derived.append(ArtifactRequirement(
                            result["artifact_dir"],
                            _adjacent_relative_path(
                                result["evidence_file"],
                                package["archive_path"],
                            ),
                            "file",
                            LIVE_CONSUMER,
                            package["archive_sha256"],
                        ))
                else:
                    transcript = _retained_transcript(record, result["name"])
                    derived.append(ArtifactRequirement(
                        result["artifact_dir"],
                        _adjacent_relative_path(
                            result["evidence_file"],
                            transcript["path"],
                        ),
                        "file",
                        LIVE_CONSUMER,
                        transcript["sha256"],
                    ))
            context.preflight(tuple(derived))
        except ArtifactContextError as exc:
            raise OpponentEvidenceError(f"live artifact preflight failed: {exc}") from exc

        for result, evidence_file, _record in retained:
            if result["outcome"] == "LOCKED":
                try:
                    lock = acquire_ai_package.validate_lock(
                        root,
                        evidence_file,
                        openttd=openttd,
                    )
                except acquire_ai_package.AIPackageError as exc:
                    raise OpponentEvidenceError(f"{result['name']} live lock failed: {exc}") from exc
                packages = lock["packages"]
                require(len(packages) == result["package_count"], f"{result['name']} package count mismatch")
                require(sum(item["archive_size"] for item in packages) == result["archive_bytes"], f"{result['name']} archive byte count mismatch")
                require(sum(len(item["licenses"]) for item in packages) == result["license_files"], f"{result['name']} license count mismatch")
                require(closure_sha256(packages) == result["closure_sha256"], f"{result['name']} closure SHA-256 mismatch")
            else:
                validate_rejection(root, evidence_file, result, evidence["executable"])

    return OpponentEvidenceSummary(
        opponents=len(results),
        locked=len(locked),
        rejected=len(rejected),
        packages=sum(result.get("package_count", 0) for result in results),
        archive_bytes=sum(result.get("archive_bytes", 0) for result in results),
        license_files=sum(result.get("license_files", 0) for result in results),
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
            f"V2_OPPONENT_EVIDENCE=PASS opponents={summary.opponents} locked={summary.locked} "
            f"rejected={summary.rejected} packages={summary.packages} "
            f"archive_bytes={summary.archive_bytes} licenses={summary.license_files} "
            f"live={str(summary.live_artifacts).lower()}"
        )
        return 0
    except (OpponentEvidenceError, ArtifactContextError, OSError) as exc:
        print(f"V2_OPPONENT_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
