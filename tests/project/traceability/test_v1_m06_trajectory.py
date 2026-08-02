#!/usr/bin/env python3
"""Exact round-trip, bounds, float guards, and corruption tests for M06 trajectories."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import tempfile
import unittest

import m06_reward_reference
import m06_trajectory
import validate_m06_reward_contract


class V1M06TrajectoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract = validate_m06_reward_contract.validate(
            cls.root / "config/v1/m06-reward-trajectory-contract.json",
            cls.root / "docs/project/schema/v1-m06-reward-trajectory-contract.schema.json",
        )

    def test_exact_m04_blob_encoding_has_frozen_shape_order_and_identity(self) -> None:
        observation = self._observation(0.0)
        digest, blob = m06_trajectory.observation_sha256(observation)
        self.assertEqual(len(blob), 132_096)
        self.assertEqual(digest, "8675651898d77ef1cbe478e28b4ef7e367fabcdd4e667f536d1a1a0ab6b7c2f2")
        self.assertEqual(blob, bytes(132_096))

    def test_bundle_round_trip_preserves_exact_records_and_deduplicates_boundary_blob(self) -> None:
        observations = [self._observation(value) for value in (0.0, 0.25, 0.5)]
        builder = m06_trajectory.TrajectoryBundle({"campaign": "unit", "run_seed": 7})
        first = builder.add(self._record(1, pre_tick=0), observations[0], observations[1])
        second = builder.add(self._record(2, pre_tick=128), observations[1], observations[2])
        self.assertEqual(first["next_observation_sha256"], second["observation_sha256"])
        self.assertEqual(len(builder.blobs), 3)
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "trajectory"
            manifest = builder.write(path)
            loaded = m06_trajectory.load_bundle(path)
            self.assertEqual(loaded, manifest)
            self.assertEqual(loaded["records"], [first, second])
            self.assertEqual(loaded["record_count"], 2)
            with self.assertRaises(FileExistsError):
                builder.write(path)
            blocked_parent = pathlib.Path(raw) / "not-a-directory"
            blocked_parent.write_bytes(b"fixture")
            with self.assertRaises(OSError):
                builder.write(blocked_parent / "trajectory")

    def test_validated_bundle_resumes_into_a_new_immutable_generation(self) -> None:
        observations = [self._observation(value) for value in (0.0, 0.25, 0.5)]
        builder = m06_trajectory.TrajectoryBundle({"campaign": "resume", "run_seed": 11})
        first = builder.add(self._record(1, pre_tick=0), observations[0], observations[1])
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            first_path = root / "generation-1"
            second_path = root / "generation-2"
            builder.write(first_path)
            resumed = m06_trajectory.TrajectoryBundle.resume(first_path)
            second = resumed.add(self._record(2, pre_tick=128), observations[1], observations[2])
            resumed.write(second_path)
            loaded = m06_trajectory.load_bundle(second_path)
            self.assertEqual(loaded["records"], [first, second])
            self.assertTrue(first_path.is_dir())
            self.assertEqual(m06_trajectory.load_bundle(first_path)["record_count"], 1)

    def test_blob_and_metadata_corruption_are_rejected_before_rollout(self) -> None:
        builder = m06_trajectory.TrajectoryBundle({"campaign": "corruption"})
        builder.add(self._record(1, pre_tick=0), self._observation(0.0), self._observation(0.25))
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            blob_bundle = root / "blob-corrupt"
            builder.write(blob_bundle)
            manifest = m06_trajectory.load_bundle(blob_bundle)
            digest = next(iter(manifest["observation_blobs"]))
            blob_path = blob_bundle / "blobs" / f"{digest}.bin"
            changed = bytearray(blob_path.read_bytes())
            changed[0] ^= 1
            blob_path.write_bytes(changed)
            with self.assertRaisesRegex(m06_trajectory.M06TrajectoryError, "blob length or SHA-256"):
                m06_trajectory.load_bundle(blob_bundle)

            metadata_bundle = root / "metadata-corrupt"
            builder.write(metadata_bundle)
            manifest_path = metadata_bundle / "manifest.json"
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
            value["records"][0]["reward"]["scalar"] = 99.0
            manifest_path.write_bytes(validate_m06_reward_contract.canonical_bytes(value) + b"\n")
            with self.assertRaisesRegex(m06_trajectory.M06TrajectoryError, "bundle integrity"):
                m06_trajectory.load_bundle(metadata_bundle)

    def test_nonfinite_float_bit_drift_discontinuous_boundary_and_segment_overflow_fail_closed(self) -> None:
        invalid = self._record(1, pre_tick=0)
        invalid["action"]["value"] = float("nan")
        with self.assertRaises((m06_trajectory.M06TrajectoryError, ValueError)):
            m06_trajectory.seal_record(invalid | {"observation_sha256": "0" * 64, "next_observation_sha256": "1" * 64})

        observation = self._observation(0.0)
        other = self._observation(0.25)
        third = self._observation(0.5)
        builder = m06_trajectory.TrajectoryBundle({"campaign": "bounds"})
        builder.add(self._record(1, pre_tick=0), observation, other)
        with self.assertRaisesRegex(m06_trajectory.M06TrajectoryError, "discontinuous"):
            builder.add(self._record(2, pre_tick=128), observation, third)

        bounded = m06_trajectory.TrajectoryBundle({"campaign": "segment-bound"})
        for ordinal in range(1, 129):
            bounded.add(self._record(ordinal, pre_tick=(ordinal - 1) * 128), observation, observation)
        with self.assertRaisesRegex(m06_trajectory.M06TrajectoryError, "128-transition"):
            bounded.add(self._record(129, pre_tick=128 * 128), observation, observation)

    def test_terminal_and_truncated_bootstrap_values_are_typed(self) -> None:
        terminal = self._record(1, pre_tick=0)
        terminal["termination"] = {
            "bootstrap": False,
            "kind": "TERMINAL",
            "reason": "BANKRUPTCY",
            "schema_version": "openttd-rl-v1-m06-termination-1",
            "terminal": True,
            "trainable": True,
            "truncated": False,
        }
        terminal["next_value"] = None
        sealed = m06_trajectory.seal_record(terminal | {"observation_sha256": "0" * 64, "next_observation_sha256": "1" * 64})
        self.assertFalse(sealed["termination"]["bootstrap"])
        broken = copy.deepcopy(terminal)
        broken["next_value"] = {"float64_bits": m06_reward_reference.float64_bits(0.0), "value": 0.0}
        with self.assertRaisesRegex(m06_trajectory.M06TrajectoryError, "null next_value"):
            m06_trajectory.seal_record(broken | {"observation_sha256": "0" * 64, "next_observation_sha256": "1" * 64})

    @staticmethod
    def _observation(value: float) -> dict[str, object]:
        return {
            "compatibility_sha256": m06_trajectory.OBSERVATION_COMPATIBILITY_SHA256,
            "schema_version": "openttd-rl-v1-m04-observation-1",
            "spatial": {
                "data": [value] * 32_768,
                "dtype": "float32",
                "logical_order": "channel-y-x",
                "shape": [32, 32, 32],
            },
            "structured": {
                "data": [value] * 256,
                "dtype": "float32",
                "logical_order": "feature",
                "shape": [256],
            },
        }

    def _record(self, ordinal: int, *, pre_tick: int) -> dict[str, object]:
        raw = {
            "delivered_passengers_delta": 0,
            "operating_profit_delta": 0,
            "capital_spend": 0,
            "noop": 1,
            "native_rejected": 0,
            "idle_bus_ticks": 0,
            "vehicle_loss_count": 0,
            "bankruptcy": 0,
        }
        result = m06_reward_reference.compute_reward(raw, self.contract)
        components = []
        for item, raw_value, clamped, weighted in zip(self.contract["reward"]["components"], result.raw, result.clamped, result.weighted):
            components.append(
                {
                    "clamped": clamped,
                    "component_id": item["component_id"],
                    "name": item["name"],
                    "order": item["order"],
                    "raw": raw_value,
                    "raw_field": item["raw_field"],
                    "weighted": weighted,
                    "weighted_float64_bits": m06_reward_reference.float64_bits(weighted),
                }
            )
        return {
            "action": {
                "index": 0,
                "log_probability": 0.0,
                "log_probability_float64_bits": m06_reward_reference.float64_bits(0.0),
                "outcome": {"status": "NO_OP"},
                "parameters": {},
                "selection_mode": "SCRIPTED",
                "value": 0.0,
                "value_float64_bits": m06_reward_reference.float64_bits(0.0),
            },
            "action_mask": {"dtype": "uint8", "legal": [1] * 41, "mask_token": f"mask-{ordinal}"},
            "boundary": {
                "advanced_ticks": 128,
                "post_tick": pre_tick + 128,
                "post_token": f"post-{ordinal}",
                "pre_tick": pre_tick,
                "pre_token": f"pre-{ordinal}",
            },
            "identities": {
                "action": m06_trajectory.ACTION_COMPATIBILITY_SHA256,
                "bridge": m06_trajectory.BRIDGE_COMPATIBILITY_SHA256,
                "model_checkpoint": None,
                "observation": m06_trajectory.OBSERVATION_COMPATIBILITY_SHA256,
                "reward": m06_trajectory.REWARD_COMPATIBILITY_SHA256,
            },
            "ids": {
                "environment_id": 0,
                "episode_id": 1,
                "request_id": ordinal + 2,
                "run_id": "unit-run",
                "transition_ordinal": ordinal,
                "worker_id": 0,
            },
            "next_value": {"float64_bits": m06_reward_reference.float64_bits(0.0), "value": 0.0},
            "reward": {
                "compatibility_sha256": m06_trajectory.REWARD_COMPATIBILITY_SHA256,
                "components": components,
                "raw": raw,
                "scalar": result.scalar,
                "scalar_float64_bits": m06_reward_reference.float64_bits(result.scalar),
                "schema_version": "openttd-rl-v1-m06-reward-1",
                "source": {
                    "post": {"company_present": True},
                    "pre": {"company_present": True},
                },
            },
            "scenario": {
                "seed_ledger_sha256": hashlib.sha256(b"seed-ledger").hexdigest(),
                "template_id": "unit-template",
                "template_sha256": hashlib.sha256(b"template").hexdigest(),
            },
            "schema_version": m06_trajectory.TRAJECTORY_SCHEMA_VERSION,
            "termination": {
                "bootstrap": True,
                "kind": "CONTINUE",
                "reason": "NONE",
                "schema_version": "openttd-rl-v1-m06-termination-1",
                "terminal": False,
                "trainable": True,
                "truncated": False,
            },
        }


if __name__ == "__main__":
    unittest.main()
