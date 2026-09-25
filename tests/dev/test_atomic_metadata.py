import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from local import write_json


class AtomicMetadataTests(unittest.TestCase):
    def test_failed_publication_preserves_last_complete_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.json"
            write_json(path, {"update": 8})
            with patch("local.os.replace", side_effect=OSError("interrupted publication")):
                with self.assertRaises(OSError):
                    write_json(path, {"update": 16})
            self.assertEqual(json.loads(path.read_text()), {"update": 8})
            self.assertEqual(list(path.parent.iterdir()), [path])
            write_json(path, {"update": 16})
            self.assertEqual(json.loads(path.read_text()), {"update": 16})
            with self.assertRaises(ValueError):
                write_json(path, {"update": float("nan")})
            self.assertEqual(json.loads(path.read_text()), {"update": 16})


if __name__ == "__main__":
    unittest.main()
