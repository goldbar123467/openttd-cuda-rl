#!/usr/bin/env python3
"""Mutation tests for active V1 documentation authority lint."""

from __future__ import annotations

import pathlib
import tempfile
import unittest

import lint_project_docs


class V1DocumentLintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]

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


if __name__ == "__main__":
    unittest.main()
