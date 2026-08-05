#!/usr/bin/env python3
"""Behavior tests for the explicit V2 Git source context."""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from source_context import (
    SourceContext,
    SourceContextError,
    add_object_repository_argument,
)


class V2SourceContextTests(unittest.TestCase):
    def git(self, repository: pathlib.Path, *arguments: str) -> str:
        observed = subprocess.run(
            ("git", "-C", str(repository), *arguments),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(observed.returncode, 0, observed.stderr)
        return observed.stdout.strip()

    def repository(self, root: pathlib.Path, name: str, content: str) -> tuple[pathlib.Path, str]:
        repository = root / name
        repository.mkdir()
        self.git(repository, "init", "-q")
        self.git(repository, "config", "user.email", "task2@example.invalid")
        self.git(repository, "config", "user.name", "Task 2")
        (repository / "tracked.txt").write_text(content, encoding="utf-8")
        self.git(repository, "add", "tracked.txt")
        self.git(repository, "commit", "-qm", "pinned source")
        return repository, self.git(repository, "rev-parse", "HEAD")

    def test_offline_context_never_resolves_an_object_repository(self) -> None:
        context = SourceContext.offline()
        with self.assertRaisesRegex(
            SourceContextError,
            "^offline validation attempted live source access$",
        ):
            _ = context.object_repository
        with self.assertRaisesRegex(
            SourceContextError,
            "^offline validation attempted live source access$",
        ):
            context.git("rev-parse", "HEAD")

    def test_live_context_requires_an_absolute_nonsymlink_git_object_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repository, pin = self.repository(root, "source", "source\n")
            linked = root / "linked-source"
            linked.symlink_to(repository, target_is_directory=True)
            plain = root / "plain"
            plain.mkdir()
            child = repository / "ordinary-child"
            child.mkdir()
            for candidate in (
                pathlib.Path("relative"), linked, plain, child, root / "missing",
            ):
                with self.subTest(candidate=candidate), self.assertRaises(SourceContextError):
                    SourceContext.live(candidate, pin)

    def test_live_context_runs_git_only_against_the_explicit_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            explicit, explicit_pin = self.repository(root, "explicit", "explicit \n\n")
            other, other_pin = self.repository(root, "other", "other\n")
            self.assertNotEqual(explicit_pin, other_pin)
            hostile_git_environment = {
                "GIT_DIR": str(other / ".git"),
                "GIT_WORK_TREE": str(other),
            }
            with mock.patch.dict(os.environ, hostile_git_environment, clear=False):
                context = SourceContext.live(explicit, explicit_pin)
                previous = pathlib.Path.cwd()
                try:
                    os.chdir(other)
                    self.assertEqual(context.git("rev-parse", "HEAD"), explicit_pin)
                    self.assertEqual(context.git("show", "HEAD:tracked.txt"), "explicit")
                    self.assertEqual(
                        context.git_bytes("show", "HEAD:tracked.txt"),
                        b"explicit \n\n",
                    )
                    with self.assertRaisesRegex(SourceContextError, "repository override"):
                        context.git("-C", str(other), "rev-parse", "HEAD")
                finally:
                    os.chdir(previous)

    def test_preflight_rejects_missing_or_wrong_pinned_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            first, first_pin = self.repository(root, "first", "first\n")
            _, other_pin = self.repository(root, "other", "other\n")
            for pin in ("0" * 40, other_pin):
                with self.subTest(pin=pin), self.assertRaisesRegex(
                    SourceContextError, "pinned commit is unavailable",
                ):
                    SourceContext.live(first, pin)
            context = SourceContext.live(first, first_pin)
            context.preflight()

    def test_cli_object_repository_wins_over_the_documented_default(self) -> None:
        parser = argparse.ArgumentParser()
        add_object_repository_argument(parser, default=pathlib.Path("/documented/default"))
        explicit = parser.parse_args(["--object-repo", "/srv/openttd.git"])
        default = parser.parse_args([])
        self.assertEqual(explicit.object_repository, pathlib.Path("/srv/openttd.git"))
        self.assertEqual(default.object_repository, pathlib.Path("/documented/default"))


if __name__ == "__main__":
    unittest.main()
