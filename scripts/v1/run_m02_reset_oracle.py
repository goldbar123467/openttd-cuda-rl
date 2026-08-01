#!/usr/bin/env python3
"""Run the native M02 clean-process and same-process reset oracle offline."""

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
from typing import Any

import generate_m02_scenario
import run_m02_map_feasibility
import validate_m02_reset_projection
import validate_m02_scenario_contract
import validate_m02_scripted_trajectory


class M02ResetOracleError(ValueError):
    """An oracle input, native execution, validation, or reproducibility gate failed."""


FORBIDDEN_DIAGNOSTIC = re.compile(
    r"(?:assert(?:ion)?|AddressSanitizer|LeakSanitizer|UndefinedBehaviorSanitizer|"
    r"runtime error:|warning|error|failed|fatal|crash)",
    re.IGNORECASE,
)
RUNTIME_BASESET_FILES = (
    "OpenTTD-Mono.ttf",
    "OpenTTD-Sans.ttf",
    "OpenTTD-Serif.ttf",
    "OpenTTD-Small.ttf",
    "no_music.obm",
    "no_sound.obs",
    "openttd.grf",
    "opntitle.dat",
)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M02ResetOracleError(message)


def repository_path(root: pathlib.Path, relative: str, label: str) -> pathlib.Path:
    path = (root / relative).resolve()
    require(path.is_relative_to(root), f"{label} escapes repository root: {relative}")
    return path


def validate_oracle_config(root: pathlib.Path, oracle: dict[str, Any]) -> dict[str, dict[str, str]]:
    require(
        oracle.get("schema_version") == "openttd-rl-v1-m02-reset-oracle-1",
        "unsupported reset oracle schema_version",
    )
    accepted = oracle["accepted_feasibility"]
    require(
        accepted
        == {
            "composed_source_identity_sha256": "2140e34ccee8534dbf712487acd2225eda4b66d1c807b9e0ce07243ba40afdbd",
            "result_tree": "eba8f4bd3c37042c184d968d2f038864184e3132",
        },
        "accepted M02 feasibility identity drifted",
    )
    delta = oracle["native_delta"]
    series = repository_path(root, delta["series_path"], "native delta series")
    require(series.is_file() and not series.is_symlink(), "native delta series is not a regular file")
    require(sha256_file(series) == delta["series_sha256"], "native delta series digest mismatch")
    patch_records = delta["patches"]
    require(isinstance(patch_records, list) and len(patch_records) == 1, "native delta must contain exactly patch 0003")
    for record in patch_records:
        patch = repository_path(root, record["path"], "native delta patch")
        require(patch.is_file() and not patch.is_symlink(), "native delta patch is not a regular file")
        require(sha256_file(patch) == record["sha256"], "native delta patch digest mismatch")
    observed_identity = run_m02_map_feasibility.composed_source_identity(
        accepted["composed_source_identity_sha256"],
        delta["series_sha256"],
        patch_records,
        delta["result_tree"],
    )
    require(
        observed_identity == delta["composed_source_identity_sha256"],
        "native scenario/reset composed source identity mismatch",
    )
    report_schema = repository_path(root, oracle["report_schema"]["path"], "report schema")
    require(sha256_file(report_schema) == oracle["report_schema"]["sha256"], "reset report schema digest mismatch")
    trajectory_schema = repository_path(root, oracle["trajectory_schema"]["path"], "trajectory schema")
    require(sha256_file(trajectory_schema) == oracle["trajectory_schema"]["sha256"], "trajectory schema digest mismatch")
    templates = oracle["oracle"]["templates"]
    expected_ids = [f"m02-template-{number:02d}" for number in range(1, 9)]
    require([item["template_id"] for item in templates] == expected_ids, "oracle template order or inventory mismatch")
    expected = {item["template_id"]: item for item in templates}
    require(len({item["projection_sha256"] for item in templates}) == 8, "oracle projection digests are not distinct")
    require(len({item["trajectory_report_sha256"] for item in templates}) == 8, "oracle trajectory digests are not distinct")
    return expected


def stage_runtime(executable: pathlib.Path, opengfx: pathlib.Path, runtime: pathlib.Path) -> dict[str, str]:
    runtime.mkdir(parents=True, exist_ok=False)
    baseset = runtime / "baseset"
    baseset.mkdir()
    source_root = executable.parent
    source_baseset = source_root / "baseset"
    require((source_root / "lang").is_dir(), f"OpenTTD runtime language directory is missing: {source_root / 'lang'}")
    staged_executable = runtime / "openttd"
    shutil.copyfile(executable, staged_executable)
    staged_executable.chmod(0o755)
    shutil.copytree(source_root / "lang", runtime / "lang", copy_function=shutil.copyfile)
    for name in RUNTIME_BASESET_FILES:
        source = source_baseset / name
        require(source.is_file(), f"required OpenTTD runtime asset is missing: {source}")
        shutil.copyfile(source, baseset / name)
    shutil.copyfile(opengfx, baseset / "opengfx-8.0.tar")

    records: dict[str, str] = {}
    for path in sorted(item for item in runtime.rglob("*") if item.is_file()):
        records[path.relative_to(runtime).as_posix()] = sha256_file(path)
    return records


