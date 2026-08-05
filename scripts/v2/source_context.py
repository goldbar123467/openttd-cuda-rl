#!/usr/bin/env python3
"""Explicit offline/live Git object-repository context for V2 validation."""

from __future__ import annotations

import argparse
import dataclasses
import os
import pathlib
import re
import subprocess

from artifact_context import ValidationMode


class SourceContextError(ValueError):
    """The requested source access is unavailable or unsafe."""


_COMMIT = re.compile(r"[0-9a-fA-F]{40}")
_REVISION = re.compile(r"(?:HEAD|[0-9a-fA-F]{40})")
_TREE_EXPRESSION = re.compile(r"(?:HEAD|[0-9a-fA-F]{40})\^\{tree\}")
_COMMIT_EXPRESSION = re.compile(r"(?:HEAD|[0-9a-fA-F]{40})\^\{commit\}")
_CLONE_FLAGS = frozenset({"-q", "--quiet", "--no-hardlinks"})


def _first_symlink(path: pathlib.Path) -> pathlib.Path | None:
    for candidate in reversed((path, *path.parents)):
        if candidate.is_symlink():
            return candidate
    return None


def _git_environment() -> dict[str, str]:
    return {
        key: value for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }


def _validate_git_arguments(arguments: tuple[str, ...]) -> None:
    if not arguments or any(
        not isinstance(argument, str) or not argument or "\x00" in argument
        for argument in arguments
    ):
        raise SourceContextError("Git command arguments must be nonempty strings")


def _canonical_absolute_path(
    value: pathlib.Path | str,
    *,
    label: str,
) -> pathlib.Path:
    if not isinstance(value, (pathlib.Path, str)):
        raise SourceContextError(f"{label} must be an absolute path")
    raw = str(value)
    if (
        not raw.startswith("/")
        or raw.startswith("//")
        or "\\" in raw
        or "\x00" in raw
        or any(part in {"", ".", ".."} for part in raw[1:].split("/"))
    ):
        raise SourceContextError(f"{label} must be an unambiguous absolute path")
    return pathlib.Path(raw)


def _repository_path(
    repository: pathlib.Path | str,
    *,
    label: str = "Git repository",
) -> pathlib.Path:
    path = _canonical_absolute_path(repository, label=label)
    symlink = _first_symlink(path)
    if symlink is not None:
        raise SourceContextError(f"{label} traverses a symlink: {symlink}")
    if not path.is_dir():
        raise SourceContextError(f"{label} must be an existing directory: {path}")
    return path


def _safe_repository_relative_path(value: str) -> bool:
    return (
        not value.startswith("/")
        and "\\" not in value
        and "\x00" not in value
        and ":" not in value
        and all(part not in {"", ".", ".."} for part in value.split("/"))
    )


def _show_object_is_safe(value: str) -> bool:
    revision, separator, path = value.partition(":")
    return (
        separator == ":"
        and _REVISION.fullmatch(revision) is not None
        and _safe_repository_relative_path(path)
    )


def _unsupported_repository_command(arguments: tuple[str, ...]) -> None:
    raise SourceContextError(
        f"unsupported Git command shape or repository override: {arguments!r}"
    )


def _validate_apply_command(arguments: tuple[str, ...]) -> None:
    if (
        len(arguments) != 4
        or arguments[1] not in {"--check", "--index"}
        or arguments[2] != "--whitespace=error-all"
    ):
        _unsupported_repository_command(arguments)
    patch = _canonical_absolute_path(arguments[3], label="Git apply patch")
    symlink = _first_symlink(patch)
    if symlink is not None:
        raise SourceContextError(f"Git apply patch traverses a symlink: {symlink}")
    if not patch.is_file():
        raise SourceContextError(
            f"Git apply patch must be an existing regular file: {patch}"
        )


