#!/usr/bin/env python3
"""Mutation tests for M15 native-map qualification and its 49-rectangle index."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import MappingProxyType
from unittest import mock

from artifact_context import (
    ArtifactContext,
    ArtifactContextError,
    LiveInputManifest,
    ValidationMode,
)
import freeze_m15_map_evidence
import qualify_m15_native_map
import run_m15_map_matrix
import validate_m15_map_evidence


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
            return run_m15_map_matrix.validate(
                self.root,
                path,
                self.matrix_schema,
                artifact_context=ArtifactContext.offline(),
            )

    def make_live_matrix_fixture(
        self,
        directory: pathlib.Path,
    ) -> tuple[
        pathlib.Path,
        pathlib.Path,
        pathlib.Path,
        LiveInputManifest,
        dict[pathlib.Path, dict[str, object]],
        dict[str, object],
    ]:
        project = directory / "project"
        for relative in (
            pathlib.Path("config/v1/openttd-source-profile.json"),
            pathlib.Path("config/v2/m15-scalable-contract.json"),
            pathlib.Path("config/v2/opponent-runtime-evidence.json"),
            pathlib.Path("docs/project/schema/v2-m15-map-evidence.schema.json"),
        ):
            target = project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.root / relative, target)

        base = directory / "live"
        matrix = copy.deepcopy(self.matrix)
        artifact_set = base / matrix["artifact_root"]
        artifact_set.mkdir(parents=True)
        executable = base / "roles" / "openttd"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"relocated map executable\n")
        executable.chmod(0o755)
        matrix["executable"] = {
            "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "size": executable.stat().st_size,
        }
        runtime_path = project / "config/v2/opponent-runtime-evidence.json"
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["executable"] = copy.deepcopy(matrix["executable"])
        runtime_path.write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")

        manifests: dict[pathlib.Path, dict[str, object]] = {}
        for item in matrix["results"]:
            result_root = artifact_set / item["artifact_dir"]
            result_root.mkdir()
            if item["outcome"] == "GENERATED":
                save_bytes = f"save {item['artifact_dir']}\n".encode()
                transcript_bytes = f"transcript {item['artifact_dir']}\n".encode()
                save_path = result_root / qualify_m15_native_map.SAVE_RELATIVE
                save_path.parent.mkdir()
                save_path.write_bytes(save_bytes)
                transcript_path = result_root / qualify_m15_native_map.TRANSCRIPT_NAME
                transcript_path.write_bytes(transcript_bytes)
                item["save_sha256"] = hashlib.sha256(save_bytes).hexdigest()
                item["save_size"] = len(save_bytes)
                observations: dict[str, object] = {
                    "save": {
                        "path": qualify_m15_native_map.SAVE_RELATIVE.as_posix(),
                        "size": len(save_bytes),
                        "sha256": item["save_sha256"],
                    },
                    "map": {"map_sha256": item["map_sha256"]},
                    "transcript_sha256": hashlib.sha256(transcript_bytes).hexdigest(),
                }
            else:
                observations = {"save": None, "map": None, "transcript_sha256": None}
            manifest: dict[str, object] = {
                "request": {
                    "width": item["width"],
                    "height": item["height"],
                    "tile_count": item["tile_count"],
                },
                "outcome": item["outcome"],
                "reason_code": item["reason_code"],
                "observations": observations,
                "resources": {
                    "max_rss_kib": item["max_rss_kib"],
                    "wall_seconds": item["wall_seconds"],
                },
            }
            evidence_path = result_root / item["evidence_file"]
            evidence_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
            item["evidence_sha256"] = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
            manifests[evidence_path] = manifest
        matrix["counts"]["save_bytes"] = sum(item["save_size"] or 0 for item in matrix["results"])
        matrix_path = directory / "matrix.json"
        matrix_path.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")
        live_inputs = LiveInputManifest(
            ValidationMode.LIVE,
            base,
            MappingProxyType({"m14-openttd-executable": executable}),
        )
        return project, base, matrix_path, live_inputs, manifests, matrix

    def test_repository_matrix_passes(self) -> None:
        summary = run_m15_map_matrix.validate(
            self.root,
            artifact_context=ArtifactContext.offline(),
        )
        self.assertEqual(summary.rectangles, 49)
        self.assertEqual(summary.generated, 39)
        self.assertEqual(summary.preflight_rejected, 10)
        self.assertEqual(summary.save_bytes, 2881300)
        self.assertEqual(summary.maximum_rss_kib, 89104)
        self.assertFalse(summary.live_artifacts)

    def test_offline_validation_does_not_open_artifact_hint(self) -> None:
        with mock.patch.object(
            qualify_m15_native_map,
            "validate_manifest",
            side_effect=AssertionError("unexpected live access"),
        ) as reader:
            summary = run_m15_map_matrix.validate(
                self.root,
                artifact_context=ArtifactContext.offline(),
            )
        self.assertFalse(summary.live_artifacts)
        reader.assert_not_called()

    def test_relocated_live_map_matrix_passes(self) -> None:
        recorded_hint = self.matrix["artifact_base_hint"]
        with tempfile.TemporaryDirectory() as raw:
            project, base, matrix_path, live_inputs, manifests, matrix = self.make_live_matrix_fixture(
                pathlib.Path(raw).resolve()
            )

            def validate_manifest(
                root: pathlib.Path,
                evidence_path: pathlib.Path,
                *,
                openttd: pathlib.Path | None = None,
            ) -> dict[str, object]:
                self.assertEqual(root, project)
                requirement = run_m15_map_matrix.required_live_roles(project, matrix_path)[0]
                self.assertEqual(openttd, live_inputs.resolve(requirement))
                run_m15_map_matrix.load_json(evidence_path)
                return manifests[evidence_path]

            with mock.patch.object(
                qualify_m15_native_map,
                "validate_manifest",
                side_effect=validate_manifest,
            ) as reader:
                summary = run_m15_map_matrix.validate(
                    project,
                    matrix_path,
                    project / run_m15_map_matrix.SCHEMA_RELATIVE,
                    artifact_context=ArtifactContext.live(base),
                    live_inputs=live_inputs,
                )
        self.assertTrue(summary.live_artifacts)
        self.assertEqual(matrix["artifact_base_hint"], recorded_hint)
        self.assertEqual(reader.call_count, 49)

    def test_live_map_preflight_fails_before_result_reader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw).resolve()
            project, base, matrix_path, live_inputs, _, _ = self.make_live_matrix_fixture(directory)
            missing = next((base / self.matrix["artifact_root"]).glob("*/m15-map-qualification.json"))
            missing.unlink()
            with mock.patch.object(
                qualify_m15_native_map,
                "validate_manifest",
                side_effect=AssertionError("unexpected live read"),
            ) as reader:
                with self.assertRaisesRegex(ArtifactContextError, "missing file"):
                    run_m15_map_matrix.validate(
                        project,
                        matrix_path,
                        project / run_m15_map_matrix.SCHEMA_RELATIVE,
                        artifact_context=ArtifactContext.live(base),
                        live_inputs=live_inputs,
                    )
            reader.assert_not_called()

    def test_live_map_preflight_rejects_nested_symlink_before_result_reader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw).resolve()
            project, base, matrix_path, live_inputs, _, _ = self.make_live_matrix_fixture(directory)
            evidence = next((base / self.matrix["artifact_root"]).glob("*/m15-map-qualification.json"))
            target = directory / "outside.json"
            target.write_bytes(evidence.read_bytes())
            evidence.unlink()
            evidence.symlink_to(target)
            with mock.patch.object(
                qualify_m15_native_map,
                "validate_manifest",
                side_effect=AssertionError("unexpected live read"),
            ) as reader:
                with self.assertRaisesRegex(ArtifactContextError, "symlink traversal"):
                    run_m15_map_matrix.validate(
                        project,
                        matrix_path,
                        project / run_m15_map_matrix.SCHEMA_RELATIVE,
                        artifact_context=ArtifactContext.live(base),
                        live_inputs=live_inputs,
                    )
            reader.assert_not_called()

    def test_live_map_role_failure_precedes_result_reader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw).resolve()
            project, base, matrix_path, _, _, _ = self.make_live_matrix_fixture(directory)
            with mock.patch.object(
                qualify_m15_native_map,
                "validate_manifest",
                side_effect=AssertionError("unexpected live read"),
            ) as reader:
                with self.assertRaisesRegex(ArtifactContextError, "offline validation"):
                    run_m15_map_matrix.validate(
                        project,
                        matrix_path,
                        project / run_m15_map_matrix.SCHEMA_RELATIVE,
                        artifact_context=ArtifactContext.live(base),
                        live_inputs=LiveInputManifest.offline(),
                    )
            reader.assert_not_called()

    def test_required_live_inputs_are_the_exact_map_closure(self) -> None:
        requirements = run_m15_map_matrix.required_live_inputs(self.root)
        self.assertEqual(len(requirements), 177)
        self.assertEqual(requirements[0].relative_path, ".")
        self.assertEqual(
            tuple((item.relative_path, item.kind) for item in requirements[1:3]),
            (
                ("map-0064x0064", "directory"),
                ("map-0064x0064/m15-map-qualification.json", "file"),
            ),
        )
        self.assertIn(
            "map-0064x0064/openttd-map-console.log",
            {item.relative_path for item in requirements},
        )
        self.assertIn(
            "map-0064x0064/save/m15-map.sav",
            {item.relative_path for item in requirements},
        )
        self.assertEqual({item.logical_set for item in requirements}, {"v2-m15-map-matrix-a"})
        self.assertEqual({item.consumer for item in requirements}, {"m15-map-matrix"})
        roles = run_m15_map_matrix.required_live_roles(self.root)
        self.assertEqual(len(roles), 1)
        self.assertEqual(roles[0].role, "m14-openttd-executable")
        self.assertEqual(roles[0].expected_sha256, self.matrix["executable"]["sha256"])
        complete = validate_m15_map_evidence.required_live_inputs(self.root)
        self.assertEqual(complete, (*requirements, *roles))

    def test_creation_artifact_root_is_not_a_validation_base(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = pathlib.Path(raw).resolve() / "new-matrix"
            with (
                mock.patch("sys.stderr", new_callable=io.StringIO),
                self.assertRaises(SystemExit) as raised,
            ):
                run_m15_map_matrix.main([
                    "--root", str(self.root),
                    "--artifact-root", str(target),
                    "--evidence", str(self.matrix_path),
                ])
        self.assertEqual(raised.exception.code, 2)
        self.assertFalse(target.exists())

    def test_incomplete_explicit_creation_option_exits_two(self) -> None:
        with (
            mock.patch("sys.stderr", new_callable=io.StringIO),
            self.assertRaises(SystemExit) as raised,
        ):
            run_m15_map_matrix.main(["--root", str(self.root), "--workers", "1"])
        self.assertEqual(raised.exception.code, 2)

    def test_validation_only_cli_owns_offline_map_validation(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(self.root / "scripts/v2/validate_m15_map_evidence.py"),
                "--root",
                str(self.root),
            ],
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("V2_M15_MAP_EVIDENCE=PASS", result.stdout)

    def test_validation_only_cli_loads_the_host_role_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = pathlib.Path(raw).resolve()
            live_inputs = mock.sentinel.live_inputs
            summary = run_m15_map_matrix.M15MapMatrixSummary(
                rectangles=49,
                generated=39,
                preflight_rejected=10,
                save_bytes=2881300,
                maximum_rss_kib=89104,
                live_artifacts=True,
            )
            with (
                mock.patch.object(
                    validate_m15_map_evidence.LiveInputManifest,
                    "load",
                    return_value=live_inputs,
                ) as loader,
                mock.patch.object(
                    validate_m15_map_evidence.matrix,
                    "validate",
                    return_value=summary,
                ) as validator,
                mock.patch("sys.stdout", new_callable=io.StringIO),
            ):
                result = validate_m15_map_evidence.main([
                    "--root", str(self.root),
                    "--artifact-root", str(base),
                ])
        self.assertEqual(result, 0)
        loader.assert_called_once_with(base)
        context = validator.call_args.kwargs["artifact_context"]
        self.assertTrue(context.is_live)
        self.assertEqual(context.artifact_root, base)
        self.assertIs(validator.call_args.kwargs["live_inputs"], live_inputs)

    def test_generated_matrix_is_not_published_when_live_validation_fails(self) -> None:
        manifests: dict[pathlib.Path, dict[str, object]] = {}

        def run_one(
            _root: pathlib.Path,
            _openttd: pathlib.Path,
            artifact_root: pathlib.Path,
            width: int,
            height: int,
            _seed: int,
            _sandbox: str,
        ) -> tuple[tuple[int, int], str]:
            run_root = artifact_root / f"map-{width:04d}x{height:04d}"
            run_root.mkdir()
            evidence_path = run_root / qualify_m15_native_map.EVIDENCE_NAME
            evidence_path.write_text("{}\n", encoding="utf-8")
            generated = width * height <= qualify_m15_native_map.MAXIMUM_GENERATED_TILES
            manifests[evidence_path] = {
                "engine_source": self.matrix["engine_source"],
                "executable": self.matrix["executable"],
                "contract_sha256": self.matrix["contract_sha256"],
                "request": {"width": width, "height": height, "tile_count": width * height},
                "outcome": "GENERATED" if generated else "PREFLIGHT_REJECTED",
                "reason_code": None if generated else "tile-count-exceeds-useful-play-preflight-budget",
                "observations": {
                    "save": ({"size": 1, "sha256": "1" * 64} if generated else None),
                    "map": ({"map_sha256": "2" * 64} if generated else None),
                },
                "resources": {"max_rss_kib": 1 if generated else 0, "wall_seconds": 0},
            }
            return (width, height), "fixture"

        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw).resolve()
            executable = directory / "openttd"
            executable.write_bytes(b"fixture executable")
            target = directory / "new-matrix"
            with (
                mock.patch.object(run_m15_map_matrix, "run_one", side_effect=run_one),
                mock.patch.object(
                    qualify_m15_native_map,
                    "validate_manifest",
                    side_effect=lambda _root, path, **_kwargs: manifests[path],
                ),
                mock.patch.object(
                    run_m15_map_matrix,
                    "validate",
                    side_effect=run_m15_map_matrix.M15MapMatrixError("generated validation failed"),
                ),
                mock.patch("builtins.print"),
            ):
                with self.assertRaisesRegex(run_m15_map_matrix.M15MapMatrixError, "generated validation failed"):
                    run_m15_map_matrix.run_matrix(
                        self.root,
                        executable,
                        target,
                        self.matrix["seed"],
                        workers=1,
                        sandbox="test-none",
                    )
            self.assertFalse((target / run_m15_map_matrix.EVIDENCE_NAME).exists())

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
            with self.assertRaisesRegex(ArtifactContextError, "missing"):
                run_m15_map_matrix.validate(
                    self.root,
                    artifact_context=ArtifactContext.live(pathlib.Path(raw).resolve()),
                    live_inputs=LiveInputManifest.offline(),
                )

    def test_freeze_helper_keeps_supported_live_validation_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw).resolve()
            project, base, matrix_path, live_inputs, manifests, _ = self.make_live_matrix_fixture(directory)
            output = directory / "published" / "map.json"
            requirement = run_m15_map_matrix.required_live_roles(project, matrix_path)[0]
            executable = live_inputs.resolve(requirement)
            with (
                mock.patch.object(
                    qualify_m15_native_map,
                    "validate_manifest",
                    side_effect=lambda _root, path, **_kwargs: manifests[path],
                ),
                mock.patch.object(sys, "argv", [
                    str(project / "scripts/v2/freeze_m15_map_evidence.py"),
                    "--root", str(project),
                    "--artifact-matrix", str(matrix_path),
                    "--artifact-base", str(base),
                    "--openttd", str(executable),
                    "--output", str(output),
                ]),
                mock.patch("sys.stdout", new_callable=io.StringIO),
            ):
                result = freeze_m15_map_evidence.main()
                published = output.is_file()
        self.assertEqual(result, 0)
        self.assertTrue(published)


if __name__ == "__main__":
    unittest.main()
