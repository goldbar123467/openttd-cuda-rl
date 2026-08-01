#!/usr/bin/env python3
"""Validate the pinned V1 CUDA/LibTorch/ONNX toolchain completely offline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from email.parser import BytesParser
from typing import Any, Iterable

import jsonschema

import validate_dependency_cache


class ToolchainProbeError(ValueError):
    """A required tool, dependency, build product, or validation was invalid."""


EXPECTED_TESTS = (
    "v1-cuda-sm120-real-ptx",
    "v1-libtorch-cpu-cuda-abi",
    "v1-onnxruntime-cpu-abi",
    "v1-onnxruntime-opset18-graph",
)
EXPECTED_MODEL_SHA256 = "2d1bbd70474ae0eae9b97b3349b1285d09b8bca577487a67c24823cdbdc6b31d"
SCHEMA_VERSION = "openttd-rl-v1-toolchain-probe-manifest-1"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def resolve_executable(value: str, label: str) -> pathlib.Path:
    candidate = pathlib.Path(value)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        discovered = shutil.which(value)
        if discovered is None:
            raise ToolchainProbeError(f"missing required executable: {label} ({value})")
        resolved = pathlib.Path(discovered).resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ToolchainProbeError(
            f"required executable is not an executable regular file: {label} ({resolved})"
        )
    return resolved


def clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "CFLAGS",
        "CPPFLAGS",
        "CXXFLAGS",
        "CUDAFLAGS",
        "CMAKE_PREFIX_PATH",
        "CPATH",
        "LD_PRELOAD",
        "LIBRARY_PATH",
        "PIP_CONFIG_FILE",
        "PYTHONPATH",
        "PYTHONSTARTUP",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INDEX": "1",
            "PYTHONHASHSEED": "0",
            "TZ": "UTC",
        }
    )
    return environment


class CommandRunner:
    def __init__(self, log_directory: pathlib.Path, environment: dict[str, str]) -> None:
        self.log_directory = log_directory
        self.environment = environment
        self.log_directory.mkdir(parents=True, exist_ok=False)

    def run(
        self,
        label: str,
        command: list[str],
        *,
        cwd: pathlib.Path | None = None,
        environment: dict[str, str] | None = None,
        reject_warnings: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=self.environment if environment is None else environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        output = result.stdout
        if result.stderr:
            output += ("\n" if output and not output.endswith("\n") else "") + result.stderr
        log_path = self.log_directory / f"{label}.log"
        log_path.write_text(output, encoding="utf-8")
        if result.returncode != 0:
            detail = "\n".join(output.strip().splitlines()[-20:])
            raise ToolchainProbeError(
                f"{label} failed with exit code {result.returncode}; "
                f"see logs/{log_path.name}: {detail}"
            )
        if reject_warnings and re.search(r"(?:CMake Warning|\bwarning:)", output):
            detail = "\n".join(
                line for line in output.splitlines() if re.search(r"(?:CMake Warning|\bwarning:)", line)
            )
            raise ToolchainProbeError(
                f"{label} emitted a warning; see logs/{log_path.name}: {detail}"
            )
        return result


def require_exact(label: str, actual: str, expected: str) -> str:
    if actual != expected:
        raise ToolchainProbeError(
            f"{label} version mismatch: expected={expected} actual={actual}"
        )
    return actual


def require_regex(label: str, value: str, pattern: str) -> str:
    match = re.search(pattern, value, re.MULTILINE)
    if match is None:
        raise ToolchainProbeError(f"cannot parse {label} version from: {value.strip()}")
    return match.group(1)


def parse_os_release(path: pathlib.Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        fields[key] = value
    if "ID" not in fields or "VERSION_ID" not in fields:
        raise ToolchainProbeError("/etc/os-release lacks ID or VERSION_ID")
    return {"id": fields["ID"], "version_id": fields["VERSION_ID"]}


def parse_cpu_model(path: pathlib.Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("model name") and ":" in line:
            model = " ".join(line.split(":", 1)[1].split())
            if model:
                return model
    raise ToolchainProbeError("cannot detect CPU model from /proc/cpuinfo")


def parse_gpu_inventory(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(csv.reader(output.splitlines())):
        fields = [field.strip() for field in row]
        if len(fields) != 4 or not all(fields):
            raise ToolchainProbeError(f"invalid nvidia-smi inventory row: {row!r}")
        try:
            memory_mib = int(fields[2])
        except ValueError as exc:
            raise ToolchainProbeError(
                f"invalid nvidia-smi memory value: {fields[2]!r}"
            ) from exc
        rows.append(
            {
                "index": index,
                "name": fields[0],
                "compute_capability": fields[1],
                "memory_total_mib": memory_mib,
                "driver_version": fields[3],
            }
        )
    if not rows:
        raise ToolchainProbeError("nvidia-smi reported no GPUs")
    return rows


def wheel_distributions(
    cache_root: pathlib.Path,
    artifacts: Iterable[dict[str, Any]],
) -> list[dict[str, str]]:
    distributions: list[dict[str, str]] = []
    for artifact in artifacts:
        if not artifact["id"].startswith("exporter-"):
            continue
        wheel = cache_root / artifact["relative_cache_path"]
        try:
            with zipfile.ZipFile(wheel) as archive:
                metadata_names = [
                    name
                    for name in archive.namelist()
                    if name.count("/") == 1 and name.endswith(".dist-info/METADATA")
                ]
                if len(metadata_names) != 1:
                    raise ToolchainProbeError(
                        f"exporter wheel has {len(metadata_names)} top-level METADATA files: "
                        f"{artifact['relative_cache_path']}"
                    )
                metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        except (OSError, KeyError, zipfile.BadZipFile) as exc:
            raise ToolchainProbeError(f"cannot inspect exporter wheel {wheel}: {exc}") from exc
        name = metadata.get("Name")
        version = metadata.get("Version")
        if not name or not version:
            raise ToolchainProbeError(f"exporter wheel METADATA lacks Name or Version: {wheel}")
        require_exact(f"{artifact['id']} wheel", version, artifact["version"])
        distributions.append({"name": name, "version": version})
    if not distributions:
        raise ToolchainProbeError("dependency lock contains no exporter wheels")
    normalized = [entry["name"].lower().replace("_", "-") for entry in distributions]
    if len(normalized) != len(set(normalized)):
        raise ToolchainProbeError("exporter wheel distribution names are not unique")
    return sorted(distributions, key=lambda entry: entry["name"].lower())


def parse_ctest_inventory(output: str) -> list[str]:
    try:
        value = json.loads(output)
        names = sorted(test["name"] for test in value["tests"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ToolchainProbeError(f"invalid CTest JSON inventory: {exc}") from exc
    expected = list(EXPECTED_TESTS)
    if names != expected:
        raise ToolchainProbeError(
            f"CTest inventory mismatch: expected={expected} actual={names}"
        )
    return names


def parse_cuda_images(cubin_output: str, ptx_output: str) -> dict[str, list[str]]:
    cubin = sorted(set(re.findall(r"\.sm_([0-9]+)\.cubin\b", cubin_output)))
    # CUDA 13 cuobjdump labels a PTX entry with its `.target sm_NNN` value,
    # even when nvcc emitted it through code=compute_NNN.
    ptx = sorted(set(re.findall(r"\.(?:compute|sm)_([0-9]+)\.ptx\b", ptx_output)))
    if cubin != ["120"]:
        raise ToolchainProbeError(
            f"CUDA cubin image mismatch: expected=['120'] actual={cubin}"
        )
    if ptx != ["120"]:
        raise ToolchainProbeError(
            f"CUDA PTX image mismatch: expected=['120'] actual={ptx}"
        )
    return {"cubin_sm": cubin, "ptx_compute": ptx}


def validate_cuda_compile_commands(path: pathlib.Path) -> None:
    try:
        commands = json.loads(path.read_text(encoding="utf-8"))
        matches = [
            command
            for command in commands
            if pathlib.Path(command["file"]).name == "cuda_probe.cu"
        ]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ToolchainProbeError(f"cannot inspect CUDA compile commands: {exc}") from exc
    if len(matches) != 1:
        raise ToolchainProbeError(
            f"expected one cuda_probe.cu compile command, found {len(matches)}"
        )
    value = matches[0].get("command")
    if not isinstance(value, str):
        arguments = matches[0].get("arguments")
        if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
            raise ToolchainProbeError("CUDA compile command has neither command nor arguments")
        value = " ".join(arguments)
    for expected in (
        "arch=compute_120,code=[sm_120]",
        "arch=compute_120,code=[compute_120]",
    ):
        if expected not in value:
            raise ToolchainProbeError(f"CUDA compile command lacks required target: {expected}")


def parse_runtime_dependencies(output: str) -> list[str]:
    dependencies: set[str] = set()
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "not found" in line:
            raise ToolchainProbeError(f"unresolved runtime dependency: {line}")
        if "=>" in line:
            soname = line.split("=>", 1)[0].strip()
        else:
            token = line.split(" ", 1)[0]
            if token.startswith("/"):
                soname = pathlib.Path(token).name
            elif token.startswith("linux-vdso"):
                soname = token
            else:
                continue
        if soname:
            dependencies.add(soname)
    if not dependencies:
        raise ToolchainProbeError("ldd returned no runtime dependencies")
    return sorted(dependencies)


def validate_installed_distributions(
    runner: CommandRunner,
    python: pathlib.Path,
    expected: list[dict[str, str]],
) -> None:
    program = (
        "import importlib.metadata,json,sys;"
        "expected=json.loads(sys.argv[1]);"
        "actual=[{'name':x['name'],'version':importlib.metadata.version(x['name'])} for x in expected];"
        "print(json.dumps(actual,sort_keys=True,separators=(',',':')))"
    )
    result = runner.run(
        "exporter-inventory",
        [str(python), "-I", "-c", program, json.dumps(expected, separators=(",", ":"))],
    )
    try:
        actual = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ToolchainProbeError("exporter inventory did not emit JSON") from exc
    if actual != expected:
        raise ToolchainProbeError(
            f"installed exporter inventory mismatch: expected={expected} actual={actual}"
        )


def build_manifest(base: dict[str, Any]) -> dict[str, Any]:
    manifest = dict(base)
    manifest["probe_identity_sha256"] = sha256_bytes(canonical_bytes(base))
    return manifest


def validate_manifest(
    manifest: dict[str, Any], schema: dict[str, Any], schema_path: pathlib.Path
) -> None:
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        ).validate(manifest)
    except jsonschema.exceptions.SchemaError as exc:
        raise ToolchainProbeError(f"toolchain manifest schema is invalid: {exc.message}") from exc
    except jsonschema.exceptions.ValidationError as exc:
        raise ToolchainProbeError(
            f"toolchain manifest validation failed: {exc.message}"
        ) from exc
    if manifest["schema_sha256"] != sha256_file(schema_path):
        raise ToolchainProbeError("toolchain manifest schema digest mismatch")
    identity_payload = dict(manifest)
    actual_identity = identity_payload.pop("probe_identity_sha256")
    expected_identity = sha256_bytes(canonical_bytes(identity_payload))
    if actual_identity != expected_identity:
        raise ToolchainProbeError(
            f"toolchain manifest identity mismatch: expected={expected_identity} "
            f"actual={actual_identity}"
        )


def render_human_report(manifest: dict[str, Any]) -> str:
    tools = manifest["tools"]
    gpu = manifest["host"]["gpus"][0]
    dependencies = manifest["dependencies"]
    products = manifest["products"]
    lines = [
        "OpenTTD RL V1 toolchain probe",
        f"result: {manifest['result']}",
        f"profile: {manifest['profile_id']}",
        f"host: {manifest['host']['os']['id']} {manifest['host']['os']['version_id']} "
        f"{manifest['host']['architecture']}",
        f"compiler: GCC {tools['gcc']} / G++ {tools['gxx']}",
        f"build tools: CMake {tools['cmake']}, CTest {tools['ctest']}, Ninja {tools['ninja']}",
        f"CUDA: nvcc {tools['nvcc']}, cuobjdump {tools['cuobjdump']}",
        f"GPU 0: {gpu['name']} (compute {gpu['compute_capability']}, driver {gpu['driver_version']})",
        f"LibTorch: {dependencies['libtorch']['version']} (C++11 ABI {dependencies['libtorch']['cxx11_abi']})",
        f"ONNX Runtime: {dependencies['onnxruntime']['version']} CPU",
        f"exporter: Python {tools['python']}, {len(dependencies['exporter'])} locked distributions",
        f"ONNX model: opset {products['onnx_model']['opset']}, sha256 {products['onnx_model']['sha256']}",
        "CUDA images: cubin sm_120, PTX compute_120",
        f"native tests: {len(manifest['tests'])}/{len(manifest['tests'])} PASS",
        f"dependency artifacts: {dependencies['cache']['artifact_count']} "
        f"({dependencies['cache']['total_artifact_bytes']} bytes)",
        f"identity: {manifest['probe_identity_sha256']}",
    ]
    return "\n".join(lines) + "\n"


def write_new(path: pathlib.Path, content: str) -> None:
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ToolchainProbeError(f"refusing to overwrite output: {path}") from exc


def extraction_root(lock: dict[str, Any], cache_root: pathlib.Path, artifact_id: str) -> pathlib.Path:
    matches = [item for item in lock["extractions"] if item["artifact_id"] == artifact_id]
    if len(matches) != 1:
        raise ToolchainProbeError(
            f"dependency lock must contain exactly one extraction for {artifact_id}"
        )
    return (cache_root / matches[0]["relative_root"]).resolve()


def probe(options: argparse.Namespace) -> dict[str, Any]:
    root = options.root.resolve()
    artifact_root = options.artifact_root.resolve()
    cache_root = options.cache_root.resolve()
    lock_path = options.lock.resolve()
    dependency_schema_path = options.dependency_schema.resolve()
    manifest_schema_path = options.manifest_schema.resolve()
    if not artifact_root.is_absolute() or not artifact_root.is_dir():
        raise ToolchainProbeError("artifact root must be an existing absolute directory")
    if any(artifact_root.iterdir()):
        raise ToolchainProbeError(f"artifact root must be empty: {artifact_root}")

    logs = artifact_root / "logs"
    runner = CommandRunner(logs, clean_environment())
    tools = {
        name: resolve_executable(getattr(options, name), name)
        for name in ("cmake", "ctest", "cuobjdump", "gcc", "gxx", "ldd", "ninja", "nvidia_smi", "nvcc", "python")
    }

    lock = validate_dependency_cache.load_strict_json(lock_path)
    cache_validation = validate_dependency_cache.validate(
        lock_path=lock_path,
        schema_path=dependency_schema_path,
        cache_root=cache_root,
    )
    host_pin = lock["host"]

    architecture = platform.machine()
    require_exact("host architecture", architecture, host_pin["architecture"])
    os_record = parse_os_release(pathlib.Path("/etc/os-release"))
    require_exact("host OS", os_record["id"], "ubuntu")
    require_exact("host OS release", os_record["version_id"], "24.04")

    gcc_version = runner.run("gcc-version", [str(tools["gcc"]), "-dumpfullversion"]).stdout.strip()
    gxx_version = runner.run("gxx-version", [str(tools["gxx"]), "-dumpfullversion"]).stdout.strip()
    expected_gcc = host_pin["cxx"].removeprefix("GCC ")
    require_exact("GCC", gcc_version, expected_gcc)
    require_exact("G++", gxx_version, expected_gcc)
    cmake_version = require_regex(
        "CMake",
        runner.run("cmake-version", [str(tools["cmake"]), "--version"]).stdout,
        r"^cmake version ([0-9.]+)$",
    )
    ctest_version = require_regex(
        "CTest",
        runner.run("ctest-version", [str(tools["ctest"]), "--version"]).stdout,
        r"^ctest version ([0-9.]+)$",
    )
    ninja_version = runner.run("ninja-version", [str(tools["ninja"]), "--version"]).stdout.strip()
    nvcc_output = runner.run("nvcc-version", [str(tools["nvcc"]), "--version"]).stdout
    cuobjdump_output = runner.run(
        "cuobjdump-version", [str(tools["cuobjdump"]), "--version"]
    ).stdout
    nvcc_version = require_regex("nvcc", nvcc_output, r"\bV([0-9.]+)\b")
    cuobjdump_version = require_regex("cuobjdump", cuobjdump_output, r"\bV([0-9.]+)\b")
    python_version = require_regex(
        "Python",
        runner.run("python-version", [str(tools["python"]), "--version"]).stdout,
        r"^Python ([0-9.]+)$",
    )
    glibc_version = require_regex(
        "glibc",
        runner.run("ldd-version", [str(tools["ldd"]), "--version"]).stdout,
        r"\) ([0-9.]+)$",
    )
    require_exact("CMake", cmake_version, host_pin["cmake"])
    require_exact("CTest", ctest_version, host_pin["cmake"])
    require_exact("Ninja", ninja_version, host_pin["ninja"])
    require_exact("nvcc", nvcc_version, host_pin["cuda"])
    require_exact("cuobjdump", cuobjdump_version, "13.0.85")
    require_exact("Python major/minor", ".".join(python_version.split(".")[:2]), host_pin["python"])

    gpu_output = runner.run(
        "nvidia-smi",
        [
            str(tools["nvidia_smi"]),
            "--query-gpu=name,compute_cap,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ],
    ).stdout
    gpus = parse_gpu_inventory(gpu_output)
    require_exact("GPU 0 compute capability", gpus[0]["compute_capability"], host_pin["gpu_cc"])

    libtorch_root = extraction_root(lock, cache_root, "libtorch-cu130")
    ort_root = extraction_root(lock, cache_root, "onnxruntime-cpu")
    runtime_root = extraction_root(lock, cache_root, "nvidia-cudnn-cu13")
    for artifact_id in (
        "nvidia-cusparselt-cu13",
        "nvidia-nccl-cu13",
        "nvidia-nvshmem-cu13",
    ):
        if extraction_root(lock, cache_root, artifact_id) != runtime_root:
            raise ToolchainProbeError("locked NVIDIA runtime extractions do not share one root")
    libtorch_version = (libtorch_root / "build-version").read_text(encoding="utf-8").strip()
    ort_version = (ort_root / "VERSION_NUMBER").read_text(encoding="utf-8").strip()
    require_exact("LibTorch", libtorch_version, "2.13.0+cu130")
    require_exact("ONNX Runtime", ort_version, "1.28.0")

    exporter = wheel_distributions(cache_root, lock["artifacts"])
    exporter_environment = artifact_root / "exporter-environment"
    runner.run(
        "exporter-venv",
        [str(tools["python"]), "-m", "venv", "--copies", str(exporter_environment)],
    )
    exporter_python = exporter_environment / "bin/python"
    wheel_paths = [
        str(cache_root / artifact["relative_cache_path"])
        for artifact in lock["artifacts"]
        if artifact["id"].startswith("exporter-")
    ]
    runner.run(
        "exporter-install",
        [
            str(exporter_python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--no-cache-dir",
            *wheel_paths,
        ],
    )
    runner.run("exporter-pip-check", [str(exporter_python), "-m", "pip", "check"])
    validate_installed_distributions(runner, exporter_python, exporter)

    model = artifact_root / "probe-model.onnx"
    runner.run(
        "onnx-export",
        [
            str(exporter_python),
            str(root / "tests/project/toolchain/export_probe.py"),
            "--output",
            str(model),
        ],
    )
    model_sha256 = sha256_file(model)
    require_exact("exported ONNX model digest", model_sha256, EXPECTED_MODEL_SHA256)

    native_build = artifact_root / "native-build"
    cmake_command = [
        str(tools["cmake"]),
        "-S",
        str(root / "tests/project/toolchain"),
        "-B",
        str(native_build),
        "-G",
        "Ninja",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        f"-DCMAKE_CXX_COMPILER={tools['gxx']}",
        f"-DCMAKE_CUDA_COMPILER={tools['nvcc']}",
        f"-DCMAKE_MAKE_PROGRAM={tools['ninja']}",
        f"-DCUDAToolkit_ROOT={options.cuda_root.resolve()}",
        f"-DTorch_DIR={libtorch_root / 'share/cmake/Torch'}",
        f"-DV1_NVIDIA_RUNTIME_ROOT={runtime_root}",
        f"-DONNXRUNTIME_ROOT={ort_root}",
        f"-DV1_ONNX_PROBE_MODEL={model}",
    ]
    runner.run("cmake-configure", cmake_command, reject_warnings=True)
    runner.run(
        "cmake-build",
        [str(tools["cmake"]), "--build", str(native_build), "--parallel", "2"],
        reject_warnings=True,
    )
    validate_cuda_compile_commands(native_build / "compile_commands.json")
    ctest_inventory = runner.run(
        "ctest-inventory",
        [str(tools["ctest"]), "--test-dir", str(native_build), "--show-only=json-v1"],
    )
    test_names = parse_ctest_inventory(ctest_inventory.stdout)
    runner.run(
        "ctest",
        [
            str(tools["ctest"]),
            "--test-dir",
            str(native_build),
            "--output-on-failure",
            "--no-tests=error",
        ],
    )

    cuda_binary = native_build / "v1_cuda_probe"
    cubin_output = runner.run(
        "cuda-list-cubin", [str(tools["cuobjdump"]), "--list-elf", str(cuda_binary)]
    ).stdout
    ptx_output = runner.run(
        "cuda-list-ptx", [str(tools["cuobjdump"]), "--list-ptx", str(cuda_binary)]
    ).stdout
    cuda_images = parse_cuda_images(cubin_output, ptx_output)

    runtime_environment = runner.environment.copy()
    library_directories = [
        libtorch_root / "lib",
        ort_root / "lib",
        runtime_root / "nvidia/cudnn/lib",
        runtime_root / "nvidia/cusparselt/lib",
        runtime_root / "nvidia/nccl/lib",
        runtime_root / "nvidia/nvshmem/lib",
    ]
    runtime_environment["LD_LIBRARY_PATH"] = ":".join(str(path) for path in library_directories)
    runtime_dependencies: dict[str, list[str]] = {}
    binary_hashes: dict[str, str] = {}
    for binary_name in ("v1_cuda_probe", "v1_libtorch_probe", "v1_onnxruntime_probe"):
        binary = native_build / binary_name
        if not binary.is_file():
            raise ToolchainProbeError(f"native build did not produce {binary_name}")
        binary_hashes[binary_name] = sha256_file(binary)
        ldd_result = runner.run(
            f"ldd-{binary_name}", [str(tools["ldd"]), str(binary)], environment=runtime_environment
        )
        runtime_dependencies[binary_name] = parse_runtime_dependencies(ldd_result.stdout)

    probe_sources = []
    for relative in (
        "scripts/v1/run_toolchain_probe.py",
        "scripts/v1/toolchain_probe.sh",
        "tests/project/toolchain/CMakeLists.txt",
        "tests/project/toolchain/cuda_probe.cu",
        "tests/project/toolchain/export_probe.py",
        "tests/project/toolchain/libtorch_probe.cpp",
        "tests/project/toolchain/onnxruntime_probe.cpp",
    ):
        source = root / relative
        probe_sources.append({"path": relative, "sha256": sha256_file(source)})

    artifacts_by_id = {artifact["id"]: artifact for artifact in lock["artifacts"]}
    manifest_schema = validate_dependency_cache.load_strict_json(manifest_schema_path)
    base_manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "schema_sha256": sha256_file(manifest_schema_path),
        "profile_id": lock["profile_id"],
        "inputs": {
            "dependency_lock_sha256": cache_validation["lock_sha256"],
            "dependency_schema_sha256": cache_validation["schema_sha256"],
            "probe_sources": probe_sources,
        },
        "host": {
            "architecture": architecture,
            "os": os_record,
            "cpu_model": parse_cpu_model(pathlib.Path("/proc/cpuinfo")),
            "gpus": gpus,
        },
        "tools": {
            "gcc": gcc_version,
            "gxx": gxx_version,
            "cmake": cmake_version,
            "ctest": ctest_version,
            "ninja": ninja_version,
            "nvcc": nvcc_version,
            "cuobjdump": cuobjdump_version,
            "python": python_version,
            "glibc": glibc_version,
        },
        "dependencies": {
            "cache": {
                "artifact_count": cache_validation["artifact_count"],
                "extraction_count": cache_validation["extraction_count"],
                "total_artifact_bytes": cache_validation["total_artifact_bytes"],
                "result": cache_validation["result"],
            },
            "libtorch": {
                "version": libtorch_version,
                "cuda": "13.0",
                "cxx11_abi": 1,
                "result": "PASS",
            },
            "onnxruntime": {
                "version": ort_version,
                "provider": "CPUExecutionProvider",
                "result": "PASS",
            },
            "nvidia_runtime": [
                {
                    "id": artifact_id,
                    "version": artifacts_by_id[artifact_id]["version"],
                }
                for artifact_id in (
                    "nvidia-cudnn-cu13",
                    "nvidia-cusparselt-cu13",
                    "nvidia-nccl-cu13",
                    "nvidia-nvshmem-cu13",
                )
            ],
            "exporter": exporter,
        },
        "cmake": {
            "generator": "Ninja",
            "build_type": "Release",
            "cxx_standard": 20,
            "cuda_standard": 20,
            "cuda_architectures": ["120-real", "120-virtual"],
            "required_components": [
                "CUDAToolkit::cudart",
                "LibTorch::Torch",
                "NVIDIA::cuDNN",
                "NVIDIA::cuSPARSELt",
                "NVIDIA::NCCL",
                "NVIDIA::NVSHMEM",
                "ONNXRuntime::CPU",
            ],
            "result": "PASS",
        },
        "products": {
            "onnx_model": {
                "opset": 18,
                "operators": ["Add", "MatMul", "Relu"],
                "sha256": model_sha256,
            },
            "native_binaries": [
                {"name": name, "sha256": binary_hashes[name]} for name in sorted(binary_hashes)
            ],
            "cuda_images": cuda_images,
            "runtime_dependencies": runtime_dependencies,
        },
        "tests": [{"name": name, "result": "PASS"} for name in test_names],
        "result": "PASS",
    }
    manifest = build_manifest(base_manifest)
    validate_manifest(manifest, manifest_schema, manifest_schema_path)
    write_new(
        artifact_root / "toolchain-probe.json",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    write_new(artifact_root / "toolchain-probe.txt", render_human_report(manifest))
    return manifest


def parse_args(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--artifact-root", required=True, type=pathlib.Path)
    parser.add_argument("--cache-root", required=True, type=pathlib.Path)
    parser.add_argument("--lock", required=True, type=pathlib.Path)
    parser.add_argument("--dependency-schema", required=True, type=pathlib.Path)
    parser.add_argument("--manifest-schema", required=True, type=pathlib.Path)
    parser.add_argument("--cuda-root", default="/usr/local/cuda-13.0", type=pathlib.Path)
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--ctest", default="ctest")
    parser.add_argument("--cuobjdump", default="/usr/local/cuda-13.0/bin/cuobjdump")
    parser.add_argument("--gcc", default="gcc")
    parser.add_argument("--gxx", default="g++")
    parser.add_argument("--ldd", default="ldd")
    parser.add_argument("--ninja", default="ninja")
    parser.add_argument("--nvidia-smi", dest="nvidia_smi", default="nvidia-smi")
    parser.add_argument("--nvcc", default="/usr/local/cuda-13.0/bin/nvcc")
    parser.add_argument("--python", default="python3")
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        manifest = probe(options)
    except (
        ToolchainProbeError,
        validate_dependency_cache.DependencyCacheError,
        OSError,
        UnicodeError,
    ) as exc:
        print(f"V1_TOOLCHAIN_PROBE=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "V1_TOOLCHAIN_PROBE=PASS "
        f"profile={manifest['profile_id']} "
        f"tests={len(manifest['tests'])} "
        f"identity={manifest['probe_identity_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
