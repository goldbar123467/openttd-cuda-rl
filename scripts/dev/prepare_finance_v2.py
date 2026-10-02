#!/usr/bin/env python3
"""Build an isolated opt-in finance engine from an existing composed live engine.

The base source, build and executable are read-only inputs. A fresh checkout and
Ninja build avoid reusing object files with stale absolute source paths.
"""
import argparse
import difflib
import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

from enable_v2_live import development_headers
from local import ROOT, capture_source, positive, source_identity, write_json

BASESET_SHA256 = "9389bcb0807058c80bd95121e978f05d9ef86b4b1bc3ac2da8da8bb02456043c"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(source, *arguments):
    return subprocess.check_output(["git", "-C", str(source), *arguments], timeout=120)


def apply_overlay(source):
    action = source / "src/rl_v2_action.cpp"
    before = action.read_text()
    if '"rl_v2_live.inc"' not in before or "EnumerateCandidates(CompanyID company" not in before:
        raise ValueError("Base must already include the company-scoped live adapter")
    after = development_headers(before)
    adapter = ROOT / "integration/dev/rl_v2_live.inc"
    text = adapter.read_text()
    if '"v2-m15-public-development-finance-v1"' not in text:
        raise ValueError("Development adapter does not include opt-in finance observations")
    action.write_text(after)
    shutil.copyfile(adapter, source / "src/rl_v2_live.inc")
    return "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                      fromfile="a/src/rl_v2_action.cpp", tofile="b/src/rl_v2_action.cpp"))


def run(args):
    root, original = args.engine_root.resolve(), args.base_engine_root.resolve()
    if root == original or root.is_relative_to(original):
        raise ValueError("Finance output must be separate from the base engine directory")
    root.mkdir(parents=True, exist_ok=False)
    record = {"kind": "isolated-development-v2-finance-engine", "status": "preparing",
              "base_engine_root": str(original), "engine_root": str(root), "jobs": args.jobs,
              "runtime": {"platform": platform.platform(), "python": sys.version},
              "claim": "Opt-in public finance observations; legacy mode retained. Build alone is not gameplay verification."}
    write_json(root / "preparation.json", record)
    started = time.monotonic()

    def execute(name, command, timeout=120):
        record.setdefault("commands", []).append({"name": name, "argv": command, "timeout_seconds": timeout})
        write_json(root / "preparation.json", record)
        with (root / (name + ".log")).open("x") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout)
        print(name + " completed", flush=True)

    try:
        record["source"] = source_identity()
        base_source = original / "source"
        record["base_engine_sha256"] = digest(original / "build/openttd")
        record["base_commit"] = git(base_source, "rev-parse", "HEAD").decode().strip()
        record["base_source_status"] = git(base_source, "status", "--porcelain").decode().strip()
        patch = git(base_source, "diff", "--binary", "HEAD")
        (root / "base-composition.patch").write_bytes(patch)
        record["base_composition_sha256"] = digest(root / "base-composition.patch")
        untracked = set(git(base_source, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")) - {b""}
        if untracked != {b"src/rl_v2_live.inc"}:
            raise ValueError("Base has unexpected untracked source; inspect it before preparation")
        record["base_adapter_sha256"] = digest(base_source / "src/rl_v2_live.inc")
        baseset = original / "build/baseset/opengfx-8.0.tar"
        if digest(baseset) != BASESET_SHA256:
            raise ValueError("Base engine OpenGFX 8.0 archive differs")
        record["baseset_sha256"] = BASESET_SHA256
        source = root / "source"
        execute("clone", ["git", "clone", "--no-hardlinks", "--no-checkout", "--dissociate", str(base_source), str(source)])
        execute("checkout", ["git", "-C", str(source), "checkout", "--detach", record["base_commit"]])
        execute("base-apply", ["git", "-C", str(source), "apply", str(root / "base-composition.patch")])
        shutil.copyfile(base_source / "src/rl_v2_live.inc", source / "src/rl_v2_live.inc")
        (root / "finance-header-overlay.patch").write_text(apply_overlay(source))
        record["finance_header_overlay_sha256"] = digest(root / "finance-header-overlay.patch")
        record["adapter_sha256"] = digest(source / "src/rl_v2_live.inc")
        record["action_source_sha256"] = digest(source / "src/rl_v2_action.cpp")
        capture_source(root / "preparation-source")
        record["status"] = "prepared"
        if not args.prepare_only:
            build = root / "build"
            command = ["cmake", "-S", str(source), "-B", str(build), "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                       "-DOPTION_RL_ENVIRONMENT=ON", "-DOPTION_RL_NEURAL_AGENT=OFF", "-DOPTION_USE_ASSERTS=ON",
                       "-DOPTION_DEDICATED=ON", "-DPERSONAL_DIR=.openttd-rl-v2-finance"]
            ccache = shutil.which("ccache")
            record["compiler_cache"] = ccache
            if ccache:
                command.extend(["-DCMAKE_C_COMPILER_LAUNCHER=" + ccache, "-DCMAKE_CXX_COMPILER_LAUNCHER=" + ccache])
            record["status"] = "building"
            execute("configure", command, timeout=300)
            execute("build", ["cmake", "--build", str(build), "--target", "openttd", "--parallel", str(args.jobs)],
                    timeout=args.build_timeout)
            (build / "baseset").mkdir(exist_ok=True)
            shutil.copyfile(baseset, build / "baseset/opengfx-8.0.tar")
            record.update(status="built", executable=str(build / "openttd"), executable_sha256=digest(build / "openttd"))
        if (digest(original / "build/openttd") != record["base_engine_sha256"] or
                git(base_source, "diff", "--binary", "HEAD") != patch or
                digest(base_source / "src/rl_v2_live.inc") != record["base_adapter_sha256"]):
            raise ValueError("Base engine changed while the isolated build was being prepared")
    except BaseException as exc:
        record.update(status="failed", error=repr(exc))
        raise
    finally:
        record["elapsed_seconds"] = time.monotonic() - started
        write_json(root / "preparation.json", record)
    print(f"Finance engine {record['status']}: {root}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-engine-root", type=Path, required=True)
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--jobs", type=positive, default=2)
    parser.add_argument("--build-timeout", type=positive, default=1800, help="Maximum build seconds; retain timed-out artifacts")
    parser.add_argument("--prepare-only", action="store_true", help="Preserve isolated source/provenance without compiling")
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("Run the native development engine build under Linux/WSL")
    run(args)
