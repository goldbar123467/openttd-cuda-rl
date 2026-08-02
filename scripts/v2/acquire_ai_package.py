#!/usr/bin/env python3
"""Acquire and fail-closed audit one BaNaNaS AI plus its dependency closure."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import pathlib
import queue
import re
import socket
import subprocess
import sys
import tarfile
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

import jsonschema


SCHEMA_RELATIVE = pathlib.Path("docs/project/schema/v2-ai-package-lock.schema.json")
REJECTION_SCHEMA_RELATIVE = pathlib.Path("docs/project/schema/v2-ai-package-rejection.schema.json")
LOCK_NAME = "ai-package-lock.json"
REJECTION_NAME = "ai-package-rejection.json"
TRANSCRIPT_NAME = "openttd-content-console.log"
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 100_000


class AIPackageError(ValueError):
    """The acquisition or package closure violates an M14 invariant."""

    def __init__(self, message: str, reason_code: str = "invariant-failed") -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class CatalogRecord:
    content_id: int
    content_type: str
    state: str
    name: str
    server_unique_id: str
    catalog_md5: str

    @property
    def local_unique_id(self) -> str:
        return bytes.fromhex(self.server_unique_id)[::-1].hex()

    def manifest_dict(self) -> dict[str, Any]:
        return {
            "content_id": self.content_id,
            "content_type": self.content_type,
            "state": self.state,
            "name": self.name,
            "server_unique_id": self.server_unique_id,
            "catalog_md5": self.catalog_md5,
        }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AIPackageError(message)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AIPackageError(f"cannot load JSON {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise AIPackageError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def canonical_version(value: str) -> int:
    match = re.fullmatch(r"v?([1-9][0-9]*)", value)
    require(match is not None, f"opponent version is not a positive integer: {value!r}")
    return int(match.group(1))


def catalog_record(line: str) -> CatalogRecord | None:
    try:
        fields = next(csv.reader([line], skipinitialspace=True))
    except (csv.Error, StopIteration):
        return None
    if len(fields) != 6 or not fields[0].isdigit():
        return None
    content_type = fields[1]
    server_unique_id = fields[4]
    catalog_md5 = fields[5]
    if content_type not in {"AI", "AI library"}:
        return None
    if re.fullmatch(r"[0-9A-F]{8}", server_unique_id) is None:
        return None
    if re.fullmatch(r"[0-9A-F]{32}", catalog_md5) is None:
        return None
    return CatalogRecord(
        content_id=int(fields[0]),
        content_type=content_type,
        state=fields[2],
        name=fields[3],
        server_unique_id=server_unique_id,
        catalog_md5=catalog_md5.lower(),
    )


class ConsoleSession:
    """Line-synchronized stdin/stdout control for the dedicated console."""

    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.lines: list[str] = []
        self.condition = threading.Condition()
        self.reader_error: BaseException | None = None
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        try:
            assert self.process.stdout is not None
            for raw_line in self.process.stdout:
                with self.condition:
                    self.lines.append(raw_line.rstrip("\r\n"))
                    self.condition.notify_all()
        except BaseException as exc:  # pragma: no cover - defensive thread boundary
            with self.condition:
                self.reader_error = exc
                self.condition.notify_all()

    def mark(self) -> int:
        with self.condition:
            return len(self.lines)

    def snapshot(self, start: int = 0) -> list[str]:
        with self.condition:
            return list(self.lines[start:])

    def send(self, command: str) -> int:
        require("\n" not in command and "\r" not in command, "console command contains a newline")
        require(self.process.poll() is None, f"OpenTTD exited before command: {command}")
        assert self.process.stdin is not None
        start = self.mark()
        try:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise AIPackageError(f"cannot send console command {command!r}: {exc}") from exc
        return start

    def wait_for(
        self,
        predicate: Callable[[str], bool],
        *,
        start: int,
        timeout: float,
        label: str,
    ) -> tuple[int, str]:
        deadline = time.monotonic() + timeout
        cursor = start
        with self.condition:
            while True:
                for index in range(cursor, len(self.lines)):
                    if predicate(self.lines[index]):
                        return index, self.lines[index]
                cursor = len(self.lines)
                if self.reader_error is not None:
                    raise AIPackageError(f"console reader failed while waiting for {label}: {self.reader_error}")
                if self.process.poll() is not None:
                    tail = "\n".join(self.lines[-20:])
                    raise AIPackageError(
                        f"OpenTTD exited with {self.process.returncode} while waiting for {label}; tail:\n{tail}"
                    )
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    tail = "\n".join(self.lines[-20:])
                    raise AIPackageError(f"timed out waiting for {label}; tail:\n{tail}")
                self.condition.wait(timeout=remaining)

    def wait_quiet(self, *, start: int, quiet: float, timeout: float) -> list[str]:
        deadline = time.monotonic() + timeout
        with self.condition:
            last_count = len(self.lines)
            last_change = time.monotonic()
            while True:
                now = time.monotonic()
                if len(self.lines) != last_count:
                    last_count = len(self.lines)
                    last_change = now
                if now - last_change >= quiet:
                    return list(self.lines[start:])
                remaining = min(deadline - now, quiet - (now - last_change))
                if remaining <= 0:
                    return list(self.lines[start:])
                self.condition.wait(timeout=remaining)

    def transcript(self) -> str:
        lines = self.snapshot()
        return "\n".join(lines) + ("\n" if lines else "")


def query_catalog(
    session: ConsoleSession,
    command: str,
    *,
    timeout: float,
    accept: Callable[[list[CatalogRecord]], bool],
    label: str,
) -> list[CatalogRecord]:
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        require(remaining > 0, f"timed out waiting for {label}")
        start = session.send(command)
        try:
            header_index, _ = session.wait_for(
                lambda line: line.strip() == "id, type, state, name",
                start=start,
                timeout=min(remaining, 5.0),
                label=f"{label} header",
            )
        except AIPackageError:
            if time.monotonic() >= deadline:
                raise
            continue
        lines = session.wait_quiet(start=header_index + 1, quiet=0.20, timeout=min(1.0, remaining))
        observed = [record for line in lines if (record := catalog_record(line)) is not None]
        by_id: dict[int, CatalogRecord] = {}
        for record in observed:
            previous = by_id.get(record.content_id)
            require(previous is None or previous == record, f"conflicting repeated catalog record for {record.content_id}")
            by_id[record.content_id] = record
        records = list(by_id.values())
        if accept(records):
            return records
        with session.condition:
            session.condition.wait(timeout=min(0.25, max(0.0, deadline - time.monotonic())))


def archive_member_path(raw: str) -> pathlib.PurePosixPath:
    require("\\" not in raw, f"archive member uses a backslash path: {raw!r}")
    path = pathlib.PurePosixPath(raw)
    require(not path.is_absolute(), f"archive member is absolute: {raw!r}")
    require(raw not in {"", "."}, f"archive member path is empty: {raw!r}")
    require(all(part not in {"", ".", ".."} for part in path.parts), f"unsafe archive member path: {raw!r}")
    return path


def parse_squirrel_return(source: str, function: str) -> str | int | None:
    match = re.search(
        rf"function\s+{re.escape(function)}\s*\(\s*\)\s*\{{\s*return\s+(.+?)\s*;\s*\}}",
        source,
        flags=re.DOTALL,
    )
    if match is None:
        return None
    value = match.group(1).strip()
    if re.fullmatch(r"[0-9]+", value):
        return int(value)
    string = re.fullmatch(r'"((?:[^"\\]|\\.)*)"', value)
    if string is None:
        return None
    try:
        return json.loads('"' + string.group(1) + '"')
    except json.JSONDecodeError:
        return None


def declared_info(files: dict[str, bytes]) -> dict[str, Any] | None:
    info_paths = sorted(path for path in files if pathlib.PurePosixPath(path).name.casefold() == "info.nut")
    if not info_paths:
        return None
    require(len(info_paths) == 1, f"package has multiple info.nut files: {info_paths}")
    try:
        source = files[info_paths[0]].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AIPackageError(f"info.nut is not UTF-8: {info_paths[0]}") from exc
    mapping = {
        "name": "GetName",
        "version": "GetVersion",
        "author": "GetAuthor",
        "api_version": "GetAPIVersion",
        "date": "GetDate",
        "description": "GetDescription",
        "instance": "CreateInstance",
        "short_name": "GetShortName",
        "url": "GetURL",
    }
    result = {
        key: value
        for key, function in mapping.items()
        if (value := parse_squirrel_return(source, function)) is not None
    }
    if not {"name", "version"}.issubset(result):
        return None
    require(isinstance(result["name"], str), "declared AI/library name is not a string")
    require(isinstance(result["version"], int), "declared AI/library version is not an integer")
    return result


def audit_archive(artifact_root: pathlib.Path, archive_path: pathlib.Path, record: CatalogRecord) -> dict[str, Any]:
    relative = archive_path.relative_to(artifact_root).as_posix()
    archive_size = archive_path.stat().st_size
    require(0 < archive_size <= MAX_ARCHIVE_BYTES, f"archive size is outside policy: {relative} ({archive_size})")
    filename = archive_path.name
    prefix = record.local_unique_id
    pattern = re.compile(rf"^{re.escape(prefix)}-(?P<label>.+)-(?P<version>v?[1-9][0-9]*)\.tar$")
    match = pattern.fullmatch(filename)
    require(match is not None, f"archive filename does not match catalog identity {prefix}: {filename}")
    package_version = canonical_version(match.group("version"))

    file_bytes: dict[str, bytes] = {}
    expanded = 0
    seen: set[str] = set()
    try:
        with tarfile.open(archive_path, mode="r:*") as archive:
            members = archive.getmembers()
            require(len(members) <= MAX_MEMBERS, f"archive has too many members: {relative}")
            for member in members:
                safe_path = archive_member_path(member.name).as_posix()
                require(safe_path not in seen, f"duplicate archive member: {safe_path}")
                seen.add(safe_path)
                require(member.isfile() or member.isdir(), f"archive contains a link or special member: {safe_path}")
                if member.isdir():
                    continue
                require(0 <= member.size <= MAX_MEMBER_BYTES, f"archive member is too large: {safe_path}")
                expanded += member.size
                require(expanded <= MAX_EXPANDED_BYTES, f"archive expansion exceeds policy: {relative}")
                handle = archive.extractfile(member)
                require(handle is not None, f"cannot read archive member: {safe_path}")
                value = handle.read(MAX_MEMBER_BYTES + 1)
                require(len(value) == member.size, f"archive member size mismatch: {safe_path}")
                file_bytes[safe_path] = value
    except (OSError, tarfile.TarError) as exc:
        raise AIPackageError(f"cannot audit archive {relative}: {exc}") from exc
    require(file_bytes, f"archive contains no regular files: {relative}")
    files = [
        {"path": path, "size": len(value), "sha256": sha256_bytes(value)}
        for path, value in sorted(file_bytes.items())
    ]
    licenses = [
        item
        for item in files
        if pathlib.PurePosixPath(item["path"]).name.casefold().startswith(("license", "copying"))
    ]
    require(licenses, f"archive contains no license/copying file: {relative}")
    package: dict[str, Any] = {
        "content_id": record.content_id,
        "content_type": record.content_type,
        "name": record.name,
        "version": package_version,
        "local_unique_id": record.local_unique_id,
        "server_unique_id": record.server_unique_id,
        "catalog_md5": record.catalog_md5,
        "archive_path": relative,
        "archive_size": archive_size,
        "archive_sha256": sha256_file(archive_path),
        "files": files,
        "licenses": licenses,
    }
    info = declared_info(file_bytes)
    if info is not None:
        package["declared_info"] = info
    return package


def find_archives(artifact_root: pathlib.Path) -> list[pathlib.Path]:
    download_root = artifact_root / "content_download"
    return sorted(
        path
        for path in download_root.rglob("*.tar")
        if path.is_file() and not path.is_symlink()
    ) if download_root.is_dir() else []


def audit_closure(
    artifact_root: pathlib.Path,
    records: Iterable[CatalogRecord],
    *,
    primary_unique_id: str,
    primary_version: int,
) -> list[dict[str, Any]]:
    records = list(records)
    require(records, "content selection has no packages")
    ids = [record.content_id for record in records]
    unique_ids = [record.local_unique_id for record in records]
    require(len(ids) == len(set(ids)), "content selection has duplicate numeric IDs")
    require(len(unique_ids) == len(set(unique_ids)), "content selection has duplicate unique IDs")
    archives = find_archives(artifact_root)
    require(len(archives) == len(records), f"download closure mismatch: selected={len(records)} archives={len(archives)}")
    archives_by_prefix: dict[str, pathlib.Path] = {}
    for path in archives:
        prefix = path.name.split("-", 1)[0]
        require(re.fullmatch(r"[0-9a-f]{8}", prefix) is not None, f"invalid archive unique-ID prefix: {path.name}")
        require(prefix not in archives_by_prefix, f"duplicate archive unique-ID prefix: {prefix}")
        archives_by_prefix[prefix] = path
    require(set(archives_by_prefix) == set(unique_ids), "download archives do not match selected catalog unique IDs")
    packages = [audit_archive(artifact_root, archives_by_prefix[record.local_unique_id], record) for record in records]
    packages.sort(key=lambda item: item["content_id"])
    primary = [item for item in packages if item["local_unique_id"] == primary_unique_id]
    require(len(primary) == 1, "download closure does not contain exactly one requested AI")
    require(primary[0]["content_type"] == "AI", "requested package is not an AI")
    require(primary[0]["version"] == primary_version, "downloaded AI version differs from research baseline")
    return packages


def write_transcript(artifact_root: pathlib.Path, session: ConsoleSession | None) -> None:
    if session is None or not artifact_root.is_dir():
        return
    try:
        (artifact_root / TRANSCRIPT_NAME).write_text(session.transcript(), encoding="utf-8")
    except OSError:
        pass


def terminate_process(session: ConsoleSession | None) -> None:
    if session is None or session.process.poll() is not None:
        return
    try:
        session.send("quit")
        session.process.wait(timeout=5)
    except (AIPackageError, subprocess.TimeoutExpired):
        session.process.terminate()
        try:
            session.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            session.process.kill()
            session.process.wait(timeout=5)


def close_process_streams(session: ConsoleSession | None) -> None:
    if session is None:
        return
    session.reader.join(timeout=1)
    for stream in (session.process.stdin, session.process.stdout):
        if stream is not None and not stream.closed:
            stream.close()


def isolated_environment(artifact_root: pathlib.Path) -> dict[str, str]:
    environment = dict(os.environ)
    for variable, relative in {
        "HOME": "home",
        "XDG_CONFIG_HOME": "xdg/config",
        "XDG_CACHE_HOME": "xdg/cache",
        "XDG_DATA_HOME": "xdg/data",
    }.items():
        path = artifact_root / relative
        path.mkdir(parents=True, exist_ok=False)
        environment[variable] = str(path)
    return environment


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def acquire(
    root: pathlib.Path,
    openttd: pathlib.Path,
    artifact_root: pathlib.Path,
    opponent_name: str,
    *,
    startup_timeout: float = 30.0,
    catalog_timeout: float = 90.0,
    download_timeout: float = 300.0,
) -> pathlib.Path:
    root = root.resolve()
    openttd = openttd.resolve()
    require(openttd.is_file() and not openttd.is_symlink() and os.access(openttd, os.X_OK), "OpenTTD must be an executable regular file")
    require(artifact_root.is_absolute(), "artifact root must be absolute")
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "artifact root must be a new path")
    require(all(timeout > 0 for timeout in (startup_timeout, catalog_timeout, download_timeout)), "timeouts must be positive")

    baseline = load_json(root / "config/v2/research-baseline.json")
    matches = [item for item in baseline["opponents"] if item["name"] == opponent_name]
    require(len(matches) == 1, f"opponent is not uniquely present in the V2 research baseline: {opponent_name!r}")
    opponent = matches[0]
    expected_unique_id = opponent["content_id"]
    expected_version = canonical_version(opponent["version"])
    expected_server_id = bytes.fromhex(expected_unique_id)[::-1].hex().upper()
    source_profile = load_json(root / "config/v1/openttd-source-profile.json")
    source = source_profile["upstream"]
    schema_path = root / SCHEMA_RELATIVE

    artifact_root.mkdir(mode=0o700)
    config_path = artifact_root / "openttd.cfg"
    config_path.write_text(
        "[game_creation]\nmap_x = 6\nmap_y = 6\n\n"
        "[network]\nserver_advertise = false\nserver_name = V2 AI package acquisition\n",
        encoding="utf-8",
    )
    environment = isolated_environment(artifact_root)
    command = [
        str(openttd),
        "-D",
        f"127.0.0.1:{reserve_port()}",
        "-v",
        "dedicated",
        "-s",
        "null",
        "-m",
        "null",
        "-x",
        "-X",
        "-c",
        str(config_path),
    ]
    session: ConsoleSession | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=openttd.parent,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        session = ConsoleSession(process)
        _, ready_line = session.wait_for(
            lambda line: "Map generated, starting game" in line or line == "FAKE CONTENT READY",
            start=0,
            timeout=startup_timeout,
            label="dedicated-server readiness",
        )
        version_match = re.search(r"(?:version |Revision [0-9]+ - )([^\s]+)", "\n".join(session.snapshot()))
        require(version_match is not None, f"cannot parse OpenTTD reported version near {ready_line!r}")
        reported_version = version_match.group(1)

        update_start = session.send("content update ai")
        _, connection_line = session.wait_for(
            lambda line: line in {"Content server connection established.", "Content server connection failed."},
            start=update_start,
            timeout=catalog_timeout,
            label="content-server connection",
        )
        if not connection_line.endswith("established."):
            raise AIPackageError("content-server connection failed", "content-server-failed")
        quoted_name = json.dumps(opponent_name, ensure_ascii=True)
        try:
            primary_rows = query_catalog(
                session,
                f"content state {quoted_name}",
                timeout=catalog_timeout,
                accept=lambda rows: sum(row.name == opponent_name for row in rows) == 1,
                label=f"catalog identity for {opponent_name}",
            )
        except AIPackageError as exc:
            raise AIPackageError(str(exc), "catalog-unavailable") from exc
        primary_matches = [row for row in primary_rows if row.name == opponent_name]
        require(len(primary_matches) == 1, f"catalog query is ambiguous for {opponent_name}")
        primary = primary_matches[0]
        require(primary.content_type == "AI", f"catalog entry is not AI content: {primary.content_type}")
        if primary.server_unique_id != expected_server_id:
            raise AIPackageError("catalog unique ID differs from research baseline", "catalog-identity-drift")
        require(primary.state == "Not selected", f"isolated catalog entry has unexpected initial state: {primary.state}")

        session.send(f"content select {primary.content_id}")
        try:
            selected = query_catalog(
                session,
                "content select",
                timeout=catalog_timeout,
                accept=lambda rows: any(row.content_id == primary.content_id for row in rows),
                label="selected AI dependency closure",
            )
        except AIPackageError as exc:
            raise AIPackageError(
                f"catalog listed {opponent_name} but the isolated client could not select it: {exc}",
                "catalog-listed-unselectable",
            ) from exc
        require(all(row.state in {"Selected", "Dep Selected"} for row in selected), "selected closure has an unexpected state")
        selected_ids = {row.content_id for row in selected}
        require(primary.content_id in selected_ids, "selected closure omits requested AI")

        download_start = session.send("content download")
        completed: set[int] = set()
        cursor = download_start
        deadline = time.monotonic() + download_timeout
        while completed != selected_ids:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AIPackageError(
                    f"timed out downloading content IDs {sorted(selected_ids - completed)}",
                    "download-failed",
                )
            index, line = session.wait_for(
                lambda candidate: candidate.startswith("Completed download of ")
                or "download failed" in candidate.casefold()
                or "connection failed" in candidate.casefold(),
                start=cursor,
                timeout=remaining,
                label="content download completion",
            )
            cursor = index + 1
            if "failed" in line.casefold():
                raise AIPackageError(f"content download failure: {line}", "download-failed")
            match = re.fullmatch(r"Completed download of ([0-9]+)\.", line)
            require(match is not None, f"malformed completion line: {line}")
            content_id = int(match.group(1))
            require(content_id in selected_ids, f"download completed an unselected content ID: {content_id}")
            require(content_id not in completed, f"duplicate download completion for content ID: {content_id}")
            completed.add(content_id)

        terminate_process(session)
        try:
            packages = audit_closure(
                artifact_root,
                selected,
                primary_unique_id=expected_unique_id,
                primary_version=expected_version,
            )
        except AIPackageError as exc:
            raise AIPackageError(str(exc), "archive-audit-failed") from exc
        manifest = {
            "$schema": "../../docs/project/schema/v2-ai-package-lock.schema.json",
            "schema_version": "openttd-rl-v2-ai-package-lock-1",
            "schema_sha256": sha256_file(schema_path),
            "engine_source": {key: source[key] for key in ("release", "commit", "tree")},
            "executable": {
                "sha256": sha256_file(openttd),
                "size": openttd.stat().st_size,
                "reported_version": reported_version,
            },
            "request": {
                "name": opponent_name,
                "content_unique_id": expected_unique_id,
                "version": expected_version,
                "catalog_url": opponent["package_url"],
            },
            "catalog_primary": primary.manifest_dict(),
            "packages": packages,
        }
        lock_path = artifact_root / LOCK_NAME
        lock_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        validate_lock(root, lock_path, openttd=openttd)
        return lock_path
    except (OSError, subprocess.SubprocessError) as exc:
        raise AIPackageError(f"cannot execute OpenTTD content acquisition: {exc}", "execution-failed") from exc
    finally:
        terminate_process(session)
        write_transcript(artifact_root, session)
        close_process_streams(session)


def validate_lock(root: pathlib.Path, lock_path: pathlib.Path, *, openttd: pathlib.Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    lock_path = lock_path.resolve()
    artifact_root = lock_path.parent
    manifest = load_json(lock_path)
    schema_path = root / SCHEMA_RELATIVE
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(manifest)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise AIPackageError(f"lock schema validation failed at {location}: {exc.message}") from exc
    require(manifest["schema_sha256"] == sha256_file(schema_path), "AI lock schema SHA-256 mismatch")
    source = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    require(manifest["engine_source"] == {key: source[key] for key in ("release", "commit", "tree")}, "AI lock engine source drifted from V1 pin")
    if openttd is not None:
        openttd = openttd.resolve()
        require(manifest["executable"]["sha256"] == sha256_file(openttd), "AI lock executable SHA-256 mismatch")
        require(manifest["executable"]["size"] == openttd.stat().st_size, "AI lock executable size mismatch")

    baseline = load_json(root / "config/v2/research-baseline.json")
    opponent_matches = [item for item in baseline["opponents"] if item["name"] == manifest["request"]["name"]]
    require(len(opponent_matches) == 1, "AI lock request is absent or ambiguous in research baseline")
    opponent = opponent_matches[0]
    require(manifest["request"]["content_unique_id"] == opponent["content_id"], "AI lock content ID drifted")
    require(manifest["request"]["version"] == canonical_version(opponent["version"]), "AI lock version drifted")
    require(manifest["request"]["catalog_url"] == opponent["package_url"], "AI lock catalog URL drifted")
    primary_catalog = CatalogRecord(**manifest["catalog_primary"])
    require(primary_catalog.name == manifest["request"]["name"], "AI lock primary catalog name mismatch")
    require(primary_catalog.local_unique_id == manifest["request"]["content_unique_id"], "AI lock primary catalog unique ID mismatch")

    packages = manifest["packages"]
    require(packages == sorted(packages, key=lambda item: item["content_id"]), "AI lock package records are not sorted")
    content_ids = [item["content_id"] for item in packages]
    local_ids = [item["local_unique_id"] for item in packages]
    require(len(content_ids) == len(set(content_ids)), "AI lock has duplicate content IDs")
    require(len(local_ids) == len(set(local_ids)), "AI lock has duplicate unique IDs")
    actual_archives = {path.relative_to(artifact_root).as_posix() for path in find_archives(artifact_root)}
    locked_archives = {item["archive_path"] for item in packages}
    require(actual_archives == locked_archives, "AI lock archive set differs from artifact directory")
    rebuilt: list[dict[str, Any]] = []
    for package in packages:
        record = CatalogRecord(
            content_id=package["content_id"],
            content_type=package["content_type"],
            state="locked",
            name=package["name"],
            server_unique_id=package["server_unique_id"],
            catalog_md5=package["catalog_md5"],
        )
        rebuilt.append(audit_archive(artifact_root, artifact_root / package["archive_path"], record))
    require(rebuilt == packages, "AI lock package metadata or bytes differ from audited archives")
    primary_packages = [item for item in packages if item["local_unique_id"] == manifest["request"]["content_unique_id"]]
    require(len(primary_packages) == 1, "AI lock omits or duplicates requested package")
    require(primary_packages[0]["version"] == manifest["request"]["version"], "AI lock requested package version mismatch")
    return manifest


def write_rejection(
    root: pathlib.Path,
    openttd: pathlib.Path,
    artifact_root: pathlib.Path,
    opponent_name: str,
    error: AIPackageError,
) -> pathlib.Path | None:
    root = root.resolve()
    openttd = openttd.resolve()
    if not artifact_root.is_dir() or not openttd.is_file():
        return None
    transcript = artifact_root / TRANSCRIPT_NAME
    if not transcript.is_file():
        transcript.write_text("", encoding="utf-8")
    baseline = load_json(root / "config/v2/research-baseline.json")
    opponents = [item for item in baseline["opponents"] if item["name"] == opponent_name]
    if len(opponents) != 1:
        return None
    opponent = opponents[0]
    source = load_json(root / "config/v1/openttd-source-profile.json")["upstream"]
    schema_path = root / REJECTION_SCHEMA_RELATIVE
    rejection = {
        "$schema": "../../docs/project/schema/v2-ai-package-rejection.schema.json",
        "schema_version": "openttd-rl-v2-ai-package-rejection-1",
        "schema_sha256": sha256_file(schema_path),
        "engine_source": {key: source[key] for key in ("release", "commit", "tree")},
        "executable": {"sha256": sha256_file(openttd), "size": openttd.stat().st_size},
        "request": {
            "name": opponent_name,
            "content_unique_id": opponent["content_id"],
            "version": canonical_version(opponent["version"]),
            "catalog_url": opponent["package_url"],
        },
        "reason_code": error.reason_code,
        "detail": str(error),
        "console_transcript": {
            "path": TRANSCRIPT_NAME,
            "size": transcript.stat().st_size,
            "sha256": sha256_file(transcript),
        },
    }
    schema = load_json(schema_path)
    try:
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(rejection)
    except jsonschema.ValidationError as exc:  # pragma: no cover - schema is covered by the writer test
        raise AIPackageError(f"generated rejection fails schema: {exc.message}") from exc
    rejection_path = artifact_root / REJECTION_NAME
    rejection_path.write_text(json.dumps(rejection, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rejection_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    subparsers = parser.add_subparsers(dest="command", required=True)
    acquire_parser = subparsers.add_parser("acquire", help="download and lock one baseline opponent")
    acquire_parser.add_argument("--openttd", type=pathlib.Path, required=True)
    acquire_parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    acquire_parser.add_argument("--opponent-name", required=True)
    acquire_parser.add_argument("--startup-timeout", type=float, default=30.0)
    acquire_parser.add_argument("--catalog-timeout", type=float, default=90.0)
    acquire_parser.add_argument("--download-timeout", type=float, default=300.0)
    validate_parser = subparsers.add_parser("validate", help="re-audit an existing lock and package closure")
    validate_parser.add_argument("--lock", type=pathlib.Path, required=True)
    validate_parser.add_argument("--openttd", type=pathlib.Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.command == "acquire":
            lock = acquire(
                args.root,
                args.openttd,
                args.artifact_root,
                args.opponent_name,
                startup_timeout=args.startup_timeout,
                catalog_timeout=args.catalog_timeout,
                download_timeout=args.download_timeout,
            )
            manifest = load_json(lock)
            print(
                f"V2_AI_ACQUIRE=PASS opponent={manifest['request']['name']} "
                f"packages={len(manifest['packages'])} lock={lock}"
            )
        else:
            manifest = validate_lock(args.root, args.lock, openttd=args.openttd)
            print(
                f"V2_AI_LOCK=PASS opponent={manifest['request']['name']} "
                f"packages={len(manifest['packages'])}"
            )
        return 0
    except (AIPackageError, OSError) as exc:
        if args.command == "acquire" and isinstance(exc, AIPackageError):
            try:
                write_rejection(args.root, args.openttd, args.artifact_root, args.opponent_name, exc)
            except (AIPackageError, OSError):
                pass
        print(f"V2_AI_PACKAGE=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
