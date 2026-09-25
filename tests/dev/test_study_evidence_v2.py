import copy
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from evaluate_guide_v2 import select_row
from infer_v2 import argument_parser
from studies.evidence_v2 import Inputs, load_episode, verify_registered_episode, verify_trace


def native_fixture():
    economy = {"alive": True, "balance": 100000, "loan": 100000, "income": 0,
               "expenses": 0, "operating_profit": 0, "delivered_passengers": 0}
    request = {"split": "development", "map_seed": 155097162, "width": 64, "height": 64,
               "simulation_seed": 2, "candidate_tiebreak_seed": 3, "executable_sha256": "a" * 64,
               "town_target": 2, "industry_target": 256, "resource_tier": "curriculum"}
    reset = {**request, "map_width": 64, "map_height": 64, "company_count": 1, "contract_sha256": "b" * 64}
    reset.pop("width"); reset.pop("height")
    projection = {"request": request, "contract_sha256": "b" * 64,
                  "state": {"date": {"tick": 1280}, "company": {"money": 100000, "loan": 100000}}}
    live = {"schema_version": "openttd-rl-development-v2-live-1", "company_id": 0, "maximum_decisions": 512, "step_ticks": 128}
    rows = [{"company_id": 0, "decision": i+1, "tick_before": 1280+i*128, "tick_after": 1280+(i+1)*128,
             "before": dict(economy), "after": dict(economy), "state_before": str(i), "state_after": str(i+1),
             "terminal": False, "truncated": i == 511,
             "action": {"status": "NO_OP", "family": "WAIT", "native_commands": []}} for i in range(512)]
    final = {"company_id": 0, "pending_step": False, "decisions": 512, "maximum_decisions": 512,
             "step_ticks": 128, "tick": 66816, "token": "512", "economy": dict(economy),
             "terminal": False, "truncated": True, "vehicles": [], "stations": []}
    return rows, final, reset, projection, live


class EvidenceTests(unittest.TestCase):
    def test_full_boundary_and_early_terminal_but_not_short_truncation(self):
        data = native_fixture()
        self.assertEqual(verify_trace(*data)["decisions"], 512)
        rows, final, reset, projection, live = copy.deepcopy(data)
        rows = rows[:2]
        rows[-1]["terminal"] = True
        final.update(decisions=2, tick=1536, token="2", terminal=True, truncated=False)
        summary = verify_trace(rows, final, reset, projection, live)
        self.assertTrue(summary["bankruptcy"])
        self.assertFalse(summary["service_in_all_final_three_windows"])
        rows[-1].update(terminal=False, truncated=True)
        final.update(terminal=False, truncated=True)
        with self.assertRaises(ValueError):
            verify_trace(rows, final, reset, projection, live)

    def test_corrupted_native_provenance_chain_and_boundary_fail(self):
        for kind in ("reset", "budget", "clock", "state", "economy", "terminal", "final", "nonfinite"):
            data = native_fixture()
            rows, final, reset, projection, live = data
            if kind == "reset": projection["request"]["map_seed"] += 1
            if kind == "budget": live["maximum_decisions"] = 128
            if kind == "clock": rows[20]["tick_before"] += 1
            if kind == "state": rows[20]["state_before"] = "corrupt"
            if kind == "economy": rows[20]["before"]["balance"] += 1
            if kind == "terminal": rows[20]["terminal"] = True
            if kind == "final": final["economy"]["balance"] += 1
            if kind == "nonfinite": rows[20]["after"]["income"] = float("nan")
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                verify_trace(*data)

    def test_compressed_evidence_hashes_summary_and_registered_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "worker").mkdir()
            rows, final, reset, projection, live = native_fixture()
            record = {"status": "completed", "split": "development", "map_seed": reset["map_seed"],
                      "final_evaluation_accessed": False, "decisions": 512, "mode": "sampled", "sampling_seed": 7,
                      "guidance": "one-bus-public-plan-v2", "controller": "uniform", "engine_sha256": "a" * 64,
                      "source": {"fixture": 1}, "final_observation": final, "summary": verify_trace(rows, final, reset, projection, live)}
            def write_record(): (root / "run.json").write_text(json.dumps(record))
            write_record()
            for name, value in (("reset", reset), ("reset-projection", projection), ("live", live)):
                (root / f"worker/{name}.json").write_text(json.dumps(value))
            compressed = root / "worker/transitions.jsonl.gz"
            compressed.write_bytes(gzip.compress(b"\n".join(json.dumps(r).encode() for r in rows)))
            inputs = Inputs()
            entry = load_episode(root, inputs)
            self.assertEqual(inputs.sha256[str(compressed)], hashlib.sha256(compressed.read_bytes()).hexdigest())
            inputs.unchanged()
            case = {k: entry[k] for k in ("split", "map_seed", "mode", "sampling_seed")}
            registration = {"binaries": {"engine": {"sha256": "a" * 64}}, "training": {"guide": record["guidance"]}, "source": record["source"]}
            verify_registered_episode(entry, case, registration)
            with self.assertRaises(ValueError):
                verify_registered_episode(entry, {**case, "mode": "greedy"}, registration)
            record["summary"]["operating_profit"] = 999
            write_record()
            with self.assertRaises(ValueError): inputs.unchanged()
            with self.assertRaisesRegex(ValueError, "Stored summary"):
                load_episode(root, Inputs())
            record.pop("summary"); record.pop("mode"); write_record()
            with self.assertRaisesRegex(ValueError, "mode must be explicit"):
                load_episode(root, Inputs())
            legacy = load_episode(root, Inputs(), legacy_sampled_control=True)
            self.assertTrue(legacy["legacy_assumed_sampled_mode"])
            with self.assertRaises((ValueError, KeyError)):
                verify_registered_episode(legacy, case, registration)

    def test_control_sampling_preserved_and_greedy_tie_does_not_consume_rng(self):
        rng, reference = random.Random(42), random.Random(42)
        rows = [0, 3, 8]
        for _ in range(40):
            row, p = select_row("uniform", "sampled", rows, None, None, rng)
            self.assertEqual(row, reference.choice(rows))
            self.assertEqual(p, 1/3)
        before = rng.getstate()
        self.assertEqual(select_row("uniform", "greedy", rows[::-1], None, None, rng), (0, 1/3))
        self.assertEqual(before, rng.getstate())
        guide = SimpleNamespace(proposal="build", families=["WAIT", "BUILD_ROAD_PATH", "MANAGE_LOAN"])
        candidates = {i: {"stable_key": name, "family_index": j} for j, (i, name) in enumerate(zip(rows, ("wait", "build", "repay")))}
        for mode in ("greedy", "sampled"):
            self.assertEqual(select_row("scripted", mode, rows, candidates, guide, rng), (3, 1))
            self.assertEqual(select_row("repay-first", mode, rows, candidates, guide, rng), (8, 1))
        self.assertEqual(before, rng.getstate())

    def test_default_neural_cli_uses_development_and_forbids_held_out(self):
        parser = argument_parser()
        base = ["--openttd", "engine", "--policy", "policy", "--output", "output", "--device", "cpu"]
        self.assertEqual(parser.parse_args(base).split, "development")
        self.assertEqual(parser.parse_args(base + ["--split", "training"]).split, "training")
        with self.assertRaises(SystemExit):
            parser.parse_args(base + ["--split", "generalization"])


if __name__ == "__main__":
    unittest.main()
