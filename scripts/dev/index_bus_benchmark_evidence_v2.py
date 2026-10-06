#!/usr/bin/env python3
"""Stream a hash inventory of the owned, finished native experiment artifacts."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(strict=True), args.output.resolve()
    if not root.is_relative_to(Path("/home/imsa/.local/share/openttd-rl/runs")):
        raise ValueError("Inventory root must be an owned experiment under the local runtime")
    count = total = 0
    with output.open("xb") as file, gzip.GzipFile(filename="", mode="wb", fileobj=file, compresslevel=1, mtime=0) as archive:
        for path in root.rglob("*"):
            if path == output:
                continue
            if path.name in ("secrets.cfg", "private.cfg"):
                raise ValueError("Private game configuration must never enter this inventory")
            if path.is_symlink():
                raise ValueError("Inventory must not follow symlinks outside the owned experiment")
            if not path.is_file():
                continue
            before = path.stat()
            sha256 = digest(path)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("Experiment file changed during final inventory")
            archive.write((json.dumps({"relative_file": str(path.relative_to(root)), "sha256": sha256,
                                      "bytes": after.st_size}, separators=(",", ":")) + "\n").encode())
            count += 1
            total += after.st_size
            if count % 10000 == 0:
                print(json.dumps({"files_indexed": count, "bytes": total}), flush=True)
    summary = {"status": "indexed", "root": str(root), "files": count, "bytes": total,
               "completed_at": datetime.now(timezone.utc).isoformat(),
               "inventory": {"path": str(output), "sha256": digest(output)}}
    with output.with_suffix(".summary.json").open("x") as stream:
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    print(json.dumps(summary), flush=True)
