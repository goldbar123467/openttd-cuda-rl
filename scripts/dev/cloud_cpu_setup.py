#!/usr/bin/env python3
"""Build the game engines and the C++ trainer on a CPU-only Linux host (for example a cloud container).

`engines` runs the existing preparation chain unchanged: V1 source composition,
the M15 native build, the live adapter, finance observations, the bus-order
interface and the opt-in town-pair focus. Only the base graphics differ when
the official OpenGFX 8.0 archive cannot be downloaded: `--substitute-opengfx DIR`
packages an installed OpenGFX directory (Ubuntu's `openttd-opengfx`) into the
engine's base graphics slot with a sidecar declaring its real version and hash.
Base graphics do not enter game rules.

`trainer` builds the development C++ trainer (including `rl_dev_v2_imitation`)
for CPU. The PyPI Torch 2.9.1 wheel is CUDA-built and its CMake package demands
a CUDA toolkit, but its `libtorch_cpu.so` needs only two small CUDA runtime
libraries, which load without a GPU. This stage downloads the three pinned
wheels, extracts the C++ headers and libraries, and builds against a CPU-only
`TorchConfig.cmake` that links `libtorch_cpu` directly. CUDA requests still fail
explicitly at run time.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile

from local import OPENGFX_SHA256, ROOT, positive, source_identity, write_json


def obg_version(directory):
    text = (directory / "opengfx.obg").read_text(errors="replace")
    for line in text.splitlines():
        if line.startswith("description ") and "[OpenGFX " in line:
            return line.rsplit("[OpenGFX ", 1)[1].rstrip("]").strip()
    raise ValueError("OpenGFX descriptor lacks its release version")


def package_substitute(directory, target):
    """Write a byte-reproducible tar of an installed OpenGFX set and declare it."""
    directory = directory.resolve(strict=True)
    version = obg_version(directory)
    names = sorted(path.name for path in directory.iterdir()
                   if path.suffix in (".grf", ".obg") or path.name == "license.txt")
    if "opengfx.obg" not in names or not any(name.endswith(".grf") for name in names):
        raise ValueError("Substitute directory must contain opengfx.obg and its .grf files")
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in names:
            data = (directory / name).read_bytes()
            info = tarfile.TarInfo(f"opengfx-{version}/{name}")
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            archive.addfile(info, io.BytesIO(data))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(buffer.getvalue())
    declaration = {"schema_version": "openttd-rl-baseset-substitute-1",
                   "sha256": hashlib.sha256(buffer.getvalue()).hexdigest(),
                   "content": f"OpenGFX {version} from {directory}",
                   "files": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in names},
                   "official_sha256": OPENGFX_SHA256,
                   "reason": "Official OpenGFX 8.0 archive unavailable on this host; base graphics do not enter game rules"}
    write_json(target.with_name(target.name + ".substitute.json"), declaration)
    return declaration


WHEELS = {
    "torch-2.9.1-cp312-cp312-manylinux_2_28_x86_64.whl": (
        "https://files.pythonhosted.org/packages/19/17/e377a460603132b00760511299fceba4102bd95db1a0ee788da21298ccff/",
        "27331cd902fb4322252657f3902adf1c4f6acad9dcad81d8df3ae14c7c4f07c4"),
    "nvidia_cuda_runtime_cu12-12.8.90-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl": (
        "https://files.pythonhosted.org/packages/0d/9b/a997b638fcd068ad6e4d53b8551a7d30fe8b404d6f1804abf1df69838932/",
        "adade8dcbd0edf427b7204d480d6066d33902cab2a4707dcfc48a2d0fd44ab90"),
    "nvidia_cuda_cupti_cu12-12.8.90-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl": (
        "https://files.pythonhosted.org/packages/f8/02/2adcaa145158bf1a8295d83591d22e4103dbfd821bcaf6f3f53151ca4ffa/",
        "ea0cb07ebda26bb9b29ba82cda34849e73c166c18162d3913575b0c9db9a6182"),
}
TORCH_CONFIG = """# CPU-only view of the Torch 2.9.1 wheel's C++ libraries: no CUDA toolkit needed.
set(TORCH_INSTALL_PREFIX "{prefix}")
set(TORCH_INCLUDE_DIRS "${{TORCH_INSTALL_PREFIX}}/include" "${{TORCH_INSTALL_PREFIX}}/include/torch/csrc/api/include")
add_library(torch SHARED IMPORTED)
set_target_properties(torch PROPERTIES IMPORTED_LOCATION "${{TORCH_INSTALL_PREFIX}}/lib/libtorch_cpu.so"
  INTERFACE_INCLUDE_DIRECTORIES "${{TORCH_INCLUDE_DIRS}}" INTERFACE_LINK_LIBRARIES "${{TORCH_INSTALL_PREFIX}}/lib/libc10.so")
