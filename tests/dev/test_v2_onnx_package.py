"""Reject deployment packages that belong to a different boundary or model."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/dev'))
from v2_onnx_package import FORMAT, METADATA, checked_package, digest


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.training = {'model': {'sha256': 'a' * 64}, 'guidance': 'one-bus-public-plan-v1'}
        (self.root / 'model.onnx').write_bytes(b'unit-test-placeholder-not-an-onnx-graph')
        self.verification = {'status': 'passed', 'exact_actions': 512, 'model_sha256': digest(self.root / 'model.onnx')}
        (self.root / 'verification.json').write_text(json.dumps(self.verification))
        self.manifest = {'format': FORMAT, 'status': 'qualified', 'metadata': copy.deepcopy(METADATA),
            'runtime': 'onnxruntime-1.28.0-cpu', 'source_weights_sha256': 'a' * 64,
            'guidance': 'one-bus-public-plan-v1', 'model_file': 'model.onnx', 'model_sha256': digest(self.root / 'model.onnx'),
            'verification_file': 'verification.json', 'verification_sha256': digest(self.root / 'verification.json')}
        self.save()

    def save(self):
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))

    def test_matching_manifest(self):
        path, manifest = checked_package(self.root, self.training, 'cpu')
        self.assertEqual(path, self.root / 'model.onnx')
        self.assertEqual(manifest, self.manifest)

    def test_explicit_cuda_rejected(self):
        with self.assertRaisesRegex(ValueError, 'explicit CPU'):
            checked_package(self.root, self.training, 'cuda:0')

    def test_incompatible_fields(self):
        original = copy.deepcopy(self.manifest)
        for field, wrong in [('format', 'other'), ('status', 'running'), ('runtime', 'other'),
                             ('source_weights_sha256', 'b' * 64), ('guidance', 'none'),
                             ('model_file', '../model.onnx'), ('model_sha256', 'b' * 64),
                             ('verification_file', '../verification.json'), ('verification_sha256', 'b' * 64)]:
            with self.subTest(field=field):
                self.manifest = {**original, field: wrong}
                self.save()
                with self.assertRaises(ValueError):
                    checked_package(self.root, self.training, 'cpu')

    def test_scaled_inputs_rejected(self):
        self.manifest['metadata']['openttd_rl.financial_features'] = 'signed-log-v1'
        self.save()
        with self.assertRaises(ValueError):
            checked_package(self.root, self.training, 'cpu')

    def test_incomplete_verification_rejected_even_with_updated_hash(self):
        self.verification['exact_actions'] = 511
        (self.root / 'verification.json').write_text(json.dumps(self.verification))
        self.manifest['verification_sha256'] = digest(self.root / 'verification.json')
        self.save()
        with self.assertRaisesRegex(ValueError, 'full-episode'):
            checked_package(self.root, self.training, 'cpu')


if __name__ == '__main__':
    unittest.main()
