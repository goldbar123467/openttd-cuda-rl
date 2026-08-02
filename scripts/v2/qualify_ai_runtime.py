#!/usr/bin/env python3
"""Run one byte-locked external AI through isolated start/save/load qualification."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import resource
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

import jsonschema

import acquire_ai_package


SCHEMA_RELATIVE = pathlib.Path("docs/project/schema/v2-ai-runtime-qualification.schema.json")
MANIFEST_NAME = "ai-runtime-qualification.json"
TRANSCRIPT_NAME = "openttd-runtime-console.log"
COPIED_LOCK_NAME = "ai-package-lock.json"
SAVE_BASENAME = "v2-qualification"
LIMITS = {
    "address_space_bytes": 2 * 1024 * 1024 * 1024,
    "cpu_seconds": 180,
    "file_bytes": 256 * 1024 * 1024,
    "open_files": 256,
    "processes": 256,
}


class AIRuntimeError(ValueError):
    """Runtime qualification could not establish a required observation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AIRuntimeError(message)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AIRuntimeError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def closure_sha256(packages: list[dict[str, Any]]) -> str:
    value = "".join(
        f"{package['local_unique_id']} {package['archive_size']} {package['archive_sha256']}\n"
        for package in packages
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def copy_package_closure(source_lock: pathlib.Path, artifact_root: pathlib.Path, lock: dict[str, Any]) -> pathlib.Path:
    for package in lock["packages"]:
        relative = pathlib.Path(package["archive_path"])
        source = source_lock.parent / relative
        target = artifact_root / relative
        require(source.is_file() and not source.is_symlink(), f"source archive is missing or a symlink: {source}")
        require(sha256_file(source) == package["archive_sha256"], f"source archive SHA-256 drifted: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o444)
    copied_lock = artifact_root / COPIED_LOCK_NAME
    shutil.copyfile(source_lock, copied_lock)
    copied_lock.chmod(0o444)
    return copied_lock


def apply_limits() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (LIMITS["address_space_bytes"], LIMITS["address_space_bytes"]))
    resource.setrlimit(resource.RLIMIT_CPU, (LIMITS["cpu_seconds"], LIMITS["cpu_seconds"]))
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS["file_bytes"], LIMITS["file_bytes"]))
    resource.setrlimit(resource.RLIMIT_NOFILE, (LIMITS["open_files"], LIMITS["open_files"]))
    resource.setrlimit(resource.RLIMIT_NPROC, (LIMITS["processes"], LIMITS["processes"]))


def current_rss_kib(pid: int) -> int:
    try:
        for line in pathlib.Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith(("VmHWM:", "VmRSS:")):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return 0


def process_tree_rss_kib(root_pid: int) -> int:
    pending = [root_pid]
    seen: set[int] = set()
    total = 0
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        total += current_rss_kib(pid)
        try:
            children = pathlib.Path(f"/proc/{pid}/task/{pid}/children").read_text(encoding="ascii").split()
            pending.extend(int(child) for child in children)
        except (OSError, ValueError):
            pass
    return total


def monitor_rss(process: subprocess.Popen[str], stop: threading.Event, result: list[int]) -> None:
    maximum = 0
    while not stop.wait(0.05):
        maximum = max(maximum, process_tree_rss_kib(process.pid))
        if process.poll() is not None:
            break
    result.append(maximum)


COMPANY_PATTERN = re.compile(
    r"^#:(?P<id>[0-9]+)\([^)]*\).* Money: (?P<money>-?[0-9]+)  Loan: (?P<loan>[0-9]+)  "
    r"Value: (?P<value>-?[0-9]+)  \(T:(?P<trains>[0-9]+), R:(?P<road>[0-9]+), "
    r"P:(?P<air>[0-9]+), S:(?P<ships>[0-9]+)\) AI$"
)


def parse_company(line: str) -> dict[str, int] | None:
    match = COMPANY_PATTERN.match(line)
    if match is None:
        return None
    values = {key: int(value) for key, value in match.groupdict().items()}
    return {
        "company_id": values["id"],
        "money": values["money"],
        "loan": values["loan"],
        "value": values["value"],
        "trains": values["trains"],
        "road_vehicles": values["road"],
        "aircraft": values["air"],
        "ships": values["ships"],
    }


