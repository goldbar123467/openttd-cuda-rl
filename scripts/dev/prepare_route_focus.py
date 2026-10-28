#!/usr/bin/env python3
"""Build the opt-in town-pair candidate focus on top of a bus-order engine, in a fresh tree.

Engines built here accept `candidate_focus: town-pair-v1` in the live config.
With it, SELECT_TOWN_PAIR ranks construction candidates around the selected
towns instead of only the most populous one; without it they behave exactly as
the bus-order engine.
"""
import argparse
import hashlib
import shutil
import subprocess

from pathlib import Path
from local import ROOT, capture_source, copy_baseset, positive, source_identity, write_json
from prepare_bus_orders import once
from prepare_human_replay import source_hashes


def compose(source):
    path = source / 'src/rl_v2_action.cpp'
    text = path.read_text()
    text = once(text, '#define RL_DEV_BUS_ORDERS 1\n',
                '#define RL_DEV_ROUTE_FOCUS 1\n#include "rl_route_focus.inc"\n\n#define RL_DEV_BUS_ORDERS 1\n')
    text = once(text, '\t\tuint32_t distance = anchor == nullptr ? Map::SizeX() + Map::SizeY() :\n'
                      '\t\t\tstatic_cast<uint32_t>(std::abs(static_cast<int>(TileX(tile)) - static_cast<int>(TileX(anchor->xy))) +\n'
                      '\t\t\tstd::abs(static_cast<int>(TileY(tile)) - static_cast<int>(TileY(anchor->xy))));',
                '\t\tuint32_t distance = DevAnchorDistance(tile, anchor);')
    text = once(text, '\t\tcase Family::SelectTownPair: break;',
                '\t\tcase Family::SelectTownPair:\n'
                '\t\t\tif (_dev_route_focus) _dev_focus_towns = std::pair{TownID{static_cast<uint16_t>(p[1])}, TownID{static_cast<uint16_t>(p[2])}};\n'
                '\t\t\tbreak;')
    text = once(text, '\tadd_u32(money); add_u32(money >> 32); add_u32(loan); add_u32(loan >> 32);\n',
                '\tadd_u32(money); add_u32(money >> 32); add_u32(loan); add_u32(loan >> 32);\n'
                '\tif (_dev_route_focus) { add_u32(_dev_focus_towns ? _dev_focus_towns->first.base() : 0xFFFFFFFFU);\n'
                '\t\tadd_u32(_dev_focus_towns ? _dev_focus_towns->second.base() : 0xFFFFFFFFU); }\n')
    path.write_text(text)
    for name in ('rl_route_focus.inc', 'rl_bus_orders.inc', 'rl_v2_live.inc'):
        shutil.copyfile(ROOT / 'integration/dev' / name, source / 'src' / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-engine-root', required=True, type=Path, help='a built prepare_bus_orders.py engine')
    parser.add_argument('--engine-root', required=True, type=Path)
    parser.add_argument('--jobs', default=4, type=positive)
    args = parser.parse_args()
    base, root = args.base_engine_root.resolve(), args.engine_root.resolve()
    if root == base or root.is_relative_to(base):
        raise ValueError('Route-focus output must be outside the input engine')
    root.mkdir(parents=True, exist_ok=False)
    before = source_hashes(base / 'source')
    base_binary = hashlib.sha256((base / 'build/openttd').read_bytes()).hexdigest()
    record = {'kind': 'development-native-route-focus-v1', 'source': source_identity(), 'base': str(base),
              'status': 'preparing', 'base_source_hashes': before, 'base_executable_sha256': base_binary}
    write_json(root / 'preparation.json', record)
    try:
        source = root / 'source'
        shutil.copytree(base / 'source', source)
        compose(source)
        capture_source(root / 'source-provenance')
        configure = ['cmake', '-S', str(source), '-B', str(root / 'build'), '-G', 'Ninja',
                     '-DCMAKE_BUILD_TYPE=Release', '-DOPTION_RL_ENVIRONMENT=ON',
                     '-DOPTION_RL_NEURAL_AGENT=OFF', '-DOPTION_USE_ASSERTS=ON', '-DOPTION_DEDICATED=ON',
                     '-DPERSONAL_DIR=.openttd-rl-route-focus']
        if shutil.which('ccache'):
            configure += ['-DCMAKE_C_COMPILER_LAUNCHER=ccache', '-DCMAKE_CXX_COMPILER_LAUNCHER=ccache']
        for name, command in [('configure', configure), ('build', ['cmake', '--build', str(root / 'build'), '--target', 'openttd', '--parallel', str(args.jobs)])]:
            with (root / (name + '.log')).open('w') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=3600)
        (root / 'build/baseset').mkdir(exist_ok=True)
        copy_baseset(base / 'build/baseset/opengfx-8.0.tar', root / 'build/baseset/opengfx-8.0.tar')
        record.update(status='built', executable_sha256=hashlib.sha256((root / 'build/openttd').read_bytes()).hexdigest(),
                      composed_source_hashes=source_hashes(source))
        record['base_unchanged'] = source_hashes(base / 'source') == before and hashlib.sha256((base / 'build/openttd').read_bytes()).hexdigest() == base_binary
        if not record['base_unchanged']:
            raise ValueError('Input engine changed during isolated preparation')
    except BaseException as error:
        record.update(status='failed', error=repr(error))
        raise
    finally:
        write_json(root / 'preparation.json', record)


if __name__ == '__main__':
    main()