def _validate_repository_command(arguments: tuple[str, ...]) -> None:
    if arguments == ("status", "--porcelain"):
        return
    if arguments[0] == "rev-parse" and len(arguments) == 2:
        operand = arguments[1]
        if (
            operand in {"--is-bare-repository", "--absolute-git-dir", "--show-toplevel"}
            or _REVISION.fullmatch(operand) is not None
            or _TREE_EXPRESSION.fullmatch(operand) is not None
        ):
            return
    if (
        arguments[0] == "show"
        and len(arguments) == 2
        and _show_object_is_safe(arguments[1])
    ):
        return
    if arguments[0] == "cat-file" and len(arguments) == 3:
        option, operand = arguments[1:]
        if (
            option == "-e" and _COMMIT_EXPRESSION.fullmatch(operand) is not None
            or option == "-p" and _REVISION.fullmatch(operand) is not None
        ):
            return
    if arguments[0] == "apply":
        _validate_apply_command(arguments)
        return
    if arguments == ("write-tree",):
        return
    _unsupported_repository_command(arguments)


def _validate_clone_command(
    arguments: tuple[str, ...],
) -> tuple[pathlib.Path, pathlib.Path]:
    if arguments[0] != "clone":
        raise SourceContextError(
            f"Git command requires an explicit repository: {arguments[0]}"
        )
    remaining = list(arguments[1:])
    flags: list[str] = []
    while remaining and remaining[0] in _CLONE_FLAGS:
        flags.append(remaining.pop(0))
    quiet_flags = flags.count("-q") + flags.count("--quiet")
    if (
        len(remaining) != 2
        or len(flags) != len(set(flags))
        or quiet_flags > 1
    ):
        raise SourceContextError(
            f"controlled clone requires optional quiet/no-hardlinks flags and "
            f"exactly one source and destination: {arguments!r}"
        )

    source = _repository_path(remaining[0], label="controlled clone source")
    destination = _canonical_absolute_path(
        remaining[1], label="controlled clone destination"
    )
    symlink = _first_symlink(destination)
    if symlink is not None:
        raise SourceContextError(
            f"controlled clone destination traverses a symlink: {symlink}"
        )
    if destination.exists():
        raise SourceContextError(
            f"controlled clone destination must not exist: {destination}"
        )
    if not destination.parent.is_dir():
        raise SourceContextError(
            f"controlled clone destination parent must be an existing directory: "
            f"{destination.parent}"
        )
    return source, destination


