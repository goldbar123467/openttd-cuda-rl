#!/usr/bin/env python3
"""Generate the complete M01 dependency provenance manifest offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
from typing import Any

import jsonschema


class ProvenanceError(ValueError):
    """A dependency, package, runtime provider, or license record was invalid."""


HEADLESS_IDENTITY = "102f07d8595673a06888bb935c809c47ea3326f8d66be158a1588e32ec530de3"
PLAYABLE_IDENTITY = "5e50757e298b5c241655663e94a5ce0dde0a69eb4e5d811c467fe2dc63cf3c7b"
SOURCE_PROFILE_SHA256 = "563339037626a8bb5a54e2f6a71e69500ccee44c11dfff2ce96bc4a96ef6c6cf"


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def load_json(path: pathlib.Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ProvenanceError(f"{path}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ProvenanceError(f"{path}: invalid JSON constant {value}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProvenanceError(f"cannot load {path}: {exc}") from exc


def run(command: list[str], label: str) -> str:
    environment = os.environ.copy()
    environment.update({"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC"})
    result = subprocess.run(
        command,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-20:])
        raise ProvenanceError(f"{label} failed with exit code {result.returncode}: {detail}")
    return result.stdout


def resolve_executable(name: str) -> pathlib.Path:
    value = shutil.which(name)
    if value is None:
        raise ProvenanceError(f"missing required offline metadata tool: {name}")
    path = pathlib.Path(value).resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ProvenanceError(f"invalid required offline metadata tool: {path}")
    return path


def parse_control(output: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current: str | None = None
    for line in output.splitlines():
        if not line:
            if fields:
                break
            continue
        if line[0].isspace() and current is not None:
            fields[current] += " " + line.strip()
        elif ":" in line:
            current, value = line.split(":", 1)
            fields[current] = value.strip()
    return fields


def apt_metadata(apt_cache: pathlib.Path, package: str, version: str) -> dict[str, str]:
    output = run([str(apt_cache), "show", f"{package}={version}"], f"apt metadata {package}")
    fields = parse_control(output)
    if fields.get("Package") != package or fields.get("Version") != version:
        raise ProvenanceError(
            f"APT metadata mismatch for {package}: expected={version} actual={fields.get('Version')}"
        )
    return fields


def package_source_url(fields: dict[str, str], package: str, source_package: str) -> str:
    homepage = fields.get("Homepage")
    if homepage and re.match(r"^https?://", homepage):
        return homepage
    return f"https://packages.ubuntu.com/source/noble/{source_package or package}"


def license_record(path: pathlib.Path) -> tuple[list[str], str]:
    if not path.is_file():
        raise ProvenanceError(f"package license evidence is missing: {path}")
    text = path.read_text(encoding="utf-8", errors="strict")
    declarations = sorted(
        {
            " ".join(match.group(1).split())
            for match in re.finditer(r"^License:\s*(.+?)\s*$", text, re.MULTILINE)
            if match.group(1).strip()
        }
    )
    if not declarations:
        declarations = ["LicenseRef-Debian-package-copyright-text"]
    return declarations, sha256_file(path)


def validate_file(path: pathlib.Path, size: int, digest: str, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ProvenanceError(f"{label} is missing or not a regular file: {path}")
    if path.stat().st_size != size:
        raise ProvenanceError(f"{label} size mismatch: {path.name}")
    if sha256_file(path) != digest:
        raise ProvenanceError(f"{label} SHA-256 mismatch: {path.name}")


def toolchain_records(lock: dict[str, Any], cache_root: pathlib.Path) -> list[dict[str, str]]:
    if len(lock.get("artifacts", [])) != 25:
        raise ProvenanceError("toolchain lock must contain exactly 25 artifacts")
    records: list[dict[str, str]] = []
    ids: set[str] = set()
    for artifact in lock["artifacts"]:
        identifier = artifact["id"]
        if identifier in ids:
            raise ProvenanceError(f"duplicate toolchain artifact: {identifier}")
        ids.add(identifier)
        path = cache_root / artifact["relative_cache_path"]
        validate_file(path, artifact["size_bytes"], artifact["sha256"], identifier)
        records.append(
            {
                "id": identifier,
                "component": artifact["component"],
                "version": artifact["version"],
                "sha256": artifact["sha256"],
                "source_url": artifact["url"],
                "license": artifact["license_expression"],
                "license_evidence": artifact["license_evidence"],
                "distribution_status": artifact["publication_disposition"],
            }
        )
    return sorted(records, key=lambda item: item["id"])


def deb_metadata(dpkg_deb: pathlib.Path, path: pathlib.Path) -> dict[str, str]:
    return parse_control(
        run(
            [
                str(dpkg_deb),
                "-f",
                str(path),
                "Package",
                "Version",
                "Architecture",
                "Source",
                "Homepage",
            ],
            f"DEB metadata {path.name}",
        )
    )


def package_contents(dpkg_deb: pathlib.Path, tar: pathlib.Path, path: pathlib.Path) -> set[str]:
    producer = subprocess.Popen(
        [str(dpkg_deb), "--fsys-tarfile", str(path)], stdout=subprocess.PIPE
    )
    assert producer.stdout is not None
    consumer = subprocess.run(
        [str(tar), "-tf", "-"],
        stdin=producer.stdout,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    producer.stdout.close()
    producer_code = producer.wait()
    if producer_code != 0 or consumer.returncode != 0:
        raise ProvenanceError(f"cannot list DEB contents: {path.name}: {consumer.stderr.strip()}")
    return {line.removeprefix("./").rstrip("/") for line in consumer.stdout.splitlines()}


def build_package_records(
    lock: dict[str, Any],
    cache_root: pathlib.Path,
    sysroot: pathlib.Path,
    apt_cache: pathlib.Path,
    dpkg_deb: pathlib.Path,
    tar: pathlib.Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    if len(lock.get("artifacts", [])) != 34:
        raise ProvenanceError("build-input lock must contain exactly 34 packages")
    records: list[dict[str, Any]] = []
    by_package: dict[str, dict[str, Any]] = {}
    file_owner: dict[str, str] = {}
    for artifact in lock["artifacts"]:
        path = cache_root / artifact["filename"]
        validate_file(path, artifact["size_bytes"], artifact["sha256"], artifact["package"])
        fields = deb_metadata(dpkg_deb, path)
        expected = {
            "Package": artifact["package"],
            "Version": artifact["version"],
            "Architecture": artifact["architecture"],
        }
        if any(fields.get(key) != value for key, value in expected.items()):
            raise ProvenanceError(
                f"DEB metadata mismatch for {path.name}: expected={expected} actual={fields}"
            )
        source_package = fields.get("Source", artifact["package"]).split(" ", 1)[0]
        apt_fields = apt_metadata(apt_cache, artifact["package"], artifact["version"])
        if apt_fields.get("SHA256") != artifact["sha256"]:
            raise ProvenanceError(f"APT/lock digest mismatch for {artifact['package']}")
        declarations, evidence_sha256 = license_record(
            sysroot / f"usr/share/doc/{artifact['package']}/copyright"
        )
        distribution = "locked-private-build-overlay; redistribution-requires-license-review"
        if artifact["package"] == "openttd-opengfx":
            distribution = "redistributable-GPL-2.0; retain-license-and-source-offer-obligations"
        record = {
            "package": artifact["package"],
            "source_package": source_package,
            "version": artifact["version"],
            "architecture": artifact["architecture"],
            "sha256": artifact["sha256"],
            "source_url": package_source_url(apt_fields, artifact["package"], source_package),
            "license_declarations": declarations,
            "license_evidence_sha256": evidence_sha256,
            "distribution_status": distribution,
        }
        if record["package"] in by_package:
            raise ProvenanceError(f"duplicate build package: {record['package']}")
        by_package[record["package"]] = record
        records.append(record)
        for member in package_contents(dpkg_deb, tar, path):
            previous = file_owner.get(member)
            if previous is not None and previous != artifact["package"]:
                continue
            file_owner[member] = artifact["package"]
    return sorted(records, key=lambda item: item["package"]), by_package, file_owner


def parse_ldd(path: pathlib.Path) -> list[tuple[str, pathlib.Path]]:
    dependencies: list[tuple[str, pathlib.Path]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "not found" in line:
            raise ProvenanceError(f"unresolved dependency in {path}: {line}")
        if line.startswith("linux-vdso"):
            continue
        if "=>" in line:
            soname, remainder = line.split("=>", 1)
            runtime_path = pathlib.Path(remainder.strip().split(" ", 1)[0])
        else:
            token = line.split(" ", 1)[0]
            if not token.startswith("/"):
                continue
            runtime_path = pathlib.Path(token)
            soname = runtime_path.name
        if not runtime_path.exists():
            raise ProvenanceError(f"runtime dependency path no longer exists: {runtime_path}")
        dependencies.append((soname.strip(), runtime_path.resolve()))
    if not dependencies:
        raise ProvenanceError(f"ldd log contains no file-backed dependencies: {path}")
    return dependencies


def installed_package(
    dpkg_query: pathlib.Path, apt_cache: pathlib.Path, runtime_path: pathlib.Path
) -> dict[str, str]:
    ownership = run(
        [str(dpkg_query), "-S", str(runtime_path)], f"package owner {runtime_path}"
    ).splitlines()
    owners = sorted(
        {
            line.split(": ", 1)[0]
            for line in ownership
            if ": " in line and not line.startswith("diversion by ")
        }
    )
    if len(owners) != 1:
        raise ProvenanceError(f"runtime file has ambiguous package ownership: {runtime_path}: {owners}")
    binary_package = owners[0]
    query = run(
        [
            str(dpkg_query),
            "-W",
            "-f=${binary:Package}|${Version}|${source:Package}|${source:Version}\\n",
            binary_package,
        ],
        f"installed package metadata {binary_package}",
    ).strip()
    values = query.split("|")
    if len(values) != 4 or not all(values):
        raise ProvenanceError(f"invalid installed package metadata: {query!r}")
    package_with_arch, version, source_package, _source_version = values
    package = package_with_arch.split(":", 1)[0]
    apt_fields = apt_metadata(apt_cache, package, version)
    declarations, evidence_sha256 = license_record(
        pathlib.Path("/usr/share/doc") / package / "copyright"
    )
    return {
        "package": package,
        "source_package": source_package,
        "version": version,
        "source_url": package_source_url(apt_fields, package, source_package),
        "license_declarations": declarations,
        "license_evidence_sha256": evidence_sha256,
    }


def runtime_records(
    roots: dict[str, pathlib.Path],
    by_package: dict[str, dict[str, Any]],
    file_owner: dict[str, str],
    apt_cache: pathlib.Path,
    dpkg_query: pathlib.Path,
) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for variant, root in roots.items():
        sysroot = (root / "sysroot").resolve()
        for soname, runtime_path in parse_ldd(root / "logs/openttd-ldd.log"):
            if runtime_path.is_relative_to(sysroot):
                relative = runtime_path.relative_to(sysroot).as_posix()
                package = file_owner.get(relative)
                if package is None:
                    raise ProvenanceError(
                        f"locked overlay runtime file has no package owner: {relative}"
                    )
                package_record = by_package[package]
                metadata = {
                    key: package_record[key]
                    for key in (
                        "package",
                        "source_package",
                        "version",
                        "source_url",
                        "license_declarations",
                        "license_evidence_sha256",
                    )
                }
                origin = "locked-build-overlay"
                distribution = package_record["distribution_status"]
            else:
                metadata = installed_package(dpkg_query, apt_cache, runtime_path)
                origin = "host-runtime"
                distribution = "host-provided-runtime; not included in project distribution"
            digest = sha256_file(runtime_path)
            candidate = {
                "soname": soname,
                "providers": [variant],
                "origin": origin,
                **metadata,
                "sha256": digest,
                "distribution_status": distribution,
            }
            previous = records.get(soname)
            if previous is None:
                records[soname] = candidate
                continue
            comparable = dict(previous)
            comparable.pop("providers")
            candidate_comparable = dict(candidate)
            candidate_comparable.pop("providers")
            if comparable != candidate_comparable:
                raise ProvenanceError(
                    f"runtime SONAME resolves to inconsistent providers across variants: {soname}"
                )
            if variant not in previous["providers"]:
                previous["providers"].append(variant)
                previous["providers"].sort()
    return [records[key] for key in sorted(records)]


def validate_manifest(manifest: dict[str, Any], schema_path: pathlib.Path) -> None:
    schema = load_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    try:
        jsonschema.Draft202012Validator(schema).validate(manifest)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(item) for item in exc.absolute_path) or "<root>"
        raise ProvenanceError(
            f"provenance schema validation failed at {location}: {exc.message}"
        ) from exc
    if len({item["id"] for item in manifest["toolchain_artifacts"]}) != 25:
        raise ProvenanceError("toolchain provenance IDs are not unique and complete")
    if len({item["package"] for item in manifest["build_overlay_packages"]}) != 34:
        raise ProvenanceError("build-overlay provenance packages are not unique and complete")
    opengfx = next(
        (
            item
            for item in manifest["build_overlay_packages"]
            if item["package"] == "openttd-opengfx"
        ),
        None,
    )
    if opengfx != manifest["opengfx"]:
        raise ProvenanceError("explicit OpenGFX provenance differs from its locked package")
    if not any(item["origin"] == "host-runtime" for item in manifest["runtime_dependencies"]):
        raise ProvenanceError("runtime provenance contains no host-provided dependencies")


def write_json(path: pathlib.Path, value: Any) -> None:
    if path.exists():
        raise ProvenanceError(f"refusing to overwrite output: {path}")
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_human(manifest: dict[str, Any]) -> str:
    host_count = sum(
        item["origin"] == "host-runtime" for item in manifest["runtime_dependencies"]
    )
    overlay_count = len(manifest["runtime_dependencies"]) - host_count
    return "\n".join(
        [
            "OpenTTD RL V1 dependency provenance",
            f"result: {manifest['result']}",
            f"toolchain artifacts: {len(manifest['toolchain_artifacts'])}",
            f"build-overlay packages: {len(manifest['build_overlay_packages'])}",
            "OpenGFX: present and explicitly licensed",
            f"runtime dependencies: {len(manifest['runtime_dependencies'])}",
            f"runtime dependencies from locked overlay: {overlay_count}",
            f"runtime dependencies from host: {host_count}",
            f"identity: {manifest['provenance_identity_sha256']}",
            "",
        ]
    )


def generate(options: argparse.Namespace) -> dict[str, Any]:
    artifact_root = options.artifact_root.resolve()
    if not artifact_root.is_dir() or any(artifact_root.iterdir()):
        raise ProvenanceError("artifact root must be an existing empty directory")
    dependency_lock = load_json(options.dependency_lock)
    build_lock = load_json(options.build_lock)
    headless_root = options.headless_root.resolve()
    playable_root = options.playable_root.resolve()
    headless_manifest = load_json(headless_root / "build-manifest.json")
    playable_manifest = load_json(playable_root / "build-manifest.json")
    if headless_manifest.get("build_identity_sha256") != HEADLESS_IDENTITY:
        raise ProvenanceError("headless accepted build identity mismatch")
    if playable_manifest.get("build_identity_sha256") != PLAYABLE_IDENTITY:
        raise ProvenanceError("playable accepted build identity mismatch")
    tools = {
        name: resolve_executable(name)
        for name in ("apt-cache", "dpkg-deb", "dpkg-query", "tar")
    }
    toolchain = toolchain_records(dependency_lock, options.dependency_cache.resolve())
    packages, by_package, file_owner = build_package_records(
        build_lock,
        options.build_cache.resolve(),
        playable_root / "sysroot",
        tools["apt-cache"],
        tools["dpkg-deb"],
        tools["tar"],
    )
    runtime = runtime_records(
        {"headless": headless_root, "playable": playable_root},
        by_package,
        file_owner,
        tools["apt-cache"],
        tools["dpkg-query"],
    )
    opengfx = next(item for item in packages if item["package"] == "openttd-opengfx")
    manifest_base = {
        "schema_version": "openttd-rl-v1-dependency-provenance-manifest-1",
        "inputs": {
            "dependency_lock_sha256": sha256_file(options.dependency_lock),
            "build_input_lock_sha256": sha256_file(options.build_lock),
            "headless_build_identity_sha256": HEADLESS_IDENTITY,
            "playable_build_identity_sha256": PLAYABLE_IDENTITY,
        },
        "openttd_source": {
            "id": "openttd",
            "version": "15.3",
            "sha256": SOURCE_PROFILE_SHA256,
            "source_url": "https://github.com/OpenTTD/OpenTTD",
            "license": "GPL-2.0-only",
            "distribution_status": "source-pinned; project patches require corresponding-source publication",
        },
        "toolchain_artifacts": toolchain,
        "build_overlay_packages": packages,
        "opengfx": opengfx,
        "runtime_dependencies": runtime,
        "result": "PASS",
    }
    manifest = dict(manifest_base)
    manifest["provenance_identity_sha256"] = hashlib.sha256(
        canonical_bytes(manifest_base)
    ).hexdigest()
    validate_manifest(manifest, options.schema)
    write_json(artifact_root / "dependency-provenance.json", manifest)
    (artifact_root / "dependency-provenance.txt").write_text(
        render_human(manifest), encoding="utf-8"
    )
    return manifest


def parse_args(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True, type=pathlib.Path)
    parser.add_argument("--dependency-cache", required=True, type=pathlib.Path)
    parser.add_argument("--build-cache", required=True, type=pathlib.Path)
    parser.add_argument("--headless-root", required=True, type=pathlib.Path)
    parser.add_argument("--playable-root", required=True, type=pathlib.Path)
    parser.add_argument("--dependency-lock", required=True, type=pathlib.Path)
    parser.add_argument("--build-lock", required=True, type=pathlib.Path)
    parser.add_argument("--schema", required=True, type=pathlib.Path)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        manifest = generate(options)
    except (ProvenanceError, OSError, UnicodeError) as exc:
        print(f"V1_DEPENDENCY_PROVENANCE=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "V1_DEPENDENCY_PROVENANCE=PASS "
        f"toolchain={len(manifest['toolchain_artifacts'])} "
        f"overlay={len(manifest['build_overlay_packages'])} "
        f"runtime={len(manifest['runtime_dependencies'])} "
        f"identity={manifest['provenance_identity_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
