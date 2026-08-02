#!/usr/bin/env python3
"""Frozen-contract, independent-reference, native-source, and evidence guards for M07."""

from __future__ import annotations

import json
import os
import pathlib
import unittest

import m07_ppo_reference
import run_m07_cpu_ppo
import validate_m07_metrics
import validate_m07_ppo_contract


class V1M07PpoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract = validate_m07_ppo_contract.validate(
            cls.root / "config/v1/m07-ppo-contract.json",
            cls.root / "docs/project/schema/v1-m07-ppo-contract.schema.json",
        )

    def test_contract_pins_cpp_libtorch_cpu_and_frozen_environment_shapes(self) -> None:
        self.assertEqual(self.contract["backend"]["language"], "C++")
        self.assertEqual(self.contract["backend"]["version"], "2.13.0+cu130")
        self.assertEqual(self.contract["backend"]["device"], "cpu")
        self.assertEqual(self.contract["architecture"]["input"]["shape"], [256])
        self.assertEqual(self.contract["architecture"]["policy_head"]["shape"], [41])
        self.assertEqual(self.contract["architecture"]["id"], "structured-mlp-v1")
        self.assertEqual(
            self.contract["verification"]["scenario_partitioning"]["forbidden_splits"],
            ["final-evaluation"],
        )

    def test_independent_scalar_oracle_matches_frozen_native_vectors(self) -> None:
        fixture = json.loads(
            (self.root / "tests/fixtures/v1/m07-ppo-reference-vectors.json").read_text(encoding="utf-8")
        )
        m07_ppo_reference.compare(fixture, m07_ppo_reference.reference_vectors())
        executable = os.environ.get("M07_TRAINER_EXECUTABLE")
        if executable:
            m07_ppo_reference.compare(
                m07_ppo_reference.run_native(pathlib.Path(executable)),
                m07_ppo_reference.reference_vectors(),
            )

    def test_native_sources_own_complete_ppo_surface_and_no_second_algorithm(self) -> None:
        directory = self.root / "training/v1"
        text = "\n".join(path.read_text(encoding="utf-8") for path in sorted(directory.rglob("*.cpp")))
        headers = "\n".join(path.read_text(encoding="utf-8") for path in sorted(directory.rglob("*.h")))
        for token in (
            "compute_gae", "normalize_advantages", "masked_categorical", "ppo_loss",
            "clip_grad_norm_", "minibatch_indices", "torch::optim::Adam", "PpoTrainer::update",
            "run_trainer_service", "run_tiny_masked_bandit",
        ):
            self.assertIn(token, text + headers)
        lowered = (text + headers).lower()
        for forbidden in ("deep_q", "dqn", "soft_actor_critic", "sac_trainer", "a2c_trainer"):
            self.assertNotIn(forbidden, lowered)

    def test_checkpoint_is_atomic_semantic_and_fail_closed(self) -> None:
        text = (self.root / "training/v1/src/checkpoint.cpp").read_text(encoding="utf-8")
        for token in (
            "optimizer_semantic_sha256", "sha256_file", "fsync", "std::filesystem::rename",
            "never overwriting", "checkpoint compatibility identity mismatch",
            "checkpoint tensor payload digest mismatch", "checkpoint optimizer semantic state mismatch",
            "development_evaluation_json",
        ):
            self.assertIn(token, text)
        self.assertIn("after-completed-ppo-update-before-next-rollout", self.contract["checkpoint"]["boundary"])

    def test_metric_sources_are_complete_and_native_fixture_is_schema_valid_when_available(self) -> None:
        executable = os.environ.get("M07_TRAINER_EXECUTABLE")
        event = validate_m07_metrics.validate(
            self.root / "docs/project/schema/v1-m07-metric-event.schema.json",
            self.root / "config/v1/m07-metric-sources.json",
            pathlib.Path(executable) if executable else None,
        )
        if executable:
            self.assertIsNotNone(event)

    def test_service_protocol_is_bounded_typed_and_error_recoverable(self) -> None:
        source = "\n".join(
            (self.root / relative).read_text(encoding="utf-8")
            for relative in ("training/v1/src/service.cpp", "training/v1/src/ppo.cpp")
        )
        client = (self.root / "scripts/v1/m07_trainer_client.py").read_text(encoding="utf-8")
        for token in ("kMaximumFrameBytes", "all-illegal action mask", "read_observations", "read_masks", "handle_update"):
            self.assertIn(token, source)
        self.assertIn("MAXIMUM_FRAME_BYTES", client)
        self.assertIn('struct.pack("<8sIQ"', client)

    def test_live_selection_uses_development_only_and_requires_complete_service(self) -> None:
        random_baseline = {
            "episodes": [{}, {}],
            "mean_delivered_passengers": 10.0,
            "mean_return": 2.0,
            "service_successes": 2,
        }
        policy = {
            "episodes": [{}, {}],
            "mean_delivered_passengers": 11.0,
            "mean_return": 2.1,
            "service_successes": 2,
        }
        self.assertTrue(run_m07_cpu_ppo.development_eligible(policy, random_baseline))
        policy["service_successes"] = 1
        self.assertFalse(run_m07_cpu_ppo.development_eligible(policy, random_baseline))
        source = (self.root / "scripts/v1/run_m07_cpu_ppo.py").read_text(encoding="utf-8")
        self.assertIn('final_evaluation_accessed": False', source)
        self.assertIn('entry["trainer_visible"]', source)


if __name__ == "__main__":
    unittest.main()
