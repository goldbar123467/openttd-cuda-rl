"""Client preflight failures must preserve native request sequencing and splits."""
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from live_v2 import LiveV2, reset_manifest


class LiveV2PreflightTests(unittest.TestCase):
    def test_visible_playback_rejects_missing_or_fake_display_before_io(self):
        with patch.object(Path, "read_text", side_effect=AssertionError("must not read")):
            for environment in ({}, {"DISPLAY": ":0", "SDL_VIDEODRIVER": "dummy"},
                                {"DISPLAY": ":0", "SDL_VIDEODRIVER": "offscreen"}):
                with patch.dict(os.environ, environment, clear=True), self.assertRaisesRegex(ValueError, "real native display"):
                    LiveV2("missing", "missing", visible=True)
            with patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True), self.assertRaisesRegex(ValueError, "one company"):
                LiveV2("missing", "missing", visible=True, companies=2)

    def test_held_out_split_rejected_before_any_file_access(self):
        with patch.object(Path, "read_text", side_effect=AssertionError("must not read")), \
                patch.object(Path, "read_bytes", side_effect=AssertionError("must not read")):
            for split in ("generalization", "final", "unknown"):
                with self.subTest(split=split), self.assertRaisesRegex(ValueError, "held-out"):
                    reset_manifest(Path("missing"), Path("missing"), None, split)

    def test_floating_and_boolean_dimensions_or_seed_fail_before_io(self):
        with patch.object(Path, "read_text", side_effect=AssertionError("must not read")):
            for options in ({"width": 64.0}, {"height": True}, {"seed": False}, {"seed": 1110312784.0}):
                arguments = {"seed": None, "split": "training", **options}
                with self.subTest(options=options), self.assertRaisesRegex(ValueError, "integers"):
                    reset_manifest(Path("missing"), Path("missing"), **arguments)

    def test_invalid_timing_rejected_before_files_or_processes(self):
        with patch.object(Path, "mkdir", side_effect=AssertionError("must not write")):
            for options in ({"decisions": 0}, {"decisions": 513}, {"ticks": 129}, {"ticks": 1.0}, {"ticks": True}):
                with self.subTest(options=options), self.assertRaisesRegex(ValueError, "bounds"):
                    LiveV2("missing", "missing", **options)

    def test_unsent_oversized_or_nonfinite_request_does_not_consume_id(self):
        client = LiveV2.__new__(LiveV2)
        client.request_id = 3
        with self.assertRaisesRegex(ValueError, "frame limit"):
            client.request("ACT", candidate="x" * 16384)
        self.assertEqual(client.request_id, 3)
        with self.assertRaises(ValueError):
            client.request("ACT", candidate=float("nan"))
        self.assertEqual(client.request_id, 3)
        with self.assertRaisesRegex(ValueError, "identity"):
            client.request("OBSERVE", id=100)
        self.assertEqual(client.request_id, 3)

    def test_shared_company_and_balanced_budget_preflight(self):
        with patch.object(Path, "read_text", side_effect=AssertionError("must not read")):
            for options in ({"companies": True}, {"companies": 3}, {"companies": 2, "decisions": 7},
                            {"companies": 2, "first_company": 2}, {"first_company": 1}):
                with self.subTest(options=options), self.assertRaisesRegex(ValueError, "Company count"):
                    LiveV2("missing", "missing", **options)


if __name__ == "__main__":
    unittest.main()
