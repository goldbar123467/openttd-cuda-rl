#!/usr/bin/env python3
"""Export both frozen M23 learned checkpoints to deterministic opset-18 ONNX graphs."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import pathlib
import sys
from typing import Any

import torch
from torch import Tensor, nn
from torch.nn import functional as functional

import onnx

import validate_m23_release_contract as contract_validator


PROGRAM_MODE = torch.tensor([0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 6, 6, 6, 6, 6], dtype=torch.int64)
INPUT_NAMES = ["public_features", "program_mask", "hidden_state", "recurrent_reset"]
OUTPUT_NAMES = ["program_logits", "program_value", "next_hidden"]
MAXIMUM_CHECKPOINT_FILE_BYTES = 32 * 1024 * 1024


class ExportError(ValueError):
    """The checkpoint or deterministic export boundary is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ExportError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ScalableEvaluationBackbone(nn.Module):
    """Exact M22 public-feature adapter, algebraically reducing single-valid-slot pools."""

    def __init__(self) -> None:
        super().__init__()
        self.entity_type_embedding = nn.Parameter(torch.empty(5, 128))
        self.structured_1 = nn.Linear(512, 256)
        self.structured_2 = nn.Linear(256, 128)
        self.spatial_1 = nn.Conv2d(32, 32, 5, stride=2, padding=2)
        self.spatial_2 = nn.Conv2d(32, 64, 3, stride=2, padding=1)
        self.spatial_3 = nn.Conv2d(64, 128, 3, stride=2, padding=1)
        self.spatial_projection = nn.Linear(384, 256)
        self.company_projection = nn.Linear(32, 128)
        self.town_projection = nn.Linear(24, 128)
        self.industry_projection = nn.Linear(24, 128)
        self.station_projection = nn.Linear(32, 128)
        self.vehicle_projection = nn.Linear(40, 128)
        self.entity_query = nn.Linear(128, 128)
        self.entity_key = nn.Linear(128, 128)
        self.entity_value = nn.Linear(128, 128)
        self.entity_fusion = nn.Linear(640, 128)
        self.entity_norm = nn.LayerNorm(128)
        self.entity_feedforward = nn.Linear(128, 128)
        self.entity_output_norm = nn.LayerNorm(128)
        self.graph_node_projection = nn.Linear(24, 128)
        self.graph_edge_projection = nn.Linear(16, 128)
        self.graph_message = nn.Linear(256, 128)
        self.graph_norm = nn.LayerNorm(128)
        self.graph_query = nn.Linear(128, 128)
        self.fusion = nn.Linear(768, 256)
        self.fusion_norm = nn.LayerNorm(256)
        self.memory = nn.GRUCell(256, 256)
        self.family_head = nn.Linear(256, 12)
        self.candidate_family_embedding = nn.Embedding(12, 128)
        self.candidate_projection = nn.Linear(32, 128)
        self.candidate_query = nn.Linear(256, 128)
        self.candidate_bias = nn.Linear(128, 1)
        self.value_head = nn.Linear(256, 1)

    def _spatial(self, public_features: Tensor, side: int) -> Tensor:
        batch = public_features.shape[0]
        ones = torch.ones((batch, 1, side, side), dtype=public_features.dtype, device=public_features.device)
        width = public_features[:, 11:12].reshape(batch, 1, 1, 1).expand(-1, -1, side, side)
        height = public_features[:, 12:13].reshape(batch, 1, 1, 1).expand(-1, -1, side, side)
        zeros = torch.zeros((batch, 29, side, side), dtype=public_features.dtype, device=public_features.device)
        return torch.cat((ones, width, height, zeros), dim=1)

    def _encode_spatial(self, value: Tensor) -> Tensor:
        value = functional.silu(self.spatial_1(value))
        value = functional.silu(self.spatial_2(value))
        value = functional.silu(self.spatial_3(value))
        return value.mean(dim=(2, 3))

    def _one_entity(self, projection: nn.Linear, raw: Tensor, type_index: int) -> Tensor:
        token = torch.tanh(projection(raw)) + self.entity_type_embedding[type_index]
        # M22 exposes only slot zero at this adapter. Its masked softmax weight is exactly one.
        return self.entity_value(token)

    def forward(self, public_features: Tensor, hidden_state: Tensor, recurrent_reset: Tensor) -> Tensor:
        batch = public_features.shape[0]
        structured = functional.pad(public_features, (0, 480))
        structured_hidden = torch.tanh(self.structured_2(torch.tanh(self.structured_1(structured))))

        spatial_hidden = torch.tanh(self.spatial_projection(torch.cat((
            self._encode_spatial(self._spatial(public_features, 64)),
            self._encode_spatial(self._spatial(public_features, 64)),
            self._encode_spatial(self._spatial(public_features, 32)),
        ), dim=1)))

        query = self.entity_query(structured_hidden)
        entity_hidden = torch.tanh(self.entity_fusion(torch.cat((
            self._one_entity(self.company_projection, public_features, 0),
            self._one_entity(self.town_projection, public_features[:, :24], 1),
            self._one_entity(self.industry_projection, public_features[:, :24], 2),
            self._one_entity(self.station_projection, public_features, 3),
            self._one_entity(self.vehicle_projection, functional.pad(public_features, (0, 8)), 4),
        ), dim=1)))
        entity_hidden = self.entity_norm(entity_hidden + query)
        entity_hidden = self.entity_output_norm(entity_hidden + functional.silu(self.entity_feedforward(entity_hidden)))

        node = torch.tanh(self.graph_node_projection(public_features[:, :24]))
        edge = torch.tanh(self.graph_edge_projection(public_features[:, 14:30]))
        message = torch.tanh(self.graph_message(torch.cat((node, edge), dim=1)))
        node = self.graph_norm(node + message)
        # The sole legal graph node receives the sole 0->0 edge and has attention weight one.
        graph_hidden = self.entity_value(node)

        candidate = torch.tanh(self.candidate_projection(public_features))
        candidate = candidate + self.candidate_family_embedding.weight[0]
        fused = functional.silu(self.fusion_norm(self.fusion(torch.cat((
            structured_hidden, spatial_hidden, entity_hidden, graph_hidden, candidate,
        ), dim=1))))
        reset_hidden = hidden_state * torch.logical_not(recurrent_reset).to(public_features.dtype).reshape(batch, 1)
        return self.memory(fused, reset_hidden)


