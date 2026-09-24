"""Compatibility checks shared by development export and live playback."""
import hashlib
import json
from pathlib import Path

FORMAT = 'development-v2-live-onnx-package-1'
METADATA = {'openttd_rl.kind': 'development-v2-live-recurrent-policy-1',
    'openttd_rl.tensor_schema': 'openttd-rl-development-v2-public-tensors-1',
    'openttd_rl.observation_schema': 'v2-m15-public-development-v2',
    'openttd_rl.financial_features': 'raw'}

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def checked_package(path, training, device):
    path = Path(path).resolve()
    if device != 'cpu':
        raise ValueError('V2 ONNX playback requires explicit CPU; no device fallback')
    manifest = json.loads((path / 'manifest.json').read_text())
    if manifest.get('format') != FORMAT or manifest.get('status') != 'qualified':
        raise ValueError('A qualified live V2 ONNX package is required')
    if manifest.get('metadata') != METADATA or manifest.get('runtime') != 'onnxruntime-1.28.0-cpu':
        raise ValueError('ONNX observation/preprocessing/runtime compatibility differs')
    if manifest.get('source_weights_sha256') != training['model']['sha256'] or manifest.get('guidance') != training.get('guidance', 'none'):
        raise ValueError('ONNX package belongs to different weights or guide')
    if manifest.get('model_file') != 'model.onnx' or digest(path / 'model.onnx') != manifest.get('model_sha256'):
        raise ValueError('ONNX graph path/hash differs')
    if manifest.get('verification_file') != 'verification.json' or digest(path / 'verification.json') != manifest.get('verification_sha256'):
        raise ValueError('ONNX verification path/hash differs')
    verification = json.loads((path / 'verification.json').read_text())
    if verification.get('status') != 'passed' or verification.get('exact_actions') != 512 or verification.get('model_sha256') != manifest['model_sha256']:
        raise ValueError('ONNX full-episode verification differs')
    return path / 'model.onnx', manifest
