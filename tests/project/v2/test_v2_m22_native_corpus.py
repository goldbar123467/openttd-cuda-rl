#!/usr/bin/env python3
"""Mutation tests for the frozen M22 native-qualified corpus."""

from __future__ import annotations

import copy
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from artifact_context import ArtifactContext
import build_m22_native_corpus as builder
import validate_m22_native_corpus as validator


class M22NativeCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.corpus = validator.load(cls.root / validator.CORPUS)
        cls.contract = validator.load(cls.root / validator.CONTRACT)

    def mutation_fails(self, value: object, pattern: str | None = None) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            corpus_path = directory / "corpus.json"
            corpus_path.write_bytes(validator.canonical(value))
            contract = copy.deepcopy(self.contract)
            contract["identities"]["m22_native_corpus_sha256"] = validator.sha256(corpus_path)
            contract_path = directory / "contract.json"
            contract_path.write_bytes(validator.canonical(contract))
            context = (self.assertRaisesRegex(validator.M22CorpusValidationError, pattern)
                       if pattern else self.assertRaises(validator.M22CorpusValidationError))
            with context:
                validator.validate(self.root, corpus_path, contract_path)

    def test_repository_corpus_passes(self) -> None:
        summary = validator.validate(self.root)
        self.assertEqual((summary.entries, summary.training, summary.development, summary.programs, summary.native_gates),
                         (32, 16, 16, 17, 7))

    def test_exact_rebuild_is_offline_even_when_recorded_artifacts_exist(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            live_root = pathlib.Path(raw).resolve()
            for logical_set in (
                "v2-m15-competence-a",
                "v2-m16-cargo-a",
                "v2-m17-rail-a",
                "v2-m18-ship-a",
                "v2-m19-air-matrix-a",
                "v2-m20-competition-matrix-f",
                "v2-m21-broad-f",
            ):
                artifact_set = live_root / logical_set
                artifact_set.mkdir()
                (artifact_set / "poison-retained-artifact").write_text(
                    "must not be read\n", encoding="utf-8"
                )
            with mock.patch.object(
                ArtifactContext,
                "preflight",
                side_effect=AssertionError("exact rebuild traversed live artifacts"),
            ):
                rebuilt = builder.build(
                    self.root,
                    artifact_context=ArtifactContext.live(live_root),
                )
        self.assertEqual(rebuilt, self.corpus)

    def test_builder_and_validator_clis_accept_common_root_but_rebuild_offline(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw).resolve()
            output = directory / "rebuilt.json"
            build = subprocess.run(
                [
                    "python3", str(self.root / "scripts/v2/build_m22_native_corpus.py"),
                    "--root", str(self.root), "--output", str(output),
                    "--artifact-root", str(directory),
                ],
                cwd=self.root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            self.assertEqual(output.read_bytes(), validator.canonical(self.corpus))
            validate = subprocess.run(
                [
                    "python3", str(self.root / "scripts/v2/validate_m22_native_corpus.py"),
                    "--root", str(self.root), "--artifact-root", str(directory),
                ],
                cwd=self.root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(validate.returncode, 0, validate.stderr)

    def test_native_corpus_cli_rejects_relative_artifact_root(self) -> None:
        completed = subprocess.run(
            [
                "python3", str(self.root / "scripts/v2/validate_m22_native_corpus.py"),
                "--root", str(self.root), "--artifact-root", "relative",
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("artifact root must be an absolute path", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_native_corpus_cli_explicit_root_precedes_environment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            explicit = pathlib.Path(raw).resolve()
            environment = dict(os.environ)
            environment["OPENTTD_RL_ARTIFACT_ROOT"] = "relative-hostile-root"
            completed = subprocess.run(
                [
                    "python3", str(self.root / "scripts/v2/validate_m22_native_corpus.py"),
                    "--root", str(self.root), "--artifact-root", str(explicit),
                ],
                cwd=self.root,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_schema_hash_mutation_fails(self) -> None:
        value = copy.deepcopy(self.corpus)
        value["schema_sha256"] = "0" * 64
        self.mutation_fails(value, "schema SHA-256")

    def test_source_identity_mutation_fails(self) -> None:
        value = copy.deepcopy(self.corpus)
        value["sources"][0]["sha256"] = "0" * 64
        self.mutation_fails(value, "exactly rebuild")

    def test_native_reward_mutation_fails(self) -> None:
        value = copy.deepcopy(self.corpus)
        value["entries"][0]["rewards"]["road-passenger"] += 0.25
        self.mutation_fails(value, "exactly rebuild")

    def test_public_state_label_leak_mutation_fails(self) -> None:
        value = copy.deepcopy(self.corpus)
        value["entries"][0]["public_state"]["required_program"] = "road-passenger"
        self.mutation_fails(value, "exactly rebuild")

    def test_final_split_mutation_fails(self) -> None:
        value = copy.deepcopy(self.corpus)
        value["entries"][0]["split"] = "final"
        self.mutation_fails(value)


if __name__ == "__main__":
    unittest.main()