def poll_company(session: acquire_ai_package.ConsoleSession, timeout: float) -> dict[str, int]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        start = session.send("companies")
        try:
            _, line = session.wait_for(
                lambda candidate: parse_company(candidate) is not None,
                start=start,
                timeout=min(1.0, max(0.01, deadline - time.monotonic())),
                label="AI company",
            )
            company = parse_company(line)
            assert company is not None
            return company
        except acquire_ai_package.AIPackageError:
            with session.condition:
                session.condition.wait(timeout=min(0.2, max(0.0, deadline - time.monotonic())))
    raise AIRuntimeError("AI company did not appear before the qualification timeout")


def query_date(session: acquire_ai_package.ConsoleSession, timeout: float = 5.0) -> dt.date:
    start = session.send("getdate")
    _, line = session.wait_for(
        lambda candidate: re.fullmatch(r"Date: [0-9]{4}-[0-9]{2}-[0-9]{2}", candidate) is not None,
        start=start,
        timeout=timeout,
        label="game date",
    )
    return dt.date.fromisoformat(line.removeprefix("Date: "))


def wait_elapsed_days(
    session: acquire_ai_package.ConsoleSession,
    start_date: dt.date,
    minimum_days: int,
    timeout: float,
) -> dt.date:
    deadline = time.monotonic() + timeout
    latest = start_date
    while (latest - start_date).days < minimum_days:
        require(time.monotonic() < deadline, f"game advanced only {(latest - start_date).days} of {minimum_days} required days")
        with session.condition:
            session.condition.wait(timeout=min(0.5, max(0.0, deadline - time.monotonic())))
        latest = query_date(session, timeout=min(5.0, max(0.1, deadline - time.monotonic())))
    return latest


