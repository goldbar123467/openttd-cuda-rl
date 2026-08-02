#!/usr/bin/env python3
"""Mutation tests for retained M15 scalable policy evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_m15_policy_evidence


class M15PolicyEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validate_m15_policy_evidence.load_json(cls.root / validate_m15_policy_evidence.CONFIG)
        cls.schema = cls.root / validate_m15_policy_evidence.SCHEMA
        cls.artifact = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m15-policy-a")

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "policy-evidence.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None, *, live: bool = False) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validate_m15_policy_evidence.M15PolicyEvidenceError, pattern) if pattern else self.assertRaises(validate_m15_policy_evidence.M15PolicyEvidenceError)
            with context:
                validate_m15_policy_evidence.validate(
                    self.root, self.write(pathlib.Path(raw), value), self.schema,
                    artifact_root=self.artifact if live else None,
                )

    def test_repository_evidence_passes(self) -> None:
        summary = validate_m15_policy_evidence.validate(self.root)
        self.assertEqual((summary.files, summary.devices, summary.parameters), (6, 2, 1239406))

    def test_live_source_and_artifact_pass(self) -> None:
        source = self.artifact / "source"
        if not source.is_dir() or not self.artifact.is_dir():
            self.skipTest("retained policy artifact is unavailable")
        summary = validate_m15_policy_evidence.validate(self.root, source_artifact=source, artifact_root=self.artifact)
        self.assertTrue(summary.live_source and summary.live_artifact)

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config); value["schema_sha256"] = "0" * 64
        self.mutation_fails(value, "schema SHA-256")

    def test_source_digest_drift_fails(self) -> None:
        value = copy.deepcopy(self.config); value["source"]["files"][0]["sha256"] = "0" * 64
        self.mutation_fails(value, "repository policy source")

    def test_device_omission_fails(self) -> None:
        value = copy.deepcopy(self.config); value["runs"].pop()
        self.mutation_fails(value)

    def test_report_digest_drift_fails_live(self) -> None:
        if not self.artifact.is_dir(): self.skipTest("retained policy artifact is unavailable")
        value = copy.deepcopy(self.config); value["runs"][0]["report_sha256"] = "0" * 64
        self.mutation_fails(value, "policy report drifted", live=True)

    def test_executable_digest_drift_fails_live(self) -> None:
        if not self.artifact.is_dir(): self.skipTest("retained policy artifact is unavailable")
        value = copy.deepcopy(self.config); value["build"]["executable"]["sha256"] = "0" * 64
        self.mutation_fails(value, "executable SHA-256", live=True)


if __name__ == "__main__":
    unittest.main()
