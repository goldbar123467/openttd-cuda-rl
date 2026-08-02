#!/usr/bin/env python3
"""Frozen-contract, architecture, CUDA, and retained-evidence guards for M08."""

from __future__ import annotations

import copy
import json
import os
import pathlib
import tempfile
import unittest

import jsonschema

import validate_m08_architecture_contract
import validate_m08_architecture_smoke
import validate_m08_cuda_report
import validate_m08_live_architectures


class V1M08ArchitectureCudaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.contract = validate_m08_architecture_contract.validate(
            cls.root / "config/v1/m08-architecture-cuda-contract.json",
            cls.root / "docs/project/schema/v1-m08-architecture-cuda-contract.schema.json",
        )

    def test_contract_freezes_three_architectures_shapes_devices_and_tolerances(self) -> None:
        self.assertEqual(
            [item["id"] for item in self.contract["architectures"]],
            ["structured-mlp-v1", "spatial-cnn-v1", "combined-cnn-mlp-v1"],
        )
        self.assertEqual(self.contract["inputs"]["spatial"]["model_shape"], [32, 32, 32])
        self.assertEqual(self.contract["backend"]["reference_device"], "cpu")
        self.assertEqual(self.contract["backend"]["accelerated_device"], "cuda:0")
        self.assertEqual(self.contract["backend"]["dtype"], "float32")
        self.assertFalse(self.contract["backend"]["mixed_precision"])
        self.assertEqual(self.contract["parity"]["forward_absolute"], 1e-4)
        self.assertEqual(self.contract["profiling"]["batch_sizes"], [1, 4, 16, 64, 256, 1024])

    def test_contract_schema_and_identity_fail_closed_on_semantic_mutation(self) -> None:
        schema = json.loads(
            (self.root / "docs/project/schema/v1-m08-architecture-cuda-contract.schema.json").read_text(encoding="utf-8")
        )
        mutation = copy.deepcopy(self.contract)
        mutation["backend"]["mixed_precision"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(mutation)
        mutation = copy.deepcopy(self.contract)
        mutation["profiling"]["minimum_accepted_speedup"] = 1.0
        self.assertNotEqual(
            validate_m08_architecture_contract.compatibility_sha256(mutation),
            mutation["identity"]["compatibility_sha256"],
        )

    def test_native_sources_implement_cnn_combined_and_real_device_training(self) -> None:
        source = "\n".join(
            (self.root / relative).read_text(encoding="utf-8")
            for relative in (
                "training/v1/src/multimodal_model.cpp",
                "training/v1/src/multimodal_trainer.cpp",
                "training/v1/src/m08_cuda_main.cpp",
                "training/v1/src/m08_trainer_main.cpp",
            )
        )
        for token in (
            "torch::nn::Conv2d", "spatial_projection", "torch::cat", "MultiModalPpoTrainer::update",
            "torch::optim::Adam", "torch::Device(torch::kCUDA, 0)", "torch::cuda::synchronize",
            "forward-backward-adam-update", "batched-inference",
        ):
            self.assertIn(token, source)

    def test_environment_semantic_boundary_and_candidate_dispositions_are_explicit(self) -> None:
        self.assertEqual(self.contract["device_semantics"]["openttd_simulation"], "cpu-only")
        self.assertEqual(self.contract["device_semantics"]["observation_encoding"], "cpu-only")
        dispositions = self.contract["profiling"]["candidate_dispositions"]
        self.assertEqual(dispositions["observation-preprocessing"], "cpu-retained-no-transform-to-accelerate")
        live_source = (self.root / "scripts/v1/run_m08_live_architectures.py").read_text(encoding="utf-8")
        self.assertIn('"final_evaluation_accessed": False', live_source)
        self.assertIn("M06_EXECUTABLE_SHA256", live_source)

    def test_failure_classes_are_clear_and_fail_closed(self) -> None:
        cuda_source = (self.root / "training/v1/src/m08_cuda_main.cpp").read_text(encoding="utf-8")
        trainer_source = (self.root / "training/v1/src/multimodal_trainer.cpp").read_text(encoding="utf-8")
        for token in ("cuda-unavailable", "cuda-unsupported", "cuda-out-of-memory", "--inject-oom"):
            self.assertIn(token, cuda_source + trainer_source)
        self.assertIn("device-unsupported", trainer_source)

    def test_retained_cuda_and_architecture_smoke_evidence_when_supplied(self) -> None:
        cuda_report = os.environ.get("M08_CUDA_REPORT")
        cpu_smoke = os.environ.get("M08_CPU_SMOKE_REPORT")
        cuda_smoke = os.environ.get("M08_CUDA_SMOKE_REPORT")
        supplied = [cuda_report, cpu_smoke, cuda_smoke]
        if not any(supplied):
            return
        self.assertTrue(all(supplied), "all paired M08 neural evidence paths must be supplied together")
        validate_m08_cuda_report.validate(
            pathlib.Path(cuda_report),
            self.root / "docs/project/schema/v1-m08-cuda-gate-report.schema.json",
        )
        validate_m08_architecture_smoke.validate(
            pathlib.Path(cpu_smoke),
            pathlib.Path(cuda_smoke),
            self.root / "docs/project/schema/v1-m08-architecture-smoke.schema.json",
        )

    def test_retained_live_evidence_and_negative_mutation_when_supplied(self) -> None:
        live_path = os.environ.get("M08_LIVE_MANIFEST")
        if not live_path:
            return
        schema = self.root / "docs/project/schema/v1-m08-live-architectures.schema.json"
        manifest = validate_m08_live_architectures.validate(pathlib.Path(live_path), schema)
        mutation = copy.deepcopy(manifest)
        mutation["environment_semantics"]["final_evaluation_accessed"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "mutation.json"
            path.write_text(json.dumps(mutation), encoding="utf-8")
            with self.assertRaises((jsonschema.ValidationError, validate_m08_live_architectures.M08LiveError)):
                validate_m08_live_architectures.validate(path, schema)


if __name__ == "__main__":
    unittest.main()