set(TORCH_LIBRARIES torch)
set(TORCH_CXX_FLAGS "")
set(Torch_FOUND TRUE)
"""


def fetch(name, cache):
    url, expected = WHEELS[name]
    path = cache / name
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".partial")
        urllib.request.urlretrieve(url + name, partial)
        partial.rename(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError(f"Pinned wheel hash differs: {name}")
    return path


def trainer(args):
    root = args.root.resolve()
    output = root / "torch-cpu"
    build = root / "build" / args.build_name
    if output.exists() or build.exists():
        raise ValueError("CPU Torch view or build directory exists; choose another --build-name or root")
    record = {"kind": "development-cloud-cpu-trainer", "status": "running", "source": source_identity(),
              "wheels": {name: sha for name, (_, sha) in WHEELS.items()}, "torch": str(output), "build": str(build),
              "claim": "C++ trainer linked to libtorch_cpu for CPU runs; CUDA requests fail explicitly"}
    record_path = root / f"cloud-trainer-{args.build_name}.json"
    write_json(record_path, record)
    started = time.monotonic()
    try:
        for name in WHEELS:
            with zipfile.ZipFile(fetch(name, args.wheel_cache.resolve())) as wheel:
                wanted = [entry for entry in wheel.namelist() if entry.startswith(("torch/include/", "torch/share/cmake/Torch/TorchConfigVersion"))
                          or entry in ("torch/lib/libtorch_cpu.so", "torch/lib/libc10.so", "torch/lib/libgomp.so.1")
                          or (entry.startswith("nvidia/") and "/lib/" in entry and ".so" in entry)]
                wheel.extractall(output, wanted)
        # libtorch_cpu's RPATH finds libcudart/libcupti in ../../nvidia/*/lib.
        package = output / "cmake/Torch"
        package.mkdir(parents=True)
        (package / "TorchConfig.cmake").write_text(TORCH_CONFIG.format(prefix=output / "torch"))
        (output / "torch/share/cmake/Torch/TorchConfigVersion.cmake").rename(package / "TorchConfigVersion.cmake")
        configure = ["cmake", "-S", str(ROOT / "training/dev"), "-B", str(build), "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                     "-DRL_DEV_CUDA_TESTS=OFF", "-DRL_DEV_FUSED_POLICY=OFF", "-DRL_DEV_V2_POLICY=ON",
                     f"-DCMAKE_PREFIX_PATH={output / 'cmake'}", "-DCMAKE_CXX_COMPILER_LAUNCHER=ccache"]
        for name, command in (("configure", configure), ("build", ["cmake", "--build", str(build), "--parallel", str(args.jobs)]),
                              ("test", ["ctest", "--test-dir", str(build), "--output-on-failure"])):
            with (root / f"cloud-trainer-{args.build_name}-{name}.log").open("w") as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            print(json.dumps({"trainer": name, "status": "passed"}), flush=True)
        imitation = build / "rl_dev_v2_imitation"
        record.update(status="built", imitation=str(imitation), imitation_sha256=hashlib.sha256(imitation.read_bytes()).hexdigest())
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        record["elapsed_seconds"] = round(time.monotonic() - started, 1)
        write_json(record_path, record)
    print(f"CPU imitation trainer: {record['imitation']}")


def engines(args):
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    record_path = root / "cloud-setup.json"
    if record_path.exists():
        raise ValueError(f"{record_path} exists; choose a new --root to keep earlier builds intact")
    paths = {"v1-source": root / "engine", "v2-native": root / "v2-live-engine", "finance": root / "v2-finance-engine",
             "bus-orders": root / "bus-orders-engine", "route-focus": root / "route-focus-engine"}
    baseset = root / "assets/opengfx-8.0.tar"
    record = {"kind": "development-cloud-cpu-engine", "status": "running", "source": source_identity(),
              "host": {"cpus": os.cpu_count(), "platform": sys.platform, "python": sys.version}, "jobs": args.jobs,
              "engines": {name: str(path) for name, path in paths.items()}, "stages": [],
              "claim": "Native OpenTTD engines for CPU game workers; no training or gameplay claim"}
    write_json(record_path, record)
    environment = os.environ.copy()
    # CMake 3.17+ reads these as default launchers; BASEDIR lets the isolated
    # copies of one source tree share cached objects across absolute paths.
    # OpenTTD's precompiled headers are only cacheable with this sloppiness.
    environment.update(CMAKE_C_COMPILER_LAUNCHER="ccache", CMAKE_CXX_COMPILER_LAUNCHER="ccache",
                       CCACHE_BASEDIR=str(root), CCACHE_NOHASHDIR="1",
                       CCACHE_SLOPPINESS="pch_defines,time_macros,include_file_mtime,include_file_ctime")
    python = sys.executable
    started = time.monotonic()

    def stage(name, command):
        began = time.monotonic()
        entry = {"name": name, "argv": command, "status": "running"}
        record["stages"].append(entry)
        write_json(record_path, record)
        with (root / f"cloud-{name}.log").open("w") as log:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
        entry.update(status="passed" if result.returncode == 0 else "failed", seconds=round(time.monotonic() - began, 1))
        write_json(record_path, record)
        print(json.dumps(entry), flush=True)
        if result.returncode:
            raise RuntimeError(f"Stage {name} failed; see {root / f'cloud-{name}.log'}")

    try:
        if args.official_opengfx:
            if hashlib.sha256(args.official_opengfx.read_bytes()).hexdigest() != OPENGFX_SHA256:
                raise ValueError("Supplied archive is not the official OpenGFX 8.0 release")
            baseset.parent.mkdir(parents=True, exist_ok=True)
            baseset.write_bytes(args.official_opengfx.read_bytes())
            record["baseset"] = {"sha256": OPENGFX_SHA256, "official_opengfx_8_0": True}
        else:
            record["baseset"] = {"official_opengfx_8_0": False,
                                 "substitute": package_substitute(args.substitute_opengfx, baseset)}
        dev = ROOT / "scripts/dev"
        stage("v1-source", [python, str(dev / "prepare_engine.py"), "--output", str(paths["v1-source"])])
        stage("v2-native", [python, str(dev / "prepare_v2.py"), "--base-source", str(paths["v1-source"] / "source"),
                            "--output", str(paths["v2-native"]), "--through", "m15-competence", "--build",
                            "--baseset", str(baseset), "--jobs", str(args.jobs)])
        stage("live-adapter", [python, str(dev / "enable_v2_live.py"), "--engine-root", str(paths["v2-native"]),
                               "--jobs", str(args.jobs)])
        stage("finance", [python, str(dev / "prepare_finance_v2.py"), "--base-engine-root", str(paths["v2-native"]),
                          "--engine-root", str(paths["finance"]), "--jobs", str(args.jobs), "--build-timeout", "7200"])
        stage("bus-orders", [python, str(dev / "prepare_bus_orders.py"), "--base-engine-root", str(paths["finance"]),
                             "--engine-root", str(paths["bus-orders"]), "--jobs", str(args.jobs)])
        stage("route-focus", [python, str(dev / "prepare_route_focus.py"), "--base-engine-root", str(paths["bus-orders"]),
                              "--engine-root", str(paths["route-focus"]), "--jobs", str(args.jobs)])
        engine = paths["route-focus"] / "build/openttd"
        record.update(status="built", openttd=str(engine),
                      openttd_sha256=hashlib.sha256(engine.read_bytes()).hexdigest())
    except BaseException as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        record["elapsed_seconds"] = round(time.monotonic() - started, 1)
        write_json(record_path, record)
    print(f"Route-focus engine: {record['openttd']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("engines")
    builder.add_argument("--root", type=Path, required=True, help="new directory for engines, logs and the setup record")
    source = builder.add_mutually_exclusive_group(required=True)
    source.add_argument("--official-opengfx", type=Path, help="the official opengfx-8.0.tar (SHA-256 checked)")
    source.add_argument("--substitute-opengfx", type=Path, help="installed OpenGFX directory, e.g. /usr/share/games/openttd/baseset/opengfx")
    builder.add_argument("--jobs", type=positive, default=os.cpu_count() or 2)
    learner = commands.add_parser("trainer")
    learner.add_argument("--root", type=Path, required=True)
    learner.add_argument("--build-name", default="v2-policy-cpu")
    learner.add_argument("--wheel-cache", type=Path, default=Path.home() / ".cache/openttd-rl-wheels")
    learner.add_argument("--jobs", type=positive, default=os.cpu_count() or 2)
    arguments = parser.parse_args()
    engines(arguments) if arguments.command == "engines" else trainer(arguments)
