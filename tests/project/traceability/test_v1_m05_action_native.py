#!/usr/bin/env python3
"""Native delta, source invariants, and actual-engine golden guards for M05."""

from __future__ import annotations

import hashlib
import pathlib
import tempfile
import unittest

import jsonschema
import m05_action_adapter
import prepare_openttd_source
import run_m02_map_feasibility
import run_m04_observation
import run_m05_actions
import validate_m02_scenario_contract
import validate_m05_action_contract


class V1M05ActionNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.patch = cls.root / "integration/openttd/patches/15.3/m05/0006-explicit-bus-actions-and-masks.patch"
        cls.series = cls.patch.parent / "series"
        cls.goldens_path = cls.root / "tests/fixtures/v1/m05-action-goldens.json"
        cls.goldens = validate_m05_action_contract.load_strict_json(cls.goldens_path)

    def test_native_delta_and_composed_identities_are_exact(self) -> None:
        run_m05_actions.validate_native_delta(self.root)
        self.assertEqual(hashlib.sha256(self.patch.read_bytes()).hexdigest(), run_m05_actions.M05_PATCH_SHA256)
        self.assertEqual(hashlib.sha256(self.series.read_bytes()).hexdigest(), run_m05_actions.M05_SERIES_SHA256)

    def test_m05_delta_applies_exactly_after_accepted_m04_tree(self) -> None:
        plan = run_m02_map_feasibility.load_strict_json(self.root / "config/v1/m02-map-feasibility-plan.json")
        oracle = validate_m02_scenario_contract.load_strict_json(self.root / "config/v1/m02-reset-oracle.json")
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
            prepare_openttd_source.apply_patches(source, [self.root / oracle["native_delta"]["patches"][0]["path"]], plan["source"]["result_tree"])
            self.assertEqual(prepare_openttd_source.git(source, "write-tree"), oracle["native_delta"]["result_tree"])
            prepare_openttd_source.apply_patches(
                source,
                [self.root / "integration/openttd/patches/15.3/m03/0004-synchronized-environment-bridge.patch"],
                oracle["native_delta"]["result_tree"],
            )
            self.assertEqual(prepare_openttd_source.git(source, "write-tree"), run_m04_observation.M03_RESULT_TREE)
            prepare_openttd_source.apply_patches(
                source,
                [self.root / "integration/openttd/patches/15.3/m04/0005-versioned-policy-observation.patch"],
                run_m04_observation.M03_RESULT_TREE,
            )
            self.assertEqual(prepare_openttd_source.git(source, "write-tree"), run_m05_actions.M04_RESULT_TREE)
            prepare_openttd_source.apply_patches(source, [self.patch], run_m05_actions.M04_RESULT_TREE)
            result_tree = prepare_openttd_source.git(source, "write-tree")
            self.assertEqual(result_tree, run_m05_actions.M05_RESULT_TREE)
            self.assertEqual(
                run_m02_map_feasibility.composed_source_identity(
                    run_m05_actions.M04_COMPOSED_SOURCE_IDENTITY,
                    run_m05_actions.M05_SERIES_SHA256,
                    [{"order": 6, "path": self.patch.relative_to(self.root).as_posix(), "sha256": run_m05_actions.M05_PATCH_SHA256}],
                    result_tree,
                ),
                run_m05_actions.M05_COMPOSED_SOURCE_IDENTITY,
            )

    def test_mask_generation_uses_test_mode_without_ticks_rng_or_gui(self) -> None:
        text = self.patch.read_text(encoding="utf-8")
        action_source = text.split("diff --git a/src/rl_action.cpp", 1)[1].split("diff --git a/src/rl_action.h", 1)[0]
        native_legal = action_source.split("static bool NativeLegal", 1)[1].split("static json Parameters", 1)[0]
        self.assertIn("BuildRlActionMask", action_source)
        self.assertIn("Command<CMD_BUILD_LONG_ROAD>::Do({}", native_legal)
        self.assertIn("Command<CMD_BUILD_ROAD_STOP>::Do({}", native_legal)
        self.assertIn("Command<CMD_BUILD_ROAD_DEPOT>::Do({}", native_legal)
        self.assertIn("Command<CMD_BUILD_VEHICLE>::Do({}", native_legal)
        self.assertIn("Command<CMD_INSERT_ORDER>::Do({}", native_legal)
        self.assertIn("Command<CMD_START_STOP_VEHICLE>::Do({}", native_legal)
        for forbidden in ("DoCommandFlag::Execute", "StateGameLoop", "Random()", "RandomRange(", "InteractiveRandom("):
            self.assertNotIn(forbidden, native_legal)
        self.assertNotIn("::Post(", action_source)
        self.assertNotIn("road_gui", action_source)

    def test_execution_uses_all_required_normal_commands_and_explicit_rollback(self) -> None:
        text = self.patch.read_text(encoding="utf-8")
        for command in (
            "CMD_BUILD_LONG_ROAD",
            "CMD_BUILD_ROAD_STOP",
            "CMD_BUILD_ROAD_DEPOT",
            "CMD_BUILD_VEHICLE",
            "CMD_DELETE_ORDER",
            "CMD_INSERT_ORDER",
            "CMD_START_STOP_VEHICLE",
        ):
            self.assertIn(command, text)
        self.assertIn("RollbackOrders", text)
        self.assertIn('"ROLLBACK"', text)
        self.assertIn('"route-after-first-order"', text)
        self.assertIn('"NATIVE_REJECTED"', text)
        self.assertIn('"INTEGRATION_FAILURE"', text)
        self.assertIn("for (uint32_t tick = 0; tick < MAXIMUM_ACTION_INTERVAL_TICKS; ++tick) StateGameLoop();", text)

    def test_catalog_identity_count_and_m03_fixture_removal_are_native_constants(self) -> None:
        text = self.patch.read_text(encoding="utf-8")
        self.assertIn("RL_ACTION_COUNT = 41", text)
        self.assertIn("215c7d3ebeea97f1629debee4a2d10301838ccfd3085e4828685591677b58536", text)
        self.assertIn("-\t\t\tApplyRlEnvironmentBridgeScriptedBusSetup();", text)
        self.assertIn("BuildRlActionMask", text)
        self.assertIn("RlActionMaskToken", text)

    def test_actual_engine_golden_fixture_is_frozen_and_complete(self) -> None:
        report_schema_path = self.root / "docs/project/schema/v1-m05-action-oracle-report.schema.json"
        self.assertEqual(hashlib.sha256(report_schema_path.read_bytes()).hexdigest(), run_m05_actions.REPORT_SCHEMA_SHA256)
        jsonschema.Draft202012Validator.check_schema(validate_m05_action_contract.load_strict_json(report_schema_path))
        self.assertEqual(
            hashlib.sha256(self.goldens_path.read_bytes()).hexdigest(),
            "6b7eee349e2d4ba6fa37c790b0d4491b385bc9a1b84c179eaa9af1f1cfa92d69",
        )
        self.assertEqual(self.goldens["action_compatibility_sha256"], m05_action_adapter.ACTION_COMPATIBILITY_SHA256)
        self.assertEqual(self.goldens["executable_sha256"], "ed23eeaea1f9deba1333c7ae3be1a8d16f30c203e706ce61b5a5138241f79094")
        self.assertEqual(self.goldens["manifest_sha256"], "30700cfb8a556ddd7c23eec7463bac7a7f2bf365b9a94742fdeddd982cb2d7b8")
        self.assertEqual(self.goldens["mask_differential_states"], 614)
        self.assertEqual([item["template_id"] for item in self.goldens["templates"]], [f"m02-template-{number:02d}" for number in range(1, 9)])
        for item in self.goldens["templates"]:
            self.assertGreater(item["income"], 0)
            self.assertGreater(item["delivered_passengers"], 0)
            self.assertGreaterEqual(item["transitions"], item["wait_actions"])


if __name__ == "__main__":
    unittest.main()
