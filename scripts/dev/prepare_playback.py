#!/usr/bin/env python3
"""Build isolated native playback for development models/maps using the M11 controller."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from local import ROOT, capture_source, positive, source_identity, write_json
from prepare_engine import prepare


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Playback source anchor changed: {old[:100]}")
    return text.replace(old, new, 1)


def overlay(source):
    options_path = source / "cmake/Options.cmake"
    options = options_path.read_text()
    anchor = '    option(OPTION_RL_NEURAL_AGENT "Enable the inference-only OpenTTD-RL normal-game neural agent" OFF)'
    options = replace_once(options, anchor, anchor + '\n    option(OPTION_RL_DEVELOPMENT_PLAYBACK "Play development policies on training/development maps" OFF)')
    anchor = '        add_definitions(-DWITH_RL_NEURAL_AGENT)'
    options = replace_once(options, anchor, anchor + '''
        if(OPTION_RL_DEVELOPMENT_PLAYBACK)
            add_definitions(-DWITH_RL_DEVELOPMENT_PLAYBACK)
        endif()''')
    path = source / "src/rl_neural_agent.cpp"
    content = path.read_text()
    start = 'static constexpr std::string_view ACCEPTED_PACKAGE_ID = '
    end = 'static void Require(bool condition, std::string_view message)'
    begin, finish = content.index(start), content.index(end)
    original = content[begin:finish].rstrip()
    content = content[:begin] + '''#ifdef WITH_RL_DEVELOPMENT_PLAYBACK
static constexpr std::string_view PLAYBACK_SCHEMA = "openttd-rl-development-playback-config-1";
static constexpr std::string_view REPORT_SCHEMA = "openttd-rl-development-playback-report-1";
#else
''' + original + '\n#endif\n\n' + content[finish:]
    anchor = '\t\tRequire(this->policy_->package_id() == ACCEPTED_PACKAGE_ID, "package is valid but is not the M09/M10 accepted combined policy");\n\t\tRequire(this->policy_->model_sha256() == ACCEPTED_MODEL_SHA256, "accepted package model identity drifted");'
    content = replace_once(content, anchor, '#ifndef WITH_RL_DEVELOPMENT_PLAYBACK\n' + anchor + '\n#endif')
    anchor = '\t\tResetRlEnvironmentBridgeScenario(this->config_.scenario_instance.string());'
    content = replace_once(content, anchor, '''#ifdef WITH_RL_DEVELOPMENT_PLAYBACK
        const std::set<std::string> development_files = {"m02-template-01.json", "m02-template-02.json",
            "m02-template-03.json", "m02-template-04.json", "m02-template-05.json", "m02-template-06.json"};
        Require(development_files.contains(this->config_.scenario_instance.filename().string()),
                "development playback requires a training/development instance filename before reset");
#endif
''' + anchor)
    anchor = '\t\tRequire(template_id == "m02-template-07" || template_id == "m02-template-08", "normal-game acceptance supports only frozen final templates 07 and 08");'
    content = replace_once(content, anchor, '''#ifdef WITH_RL_DEVELOPMENT_PLAYBACK
        Require(template_id == "m02-template-01" || template_id == "m02-template-02" ||
                template_id == "m02-template-03" || template_id == "m02-template-04" ||
                template_id == "m02-template-05" || template_id == "m02-template-06",
                "development playback forbids held-out scenarios");
#else
''' + anchor + '\n#endif')
    anchor = 'fmt::format("Model: combined-cnn-mlp-v1 v1 | package {}...", this->policy_->package_id().substr(0, 12))'
    content = replace_once(content, anchor, 'fmt::format("Model: {} v1 | package {}...", openttd_rl::deployment::architecture_name(this->policy_->architecture()), this->policy_->package_id().substr(0, 12))')
    if content.count('{"model_name", "combined-cnn-mlp-v1"}') != 2:
        raise ValueError("Unexpected native model-label count")
    content = content.replace('{"model_name", "combined-cnn-mlp-v1"}',
                              '{"model_name", openttd_rl::deployment::architecture_name(this->policy_->architecture())}')
    # Write only after every expected source anchor has been verified.
    options_path.write_text(options)
    path.write_text(content)


def run(args):
    root = args.engine_root.resolve()
    if not root.exists():
        prepare(root)
    source = root / "source"
    marker = root / "development-playback.json"
    if not marker.exists():
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True).strip():
            raise ValueError("Playback preparation requires a pristine composed engine")
        overlay(source)
        patch = subprocess.check_output(["git", "diff", "--binary"], cwd=source)
        (root / "development-playback.patch").write_bytes(patch)
        capture_source(root / "preparation-source")
        write_json(marker, {"kind": "development-playback-engine", "status": "prepared", "source": source_identity(),
                           "overlay_sha256": hashlib.sha256(patch).hexdigest(),
                           "claim": "development models on training/development maps; no historical playback gate claim"})
    metadata = json.loads(marker.read_text())
    current_patch = subprocess.check_output(["git", "diff", "--binary"], cwd=source)
    if hashlib.sha256(current_patch).hexdigest() != metadata["overlay_sha256"]:
        raise ValueError("Composed playback source differs from its recorded development overlay")
    build = root / "build"
    command = ["cmake", "-S", str(source), "-B", str(build), "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
               "-DOPTION_RL_ENVIRONMENT=ON", "-DOPTION_RL_NEURAL_AGENT=ON", "-DOPTION_RL_DEVELOPMENT_PLAYBACK=ON",
               "-DOPTION_USE_ASSERTS=ON", "-DOPTION_DEDICATED=OFF", "-DPERSONAL_DIR=.openttd-rl-development",
               f"-DOPENTTD_RL_PROJECT_ROOT={ROOT}", f"-DOPENTTD_RL_ONNXRUNTIME_ROOT={args.onnxruntime.resolve()}"]
    subprocess.run(command, check=True)
    subprocess.run(["cmake", "--build", str(build), "--parallel", str(args.jobs)], check=True)
    baseset = args.baseset.resolve()
    if hashlib.sha256(baseset.read_bytes()).hexdigest() != "9389bcb0807058c80bd95121e978f05d9ef86b4b1bc3ac2da8da8bb02456043c":
        raise ValueError("OpenGFX 8.0 archive hash differs")
    (build / "baseset").mkdir(exist_ok=True)
    shutil.copyfile(baseset, build / "baseset/opengfx-8.0.tar")
    write_json(root / "playback-build.json", {"source": source_identity(), "configure": command,
               "executable_sha256": hashlib.sha256((build / "openttd").read_bytes()).hexdigest(), "status": "built"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--onnxruntime", type=Path, required=True)
    parser.add_argument("--baseset", type=Path, required=True)
    parser.add_argument("--jobs", type=positive, default=2)
    run(parser.parse_args())
