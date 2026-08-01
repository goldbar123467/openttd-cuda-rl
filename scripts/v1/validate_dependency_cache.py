#!/usr/bin/env python3
"""Validate the complete pinned V1 binary dependency cache offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from typing import Any

import jsonschema


class DependencyCacheError(ValueError):
    """The lock, cache inventory, digest, or extraction closure is invalid."""


ARCHIVE_SUFFIXES = (".zip", ".tgz", ".whl")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_strict_json(path: pathlib.Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DependencyCacheError(f"{path}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                DependencyCacheError(f"{path}: invalid JSON constant {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DependencyCacheError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DependencyCacheError(f"{path}: top level must be an object")
    return value


def resolve_relative(root: pathlib.Path, relative: str, label: str) -> pathlib.Path:
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise DependencyCacheError(f"{label} escapes cache root: {relative}")
    return candidate


def validate(
    *,
    lock_path: pathlib.Path,
    schema_path: pathlib.Path,
    cache_root: pathlib.Path,
) -> dict[str, Any]:
    lock_path = lock_path.resolve()
    schema_path = schema_path.resolve()
    cache_root = cache_root.resolve()
    if not cache_root.is_dir():
        raise DependencyCacheError(f"cache root is not a directory: {cache_root}")

    lock = load_strict_json(lock_path)
    schema = load_strict_json(schema_path)
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(
            schema,
            format_checker=jsonschema.FormatChecker(),
        ).validate(lock)
    except jsonschema.exceptions.SchemaError as exc:
        raise DependencyCacheError(f"dependency schema is invalid: {exc.message}") from exc
    except jsonschema.exceptions.ValidationError as exc:
        raise DependencyCacheError(f"dependency lock schema validation failed: {exc.message}") from exc

    schema_sha256 = sha256_file(schema_path)
    if lock["schema_sha256"] != schema_sha256:
        raise DependencyCacheError(
            "dependency schema digest mismatch: "
            f"expected={schema_sha256} actual={lock['schema_sha256']}"
        )

    artifacts = lock["artifacts"]
    ids = [artifact["id"] for artifact in artifacts]
    paths = [artifact["relative_cache_path"] for artifact in artifacts]
    if len(ids) != len(set(ids)):
        raise DependencyCacheError("dependency artifact ids are not unique")
    if len(paths) != len(set(paths)):
        raise DependencyCacheError("dependency artifact paths are not unique")

    expected_paths = {
        artifact["relative_cache_path"]
        for artifact in artifacts
        if artifact["kind"] != "text"
    }
    discovered_paths = {
        path.relative_to(cache_root).as_posix()
        for path in cache_root.rglob("*")
        if path.is_file() and path.name.endswith(ARCHIVE_SUFFIXES)
    }
    if discovered_paths != expected_paths:
        raise DependencyCacheError(
            "cache archive inventory mismatch: "
            f"unlisted={sorted(discovered_paths - expected_paths)} "
            f"missing={sorted(expected_paths - discovered_paths)}"
        )

    total_bytes = 0
    for artifact in artifacts:
        relative = artifact["relative_cache_path"]
        path = resolve_relative(cache_root, relative, f"artifact {artifact['id']}")
        if path.is_symlink() or not path.is_file():
            raise DependencyCacheError(f"artifact is not a regular non-symlink file: {relative}")
        actual_size = path.stat().st_size
        if actual_size != artifact["size_bytes"]:
            raise DependencyCacheError(
                f"artifact size mismatch for {relative}: "
                f"expected={artifact['size_bytes']} actual={actual_size}"
            )
        actual_sha256 = sha256_file(path)
        if actual_sha256 != artifact["sha256"]:
            raise DependencyCacheError(
                f"artifact digest mismatch for {relative}: "
                f"expected={artifact['sha256']} actual={actual_sha256}"
            )
        total_bytes += actual_size

    artifact_ids = set(ids)
    extraction_ids: set[str] = set()
    for extraction in lock["extractions"]:
        artifact_id = extraction["artifact_id"]
        if artifact_id not in artifact_ids:
            raise DependencyCacheError(
                f"extraction references unknown artifact id: {artifact_id}"
            )
        if artifact_id in extraction_ids:
            raise DependencyCacheError(f"duplicate extraction artifact id: {artifact_id}")
        extraction_ids.add(artifact_id)
        extraction_root = resolve_relative(
            cache_root,
            extraction["relative_root"],
            f"extraction {artifact_id}",
        )
        if extraction_root.is_symlink() or not extraction_root.is_dir():
            raise DependencyCacheError(
                f"extraction root is not a directory: {extraction['relative_root']}"
            )
        markers = extraction["required_markers"]
        if len(markers) != len(set(markers)):
            raise DependencyCacheError(f"duplicate extraction marker for {artifact_id}")
        for marker in markers:
            marker_path = resolve_relative(
                extraction_root,
                marker,
                f"extraction marker {artifact_id}",
            )
            if not marker_path.exists():
                raise DependencyCacheError(
                    f"missing extraction marker for {artifact_id}: {marker}"
                )

    lock_sha256 = sha256_file(lock_path)
    return {
        "schema_version": "openttd-rl-v1-dependency-cache-validation-1",
        "profile_id": lock["profile_id"],
        "lock_sha256": lock_sha256,
        "schema_sha256": schema_sha256,
        "artifact_count": len(artifacts),
        "extraction_count": len(lock["extractions"]),
        "total_artifact_bytes": total_bytes,
        "result": "PASS",
    }


def parse_args(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", required=True, type=pathlib.Path)
    parser.add_argument("--schema", required=True, type=pathlib.Path)
    parser.add_argument("--cache-root", required=True, type=pathlib.Path)
    parser.add_argument("--json", action="store_true", help="emit canonical JSON")
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        result = validate(
            lock_path=options.lock,
            schema_path=options.schema,
            cache_root=options.cache_root,
        )
    except DependencyCacheError as exc:
        print(f"DEPENDENCY_CACHE=FAIL {exc}", file=sys.stderr)
        return 1
    if options.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(
            "DEPENDENCY_CACHE=PASS"
            f" profile={result['profile_id']}"
            f" artifacts={result['artifact_count']}"
            f" extractions={result['extraction_count']}"
            f" bytes={result['total_artifact_bytes']}"
            f" lock_sha256={result['lock_sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
