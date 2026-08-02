#!/usr/bin/env python3
"""Validate the M14 opponent acquisition evidence index and optional live artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

import jsonschema

import acquire_ai_package


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
    artifact_base: pathlib.Path | None = None,
    openttd: pathlib.Path | None = None,
) -> OpponentEvidenceSummary:
    root = root.resolve()
    evidence_path = evidence_path or root / "config/v2/opponent-package-evidence.json"
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

    if artifact_base is not None:
        artifact_base = artifact_base.resolve()
        require(artifact_base.is_dir(), f"artifact base does not exist: {artifact_base}")
        if openttd is not None:
            openttd = openttd.resolve()
            require(sha256_file(openttd) == evidence["executable"]["sha256"], "evidence executable SHA-256 mismatch")
            require(openttd.stat().st_size == evidence["executable"]["size"], "evidence executable size mismatch")
        for result in results:
            artifact_dir = artifact_base / result["artifact_dir"]
            require(artifact_dir.is_dir() and not artifact_dir.is_symlink(), f"opponent artifact directory is missing or a symlink: {artifact_dir}")
            evidence_file = artifact_dir / result["evidence_file"]
            require(evidence_file.is_file() and not evidence_file.is_symlink(), f"opponent evidence file is missing or a symlink: {evidence_file}")
            require(sha256_file(evidence_file) == result["evidence_sha256"], f"{result['name']} evidence SHA-256 mismatch")
            if result["outcome"] == "LOCKED":
                try:
                    lock = acquire_ai_package.validate_lock(root, evidence_file, openttd=openttd)
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
        live_artifacts=artifact_base is not None,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--evidence", type=pathlib.Path)
    parser.add_argument("--schema", type=pathlib.Path)
    parser.add_argument("--artifact-base", type=pathlib.Path)
    parser.add_argument("--openttd", type=pathlib.Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        summary = validate(
            args.root,
            args.evidence,
            args.schema,
            artifact_base=args.artifact_base,
            openttd=args.openttd,
        )
        print(
            f"V2_OPPONENT_EVIDENCE=PASS opponents={summary.opponents} locked={summary.locked} "
            f"rejected={summary.rejected} packages={summary.packages} "
            f"archive_bytes={summary.archive_bytes} licenses={summary.license_files} "
            f"live={str(summary.live_artifacts).lower()}"
        )
        return 0
    except (OpponentEvidenceError, OSError) as exc:
        print(f"V2_OPPONENT_EVIDENCE=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