class GeneralistDeploymentModel(nn.Module):
    """Exact learned M22 program head at the frozen compact deployment boundary."""

    def __init__(self, architecture: str) -> None:
        super().__init__()
        require(architecture in contract_validator.ARCHITECTURES, "unsupported M23 learned architecture")
        self.architecture = architecture
        self.register_buffer("program_mode", PROGRAM_MODE.clone())
        self.base_policy = ScalableEvaluationBackbone()
        self.domain_projection = nn.Linear(64, 128)
        self.domain_kind_embedding = nn.Embedding(18, 128)
        self.domain_key = nn.Linear(128, 128)
        self.domain_value = nn.Linear(128, 128)
        self.domain_query = nn.Linear(256, 128)
        self.program_projection = nn.Linear(64, 128)
        self.specialist_embedding = nn.Embedding(7, 128)
        self.planner_fusion = nn.Linear(384, 256)
        self.planner_norm = nn.LayerNorm(256)
        self.program_query = nn.Linear(256, 128)
        self.program_bias = nn.Linear(128, 1)
        self.planner_value = nn.Linear(256, 1)

    def _program_features(self, public_features: Tensor) -> Tensor:
        batch = public_features.shape[0]
        identity = torch.eye(17, dtype=public_features.dtype, device=public_features.device)
        identity = identity.unsqueeze(0).expand(batch, -1, -1)
        mode_identity = torch.eye(7, dtype=public_features.dtype, device=public_features.device)
        mode_identity = mode_identity[self.program_mode].unsqueeze(0).expand(batch, -1, -1)
        capability = torch.cat((
            torch.ones((batch, 1), dtype=public_features.dtype, device=public_features.device),
            public_features[:, 14:30],
        ), dim=1).unsqueeze(-1)
        width = public_features[:, 11:12].unsqueeze(1).expand(-1, 17, -1)
        height = public_features[:, 12:13].unsqueeze(1).expand(-1, 17, -1)
        climates = public_features[:, 7:11].unsqueeze(1).expand(-1, 17, -1)
        mode_state = public_features[:, :7][:, self.program_mode].unsqueeze(-1)
        zeros = torch.zeros((batch, 32), dtype=public_features.dtype, device=public_features.device)
        zeros = zeros.unsqueeze(1).expand(-1, 17, -1)
        return torch.cat((identity, mode_identity, capability, width, height, climates, mode_state, zeros), dim=2)

    def forward(
        self,
        public_features: Tensor,
        program_mask: Tensor,
        hidden_state: Tensor,
        recurrent_reset: Tensor,
    ) -> tuple[Tensor, Tensor, Tensor]:
        next_hidden = self.base_policy(public_features, hidden_state, recurrent_reset)
        domain = torch.tanh(self.domain_projection(functional.pad(public_features, (0, 32))))
        domain_kind = public_features[:, :7].argmax(dim=1)
        domain = domain + self.domain_kind_embedding(domain_kind)
        # The compact M22 adapter exposes one domain token, so its attention weight is exactly one.
        domain_summary = self.domain_value(domain)
        planner = functional.silu(self.planner_fusion(torch.cat((next_hidden, domain_summary), dim=1)))
        planner = self.planner_norm(planner + next_hidden)
        programs = torch.tanh(self.program_projection(self._program_features(public_features)))
        if self.architecture == "specialist-router-v1":
            programs = programs + self.specialist_embedding(self.program_mode).unsqueeze(0)
        logits = (programs * self.program_query(planner).unsqueeze(1)).sum(dim=-1) / (128.0 ** 0.5)
        logits = logits + self.program_bias(programs).squeeze(-1)
        logits = logits.masked_fill(torch.logical_not(program_mask), -1.0e9)
        value = self.planner_value(planner).squeeze(-1)
        return logits, value, next_hidden


