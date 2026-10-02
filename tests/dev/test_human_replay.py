"""Recording extraction excludes unconfirmed and semantically different actions."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/dev'))
import replay_human


class HumanReplayTests(unittest.TestCase):
    def test_recorded_bus_orders_map_to_exact_primitive_parameters(self):
        cases = [
            ('CmdInsertOrder', '010000000061000100FE00000000FFFF', {'1': 1, '2': 1 | 0x61 << 16, '3': 1}, 'insert-order'),
            ('CmdInsertOrder', '010000000161000000FE00000000FFFF', {'1': 1, '2': 1 | 1 << 8 | 0x61 << 16, '3': 0}, 'insert-order'),
            ('CmdModifyOrder', '0100000000030300', {'1': 1, '2': 2 | 3 << 16, '3': 3}, 'full-load-any'),
            ('CmdModifyOrder', '0100000001030300', {'1': 1, '2': 2 | 1 << 8 | 3 << 16, '3': 3}, 'full-load-any'),
            ('CmdCloneOrder', '010200000001000000', {'1': 2, '2': 3, '3': 1}, 'copy-orders'),
            ('CmdDeleteOrder', '0200000001', {'1': 2, '2': 4 | 1 << 8, '3': 0}, 'delete-order'),
            ('CmdInsertOrder', '020000000161000200FE00000000FFFF', {'1': 2, '2': 1 | 1 << 8 | 0x61 << 16, '3': 2}, 'insert-order'),
            ('CmdModifyOrder', '0200000001030300', {'1': 2, '2': 2 | 1 << 8 | 3 << 16, '3': 3}, 'full-load-any'),
        ]
        for name, payload, parameters, operation in cases:
            with self.subTest(name=name, payload=payload):
                action = replay_human.mapping(name, payload, 'orders-v1')
                self.assertEqual(action, {'family': 'SET_ROUTE', 'parameters': parameters})
                self.assertEqual(replay_human.operation(action), operation)
                self.assertIsNone(replay_human.mapping(name, payload))

    def test_insert_flags_and_other_loading_modes_do_not_collapse(self):
        nonstop = replay_human.mapping('CmdInsertOrder', '010000000061000100FE00000000FFFF', 'orders-v1')
        ordinary = replay_human.mapping('CmdInsertOrder', '010000000021000100FE00000000FFFF', 'orders-v1')
        self.assertNotEqual(nonstop['parameters'], ordinary['parameters'])
        loads = [replay_human.mapping('CmdModifyOrder', f'010000000003{value:02x}00', 'orders-v1') for value in (0, 2, 3, 4)]
        self.assertEqual([action['parameters']['3'] for action in loads], [0, 2, 3, 4])
        self.assertEqual([replay_human.operation(action) for action in loads], ['set-load', 'set-load', 'full-load-any', 'set-load'])

    def test_unsupported_order_variants_remain_excluded(self):
        insertion = bytes.fromhex('010000000061000100FE00000000FFFF')
        mutations = {5: 0xE1, 6: 0x30, 9: 0, 10: 1, 12: 1, 14: 1}
        for index, value in mutations.items():
            data = bytearray(insertion); data[index] = value
            with self.subTest(index=index):
                self.assertIsNone(replay_human.mapping('CmdInsertOrder', data.hex(), 'orders-v1'))
        for name, payload in (
                ('CmdInsertOrder', insertion[:-1].hex()),
                ('CmdInsertOrder', (insertion + b'\0').hex()),
                ('CmdCloneOrder', '000200000001000000'),
                ('CmdCloneOrder', '020200000001000000'),
                ('CmdModifyOrder', '0100000000020300'),
                ('CmdModifyOrder', '0100000000030100'),
                ('CmdModifyOrder', '0100000000030301'),
                ('CmdDeleteOrder', '020000000100')):
            with self.subTest(name=name, payload=payload):
                self.assertIsNone(replay_human.mapping(name, payload, 'orders-v1'))

    def test_native_label_requires_matching_candidate_cost_parameters_and_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            meta_path, observation_path = root / 'candidate.json', root / 'observation.json'
            observation_path.write_text(json.dumps({'observation_schema_id': replay_human.OBSERVATION_SCHEMAS['orders-v1']}))
            action = replay_human.mapping('CmdModifyOrder', '0100000000030300', 'orders-v1')
            event = {'line': 23, 'kind': 'cmd', 'mapping': action}
            command = {'source_command_index': 23, 'supported_policy_label': True, 'succeeded': True, 'command_cost': 0}
            candidate = {'row': 2817, 'family_index': 6, 'stable_key': 'exact', 'cost': 0,
                         'parameters': [6, 1, 2 | 3 << 16, 3] + [0] * 12}
            metadata = {'records': [candidate], 'families': [{'family_index': 6, 'name': 'SET_ROUTE'}]}
            sample = {'source_command_index': 23, 'command_cost': 0, 'candidate_metadata_path': str(meta_path),
                      'observation_metadata_path': str(observation_path), 'action_row': 2817,
                      'action_family': 6, 'candidate_key': 'exact', 'legal_rows': [2817],
                      'source_command': event, 'operation': 'full-load-any', 'after_observation_path': str(observation_path)}
            meta_path.write_text(json.dumps(metadata))
            self.assertEqual(replay_human.validate_samples([sample], [command], [event], 'orders-v1'), {'full-load-any': 1})
            for key, value in (('cost', 1), ('stable_key', 'other'), ('parameters', [6, 2, 2 | 3 << 16, 3] + [0] * 12)):
                altered = {**candidate, key: value}
                meta_path.write_text(json.dumps({**metadata, 'records': [altered]}))
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'exact legal'):
                    replay_human.validate_samples([sample], [command], [event], 'orders-v1')
            meta_path.write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, 'requested mode'):
                replay_human.validate_samples([sample], [command], [event], 'finance-v1')
            with self.assertRaisesRegex(ValueError, 'Duplicate human label'):
                replay_human.validate_samples([sample, sample], [command], [event], 'orders-v1')
            with self.assertRaisesRegex(ValueError, 'inventory differs'):
                replay_human.validate_samples([], [command], [event], 'orders-v1')
            with self.assertRaisesRegex(ValueError, 'provenance differs'):
                replay_human.validate_samples([{**sample, 'source_command': {}}], [command], [event], 'orders-v1')
            with self.assertRaisesRegex(ValueError, 'post-command observation'):
                replay_human.validate_samples([{**sample, 'after_observation_path': str(root / 'missing.json')}], [command], [event], 'orders-v1')

    def test_exact_supported_and_unsupported_decisions(self):
        self.assertEqual(replay_human.mapping('CmdBuildRoadDepot', '130700000002'),
                         {'family': 'BUILD_ROAD_DEPOT', 'parameters': {'1': 1811, '2': 2}})
        self.assertEqual(replay_human.mapping('CmdDecreaseLoan', '000000000000000000')['parameters'], {'1': 2, '2': 10000})
        self.assertIsNone(replay_human.mapping('CmdDecreaseLoan', '010000000000000000'))
        self.assertIsNone(replay_human.mapping('CmdCloneVehicle', '130700000100000000'))
        self.assertIsNone(replay_human.mapping('CmdBuildLongRoad', '9406000096060000000000000100'))
        self.assertEqual(replay_human.mapping('CmdBuildVehicle', '13070000740001FF01000000')['family'], 'BUY_BUS')

    def test_prefix_boundary_failures_and_setup(self):
        lines = ['[time] cmd: 00000001; 00; ff; 00000047; 00000000; 0001 (CmdPause)',
                 '[time] save: 00000001; 00; initial.sav',
                 '[time] cmdf: 00000002; 00; 00; 00000038; 00000000; 000000000000000000 (CmdDecreaseLoan)',
                 '[time] cmd: 00000002; 01; 00; 00000038; 00000000; 000000000000000000 (CmdDecreaseLoan)',
                 '[time] save: 00000002; 02; C:\\sandbox\\done.sav',
                 '[time] cmd: 00000003; 00; 00; 00000038; 00000000; 000000000000000000 (CmdDecreaseLoan)']
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'commands.log'
            log.write_text('\n'.join(lines))
            events, exclusions = replay_human.build_events(log, 'done.sav')
            self.assertEqual([e['line'] for e in events], [4, 5])
            self.assertEqual(exclusions[0]['line'], 3)
            with self.assertRaisesRegex(ValueError, 'absent'):
                replay_human.build_events(log, 'missing.sav')

    def test_damaged_or_ambiguous_recording_fails_closed(self):
        initial = '[time] save: 00000001; 00; initial.sav'
        checkpoint = '[time] save: 00000002; 02; done.sav'
        cases = [
            ([initial, '[time] cmd: truncated packet', checkpoint], 'Malformed'),
            ([initial, '[time] cmdf: truncated estimate', checkpoint], 'Malformed'),
            ([initial, '[time] save: broken marker', checkpoint], 'Malformed'),
            ([initial, initial, checkpoint], 'Duplicate initial'),
            ([checkpoint, initial], 'precedes initial'),
        ]
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'commands.log'
            for lines, error in cases:
                with self.subTest(lines=lines):
                    log.write_text('\n'.join(lines))
                    with self.assertRaisesRegex(ValueError, error):
                        replay_human.build_events(log, 'done.sav')

    def test_checkpoint_discovery_and_ambiguity(self):
        with tempfile.TemporaryDirectory() as directory:
            recording = Path(directory)
            autosave = recording / 'save/autosave'
            autosave.mkdir(parents=True)
            saved = autosave / '1954-autosave.sav'
            saved.write_bytes(b'preserved autosave')
            self.assertEqual(replay_human.find_checkpoint(recording, saved.name), saved)
            manual = recording / 'save/done.sav'
            manual.write_bytes(b'manual save')
            self.assertEqual(replay_human.find_checkpoint(recording, manual.name), manual)
            (recording / 'save' / saved.name).write_bytes(b'another checkpoint')
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                replay_human.find_checkpoint(recording, saved.name)
            with self.assertRaisesRegex(ValueError, 'not present'):
                replay_human.find_checkpoint(recording, 'missing.sav')
            for name in ('../done.sav', 'autosave/done.sav', r'autosave\done.sav',
                         '/done.sav', r'C:\done.sav', 'C:done.sav', '', '.', '..'):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'basename'):
                    replay_human.find_checkpoint(recording, name)

    def test_overwritten_checkpoint_or_initial_is_rejected_after_prefix(self):
        initial = '[time] save: 00000001; 00; initial.sav'
        checkpoint = '[time] save: 00000002; 02; done.sav'
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'commands.log'
            for later, error in (
                    ('[time] save: 00000003; 00; C:\\sandbox\\done.sav', 'Duplicate checkpoint'),
                    ('[time] save: 00000003; 00; initial.sav', 'Duplicate initial')):
                log.write_text('\n'.join([initial, checkpoint, later]))
                with self.subTest(later=later), self.assertRaisesRegex(ValueError, error):
                    replay_human.build_events(log, 'done.sav')

    def test_ambiguous_world_changes_and_safe_prefix(self):
        initial = '[time] save: 00000001; 00; initial.sav'
        new_map = '[time] new_map: 6ad71e53'
        command = '[time] cmd: 00000002; 01; 00; 00000038; 00000000; 000000000000000000 (CmdDecreaseLoan)'
        checkpoint = '[time] save: 00000002; 02; done.sav'
        load = '[time] load: C:\\sandbox\\done.sav'
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'commands.log'
            # Startup's new_map is valid, and later ambiguous activity cannot
            # invalidate an earlier uniquely saved prefix.
            log.write_text('\n'.join([initial, new_map, command, checkpoint, load, new_map]))
            events, exclusions = replay_human.build_events(log, 'done.sav')
            self.assertEqual([event['line'] for event in events], [3, 4])
            self.assertEqual(exclusions, [])
            for change, error in ((load, 'Load or save-preview'), (new_map, 'New map')):
                log.write_text('\n'.join([initial, new_map, command, change, checkpoint]))
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, error):
                    replay_human.build_events(log, 'done.sav')

    def test_explicit_latest_checkpoint_selects_last_marker(self):
        lines = ['[time] save: 00000001; 00; initial.sav',
                 '[time] save: 00000002; 00; C:\\sandbox\\done.sav',
                 '[time] cmd: 00000002; 01; 00; 00000038; 00000000; 000000000000000000 (CmdDecreaseLoan)',
                 '[time] save: 00000003; 02; C:\\sandbox\\done.sav']
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'commands.log'
            log.write_text('\n'.join(lines))
            with self.assertRaisesRegex(ValueError, 'Duplicate checkpoint'):
                replay_human.build_events(log, 'done.sav')
            events, exclusions = replay_human.build_events(log, 'done.sav', 'latest')
            self.assertEqual([event['line'] for event in events], [3, 4])
            self.assertEqual(events[-1]['date'], 3)
            self.assertEqual(exclusions, [])
            log.write_text('\n'.join(lines + [lines[0]]))
            with self.assertRaisesRegex(ValueError, 'Duplicate initial'):
                replay_human.build_events(log, 'done.sav', 'latest')

    def test_latest_allows_only_immediate_same_file_preview_pending_equality(self):
        initial = '[time] save: 00000001; 00; initial.sav'
        earlier = '[time] save: 00000002; 00; C:\\sandbox\\done.sav'
        load = '[time] load: C:\\sandbox\\done.sav'
        command = '[time] cmd: 00000002; 01; 00; 00000038; 00000000; 000000000000000000 (CmdDecreaseLoan)'
        checkpoint = '[time] save: 00000003; 02; C:/sandbox/done.sav'
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'commands.log'
            log.write_text('\n'.join([initial, earlier, command, load, checkpoint]))
            events, exclusions = replay_human.build_events(log, 'done.sav', 'latest')
            self.assertEqual([event['line'] for event in events], [3, 5])
            self.assertEqual(exclusions, [{'line': 4, 'name': 'load',
                'reason': 'ambiguous-load-or-save-preview-ignored-pending-native-checkpoint-equality',
                'checkpoint_line': 5}])
            cases = [
                [initial, earlier, load, command, checkpoint],
                [initial, earlier, '[time] load: C:/other/done.sav', checkpoint],
                [initial, earlier, '[time] load: C:/sandbox/other.sav', checkpoint],
                [initial, load, earlier, command, load, checkpoint],
            ]
            for lines in cases:
                log.write_text('\n'.join(lines))
                with self.subTest(lines=lines), self.assertRaisesRegex(ValueError, 'Load or save-preview'):
                    replay_human.build_events(log, 'done.sav', 'latest')
            log.write_text('\n'.join([initial, load, checkpoint]))
            with self.assertRaisesRegex(ValueError, 'Load or save-preview'):
                replay_human.build_events(log, 'done.sav')


if __name__ == '__main__':
    unittest.main()
