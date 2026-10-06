"""Interrupted benchmarks cannot silently reuse partial or changed episodes."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from audit_action_inputs_v2 import artifact
from run_bus_orders_benchmark_v2 import reuse_case, reuse_source


class BenchmarkResumeTests(unittest.TestCase):
    def fixture(self, root):
        saved = root / "final.sav"
        saved.write_bytes(b"native-save")
        source = root / "initial.sav"
        source.write_bytes(b"initial")
        context = {"save": artifact(source)}
        case = {"case_id": 3, "world_id": 2, "mode": "greedy", "action_seed": 12}
        model = {"path": "frozen-model", "sha256": "frozen-hash"}
        report = {"status": "completed", "case": case, "source_save": context["save"], "model": model,
                  "training_run": False, "decisions_budget": 512, "step_ticks": 128,
                  "summary": {"decisions": 512, "simulation_ticks": 65536, "invalid_actions": 0, "bankruptcy": False},
                  "final_save": artifact(saved), "checkpoints": [], "valid_running_routes": 0}
        path = root / "run.json"
        path.write_text(json.dumps(report))
        return path, case, context, model, report

    def test_completed_case_preserves_original_report_and_save_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            path, case, context, model, _ = self.fixture(Path(temporary))
            before = path.read_bytes()
            item = reuse_case(path, case, context, model, 512, 128)
            self.assertEqual(item["report"], artifact(path))
            self.assertEqual(path.read_bytes(), before)

    def test_partial_budget_cannot_be_counted_as_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            path, case, context, model, report = self.fixture(Path(temporary))
            report["summary"]["decisions"] = 511
            report["summary"]["simulation_ticks"] = 511 * 128
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "incomplete"):
                reuse_case(path, case, context, model, 512, 128)

    def test_other_model_or_changed_save_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path, case, context, model, _ = self.fixture(Path(temporary))
            with self.assertRaisesRegex(ValueError, "case/model/budget"):
                reuse_case(path, case, context, {**model, "sha256": "other"}, 512, 128)
            (Path(temporary) / "final.sav").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "hash differs"):
                reuse_case(path, case, context, model, 512, 128)

    def test_interface_termination_requires_explicit_permission_and_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            path, case, context, model, report = self.fixture(Path(temporary))
            report.update(status="terminated-interface", interface_limit=[{"vehicle_id": 8, "orders": [{"type": 5}]}], saved_game_roundtrip="passed")
            report["summary"].update(decisions=395, simulation_ticks=395 * 128)
            path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "case/model/budget"):
                reuse_case(path, case, context, model, 512, 128)
            item = reuse_case(path, case, context, model, 512, 128, allow_interface_limit=True)
            self.assertEqual(item["outcome"], "terminated-interface")
            self.assertEqual(item["summary"]["decisions"], 395)

    def test_native_engine_identity_is_required_when_reusing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, case, context, model, _ = self.fixture(root)
            engine = root / "openttd"
            engine.write_bytes(b"frozen-engine")
            (root / "worker").mkdir()
            reset = root / "worker/reset.json"
            reset.write_text(json.dumps({"executable_sha256": artifact(engine)["sha256"]}))
            reuse_case(path, case, context, model, 512, 128, engine=artifact(engine))
            reset.write_text(json.dumps({"executable_sha256": "other-engine"}))
            with self.assertRaisesRegex(ValueError, "native engine differs"):
                reuse_case(path, case, context, model, 512, 128, engine=artifact(engine))

    def test_actor_protocol_and_reader_are_bound_before_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            protocol, reader, other = [root / name for name in ("protocol", "reader", "other")]
            for file in (protocol, reader, other):
                file.write_bytes(file.name.encode())
            source = root / "actor.json"
            data = {"actor": "actor", "protocol": artifact(protocol), "policy": artifact(reader), "episodes": []}
            source.write_text(json.dumps(data))
            self.assertEqual(reuse_source(source, artifact(protocol), artifact(reader))[0], data)
            with self.assertRaisesRegex(ValueError, "another frozen protocol"):
                reuse_source(source, artifact(other), artifact(reader))
            with self.assertRaisesRegex(ValueError, "policy reader differs"):
                reuse_source(source, artifact(protocol), artifact(other))


if __name__ == "__main__":
    unittest.main()
