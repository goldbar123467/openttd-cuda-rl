#!/usr/bin/env python3
"""Mutation tests for active V1 documentation authority lint."""

from __future__ import annotations

import os
import pathlib
import tempfile
import unittest

import lint_project_docs


class V1DocumentLintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]

    def write_navigation_fixture(self, root: pathlib.Path) -> None:
        targets = set(lint_project_docs.REQUIRED_NAVIGATION_TARGETS)
        targets.update(lint_project_docs.PUBLIC_NAVIGATION_TARGETS)
        for relative in targets:
            path = root / relative
            if relative.endswith("/"):
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Document\n", encoding="utf-8")
        (root / "README.md").write_text(
            "# OpenTTD neural-agent development\n\n"
            + "\n".join(
                f"[Read more]({target})" for target in lint_project_docs.PUBLIC_NAVIGATION_TARGETS
            ),
            encoding="utf-8",
        )
        (root / lint_project_docs.INTERNAL_INDEX).write_text(
            "[Preserved README](README_HISTORY_2026-10-02.md)\n", encoding="utf-8"
        )
        archive = root / lint_project_docs.README_HISTORY
        archive.write_text(
            "# Historical navigation\n\n"
            + "\n".join(
                f"[{target}]({pathlib.Path(os.path.relpath(root / target, archive.parent)).as_posix()})"
                for target in lint_project_docs.REQUIRED_NAVIGATION_TARGETS
            ),
            encoding="utf-8",
        )

    def test_repository_documents_pass(self) -> None:
        summary = lint_project_docs.validate(self.root)
        self.assertEqual(summary.accepted_v1_adrs, 7)
        self.assertEqual(summary.legacy_banners, 9)
        self.assertGreaterEqual(summary.active_docs, 18)

    def test_broken_local_link_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            document = root / "doc.md"
            document.write_text("[missing](does-not-exist.md)\n", encoding="utf-8")
            with self.assertRaisesRegex(lint_project_docs.DocLintError, "broken local link"):
                lint_project_docs.check_local_links(root, [document])

    def test_absolute_local_link_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            document = root / "doc.md"
            document.write_text("[host](/tmp/host-only.md)\n", encoding="utf-8")
            with self.assertRaisesRegex(lint_project_docs.DocLintError, "absolute local link"):
                lint_project_docs.check_local_links(root, [document])

    def test_conflicting_active_scope_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            document = root / "doc.md"
            document.write_text(
                "Version 1 begins with a 64 by 64 road-freight fixture.\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                lint_project_docs.DocLintError,
                "conflicting active scope",
            ):
                lint_project_docs.check_scope_conflicts(root, [document])

    def test_missing_legacy_banner_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            document = root / "legacy.md"
            document.write_text("# Old plan\n\nBuild freight first.\n", encoding="utf-8")
            with self.assertRaisesRegex(
                lint_project_docs.DocLintError,
                "lacks an early legacy/supersession notice",
            ):
                lint_project_docs.check_legacy_banner(document, root)

    def test_unaccepted_v1_adr_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            document = root / "0007-test.md"
            document.write_text("# ADR\n\n- Status: Proposed\n", encoding="utf-8")
            with self.assertRaisesRegex(lint_project_docs.DocLintError, "is not accepted"):
                lint_project_docs.check_authority_for_adr(document, root)

    def test_repository_authority_and_current_workflow_are_reachable(self) -> None:
        goal = (self.root / "GOAL.md").read_text(encoding="utf-8")
        self.assertIn("Version 2 active expansion", goal)
        lint_project_docs.check_navigation(self.root)
        readme_targets = lint_project_docs.local_link_targets(self.root, self.root / "README.md")
        self.assertIn(self.root / "GOAL.md", readme_targets)
        self.assertIn(self.root / "docs/DEVELOPMENT.md", readme_targets)

    def test_compact_readme_reaches_rebased_historical_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_navigation_fixture(root)
            # Resolve actual destinations, including titles, anchors and URL escapes.
            archive = root / lint_project_docs.README_HISTORY
            archive.write_text(
                archive.read_text(encoding="utf-8").replace(
                    "(../project/V2_PLAN.md)", '(../project/V2%5FPLAN.md#scope "V2 plan")'
                ),
                encoding="utf-8",
            )
            lint_project_docs.check_navigation(root)

    def test_public_readme_must_reach_each_internal_entry_point(self) -> None:
        for target in (lint_project_docs.INTERNAL_INDEX, lint_project_docs.README_HISTORY):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as raw:
                root = pathlib.Path(raw)
                self.write_navigation_fixture(root)
                readme = root / "README.md"
                readme.write_text(
                    readme.read_text(encoding="utf-8").replace(f"[Read more]({target})", ""),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(lint_project_docs.DocLintError, "README.md navigation omits"):
                    lint_project_docs.check_navigation(root)

    def test_internal_index_must_reach_history(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_navigation_fixture(root)
            (root / lint_project_docs.INTERNAL_INDEX).write_text("# Internal\n", encoding="utf-8")
            with self.assertRaisesRegex(lint_project_docs.DocLintError, "internal/README.md navigation omits"):
                lint_project_docs.check_navigation(root)

    def test_required_target_must_remain_in_internal_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_navigation_fixture(root)
            archive = root / lint_project_docs.README_HISTORY
            link = "[docs/project/V2_PLAN.md](../project/V2_PLAN.md)"
            archive.write_text(archive.read_text(encoding="utf-8").replace(link, ""), encoding="utf-8")
            # Public links alone cannot replace the retained internal ledger.
            with (root / "README.md").open("a", encoding="utf-8") as stream:
                stream.write("\n[Plan](docs/project/V2_PLAN.md)\n")
            with self.assertRaisesRegex(lint_project_docs.DocLintError, "internal navigation omits docs/project/V2_PLAN.md"):
                lint_project_docs.check_navigation(root)
            with (root / lint_project_docs.INTERNAL_INDEX).open("a", encoding="utf-8") as stream:
                stream.write(link + "\n")
            lint_project_docs.check_navigation(root)

    def test_history_links_cannot_be_broken_or_escape_repository(self) -> None:
        for link, error in (
            ("missing.md", "broken local link"),
            ("../../../outside.md", "link escapes repository"),
        ):
            with self.subTest(link=link), tempfile.TemporaryDirectory() as raw:
                root = pathlib.Path(raw)
                self.write_navigation_fixture(root)
                with (root / lint_project_docs.README_HISTORY).open("a", encoding="utf-8") as stream:
                    stream.write(f"\n[Bad destination]({link})\n")
                with self.assertRaisesRegex(lint_project_docs.DocLintError, error):
                    lint_project_docs.check_navigation(root)


if __name__ == "__main__":
    unittest.main()
