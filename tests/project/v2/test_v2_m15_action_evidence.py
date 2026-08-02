#!/usr/bin/env python3
"""Mutation tests for frozen M15 hierarchical-action evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import shutil
import tempfile
import unittest

import freeze_m15_action_evidence
import qualify_m15_action


class M15ActionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = freeze_m15_action_evidence.load_json(cls.root / freeze_m15_action_evidence.CONFIG)
        cls.schema = cls.root / freeze_m15_action_evidence.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "action-evidence.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def test_repository_evidence_passes(self) -> None:
        summary = freeze_m15_action_evidence.validate(self.root)
        self.assertEqual((summary.map_cases, summary.action_cases, summary.passed), (4, 10, 14))
        self.assertGreaterEqual(summary.maximum_rss_kib, 1)

    def test_live_artifacts_pass(self) -> None:
        artifact_base = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl")
        if not (artifact_base / "v2-m15-action-evidence-a").is_dir():
            self.skipTest("retained action artifacts are unavailable")
        self.assertTrue(freeze_m15_action_evidence.validate(self.root, artifact_base=artifact_base).live)

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_action_evidence.M15ActionEvidenceError, "schema SHA-256"):
                freeze_m15_action_evidence.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_deterministic_binary_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["map_cases"][0]["candidate_binary_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_action_evidence.M15ActionEvidenceError, "deterministic lock"):
                freeze_m15_action_evidence.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_negative_mutation_claim_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["action_cases"][-1]["mutated"] = True
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_action_evidence.M15ActionEvidenceError, "negative action invariant"):
                freeze_m15_action_evidence.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_live_candidate_binary_corruption_fails(self) -> None:
        artifact_base = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl")
        source_root = artifact_base / "v2-m15-action-evidence-a"
        if not source_root.is_dir():
            self.skipTest("retained action artifacts are unavailable")
        with tempfile.TemporaryDirectory() as raw:
            target_root = pathlib.Path(raw) / "v2-m15-action-evidence-a"
            source_case = source_root / "reset-0064x0064"
            target_case = target_root / "reset-0064x0064"
            shutil.copytree(source_case, target_case)
            binary = target_case / qualify_m15_action.CANDIDATE_BINARY_NAME
            data = bytearray(binary.read_bytes())
            data[0] ^= 1
            binary.write_bytes(data)
            with self.assertRaisesRegex(qualify_m15_action.M15ActionError, "SHA-256"):
                freeze_m15_action_evidence.map_case_from_artifact(self.root, target_root, "reset-0064x0064")


if __name__ == "__main__":
    unittest.main()
