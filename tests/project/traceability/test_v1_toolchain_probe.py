#!/usr/bin/env python3
"""Unit and mutation tests for the fail-closed V1 toolchain probe runner."""

from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest
import zipfile

import run_toolchain_probe


class V1ToolchainProbeTests(unittest.TestCase):
    def test_exact_version_guard_passes_and_mismatch_fails(self) -> None:
        self.assertEqual(
            run_toolchain_probe.require_exact("CMake", "3.28.3", "3.28.3"),
            "3.28.3",
        )
        with self.assertRaisesRegex(
            run_toolchain_probe.ToolchainProbeError,
            "CMake version mismatch: expected=3.28.3 actual=3.29.0",
        ):
            run_toolchain_probe.require_exact("CMake", "3.29.0", "3.28.3")

    def test_missing_executable_fails_explicitly(self) -> None:
        with self.assertRaisesRegex(
            run_toolchain_probe.ToolchainProbeError,
            "missing required executable",
        ):
            run_toolchain_probe.resolve_executable(
                "openttd-rl-intentionally-absent-tool", "fixture"
            )

    def test_gpu_inventory_is_structured_and_rejects_bad_memory(self) -> None:
        inventory = run_toolchain_probe.parse_gpu_inventory(
            "NVIDIA Fixture, 12.0, 16384, 610.88\n"
        )
        self.assertEqual(inventory[0]["index"], 0)
        self.assertEqual(inventory[0]["compute_capability"], "12.0")
        self.assertEqual(inventory[0]["memory_total_mib"], 16384)
        with self.assertRaisesRegex(
            run_toolchain_probe.ToolchainProbeError,
            "invalid nvidia-smi memory",
        ):
            run_toolchain_probe.parse_gpu_inventory("NVIDIA Fixture, 12.0, bad, 610.88\n")

    def test_ctest_inventory_requires_the_complete_exact_set(self) -> None:
        payload = {
            "tests": [
                {"name": name} for name in reversed(run_toolchain_probe.EXPECTED_TESTS)
            ]
        }
        self.assertEqual(
            run_toolchain_probe.parse_ctest_inventory(json.dumps(payload)),
            list(run_toolchain_probe.EXPECTED_TESTS),
        )
        payload["tests"].pop()
        with self.assertRaisesRegex(
            run_toolchain_probe.ToolchainProbeError,
            "CTest inventory mismatch",
        ):
            run_toolchain_probe.parse_ctest_inventory(json.dumps(payload))

    def test_cuda_image_parser_requires_real_and_virtual_sm120(self) -> None:
        parsed = run_toolchain_probe.parse_cuda_images(
            "ELF file 1: fixture.1.sm_120.cubin\n",
            "PTX file 1: fixture.1.sm_120.ptx\n",
        )
        self.assertEqual(parsed, {"cubin_sm": ["120"], "ptx_compute": ["120"]})
        with self.assertRaisesRegex(
            run_toolchain_probe.ToolchainProbeError,
            "CUDA PTX image mismatch",
        ):
            run_toolchain_probe.parse_cuda_images(
                "fixture.sm_120.cubin\n", "fixture.compute_90.ptx\n"
            )

    def test_cuda_compile_command_requires_real_and_virtual_targets(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = pathlib.Path(raw) / "compile_commands.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "file": "/source/cuda_probe.cu",
                            "command": "nvcc --generate-code=arch=compute_120,code=[sm_120] "
                            "--generate-code=arch=compute_120,code=[compute_120]",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            run_toolchain_probe.validate_cuda_compile_commands(path)
            value = json.loads(path.read_text(encoding="utf-8"))
            value[0]["command"] = "nvcc --generate-code=arch=compute_120,code=[sm_120]"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(
                run_toolchain_probe.ToolchainProbeError,
                "lacks required target.*compute_120",
            ):
                run_toolchain_probe.validate_cuda_compile_commands(path)

    def test_runtime_dependency_parser_is_path_independent_and_fail_closed(self) -> None:
        first = run_toolchain_probe.parse_runtime_dependencies(
            "linux-vdso.so.1 (0x0)\nlibc.so.6 => /one/libc.so.6 (0x1)\n/lib64/ld-linux-x86-64.so.2 (0x2)\n"
        )
        second = run_toolchain_probe.parse_runtime_dependencies(
            "linux-vdso.so.1 (0x9)\nlibc.so.6 => /two/libc.so.6 (0x8)\n/lib64/ld-linux-x86-64.so.2 (0x7)\n"
        )
        self.assertEqual(first, second)
        with self.assertRaisesRegex(
            run_toolchain_probe.ToolchainProbeError,
            "unresolved runtime dependency",
        ):
            run_toolchain_probe.parse_runtime_dependencies("libmissing.so => not found\n")

    def test_wheel_inventory_uses_metadata_and_rejects_version_drift(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            wheel = root / "fixture-1.2.3-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr(
                    "fixture-1.2.3.dist-info/METADATA",
                    "Metadata-Version: 2.1\nName: Fixture_Project\nVersion: 1.2.3\n\n",
                )
            artifact = {
                "id": "exporter-fixture",
                "relative_cache_path": wheel.name,
                "version": "1.2.3",
            }
            self.assertEqual(
                run_toolchain_probe.wheel_distributions(root, [artifact]),
                [{"name": "Fixture_Project", "version": "1.2.3"}],
            )
            artifact["version"] = "1.2.4"
            with self.assertRaisesRegex(
                run_toolchain_probe.ToolchainProbeError,
                "wheel version mismatch",
            ):
                run_toolchain_probe.wheel_distributions(root, [artifact])

    def test_identity_and_human_output_are_deterministic(self) -> None:
        base = {
            "schema_version": run_toolchain_probe.SCHEMA_VERSION,
            "profile_id": "fixture",
            "host": {
                "architecture": "x86_64",
                "os": {"id": "ubuntu", "version_id": "24.04"},
                "gpus": [
                    {
                        "name": "GPU",
                        "compute_capability": "12.0",
                        "driver_version": "1.0",
                    }
                ],
            },
            "tools": {
                "gcc": "13.3.0",
                "gxx": "13.3.0",
                "cmake": "3.28.3",
                "ctest": "3.28.3",
                "ninja": "1.11.1",
                "nvcc": "13.0.88",
                "cuobjdump": "13.0.85",
                "python": "3.12.3",
            },
            "dependencies": {
                "cache": {"artifact_count": 25, "total_artifact_bytes": 1556894253},
                "libtorch": {"version": "2.13.0+cu130", "cxx11_abi": 1},
                "onnxruntime": {"version": "1.28.0"},
                "exporter": [{}] * 17,
            },
            "products": {
                "onnx_model": {
                    "opset": 18,
                    "sha256": run_toolchain_probe.EXPECTED_MODEL_SHA256,
                }
            },
            "tests": [{"result": "PASS"}] * 4,
            "result": "PASS",
        }
        first = run_toolchain_probe.build_manifest(copy.deepcopy(base))
        second = run_toolchain_probe.build_manifest(copy.deepcopy(base))
        self.assertEqual(first, second)
        self.assertEqual(
            run_toolchain_probe.render_human_report(first),
            run_toolchain_probe.render_human_report(second),
        )
        changed = copy.deepcopy(base)
        changed["tools"]["python"] = "3.12.4"
        self.assertNotEqual(
            first["probe_identity_sha256"],
            run_toolchain_probe.build_manifest(changed)["probe_identity_sha256"],
        )

    def test_write_new_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = pathlib.Path(raw) / "output.txt"
            run_toolchain_probe.write_new(output, "first\n")
            with self.assertRaisesRegex(
                run_toolchain_probe.ToolchainProbeError,
                "refusing to overwrite output",
            ):
                run_toolchain_probe.write_new(output, "second\n")
            self.assertEqual(output.read_text(encoding="utf-8"), "first\n")


if __name__ == "__main__":
    unittest.main()
