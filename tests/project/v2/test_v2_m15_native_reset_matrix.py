#!/usr/bin/env python3
"""Mutation tests for the complete source-integrated M15 reset matrix."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import run_m15_native_reset_matrix


class M15NativeResetMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.evidence = run_m15_native_reset_matrix.load_json(cls.root / run_m15_native_reset_matrix.EVIDENCE)
        cls.schema = cls.root / run_m15_native_reset_matrix.SCHEMA
        cls.artifact_base = pathlib.Path("/home/thecl/.codex/artifacts/openttd-rl")

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "matrix.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def validate_mutation(self, directory: pathlib.Path, value: object) -> run_m15_native_reset_matrix.M15NativeResetMatrixSummary:
        return run_m15_native_reset_matrix.validate(self.root, self.write(directory, value), self.schema)

    def test_repository_complete_matrix_passes(self) -> None:
        summary = run_m15_native_reset_matrix.validate(self.root)
        self.assertEqual((summary.rectangles, summary.generated, summary.preflight_rejected), (49, 39, 10))

    def test_live_complete_matrix_passes(self) -> None:
        if not (self.artifact_base / self.evidence["artifact_root"]).is_dir():
            self.skipTest("retained complete reset matrix is unavailable")
        summary = run_m15_native_reset_matrix.validate(self.root, artifact_base=self.artifact_base)
        self.assertTrue(summary.live)

    def test_missing_rectangle_fails_schema(self) -> None:
        value = copy.deepcopy(self.evidence)
        value["results"].pop()
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(run_m15_native_reset_matrix.M15NativeResetMatrixError, "schema"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_reordered_rectangle_fails(self) -> None:
        value = copy.deepcopy(self.evidence)
        value["results"][0], value["results"][1] = value["results"][1], value["results"][0]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(run_m15_native_reset_matrix.M15NativeResetMatrixError, "order/coverage"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_in_budget_cannot_claim_preflight(self) -> None:
        value = copy.deepcopy(self.evidence)
        value["results"][0] = run_m15_native_reset_matrix.preflight_result(64, 64)
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(run_m15_native_reset_matrix.M15NativeResetMatrixError, "generated outcome"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_above_budget_cannot_claim_generation(self) -> None:
        value = copy.deepcopy(self.evidence)
        row = next(item for item in value["results"] if item["outcome"] == "PREFLIGHT_REJECTED")
        row["outcome"] = "GENERATED"
        row["reason_code"] = None
        row["artifact_dir"] = "invented"
        row["manifest_sha256"] = row["projection_sha256"] = row["evidence_sha256"] = row["transcript_sha256"] = "0" * 64
        row["towns"] = 128
        row["industries"] = 0
        row["maximum_rss_kib"] = 1
        row["wall_seconds"] = 1
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(run_m15_native_reset_matrix.M15NativeResetMatrixError, "preflight outcome"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_duplicate_artifact_directory_fails(self) -> None:
        value = copy.deepcopy(self.evidence)
        value["results"][1]["artifact_dir"] = value["results"][0]["artifact_dir"]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(run_m15_native_reset_matrix.M15NativeResetMatrixError, "duplicated"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_town_target_drift_fails(self) -> None:
        value = copy.deepcopy(self.evidence)
        value["results"][0]["towns"] = 3
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(run_m15_native_reset_matrix.M15NativeResetMatrixError, "town target"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_deterministic_repeat_drift_fails(self) -> None:
        value = copy.deepcopy(self.evidence)
        value["determinism"]["projection_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(run_m15_native_reset_matrix.M15NativeResetMatrixError, "deterministic repeat"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_summary_drift_fails(self) -> None:
        value = copy.deepcopy(self.evidence)
        value["summary"]["maximum_rss_kib"] += 1
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(run_m15_native_reset_matrix.M15NativeResetMatrixError, "summary"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_source_identity_drift_fails(self) -> None:
        value = copy.deepcopy(self.evidence)
        value["native_source_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(run_m15_native_reset_matrix.M15NativeResetMatrixError, "source SHA-256"):
                self.validate_mutation(pathlib.Path(raw), value)


if __name__ == "__main__":
    unittest.main()
