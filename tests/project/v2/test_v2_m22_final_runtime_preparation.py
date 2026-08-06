#!/usr/bin/env python3
"""Offline and mutation tests for M22 final-runtime preparation."""

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
import prepare_m22_final_runtime as preparation
import validate_m22_final_runtime_source as validator


class M22FinalRuntimePreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.schema = validator.load(cls.root / preparation.SCHEMA)
        cls.m21 = validator.load(cls.root / preparation.M21_SOURCE)

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
            "build": {"cmake_arguments": list(preparation.CMAKE_ARGUMENTS), "generator": "Ninja", "jobs": 8,
                      "logs": {name: self.fake_file(name) for name in ("build", "configure", "ctest", "junit")},
                      "test_inventory": self.fake_file("inventory"), "upstream_ctest": {"passed": 98, "total": 98}},
            "executable": {"bytes": 1, "path": "/retained/build-final/openttd", "sha256": "3" * 64},
            "final_boundary": {"expected_manifest_sha256": "a" * 64, "manifest_executions": 0,
                               "manifest_opened": False},
            "patch": {"path": str(preparation.PATCH), "sha256": "b" * 64,
                      "touched_files": list(preparation.TOUCHED)},
            "prerequisites": {"m20_source_record_sha256": "c" * 64, "m21_source_record_sha256": "d" * 64},
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
            "schema_version": "openttd-rl-v2-m22-final-runtime-source-1", "smokes": smokes,
            "source": {"commit": "f" * 40, "path": "/retained/source", "tree": source_tree}, "status": "PASS",
        }

    def test_schema_accepts_complete_closed_preparation_record(self) -> None:
        jsonschema.Draft202012Validator(self.schema).validate(self.fake_record())

    def test_schema_rejects_hidden_seed_in_public_case(self) -> None:
        record = self.fake_record()
        record["smokes"][0]["case"]["seed"] = 1
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(record)

    def test_source_smoke_inventory_covers_every_native_gate(self) -> None:
        self.assertEqual([case["source_gate"] for case in preparation.SMOKE_CASES],
                         ["G15", "G16", "G17", "G18", "G19", "G20", "G21", "G21"])
        self.assertEqual(len({case["case_id"] for case in preparation.SMOKE_CASES}), 8)
        self.assertEqual({case["climate"] for case in preparation.SMOKE_CASES}, {"arctic", "tropic", "toyland"})

    def test_public_projection_omits_seed_and_required_program(self) -> None:
        for case in preparation.SMOKE_CASES:
            public = native.public_case(case)
            self.assertEqual(tuple(public), native.PUBLIC_FIELDS)
            self.assertNotIn("seed", public)
            self.assertNotIn("required_program", public)

    def test_g15_resource_tier_covers_the_complete_final_map_domain(self) -> None:
        self.assertEqual(native.resource_tier(64, 64), "curriculum")
        self.assertEqual(native.resource_tier(512, 128), "curriculum")
        self.assertEqual(native.resource_tier(512, 1024), "generalization")
        self.assertEqual(native.resource_tier(1024, 1024), "generalization")

    def test_preparation_has_no_final_manifest_path_or_case_loader(self) -> None:
        source = (self.root / "scripts/v2/prepare_m22_final_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("m22-evaluation-manifest.json", source)
        self.assertNotIn("required_program=", source)
        self.assertNotIn("subprocess.Popen", source)

    def test_opengfx_is_staged_before_upstream_ctest(self) -> None:
        source = (self.root / "scripts/v2/prepare_m22_final_runtime.py").read_text(encoding="utf-8")
        function = source[source.index("def configure_and_build"):source.index("def stage_runtime")]
        self.assertLess(function.index("open_gfx = copy_exact"), function.index("inventory_raw = checked"))

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
            self.assertEqual((len(records), patched.call_count), (8, 8))

    def test_output_writer_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "record.json"
            preparation.write_new(path, {"value": 1})
            with self.assertRaisesRegex(preparation.M22RuntimePreparationError, "already exists"):
                preparation.write_new(path, {"value": 2})

    def test_cumulative_patch_scope_and_tokens_pass(self) -> None:
        validator.validate_patch(self.root, {"path": str(preparation.PATCH),
                                 "sha256": preparation.sha256(self.root / preparation.PATCH),
                                 "touched_files": list(preparation.TOUCHED)})

    def test_source_commit_is_reproducible_from_accepted_m21_base(self) -> None:
        artifact_root = resolve_artifact_root(None)
        if artifact_root is None:
            self.skipTest("live artifact validation is outside offline mode")
        context = ArtifactContext.live(artifact_root)
        base = context.artifact_set("v2-m21-broad-a") / "source"
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            first = preparation.prepare_source(base, directory / "first", self.root / preparation.PATCH,
                                               self.m21["source"]["commit"])
            second = preparation.prepare_source(base, directory / "second", self.root / preparation.PATCH,
                                                self.m21["source"]["commit"])
            self.assertEqual((first["commit"], first["tree"]), (second["commit"], second["tree"]))

    def test_source_reproduction_skips_offline_without_probing_recorded_path(self) -> None:
        with mock.patch.object(pathlib.Path, "is_dir", side_effect=AssertionError("offline path probe")):
            self.assertIsNone(resolve_artifact_root(None, {}))

    def test_schema_closure_rejects_unknown_top_level_property(self) -> None:
        record = copy.deepcopy(self.fake_record())
        record["unknown"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(self.schema).validate(record)

    def test_schema_file_is_canonical_json(self) -> None:
        encoded = json.loads((self.root / preparation.SCHEMA).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(encoded)


if __name__ == "__main__":
    unittest.main()
