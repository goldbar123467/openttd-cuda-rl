#!/usr/bin/env python3
"""Deterministic M23 checkpoint/deployment package construction and validation."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import pathlib
import shutil
from dataclasses import dataclass
from typing import Any, Callable

import m23_golden
import validate_m23_release_contract as contract_validator


class M23PackageError(RuntimeError):
    """An M23 package input, payload, or identity failed closed."""


PAYLOAD_FILES = ["model.onnx", "golden.jsonl", "evaluation.json", "INSTALL.md", "MODEL_CARD.md"]
COMPLETE_FILES = ["INSTALL.md", "MODEL_CARD.md", "evaluation.json", "golden.jsonl", "manifest.json", "model.onnx"]
MANIFEST_KEYS = {
    "architecture_id", "architecture_version", "checkpoint_id", "compatibility_version", "files", "format",
    "graph", "installation", "learning_contract_sha256", "normalization", "onnx_opset", "onnxruntime_version",
    "package_id", "provenance", "recurrent_reset_semantics", "recurrent_width", "role", "source_tree_id",
}
PROVENANCE_KEYS = {
    "contract_sha256", "equivalence_report_sha256", "export_report_sha256", "golden_binary_sha256",
    "model_sha256",
}
EVALUATION_KEYS = {
    "architecture_id", "case_count", "checkpoint_id", "compared_runtimes", "equivalence_report_sha256",
    "failure_counts", "golden_binary_sha256", "maximum_error", "model_sha256", "result_runtime", "results",
    "row_count", "schema_version", "status", "tolerance",
}
FORBIDDEN_BYTES = (
    b"/home/", b"/Users/", b"BEGIN PRIVATE KEY", b"AWS_SECRET_ACCESS_KEY", b"GITHUB_TOKEN=",
    b"OPENAI_API_KEY=",
)
TRAINING_NODES = {"Adagrad", "Adam", "Dropout", "Gradient", "Momentum"}
SHA256_LENGTH = 64


@dataclass(frozen=True)
class PackageSummary:
    architecture_id: str
    checkpoint_id: str
    package_id: str
    model_sha256: str
    golden_sha256: str
    evaluation_sha256: str
    total_bytes: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M23PackageError(message)


def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_json(value: Any, *, newline: bool = False) -> bytes:
    result = json.dumps(
        value, allow_nan=False, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("ascii")
    return result + (b"\n" if newline else b"")


def load_json_bytes(value: bytes, label: str) -> Any:
    require(value and not value.startswith(b"\xef\xbb\xbf"), f"{label} is empty or has a BOM")
    try:
        return json.loads(value.decode("utf-8"), object_pairs_hook=reject_duplicate)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise M23PackageError(f"{label} is not strict JSON: {exc}") from exc


def load_json(path: pathlib.Path, maximum: int = 64 * 1024 * 1024) -> Any:
    require(path.is_file() and not path.is_symlink(), f"JSON input is not a regular file: {path.name}")
    require(0 < path.stat().st_size <= maximum, f"JSON input size is invalid: {path.name}")
    return load_json_bytes(path.read_bytes(), path.name)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_new(path: pathlib.Path, value: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
    finally:
        os.close(descriptor)


def foundation_sha(contract: dict[str, Any], name: str) -> str:
    matches = [item["sha256"] for item in contract["foundations"]["files"] if item["path"] == name]
    require(len(matches) == 1, f"M23 foundation identity is missing: {name}")
    return matches[0]


def architecture_maps(contract: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    checkpoints = {item["architecture_id"]: item for item in contract["checkpoint_packages"]["architectures"]}
    deployments = {item["architecture_id"]: item for item in contract["deployment_packages"]["architectures"]}
    require(list(checkpoints) == list(deployments) == contract_validator.ARCHITECTURES,
            "M23 architecture inventory/order drifted")
    return checkpoints, deployments


def validate_checkpoint(path: pathlib.Path, item: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    require(path.is_absolute() and path.is_dir() and not path.is_symlink(),
            "checkpoint must be an absolute nonsymlink directory")
    require(path.name == item["checkpoint_id"], "checkpoint directory/content address mismatch")
    expected_names = contract["checkpoint_packages"]["inventory"]
    entries = list(path.iterdir())
    require(len(entries) == len(expected_names) and sorted(entry.name for entry in entries) == sorted(expected_names),
            "checkpoint exact file inventory drifted")
    expected = {entry["name"]: entry for entry in item["files"]}
    total = 0
    files: list[dict[str, Any]] = []
    for name in expected_names:
        source = path / name
        require(source.is_file() and not source.is_symlink(), f"checkpoint entry is not a regular file: {name}")
        size = source.stat().st_size
        digest = sha256_file(source)
        require(size == expected[name]["bytes"] and digest == expected[name]["sha256"],
                f"checkpoint file identity mismatch: {name}")
        total += size
        files.append({"bytes": size, "name": name, "sha256": digest})
    require(total <= contract["checkpoint_packages"]["maximum_total_bytes_per_checkpoint"],
            "checkpoint exceeds the frozen byte budget")
    return {"architecture_id": item["architecture_id"], "checkpoint_id": item["checkpoint_id"],
            "files": files, "total_bytes": total}


def copy_checkpoint(source: pathlib.Path, destination: pathlib.Path, item: dict[str, Any],
                    contract: dict[str, Any]) -> dict[str, Any]:
    before = validate_checkpoint(source, item, contract)
    require(not destination.exists() and destination.parent.is_dir(), "checkpoint destination already exists")
    destination.mkdir(mode=0o700)
    for name in contract["checkpoint_packages"]["inventory"]:
        shutil.copyfile(source / name, destination / name)
    after = validate_checkpoint(destination.resolve(), item, contract)
    require(before == after, "checkpoint exact-copy verification drifted")
    return after


def tensor_signature(value: Any) -> list[dict[str, Any]]:
    from onnx import TensorProto

    types = {TensorProto.FLOAT: "float32", TensorProto.BOOL: "bool"}
    result: list[dict[str, Any]] = []
    for item in value:
        tensor = item.type.tensor_type
        require(tensor.elem_type in types, f"ONNX tensor dtype is unsupported: {item.name}")
        shape: list[str | int] = []
        for dimension in tensor.shape.dim:
            if dimension.dim_param:
                shape.append(dimension.dim_param)
            else:
                shape.append(dimension.dim_value)
        result.append({"dtype": types[tensor.elem_type], "name": item.name, "shape": shape})
    return result


def inspect_onnx(path: pathlib.Path, graph_contract: dict[str, Any]) -> dict[str, Any]:
    try:
        import onnx
    except ImportError as exc:
        raise M23PackageError("ONNX 1.22.0 is required for M23 graph inspection") from exc
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), "ONNX model path is invalid")
    try:
        model = onnx.load(path, load_external_data=False)
        onnx.checker.check_model(model, full_check=True)
    except Exception as exc:
        raise M23PackageError(f"ONNX graph validation failed: {exc}") from exc
    require([(item.domain, item.version) for item in model.opset_import] == [("", graph_contract["opset"])],
            "ONNX opset drifted")
    inputs = tensor_signature(model.graph.input)
    outputs = tensor_signature(model.graph.output)
    require(inputs == graph_contract["inputs"], f"ONNX input signature drifted: {inputs}")
    require(outputs == graph_contract["outputs"], f"ONNX output signature drifted: {outputs}")
    require(model.producer_name == "openttd-rl" and model.producer_version == "2.0.0" and
            model.domain == "openttd-rl" and model.model_version == 2,
            "ONNX canonical producer metadata drifted")
    require(not model.doc_string and not model.metadata_props and not model.graph.doc_string and
            all(not node.doc_string for node in model.graph.node), "ONNX documentation metadata was not removed")
    require(not any(node.op_type in TRAINING_NODES or node.domain.startswith("ai.onnx.preview.training")
                    for node in model.graph.node), "ONNX graph contains a training-only node")
    for tensor in model.graph.initializer:
        require(tensor.data_location != onnx.TensorProto.EXTERNAL and not tensor.external_data,
                "ONNX graph contains external tensor data")
    return {
        "initializer_count": len(model.graph.initializer), "inputs": inputs, "node_count": len(model.graph.node),
        "outputs": outputs, "opset": graph_contract["opset"], "training_nodes": False,
    }


def validate_export(export_root: pathlib.Path, architecture: str, checkpoint: dict[str, Any],
                    contract: dict[str, Any]) -> tuple[pathlib.Path, dict[str, Any], dict[str, Any]]:
    directory = export_root / architecture
    require(export_root.is_absolute() and directory.is_dir() and not directory.is_symlink(),
            f"export directory is missing: {architecture}")
    require(sorted(item.name for item in directory.iterdir()) == ["export-report.json", "model.onnx"],
            "export directory inventory drifted")
    report_path = directory / "export-report.json"
    report = load_json(report_path)
    model_path = (directory / "model.onnx").resolve()
    model_sha = sha256_file(model_path)
    expected_model_sha = next(item["sha256"] for item in checkpoint["files"] if item["name"] == "model.pt")
    require(report.get("schema_version") == "openttd-rl-v2-m23-export-report-1" and
            report.get("status") == "PASS" and report.get("architecture_id") == architecture and
            report.get("checkpoint_id") == checkpoint["checkpoint_id"] and
            report.get("checkpoint_model_sha256") == expected_model_sha and report.get("state_tensors") == 89,
            "M23 export report identity drifted")
    onnx_report = report.get("onnx", {})
    require(onnx_report.get("sha256") == model_sha and onnx_report.get("bytes") == model_path.stat().st_size and
            onnx_report.get("opset") == 18 and onnx_report.get("onnxruntime") == "1.28.0" and
            onnx_report.get("same_process_repeat_byte_identical") is True,
            "M23 export report/model identity drifted")
    graph = inspect_onnx(model_path, contract["deployment_packages"]["graph"])
    return model_path, report, graph


def validate_equivalence(path: pathlib.Path, golden_binary: pathlib.Path, model_shas: dict[str, str],
                         contract: dict[str, Any]) -> tuple[dict[str, Any], list[m23_golden.GoldenRecord]]:
    report = load_json(path)
    records = m23_golden.decode(golden_binary.resolve())
    require(len(records) == contract["equivalence"]["total_architecture_cases"],
            "M23 golden case count drifted")
    expected_ids = [item.definition.case_id for item in records]
    cases = report.get("cases")
    require(report.get("schema_version") == "openttd-rl-v2-m23-onnx-equivalence-report-1" and
            report.get("status") == "PASS" and isinstance(cases, list) and len(cases) == len(records),
            "M23 equivalence report header drifted")
    require([item.get("case_id") for item in cases] == expected_ids and
            all(item.get("passed") is True and item.get("action_exact") is True for item in cases),
            "M23 equivalence case order or result drifted")
    require(report.get("failure_counts") == {"action": 0, "float": 0, "total": 0},
            "M23 equivalence failure counts are nonzero")
    require(report.get("golden") == {"sha256": sha256_file(golden_binary)} and
            report.get("models") == {"monolithic_sha256": model_shas[contract_validator.ARCHITECTURES[0]],
                                     "specialist_sha256": model_shas[contract_validator.ARCHITECTURES[1]]},
            "M23 equivalence input identity drifted")
    tolerances = contract["equivalence"]["tolerances"]
    expected_tolerance = {"absolute": tolerances["program_logits"]["absolute"],
                          "relative": tolerances["program_logits"]["relative"]}
    require(report.get("tolerance") == expected_tolerance and report.get("runtime") == "onnxruntime-1.28.0-cpu",
            "M23 equivalence runtime/tolerance drifted")
    for item in cases:
        require(item.get("batch") in contract["equivalence"]["coverage"]["batch_sizes"],
                "M23 equivalence batch drifted")
        for key in ("hidden_absolute", "hidden_input_absolute", "hidden_relative", "logits_absolute",
                    "logits_relative", "value_absolute", "value_relative"):
            require(isinstance(item.get(key), (int, float)) and math.isfinite(item[key]) and item[key] >= 0,
                    f"M23 equivalence error is invalid: {key}")
    return report, records


def validate_golden_jsonl(path: pathlib.Path, architecture: str) -> list[dict[str, Any]]:
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= 64 * 1024 * 1024,
            "golden.jsonl path/size is invalid")
    raw = path.read_bytes()
    require(raw.endswith(b"\n") and b"\r" not in raw, "golden.jsonl line encoding drifted")
    lines = raw.splitlines(keepends=True)
    require(len(lines) == m23_golden.CASES_PER_ARCHITECTURE, "golden.jsonl case count drifted")
    result: list[dict[str, Any]] = []
    carried: list[list[float] | None] = [None, None]
    architecture_index = contract_validator.ARCHITECTURES.index(architecture)
    for local, line in enumerate(lines):
        value = load_json_bytes(line[:-1], f"golden.jsonl line {local}")
        require(isinstance(value, dict) and canonical_json(value, newline=True) == line,
                "golden.jsonl record is not canonical")
        definition = m23_golden.generate_definition(architecture_index, local)
        expected = m23_golden.record_json(m23_golden.GoldenRecord(
            definition, [], [], [], [], [],
        ))
        for key in ("architecture_id", "batch", "case_class", "case_id", "hidden_mode", "mask_pattern",
                    "program_mask", "public_features", "recurrent_reset", "seed", "sequence", "step"):
            require(value.get(key) == expected[key], f"golden.jsonl definition drifted: {definition.case_id}:{key}")
        batch = definition.batch
        for key, size in (("hidden_input", batch * m23_golden.HIDDEN),
                          ("program_logits", batch * m23_golden.PROGRAMS),
                          ("program_value", batch), ("next_hidden", batch * m23_golden.HIDDEN),
                          ("greedy_program", batch)):
            observed = value.get(key)
            require(isinstance(observed, list) and len(observed) == size,
                    f"golden.jsonl output shape drifted: {definition.case_id}:{key}")
            require(all(isinstance(item, (int, float)) and math.isfinite(item) for item in observed),
                    f"golden.jsonl output is nonfinite: {definition.case_id}:{key}")
        expected_hidden = definition.initial_hidden
        if definition.hidden_mode == 1:
            require(definition.sequence < 2 and carried[definition.sequence] is not None,
                    "golden.jsonl carried state lacks its predecessor")
            expected_hidden = carried[definition.sequence] or []
        require(value["hidden_input"] == expected_hidden, "golden.jsonl carried hidden state drifted")
        for row, action in enumerate(value["greedy_program"]):
            require(isinstance(action, int) and 0 <= action < m23_golden.PROGRAMS and
                    definition.program_mask[row * m23_golden.PROGRAMS + action] == 1,
                    "golden.jsonl greedy program is illegal")
        if definition.case_class == 1:
            carried[definition.sequence] = value["next_hidden"]
        require(set(value) == set(expected), "golden.jsonl field inventory drifted")
        result.append(value)
    return result


def architecture_evaluation(report: dict[str, Any], records: list[m23_golden.GoldenRecord], architecture: str,
                            checkpoint_id: str, model_sha: str, report_sha: str,
                            golden_sha: str) -> dict[str, Any]:
    selected = [item for item in report["cases"] if item["case_id"].startswith(architecture + "-")]
    selected_records = [item for item in records if m23_golden.ARCHITECTURES[item.definition.architecture] == architecture]
    require(len(selected) == len(selected_records) == 24, "per-architecture equivalence inventory drifted")
    maximum = {
        key: max(item[key] for item in selected)
        for key in ("hidden_absolute", "hidden_input_absolute", "hidden_relative", "logits_absolute",
                    "logits_relative", "value_absolute", "value_relative")
    }
    return {
        "architecture_id": architecture,
        "case_count": len(selected),
        "checkpoint_id": checkpoint_id,
        "compared_runtimes": ["native-libtorch-cpu", "standalone-onnxruntime-cpu"],
        "equivalence_report_sha256": report_sha,
        "failure_counts": {"action": 0, "float": 0, "total": 0},
        "golden_binary_sha256": golden_sha,
        "maximum_error": maximum,
        "model_sha256": model_sha,
        "result_runtime": report["runtime"],
        "results": selected,
        "row_count": sum(item.definition.batch for item in selected_records),
        "schema_version": "openttd-rl-v2-m23-package-evaluation-1",
        "status": "PASS",
        "tolerance": report["tolerance"],
    }


def install_text(package_format: str) -> bytes:
    return f"""# OpenTTD RL V2 inference-only deployment package

