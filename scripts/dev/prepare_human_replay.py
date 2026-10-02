#!/usr/bin/env python3
"""Build an isolated command replay engine; never modify the input engine."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from local import ROOT, capture_source, source_identity, write_json


def source_hashes(source):
    return {str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(source.rglob('*')) if path.is_file() and '.git' not in path.relative_to(source).parts}


def replace(path, before, after):
    text = path.read_text()
    if text.count(before) != 1:
        raise ValueError(f"Replay insertion anchor differs in {path}: {before[:60]}")
    path.write_text(text.replace(before, after))


def refresh(base, root, jobs):
    """Refresh only this task's order helper and replay include, with an archive.

    Other base changes need a fresh preparation. The original preparation and
    its source/binary remain recoverable; final-build.json identifies the new
    executable without pretending it is the originally prepared version.
    """
    original = json.loads((root / 'preparation.json').read_text())
    if original.get('status') not in ('built', 'failed') or Path(original['base']).resolve() != base:
        raise ValueError('Refresh requires a completed preparation attempt with the same base')
    source = root / 'source'
    before_sources = source_hashes(source)
    binary = root / 'build/openttd'
    before_binary = hashlib.sha256(binary.read_bytes()).hexdigest() if binary.is_file() else None
    if original['status'] == 'built':
        if (before_sources != original['composed_source_hashes']
                or before_binary != original['executable_sha256']):
            raise ValueError('Prepared replay source or executable changed before refresh')
    elif (not (root / 'build/build.ninja').is_file() or not (root / 'build.log').is_file()
          or before_sources.get('src/rl_human_replay.inc') != original['repository_replay_include_sha256']):
        raise ValueError('Failed-build recovery requires configured source with its original replay include')
    base_hashes = source_hashes(base / 'source')
    changed = {name for name in set(base_hashes) | set(original['base_source_hashes'])
               if base_hashes.get(name) != original['base_source_hashes'].get(name)}
    if not changed <= {'src/rl_bus_orders.inc'}:
        raise ValueError('Base changes outside the bounded bus-order helper require a fresh replay preparation')
    base_binary = hashlib.sha256((base / 'build/openttd').read_bytes()).hexdigest()
    archive = root / 'pre-refresh'
    archive.mkdir(exist_ok=False)
    if before_binary is not None:
        shutil.copyfile(binary, archive / 'openttd')
    shutil.copyfile(root / 'preparation.json', archive / 'preparation.json')
    shutil.copyfile(root / 'build.log', archive / 'build.log')
    shutil.make_archive(str(archive / 'source'), 'gztar', root_dir=source)
    shutil.copytree(root / 'source-provenance', archive / 'source-provenance')
    record = {'kind': 'development-native-human-replay-refresh', 'status': 'preparing',
        'source': source_identity(), 'base': str(base), 'archive': str(archive),
        'previous_status': original['status'],
        'previous_executable_sha256': before_binary, 'previous_source_hashes': before_sources,
        'base_executable_sha256': base_binary, 'base_source_hashes': base_hashes,
        'changed_base_files': sorted(changed)}
    try:
        for name in changed:
            shutil.copyfile(base / 'source' / name, source / name)
        shutil.copyfile(ROOT / 'integration/dev/rl_human_replay.inc', source / 'src/rl_human_replay.inc')
        record['source_capture'] = capture_source(root / 'final-source-provenance')
        record['repository_replay_include_sha256'] = hashlib.sha256((source / 'src/rl_human_replay.inc').read_bytes()).hexdigest()
        command = ['cmake', '--build', str(root / 'build'), '--target', 'openttd', '--parallel', str(jobs)]
        record['command'] = command
        with (root / 'refresh-build.log').open('x') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=1800)
        record['base_unchanged'] = (source_hashes(base / 'source') == base_hashes and
            hashlib.sha256((base / 'build/openttd').read_bytes()).hexdigest() == base_binary)
        if not record['base_unchanged']:
            raise ValueError('Input engine changed during isolated replay refresh')
        (root / 'build/baseset').mkdir(exist_ok=True)
        shutil.copyfile(base / 'build/baseset/opengfx-8.0.tar', root / 'build/baseset/opengfx-8.0.tar')
        record.update(status='built', executable_sha256=hashlib.sha256((root / 'build/openttd').read_bytes()).hexdigest(),
                      composed_source_hashes=source_hashes(source))
    except BaseException as error:
        record.update(status='failed', error=repr(error)); raise
    finally:
        write_json(root / 'final-build.json', record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-engine-root', required=True, type=Path)
    parser.add_argument('--engine-root', required=True, type=Path)
    parser.add_argument('--jobs', default=4, type=int)
    parser.add_argument('--refresh', action='store_true',
                        help='Archive and refresh one prepared replay after a bounded bus-order helper/include change')
    args = parser.parse_args()
    base, root = args.base_engine_root.resolve(), args.engine_root.resolve()
    if root == base or root.is_relative_to(base):
        raise ValueError('Replay output must be outside input engine')
    if args.refresh:
        refresh(base, root, args.jobs)
        return
    root.mkdir(parents=True, exist_ok=False)
    source = root / 'source'
    base_hashes = source_hashes(base / 'source')
    base_binary = hashlib.sha256((base / 'build/openttd').read_bytes()).hexdigest()
    record = {'kind': 'development-native-human-replay', 'source': source_identity(), 'base': str(base), 'status': 'preparing',
        'base_executable_sha256': base_binary, 'base_source_hashes': base_hashes,
        'repository_replay_include_sha256': hashlib.sha256((ROOT / 'integration/dev/rl_human_replay.inc').read_bytes()).hexdigest()}
    write_json(root / 'preparation.json', record)
    try:
        # Copy only source tree; fresh build prevents stale CMake absolute paths.
        shutil.copytree(base / 'source', source)
        shutil.copyfile(ROOT / 'integration/dev/rl_human_replay.inc', source / 'src/rl_human_replay.inc')
        action = source / 'src/rl_v2_action.cpp'
        replace(action, '#include "rl_v2_live.inc"', '#include "rl_v2_live.inc"\n#include "rl_human_replay.inc"')
        replace(action, '#include "timer/timer_game_tick.h"', '#include "timer/timer_game_tick.h"\n#include "timer/timer_game_economy.h"\n#include "order_backup.h"\n#include "progress.h"')
        replace(source / 'src/openttd.cpp', 'if (!rl_v2_reset_manifest.empty()) {',
            'if (const char *replay_config = std::getenv("OPENTTD_RL_HUMAN_REPLAY")) {\n'
            '\t\t\textern void RunRlHumanReplay(const std::string &);\n'
            '\t\t\ttry { RunRlHumanReplay(replay_config); } catch (const std::exception &e) { UserError("Human replay: {}", e.what()); }\n'
            '\t\t\t_save_config = false; _exit_game = true;\n\t\t} else if (!rl_v2_reset_manifest.empty()) {')
        command = source / 'src/command.cpp'
        replace(command, 'void CommandHelperBase::InternalPostResult(CommandCost &res,',
            'CommandCost _rl_human_command_result;\nbool _rl_human_command_result_seen = false;\n\nvoid CommandHelperBase::InternalPostResult(CommandCost &res,')
        replace(command, '\n\tint x = TileX(tile) * TILE_SIZE;',
            '\n\t_rl_human_command_result = res;\n\t_rl_human_command_result_seen = true;\n\tint x = TileX(tile) * TILE_SIZE;')
        network = source / 'src/network/network_command.cpp'
        with network.open('a') as stream:
            stream.write('\nvoid RlHumanDispatch(Commands command, StringID message, CompanyID company, const CommandDataBuffer &data)\n'
                '{\n\tassert(IsValidCommand(command));\n\tCommandPacket cp; cp.cmd = command; cp.err_msg = message; cp.company = company; cp.data = data; cp.my_cmd = false;\n'
                '\t_current_company = company;\n\t_cmd_dispatch[command].Unpack[0](cp);\n}\n')
        # Replay retains backups just like upstream DEBUG_DUMP_COMMANDS; ordinary
        # live engine and user saves are untouched.
        replace(source / 'src/saveload/afterload.cpp', '#ifndef DEBUG_DUMP_COMMANDS', '#if !defined(DEBUG_DUMP_COMMANDS) && !defined(WITH_RL_ENVIRONMENT)')
        capture_source(root / 'source-provenance')
        configure = ['cmake', '-S', str(source), '-B', str(root / 'build'), '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
            '-DOPTION_RL_ENVIRONMENT=ON', '-DOPTION_RL_NEURAL_AGENT=OFF', '-DOPTION_USE_ASSERTS=ON', '-DOPTION_DEDICATED=ON',
            '-DPERSONAL_DIR=.openttd-rl-human-replay']
        if shutil.which('ccache'):
            configure += ['-DCMAKE_C_COMPILER_LAUNCHER=ccache', '-DCMAKE_CXX_COMPILER_LAUNCHER=ccache']
        for name, command in [('configure', configure), ('build', ['cmake', '--build', str(root / 'build'), '--target', 'openttd', '--parallel', str(args.jobs)])]:
            with (root / (name + '.log')).open('w') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
        (root / 'build/baseset').mkdir(exist_ok=True)
        shutil.copyfile(base / 'build/baseset/opengfx-8.0.tar', root / 'build/baseset/opengfx-8.0.tar')
        record.update(status='built', executable_sha256=hashlib.sha256((root / 'build/openttd').read_bytes()).hexdigest())
        record['base_unchanged'] = (source_hashes(base / 'source') == base_hashes and
            hashlib.sha256((base / 'build/openttd').read_bytes()).hexdigest() == base_binary)
        if not record['base_unchanged']:
            raise ValueError('Input engine changed during isolated preparation')
        record['composed_source_hashes'] = source_hashes(source)
    except BaseException as error:
        record.update(status='failed', error=repr(error)); raise
    finally:
        write_json(root / 'preparation.json', record)


if __name__ == '__main__':
    main()
