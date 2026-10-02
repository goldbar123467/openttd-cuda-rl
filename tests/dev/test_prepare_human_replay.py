"""Bounded replay rebuilds preserve the earlier executable and failed evidence."""
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/dev'))
import prepare_human_replay as prepare


class ReplayRefreshTests(unittest.TestCase):
    def fixture(self, directory, status='built'):
        root, base, repo = (Path(directory) / name for name in ('replay', 'base', 'repo'))
        for folder in (root / 'source/src', root / 'build', root / 'source-provenance',
                       base / 'source/src', base / 'build/baseset', repo / 'integration/dev'):
            folder.mkdir(parents=True)
        (root / 'source/src/rl_bus_orders.inc').write_text('original helper')
        (root / 'source/src/rl_human_replay.inc').write_text('original replay')
        (root / 'source-provenance/source.json').write_text('{}')
        (root / 'build.log').write_text('original build log')
        (root / 'build/build.ninja').write_text('configured')
        (base / 'source/src/rl_bus_orders.inc').write_text('original helper')
        (base / 'build/openttd').write_bytes(b'base executable')
        (base / 'build/baseset/opengfx-8.0.tar').write_bytes(b'isolated assets')
        (repo / 'integration/dev/rl_human_replay.inc').write_text('repaired replay')
        original = {'status': status, 'base': str(base), 'base_source_hashes': prepare.source_hashes(base / 'source'),
                    'repository_replay_include_sha256': hashlib.sha256(b'original replay').hexdigest()}
        if status == 'built':
            (root / 'build/openttd').write_bytes(b'original executable')
            original.update(composed_source_hashes=prepare.source_hashes(root / 'source'),
                            executable_sha256=hashlib.sha256(b'original executable').hexdigest())
        (root / 'preparation.json').write_text(json.dumps(original))
        (base / 'source/src/rl_bus_orders.inc').write_text('bounded shared guard')
        return root, base, repo, original

    def perform_refresh(self, root, base, repo):
        def build(*args, **kwargs):
            (root / 'build/openttd').write_bytes(b'updated executable')
        with patch.object(prepare, 'ROOT', repo), patch.object(prepare, 'source_identity', return_value={}), \
                patch.object(prepare, 'capture_source', return_value={}), patch.object(prepare.subprocess, 'run', side_effect=build):
            prepare.refresh(base, root, 2)

    def test_successful_preparation_is_archived_before_incremental_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            root, base, repo, original = self.fixture(directory)
            self.perform_refresh(root, base, repo)
            self.assertEqual(json.loads((root / 'preparation.json').read_text()), original)
            self.assertEqual((root / 'pre-refresh/openttd').read_bytes(), b'original executable')
            with tarfile.open(root / 'pre-refresh/source.tar.gz') as archive:
                self.assertEqual(archive.extractfile('./src/rl_human_replay.inc').read(), b'original replay')
            self.assertEqual((root / 'source/src/rl_bus_orders.inc').read_text(), 'bounded shared guard')
            self.assertEqual((root / 'source/src/rl_human_replay.inc').read_text(), 'repaired replay')
            final = json.loads((root / 'final-build.json').read_text())
            self.assertEqual(final['status'], 'built')
            self.assertEqual(final['previous_status'], 'built')
            self.assertTrue(final['base_unchanged'])

    def test_failed_compile_is_preserved_without_inventing_prior_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root, base, repo, original = self.fixture(directory, 'failed')
            self.perform_refresh(root, base, repo)
            self.assertEqual(json.loads((root / 'preparation.json').read_text()), original)
            self.assertEqual((root / 'pre-refresh/build.log').read_text(), 'original build log')
            self.assertFalse((root / 'pre-refresh/openttd').exists())
            final = json.loads((root / 'final-build.json').read_text())
            self.assertEqual(final['previous_status'], 'failed')
            self.assertIsNone(final['previous_executable_sha256'])

    def test_unrelated_base_or_prepared_source_edits_fail_closed(self):
        for target in ('base', 'replay'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root, base, repo, _ = self.fixture(directory)
                ((base if target == 'base' else root) / 'source/src/unrelated.cpp').write_text('unrelated edit')
                with self.assertRaisesRegex(ValueError, 'outside|changed before refresh'):
                    self.perform_refresh(root, base, repo)
                self.assertFalse((root / 'pre-refresh').exists())


if __name__ == '__main__':
    unittest.main()