def validate_checkpoint(path: pathlib.Path, contract_item: dict[str, Any]) -> None:
    require(path.is_absolute() and path.is_dir() and not path.is_symlink(),
            "checkpoint must be an absolute real directory")
    actual_names = sorted(item.name for item in path.iterdir())
    require(actual_names == contract_validator.CHECKPOINT_INVENTORY, "checkpoint inventory mismatch")
    declared = {item["name"]: item for item in contract_item["files"]}
    for name in actual_names:
        target = path / name
        require(target.is_file() and not target.is_symlink(), f"checkpoint entry is not a regular file: {name}")
        size = target.stat().st_size
        require(size <= MAXIMUM_CHECKPOINT_FILE_BYTES, f"checkpoint file exceeds byte bound: {name}")
        require(size == declared[name]["bytes"] and sha256_file(target) == declared[name]["sha256"],
                f"checkpoint file identity mismatch: {name}")
    require(path.name == contract_item["checkpoint_id"], "checkpoint directory/content address mismatch")


def example_inputs() -> tuple[Tensor, Tensor, Tensor, Tensor]:
    public = torch.zeros((2, 32), dtype=torch.float32)
    public[0, 0] = 1.0
    public[1, 3] = 1.0
    public[0, 7] = 1.0
    public[1, 10] = 1.0
    public[:, 11] = torch.tensor([1.0 / 32.0, 1.0 / 8.0])
    public[:, 12] = torch.tensor([1.0 / 32.0, 1.0 / 8.0])
    public[:, 13] = torch.tensor([1.0 / 64.0, 1.0 / 4.0])
    public[0, 14] = 1.0
    public[1, 21] = 1.0
    public[:, 31] = torch.tensor([0.25, 0.75])
    mask = torch.zeros((2, 17), dtype=torch.bool)
    mask[:, 0] = True
    mask[0, 1] = True
    mask[1, 8] = True
    hidden = torch.zeros((2, 256), dtype=torch.float32)
    reset = torch.tensor([True, False], dtype=torch.bool)
    return public, mask, hidden, reset


def canonicalize_onnx(raw: bytes) -> bytes:
    model = onnx.load_model_from_string(raw)
    require(len(model.opset_import) == 1 and model.opset_import[0].domain in {"", "ai.onnx"} and
            model.opset_import[0].version == 18, "exported graph does not have exact opset 18")
    model.producer_name = "openttd-rl"
    model.producer_version = "2.0.0"
    model.domain = "openttd-rl"
    model.model_version = 2
    model.doc_string = ""
    del model.metadata_props[:]
    model.graph.doc_string = ""
    for node in model.graph.node:
        node.doc_string = ""
    for value in list(model.graph.input) + list(model.graph.output) + list(model.graph.value_info):
        value.doc_string = ""
    onnx.checker.check_model(model, full_check=True)
    return model.SerializeToString(deterministic=True)


