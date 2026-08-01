#!/usr/bin/env python3
"""Export and statically validate a fixed opset-18 graph with the pinned exporter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys

import onnx
import onnxscript
import torch


EXPECTED_VERSIONS = {
    "python": (3, 12),
    "torch": "2.13.0+cpu",
    "onnx": "1.22.0",
    "onnxscript": "0.7.1",
}


class ProbeModel(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.register_buffer(
            "weight",
            torch.arange(12, dtype=torch.float32).reshape(4, 3) / 10.0,
        )
        self.register_buffer(
            "bias",
            torch.tensor([-0.25, 0.0, 0.25], dtype=torch.float32),
        )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return torch.relu(torch.matmul(value, self.weight) + self.bias)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    options = parser.parse_args()
    output = options.output.resolve()
    if not output.is_absolute() or output.exists() or output.parent.is_symlink():
        raise SystemExit("EXPORTER_PROBE=FAIL --output must be a new absolute path")
    output.parent.mkdir(parents=True, exist_ok=True)

    actual_versions = {
        "python": sys.version_info[:2],
        "torch": torch.__version__,
        "onnx": onnx.__version__,
        "onnxscript": onnxscript.__version__,
    }
    if actual_versions != EXPECTED_VERSIONS:
        raise SystemExit(
            "EXPORTER_PROBE=FAIL version mismatch "
            + json.dumps({key: str(value) for key, value in actual_versions.items()}, sort_keys=True)
        )
    if os.environ.get("PIP_NO_INDEX") != "1":
        raise SystemExit("EXPORTER_PROBE=FAIL PIP_NO_INDEX=1 is required")

    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    model = ProbeModel().eval()
    example = torch.tensor(
        [[1.0, -2.0, 0.5, 3.0], [2.0, -1.0, 0.0, 0.0]],
        dtype=torch.float32,
    )
    expected = torch.tensor(
        [[2.15, 2.65, 3.15], [0.0, 0.0, 0.15]],
        dtype=torch.float32,
    )
    torch.testing.assert_close(model(example), expected, rtol=0.0, atol=1.0e-6)

    program = torch.onnx.export(
        model,
        (example,),
        output,
        input_names=["input"],
        output_names=["output"],
        opset_version=18,
        dynamo=True,
        external_data=False,
        optimize=True,
        verify=False,
        report=False,
    )
    if program is None or not output.is_file():
        raise SystemExit("EXPORTER_PROBE=FAIL exporter did not return a program")

    graph = onnx.load(output, load_external_data=False)
    onnx.checker.check_model(graph, full_check=True)
    default_opsets = [item.version for item in graph.opset_import if item.domain in ("", "ai.onnx")]
    if default_opsets != [18]:
        raise SystemExit(f"EXPORTER_PROBE=FAIL unexpected default opsets: {default_opsets}")
    if [value.name for value in graph.graph.input] != ["input"]:
        raise SystemExit("EXPORTER_PROBE=FAIL input name drift")
    if [value.name for value in graph.graph.output] != ["output"]:
        raise SystemExit("EXPORTER_PROBE=FAIL output name drift")
    if {value.name for value in graph.graph.initializer} != {"weight", "bias"}:
        raise SystemExit("EXPORTER_PROBE=FAIL initializer name drift")
    if any(initializer.data_location == onnx.TensorProto.EXTERNAL for initializer in graph.graph.initializer):
        raise SystemExit("EXPORTER_PROBE=FAIL external tensor data is forbidden")
    operator_types = sorted({node.op_type for node in graph.graph.node})
    if operator_types != ["Add", "MatMul", "Relu"]:
        raise SystemExit(f"EXPORTER_PROBE=FAIL unexpected operators: {operator_types}")

    print(
        "EXPORTER_PROBE=PASS"
        f" torch={torch.__version__}"
        f" onnx={onnx.__version__}"
        f" onnxscript={onnxscript.__version__}"
        " opset=18"
        f" operators={','.join(operator_types)}"
        f" model_sha256={sha256_file(output)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
