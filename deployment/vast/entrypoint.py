#!/usr/bin/env python3
"""Start the pinned study on an existing GPU instance; never rent or publish."""
import fcntl
import hashlib
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

REPOSITORY = "https://github.com/goldbar123467/openttd-cuda-rl.git"


def persistent_mount(root, mountinfo=Path("/proc/self/mountinfo")):
    # ismount() alone misses bind mounts on the same filesystem.
    root = root.resolve()
    mounts = []
    for line in mountinfo.read_text().splitlines():
        fields = line.split()
        if len(fields) < 6:
            continue
        mount = Path(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields[4]))
        if mount != Path("/") and (mount == root or mount in root.parents):
            mounts.append(mount)
    if not mounts:
        raise ValueError("RL_DATA_ROOT needs a persistent volume mount, for example /data/openttd-study")
    return max(mounts, key=lambda p: len(p.parts))


def checked_revision(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value or ""):
        raise ValueError("Set RL_REVISION to the exact committed Git SHA; moving branches are forbidden")
    return value


def checkout(root, revision):
    source = root / "source"
    if not source.exists():
        attempts = root / "checkouts"
        attempts.mkdir(exist_ok=True)
        count = len(list(attempts.glob("attempt-*")))
        if count >= 3:
            raise RuntimeError("Three interrupted checkout attempts retained; inspect their logs")
        candidate = attempts / f"attempt-{count + 1:03d}"
        subprocess.run(["git", "clone", "--no-checkout", REPOSITORY, str(candidate)], check=True)
        subprocess.run(["git", "-C", str(candidate), "fetch", "origin", revision], check=True)
        subprocess.run(["git", "-C", str(candidate), "checkout", "--detach", revision], check=True)
        subprocess.run(["git", "-C", str(candidate), "submodule", "update", "--init", "--recursive"], check=True)
        candidate.rename(source)
    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()
    if git("rev-parse", "HEAD") != revision or git("status", "--porcelain"):
        raise ValueError("Persistent checkout changed; preserve it and use the registered source revision")
    image_script = Path(__file__).read_bytes()
    saved_script = (source / "deployment/vast/entrypoint.py").read_bytes()
    if hashlib.sha256(image_script).digest() != hashlib.sha256(saved_script).digest():
        raise ValueError("Image entrypoint differs from the pinned study; rebuild the image from that revision")
    return source


def main():
    revision = checked_revision(os.environ.get("RL_REVISION"))
    root = Path(os.environ.get("RL_DATA_ROOT", "/data/openttd-study"))
    if not root.is_absolute() or len(root.parts) < 3:
        raise ValueError("RL_DATA_ROOT must be an absolute study subdirectory")
    persistent_mount(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".instance.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("This persistent study already has an active launcher") from exc
        source = checkout(root, revision)
        command = [sys.executable, str(source / "scripts/dev/studies/unattended_v2.py"),
                   "--root", str(root), "--revision", revision]
        child = subprocess.Popen(command, cwd=source, start_new_session=True)
        def stop(signum, frame):
            if child.poll() is None:
                # The supervisor owns its child cleanup and retains its journal.
                child.send_signal(signum)
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        return child.wait()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Study launcher refused execution: {error}", file=sys.stderr, flush=True)
        raise SystemExit(2)
