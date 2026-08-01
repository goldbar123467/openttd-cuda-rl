#!/usr/bin/env python3
"""Positive and first-divergence regression tests for the PORT-001 comparator."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

import rfc8785


EXPECTED_SUBMODULE = "29f808ef0022064e6d9a83c8476d1e0f4686af86"


def write_json(path: pathlib.Path, value: object, *, canonical: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if canonical:
        path.write_bytes(rfc8785.dumps(value))
    else:
        path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_fixture(
    root: pathlib.Path,
    smoke_mutation: bool,
    binary_mutation: bool = False,
    missing_stage_rc: bool = False,
) -> None:
    (root / "contract-tests").mkdir(parents=True)
    (root / "contract-tests/p001-contract.junit.xml").write_text(
        '<testsuite tests="2" failures="0"><testcase name="p001_contract"/><testcase name="p001_comparator"/></testsuite>\n',
        encoding="utf-8",
    )
    (root / "contract-tests/p001-contract.log").write_text("randomized repeated suite PASS\n", encoding="utf-8")
    (root / "logs").mkdir(parents=True)
    (root / "logs/port001-gate.log").write_text("RUNNING\n", encoding="utf-8")
    write_json(root / "results/port001-gate.json", {"status": "RUNNING"})
    write_json(root / "results/port001-host-profile.json", {"status": "PASS", "checked_tools": [], "checked_packages": []})
    for role in ("run-a", "run-b"):
        run = root / role
        for result_name in (
            "preflight.json",
            "configure-reference.json",
            "fetch-opengfx.json",
            "build-reference.json",
            "test-reference.json",
            "smoke-reference.json",
        ):
            result = {"return_code": 0, "status": "PASS"}
            if missing_stage_rc and role == "run-a" and result_name == "preflight.json":
                del result["return_code"]
            write_json(run / "results" / result_name, result)

        source_executable = pathlib.Path("/bin/false" if binary_mutation and role == "run-b" else "/bin/true")
        executable_sha256 = sha256_file(source_executable)
        executable_size = source_executable.stat().st_size

        configure = {
            "authoritative": {"configuration": "same", "source_commit": EXPECTED_SUBMODULE},
            "diagnostics": {},
            "return_code": 0,
            "status": "PASS",
        }
        build = {
            "authoritative": {
                "executable": {
                    "sha256": executable_sha256,
                    "size": executable_size,
                    "version": "OpenTTD fixture",
                },
                "opengfx_sha256": "9" * 64,
                "source_commit": EXPECTED_SUBMODULE,
            },
            "diagnostics": {},
            "return_code": 0,
            "status": "PASS",
        }
        tests = {
            "authoritative": {
                "counts": {"failed": 0, "passed": 99, "skipped": 0, "total": 99},
                "inventory_command": ["ctest", "--test-dir", "$BUILD_ROOT"],
                "inventory_sha256": "5" * 64,
            },
            "diagnostics": {},
            "return_code": 0,
            "status": "PASS",
        }
        smoke_stdout = ("4" if smoke_mutation and role == "run-b" else "3") * 64
        smoke = {
            "authoritative": {
                "behavior": {
                    "capabilities_sha256": "1" * 64,
                    "return_code": 0,
                    "stderr_sha256": "2" * 64,
                    "stdout_sha256": smoke_stdout,
                },
                "command": ["$INSTALL_ROOT/games/openttd", "-g"],
                "content": {"name": "OpenGFX", "sha256": "9" * 64, "version": "8.0"},
                "executable": {"sha256": executable_sha256, "version": "OpenTTD fixture"},
            },
            "diagnostics": {},
            "return_code": 0,
            "status": "PASS",
        }
        for name, value in (
            ("configure-reference.json", configure),
            ("build-reference.json", build),
            ("test-reference.json", tests),
            ("smoke-reference.json", smoke),
        ):
            write_json(run / "manifests" / name, value, canonical=True)
        write_json(
            run / "results/fetch-opengfx-details.json",
            {
                "authoritative": {
                    "archive": {"name": "archive", "sha256": "8" * 64, "url": "https://example.invalid/archive"},
                    "installed": {"name": "opengfx-8.0.tar", "sha256": "9" * 64, "state": "INSTALLED"},
                },
                "status": "PASS",
            },
        )
        write_json(
            run / "test-results/ctest-counts.json",
            {
                "failed": 0,
                "passed": 99,
                "return_code": 0,
                "skipped": 0,
                "test_names": [f"test-{index:03d}" for index in range(99)],
                "total": 99,
            },
        )
        write_json(run / "inventory/ctest-inventory.raw.json", {"tests": []})
        write_json(run / "inventory/ctest-inventory.normalized.json", {"tests": [], "version": {"major": 1, "minor": 0}})
        (run / "test-results/ctest-results.junit.xml").write_text(
            '<testsuite tests="99" failures="0"><testcase name="fixture"/></testsuite>\n',
            encoding="utf-8",
        )
        executable = run / "install/games/openttd"
        executable.parent.mkdir(parents=True)
        shutil.copy2(source_executable, executable)


def comparator_command(repository: pathlib.Path, root: pathlib.Path, commit: str) -> list[str]:
    return [
        sys.executable,
        str(repository / "tools/compare_port001_runs.py"),
        "--repository-root",
        str(repository),
        "--artifact-root",
        str(root),
        "--run-a",
        str(root / "run-a"),
        "--run-b",
        str(root / "run-b"),
        "--outer-commit",
        commit,
        "--remote-commit",
        commit,
        "--started-at",
        "2026-07-30T00:00:00Z",
        "--finished-at",
        "2026-07-30T00:01:00Z",
        "--parallel",
        "1",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True, type=pathlib.Path)
    args = parser.parse_args()
    repository = args.repository_root.resolve(strict=True)
    commit = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()

    with tempfile.TemporaryDirectory(prefix="p001-comparator-positive.") as temp:
        root = pathlib.Path(temp)
        create_fixture(root, smoke_mutation=False)
        positive = subprocess.run(comparator_command(repository, root, commit), check=False, text=True, capture_output=True)
        if positive.returncode != 0:
            raise SystemExit(f"positive comparator fixture failed:\n{positive.stdout}\n{positive.stderr}")
        for output, schema in (
            ("port001-evidence.json", "evidence.schema.json"),
            ("port001-gate-result.json", "gate-result.schema.json"),
        ):
            validation = subprocess.run(
                [
                    sys.executable,
                    str(repository / "tools/validate_manifest.py"),
                    "--schema",
                    str(repository / "oracle/manifests/schema" / schema),
                    str(root / "comparison" / output),
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            if validation.returncode != 0:
                raise SystemExit(f"comparator output validation failed: {output}\n{validation.stderr}")

        portable_pairs = {
            "build-relwithdebinfo.json": "build.schema.json",
            "dependencies-ubuntu-24.04.json": "dependency.schema.json",
            "opengfx-8.0.json": "opengfx.schema.json",
            "openttd-source.json": "source.schema.json",
            "tests-relwithdebinfo.json": "test-inventory.schema.json",
            "toolchain-linux-x86_64.json": "toolchain.schema.json",
        }
        for baseline_name, schema_name in portable_pairs.items():
            baseline_path = root / "profile" / baseline_name
            declared_schema = json.loads(baseline_path.read_text(encoding="utf-8"))["$schema"]
            resolved_schema = (baseline_path.parent / declared_schema).resolve(strict=True)
            if resolved_schema != (root / "schema" / schema_name).resolve(strict=True):
                raise SystemExit(f"portable schema reference resolved incorrectly: {baseline_name}")
            validation = subprocess.run(
                [
                    sys.executable,
                    str(repository / "tools/validate_manifest.py"),
                    "--schema",
                    str(resolved_schema),
                    "--profile-lock",
                    str(root / "profile/P0_PROFILE_LOCK.json"),
                    str(baseline_path),
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            if validation.returncode != 0:
                raise SystemExit(f"portable baseline/schema validation failed: {baseline_name}\n{validation.stderr}")
        if sha256_file(root / "profile/requirements-p0.txt") != sha256_file(repository / "tools/requirements-p0.txt"):
            raise SystemExit("portable requirements lock digest differs from the repository lock")

        raw_index = json.loads((root / "comparison/port001-raw-artifact-index.json").read_text(encoding="utf-8"))
        indexed_paths = {item["path"] for item in raw_index["artifacts"]}
        forbidden_mutable = {
            "logs/port001-comparator.stderr.log",
            "logs/port001-comparator.stdout.log",
            "logs/port001-gate.log",
            "results/port001-gate.json",
        }
        if indexed_paths & forbidden_mutable or set(raw_index["excluded_downstream_mutable_roles"]) != forbidden_mutable:
            raise SystemExit("raw artifact index did not exclude exactly the downstream-mutable gate/comparator roles")
        for item in raw_index["artifacts"]:
            indexed_path = root / item["path"]
            if (
                not indexed_path.is_file()
                or indexed_path.stat().st_size != item["size_bytes"]
                or sha256_file(indexed_path) != item["sha256"]
            ):
                raise SystemExit(f"raw artifact index contains a stale or missing entry: {item['path']}")

        gate_path = root / "comparison/port001-gate-result.json"
        valid_gate = json.loads(gate_path.read_text(encoding="utf-8"))
        semantic_mutants: list[tuple[str, dict[str, object], str]] = []

        failed_check = copy.deepcopy(valid_gate)
        failed_check["checks"][0]["status"] = "FAIL"
        failed_check["checks"][0]["reason"] = "semantic regression fixture"
        semantic_mutants.append(("failed-check", failed_check, "PASS gate contains a non-PASS check"))

        duplicate_id = copy.deepcopy(valid_gate)
        duplicate_id["checks"][0]["id"] = duplicate_id["checks"][1]["id"]
        semantic_mutants.append(("duplicate-check-id", duplicate_id, "check IDs must be unique"))

        missing_id = copy.deepcopy(valid_gate)
        missing_id["checks"].pop()
        semantic_mutants.append(("missing-check-id", missing_id, "check set is not exact"))

        unexpected_id = copy.deepcopy(valid_gate)
        extra_check = copy.deepcopy(unexpected_id["checks"][0])
        extra_check["id"] = "UNEXPECTED-CHECK"
        unexpected_id["checks"].append(extra_check)
        semantic_mutants.append(("unexpected-check-id", unexpected_id, "check set is not exact"))

        nonzero_open_count = copy.deepcopy(valid_gate)
        nonzero_open_count["open_counts"]["defects"] = 1
        semantic_mutants.append(("nonzero-open-count", nonzero_open_count, "nonzero or malformed open count"))

        unverified_push = copy.deepcopy(valid_gate)
        unverified_push["branch_push"]["verified"] = False
        semantic_mutants.append(("unverified-push", unverified_push, "branch push is unverified"))

        unequal_push = copy.deepcopy(valid_gate)
        unequal_push["branch_push"]["remote_commit"] = "f" * 40
        semantic_mutants.append(("unequal-push", unequal_push, "local/remote commits differ"))

        for label, mutant, needle in semantic_mutants:
            mutant_path = root / "comparison" / f"port001-gate-{label}.json"
            write_json(mutant_path, mutant)
            validation = subprocess.run(
                [
                    sys.executable,
                    str(repository / "tools/validate_manifest.py"),
                    "--schema",
                    str(repository / "oracle/manifests/schema/gate-result.schema.json"),
                    str(mutant_path),
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            if validation.returncode == 0 or needle not in validation.stderr:
                raise SystemExit(f"PASS-gate semantic mutant {label} was not rejected precisely:\n{validation.stderr}")

    with tempfile.TemporaryDirectory(prefix="p001-comparator-negative.") as temp:
        root = pathlib.Path(temp)
        create_fixture(root, smoke_mutation=True)
        negative = subprocess.run(comparator_command(repository, root, commit), check=False, text=True, capture_output=True)
        combined = negative.stdout + negative.stderr
        if negative.returncode == 0 or "headless-smoke-behavior" not in combined:
            raise SystemExit(f"known smoke divergence was not rejected precisely:\n{combined}")

    with tempfile.TemporaryDirectory(prefix="p001-comparator-binary-negative.") as temp:
        root = pathlib.Path(temp)
        create_fixture(root, smoke_mutation=False, binary_mutation=True)
        negative = subprocess.run(comparator_command(repository, root, commit), check=False, text=True, capture_output=True)
        combined = negative.stdout + negative.stderr
        if negative.returncode == 0 or "unexplained binary difference" not in combined:
            raise SystemExit(f"unexplained executable divergence was not rejected precisely:\n{combined}")

    with tempfile.TemporaryDirectory(prefix="p001-comparator-replacement-negative.") as temp:
        root = pathlib.Path(temp)
        create_fixture(root, smoke_mutation=False)
        for role in ("run-a", "run-b"):
            shutil.copy2("/bin/false", root / role / "install/games/openttd")
        negative = subprocess.run(comparator_command(repository, root, commit), check=False, text=True, capture_output=True)
        combined = negative.stdout + negative.stderr
        if negative.returncode == 0 or "installed executable does not match the build/smoke manifest chain" not in combined:
            raise SystemExit(f"same post-smoke executable replacement was not rejected precisely:\n{combined}")

    with tempfile.TemporaryDirectory(prefix="p001-comparator-missing-rc-negative.") as temp:
        root = pathlib.Path(temp)
        create_fixture(root, smoke_mutation=False, missing_stage_rc=True)
        negative = subprocess.run(comparator_command(repository, root, commit), check=False, text=True, capture_output=True)
        combined = negative.stdout + negative.stderr
        if negative.returncode == 0 or "required stage result is not PASS" not in combined:
            raise SystemExit(f"missing stage return code was not rejected precisely:\n{combined}")

    print("PORT-001 comparator tests: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
