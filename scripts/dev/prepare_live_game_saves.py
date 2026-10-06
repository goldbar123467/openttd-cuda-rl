#!/usr/bin/env python3
"""Build native live-save support in a fresh tree, preserving the input engine."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess

from local import ROOT, capture_source, source_identity, write_json
from prepare_human_replay import source_hashes


def build(base, root, jobs):
    base, root = base.resolve(), root.resolve()
    if root == base or root.is_relative_to(base):
        raise ValueError("Save-enabled engine must be separate from its input")
    root.mkdir(parents=True, exist_ok=False)
    original = source_hashes(base / "source")
    binary_hash = hashlib.sha256((base / "build/openttd").read_bytes()).hexdigest()
    record = {"kind": "native-live-game-saves", "status": "preparing", "source": source_identity(),
              "base": str(base), "base_source_hashes": original, "base_executable_sha256": binary_hash}
    try:
        source = root / "source"
        shutil.copytree(base / "source", source)
        shutil.copyfile(ROOT / "integration/dev/rl_v2_live.inc", source / "src/rl_v2_live.inc")
        action = source / "src/rl_v2_action.cpp"
        text = action.read_text()
        if '#include "saveload/saveload.h"' not in text:
            anchor = '#include "progress.h"'
            if text.count(anchor) != 1:
                raise ValueError("Live save header insertion anchor differs")
            action.write_text(text.replace(anchor, anchor + '\n#include "saveload/saveload.h"', 1))
        record["source_capture"] = capture_source(root / "source-provenance")
        configure = ["cmake", "-S", str(source), "-B", str(root / "build"), "-G", "Ninja",
                     "-DCMAKE_BUILD_TYPE=Release", "-DOPTION_RL_ENVIRONMENT=ON", "-DOPTION_RL_NEURAL_AGENT=OFF",
                     "-DOPTION_USE_ASSERTS=ON", "-DOPTION_DEDICATED=ON", "-DPERSONAL_DIR=.openttd-rl-live-saves"]
        if shutil.which("ccache"):
            configure += ["-DCMAKE_C_COMPILER_LAUNCHER=ccache", "-DCMAKE_CXX_COMPILER_LAUNCHER=ccache"]
        for name, command in [("configure", configure), ("build", ["cmake", "--build", str(root / "build"),
                                          "--target", "openttd", "--parallel", str(jobs)])]:
            with (root / (name + ".log")).open("x") as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
        (root / "build/baseset").mkdir(exist_ok=True)
        shutil.copyfile(base / "build/baseset/opengfx-8.0.tar", root / "build/baseset/opengfx-8.0.tar")
        record.update(status="built", executable_sha256=hashlib.sha256((root / "build/openttd").read_bytes()).hexdigest(),
                      composed_source_hashes=source_hashes(source), base_unchanged=(source_hashes(base / "source") == original and
                          hashlib.sha256((base / "build/openttd").read_bytes()).hexdigest() == binary_hash))
        if not record["base_unchanged"]:
            raise ValueError("Input engine changed during isolated save build")
    except BaseException as error:
        record.update(status="failed", error=repr(error))
        raise
    finally:
        write_json(root / "preparation.json", record)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-engine-root", type=Path, required=True)
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("jobs must be positive")
    build(args.base_engine_root, args.engine_root, args.jobs)
