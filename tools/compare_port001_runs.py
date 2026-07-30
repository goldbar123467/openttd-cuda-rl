#!/usr/bin/env python3
"""Compare two clean PORT-001 reconstructions and emit canonical evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import rfc8785


EXPECTED_SUBMODULE = "29f808ef0022064e6d9a83c8476d1e0f4686af86"
EXPECTED_BRANCH = "port/p0-oracle-contract"
STAGE_RESULTS = (
    "preflight.json",
    "configure-reference.json",
    "fetch-opengfx.json",
    "build-reference.json",
    "test-reference.json",
    "smoke-reference.json",
)


class ComparisonError(ValueError):
    """Raised when a mandatory reconstruction equality is not established."""


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ComparisonError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_json(path: pathlib.Path) -> Any:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ComparisonError(f"JSON contains a forbidden UTF-8 BOM: {path}")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicates)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return rfc8785.dumps(value)


def canonical_digest(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def write_canonical(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def artifact(name: str, path: pathlib.Path, relative_path: str, media_type: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "name": name,
        "relative_path": relative_path,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }
    if media_type is not None:
        value["media_type"] = media_type
    return value


def require_pass_results(run_root: pathlib.Path) -> None:
    for name in STAGE_RESULTS:
        path = run_root / "results" / name
        value = load_json(path)
        if (
            not isinstance(value, dict)
            or value.get("status") != "PASS"
            or type(value.get("return_code")) is not int
            or value["return_code"] != 0
        ):
            raise ComparisonError(f"required stage result is not PASS: {path}")


def require_canonical_manifest(path: pathlib.Path) -> dict[str, Any]:
    value = load_json(path)
    if not isinstance(value, dict):
        raise ComparisonError(f"manifest is not an object: {path}")
    if path.read_bytes() != canonical_bytes(value):
        raise ComparisonError(f"manifest is not in canonical RFC 8785 byte form: {path}")
    if value.get("status") != "PASS" or value.get("return_code") != 0:
        raise ComparisonError(f"manifest is not PASS: {path}")
    return value


def run_command(argv: list[str], output: pathlib.Path) -> str:
    result = subprocess.run(argv, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output.write_bytes(result.stdout)
    if result.returncode != 0:
        raise ComparisonError(f"binary inspection command failed with exit {result.returncode}: {argv[0]}")
    return result.stdout.decode("utf-8", errors="replace")


def build_id(text: str) -> str | None:
    match = re.search(r"Build ID: ([0-9a-f]+)", text)
    return match.group(1) if match else None


def inspect_binaries(run_a: pathlib.Path, run_b: pathlib.Path, output_root: pathlib.Path) -> dict[str, Any]:
    executable_a = run_a / "install/games/openttd"
    executable_b = run_b / "install/games/openttd"
    for path in (executable_a, executable_b):
        if not path.is_file() or path.is_symlink() or not os.access(path, os.X_OK):
            raise ComparisonError(f"installed executable is absent, linked, or not executable: {path}")

    output_root.mkdir(parents=True, exist_ok=True)
    notes_a_path = output_root / "run-a.readelf-notes.txt"
    notes_b_path = output_root / "run-b.readelf-notes.txt"
    sections_a_path = output_root / "run-a.readelf-sections.txt"
    sections_b_path = output_root / "run-b.readelf-sections.txt"
    notes_a = run_command(["/usr/bin/readelf", "-nW", str(executable_a)], notes_a_path)
    notes_b = run_command(["/usr/bin/readelf", "-nW", str(executable_b)], notes_b_path)
    run_command(["/usr/bin/readelf", "-SW", str(executable_a)], sections_a_path)
    run_command(["/usr/bin/readelf", "-SW", str(executable_b)], sections_b_path)

    stripped_a = output_root / "run-a.stripped-no-build-id"
    stripped_b = output_root / "run-b.stripped-no-build-id"
    shutil.copyfile(executable_a, stripped_a)
    shutil.copyfile(executable_b, stripped_b)
    for path in (stripped_a, stripped_b):
        result = subprocess.run(
            ["/usr/bin/objcopy", "--strip-debug", "--remove-section=.note.gnu.build-id", str(path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            raise ComparisonError(f"objcopy binary inspection failed for {path}: exit {result.returncode}")

    stripped_a_bytes = stripped_a.read_bytes()
    stripped_b_bytes = stripped_b.read_bytes()
    root_a = str(run_a).encode("utf-8")
    root_b = str(run_b).encode("utf-8")
    normalized_equal = False
    normalized_a_sha: str | None = None
    normalized_b_sha: str | None = None
    normalization_occurrences = [stripped_a_bytes.count(root_a), stripped_b_bytes.count(root_b)]
    if len(root_a) == len(root_b):
        replacement = b"$RUN_ROOT" + (b"_" * (len(root_a) - len(b"$RUN_ROOT")))
        normalized_a = stripped_a_bytes.replace(root_a, replacement)
        normalized_b = stripped_b_bytes.replace(root_b, replacement)
        normalized_a_sha = sha256_bytes(normalized_a)
        normalized_b_sha = sha256_bytes(normalized_b)
        normalized_equal = normalized_a == normalized_b

    raw_a_sha = sha256_file(executable_a)
    raw_b_sha = sha256_file(executable_b)
    raw_equal = raw_a_sha == raw_b_sha and executable_a.stat().st_size == executable_b.stat().st_size
    if raw_equal:
        claim = "byte-identical under the frozen profile"
        classification = "BYTE_IDENTICAL"
        explanation = "The complete installed executable bytes and sizes are equal."
    elif normalized_equal:
        claim = "behaviorally reproduced under the frozen profile"
        classification = "BEHAVIORAL_PATH_NORMALIZED_CODE_DATA_EQUAL"
        explanation = (
            "Raw executables differ. Build IDs and debug data reflect distinct generated roots; after stripping debug data and "
            "the GNU build-id note and replacing equal-length run-root strings, the remaining bytes are identical."
        )
    else:
        claim = "behaviorally reproduced under the frozen profile"
        classification = "BEHAVIORAL_ONLY"
        explanation = (
            "Raw executables differ and equivalent readelf/objcopy inspection did not establish byte identity after debug, "
            "build-id, and equal-length generated-root normalization. No binary reproducibility claim is made."
        )

    return {
        "acceptable": raw_equal or normalized_equal,
        "claim": claim,
        "classification": classification,
        "explanation": explanation,
        "raw": {
            "equal": raw_equal,
            "run_a": {"sha256": raw_a_sha, "size_bytes": executable_a.stat().st_size},
            "run_b": {"sha256": raw_b_sha, "size_bytes": executable_b.stat().st_size},
        },
        "inspection": {
            "build_ids": {"run_a": build_id(notes_a), "run_b": build_id(notes_b)},
            "normalization_occurrences": {"run_a": normalization_occurrences[0], "run_b": normalization_occurrences[1]},
            "normalized_non_debug_equal": normalized_equal,
            "normalized_non_debug_sha256": {"run_a": normalized_a_sha, "run_b": normalized_b_sha},
            "readelf_notes_sha256": {"run_a": sha256_file(notes_a_path), "run_b": sha256_file(notes_b_path)},
            "readelf_sections_sha256": {"run_a": sha256_file(sections_a_path), "run_b": sha256_file(sections_b_path)},
            "stripped_no_build_id_sha256": {"run_a": sha256_file(stripped_a), "run_b": sha256_file(stripped_b)},
        },
    }


def verify_installed_executable(
    run_root: pathlib.Path,
    build: dict[str, Any],
    smoke: dict[str, Any],
) -> dict[str, Any]:
    executable = run_root / "install/games/openttd"
    if not executable.is_file() or executable.is_symlink() or not os.access(executable, os.X_OK):
        raise ComparisonError(f"installed executable is absent, linked, or not executable: {executable}")
    try:
        build_authoritative = build["authoritative"]
        smoke_authoritative = smoke["authoritative"]
        build_executable = build_authoritative["executable"]
        smoke_executable = smoke_authoritative["executable"]
        build_identity = {
            "sha256": build_executable["sha256"],
            "size_bytes": build_executable["size"],
            "version": build_executable["version"],
        }
        smoke_identity = {
            "sha256": smoke_executable["sha256"],
            "version": smoke_executable["version"],
        }
    except (KeyError, TypeError) as exc:
        raise ComparisonError(f"build/smoke executable identity is malformed: {run_root}") from exc
    actual_identity = {
        "sha256": sha256_file(executable),
        "size_bytes": executable.stat().st_size,
        "version": build_identity["version"],
    }
    if build_authoritative.get("source_commit") != EXPECTED_SUBMODULE:
        raise ComparisonError(f"build source identity differs from the frozen submodule commit: {run_root}")
    if build_identity["sha256"] != smoke_identity["sha256"] or build_identity["version"] != smoke_identity["version"]:
        raise ComparisonError(f"build and smoke executable identities disagree: {run_root}")
    if actual_identity["sha256"] != build_identity["sha256"] or actual_identity["size_bytes"] != build_identity["size_bytes"]:
        raise ComparisonError(f"installed executable does not match the build/smoke manifest chain: {run_root}")
    return actual_identity


def project_run(run_root: pathlib.Path) -> dict[str, Any]:
    configure = require_canonical_manifest(run_root / "manifests/configure-reference.json")
    build = require_canonical_manifest(run_root / "manifests/build-reference.json")
    tests = require_canonical_manifest(run_root / "manifests/test-reference.json")
    smoke = require_canonical_manifest(run_root / "manifests/smoke-reference.json")
    fetch = load_json(run_root / "results/fetch-opengfx-details.json")
    test_counts = load_json(run_root / "test-results/ctest-counts.json")
    if configure["authoritative"].get("source_commit") != EXPECTED_SUBMODULE:
        raise ComparisonError("configure source identity differs from the frozen submodule commit")

    smoke_authoritative = smoke["authoritative"]
    installed_executable = verify_installed_executable(run_root, build, smoke)
    smoke_executable = dict(smoke_authoritative["executable"])
    smoke_executable.pop("sha256", None)
    return {
        "source-identity": {"submodule_commit": configure["authoritative"]["source_commit"]},
        "configuration-identity": configure["authoritative"],
        "test-inventory": {
            "command": tests["authoritative"]["inventory_command"],
            "count": tests["authoritative"]["counts"]["total"],
            "sha256": tests["authoritative"]["inventory_sha256"],
        },
        "test-results": {
            "counts": tests["authoritative"]["counts"],
            "executed_names": test_counts["test_names"],
            "return_code": test_counts["return_code"],
        },
        "runtime-version-output": {
            "build": installed_executable["version"],
            "smoke": smoke_executable["version"],
        },
        "opengfx-identity": {
            "archive": fetch["authoritative"]["archive"],
            "build_sha256": build["authoritative"]["opengfx_sha256"],
            "installed": {
                "name": fetch["authoritative"]["installed"]["name"],
                "sha256": fetch["authoritative"]["installed"]["sha256"],
            },
            "smoke_content": smoke_authoritative["content"],
        },
        "headless-smoke-behavior": {
            "behavior": smoke_authoritative["behavior"],
            "command": smoke_authoritative["command"],
            "content": smoke_authoritative["content"],
            "executable": smoke_executable,
        },
    }


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ComparisonError(f"timestamp has no timezone: {value}")
    return parsed.astimezone(timezone.utc)


def copy_portable_profile(repository: pathlib.Path, artifact_root: pathlib.Path) -> tuple[dict[str, pathlib.Path], dict[str, pathlib.Path]]:
    schema_names = (
        "build.schema.json",
        "dependency.schema.json",
        "evidence.schema.json",
        "gate-result.schema.json",
        "opengfx.schema.json",
        "source.schema.json",
        "test-inventory.schema.json",
        "toolchain.schema.json",
    )
    baseline_names = (
        "P0_PROFILE_LOCK.json",
        "build-relwithdebinfo.json",
        "dependencies-ubuntu-24.04.json",
        "opengfx-8.0.json",
        "openttd-source.json",
        "tests-relwithdebinfo.json",
        "toolchain-linux-x86_64.json",
    )
    schemas: dict[str, pathlib.Path] = {}
    baselines: dict[str, pathlib.Path] = {}
    for name in schema_names:
        destination = artifact_root / "schema" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository / "oracle/manifests/schema" / name, destination)
        schemas[name] = destination
    for name in baseline_names:
        destination = artifact_root / "profile" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository / "oracle/manifests/baseline" / name, destination)
        baselines[name] = destination
    requirements_name = "requirements-p0.txt"
    requirements_destination = artifact_root / "profile" / requirements_name
    shutil.copyfile(repository / "tools" / requirements_name, requirements_destination)
    baselines[requirements_name] = requirements_destination
    return schemas, baselines


def write_raw_artifact_index(artifact_root: pathlib.Path, comparison_root: pathlib.Path) -> pathlib.Path:
    roots = [
        artifact_root / "commands",
        artifact_root / "logs",
        artifact_root / "results",
        artifact_root / "contract-tests",
        artifact_root / "profile",
        artifact_root / "schema",
    ]
    for role in ("run-a", "run-b"):
        for subdirectory in ("commands", "logs", "manifests", "results", "inventory", "test-results"):
            roots.append(artifact_root / role / subdirectory)
    records = []
    seen: set[pathlib.Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink() or path in seen:
                continue
            if path.parent == artifact_root / "logs" and path.name.startswith("port001-comparator."):
                continue
            seen.add(path)
            records.append(
                {
                    "path": path.relative_to(artifact_root).as_posix(),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    for path in sorted(comparison_root.glob("*.txt")) + [comparison_root / "port001-reference-comparison.json"]:
        if path.is_file() and path not in seen:
            records.append(
                {
                    "path": path.relative_to(artifact_root).as_posix(),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    output = comparison_root / "port001-raw-artifact-index.json"
    write_canonical(output, {"artifacts": records, "root_role": "$ARTIFACT_ROOT", "schema_version": 1})
    return output


def invocation_commands(parallel: int) -> list[dict[str, Any]]:
    commands = [
        {
            "argv": [
                "oracle/runner/port001_gate.sh", "--profile", "local-release", "--artifact-root", "$ARTIFACT_ROOT",
                "--tools-python", "$P0_TOOLS_PYTHON", "--parallel", str(parallel),
            ],
            "purpose": "two-clean-root PORT-001 release reconstruction",
            "return_code": 0,
        },
        {
            "argv": [
                "/usr/bin/ctest", "--test-dir", "$ARTIFACT_ROOT/contract-build", "--output-on-failure",
                "--no-tests=error", "--schedule-random", "--repeat", "until-fail:3", "--timeout", "900",
                "--output-junit", "$ARTIFACT_ROOT/contract-tests/p001-contract.junit.xml",
                "-R", "^p001_(contract|comparator)$",
            ],
            "purpose": "randomized and repeated PORT-001 contract tests",
            "return_code": 0,
        },
    ]
    for label, run_role in (("A", "$ARTIFACT_ROOT/run-a"), ("B", "$ARTIFACT_ROOT/run-b")):
        build_role = f"{run_role}/build"
        install_role = f"{run_role}/install"
        commands.extend(
            [
                {
                    "argv": ["oracle/runner/preflight.sh", "--mode", "edit", "--artifact-root", run_role, "--content-root", f"{build_role}/baseset"],
                    "purpose": f"clean reference {label} preflight",
                    "return_code": 0,
                },
                {
                    "argv": [
                        "oracle/runner/configure_reference.sh", "--source-root", "$SOURCE_ROOT", "--build-root", build_role,
                        "--install-root", install_role, "--artifact-root", run_role,
                    ],
                    "purpose": f"clean reference {label} configuration",
                    "return_code": 0,
                },
                {
                    "argv": ["oracle/runner/fetch_opengfx.sh", "--destination", f"{build_role}/baseset", "--artifact-root", run_role],
                    "purpose": f"clean reference {label} verified OpenGFX acquisition",
                    "return_code": 0,
                },
                {
                    "argv": [
                        "oracle/runner/build_reference.sh", "--build-root", build_role, "--install-root", install_role,
                        "--artifact-root", run_role, "--configuration-manifest", f"{run_role}/manifests/configure-reference.json",
                        "--parallel", str(parallel),
                    ],
                    "purpose": f"clean reference {label} build and install",
                    "return_code": 0,
                },
                {
                    "argv": [
                        "oracle/runner/test_reference.sh", "--build-root", build_role, "--artifact-root", run_role,
                        "--baseline-inventory", "$REPOSITORY_ROOT/oracle/manifests/baseline/tests-relwithdebinfo.json",
                    ],
                    "purpose": f"clean reference {label} 99-test suite",
                    "return_code": 0,
                },
                {
                    "argv": [
                        "oracle/runner/smoke_reference.sh", "--install-root", install_role, "--artifact-root", run_role,
                        "--build-manifest", f"{run_role}/manifests/build-reference.json",
                    ],
                    "purpose": f"clean reference {label} 128-tick headless smoke",
                    "return_code": 0,
                },
            ]
        )
    return commands


def without_media_type(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "media_type"}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True, type=pathlib.Path)
    parser.add_argument("--artifact-root", required=True, type=pathlib.Path)
    parser.add_argument("--run-a", required=True, type=pathlib.Path)
    parser.add_argument("--run-b", required=True, type=pathlib.Path)
    parser.add_argument("--outer-commit", required=True)
    parser.add_argument("--remote-commit", required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--finished-at", required=True)
    parser.add_argument("--parallel", required=True, type=int)
    args = parser.parse_args(argv)

    try:
        repository = args.repository_root.resolve(strict=True)
        artifact_root = args.artifact_root.resolve(strict=True)
        run_a = args.run_a.resolve(strict=True)
        run_b = args.run_b.resolve(strict=True)
        if run_a.parent != artifact_root or run_b.parent != artifact_root or run_a == run_b:
            raise ComparisonError("run roots must be distinct direct children of the artifact root")
        if len(args.outer_commit) != 40 or args.outer_commit != args.remote_commit:
            raise ComparisonError("authoritative comparison requires the exact pushed outer commit")
        require_pass_results(run_a)
        require_pass_results(run_b)
        projection_a = project_run(run_a)
        projection_b = project_run(run_b)

        equalities = []
        for equality_id in (
            "source-identity",
            "configuration-identity",
            "test-inventory",
            "test-results",
            "runtime-version-output",
            "opengfx-identity",
            "headless-smoke-behavior",
        ):
            digest_a = canonical_digest(projection_a[equality_id])
            digest_b = canonical_digest(projection_b[equality_id])
            status = "PASS" if projection_a[equality_id] == projection_b[equality_id] else "FAIL"
            equalities.append({"id": equality_id, "run_a_sha256": digest_a, "run_b_sha256": digest_b, "status": status})
        failures = [entry["id"] for entry in equalities if entry["status"] != "PASS"]
        if failures:
            raise ComparisonError(f"mandatory reconstruction equalities failed: {failures}")

        comparison_root = artifact_root / "comparison"
        comparison_root.mkdir(parents=True, exist_ok=True)
        binary = inspect_binaries(run_a, run_b, comparison_root)
        report_path = comparison_root / "port001-reference-comparison.json"
        report = {
            "binary_measurement": binary,
            "equalities": equalities,
            "outer_commit": args.outer_commit,
            "profile": "local-release",
            "report_kind": "port001-reference-comparison",
            "run_roots": {"run_a": "$ARTIFACT_ROOT/run-a", "run_b": "$ARTIFACT_ROOT/run-b"},
            "schema_version": 1,
            "status": "PASS" if binary["acceptable"] else "FAIL",
            "submodule_commit": EXPECTED_SUBMODULE,
        }
        write_canonical(report_path, report)
        if not binary["acceptable"]:
            raise ComparisonError(
                "unexplained binary difference: non-debug code/data remained unequal after build-id and generated-root normalization",
            )

        started = parse_timestamp(args.started_at)
        finished = parse_timestamp(args.finished_at)
        duration = max(0, int((finished - started).total_seconds()))
        copied_schemas, copied_baselines = copy_portable_profile(repository, artifact_root)
        evidence_schema = copied_schemas["evidence.schema.json"]
        gate_schema = copied_schemas["gate-result.schema.json"]
        contract_junit = artifact_root / "contract-tests/p001-contract.junit.xml"
        contract_log = artifact_root / "contract-tests/p001-contract.log"
        if not contract_junit.is_file() or not contract_junit.stat().st_size or not contract_log.is_file():
            raise ComparisonError("randomized/repeated PORT-001 contract test evidence is missing")
        try:
            contract_xml = ET.parse(contract_junit).getroot()
        except ET.ParseError as exc:
            raise ComparisonError(f"mandatory-suite JUnit is malformed: {exc}") from exc
        contract_cases = contract_xml.findall(".//testcase")
        contract_names = sorted(case.attrib.get("name", "") for case in contract_cases)
        if contract_names != ["p001_comparator", "p001_contract"]:
            raise ComparisonError(f"mandatory-suite JUnit executed-name set is incomplete: {contract_names}")
        if any(case.find("failure") is not None or case.find("error") is not None or case.find("skipped") is not None for case in contract_cases):
            raise ComparisonError("mandatory-suite JUnit contains a failure, error, or skip")
        raw_index_path = write_raw_artifact_index(artifact_root, comparison_root)
        run_a_exe = run_a / "install/games/openttd"
        run_b_exe = run_b / "install/games/openttd"
        report_artifact = artifact(
            "PORT-001 reconstruction comparison",
            report_path,
            "comparison/port001-reference-comparison.json",
            "application/json",
        )
        schema_artifacts = [
            artifact(
                name.removesuffix(".json").replace(".", " "),
                path,
                f"schema/{name}",
                "application/schema+json",
            )
            for name, path in sorted(copied_schemas.items())
        ]
        baseline_artifacts = [
            artifact(
                f"frozen baseline {name}",
                path,
                f"profile/{name}",
                "application/json" if path.suffix == ".json" else "text/plain",
            )
            for name, path in sorted(copied_baselines.items())
        ]
        evidence_path = comparison_root / "port001-evidence.json"
        evidence = {
            "$schema": "../schema/evidence.schema.json",
            "diagnostics": {
                "artifact_root": str(artifact_root),
                "duration_seconds": duration,
                "finished_at": args.finished_at,
                "host_note": "Ubuntu 24.04 x86-64 frozen local-release profile; generated roots are diagnostics.",
                "started_at": args.started_at,
            },
            "invocation": {
                "builder_profile": "build-relwithdebinfo",
                "commands": invocation_commands(args.parallel),
                "environment": [
                    {"name": "LANG", "value": "C.UTF-8"},
                    {"name": "LC_ALL", "value": "C.UTF-8"},
                    {"name": "P0_PROFILE", "value": "local-release"},
                    {"name": "PYTHONHASHSEED", "value": "0"},
                    {"name": "SOURCE_DATE_EPOCH", "value": "1785314342"},
                    {"name": "TZ", "value": "UTC"},
                ],
                "parameters": [
                    {"name": "CLEAN_BUILD_ROOTS", "value": 2},
                    {"name": "EXPECTED_TEST_COUNT", "value": 99},
                    {"name": "P0_JOBS", "value": args.parallel},
                    {"name": "SMOKE_TICKS", "value": 128},
                ],
            },
            "materials": [
                *baseline_artifacts,
                artifact("run A configure manifest", run_a / "manifests/configure-reference.json", "run-a/manifests/configure-reference.json", "application/json"),
                artifact("run B configure manifest", run_b / "manifests/configure-reference.json", "run-b/manifests/configure-reference.json", "application/json"),
            ],
            "outputs": [
                report_artifact,
                artifact("complete raw PORT-001 artifact digest index", raw_index_path, "comparison/port001-raw-artifact-index.json", "application/json"),
                artifact("exact host, toolchain, and Python profile result", artifact_root / "results/port001-host-profile.json", "results/port001-host-profile.json", "application/json"),
                artifact("run A OpenTTD executable", run_a_exe, "run-a/install/games/openttd", "application/x-executable"),
                artifact("run B OpenTTD executable", run_b_exe, "run-b/install/games/openttd", "application/x-executable"),
                artifact("run A build manifest", run_a / "manifests/build-reference.json", "run-a/manifests/build-reference.json", "application/json"),
                artifact("run B build manifest", run_b / "manifests/build-reference.json", "run-b/manifests/build-reference.json", "application/json"),
                artifact("run A test manifest", run_a / "manifests/test-reference.json", "run-a/manifests/test-reference.json", "application/json"),
                artifact("run B test manifest", run_b / "manifests/test-reference.json", "run-b/manifests/test-reference.json", "application/json"),
                artifact("run A smoke manifest", run_a / "manifests/smoke-reference.json", "run-a/manifests/smoke-reference.json", "application/json"),
                artifact("run B smoke manifest", run_b / "manifests/smoke-reference.json", "run-b/manifests/smoke-reference.json", "application/json"),
                artifact("run A OpenGFX acquisition details", run_a / "results/fetch-opengfx-details.json", "run-a/results/fetch-opengfx-details.json", "application/json"),
                artifact("run B OpenGFX acquisition details", run_b / "results/fetch-opengfx-details.json", "run-b/results/fetch-opengfx-details.json", "application/json"),
                artifact("run A raw CTest inventory", run_a / "inventory/ctest-inventory.raw.json", "run-a/inventory/ctest-inventory.raw.json", "application/json"),
                artifact("run B raw CTest inventory", run_b / "inventory/ctest-inventory.raw.json", "run-b/inventory/ctest-inventory.raw.json", "application/json"),
                artifact("run A normalized CTest inventory", run_a / "inventory/ctest-inventory.normalized.json", "run-a/inventory/ctest-inventory.normalized.json", "application/json"),
                artifact("run B normalized CTest inventory", run_b / "inventory/ctest-inventory.normalized.json", "run-b/inventory/ctest-inventory.normalized.json", "application/json"),
                artifact("run A upstream CTest JUnit", run_a / "test-results/ctest-results.junit.xml", "run-a/test-results/ctest-results.junit.xml", "application/xml"),
                artifact("run B upstream CTest JUnit", run_b / "test-results/ctest-results.junit.xml", "run-b/test-results/ctest-results.junit.xml", "application/xml"),
                artifact("randomized repeated PORT-001 contract JUnit", contract_junit, "contract-tests/p001-contract.junit.xml", "application/xml"),
                artifact("randomized repeated PORT-001 contract log", contract_log, "contract-tests/p001-contract.log", "text/plain"),
            ],
            "profile": "local-release",
            "schema_sha256": sha256_file(evidence_schema),
            "schema_version": 1,
            "source_identity": {
                "outer_commit": args.outer_commit,
                "schemas": schema_artifacts,
                "submodule_clean": True,
                "submodule_commit": EXPECTED_SUBMODULE,
            },
            "statement_kind": "p0-run-evidence",
            "status": "PASS",
            "subject": "port001-reference-reconstruction",
        }
        write_canonical(evidence_path, evidence)

        evidence_artifact = artifact("PORT-001 evidence statement", evidence_path, "comparison/port001-evidence.json")
        report_gate_artifact = without_media_type(report_artifact)
        baseline_gate_artifacts = [without_media_type(item) for item in baseline_artifacts]
        schema_gate_artifacts = [without_media_type(item) for item in schema_artifacts]
        raw_index_gate_artifact = artifact(
            "complete raw PORT-001 artifact digest index",
            raw_index_path,
            "comparison/port001-raw-artifact-index.json",
        )
        contract_gate_artifact = artifact(
            "randomized repeated PORT-001 contract JUnit",
            contract_junit,
            "contract-tests/p001-contract.junit.xml",
        )
        checks = [
            {"evidence": [*baseline_gate_artifacts, *schema_gate_artifacts], "id": "BASELINE-SCHEMAS", "status": "PASS"},
            {"evidence": [contract_gate_artifact], "id": "MANDATORY-TESTS", "status": "PASS"},
            {"evidence": [raw_index_gate_artifact], "id": "CLEAN-RUN-A", "status": "PASS"},
            {"evidence": [raw_index_gate_artifact], "id": "CLEAN-RUN-B", "status": "PASS"},
        ]
        for equality in equalities:
            checks.append({"evidence": [report_gate_artifact], "id": equality["id"].upper(), "status": "PASS"})
        checks.extend(
            [
                {"evidence": [report_gate_artifact], "id": "BINARY-ANALYSIS", "status": "PASS"},
                {"evidence": [evidence_artifact], "id": "BRANCH-PUSH", "status": "PASS"},
            ]
        )
        gate_path = comparison_root / "port001-gate-result.json"
        gate = {
            "$schema": "../schema/gate-result.schema.json",
            "artifacts": [contract_gate_artifact, evidence_artifact, raw_index_gate_artifact, report_gate_artifact],
            "branch_push": {
                "branch": EXPECTED_BRANCH,
                "local_commit": args.outer_commit,
                "remote_commit": args.remote_commit,
                "required": True,
                "verified": True,
            },
            "checks": checks,
            "diagnostics": {
                "artifact_root": str(artifact_root),
                "duration_seconds": duration,
                "finished_at": args.finished_at,
                "started_at": args.started_at,
            },
            "gate_id": "PORT-001",
            "gate_result_kind": "p0-gate-result",
            "open_counts": {"defects": 0, "divergences": 0, "mandatory_skips": 0, "unverified_artifacts": 0},
            "profile": "local-release",
            "schema_sha256": sha256_file(gate_schema),
            "schema_version": 1,
            "status": "PASS",
        }
        write_canonical(gate_path, gate)

        completion_path = comparison_root / "PORT001_COMPLETION_REPORT.md"
        completion_path.write_text(
            "\n".join(
                [
                    "# PORT-001 completion report",
                    "",
                    f"- Status: **PASS**",
                    f"- Source commit: `{args.outer_commit}` (verified pushed to `{EXPECTED_BRANCH}`)",
                    f"- OpenTTD submodule: `{EXPECTED_SUBMODULE}` (clean)",
                    "- Clean reference roots: 2",
                    "- Upstream tests: 99/99 passed in each root, with no skip or timeout",
                    "- Headless smoke: exact 128-tick null-backend command passed in each root",
                    "- Required reconstruction equalities: 7/7",
                    f"- Executable claim: {binary['claim']}",
                    f"- Binary analysis: {binary['explanation']}",
                    "",
                    "The raw executable digests, stage manifests, inventories, JUnit files, logs, readelf output,",
                    "and canonical comparison evidence remain below the external artifact root. This report does",
                    "not claim byte reproducibility unless the comparison record classifies the raw bytes as equal.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(gate_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ComparisonError, rfc8785.CanonicalizationError) as exc:
        print(f"PORT-001 comparison failed: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
