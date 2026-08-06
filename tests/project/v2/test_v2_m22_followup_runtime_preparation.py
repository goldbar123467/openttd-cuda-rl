#!/usr/bin/env python3
"""Offline and mutation tests for corrected M22 follow-up-runtime preparation."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import jsonschema

from artifact_context import ArtifactContext, resolve_artifact_root
import m22_final_native as native
import prepare_m22_followup_runtime as preparation
import validate_m22_followup_runtime_source as validator


class M22FollowupRuntimePreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.schema = validator.load(cls.root / preparation.SCHEMA)
        cls.m21 = validator.load(cls.root / preparation.foundation.M21_SOURCE)

    @staticmethod
    def fake_file(name: str) -> dict[str, object]:
        return {"bytes": 1, "path": f"/retained/{name}", "sha256": "0" * 64}

    def fake_record(self) -> dict[str, object]:
        source_tree = "2" * 40
        smokes = []
        for case in preparation.SMOKE_CASES:
            smokes.append({
                "artifact_root": f"/retained/smokes/{case['case_id']}", "case": native.public_case(case),
                "executable_sha256": "3" * 64, "fresh_processes": 1, "manifest_path": "manifest.json",
                "manifest_sha256": "4" * 64, "metrics": {"value": 1},
                "native_probe": native.canonical_probe(case), "network_unshared": True,
                "openttd_log_path": "openttd.log", "openttd_log_sha256": "5" * 64,
                "private_seed": case["seed"], "report_path": "report.json", "report_sha256": "6" * 64,
                "source_tree": source_tree, "status": "PASS", "wall_seconds": 1.0,
            })
        return {
            "base": {"commit": "7" * 40, "source_record_sha256": "8" * 64, "tree": "9" * 40},
            "boundaries": {
                "followup": {"evaluator_processes": 0, "manifest_opened": False, "native_dispatches": 0,
                             "protocol_state": "not-yet-frozen"},
                "immutable_final_v1": {"evidence_path": str(preparation.IMMUTABLE_FINAL_EVIDENCE),
                                       "evidence_sha256": "a" * 64, "evaluator_processes": 0,
                                       "manifest_opened": False, "native_dispatches": 0, "status": "FAIL"},
            },
            "build": {"cmake_arguments": list(preparation.foundation.CMAKE_ARGUMENTS), "generator": "Ninja",
                      "jobs": 8, "logs": {name: self.fake_file(name)
                                           for name in ("build", "configure", "ctest", "junit")},
                      "test_inventory": self.fake_file("inventory"),
                      "upstream_ctest": {"passed": 98, "total": 98}},
            "executable": {"bytes": 1, "path": "/retained/build-followup/openttd", "sha256": "3" * 64},
            "patches": [
                {"path": str(path), "sha256": chr(ord("b") + index) * 64, "touched_files": list(touched)}
                for index, (path, touched) in enumerate(zip(preparation.PATCHES, preparation.PATCH_TOUCHED, strict=True))
            ],
            "prerequisites": {"final_runtime_source_record_sha256": "d" * 64,
                              "m20_source_record_sha256": "e" * 64,
                              "m21_source_record_sha256": "f" * 64},
            "repository": {"commit": "1" * 40, "tree": "e" * 40}, "retained_artifact": "/retained",
            "runtime": {
                "ai_archives": [{"name": name, **self.fake_file(f"ai-{index}")}
                                for index, name in enumerate(("AAAHogEx", "KrakenAI2", "NoOpAI"))],
                "ai_libraries": [self.fake_file(f"library-{index}") for index in range(4)],
                "configs": {name: self.fake_file(f"{name}.cfg") for name in ("base", "content", "gamescript")},
                "gamescript_files": [self.fake_file(f"gamescript-{index}") for index in range(2)],
                "network_calls_during_preparation": "none",
                "newgrf_archives": [self.fake_file(f"newgrf-archive-{index}") for index in range(10)],
                "newgrf_files": [self.fake_file(f"newgrf-{index}") for index in range(10)],
                "open_gfx": self.fake_file("opengfx"),
            },
            "schema_version": "openttd-rl-v2-m22-followup-runtime-source-1", "smokes": smokes,
            "source": {"commit": "f" * 40, "path": "/retained/source", "tree": source_tree}, "status": "PASS",
        }

    def test_schema_accepts_complete_closed_preparation_record(self) -> None:
        jsonschema.Draft202012Validator(self.schema).validate(self.fake_record())

    def test_schema_rejects_unknown_property_and_manifest_access(self) -> None:
        record = self.fake_record()
        record["unknown"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(record)
        record = self.fake_record()
        record["boundaries"]["followup"]["manifest_opened"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(record)

    def test_fixed_smokes_cover_foundation_and_every_diagnosed_boundary(self) -> None:
        self.assertEqual(len(preparation.SMOKE_CASES), 14)
        correction = preparation.SMOKE_CASES[8:]
        self.assertEqual([case["native_probe"] for case in correction],
                         ["multimodal", "head-to-head", "head-to-head", "head-to-head",
                          "authority-economy", "events"])
        self.assertEqual([case["opponent"] for case in correction[1:4]],
                         ["AAAHogEx", "KrakenAI2", "NoOpAI"])
        self.assertTrue(all(case["map_width"] == case["map_height"] == 128 for case in correction[1:4]))

    def test_smoke_seeds_are_absent_from_immutable_final_v1(self) -> None:
        final = validator.load(self.root / preparation.IMMUTABLE_FINAL_EVIDENCE)
        final_seeds = {run["private_seed"] for run in final["runs"]}
        smoke_seeds = {case["seed"] for case in preparation.SMOKE_CASES}
        self.assertEqual(len(smoke_seeds), 14)
        self.assertFalse(final_seeds & smoke_seeds)

    def test_public_projection_omits_seed_and_required_program(self) -> None:
        for case in preparation.SMOKE_CASES:
            public = native.public_case(case)
            self.assertEqual(tuple(public), native.PUBLIC_FIELDS)
            self.assertNotIn("seed", public)
            self.assertNotIn("required_program", public)

    def test_preparer_has_no_evaluation_manifest_path_or_case_loader(self) -> None:
        source = (self.root / "scripts/v2/prepare_m22_followup_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("m22-evaluation-manifest.json", source)
        self.assertNotIn("m22-followup-manifest.json", source)
        self.assertNotIn("subprocess.Popen", source)

    def test_patch_series_scope_and_required_tokens_pass(self) -> None:
        record = self.fake_record()
        for item, path in zip(record["patches"], preparation.PATCHES, strict=True):
            item["sha256"] = preparation.foundation.sha256(self.root / path)
        validator.validate_patch_series(self.root, record)

    def test_source_commit_is_reproducible_from_accepted_m21_base(self) -> None:
        artifact_root = resolve_artifact_root(None)
        if artifact_root is None:
            self.skipTest("live artifact validation is outside offline mode")
        context = ArtifactContext.live(artifact_root)
        base = context.artifact_set("v2-m21-broad-a") / "source"
        patches = tuple((self.root / path).resolve() for path in preparation.PATCHES)
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            first = preparation.prepare_source(base, directory / "first", patches, self.m21["source"]["commit"])
            second = preparation.prepare_source(base, directory / "second", patches, self.m21["source"]["commit"])
        self.assertEqual((first["commit"], first["tree"]), (second["commit"], second["tree"]))
        self.assertEqual(first["tree"], "f8985045f9ba14bad1e46a81cb58fdbb8037f277")

    def test_source_reproduction_skips_offline_without_probing_recorded_path(self) -> None:
        with mock.patch.object(pathlib.Path, "is_dir", side_effect=AssertionError("offline path probe")):
            self.assertIsNone(resolve_artifact_root(None, {}))

    def test_smoke_parent_exists_before_first_native_dispatch(self) -> None:
        runtime = native.RuntimePaths(*(pathlib.Path("/not-used") for _ in range(5)), source_tree="0" * 40)
        with tempfile.TemporaryDirectory() as raw:
            artifact = pathlib.Path(raw)

            def dispatch(_root: pathlib.Path, _runtime: native.RuntimePaths, case_root: pathlib.Path,
                         case: dict[str, object]) -> dict[str, object]:
                self.assertTrue(case_root.parent.is_dir())
                return {"case": native.public_case(case)}

            with mock.patch.object(native, "run_native_case", side_effect=dispatch) as patched:
                records = preparation.run_smokes(self.root, artifact, runtime)
            self.assertEqual((len(records), patched.call_count), (14, 14))

    def test_output_writer_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "record.json"
            preparation.foundation.write_new(path, {"value": 1})
            with self.assertRaisesRegex(preparation.foundation.M22RuntimePreparationError, "already exists"):
                preparation.foundation.write_new(path, {"value": 2})

    def test_supported_run_routes_one_common_artifact_context(self) -> None:
        fake = self.fake_record()
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw).resolve()
            context = ArtifactContext.live(directory / "inputs")
            artifact = directory / "runtime-output"
            evidence = directory / "evidence.json"

            def fake_git(_repository: pathlib.Path, *arguments: str) -> str:
                if arguments == ("status", "--porcelain"):
                    return ""
                if arguments == ("rev-parse", "HEAD"):
                    return fake["repository"]["commit"]
                if arguments == ("rev-parse", "HEAD^{tree}"):
                    return fake["repository"]["tree"]
                raise AssertionError(arguments)

            with mock.patch.object(preparation.foundation, "git", side_effect=fake_git), \
                 mock.patch.object(preparation.foundation.m20_source, "validate") as m20_validate, \
                 mock.patch.object(preparation.foundation.m21_source, "validate") as m21_validate, \
                 mock.patch.object(preparation, "prepare_source", return_value=fake["source"]) as prepare_source, \
                 mock.patch.object(preparation.foundation, "configure_and_build",
                                   return_value=(fake["build"], fake["runtime"]["open_gfx"])), \
                 mock.patch.object(preparation.foundation, "stage_runtime", return_value=fake["runtime"]) as stage_runtime, \
                 mock.patch.object(preparation.foundation, "file_record", return_value=fake["executable"]), \
                 mock.patch.object(preparation, "run_smokes", return_value=fake["smokes"]):
                result = preparation.run(
                    self.root, artifact, evidence, jobs=2, artifact_context=context,
                )

        self.assertEqual(result["retained_artifact"], str(artifact))
        m20_validate.assert_called_once_with(self.root.resolve(), artifact_context=context)
        m21_validate.assert_called_once_with(self.root.resolve(), artifact_context=context)
        self.assertEqual(prepare_source.call_args.args[0], context.artifact_set("v2-m21-broad-a") / "source")
        self.assertIs(stage_runtime.call_args.args[3], context)

    def test_schema_file_is_valid(self) -> None:
        jsonschema.Draft202012Validator.check_schema(self.schema)
        mutated = copy.deepcopy(self.fake_record())
        mutated["patches"].reverse()
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(mutated)


if __name__ == "__main__":
    unittest.main()
