#!/usr/bin/env python3
"""Pure offline/live path contexts for V2 verification inputs."""

from __future__ import annotations

import argparse
import dataclasses
import enum
import hashlib
import json
import os
import pathlib
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import Any


ARTIFACT_ROOT_ENV = "OPENTTD_RL_ARTIFACT_ROOT"
LIVE_INPUT_MANIFEST = "v2-live-inputs.json"
LIVE_INPUT_SCHEMA_VERSION = "openttd-rl-v2-live-inputs-1"


class ArtifactContextError(ValueError):
    """A live artifact input is absent, unsafe, or inconsistent."""


class ValidationMode(enum.StrEnum):
    OFFLINE = "offline"
    LIVE = "live"


_KINDS = frozenset({"file", "directory"})
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _raise_issues(issues: Iterable[str]) -> None:
    failures = sorted(set(issues))
    if failures:
        raise ArtifactContextError("\n".join(failures))


def _validate_component(value: str, *, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise ArtifactContextError(f"{label} must be one nonempty POSIX path component: {value!r}")


def _relative_parts(value: str, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ArtifactContextError(f"{label} must be a safe nonempty relative POSIX path: {value!r}")
    if value == ".":
        return ()
    parts = value.split("/")
    if value.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise ArtifactContextError(f"{label} must be a safe nonempty relative POSIX path: {value!r}")
    return tuple(parts)


def _absolute_parts(value: str, *, label: str) -> tuple[str, ...]:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or "\x00" in value
    ):
        raise ArtifactContextError(f"{label} must be an unambiguous absolute POSIX path: {value!r}")
    parts = value[1:].split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ArtifactContextError(f"{label} must be an unambiguous absolute POSIX path: {value!r}")
    return tuple(parts)


def _validate_kind_and_digest(kind: str, expected_sha256: str | None) -> None:
    if kind not in _KINDS:
        raise ArtifactContextError(f"requirement kind must be file or directory: {kind!r}")
    if expected_sha256 is not None:
        if kind != "file":
            raise ArtifactContextError("only file requirements may declare a SHA-256 digest")
        if _SHA256.fullmatch(expected_sha256) is None:
            raise ArtifactContextError("expected SHA-256 must be 64 lowercase hexadecimal characters")


@dataclasses.dataclass(frozen=True, slots=True)
class ArtifactRequirement:
    logical_set: str
    relative_path: str
    kind: str
    consumer: str
    expected_sha256: str | None = None

    def __post_init__(self) -> None:
        _validate_component(self.logical_set, label="logical artifact set")
        _relative_parts(self.relative_path, label="artifact relative path")
        _validate_kind_and_digest(self.kind, self.expected_sha256)


@dataclasses.dataclass(frozen=True, slots=True)
class RoleRequirement:
    role: str
    relative_path: str
    kind: str
    consumer: str
    expected_sha256: str | None = None

    def __post_init__(self) -> None:
        _validate_component(self.role, label="live-input role")
        _relative_parts(self.relative_path, label="role relative path")
        _validate_kind_and_digest(self.kind, self.expected_sha256)


@dataclasses.dataclass(frozen=True, slots=True)
class ToolRequirement:
    name: str
    path: pathlib.Path
    expected_sha256: str | None = None

    def __post_init__(self) -> None:
        _validate_component(self.name, label="tool name")
        object.__setattr__(self, "path", pathlib.Path(self.path))
        if self.expected_sha256 is not None and _SHA256.fullmatch(self.expected_sha256) is None:
            raise ArtifactContextError("expected SHA-256 must be 64 lowercase hexadecimal characters")


def _first_symlink(path: pathlib.Path) -> pathlib.Path | None:
    candidates = (path, *path.parents)
    for candidate in reversed(candidates):
        if candidate.is_symlink():
            return candidate
    return None


def _sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_issues(
    path: pathlib.Path,
    *,
    kind: str,
    label: str,
    expected_sha256: str | None = None,
) -> list[str]:
    issues: list[str] = []
    symlink = _first_symlink(path)
    if symlink is not None:
        return [f"{label}: symlink traversal is forbidden: {symlink}"]
    if not path.exists():
        return [f"{label}: missing {kind}: {path}"]
    if kind == "file" and not path.is_file():
        issues.append(f"{label}: expected regular file: {path}")
    elif kind == "directory" and not path.is_dir():
        issues.append(f"{label}: expected directory: {path}")
    if expected_sha256 is not None and path.is_file():
        try:
            actual = _sha256_file(path)
        except OSError as exc:
            issues.append(f"{label}: cannot hash {path}: {exc}")
        else:
            if actual != expected_sha256:
                issues.append(
                    f"{label}: SHA-256 mismatch for {path}: expected {expected_sha256}, got {actual}"
                )
    return issues


def resolve_artifact_root(
    explicit_root: pathlib.Path | str | None,
    environ: Mapping[str, str] = os.environ,
) -> pathlib.Path | None:
    """Resolve CLI, then environment configuration without filesystem inference."""

    configured: pathlib.Path | str | None = explicit_root
    if configured is None:
        configured = environ.get(ARTIFACT_ROOT_ENV) or None
    if configured is None:
        return None
    root = pathlib.Path(configured)
    if not root.is_absolute():
        raise ArtifactContextError("artifact root must be an absolute path")
    return root


def add_artifact_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--artifact-root", type=pathlib.Path)


@dataclasses.dataclass(frozen=True, slots=True)
class ArtifactContext:
    mode: ValidationMode
    artifact_root: pathlib.Path | None

    @classmethod
    def offline(cls) -> ArtifactContext:
        return cls(ValidationMode.OFFLINE, None)

    @classmethod
    def live(cls, artifact_root: pathlib.Path | str) -> ArtifactContext:
        root = pathlib.Path(artifact_root)
        if not root.is_absolute():
            raise ArtifactContextError("artifact root must be an absolute path")
        return cls(ValidationMode.LIVE, root)

    @property
    def is_live(self) -> bool:
        return self.mode is ValidationMode.LIVE

    def _live_root(self) -> pathlib.Path:
        if not self.is_live or self.artifact_root is None:
            raise ArtifactContextError("offline validation attempted live artifact access")
        return self.artifact_root

    def artifact_set(self, logical_name: str) -> pathlib.Path:
        root = self._live_root()
        _validate_component(logical_name, label="logical artifact set")
        return root / logical_name

    def relocate(
        self,
        recorded_path: pathlib.Path | str,
        *,
        recorded_root: pathlib.Path | str,
    ) -> pathlib.Path:
        self._live_root()
        path = pathlib.PurePosixPath(str(recorded_path))
        root = pathlib.PurePosixPath(str(recorded_root))
        if not path.is_absolute() or not root.is_absolute() or root.name in {"", ".", ".."}:
            raise ArtifactContextError("recorded path and root must be absolute POSIX paths")
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise ArtifactContextError("recorded path is outside recorded root") from exc
        if any(part == ".." for part in relative.parts):
            raise ArtifactContextError("recorded path is outside recorded root")
        destination = self.artifact_set(root.name)
        if relative != pathlib.PurePosixPath("."):
            destination = destination.joinpath(*relative.parts)
        return destination

    def resolve(self, requirement: ArtifactRequirement) -> pathlib.Path:
        if not isinstance(requirement, ArtifactRequirement):
            raise TypeError("artifact resolution requires an ArtifactRequirement")
        relative = _relative_parts(requirement.relative_path, label="artifact relative path")
        return self.artifact_set(requirement.logical_set).joinpath(*relative)

    def preflight(self, requirements: Sequence[ArtifactRequirement]) -> None:
        root = self._live_root()
        issues = _path_issues(root, kind="directory", label="artifact root")
        for requirement in requirements:
            if not isinstance(requirement, ArtifactRequirement):
                raise TypeError("artifact preflight requires ArtifactRequirement values")
            artifact_set = self.artifact_set(requirement.logical_set)
            issues.extend(_path_issues(
                artifact_set,
                kind="directory",
                label=f"artifact set {requirement.logical_set}",
            ))
            if artifact_set.exists() and _first_symlink(artifact_set) is None:
                issues.extend(_path_issues(
                    self.resolve(requirement),
                    kind=requirement.kind,
                    label=(
                        f"artifact requirement {requirement.logical_set}/"
                        f"{requirement.relative_path} for {requirement.consumer}"
                    ),
                    expected_sha256=requirement.expected_sha256,
                ))
        _raise_issues(issues)


@dataclasses.dataclass(frozen=True, slots=True)
class _RoleSpec:
    kind: str
    expected_sha256: str | None = None


LIVE_INPUT_ROLE_SPECS: Mapping[str, _RoleSpec] = MappingProxyType({
    "recovery-v1-artifacts": _RoleSpec("directory"),
    "recovery-v1-executable": _RoleSpec(
        "file", "2f26dc241b029abeb4641f1497e9347a6675a3d607b564855518fb91b391356f",
    ),
    "recovery-v1-corpus": _RoleSpec(
        "file", "0d5aa3944241b3c00e0b1283de586e00c8fb0a5a51abe385c7e3288785369a0d",
    ),
    "recovery-v2-artifacts": _RoleSpec("directory"),
    "training-artifacts": _RoleSpec("directory"),
    "qualification-artifacts": _RoleSpec("directory"),
    "v2-campaign-executable": _RoleSpec(
        "file", "62ed497cf6f237248a54861269e5b0ad27c8808f8e3d4d7b73d29148e84a5fc2",
    ),
    "v2-corpus-binary": _RoleSpec(
        "file", "d6cdf022e4382a90da4b89a225eb3e1cf15833a63d9c450712aa4c9dbfbc4021",
    ),
    "qualification-executable": _RoleSpec(
        "file", "ae5a74d890e980a6c1308cdad31154e902d0c5e40f234f98b7d34e61849f4b52",
    ),
    "final-v1-evaluator": _RoleSpec(
        "file", "bc87f4608643b4664068381fa5136d464c44bd05dad09a66fa088bfa995b92e6",
    ),
    "m14-openttd-executable": _RoleSpec(
        "file", "8b27f06113d08fa3a21f81c01721873194f35bf885963be2697cc9da52e1ef9a",
    ),
})


class _ObjectPairs(list[tuple[str, Any]]):
    pass


def _load_pairs(path: pathlib.Path) -> _ObjectPairs:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_ObjectPairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactContextError(f"cannot load live-input manifest {path}: {exc}") from exc
    if not isinstance(value, _ObjectPairs):
        raise ArtifactContextError(f"live-input manifest root is not an object: {path}")
    return value


def _duplicate_issues(pairs: _ObjectPairs, *, label: str) -> list[str]:
    return [
        f"{label}: duplicate JSON key {key!r}"
        for key, count in sorted(Counter(key for key, _ in pairs).items())
        if count > 1
    ]


def _manifest_role_path(root: pathlib.Path, value: str) -> pathlib.Path:
    if value.startswith("/"):
        candidate = pathlib.Path("/").joinpath(*_absolute_parts(value, label="live-input path"))
        try:
            relative = candidate.relative_to(root)
        except ValueError as exc:
            raise ArtifactContextError(
                f"live-input path is outside artifact root: {value}"
            ) from exc
        if relative == pathlib.Path("."):
            raise ArtifactContextError(f"live-input path must be below artifact root: {value}")
        return candidate
    parts = _relative_parts(value, label="live-input path")
    return root.joinpath(*parts)


@dataclasses.dataclass(frozen=True, slots=True)
class LiveInputManifest:
    mode: ValidationMode
    artifact_root: pathlib.Path | None
    _roles: Mapping[str, pathlib.Path]

    @classmethod
    def offline(cls) -> LiveInputManifest:
        return cls(ValidationMode.OFFLINE, None, MappingProxyType({}))

    @classmethod
    def load(cls, artifact_root: pathlib.Path | str) -> LiveInputManifest:
        root = pathlib.Path(artifact_root)
        if not root.is_absolute():
            raise ArtifactContextError("artifact root must be an absolute path")
        root_issues = _path_issues(root, kind="directory", label="artifact root")
        _raise_issues(root_issues)
        manifest_path = root / LIVE_INPUT_MANIFEST
        manifest_issues = _path_issues(manifest_path, kind="file", label="live-input manifest")
        _raise_issues(manifest_issues)

        top_pairs = _load_pairs(manifest_path)
        issues = _duplicate_issues(top_pairs, label="live-input manifest")
        top_keys = [key for key, _ in top_pairs]
        for key in sorted(set(top_keys) - {"schema_version", "roles"}):
            issues.append(f"live-input manifest: unknown top-level key {key!r}")
        for key in sorted({"schema_version", "roles"} - set(top_keys)):
            issues.append(f"live-input manifest: missing top-level key {key!r}")
        top = dict(top_pairs)
        if top.get("schema_version") != LIVE_INPUT_SCHEMA_VERSION:
            issues.append(
                "live-input manifest: schema_version must be "
                f"{LIVE_INPUT_SCHEMA_VERSION!r}"
            )

        role_pairs = top.get("roles")
        if not isinstance(role_pairs, _ObjectPairs):
            issues.append("live-input manifest: roles is not an object")
            role_pairs = _ObjectPairs()
        issues.extend(_duplicate_issues(role_pairs, label="live-input roles"))
        role_names = [key for key, _ in role_pairs]
        configured = set(role_names)
        expected = set(LIVE_INPUT_ROLE_SPECS)
        for role in sorted(configured - expected):
            issues.append(f"live-input roles: unknown role {role!r}")
        for role in sorted(expected - configured):
            issues.append(f"live-input roles: missing role {role!r}")

        roles: dict[str, pathlib.Path] = {}
        for role, value in role_pairs:
            if role not in LIVE_INPUT_ROLE_SPECS or role in roles:
                continue
            if not isinstance(value, str):
                issues.append(f"live-input role {role}: path must be a string")
                continue
            try:
                roles[role] = _manifest_role_path(root, value)
            except ArtifactContextError as exc:
                issues.append(f"live-input role {role}: {exc}")

        aliases: dict[pathlib.Path, list[str]] = {}
        for role, path in roles.items():
            spec = LIVE_INPUT_ROLE_SPECS[role]
            if spec.expected_sha256 is not None:
                aliases.setdefault(path, []).append(role)
        for path, names in aliases.items():
            digests = {LIVE_INPUT_ROLE_SPECS[name].expected_sha256 for name in names}
            if len(names) > 1 and len(digests) > 1:
                issues.append(
                    f"incompatible live-input roles alias {path}: {', '.join(sorted(names))}"
                )

        for role, path in roles.items():
            spec = LIVE_INPUT_ROLE_SPECS[role]
            issues.extend(_path_issues(
                path,
                kind=spec.kind,
                label=f"live-input role {role}",
                expected_sha256=spec.expected_sha256,
            ))
        _raise_issues(issues)
        return cls(ValidationMode.LIVE, root, MappingProxyType(dict(roles)))

    @property
    def is_live(self) -> bool:
        return self.mode is ValidationMode.LIVE

    @property
    def roles(self) -> frozenset[str]:
        self._require_live()
        return frozenset(self._roles)

    def _require_live(self) -> None:
        if not self.is_live or self.artifact_root is None:
            raise ArtifactContextError("offline validation attempted live artifact access")

    def resolve(self, requirement: RoleRequirement) -> pathlib.Path:
        self._require_live()
        if not isinstance(requirement, RoleRequirement):
            raise TypeError("role resolution requires a RoleRequirement")
        try:
            base = self._roles[requirement.role]
        except KeyError as exc:
            raise ArtifactContextError(f"live-input role is not declared: {requirement.role}") from exc
        relative = _relative_parts(requirement.relative_path, label="role relative path")
        return base.joinpath(*relative)

    def preflight(self, requirements: Sequence[RoleRequirement]) -> None:
        self._require_live()
        issues: list[str] = []
        for requirement in requirements:
            if not isinstance(requirement, RoleRequirement):
                raise TypeError("role preflight requires RoleRequirement values")
            if requirement.role not in self._roles:
                issues.append(f"live-input role is not declared: {requirement.role}")
                continue
            issues.extend(_path_issues(
                self.resolve(requirement),
                kind=requirement.kind,
                label=(
                    f"role requirement {requirement.role}/"
                    f"{requirement.relative_path} for {requirement.consumer}"
                ),
                expected_sha256=requirement.expected_sha256,
            ))
        _raise_issues(issues)


def preflight_tools(requirements: Sequence[ToolRequirement]) -> None:
    issues: list[str] = []
    for requirement in requirements:
        if not isinstance(requirement, ToolRequirement):
            raise TypeError("tool preflight requires ToolRequirement values")
        path = requirement.path
        label = f"tool {requirement.name}"
        if not path.is_absolute():
            issues.append(f"{label}: path must be absolute: {path}")
            continue
        issues.extend(_path_issues(
            path,
            kind="file",
            label=label,
            expected_sha256=requirement.expected_sha256,
        ))
        if path.is_file() and _first_symlink(path) is None and not os.access(path, os.X_OK):
            issues.append(f"{label}: path is not executable: {path}")
    _raise_issues(issues)
