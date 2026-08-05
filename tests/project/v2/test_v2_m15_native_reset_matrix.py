#!/usr/bin/env python3
"""Mutation tests for the complete source-integrated M15 reset matrix."""

from __future__ import annotations

import copy
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    ArtifactRequirement,
    resolve_artifact_root,
)
import qualify_m15_native_reset
import run_m15_native_reset_matrix


class M15NativeResetMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.evidence = run_m15_native_reset_matrix.load_json(cls.root / run_m15_native_reset_matrix.EVIDENCE)
        cls.schema = cls.root / run_m15_native_reset_matrix.SCHEMA

    @staticmethod
    def write(directory: pathlib.Path, value: object) -> pathlib.Path:
        path = directory / "matrix.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def validate_mutation(
        self,
        directory: pathlib.Path,
        value: object,
    ) -> run_m15_native_reset_matrix.M15NativeResetMatrixSummary:
        return run_m15_native_reset_matrix.validate(
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

    def test_repository_complete_matrix_passes(self) -> None:
        summary = run_m15_native_reset_matrix.validate(
            self.root,
            artifact_context=ArtifactContext.offline(),
        )
        self.assertEqual((summary.rectangles, summary.generated, summary.preflight_rejected), (49, 39, 10))
        self.assertFalse(summary.live)

    def test_live_complete_matrix_passes(self) -> None:
        summary = run_m15_native_reset_matrix.validate(
            self.root,
            artifact_context=ArtifactContext.live(self.live_base()),
        )
        self.assertTrue(summary.live)

    def test_relocated_live_complete_matrix_uses_context_set(self) -> None:
        records = {
            (item["width"], item["height"]): item
            for item in self.evidence["results"]
            if item["outcome"] == "GENERATED"
        }
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            matrix_root = base / self.evidence["artifact_root"]
            requirements = tuple(
                ArtifactRequirement(
                    self.evidence["artifact_root"],
                    requirement.relative_path,
                    requirement.kind,
                    requirement.consumer,
                )
                for requirement in run_m15_native_reset_matrix.required_live_inputs(self.root)
            )
            for requirement in requirements:
                path = base / requirement.logical_set / requirement.relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.name == qualify_m15_native_reset.MANIFEST_NAME:
                    directory = path.parent.name
                    if directory == run_m15_native_reset_matrix.REPEAT_DIR:
                        width, height = 64, 64
                    else:
                        width, height = map(int, directory.removeprefix("reset-").split("x"))
                    path.write_text(
                        json.dumps({
                            "map_seed": self.evidence["seed"],
                            "map_width": width,
                            "map_height": height,
                        }) + "\n",
                        encoding="utf-8",
                    )
                else:
                    path.write_bytes(b"synthetic reset matrix fixture\n")

            def generated_projection(
                root: pathlib.Path,
                width: int,
                height: int,
                directory: str | None = None,
            ) -> dict[str, object]:
                self.assertEqual(root, matrix_root)
                if directory == run_m15_native_reset_matrix.REPEAT_DIR:
                    return {
                        "width": 64,
                        "height": 64,
                        **{
                            key: self.evidence["determinism"][key]
                            for key in (
                                "artifact_dir",
                                "manifest_sha256",
                                "projection_sha256",
                                "evidence_sha256",
                                "transcript_sha256",
                            )
                        },
                    }
                return copy.deepcopy(records[(width, height)])

            with (
                mock.patch.object(
                    run_m15_native_reset_matrix,
                    "required_live_inputs",
                    return_value=requirements,
                ),
                mock.patch.object(
                    run_m15_native_reset_matrix,
                    "generated_result",
                    side_effect=generated_projection,
                ) as result_reader,
                mock.patch.object(
                    qualify_m15_native_reset,
                    "validate_projection",
                    return_value={},
                ) as projection_reader,
            ):
                summary = run_m15_native_reset_matrix.validate(
                    self.root,
                    artifact_context=ArtifactContext.live(base),
                )

        self.assertTrue(summary.live)
        self.assertEqual(result_reader.call_count, 40)
        self.assertEqual(projection_reader.call_count, 39)
        self.assertTrue(all(call.args[0] == matrix_root for call in result_reader.call_args_list))

    def test_live_preflight_fails_before_matrix_read(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            (base / self.evidence["artifact_root"]).mkdir()
            with mock.patch.object(
                run_m15_native_reset_matrix,
                "generated_result",
                side_effect=AssertionError("unexpected live read"),
            ) as reader:
                with self.assertRaisesRegex(ArtifactContextError, "missing file"):
                    run_m15_native_reset_matrix.validate(
                        self.root,
                        artifact_context=ArtifactContext.live(base),
                    )
            reader.assert_not_called()

    def test_custom_generated_evidence_preflights_its_own_artifact_set(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            evidence = copy.deepcopy(self.evidence)
            evidence_path = self.write(base, evidence)
            requirement = ArtifactRequirement(
                evidence["artifact_root"],
                "fixture.txt",
                "file",
                "m15-native-reset-matrix",
            )
            fixture = base / evidence["artifact_root"] / "fixture.txt"
            fixture.parent.mkdir()
            fixture.write_text("fixture\n", encoding="utf-8")
            load_json = run_m15_native_reset_matrix.load_json

            def load_live_json(path: pathlib.Path) -> dict[str, object]:
                if path.name == qualify_m15_native_reset.MANIFEST_NAME:
                    width, height = map(
                        int,
                        path.parent.name.removeprefix("reset-").split("x"),
                    )
                    return {
                        "map_seed": evidence["seed"],
                        "map_width": width,
                        "map_height": height,
                    }
                return load_json(path)

            with (
                mock.patch.object(
                    run_m15_native_reset_matrix,
                    "required_live_inputs",
                    side_effect=AssertionError("unexpected frozen inventory"),
                ),
                mock.patch.object(
                    run_m15_native_reset_matrix,
                    "_requirements",
                    return_value=(requirement,),
                ) as inventory,
                mock.patch.object(
                    run_m15_native_reset_matrix,
                    "generated_result",
                    side_effect=lambda _root, width, height, directory=None: (
                        copy.deepcopy(self.evidence["determinism"])
                        if directory == run_m15_native_reset_matrix.REPEAT_DIR
                        else copy.deepcopy(next(
                            item
                            for item in self.evidence["results"]
                            if item["width"] == width and item["height"] == height
                        ))
                    ),
                ),
                mock.patch.object(
                    qualify_m15_native_reset,
                    "validate_projection",
                    return_value={},
                ),
                mock.patch.object(
                    run_m15_native_reset_matrix,
                    "load_json",
                    side_effect=load_live_json,
                ) as loader,
            ):
                summary = run_m15_native_reset_matrix.validate(
                    self.root,
                    evidence_path,
                    self.schema,
                    artifact_context=ArtifactContext.live(base),
                )

        self.assertTrue(summary.live)
        inventory.assert_called_once_with(evidence)
        self.assertTrue(any(call.args[0] == fixture.parent / "reset-0064x0064" / qualify_m15_native_reset.MANIFEST_NAME for call in loader.call_args_list))

    def test_required_live_inputs_are_the_exact_matrix_closure(self) -> None:
        generated = tuple(
            item["artifact_dir"]
            for item in self.evidence["results"]
            if item["outcome"] == "GENERATED"
        ) + ("repeat-0064x0064",)
        expected_paths = tuple(
            f"{directory}/{filename}"
            for directory in generated
            for filename in (
                "reset-evidence.json",
                "reset-manifest.json",
                "reset-projection.json",
                "openttd-reset.log",
            )
        )
        requirements = run_m15_native_reset_matrix.required_live_inputs(self.root)
        self.assertEqual(tuple(item.relative_path for item in requirements), expected_paths)
        self.assertEqual(
            {item.logical_set for item in requirements},
            {"v2-m15-native-reset-matrix-a"},
        )
        self.assertEqual({item.consumer for item in requirements}, {"m15-native-reset-matrix"})
        self.assertEqual(
            requirements[0].expected_sha256,
            self.evidence["results"][0]["evidence_sha256"],
        )

    def test_validation_only_cli_owns_offline_validation(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts/v2/validate_m15_native_reset_matrix.py"),
                "--root",
                str(self.root),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("V2_M15_NATIVE_RESET_MATRIX=PASS", completed.stdout)
        self.assertIn("live=false", completed.stdout)

    def test_creation_artifact_root_is_not_a_validation_base(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(self.root / "scripts/v2/run_m15_native_reset_matrix.py"),
                    "--root",
                    str(self.root),
                    "--artifact-root",
                    raw,
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("creation mode requires", completed.stderr)

    def test_runner_rejects_validation_evidence_option(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts/v2/run_m15_native_reset_matrix.py"),
                "--root",
                str(self.root),
                "--evidence",
                str(self.root / run_m15_native_reset_matrix.EVIDENCE),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("unrecognized arguments: --evidence", completed.stderr)

    def test_runner_rejects_each_incomplete_creation_option(self) -> None:
        options = (
            ("--openttd", "/tmp/openttd"),
            ("--opengfx", "/tmp/opengfx"),
            ("--artifact-root", "/tmp/generated-matrix"),
            ("--seed", "1110312784"),
            ("--workers", "1"),
            ("--sandbox", "test-none"),
        )
        for option in options:
            with self.subTest(option=option[0]):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(self.root / "scripts/v2/run_m15_native_reset_matrix.py"),
                        "--root",
                        str(self.root),
                        *option,
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 2, completed.stdout)
                self.assertIn("creation mode requires", completed.stderr)

    def test_runner_rejects_mixed_incomplete_creation_options(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts/v2/run_m15_native_reset_matrix.py"),
                "--root",
                str(self.root),
                "--openttd",
                "/tmp/openttd",
                "--workers",
                "1",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("creation mode requires", completed.stderr)

    def test_freeze_helper_reports_preflight_failure_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            output_directory = base / "output"
            output_directory.mkdir()
            output = output_directory / "matrix.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(self.root / "scripts/v2/freeze_m15_native_reset_matrix.py"),
                    "--root",
                    str(self.root),
                    "--matrix",
                    str(self.root / run_m15_native_reset_matrix.EVIDENCE),
                    "--artifact-base",
                    str(base),
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 1)
            self.assertIn("V2_M15_NATIVE_RESET_MATRIX=FAIL", completed.stderr)
            self.assertNotIn("TypeError", completed.stderr)
            self.assertFalse(output.exists())
            self.assertEqual(list(output_directory.iterdir()), [])

    def test_runner_reports_generated_artifact_preflight_failure(self) -> None:
        with (
            mock.patch.object(
                run_m15_native_reset_matrix,
                "run_matrix",
                side_effect=ArtifactContextError("generated matrix preflight failed"),
            ),
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            result = run_m15_native_reset_matrix.main([
                "--root",
                str(self.root),
                "--openttd",
                "/tmp/openttd",
                "--opengfx",
                "/tmp/opengfx",
                "--artifact-root",
                "/tmp/generated-matrix",
            ])

        self.assertEqual(result, 1)
        self.assertIn("generated matrix preflight failed", stderr.getvalue())

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