def wait_nonempty_stable_file(path: pathlib.Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    previous = -1
    stable = 0
    while time.monotonic() < deadline:
        size = path.stat().st_size if path.is_file() else 0
        if size > 0 and size == previous:
            stable += 1
            if stable >= 2:
                return
        else:
            stable = 0
        previous = size
        time.sleep(0.1)
    raise AIRuntimeError(f"savegame did not become nonempty and stable: {path}")


def write_config(path: pathlib.Path, seed: int) -> None:
    path.write_text(
        "[game_creation]\n"
        "map_x = 7\n"
        "map_y = 7\n"
        "starting_year = 1950\n"
        f"generation_seed = {seed}\n"
        "landscape = temperate\n\n"
        "[ai]\n"
        "ai_in_multiplayer = true\n"
        "ai_disable_veh_train = false\n"
        "ai_disable_veh_roadveh = false\n"
        "ai_disable_veh_aircraft = false\n"
        "ai_disable_veh_ship = false\n\n"
        "[network]\n"
        "server_advertise = false\n"
        "server_name = V2 AI runtime qualification\n",
        encoding="utf-8",
    )


def command_for(
    openttd: pathlib.Path,
    artifact_root: pathlib.Path,
    config_path: pathlib.Path,
    sandbox: str,
    scenario_save: pathlib.Path | None = None,
) -> list[str]:
    port = 3979 if sandbox == "bubblewrap" else acquire_ai_package.reserve_port()
    openttd_command = [
        str(openttd), "-D", f"127.0.0.1:{port}", "-v", "dedicated", "-s", "null", "-m", "null",
        "-x", "-X", "-c", str(config_path),
    ]
    if scenario_save is not None:
        openttd_command.extend(("-g", str(scenario_save)))
    if sandbox == "test-none":
        return openttd_command
    bwrap = shutil.which("bwrap")
    require(bwrap is not None, "bubblewrap is required for runtime qualification")
    return [
        bwrap,
        "--die-with-parent",
        "--new-session",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--unshare-net",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--bind", str(artifact_root), str(artifact_root),
        "--chdir", str(openttd.parent),
        "--",
        *openttd_command,
    ]


def validate_manifest(
    root: pathlib.Path,
    manifest_path: pathlib.Path,
    *,
    openttd: pathlib.Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    artifact_root = manifest_path.parent
    manifest = load_json(manifest_path)
    schema_path = root / SCHEMA_RELATIVE
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(manifest)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise AIRuntimeError(f"qualification schema failed at {location}: {exc.message}") from exc
    require(manifest["schema_sha256"] == sha256_file(schema_path), "qualification schema SHA-256 mismatch")
    source = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    require(manifest["engine_source"] == {key: source[key] for key in ("release", "commit", "tree")}, "qualification engine source drifted")
    if openttd is not None:
        openttd = openttd.resolve()
        require(manifest["executable"]["sha256"] == sha256_file(openttd), "qualification executable SHA-256 mismatch")
        require(manifest["executable"]["size"] == openttd.stat().st_size, "qualification executable size mismatch")
    copied_lock = artifact_root / COPIED_LOCK_NAME
    require(manifest["package_lock"]["sha256"] == sha256_file(copied_lock), "qualification package-lock SHA-256 mismatch")
    try:
        lock = acquire_ai_package.validate_lock(root, copied_lock, openttd=openttd)
    except acquire_ai_package.AIPackageError as exc:
        raise AIRuntimeError(f"qualification package closure failed: {exc}") from exc
    require(manifest["package_lock"]["closure_sha256"] == closure_sha256(lock["packages"]), "qualification closure SHA-256 mismatch")
    transcript = artifact_root / TRANSCRIPT_NAME
    require(transcript.is_file(), "qualification console transcript is missing")
    require(manifest["resources"]["console_transcript_sha256"] == sha256_file(transcript), "qualification transcript SHA-256 mismatch")
    save = manifest["observations"]["save"]
    if save is not None:
        save_path = artifact_root / save["path"]
        require(save_path.is_file(), "qualification savegame is missing")
        require(save_path.stat().st_size == save["size"], "qualification savegame size mismatch")
        require(sha256_file(save_path) == save["sha256"], "qualification savegame SHA-256 mismatch")
    checks = manifest["checks"]
    if manifest["outcome"] != "REJECTED":
        require(all(checks.values()), "qualified runtime has a failed check")
        company = manifest["observations"]["company_after_load"]
        assert company is not None
        vehicles = sum(company[key] for key in ("trains", "road_vehicles", "aircraft", "ships"))
        if manifest["outcome"] == "QUALIFIED_ACTIVE":
            require(vehicles > 0, "active qualification has no vehicles")
        elif manifest["outcome"] == "QUALIFIED_CONTROL":
            require(manifest["package_lock"]["catalog_name"] == "NoOpAI" and vehicles == 0, "control qualification is not inactive NoOpAI")
        else:
            require(vehicles == 0, "healthy-inactive qualification has vehicles")
    return manifest


def qualify(
    root: pathlib.Path,
    openttd: pathlib.Path,
    source_lock: pathlib.Path,
    artifact_root: pathlib.Path,
    *,
    seed: int,
    minimum_days: int,
    timeout: float,
    sandbox: str,
    scenario_save: pathlib.Path | None = None,
) -> pathlib.Path:
    root = root.resolve()
    openttd = openttd.resolve()
    source_lock = source_lock.resolve()
    require(artifact_root.is_absolute() and not artifact_root.exists() and not artifact_root.is_symlink(), "artifact root must be a new absolute path")
    require(0 <= seed <= 0xFFFFFFFF, "generation seed is outside uint32")
    require(minimum_days > 0 and timeout > 0, "minimum days and timeout must be positive")
    require(sandbox in {"bubblewrap", "test-none"}, "unknown sandbox kind")
    if scenario_save is not None:
        scenario_save = scenario_save.resolve()
        require(scenario_save.is_file() and not scenario_save.is_symlink(), "scenario save is missing or a symlink")
    try:
        lock = acquire_ai_package.validate_lock(root, source_lock, openttd=openttd)
    except acquire_ai_package.AIPackageError as exc:
        raise AIRuntimeError(f"source package lock failed: {exc}") from exc
    primary = next(item for item in lock["packages"] if item["local_unique_id"] == lock["request"]["content_unique_id"])
    info = primary.get("declared_info")
    require(info is not None, "requested AI archive has no parseable declared info")
    declared_name = info["name"]
    declared_version = info["version"]
    artifact_root.mkdir(mode=0o700)
    copied_lock = copy_package_closure(source_lock, artifact_root, lock)
    config_path = artifact_root / "openttd.cfg"
    write_config(config_path, seed)
    environment = acquire_ai_package.isolated_environment(artifact_root)

    checks = {
        "declared_identity_listed": False,
        "company_started": False,
        "minimum_days_elapsed": False,
        "save_created": False,
        "company_survived_load": False,
        "no_script_crash": False,
        "resource_limits_respected": False,
    }
    observations: dict[str, Any] = {
        "list_line": None,
        "start_date": None,
        "pre_save_date": None,
        "post_load_date": None,
        "company_before_load": None,
        "company_after_load": None,
        "save": None,
    }
    errors: list[str] = []
    session: acquire_ai_package.ConsoleSession | None = None
    reported_version: str | None = None
    returncode: int | None = None
    max_rss: list[int] = []
    rss_stop = threading.Event()
    rss_thread: threading.Thread | None = None
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            command_for(openttd, artifact_root, config_path, sandbox, scenario_save),
            cwd=openttd.parent,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            preexec_fn=apply_limits,
            start_new_session=True,
        )
        session = acquire_ai_package.ConsoleSession(process)
        rss_thread = threading.Thread(target=monitor_rss, args=(process, rss_stop, max_rss), daemon=True)
        rss_thread.start()
        session.wait_for(
            lambda line: (line.startswith("Map ") and "starting game" in line) or "Listening on 127.0.0.1:" in line or line == "FAKE CONTENT READY",
            start=0,
            timeout=min(30.0, timeout),
            label="qualification server readiness",
        )
        version_match = re.search(r"(?:version |Revision [0-9]+ - )([^\s]+)", "\n".join(session.snapshot()))
        if version_match is not None:
            reported_version = version_match.group(1)
        list_start = session.send("list_ai")
        _, list_line = session.wait_for(
            lambda line: re.search(rf"^\s*{re.escape(declared_name)} \(v{declared_version}\):", line) is not None,
            start=list_start,
            timeout=min(10.0, timeout),
            label="declared AI identity in list_ai",
        )
        observations["list_line"] = list_line.strip()
        checks["declared_identity_listed"] = True
        observations["start_date"] = query_date(session).isoformat()
        start_command = f"start_ai {json.dumps(f'{declared_name}.{declared_version}') }"
        command_start = session.send(start_command)
        company = poll_company(session, min(15.0, timeout))
        checks["company_started"] = True
        failure_lines = [
            line for line in session.snapshot(command_start)
            if "failed to load the specified ai" in line.casefold()
        ]
        require(not failure_lines, failure_lines[0] if failure_lines else "AI start failed")
        pre_save_date = wait_elapsed_days(
            session,
            dt.date.fromisoformat(observations["start_date"]),
            minimum_days,
            timeout,
        )
        observations["pre_save_date"] = pre_save_date.isoformat()
        checks["minimum_days_elapsed"] = True
        observations["company_before_load"] = poll_company(session, 5.0)
        save_start = session.send(f"save {SAVE_BASENAME}")
        session.wait_for(
            lambda line: line.startswith("Map successfully saved to "),
            start=save_start,
            timeout=15.0,
            label="qualification savegame",
        )
        save_matches = list(artifact_root.rglob(f"{SAVE_BASENAME}.sav"))
        require(len(save_matches) == 1, f"expected one qualification savegame, found {save_matches}")
        save_path = save_matches[0]
        wait_nonempty_stable_file(save_path, 10.0)
        observations["save"] = {
            "path": save_path.relative_to(artifact_root).as_posix(),
            "size": save_path.stat().st_size,
            "sha256": sha256_file(save_path),
        }
        checks["save_created"] = True
        load_start = session.send(f"load {SAVE_BASENAME}.sav")
        session.wait_for(
            lambda line: "Listening on 127.0.0.1:" in line or line == "FAKE LOAD COMPLETE",
            start=load_start,
            timeout=20.0,
            label="qualification savegame reload",
        )
        observations["company_after_load"] = poll_company(session, 20.0)
        observations["post_load_date"] = query_date(session, timeout=15.0).isoformat()
        checks["company_survived_load"] = True
    except (AIRuntimeError, acquire_ai_package.AIPackageError, OSError, subprocess.SubprocessError) as exc:
        errors.append(str(exc))
    finally:
        acquire_ai_package.terminate_process(session)
        if session is not None:
            returncode = session.process.returncode
            (artifact_root / TRANSCRIPT_NAME).write_text(session.transcript(), encoding="utf-8")
            acquire_ai_package.close_process_streams(session)
        else:
            (artifact_root / TRANSCRIPT_NAME).write_text("", encoding="utf-8")
        rss_stop.set()
        if rss_thread is not None:
            rss_thread.join(timeout=1)

    transcript_path = artifact_root / TRANSCRIPT_NAME
    transcript = transcript_path.read_text(encoding="utf-8")
    crash_lines = sorted({
        line for line in transcript.splitlines()
        if "your script made an error" in line.casefold() or "fatal error" in line.casefold()
    })
    if crash_lines:
        errors.extend(crash_lines)
    checks["no_script_crash"] = not crash_lines
    checks["resource_limits_respected"] = returncode == 0
    all_checks = all(checks.values())
    after = observations["company_after_load"]
    vehicles = 0 if after is None else sum(after[key] for key in ("trains", "road_vehicles", "aircraft", "ships"))
    if not all_checks:
        outcome = "REJECTED"
    elif lock["request"]["name"] == "NoOpAI":
        outcome = "QUALIFIED_CONTROL"
    elif vehicles > 0:
        outcome = "QUALIFIED_ACTIVE"
    else:
        outcome = "QUALIFIED_HEALTHY_INACTIVE"

    source = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    manifest = {
        "$schema": "../../docs/project/schema/v2-ai-runtime-qualification.schema.json",
        "schema_version": "openttd-rl-v2-ai-runtime-qualification-1",
        "schema_sha256": sha256_file(root / SCHEMA_RELATIVE),
        "engine_source": {key: source[key] for key in ("release", "commit", "tree")},
        "executable": {"sha256": sha256_file(openttd), "size": openttd.stat().st_size, "reported_version": reported_version},
        "package_lock": {
            "sha256": sha256_file(copied_lock),
            "catalog_name": lock["request"]["name"],
            "catalog_unique_id": lock["request"]["content_unique_id"],
            "catalog_version": lock["request"]["version"],
            "declared_name": declared_name,
            "declared_version": declared_version,
            "api_version": info.get("api_version"),
            "package_count": len(lock["packages"]),
            "closure_sha256": closure_sha256(lock["packages"]),
        },
        "sandbox": {
            "kind": sandbox,
            "read_only_root": sandbox == "bubblewrap",
            "private_network": sandbox == "bubblewrap",
            "new_session": True,
            "resource_limits": LIMITS,
        },
        "scenario": {"map_width": 128, "map_height": 128, "start_year": 1950, "generation_seed": seed, "minimum_elapsed_days": minimum_days},
        "checks": checks,
        "observations": observations,
        "resources": {
            "wall_seconds": round(time.monotonic() - started, 6),
            "max_rss_kib": max(max_rss, default=0),
            "process_returncode": returncode,
            "console_transcript_sha256": sha256_file(transcript_path),
        },
        "outcome": outcome,
        "error_details": sorted(set(errors)),
    }
    manifest_path = artifact_root / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validate_manifest(root, manifest_path, openttd=openttd)
    return manifest_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    subparsers = parser.add_subparsers(dest="command", required=True)
    qualify_parser = subparsers.add_parser("qualify")
    qualify_parser.add_argument("--openttd", type=pathlib.Path, required=True)
    qualify_parser.add_argument("--lock", type=pathlib.Path, required=True)
    qualify_parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    qualify_parser.add_argument("--seed", type=int, default=0x51414C31)
    qualify_parser.add_argument("--minimum-days", type=int, default=7)
    qualify_parser.add_argument("--timeout", type=float, default=90.0)
    qualify_parser.add_argument("--sandbox", choices=["bubblewrap", "test-none"], default="bubblewrap")
    qualify_parser.add_argument("--scenario-save", type=pathlib.Path)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--manifest", type=pathlib.Path, required=True)
    validate_parser.add_argument("--openttd", type=pathlib.Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.command == "qualify":
            manifest_path = qualify(
                args.root,
                args.openttd,
                args.lock,
                args.artifact_root,
                seed=args.seed,
                minimum_days=args.minimum_days,
                timeout=args.timeout,
                sandbox=args.sandbox,
                scenario_save=args.scenario_save,
            )
            manifest = load_json(manifest_path)
            print(f"V2_AI_RUNTIME={manifest['outcome']} opponent={manifest['package_lock']['catalog_name']} manifest={manifest_path}")
        else:
            manifest = validate_manifest(args.root, args.manifest, openttd=args.openttd)
            print(f"V2_AI_RUNTIME_LOCK=PASS opponent={manifest['package_lock']['catalog_name']} outcome={manifest['outcome']}")
        return 0
    except (AIRuntimeError, OSError) as exc:
        print(f"V2_AI_RUNTIME=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
