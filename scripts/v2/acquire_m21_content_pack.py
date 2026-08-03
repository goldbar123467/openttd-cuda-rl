#!/usr/bin/env python3
"""Acquire and byte-lock the finite M21 NewGRF compatibility pack."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import pathlib
import re
import subprocess
import tarfile
import time
from dataclasses import dataclass
from typing import Any

from acquire_ai_package import ConsoleSession, isolated_environment, reserve_port, terminate_process


REQUEST = pathlib.Path("config/v2/m21-content-request.json")
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 100_000


class M21ContentError(ValueError):
    """The selected NewGRF closure violated the frozen M21 request."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M21ContentError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
        return self.server_unique_id.lower()

    def projection(self) -> dict[str, Any]:
        return {
            "catalog_md5": self.catalog_md5.lower(),
            "content_id": self.content_id,
            "content_type": self.content_type,
            "name": self.name,
            "server_unique_id": self.server_unique_id,
            "state": self.state,
        }


def catalog_record(line: str) -> CatalogRecord | None:
    try:
        fields = next(csv.reader([line], skipinitialspace=True))
    except (csv.Error, StopIteration):
        return None
    if len(fields) < 6 or not fields[0].isdigit():
        return None
    server_unique_id, catalog_md5 = fields[-2:]
    if re.fullmatch(r"[0-9A-F]{8}", server_unique_id) is None or re.fullmatch(r"[0-9A-F]{32}", catalog_md5) is None:
        return None
    return CatalogRecord(int(fields[0]), fields[1], fields[2], ", ".join(fields[3:-2]), server_unique_id, catalog_md5)


def query(session: ConsoleSession, command: str, expected_name: str, timeout: float) -> CatalogRecord:
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        require(remaining > 0, f"timed out querying content catalog for {expected_name}")
        start = session.send(command)
        try:
            header, _ = session.wait_for(
                lambda line: line.strip() == "id, type, state, name",
                start=start,
                timeout=min(remaining, 5.0),
                label=f"catalog header for {expected_name}",
            )
        except ValueError:
            continue
        lines = session.wait_quiet(start=header + 1, quiet=0.2, timeout=min(1.0, remaining))
        matches = [record for line in lines if (record := catalog_record(line)) is not None and record.name == expected_name]
        if len(matches) == 1:
            return matches[0]


def query_selected(session: ConsoleSession, expected_ids: set[int], timeout: float) -> list[CatalogRecord]:
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        require(remaining > 0, "timed out querying selected NewGRF closure")
        start = session.send("content select")
        try:
            header, _ = session.wait_for(
                lambda line: line.strip() == "id, type, state, name",
                start=start,
                timeout=min(remaining, 5.0),
                label="selected NewGRF closure header",
            )
        except ValueError:
            continue
        lines = session.wait_quiet(start=header + 1, quiet=0.25, timeout=min(1.5, remaining))
        records = [record for line in lines if (record := catalog_record(line)) is not None]
        by_id = {record.content_id: record for record in records}
        if expected_ids.issubset(by_id):
            result = sorted(by_id.values(), key=lambda item: item.content_id)
            require(all(item.state in {"Selected", "Dep Selected"} for item in result), "selected closure state drifted")
            return result


def safe_member(raw: str) -> pathlib.PurePosixPath:
    require("\\" not in raw, f"archive member uses backslash: {raw!r}")
    path = pathlib.PurePosixPath(raw)
    require(not path.is_absolute() and raw not in {"", "."}, f"unsafe archive member: {raw!r}")
    require(all(part not in {"", ".", ".."} for part in path.parts), f"unsafe archive member: {raw!r}")
    return path


