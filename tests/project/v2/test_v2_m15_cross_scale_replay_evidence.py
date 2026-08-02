#!/usr/bin/env python3
"""Mutation tests for M15 curriculum/generalization exact replay evidence."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import validate_m15_cross_scale_replay_evidence


class M15CrossScaleReplayEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validate_m15_cross_scale_replay_evidence.load_json(cls.root / validate_m15_cross_scale_replay_evidence.CONFIG)
        cls.schema = cls.root / validate_m15_cross_scale_replay_evidence.SCHEMA
        cls.artifact = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl/v2-m15-cross-scale-replay-a")

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "cross-scale.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def mutation_fails(self, value: object, pattern: str | None = None, *, live: bool = False) -> None:
        with tempfile.TemporaryDirectory() as raw:
            context = self.assertRaisesRegex(validate_m15_cross_scale_replay_evidence.M15CrossScaleReplayEvidenceError, pattern) if pattern else self.assertRaises(validate_m15_cross_scale_replay_evidence.M15CrossScaleReplayEvidenceError)
            with context:
                validate_m15_cross_scale_replay_evidence.validate(
                    self.root, self.write(pathlib.Path(raw), value), self.schema,
                    artifact_root=self.artifact if live else None,
                )

    def test_repository_evidence_passes(self) -> None:
        summary = validate_m15_cross_scale_replay_evidence.validate(self.root)
        self.assertEqual((summary.cases, summary.runs, summary.maximum_rss_kib), (9, 18, 90916))

    def test_live_artifacts_pass(self) -> None:
        if not self.artifact.is_dir(): self.skipTest("retained cross-scale replay is unavailable")
        summary = validate_m15_cross_scale_replay_evidence.validate(self.root, artifact_root=self.artifact)
        self.assertTrue(summary.live)

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config); value["schema_sha256"] = "0" * 64
        self.mutation_fails(value, "schema SHA-256")

    def test_case_omission_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"].pop()
        self.mutation_fails(value)

    def test_generalization_rectangle_drift_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][4]["height"] = 128
        self.mutation_fails(value, "case inventory")

    def test_seed_leakage_fails(self) -> None:
        value = copy.deepcopy(self.config); value["cases"][0]["seed"] = 484178880
        self.mutation_fails(value, "case inventory")

    def test_matrix_digest_drift_fails_live(self) -> None:
        if not self.artifact.is_dir(): self.skipTest("retained cross-scale replay is unavailable")
        value = copy.deepcopy(self.config); value["matrix_run_sha256"] = "0" * 64
        self.mutation_fails(value, "matrix-run digest", live=True)

    def test_capture_digest_drift_fails_live(self) -> None:
        if not self.artifact.is_dir(): self.skipTest("retained cross-scale replay is unavailable")
        value = copy.deepcopy(self.config); value["cases"][8]["candidate_sha256"] = "1" * 64
        self.mutation_fails(value, "candidate_sha256", live=True)


if __name__ == "__main__":
    unittest.main()