Format: `{package_format}`.

Install by copying this complete directory to a new temporary sibling of
`openttd-rl/models/<package-id>`, validating it with the M23 inference-only
loader, and atomically renaming it to its package ID. Never merge or rewrite
package files. OpenTTD, ONNX Runtime 1.28.0 CPU, and OpenSSL Crypto are required.
Python, LibTorch, CUDA, optimizer state, and trainer code are not runtime
dependencies.

Uninstall only the exact content-addressed package directory after OpenTTD has
released it. A validation failure must occur before company control; runtime
fallback is the wait program and issues no construction, vehicle, or order
commands.
""".encode("ascii")


def model_card_text(architecture: str, role: str, checkpoint_id: str) -> bytes:
    return f"""# OpenTTD RL V2 model card: {architecture}

- Role: `{role}`
- Checkpoint: `{checkpoint_id}`
- Parameters: `1,457,520`
- Interface: 32 public float32 features, a 17-program legal mask, and a
  256-value recurrent state; dynamic batches are limited to 1 through 32.
- Output: masked logits for one high-level program, a scalar value estimate,
  and the next recurrent state.

The learned model chooses a legal high-level program from public game state.
Reviewed deterministic OpenTTD code performs planning, construction, vehicle,
order, and recovery commands. This package does not claim end-to-end learned
low-level control. It supports the finite G15-G21 V2 scope and is not a claim of
compatibility with arbitrary NewGRFs, Game Scripts, third-party AIs, or future
OpenTTD releases.

