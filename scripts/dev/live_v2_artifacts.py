"""Lossless storage of native tensor observations after their consumers finish."""
import gzip
import hashlib
import shutil


def archive_tensors(worker):
    directory = worker.resolve() / "artifacts"
    for path in sorted(directory.glob("tensors-*.bin")):
        if path.is_symlink() or path.resolve().parent != directory:
            raise ValueError("Tensor archive target escaped the owned worker directory")
        destination = path.with_suffix(".bin.gz")
        with path.open("rb") as source, destination.open("xb") as stream:
            with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as compressed:
                shutil.copyfileobj(source, compressed)
        with gzip.open(destination, "rb") as check:
            if hashlib.sha256(check.read()).digest() != hashlib.sha256(path.read_bytes()).digest():
                raise RuntimeError("Lossless tensor archive verification failed")
        path.unlink()
