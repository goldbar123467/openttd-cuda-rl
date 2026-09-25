#!/usr/bin/env python3
"""S2-7: full V1 solo/four-worker and V2 solo/two-worker determinism checks.

Launch existing evaluation CLIs without changing their inference or game loops.
Compare original action/economic bytes and separately record actual overlap. This
is a bounded correctness experiment, not a throughput or learning comparison.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from local import ROOT, capture_source, host, positive, source_identity, write_json
from studies.evidence_v2 import Inputs, load_episode
from verify_device_agreement import package_hashes


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode() + b'\n'


class LineCounter:
    """Read only newly appended bytes; count complete records without parsing them."""
    def __init__(self, path):
        self.path, self.offset, self.count, self.inode = Path(path), 0, 0, None

    def poll(self):
        if not self.path.exists():
            return self.count
        stat = self.path.stat()
        if self.inode not in (None, stat.st_ino) or stat.st_size < self.offset:
            raise ValueError('A monitored trace was replaced/truncated')
        self.inode = stat.st_ino
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            data = stream.read()
        self.offset += len(data)
        self.count += data.count(b'\n')
        return self.count


def overlap(samples, workers):
    """Require every worker to advance within a shared unfinished interval."""
    if workers < 2:
        raise ValueError('Concurrency proof requires at least two workers')
    active = [s for s in samples if len(s['counts']) == workers and all(0 < n < 512 for n in s['counts'])]
    for first in active:
        for last in active:
            if last['monotonic_ns'] > first['monotonic_ns'] and all(b > a for a, b in zip(first['counts'], last['counts'], strict=True)):
                return {'passed': True, 'workers': workers, 'first': first, 'last': last,
                        'shared_progress_seconds': (last['monotonic_ns'] - first['monotonic_ns']) / 1e9}
    raise ValueError('No observed interval in which all concurrent games advanced')


def run_stage(name, commands, progress_paths, root, timeout):
    """Own process groups, preserve logs, and clean up only this stage on failure."""
    processes, samples = [], []
    counters = [LineCounter(p) for p in progress_paths]
    record = {'name': name, 'commands': commands, 'status': 'running', 'processes': [],
              'progress_paths': [str(p) for p in progress_paths], 'started_monotonic_ns': time.monotonic_ns()}
    try:
        with contextlib.ExitStack() as stack:
            for index, command in enumerate(commands):
                log = stack.enter_context((root / f'{name}-{index}.log').open('x'))
                process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                processes.append(process)
                record['processes'].append({'pid': process.pid, 'started_monotonic_ns': time.monotonic_ns()})
            write_json(root / f'{name}.json', record)
            while True:
                counts = [counter.poll() for counter in counters]
                if not samples or counts != samples[-1]['counts']:
                    samples.append({'monotonic_ns': time.monotonic_ns(), 'counts': counts})
                codes = [process.poll() for process in processes]
                if any(code not in (None, 0) for code in codes):
                    raise RuntimeError(f'{name} child failed: {codes}; inspect retained stage logs')
                if all(code == 0 for code in codes):
                    break
                if (time.monotonic_ns() - record['started_monotonic_ns']) / 1e9 > timeout:
                    raise TimeoutError(f'{name} exceeded its bounded timeout')
                time.sleep(.1)
            record['status'] = 'passed'
    except BaseException as exc:
        record.update(status='failed', error=str(exc))
        # start_new_session gives each owned CLI a private process group, including
        # its native workers. Do not leave grandchildren running after a failure.
        for process in processes:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        raise
    finally:
        record.update(finished_monotonic_ns=time.monotonic_ns(), returncodes=[p.poll() for p in processes], progress=samples)
        write_json(root / f'{name}.json', record)
    print(f'CONCURRENCY stage={name} passed', flush=True)
    return record


def compare_bytes(label, left, right, inputs):
    a, b = inputs.read(left), inputs.read(right)
    result = {'label': label, 'left': str(left), 'right': str(right), 'equal': a == b,
              'left_sha256': hashlib.sha256(a).hexdigest(), 'right_sha256': hashlib.sha256(b).hexdigest(),
              'left_bytes': len(a), 'right_bytes': len(b)}
    if a != b:
        result['first_different_byte'] = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return result


def checked_v1(root, policy, template, seed, inputs):
    run = inputs.json(root / 'run.json')
    episode = root / f'{policy}-{template}-s{seed}'
    ep = inputs.json(episode / 'episode.json')
    if (run['kind'] != 'complete-episode-development-evaluation' or run['status'] != 'completed' or
            run['split'] != 'development' or run['final_evaluation_accessed'] is not False or
            run['action_horizon'] != 512 or run['ticks_per_action'] != 128 or run['inference_backend'] != 'native' or
            ep['status'] != 'completed' or ep['scenario']['split'] != 'development' or ep['template_id'] != template or
            ep['policy'] != policy or ep['sampling_seed'] != seed or ep['actions'] != 512 or
            ep['inference_device'] != 'cpu' or ep['inference_backend'] != 'native' or
            ep['package_id'] != Path(run['package']).name or ep not in run['episodes']):
        raise ValueError('V1 full development evaluation identity differs')
    rows = [json.loads(line) for line in inputs.read(episode / 'actions.jsonl').splitlines()]
    if len(rows) != 512 or [row['step'] for row in rows] != list(range(1, 513)) or rows[-1]['termination']['reason'] == 'NONE':
        raise ValueError('V1 action trace is incomplete or unordered')
    if any(row['prediction'] is None or row['prediction']['action'] != row['action'] or not row['legal'][row['action']] for row in rows):
        raise ValueError('V1 action differs from its neural prediction or legal mask')
    summary = dict(ep)
    del summary['elapsed_seconds']  # Only the measured duration is nondeterministic.
    return episode, summary


def v2_prediction_bytes(root, inputs):
    """Compare every prediction/guide field except elapsed time and root location."""
    result = []
    for index, line in enumerate(inputs.read(root / 'predictions.jsonl').splitlines()):
        row = json.loads(line)
        if row['decision'] != index + 1 or not isinstance(row.pop('inference_elapsed_ns'), int):
            raise ValueError('V2 prediction sequence/timing differs')
        if row['guidance'] is not None:
            # Keep the complete relative filename AND both content hashes. Only
            # the unique output directory differs between identical executions.
            path = Path(row['guidance']['sampling_binary'])
            row['guidance']['sampling_binary'] = str(path.relative_to(root / 'worker'))
        result.append(canonical(row))
    if len(result) != 512:
        raise ValueError('V2 prediction trace is incomplete')
    return b''.join(result)


def run(args):
    if sys.platform != 'linux':
        raise ValueError('Run this native concurrency check on Linux/WSL')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    inputs = Inputs()
    record = {'kind': 'v1-v2-concurrency-determinism-v1', 'status': 'running', 'command': sys.argv,
              'source': source_identity(), 'source_archive': capture_source(root / 'source'), 'host': host(),
              'configuration': {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
              'disk_before': shutil.disk_usage(root)._asdict(), 'stages': {}, 'comparisons': [],
              'final_evaluation_accessed': False,
              'claim': 'Finite full-game determinism under verified concurrent load; no learning or speedup claim'}
    try:
        if record['disk_before']['free'] < 20 * 1024**3:
            raise ValueError('Concurrency experiment requires 20 GiB free for retained native artifacts')
        if args.device == 'cuda:0' and not record['host']['cuda_available']:
            raise ValueError('CUDA requested but unavailable; no CPU fallback')
        contract = inputs.json(ROOT / 'config/v2/m15-scalable-contract.json')
        if args.map_seed not in contract['seeds']['sets']['development']['seeds']:
            raise ValueError('Only an explicit V2 development map is permitted')
        for binary in (args.v1_engine, args.v1_evaluator, args.v2_engine, args.v2_policy):
            inputs.read(binary.resolve())
        hashes, _ = package_hashes(args.v1_package.resolve())
        for name in hashes:
            inputs.read(args.v1_package.resolve() / name)
        for template in ('m02-template-05', 'm02-template-06'):
            inputs.json(args.v1_instance_dir.resolve() / (template + '.json'))
        training = inputs.json(args.v2_training_run.resolve() / 'run.json')
        model = args.v2_training_run.resolve() / 'inference-weights.pt'
        if (training['kind'] != 'native-v2-live-recurrent-ppo' or training['status'] != 'completed' or
                Path(training['model']['path']).resolve() != model or
                hashlib.sha256(inputs.read(model)).hexdigest() != training['model']['sha256'] or
                training['engine_sha256'] != sha256(args.v2_engine)):
            raise ValueError('V2 final weights/training/engine provenance differs')
        record['v1_package_hashes'] = hashes
        record['v2_model'] = training['model']
        write_json(root / 'verification.json', record)
        v1 = [sys.executable, str(ROOT / 'scripts/dev/evaluate_live.py'),
              '--openttd', str(args.v1_engine.resolve()), '--instance-dir', str(args.v1_instance_dir.resolve()),
              '--evaluator', str(args.v1_evaluator.resolve()), '--package', str(args.v1_package.resolve()),
              '--backend', 'native', '--split', 'development', '--templates', 'm02-template-05', 'm02-template-06',
              '--seeds', str(args.seed), '--executor', 'process', '--bridge-validation', 'fast',
              '--hypothesis', 'Fixed-model concurrency correctness; no recipe selection or learning claim']
        v1_solo, v1_loaded = root / 'v1-solo', root / 'v1-workers4'
        record['stages']['v1-solo'] = run_stage('v1-solo', [v1 + ['--policies', 'greedy', '--workers', '1', '--output', str(v1_solo)]], [], root, args.timeout)
        progress = [v1_loaded / f'{policy}-{template}-s{args.seed}' / 'actions.jsonl'
                    for policy in ('greedy', 'sampled') for template in ('m02-template-05', 'm02-template-06')]
        record['stages']['v1-workers4'] = run_stage('v1-workers4', [v1 + ['--policies', 'greedy', 'sampled', '--workers', '4', '--output', str(v1_loaded)]], progress, root, args.timeout)
        record['v1_overlap'] = overlap(record['stages']['v1-workers4']['progress'], 4)
        for policy in ('greedy', 'sampled'):
            for template in ('m02-template-05', 'm02-template-06'):
                checked_v1(v1_loaded, policy, template, args.seed, inputs)
        for template in ('m02-template-05', 'm02-template-06'):
            a, summary_a = checked_v1(v1_solo, 'greedy', template, args.seed, inputs)
            b, summary_b = checked_v1(v1_loaded, 'greedy', template, args.seed, inputs)
            record['comparisons'].append(compare_bytes('V1 ' + template + ' complete action/economic trace', a/'actions.jsonl', b/'actions.jsonl', inputs))
            # Retain the separately comparable metadata/economic summary, with its
            # sole measured duration field excluded explicitly.
            for label, summary in (('solo', summary_a), ('workers4', summary_b)):
                (root / f'v1-{template}-{label}-summary.json').write_bytes(canonical(summary))
            record['comparisons'].append(compare_bytes('V1 ' + template + ' episode summary', root/f'v1-{template}-solo-summary.json', root/f'v1-{template}-workers4-summary.json', inputs))
        write_json(root / 'verification.json', record)
        v2 = [sys.executable, str(ROOT / 'scripts/dev/infer_v2.py'), '--openttd', str(args.v2_engine.resolve()),
              '--policy', str(args.v2_policy.resolve()), '--training-run', str(args.v2_training_run.resolve()),
              '--device', args.device, '--mode', 'greedy', '--decisions', '512', '--split', 'development',
              '--map-seed', str(args.map_seed), '--seed', str(args.seed)]
        cases = [root/'v2-solo', root/'v2-concurrent-a', root/'v2-concurrent-b']
        record['stages']['v2-solo'] = run_stage('v2-solo', [v2 + ['--output', str(cases[0])]], [], root, args.timeout)
        record['stages']['v2-concurrent'] = run_stage('v2-concurrent', [v2 + ['--output', str(p)] for p in cases[1:]], [p/'predictions.jsonl' for p in cases[1:]], root, args.timeout)
        record['v2_overlap'] = overlap(record['stages']['v2-concurrent']['progress'], 2)
        for case in cases:
            entry = load_episode(case, inputs)
            if entry['mode'] != 'greedy' or entry['map_seed'] != args.map_seed or entry['summary']['decisions'] != 512:
                raise ValueError('V2 full greedy development case differs')
            (root / (case.name+'-prediction-semantics.jsonl')).write_bytes(v2_prediction_bytes(case, inputs))
        for left, right in ((cases[0], cases[1]), (cases[0], cases[2]), (cases[1], cases[2])):
            for name in ('worker/transitions.jsonl', 'summary.json'):
                record['comparisons'].append(compare_bytes(f'V2 {left.name}/{right.name} {name}', left/name, right/name, inputs))
            record['comparisons'].append(compare_bytes(f'V2 {left.name}/{right.name} complete prediction semantics', root/(left.name+'-prediction-semantics.jsonl'), root/(right.name+'-prediction-semantics.jsonl'), inputs))
        inputs.unchanged()
        record['status'] = 'passed' if all(c['equal'] for c in record['comparisons']) else 'failed'
        return 0 if record['status'] == 'passed' else 1
    except BaseException as exc:
        record.update(status='failed', error=str(exc))
        raise
    finally:
        record.update(input_sha256=inputs.sha256, disk_after=shutil.disk_usage(root)._asdict())
        write_json(root / 'verification.json', record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('v1-engine', 'v1-evaluator', 'v1-instance-dir', 'v1-package', 'v2-engine', 'v2-policy', 'v2-training-run', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--device', choices=('cpu', 'cuda:0'), required=True)
    parser.add_argument('--map-seed', type=int, required=True)
    parser.add_argument('--seed', type=positive, default=20260925)
    parser.add_argument('--timeout', type=positive, default=1800, help='Bound for each complete stage in seconds')
    try:
        return run(parser.parse_args())
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print('Concurrent determinism failed: '+str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
