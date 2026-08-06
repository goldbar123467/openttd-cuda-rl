#!/usr/bin/env python3
"""Isolation, caching, and authority tests for shared M23 fixtures."""

from __future__ import annotations

import copy
import hashlib
import os
import pathlib
import tempfile
import unittest
from unittest import mock

import m23_golden
import m23_ingame
import m23_package
import validate_m23_release_contract as contract_validator
from tests.project.v2 import m23_fixture_support as fixtures


class _DecodeReached(RuntimeError):
    """Sentinel proving the full file authority reached golden decode."""


class M23FixtureSupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract = contract_validator.load(cls.root / contract_validator.CONTRACT)
        cls.architecture = contract_validator.ARCHITECTURES[0]
        cls.model_shas = {
            "monolithic_sha256": "1" * 64,
            "specialist_sha256": "2" * 64,
        }

    def complete_records(self) -> tuple[m23_golden.GoldenRecord, ...]:
        return (
            *fixtures.make_golden_records(0),
            *fixtures.make_golden_records(1),
        )

    def package_report(self) -> dict[str, object]:
        return {
            "deployment_packages": [
                {"model_sha256": self.model_shas["monolithic_sha256"]},
                {"model_sha256": self.model_shas["specialist_sha256"]},
            ],
        }

    def test_golden_records_and_binary_are_cached_immutable_values(self) -> None:
        mechanics = fixtures
        records = mechanics.make_golden_records(0)
        binary = mechanics.make_golden_binary()

        self.assertIs(records, mechanics.make_golden_records(0))
        self.assertIs(binary, mechanics.make_golden_binary())
        self.assertIsInstance(records, tuple)
        self.assertIsInstance(records[0].definition.public_features, tuple)
        self.assertIsInstance(records[0].program_logits, tuple)
        with self.assertRaises(TypeError):
            records[0].program_logits[0] = 1.0

        with tempfile.TemporaryDirectory() as raw:
            golden = (pathlib.Path(raw) / "golden.bin").resolve()
            golden.write_bytes(binary)
            decoded = m23_golden.decode(golden)
        self.assertEqual(len(decoded), 48)
        self.assertEqual(sum(item.definition.batch for item in decoded), 580)

    def test_package_clone_is_independent_and_requires_a_new_target(self) -> None:
        mechanics = fixtures
        with tempfile.TemporaryDirectory() as raw:
            temporary = pathlib.Path(raw).resolve()
            base_parent = temporary / "base"
            clone_parent = temporary / "clone"
            base_parent.mkdir()
            clone_parent.mkdir()
            base = mechanics.make_package(
                base_parent,
                self.root,
                self.contract,
                self.architecture,
                mechanics.make_golden_records(0),
            )
            before = mechanics.snapshot_tree(base)
            clone = mechanics.clone_package(base, clone_parent)

            self.assertEqual(mechanics.snapshot_tree(clone), before)
            for relative, _digest in before:
                base_stat = os.stat(base / relative, follow_symlinks=False)
                clone_stat = os.stat(clone / relative, follow_symlinks=False)
                self.assertNotEqual(
                    (base_stat.st_dev, base_stat.st_ino),
                    (clone_stat.st_dev, clone_stat.st_ino),
                    relative,
                )

            (clone / "INSTALL.md").write_bytes(b"mutated\n")
            self.assertEqual(mechanics.snapshot_tree(base), before)
            with self.assertRaises((FileExistsError, ValueError)):
                mechanics.clone_package(base, clone_parent)

    def test_package_factory_rejects_target_reuse_and_symlink_parent(self) -> None:
        mechanics = fixtures
        with tempfile.TemporaryDirectory() as raw:
            temporary = pathlib.Path(raw).resolve()
            parent = temporary / "packages"
            parent.mkdir()
            records = mechanics.make_golden_records(0)
            mechanics.make_package(
                parent, self.root, self.contract, self.architecture, records,
            )
            with self.assertRaises((FileExistsError, ValueError)):
                mechanics.make_package(
                    parent, self.root, self.contract, self.architecture, records,
                )

            linked_parent = temporary / "linked-packages"
            linked_parent.symlink_to(parent, target_is_directory=True)
            with self.assertRaises(ValueError):
                mechanics.make_package(
                    linked_parent,
                    self.root,
                    self.contract,
                    self.architecture,
                    records,
                )

    def test_snapshot_tree_rejects_file_and_directory_symlinks(self) -> None:
        mechanics = fixtures
        for label in ("file", "directory"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                root = pathlib.Path(raw).resolve()
                (root / "plain").write_bytes(b"plain\n")
                if label == "file":
                    (root / "linked").symlink_to("plain")
                else:
                    target = root / "target"
                    target.mkdir()
                    (target / "nested").write_bytes(b"nested\n")
                    (root / "linked").symlink_to(target, target_is_directory=True)
                with self.assertRaises(ValueError):
                    mechanics.snapshot_tree(root)

    def test_equivalence_reports_are_fresh_and_copies_do_not_alias(self) -> None:
        mechanics = fixtures
        model_shas = dict(self.model_shas)
        records = self.complete_records()
        golden_sha256 = hashlib.sha256(mechanics.make_golden_binary()).hexdigest()

        first = mechanics.make_equivalence_report(
            records,
            golden_sha256=golden_sha256,
            runtime=m23_ingame.INGAME_RUNTIME,
            model_shas=model_shas,
        )
        second = mechanics.make_equivalence_report(
            records,
            golden_sha256=golden_sha256,
            runtime=m23_ingame.INGAME_RUNTIME,
            model_shas=model_shas,
        )
        copied = copy.deepcopy(first)
        copied["cases"][0]["action_exact"] = False
        copied["models"]["monolithic_sha256"] = "0" * 64

        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertIsNot(first["cases"], second["cases"])
        self.assertTrue(first["cases"][0]["action_exact"])
        self.assertEqual(first["models"], model_shas)
        self.assertEqual(model_shas, self.model_shas)

    def test_semantic_value_validation_never_decodes_golden_data(self) -> None:
        mechanics = fixtures
        validator = getattr(m23_ingame, "validate_equivalence_value", None)
        self.assertTrue(callable(validator), "semantic equivalence validator is missing")
        records = self.complete_records()
        golden_sha256 = hashlib.sha256(mechanics.make_golden_binary()).hexdigest()
        value = mechanics.make_equivalence_report(
            records,
            golden_sha256=golden_sha256,
            runtime=m23_ingame.INGAME_RUNTIME,
            model_shas=self.model_shas,
        )
        with mock.patch.object(
            m23_golden, "decode", side_effect=AssertionError("unexpected decode"),
        ):
            summary = validator(
                copy.deepcopy(value),
                m23_ingame.INGAME_RUNTIME,
                golden_sha256,
                records,
                self.package_report(),
            )
        self.assertEqual(len(summary["cases"]), 48)

    def test_full_file_validation_is_canonical_and_always_decodes(self) -> None:
        mechanics = fixtures
        records = self.complete_records()
        binary = mechanics.make_golden_binary()
        golden_sha256 = hashlib.sha256(binary).hexdigest()
        value = mechanics.make_equivalence_report(
            records,
            golden_sha256=golden_sha256,
            runtime=m23_ingame.INGAME_RUNTIME,
            model_shas=self.model_shas,
        )
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw).resolve()
            golden = root / "golden.bin"
            report = root / "report.json"
            golden.write_bytes(binary)
            report.write_bytes(m23_package.canonical_json(value, newline=True))
            with mock.patch.object(
                m23_golden, "decode", side_effect=_DecodeReached("decode reached"),
            ), self.assertRaisesRegex(_DecodeReached, "decode reached"):
                m23_ingame.validate_equivalence_report(
                    report,
                    m23_ingame.INGAME_RUNTIME,
                    golden,
                    self.package_report(),
                )

            report.write_text(
                m23_package.canonical_json(value).decode("ascii") + " \n",
                encoding="ascii",
            )
            with self.assertRaisesRegex(m23_ingame.M23InGameError, "canonical"):
                m23_ingame.validate_equivalence_report(
                    report,
                    m23_ingame.INGAME_RUNTIME,
                    golden,
                    self.package_report(),
                )


if __name__ == "__main__":
    unittest.main()
