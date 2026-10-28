"""Substitute base graphics are accepted only when declared with their exact hash."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from cloud_cpu_setup import package_substitute
from local import baseset_identity, copy_baseset


class BasesetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.installed = self.root / "opengfx"
        self.installed.mkdir()
        (self.installed / "opengfx.obg").write_text("[metadata]\nname = OpenGFX\ndescription = base set [OpenGFX 7.1]\n")
        (self.installed / "ogfx1_base.grf").write_bytes(b"sprites")
        (self.installed / "readme.txt.gz").write_bytes(b"not packaged")

    def test_official_archive_needs_no_declaration(self):
        archive = self.root / "opengfx-8.0.tar"
        archive.write_bytes(b"official")
        identity = baseset_identity(archive, hashlib.sha256(b"official").hexdigest())
        self.assertEqual(identity, {"sha256": hashlib.sha256(b"official").hexdigest(), "official_opengfx_8_0": True})

    def test_undeclared_or_mismatched_substitute_is_rejected(self):
        archive = self.root / "slot/opengfx-8.0.tar"
        package_substitute(self.installed, archive)
        archive.write_bytes(archive.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "does not match"):
            baseset_identity(archive)
        archive.with_name(archive.name + ".substitute.json").unlink()
        with self.assertRaisesRegex(ValueError, "no substitute is declared"):
            baseset_identity(archive)

    def test_declared_substitute_is_reproducible_and_travels_with_copies(self):
        first, second = self.root / "a/opengfx-8.0.tar", self.root / "b/opengfx-8.0.tar"
        declaration = package_substitute(self.installed, first)
        package_substitute(self.installed, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(declaration["content"], f"OpenGFX 7.1 from {self.installed.resolve()}")
        self.assertEqual(sorted(declaration["files"]), ["ogfx1_base.grf", "opengfx.obg"])
        copied = self.root / "engine/baseset/opengfx-8.0.tar"
        copied.parent.mkdir(parents=True)
        copy_baseset(first, copied)
        identity = baseset_identity(copied)
        self.assertFalse(identity["official_opengfx_8_0"])
        self.assertEqual(identity["sha256"], declaration["sha256"])


if __name__ == "__main__":
    unittest.main()