def dynamic_libraries(executable: pathlib.Path, environment: dict[str, str]) -> list[dict[str, str]]:
    result = subprocess.run(
        ["ldd", str(executable)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=environment,
    )
    require(result.returncode == 0, f"ldd failed: {(result.stderr or result.stdout).strip()}")
    require("not found" not in result.stdout, f"unresolved dynamic library: {result.stdout.strip()}")
    records: dict[str, str] = {}
    for line in result.stdout.splitlines():
        match = re.match(r"\s*(\S+)\s+=>\s+(/\S+)\s+\(", line)
        if match is None:
            match = re.match(r"\s*(/\S+)\s+\(", line)
            if match is None:
                continue
            name, raw_path = pathlib.Path(match.group(1)).name, match.group(1)
        else:
            name, raw_path = match.group(1), match.group(2)
        path = pathlib.Path(raw_path).resolve()
        require(path.is_file(), f"resolved dynamic library is not a file: {path}")
        digest = sha256_file(path)
        if name in records:
            require(records[name] == digest, f"dynamic library {name} resolved inconsistently")
        records[name] = digest
    require(records, "ldd produced no resolved dynamic-library inventory")
    return [{"name": name, "sha256": records[name]} for name in sorted(records)]


def run_native(
    executable: pathlib.Path,
    run_root: pathlib.Path,
    instance: pathlib.Path,
    repetitions: int,
    environment: dict[str, str],
    timeout: int,
) -> tuple[pathlib.Path, pathlib.Path, list[str], str]:
    run_root.mkdir(parents=True, exist_ok=False)
    output = run_root / "report.json"
    trajectory_output = run_root / "trajectory.json"
    command = [
        str(executable),
        "-X",
        "-v",
        "null:ticks=1",
        "-s",
        "null",
        "-m",
        "null",
        "-b",
        "null",
        "-I",
        "OpenGFX",
        "-Q",
        "-x",
        "-c",
        str(run_root / "openttd.cfg"),
        "-Z",
        str(instance),
        "-Y",
        str(output),
        "-T",
        str(trajectory_output),
        "-R",
        str(repetitions),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=run_root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise M02ResetOracleError(f"native reset timed out after {timeout} seconds") from exc
    require(result.returncode == 0, f"native reset exited {result.returncode}: {(result.stderr or result.stdout).strip()}")
    require(result.stderr == "", f"native reset wrote stderr: {result.stderr.strip()}")
    require(FORBIDDEN_DIAGNOSTIC.search(result.stdout) is None, f"native reset emitted a forbidden diagnostic: {result.stdout.strip()}")
    require(
        re.fullmatch(
            rf"M02_SCENARIO_RESET=PASS template=m02-template-[0-9]{{2}} repetitions={repetitions} projection_bytes=[0-9]+ trajectory=PASS\n",
            result.stdout,
        )
        is not None,
        f"native reset human output is not canonical: {result.stdout!r}",
    )
    require(output.is_file() and not output.is_symlink(), "native reset did not create a regular report")
    require(trajectory_output.is_file() and not trajectory_output.is_symlink(), "native trajectory did not create a regular report")
    normalized_command = [
        "<runtime>/openttd" if item == str(executable) else
        "<run>/openttd.cfg" if item == str(run_root / "openttd.cfg") else
        "<instance>" if item == str(instance) else
        "<run>/report.json" if item == str(output) else item
        for item in command
    ]
    normalized_command = [
        "<run>/trajectory.json" if item == str(trajectory_output) else item
        for item in normalized_command
    ]
    return output, trajectory_output, normalized_command, result.stdout.rstrip("\n")


def write_canonical_new(path: pathlib.Path, value: dict[str, Any]) -> None:
    generate_m02_scenario.write_new(path.resolve(), value)


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    executable = args.executable.resolve()
    opengfx = args.opengfx_tar.resolve()
    artifact_root = args.artifact_root.resolve()
    oracle_path = args.oracle.resolve() if args.oracle else root / "config/v1/m02-reset-oracle.json"
    require(executable.is_file() and os.access(executable, os.X_OK), f"OpenTTD executable is not executable: {executable}")
    require(opengfx.is_file() and not opengfx.is_symlink(), f"OpenGFX archive is not a regular file: {opengfx}")
    require(not artifact_root.exists() and not artifact_root.is_symlink(), f"artifact root already exists: {artifact_root}")
    oracle = validate_m02_scenario_contract.load_strict_json(oracle_path)
    expected_templates = validate_oracle_config(root, oracle)
    require(
        sha256_file(opengfx) == oracle["content"]["opengfx_archive_sha256"],
        "OpenGFX archive digest is not the frozen 8.0 payload",
    )
    require(oracle["content"]["opengfx_metadata_version"] == 9499, "OpenGFX internal metadata version drifted")

    contract, corpus, ledger = generate_m02_scenario.load_and_validate(
        root / "config/v1/m02-scenario-contract.json",
        root / "docs/project/schema/v1-m02-scenario-contract.schema.json",
        root / "config/v1/m02-scenario-corpus.json",
        root / "docs/project/schema/v1-m02-scenario-corpus.schema.json",
        root / "config/v1/m02-seed-ledger.json",
        root / "docs/project/schema/v1-m02-seed-ledger.schema.json",
    )
    selected = args.template_id or [item["template_id"] for item in corpus["templates"]]
    require(len(selected) == len(set(selected)), "template selection contains duplicates")
    by_id = {item["template_id"]: item for item in corpus["templates"]}
    require(set(selected) <= set(by_id), f"unknown template selection: {sorted(set(selected) - set(by_id))}")
    if any(by_id[item]["split"] == "final-evaluation" for item in selected):
        require(args.allow_final_evaluation, "final-evaluation templates require --allow-final-evaluation")

    artifact_root.mkdir(parents=True)
    runtime = artifact_root / "runtime"
    runtime_assets = stage_runtime(executable, opengfx, runtime)
    staged_executable = runtime / "openttd"
    environment = os.environ.copy()
    environment.update({"LC_ALL": "C", "LANG": "C", "TZ": "UTC", "SOURCE_DATE_EPOCH": "1742688000"})
    if args.sysroot is not None:
        sysroot = args.sysroot.resolve()
        library_directories = [
            sysroot / "usr/lib/x86_64-linux-gnu",
            sysroot / "usr/lib/x86_64-linux-gnu/pulseaudio",
        ]
        for directory in library_directories:
            require(directory.is_dir(), f"sysroot runtime library directory is missing: {directory}")
        prior = environment.get("LD_LIBRARY_PATH")
        environment["LD_LIBRARY_PATH"] = ":".join(
            [*(str(item) for item in library_directories), *([prior] if prior else [])]
        )
    libraries = dynamic_libraries(staged_executable, environment)

    report_schema = root / oracle["report_schema"]["path"]
    trajectory_schema = root / oracle["trajectory_schema"]["path"]
    contract_path = root / "config/v1/m02-scenario-contract.json"
    contract_schema = root / "docs/project/schema/v1-m02-scenario-contract.schema.json"
    instance_schema = root / "docs/project/schema/v1-m02-scenario-instance.schema.json"
    records: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    for template_id in selected:
        template = by_id[template_id]
        instance = generate_m02_scenario.build_instance(contract, corpus, ledger, template, instance_schema)
        instance_path = artifact_root / "instances" / f"{template_id}.json"
        write_canonical_new(instance_path, instance)

        clean_reports: list[pathlib.Path] = []
        clean_trajectories: list[pathlib.Path] = []
        clean_commands: list[list[str]] = []
        clean_stdout: list[str] = []
        for repetition in range(1, oracle["oracle"]["clean_process_repetitions"] + 1):
            report_path, trajectory_path, command, stdout = run_native(
                staged_executable,
                artifact_root / "runs" / template_id / f"clean-{repetition}",
                instance_path,
                1,
                environment,
                args.timeout,
            )
            _, digest = validate_m02_reset_projection.validate_paths(
                report_path, instance_path, contract_path, contract_schema, report_schema
            )
            require(digest == expected_templates[template_id]["projection_sha256"], f"{template_id} projection digest drifted")
            _, trajectory_digest = validate_m02_scripted_trajectory.validate_paths(
                trajectory_path, instance_path, trajectory_schema
            )
            require(
                trajectory_digest == expected_templates[template_id]["trajectory_report_sha256"],
                f"{template_id} trajectory digest drifted",
            )
            clean_reports.append(report_path)
            clean_trajectories.append(trajectory_path)
            clean_commands.append(command)
            clean_stdout.append(stdout)
        first_clean = clean_reports[0].read_bytes()
        require(all(item.read_bytes() == first_clean for item in clean_reports[1:]), f"{template_id} clean-process reports differ")
        first_trajectory = clean_trajectories[0].read_bytes()
        require(
            all(item.read_bytes() == first_trajectory for item in clean_trajectories[1:]),
            f"{template_id} clean-process trajectories differ",
        )
        require(len(set(clean_stdout)) == 1, f"{template_id} clean-process human outputs differ")

        same_report, same_trajectory, same_command, same_stdout = run_native(
            staged_executable,
            artifact_root / "runs" / template_id / "same-process",
            instance_path,
            oracle["oracle"]["same_process_repetitions"],
            environment,
            args.timeout,
        )
        same_value, same_digest = validate_m02_reset_projection.validate_paths(
            same_report, instance_path, contract_path, contract_schema, report_schema
        )
        clean_value = validate_m02_reset_projection.load_canonical_json(clean_reports[0])
        require(same_digest == expected_templates[template_id]["projection_sha256"], f"{template_id} same-process projection digest drifted")
        require(
            validate_m02_reset_projection.canonical_bytes(same_value["projection"])
            == validate_m02_reset_projection.canonical_bytes(clean_value["projection"]),
            f"{template_id} same-process projection differs from clean-process oracle",
        )
        _, same_trajectory_digest = validate_m02_scripted_trajectory.validate_paths(
            same_trajectory, instance_path, trajectory_schema
        )
        require(
            same_trajectory_digest == expected_templates[template_id]["trajectory_report_sha256"],
            f"{template_id} same-process trajectory digest drifted",
        )
        require(
            same_trajectory.read_bytes() == first_trajectory,
            f"{template_id} trajectory after same-process resets differs from clean-process trajectory",
        )
        records.append(
            {
                "clean_process_report_sha256": sha256_file(clean_reports[0]),
                "projection_sha256": same_digest,
                "same_process_report_sha256": sha256_file(same_report),
                "scenario_sha256": instance["identity"]["scenario_sha256"],
                "split": template["split"],
                "template_id": template_id,
                "trajectory_report_sha256": same_trajectory_digest,
            }
        )
        for index, command in enumerate(clean_commands, 1):
            commands.append({"argv": command, "mode": f"clean-{index}", "template_id": template_id})
        commands.append({"argv": same_command, "mode": "same-process", "template_id": template_id})
        print(f"M02_RESET_ORACLE_TEMPLATE=PASS template={template_id} projection_sha256={same_digest}")

    manifest = {
        "commands_sha256": hashlib.sha256(validate_m02_reset_projection.canonical_bytes(commands)).hexdigest(),
        "content": {
            "opengfx_archive_sha256": sha256_file(opengfx),
            "runtime_asset_identity_sha256": hashlib.sha256(
                validate_m02_reset_projection.canonical_bytes(runtime_assets)
            ).hexdigest(),
        },
        "dynamic_libraries": libraries,
        "executable_sha256": sha256_file(staged_executable),
        "native_delta_composed_source_identity_sha256": oracle["native_delta"]["composed_source_identity_sha256"],
        "oracle": {
            "clean_process_repetitions": oracle["oracle"]["clean_process_repetitions"],
            "same_process_repetitions": oracle["oracle"]["same_process_repetitions"],
        },
        "schema_version": "openttd-rl-v1-m02-reset-oracle-report-1",
        "status": "PASS",
        "templates": records,
    }
    write_canonical_new(artifact_root / "commands.json", {"commands": commands})
    write_canonical_new(artifact_root / "manifest.json", manifest)
    return manifest


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=pathlib.Path)
    parser.add_argument("--executable", required=True, type=pathlib.Path)
    parser.add_argument("--opengfx-tar", required=True, type=pathlib.Path)
    parser.add_argument("--artifact-root", required=True, type=pathlib.Path)
    parser.add_argument("--oracle", type=pathlib.Path)
    parser.add_argument("--sysroot", type=pathlib.Path)
    parser.add_argument("--template-id", action="append")
    parser.add_argument("--allow-final-evaluation", action="store_true")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        require(1 <= args.timeout <= 3600, "timeout must be in 1..3600 seconds")
        manifest = run(args)
    except (
        OSError,
        KeyError,
        M02ResetOracleError,
        generate_m02_scenario.M02ScenarioGenerationError,
        validate_m02_reset_projection.M02ResetProjectionError,
        validate_m02_scripted_trajectory.M02ScriptedTrajectoryError,
        validate_m02_scenario_contract.M02ScenarioContractError,
    ) as exc:
        print(f"M02_RESET_ORACLE=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "M02_RESET_ORACLE=PASS "
        f"templates={len(manifest['templates'])} "
        f"executable_sha256={manifest['executable_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
