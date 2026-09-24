"""Run with the optional MCP environment; preprocessing must fail before game launch."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
HAS_MCP = importlib.util.find_spec("mcp") is not None
if HAS_MCP:
    from mcp_v2 import Match


@unittest.skipUnless(HAS_MCP, "requires the separate MCP environment")
class MCPFinancialFeaturesTests(unittest.TestCase):
    def test_bad_training_mode_rejected_before_output_or_native_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            training = {"kind": "native-v2-live-recurrent-ppo", "status": "completed",
                        "observation_schema_id": "v2-m15-public-development-v2",
                        "financial_features": "unknown", "model": {}}
            (root / "run.json").write_text(json.dumps(training))
            args = SimpleNamespace(decisions=8, training_run=root, output=root / "output")
            with patch("mcp_v2.PolicyClient") as policy, patch("mcp_v2.LiveV2") as game:
                with self.assertRaises(ValueError):
                    Match(args)
                policy.assert_not_called()
                game.assert_not_called()
            self.assertFalse(args.output.exists())

    def test_mismatched_training_and_archive_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for training_mode, model_mode in (("signed-log-v1", "raw"), ("raw", "signed-log-v1")):
                with self.subTest(training_mode=training_mode):
                    training = {"kind": "native-v2-live-recurrent-ppo", "status": "completed",
                                "observation_schema_id": "v2-m15-public-development-v2",
                                "financial_features": training_mode,
                                "model": {"financial_features": model_mode}}
                    (root / "run.json").write_text(json.dumps(training))
                    args = SimpleNamespace(decisions=8, training_run=root, output=root / "output")
                    with patch("mcp_v2.PolicyClient") as policy, patch("mcp_v2.LiveV2") as game:
                        with self.assertRaisesRegex(ValueError, "preprocessing differs"):
                            Match(args)
                        policy.assert_not_called()
                        game.assert_not_called()
                    self.assertFalse(args.output.exists())

    def start_fixture(self, mode):
        match = Match.__new__(Match)
        match.args = SimpleNamespace(policy=Path("policy"), device="cpu", sampling_seed=23,
                                     openttd=Path("engine"), map_seed=1630856436,
                                     split="development", decisions=8)
        match.root = Path("unused-output")
        match.weights = Path("weights")
        match.financial_features = mode
        match.started, match.current = False, 0
        match.record = {}
        match.persist = Mock()
        match.neural_turn = Mock()
        match.observe = Mock(return_value={"state": "checked"})
        return match

    def test_saved_mode_is_checked_before_creating_native_game(self):
        for mode in ("raw", "signed-log-v1"):
            with self.subTest(mode=mode):
                match = self.start_fixture(mode)
                order = []
                policy = Mock()
                policy.check_financial_features.side_effect = lambda: order.append("verified")
                with patch("mcp_v2.PolicyClient", return_value=policy) as client, patch("mcp_v2.LiveV2", side_effect=lambda *a, **k: order.append("game")):
                    self.assertEqual(match.start(), {"state": "checked"})
                    self.assertEqual(client.call_args.kwargs["financial_features"], mode)
                self.assertEqual(order, ["verified", "game"])

    def test_native_mode_mismatch_aborts_before_game(self):
        match = self.start_fixture("signed-log-v1")
        policy = Mock()
        policy.check_financial_features.side_effect = ValueError("native preprocessing differs")
        with patch("mcp_v2.PolicyClient", return_value=policy), patch("mcp_v2.LiveV2") as game:
            with self.assertRaisesRegex(ValueError, "preprocessing differs"):
                match.start()
            game.assert_not_called()
        self.assertEqual(match.record["status"], "failed")


if __name__ == "__main__":
    unittest.main()
