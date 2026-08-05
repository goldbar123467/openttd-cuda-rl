#!/usr/bin/env python3
"""Mutation tests for M15 curriculum/generalization exact replay evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    resolve_artifact_root,
)
import run_m15_cross_scale_replay
import validate_m15_cross_scale_replay_evidence


class M15CrossScaleReplayEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.config = validate_m15_cross_scale_replay_evidence.load_json(
            cls.root / validate_m15_cross_scale_replay_evidence.CONFIG
        )
        cls.schema = cls.root / validate_m15_cross_scale_replay_evidence.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "cross-scale.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def live_base(self) -> pathlib.Path:
        base = resolve_artifact_root(None)
        if base is None:
            self.skipTest("live artifact validation is outside offline mode")
        return base

    def mutation_fails(self, value: object, pattern: str | None = None, *, live: bool = False) -> None:
        with tempfile.TemporaryDirectory() as raw:
            error = (
                self.assertRaisesRegex(
                    validate_m15_cross_scale_replay_evidence.M15CrossScaleReplayEvidenceError,
                    pattern,
                )
                if pattern
                else self.assertRaises(
                    validate_m15_cross_scale_replay_evidence.M15CrossScaleReplayEvidenceError
                )
            )
            with error:
                validate_m15_cross_scale_replay_evidence.validate(
                    self.root,
                    self.write(pathlib.Path(raw), value),
                    self.schema,
                    artifact_context=(
                        ArtifactContext.live(self.live_base())
                        if live
                        else ArtifactContext.offline()
                    ),
                )

    def test_repository_evidence_passes(self) -> None:
        summary = validate_m15_cross_scale_replay_evidence.validate(
            self.root,
            artifact_context=ArtifactContext.offline(),
        )
        self.assertEqual((summary.cases, summary.runs, summary.maximum_rss_kib), (9, 18, 90916))
        self.assertFalse(summary.live)

    def test_live_artifacts_pass(self) -> None:
        summary = validate_m15_cross_scale_replay_evidence.validate(
            self.root,
            artifact_context=ArtifactContext.live(self.live_base()),
        )
        self.assertTrue(summary.live)

    def test_relocated_live_replay_uses_context_before_helper_reads(self) -> None:
        value = copy.deepcopy(self.config)
        recorded_root = value["artifact_root"]
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            logical_set = pathlib.PurePosixPath(recorded_root).name
            requirements = validate_m15_cross_scale_replay_evidence.required_live_inputs(self.root)
            fixture_bytes = b"custom cross-scale fixture\n"
            for requirement in requirements:
                path = base / logical_set / requirement.relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(fixture_bytes)
            fixture_sha256 = hashlib.sha256(fixture_bytes).hexdigest()
            for case in value["cases"]:
                for field in (
                    "trace_sha256",
                    "projection_sha256",
                    "checkpoint_sha256",
                    "save_sha256",
                    "observation_sha256",
                    "candidate_sha256",
                ):
                    case[field] = fixture_sha256
            self.assertNotEqual(
                value["cases"][0]["trace_sha256"],
                self.config["cases"][0]["trace_sha256"],
            )
            matrix = {
                "outcome": "PASS",
                "program_sha256": value["program_sha256"],
                "cases": [
                    {
                        **{
                            field: case[field]
                            for field in ("case_id", "width", "height", "seed", "split", "tier")
                        },
                        "twin_process_exact": True,
                        "save_load_exact": True,
                        "runs": [{}, {}],
                    }
                    for case in value["cases"]
                ],
            }
            matrix_path = base / logical_set / "matrix-run.json"
            matrix_path.write_text(json.dumps(matrix, sort_keys=True) + "\n", encoding="utf-8")
            value["matrix_run_sha256"] = hashlib.sha256(matrix_path.read_bytes()).hexdigest()
            config_path = self.write(base, value)
            by_case = {case["case_id"]: case for case in value["cases"]}

            def project(root: pathlib.Path, run: pathlib.Path) -> dict[str, object]:
                self.assertEqual(root, self.root)
                projected = copy.deepcopy(by_case[run.parent.name])
                projected["wall_seconds"] = projected["maximum_wall_seconds"]
                return projected

            with mock.patch.object(
                run_m15_cross_scale_replay,
                "project_run",
                side_effect=project,
            ) as reader:
                summary = validate_m15_cross_scale_replay_evidence.validate(
                    self.root,
                    config_path,
                    self.schema,
                    artifact_context=ArtifactContext.live(base),
                )

        self.assertTrue(summary.live)
        self.assertEqual(value["artifact_root"], recorded_root)
        self.assertEqual(
            [call.args[1] for call in reader.call_args_list],
            [
                base / logical_set / case_id / run
                for case_id in (
                    "curriculum-64x64",
                    "curriculum-128x128",
                    "curriculum-256x256",
                    "curriculum-512x512",
                    "generalization-64x256",
                    "generalization-128x512",
                    "generalization-256x1024",
                    "generalization-512x128",
                    "generalization-1024x1024",
                )
                for run in ("run-a", "run-b")
            ],
        )

    def test_live_preflight_fails_before_replay_helper_read(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            (base / "v2-m15-cross-scale-replay-a").mkdir()
            with mock.patch.object(
                run_m15_cross_scale_replay,
                "project_run",
                side_effect=AssertionError("unexpected live read"),
            ) as reader:
                with self.assertRaisesRegex(ArtifactContextError, "missing file"):
                    validate_m15_cross_scale_replay_evidence.validate(
                        self.root,
                        artifact_context=ArtifactContext.live(base),
                    )
            reader.assert_not_called()

    def test_required_live_inputs_are_the_exact_replay_closure(self) -> None:
        expected = ["matrix-run.json"]
        for case_id in (
            "curriculum-64x64",
            "curriculum-128x128",
            "curriculum-256x256",
            "curriculum-512x512",
            "generalization-64x256",
            "generalization-128x512",
            "generalization-256x1024",
            "generalization-512x128",
            "generalization-1024x1024",
        ):
            for run in ("run-a", "run-b"):
                prefix = f"{case_id}/{run}"
                expected.extend([
                    f"{prefix}/episode-trace.json",
                    f"{prefix}/reset-projection.json",
                    f"{prefix}/resource.txt",
                    f"{prefix}/artifacts/reset-ready.sav",
                ])
                for label in ("capture-branch-a", "capture-branch-b"):
                    expected.extend([
                        f"{prefix}/artifacts/{label}.sav",
                        f"{prefix}/artifacts/{label}-observation.json",
                        f"{prefix}/artifacts/{label}-observation.bin",
                        f"{prefix}/artifacts/{label}-candidates.json",
                        f"{prefix}/artifacts/{label}-candidates.bin",
                    ])
        requirements = validate_m15_cross_scale_replay_evidence.required_live_inputs(self.root)
        self.assertEqual(tuple(item.relative_path for item in requirements), tuple(expected))
        self.assertEqual(
            {item.logical_set for item in requirements},
            {"v2-m15-cross-scale-replay-a"},
        )
        self.assertEqual({item.consumer for item in requirements}, {"m15-cross-scale-replay"})
        by_path = {item.relative_path: item for item in requirements}
        first = self.config["cases"][0]
        self.assertEqual(by_path["matrix-run.json"].expected_sha256, self.config["matrix_run_sha256"])
        self.assertEqual(
            by_path["curriculum-64x64/run-a/episode-trace.json"].expected_sha256,
            first["trace_sha256"],
        )
        self.assertEqual(
            by_path["curriculum-64x64/run-a/artifacts/reset-ready.sav"].expected_sha256,
            first["checkpoint_sha256"],
        )

    def test_schema_hash_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["schema_sha256"] = "0" * 64
        self.mutation_fails(value, "schema SHA-256")

    def test_case_omission_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["cases"].pop()
        self.mutation_fails(value)

    def test_generalization_rectangle_drift_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["cases"][4]["height"] = 128
        self.mutation_fails(value, "case inventory")

    def test_seed_leakage_fails(self) -> None:
        value = copy.deepcopy(self.config)
        value["cases"][0]["seed"] = 484178880
        self.mutation_fails(value, "case inventory")

    def test_matrix_digest_drift_fails_live(self) -> None:
        value = copy.deepcopy(self.config)
        value["matrix_run_sha256"] = "0" * 64
        self.mutation_fails(value, "matrix-run digest", live=True)

    def test_capture_digest_drift_fails_live(self) -> None:
        value = copy.deepcopy(self.config)
        value["cases"][8]["candidate_sha256"] = "1" * 64
        self.mutation_fails(value, "candidate_sha256", live=True)


if __name__ == "__main__":
    unittest.main()
