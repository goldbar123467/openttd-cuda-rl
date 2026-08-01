#!/usr/bin/env python3
"""Measure accepted M01 OpenTTD binaries under a preregistered resource plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import re
import resource
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any

import jsonschema


class ResourceMeasurementError(ValueError):
    """A resource plan, accepted binary, workload, or report was invalid."""


HEADLESS_IDENTITY = "102f07d8595673a06888bb935c809c47ea3326f8d66be158a1588e32ec530de3"
PLAYABLE_IDENTITY = "5e50757e298b5c241655663e94a5ce0dde0a69eb4e5d811c467fe2dc63cf3c7b"
EXPECTED_WORKLOADS = [
    "headless-startup-shutdown",
    "headless-tick-throughput",
    "playable-startup-shutdown",
    "playable-paused-idle",
]


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
                raise ResourceMeasurementError(f"{path}: duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ResourceMeasurementError(f"{path}: invalid JSON constant {value}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResourceMeasurementError(f"cannot load {path}: {exc}") from exc


def validate_json(value: Any, schema_path: pathlib.Path, label: str) -> None:
    schema = load_json(schema_path)
    jsonschema.Draft202012Validator.check_schema(schema)
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(item) for item in exc.absolute_path) or "<root>"
        raise ResourceMeasurementError(
            f"{label} schema validation failed at {location}: {exc.message}"
        ) from exc


def validate_plan(plan: dict[str, Any], schema_path: pathlib.Path) -> None:
    validate_json(plan, schema_path, "resource plan")
    ids = [workload["id"] for workload in plan["workloads"]]
    if ids != EXPECTED_WORKLOADS:
        raise ResourceMeasurementError(
            f"workload order/inventory mismatch: expected={EXPECTED_WORKLOADS} actual={ids}"
        )
    required_metrics = {
        "headless-startup-shutdown": {"wall_seconds", "cpu_seconds", "max_rss_kib"},
        "headless-tick-throughput": {
            "wall_seconds",
            "cpu_seconds",
            "max_rss_kib",
            "ticks_per_second",
        },
        "playable-startup-shutdown": {"wall_seconds", "cpu_seconds", "max_rss_kib"},
        "playable-paused-idle": {
            "wall_seconds",
            "cpu_seconds",
            "cpu_utilization_percent",
            "max_rss_kib",
        },
    }
    for workload in plan["workloads"]:
        if set(workload["metrics"]) != required_metrics[workload["id"]]:
            raise ResourceMeasurementError(
                f"metric inventory mismatch for {workload['id']}"
            )


def load_accepted_binary(root: pathlib.Path, expected_identity: str) -> tuple[pathlib.Path, pathlib.Path, dict[str, Any]]:
    manifest_path = root / "build-manifest.json"
    manifest = load_json(manifest_path)
    if manifest.get("result") != "PASS" or manifest.get("build_identity_sha256") != expected_identity:
        raise ResourceMeasurementError(
            f"accepted build identity mismatch at {root}: "
            f"expected={expected_identity} actual={manifest.get('build_identity_sha256')}"
        )
    variant = manifest.get("variant")
    if variant not in {"headless", "playable"}:
        raise ResourceMeasurementError(f"invalid accepted build variant: {variant}")
    prefix = f"opt/openttd-rl-v1-{variant}"
    executable = root / "stage" / prefix / "games/openttd"
    runtime_root = root / "stage" / prefix / "share/games/openttd"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ResourceMeasurementError(f"accepted executable is missing: {executable}")
    if not (runtime_root / "lang/english.lng").is_file():
        raise ResourceMeasurementError(f"accepted runtime data is incomplete: {runtime_root}")
    executable_record = next(
        (
            item
            for item in manifest["install_artifacts"]
            if item.get("path") == "games/openttd" and item.get("type") == "file"
        ),
        None,
    )
    actual_sha256 = sha256_file(executable)
    if executable_record is None or executable_record.get("sha256") != actual_sha256:
        raise ResourceMeasurementError(f"accepted executable digest mismatch: {executable}")
    return executable, runtime_root, manifest


def runtime_environment(root: pathlib.Path, user_root: pathlib.Path) -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("LD_PRELOAD", "XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        environment.pop(name, None)
    environment.update(
        {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
            "SDL_AUDIODRIVER": "dummy",
            "SDL_VIDEODRIVER": "dummy",
            "XDG_CONFIG_HOME": str(user_root / "config"),
            "XDG_DATA_HOME": str(user_root / "data"),
            "LD_LIBRARY_PATH": ":".join(
                [
                    str(root / "sysroot/usr/lib/x86_64-linux-gnu"),
                    str(root / "sysroot/usr/lib/x86_64-linux-gnu/pulseaudio"),
                    str(root / "sysroot/lib/x86_64-linux-gnu"),
                ]
            ),
        }
    )
    return environment


def reap_with_timeout(
    process: subprocess.Popen[bytes],
    timeout_seconds: float,
    terminate_after: float | None,
) -> tuple[int, resource.struct_rusage, float, str]:
    start = time.monotonic()
    deadline = start + timeout_seconds
    termination = "NORMAL"
    while True:
        waited_pid, status, usage = os.wait4(process.pid, os.WNOHANG)
        if waited_pid == process.pid:
            process.returncode = os.waitstatus_to_exitcode(status)
            return process.returncode, usage, time.monotonic() - start, termination
        elapsed = time.monotonic() - start
        if terminate_after is not None and elapsed >= terminate_after:
            process.send_signal(signal.SIGKILL)
            termination = "SIGKILL_AFTER_DECLARED_WINDOW"
            waited_pid, status, usage = os.wait4(process.pid, 0)
            if waited_pid != process.pid:
                raise ResourceMeasurementError("wait4 reaped an unexpected process")
            process.returncode = os.waitstatus_to_exitcode(status)
            return process.returncode, usage, time.monotonic() - start, termination
        if time.monotonic() >= deadline:
            process.kill()
            os.wait4(process.pid, 0)
            raise ResourceMeasurementError(
                f"workload timed out after {timeout_seconds:.3f} seconds"
            )
        time.sleep(0.005)


def run_sample(
    command: list[str],
    cwd: pathlib.Path,
    environment: dict[str, str],
    log_path: pathlib.Path,
    timeout_seconds: float,
    terminate_after: float | None,
    index: int,
    ticks: int | None,
) -> tuple[dict[str, Any], str]:
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        exit_code, usage, wall_seconds, termination = reap_with_timeout(
            process, timeout_seconds, terminate_after
        )
    output = log_path.read_text(encoding="utf-8", errors="replace")
    if termination == "NORMAL" and exit_code != 0:
        raise ResourceMeasurementError(
            f"sample exited with code {exit_code}; see {log_path}"
        )
    if termination != "NORMAL" and exit_code != -signal.SIGKILL:
        raise ResourceMeasurementError(
            f"idle sample expected SIGKILL exit {-signal.SIGKILL}, got {exit_code}; see {log_path}"
        )
    cpu_seconds = usage.ru_utime + usage.ru_stime
    sample: dict[str, Any] = {
        "index": index,
        "wall_seconds": round(wall_seconds, 6),
        "user_seconds": round(usage.ru_utime, 6),
        "system_seconds": round(usage.ru_stime, 6),
        "cpu_seconds": round(cpu_seconds, 6),
        "max_rss_kib": usage.ru_maxrss,
        "exit_code": exit_code,
        "termination": termination,
    }
    if ticks is not None:
        sample["ticks_per_second"] = round(ticks / wall_seconds, 3)
    if terminate_after is not None:
        sample["cpu_utilization_percent"] = round(cpu_seconds / wall_seconds * 100, 3)
    return sample, output


def aggregate(samples: list[dict[str, Any]], metrics: list[str]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for metric in metrics:
        values = [float(sample[metric]) for sample in samples]
        result[metric] = {
            "median": round(statistics.median(values), 6),
            "minimum": round(min(values), 6),
            "maximum": round(max(values), 6),
        }
    return result


def write_json(path: pathlib.Path, value: Any) -> None:
    if path.exists():
        raise ResourceMeasurementError(f"refusing to overwrite output: {path}")
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_human(report: dict[str, Any]) -> str:
    lines = [
        "OpenTTD RL V1 runtime resource baseline",
        f"result: {report['result']}",
        f"plan: {report['plan']['id']} ({report['plan']['sha256']})",
        "",
    ]
    for workload in report["workloads"]:
        lines.append(workload["id"])
        for metric, values in sorted(workload["aggregate"].items()):
            lines.append(
                f"  {metric}: median={values['median']} "
                f"range={values['minimum']}..{values['maximum']}"
            )
        lines.append("")
    lines.append(f"report identity: {report['report_identity_sha256']}")
    return "\n".join(lines) + "\n"


def measure(options: argparse.Namespace) -> dict[str, Any]:
    artifact_root = options.artifact_root.resolve()
    if not artifact_root.is_dir() or any(artifact_root.iterdir()):
        raise ResourceMeasurementError("artifact root must be an existing empty directory")
    plan = load_json(options.plan)
    validate_plan(plan, options.plan_schema)
    headless_exe, headless_runtime, headless_manifest = load_accepted_binary(
        options.headless_root.resolve(), HEADLESS_IDENTITY
    )
    playable_exe, playable_runtime, playable_manifest = load_accepted_binary(
        options.playable_root.resolve(), PLAYABLE_IDENTITY
    )
    if headless_manifest["variant"] != "headless" or playable_manifest["variant"] != "playable":
        raise ResourceMeasurementError("accepted binary variants are reversed")

    logs = artifact_root / "logs"
    logs.mkdir()
    sampling = plan["sampling"]
    common_tail = [
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
    ]
    workload_specs = [
        {
            "id": "headless-startup-shutdown",
            "command": [str(headless_exe), "-g", "-v", "null:ticks=1", *common_tail],
            "cwd": headless_runtime,
            "root": options.headless_root.resolve(),
            "script": None,
            "terminate_after": None,
            "ticks": None,
        },
        {
            "id": "headless-tick-throughput",
            "command": [
                str(headless_exe),
                "-g",
                "-v",
                f"null:ticks={sampling['headless_ticks']}",
                *common_tail,
            ],
            "cwd": headless_runtime,
            "root": options.headless_root.resolve(),
            "script": None,
            "terminate_after": None,
            "ticks": sampling["headless_ticks"],
        },
        {
            "id": "playable-startup-shutdown",
            "command": [
                str(playable_exe),
                "-g",
                "-v",
                "sdl",
                "-s",
                "null",
                "-m",
                "null",
                "-b",
                "32bpp-anim",
                "-I",
                "OpenGFX",
                "-Q",
                "-x",
                "-d",
                "driver=1",
            ],
            "cwd": playable_runtime,
            "root": options.playable_root.resolve(),
            "script": "exit\n",
            "terminate_after": None,
            "ticks": None,
        },
        {
            "id": "playable-paused-idle",
            "command": [
                str(playable_exe),
                "-g",
                "-v",
                "sdl",
                "-s",
                "null",
                "-m",
                "null",
                "-b",
                "32bpp-anim",
                "-I",
                "OpenGFX",
                "-Q",
                "-x",
                "-d",
                "driver=1",
            ],
            "cwd": playable_runtime,
            "root": options.playable_root.resolve(),
            "script": "pause\n",
            "terminate_after": sampling["idle_seconds"],
            "ticks": None,
        },
    ]
    plan_workloads = {workload["id"]: workload for workload in plan["workloads"]}
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="openttd-rl-resource-") as raw_user_root:
        user_base = pathlib.Path(raw_user_root)
        for workload in workload_specs:
            workload_id = workload["id"]
            warmups: list[dict[str, Any]] = []
            samples: list[dict[str, Any]] = []
            total = sampling["warmup_repetitions"] + sampling["measurement_repetitions"]
            for run_index in range(1, total + 1):
                phase = "warmup" if run_index <= sampling["warmup_repetitions"] else "sample"
                phase_index = (
                    run_index
                    if phase == "warmup"
                    else run_index - sampling["warmup_repetitions"]
                )
                user_root = user_base / workload_id / f"{phase}-{phase_index}"
                scripts = user_root / "data/openttd-v1/scripts"
                scripts.mkdir(parents=True)
                if workload["script"] is not None:
                    (scripts / "game_start.scr").write_text(
                        workload["script"], encoding="utf-8"
                    )
                environment = runtime_environment(workload["root"], user_root)
                sample, output = run_sample(
                    workload["command"],
                    workload["cwd"],
                    environment,
                    logs / f"{workload_id}-{phase}-{phase_index}.log",
                    sampling["timeout_seconds"],
                    workload["terminate_after"],
                    phase_index,
                    workload["ticks"],
                )
                if re.search(plan["correctness"]["forbidden_diagnostics_regex"], output, re.I):
                    raise ResourceMeasurementError(
                        f"{workload_id} emitted a forbidden diagnostic in {phase}-{phase_index}"
                    )
                if workload_id.startswith("playable-"):
                    missing = [
                        value
                        for value in plan["correctness"]["required_playable_diagnostics"]
                        if value not in output
                    ]
                    if missing:
                        raise ResourceMeasurementError(
                            f"{workload_id} omitted required SDL diagnostics: {missing}"
                        )
                (warmups if phase == "warmup" else samples).append(sample)
            metrics = plan_workloads[workload_id]["metrics"]
            results.append(
                {
                    "id": workload_id,
                    "command": [
                        "<HEADLESS_EXECUTABLE>" if item == str(headless_exe) else
                        "<PLAYABLE_EXECUTABLE>" if item == str(playable_exe) else item
                        for item in workload["command"]
                    ],
                    "warmups": warmups,
                    "samples": samples,
                    "aggregate": aggregate(samples, metrics),
                    "result": "PASS",
                }
            )

    report_base = {
        "schema_version": "openttd-rl-v1-resource-measurement-report-1",
        "plan": {"id": plan["plan_id"], "sha256": sha256_file(options.plan)},
        "binaries": {
            "headless": {
                "build_identity_sha256": headless_manifest["build_identity_sha256"],
                "sha256": sha256_file(headless_exe),
                "version": "15.3-v1",
            },
            "playable": {
                "build_identity_sha256": playable_manifest["build_identity_sha256"],
                "sha256": sha256_file(playable_exe),
                "version": "15.3-v1",
            },
        },
        "host": {"architecture": platform.machine(), "os": "ubuntu-24.04"},
        "workloads": results,
        "result": "PASS",
    }
    report = dict(report_base)
    report["report_identity_sha256"] = hashlib.sha256(canonical_bytes(report_base)).hexdigest()
    validate_json(report, options.report_schema, "resource report")
    write_json(artifact_root / "resource-report.json", report)
    (artifact_root / "resource-report.txt").write_text(render_human(report), encoding="utf-8")
    return report


def parse_args(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True, type=pathlib.Path)
    parser.add_argument("--headless-root", required=True, type=pathlib.Path)
    parser.add_argument("--playable-root", required=True, type=pathlib.Path)
    parser.add_argument("--plan", required=True, type=pathlib.Path)
    parser.add_argument("--plan-schema", required=True, type=pathlib.Path)
    parser.add_argument("--report-schema", required=True, type=pathlib.Path)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_args(sys.argv[1:] if arguments is None else arguments)
    try:
        report = measure(options)
    except (ResourceMeasurementError, OSError, UnicodeError) as exc:
        print(f"V1_RUNTIME_RESOURCES=FAIL {exc}", file=sys.stderr)
        return 1
    print(
        "V1_RUNTIME_RESOURCES=PASS "
        f"workloads={len(report['workloads'])} "
        f"identity={report['report_identity_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
