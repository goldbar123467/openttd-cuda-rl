"""Concurrency evidence must show overlap and preserve every semantic byte."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/dev'))
import check_concurrent_determinism as check


class DeterminismTests(unittest.TestCase):
    def test_append_counter_only_counts_complete_lines_and_rejects_truncation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'trace'
            counter = check.LineCounter(path)
            self.assertEqual(counter.poll(), 0)
            path.write_bytes(b'one\npar')
            self.assertEqual(counter.poll(), 1)
            with path.open('ab') as stream:
                stream.write(b'tial\nthree\n')
            self.assertEqual(counter.poll(), 3)
            self.assertEqual(counter.poll(), 3)
            path.write_bytes(b'')
            with self.assertRaisesRegex(ValueError, 'truncated'):
                counter.poll()

    def test_real_shared_progress_is_required(self):
        samples = [{'monotonic_ns': 10, 'counts': [1, 2, 3, 4]},
                   {'monotonic_ns': 20, 'counts': [2, 3, 4, 5]}]
        self.assertTrue(check.overlap(samples, 4)['passed'])
        # One worker was already done: overlapping process lifetimes are insufficient.
        samples[0]['counts'][3] = samples[1]['counts'][3] = 512
        with self.assertRaisesRegex(ValueError, 'all concurrent games advanced'):
            check.overlap(samples, 4)

    def test_static_worker_or_sequential_runs_do_not_count_as_overlap(self):
        for counts in (([1, 1], [5, 1]), ([1, 0], [512, 1]), ([0, 0], [512, 512])):
            with self.assertRaises(ValueError):
                check.overlap([{'monotonic_ns': i, 'counts': value} for i, value in enumerate(counts)], 2)
        with self.assertRaises(ValueError):
            check.overlap([], 1)

    def test_one_byte_difference_fails_even_when_json_semantics_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            a, b = root/'a', root/'b'
            a.write_bytes(b'{"action":1}\n')
            b.write_bytes(b'{"action": 1}\n')
            result = check.compare_bytes('test', a, b, check.Inputs())
            self.assertFalse(result['equal'])
            self.assertIn('first_different_byte', result)
            b.write_bytes(a.read_bytes())
            self.assertTrue(check.compare_bytes('test', a, b, check.Inputs())['equal'])

    def predictions(self, root, *, delta=0, escape=False, incomplete=False):
        root.mkdir()
        lines = []
        for i in range(1, 512 if incomplete else 513):
            lines.append({'decision': i, 'token': 'state', 'inference_elapsed_ns': i+delta,
                          'prediction': {'row': 3, 'value': .25}, 'candidate': {'stable_key': 'bus'},
                          'guidance': {'sampling_binary': '/outside/tensor.bin' if escape else str(root/'worker/artifacts/tensor.bin'),
                                       'sampling_binary_sha256': 'guided', 'native_binary_sha256': 'native'},
                          'future_semantic_field': i})
        (root/'predictions.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in lines))

    def test_prediction_projection_excludes_only_time_and_run_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            a, b = root/'a', root/'b'
            self.predictions(a)
            self.predictions(b, delta=25)
            self.assertEqual(check.v2_prediction_bytes(a, check.Inputs()), check.v2_prediction_bytes(b, check.Inputs()))
            p = b/'predictions.jsonl'
            p.write_text(p.read_text().replace('"future_semantic_field": 512', '"future_semantic_field": 513'))
            self.assertNotEqual(check.v2_prediction_bytes(a, check.Inputs()), check.v2_prediction_bytes(b, check.Inputs()))

    def test_prediction_projection_rejects_missing_rows_and_escaped_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, options in [('missing', {'incomplete': True}), ('escape', {'escape': True})]:
                self.predictions(root/name, **options)
                with self.assertRaises(ValueError):
                    check.v2_prediction_bytes(root/name, check.Inputs())

    @unittest.skipUnless(sys.platform == 'linux', 'native driver requires Linux')
    def test_heldout_seed_refused_before_any_process_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = argparse.Namespace(output=Path(temporary)/'run', device='cpu', map_seed=999)
            with patch.object(check, 'host', return_value={}), patch.object(check, 'capture_source', return_value={}), \
                    patch.object(check, 'source_identity', return_value={}), \
                    patch.object(check.Inputs, 'json', return_value={'seeds': {'sets': {'development': {'seeds': [1, 2]}}}}), \
                    patch.object(check, 'run_stage') as launch:
                with self.assertRaisesRegex(ValueError, 'development map'):
                    check.run(args)
                launch.assert_not_called()
            self.assertEqual(json.loads((args.output/'verification.json').read_text())['status'], 'failed')

    @unittest.skipUnless(sys.platform == 'linux', 'native process groups require Linux')
    def test_failed_child_retains_failure_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, 'child failed'):
                check.run_stage('failed-child', [[sys.executable, '-c', 'raise SystemExit(2)']], [], root, 5)
            record = json.loads((root/'failed-child.json').read_text())
            self.assertEqual(record['status'], 'failed')
            self.assertEqual(record['returncodes'], [2])
            self.assertTrue((root/'failed-child-0.log').is_file())


if __name__ == '__main__':
    unittest.main()
