#!/usr/bin/env python3
"""Mutation tests for M15 lifecycle and replay evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import shutil
import tempfile
import unittest

import freeze_m15_episode_evidence


class M15EpisodeEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = freeze_m15_episode_evidence.load_json(cls.root / freeze_m15_episode_evidence.CONFIG)
        cls.schema = cls.root / freeze_m15_episode_evidence.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "episode-evidence.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def test_repository_evidence_passes(self) -> None:
        summary = freeze_m15_episode_evidence.validate(self.root)
        self.assertEqual((summary.runs, summary.transitions, summary.families), (2, 16, 12))

    def test_live_artifacts_pass(self) -> None:
        artifact_base = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl")
        if not (artifact_base / "v2-m15-episode-evidence-a").is_dir():
            self.skipTest("retained episode artifacts are unavailable")
        self.assertTrue(freeze_m15_episode_evidence.validate(self.root, artifact_base=artifact_base).live)

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_episode_evidence.M15EpisodeEvidenceError, "schema SHA-256"):
                freeze_m15_episode_evidence.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_rollback_claim_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["runs"][0]["rollback"]["state_exact"] = False
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(freeze_m15_episode_evidence.M15EpisodeEvidenceError):
                freeze_m15_episode_evidence.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_deterministic_trace_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["runs"][1]["trace_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(freeze_m15_episode_evidence.M15EpisodeEvidenceError, "deterministic trace"):
                freeze_m15_episode_evidence.validate(self.root, self.write(pathlib.Path(raw), value), self.schema)

    def test_live_capture_binary_corruption_fails(self) -> None:
        source = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m15-episode-evidence-a")
        if not source.is_dir():
            self.skipTest("retained episode artifacts are unavailable")
        with tempfile.TemporaryDirectory() as raw:
            target = pathlib.Path(raw) / "evidence"
            shutil.copytree(source / "run-a", target / "run-a")
            binary = target / "run-a/artifacts/capture-branch-a-candidates.bin"
            data = bytearray(binary.read_bytes())
            data[0] ^= 1
            binary.write_bytes(data)
            with self.assertRaisesRegex(freeze_m15_episode_evidence.M15EpisodeEvidenceError, "capture candidates"):
                freeze_m15_episode_evidence.project_run(self.root, target, "run-a")


if __name__ == "__main__":
    unittest.main()
