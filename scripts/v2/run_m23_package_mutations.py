#!/usr/bin/env python3
"""Execute every frozen M23 deployment package and request rejection mutation."""

from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Any, Callable

import m23_package
import validate_m23_release_contract as contract_validator


ManifestMutation = Callable[[dict[str, Any]], None]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise m23_package.M23PackageError(message)


def write_manifest(path: pathlib.Path, manifest: dict[str, Any], *, resign: bool = True) -> pathlib.Path:
    if resign:
        manifest.pop("package_id", None)
        identity = m23_package.sha256_bytes(m23_package.canonical_json(manifest))
        manifest["package_id"] = identity
    m23_package.write_new(path, m23_package.canonical_json(manifest))
    return path.parent


def manifest_mutation(source: pathlib.Path, scratch: pathlib.Path, label: str,
                      mutation: ManifestMutation, *, resign: bool = True) -> pathlib.Path:
    stage = scratch / ("." + label)
    shutil.copytree(source, stage)
    manifest_path = stage / "manifest.json"
    manifest = m23_package.load_json(manifest_path)
    mutation(manifest)
    manifest_path.unlink()
    write_manifest(manifest_path, manifest, resign=resign)
    if not resign:
        return stage
    final = scratch / manifest["package_id"]
    stage.rename(final)
    return final


def refresh_model_identity(stage: pathlib.Path, manifest: dict[str, Any]) -> None:
    digest = m23_package.sha256_file(stage / "model.onnx")
    manifest["files"]["model.onnx"] = digest
    manifest["provenance"]["model_sha256"] = digest


def graph_mutation(source: pathlib.Path, scratch: pathlib.Path, label: str) -> pathlib.Path:
    import onnx
    from onnx import TensorProto

    stage = scratch / ("." + label)
    shutil.copytree(source, stage)
    model_path = stage / "model.onnx"
    model = onnx.load(model_path, load_external_data=False)
    manifest = m23_package.load_json(stage / "manifest.json")
    if label.startswith("input-"):
        value = model.graph.input[0]
        manifest_value = manifest["graph"]["inputs"][0]
    else:
        value = model.graph.output[0]
        manifest_value = manifest["graph"]["outputs"][0]
    if label == "output-shape":
        before = value.name
        raw = before + "_raw"
        for node in model.graph.node:
            for index, name in enumerate(node.output):
                if name == before:
                    node.output[index] = raw
        model.graph.node.append(onnx.helper.make_node("Flatten", [raw], [before], axis=0))
        del value.type.tensor_type.shape.dim[:]
        value.type.tensor_type.shape.dim.add().dim_value = 1
        value.type.tensor_type.shape.dim.add().dim_param = "mutated"
        manifest_value["shape"] = [1, "mutated"]
    elif label == "output-dtype":
        before = value.name
        raw = before + "_raw"
        for node in model.graph.node:
            for index, name in enumerate(node.output):
                if name == before:
                    node.output[index] = raw
        model.graph.node.append(onnx.helper.make_node("Cast", [raw], [before], to=TensorProto.INT64))
        value.type.tensor_type.elem_type = TensorProto.INT64
        manifest_value["dtype"] = "int64"
    elif label.endswith("name"):
        before = value.name
        value.name = "mutated_tensor"
        nodes = model.graph.node
        for node in nodes:
            fields = node.input if label.startswith("input-") else node.output
            for index, name in enumerate(fields):
                if name == before:
                    fields[index] = value.name
        manifest_value["name"] = value.name
    elif label.endswith("shape"):
        value.type.tensor_type.shape.dim[-1].ClearField("dim_param")
        value.type.tensor_type.shape.dim[-1].dim_value = 99
        manifest_value["shape"][-1] = 99
    elif label.endswith("dtype"):
        value.type.tensor_type.elem_type = TensorProto.INT64
        manifest_value["dtype"] = "int64"
    else:
        raise m23_package.M23PackageError(f"unknown graph mutation: {label}")
    onnx.save_model(model, model_path, save_as_external_data=False)
    refresh_model_identity(stage, manifest)
    (stage / "manifest.json").unlink()
    write_manifest(stage / "manifest.json", manifest)
    final = scratch / manifest["package_id"]
    stage.rename(final)
    return final