def export_bytes(model: nn.Module, inputs: tuple[Tensor, Tensor, Tensor, Tensor]) -> bytes:
    destination = io.BytesIO()
    torch.onnx.export(
        model,
        inputs,
        destination,
        export_params=True,
        opset_version=18,
        do_constant_folding=True,
        input_names=INPUT_NAMES,
        output_names=OUTPUT_NAMES,
        dynamic_axes={name: {0: "batch"} for name in INPUT_NAMES + OUTPUT_NAMES},
        dynamo=False,
        external_data=False,
    )
    return canonicalize_onnx(destination.getvalue())


def write_new(path: pathlib.Path, value: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
    finally:
        os.close(descriptor)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def export_one(architecture: str, checkpoint: pathlib.Path, output: pathlib.Path,
               contract_item: dict[str, Any]) -> dict[str, Any]:
    validate_checkpoint(checkpoint, contract_item)
    archive = torch.jit.load(str(checkpoint / "model.pt"), map_location="cpu")
    state = archive.state_dict()
    model = GeneralistDeploymentModel(architecture)
    result = model.load_state_dict(state, strict=True)
    require(not result.missing_keys and not result.unexpected_keys, "checkpoint state mapping is incomplete")
    model.eval()
    for parameter in model.parameters():
        require(torch.isfinite(parameter).all().item(), "checkpoint contains a nonfinite parameter")
    inputs = example_inputs()
    with torch.inference_mode():
        expected = model(*inputs)
        require(all(torch.isfinite(item).all().item() for item in expected), "native mirror smoke produced nonfinite output")
        first = export_bytes(model, inputs)
        second = export_bytes(model, inputs)
    require(first == second, "two same-process exports did not produce identical ONNX bytes")
    output.mkdir(mode=0o700)
    model_path = output / "model.onnx"
    write_new(model_path, first)
    report = {
        "schema_version": "openttd-rl-v2-m23-export-report-1",
        "status": "PASS",
        "architecture_id": architecture,
        "checkpoint_id": contract_item["checkpoint_id"],
        "checkpoint_model_sha256": next(item["sha256"] for item in contract_item["files"] if item["name"] == "model.pt"),
        "state_tensors": len(state),
        "onnx": {
            "bytes": len(first),
            "sha256": sha256_bytes(first),
            "opset": 18,
            "onnxruntime": "1.28.0",
            "inputs": INPUT_NAMES,
            "outputs": OUTPUT_NAMES,
            "dynamic_axis": "batch",
            "same_process_repeat_byte_identical": True,
        },
        "adapter": {
            "public_features": 32,
            "programs": 17,
            "hidden": 256,
            "functionally_cancelled_single_slot_attention": [
                "base_policy.entity_key", "base_policy.graph_query", "domain_key", "domain_query",
            ],
            "unused_training_outputs": [
                "base_policy.family_head", "base_policy.candidate_query", "base_policy.candidate_bias",
                "base_policy.value_head",
            ],
        },
    }
    write_new(output / "export-report.json", canonical_json(report))
    return report


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--monolithic-checkpoint", type=pathlib.Path, required=True)
    parser.add_argument("--specialist-checkpoint", type=pathlib.Path, required=True)
    parser.add_argument("--output-root", type=pathlib.Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        root = arguments.root.resolve()
        contract_validator.validate(root)
        output = arguments.output_root
        require(output.is_absolute() and not output.exists() and output.parent.is_dir() and not output.is_symlink(),
                "output root must be a new absolute path below an existing directory")
        output.mkdir(mode=0o700)
        contract = contract_validator.load(root / contract_validator.CONTRACT)
        items = {item["architecture_id"]: item for item in contract["checkpoint_packages"]["architectures"]}
        reports = []
        for architecture, checkpoint in (
            ("monolithic-generalist-v1", arguments.monolithic_checkpoint),
            ("specialist-router-v1", arguments.specialist_checkpoint),
        ):
            reports.append(export_one(architecture, checkpoint, output / architecture, items[architecture]))
        summary = {
            "schema_version": "openttd-rl-v2-m23-export-summary-1",
            "status": "PASS",
            "architectures": [item["architecture_id"] for item in reports],
            "models": [
                {"architecture_id": item["architecture_id"], "bytes": item["onnx"]["bytes"],
                 "sha256": item["onnx"]["sha256"]}
                for item in reports
            ],
        }
        write_new(output / "export-summary.json", canonical_json(summary))
        print("V2_M23_EXPORT=PASS " + " ".join(
            f"{item['architecture_id']}={item['onnx']['sha256']}" for item in reports
        ))
        return 0
    except (ExportError, contract_validator.M23ContractError, OSError, RuntimeError, ValueError) as exc:
        print(f"V2_M23_EXPORT=FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
