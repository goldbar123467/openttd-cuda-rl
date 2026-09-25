#!/usr/bin/env python3
"""Qualify V1 stage timing, then run four counterbalanced full-episode pairs.

The fixed workload is sampled MLP play on both development maps at seed 20260925,
with one process worker and the recorded fast bridge. This measures optional
instrumentation, not a policy improvement or a pipeline optimization.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import sys

from local import ROOT, capture_source, host, source_identity, write_json
from check_concurrent_determinism import checked_v1, compare_bytes, run_stage
from studies.evidence_v2 import Inputs
from verify_device_agreement import package_hashes


def timing_summary(path, inputs):
    rows = [json.loads(line) for line in inputs.read(path).splitlines()]
    stages = defaultdict(list)
    previous_end = 0
    for index, row in enumerate(rows, 1):
        if (row['schema'] != 'development-stage-wall-timing-v1' or row['sequence'] != index or
                row['clock'] != 'perf_counter_ns' or row['status'] != 'completed' or
                type(row['elapsed_ns']) is not int or row['elapsed_ns'] < 0 or
                row['start_ns'] < previous_end):
            raise ValueError('Invalid, overlapping or failed timing record')
        previous_end = row['start_ns'] + row['elapsed_ns']
        stages[row['stage']].append(row['elapsed_ns'])
    per_step = ('legal_mask', 'policy_inputs', 'policy_request', 'trace_inputs', 'game_step',
                'observe', 'trace_assemble', 'trace_serialize', 'trace_write', 'trace_flush')
    for name in per_step:
        steps = [r['context'].get('step') for r in rows if r['stage'] == name]
        if steps != list(range(1, 513)):
            raise ValueError('Incomplete timing stage: '+name)
    if [r['context'].get('step') for r in rows if r['stage'] == 'legal_actions_request'] != list(range(1, 512)):
        raise ValueError('Incomplete legal-action timings')
    startup = ('environment_start', 'initial_snapshot', 'initial_write', 'package_before',
               'policy_start', 'environment_close', 'policy_close', 'package_after')
    if any(len(stages[n]) != 1 for n in startup) or set(stages) != set((*per_step, *startup, 'legal_actions_request')):
        raise ValueError('Timing inventory differs')
    return {name: {'calls': len(values), 'total_seconds': sum(values)/1e9,
                   'median_call_ms': statistics.median(values)/1e6,
                   'min_call_ms': min(values)/1e6, 'max_call_ms': max(values)/1e6}
            for name, values in sorted(stages.items())}


def spread(values):
    return {'values': values, 'median': statistics.median(values), 'min': min(values), 'max': max(values)}


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    inputs = Inputs()
    record = {'kind': 'v1-stage-timing-qualification-and-four-pairs-v1', 'status': 'running',
              'source': source_identity(), 'source_archive': capture_source(root/'source'), 'host': host(),
              'command': sys.argv, 'disk_before': shutil.disk_usage(root)._asdict(),
              'settings': {'seed': 20260925, 'policy': 'sampled', 'workers': 1, 'executor': 'process',
                           'bridge_validation': 'fast', 'decisions_per_game': 512,
                           'templates': ['m02-template-05', 'm02-template-06'],
                           'pair_orders': [['off','on'], ['on','off'], ['on','off'], ['off','on']]},
              'runs': {}, 'comparisons': [], 'final_evaluation_accessed': False,
              'claim': 'Stage wall-time breakdown and timing overhead on a finite V1 workload; no optimization speedup claim'}
    try:
        if record['disk_before']['free'] < 10*1024**3:
            raise ValueError('At least 10 GiB free is required')
        engine_sha = hashlib.sha256(inputs.read(args.engine.resolve())).hexdigest()
        evaluator_sha = hashlib.sha256(inputs.read(args.evaluator.resolve())).hexdigest()
        package_sha, _ = package_hashes(args.package.resolve())
        for name in package_sha:
            inputs.read(args.package.resolve()/name)
        for template in record['settings']['templates']:
            inputs.read(args.instance_dir.resolve()/(template+'.json'))
        reference = inputs.json(args.reference.resolve()/'run.json')
        if (reference['engine_sha256'] != engine_sha or reference['evaluator_sha256'] != evaluator_sha or
                reference['package_hashes'] != package_sha):
            raise ValueError('Retained reference engine/evaluator/package differs')
        record['binaries'] = {'engine_sha256': engine_sha, 'evaluator_sha256': evaluator_sha}
        record['package_hashes'] = package_sha
        base = [sys.executable, str(ROOT/'scripts/dev/evaluate_live.py'), '--openttd', str(args.engine.resolve()),
                '--instance-dir', str(args.instance_dir.resolve()), '--evaluator', str(args.evaluator.resolve()),
                '--package', str(args.package.resolve()), '--backend', 'native', '--split', 'development',
                '--templates', *record['settings']['templates'], '--policies', 'sampled', '--seeds', '20260925',
                '--workers', '1', '--executor', 'process', '--bridge-validation', 'fast',
                '--hypothesis', 'Fixed-workload stage timing; no recipe selection or optimization claim']
        def execute(name, timed):
            command = base + ['--output', str(root/name)] + (['--stage-timing'] if timed else [])
            stage = run_stage(name, [command], [], root, 1800)
            d = inputs.json(root/name/'run.json')
            if (d['source'] != record['source'] or d['stage_timing'] is not timed or
                    d['engine_sha256'] != engine_sha or d['evaluator_sha256'] != evaluator_sha or
                    d['package_hashes'] != package_sha):
                raise ValueError('Evaluation source or timing option differs')
            episodes = {}
            for template in record['settings']['templates']:
                ep, summary = checked_v1(root/name, 'sampled', template, 20260925, inputs)
                native = inputs.json(ep/'episode.json')
                episodes[template] = {'summary': summary, 'elapsed_seconds': native['elapsed_seconds']}
                if timed:
                    breakdown = timing_summary(ep/'timing.jsonl', inputs)
                    total = sum(s['total_seconds'] for s in breakdown.values())
                    if total > native['elapsed_seconds']+.001:
                        raise ValueError('Stage times exceed episode wall time')
                    episodes[template].update(stages=breakdown, unmeasured_seconds=native['elapsed_seconds']-total)
                elif (ep/'timing.jsonl').exists():
                    raise ValueError('Disabled timing unexpectedly created a file')
            record['runs'][name] = {'stage_timing': timed, 'episodes': episodes,
                'command_seconds': (stage['finished_monotonic_ns']-stage['started_monotonic_ns'])/1e9}
            write_json(root/'profile.json', record)
        def compare(left, right):
            for template in record['settings']['templates']:
                a, sa = checked_v1(left, 'sampled', template, 20260925, inputs)
                b, sb = checked_v1(right, 'sampled', template, 20260925, inputs)
                result = compare_bytes(left.name+'/'+right.name+'/'+template, a/'actions.jsonl', b/'actions.jsonl', inputs)
                result['summary_equal_except_elapsed'] = sa == sb
                record['comparisons'].append(result)
                if not result['equal'] or sa != sb:
                    raise ValueError('Timing changed canonical actions or episode semantics')
        write_json(root/'profile.json', record)
        execute('qualification-off', False)
        compare(args.reference.resolve(), root/'qualification-off')
        execute('qualification-on', True)
        compare(root/'qualification-off', root/'qualification-on')
        record['qualification_passed_before_timing_pairs'] = True
        write_json(root/'profile.json', record)
        for pair, order in enumerate(record['settings']['pair_orders'], 1):
            for mode in order:
                execute(f'pair-{pair}-{mode}', mode=='on')
            compare(root/f'pair-{pair}-off', root/f'pair-{pair}-on')
        record['timing'] = {}
        for template in record['settings']['templates']:
            on = [record['runs'][f'pair-{p}-on']['episodes'][template] for p in range(1,5)]
            off = [record['runs'][f'pair-{p}-off']['episodes'][template] for p in range(1,5)]
            record['timing'][template] = {'episode_seconds': {
                'off': spread([r['elapsed_seconds'] for r in off]), 'on': spread([r['elapsed_seconds'] for r in on]),
                'paired_on_minus_off': spread([a['elapsed_seconds']-b['elapsed_seconds'] for a,b in zip(on,off)])},
                'stage_seconds': {name: spread([r['stages'][name]['total_seconds'] for r in on]) for name in on[0]['stages']},
                'unmeasured_seconds': spread([r['unmeasured_seconds'] for r in on])}
        record['command_seconds'] = {mode: spread([record['runs'][f'pair-{p}-{mode}']['command_seconds'] for p in range(1,5)]) for mode in ['off','on']}
        inputs.unchanged()
        if source_identity() != record['source']:
            raise ValueError('Source changed during profiling')
        record['status'] = 'passed'
    except BaseException as exc:
        record.update(status='failed', error=str(exc))
        raise
    finally:
        record.update(input_sha256=inputs.sha256, disk_after=shutil.disk_usage(root)._asdict())
        write_json(root/'profile.json', record)
    print('V1 timing qualification and four counterbalanced pairs passed', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['engine','instance-dir','evaluator','package','reference','output']:
        parser.add_argument('--'+name, type=Path, required=True)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