def file_mutation(source: pathlib.Path, scratch: pathlib.Path, label: str) -> pathlib.Path:
    stage = scratch / ("." + label)
    shutil.copytree(source, stage)
    if label == "missing-file":
        (stage / "golden.jsonl").unlink()
        return stage
    if label == "unknown-file":
        (stage / "unknown").write_text("x", encoding="ascii")
        return stage
    if label == "symlink":
        (stage / "golden.jsonl").unlink()
        (stage / "golden.jsonl").symlink_to("evaluation.json")
        return stage
    if label == "truncated-onnx":
        (stage / "model.onnx").write_bytes(b"truncated")
        manifest = m23_package.load_json(stage / "manifest.json")
        refresh_model_identity(stage, manifest)
        (stage / "manifest.json").unlink()
        write_manifest(stage / "manifest.json", manifest)
        final = scratch / manifest["package_id"]
        stage.rename(final)
        return final
    raise m23_package.M23PackageError(f"unknown file mutation: {label}")


def runtime(arguments: argparse.Namespace, package: pathlib.Path, probe: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [str(arguments.runtime_smoke), "--package", str(package), "--probe", probe],
        capture_output=True, timeout=60, check=False,
    )


def expect_package_rejection(arguments: argparse.Namespace, package: pathlib.Path,
                             contract: dict[str, Any], label: str) -> dict[str, Any]:
    python_rejected = False
    try:
        m23_package.validate_package(package.resolve(), contract)
    except (m23_package.M23PackageError, OSError, RuntimeError, ValueError):
        python_rejected = True
    observed = runtime(arguments, package.resolve(), "load")
    runtime_rejected = observed.returncode != 0 and b"M23_PACKAGE_SMOKE=FAIL" in observed.stderr
    require(python_rejected and runtime_rejected, f"package mutation was not rejected before inference: {label}")
    return {"label": label, "python_validator": "REJECTED", "runtime_loader": "REJECTED"}


