"""Maintenance must retain evidence on corruption, changed inputs or unsafe paths."""
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
import archive_completed as archive


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "runs"
        self.worker = self.root / "completed" / "worker"
        self.worker.mkdir(parents=True)
        (self.worker.parent / "run.json").write_text('{"status":"completed"}')
        self.path = self.worker / "requests.jsonl"
        self.original = (b'{"request":"OBSERVE","value":1234}\n' * 2048)
        self.path.write_bytes(self.original)

    def tearDown(self):
        self.temporary.cleanup()

    def row(self):
        return {"path": str(self.path.relative_to(self.root)), **archive.fingerprint(self.path),
                "completion": archive.completion(self.root, self.path)}

    def test_archive_and_restore_match_original_and_keep_verified_archive(self):
        records = []
        archive.archive_one(self.root, self.row(), [], records.append)
        self.assertFalse(self.path.exists())
        self.assertEqual([r['state'] for r in records], ['verified', 'archived'])
        zipped = self.path.with_suffix('.jsonl.gz')
        self.assertEqual(gzip.decompress(zipped.read_bytes()), self.original)
        journal = self.root / 'journal.jsonl'
        journal.write_text(''.join(json.dumps(r) + '\n' for r in records))
        archive.restore(self.root, journal, str(self.path.relative_to(self.root)))
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertTrue(zipped.exists())
        with self.assertRaises(FileExistsError):
            archive.restore(self.root, journal, str(self.path.relative_to(self.root)))

    def test_changed_input_and_existing_archive_preserve_original(self):
        row = self.row()
        self.path.write_bytes(self.original + b'changed')
        with self.assertRaisesRegex(ValueError, 'changed since plan'):
            archive.archive_one(self.root, row, [], lambda r: None)
        self.assertTrue(self.path.exists())
        zipped = self.path.with_suffix('.jsonl.gz')
        zipped.write_bytes(b'conflicting archive')
        with self.assertRaises(FileExistsError):
            archive.archive_one(self.root, self.row(), [], lambda r: None)
        self.assertEqual(zipped.read_bytes(), b'conflicting archive')
        self.assertTrue(self.path.exists())

    def test_corrupt_verification_never_removes_source(self):
        with patch.object(archive, 'sha_stream', return_value=('wrong', len(self.original))):
            with self.assertRaisesRegex(RuntimeError, 'Lossless verification'):
                archive.archive_one(self.root, self.row(), [], lambda r: None)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertFalse(self.path.with_suffix('.jsonl.gz').exists())

    def test_failed_child_active_parent_and_protected_paths_rejected(self):
        (self.worker / 'run.json').write_text('{"status":"failed"}')
        with self.assertRaisesRegex(ValueError, 'No completed status'):
            archive.completion(self.root, self.path)
        (self.worker / 'run.json').write_text('{"status":"completed"}')
        (self.worker.parent / 'run.json').write_text('{"status":"running"}')
        with self.assertRaisesRegex(ValueError, 'Running ancestor'):
            archive.completion(self.root, self.path)
        for relative in ('heldout-confirmation/requests.jsonl', 'completed/checkpoints/tensors-0.bin',
                         'completed/source/requests.jsonl', 'completed/trainer.pt', '../requests.jsonl'):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                archive.eligible(self.root, self.root / relative, [])
        with self.assertRaisesRegex(ValueError, 'Explicitly protected'):
            archive.eligible(self.root, self.path, ['completed'])

    def test_symlink_rejected(self):
        link = self.worker / 'tensors-000000-observation.bin'
        link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            archive.eligible(self.root, link, [])

    def test_metadata_archive_and_explicit_plan_kind(self):
        metadata = self.worker / 'tensors-000000-candidates.json'
        metadata.write_bytes(self.original)
        with patch.object(archive, 'idle'):
            result = archive.plan(self.root, [], ('tensor_metadata',))
        self.assertEqual(len(result['files']), 1)
        self.assertEqual(result['files'][0]['path'], str(metadata.relative_to(self.root)))
        records = []
        archive.archive_one(self.root, result['files'][0], [], records.append)
        self.assertFalse(metadata.exists())
        self.assertEqual(gzip.decompress(metadata.with_suffix('.json.gz').read_bytes()), self.original)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_batch_flush_failure_preserves_all_originals(self):
        for i in range(3):
            (self.worker / f'tensors-{i:06d}-candidates.json').write_bytes(self.original)
        with patch.object(archive, 'idle'):
            plan = archive.plan(self.root, [], ('tensor_metadata',))
        plan_path = self.root.parent / 'plan.json'
        plan_path.write_text(json.dumps(plan))
        with patch.object(archive, 'idle'), patch.object(archive, 'sync_filesystem', side_effect=OSError('flush failed')):
            with self.assertRaisesRegex(OSError, 'flush failed'):
                archive.apply(plan_path, self.root.parent / 'execution', batch_size=3)
        for row in plan['files']:
            self.assertEqual((self.root / row['path']).read_bytes(), self.original)

    def test_batch_rejects_other_filesystem_before_creating_outputs(self):
        with patch.object(archive, 'idle'):
            plan = archive.plan(self.root, [])
        plan['files'][0]['device'] += 1
        plan_path = self.root.parent / 'plan.json'
        plan_path.write_text(json.dumps(plan))
        output = self.root.parent / 'execution'
        with self.assertRaisesRegex(ValueError, 'flushed run-root filesystem'):
            archive.apply(plan_path, output, batch_size=2)
        self.assertFalse(output.exists())
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_batched_archives_have_prior_verified_journal_and_exact_bytes(self):
        for i in range(5):
            (self.worker / f'tensors-{i:06d}-observation.json').write_bytes(self.original)
        with patch.object(archive, 'idle'):
            plan = archive.plan(self.root, [], ('tensor_metadata',))
        plan_path = self.root.parent / 'plan.json'
        plan_path.write_text(json.dumps(plan))
        output = self.root.parent / 'execution'
        with patch.object(archive, 'idle'):
            archive.apply(plan_path, output, batch_size=2)
        self.assertEqual(json.loads((output / 'summary.json').read_text())['files'], 5)
        seen = set()
        for row in map(json.loads, (output / 'journal.jsonl').read_text().splitlines()):
            if row['state'] == 'verified':
                seen.add(row['path'])
            else:
                self.assertIn(row['path'], seen)
                self.assertFalse((self.root / row['path']).exists())
                self.assertEqual(gzip.decompress((self.root / row['archive']).read_bytes()), self.original)


if __name__ == '__main__':
    unittest.main()
