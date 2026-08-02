#!/usr/bin/env python3
"""Mutation tests for M15 native-map qualification and its 49-rectangle index."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

import qualify_m15_native_map
import run_m15_map_matrix


class M15MapQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.matrix_path = cls.root / "config/v2/m15-map-evidence.json"
        cls.matrix_schema = cls.root / "docs/project/schema/v2-m15-map-evidence.schema.json"
        cls.matrix = run_m15_map_matrix.load_json(cls.matrix_path)

    def validate_matrix_mutation(self, value: object) -> run_m15_map_matrix.M15MapMatrixSummary:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "matrix.json"
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            return run_m15_map_matrix.validate(self.root, path, self.matrix_schema)

    def test_repository_matrix_passes(self) -> None:
        summary = run_m15_map_matrix.validate(self.root)
        self.assertEqual(summary.rectangles, 49)
        self.assertEqual(summary.generated, 39)
        self.assertEqual(summary.preflight_rejected, 10)
        self.assertEqual(summary.save_bytes, 2881300)
        self.assertEqual(summary.maximum_rss_kib, 89104)
        self.assertFalse(summary.live_artifacts)

    def test_preflight_rejection_is_machine_validated_without_launch(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            executable = directory / "openttd"
            executable.write_bytes(b"test executable")
            executable.chmod(0o755)
            artifact = directory / "artifact"
            evidence = qualify_m15_native_map.qualify(
                self.root, executable, artifact, 4096, 4096, 1110312784, sandbox="test-none"
            )
            manifest = qualify_m15_native_map.validate_manifest(self.root, evidence, openttd=executable)
            self.assertEqual(manifest["outcome"], "PREFLIGHT_REJECTED")
            self.assertFalse((artifact / qualify_m15_native_map.TRANSCRIPT_NAME).exists())

    def test_unknown_dimension_rejected_before_artifact_creation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            executable = directory / "openttd"
            executable.write_bytes(b"test executable")
            executable.chmod(0o755)
            artifact = directory / "artifact"
            with self.assertRaisesRegex(qualify_m15_native_map.M15MapQualificationError, "native rectangle"):
                qualify_m15_native_map.qualify(self.root, executable, artifact, 32, 64, 1110312784, sandbox="test-none")
            self.assertFalse(artifact.exists())

    def test_unfrozen_seed_rejected_before_artifact_creation(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            executable = directory / "openttd"
            executable.write_bytes(b"test executable")
            executable.chmod(0o755)
            artifact = directory / "artifact"
            with self.assertRaisesRegex(qualify_m15_native_map.M15MapQualificationError, "seed"):
                qualify_m15_native_map.qualify(self.root, executable, artifact, 64, 64, 1, sandbox="test-none")
            self.assertFalse(artifact.exists())

    def test_schema_hash_drift_fails(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        matrix["schema_sha256"] = "0" * 64
        with self.assertRaisesRegex(run_m15_map_matrix.M15MapMatrixError, "schema SHA-256"):
            self.validate_matrix_mutation(matrix)

    def test_contract_hash_drift_fails(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        matrix["contract_sha256"] = "0" * 64
        with self.assertRaisesRegex(run_m15_map_matrix.M15MapMatrixError, "contract SHA-256"):
            self.validate_matrix_mutation(matrix)

    def test_unfrozen_matrix_seed_fails(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        matrix["seed"] = 1
        with self.assertRaisesRegex(run_m15_map_matrix.M15MapMatrixError, "seed is not frozen"):
            self.validate_matrix_mutation(matrix)

    def test_executable_identity_drift_fails(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        matrix["executable"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(run_m15_map_matrix.M15MapMatrixError, "executable drifted"):
            self.validate_matrix_mutation(matrix)

    def test_missing_rectangle_fails_schema(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        matrix["results"].pop()
        with self.assertRaisesRegex(run_m15_map_matrix.M15MapMatrixError, "schema failed"):
            self.validate_matrix_mutation(matrix)

    def test_reordered_rectangle_fails(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        matrix["results"][0], matrix["results"][1] = matrix["results"][1], matrix["results"][0]
        with self.assertRaisesRegex(run_m15_map_matrix.M15MapMatrixError, "order/coverage"):
            self.validate_matrix_mutation(matrix)

    def test_tile_count_drift_fails(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        matrix["results"][0]["tile_count"] += 1
        with self.assertRaisesRegex(run_m15_map_matrix.M15MapMatrixError, "tile count"):
            self.validate_matrix_mutation(matrix)

    def test_inside_budget_cannot_be_preflight_rejected(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        row = matrix["results"][0]
        row["outcome"] = "PREFLIGHT_REJECTED"
        row["reason_code"] = "tile-count-exceeds-useful-play-preflight-budget"
        with self.assertRaisesRegex(run_m15_map_matrix.M15MapMatrixError, "was not generated inside budget"):
            self.validate_matrix_mutation(matrix)

    def test_above_budget_cannot_claim_generation(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        row = next(item for item in matrix["results"] if item["outcome"] == "PREFLIGHT_REJECTED")
        row["outcome"] = "GENERATED"
        row["reason_code"] = None
        with self.assertRaisesRegex(run_m15_map_matrix.M15MapMatrixError, "preflight disposition"):
            self.validate_matrix_mutation(matrix)

    def test_generated_result_requires_content_hashes(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        matrix["results"][0]["map_sha256"] = None
        with self.assertRaisesRegex(run_m15_map_matrix.M15MapMatrixError, "generated evidence is incomplete"):
            self.validate_matrix_mutation(matrix)

    def test_duplicate_artifact_directory_fails(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        matrix["results"][1]["artifact_dir"] = matrix["results"][0]["artifact_dir"]
        with self.assertRaisesRegex(run_m15_map_matrix.M15MapMatrixError, "duplicated"):
            self.validate_matrix_mutation(matrix)

    def test_summary_count_drift_fails(self) -> None:
        matrix = copy.deepcopy(self.matrix)
        matrix["counts"]["save_bytes"] += 1
        with self.assertRaisesRegex(run_m15_map_matrix.M15MapMatrixError, "summary counts"):
            self.validate_matrix_mutation(matrix)

    def test_live_validation_requires_artifact_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(run_m15_map_matrix.M15MapMatrixError, "artifact root"):
                run_m15_map_matrix.validate(self.root, artifact_base=pathlib.Path(raw))


if __name__ == "__main__":
    unittest.main()
