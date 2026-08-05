#!/usr/bin/env python3
"""Mutation and live tests for the source-integrated M15 scalable reset."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    resolve_artifact_root,
)
import acquire_ai_package
import qualify_m15_native_reset
import validate_m15_native_reset_evidence


class M15NativeResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.matrix_path = cls.root / validate_m15_native_reset_evidence.EVIDENCE
        cls.matrix = validate_m15_native_reset_evidence.load_json(cls.matrix_path)
        cls.schema = cls.root / validate_m15_native_reset_evidence.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "matrix.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def validate_mutation(
        self,
        directory: pathlib.Path,
        value: object,
    ) -> validate_m15_native_reset_evidence.M15NativeResetEvidenceSummary:
        return validate_m15_native_reset_evidence.validate(
            self.root,
            self.write(directory, value),
            self.schema,
            artifact_context=ArtifactContext.offline(),
        )

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def test_repository_matrix_passes(self) -> None:
        summary = validate_m15_native_reset_evidence.validate(
            self.root,
            artifact_context=ArtifactContext.offline(),
        )
        self.assertEqual(summary.runs, 6)
        self.assertEqual(summary.rectangles, 5)
        self.assertFalse(summary.live)

    def test_live_matrix_passes(self) -> None:
        summary = validate_m15_native_reset_evidence.validate(
            self.root,
            artifact_context=ArtifactContext.live(self.live_base()),
        )
        self.assertTrue(summary.live)

    def test_relocated_live_reset_uses_one_artifact_context(self) -> None:
        value = copy.deepcopy(self.matrix)
        recorded_base = value["artifact_base_hint"]
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            set_root = base / "v2-m15-native-a"
            for index, result in enumerate(value["results"]):
                artifact = set_root / result["artifact_dir"]
                artifact.mkdir(parents=True)
                manifest = {
                    "map_width": result["width"],
                    "map_height": result["height"],
                    "map_seed": value["seed"],
                }
                projection = {
                    "fixture_index": 0 if index == 1 else index,
                    "state": {"counts": {"towns": result["towns"]}},
                }
                manifest_bytes = json.dumps(manifest, sort_keys=True).encode() + b"\n"
                projection_bytes = json.dumps(projection, sort_keys=True).encode() + b"\n"
                transcript_bytes = b""
                (artifact / qualify_m15_native_reset.MANIFEST_NAME).write_bytes(manifest_bytes)
                (artifact / qualify_m15_native_reset.PROJECTION_NAME).write_bytes(projection_bytes)
                (artifact / qualify_m15_native_reset.TRANSCRIPT_NAME).write_bytes(transcript_bytes)
                result["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
                result["projection_sha256"] = hashlib.sha256(projection_bytes).hexdigest()
                result["transcript_sha256"] = hashlib.sha256(transcript_bytes).hexdigest()
                evidence = {
                    "width": result["width"],
                    "height": result["height"],
                    "outcome": result["outcome"],
                    "manifest_sha256": result["manifest_sha256"],
                    "projection_sha256": result["projection_sha256"],
                    "transcript_sha256": result["transcript_sha256"],
                    "towns": result["towns"],
                    "industries": result["industries"],
                    "maximum_rss_kib": result["maximum_rss_kib"],
                    "wall_seconds": result["wall_seconds"],
                }
                evidence_bytes = json.dumps(evidence, sort_keys=True).encode() + b"\n"
                (artifact / qualify_m15_native_reset.EVIDENCE_NAME).write_bytes(evidence_bytes)
                result["evidence_sha256"] = hashlib.sha256(evidence_bytes).hexdigest()
                if index == 1:
                    result["projection_sha256"] = value["results"][0]["projection_sha256"]
                    (artifact / qualify_m15_native_reset.PROJECTION_NAME).write_bytes(
                        (set_root / value["results"][0]["artifact_dir"] / qualify_m15_native_reset.PROJECTION_NAME).read_bytes()
                    )
                    evidence["projection_sha256"] = result["projection_sha256"]
                    evidence_bytes = json.dumps(evidence, sort_keys=True).encode() + b"\n"
                    (artifact / qualify_m15_native_reset.EVIDENCE_NAME).write_bytes(evidence_bytes)
                    result["evidence_sha256"] = hashlib.sha256(evidence_bytes).hexdigest()
            value["summary"] = validate_m15_native_reset_evidence.expected_summary(value["results"])
            config_path = self.write(base, value)
            requirements = tuple(
                ArtifactRequirement(
                    "v2-m15-native-a",
                    requirement.relative_path,
                    requirement.kind,
                    requirement.consumer,
                )
                for requirement in validate_m15_native_reset_evidence.required_live_inputs(self.root)
            )
            with (
                mock.patch.object(
                    validate_m15_native_reset_evidence,
                    "required_live_inputs",
                    return_value=requirements,
                ),
                mock.patch.object(qualify_m15_native_reset, "validate_schema") as schema_reader,
                mock.patch.object(
                    qualify_m15_native_reset,
                    "validate_projection",
                    side_effect=lambda root, manifest, path: validate_m15_native_reset_evidence.load_json(path),
                ) as projection_reader,
            ):
                summary = validate_m15_native_reset_evidence.validate(
                    self.root,
                    config_path,
                    self.schema,
                    artifact_context=ArtifactContext.live(base),
                )

        self.assertTrue(summary.live)
        self.assertEqual(value["artifact_base_hint"], recorded_base)
        self.assertEqual(schema_reader.call_count, len(value["results"]))
        self.assertEqual(
            [call.args[2] for call in projection_reader.call_args_list],
            [
                set_root / result["artifact_dir"] / qualify_m15_native_reset.PROJECTION_NAME
                for result in value["results"]
            ],
        )

    def test_live_preflight_fails_before_reset_read(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            (base / "v2-m15-native-a").mkdir()
            with mock.patch.object(
                validate_m15_native_reset_evidence,
                "result_from_live",
                side_effect=AssertionError("unexpected live read"),
            ) as reader:
                with self.assertRaisesRegex(ArtifactContextError, "missing file"):
                    validate_m15_native_reset_evidence.validate(
                        self.root,
                        artifact_context=ArtifactContext.live(base),
                    )
            reader.assert_not_called()

    def test_required_live_inputs_are_the_exact_reset_closure(self) -> None:
        expected_paths = tuple(
            f"{directory}/{filename}"
            for directory in (
                "qualified-64-a",
                "qualified-64-b",
                "qualified-128-a",
                "qualified-64x256-a",
                "qualified-512x128-a",
                "qualified-1024-a",
            )
            for filename in (
                "reset-evidence.json",
                "reset-manifest.json",
                "reset-projection.json",
                "openttd-reset.log",
            )
        )
        requirements = validate_m15_native_reset_evidence.required_live_inputs(self.root)
        self.assertEqual(tuple(item.relative_path for item in requirements), expected_paths)
        self.assertEqual({item.logical_set for item in requirements}, {"v2-m15-native-a"})
        self.assertEqual({item.kind for item in requirements}, {"file"})
        self.assertEqual({item.consumer for item in requirements}, {"m15-native-reset-evidence"})
        self.assertEqual(
            requirements[0].expected_sha256,
            self.matrix["results"][0]["evidence_sha256"],
        )

    def test_same_manifest_repeat_is_byte_identical(self) -> None:
        first, second = self.matrix["results"][:2]
        self.assertEqual(first["projection_sha256"], second["projection_sha256"])

    def test_reordered_run_fails(self) -> None:
        value = copy.deepcopy(self.matrix)
        value["results"][0], value["results"][1] = value["results"][1], value["results"][0]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_reset_evidence.M15NativeResetEvidenceError, "order/coverage"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_repeat_projection_drift_fails(self) -> None:
        value = copy.deepcopy(self.matrix)
        value["results"][1]["projection_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_reset_evidence.M15NativeResetEvidenceError, "projections differ"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_town_target_drift_fails(self) -> None:
        value = copy.deepcopy(self.matrix)
        value["results"][2]["towns"] = 3
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_reset_evidence.M15NativeResetEvidenceError, "town target"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_summary_drift_fails(self) -> None:
        value = copy.deepcopy(self.matrix)
        value["summary"]["maximum_rss_kib"] += 1
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_reset_evidence.M15NativeResetEvidenceError, "summary"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_source_identity_drift_fails(self) -> None:
        value = copy.deepcopy(self.matrix)
        value["native_source_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(validate_m15_native_reset_evidence.M15NativeResetEvidenceError, "source evidence"):
                self.validate_mutation(pathlib.Path(raw), value)

    def test_manifest_builder_rejects_unknown_rectangle(self) -> None:
        artifact = self.live_base() / "v2-m15-native-a"
        executable = artifact / "build/openttd"
        opengfx = artifact / "build/baseset/opengfx-8.0.tar"
        if not executable.is_file() or not opengfx.is_file():
            self.skipTest("live artifact validation is outside offline mode")
        with self.assertRaisesRegex(qualify_m15_native_reset.M15NativeResetError, "frozen native rectangle"):
            qualify_m15_native_reset.build_manifest(self.root, executable, opengfx, 32, 32, 1110312784)

    def test_preflight_rejects_before_artifact_creation(self) -> None:
        artifact = self.live_base() / "v2-m15-native-a"
        executable = artifact / "build/openttd"
        opengfx = artifact / "build/baseset/opengfx-8.0.tar"
        if not executable.is_file() or not opengfx.is_file():
            self.skipTest("live artifact validation is outside offline mode")
        with tempfile.TemporaryDirectory() as raw:
            target = pathlib.Path(raw) / "must-not-exist"
            with self.assertRaisesRegex(qualify_m15_native_reset.M15NativeResetError, "preallocation budget"):
                qualify_m15_native_reset.qualify(self.root, executable, opengfx, target, 2048, 1024, 1110312784, sandbox="test-none")
            self.assertFalse(target.exists())

    def test_native_binary_rejects_over_budget_before_projection(self) -> None:
        artifact = self.live_base() / "v2-m15-native-a"
        executable = artifact / "build/openttd"
        opengfx = artifact / "build/baseset/opengfx-8.0.tar"
        if not executable.is_file() or not opengfx.is_file():
            self.skipTest("live artifact validation is outside offline mode")
        manifest = qualify_m15_native_reset.build_manifest(self.root, executable, opengfx, 1024, 1024, 1110312784)
        manifest["map_width"] = 2048
        manifest["map_height"] = 1024
        manifest["town_target"] = 128
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            manifest_path = directory / "manifest.json"
            projection_path = directory / "projection.json"
            manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            environment = acquire_ai_package.isolated_environment(directory)
            result = subprocess.run(
                [str(executable), "-x", "-X", "-Q", "-I", "OpenGFX", "-v", "null", "-s", "null", "-m", "null", "-V", str(manifest_path), "-U", str(projection_path)],
                cwd=executable.parent, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30,
            )
            self.assertIn("tile count exceeds the M15 preflight generation budget", result.stdout)
            self.assertFalse(projection_path.exists())

    def test_projection_request_mutation_fails(self) -> None:
        artifact = self.live_base() / "v2-m15-native-a" / "qualified-64-a"
        projection_path = artifact / "reset-projection.json"
        manifest_path = artifact / "reset-manifest.json"
        if not projection_path.is_file() or not manifest_path.is_file():
            self.skipTest("live artifact validation is outside offline mode")
        projection = validate_m15_native_reset_evidence.load_json(projection_path)
        manifest = validate_m15_native_reset_evidence.load_json(manifest_path)
        projection["request"]["simulation_seed"] += 1
        with tempfile.TemporaryDirectory() as raw:
            mutated = pathlib.Path(raw) / "projection.json"
            mutated.write_text(json.dumps(projection) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(qualify_m15_native_reset.M15NativeResetError, "request echo"):
                qualify_m15_native_reset.validate_projection(self.root, manifest, mutated)


if __name__ == "__main__":
    unittest.main()