def _invoke_git(
    command: tuple[str, ...],
    *,
    repository: pathlib.Path | None,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            env=environment,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        if repository is None:
            raise SourceContextError(f"cannot run Git: {exc}") from exc
        raise SourceContextError(f"cannot run Git against {repository}: {exc}") from exc


def _validate_repository_identity(
    repository: pathlib.Path,
    environment: dict[str, str],
    *,
    label: str = "Git repository",
    invocation_repository: pathlib.Path | None = None,
) -> None:
    prefix = ("git", "--no-replace-objects", "-C", str(repository))
    bare = _invoke_git(
        (*prefix, "rev-parse", "--is-bare-repository"),
        repository=invocation_repository,
        environment=environment,
    )
    if bare.returncode != 0:
        raise SourceContextError(f"{label} is not a repository root: {repository}")
    identity_argument = (
        "--absolute-git-dir" if bare.stdout.strip() == b"true" else "--show-toplevel"
    )
    identity = _invoke_git(
        (*prefix, "rev-parse", identity_argument),
        repository=invocation_repository,
        environment=environment,
    )
    if identity.returncode != 0:
        raise SourceContextError(f"{label} is not a repository root: {repository}")
    try:
        identified = pathlib.Path(identity.stdout.decode("utf-8").strip())
    except UnicodeDecodeError as exc:
        raise SourceContextError(f"{label} path is not UTF-8") from exc
    if identified != repository:
        raise SourceContextError(f"{label} is not a repository root: {repository}")


def run_git(
    *arguments: str,
    repository: pathlib.Path | str | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run Git through one scrubbed, replacement-free subprocess boundary."""

    _validate_git_arguments(arguments)
    environment = _git_environment()
    if repository is None:
        source, _ = _validate_clone_command(arguments)
        _validate_repository_identity(
            source,
            environment,
            label="controlled clone source",
            invocation_repository=None,
        )
        return _invoke_git(
            ("git", "--no-replace-objects", *arguments),
            repository=None,
            environment=environment,
        )
    repository_path = _repository_path(repository)
    _validate_repository_command(arguments)
    _validate_repository_identity(
        repository_path,
        environment,
        invocation_repository=repository_path,
    )
    return _invoke_git(
        (
            "git", "--no-replace-objects", "-C", str(repository_path),
            *arguments,
        ),
        repository=repository_path,
        environment=environment,
    )


def add_object_repository_argument(
    parser: argparse.ArgumentParser,
    *,
    default: pathlib.Path | None = None,
) -> None:
    parser.add_argument(
        "--object-repo",
        "--object-repository",
        dest="object_repository",
        type=pathlib.Path,
        default=default,
    )


@dataclasses.dataclass(frozen=True, slots=True)
class SourceContext:
    mode: ValidationMode
    _object_repository: pathlib.Path | None
    pinned_commit: str | None

    @classmethod
    def offline(cls) -> SourceContext:
        return cls(ValidationMode.OFFLINE, None, None)

    @classmethod
    def live(
        cls,
        object_repository: pathlib.Path | str,
        pinned_commit: str,
    ) -> SourceContext:
        repository = pathlib.Path(object_repository)
        if not repository.is_absolute():
            raise SourceContextError("object repository must be an absolute path")
        symlink = _first_symlink(repository)
        if symlink is not None:
            raise SourceContextError(f"object repository traverses a symlink: {symlink}")
        if not repository.is_dir():
            raise SourceContextError(
                f"object repository must be an existing directory: {repository}"
            )
        if _COMMIT.fullmatch(pinned_commit) is None:
            raise SourceContextError(f"pinned commit is unavailable: {pinned_commit}")
        context = cls(ValidationMode.LIVE, repository, pinned_commit)
        context.preflight()
        return context

    @property
    def is_live(self) -> bool:
        return self.mode is ValidationMode.LIVE

    @property
    def object_repository(self) -> pathlib.Path:
        if not self.is_live or self._object_repository is None:
            raise SourceContextError("offline validation attempted live source access")
        return self._object_repository

    def _run_git(self, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        return run_git(*arguments, repository=self.object_repository)

    def git_bytes(self, *arguments: str) -> bytes:
        observed = self._run_git(*arguments)
        if observed.returncode != 0:
            raw_detail = observed.stderr.strip() or observed.stdout.strip()
            detail = raw_detail.decode("utf-8", errors="replace") if raw_detail else "Git command failed"
            raise SourceContextError(
                f"Git read failed in {self.object_repository}: {detail}"
            )
        return observed.stdout

    def git(self, *arguments: str) -> str:
        try:
            return self.git_bytes(*arguments).decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise SourceContextError("Git output is not UTF-8 text; use git_bytes()") from exc

    def preflight(self) -> None:
        repository = self.object_repository
        symlink = _first_symlink(repository)
        if symlink is not None:
            raise SourceContextError(f"object repository traverses a symlink: {symlink}")
        if not repository.is_dir():
            raise SourceContextError(
                f"object repository must be an existing directory: {repository}"
            )
        if self.pinned_commit is None or _COMMIT.fullmatch(self.pinned_commit) is None:
            raise SourceContextError(f"pinned commit is unavailable: {self.pinned_commit}")
        bare = self._run_git("rev-parse", "--is-bare-repository")
        if bare.returncode != 0:
            raise SourceContextError(f"object repository is not a Git repository: {repository}")
        is_bare = bare.stdout.strip() == b"true"
        identity_argument = "--absolute-git-dir" if is_bare else "--show-toplevel"
        identity = self._run_git("rev-parse", identity_argument)
        if identity.returncode != 0:
            raise SourceContextError(f"cannot identify Git object repository: {repository}")
        try:
            identified = pathlib.Path(identity.stdout.decode("utf-8").strip())
        except UnicodeDecodeError as exc:
            raise SourceContextError("Git object-repository path is not UTF-8") from exc
        if identified != repository:
            raise SourceContextError(
                f"explicit path is not the Git object-repository root: {repository}"
            )
        observed = self._run_git("cat-file", "-e", f"{self.pinned_commit}^{{commit}}")
        if observed.returncode != 0:
            raise SourceContextError(f"pinned commit is unavailable: {self.pinned_commit}")
