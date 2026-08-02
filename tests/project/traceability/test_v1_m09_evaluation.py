#!/usr/bin/env python3
"""M09 preregistration, independent evaluator, runtime lock, and fairness guards."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import tempfile
import unittest

import jsonschema

import prepare_openttd_source
import run_m02_map_feasibility
import run_m04_observation
import run_m05_actions
import run_m06_reward_trajectory
import run_m09_evaluation
import validate_m02_scenario_contract
import validate_m09_evaluation_contract


class V1M09EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract_path = cls.root / "config/v1/m09-evaluation-contract.json"
        cls.schema_path = cls.root / "docs/project/schema/v1-m09-evaluation-contract.schema.json"
        cls.lock_path = cls.root / "config/v1/m09-runtime-lock.json"
        cls.lock_schema_path = cls.root / "docs/project/schema/v1-m09-runtime-lock.schema.json"

    def test_contract_and_runtime_lock_are_frozen_and_self_consistent(self) -> None:
        contract = validate_m09_evaluation_contract.validate(self.contract_path, self.schema_path)
        lock = validate_m09_evaluation_contract.validate_runtime_lock(self.lock_path, self.lock_schema_path)
        self.assertEqual(contract["identity"]["compatibility_sha256"], "c64c9876c1f6cf46dcc2642bd4628ed45f4659d1866a047d4e51def60dab9a5e")
        self.assertEqual(lock["native_delta"]["result_tree"], "a73dd3d6eb38cbdb8db7b67413f12375509c0466")
        self.assertEqual(lock["runtime"]["openttd_executable_sha256"], "8e61a1325090240cf084ad0a9d82376bf11082564bb0eb17ac4a1c8033158a0c")

    def test_preregistered_inventory_is_complete_and_fair(self) -> None:
        contract = validate_m09_evaluation_contract.validate(self.contract_path, self.schema_path)
        budget = contract["training_budget"]
        self.assertEqual(len(budget["architectures"]), 3)
        self.assertEqual(len(budget["run_seeds"]), 3)
        self.assertEqual(budget["accepted_samples_per_run"], budget["updates"] * budget["rollout_length"] * budget["environment_count"])
        self.assertEqual(len(contract["metrics"]), 15)
        self.assertEqual(len(contract["baselines"]), 3)
        self.assertFalse(contract["statistics"]["best_seed_claims"])
        self.assertFalse(contract["selection"]["final_results_used"])

    def test_contract_mutations_fail_closed(self) -> None:
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        mutations = []
        value = copy.deepcopy(contract)
        value["training_budget"]["accepted_samples_per_run"] = 1024
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["partitions"]["trainer_visible"].append("final-evaluation")
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["statistics"]["best_seed_claims"] = True
        mutations.append(value)
        value = copy.deepcopy(contract)
        value["metrics"].pop()
        mutations.append(value)
        for mutation in mutations:
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(schema).validate(mutation)

    def test_m09_delta_applies_exactly_after_accepted_m06_tree(self) -> None:
        plan = run_m02_map_feasibility.load_strict_json(self.root / "config/v1/m02-map-feasibility-plan.json")
        oracle = validate_m02_scenario_contract.load_strict_json(self.root / "config/v1/m02-reset-oracle.json")
        lock = validate_m09_evaluation_contract.validate_runtime_lock(self.lock_path, self.lock_schema_path)
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
            _, patches, _ = run_m02_map_feasibility.validate_delta_series(self.root, plan["source"])
            prepare_openttd_source.apply_patches(source, patches, run_m02_map_feasibility.SOURCE_TREE)
            self.assertEqual(prepare_openttd_source.git(source, "write-tree"), plan["source"]["result_tree"])
            chain = [
                (oracle["native_delta"]["patches"][0]["path"], plan["source"]["result_tree"], oracle["native_delta"]["result_tree"]),
                ("integration/openttd/patches/15.3/m03/0004-synchronized-environment-bridge.patch", oracle["native_delta"]["result_tree"], run_m04_observation.M03_RESULT_TREE),
                ("integration/openttd/patches/15.3/m04/0005-versioned-policy-observation.patch", run_m04_observation.M03_RESULT_TREE, run_m05_actions.M04_RESULT_TREE),
                ("integration/openttd/patches/15.3/m05/0006-explicit-bus-actions-and-masks.patch", run_m05_actions.M04_RESULT_TREE, run_m06_reward_trajectory.M05_RESULT_TREE),
                ("integration/openttd/patches/15.3/m06/0007-native-reward-termination.patch", run_m06_reward_trajectory.M05_RESULT_TREE, run_m06_reward_trajectory.M06_RESULT_TREE),
                (lock["native_delta"]["patch_path"], run_m06_reward_trajectory.M06_RESULT_TREE, lock["native_delta"]["result_tree"]),
            ]
            for relative, parent_tree, expected_tree in chain:
                prepare_openttd_source.apply_patches(source, [self.root / relative], parent_tree)
                self.assertEqual(prepare_openttd_source.git(source, "write-tree"), expected_tree)
            self.assertEqual(prepare_openttd_source.git(source, "write-tree"), lock["native_delta"]["result_tree"])
            self.assertEqual(
                run_m02_map_feasibility.composed_source_identity(
                    lock["native_delta"]["parent_composed_source_identity_sha256"],
                    lock["native_delta"]["series_sha256"],
                    [{
                        "order": 8,
                        "path": lock["native_delta"]["patch_path"],
                        "sha256": lock["native_delta"]["patch_sha256"],
                    }],
                    lock["native_delta"]["result_tree"],
                ),
                lock["native_delta"]["composed_source_identity_sha256"],
            )

    def test_evaluator_build_is_optimizer_free_and_read_only_by_construction(self) -> None:
        cmake = (self.root / "training/v1/CMakeLists.txt").read_text(encoding="utf-8")
        evaluator = (self.root / "training/v1/src/m09_evaluator_main.cpp").read_text(encoding="utf-8")
        model = (self.root / "training/v1/src/evaluation_model.cpp").read_text(encoding="utf-8")
        self.assertIn("add_library(\n  openttd_rl_inference", cmake)
        self.assertIn("target_link_libraries(m09_evaluator PRIVATE openttd_rl_inference)", cmake)
        self.assertNotIn("openttd_rl_training", cmake.split("add_executable(m09_evaluator", 1)[1].split("if(BUILD_TESTING)", 1)[0])
        self.assertNotIn("multimodal_trainer.h", evaluator)
        self.assertNotIn("torch::optim", evaluator + model)
        self.assertIn("read-only evaluator mutated model state", evaluator)
        self.assertIn("model_->eval()", model)
        self.assertIn("torch::InferenceMode", model)

    def test_training_runner_has_no_final_evaluation_execution_path(self) -> None:
        runner = (self.root / "scripts/v1/run_m09_training.py").read_text(encoding="utf-8")
        self.assertIn("final_evaluation_accessed\": False", runner)
        self.assertIn("Deliberately do not open final_paths", runner)
        self.assertNotIn("reset_evaluation", runner)

    def test_final_runner_is_fail_closed_and_uses_only_development_selection(self) -> None:
        runner = (self.root / "scripts/v1/run_m09_evaluation.py").read_text(encoding="utf-8")
        self.assertIn("accepted final evaluation requires a clean committed repository", runner)
        self.assertIn("development_selection(training)", runner)
        self.assertIn('"final_results_used": False', runner)
        self.assertIn("package_snapshot", runner)
        self.assertIn("in-memory model state changed across episodes", runner)
        self.assertNotIn("torch.optim", runner)

    def test_development_selection_prefers_eligible_policy_without_final_data(self) -> None:
        runs = []
        for architecture in run_m09_evaluation.ARCHITECTURES:
            for seed in (1, 2, 3):
                eligible = architecture == "combined-cnn-mlp-v1" and seed == 2
                runs.append({
                    "architecture": architecture,
                    "run_seed": seed,
                    "package": {"id": f"{architecture}-{seed}", "path": "unused"},
                    "development": {
                        "reliably_profitable": eligible,
                        "mean_operating_profit": 10 if eligible else -seed,
                        "mean_passenger_deliveries": 5 if eligible else 0,
                        "mean_final_balance": 100_000 - seed,
                        "mean_invalid_actions": 0,
                    },
                })
        manifest = {"runs": runs, "selected_on_development": {}}
        for architecture in run_m09_evaluation.ARCHITECTURES:
            seed = 2 if architecture == "combined-cnn-mlp-v1" else 1
            manifest["selected_on_development"][architecture] = {
                "package": {"id": f"{architecture}-{seed}", "path": "unused"},
                "run_seed": seed,
            }
        selected, overall = run_m09_evaluation.development_selection(manifest)
        self.assertEqual(selected["combined-cnn-mlp-v1"]["run_seed"], 2)
        self.assertEqual(overall["architecture"], "combined-cnn-mlp-v1")
        self.assertEqual(overall["run_seed"], 2)

    def test_seed_statistics_report_student_t_interval_over_run_seeds(self) -> None:
        episodes = [
            {"run_seed": seed, "metrics": {"operating_profit": value}}
            for seed, values in ((1, (1, 3)), (2, (2, 4)), (3, (3, 5)))
            for value in values
        ]
        result = run_m09_evaluation.seed_statistics(episodes, "operating_profit")
        self.assertEqual(result["status"], "REPORTED")
        self.assertEqual(result["mean"], 3.0)
        self.assertEqual(result["sample_standard_deviation"], 1.0)
        self.assertEqual([item["value"] for item in result["seed_means"]], [2.0, 3.0, 4.0])


if __name__ == "__main__":
    unittest.main()
