#!/usr/bin/env python3
"""Mechanical pinned PyTorch-to-ONNX conversion for one immutable M09 model."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import sys
from typing import Any

import onnx
import torch
from onnx import numpy_helper


class M10ExportError(RuntimeError):
    """The mechanical ONNX conversion failed closed."""


M10_COMPATIBILITY = "e77edf9be1343970a55becbb05da96a6b9a17edbd8df2c7999701dd8fa1f33b6"
M09_COMPATIBILITY = "c64c9876c1f6cf46dcc2642bd4628ed45f4659d1866a047d4e51def60dab9a5e"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise M10ExportError(message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class StructuredMlp(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.hidden_1 = torch.nn.Linear(256, 128)
        self.hidden_2 = torch.nn.Linear(128, 128)
        self.policy_head = torch.nn.Linear(128, 41)
        self.value_head = torch.nn.Linear(128, 1)

    def forward(self, structured: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        hidden = torch.tanh(self.hidden_1(structured))
        hidden = torch.tanh(self.hidden_2(hidden))
        return self.policy_head(hidden), self.value_head(hidden).squeeze(-1)


class SpatialCnn(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.spatial_1 = torch.nn.Conv2d(32, 32, 3, stride=1, padding=1)
        self.spatial_2 = torch.nn.Conv2d(32, 64, 3, stride=2, padding=1)
        self.spatial_3 = torch.nn.Conv2d(64, 64, 3, stride=2, padding=1)
        self.spatial_projection = torch.nn.Linear(64 * 8 * 8, 128)
        self.policy_head = torch.nn.Linear(128, 41)
        self.value_head = torch.nn.Linear(128, 1)

    def encode_spatial(self, spatial: torch.Tensor) -> torch.Tensor:
        hidden = torch.tanh(self.spatial_1(spatial))
        hidden = torch.tanh(self.spatial_2(hidden))
        hidden = torch.tanh(self.spatial_3(hidden))
        return torch.tanh(self.spatial_projection(torch.flatten(hidden, 1)))

    def forward(self, spatial: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        hidden = self.encode_spatial(spatial)
        return self.policy_head(hidden), self.value_head(hidden).squeeze(-1)


class CombinedCnnMlp(SpatialCnn):
    def __init__(self) -> None:
        super().__init__()
        self.structured_1 = torch.nn.Linear(256, 128)
        self.fusion = torch.nn.Linear(256, 128)

    def forward(self, structured: torch.Tensor, spatial: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        structured_hidden = torch.tanh(self.structured_1(structured))
        spatial_hidden = self.encode_spatial(spatial)
        hidden = torch.tanh(self.fusion(torch.cat((structured_hidden, spatial_hidden), 1)))
        return self.policy_head(hidden), self.value_head(hidden).squeeze(-1)


def model_for(architecture: str) -> tuple[torch.nn.Module, tuple[torch.Tensor, ...], list[str], tuple[dict[int, str], ...]]:
    structured = torch.linspace(-1.0, 1.0, 2 * 256, dtype=torch.float32).reshape(2, 256)
    spatial = torch.linspace(0.0, 1.0, 2 * 32 * 32 * 32, dtype=torch.float32).reshape(2, 32, 32, 32)
    if architecture == "structured-mlp-v1":
        return StructuredMlp(), (structured,), ["structured"], ({0: "batch"},)
    if architecture == "spatial-cnn-v1":
        return SpatialCnn(), (spatial,), ["spatial"], ({0: "batch"},)
    if architecture == "combined-cnn-mlp-v1":
        return CombinedCnnMlp(), (structured, spatial), ["structured", "spatial"], ({0: "batch"}, {0: "batch"})
    raise M10ExportError(f"unknown architecture {architecture}")


def graph_shape(value: onnx.ValueInfoProto) -> list[str | int]:
    result: list[str | int] = []
    for dimension in value.type.tensor_type.shape.dim:
        result.append(dimension.dim_param if dimension.dim_param else dimension.dim_value)
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    source = args.source_package.resolve()
    output = args.output_dir.resolve()
    contract = json.loads(args.contract.resolve().read_text(encoding="utf-8"))
    require(contract["identity"]["compatibility_sha256"] == M10_COMPATIBILITY, "M10 contract identity drifted")
    require(sys.version_info[:3] == (3, 12, 3), "exporter Python version drifted")
    require(torch.__version__ == "2.13.0+cpu", "exporter PyTorch version drifted")
    require(onnx.__version__ == "1.22.0", "exporter ONNX version drifted")
    require(source.is_dir() and not source.is_symlink() and source.name == args.source_package_id, "source package identity/path mismatch")
    source_manifest_path = source / "manifest.json"
    source_model_path = source / "model.pt"
    source_before = {"manifest.json": sha256_file(source_manifest_path), "model.pt": sha256_file(source_model_path)}
    source_manifest_bytes = source_manifest_path.read_bytes()
    source_manifest = json.loads(source_manifest_bytes)
    require(hashlib.sha256(source_manifest_bytes).hexdigest() == source.name, "M09 source package content address drifted")
    require(source_manifest["format"] == "openttd-rl-evaluation-model-v1", "source is not an evaluation model")
    require(source_manifest["m09_compatibility_sha256"] == M09_COMPATIBILITY, "source M09 compatibility drifted")
    require(source_manifest["architecture"] == args.architecture, "source architecture drifted")
    require(source_manifest["model_sha256"] == source_before["model.pt"], "source model digest drifted")
    registered = next(item for item in contract["models"] if item["architecture_id"] == args.architecture)
    require(registered["source_package_id"] == source.name and registered["run_seed"] == source_manifest["run_seed"], "source is not the frozen selected package")
    require(not output.exists(), "export output already exists")
    output.mkdir(parents=True)
    try:
        archived = torch.jit.load(str(source_model_path), map_location="cpu")
        source_state = archived.state_dict()
        model, example_inputs, input_names, dynamic_shapes = model_for(args.architecture)
        model.load_state_dict(source_state, strict=True)
        model.eval()
        require(all(torch.equal(model.state_dict()[name], value) for name, value in source_state.items()), "Python module tensor transfer was not exact")
        first = output / "model.onnx"
        second = output / ".model-second.onnx"
        for destination in (first, second):
            torch.onnx.export(
                model,
                example_inputs,
                str(destination),
                input_names=input_names,
                output_names=["policy_logits", "value"],
                opset_version=18,
                dynamo=True,
                external_data=False,
                dynamic_shapes=dynamic_shapes,
            )
        require(first.read_bytes() == second.read_bytes(), "independent exports are not byte-identical")
        second.unlink()
        graph = onnx.load(str(first), load_external_data=False)
        onnx.checker.check_model(graph, full_check=True)
        require([(item.domain, item.version) for item in graph.opset_import] == [("", 18)], "ONNX opset drifted")
        observed_inputs = [{"name": item.name, "dtype": "float32", "shape": graph_shape(item)} for item in graph.graph.input]
        observed_outputs = [{"name": item.name, "dtype": "float32", "shape": graph_shape(item)} for item in graph.graph.output]
        require(observed_inputs == registered["inputs"], f"ONNX input signature drifted: {observed_inputs}")
        require(observed_outputs == contract["graph"]["outputs"], f"ONNX output signature drifted: {observed_outputs}")
        forbidden = {"Dropout", "Gradient", "Momentum", "Adam", "Adagrad"}
        require(not any(node.op_type in forbidden or node.domain.startswith("ai.onnx.preview.training") for node in graph.graph.node), "training-only ONNX node was exported")
        initializers = {item.name: numpy_helper.to_array(item) for item in graph.graph.initializer}
        for name, tensor in source_state.items():
            require(name in initializers, f"source tensor {name} is absent from ONNX")
            observed = torch.from_numpy(initializers[name].copy())
            require(torch.equal(observed, tensor), f"source tensor {name} changed during ONNX export")
        metadata = {
            "schema_version": "openttd-rl-v1-m10-export-metadata-1",
            "architecture": args.architecture,
            "source_package_id": source.name,
            "source_model_sha256": source_before["model.pt"],
            "m10_compatibility_sha256": M10_COMPATIBILITY,
            "repository_commit": args.repository_commit,
            "exporter": {"python": sys.version.split()[0], "torch": torch.__version__, "onnx": onnx.__version__, "opset": 18, "fallback": False},
            "graph": {
                "inputs": observed_inputs,
                "outputs": observed_outputs,
                "node_count": len(graph.graph.node),
                "initializer_count": len(graph.graph.initializer),
                "source_tensor_count": len(source_state),
                "training_nodes": False,
            },
            "model_onnx_sha256": sha256_file(first),
            "repeat_export_byte_identical": True,
            "source_read_only": True,
        }
        (output / "export-metadata.json").write_bytes(canonical_bytes(metadata) + b"\n")
        require({"manifest.json": sha256_file(source_manifest_path), "model.pt": sha256_file(source_model_path)} == source_before, "export mutated its source package")
        print(f"M10_EXPORT=PASS architecture={args.architecture} onnx_sha256={metadata['model_onnx_sha256']}", flush=True)
        return metadata
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-package", type=pathlib.Path, required=True)
    parser.add_argument("--source-package-id", required=True)
    parser.add_argument("--architecture", required=True)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--contract", type=pathlib.Path, required=True)
    parser.add_argument("--repository-commit", required=True)
    args = parser.parse_args()
    try:
        run(args)
    except Exception as exc:
        print(f"M10_EXPORT=FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