def audit_archive(artifact_root: pathlib.Path, path: pathlib.Path, record: CatalogRecord, request: dict[str, Any] | None) -> dict[str, Any]:
    require(0 < path.stat().st_size <= MAX_ARCHIVE_BYTES, f"archive size outside policy: {path}")
    require(path.name.startswith(record.local_unique_id + "-") and path.suffix == ".tar", f"archive name/identity mismatch: {path.name}")
    members: list[dict[str, Any]] = []
    grfs: list[dict[str, Any]] = []
    licenses: list[dict[str, Any]] = []
    expanded = 0
    seen: set[str] = set()
    with tarfile.open(path, mode="r:*") as archive:
        entries = archive.getmembers()
        require(len(entries) <= MAX_MEMBERS, f"too many archive members: {path.name}")
        for entry in entries:
            member = safe_member(entry.name).as_posix()
            require(member not in seen, f"duplicate archive member: {member}")
            seen.add(member)
            require(entry.isfile() or entry.isdir(), f"link or special archive member: {member}")
            if entry.isdir():
                continue
            expanded += entry.size
            require(expanded <= MAX_EXPANDED_BYTES, f"expanded archive exceeds policy: {path.name}")
            handle = archive.extractfile(entry)
            require(handle is not None, f"cannot read archive member: {member}")
            data = handle.read()
            require(len(data) == entry.size, f"archive member size mismatch: {member}")
            item = {"bytes": len(data), "path": member, "sha256": hashlib.sha256(data).hexdigest()}
            members.append(item)
            lower = pathlib.PurePosixPath(member).name.casefold()
            if lower.endswith(".grf"):
                grfs.append({**item, "md5": hashlib.md5(data, usedforsecurity=False).hexdigest()})
            if re.search(r"(?:^|[-_.])(copying|licen[cs]e)(?:[-_.]|$)", lower):
                licenses.append(item)
    require(grfs, f"archive contains no GRF: {path.name}")
    require(licenses, f"archive contains no license file: {path.name}")
    version = request["version"] if request is not None else "dependency"
    if request is not None:
        normalized = re.sub(r"[^a-z0-9]+", "", path.stem.casefold())
        expected = re.sub(r"[^a-z0-9]+", "", str(version).casefold())
        require(expected in normalized, f"archive filename does not contain requested version {version}: {path.name}")
    return {
        "archive": {
            "bytes": path.stat().st_size,
            "path": str(path.relative_to(artifact_root)),
            "sha256": sha256_file(path),
        },
        "capabilities": [] if request is None else request["capabilities"],
        "catalog": record.projection(),
        "grf_files": sorted(grfs, key=lambda item: item["path"]),
        "license": "dependency-declared" if request is None else request["license"],
        "license_files": sorted(licenses, key=lambda item: item["path"]),
        "members": sorted(members, key=lambda item: item["path"]),
        "requested": request is not None,
        "unique_id": record.local_unique_id,
        "version": version,
    }


