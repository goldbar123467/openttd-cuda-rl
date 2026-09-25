import copy
from argparse import Namespace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from audit_time_features import clock_features, run, summary, training_features


class TimeFeatureTests(unittest.TestCase):
    def test_full_episode_and_short_training_ranges_differ(self):
        self.assertEqual(clock_features(128, 16384), [.25, .75, .25, .75])
        self.assertEqual(clock_features(512, 65536), [1., 0., 1., 0.])
        report = summary([clock_features(i, 128 * i) for i in range(128)])
        self.assertEqual(report["16"]["max"], 127 / 512)
        self.assertEqual(report["17"]["min"], 385 / 512)
        self.assertEqual(sum(report["16"]["histogram"]), 128)

    def test_reconstructs_pre_action_clock_with_nonzero_native_origin(self):
        rows = [{"step": i + 1, "snapshot": {"tick": 4000 + (i + 1) * 128,
                 "transition_ordinal": i + 1, "scenario": {"split": "training"}}} for i in range(2)]
        self.assertEqual(training_features(rows), [[0., 1., 0., 1.], [1 / 512, 511 / 512, 1 / 512, 511 / 512]])
        for key, value in (("tick", 8000), ("transition_ordinal", 7), ("scenario", {"split": "final"})):
            changed = copy.deepcopy(rows)
            changed[1]["snapshot"][key] = value
            with self.assertRaises(ValueError):
                training_features(changed)

    def test_only_declared_unused_reset_may_have_empty_trace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            training = root / "training"
            metrics = training / "episode-metrics"
            metrics.mkdir(parents=True)
            (training / "run.json").write_text(json.dumps({"status": "completed", "episode_action_horizon": 128}))
            (metrics / "used.jsonl").write_text(json.dumps({"step": 1, "snapshot": {
                "tick": 128, "transition_ordinal": 1, "scenario": {"split": "training"}}}) + "\n")
            empty = metrics / "reset.jsonl"
            empty.write_bytes(b"")
            reset = metrics / "reset.json"
            reset.write_text(json.dumps({"status": "partial", "actions": 0}))
            args = Namespace(training_runs=[training], evaluations=[], output=root / "pass")
            with patch("audit_time_features.source_identity", return_value={}):
                run(args)
                report = json.loads((args.output / "audit.json").read_text())
                self.assertEqual(report["training"][0]["unused_reset_episodes"], [str(empty)])
                self.assertIn(str(reset), report["inputs_sha256"])
                self.assertEqual(empty.read_bytes(), b"")
                reset.write_text(json.dumps({"status": "completed", "actions": 0}))
                args.output = root / "fail"
                with self.assertRaisesRegex(ValueError, "declared unused reset"):
                    run(args)
                self.assertEqual(json.loads((args.output / "audit.json").read_text())["status"], "failed")


if __name__ == "__main__":
    unittest.main()
