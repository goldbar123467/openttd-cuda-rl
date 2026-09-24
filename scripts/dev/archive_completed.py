#!/usr/bin/env python3
"""Plan and verify lossless compression of completed development-run artifacts.

Run in WSL with all experiment producers stopped. This maintenance command does
not change the live collector, checkpoints, archived source, or release data.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import time

CHUNK = 4 * 1024 * 1024
SUCCESS = {"completed", "passed", "complete"}
PROTECTED = {"source", "sources", "checkpoints", "models", "packages", ".git"}


def artifact_kind(name):
    if name == "requests.jsonl":
        return "request_logs"
    if re.fullmatch(r"tensors-\d{6}-(observation|candidates)(-guided-one-bus)?\.bin", name):
        return "tensor_snapshots"
    if re.fullmatch(r"tensors-\d{6}-(observation|candidates)\.json", name):
        return "tensor_metadata"
    return None


def write_new(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def sha_stream(stream):
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(CHUNK):
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def fingerprint(path):
    value = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        raise ValueError(f"Expected a regular file with one hard link: {path}")
    return {"size": value.st_size, "mtime_ns": value.st_mtime_ns,
            "inode": value.st_ino, "device": value.st_dev}


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sync_filesystem(path):
    """Durably publish a batch on Linux before removing any original in it."""
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        library = ctypes.CDLL(None, use_errno=True)
        if library.syncfs(descriptor) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
    finally:
        os.close(descriptor)


def eligible(root, path, excludes):
    relative = path.relative_to(root)
    if not relative.parts or relative.parts[0] in excludes:
        raise ValueError("Explicitly protected run")
    if any(part in PROTECTED or "heldout" in part.lower() or "held-out" in part.lower()
           for part in relative.parts):
        raise ValueError("Protected evidence/source/checkpoint path")
    if artifact_kind(path.name) is None:
        raise ValueError("Not an approved artifact filename")
    if path.resolve() != path or not path.resolve().is_relative_to(root):
        raise ValueError("Symlink or escaped run root")


def completion(root, path):
    # Nearest run status wins: a failed child must not inherit its parent's PASS.
    found = None
    for directory in (path.parent, *path.parent.parents):
        if directory == root:
            break
        for name in ("run.json", "comparison.json", "verification.json"):
            marker = directory / name
            if not marker.is_file() or marker.is_symlink():
                continue
            data = json.loads(marker.read_text())
            status = str(data.get("status", "")).lower()
            if not status:
                continue
            if status == "running":
                raise ValueError(f"Running ancestor: {marker}")
            if found is None:
                if status not in SUCCESS:
                    raise ValueError(f"No completed status: {marker}: {status}")
                found = {"path": str(marker.relative_to(root)), "status": status,
                         "sha256": hashlib.sha256(marker.read_bytes()).hexdigest()}
            break
    if found is None:
        raise ValueError("No completed run marker")
    return found


def idle(root):
    if os.name != "posix" or not Path("/proc").is_dir():
        raise RuntimeError("Run maintenance in Linux/WSL")
    for process in Path("/proc").iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            command = (process / "cmdline").read_bytes().split(b"\0")
            names = [Path(os.fsdecode(arg)).name for arg in command if arg]
            if names and (names[0] == "openttd" or names[0].startswith("rl_dev_v2_") or
                          any(name in ("train_v2.py", "infer_v2.py", "evaluate_guide_v2.py") for name in names)):
                raise RuntimeError(f"Experiment producer still active: PID {process.name}")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue


def plan(root, excludes, kinds=("request_logs", "tensor_snapshots")):
    if root.name != "runs" or root.is_symlink():
        raise ValueError("Specify the experiment runs directory")
    idle(root)
    files, skipped, totals, completions = [], [], {}, {}
    for parent, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(d for d in directories if d not in PROTECTED and
            d not in excludes and "heldout" not in d.lower() and "held-out" not in d.lower()
            and not Path(parent, d).is_symlink())
        for name in sorted(names):
            kind = artifact_kind(name)
            if kind not in kinds:
                continue
            path = Path(parent, name)
            try:
                eligible(root, path, excludes)
                if path.parent not in completions:
                    try:
                        completions[path.parent] = completion(root, path)
                    except ValueError as exc:
                        completions[path.parent] = str(exc)
                marker = completions[path.parent]
                if isinstance(marker, str):
                    raise ValueError(marker)
                row = {"path": str(path.relative_to(root)), **fingerprint(path), "completion": marker}
                files.append(row)
                total = totals.setdefault(kind, {"files": 0, "bytes": 0})
                total["files"] += 1
                total["bytes"] += row["size"]
            except ValueError as exc:
                skipped.append({"path": str(path.relative_to(root)), "reason": str(exc)})
    files.sort(key=lambda row: (not row["path"].endswith("requests.jsonl"), -row["size"], row["path"]))
    return {"schema": "development-lossless-archive-1", "root": str(root), "exclude_runs": sorted(excludes),
            "gzip_level": 1, "maximum_workers": 2, "kinds": list(kinds), "files": files, "skipped": skipped, "totals": totals,
            "scope": "Completed development logs/snapshots only; no model/checkpoint/source/held-out removal"}


def archive_one(root, row, excludes, record, *, defer_removal=False):
    path = root / row["path"]
    eligible(root, path, excludes)
    expected = {key: row[key] for key in ("size", "mtime_ns", "inode", "device")}
    if fingerprint(path) != expected or completion(root, path) != row["completion"]:
        raise ValueError(f"Source or completion marker changed since plan: {path}")
    archive = path.with_name(path.name + ".gz")
    temporary = path.with_name(path.name + ".gz.partial")
    # Never overwrite even a corrupt or interrupted archive.
    if archive.exists() or archive.is_symlink() or temporary.exists() or temporary.is_symlink():
        raise FileExistsError(f"Archive/partial already exists for {path}")
    original = hashlib.sha256()
    with path.open("rb") as source, temporary.open("xb") as target:
        with gzip.GzipFile(filename="", mode="wb", fileobj=target, compresslevel=1, mtime=0) as compressed:
            while chunk := source.read(CHUNK):
                original.update(chunk)
                compressed.write(chunk)
        target.flush()
        if not defer_removal:
            os.fsync(target.fileno())
    with gzip.open(temporary, "rb") as check:
        restored_hash, restored_size = sha_stream(check)
    with path.open("rb") as check:
        current_hash, current_size = sha_stream(check)
    if (restored_hash != original.hexdigest() or current_hash != restored_hash or
            current_size != row["size"] or restored_size != row["size"] or fingerprint(path) != expected):
        raise RuntimeError(f"Lossless verification/source stability failed: {path}")
    with temporary.open("rb") as check:
        archive_hash, archive_size = sha_stream(check)
    if archive_size >= row["size"]:
        record({"state": "no_saving_original_retained", "path": row["path"], "bytes": row["size"]})
        temporary.unlink()
        return
    os.link(temporary, archive)  # Exclusive publication; cannot replace another file.
    temporary.unlink()
    if not defer_removal:
        sync_directory(path.parent)
    detail = {"path": row["path"], "archive": str(archive.relative_to(root)),
              "original_sha256": current_hash, "archive_sha256": archive_hash,
              "original_bytes": current_size, "archive_bytes": archive_size,
              "saved_bytes": current_size - archive_size}
    if defer_removal:
        return detail
    record({"state": "verified", **detail})  # Durable recovery map before original removal.
    if fingerprint(path) != expected:
        raise RuntimeError(f"Source changed after archive publication: {path}")
    path.unlink()
    sync_directory(path.parent)
    record({"state": "archived", **detail})


def apply(plan_path, output, batch_size=1):
    if type(batch_size) is not int or not 1 <= batch_size <= 128:
        raise ValueError("Archive batch size must be between 1 and 128")
    data = json.loads(plan_path.read_text())
    root = Path(data["root"]).resolve(strict=True)
    if data["schema"] != "development-lossless-archive-1" or root.name != "runs":
        raise ValueError("Unexpected archive plan/root")
    if batch_size > 1 and any(row["device"] != root.stat().st_dev for row in data["files"]):
        raise ValueError("Batched archives must share the flushed run-root filesystem")
    idle(root)
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "plan.json", data)
    lock = threading.Lock()
    started = time.monotonic()
    last_progress = started
    counts = {"files": 0, "original_bytes": 0, "archive_bytes": 0, "saved_bytes": 0}
    with (output / "journal.jsonl").open("x") as journal:
        sync_directory(output)
        def record(row, *, durable=True):
            nonlocal last_progress
            with lock:
                journal.write(json.dumps(row) + "\n")
                journal.flush()
                if durable:
                    os.fsync(journal.fileno())
                if row["state"] == "archived":
                    counts["files"] += 1
                    for key in ("original_bytes", "archive_bytes", "saved_bytes"):
                        counts[key] += row[key]
                    if time.monotonic() - last_progress >= 30:
                        print(json.dumps({**counts, "elapsed_seconds": time.monotonic() - started}), flush=True)
                        last_progress = time.monotonic()
        try:
            # Process logs first, then tensors. Only two compression workers.
            with ThreadPoolExecutor(max_workers=2) as pool:
                for is_log in (True, False):
                    selected = [row for row in data["files"] if row["path"].endswith("requests.jsonl") == is_log]
                    if batch_size == 1:
                        for _ in pool.map(lambda row: archive_one(root, row, data["exclude_runs"], record), selected):
                            pass
                    else:
                        for offset in range(0, len(selected), batch_size):
                            batch = selected[offset:offset + batch_size]
                            prepared = list(pool.map(lambda row: archive_one(root, row,
                                data["exclude_runs"], record, defer_removal=True), batch))
                            # Every archive and directory entry is durable before the
                            # verification journal; that journal is durable before unlink.
                            sync_filesystem(root)
                            for detail in prepared:
                                if detail is not None:
                                    record({"state": "verified", **detail}, durable=False)
                            os.fsync(journal.fileno())
                            for row, detail in zip(batch, prepared, strict=True):
                                if detail is None:
                                    continue
                                path = root / row["path"]
                                expected = {key: row[key] for key in ("size", "mtime_ns", "inode", "device")}
                                if fingerprint(path) != expected:
                                    raise RuntimeError(f"Source changed before batch removal: {path}")
                                path.unlink()
                                record({"state": "archived", **detail}, durable=False)
                            os.fsync(journal.fileno())
            sync_filesystem(root)
            write_new(output / "summary.json", {"status": "completed", **counts,
                "elapsed_seconds": time.monotonic() - started,
                "batch_size": batch_size,
                "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest()})
        except BaseException as exc:
            write_new(output / "failure.json", {"status": "failed", "error": repr(exc), **counts})
            raise


def restore(root, journal_path, relative):
    with journal_path.open() as stream:
        records = [json.loads(line) for line in stream]
    entry = next(row for row in records if row["path"] == relative and row["state"] == "verified")
    path, archive = root / relative, root / entry["archive"]
    eligible(root, path, [])
    if (archive != path.with_name(path.name + ".gz") or not archive.is_relative_to(root) or
            archive.resolve() != archive or archive.is_symlink()):
        raise ValueError("Unsafe archive path")
    with archive.open("rb") as source:
        if sha_stream(source) != (entry["archive_sha256"], entry["archive_bytes"]):
            raise ValueError("Archive checksum differs")
    with gzip.open(archive, "rb") as source:
        if sha_stream(source) != (entry["original_sha256"], entry["original_bytes"]):
            raise ValueError("Restored checksum differs")
    # Keep the verified archive even after restoration; never overwrite a file.
    with gzip.open(archive, "rb") as source, path.open("xb") as target:
        while chunk := source.read(CHUNK):
            target.write(chunk)
        target.flush()
        os.fsync(target.fileno())
    with path.open("rb") as source:
        if sha_stream(source) != (entry["original_sha256"], entry["original_bytes"]):
            raise RuntimeError("Restored file verification failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    planning = sub.add_parser("plan")
    planning.add_argument("--root", type=Path, required=True)
    planning.add_argument("--exclude", action="append", default=[])
    planning.add_argument("--output", type=Path, required=True)
    planning.add_argument("--kind", action="append", choices=("request_logs", "tensor_snapshots", "tensor_metadata"))
    execution = sub.add_parser("apply")
    execution.add_argument("--plan", type=Path, required=True)
    execution.add_argument("--output", type=Path, required=True)
    execution.add_argument("--batch-size", type=int, default=1)
    restoration = sub.add_parser("restore")
    restoration.add_argument("--root", type=Path, required=True)
    restoration.add_argument("--journal", type=Path, required=True)
    restoration.add_argument("--path", required=True)
    args = parser.parse_args()
    if args.command == "plan":
        result = plan(args.root.resolve(strict=True), args.exclude,
                      args.kind or ("request_logs", "tensor_snapshots"))
        write_new(args.output, result)
        print(json.dumps({"totals": result["totals"], "skipped_files": len(result["skipped"])}))
    elif args.command == "apply":
        apply(args.plan.resolve(strict=True), args.output.resolve(), args.batch_size)
    else:
        restore(args.root.resolve(strict=True), args.journal, args.path)


if __name__ == "__main__":
    main()
