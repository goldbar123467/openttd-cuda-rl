#!/usr/bin/env python3
"""Derive a path-neutral M10 package by removing ONNX metadata only."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import shutil
import sys
from typing import Any

import onnx
from google.protobuf.message import Message


class SanitizationError(RuntimeError):
    """The source package or sanitized result is invalid."""


SOURCE_PACKAGE_ID = "0334e6a9da8d5b87d48ecdcd859dc3a5be6b1f7913511bf3336f8d3cf1feeeb9"
SOURCE_MODEL_SHA256 = "10df689ccc6d1cb7f2e98f05f0474f72577cd9328a4589e3b1c7167bcbf08b5b"
EXPECTED_FILES = {"INSTALL.md", "evaluation.json", "golden.jsonl", "manifest.json", "model.onnx"}
FORBIDDEN_TEXT = (
    b"/home/",
    b"/Users/",
    b"BEGIN PRIVATE KEY",
    b"AWS_SECRET_ACCESS_KEY",
    b"GITHUB_TOKEN=",
    b"OPENAI_API_KEY=",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SanitizationError(message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clear_metadata(message: Message) -> int:
    """Recursively clear protobuf documentation/metadata fields."""
    removed = 0
    for field, value in list(message.ListFields()):
        if field.name in {"doc_string", "metadata_props"}:
            removed += len(value) if field.is_repeated else 1
            message.ClearField(field.name)
            continue
        if field.message_type is None:
            continue
        if field.is_repeated:
            for child in value:
                removed += clear_metadata(child)
        else:
            removed += clear_metadata(value)
    return removed


def semantic_graph_identity(model: onnx.ModelProto) -> str:
    value = copy.deepcopy(model)
    clear_metadata(value)
    return hashlib.sha256(value.SerializeToString(deterministic=True)).hexdigest()


def sanitized_model(source: pathlib.Path, destination: pathlib.Path) -> int:
    model = onnx.load(source, load_external_data=False)
    before = semantic_graph_identity(model)
    removed = clear_metadata(model)
    require(removed > 0, "source ONNX contains no removable metadata")
    onnx.checker.check_model(model, full_check=True)
    require(semantic_graph_identity(model) == before, "ONNX graph semantics changed during sanitization")
    destination.write_bytes(model.SerializeToString(deterministic=True))
    require(not any(token in destination.read_bytes() for token in FORBIDDEN_TEXT), "sanitized ONNX still contains a forbidden path or credential marker")
    return removed


def run(args: argparse.Namespace) -> pathlib.Path:
    source = args.source_package.resolve()
    output = args.output_root.resolve()
    require(source.is_dir() and not source.is_symlink(), "source package must be a nonsymlink directory")
    require(source.name == SOURCE_PACKAGE_ID, "source package identity drifted")
    require(not output.exists(), "output root already exists")
    observed = {item.name for item in source.iterdir() if item.is_file() and not item.is_symlink()}
    require(observed == EXPECTED_FILES and len(list(source.iterdir())) == 5, "source package inventory drifted")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    require(manifest["package_id"] == SOURCE_PACKAGE_ID, "source manifest package identity drifted")
    source_identity = copy.deepcopy(manifest)
    source_identity.pop("package_id")
    require(hashlib.sha256(canonical_bytes(source_identity)).hexdigest() == SOURCE_PACKAGE_ID, "source package content address is invalid")
    require(sha256_file(source / "model.onnx") == SOURCE_MODEL_SHA256, "source model identity drifted")

    stage = output / ".stage"
    stage.mkdir(parents=True)
    try:
        for name in EXPECTED_FILES - {"manifest.json", "model.onnx"}:
            shutil.copyfile(source / name, stage / name)
        first = stage / "model.onnx"
        second = stage / ".model-second.onnx"
        removed = sanitized_model(source / "model.onnx", first)
        require(sanitized_model(source / "model.onnx", second) == removed, "metadata removal count is not repeatable")
        require(first.read_bytes() == second.read_bytes(), "independent sanitized ONNX bytes differ")
        second.unlink()

        manifest["files"]["model.onnx"] = sha256_file(first)
        manifest["provenance"]["export_model_sha256"] = manifest["files"]["model.onnx"]
        manifest["publication_derivation"] = {
            "kind": "onnx-metadata-removal-only",
            "source_package_id": SOURCE_PACKAGE_ID,
            "source_model_sha256": SOURCE_MODEL_SHA256,
            "removed_fields": ["doc_string", "metadata_props"],
            "removed_field_values": removed,
            "graph_semantics": "unchanged",
            "byte_identical_repeats": 2,
        }
        manifest.pop("package_id")
        identity = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
        manifest["package_id"] = identity
        (stage / "manifest.json").write_bytes(canonical_bytes(manifest))
        for path in stage.iterdir():
            require(path.is_file() and not path.is_symlink() and path.stat().st_size > 0, "sanitized package contains an invalid entry")
            require(not any(token in path.read_bytes() for token in FORBIDDEN_TEXT), f"sanitized package contains forbidden text: {path.name}")
        final = output / identity
        stage.rename(final)
        print(
            "M13_MODEL_SANITIZATION=PASS "
            f"package_id={identity} model_sha256={manifest['files']['model.onnx']} "
            f"removed_fields={removed}",
            flush=True,
        )
        return final
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-package", type=pathlib.Path, required=True)
    parser.add_argument("--output-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        run(args)
    except (OSError, ValueError, SanitizationError, onnx.checker.ValidationError) as error:
        print(f"M13_MODEL_SANITIZATION=FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
