#!/usr/bin/env python3
"""Source, report, and fail-closed tests for M23 OpenTTD-integrated inference."""

from __future__ import annotations

import copy
import pathlib
import struct
import subprocess
import tempfile
import unittest

import m23_golden
import m23_ingame
import m23_package


class M23InGameSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = pathlib.Path(__file__).resolve().parents[3]
        cls.patch = (cls.root / m23_ingame.PATCH).read_text(encoding="utf-8")
        cls.equivalence = (cls.root / "training/v2/src/m23_equivalence.cpp").read_text(encoding="utf-8")
        cls.main = (cls.root / "training/v2/src/m23_onnx_evaluator_main.cpp").read_text(encoding="utf-8")
        cls.cmake = (cls.root / "training/v2/m23/CMakeLists.txt").read_text(encoding="utf-8")
        cls.runner = (cls.root / "scripts/v2/run_m23_ingame_equivalence.py").read_text(encoding="utf-8")

    @staticmethod
    def golden_bytes() -> bytes:
        output = bytearray(m23_golden.MAGIC)
        output.extend(struct.pack("<II", m23_golden.VERSION, 48))
        carried: list[list[list[float] | None]] = [[None, None], [None, None]]
        for architecture in range(2):
            for local in range(24):
                definition = m23_golden.generate_definition(architecture, local)
                output.extend(struct.pack(
                    "<BBBBBBHII", definition.architecture, definition.case_class, definition.sequence,
                    definition.step, definition.mask_pattern, definition.hidden_mode, 0,
                    definition.seed, definition.batch,
                ))
                case_id = definition.case_id.encode("ascii")
                output.extend(struct.pack("<H", len(case_id)))
                output.extend(case_id)
                output.extend(struct.pack(f"<{len(definition.public_features)}f", *definition.public_features))
                output.extend(bytes(definition.program_mask))
                output.extend(struct.pack(f"<{len(definition.initial_hidden)}f", *definition.initial_hidden))
                output.extend(bytes(definition.recurrent_reset))
                hidden = definition.initial_hidden
                if definition.hidden_mode == 1:
                    hidden = carried[architecture][definition.sequence] or []
                output.extend(struct.pack(f"<{len(hidden)}f", *hidden))
                logits = [0.0] * (definition.batch * m23_golden.PROGRAMS)
                output.extend(struct.pack(f"<{len(logits)}f", *logits))
                output.extend(struct.pack(f"<{definition.batch}f", *([0.0] * definition.batch)))
                next_hidden = [0.0] * (definition.batch * m23_golden.HIDDEN)
                output.extend(struct.pack(f"<{len(next_hidden)}f", *next_hidden))
                actions = []
                for row in range(definition.batch):
                    mask = definition.program_mask[
                        row * m23_golden.PROGRAMS:(row + 1) * m23_golden.PROGRAMS
                    ]
                    actions.append(mask.index(1))
                output.extend(struct.pack(f"<{len(actions)}q", *actions))
                if definition.case_class == 1:
                    carried[architecture][definition.sequence] = next_hidden
        return bytes(output)

    @staticmethod
    def package_report() -> dict[str, object]:
        return {
            "deployment_packages": [
                {"model_sha256": "1" * 64},
                {"model_sha256": "2" * 64},
            ],
        }

    def report_value(self, golden: pathlib.Path, runtime: str) -> dict[str, object]:
        records = m23_golden.decode(golden)
        cases = [{
            "action_exact": True,
            "batch": record.definition.batch,
            "case_id": record.definition.case_id,
            "hidden_absolute": 0.0,
            "hidden_input_absolute": 0.0,
            "hidden_relative": 0.0,
            "logits_absolute": 0.0,
            "logits_relative": 0.0,
            "passed": True,
            "value_absolute": 0.0,
            "value_relative": 0.0,
        } for record in records]
        return {
            "cases": cases,
            "failure_counts": {"action": 0, "float": 0, "total": 0},
            "golden": {"sha256": m23_package.sha256_file(golden)},
            "maximum_error": {key: 0.0 for key in m23_ingame.ERROR_KEYS},
            "models": {"monolithic_sha256": "1" * 64, "specialist_sha256": "2" * 64},
            "runtime": runtime,
            "schema_version": m23_ingame.REPORT_SCHEMA,
            "status": "PASS",
            "tolerance": {"absolute": 0.00005, "relative": 0.00005},
        }

    def validate_value(self, mutate: object | None = None) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            golden = (root / "golden.bin").resolve()
            golden.write_bytes(self.golden_bytes())
            value = self.report_value(golden, m23_ingame.INGAME_RUNTIME)
            if mutate is not None:
                mutate(value)  # type: ignore[operator]
            report = (root / "report.json").resolve()
            report.write_bytes(m23_package.canonical_json(value, newline=True))
            return m23_ingame.validate_equivalence_report(
                report, m23_ingame.INGAME_RUNTIME, golden, self.package_report(),
            )

    def test_source_patch_has_exact_bounded_scope(self) -> None:
        record = m23_ingame.validate_source_patch(self.root)
        self.assertEqual(record["path"], m23_ingame.PATCH.as_posix())
        self.assertEqual(record["bytes"], len(self.patch.encode("utf-8")))

    def test_patch_preserves_v1_a_and_m03_fd_pair_while_adding_v2_b(self) -> None:
        for token in (
            "M11 -A playback mode forbids", "-B bridge_or_config",
            "std::string_view(mgo.opt).find(':')", "scanner->rl_bridge_descriptors = mgo.opt",
            "scanner->rl_v2_neural_agent_config = mgo.opt",
        ):
            self.assertIn(token, self.patch)

    def test_patch_build_boundary_is_inference_only(self) -> None:
        lowered = self.patch.lower()
        for forbidden in ("libtorch", "libc10", "cuda", "python"):
            self.assertNotIn(forbidden, lowered)
        for required in ("m23_equivalence.cpp", "m23_golden.cpp", "m23_onnx.cpp", "OpenSSL::Crypto"):
            self.assertIn(required, self.patch)

    def test_patch_applies_exactly_to_retained_m22_source_when_available(self) -> None:
        source = pathlib.Path(
            "/home/thecl/.codex/artifacts/openttd-rl/v2-m22-followup-runtime-a/source"
        )
        if not source.is_dir():
            self.skipTest("retained M22 source is not present")
        completed = subprocess.run(
            ["git", "-C", str(source), "apply", "--check", "--whitespace=error-all",
             str((self.root / m23_ingame.PATCH).resolve())],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_equivalence_logic_is_shared_by_standalone_and_openttd(self) -> None:
        self.assertIn("run_m23_onnx_equivalence", self.main)
        self.assertIn("run_m23_onnx_equivalence", self.patch)
        self.assertIn("../src/m23_equivalence.cpp", self.cmake)
        self.assertIn(m23_ingame.STANDALONE_RUNTIME, self.equivalence)
        self.assertIn(m23_ingame.INGAME_RUNTIME, self.equivalence)

    def test_shared_equivalence_owns_recurrent_carry_and_every_output(self) -> None:
        for token in (
            "M23HiddenMode::Carry", "carried[architecture][record.definition.sequence]",
            "output.program_logits", "output.program_value", "output.next_hidden",
            "output.greedy_program == record.greedy_program",
        ):
            self.assertIn(token, self.equivalence)

    def test_refactored_standalone_runtime_remains_exact(self) -> None:
        self.assertIn('"onnxruntime-1.28.0-cpu"', self.main)
        self.assertIn("M23_ONNX_EQUIVALENCE=", self.main)
        self.assertIn("summary.failures == 0 ? 0 : 2", self.main)

    def test_source_config_is_canonical_absolute_and_greedy(self) -> None:
        for token in (
            "parsed.dump() == bytes", "configuration path must be absolute",
            'inference.at("mode") == "greedy"', 'inference.at("interval_ticks") == 128',
            "equivalence report must be a new file",
        ):
            self.assertIn(token, self.patch)

    def test_source_loads_and_pins_both_content_addressed_packages(self) -> None:
        for package_id in (
            "50060fd871d3c737b41bb4523748fbaac5047fed106e9ce0a9d1b36c7637f955",
            "d280683090b65eeea8e6cba1ab6ece3ca561a1b1d1708840f8616855ff44ac5a",
        ):
            self.assertIn(package_id, self.patch)
        self.assertEqual(self.patch.count("M23DeploymentPackage"), 3)

    def test_runner_network_isolates_and_counts_all_144_runtime_results(self) -> None:
        for token in (
            '"--unshare-net"', '"native": 48', '"standalone": 48', '"ingame": 48',
            '"total": 144', "reports_match_except_runtime", "dependency_closure",
        ):
            self.assertIn(token, self.runner)

    def test_valid_source_integrated_report_passes(self) -> None:
        value = self.validate_value()
        self.assertEqual(len(value["cases"]), 48)
        self.assertEqual(sum(item["batch"] for item in value["cases"]), 580)

    def test_runtime_case_and_status_mutations_fail_closed(self) -> None:
        mutations = (
            lambda value: value.__setitem__("runtime", m23_ingame.STANDALONE_RUNTIME),
            lambda value: value.__setitem__("status", "FAIL"),
            lambda value: value["cases"].pop(),
            lambda value: value["cases"][0].__setitem__("action_exact", False),
            lambda value: value["failure_counts"].__setitem__("total", 1),
            lambda value: value["maximum_error"].__setitem__("value_absolute", 0.1),
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(m23_ingame.M23InGameError):
                self.validate_value(mutation)

    def test_reports_may_differ_only_by_runtime_identity(self) -> None:
        left = {"runtime": m23_ingame.STANDALONE_RUNTIME, "status": "PASS"}
        right = {"runtime": m23_ingame.INGAME_RUNTIME, "status": "PASS"}
        self.assertTrue(m23_ingame.reports_match_except_runtime(left, right))
        right["status"] = "FAIL"
        self.assertFalse(m23_ingame.reports_match_except_runtime(left, right))

    def test_native_report_requires_exact_48_case_580_row_identity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            golden = (root / "golden.bin").resolve()
            golden.write_bytes(self.golden_bytes())
            value = {
                "architectures": list(m23_ingame.ARCHITECTURES), "cases": 48,
                "file": m23_ingame.file_record(golden), "rows": 580,
                "schema_version": m23_ingame.NATIVE_SCHEMA, "status": "PASS",
            }
            report = (root / "native.json").resolve()
            report.write_bytes(m23_package.canonical_json(value, newline=True))
            self.assertEqual(m23_ingame.validate_native_report(report, golden)["rows"], 580)
            value["rows"] = 579
            report.write_bytes(m23_package.canonical_json(value, newline=True))
            with self.assertRaises(m23_ingame.M23InGameError):
                m23_ingame.validate_native_report(report, golden)


if __name__ == "__main__":
    unittest.main()
