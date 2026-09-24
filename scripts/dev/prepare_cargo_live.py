#!/usr/bin/env python3
"""Compose opt-in live passenger/mail primitives in a separate native tree."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from local import ROOT, capture_source, positive, source_identity, write_json


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Cargo adapter source anchor differs: {old[:100]}")
    return text.replace(old, new, 1)


def live_source(text):
    text = replace_once(text, 'const std::string_view schema = shared ? DEV_SHARED_SCHEMA : DEV_LIVE_SCHEMA;',
        '_dev_cargo_live = config.at("schema_version") == DEV_CARGO_SCHEMA;\n'
        '    const std::string_view schema = shared ? DEV_SHARED_SCHEMA : (_dev_cargo_live ? DEV_CARGO_SCHEMA : DEV_LIVE_SCHEMA);')
    text = text.replace('enumeration = EnumerateCandidates();', 'enumeration = DevCargoCandidates();')
    text = replace_once(text, 'action = ExecuteCandidate(*selected);', 'action = DevCargoExecute(*selected);')
    text = replace_once(text, 'action["family"] = FAMILY_NAMES[static_cast<size_t>(selected->family)];',
        'action["family"] = DevCargoFamilyName(*selected);')
    text = replace_once(text, '{"family", FAMILY_NAMES[family]}', '{"family", DevCargoFamilyName(candidate)}')
    text = replace_once(text, 'return {{"alive", company->months_of_bankruptcy < 10}',
        'return DevCargoEconomy({{"alive", company->months_of_bankruptcy < 10}')
    text = replace_once(text, '{"operating_profit", income + expenses}, {"delivered_passengers", delivered}};',
        '{"operating_profit", income + expenses}, {"delivered_passengers", delivered}}, identity);')
    text = replace_once(text, 'return {{"schema_version", schema}, {"action_schema_id", ACTION_SCHEMA_ID}',
        'return DevCargoObservation({{"schema_version", schema}, {"action_schema_id", ACTION_SCHEMA_ID}')
    text = replace_once(text, '{"towns", towns}, {"stations", stations}, {"depots", depots}, {"vehicles", vehicles}, {"candidates", candidates}};',
        '{"towns", towns}, {"stations", stations}, {"depots", depots}, {"vehicles", vehicles}, {"candidates", candidates}});')
    text = replace_once(text, 'if (pending || terminal) {',
        'if (_dev_cargo_live) {\n'
        '                    response.update({{"status", "REJECTED"}, {"reason", "CARGO_TENSORS_NOT_IMPLEMENTED"}});\n'
        '                } else if (pending || terminal) {')
    return text


def run(args):
    if args.refresh:
        return refresh(args)
    base, output = args.base_engine.resolve(), args.output.resolve()
    marker = base / "live-adapter.json"
    prior = json.loads(marker.read_text())
    if prior["status"] != "built":
        raise ValueError("Cargo preparation requires the completed live bus engine")
    expected = {"rl_v2_action.cpp": prior["action_source_sha256"], "rl_v2_live.inc": prior["adapter_sha256"],
                **prior["public_observation_sources"]}
    for name, sha in expected.items():
        if hashlib.sha256((base / "source/src" / name).read_bytes()).hexdigest() != sha:
            raise ValueError("Existing bus source changed: " + name)
    output.mkdir(parents=True, exist_ok=False)
    record = {"kind": "native-live-mail-development-composition", "status": "preparing",
              "source": source_identity(), "base_engine": str(base),
              "base_marker_sha256": hashlib.sha256(marker.read_bytes()).hexdigest(),
              "base_source_sha256": expected,
              "claim": "New opt-in native mail primitives, not the M16 qualification fixture or neural mail learning"}
    write_json(output / "preparation.json", record)
    try:
        source = output / "source"
        shutil.copytree(base / "source", source)
        action = source / "src/rl_v2_action.cpp"
        text = action.read_text()
        text = replace_once(text, '#include "cargotype.h"',
            '#include "cargotype.h"\n#include "articulated_vehicles.h"\n#include "engine_base.h"\n#include "roadstop_base.h"')
        text = replace_once(text, '#include "rl_v2_live.inc"',
            '#include "rl_v2_cargo_live.inc"\n#include "rl_v2_live.inc"')
        text = replace_once(text, 'program.value("schema_version", "") == DEV_SHARED_SCHEMA)',
            'program.value("schema_version", "") == DEV_SHARED_SCHEMA || program.value("schema_version", "") == DEV_CARGO_SCHEMA)')
        action.write_text(text)
        include = source / "src/rl_v2_live.inc"
        include.write_text(live_source(include.read_text()))
        shutil.copyfile(ROOT / "integration/dev/rl_v2_cargo_live.inc", source / "src/rl_v2_cargo_live.inc")
        record["result_source_sha256"] = {name: hashlib.sha256((source / "src" / name).read_bytes()).hexdigest()
            for name in [*expected, "rl_v2_cargo_live.inc"]}
        capture_source(output / "source-archive")
        record["status"] = "prepared"
        write_json(output / "preparation.json", record)
        command = ["cmake", "-S", str(source), "-B", str(output / "build"), "-G", "Ninja",
                   "-DCMAKE_BUILD_TYPE=Release", "-DOPTION_RL_ENVIRONMENT=ON", "-DOPTION_RL_NEURAL_AGENT=OFF",
                   "-DOPTION_USE_ASSERTS=ON", "-DOPTION_DEDICATED=ON", "-DPERSONAL_DIR=.openttd-rl-cargo-development"]
        record["configure"] = command
        record["status"] = "building"
        write_json(output / "preparation.json", record)
        subprocess.run(command, check=True)
        subprocess.run(["cmake", "--build", str(output / "build"), "--parallel", str(args.jobs)], check=True)
        baseset = output / "build/baseset"
        baseset.mkdir(exist_ok=True)
        shutil.copy2(base / "build/baseset/opengfx-8.0.tar", baseset / "opengfx-8.0.tar")
        record.update(status="built", executable_sha256=hashlib.sha256((output / "build/openttd").read_bytes()).hexdigest())
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(output / "preparation.json", record)


def refresh(args):
    output = args.output.resolve()
    marker = output / "preparation.json"
    record = json.loads(marker.read_text())
    if record["status"] not in ("built", "failed") or "result_source_sha256" not in record:
        raise ValueError("Cargo refresh requires a finished prior build attempt")
    for name, digest in record["result_source_sha256"].items():
        if hashlib.sha256((output / "source/src" / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Cargo source changed outside preparation: " + name)
    revision = {key: record.get(key) for key in ("status", "error", "source", "result_source_sha256", "executable_sha256")}
    record.setdefault("revisions", []).append(revision)
    number = len(record["revisions"])
    binary = output / "build/openttd"
    if binary.exists():
        saved = output / f"openttd-before-refresh-{number:03d}"
        if saved.exists():
            raise ValueError("Preserved cargo binary already exists")
        shutil.copy2(binary, saved)
        revision["preserved_binary"] = str(saved)
    include = output / "source/src/rl_v2_cargo_live.inc"
    shutil.copyfile(ROOT / "integration/dev/rl_v2_cargo_live.inc", include)
    action = output / "source/src/rl_v2_action.cpp"
    text = action.read_text()
    if '#include "roadstop_base.h"' not in text:
        action.write_text(replace_once(text, '#include "engine_base.h"', '#include "engine_base.h"\n#include "roadstop_base.h"'))
    record["result_source_sha256"] = {**record["result_source_sha256"],
        include.name: hashlib.sha256(include.read_bytes()).hexdigest(), action.name: hashlib.sha256(action.read_bytes()).hexdigest()}
    record.update(status="building", source=source_identity())
    record.pop("error", None)
    capture_source(output / f"source-archive-refresh-{number:03d}")
    write_json(marker, record)
    try:
        subprocess.run(["cmake", "--build", str(output / "build"), "--parallel", str(args.jobs)], check=True)
        baseset = output / "build/baseset"
        baseset.mkdir(exist_ok=True)
        shutil.copy2(args.base_engine.resolve() / "build/baseset/opengfx-8.0.tar", baseset / "opengfx-8.0.tar")
        record.update(status="built", executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(marker, record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-engine", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=positive, default=2)
    parser.add_argument("--refresh", action="store_true", help="Preserve the prior binary and rebuild only the development mail include")
    run(parser.parse_args())
