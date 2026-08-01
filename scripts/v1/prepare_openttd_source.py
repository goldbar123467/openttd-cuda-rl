#!/usr/bin/env python3
"""Prepare the pinned V1 OpenTTD tree without changing the P0 checkout."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tarfile
from typing import Any

import jsonschema


class SourcePreparationError(ValueError):
    """A source identity, patch, path, or preservation guard failed."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_strict_json(path: pathlib.Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SourcePreparationError(f"{path}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                SourcePreparationError(f"{path}: invalid JSON constant {token}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourcePreparationError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SourcePreparationError(f"{path}: top level must be an object")
    return value


def run(
    command: list[str],
    *,
    cwd: pathlib.Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SourcePreparationError(
            f"command failed ({result.returncode}): {' '.join(command)}: {detail}"
        )
    return result


def git(repository: pathlib.Path, *arguments: str) -> str:
    return run(["git", "-C", str(repository), *arguments]).stdout.strip()


def repository_path(root: pathlib.Path, relative: str, label: str) -> pathlib.Path:
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise SourcePreparationError(f"{label} escapes repository root: {relative}")
    return candidate


def validate_schema(instance: dict[str, Any], schema: dict[str, Any], label: str) -> None:
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(
            schema,
            format_checker=jsonschema.FormatChecker(),
        ).validate(instance)
    except jsonschema.exceptions.ValidationError as exc:
        raise SourcePreparationError(f"{label} schema validation failed: {exc.message}") from exc


def parse_patch_series(
    root: pathlib.Path,
    profile: dict[str, Any],
) -> tuple[pathlib.Path, list[pathlib.Path]]:
    patch_config = profile["patch_series"]
    patch_directory = repository_path(root, patch_config["directory"], "patch directory")
    series_path = repository_path(root, patch_config["series_file"], "series file")
    if not patch_directory.is_dir():
        raise SourcePreparationError(f"patch directory does not exist: {patch_directory}")
    if not series_path.is_file() or series_path.parent != patch_directory:
        raise SourcePreparationError("series file must be a regular file directly in patch directory")
    series_bytes = series_path.read_bytes()
    actual_series_sha256 = sha256_bytes(series_bytes)
    if actual_series_sha256 != patch_config["series_sha256"]:
        raise SourcePreparationError(
            "patch series digest mismatch: "
            f"expected={patch_config['series_sha256']} actual={actual_series_sha256}"
        )

    patch_names: list[str] = []
    for line_number, raw in enumerate(series_bytes.decode("utf-8").splitlines(), 1):
        name = raw.strip()
        if not name or name.startswith("#"):
            continue
        if name != pathlib.PurePosixPath(name).name or not name.endswith(".patch"):
            raise SourcePreparationError(
                f"{series_path}:{line_number}: patch must be a .patch basename"
            )
        if name in patch_names:
            raise SourcePreparationError(f"{series_path}:{line_number}: duplicate patch {name}")
        patch_names.append(name)

    listed = [patch_directory / name for name in patch_names]
    for path in listed:
        if not path.is_file() or path.is_symlink():
            raise SourcePreparationError(f"listed patch is not a regular file: {path}")
    present = {path.name for path in patch_directory.glob("*.patch") if path.is_file()}
    if present != set(patch_names):
        raise SourcePreparationError(
            "listed/present patch mismatch: "
            f"unlisted={sorted(present - set(patch_names))} "
            f"missing={sorted(set(patch_names) - present)}"
        )
    return series_path, listed


def extract_git_archive(
    object_repository: pathlib.Path,
    commit: str,
    output: pathlib.Path,
) -> None:
    result = subprocess.run(
        ["git", "-C", str(object_repository), "archive", "--format=tar", commit],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise SourcePreparationError(
            f"git archive failed ({result.returncode}): {result.stderr.decode(errors='replace').strip()}"
        )
    output.mkdir(parents=False, exist_ok=False)
    try:
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            archive.extractall(output, filter="data")
    except (tarfile.TarError, OSError) as exc:
        raise SourcePreparationError(f"cannot extract pinned source archive: {exc}") from exc


def initialize_index(output: pathlib.Path, expected_tree: str) -> None:
    run(["git", "init", "-q", str(output)])
    run(["git", "-C", str(output), "config", "core.autocrlf", "false"])
    run(["git", "-C", str(output), "config", "core.filemode", "true"])
    run(["git", "-C", str(output), "add", "-A"])
    observed_tree = git(output, "write-tree")
    if observed_tree != expected_tree:
        raise SourcePreparationError(
            f"extracted base tree mismatch: expected={expected_tree} actual={observed_tree}"
        )


def apply_patches(
    output: pathlib.Path,
    patches: list[pathlib.Path],
    base_tree: str,
) -> None:
    for patch in patches:
        arguments = [
            "git",
            "-C",
            str(output),
            "apply",
            "--index",
            "--whitespace=error-all",
            "--verbose",
            str(patch),
        ]
        check_result = run(arguments[:5] + ["--check"] + arguments[5:], check=False)
        diagnostic = f"{check_result.stdout}\n{check_result.stderr}"
        if check_result.returncode != 0:
            raise SourcePreparationError(
                f"patch check failed for {patch.name}: {diagnostic.strip()}"
            )
        if re.search(r"\b(?:offset|fuzz|warning)\b", diagnostic, re.IGNORECASE):
            raise SourcePreparationError(
                f"patch check was not exact for {patch.name}: {diagnostic.strip()}"
            )
        apply_result = run(arguments, check=False)
        diagnostic = f"{apply_result.stdout}\n{apply_result.stderr}"
        if apply_result.returncode != 0:
            raise SourcePreparationError(
                f"patch application failed for {patch.name}: {diagnostic.strip()}"
            )
        if re.search(r"\b(?:offset|fuzz|warning)\b", diagnostic, re.IGNORECASE):
            raise SourcePreparationError(
                f"patch application was not exact for {patch.name}: {diagnostic.strip()}"
            )
    run(["git", "-C", str(output), "diff", "--cached", "--check", base_tree])


def atomic_write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise SourcePreparationError(f"manifest already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise SourcePreparationError(f"cannot publish manifest {path}: {exc}") from exc


def prepare(
    *,
    root: pathlib.Path,
    profile_path: pathlib.Path,
    profile_schema_path: pathlib.Path,
    manifest_schema_path: pathlib.Path,
    object_repository_override: pathlib.Path | None,
    output: pathlib.Path,
    manifest_path: pathlib.Path,
) -> dict[str, Any]:
    root = root.resolve()
    profile_path = profile_path.resolve()
    profile_schema_path = profile_schema_path.resolve()
    manifest_schema_path = manifest_schema_path.resolve()
    output = output.resolve()
    manifest_path = manifest_path.resolve()
    if output.exists():
        raise SourcePreparationError(f"output path already exists: {output}")
    if manifest_path.exists():
        raise SourcePreparationError(f"manifest already exists: {manifest_path}")

    profile_bytes = profile_path.read_bytes()
    profile = load_strict_json(profile_path)
    profile_schema = load_strict_json(profile_schema_path)
    manifest_schema = load_strict_json(manifest_schema_path)
    validate_schema(profile, profile_schema, "source profile")
    actual_profile_schema_sha256 = sha256_bytes(profile_schema_path.read_bytes())
    if profile["schema_sha256"] != actual_profile_schema_sha256:
        raise SourcePreparationError(
            "profile schema digest mismatch: "
            f"expected={actual_profile_schema_sha256} actual={profile['schema_sha256']}"
        )

    series_path, patches = parse_patch_series(root, profile)
    if object_repository_override is None:
        object_repository = repository_path(
            root,
            profile["object_repository"],
            "object repository",
        )
    else:
        object_repository = object_repository_override.resolve()
    if not object_repository.is_dir():
        raise SourcePreparationError(f"object repository does not exist: {object_repository}")

    status_before = git(object_repository, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    if status_before:
        raise SourcePreparationError(
            f"object repository worktree is dirty: {status_before[:10]}"
        )
    head_before = git(object_repository, "rev-parse", "HEAD")
    origin = git(object_repository, "remote", "get-url", "origin")
    if origin != profile["upstream"]["url"]:
        raise SourcePreparationError(
            f"object repository origin mismatch: expected={profile['upstream']['url']} actual={origin}"
        )

    commit = profile["upstream"]["commit"]
    object_check = run(
        ["git", "-C", str(object_repository), "cat-file", "-e", f"{commit}^{{commit}}"],
        check=False,
    )
    if object_check.returncode != 0:
        raise SourcePreparationError(
            f"pinned commit is unavailable offline in object repository: {commit}"
        )
    actual_tree = git(object_repository, "rev-parse", f"{commit}^{{tree}}")
    if actual_tree != profile["upstream"]["tree"]:
        raise SourcePreparationError(
            f"pinned base tree mismatch: expected={profile['upstream']['tree']} actual={actual_tree}"
        )

    extract_git_archive(object_repository, commit, output)
    initialize_index(output, actual_tree)
    cmake_text = (output / "CMakeLists.txt").read_text(encoding="utf-8")
    expected_standard = profile["upstream"]["cxx_standard"]
    if not re.search(
        rf"set\(CMAKE_CXX_STANDARD\s+{expected_standard}\)",
        cmake_text,
    ):
        raise SourcePreparationError(
            f"pinned source does not declare expected C++ standard {expected_standard}"
        )
    copying = output / "COPYING.md"
    if not copying.is_file() or "GNU General Public License" not in copying.read_text(
        encoding="utf-8"
    ):
        raise SourcePreparationError("pinned source license file is missing or unexpected")

    apply_patches(output, patches, actual_tree)
    result_tree = git(output, "write-tree")
    worktree_status = git(
        output,
        "diff",
        "--cached",
        "--name-status",
        actual_tree,
    ).splitlines()

    head_after = git(object_repository, "rev-parse", "HEAD")
    status_after = git(object_repository, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    if head_after != head_before or status_after != status_before:
        raise SourcePreparationError("source preparation changed the object repository checkout")

    patch_records = [
        {
            "order": index,
            "path": patch.relative_to(root).as_posix(),
            "sha256": sha256_bytes(patch.read_bytes()),
        }
        for index, patch in enumerate(patches, 1)
    ]
    identity = {
        "profile_sha256": sha256_bytes(profile_bytes),
        "source_commit": commit,
        "source_tree": actual_tree,
        "series_sha256": sha256_bytes(series_path.read_bytes()),
        "patches": patch_records,
        "result_tree": result_tree,
    }
    identity_bytes = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest = {
        "schema_version": "openttd-rl-v1-prepared-source-manifest-1",
        "schema_sha256": sha256_bytes(manifest_schema_path.read_bytes()),
        "profile_id": profile["profile_id"],
        "profile_sha256": sha256_bytes(profile_bytes),
        "source": profile["upstream"],
        "patch_series": {
            "series_file": series_path.relative_to(root).as_posix(),
            "series_sha256": sha256_bytes(series_path.read_bytes()),
            "patches": patch_records,
        },
        "result": {
            "tree": result_tree,
            "patch_count": len(patches),
            "worktree_status": worktree_status,
        },
        "object_repository_guard": {
            "head_before": head_before,
            "head_after": head_after,
            "status_before": status_before,
            "status_after": status_after,
            "origin": origin,
        },
        "tools": {"git": run(["git", "--version"]).stdout.strip()},
        "preparation_identity_sha256": sha256_bytes(identity_bytes),
    }
    validate_schema(manifest, manifest_schema, "prepared-source manifest")
    atomic_write_json(manifest_path, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--profile", type=pathlib.Path, required=True)
    parser.add_argument("--profile-schema", type=pathlib.Path, required=True)
    parser.add_argument("--manifest-schema", type=pathlib.Path, required=True)
    parser.add_argument("--source-repo", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = prepare(
            root=args.root,
            profile_path=args.profile,
            profile_schema_path=args.profile_schema,
            manifest_schema_path=args.manifest_schema,
            object_repository_override=args.source_repo,
            output=args.output,
            manifest_path=args.manifest,
        )
    except (SourcePreparationError, OSError, UnicodeError) as exc:
        print(f"V1_SOURCE_PREP=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "V1_SOURCE_PREP=PASS "
        f"profile={manifest['profile_id']} "
        f"base={manifest['source']['commit']} "
        f"patches={manifest['result']['patch_count']} "
        f"tree={manifest['result']['tree']} "
        f"identity={manifest['preparation_identity_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
