"""Finance pilots must preserve schema boundaries and financing-neutral rewards."""
import hashlib
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
import checkpoint_v2
from evaluate_guide_v2 import select_row
from guide_v2 import FINANCE_GUIDANCE
from infer_v2 import checked_tensors, TENSOR_SCHEMA
from live_v2 import LiveV2, OBSERVATION_SCHEMAS
from train_v2 import reward_components, run
from finance_observation_v2 import expected_features, field_descriptions, MAXIMUM_LOAN_ENCODING
from orders_observation_v2 import description as order_description


class FinanceWiringTests(unittest.TestCase):
    def tensor_pair(self, root, mode):
        observation = {"token": "snapshot", "company_id": 0, "candidates": []}
        response = {"status": "OK", "tensors": {"schema_version": TENSOR_SCHEMA,
                    "token": "snapshot", "company_id": 0}}
        obs_data = bytearray(2182927)
        finance = {"maximum_loan": 300000, "borrowing_headroom": 200000, "interest_rate_percent": 2,
                   "quarter_income": 0, "quarter_expenses": 0, "quarter_operating_profit": 0, "year_interest_paid": 0}
        if mode in ("finance-v1", "orders-v1"):
            observation["economy"] = {"loan": 100000, "finance": finance}
            struct.pack_into("<7f", obs_data, 16 * 4, *expected_features(finance))
            struct.pack_into("<f", obs_data, 1181696 + 4 * 4, 300000 / 1e9)
        if mode == "orders-v1":
            observation["vehicles"] = []
            observation.update(action_semantics="orders-v1", action_schema_id="v2-m15-bus-orders-action-v1")
            struct.pack_into("<f", obs_data, 511 * 4, 1.0)
        obs_hash = hashlib.sha256(obs_data).hexdigest()
        for name, size in (("observation", 2182927), ("candidates", 790528)):
            binary = root / (name + ".bin")
            binary.write_bytes(obs_data if name == "observation" else bytes(size))
            meta = {"binary": {"file": binary.name, "bytes": size,
                    "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()},
                    "snapshot": {"map_seed": 0, "simulation_seed": 0, "candidate_tiebreak_seed": 0}}
            if name == "observation":
                meta.update(schema_version="openttd-rl-development-v2-observation-metadata-1",
                            observation_schema_id=OBSERVATION_SCHEMAS[mode], observing_company=0,
                            vehicle_order="own-company-first-then-public-vehicle-id")
                if mode in ("finance-v1", "orders-v1"):
                    meta["finance_observation"] = {"mode": "finance-v1", "values": finance,
                        "structured": field_descriptions(), "company_maximum_loan": MAXIMUM_LOAN_ENCODING,
                        "quarter_expenses_sign": "native-negative-expense"}
                if mode == "orders-v1":
                    meta.update(action_semantics="orders-v1", order_observation=order_description())
            else:
                meta.update(observation_sha256=obs_hash, records=[])
                if mode == "orders-v1":
                    meta.update(action_semantics="orders-v1", action_schema_id="v2-m15-bus-orders-action-v1")
            path = root / (name + ".json")
            path.write_text(json.dumps(meta))
            response["tensors"][name] = str(path)
        return response, observation

    def test_finance_and_legacy_tensor_schemas_cannot_be_interchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            for mode in OBSERVATION_SCHEMAS:
                response, observation = self.tensor_pair(Path(directory), mode)
                checked_tensors(response, observation, observation_mode=mode)
                other = "legacy" if mode == "finance-v1" else "finance-v1"
                with self.assertRaisesRegex(ValueError, "observation schema"):
                    checked_tensors(response, observation, observation_mode=other)

    def test_finance_label_without_financial_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            response, observation = self.tensor_pair(Path(directory), "finance-v1")
            path = Path(response["tensors"]["observation"])
            meta = json.loads(path.read_text())
            del meta["finance_observation"]
            path.write_text(json.dumps(meta))
            with self.assertRaises((ValueError, KeyError)):
                checked_tensors(response, observation, observation_mode="finance-v1")

    def test_unknown_mode_fails_before_native_io(self):
        with patch.object(Path, "mkdir", side_effect=AssertionError("unexpected filesystem mutation")):
            with self.assertRaisesRegex(ValueError, "observation mode"):
                LiveV2("missing", "missing", observation_mode="finance-v2")

    def test_finance_pilot_cannot_enter_registered_study_or_frozen_probes(self):
        for options in ({"study_registration": Path("missing")}, {"training_reset_probes": True}):
            with self.assertRaisesRegex(ValueError, "separate pilot"):
                run(SimpleNamespace(finance_observations=True, **options))

    def test_checkpoint_schema_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = b"native checkpoint fixture"
            (root / "trainer.pt").write_bytes(payload)
            config = {"episode_horizon": 128, "rollout_steps": 128,
                      "observation_schema_id": OBSERVATION_SCHEMAS["legacy"]}
            expected = {"configuration": config}
            manifest = {"format": "openttd-rl-development-v2-reset-checkpoint-1",
                        "compatibility": expected, "update": 1, "transitions": 128,
                        "next_episode": 1, "trainer_sha256": hashlib.sha256(payload).hexdigest()}
            (root / "checkpoint.json").write_text(json.dumps(manifest))
            checkpoint_v2.read(root, expected)
            finance = {"configuration": {**config, "observation_schema_id": OBSERVATION_SCHEMAS["finance-v1"]}}
            with self.assertRaisesRegex(ValueError, "configuration"):
                checkpoint_v2.read(root, finance)

    def test_borrow_repay_principal_never_creates_earned_reward(self):
        before = {"balance": 50000, "loan": 100000, "operating_profit": 0, "delivered_passengers": 0}
        reference = None
        for delta in (0, 10000, -10000):
            after = {**before, "balance": before["balance"] + delta, "loan": before["loan"] + delta}
            row = {"before": before, "after": after, "terminal": False,
                   "action": {"family": "MANAGE_LOAN", "native_commands": []}}
            reward = reward_components(row)
            if reference is None:
                reference = reward
            self.assertEqual(reward, reference)
            self.assertEqual(reward["raw_operating_profit"], 0)
            self.assertEqual((after["balance"] - before["balance"]) - (after["loan"] - before["loan"]), 0)
        row["after"]["operating_profit"] = -20
        self.assertLess(reward_components(row)["reward"], reference["reward"])

    def test_v5_repay_control_does_not_accidentally_pick_borrow(self):
        guide = SimpleNamespace(guidance=FINANCE_GUIDANCE, proposal="invest", families=["BUILD_BUS_STOP", "MANAGE_LOAN"])
        candidates = {0: {"family_index": 1, "parameters": [11, 1, 10000], "stable_key": "borrow"},
                      1: {"family_index": 1, "parameters": [11, 2, 10000], "stable_key": "repay"},
                      2: {"family_index": 0, "parameters": [0], "stable_key": "invest"}}
        self.assertEqual(select_row("repay-first", "sampled", [0, 1, 2], candidates, guide, random.Random(0))[0], 1)
        self.assertEqual(select_row("repay-first", "sampled", [0, 2], candidates, guide, random.Random(0))[0], 2)


if __name__ == "__main__":
    unittest.main()
