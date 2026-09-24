#!/usr/bin/env python3
"""Export raw live recurrent V2 weights and verify a complete archived episode."""
import argparse
import gzip
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

from infer_v2 import PolicyClient
from local import capture_source, source_identity, write_json
from v2_export_policy import INPUT_NAMES, OUTPUT_NAMES, load_raw_policy, read_native_inputs
from v2_onnx_package import FORMAT, METADATA, digest


def run(args):
    torch.set_num_threads(1)
    training = json.loads((args.training_run / 'run.json').read_text())
    evaluation = json.loads((args.evaluation / 'run.json').read_text())
    if training.get('status') != 'completed' or training.get('kind') != 'native-v2-live-recurrent-ppo':
        raise ValueError('Export requires completed live V2 training')
    if training.get('observation_schema_id') != 'v2-m15-public-development-v2' or training.get('financial_features', 'raw') != 'raw':
        raise ValueError('This export supports only raw public V2 observations')
    weights = args.training_run.resolve() / 'inference-weights.pt'
    if Path(training['model']['path']).resolve() != weights or digest(weights) != training['model']['sha256']:
        raise ValueError('Source model identity differs')
    if evaluation.get('status') not in ('passed', 'completed') or evaluation.get('split') != 'development' or evaluation.get('model', {}).get('sha256') != digest(weights):
        raise ValueError('Export requires completed development evaluation of the same model')
    if evaluation.get('guidance', 'none') != training.get('guidance', 'none') or evaluation.get('guidance_override') is not None:
        raise ValueError('Export evaluation must use the trained guide')
    if evaluation.get('mode') != 'greedy' or evaluation.get('summary', {}).get('decisions') != 512:
        raise ValueError('Export requires one complete 512-decision greedy development episode')
    if ort.__version__ != '1.28.0':
        raise ValueError('Use ONNX Runtime 1.28.0 for this development export')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {'status': 'running', 'kind': 'live-v2-onnx-export', 'source': source_identity(),
        'source_training_run': str(args.training_run.resolve()), 'source_weights_sha256': digest(weights),
        'source_evaluation': str(args.evaluation.resolve()), 'source_evaluation_sha256': digest(args.evaluation / 'run.json'),
        'policy_sha256': digest(args.policy), 'torch': torch.__version__, 'onnx': onnx.__version__, 'onnxruntime': ort.__version__,
        'tolerances': {'probability_absolute': 1e-5, 'value_absolute': 1e-4},
        'claim_limit': 'Complete archived-input equivalence. New sequential game execution is a separate check.'}
    write_json(output / 'export.json', record)
    capture_source(output / 'source')
    client = None
    try:
        model = load_raw_policy(weights)
        observation, candidates = output / 'example-observation.bin', output / 'example-candidates.bin'
        def restore(index):
            root = args.evaluation / 'worker/artifacts'
            suffix = 'candidates-guided-one-bus' if training.get('guidance', 'none') != 'none' else 'candidates'
            for path, kind in [(observation, 'observation'), (candidates, suffix)]:
                archived = root / f'tensors-{index:06d}-{kind}.bin.gz'
                path.write_bytes(gzip.decompress(archived.read_bytes()))
            return read_native_inputs(observation, candidates)
        example = restore(0)
        with torch.inference_mode():
            for name in ['model.onnx', 'model-repeat.onnx']:
                torch.onnx.export(model, example, str(output / name), input_names=list(INPUT_NAMES),
                    output_names=list(OUTPUT_NAMES), opset_version=18, dynamo=False, external_data=False)
                graph = onnx.load(output / name, load_external_data=False)
                onnx.helper.set_model_props(graph, {**METADATA, 'openttd_rl.source_weights_sha256': digest(weights),
                    'openttd_rl.guidance': training.get('guidance', 'none')})
                onnx.checker.check_model(graph, full_check=True)
                onnx.save(graph, output / name)
        if digest(output / 'model.onnx') != digest(output / 'model-repeat.onnx'):
            raise RuntimeError('Repeated V2 exports differ')
        options = ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(output / 'model.onnx'), options, providers=['CPUExecutionProvider'])
        if [x.name for x in session.get_inputs()] != list(INPUT_NAMES) or [x.name for x in session.get_outputs()] != list(OUTPUT_NAMES):
            raise ValueError('ONNX graph signature differs')
        client = PolicyClient(args.policy.resolve(), output / 'native-reference.log', 'cpu', 20260923, 'greedy', weights)
        records = [json.loads(line) for line in (args.evaluation / 'predictions.jsonl').open()]
        if len(records) != 512:
            raise ValueError('Recorded evaluation is incomplete')
        hidden = np.zeros((1, 256), np.float32)
        errors = {'probability_max_abs': 0., 'value_max_abs': 0.}
        with (output / 'golden.jsonl').open('x') as golden:
            for index, recorded in enumerate(records):
                inputs = restore(index)
                native = client.request(f'{observation}\t{candidates}')
                feed = {name: tensor.numpy() for name, tensor in zip(INPUT_NAMES, inputs, strict=True)}
                feed['hidden_state'] = hidden
                values = session.run(list(OUTPUT_NAMES), feed)
                hidden, p = values[3], values[4][0]
                if not all(np.isfinite(t).all() for t in values) or np.any(p < 0) or abs(float(p.sum()) - 1.) > 1e-5 or np.any(p[~inputs[-4].numpy()[0]]):
                    raise RuntimeError('ONNX output is nonfinite or violates the legal mask')
                probability_error = float(np.max(np.abs(p - native['probabilities'])))
                value_error = abs(values[2].item() - native['value'])
                errors['probability_max_abs'] = max(errors['probability_max_abs'], probability_error)
                errors['value_max_abs'] = max(errors['value_max_abs'], value_error)
                if probability_error > 1e-5 or value_error > 1e-4 or int(p.argmax()) != native['row'] or native['row'] != recorded['prediction']['row']:
                    raise RuntimeError(f'Native/ONNX/recorded policy differs at decision {index + 1}')
                golden.write(json.dumps({'decision': index + 1, 'observation_sha256': digest(observation),
                    'candidates_sha256': digest(candidates), 'native_row': native['row'],
                    'probability_error': probability_error, 'value_error': value_error}) + '\n')
                if (index + 1) % 128 == 0:
                    print(f'Export verified {index + 1}/512 archived decisions', flush=True)
        client.close(); client = None
        verification = {'status': 'passed', 'exact_actions': 512, 'model_sha256': digest(output / 'model.onnx'),
            'repeat_bytes_exact': True, 'comparison': errors, 'golden_sha256': digest(output / 'golden.jsonl'),
            'native_policy_sha256': digest(args.policy), 'source_evaluation_sha256': record['source_evaluation_sha256']}
        write_json(output / 'verification.json', verification)
        manifest = {'format': FORMAT, 'status': 'qualified', 'metadata': METADATA,
            'runtime': 'onnxruntime-1.28.0-cpu', 'model_file': 'model.onnx', 'model_sha256': verification['model_sha256'],
            'source_weights_sha256': digest(weights), 'guidance': training.get('guidance', 'none'),
            'verification_file': 'verification.json', 'verification_sha256': digest(output / 'verification.json'),
            'qualification_scope': '512 archived native inputs; new sequential gameplay verified separately'}
        write_json(output / 'manifest.json', manifest)
        restore(0)
        record.update(status='passed', manifest_sha256=digest(output / 'manifest.json'), verification=verification)
    except BaseException as exc:
        record.update(status='failed', error=repr(exc))
        raise
    finally:
        if client is not None:
            client.abort()
        write_json(output / 'export.json', record)
    print(json.dumps(record['verification']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--training-run', type=Path, required=True)
    parser.add_argument('--evaluation', type=Path, required=True)
    parser.add_argument('--policy', type=Path, required=True, help='Native LibTorch inference executable for the CPU reference')
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args())
