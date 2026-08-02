#!/usr/bin/env python3
"""Source-delta, actual-engine golden, and non-perturbation guards for M04."""

from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile
import unittest

import jsonschema

import prepare_openttd_source
import run_m02_map_feasibility
import run_m03_bridge
import run_m04_observation
import validate_m02_scenario_contract
import validate_m04_observation_contract


class V1M04ObservationNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.patch = cls.root / "integration/openttd/patches/15.3/m04/0005-versioned-policy-observation.patch"
        cls.series = cls.patch.parent / "series"
        cls.golden_path = cls.root / "tests/fixtures/v1/m04-observation-goldens.json"

    def test_native_delta_and_composed_identities_are_exact(self) -> None:
        run_m04_observation.validate_native_delta(self.root)
        self.assertEqual(hashlib.sha256(self.patch.read_bytes()).hexdigest(), run_m04_observation.M04_PATCH_SHA256)
        self.assertEqual(hashlib.sha256(self.series.read_bytes()).hexdigest(), run_m04_observation.M04_SERIES_SHA256)

    def test_m04_delta_applies_exactly_after_accepted_m03_tree(self) -> None:
        plan = run_m02_map_feasibility.load_strict_json(self.root / "config/v1/m02-map-feasibility-plan.json")
        oracle = validate_m02_scenario_contract.load_strict_json(self.root / "config/v1/m02-reset-oracle.json")
        m03_patch = self.root / "integration/openttd/patches/15.3/m03/0004-synchronized-environment-bridge.patch"
        with tempfile.TemporaryDirectory() as raw:
            temporary = pathlib.Path(raw)
            source = temporary / "source"
            prepare_openttd_source.prepare(
                root=self.root,
                profile_path=self.root / plan["source"]["base_profile_path"],
                profile_schema_path=self.root / "docs/project/schema/v1-source-profile.schema.json",
                manifest_schema_path=self.root / "docs/project/schema/v1-prepared-source-manifest.schema.json",
                object_repository_override=self.root / "openttd-upstream",
                output=source,
                manifest_path=temporary / "base.json",
            )
            _, feasibility_patches, _ = run_m02_map_feasibility.validate_delta_series(self.root, plan["source"])
            prepare_openttd_source.apply_patches(source, feasibility_patches, run_m02_map_feasibility.SOURCE_TREE)
            self.assertEqual(prepare_openttd_source.git(source, "write-tree"), plan["source"]["result_tree"])
            native_patch = self.root / oracle["native_delta"]["patches"][0]["path"]
            prepare_openttd_source.apply_patches(source, [native_patch], plan["source"]["result_tree"])
            self.assertEqual(prepare_openttd_source.git(source, "write-tree"), oracle["native_delta"]["result_tree"])
            prepare_openttd_source.apply_patches(source, [m03_patch], oracle["native_delta"]["result_tree"])
            self.assertEqual(prepare_openttd_source.git(source, "write-tree"), run_m04_observation.M03_RESULT_TREE)
            prepare_openttd_source.apply_patches(source, [self.patch], run_m04_observation.M03_RESULT_TREE)
            result_tree = prepare_openttd_source.git(source, "write-tree")
            self.assertEqual(result_tree, run_m04_observation.M04_RESULT_TREE)
            self.assertEqual(
                run_m02_map_feasibility.composed_source_identity(
                    run_m04_observation.M03_COMPOSED_SOURCE_IDENTITY,
                    run_m04_observation.M04_SERIES_SHA256,
                    [{"order": 5, "path": self.patch.relative_to(self.root).as_posix(), "sha256": run_m04_observation.M04_PATCH_SHA256}],
                    result_tree,
                ),
                run_m04_observation.M04_COMPOSED_SOURCE_IDENTITY,
            )

    def test_encoder_source_has_no_tick_command_rng_or_pathfinder_entrypoint(self) -> None:
        text = self.patch.read_text(encoding="utf-8")
        encoder = text.split("diff --git a/src/rl_observation.cpp", 1)[1]
        self.assertIn("EncodeRlObservation", encoder)
        self.assertIn("station->TileIsInCatchment", encoder)
        self.assertIn("GetRoadOwner", encoder)
        for forbidden in (
            "StateGameLoop();",
            "Command<",
            "Random()",
            "RandomRange(",
            "InteractiveRandom(",
            "Yapf",
            "NPF",
        ):
            self.assertNotIn(forbidden, encoder)

    def test_actual_engine_goldens_cover_all_templates_and_are_exact(self) -> None:
        golden = validate_m04_observation_contract.load_strict_json(self.golden_path)
        self.assertEqual(golden["compatibility_sha256"], "7f8a46af1fe2a2c23e755c71b3bc2d04c9a0d057c573e901e5c9ed9178ca13eb")
        self.assertEqual([item["template_id"] for item in golden["templates"]], [f"m02-template-{index:02d}" for index in range(1, 9)])
        self.assertEqual(len({item["post_setup_tensor_sha256"] for item in golden["templates"]}), 8)
        self.assertEqual(hashlib.sha256(self.golden_path.read_bytes()).hexdigest(), "1dce190b8e7216b03c5e45cc6ee0af050bf69aa773aecc051250a4288ccf3ec6")

    def test_oracle_report_schema_freezes_every_gate_claim(self) -> None:
        schema_path = self.root / "docs/project/schema/v1-m04-observation-oracle-report.schema.json"
        self.assertEqual(hashlib.sha256(schema_path.read_bytes()).hexdigest(), run_m04_observation.REPORT_SCHEMA_SHA256)
        schema = validate_m04_observation_contract.load_strict_json(schema_path)
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertEqual(schema["properties"]["total_semantic_comparisons"], {"const": 264192})
        self.assertEqual(schema["properties"]["nonperturbation"], {"const": "PASS"})
        self.assertEqual(schema["$defs"]["template"]["properties"]["spatial_comparisons"], {"const": 32768})


if __name__ == "__main__":
    unittest.main()
