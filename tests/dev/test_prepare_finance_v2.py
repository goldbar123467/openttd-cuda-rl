"""Isolated engine preparation preserves its base and failed attempt evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from prepare_finance_v2 import run


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def arguments(self, base, output):
        return SimpleNamespace(base_engine_root=base, engine_root=output, jobs=2,
                               build_timeout=30, prepare_only=True)

    def test_output_inside_base_is_rejected_before_any_directory_creation(self):
        base = self.root / "base"
        base.mkdir()
        output = base / "finance"
        with self.assertRaisesRegex(ValueError, "separate"):
            run(self.arguments(base, output))
        self.assertFalse(output.exists())
        self.assertEqual(list(base.iterdir()), [])

    def test_initialization_failure_retains_manifest(self):
        output = self.root / "failed"
        with patch("prepare_finance_v2.source_identity", return_value={"commit": "fixture"}):
            with self.assertRaises(FileNotFoundError):
                run(self.arguments(self.root / "missing", output))
        record = json.loads((output / "preparation.json").read_text())
        self.assertEqual(record["status"], "failed")
        self.assertIn("FileNotFoundError", record["error"])
        self.assertGreaterEqual(record["elapsed_seconds"], 0)

    def test_prepare_clones_dirty_composition_without_mutating_base(self):
        base, output = self.root / "base", self.root / "finance"
        source = base / "source"
        (source / "src").mkdir(parents=True)
        action = source / "src/rl_v2_action.cpp"
        original = '#include <algorithm>\n#include "rl_v2_live.inc"\nEnumerateCandidates(CompanyID company)\n'
        action.write_text(original)
        def git(*args):
            subprocess.run(["git", "-C", str(source), *args], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        git("init", "-q")
        git("add", "src/rl_v2_action.cpp")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
        action.write_text(original + "// Existing dirty composition.\n")
        adapter = source / "src/rl_v2_live.inc"
        adapter.write_text("// Existing live adapter.\n")
        (base / "build/baseset").mkdir(parents=True)
        binary = base / "build/openttd"
        binary.write_bytes(b"fixture-engine")
        baseset = base / "build/baseset/opengfx-8.0.tar"
        baseset.write_bytes(b"fixture-baseset")
        before = {path: path.read_bytes() for path in (action, adapter, binary, baseset)}
        with patch("prepare_finance_v2.source_identity", return_value={"commit": "fixture"}), \
                patch("prepare_finance_v2.capture_source", side_effect=lambda path: path.mkdir()), \
                patch("prepare_finance_v2.BASESET_SHA256", hashlib.sha256(baseset.read_bytes()).hexdigest()):
            run(self.arguments(base, output))
        record = json.loads((output / "preparation.json").read_text())
        self.assertEqual(record["status"], "prepared")
        prepared = output / "source/src/rl_v2_action.cpp"
        self.assertIn("// Existing dirty composition.", prepared.read_text())
        self.assertIn('#include "economy_func.h"', prepared.read_text())
        self.assertIn("#include <cmath>", prepared.read_text())
        self.assertFalse(action.samefile(prepared))
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertTrue((output / "base-composition.patch").exists())
        self.assertTrue((output / "preparation-source").is_dir())
        self.assertFalse((output / "build").exists())


if __name__ == "__main__":
    unittest.main()
