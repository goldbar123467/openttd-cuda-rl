import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
import evaluate_guide_v2
import infer_v2
from studies.execution_v2 import artifact, digest
from studies.heldout_v2 import _Permit, jobs, open_registration
from studies import heldout_v2
from studies.evidence_v2 import Inputs
from studies.recovery_v2 import case_name
from local import write_json
from studies.protocol_v2 import PROTOCOL_SHA256, load_protocol


class HeldoutTests(unittest.TestCase):
    def test_ordinary_launchers_refuse_before_policy_or_game_processes(self):
        for function in (infer_v2.run, evaluate_guide_v2.run):
            with patch("infer_v2.PolicyClient") as policy, patch("live_v2.subprocess.Popen") as process:
                with self.assertRaisesRegex(ValueError, "forbids|forbid"):
                    function(SimpleNamespace(split="generalization"))
                policy.assert_not_called()
                process.assert_not_called()

    def test_reserved_matrix_has_all_models_controls_and_only_generalization(self):
        p = load_protocol()
        rows = jobs([{"training_seed": s, "training_run": f"/training/{s}"} for s in p["training_seeds"]], p)
        self.assertEqual(len(rows), 160)
        self.assertEqual({r["split"] for r in rows}, {"generalization"})
        self.assertEqual({r["map_seed"] for r in rows}, set(p["held_out"]["maps"]))
        self.assertFalse({r["map_seed"] for r in rows} & set(p["development"]["maps"]))

    def test_registration_without_eligibility_or_changed_digest_refuses_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = root / "registration.json"
            frozen = {"format": "openttd-rl-v2-heldout-registration-1", "protocol_sha256": PROTOCOL_SHA256,
                      "split": "generalization", "accesses_per_case": 1, "tuning_from_results": False,
                      "final_split_access": False, "access_directory": str(root / "access"), "development_results": []}
            p.write_text(json.dumps(frozen))
            p.with_suffix(".sha256").write_text(digest(p))
            with patch("studies.heldout_v2.selected_evidence", return_value=(None, load_protocol())), patch("studies.heldout_v2.LiveV2") as game:
                with self.assertRaisesRegex(ValueError, "No eligible"):
                    open_registration(p)
                p.write_text(json.dumps({**frozen, "split": "final-evaluation"}))
                with self.assertRaisesRegex(ValueError, "changed"):
                    open_registration(p)
                game.assert_not_called()

    def test_interrupted_reserved_case_is_failed_without_another_game(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regpath = root / "registration.json"
            regpath.write_text("fixture")
            reference = artifact(regpath)
            access = root / "access"
            (access / "receipts").mkdir(parents=True)
            case = {"controller": "uniform", "split": "generalization", "map_seed": 865927513,
                    "mode": "greedy", "sampling_seed": 20260923}
            receipt = access / "receipts" / (case_name(case) + ".json")
            write_json(receipt, {"case": case, "registration": reference, "status": "reserved"})
            frozen = {"access_directory": str(access)}
            registration = {"arm": "A3", "training": {"guide": "one-bus-public-plan-v4"}}
            verified = (frozen, registration, load_protocol(), [], Inputs())
            with patch.object(heldout_v2, "open_registration", return_value=verified), \
                    patch.object(heldout_v2, "jobs", return_value=[case]), \
                    patch.object(heldout_v2, "decide_arm", return_value={"eligible": False}), \
                    patch.object(heldout_v2, "_Permit") as permit, patch.object(heldout_v2.LiveV2, "__init__") as game:
                result = heldout_v2.execute(regpath)
                heldout_v2.execute(regpath)
                permit.assert_not_called()
                game.assert_not_called()
            self.assertEqual(json.loads(receipt.read_text())["status"], "failed")
            self.assertEqual(json.loads(result.read_text())["cases"][0]["execution_status"], "failed")

    def test_permit_binds_case_and_consumes_single_game_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine, regpath = root / "engine", root / "registration.json"
            engine.write_bytes(b"fixture engine")
            regpath.write_bytes(b"fixture registration")
            reference = artifact(regpath)
            reg = {"binaries": {"engine": artifact(engine)}, "training": {"guide": "one-bus-public-plan-v4"}}
            frozen = {"execution_registration": reference, "models": []}
            case = {"controller": "uniform", "map_seed": load_protocol()["held_out"]["maps"][0], "mode": "greedy", "sampling_seed": 20260923}
            args = SimpleNamespace(output=root / "case", openttd=engine, split="generalization", map_seed=case["map_seed"],
                                   mode="greedy", seed=20260923, decisions=512, guidance="one-bus-public-plan-v4")
            permit = _Permit(reference, frozen, reg, case, root / "case")
            with self.assertRaisesRegex(ValueError, "permit"):
                permit.live(engine, root / "case/worker", split=args.split, seed=args.map_seed, decisions=512)
            with patch("studies.heldout_v2.preflight"), patch("studies.heldout_v2.LiveV2") as game:
                for key, bad in (("split", "development"), ("map_seed", 1), ("decisions", 128), ("mode", "sampled"),
                                 ("seed", 1), ("guidance", "one-bus-public-plan-v2")):
                    changed = copy.copy(args)
                    setattr(changed, key, bad)
                    with self.assertRaises(ValueError):
                        permit.validate(changed, "uniform")
                game.assert_not_called()
                permit.validate(args, "uniform")
                permit.live(engine, root / "case/worker", split=args.split, seed=args.map_seed, decisions=512)
                self.assertEqual(game.call_count, 1)
                with self.assertRaises(ValueError):
                    permit.live(engine, root / "case/worker", split=args.split, seed=args.map_seed, decisions=512)


if __name__ == "__main__":
    unittest.main()
