#!/usr/bin/env python3
"""Native delta, actual-engine reward goldens, and G06 evidence guards."""

from __future__ import annotations

import hashlib
import pathlib
import tempfile
import unittest

import jsonschema
import prepare_openttd_source
import run_m02_map_feasibility
import run_m04_observation
import run_m05_actions
import run_m06_reward_trajectory
import validate_m02_scenario_contract
import validate_m06_reward_contract


class V1M06RewardNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.patch = cls.root / "integration/openttd/patches/15.3/m06/0007-native-reward-termination.patch"
        cls.series = cls.patch.parent / "series"
        cls.goldens_path = cls.root / "tests/fixtures/v1/m06-reward-goldens.json"
        cls.goldens = validate_m06_reward_contract.load_strict_json(cls.goldens_path)

    def test_native_delta_and_composed_identities_are_exact(self) -> None:
        run_m06_reward_trajectory.validate_native_delta(self.root)
        self.assertEqual(hashlib.sha256(self.patch.read_bytes()).hexdigest(), run_m06_reward_trajectory.M06_PATCH_SHA256)
        self.assertEqual(hashlib.sha256(self.series.read_bytes()).hexdigest(), run_m06_reward_trajectory.M06_SERIES_SHA256)
        self.assertEqual(run_m06_reward_trajectory.M06_RESULT_TREE, "56b7f68297cb1ec7548c25ac9dfa0d0088e70547")
        self.assertEqual(run_m06_reward_trajectory.M06_COMPOSED_SOURCE_IDENTITY, "98693ab0595fb26612079683a192a12f7bce6bb4cb25a7edf895244c50c568a2")

    def test_m06_delta_applies_exactly_after_accepted_m05_tree(self) -> None:
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
            prepare_openttd_source.apply_patches(
                source,
                [self.root / oracle["native_delta"]["patches"][0]["path"]],
                plan["source"]["result_tree"],
            )
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
            prepare_openttd_source.apply_patches(
                source,
                [self.root / "integration/openttd/patches/15.3/m05/0006-explicit-bus-actions-and-masks.patch"],
                run_m05_actions.M04_RESULT_TREE,
            )
            self.assertEqual(prepare_openttd_source.git(source, "write-tree"), run_m06_reward_trajectory.M05_RESULT_TREE)
            prepare_openttd_source.apply_patches(source, [self.patch], run_m06_reward_trajectory.M05_RESULT_TREE)
            result_tree = prepare_openttd_source.git(source, "write-tree")
            self.assertEqual(result_tree, run_m06_reward_trajectory.M06_RESULT_TREE)
            self.assertEqual(
                run_m02_map_feasibility.composed_source_identity(
                    run_m06_reward_trajectory.M05_COMPOSED_SOURCE_IDENTITY,
                    run_m06_reward_trajectory.M06_SERIES_SHA256,
                    [
                        {
                            "order": 7,
                            "path": self.patch.relative_to(self.root).as_posix(),
                            "sha256": run_m06_reward_trajectory.M06_PATCH_SHA256,
                        }
                    ],
                    result_tree,
                ),
                run_m06_reward_trajectory.M06_COMPOSED_SOURCE_IDENTITY,
            )

    def test_native_projection_sums_quarters_and_retains_all_components_before_left_fold(self) -> None:
        text = self.patch.read_text(encoding="utf-8")
        self.assertIn("company->cur_economy", text)
        self.assertIn("company->num_valid_stat_ent", text)
        self.assertIn("company->old_economy[index]", text)
        self.assertIn("std::array<int64_t, 8> raw", text)
        self.assertIn("std::clamp(raw[index]", text)
        self.assertIn("scalar += weighted", text)
        self.assertIn("weighted_float64_bits", text)
        self.assertIn("ACTION_AND_TICK_HORIZON", text)
        self.assertIn("pre.company_present && !post.company_present", text)
        self.assertIn("post.stopped_primary_bus_count * static_cast<int64_t>(advanced_ticks)", text)
        self.assertNotIn("station_rating", text)
        self.assertNotIn("town-percent", text)

    def test_actual_engine_goldens_are_schema_valid_complete_and_byte_reproducible(self) -> None:
        schema_path = self.root / "docs/project/schema/v1-m06-reward-oracle-report.schema.json"
        self.assertEqual(hashlib.sha256(schema_path.read_bytes()).hexdigest(), run_m06_reward_trajectory.REPORT_SCHEMA_SHA256)
        schema = validate_m06_reward_contract.load_strict_json(schema_path)
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(self.goldens)
        self.assertEqual(hashlib.sha256(self.goldens_path.read_bytes()).hexdigest(), "6b72ac4e4a21667bcbc40ae4dde6a0b2e16ebad53109b45f4d03c4939c6dfce7")
        self.assertEqual(self.goldens["status"], "PASS")
        self.assertEqual(self.goldens["executable_sha256"], "765c108213bfbb23df2712956acb9bbf6bbb5b0a1d446b0ec154a94fbf41876c")
        self.assertEqual(self.goldens["trajectory"]["record_count"], 128)
        self.assertEqual(self.goldens["trajectory"]["observation_blob_count"], 129)
        self.assertEqual(self.goldens["horizon_and_rollover"]["quarter_counter_resets"], 9)
        self.assertEqual(self.goldens["horizon_and_rollover"]["relative_ticks"], 65_536)
        self.assertEqual([item["template_id"] for item in self.goldens["actual_engine_templates"]], [f"m02-template-{index:02d}" for index in range(1, 9)])
        self.assertTrue(all(item["delivered_passengers"] > 0 and item["income"] > 0 for item in self.goldens["actual_engine_templates"]))

    def test_exploit_and_terminal_goldens_are_fail_closed(self) -> None:
        exploits = self.goldens["exploit_campaign"]
        for name in ("construction_return", "cycling_return", "idle_return", "native_rejection_return", "noop_return", "vehicle_loss_return"):
            self.assertLessEqual(exploits[name], 0.0, name)
        self.assertEqual(exploits["duplicate_attempt_advanced_ticks"], 0)
        self.assertFalse(exploits["duplicate_attempt_rewarded"])
        self.assertTrue(exploits["bankruptcy_terminal"])
        self.assertFalse(exploits["bankruptcy_bootstrap"])
        self.assertLessEqual(exploits["bankruptcy_return"], -8.0)


if __name__ == "__main__":
    unittest.main()
