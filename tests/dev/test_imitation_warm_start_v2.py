"""Supervised ancestry must be verified before fresh PPO can consume weights."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from imitation_warm_start_v2 import checked_imitation_run, import_imitation
from train_v2 import run


class ImitationWarmStartTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.weights = self.root / "inference-weights.pt"
        self.weights.write_bytes(b"test archive; native validation is a separate test")
        self.record = {"kind": "native-v2-human-imitation", "status": "completed",
                       "observation_schema_id": "finance-test", "financial_features": "signed-log-v1",
                       "guidance": "none", "model": {"path": str(self.weights),
                           "sha256": hashlib.sha256(self.weights.read_bytes()).hexdigest(),
                           "financial_features": "signed-log-v1"}}
        self.save()

    def save(self):
        (self.root / "run.json").write_text(json.dumps(self.record))

    def test_hash_verified_archive_and_fresh_import(self):
        record, ancestry = checked_imitation_run(self.root, observation_schema="finance-test",
                                                 financial_features="signed-log-v1")
        self.assertEqual(record, self.record)
        trainer = Mock()
        trainer.request.return_value = {"status": "IMPORTED_WEIGHTS", "updates": 0,
                                        "optimizer_reset": True, "recurrent_reset": True}
        import_imitation(trainer, ancestry)
        trainer.request.assert_called_once_with(f"IMPORT_WEIGHTS\t{self.weights}")

    def test_failed_run_wrong_schema_and_preprocessing_are_rejected(self):
        for key, value, error in (("status", "failed", "completed"),
                                  ("observation_schema_id", "legacy", "schema"),
                                  ("financial_features", "raw", "preprocessing")):
            original = self.record[key]
            self.record[key] = value
            self.save()
            with self.assertRaisesRegex(ValueError, error):
                checked_imitation_run(self.root, observation_schema="finance-test",
                                      financial_features="signed-log-v1")
            self.record[key] = original
        self.save()

    def test_changed_archive_rejected_before_native_import(self):
        _, ancestry = checked_imitation_run(self.root)
        self.weights.write_bytes(b"changed")
        trainer = Mock()
        with self.assertRaisesRegex(ValueError, "changed"):
            import_imitation(trainer, ancestry)
        trainer.request.assert_not_called()
        with self.assertRaisesRegex(ValueError, "hash"):
            checked_imitation_run(self.root)

    def test_order_modes_require_explicit_semantics_and_do_not_interchange(self):
        for mode in ("signed-log-orders-v1", "signed-log-orders-v2", "signed-log-orders-v3"):
            self.record.update(financial_features=mode,
                observation_schema_id="v2-m15-public-development-orders-v1", action_semantics="orders-v1")
            self.record["model"].update(financial_features=mode,
                observation_schema_id=self.record["observation_schema_id"], action_semantics="orders-v1")
            self.save()
            checked_imitation_run(self.root, financial_features=mode)
            other = "signed-log-orders-v2" if mode.endswith("v1") else "signed-log-orders-v1"
            with self.assertRaisesRegex(ValueError, "preprocessing differs"):
                checked_imitation_run(self.root, financial_features=other)
            del self.record["model"]["action_semantics"]
            self.save()
            with self.assertRaisesRegex(ValueError, "order observation/action"):
                checked_imitation_run(self.root, financial_features=mode)

    def test_native_must_confirm_fresh_optimizer_and_recurrent_state(self):
        _, ancestry = checked_imitation_run(self.root)
        trainer = Mock()
        trainer.request.return_value = {"status": "IMPORTED_WEIGHTS", "updates": 1,
                                        "optimizer_reset": False, "recurrent_reset": True}
        with self.assertRaisesRegex(ValueError, "fresh"):
            import_imitation(trainer, ancestry)

    def test_resume_and_registered_study_cannot_reinitialize(self):
        for incompatible in ({"resume": self.root}, {"study_registration": self.root},
                             {"training_reset_probes": True}):
            args = SimpleNamespace(episode_horizon=128, guidance="one-bus-public-plan-v5",
                                   imitation_run=self.root, **incompatible)
            with self.assertRaisesRegex(ValueError, "fresh unregistered"):
                run(args)


if __name__ == "__main__":
    unittest.main()
