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
_REPOSITORY_OVERRIDES = ("--git-dir", "--work-tree", "--namespace", "--bare")


def _first_symlink(path: pathlib.Path) -> pathlib.Path | None:
    for candidate in reversed((path, *path.parents)):
        if candidate.is_symlink():
            return candidate
    return None


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
        repository = self.object_repository
        if any(
            argument.startswith("-C")
            or argument == option
            or argument.startswith(f"{option}=")
            for argument in arguments
            for option in _REPOSITORY_OVERRIDES
        ):
            raise SourceContextError("Git repository override arguments are forbidden")
        environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith("GIT_")
        }
        try:
            return subprocess.run(
                ("git", "-C", str(repository), *arguments),
                env=environment,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            raise SourceContextError(f"cannot run Git against {repository}: {exc}") from exc

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
