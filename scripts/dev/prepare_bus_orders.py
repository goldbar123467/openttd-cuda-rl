#!/usr/bin/env python3
"""Build the opt-in bounded native bus-order interface in a fresh isolated tree."""
import argparse
import hashlib
import shutil
import subprocess

from pathlib import Path
from local import ROOT, capture_source, source_identity, write_json
from prepare_human_replay import source_hashes


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Native bus-order insertion anchor differs: {old[:80]}')
    return text.replace(old, new, 1)


def compose(source):
    path = source / 'src/rl_v2_action.cpp'
    text = path.read_text()
    text = once(text, 'static constexpr std::string_view ACTION_SCHEMA_ID', 'static std::string_view ACTION_SCHEMA_ID')
    text = once(text, '#include "timer/timer_game_tick.h"', '#include "timer/timer_game_tick.h"\n#include "progress.h"')
    text = once(text, 'static CandidateEnumeration EnumerateCandidates(CompanyID company = _current_company)',
                '#define RL_DEV_BUS_ORDERS 1\n#include "rl_bus_orders.inc"\n\nstatic CandidateEnumeration EnumerateCandidates(CompanyID company = _current_company)')
    text = once(text, '\t\tfor (const Station *origin : stations) for (const Station *destination : stations) {',
                '\t\tif (_dev_bus_orders) DevEnumerateBusOrders(vehicle, stations, add);\n'
                '\t\tif (!_dev_bus_orders) for (const Station *origin : stations) for (const Station *destination : stations) {')
    text = once(text, '\t\tcase Family::SetRoute: {',
                '\t\tcase Family::SetRoute: {\n'
                '\t\t\tif (_dev_bus_orders) {\n'
                '\t\t\t\tstatic constexpr std::array<const char *, 5> names = {"INVALID", "CMD_INSERT_ORDER", "CMD_MODIFY_ORDER", "CMD_CLONE_ORDER", "CMD_DELETE_ORDER"};\n'
                '\t\t\t\tconst auto operation = p[2] & 0xFF;\n'
                '\t\t\t\texecute(operation < names.size() ? names[operation] : names[0], [&] { return DevBusOrderCommand(p, DoCommandFlag::Execute); });\n'
                '\t\t\t\tbreak;\n\t\t\t}\n')
    text = once(text, '\t\tfor (const Order &order : vehicle->Orders()) { add_u32(static_cast<uint8_t>(order.GetType())); add_u32(order.GetDestination().base()); }',
                '\t\tfor (const Order &order : vehicle->Orders()) { add_u32(static_cast<uint8_t>(order.GetType())); add_u32(order.GetDestination().base()); if (_dev_bus_orders) sha.Update(DevOrderBytes(order)); }\n'
                '\t\tif (_dev_bus_orders) { add_u32(vehicle->cur_real_order_index); add_u32(vehicle->cur_implicit_order_index); add_u32(vehicle->IsOrderListShared()); }')
    text = once(text, '\tWriteCanonicalNew(metadata, metadata_value);',
                '\tif (_dev_bus_orders) metadata_value["action_semantics"] = "orders-v1";\n\tWriteCanonicalNew(metadata, metadata_value);')
    path.write_text(text)
    for name in ('rl_bus_orders.inc', 'rl_v2_live.inc'):
        shutil.copyfile(ROOT / 'integration/dev' / name, source / 'src' / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-engine-root', required=True, type=Path)
    parser.add_argument('--engine-root', required=True, type=Path)
    parser.add_argument('--jobs', default=4, type=int)
    args = parser.parse_args()
    base, root = args.base_engine_root.resolve(), args.engine_root.resolve()
    if root == base or root.is_relative_to(base):
        raise ValueError('Bus-order output must be outside input engine')
    root.mkdir(parents=True, exist_ok=False)
    before = source_hashes(base / 'source')
    base_binary = hashlib.sha256((base / 'build/openttd').read_bytes()).hexdigest()
    record = {'kind': 'development-native-bus-orders-v1', 'source': source_identity(),
              'base': str(base), 'status': 'preparing', 'base_source_hashes': before,
              'base_executable_sha256': base_binary}
    write_json(root / 'preparation.json', record)
    try:
        source = root / 'source'
        shutil.copytree(base / 'source', source)
        compose(source)
        capture_source(root / 'source-provenance')
        configure = ['cmake', '-S', str(source), '-B', str(root / 'build'), '-G', 'Ninja',
                     '-DCMAKE_BUILD_TYPE=Release', '-DOPTION_RL_ENVIRONMENT=ON',
                     '-DOPTION_RL_NEURAL_AGENT=OFF', '-DOPTION_USE_ASSERTS=ON', '-DOPTION_DEDICATED=ON',
                     '-DPERSONAL_DIR=.openttd-rl-bus-orders']
        if shutil.which('ccache'):
            configure += ['-DCMAKE_C_COMPILER_LAUNCHER=ccache', '-DCMAKE_CXX_COMPILER_LAUNCHER=ccache']
        for name, command in [('configure', configure), ('build', ['cmake', '--build', str(root / 'build'), '--target', 'openttd', '--parallel', str(args.jobs)])]:
            with (root / (name + '.log')).open('w') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
        (root / 'build/baseset').mkdir(exist_ok=True)
        shutil.copyfile(base / 'build/baseset/opengfx-8.0.tar', root / 'build/baseset/opengfx-8.0.tar')
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