def acquire(root: pathlib.Path, executable: pathlib.Path, artifact_root: pathlib.Path, timeout: float) -> pathlib.Path:
    root, executable, artifact_root = root.resolve(), executable.resolve(), artifact_root.resolve()
    require(executable.is_file() and os.access(executable, os.X_OK), "OpenTTD executable is unavailable")
    require(not artifact_root.exists() and not artifact_root.is_symlink(), "artifact root must be new")
    request_path = root / REQUEST
    request = load(request_path)
    packages = request["packages"]
    require(len(packages) == 10 and len({item["unique_id"] for item in packages}) == 10, "request must contain ten unique packages")
    artifact_root.mkdir(mode=0o700)
    config = artifact_root / "openttd.cfg"
    config.write_text("[game_creation]\nmap_x = 6\nmap_y = 6\n\n[network]\nserver_advertise = false\nserver_name = M21 content acquisition\n", encoding="utf-8")
    environment = isolated_environment(artifact_root)
    command = [str(executable), "-D", f"127.0.0.1:{reserve_port()}", "-v", "dedicated", "-s", "null", "-m", "null", "-x", "-X", "-c", str(config)]
    session: ConsoleSession | None = None
    try:
        process = subprocess.Popen(command, cwd=executable.parent, env=environment, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                   errors="replace", bufsize=1)
        session = ConsoleSession(process)
        session.wait_for(lambda line: "Map generated, starting game" in line, start=0, timeout=30, label="dedicated readiness")
        update = session.send("content update newgrf")
        _, line = session.wait_for(lambda value: value in {"Content server connection established.", "Content server connection failed."},
                                   start=update, timeout=timeout, label="content server")
        require(line.endswith("established."), "content server connection failed")
        primary: list[CatalogRecord] = []
        for item in packages:
            print(f"M21 content catalog query: {item['name']}", flush=True)
            record = query(session, f"content state {json.dumps(item['name'])}", item["name"], timeout)
            expected_server = item["unique_id"].upper()
            require(record.server_unique_id == expected_server and record.state == "Not selected",
                    f"catalog identity/state drifted: {item['name']} observed={record.projection()}")
            require(record.content_type == "NewGRF", f"catalog type is not NewGRF: {item['name']} ({record.content_type})")
            primary.append(record)
            session.send(f"content select {record.content_id}")
            print(f"M21 content selected: {item['name']} id={record.content_id}", flush=True)
        selected = query_selected(session, {item.content_id for item in primary}, timeout)
        download = session.send("content download")
        completed: set[int] = set()
        cursor = download
        deadline = time.monotonic() + timeout
        selected_ids = {item.content_id for item in selected}
        while completed != selected_ids:
            remaining = deadline - time.monotonic()
            require(remaining > 0, f"timed out downloading IDs {sorted(selected_ids - completed)}")
            index, line = session.wait_for(lambda value: value.startswith("Completed download of ") or "failed" in value.casefold(),
                                           start=cursor, timeout=remaining, label="content download")
            cursor = index + 1
            require("failed" not in line.casefold(), f"content download failed: {line}")
            match = re.fullmatch(r"Completed download of ([0-9]+)\.", line)
            require(match is not None and int(match.group(1)) in selected_ids, f"unexpected completion line: {line}")
            completed.add(int(match.group(1)))
        terminate_process(session)
        transcript = artifact_root / "openttd-content-console.log"
        transcript.write_text(session.transcript(), encoding="utf-8")
        archives = sorted(artifact_root.rglob("content_download/newgrf/*.tar"))
        by_prefix = {path.name[:8]: path for path in archives}
        require(len(by_prefix) == len(archives) == len(selected), "downloaded archive closure count drifted")
        request_by_id = {item["unique_id"]: item for item in packages}
        records_by_id = {item.local_unique_id: item for item in selected}
        require(set(by_prefix) == set(records_by_id), "downloaded archive identities differ from selected closure")
        audited = [audit_archive(artifact_root, by_prefix[identifier], records_by_id[identifier], request_by_id.get(identifier))
                   for identifier in sorted(by_prefix)]
        lock = {
            "acquisition": {"network_calls": "content-server-only", "selected_closure": len(selected), "transcript_sha256": sha256_file(transcript)},
            "executable": {"bytes": executable.stat().st_size, "path": str(executable), "sha256": sha256_file(executable)},
            "packages": audited,
            "request_sha256": sha256_file(request_path),
            "schema_version": "openttd-rl-v2-m21-content-lock-1",
            "status": "LOCKED",
        }
        output = artifact_root / "m21-content-lock.json"
        output.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"V2_M21_CONTENT_ACQUISITION=PASS requested={len(packages)} closure={len(selected)} archives={len(archives)}")
        return output
    finally:
        terminate_process(session)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--executable", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()
    try:
        acquire(args.root, args.executable, args.artifact_root, args.timeout)
        return 0
    except (M21ContentError, OSError, json.JSONDecodeError, tarfile.TarError, subprocess.SubprocessError, ValueError) as exc:
        print(f"V2_M21_CONTENT_ACQUISITION=FAIL {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
