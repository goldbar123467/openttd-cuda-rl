"""Recomputed benchmark finance rejects broken native evidence chains."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from audit_action_inputs_v2 import artifact
from service_v2 import summarize
from summarize_bus_benchmark_v2 import MODE, clustered_difference, verify_episode, verify_offline_models


class BenchmarkSummaryTests(unittest.TestCase):
    def fixture(self, root):
        (root / "worker").mkdir()
        engine = root / "engine"
        engine.write_bytes(b"frozen-engine")
        (root / "worker/reset.json").write_text(json.dumps({"executable_sha256": artifact(engine)["sha256"]}))
        economy = {"alive": True, "balance": 100, "loan": 100, "delivered_passengers": 0,
                   "operating_profit": 0, "income": 0, "expenses": 0}
        initial = {"tick": 0, "token": "before", "economy": economy, "vehicles": [],
                   "stations": [], "depots": [], "company_id": 0, "terminal": False, "map": {"roads": []}}
        final = {**initial, "tick": 128, "token": "after", "economy": {**economy, "balance": 90, "loan": 90}}
        candidate = {"key": "repay", "family": "MANAGE_LOAN"}
        transition = {"decision": 1, "tick_before": 0, "tick_after": 128, "state_before": "before", "state_after": "after",
                      "before": economy, "after": final["economy"], "company_id": 0,
                      "action": {"candidate": "repay", "family": "MANAGE_LOAN", "status": "SUCCESS", "native_commands": []}}
        for name, value in (("initial", initial), ("final", final)):
            (root / (name + ".json")).write_text(json.dumps(value))
        saved = root / "initial.sav"
        saved.write_bytes(b"initial-save")
        final_save = root / "final.sav"
        final_save.write_bytes(b"final-save")
        (root / "worker/transitions.jsonl").write_text(json.dumps(transition) + "\n")
        (root / "decisions.jsonl").write_text(json.dumps({"decision": 1, "tick": 0, "candidate": candidate}) + "\n")
        context = {"save": artifact(saved), "initial": artifact(root / "initial.json")}
        case = {"case_id": 3}
        summary = summarize([transition], initial, final)
        report = {"status": "completed", "case": case, "source_save": context["save"], "training_run": False,
                  "decisions_budget": 1, "step_ticks": 128, "summary": summary, "checkpoints": [],
                  "final_save": artifact(final_save), "valid_running_routes": 0}
        path = root / "run.json"
        path.write_text(json.dumps(report))
        item = {"case": case, "report": artifact(path), "summary": summary,
                "final_save": report["final_save"], "valid_running_routes": 0}
        return item, context, {"decisions": 1, "step_ticks": 128, "engine": artifact(engine)}, transition

    def test_repayment_principal_is_not_operating_loss(self):
        with tempfile.TemporaryDirectory() as temporary:
            item, context, protocol, _ = self.fixture(Path(temporary))
            self.assertEqual(item["summary"]["cash_result_excluding_financing"], 0)
            self.assertEqual(item["summary"]["operating_profit"], 0)
            self.assertEqual(verify_episode(item, context, None, protocol)["verified_decisions"], 1)

    def test_changed_transition_accounting_cannot_retain_reported_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            item, context, protocol, transition = self.fixture(root)
            transition["after"]["loan"] = 80
            (root / "worker/transitions.jsonl").write_text(json.dumps(transition) + "\n")
            with self.assertRaisesRegex(ValueError, "Final state"):
                verify_episode(item, context, None, protocol)

    def test_bootstrap_resamples_seeds_instead_of_individual_episodes(self):
        rows = [{"map_seed": 1, "profit": 1}] * 6 + [{"map_seed": 2, "profit": 5}] * 2
        result = clustered_difference(rows, "profit", repeats=1000)
        self.assertEqual(result["independent_map_seed_clusters"], 2)
        self.assertEqual(result["paired_cases"], 8)
        self.assertEqual(result["paired_mean_difference"], 2)
        self.assertEqual(result["cluster_bootstrap_95_percent_interval"], [1, 5])

    def test_offline_model_and_reader_must_match_live_actors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = {name: root / name for name in ("run.json", "model", "reader", "other-model")}
            for name, path in files.items():
                path.write_bytes(name.encode())
            model, run, reader = [artifact(files[name]) for name in ("model", "run.json", "reader")]
            protocol = {"frozen_actors": {"actor": {"run": str(root), "run_sha256": run["sha256"], "model": model}}}
            offline = {"financial_features": MODE, "policy": reader, "models": {"actor": {"model": model, "run": run}},
                       "results": [{"model": "actor"}]}
            verify_offline_models(offline, protocol, reader)
            offline["models"]["actor"]["model"] = artifact(files["other-model"])
            with self.assertRaisesRegex(ValueError, "Offline model/run differs"):
                verify_offline_models(offline, protocol, reader)
            offline["models"]["actor"]["model"] = model
            offline["policy"] = artifact(files["other-model"])
            with self.assertRaisesRegex(ValueError, "Offline policy reader differs"):
                verify_offline_models(offline, protocol, reader)


if __name__ == "__main__":
    unittest.main()
