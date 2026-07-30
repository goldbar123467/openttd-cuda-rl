#!/usr/bin/env python3
"""Fail-closed verifier for the frozen P0 Ubuntu dependency profile."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import pathlib
import platform
import re
import subprocess
import sys
from typing import Any


PYTHON_LOCK_LINE_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^ \\\r\n]+)\s+\\$", re.MULTILINE)


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def strict_json(path: pathlib.Path) -> Any:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 byte-order mark is forbidden")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)


def command_output(argv: list[str]) -> str:
    result = subprocess.run(argv, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise ValueError(f"command failed with exit {result.returncode}: {argv[0]}")
    return result.stdout.strip()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirements_lock(path: pathlib.Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    locked: dict[str, str] = {}
    for match in PYTHON_LOCK_LINE_RE.finditer(text):
        name = normalized_distribution_name(match.group(1))
        if name in locked:
            raise ValueError(f"duplicate Python distribution in requirements lock: {name}")
        locked[name] = match.group(2)
    if not locked:
        raise ValueError("requirements lock contains no exact hashed distributions")
    if "--hash=sha256:" not in text:
        raise ValueError("requirements lock omits SHA-256 artifact hashes")
    return locked


def os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in pathlib.Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        values[key] = raw_value.strip().strip('"')
    return values


def verify(
    profile: dict[str, Any],
    include_python: bool,
    requirements_lock: pathlib.Path | None,
    tools_python: pathlib.Path | None,
) -> dict[str, Any]:
    expected_platform = profile.get("platform")
    if not isinstance(expected_platform, dict):
        raise ValueError("dependency profile omits platform")
    release = os_release()
    actual_platform = {
        "architecture": platform.machine(),
        "os_id": release.get("ID", ""),
        "os_version": release.get("VERSION_ID", ""),
        "package_architecture": command_output(["dpkg", "--print-architecture"]),
    }
    if actual_platform != expected_platform:
        raise ValueError(f"platform drift: expected {expected_platform!r}, got {actual_platform!r}")

    packages = profile.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("dependency profile omits packages")
    checked: list[dict[str, str]] = []
    expected_python: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()
    for package in packages:
        if not isinstance(package, dict):
            raise ValueError("dependency package entry is not an object")
        manager = package.get("package_manager")
        name = package.get("binary_package")
        version = package.get("package_version")
        if not all(isinstance(item, str) and item for item in (manager, name, version)):
            raise ValueError("dependency package entry omits manager, name, or version")
        identity = (manager, name)
        if identity in seen:
            raise ValueError(f"duplicate dependency package identity: {manager}:{name}")
        seen.add(identity)
        if manager == "dpkg":
            fields = command_output(
                [
                    "dpkg-query",
                    "-W",
                    "-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\t${Status}",
                    name,
                ]
            ).split("\t")
            if len(fields) != 5:
                raise ValueError(f"unexpected dpkg-query output for {name}")
            actual_name, actual_version, actual_source, actual_source_version, status = fields
            if status != "install ok installed":
                raise ValueError(f"required package is not fully installed: {name} ({status!r})")
            expected = (
                name,
                version,
                package.get("source_package"),
                package.get("source_version"),
            )
            actual = (actual_name, actual_version, actual_source, actual_source_version)
            if actual != expected:
                raise ValueError(f"dpkg identity drift for {name}: expected {expected!r}, got {actual!r}")
            checked.append({"manager": manager, "name": name, "version": actual_version})
        elif manager == "python-distribution":
            normalized_name = normalized_distribution_name(name)
            if normalized_name in expected_python:
                raise ValueError(f"duplicate normalized Python distribution identity: {normalized_name}")
            expected_python[normalized_name] = version
            if include_python:
                actual_version = importlib.metadata.version(name)
                if actual_version != version:
                    raise ValueError(f"Python distribution drift for {name}: expected {version}, got {actual_version}")
                checked.append({"manager": manager, "name": name, "version": actual_version})
        else:
            raise ValueError(f"unsupported package manager in frozen profile: {manager}")
    result: dict[str, Any] = {
        "checked_packages": checked,
        "include_python_distributions": include_python,
        "platform": actual_platform,
        "profile": profile.get("profile"),
        "status": "PASS",
    }
    if include_python:
        python_profile = profile.get("python_environment")
        if not isinstance(python_profile, dict):
            raise ValueError("dependency profile omits the frozen Python environment")
        if requirements_lock is None or tools_python is None:
            raise ValueError("Python verification requires both the requirements lock and tools interpreter")
        lock_path = requirements_lock.absolute()
        interpreter_path = tools_python.absolute()
        if not lock_path.is_file() or lock_path.is_symlink():
            raise ValueError(f"requirements lock is absent or linked: {lock_path}")
        if not interpreter_path.is_file() or not os.access(interpreter_path, os.X_OK):
            raise ValueError(f"tools Python is absent or not executable: {interpreter_path}")
        actual_lock_sha256 = sha256_file(lock_path)
        if actual_lock_sha256 != python_profile.get("requirements_lock_sha256"):
            raise ValueError(
                "requirements lock drift: "
                f"expected {python_profile.get('requirements_lock_sha256')}, got {actual_lock_sha256}",
            )
        locked = parse_requirements_lock(lock_path)
        if locked != expected_python:
            raise ValueError(f"requirements lock distribution set drift: expected {expected_python!r}, got {locked!r}")
        installed: dict[str, str] = {}
        for distribution in importlib.metadata.distributions():
            raw_name = distribution.metadata.get("Name")
            if not isinstance(raw_name, str) or not raw_name:
                raise ValueError("installed Python distribution omits its canonical name")
            normalized_name = normalized_distribution_name(raw_name)
            if normalized_name in installed:
                raise ValueError(f"duplicate installed Python distribution identity: {normalized_name}")
            installed[normalized_name] = distribution.version
        if installed != expected_python:
            raise ValueError(f"installed Python distribution set drift: expected {expected_python!r}, got {installed!r}")
        if len(installed) != python_profile.get("distribution_count"):
            raise ValueError("installed Python distribution count differs from the frozen profile")
        observed_executable = pathlib.Path(sys.executable).absolute()
        expected_venv_root = interpreter_path.parent.parent
        if observed_executable != interpreter_path:
            raise ValueError(f"verifier interpreter drift: expected {interpreter_path}, got {observed_executable}")
        if pathlib.Path(sys.prefix).absolute() != expected_venv_root or sys.prefix == sys.base_prefix:
            raise ValueError("tools Python is not executing from the declared isolated virtual environment")
        if not (expected_venv_root / "pyvenv.cfg").is_file():
            raise ValueError("tools Python virtual environment omits pyvenv.cfg")
        base_executable = pathlib.Path(sys._base_executable).resolve(strict=True)
        if str(base_executable) != python_profile.get("base_executable"):
            raise ValueError(
                f"tools Python base executable drift: expected {python_profile.get('base_executable')}, got {base_executable}",
            )
        if platform.python_implementation() != python_profile.get("implementation"):
            raise ValueError("tools Python implementation differs from the frozen profile")
        if platform.python_version() != python_profile.get("interpreter_version"):
            raise ValueError("tools Python version differs from the frozen profile")
        result["python_environment"] = {
            "base_executable": str(base_executable),
            "base_executable_sha256": sha256_file(base_executable),
            "distributions": [
                {"name": name, "version": installed[name]} for name in sorted(installed)
            ],
            "implementation": platform.python_implementation(),
            "interpreter": str(interpreter_path),
            "interpreter_version": platform.python_version(),
            "requirements_lock": str(lock_path),
            "requirements_lock_sha256": actual_lock_sha256,
            "venv_root": str(expected_venv_root),
        }
    return result


def tool_version(name: str, path: str) -> str | None:
    if name in {"gcc", "g++"}:
        return command_output([path, "-dumpfullversion", "-dumpversion"])
    if name in {"ld", "objcopy", "readelf"}:
        first = command_output([path, "--version"]).splitlines()[0]
        match = re.search(r"\bGNU (ld|objcopy|readelf)(?: \([^)]*\))? ([0-9]+(?:\.[0-9]+)+)\b", first)
        return f"GNU {match.group(1)} {match.group(2)}" if match else None
    if name in {"cmake", "ctest"}:
        first = command_output([path, "--version"]).splitlines()[0]
        match = re.search(r" version ([0-9]+(?:\.[0-9]+)+)", first)
        return match.group(1) if match else None
    if name == "git":
        match = re.fullmatch(r"git version ([0-9]+(?:\.[0-9]+)+)(?:\..*)?", command_output([path, "--version"]))
        return match.group(1) if match else None
    if name == "python3":
        return command_output([path, "-c", "import platform; print(platform.python_version())"])
    if name in {"ninja", "pkg-config"}:
        return command_output([path, "--version"]).splitlines()[0]
    if name in {"clang-16", "clang-tidy-16", "llvm-cov-16"}:
        first = command_output([path, "--version"]).splitlines()[0]
        match = re.search(r" version ([0-9]+(?:\.[0-9]+)+)", first)
        return match.group(1) if match else None
    if name == "llvm-profdata-16":
        first = command_output([path, "merge", "--version"]).splitlines()[0]
        match = re.search(r" version ([0-9]+(?:\.[0-9]+)+)", first)
        return match.group(1) if match else None
    if name == "scan-build-16":
        # scan-build has no version option. Its exact dpkg/source identity below
        # is the fail-closed version authority; --help proves the entry point runs.
        command_output([path, "--help"])
        return None
    raise ValueError(f"unsupported tool in frozen toolchain profile: {name}")


def dpkg_owners(path: pathlib.Path) -> set[str]:
    output = command_output(["dpkg-query", "-S", str(path)])
    owners: set[str] = set()
    for line in output.splitlines():
        try:
            owner, listed_path = line.rsplit(": ", 1)
        except ValueError as exc:
            raise ValueError(f"malformed dpkg path ownership record: {line!r}") from exc
        if listed_path == str(path):
            owners.add(owner)
    if not owners:
        raise ValueError(f"no exact dpkg owner found for tool path: {path}")
    return owners


def verify_dpkg_files(package: str) -> None:
    result = subprocess.run(
        ["dpkg", "--verify", package],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0 or result.stdout or result.stderr:
        raise ValueError(f"dpkg file verification failed for {package}")


def verify_toolchain(profile: dict[str, Any]) -> list[dict[str, Any]]:
    tools = profile.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError("toolchain profile omits tools")
    checked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for tool in tools:
        if not isinstance(tool, dict):
            raise ValueError("toolchain entry is not an object")
        required = (
            "name", "path", "path_binary_package", "resolved_path", "resolved_binary_package", "sha256",
            "version", "binary_package", "package_version", "source_package", "source_version",
        )
        if not all(isinstance(tool.get(key), str) and tool[key] for key in required):
            raise ValueError("toolchain entry omits a required identity field")
        name = tool["name"]
        path = tool["path"]
        if name in seen:
            raise ValueError(f"duplicate toolchain name: {name}")
        seen.add(name)
        path_object = pathlib.Path(path)
        if not path_object.is_file() or not os.access(path, os.X_OK):
            raise ValueError(f"frozen tool path is absent or not executable: {path}")
        resolved_path = path_object.resolve(strict=True)
        if str(resolved_path) != tool["resolved_path"]:
            raise ValueError(f"resolved tool path drift for {name}: expected {tool['resolved_path']}, got {resolved_path}")
        path_owners = dpkg_owners(path_object)
        resolved_owners = dpkg_owners(resolved_path)
        if path_owners != {tool["path_binary_package"]}:
            raise ValueError(f"tool entry-point owner drift for {name}: expected {tool['path_binary_package']}, got {path_owners}")
        if resolved_owners != {tool["resolved_binary_package"]}:
            raise ValueError(
                f"resolved tool owner drift for {name}: expected {tool['resolved_binary_package']}, got {resolved_owners}",
            )
        observed_sha256 = sha256_file(resolved_path)
        if observed_sha256 != tool["sha256"]:
            raise ValueError(f"tool executable digest drift for {name}: expected {tool['sha256']}, got {observed_sha256}")

        fields = command_output(
            [
                "dpkg-query",
                "-W",
                "-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\t${Status}",
                tool["binary_package"],
            ]
        ).split("\t")
        if len(fields) != 5 or fields[4] != "install ok installed":
            raise ValueError(f"tool package is not fully installed: {tool['binary_package']}")
        expected_package = (
            tool["binary_package"], tool["package_version"], tool["source_package"], tool["source_version"],
        )
        if tuple(fields[:4]) != expected_package:
            raise ValueError(
                f"tool package drift for {name}: expected {expected_package!r}, got {tuple(fields[:4])!r}",
            )

        for package in sorted({tool["binary_package"], tool["path_binary_package"], tool["resolved_binary_package"]}):
            verify_dpkg_files(package)

        observed_version = tool_version(name, path)
        if observed_version is not None and observed_version != tool["version"]:
            raise ValueError(f"tool version drift for {name}: expected {tool['version']}, got {observed_version}")
        checked.append(
            {
                "name": name,
                "path": path,
                "path_binary_package": tool["path_binary_package"],
                "resolved_binary_package": tool["resolved_binary_package"],
                "resolved_path": str(resolved_path),
                "sha256": observed_sha256,
                "version": observed_version or tool["version"],
            }
        )
    return checked


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dependency-profile", required=True, type=pathlib.Path)
    parser.add_argument("--toolchain-profile", type=pathlib.Path)
    parser.add_argument("--include-python-distributions", action="store_true")
    parser.add_argument("--requirements-lock", type=pathlib.Path)
    parser.add_argument("--tools-python", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        profile = strict_json(args.dependency_profile)
        if not isinstance(profile, dict):
            raise ValueError("dependency profile must be an object")
        result = verify(profile, args.include_python_distributions, args.requirements_lock, args.tools_python)
        if args.toolchain_profile is not None:
            toolchain = strict_json(args.toolchain_profile)
            if not isinstance(toolchain, dict):
                raise ValueError("toolchain profile must be an object")
            result["checked_tools"] = verify_toolchain(toolchain)
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(encoded)
        else:
            os.write(sys.stdout.fileno(), encoded + b"\n")
    except (OSError, UnicodeError, ValueError, importlib.metadata.PackageNotFoundError) as exc:
        print(f"host profile verification failed: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
