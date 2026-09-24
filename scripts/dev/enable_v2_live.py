#!/usr/bin/env python3
"""Apply the interactive development adapter to a separately prepared M15 tree."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from local import ROOT, capture_source, positive, source_identity, write_json


def development_headers(text):
    for name in ("settings_type.h", "station_func.h"):
        include = f'#include "{name}"'
        if include not in text:
            if text.count("#include <algorithm>") != 1:
                raise ValueError("Native header insertion anchor differs")
            text = text.replace("#include <algorithm>", include + "\n\n#include <algorithm>", 1)
    return text


def public_observation_sources(source, record):
    """Preserve historical encoding; opt live calls into public vehicle ordering."""
    marker = "bool development_public"
    for name in ("rl_v2_observation.cpp", "rl_v2_observation.h"):
        path = source / "src" / name
        expected = record.get("public_observation_sources", {}).get(name)
        if expected is None:
            baseline = subprocess.check_output(["git", "show", f":src/{name}"], cwd=source)
            expected = hashlib.sha256(baseline).hexdigest()
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Observation source changed outside the recorded adapter: {name}")
    signature = "uint32_t simulation_seed, uint32_t candidate_tiebreak_seed)"
    header = source / "src/rl_v2_observation.h"
    implementation = source / "src/rl_v2_observation.cpp"
    if marker not in implementation.read_text():
        text = implementation.read_text()
        replacements = [
            (signature, "uint32_t simulation_seed, uint32_t candidate_tiebreak_seed, bool development_public)"),
            ("static std::vector<const Vehicle *> OrderedVehicles()", "static std::vector<const Vehicle *> OrderedVehicles(bool development_public)"),
            ("auto vehicles = OrderedVehicles();", "auto vehicles = OrderedVehicles(development_public);"),
            ("std::sort(result.begin(), result.end(), [](const Vehicle *a, const Vehicle *b) {",
             "std::sort(result.begin(), result.end(), [development_public](const Vehicle *a, const Vehicle *b) {\n"
             "\t\tif (development_public) return std::tuple(a->owner == CompanyID::Begin() ? 0 : 1, a->index.base()) <\n"
             "\t\t\t\tstd::tuple(b->owner == CompanyID::Begin() ? 0 : 1, b->index.base());"),
            ("row[7] = Unit(vehicle->breakdown_delay, 255); row[8] = Unit(vehicle->breakdown_ctr, 255);",
             "row[7] = development_public ? 0.0F : Unit(vehicle->breakdown_delay, 255); row[8] = development_public ? 0.0F : Unit(vehicle->breakdown_ctr, 255);")]
        for old, new in replacements:
            if text.count(old) != 1:
                raise ValueError("Native public observation insertion anchor differs")
            text = text.replace(old, new, 1)
        header_text = header.read_text()
        if header_text.count(signature) != 1:
            raise ValueError("Native public observation declaration anchor differs")
        implementation.write_text(text)
        header.write_text(header_text.replace(signature,
            "uint32_t simulation_seed, uint32_t candidate_tiebreak_seed, bool development_public = false)", 1))
    record["public_observation_sources"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (header, implementation)}


def company_scoped_sources(source, record):
    action = source / "src/rl_v2_action.cpp"
    text = action.read_text()
    if "EnumerateCandidates(CompanyID company" not in text:
        begin = text.index("static CandidateEnumeration EnumerateCandidates()")
        end = text.index("static json CommandLog", begin)
        block = text[begin:end].replace("EnumerateCandidates()", "EnumerateCandidates(CompanyID company = _current_company)", 1)
        block = block.replace("CompanyID::Begin()", "company")
        text = text[:begin] + block + text[end:]
        begin, end = text.index("static std::string NativeStateSha256()"), text.index("static json ExecuteCandidate")
        text = text[:begin] + text[begin:end].replace("Company::Get(CompanyID::Begin())", "Company::Get(_current_company)") + text[end:]
        text = text.replace('#include "rl_v2_live.inc"',
            'extern Company *DoStartupNewCompany(bool is_ai, CompanyID company);\n\n#include "rl_v2_live.inc"', 1)
        text = text.replace('== DEV_LIVE_SCHEMA) {', '== DEV_LIVE_SCHEMA || program.value("schema_version", "") == DEV_SHARED_SCHEMA) {', 1)
        action.write_text(text)
    observation = source / "src/rl_v2_observation.cpp"
    text = observation.read_text()
    if '#include "company_func.h"' not in text:
        text = text.replace('#include "company_base.h"', '#include "company_base.h"\n#include "company_func.h"', 1)
    if "// Development public company scope." not in text:
        text = text.replace("CompanyID::Begin()", "_current_company")
        # Opponent identity/position are public; its financial/internal state is
        # excluded from the live view. The historical single-company calls stay
        # on company 0 and retain their original encoding.
        replacements = [
            ("company_rows.push_back(std::move(row));",
             "// Development public company scope.\n\t\tif (development_public && item->index != _current_company) std::fill(row.begin() + 2, row.end(), 0.0F);\n\t\tcompany_rows.push_back(std::move(row));"),
            ("station_rows.push_back(std::move(row));",
             "if (development_public && station->owner != _current_company) std::fill(row.begin() + 4, row.end(), 0.0F);\n\t\tstation_rows.push_back(std::move(row));"),
            ("vehicle_rows.push_back(std::move(row));",
             "if (development_public && vehicle->owner != _current_company) std::fill(row.begin() + 9, row.end(), 0.0F);\n\t\tvehicle_rows.push_back(std::move(row));"),
            ("row[4] = Unit(StationWaiting(station), 65535);",
             "row[4] = development_public && station->owner != _current_company ? 0.0F : Unit(StationWaiting(station), 65535);")]
        for old, new in replacements:
            if text.count(old) != 1:
                raise ValueError("Native scoped observation insertion anchor differs")
            text = text.replace(old, new, 1)
    if "OrderedStations(bool development_public)" not in text:
        text = text.replace("OrderedStations()", "OrderedStations(bool development_public)", 1)
        text = text.replace("auto stations = OrderedStations();", "auto stations = OrderedStations(development_public);", 1)
        text = text.replace("std::sort(result.begin(), result.end(), [](const Station *a, const Station *b) {",
            "std::sort(result.begin(), result.end(), [development_public](const Station *a, const Station *b) {\n"
            "\t\tif (development_public && a->owner != _current_company && b->owner != _current_company) return a->index < b->index;", 1)
    observation.write_text(text)
    record["public_observation_sources"][observation.name] = hashlib.sha256(observation.read_bytes()).hexdigest()


def refresh(args):
    root = args.engine_root.resolve()
    marker = root / "live-adapter.json"
    record = json.loads(marker.read_text())
    action = root / "source/src/rl_v2_action.cpp"
    include = root / "source/src/rl_v2_live.inc"
    if hashlib.sha256(action.read_bytes()).hexdigest() != record["action_source_sha256"] or \
            hashlib.sha256(include.read_bytes()).hexdigest() != record["adapter_sha256"]:
        raise ValueError("Live engine source changed outside the recorded adapter; preserve and inspect it")
    previous = {key: record.get(key) for key in ("status", "source", "adapter_sha256", "executable_sha256")}
    record.setdefault("revisions", []).append(previous)
    try:
        preserved = root / "build" / f"openttd-live-revision-{len(record['revisions']):03d}"
        if preserved.exists():
            raise ValueError("Preserved live revision executable already exists")
        shutil.copy2(root / "build/openttd", preserved)
        previous["preserved_executable"] = str(preserved)
        public_observation_sources(root / "source", record)
        company_scoped_sources(root / "source", record)
        action.write_text(development_headers(action.read_text()))
        shutil.copyfile(ROOT / "integration/dev/rl_v2_live.inc", include)
        record.update(status="building", source=source_identity(), adapter_sha256=hashlib.sha256(include.read_bytes()).hexdigest(),
                      action_source_sha256=hashlib.sha256(action.read_bytes()).hexdigest())
        archive = root / f"live-adapter-source-{len(record['revisions']):03d}"
        capture_source(archive)
        record["source_archive"] = str(archive)
        (root / f"live-adapter-{len(record['revisions']):03d}.patch").write_bytes(
            subprocess.check_output(["git", "diff", "--binary"], cwd=root / "source"))
        write_json(marker, record)
        subprocess.run(["cmake", "--build", str(root / "build"), "--parallel", str(args.jobs)], check=True)
        record.update(status="built", executable_sha256=hashlib.sha256((root / "build/openttd").read_bytes()).hexdigest())
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(marker, record)


def run(args):
    if args.refresh:
        return refresh(args)
    root = args.engine_root.resolve()
    preparation = json.loads((root / "preparation.json").read_text())
    if preparation["status"] != "built" or preparation["stages"][-1]["name"] != "m15-competence":
        raise ValueError("Complete the existing M15 native build before applying the live adapter")
    source = root / "source"
    marker = root / "live-adapter.json"
    if marker.exists():
        raise ValueError("Live adapter already prepared; preserve its evidence and use an explicit rebuild")
    actual = subprocess.check_output(["git", "write-tree"], cwd=source, text=True).strip()
    if actual != preparation["stages"][-1]["tree"]:
        raise ValueError("M15 staged source tree differs from preparation")
    subprocess.run(["git", "diff", "--exit-code"], cwd=source, check=True)
    record = {"kind": "development-v2-live-adapter", "status": "preparing", "source": source_identity(), "base_tree": actual}
    write_json(marker, record)
    try:
        baseline = root / "build/openttd-m15-baseline"
        if baseline.exists():
            raise ValueError("Preserved baseline executable already exists")
        shutil.copy2(root / "build/openttd", baseline)
        record["baseline_executable"] = str(baseline)
        record["baseline_sha256"] = hashlib.sha256(baseline.read_bytes()).hexdigest()
        target = source / "src/rl_v2_action.cpp"
        text = target.read_text()
        signature = "void RunRlV2EpisodeProgram(const std::string &program_path, const std::string &trace_path,"
        dispatch = "\tjson program = ReadCanonicalJson(program_path);"
        if text.count(signature) != 1 or text.count(dispatch) != 1:
            raise ValueError("M15 source anchors differ; no adapter applied")
        text = text.replace("#include <algorithm>", "#include <algorithm>\n#include <cerrno>\n#include <chrono>\n#include <poll.h>\n#include <unistd.h>", 1)
        text = text.replace(signature, '#include "rl_v2_live.inc"\n\n' + signature, 1)
        text = text.replace(dispatch, dispatch + '\n\tif (program.value("schema_version", "") == DEV_LIVE_SCHEMA) {\n'
                            '\t\tRunDevelopmentV2Live(program, trace_path, artifact_directory);\n\t\treturn;\n\t}', 1)
        target.write_text(development_headers(text))
        public_observation_sources(source, record)
        company_scoped_sources(source, record)
        overlay = ROOT / "integration/dev/rl_v2_live.inc"
        shutil.copyfile(overlay, source / "src/rl_v2_live.inc")
        record["adapter_sha256"] = hashlib.sha256(overlay.read_bytes()).hexdigest()
        record["action_source_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        capture_source(root / "live-adapter-source")
        (root / "live-adapter.patch").write_bytes(subprocess.check_output(["git", "diff", "--binary"], cwd=source))
        subprocess.run(["cmake", "--build", str(root / "build"), "--parallel", str(args.jobs)], check=True)
        record.update(status="built", executable_sha256=hashlib.sha256((root / "build/openttd").read_bytes()).hexdigest())
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        write_json(marker, record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--jobs", type=positive, default=2)
    parser.add_argument("--refresh", action="store_true", help="Rebuild a recorded adapter after updating its development include")
    run(parser.parse_args())