def expect_request_rejection(arguments: argparse.Namespace, package: pathlib.Path,
                             label: str, probe: str) -> dict[str, Any]:
    observed = runtime(arguments, package, probe)
    require(observed.returncode != 0 and b"M23_PACKAGE_SMOKE=FAIL" in observed.stderr,
            f"request mutation was not rejected before inference: {label}")
    return {"label": label, "probe": probe, "runtime_request": "REJECTED"}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--package-root", type=pathlib.Path, required=True)
    parser.add_argument("--runtime-smoke", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    return parser.parse_args()


def run(arguments: argparse.Namespace) -> dict[str, Any]:
    root = arguments.root.resolve()
    contract_validator.validate(root)
    contract = contract_validator.load(root / contract_validator.CONTRACT)
    m23_package.validate_output_root(root, arguments.package_root)
    require(arguments.runtime_smoke.is_absolute() and arguments.runtime_smoke.is_file() and
            os.access(arguments.runtime_smoke, os.X_OK), "M23 package runtime smoke is not executable")
    require(arguments.artifact_root.is_absolute() and not arguments.artifact_root.exists() and
            arguments.artifact_root.parent.is_dir(), "M23 mutation artifact root must be new and absolute")
    models = sorted((arguments.package_root / "models").iterdir())
    source = next(item for item in models if m23_package.load_json(item / "manifest.json")["architecture_id"] ==
                  "monolithic-generalist-v1").resolve()
    require(runtime(arguments, source, "load").returncode == 0 and runtime(arguments, source, "valid").returncode == 0,
            "M23 accepted package failed its load/valid preflight")
    arguments.artifact_root.mkdir(mode=0o700)
    scratch = arguments.artifact_root / ".mutations"
    scratch.mkdir()
    manifest_mutations: dict[str, ManifestMutation] = {
        "package-format": lambda value: value.__setitem__("format", "mutated"),
        "compatibility-version": lambda value: value.__setitem__("compatibility_version", 2),
        "architecture-id": lambda value: value.__setitem__("architecture_id", "mutated"),
        "architecture-version": lambda value: value.__setitem__("architecture_version", 2),
        "checkpoint-id": lambda value: value.__setitem__("checkpoint_id", "0" * 64),
        "learning-contract-id": lambda value: value.__setitem__("learning_contract_sha256", "0" * 64),
        "source-tree-id": lambda value: value.__setitem__("source_tree_id", "0" * 40),
        "onnx-opset": lambda value: value.__setitem__("onnx_opset", 19),
        "onnxruntime-version": lambda value: value.__setitem__("onnxruntime_version", "0.0.0"),
        "recurrent-width": lambda value: value.__setitem__("recurrent_width", 128),
        "recurrent-reset-semantics": lambda value: value.__setitem__("recurrent_reset_semantics", "mutated"),
        "normalization": lambda value: value.__setitem__("normalization", "mutated"),
        "file-digest": lambda value: value["files"].__setitem__("model.onnx", "0" * 64),
    }
    graph_labels = {"input-name", "input-shape", "input-dtype", "output-name", "output-shape", "output-dtype"}
    file_labels = {"missing-file", "unknown-file", "symlink", "truncated-onnx"}
    request_probes = {
        "nonfinite-input": "nonfinite", "all-illegal-mask": "all-illegal",
        "batch-zero": "batch-zero", "batch-over-32": "batch-over-32",
    }
    results: list[dict[str, Any]] = []
    try:
        for label in contract["equivalence"]["rejection_matrix"]:
            if label == "package-id":
                mutated = manifest_mutation(
                    source, scratch, label, lambda value: value.__setitem__("package_id", "0" * 64), resign=False,
                )
            elif label in manifest_mutations:
                mutated = manifest_mutation(source, scratch, label, manifest_mutations[label])
            elif label in graph_labels:
                mutated = graph_mutation(source, scratch, label)
            elif label in file_labels:
                mutated = file_mutation(source, scratch, label)
            elif label in request_probes:
                results.append(expect_request_rejection(arguments, source, label, request_probes[label]))
                continue
            else:
                raise m23_package.M23PackageError(f"M23 rejection mutation is unimplemented: {label}")
            results.append(expect_package_rejection(arguments, mutated, contract, label))
            if mutated.exists():
                shutil.rmtree(mutated)
        require([item["label"] for item in results] == contract["equivalence"]["rejection_matrix"],
                "M23 rejection mutation order/coverage drifted")
        report = {
            "accepted_package_id": source.name,
            "contract_sha256": m23_package.sha256_file(root / contract_validator.CONTRACT),
            "rejections": results,
            "schema_version": "openttd-rl-v2-m23-package-mutation-report-1",
            "status": "PASS",
            "summary": {"package_mutations": 24, "request_mutations": 4, "total": 28},
        }
        m23_package.write_new(arguments.artifact_root / "package-mutation-report.json",
                              m23_package.canonical_json(report, newline=True))
        return report
    finally:
        if scratch.exists():
            shutil.rmtree(scratch)


def main() -> int:
    arguments = parse_arguments()
    try:
        report = run(arguments)
        print(f"V2_M23_PACKAGE_MUTATIONS=PASS total={report['summary']['total']} "
              f"package={report['summary']['package_mutations']} request={report['summary']['request_mutations']}")
        return 0
    except (m23_package.M23PackageError, contract_validator.M23ContractError, OSError, RuntimeError, ValueError,
            subprocess.SubprocessError) as exc:
        print(f"V2_M23_PACKAGE_MUTATIONS=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
