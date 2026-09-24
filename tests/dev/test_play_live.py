"""Portable native screenshot handling and pre-launch scenario boundaries."""
from argparse import Namespace
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
import play_live


class PlaybackTests(unittest.TestCase):
    def test_rejects_held_out_filename_before_reading_or_launching(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "training/development instance filenames"):
                play_live.run(Namespace(instance=root / "m02-template-07.json", output=root / "run"))
            self.assertFalse((root / "run").exists())

    def test_rejects_nontraining_metadata_even_with_allowed_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            instance = root / "m02-template-05.json"
            instance.write_text(json.dumps({"template_id": "m02-template-05", "split": "final"}))
            with self.assertRaisesRegex(ValueError, "forbids held-out"):
                play_live.run(Namespace(instance=instance, output=root / "run"))
            self.assertFalse((root / "run").exists())

    def test_png_is_optional_bmp_header_is_supported_and_dimensions_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "screenshot").mkdir()
            path = root / "screenshot/m11-playback.bmp"
            # Header-only fixture for format/size detection; real bitmap decoding
            # is separately verified on the native SDL replay's rendered output.
            path.write_bytes(b"BM" + bytes(16) + struct.pack("<ii", 1280, 800))
            self.assertEqual(play_live.native_screenshot(root), path)
            path.write_bytes(b"BM" + bytes(16) + struct.pack("<ii", 800, 600))
            with self.assertRaisesRegex(RuntimeError, "dimensions differ"):
                play_live.native_screenshot(root)


if __name__ == "__main__":
    unittest.main()
