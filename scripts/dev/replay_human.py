#!/usr/bin/env python3
"""Validate a recorded native command prefix and export exact supported labels.

Only successful stock `cmd` entries are submitted. Failed/estimate entries are
preserved as exclusions, never silently treated as successful decisions or WAIT.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import subprocess

from local import capture_source, source_identity, write_json

COMMAND = re.compile(r'^\[[^]]+\] (cmdf?): ([0-9a-f]+); ([0-9a-f]+); ([0-9a-f]+); ([0-9a-f]+); ([0-9a-f]+); ([0-9a-f]+) \(([^)]+)\)$', re.I)
SAVE = re.compile(r'^\[[^]]+\] save: ([0-9a-f]+); ([0-9a-f]+); (.+)$', re.I)
RECORD_PREFIX = re.compile(r'^\[[^]]+\] (?:cmdf?|save):', re.I)
WORLD_CHANGE = re.compile(r'^\[[^]]+\] (load|new_map):', re.I)
LOAD = re.compile(r'^\[[^]]+\] load: (.+)$', re.I)
OBSERVATION_SCHEMAS = {
    'finance-v1': 'v2-m15-public-development-finance-v1',
    'orders-v1': 'v2-m15-public-development-orders-v1',
}
ORDER_OPERATIONS = {1: 'insert-order', 2: 'set-load', 3: 'copy-orders', 4: 'delete-order'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checkpoint_basename(checkpoint):
    if not checkpoint or checkpoint in ('.', '..') or any(c in checkpoint for c in '/\\:'):
        raise ValueError('Checkpoint must be a basename, without directories or a drive')
    return checkpoint


def find_checkpoint(recording, checkpoint):
    """Resolve one preserved manual save or autosave without guessing its path."""
    checkpoint_basename(checkpoint)
    matches = [path for folder in ('save', 'save/autosave')
               if (path := recording / folder / checkpoint).is_file()]
    if not matches:
        raise ValueError('Checkpoint not present in preserved recording')
    if len(matches) != 1:
        raise ValueError('Checkpoint basename is ambiguous between save and save/autosave')
    return matches[0]


def mapping(name, payload, observation_mode='finance-v1'):
    if observation_mode not in OBSERVATION_SCHEMAS:
        raise ValueError('Unsupported replay observation mode')
    data = bytes.fromhex(payload)
    tile = int.from_bytes(data[:4], 'little')
    if name == 'CmdBuildRoadDepot' and len(data) == 6 and data[4] == 0:
        return {'family': 'BUILD_ROAD_DEPOT', 'parameters': {'1': tile, '2': data[5]}}
    if name == 'CmdBuildVehicle' and len(data) == 12 and int.from_bytes(data[4:6], 'little') == 116 and data[6] == 1 and data[7] in (0, 255):
        return {'family': 'BUY_BUS', 'parameters': {'1': tile, '2': 116}}
    if name == 'CmdStartStopVehicle' and len(data) == 5 and data[4] == 0:
        # These recorded actions all start stopped vehicles. Native legal
        # enumeration rejects the mapping if the vehicle is already running.
        return {'family': 'START_VEHICLE', 'parameters': {'1': tile}}
    if name in ('CmdDecreaseLoan', 'CmdIncreaseLoan') and len(data) == 9 and data[0] == 0:
        return {'family': 'MANAGE_LOAN', 'parameters': {'1': 2 if name == 'CmdDecreaseLoan' else 1, '2': 10000}}
    if observation_mode == 'orders-v1':
        # Pinned 15.3 order serialization is type, flags, uint16 destination,
        # refit cargo, uint16 wait, uint16 travel, uint16 maximum speed. The
        # primitive interface accepts ordinary bus station orders only. Never
        # erase non-stop, load/unload, refit, timetable or speed semantics to
        # manufacture an apparently equivalent station insertion.
        if (name == 'CmdInsertOrder' and len(data) == 16 and data[5] in (0x21, 0x61)
                and data[6] == 0 and data[9:] == bytes.fromhex('fe00000000ffff')):
            descriptor = 1 | data[4] << 8 | data[5] << 16 | data[6] << 24
            return {'family': 'SET_ROUTE', 'parameters': {
                '1': tile, '2': descriptor, '3': int.from_bytes(data[7:9], 'little')}}
        if name == 'CmdModifyOrder' and len(data) == 8 and data[5] == 3:
            load = int.from_bytes(data[6:8], 'little')
            if load in (0, 2, 3, 4):
                return {'family': 'SET_ROUTE', 'parameters': {
                    '1': tile, '2': 2 | data[4] << 8 | 3 << 16, '3': load}}
        # CO_COPY (1) makes independent orders. CO_SHARE/CO_UNSHARE are not
        # aliases for it, even if the station sequences happen to be equal.
        if name == 'CmdCloneOrder' and len(data) == 9 and data[0] == 1:
            return {'family': 'SET_ROUTE', 'parameters': {
                '1': int.from_bytes(data[1:5], 'little'), '2': 3,
                '3': int.from_bytes(data[5:9], 'little')}}
        if name == 'CmdDeleteOrder' and len(data) == 5:
            return {'family': 'SET_ROUTE', 'parameters': {
                '1': tile, '2': 4 | data[4] << 8, '3': 0}}
    return None


def operation(action):
    if action['family'] == 'SET_ROUTE':
        opcode = action['parameters']['2'] & 255
        if opcode == 2 and action['parameters']['3'] == 3:
            return 'full-load-any'
        return ORDER_OPERATIONS[opcode]
    return action['family'].lower().replace('_', '-')


def validate_samples(samples, commands, events, observation_mode='finance-v1'):
    """Cross-check exact labels against their recorded command and native rows.

    This runs only after checkpoint equality. Failed candidate tests, unmatched
    client order backups, and unsupported variants cannot acquire a label here.
    """
    commands_by_line = {command['source_command_index']: command for command in commands}
    events_by_line = {event['line']: event for event in events if event['kind'] == 'cmd'}
    if len(commands_by_line) != len(commands):
        raise ValueError('Duplicate native replay command identity')
    seen = set()
    operations = Counter()
    for sample in samples:
        line = sample['source_command_index']
        if line in seen:
            raise ValueError('Duplicate human label for one command')
        seen.add(line)
        event, command = events_by_line[line], commands_by_line[line]
        if ('mapping' not in event or command['supported_policy_label'] is not True
                or command['succeeded'] is not True or command['command_cost'] != sample['command_cost']):
            raise ValueError('Human label lacks an exact successful native command mapping')
        if observation_mode == 'orders-v1':
            if sample.get('source_command') != event or sample.get('operation') != operation(event['mapping']):
                raise ValueError('Primitive order label source-command provenance differs')
            if not Path(sample.get('after_observation_path', '')).is_file():
                raise ValueError('Primitive order label lacks its confirmed post-command observation')
        observation_metadata = json.loads(Path(sample['observation_metadata_path']).read_text())
        if observation_metadata['observation_schema_id'] != OBSERVATION_SCHEMAS[observation_mode]:
            raise ValueError('Replay engine observation schema differs from requested mode')
        metadata = json.loads(Path(sample['candidate_metadata_path']).read_text())
        matches = [row for row in metadata['records'] if row['row'] == sample['action_row']]
        if len(matches) != 1:
            raise ValueError('Human label candidate row is absent or ambiguous')
        candidate = matches[0]
        family = next(family for family in metadata['families'] if family['family_index'] == candidate['family_index'])
        if (family['name'] != event['mapping']['family'] or candidate['family_index'] != sample['action_family']
                or candidate['stable_key'] != sample['candidate_key'] or sample['action_row'] not in sample['legal_rows']
                or candidate['cost'] != sample['command_cost']
                or any(candidate['parameters'][int(key)] != value for key, value in event['mapping']['parameters'].items())):
            raise ValueError('Human label differs from the exact legal native candidate')
        if sample['action_family'] == 11 and abs(command['after_loan'] - command['before_loan']) != 10000:
            raise ValueError('Loan example differs from supported 10000 principal action')
        operations[operation(event['mapping'])] += 1
    if seen != {line for line, command in commands_by_line.items() if command['supported_policy_label']}:
        raise ValueError('Native supported label inventory differs from exported samples')
    return dict(operations)


def build_events(log, checkpoint, checkpoint_occurrence='unique', observation_mode='finance-v1'):
    checkpoint_basename(checkpoint)
    if checkpoint_occurrence not in ('unique', 'latest'):
        raise ValueError('Checkpoint occurrence must be unique or latest')
    lines = log.read_text(encoding='utf-8-sig').splitlines()
    # A later save may overwrite the selected file even when its earlier marker
    # ends our replay prefix. Inspect every marker before choosing that prefix.
    saves = {line: save for line, raw in enumerate(lines, 1) if (save := SAVE.fullmatch(raw))}
    saved_names = Counter(save.group(3).replace('\\', '/').rsplit('/', 1)[-1] for save in saves.values())
    checkpoint_lines = [line for line, save in saves.items()
                        if save.group(3).replace('\\', '/').rsplit('/', 1)[-1] == checkpoint]
    if saved_names[checkpoint] > 1 and checkpoint_occurrence == 'unique':
        raise ValueError('Duplicate checkpoint save markers; preserved checkpoint may have been overwritten')
    if saved_names['initial.sav'] > 1:
        raise ValueError('Duplicate initial save markers; preserved initial state may have been overwritten')
    selected_line = checkpoint_lines[-1] if checkpoint_lines else None
    events, exclusions = [], []
    initial_seen = False
    initial_line = None
    for line, raw in enumerate(lines, 1):
        save = SAVE.fullmatch(raw)
        if save:
            date, fraction, filename = save.groups()
            filename = filename.replace('\\', '/').rsplit('/', 1)[-1]
            if filename == 'initial.sav':
                if initial_seen:
                    raise ValueError(f'Duplicate initial save marker at line {line}')
                initial_seen = True
                initial_line = line
            if filename == checkpoint:
                if not initial_seen:
                    raise ValueError(f'Checkpoint precedes initial save marker at line {line}')
                if line == selected_line:
                    events.append({'kind': 'checkpoint', 'line': line, 'date': int(date, 16), 'fraction': int(fraction, 16)})
                    return events, exclusions
            continue
        world_change = WORLD_CHANGE.match(raw)
        if world_change and initial_seen:
            if world_change.group(1).lower() == 'load':
                load = LOAD.fullmatch(raw)
                # Stock OpenTTD emits load for save-dialog preview as well as
                # actual loading. Explicit latest selection may defer this one
                # ambiguity to mandatory native equality, only when the same
                # file is saved on the very next log line with no intervening
                # commands. Never traverse earlier or unrelated load markers.
                if checkpoint_occurrence == 'latest' and load and selected_line == line + 1:
                    loaded_path = posixpath.normpath(load.group(1).replace('\\', '/'))
                    saved_path = posixpath.normpath(saves[selected_line].group(3).replace('\\', '/'))
                    if loaded_path == saved_path and loaded_path.rsplit('/', 1)[-1] == checkpoint:
                        exclusions.append({'line': line, 'name': 'load',
                            'reason': 'ambiguous-load-or-save-preview-ignored-pending-native-checkpoint-equality',
                            'checkpoint_line': selected_line})
                        continue
                raise ValueError(f'Load or save-preview marker makes replay prefix ambiguous at line {line}')
            # Stock startup logs the initial save immediately before new_map.
            if line != initial_line + 1:
                raise ValueError(f'New map after initial save makes replay prefix ambiguous at line {line}')
        command = COMMAND.fullmatch(raw)
        if not command and RECORD_PREFIX.match(raw):
            raise ValueError(f'Malformed native replay record at line {line}')
        if not command or not initial_seen:
            continue
        kind, date, fraction, company, command_id, message, payload, name = command.groups()
        if kind == 'cmdf':
            exclusions.append({'line': line, 'name': name, 'reason': 'failed-test-or-estimate-no-confirmed-execution'})
            continue
        entry = {'kind': kind, 'date': int(date, 16), 'fraction': int(fraction, 16), 'company': int(company, 16),
                 'command': int(command_id, 16), 'message': int(message, 16), 'payload': payload, 'name': name, 'line': line}
        action = mapping(name, payload, observation_mode)
        if action:
            entry['mapping'] = action
            entry['operation'] = operation(action)
        else:
            exclusions.append({'line': line, 'name': name, 'reason': 'replayed-native-command-not-exact-v2-policy-action'})
        events.append(entry)
    raise ValueError('Requested checkpoint save is absent from command log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recording', type=Path, required=True)
    parser.add_argument('--openttd', type=Path, required=True)
    parser.add_argument('--checkpoint', default='Cartborough Transport, 1950-03-18.sav')
    parser.add_argument('--checkpoint-occurrence', choices=('unique', 'latest'), default='unique',
                        help='Require a unique save marker (default), or explicitly replay through the latest marker; native equality remains mandatory')
    parser.add_argument('--observation-mode', choices=tuple(OBSERVATION_SCHEMAS), default='finance-v1',
                        help='Opt into exact primitive bus orders; historical finance replay semantics remain available')
    parser.add_argument('--export-before-lines', type=int, nargs='*', default=[],
                        help='Preserve isolated saves immediately before these confirmed command lines for live exercises')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    recording, engine, output = args.recording.resolve(), args.openttd.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    log = recording / 'save/autosave/commands-out.log'
    checkpoint = find_checkpoint(recording, args.checkpoint)
    initial = recording / 'save/initial.sav'
    transfer_path = recording / 'transfer.json'
    transfer = json.loads(transfer_path.read_text(encoding='utf-8-sig')) if transfer_path.exists() else None
    if transfer:
        for item in transfer['files']:
            if digest(recording / item['file'].replace('\\', '/')) != item['sha256']:
                raise ValueError('Recording transfer provenance no longer matches')
    events, exclusions = build_events(log, args.checkpoint, args.checkpoint_occurrence, args.observation_mode)
    if (len(set(args.export_before_lines)) != len(args.export_before_lines)
            or not set(args.export_before_lines) <= {event['line'] for event in events if event['kind'] == 'cmd'}):
        raise ValueError('Each requested pre-command save must identify a unique replayed command')
    config = {'initial_save': str(initial), 'checkpoint_save': str(checkpoint), 'events': events,
              'output': str(output), 'observation_mode': args.observation_mode,
              'export_before_lines': args.export_before_lines,
              'game_id': (transfer['source_recording'].replace('\\', '/').rsplit('/', 1)[-1] if transfer else recording.name)}
    write_json(output / 'config.json', config)
    # Native config parser requires canonical JSON.
    (output / 'config.json').write_text(json.dumps(config, sort_keys=True, separators=(',', ':')) + '\n')
    record = {'schema_version': 'openttd-rl-development-human-replay-validation-1', 'status': 'running',
        'source': source_identity(), 'source_recording': {'path': transfer['source_recording'] if transfer else str(recording),
            'runtime_copy': str(recording), 'sha256': digest(log)},
        'inputs': {str(p): digest(p) for p in [initial, checkpoint, log]},
        'engine': {'path': str(engine), 'sha256': digest(engine)}, 'checkpoint': args.checkpoint,
        'checkpoint_occurrence': args.checkpoint_occurrence,
        'checkpoint_log_line': events[-1]['line'], 'observation_mode': args.observation_mode,
        'observation_schema_id': OBSERVATION_SCHEMAS[args.observation_mode],
        'exclusions': exclusions, 'cpu_only': True, 'seeds': 'restored-from-initial-save'}
    write_json(output / 'report.json', record)
    capture_source(output / 'source-provenance')
    (output / 'openttd.cfg').write_text('\n')
    command = [str(engine), '-x', '-X', '-Q', '-I', 'OpenGFX', '-v', 'null', '-s', 'null', '-m', 'null', '-c', str(output / 'openttd.cfg')]
    record['command'] = command
    environment = os.environ.copy()
    environment['OPENTTD_RL_HUMAN_REPLAY'] = str(output / 'config.json')
    try:
        with (output / 'engine.log').open('w') as stream:
            subprocess.run(command, env=environment, cwd=output, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=600)
        replayed = json.loads((output / 'replayed.json').read_text())
        saved = json.loads((output / 'checkpoint.json').read_text())
        checks = {'roads': replayed['map']['roads'] == saved['map']['roads'],
            'orders': replayed['exact_orders'] == saved['exact_orders'],
            'cash': replayed['economy']['balance'] == saved['economy']['balance'],
            'debt': replayed['economy']['loan'] == saved['economy']['loan'],
            'date': (replayed['date'], replayed['date_fraction']) == (saved['date'], saved['date_fraction']),
            'tick': replayed['tick'] == saved['tick'],
            'finance': replayed['economy']['finance'] == saved['economy']['finance'],
            'vehicles': replayed['vehicles'] == saved['vehicles'], 'stations': replayed['stations'] == saved['stations'],
            'depots': replayed['depots'] == saved['depots']}
        commands = [json.loads(x) for x in (output / 'commands.jsonl').read_text().splitlines()]
        mapped_lines = {event['line'] for event in events if 'mapping' in event}
        record['exclusions'].extend({'line': c['source_command_index'], 'name': c['name'], 'reason': 'mapping-not-present-in-native-legal-candidates-or-client-order-backup'}
            for c in commands if c['source_command_index'] in mapped_lines and not c['supported_policy_label'])
        checks['command_cost_accounting'] = all(c['succeeded'] and c['after_cash'] - c['before_cash'] == c['after_loan'] - c['before_loan'] - c['command_cost'] for c in commands)
        record.update(status='passed' if all(checks.values()) else 'failed', checks=checks,
            command_count=len(commands), cash={'replayed': replayed['economy']['balance'], 'saved': saved['economy']['balance']},
            debt={'replayed': replayed['economy']['loan'], 'saved': saved['economy']['loan']},
            total_command_cost=sum(c['command_cost'] for c in commands),
            supported_policy_labels=sum(c['supported_policy_label'] for c in commands),
            claimed_equivalence='roads, complete serialized orders, cash, debt, date, tick, public finance/vehicles/stations/depots; replay-executed command costs reconciled with exact immediate cash/principal accounting; original command log contains no independent per-command cost values')
        write_json(output / 'report.json', record)
        if record['status'] != 'passed':
            raise ValueError('Native replay differs from saved checkpoint; labels withheld')
        samples = json.loads((output / 'samples.json').read_text())
        operations = validate_samples(samples, commands, events, args.observation_mode)
        record.update(supported_operations=operations, excluded_count=len(record['exclusions']),
                      excluded_reasons=dict(Counter(item['reason'] for item in record['exclusions'])))
        write_json(output / 'report.json', record)
        dataset = {'schema_version': 'openttd-rl-development-human-imitation-dataset-1', 'source_kind': 'human',
            'replay_validation': {'status': 'passed', 'path': str(output / 'report.json'), 'sha256': digest(output / 'report.json')},
            'source_recording': record['source_recording'], 'observation_schema_id': OBSERVATION_SCHEMAS[args.observation_mode],
            'observation_mode': args.observation_mode, 'records': samples}
        if args.observation_mode == 'orders-v1':
            dataset.update(action_semantics='orders-v1', financial_features='signed-log-orders-v1')
        write_json(output / 'dataset.json', dataset)
        print(json.dumps({'status': record['status'], 'samples': len(samples), 'families': Counter(s['action_family'] for s in samples), 'output': str(output)}))
    except BaseException as error:
        record.update(status='failed', error=repr(error)); write_json(output / 'report.json', record); raise


if __name__ == '__main__':
    main()