Training and selection use the frozen M22 semantic-v2 curriculum. The package
golden corpus records 24 native LibTorch CPU cases for this architecture across
batches 1, 8, and 32, legal-mask adversaries, zero/reset/carried recurrent
state, all public modes, and four climates. `evaluation.json` records the
standalone ONNX Runtime comparison; source-integrated in-game equivalence and
visible-play acceptance remain external G23 release evidence.
""".encode("ascii")


def package_manifest(contract: dict[str, Any], deployment: dict[str, Any], checkpoint: dict[str, Any],
                     graph: dict[str, Any], files: dict[str, str], provenance: dict[str, str]) -> dict[str, Any]:
    package = contract["deployment_packages"]
    return {
        "architecture_id": deployment["architecture_id"],
        "architecture_version": deployment["architecture_version"],
        "checkpoint_id": deployment["checkpoint_id"],
        "compatibility_version": package["compatibility_version"],
        "files": files,
        "format": package["format"],
        "graph": {"dynamic_axis": package["graph"]["dynamic_axis"], "inputs": graph["inputs"],
                  "outputs": graph["outputs"], "training_nodes": graph["training_nodes"]},
        "installation": {key: package["installation"][key]
                         for key in ("atomic", "root", "training_dependencies", "uninstall")},
        "learning_contract_sha256": foundation_sha(contract, "config/v2/m22-learning-contract.json"),
        "normalization": package["adapter"]["normalization"],
        "onnx_opset": package["graph"]["opset"],
        "onnxruntime_version": package["graph"]["onnxruntime"],
        "provenance": provenance,
        "recurrent_reset_semantics": package["adapter"]["reset"],
        "recurrent_width": 256,
        "role": deployment["role"],
        "source_tree_id": contract["foundations"]["corrected_m22_source_tree"],
    }


def validate_evaluation(value: Any, architecture: str, checkpoint_id: str, model_sha: str,
                        golden_binary_sha: str) -> dict[str, Any]:
    require(isinstance(value, dict) and set(value) == EVALUATION_KEYS, "evaluation.json field inventory drifted")
    require(value["schema_version"] == "openttd-rl-v2-m23-package-evaluation-1" and value["status"] == "PASS" and
            value["architecture_id"] == architecture and value["checkpoint_id"] == checkpoint_id and
            value["model_sha256"] == model_sha and value["golden_binary_sha256"] == golden_binary_sha and
            value["case_count"] == 24 and value["failure_counts"] == {"action": 0, "float": 0, "total": 0} and
            value["compared_runtimes"] == ["native-libtorch-cpu", "standalone-onnxruntime-cpu"] and
            value["result_runtime"] == "onnxruntime-1.28.0-cpu",
            "evaluation.json identity/status drifted")
    require(isinstance(value["results"], list) and len(value["results"]) == 24 and
            all(item.get("passed") is True and item.get("action_exact") is True for item in value["results"]),
            "evaluation.json result inventory drifted")
    require(len(value["equivalence_report_sha256"]) == SHA256_LENGTH and
            all(character in "0123456789abcdef" for character in value["equivalence_report_sha256"]),
            "evaluation.json source identity is invalid")
    require(value["tolerance"] == {"absolute": 0.00005, "relative": 0.00005},
            "evaluation.json tolerance drifted")
    require(isinstance(value["row_count"], int) and value["row_count"] > 0,
            "evaluation.json row count is invalid")
    return value


def validate_package(package_path: pathlib.Path, contract: dict[str, Any], *, inspect_graph: bool = True) -> PackageSummary:
    require(package_path.is_absolute() and package_path.is_dir() and not package_path.is_symlink(),
            "deployment package must be an absolute nonsymlink directory")
    entries = list(package_path.iterdir())
    require(len(entries) == len(COMPLETE_FILES) and sorted(item.name for item in entries) == COMPLETE_FILES,
            "deployment package file inventory drifted")
    maximum = contract["deployment_packages"]["maximum_file_bytes"]
    for entry in entries:
        require(entry.is_file() and not entry.is_symlink() and 0 < entry.stat().st_size <= maximum,
                f"deployment package entry is invalid: {entry.name}")
    manifest_path = package_path / "manifest.json"
    raw_manifest = manifest_path.read_bytes()
    manifest = load_json_bytes(raw_manifest, "manifest.json")
    require(isinstance(manifest, dict) and set(manifest) == MANIFEST_KEYS,
            "deployment manifest field inventory drifted")
    require(raw_manifest == canonical_json(manifest), "deployment manifest is not canonical JSON")
    package_id = manifest["package_id"]
    require(isinstance(package_id, str) and len(package_id) == SHA256_LENGTH and package_path.name == package_id,
            "deployment package directory identity drifted")
    identity = copy.deepcopy(manifest)
    del identity["package_id"]
    require(sha256_bytes(canonical_json(identity)) == package_id, "deployment package content address drifted")
    checkpoints, deployments = architecture_maps(contract)
    architecture = manifest["architecture_id"]
    require(architecture in deployments, "deployment package architecture is unsupported")
    deployment = deployments[architecture]
    checkpoint = checkpoints[architecture]
    package = contract["deployment_packages"]
    require(manifest["format"] == package["format"] and
            manifest["compatibility_version"] == package["compatibility_version"] and
            manifest["architecture_version"] == deployment["architecture_version"] and
            manifest["checkpoint_id"] == deployment["checkpoint_id"] == checkpoint["checkpoint_id"] and
            manifest["role"] == deployment["role"], "deployment package compatibility/selection drifted")
    require(manifest["learning_contract_sha256"] == foundation_sha(contract, "config/v2/m22-learning-contract.json") and
            manifest["source_tree_id"] == contract["foundations"]["corrected_m22_source_tree"] and
            manifest["onnx_opset"] == package["graph"]["opset"] and
            manifest["onnxruntime_version"] == package["graph"]["onnxruntime"] and
            manifest["normalization"] == package["adapter"]["normalization"] and
            manifest["recurrent_width"] == 256 and
            manifest["recurrent_reset_semantics"] == package["adapter"]["reset"],
            "deployment package semantic compatibility drifted")
    expected_installation = {key: package["installation"][key]
                             for key in ("atomic", "root", "training_dependencies", "uninstall")}
    require(manifest["installation"] == expected_installation,
            "deployment package installation boundary drifted")
    frozen_graph = {"dynamic_axis": package["graph"]["dynamic_axis"], "inputs": package["graph"]["inputs"],
                    "outputs": package["graph"]["outputs"], "training_nodes": False}
    require(manifest["graph"] == frozen_graph, "deployment manifest graph contract drifted")
    require(isinstance(manifest["provenance"], dict) and set(manifest["provenance"]) == PROVENANCE_KEYS and
            manifest["provenance"]["contract_sha256"] == sha256_file(
                pathlib.Path(__file__).resolve().parents[2] / contract_validator.CONTRACT),
            "deployment package provenance drifted")
    require(manifest["files"].keys() == dict.fromkeys(PAYLOAD_FILES).keys(),
            "deployment payload digest inventory drifted")
    for name in PAYLOAD_FILES:
        require(manifest["files"][name] == sha256_file(package_path / name),
                f"deployment payload digest mismatch: {name}")
    model_sha = sha256_file(package_path / "model.onnx")
    require(manifest["provenance"]["model_sha256"] == model_sha,
            "deployment provenance/model digest drifted")
    if inspect_graph:
        graph = inspect_onnx((package_path / "model.onnx").resolve(), package["graph"])
        expected_graph = {"dynamic_axis": package["graph"]["dynamic_axis"], "inputs": graph["inputs"],
                          "outputs": graph["outputs"], "training_nodes": graph["training_nodes"]}
        require(manifest["graph"] == expected_graph, "deployment manifest/ONNX graph drifted")
    golden = validate_golden_jsonl(package_path / "golden.jsonl", architecture)
    evaluation_raw = (package_path / "evaluation.json").read_bytes()
    evaluation = load_json_bytes(evaluation_raw, "evaluation.json")
    require(evaluation_raw == canonical_json(evaluation, newline=True), "evaluation.json is not canonical JSON")
    validate_evaluation(evaluation, architecture, checkpoint["checkpoint_id"], model_sha,
                        manifest["provenance"]["golden_binary_sha256"])
    require([item["case_id"] for item in evaluation["results"]] == [item["case_id"] for item in golden],
            "evaluation/golden case identity drifted")
    for name in ("INSTALL.md", "MODEL_CARD.md"):
        value = (package_path / name).read_bytes()
        require(value.endswith(b"\n") and not any(token in value for token in FORBIDDEN_BYTES),
                f"deployment documentation contains a forbidden or malformed value: {name}")
    for name in COMPLETE_FILES:
        value = (package_path / name).read_bytes()
        require(not any(token in value for token in FORBIDDEN_BYTES),
                f"deployment package contains a forbidden path/dependency marker: {name}")
    return PackageSummary(
        architecture, checkpoint["checkpoint_id"], package_id, model_sha, manifest["files"]["golden.jsonl"],
        manifest["files"]["evaluation.json"], sum(item.stat().st_size for item in entries),
    )


def build_deployment_package(destination_root: pathlib.Path, contract: dict[str, Any], deployment: dict[str, Any],
                             checkpoint: dict[str, Any], model_path: pathlib.Path, export_report_path: pathlib.Path,
                             graph: dict[str, Any], records: list[m23_golden.GoldenRecord],
                             equivalence: dict[str, Any], equivalence_path: pathlib.Path,
                             golden_binary: pathlib.Path) -> pathlib.Path:
    architecture = deployment["architecture_id"]
    stage = destination_root / f".{architecture}.stage"
    require(not stage.exists(), "deployment staging directory already exists")
    stage.mkdir(mode=0o700)
    shutil.copyfile(model_path, stage / "model.onnx")
    selected = [item for item in records if m23_golden.ARCHITECTURES[item.definition.architecture] == architecture]
    m23_golden.write_jsonl((stage / "golden.jsonl").resolve(), selected, "all" if len(selected) == 48 else architecture)
    equivalence_sha = sha256_file(equivalence_path)
    golden_sha = sha256_file(golden_binary)
    model_sha = sha256_file(model_path)
    evaluation = architecture_evaluation(equivalence, records, architecture, checkpoint["checkpoint_id"], model_sha,
                                         equivalence_sha, golden_sha)
    write_new(stage / "evaluation.json", canonical_json(evaluation, newline=True))
    write_new(stage / "INSTALL.md", install_text(contract["deployment_packages"]["format"]))
    write_new(stage / "MODEL_CARD.md", model_card_text(architecture, deployment["role"], checkpoint["checkpoint_id"]))
    files = {name: sha256_file(stage / name) for name in PAYLOAD_FILES}
    provenance = {
        "contract_sha256": sha256_file(pathlib.Path(__file__).resolve().parents[2] / contract_validator.CONTRACT),
        "equivalence_report_sha256": equivalence_sha,
        "export_report_sha256": sha256_file(export_report_path),
        "golden_binary_sha256": golden_sha,
        "model_sha256": model_sha,
    }
    manifest = package_manifest(contract, deployment, checkpoint, graph, files, provenance)
    package_id = sha256_bytes(canonical_json(manifest))
    manifest["package_id"] = package_id
    write_new(stage / "manifest.json", canonical_json(manifest))
    final = destination_root / package_id
    require(not final.exists(), "deployment content address already exists")
    stage.rename(final)
    validate_package(final.resolve(), contract)
    return final


def build_all(repository_root: pathlib.Path, checkpoint_paths: dict[str, pathlib.Path], export_root: pathlib.Path,
              golden_binary: pathlib.Path, equivalence_path: pathlib.Path, output_root: pathlib.Path) -> dict[str, Any]:
    root = repository_root.resolve()
    contract_validator.validate(root)
    contract = contract_validator.load(root / contract_validator.CONTRACT)
    require(output_root.is_absolute() and not output_root.exists() and output_root.parent.is_dir(),
            "M23 package output root must be a new absolute directory")
    require(export_root.is_absolute() and export_root.is_dir() and golden_binary.is_absolute() and
            equivalence_path.is_absolute(), "M23 package inputs must be absolute existing paths")
    checkpoints, deployments = architecture_maps(contract)
    output_root.mkdir(mode=0o700)
    try:
        checkpoint_root = output_root / "checkpoints"
        model_root = output_root / "models"
        checkpoint_root.mkdir()
        model_root.mkdir()
        checkpoint_reports: list[dict[str, Any]] = []
        export_values: dict[str, tuple[pathlib.Path, dict[str, Any], dict[str, Any]]] = {}
        model_shas: dict[str, str] = {}
        for architecture in contract_validator.ARCHITECTURES:
            source = checkpoint_paths[architecture].resolve()
            checkpoint = checkpoints[architecture]
            destination_parent = checkpoint_root / architecture
            destination_parent.mkdir()
            checkpoint_reports.append(copy_checkpoint(source, destination_parent / checkpoint["checkpoint_id"],
                                                      checkpoint, contract))
            export_values[architecture] = validate_export(export_root, architecture, checkpoint, contract)
            model_shas[architecture] = sha256_file(export_values[architecture][0])
        equivalence, records = validate_equivalence(equivalence_path, golden_binary, model_shas, contract)
        packages: list[PackageSummary] = []
        for architecture in contract_validator.ARCHITECTURES:
            model_path, _, graph = export_values[architecture]
            final = build_deployment_package(
                model_root, contract, deployments[architecture], checkpoints[architecture], model_path,
                export_root / architecture / "export-report.json", graph, records, equivalence,
                equivalence_path, golden_binary,
            )
            packages.append(validate_package(final.resolve(), contract))
        report = {
            "checkpoint_packages": checkpoint_reports,
            "contract_sha256": sha256_file(root / contract_validator.CONTRACT),
            "deployment_packages": [item.__dict__ for item in packages],
            "equivalence_report_sha256": sha256_file(equivalence_path),
            "golden_binary_sha256": sha256_file(golden_binary),
            "schema_version": "openttd-rl-v2-m23-package-build-report-1",
            "status": "PASS",
        }
        write_new(output_root / "package-build-report.json", canonical_json(report, newline=True))
        return report
    except Exception:
        shutil.rmtree(output_root, ignore_errors=True)
        raise


def validate_output_root(repository_root: pathlib.Path, output_root: pathlib.Path,
                         *, inspect_graph: bool = True) -> dict[str, Any]:
    root = repository_root.resolve()
    contract_validator.validate(root)
    contract = contract_validator.load(root / contract_validator.CONTRACT)
    require(output_root.is_absolute() and output_root.is_dir() and not output_root.is_symlink(),
            "M23 package output root is invalid")
    require(sorted(item.name for item in output_root.iterdir()) == ["checkpoints", "models", "package-build-report.json"],
            "M23 package root inventory drifted")
    checkpoints, _ = architecture_maps(contract)
    checkpoint_reports: list[dict[str, Any]] = []
    for architecture in contract_validator.ARCHITECTURES:
        parent = output_root / "checkpoints" / architecture
        require(parent.is_dir() and not parent.is_symlink() and
                [item.name for item in parent.iterdir()] == [checkpoints[architecture]["checkpoint_id"]],
                "M23 checkpoint package directory inventory drifted")
        checkpoint_reports.append(validate_checkpoint(
            (parent / checkpoints[architecture]["checkpoint_id"]).resolve(), checkpoints[architecture], contract,
        ))
    models = output_root / "models"
    require(models.is_dir() and not models.is_symlink(), "M23 model package root is invalid")
    paths = sorted(models.iterdir(), key=lambda item: item.name)
    require(len(paths) == 2, "M23 deployment package count drifted")
    packages = sorted((validate_package(path.resolve(), contract, inspect_graph=inspect_graph) for path in paths),
                      key=lambda item: contract_validator.ARCHITECTURES.index(item.architecture_id))
    report_path = output_root / "package-build-report.json"
    report_raw = report_path.read_bytes()
    report = load_json_bytes(report_raw, "package-build-report.json")
    require(report_raw == canonical_json(report, newline=True) and
            report.get("schema_version") == "openttd-rl-v2-m23-package-build-report-1" and
            report.get("status") == "PASS" and report.get("contract_sha256") == sha256_file(root / contract_validator.CONTRACT) and
            report.get("checkpoint_packages") == checkpoint_reports and
            report.get("deployment_packages") == [item.__dict__ for item in packages],
            "M23 package build report drifted")
    return report
