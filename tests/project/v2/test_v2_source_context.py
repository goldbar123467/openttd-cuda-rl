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

import source_context
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

    def test_live_context_ignores_repository_replacement_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repository, pinned = self.repository(root, "source", "original pinned bytes\n")
            (repository / "tracked.txt").write_text("replacement bytes\n", encoding="utf-8")
            self.git(repository, "add", "tracked.txt")
            self.git(repository, "commit", "-qm", "replacement source")
            replacement = self.git(repository, "rev-parse", "HEAD")
            self.git(repository, "replace", pinned, replacement)

            context = SourceContext.live(repository, pinned)

            self.assertEqual(
                context.git_bytes("show", f"{pinned}:tracked.txt"),
                b"original pinned bytes\n",
            )

    def test_run_git_repository_scope_scrubs_hostile_git_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            explicit, explicit_pin = self.repository(root, "explicit", "explicit \n\n")
            other, _ = self.repository(root, "other", "other\n")
            with mock.patch.dict(os.environ, {
                "GIT_DIR": str(other / ".git"),
                "GIT_WORK_TREE": str(other),
            }, clear=False):
                revision = source_context.run_git(
                    "rev-parse", "HEAD", repository=explicit,
                )
                content = source_context.run_git(
                    "show", "HEAD:tracked.txt", repository=explicit,
                )

            self.assertEqual(revision.returncode, 0)
            self.assertEqual(revision.stdout, f"{explicit_pin}\n".encode("ascii"))
            self.assertEqual(revision.stderr, b"")
            self.assertEqual(content.returncode, 0)
            self.assertEqual(content.stdout, b"explicit \n\n")
            self.assertIsInstance(content.stderr, bytes)

    def test_run_git_disables_replace_refs_for_rev_parse_show_and_cat_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repository, pinned = self.repository(root, "source", "original pinned bytes\n")
            original_tree = self.git(repository, "rev-parse", f"{pinned}^{{tree}}")
            original_commit = subprocess.run(
                ("git", "-C", str(repository), "cat-file", "-p", pinned),
                capture_output=True,
                check=True,
            ).stdout
            (repository / "tracked.txt").write_text("replacement bytes\n", encoding="utf-8")
            self.git(repository, "add", "tracked.txt")
            self.git(repository, "commit", "-qm", "replacement source")
            replacement = self.git(repository, "rev-parse", "HEAD")
            self.git(repository, "replace", pinned, replacement)

            tree = source_context.run_git(
                "rev-parse", f"{pinned}^{{tree}}", repository=repository,
            )
            shown = source_context.run_git(
                "show", f"{pinned}:tracked.txt", repository=repository,
            )
            commit = source_context.run_git(
                "cat-file", "-p", pinned, repository=repository,
            )

            self.assertEqual(tree.stdout, f"{original_tree}\n".encode("ascii"))
            self.assertEqual(shown.stdout, b"original pinned bytes\n")
            self.assertEqual(commit.stdout, original_commit)
            self.assertEqual((tree.returncode, shown.returncode, commit.returncode), (0, 0, 0))

    def test_run_git_clone_and_apply_share_the_scrubbed_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            source, _ = self.repository(root, "source", "base\n")
            other, _ = self.repository(root, "other", "other\n")
            target = root / "target"
            patch = root / "change.patch"
            patch.write_text(
                "diff --git a/tracked.txt b/tracked.txt\n"
                "--- a/tracked.txt\n"
                "+++ b/tracked.txt\n"
                "@@ -1 +1 @@\n"
                "-base\n"
                "+patched\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {
                "GIT_DIR": str(other / ".git"),
                "GIT_WORK_TREE": str(other),
            }, clear=False):
                cloned = source_context.run_git(
                    "clone", "-q", "--no-hardlinks", str(source), str(target),
                )
                checked = source_context.run_git(
                    "apply", "--check", "--whitespace=error-all", str(patch),
                    repository=target,
                )
                applied = source_context.run_git(
                    "apply", "--index", "--whitespace=error-all", str(patch),
                    repository=target,
                )
                tree = source_context.run_git("write-tree", repository=target)

            self.assertEqual(
                (cloned.returncode, checked.returncode, applied.returncode, tree.returncode),
                (0, 0, 0, 0),
            )
            self.assertTrue(all(
                isinstance(stream, bytes)
                for result in (cloned, checked, applied, tree)
                for stream in (result.stdout, result.stderr)
            ))
            self.assertEqual((target / "tracked.txt").read_bytes(), b"patched\n")
            self.assertRegex(tree.stdout, rb"^[0-9a-f]{40}\n$")

    def test_run_git_rejects_repository_mutation_and_unsupported_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repository, pinned = self.repository(root, "source", "source\n")
            isolated_home = root / "isolated-home"
            isolated_home.mkdir()
            rejected = (
                ("config", "--global", "task2.escape", "written"),
                ("config", "--system", "--get", "task2.escape"),
                ("config", "--local", "task2.escape", "written"),
                ("branch", "escape"),
                ("status", "--porcelain", "extra"),
                ("rev-parse", "HEAD", "extra"),
                ("show", "HEAD:tracked.txt", "extra"),
                ("cat-file", "-p", pinned, "extra"),
                ("write-tree", "extra"),
                ("status", "--global", "--porcelain"),
            )

            with mock.patch.dict(os.environ, {"HOME": str(isolated_home)}, clear=False):
                for arguments in rejected:
                    with self.subTest(arguments=arguments), self.assertRaisesRegex(
                        SourceContextError,
                        "unsupported Git command shape",
                    ):
                        source_context.run_git(*arguments, repository=repository)

            self.assertFalse((isolated_home / ".gitconfig").exists())
            self.assertNotIn("task2.escape", (repository / ".git/config").read_text())

    def test_run_git_apply_requires_exact_options_and_safe_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repository, _ = self.repository(root, "source", "base\n")
            patch = root / "change.patch"
            patch.write_text(
                "diff --git a/tracked.txt b/tracked.txt\n"
                "--- a/tracked.txt\n"
                "+++ b/tracked.txt\n"
                "@@ -1 +1 @@\n"
                "-base\n"
                "+patched\n",
                encoding="utf-8",
            )
            linked_patch = root / "linked.patch"
            linked_patch.symlink_to(patch)
            patch_directory = root / "patch-directory"
            patch_directory.mkdir()
            rejected = (
                ("apply", "--unsafe-paths", "--check", "--whitespace=error-all", str(patch)),
                ("apply", "--check", "--directory=../escape", "--whitespace=error-all", str(patch)),
                ("apply", "--check", "--whitespace=error-all", "relative.patch"),
                ("apply", "--check", "--whitespace=error-all", str(linked_patch)),
                ("apply", "--check", "--whitespace=error-all", str(patch_directory)),
                ("apply", "--check", "--whitespace=error-all", f"{root}/./change.patch"),
                ("apply", "--check", "--whitespace=error-all", str(patch), str(patch)),
                ("apply", "--check", str(patch)),
            )

            for arguments in rejected:
                with self.subTest(arguments=arguments), self.assertRaisesRegex(
                    SourceContextError,
                    "unsupported Git command shape|patch",
                ):
                    source_context.run_git(*arguments, repository=repository)

    def test_run_git_clone_requires_exact_absolute_source_and_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            source, _ = self.repository(root, "source", "source\n")
            source_child = source / "ordinary-child"
            source_child.mkdir()
            linked_source = root / "linked-source"
            linked_source.symlink_to(source, target_is_directory=True)
            nonrepository = root / "nonrepository"
            nonrepository.mkdir()
            existing_destination = root / "existing-destination"
            existing_destination.mkdir()
            linked_destination = root / "linked-destination"
            linked_destination.symlink_to(root / "missing-destination")
            real_parent = root / "real-parent"
            real_parent.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            rejected = (
                ("clone", ".", str(root / "ambient-target")),
                ("clone", str(source_child), str(root / "child-target")),
                ("clone", str(linked_source), str(root / "linked-source-target")),
                ("clone", str(nonrepository), str(root / "nonrepository-target")),
                ("clone", f"{source}/.", str(root / "ambiguous-source-target")),
                ("clone", str(source), "relative-target"),
                ("clone", str(source), str(existing_destination)),
                ("clone", str(source), str(linked_destination)),
                ("clone", str(source), str(linked_parent / "target")),
                ("clone", str(source), str(root / "missing-parent/target")),
                ("clone", str(source), f"{root}/./ambiguous-target"),
                ("clone", "--shared", str(source), str(root / "shared-target")),
                ("clone", str(source), str(root / "extra-target"), "extra"),
            )

            previous = pathlib.Path.cwd()
            try:
                os.chdir(source)
                for arguments in rejected:
                    with self.subTest(arguments=arguments), self.assertRaisesRegex(
                        SourceContextError,
                        "controlled clone",
                    ):
                        source_context.run_git(*arguments)
            finally:
                os.chdir(previous)

    def test_run_git_rejects_scope_overrides_and_ambient_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repository, _ = self.repository(root, "source", "source\n")
            other, _ = self.repository(root, "other", "other\n")
            forbidden = (
                ("-C", str(other), "status"),
                (f"-C{other}", "status"),
                ("--git-dir", str(other / ".git"), "status"),
                (f"--git-dir={other / '.git'}", "status"),
                ("--work-tree", str(other), "status"),
                (f"--work-tree={other}", "status"),
                ("--namespace=other", "status"),
                ("--bare", "status"),
            )
            for arguments in forbidden:
                with self.subTest(arguments=arguments), self.assertRaisesRegex(
                    SourceContextError, "repository override",
                ):
                    source_context.run_git(*arguments, repository=repository)
            with self.assertRaisesRegex(SourceContextError, "requires an explicit repository"):
                source_context.run_git("status", "--porcelain")

    def test_run_git_validates_repository_and_reports_oserror_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            repository, _ = self.repository(root, "source", "source\n")
            linked = root / "linked"
            linked.symlink_to(repository, target_is_directory=True)
            plain_file = root / "plain-file"
            plain_file.write_text("not a repository\n", encoding="utf-8")
            for candidate in (
                pathlib.Path("relative"), linked, root / "missing", plain_file,
            ):
                with self.subTest(candidate=candidate), self.assertRaises(SourceContextError):
                    source_context.run_git("status", repository=candidate)
            with mock.patch.object(
                source_context.subprocess,
                "run",
                side_effect=OSError("Git executable unavailable"),
            ), self.assertRaisesRegex(
                SourceContextError,
                "^cannot run Git: Git executable unavailable$",
            ):
                source_context.run_git("clone", str(repository), str(root / "target"))

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
